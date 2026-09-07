"""Recorder state privacy: owned temporary directories only."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_a_directory_in_place_of_a_state_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            (Path(tmp) / 'snapshot.json').mkdir()
            with self.assertRaises(RuntimeError):
                ram.prepare_state()

    def test_a_hard_linked_state_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            snapshot = Path(tmp) / 'snapshot.json'
            snapshot.write_text('{}')
            os.link(snapshot, Path(tmp) / 'second-name')
            with self.assertRaises(RuntimeError):
                ram.prepare_state()

    def test_a_symlinked_state_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ram, 'STATE', Path(tmp)):
            target = Path(tmp) / 'elsewhere.json'
            target.write_text('{}')
            (Path(tmp) / 'snapshot.json').symlink_to(target)
            with self.assertRaises(OSError):
                ram.prepare_state()

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
