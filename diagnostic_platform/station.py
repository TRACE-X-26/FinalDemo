"""Explicit branch confirmation and acknowledged all-off; one serial owner."""
import threading
from .hardware_runtime import RunRejected


class StationService:
    def __init__(self, engine):
        self.engine = engine
        self._lock = threading.RLock()
        self.reset_status = {'off_confirmed': False, 'reason': 'Off state not checked'}

    @staticmethod
    def all_off(reply):
        return (reply.get('accepted') is True and reply.get('all_off_confirmed') is True
                and reply.get('motor_relay_requested_on') is False
                and reply.get('circuit_relay_requested_on') is False
                and type(reply.get('applied_pwm_percent')) is int
                and reply['applied_pwm_percent'] == 0)

    def snapshot(self):
        # Polling status never waits behind a serial command or sends a command.
        return dict(self.reset_status)

    def select(self, branch):
        with self._lock:
            if branch not in ('MOTOR', 'CIRCUIT'):
                raise RunRejected('Select MOTOR or CIRCUIT')
            if self._active():
                raise RunRejected('Reset / All Off before changing a powered branch')
            # A short read-only sensor poll is not an active power session.
            if not self.engine._mutex.acquire(timeout=1.5):
                raise RunRejected('Serial acquisition busy; retry branch selection')
            try:
                if self._active() or self.engine._station_resetting:
                    raise RunRejected('Reset / All Off before changing a powered branch')
                self.engine.circuit_power.selected_branch=branch
                return {'selected_branch':branch,'power_changed':False}
            finally:
                self.engine._mutex.release()

    def _active(self):
        motor=self.engine.snapshot()
        circuit=self.engine.circuit_power.snapshot()
        return bool((motor and not motor.get('ended_at')) or
                    (circuit and not circuit.get('ended_at')))

    def reset(self):
        with self._lock:
            e = self.engine
            e._station_resetting = True
            e.stop()
            e.circuit_power.selected_branch = None
            self.reset_status = {'off_confirmed': False, 'reason': 'Stopping both branches'}
            owned = False
            connection = None
            try:
                # Existing owner must finish its STOP exchange before we open USB.
                owned = e._mutex.acquire(timeout=5)
                if not owned:
                    raise RunRejected('Active operation did not release serial ownership')
                from .automated_engine import load_hardware_profile
                from .test_registry import REGISTRY
                profile = load_hardware_profile(e.hardware_profile_path)
                connection = e._connection('hardware', REGISTRY['pwm_50'], None, profile)
                connection.connect()
                caps = e._read(connection, 'GET_CAPABILITIES')
                if caps.get('integrity') != 'CRC32':
                    raise RunRejected('CRC32-capable firmware required')
                if 'RESET_ALL' in caps.get('commands', []):
                    reply = connection.execute('RESET_ALL')
                    confirmed = self.all_off(reply)
                else:
                    # Recovery support for the preserved firmware: only STOPs,
                    # and confirm both controller states before reporting off.
                    motor = connection.execute('STOP_TEST')
                    circuit = connection.execute('STOP_CIRCUIT')
                    confirmed = (e._stopped(motor) and circuit.get('accepted') is True
                                 and circuit.get('power_on') is False
                                 and circuit.get('state') in ('STOPPED', 'DISARMED', 'LOCKOUT'))
                self.reset_status = {
                    'off_confirmed': confirmed,
                    'reason': 'Both relay-off commands and zero PWM acknowledged' if confirmed
                              else 'Off not confirmed by STM32',
                    'physical_power_verified': False,
                    'firmware_version': caps.get('firmware_version'),
                    'station_control': caps.get('station_control') is True,
                }
            except Exception as exc:
                self.reset_status = {'off_confirmed': False,
                                     'reason': 'Off not confirmed: ' + str(exc),
                                     'physical_power_verified': False}
            finally:
                try:
                    if connection:
                        # RESET already stopped both: avoid a second disconnect STOP.
                        connection.allow_motor_control = False
                        connection.disconnect()
                finally:
                    if owned:
                        e._mutex.release()
                    e._station_resetting = False
            return dict(self.reset_status, selected_branch=None)

    def confirm_power(self, duration_ms, confirmed):
        with self._lock:
            if confirmed is not True:
                raise RunRejected('Confirm the selected branch before applying power')
            if type(duration_ms) is not int or not 100 <= duration_ms <= 30000:
                raise RunRejected('Duration must be 100–30000 ms')
            e = self.engine
            branch = e.circuit_power.selected_branch
            if branch not in ('MOTOR', 'CIRCUIT'):
                raise RunRejected('Select Motor or Circuit first')
            # Reconfirmation cannot silently cancel or replace an active operation.
            if self._active():
                raise RunRejected('Reset / All Off before confirming another branch')
            off = self.reset()
            if not off['off_confirmed']:
                raise RunRejected(off['reason'])
            if off.get('station_control') is not True:
                raise RunRejected('Both branches stopped. Flash firmware 0.9.0 before confirming branch power')
            e.circuit_power.selected_branch = branch
            self.reset_status = {'off_confirmed': False, 'reason': 'Branch power requested'}
            if branch == 'CIRCUIT':
                return e.circuit_power.start(duration_ms, True)
            return e.start({'mode': 'hardware', 'tests': ['pwm_50'],
                            'duration_ms': duration_ms, 'supervised_confirmed': True,
                            'station_prepare': True})

    def start_motor(self, duration_ms):
        with self._lock:
            return self.engine.start_prepared_motor(duration_ms)
