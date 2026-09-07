"""Process-scan subprocess budget: mocked desktop commands and a mocked clock."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('budget_ram', ROOT / 'ram_pulse.py')
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)


class CommandBudgetTests(unittest.TestCase):
    def test_identical_queries_are_asked_once(self):
        with patch.object(ram.time, 'monotonic', return_value=1000), \
             patch.object(ram, 'run', return_value='same answer') as command:
            query = ram.CommandBudget()
            self.assertEqual(query(['hyprctl', 'clients', '-j']), 'same answer')
            self.assertEqual(query(['hyprctl', 'clients', '-j']), 'same answer')
            command.assert_called_once()

    def test_a_later_query_only_gets_the_remaining_time(self):
        with patch.object(ram.time, 'monotonic', side_effect=[1000, 1001.75, 1003]), \
             patch.object(ram, 'run', return_value='answer') as command:
            query = ram.CommandBudget()
            self.assertEqual(query(['one']), 'answer')
            self.assertEqual(query(['two']), '')
            command.assert_called_once_with(['one'], timeout=0.25)

    def test_undecodable_command_output_is_not_fatal(self):
        with patch.object(ram.subprocess, 'run', side_effect=UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'bad')):
            self.assertEqual(ram.run(['anything']), '')

    def test_scan_shares_one_subprocess_wait_budget(self):
        clock = [1000.0]
        queries = []
        def command(args, **kwargs):
            queries.append(args)
            if args[0] == 'hyprctl':
                return SimpleNamespace(returncode=0, stdout=json.dumps([
                    {'pid': 2000, 'address': '0xabc', 'title': 'terminal', 'workspace': {'name': '1'}}]))
            clock[0] += kwargs['timeout']
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        members = {n: {'pid': n, 'ppid': 2000, 'start': str(n), 'name': 'worker',
                       'rss': n, 'swap': 0} for n in range(100, 124)}
        with patch.object(Path, 'iterdir', return_value=[Path(f'/proc/{n}') for n in members]), \
             patch.object(Path, 'stat', return_value=SimpleNamespace(st_uid=os.getuid())), \
             patch.object(ram, 'process', side_effect=lambda n: members[int(n)].copy()), \
             patch.object(ram, 'read', return_value='Pss: 10 kB'), \
             patch.object(ram, 'environment', return_value={'TMUX': '/test/socket,1,0', 'TMUX_PANE': '%1'}), \
             patch.object(ram.subprocess, 'run', side_effect=command), \
             patch.object(ram.time, 'monotonic', side_effect=lambda: clock[0]):
            rows, groups = ram.hoarders()
        self.assertEqual(len(rows), 24)
        self.assertTrue(groups)
        self.assertLessEqual(clock[0] - 1000.0, 2.01)
        self.assertLessEqual(sum(args[0] == 'tmux' for args in queries), 2)

    def test_unresolved_session_skips_the_client_list_query(self):
        asked = []
        def query(args):
            asked.append(args)
            return ''
        procs = {5: {'pid': 5, 'ppid': 1, 'start': '5', 'name': 'sh', 'rss': 1, 'swap': 0}}
        with patch.object(ram, 'environment', return_value={'TMUX': '/test/socket,1,0', 'TMUX_PANE': '%1'}):
            ram.target_for(procs[5], procs, [], query)
        self.assertEqual([args[2] for args in asked if args[0] == 'tmux'], ['/test/socket'])
        self.assertNotIn('list-clients', [a for args in asked for a in args])

    def test_malformed_client_records_are_rejected_or_normalized(self):
        payload = [{'pid': True, 'address': '0xabc'}, {'pid': -1, 'address': '0xabc'},
                   {'pid': 3, 'address': 'not-an-address'},
                   {'pid': 4, 'address': '0xdef', 'workspace': None}]
        with patch.object(ram, 'run', return_value=json.dumps(payload)):
            value = ram.clients()
        self.assertEqual(len(value), 1)
        self.assertEqual(value[0]['workspace'], {})

    def test_a_non_list_client_payload_is_not_fatal(self):
        with patch.object(ram, 'run', return_value='{"error":"no compositor"}'):
            self.assertEqual(ram.clients(), [])


if __name__ == '__main__':
    unittest.main()
