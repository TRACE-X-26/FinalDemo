"""Python backend exchanges real CRC-protected frames with production C code.

The child process replaces only hardware callbacks; it never opens a serial port.
"""
import csv
import io
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from diagnostic_platform.automated_engine import AutomatedTestEngine
from diagnostic_platform.motor_csv import render_motor_csv
from diagnostic_platform.protocol import decode_message
from diagnostic_platform.stm32 import STM32SerialConnection
from diagnostic_platform.verify_stm32 import verify_connection

ROOT = Path(__file__).resolve().parents[1]


class CTransport:
    def __init__(self, executable, mode="normal"):
        self.executable, self.mode = executable, mode
        self.epoch = time.monotonic()
        self.history = bytearray()
        self.seen = 0
        self.responses = []
        self.commands = []

    def write(self, data):
        message = decode_message(data)
        self.commands.append(message.payload.get('command', 'HEARTBEAT'))
        timestamp = int((time.monotonic()-self.epoch)*1000)
        self.history.extend(f'FIXTURE_TICK {timestamp}\n'.encode()+data)
        # Replay a deterministic C session with its original request timestamps.
        # This avoids OS pipe scheduling changing the fixture's simulated clock.
        output = subprocess.check_output([str(self.executable), self.mode],
                                         input=bytes(self.history), timeout=3)
        lines = output.splitlines(keepends=True)
        self.responses.extend(lines[self.seen:])
        self.seen = len(lines)
        return len(data)

    def readline(self):
        if not self.responses:
            return b''
        return self.responses.pop(0)

    def close(self):
        pass


