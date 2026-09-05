#!/usr/bin/env python3
"""Install RAM Pulse with timestamped rollback copies; preserve other bar entries."""
from pathlib import Path
import datetime
import json
import shutil
import subprocess

source=Path(__file__).resolve().parent
home=Path.home()
config=home/'.config/omarchy/shell.json'
dest=home/'.config/omarchy/plugins/nixfred.ram-pulse'
unit=home/'.config/systemd/user/ram-pulse.service'
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup=home/'.local/state/omarchy/backups'/('ram-pulse-'+stamp)
backup.mkdir(parents=True)
shutil.copy2(config,backup/'shell.json')
if dest.exists():shutil.copytree(dest,backup/'plugin')
if unit.exists():shutil.copy2(unit,backup/'ram-pulse.service')
dest.mkdir(parents=True,exist_ok=True)
for name in ['manifest.json','Panel.qml','Model.js','MemoryChip.qml','HistoryGraph.qml','ram_pulse.py','README.md']:
    shutil.copy2(source/name,dest/name)
unit.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(source/'ram-pulse.service',unit)
# Read after copying, minimizing the time between config read and atomic write.
data=json.loads(config.read_text())
layout=data['bar']['layout']
for section in ('left','center','right'):
    layout[section]=[entry for entry in layout[section] if entry.get('id')!='nixfred.ram-pulse']
layout['right'].append({'id':'nixfred.ram-pulse','displayMode':0,'animated':True})
tmp=config.with_suffix('.ram-pulse.tmp')
tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(config)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','ram-pulse.service'],check=True)
subprocess.run(['systemctl','--user','restart','ram-pulse.service'],check=True)
subprocess.run(['omarchy-shell','shell','rescanPlugins'],check=True)
print('Installed RAM Pulse. Backup: '+str(backup))
