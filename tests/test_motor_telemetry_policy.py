"""Electrical telemetry does not gate the operator-selected motor build."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class MotorTelemetryPolicyTests(unittest.TestCase):
    def test_production_sensor_readiness_and_relay_settling_without_calibration(self):
        cc=shutil.which('cc')
        if not cc:self.skipTest('Host C compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/'telemetry'
            result=subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'tests/hal_stub'),'-I',str(ROOT/'ADS/Core/Inc'),
                '-DADS_USE_DIRECT_MOTOR_PROFILE=1',
                '-include',str(ROOT/'ADS/bench/downstream.operator.h'),
                '-UADS_INA219_CALIBRATED','-DADS_INA219_CALIBRATED=0',
                '-DADS_SENSOR_WIRING_VERIFIED=0',
                str(ROOT/'tests/telemetry_motor_sensors_harness.c'),
                *(str(ROOT/'ADS/Core/Src'/f) for f in
                  ('ads_acquisition.c','ads_ina219.c','ads_protection.c')),
                '-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(exe)],check=True)
