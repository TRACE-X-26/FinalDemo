"""Version 0.9 station workflow against production C protocol/controller code."""
import json
import subprocess
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from diagnostic_platform.hardware_runtime import RunRejected
from diagnostic_platform.protocol import command_message, encode_message, decode_message, ProtocolMessage, MessageType, CommandName
from diagnostic_platform.stm32 import STM32SerialConnection, CommunicationTimeout
from tests import test_backend_firmware_contract as fixtures


class StationControlTests(unittest.TestCase):
    station_enabled = True

    @classmethod
    def setUpClass(cls):
        fixtures.BackendFirmwareContractTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.BackendFirmwareContractTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixtures.BackendFirmwareContractTests.setUp(self)
        self.board = fixtures.CTransport(self.executable)
        self.transports.append(self.board)
        profile=json.loads(Path(self.engine.hardware_profile_path).read_text())
        profile['serial_identity']='C_FIXTURE_ONLY'
        profile_path=Path(self.temp.name)/'profile.json'
        profile_path.write_text(json.dumps(profile))
        self.engine.hardware_profile_path=str(profile_path)
        self.engine.connection_factory = lambda *_: STM32SerialConnection(
            port='C_FIXTURE_ONLY', require_crc=True, allow_motor_control=True,
            command_timeout=2, transport_factory=lambda *_: self.board)

    def tearDown(self):
        fixtures.BackendFirmwareContractTests.tearDown(self)

    def wait_state(self, state):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            run=self.engine.snapshot()
            if run and run['state']==state:return run
            if run and run.get('ended_at'):self.fail(str(run))
            time.sleep(.01)
        self.fail(f'Timed out waiting for {state}: {self.engine.snapshot()}')

    def prepare_motor(self):
        self.engine.station.select('MOTOR')
        self.engine.station.confirm_power(200,True)
        return self.wait_state('POWER_READY')

    def test_selection_and_unconfirmed_requests_never_send_power_commands(self):
        self.engine.station.select('MOTOR')
        self.assertFalse(self.board.commands)
        with self.assertRaises(RunRejected):self.engine.station.confirm_power(200,False)
        with self.assertRaises(RunRejected):self.engine.station.start_motor(200)
        self.assertFalse(self.board.commands)

    def test_selection_waits_for_readonly_poll_without_power_commands(self):
        self.engine._mutex.acquire()
        timer=threading.Timer(.05,self.engine._mutex.release)
        timer.start()
        try:
            result=self.engine.station.select('CIRCUIT')
            self.assertEqual(result['selected_branch'],'CIRCUIT')
            self.assertFalse(self.board.commands)
        finally:timer.join()

    def test_confirm_motor_keeps_pwm_zero_until_explicit_start(self):
        run=self.prepare_motor()
        self.assertEqual(run['applied_pwm_percent'],0)
        self.assertTrue(run['motor_relay_requested_on'])
        self.assertNotIn('SET_PWM',self.board.commands)
        self.assertNotIn('START_TEST',self.board.commands)
        self.engine.station.start_motor(200)
        self.engine._thread.join(timeout=8)
        run=self.engine.snapshot()
        self.assertEqual(run['state'],'COMPLETED',run.get('reason'))
        self.assertTrue(run['stop_confirmed'])
        self.assertEqual(self.board.commands.count('START_TEST'),1)
        self.assertEqual(run['applied_pwm_percent'],0)

    def test_reset_during_power_ready_clears_selection_and_never_starts_pwm(self):
        self.prepare_motor()
        with self.assertRaises(RunRejected):self.engine.station.select('CIRCUIT')
        with self.assertRaises(RunRejected):self.engine.station.confirm_power(200,True)
        result=self.engine.station.reset()
        self.assertTrue(result['off_confirmed'],result)
        self.assertIsNone(self.engine.circuit_power.selected_branch)
        self.assertEqual(self.engine.snapshot()['state'],'CANCELLED')
        self.assertNotIn('START_TEST',self.board.commands)
        self.assertTrue(self.engine.station.reset()['off_confirmed'])
        with self.assertRaises(RunRejected):self.engine.station.start_motor(200)

    def test_reset_during_running_motor_confirms_both_relays_and_zero_pwm(self):
        self.prepare_motor()
        self.engine.station.start_motor(2000)
        self.wait_state('RUNNING')
        result=self.engine.station.reset()
        self.assertTrue(result['off_confirmed'],result)
        self.assertEqual(self.engine.snapshot()['applied_pwm_percent'],0)
        self.assertIsNone(self.engine.circuit_power.selected_branch)
        self.assertEqual(self.board.commands.count('START_TEST'),1)

    def test_circuit_power_with_missing_ina_still_reports_invalid_measurements(self):
        self.engine.hardware_runtime.enabled=True
        self.engine.station.select('CIRCUIT')
        self.engine.station.confirm_power(200,True)
        self.engine.circuit_power._thread.join(timeout=8)
        state=self.engine.circuit_power.snapshot()
        self.assertEqual(state['state'],'STOPPED',state)
        self.assertTrue(state['stop_confirmed'])
        self.assertFalse(state['measurements']['valid'])
        self.assertIsNone(state['measurements']['measurements']['voltage']['value'])
        self.assertNotIn('START_TEST',self.board.commands)

    def test_reset_during_circuit_power_and_reconfirmation_of_other_branch(self):
        self.engine.hardware_runtime.enabled=True
        self.engine.station.select('CIRCUIT')
        self.engine.station.confirm_power(2000,True)
        deadline=time.monotonic()+8
        while self.engine.circuit_power.snapshot()['state']!='POWERED':
            self.assertLess(time.monotonic(),deadline)
            time.sleep(.01)
        self.assertTrue(self.engine.station.reset()['off_confirmed'])
        self.prepare_motor()
        self.assertTrue(self.engine.station.reset()['off_confirmed'])

    def test_lost_reset_reply_is_never_reported_as_off(self):
        original=self.board.write
        def write(data):
            if decode_message(data).payload.get('command')=='RESET_ALL':
                raise CommunicationTimeout('Injected lost reset acknowledgment')
            return original(data)
        with patch.object(self.board,'write',side_effect=write):
            result=self.engine.station.reset()
        self.assertFalse(result['off_confirmed'])
        self.assertIn('Off not confirmed',result['reason'])
        self.assertIsNone(result['selected_branch'])

    def test_api_confirm_start_and_reset_use_actual_c_crc_exchange(self):
        from fastapi.testclient import TestClient
        import api.main as main
        client=TestClient(main.app)
        try:
            with patch.object(main,'automated_engine',self.engine):
                self.assertEqual(client.post('/api/station/select',json={'branch':'MOTOR'}).status_code,200)
                rejected=client.post('/api/station/confirm-power',json={'duration_ms':200})
                self.assertEqual(rejected.status_code,409)
                confirmed=client.post('/api/station/confirm-power',json={'duration_ms':200,'confirmed':True})
                self.assertEqual(confirmed.status_code,200,confirmed.text)
                self.wait_state('POWER_READY')
                response=client.post('/api/station/motor/start',json={'duration_ms':200})
                self.assertEqual(response.status_code,200,response.text)
                self.engine._thread.join(timeout=8)
                result=client.post('/api/station/reset')
                self.assertEqual(result.status_code,200,result.text)
                self.assertTrue(result.json()['off_confirmed'])
                state=client.get('/api/station/status').json()
                self.assertIsNone(state['selected_branch'])
                self.assertEqual(state['dashboard_version'],'0.9.0')
        finally:client.close()

    def wire(self, entries):
        data=b''
        for tick,command,seq,args in entries:
            message=ProtocolMessage(MessageType.HEARTBEAT,seq,'STM32-ADS',{},0) if command=='HEARTBEAT' else command_message(CommandName(command),seq,arguments=args)
            data+=f'FIXTURE_TICK {tick}\n'.encode()+encode_message(message,checksum=True)
        output=subprocess.check_output([str(self.executable)],input=data,timeout=5)
        return [decode_message(line) for line in output.splitlines()]

    def test_firmware_requires_confirmation_and_blocks_conflicting_branch(self):
        replies=self.wire([(0,'HEARTBEAT',1,{}),(0,'ARM_TEST',2,{}),
            (0,'PREPARE_TEST_POWER',3,{}),
            (0,'PREPARE_TEST_POWER',4,{'supervised_confirmed':True}),
            (50,'GET_STATUS',5,{}),(50,'ARM_CIRCUIT',6,{'supervised_confirmed':True}),
            (50,'RESET_ALL',1,{}),(50,'START_TEST',7,{'pwm_percent':50,'duration_ms':100,'direction':'FORWARD'})])
        results={x.payload['reply_to']:x.payload['result'] for x in replies if 'result' in x.payload}
        self.assertEqual(results[3]['reason'],'BRANCH_CONFIRMATION_REQUIRED')
        self.assertTrue(results[4]['accepted'])
        self.assertEqual(results[5]['state'],'POWER_READY')
        self.assertFalse(results[6]['accepted'])
        self.assertTrue(results[1]['all_off_confirmed'])
        self.assertFalse(results[7]['accepted'])

    def test_firmware_standby_timeout_and_heartbeat_loss_stop_power(self):
        prefix=[(0,'HEARTBEAT',1,{}),(0,'ARM_TEST',2,{}),
            (0,'PREPARE_TEST_POWER',3,{'supervised_confirmed':True}),(50,'GET_STATUS',4,{})]
        results=self.wire(prefix+[(2050,'GET_STATION_STATUS',5,{})])
        self.assertTrue(results[-1].payload['result']['all_off_confirmed'])
        sequence=prefix+[(tick,'HEARTBEAT',tick//1000+10,{}) for tick in range(1000,30000,1000)]
        replies=self.wire(sequence+[(30000,'GET_STATUS',99,{})])
        last=replies[-1].payload['result']
        self.assertFalse(last['motor_relay_requested_on'])
        self.assertEqual(last['applied_pwm_percent'],0)
        self.assertEqual(last['stop_reason'],'POWER_READY_TIMEOUT')
