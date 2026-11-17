import copy
import csv
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from diagnostic_platform.live import LiveMonitor
from diagnostic_platform.collector import ExperimentRecorder
from diagnostic_platform.probe import normalize_probe
from diagnostic_platform.protocol import CommandName, command_message, encode_message, decode_message, unprotect_frame

ROOT=Path(__file__).resolve().parents[1]


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which('cc')
        if not cc:raise unittest.SkipTest('Host C compiler unavailable')
        cls.temp=tempfile.TemporaryDirectory();cls.exe=Path(cls.temp.name)/'probe'
        subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'ADS/Core/Inc'),
            *(str(ROOT/'ADS/Core/Src'/s) for s in ('ads_probe.c','ads_protocol.c','ads_test.c')),
            str(ROOT/'tests/probe_harness.c'),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def frame(self,raw=1551,stale=False):
        request=encode_message(command_message(CommandName.READ_MEASUREMENTS,1),checksum=True)
        reply=subprocess.check_output([str(self.exe),str(raw),*(['stale'] if stale else [])],input=request)
        unprotect_frame(reply,required=True)
        self.assertLess(len(reply),4096)
        return reply

    def test_conversion_scheduler_filter_errors_and_wrap(self):
        subprocess.run([str(self.exe)],check=True)

    def test_real_c_wire_preserves_both_ina219s_and_independent_probe(self):
        for raw,expected in ((0,0),(931,3),(1551,5),(2792,9),(3723,12)):
            with self.subTest(raw=raw):
                frame=self.frame(raw);result=decode_message(frame).payload['result']
                self.assertAlmostEqual(result['circuit_probe']['voltage'],expected,delta=.002)
                self.assertEqual(result['ina219']['MOTOR']['measurements']['voltage']['value'],12)
                self.assertEqual(result['ina219']['CIRCUIT']['measurements']['voltage']['value'],5)
                monitor=LiveMonitor();monitor.publish_acquisition(result)
                snapshot=monitor.snapshot()
                self.assertTrue(snapshot['circuit_probe']['valid'])
                self.assertEqual(snapshot['circuit_probe']['raw_adc'],raw)
                self.assertEqual(snapshot['ina219']['CIRCUIT']['measurements']['voltage']['value'],5)

    def test_saturation_and_stale_c_frames_have_null_voltage(self):
        for frame,status in ((self.frame(4095),'OUT_OF_RANGE'),(self.frame(stale=True),'STALE')):
            result=decode_message(frame).payload['result'];probe=result['circuit_probe']
            self.assertFalse(probe['valid']);self.assertIsNone(probe['voltage'])
            self.assertEqual(probe['status'],status)

    def test_absent_malformed_and_negative_never_fall_back_to_supply(self):
        result=decode_message(self.frame()).payload['result']
        absent=copy.deepcopy(result);absent.pop('circuit_probe')
        self.assertIsNone(normalize_probe(absent)['voltage'])
        for field,value in [('voltage',float('nan')),('voltage',-1),('raw_adc',True),
                            ('timestamp_ms',-1),('valid','true'),('unit','A')]:
            bad=copy.deepcopy(result);bad['circuit_probe'][field]=value
            self.assertFalse(normalize_probe(bad)['valid'])
            self.assertIsNone(normalize_probe(bad)['voltage'])

    def test_host_staleness_repeated_samples_disconnect_and_crc(self):
        result=decode_message(self.frame(0)).payload['result'];monitor=LiveMonitor()
        with patch('diagnostic_platform.live.time.monotonic',return_value=10):
            monitor.publish_acquisition(result)
        with patch('diagnostic_platform.live.time.monotonic',return_value=14):
            monitor.publish_acquisition(result) # same sample must remain stale
            snapshot=monitor.snapshot()['circuit_probe']
            self.assertFalse(snapshot['valid']);self.assertIsNone(snapshot['voltage'])
            self.assertEqual(snapshot['status'],'STALE')
        monitor.publish_acquisition(None)
        self.assertEqual(monitor.snapshot()['circuit_probe']['status'],'DISCONNECTED')
        monitor.publish_acquisition(result);monitor.feed('{bad}*00000000')
        self.assertIsNone(monitor.snapshot()['circuit_probe']['voltage'])
        self.assertFalse(monitor.snapshot()['circuit_probe']['valid'])

    def test_mcu_age_and_wrap(self):
        result=decode_message(self.frame()).payload['result']
        self.assertEqual(normalize_probe(result,1000)['status'],'STALE')
        result['circuit_probe']['timestamp_ms']=0xfffffff0
        self.assertTrue(normalize_probe(result,20)['valid'])

    def test_live_api_exposes_probe_without_serial_reader(self):
        from fastapi.testclient import TestClient
        import api.main as main
        monitor=LiveMonitor();monitor.publish_acquisition(decode_message(self.frame()).payload['result'])
        client=TestClient(main.app)
        try:
            with patch.object(main,'live_monitor',monitor):
                response=client.get('/api/live/status')
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.json()['circuit_probe']['valid'])
        finally:client.close()

    def test_csv_keeps_probe_distinct_from_supply_and_preserves_zero(self):
        for raw,valid in ((0,True),(4095,False)):
            result=decode_message(self.frame(raw)).payload['result']
            with tempfile.TemporaryDirectory() as directory:
                recorder=ExperimentRecorder(directory,'fixture')
                recorder.record(result);recorder.close()
                with recorder.path.open() as source:rows=list(csv.DictReader(source))
                probe=next(row for row in rows if row['branch']=='PROBE')
                self.assertEqual(probe['raw_adc'],str(raw))
                self.assertEqual(probe['value'],'0.0' if valid else '')
                self.assertEqual(probe['valid'],str(valid))
                circuit=next(row for row in rows if row['branch']=='CIRCUIT' and row['channel']=='voltage')
                self.assertEqual(circuit['value'],'5.0')
