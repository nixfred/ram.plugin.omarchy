"""Collector failure isolation: mocked subsystems and temporary state only."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recorder_ram', ROOT / 'ram_pulse.py')
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)


class CollectorFailureTests(unittest.TestCase):
    def _one_iteration(self, record_error=None, process_error=None):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)), \
             patch.object(ram, 'db_open', return_value=MagicMock()), \
             patch.object(ram, 'metrics', return_value={'ts': 1000, 'total': 1024}), \
             patch.object(ram, 'record', side_effect=record_error), \
             patch.object(ram, 'history', return_value={}), \
             patch.object(ram, 'hoarders', side_effect=process_error, return_value=([], [])), \
             patch.object(ram, 'atomic') as write, \
             patch.object(ram.time, 'monotonic', return_value=1000), \
             patch.object(ram.time, 'sleep', side_effect=StopIteration), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopIteration):
                ram.daemon()
            self.assertIn('snapshot.json', [call.args[0] for call in write.call_args_list])

    def test_history_write_failure_does_not_suppress_current_memory(self):
        self._one_iteration(record_error=sqlite3.OperationalError('database is locked'))

    def test_process_scan_failure_does_not_suppress_current_memory(self):
        self._one_iteration(process_error=OSError('process list unavailable'))

    def test_unusable_database_does_not_stop_the_recorder(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)), \
             patch.object(ram, 'db_open', side_effect=sqlite3.DatabaseError('not a database')), \
             patch.object(ram, 'metrics', return_value={'ts': 1000, 'total': 1024}), \
             patch.object(ram, 'hoarders', return_value=([], [])), \
             patch.object(ram, 'atomic') as write, \
             patch.object(ram.time, 'monotonic', return_value=1000), \
             patch.object(ram.time, 'sleep', side_effect=StopIteration), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopIteration):
                ram.daemon()
            snapshots = [c.args[1] for c in write.call_args_list if c.args[0] == 'snapshot.json']
            self.assertEqual(len(snapshots), 1)
            self.assertIn('history', snapshots[0]['collectorErrors'])

    def test_history_error_clears_after_a_successful_retry(self):
        clock, sleeps = [1000.0], [0]
        def sleep(_):
            sleeps[0] += 1
            if sleeps[0] == 2:
                raise StopIteration
            clock[0] += 16
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)), \
             patch.object(ram, 'db_open', return_value=MagicMock()), \
             patch.object(ram, 'metrics', side_effect=lambda _: {'ts': clock[0], 'total': 1024}), \
             patch.object(ram, 'record', side_effect=[sqlite3.OperationalError('busy'), None]), \
             patch.object(ram, 'history', return_value={}), \
             patch.object(ram, 'hoarders', return_value=([], [])), \
             patch.object(ram, 'atomic') as write, \
             patch.object(ram.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(ram.time, 'sleep', side_effect=sleep), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopIteration):
                ram.daemon()
            snapshots = [c.args[1] for c in write.call_args_list if c.args[0] == 'snapshot.json']
            self.assertEqual(len(snapshots), 2)
            self.assertIn('history', snapshots[0]['collectorErrors'])
            self.assertEqual(snapshots[1]['collectorErrors'], {})

    def test_a_failed_process_scan_clears_the_stale_list(self):
        clock, sleeps = [1000.0], [0]
        def sleep(_):
            sleeps[0] += 1
            if sleeps[0] == 2:
                raise StopIteration
            clock[0] += 10
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)), \
             patch.object(ram, 'db_open', return_value=MagicMock()), \
             patch.object(ram, 'metrics', side_effect=lambda _: {'ts': clock[0], 'total': 1024}), \
             patch.object(ram, 'record', return_value=None), \
             patch.object(ram, 'history', return_value={}), \
             patch.object(ram, 'hoarders', side_effect=[([{'pid': 1}], [{'key': 'a'}]),
                                                        OSError('process list unavailable')]), \
             patch.object(ram, 'atomic') as write, \
             patch.object(ram.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(ram.time, 'sleep', side_effect=sleep), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopIteration):
                ram.daemon()
            snapshots = [c.args[1] for c in write.call_args_list if c.args[0] == 'snapshot.json']
            self.assertEqual(snapshots[0]['hoarders'], [{'pid': 1}])
            self.assertEqual(snapshots[1]['hoarders'], [])
            self.assertIn('processes', snapshots[1]['collectorErrors'])


if __name__ == '__main__':
    unittest.main()
