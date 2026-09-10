#!/usr/bin/env python3
"""Install RAM Pulse with preflight validation and private rollback copies."""
from pathlib import Path
import datetime
import json
import os
import shutil
import stat
import subprocess
import tempfile

PLUGIN_ID = 'nixfred.ram-pulse'
FILES = ('manifest.json', 'Panel.qml', 'Model.js', 'MemoryChip.qml',
         'HistoryGraph.qml', 'ram_pulse.py', 'README.md')


def atomic_write(path, payload, mode):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def update_layout(raw):
    data = json.loads(raw)
    bar = data.get('bar') if isinstance(data, dict) else None
    layout = bar.get('layout') if isinstance(bar, dict) else None
    if not isinstance(layout, dict):
        raise ValueError('shell.json must contain an object at bar.layout.')
    for section in ('left', 'center', 'right'):
        entries = layout.get(section)
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('bar.layout.' + section + ' must be an array of entry objects.')
    found = False
    for section in ('left', 'center', 'right'):
        entries = []
        for entry in layout[section]:
            if entry.get('id') == PLUGIN_ID:
                if found:
                    continue
                found = True
            entries.append(entry)
        layout[section] = entries
    if not found:
        layout['right'].append({'id': PLUGIN_ID, 'displayMode': 0, 'animated': True})
    return (json.dumps(data, indent=2) + '\n').encode('utf-8')


def symlinked_ancestors(*paths):
    """Symlinks at or above each path, stopping below $HOME.

    Path.is_symlink() tests only the final component, so checking the files
    alone catches a symlinked shell.json while missing the far more common
    dotfiles layout where ~/.config or ~/.config/omarchy is itself the link
    into a tracked repo. Publishing through one of those writes into the
    dotfiles repo rather than the destination the installer reports, and the
    rollback copies then describe files that were never the live ones. $HOME
    itself is not checked: a symlinked home directory is a system choice, not
    an install destination the user picked.
    """
    home = Path.home()
    found = set()
    for path in paths:
        for candidate in (path, *path.parents):
            if candidate == home:
                break
            if candidate.is_symlink():
                found.add(str(candidate))
    return sorted(found)


def main():
    # Private by default: directories this installer creates (plugin copy,
    # unit directory, backup parents) inherit this mask. Payload file modes
    # are set explicitly by atomic_write and are unaffected.
    os.umask(0o077)
    source = Path(__file__).resolve().parent
    home = Path.home()
    config = home / '.config/omarchy/shell.json'
    dest = config.parent / 'plugins' / PLUGIN_ID
    unit = home / '.config/systemd/user/ram-pulse.service'
    linked = symlinked_ancestors(config, dest, unit)
    if linked:
        raise RuntimeError('Resolve symlinked install destinations explicitly '
                           'before installing: ' + ', '.join(linked))
    raw = config.read_bytes()
    updated = update_layout(raw)
    config_mode = stat.S_IMODE(config.stat().st_mode) & 0o777
    payloads = {}
    for name in (*FILES, 'ram-pulse.service'):
        path = source / name
        if not path.is_file():
            raise RuntimeError('Missing install payload: ' + name)
        payloads[name] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode) & 0o777)

    backups = home / '.local/state/omarchy/backups'
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = Path(tempfile.mkdtemp(prefix='ram-pulse-' + stamp + '-', dir=backups))
    shutil.copy2(config, backup / 'shell.json')
    if dest.exists():
        shutil.copytree(dest, backup / 'plugin', symlinks=True)
    if unit.exists():
        shutil.copy2(unit, backup / 'ram-pulse.service')
    try:
        if config.read_bytes() != raw:
            raise RuntimeError('shell.json changed during installation; no payload was published.')
        dest.mkdir(parents=True, exist_ok=True)
        unit.parent.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            atomic_write(dest / name, *payloads[name])
        atomic_write(unit, *payloads['ram-pulse.service'])
        atomic_write(config, updated, config_mode)
        for command in (['systemctl', '--user', 'daemon-reload'],
                        ['systemctl', '--user', 'enable', 'ram-pulse.service'],
                        ['systemctl', '--user', 'restart', 'ram-pulse.service'],
                        ['omarchy-shell', 'shell', 'rescanPlugins']):
            subprocess.run(command, check=True, timeout=30)
    except Exception:
        print('Install did not complete. Rollback copies: ' + str(backup))
        raise
    print('Installed RAM Pulse. Backup: ' + str(backup))


if __name__ == '__main__':
    main()
