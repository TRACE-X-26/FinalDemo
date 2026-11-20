import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import main
from diagnostic_platform.automated_storage import RunStore
from diagnostic_platform.collector import CHANNELS


class MotorHealthDashboardTests(unittest.TestCase):
    def test_numbered_runs_and_diagnostics_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'diagnostics.db'
            with patch.object(main, 'DATABASE_PATH', path):
                with TestClient(main.app) as client:
                    store = main.test_engine().store
                    self._save_run(store, 'normal', 15_000, 3255.882, 0.11)
                    self._save_run(store, 'deviation', 15_000, 600, 0.40)
                    self._save_run(store, 'short', 5_000, 78, 0.11)
                    runs = client.get('/api/motor/health').json()['tests']
                    self.assertEqual([(run['id'], run['number']) for run in runs],
                                     [('short', 3), ('deviation', 2), ('normal', 1)])
                    normal = client.get('/api/motor/health/tests/normal').json()
                    self.assertEqual(normal['status'], 'Within reference')
                    self.assertEqual(normal['metrics']['rpm']['value'], 3255.882)
                    self.assertIsNone(normal['metrics']['rpm']['outside'])
                    diagnosis = client.post('/api/motor/health/tests/deviation/diagnostics')
                    self.assertEqual(diagnosis.status_code, 201)
                    result = diagnosis.json()
                    self.assertEqual(result['status'], 'Deviation detected')
                    self.assertEqual(result['metrics']['rpm']['value'], 600)
                    self.assertTrue(any('encoder scaling' in finding for finding in result['findings']))
                    short = client.post('/api/motor/health/tests/short/diagnostics').json()
                    self.assertEqual(short['status'], 'Not assessed')

                self.assertEqual([number for number, _ in RunStore(path).motor_health_runs()], [3, 2, 1])
                with TestClient(main.app) as client:
                    history = client.get('/api/motor/health').json()['history']
                    self.assertEqual([row['number'] for row in history], [3, 2])
                    self.assertEqual(history[1]['reference']['run_ids'], ['T08-01', 'T08-02'])

    @staticmethod
    def _save_run(store, identifier, duration, rpm, amps):
        started = 0xffffff00
        run = {
            'id': identifier, 'state': 'COMPLETED', 'mode': 'hardware', 'source': 'stm32_serial',
            'created_at': '2026-11-20T00:00:00Z', 'configuration': {'duration_ms': duration},
            'steps': [{'test_id': 'pwm_50', 'started_ms': started}],
        }
        store.create(run)
        for elapsed in range(0, duration, 1000):
            tick = (started + elapsed) & 0xffffffff
            values = {'rpm': rpm, 'voltage': 12.26, 'current': amps, 'power': 12.26 * amps}
            measurements = {name: {'valid': name in values, 'value': values.get(name),
                                   'unit': unit, 'timestamp_ms': tick}
                            for name, unit in CHANNELS.items()}
            store.sample(identifier, {'measurements': measurements, 'test_id': 'pwm_50',
                                       'motor_state': 'RUNNING', 'applied_pwm_percent': 50,
                                       'stm32_status_timestamp_ms': tick}, [])
        store.release(identifier)
