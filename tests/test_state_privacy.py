"""Recorder state privacy: owned temporary directories only."""
import importlib.util
import os
from pathlib import Path
import stat
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('privacy_ram', ROOT / 'ram_pulse.py')
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)


class StatePrivacyTests(unittest.TestCase):
    def test_existing_permissive_state_is_made_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'ram-pulse'
            state.mkdir(mode=0o755)
            state.chmod(0o755)
            stored = state / 'snapshot.json'
            stored.write_text('{}')
            stored.chmod(0o644)
            result = subprocess.run([sys.executable, str(ROOT / 'ram_pulse.py'), 'snapshot'],
                                    env={**os.environ, 'XDG_STATE_HOME': tmp},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)

    def test_a_reused_temporary_file_cannot_carry_its_old_mode_over(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            old = Path(tmp) / 'snapshot.tmp'
            old.write_text('interrupted older write')
            old.chmod(0o644)
            ram.atomic('snapshot.json', {'total': 1024})
            self.assertEqual(stat.S_IMODE((Path(tmp) / 'snapshot.json').stat().st_mode), 0o600)

    def test_a_directory_in_place_of_an_in_place_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            (Path(tmp) / 'history.sqlite3').mkdir()
            with self.assertRaises(RuntimeError):
                ram.prepare_state()

    def test_a_hard_linked_in_place_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            db = Path(tmp) / 'history.sqlite3'
            db.write_text('')
            os.link(db, Path(tmp) / 'second-name')
            with self.assertRaises(RuntimeError):
                ram.prepare_state()

    def test_a_symlinked_in_place_file_is_refused(self):
        # sqlite opens the database by path, so a link here is written through.
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            target = Path(tmp) / 'elsewhere.sqlite3'
            target.write_text('')
            (Path(tmp) / 'history.sqlite3').symlink_to(target)
            with self.assertRaises(RuntimeError):
                ram.prepare_state()

    def test_every_in_place_file_is_refused_not_just_the_database(self):
        for name in ('collector.lock', 'flush.lock', 'last-flush',
                     'history.sqlite3-wal', 'history.sqlite3-shm', 'history.sqlite3-journal'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(ram, 'STATE', Path(tmp)):
                target = Path(tmp) / 'elsewhere'
                target.write_text('')
                (Path(tmp) / name).symlink_to(target)
                with self.assertRaises(RuntimeError):
                    ram.prepare_state()

    def test_a_symlinked_replaced_file_is_reported_but_not_refused(self):
        # rename(2) does not follow a link at the destination, so atomic()
        # replaces the link rather than writing through it. A deliberate
        # dotfiles symlink keeps working and is named in the report.
        for name in ('snapshot.json', 'history.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(ram, 'STATE', Path(tmp)):
                target = Path(tmp) / 'elsewhere.json'
                target.write_text('{}')
                (Path(tmp) / name).symlink_to(target)
                unsafe = ram.prepare_state()
                self.assertIn(name, unsafe)
                self.assertIn('symlink', unsafe[name])
                # The link is intact and the target was not written through.
                self.assertTrue((Path(tmp) / name).is_symlink())
                self.assertEqual(target.read_text(), '{}')

    def test_replacing_a_symlinked_snapshot_leaves_the_target_untouched(self):
        # The claim the softening rests on, exercised rather than asserted.
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            target = Path(tmp) / 'elsewhere.json'
            target.write_text('original')
            (Path(tmp) / 'snapshot.json').symlink_to(target)
            ram.atomic('snapshot.json', {'total': 1024})
            self.assertEqual(target.read_text(), 'original')
            self.assertFalse((Path(tmp) / 'snapshot.json').is_symlink())

    def test_a_stale_fixed_name_temporary_file_is_repaired(self):
        # The fixed name an older release wrote to. It was listed as fixed by
        # the state-privacy change but was absent from the vetted names, so an
        # existing one kept its old mode.
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            stale = Path(tmp) / 'snapshot.tmp'
            stale.write_text('interrupted older write')
            stale.chmod(0o644)
            ram.prepare_state()
            self.assertEqual(stat.S_IMODE(stale.stat().st_mode), 0o600)

    def test_ordinary_private_state_is_accepted_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            snapshot = Path(tmp) / 'snapshot.json'
            snapshot.write_text('{}')
            snapshot.chmod(0o600)
            os.chmod(tmp, 0o700)
            ram.prepare_state()
            self.assertEqual(snapshot.read_text(), '{}')
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)

    def test_a_failed_replace_keeps_the_old_snapshot_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            path = Path(tmp) / 'snapshot.json'
            path.write_text('{"old":true}')
            with patch.object(Path, 'replace', side_effect=OSError('simulated I/O failure')):
                with self.assertRaises(OSError):
                    ram.atomic('snapshot.json', {'new': True})
            self.assertEqual(path.read_text(), '{"old":true}')
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['snapshot.json'])


if __name__ == '__main__':
    unittest.main()


class UnsafeStateInTheDaemonTests(unittest.TestCase):
    """The unattended path. ram-pulse.service is Restart=on-failure, so a raise
    out of main() is not one failure a reader can act on -- it is an endless
    five-second cycle of the same JSON error."""

    def _daemon_over(self, tmp, forbid_db=False):
        """Run one daemon iteration against a real state directory.

        forbid_db turns opening the database into a test failure, which is how
        the database cases prove it was never touched rather than merely that
        history was reported as broken.
        """
        writes = []
        db = {'side_effect': AssertionError('database must not be opened')} if forbid_db \
            else {'return_value': MagicMock()}
        with patch.object(ram, 'STATE', Path(tmp)), \
             patch.object(ram, 'metrics', return_value={'ts': 1000, 'total': 1024}), \
             patch.object(ram, 'hoarders', return_value=([], [])), \
             patch.object(ram, 'db_open', **db), \
             patch.object(ram, 'record'), \
             patch.object(ram, 'history', return_value={}), \
             patch.object(ram, 'atomic', side_effect=lambda n, v: writes.append((n, v))), \
             patch.object(ram.time, 'monotonic', return_value=1000), \
             patch.object(ram.time, 'sleep', side_effect=StopIteration), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            with contextlib.suppress(StopIteration):
                ram.daemon()
        return writes, out.getvalue()

    def test_an_unsafe_database_costs_history_not_the_recorder(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'elsewhere.sqlite3'
            target.write_text('')
            (Path(tmp) / 'history.sqlite3').symlink_to(target)
            writes, output = self._daemon_over(tmp, forbid_db=True)
            published = dict((name, value) for name, value in writes)
            # Current memory still reaches the panel, and db_open was never
            # called -- the patch above fails the test if it was.
            self.assertIn('snapshot.json', published)
            self.assertIn('history.sqlite3', published['snapshot.json']['collectorErrors']['history'])
            self.assertIn('symlink', published['snapshot.json']['collectorErrors']['history'])
            self.assertNotIn('history.json', published)
            self.assertTrue((Path(tmp) / 'history.sqlite3').is_symlink())

    def test_a_symlinked_snapshot_is_reported_in_the_dashboard_and_still_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'elsewhere.json'
            target.write_text('{}')
            (Path(tmp) / 'snapshot.json').symlink_to(target)
            writes, output = self._daemon_over(tmp)
            published = dict((name, value) for name, value in writes)
            self.assertIn('snapshot.json', published)
            self.assertIn('snapshot.json', published['snapshot.json']['collectorErrors']['state'])

    def test_an_unsafe_lock_stops_the_daemon_without_a_restart_loop(self):
        # Exit status zero, because Restart=on-failure must not fire. The lock
        # is opened by path and is the first thing the daemon touches, so this
        # one cannot be worked around.
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'ram-pulse'
            state.mkdir(mode=0o700)
            target = Path(tmp) / 'elsewhere.lock'
            target.write_text('')
            (state / 'collector.lock').symlink_to(target)
            result = subprocess.run([sys.executable, str(ROOT / 'ram_pulse.py'), 'daemon'],
                                    env={**os.environ, 'XDG_STATE_HOME': tmp},
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('collector.lock', result.stdout)
            self.assertIn('symlink', result.stdout)
            self.assertEqual(target.read_text(), '')

    def test_an_interactive_run_still_refuses_outright(self):
        # A person is waiting on this one and can act on the message.
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'ram-pulse'
            state.mkdir(mode=0o700)
            target = Path(tmp) / 'elsewhere.sqlite3'
            target.write_text('')
            (state / 'history.sqlite3').symlink_to(target)
            result = subprocess.run([sys.executable, str(ROOT / 'ram_pulse.py'), 'snapshot'],
                                    env={**os.environ, 'XDG_STATE_HOME': tmp},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn('history.sqlite3', result.stdout)