class BackendFirmwareContractTests(unittest.TestCase):
    station_enabled = False
    @classmethod
    def setUpClass(cls):
        cc = shutil.which('cc')
        if not cc:
            raise unittest.SkipTest('Host C compiler unavailable')
        cls.build = tempfile.TemporaryDirectory()
        cls.executable = Path(cls.build.name) / 'firmware'
        subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DADS_USE_DIRECT_MOTOR_PROFILE=1',
                        f'-DADS_STATION_CONTROL_ENABLED={int(cls.station_enabled)}', '-I', str(ROOT/'ADS/Core/Inc'),
                        *(str(ROOT/'ADS/Core/Src'/name) for name in
                          ('ads_protocol.c', 'ads_test.c', 'ads_acquisition.c', 'ads_protection.c')),
                        str(ROOT/'tests/backend_firmware_harness.c'), '-o', str(cls.executable)],
                       check=True, capture_output=True)
        # Initialize the newly compiled executable on the test's main thread
        # before the backend worker starts (not a serial/device operation).
        subprocess.run([str(cls.executable)], input=b'', check=True,
                       capture_output=True, timeout=15)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.transports = []
        self.mode = 'normal'
        def factory(*_):
            transport = CTransport(self.executable, self.mode)
            self.transports.append(transport)
            return STM32SerialConnection(port='C_FIXTURE_ONLY', require_crc=True,
                allow_motor_control=True, command_timeout=2,
                transport_factory=lambda *_: transport)
        self.engine = AutomatedTestEngine(Path(self.temp.name)/'runs.db',
            hardware_profile_path=str(ROOT/'deploy/pi/supervised-operator-profile.json'),
            connection_factory=factory)

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def run_motor(self, pwm=50, duration=300):
        self.engine.start({'mode':'hardware', 'tests':[f'pwm_{pwm}'], 'duration_ms':duration})
        self.engine._thread.join(timeout=6)
        self.assertFalse(self.engine._thread.is_alive())
        return self.engine.store.get(self.engine.current['id'])

    def test_read_only_handshake_uses_current_c_firmware(self):
        result = self.engine.preflight()
        self.assertTrue(result['ready'], result['reason'])
        self.assertEqual(result['capabilities']['firmware_version'], '0.8.0-motor-telemetry')
        self.assertEqual(result['capabilities']['fixed_pwm_percent'], 50)
        self.engine.hardware_runtime.validate_motor_protections(result['capabilities'])
        self.assertEqual(self.transports[0].commands,
                         ['GET_CAPABILITIES','GET_STATUS','READ_MEASUREMENTS','GET_STATUS'])

    def test_connection_verifier_accepts_enabled_but_stopped_c_firmware(self):
        def factory(**settings):
            transport = CTransport(self.executable)
            self.transports.append(transport)
            return STM32SerialConnection(**settings, transport_factory=lambda *_: transport)
        result = verify_connection('C_FIXTURE_ONLY', require_crc=True, connection_factory=factory)
        self.assertTrue(result['hardware_control'])
        self.assertTrue(result['heartbeat_alive'])
        self.assertEqual(result['firmware_version'], '0.8.0-motor-telemetry')
        self.assertEqual(self.transports[0].commands,
                         ['GET_STATUS','GET_CAPABILITIES','GET_FAULTS','HEARTBEAT'])

    def test_complete_motor_capture_and_csv_against_c_firmware(self):
        run = self.run_motor()
        self.assertEqual(run['state'], 'COMPLETED', run.get('reason'))
        self.assertTrue(run['stop_confirmed'])
        self.assertTrue(run['samples'])
        self.assertEqual(run['source'], 'stm32_serial')
        self.assertEqual(run['applied_pwm_percent'], 0)
        commands = self.transports[0].commands
        expected = ['ARM_TEST','PREPARE_TEST_POWER','SET_PWM','START_TEST','STOP_TEST']
        self.assertEqual([c for c in commands if c in expected], expected)
        self.assertTrue(any(s['raw']['measurements']['voltage']['value']==12 for s in run['samples']))
        self.assertIn('RPM_UNCALIBRATED', run['warnings'])
        self.assertIsNone(run['health_score'])
        rows = list(csv.DictReader(io.StringIO(render_motor_csv(run))))
        self.assertTrue(any(r['record_type']=='MOTOR_START' for r in rows))
        self.assertTrue(any(r['record_type']=='MOTOR_STOP' for r in rows))
        self.assertEqual(rows[-1]['stop_confirmed'], 'True')

    def test_dashboard_api_runs_and_exports_actual_c_protocol_exchange(self):
        from fastapi.testclient import TestClient
        import api.main as main
        # This fixture owns its engine. Do not start the application's separate
        # lifespan, which would create another owner and background serial reader.
        client = TestClient(main.app)
        try:
            with patch.object(main, 'automated_engine', self.engine):
                preflight = client.post('/api/motor/hardware/preflight')
                self.assertEqual(preflight.status_code, 200)
                self.assertTrue(preflight.json()['ready'])
                response = client.post('/api/automated/runs', json={
                    'mode':'hardware','tests':['pwm_50'],'duration_ms':300})
                self.assertEqual(response.status_code, 201, response.text)
                run_id = response.json()['id']
                self.engine._thread.join(timeout=6)
                run = client.get('/api/automated/runs/'+run_id).json()
                self.assertEqual(run['state'], 'COMPLETED', run.get('reason'))
                self.assertTrue(run['stop_confirmed'])
                export = client.get('/api/automated/runs/'+run_id+'/csv')
                self.assertEqual(export.status_code, 200)
                self.assertIn('MOTOR_START', export.text)
                self.assertIn('MOTOR_STOP', export.text)
        finally:
            client.close()

    def test_wrong_pwm_returns_actual_firmware_rejection_and_stops(self):
        run = self.run_motor(pwm=25)
        self.assertEqual(run['state'], 'FAILED')
        self.assertIn('PWM_OUT_OF_RANGE', run['reason'])
        self.assertTrue(run['stop_confirmed'])
        self.assertNotIn('START_TEST', self.transports[0].commands)

    def test_zero_voltage_after_confirmed_completion_is_not_running_undervoltage(self):
        self.mode = 'complete-on-measure'
        run = self.run_motor()
        self.assertEqual(run['state'], 'COMPLETED', run.get('reason'))
        self.assertTrue(run['stop_confirmed'])
        self.assertTrue(any(s['raw']['measurements']['voltage']['value']==0 and
                            s['raw']['motor_state']=='STOPPED' for s in run['samples']))

    def test_telemetry_quality_and_electrical_values_do_not_block_motor(self):
        for mode in ('missing-supply','high-current','high-voltage','powered-idle',
                     'invalid-electrical','stale-electrical'):
            with self.subTest(mode=mode):
                self.mode=mode
                run=self.run_motor()
                self.assertEqual(run['state'],'COMPLETED',run.get('reason'))
                self.assertTrue(run['stop_confirmed'])
                caps=run['device_capabilities']
                self.assertFalse(caps['electrical_limits_enabled'])
                self.assertFalse(caps['motor_sensor_gating_enabled'])
                self.assertEqual(caps['power_check_mode'],'RELAY_SETTLE_ONLY')
                commands=self.transports[-1].commands
                self.assertIn('SET_PWM',commands)
                self.assertIn('START_TEST',commands)
                if mode in ('invalid-electrical','stale-electrical'):
                    self.assertTrue(any(not sample['raw']['measurements']['voltage']['valid']
                                        for sample in run['samples']))
                    self.assertTrue(any(sample['raw']['measurements']['voltage']['value'] is None
                                        for sample in run['samples']))

    def test_incomplete_telemetry_policy_is_rejected(self):
        from diagnostic_platform.hardware_runtime import HardwareRuntime,RunRejected
        self.engine.preflight()
        caps=self.engine.hardware_runtime.snapshot()['capabilities']
        for key in ('motor_sensor_gating_enabled','power_check_mode','supply_sensing',
                    'heartbeat_timeout_ms','power_check_required'):
            changed=dict(caps);changed.pop(key)
            with self.subTest(key=key),self.assertRaises(RunRejected):
                HardwareRuntime.validate_motor_protections(changed)
