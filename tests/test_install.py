"""Installer regressions: temporary directories and mocked service commands only."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    @contextlib.contextmanager
    def installer_fixture(self, config_text=None, missing=None):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home, source = base / 'home', base / 'source'
            source.mkdir()
            shutil.copy2(ROOT / 'install.py', source / 'install.py')
            for name in ('manifest.json', 'Panel.qml', 'Model.js', 'MemoryChip.qml',
                         'HistoryGraph.qml', 'ram_pulse.py', 'README.md', 'ram-pulse.service'):
                if name != missing:
                    (source / name).write_text('new fixture: ' + name)
            config = home / '.config/omarchy/shell.json'
            dest = config.parent / 'plugins/nixfred.ram-pulse'
            dest.mkdir(parents=True)
            (dest / 'Panel.qml').write_text('old plugin')
            unit = home / '.config/systemd/user/ram-pulse.service'
            unit.parent.mkdir(parents=True)
            unit.write_text('old unit')
            data = {'bar': {'layout': {'left': [{'id': 'clock'}], 'center': [
                {'id': 'nixfred.ram-pulse', 'displayMode': 3, 'animated': False,
                 'groupByApp': False, 'custom': 'keep'}], 'right': []}}}
            config.write_text(config_text if config_text is not None else json.dumps(data))
            config.chmod(0o600)
            def install():
                with patch.object(Path, 'home', return_value=home), \
                     patch('subprocess.run', return_value=SimpleNamespace(returncode=0)), \
                     contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(source / 'install.py'), run_name='__main__')
            yield home, config, dest, unit, data, install

    def test_invalid_json_preserves_installed_files(self):
        with self.installer_fixture(config_text='{ broken') as (_, _, dest, unit, _, install):
            with self.assertRaises((ValueError, RuntimeError)):
                install()
            self.assertEqual((dest / 'Panel.qml').read_text(), 'old plugin')
            self.assertEqual(unit.read_text(), 'old unit')

    def test_invalid_layout_preserves_installed_files(self):
        with self.installer_fixture(config_text='{"bar":{"layout":{"left":"invalid"}}}') as (_, _, dest, unit, _, install):
            with self.assertRaises(ValueError):
                install()
            self.assertEqual((dest / 'Panel.qml').read_text(), 'old plugin')
            self.assertEqual(unit.read_text(), 'old unit')

    def test_missing_payload_preserves_installed_files(self):
        with self.installer_fixture(missing='HistoryGraph.qml') as (_, _, dest, unit, _, install):
            with self.assertRaises((OSError, RuntimeError)):
                install()
            self.assertEqual((dest / 'Panel.qml').read_text(), 'old plugin')
            self.assertEqual(unit.read_text(), 'old unit')

    def test_reinstall_preserves_settings_and_bar_location(self):
        with self.installer_fixture() as (_, config, _, _, data, install):
            install()
            self.assertEqual(json.loads(config.read_text()), data)

    def test_new_install_appends_far_right_without_changing_other_entries(self):
        with self.installer_fixture() as (_, config, _, _, data, install):
            data['bar']['layout']['center'] = [{'id': 'workspace'}]
            data['bar']['layout']['right'] = [{'id': 'tray'}]
            config.write_text(json.dumps(data))
            install()
            layout = json.loads(config.read_text())['bar']['layout']
            self.assertEqual(layout['left'], data['bar']['layout']['left'])
            self.assertEqual(layout['center'], data['bar']['layout']['center'])
            self.assertEqual(layout['right'], [{'id': 'tray'},
                {'id': 'nixfred.ram-pulse', 'displayMode': 0, 'animated': True}])

    def test_install_preserves_private_config_mode(self):
        old_umask = os.umask(0o022)
        try:
            with self.installer_fixture() as (_, config, _, _, _, install):
                install()
                self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        finally:
            os.umask(old_umask)

    def test_repeated_install_creates_distinct_private_backups(self):
        old_umask = os.umask(0o022)
        try:
            with self.installer_fixture() as (home, _, _, _, _, install):
                install()
                install()
                backups = list((home / '.local/state/omarchy/backups').iterdir())
                self.assertEqual(len(backups), 2)
                self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o700 for p in backups))
        finally:
            os.umask(old_umask)


if __name__ == '__main__':
    unittest.main()
