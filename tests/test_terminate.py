"""The one destructive action, and the guards that keep it narrow.

Every test here is a promise the README makes. A change that widens Quit
should have to delete one of these on purpose.
"""
import importlib.util
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('terminate_ram', ROOT / 'ram_pulse.py')
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)


def start_of(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


class TerminateGuardTests(unittest.TestCase):
    def sleeper(self):
        """A real child of this test, cleaned up however the test ends."""
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.addCleanup(lambda: (proc.poll() is None and proc.kill(), proc.wait()))
        for _ in range(50):
            if Path(f'/proc/{proc.pid}/stat').exists():
                break
            time.sleep(0.01)
        return proc

    def test_it_sends_sigterm_and_never_sigkill(self):
        proc = self.sleeper()
        with patch.object(ram.os, 'kill') as killed:
            ram.terminate(proc.pid, start_of(proc.pid))
        killed.assert_called_once_with(proc.pid, signal.SIGTERM)

    def test_a_live_process_actually_receives_it(self):
        proc = self.sleeper()
        ram.terminate(proc.pid, start_of(proc.pid))
        self.assertEqual(proc.wait(timeout=10), -signal.SIGTERM)

    def test_a_recycled_pid_is_refused(self):
        # A hoarders row can be nine seconds old. The start time is what tells
        # this process apart from whoever inherited its pid.
        proc = self.sleeper()
        with patch.object(ram.os, 'kill') as killed:
            with self.assertRaises(RuntimeError):
                ram.terminate(proc.pid, '999999999')
        killed.assert_not_called()

    def test_an_exited_process_is_refused(self):
        proc = self.sleeper()
        start = start_of(proc.pid)
        proc.kill()
        proc.wait()
        with patch.object(ram.os, 'kill') as killed:
            with self.assertRaises(RuntimeError):
                ram.terminate(proc.pid, start)
        killed.assert_not_called()

    def test_pid_one_and_nonsense_pids_are_refused(self):
        for pid in (1, 0, -1, None):
            with self.subTest(pid=pid), patch.object(ram.os, 'kill') as killed:
                with self.assertRaises(RuntimeError):
                    ram.terminate(pid, '0')
                killed.assert_not_called()

    def test_the_panel_cannot_quit_the_shell_it_runs_inside(self):
        # own_ancestry() reaches the shell that launched this helper. Without
        # this guard, quitting the bar from a row in the bar is one click.
        chain = ram.own_ancestry()
        self.assertIn(os.getpid(), chain)
        self.assertNotIn(1, chain)
        for pid in sorted(chain):
            with self.subTest(pid=pid), patch.object(ram.os, 'kill') as killed:
                with self.assertRaises(RuntimeError) as caught:
                    ram.terminate(pid, start_of(pid))
                self.assertIn('running this panel', str(caught.exception))
                killed.assert_not_called()

    def test_it_reports_a_request_rather_than_a_kill(self):
        # SIGTERM is a request. Nothing escalates, so the message must not
        # claim the process is gone.
        proc = self.sleeper()
        with patch.object(ram.os, 'kill'):
            message = ram.terminate(proc.pid, start_of(proc.pid))['message']
        self.assertIn('decides whether to', message)

    def test_the_cli_refuses_a_bad_target_with_a_nonzero_exit(self):
        result = subprocess.run([sys.executable, str(ROOT / 'ram_pulse.py'), 'terminate', '1', '0'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('error', result.stdout)


class TerminateStaysNarrowTests(unittest.TestCase):
    """The scope lives in the panel, so read the panel."""

    def setUp(self):
        self.panel = (ROOT / 'Panel.qml').read_text()
        self.helper = (ROOT / 'ram_pulse.py').read_text()

    def test_quit_is_offered_on_process_rows_only(self):
        self.assertIn('visible:!root.grouped && !root.isPending', self.panel)
        self.assertIn('root.pendingKill = root.grouped ? null : row', self.panel)

    def test_quitting_always_goes_through_a_confirmation(self):
        # runAction('terminate') must be reachable only from the confirm step.
        armed = [line for line in self.panel.split('\n') if "runAction('terminate'" in line]
        self.assertEqual(len(armed), 1, armed)
        self.assertIn('isPending', self.panel)
        self.assertIn("procRow.modelData.name+'  ·  PID '+procRow.modelData.pid", self.panel)

    def test_a_stale_confirmation_cannot_survive_the_row_moving(self):
        for clear in ('onPageChanged: pendingKill=null', 'onTabChanged: pendingKill=null',
                      'onGroupedChanged: pendingKill=null'):
            self.assertIn(clear, self.panel)

    def test_no_sigkill_anywhere(self):
        self.assertNotIn('SIGKILL', self.helper)
        self.assertNotIn('SIGKILL', self.panel)
        self.assertEqual(re.findall(r'os\.kill\([^)]*\)', self.helper),
                         ['os.kill(pid, signal.SIGTERM)'])

    def test_the_readme_promise_matches_the_code(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('SIGTERM', readme)
        self.assertIn('There is no SIGKILL', readme)
        self.assertNotIn('There are no process termination', readme)


if __name__ == '__main__':
    unittest.main()
