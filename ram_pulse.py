#!/usr/bin/env python3
"""RAM Pulse: unprivileged telemetry, persistent history, focus-only navigation."""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import subprocess
import tempfile
import time

_state_home = os.environ.get('XDG_STATE_HOME', '')
STATE = (Path(_state_home) if os.path.isabs(_state_home) else Path.home() / '.local/state') / 'ram-pulse'
ENV_KEYS = {'HERDR_ENV', 'HERDR_SOCKET_PATH', 'HERDR_WORKSPACE_ID', 'HERDR_TAB_ID', 'HERDR_PANE_ID', 'TMUX', 'TMUX_PANE', 'BOOMUX_SHELL_ID'}

def read(path):
    try:
        return Path(path).read_text(errors='replace')
    except (OSError, ValueError):
        return ''

def fields(raw):
    result = {}
    for line in raw.splitlines():
        key, _, value = line.partition(':')
        try:
            result[key] = int(value.split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    return result

def run(args, timeout=2):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return p.stdout if p.returncode == 0 else ''
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return ''

class CommandBudget:
    # One scan gets one subprocess-wait budget, not one per invocation, and
    # repeated identical lookups answer from the cache.
    def __init__(self, seconds=2):
        self.deadline = time.monotonic() + seconds
        self.cache = {}

    def __call__(self, args):
        key = tuple(args)
        if key not in self.cache:
            remaining = self.deadline - time.monotonic()
            self.cache[key] = run(args, timeout=min(2, remaining)) if remaining > 0 else ''
        return self.cache[key]

def clients(query=None):
    query = run if query is None else query
    try:
        value = json.loads(query(['hyprctl', 'clients', '-j']))
        if not isinstance(value, list):
            return []
        result = []
        for c in value:
            if not isinstance(c, dict) or type(c.get('pid')) is not int or c['pid'] <= 0:
                continue
            if not re.fullmatch(r'0x[0-9a-fA-F]+', str(c.get('address', ''))):
                continue
            if not isinstance(c.get('workspace'), dict):
                c = dict(c, workspace={})
            result.append(c)
        return result
    except (ValueError, TypeError):
        return []

def environment(pid):
    # Only these routing identities ever leave this function. No credentials,
    # command lines, or full process environments are persisted.
    return {k: v for s in read(f'/proc/{pid}/environ').split('\0') for k, sep, v in [s.partition('=')] if sep and k in ENV_KEYS}

def process(pid):
    raw = read(f'/proc/{pid}/stat')
    if not raw:
        return None
    try:
        tail = raw[raw.rindex(')') + 2:].split()
        st = fields(read(f'/proc/{pid}/status'))
        return {'pid': int(pid), 'start': tail[19], 'ppid': int(tail[1]),
                'name': raw[raw.index('(')+1:raw.rindex(')')][:64],
                'rss': st.get('VmRSS', 0), 'swap': st.get('VmSwap', 0)}
    except (ValueError, IndexError):
        return None

def window_for(pid, procs, windows):
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        if pid in windows:
            return windows[pid]
        pid = procs.get(pid, {}).get('ppid', 0)
    return None

def owned_socket(path):
    # Herdr/TMUX socket paths come from the target process's own environment,
    # so they are attacker-influenced. Only a path that is currently a socket
    # owned by this user is usable; anything else degrades to plain window
    # focus rather than failing the click.
    try:
        info = os.stat(path)
    except (OSError, ValueError, TypeError):
        return ''
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        return ''
    return path

def related(a, b, procs):
    # A window title is attacker-reproducible: any same-user client can set
    # its title to match. A focus target the process tree cannot relate to
    # the target process is title-only evidence. Either direction counts, so
    # a terminal emulator above the shell and a helper below it both bind.
    for start, goal in ((a, b), (b, a)):
        seen = set()
        pid = start
        while isinstance(pid, int) and pid > 1 and pid not in seen:
            if pid == goal:
                return True
            seen.add(pid)
            pid = procs.get(pid, {}).get('ppid', 0)
    return False

def target_for(p, procs, wins, query=None):
    query = run if query is None else query
    windows = {c['pid']: c for c in wins}
    w = window_for(p['pid'], procs, windows)
    env = environment(p['pid'])
    host = {}
    # Boomux terminal titles carry an exact shell id. Focusing that existing
    # window needs no launcher and cannot create or terminate a session.
    # Titles alone do not bind a window to a shell -- any same-user client
    # can set its title -- so a candidate whose window process the tree
    # relates to the target wins over one that merely matches the title. The
    # title-only fallback stays for multiplexer layouts where the window and
    # the shell share no ancestry, where no better binding is available.
    shell = env.get('BOOMUX_SHELL_ID', '')
    if shell and re.fullmatch(r'\S{1,64}', shell):
        match = [c for c in wins if str(c.get('title', '')).startswith('boomux:shell:') and str(c.get('title', '')).split(' ')[0].endswith(':' + shell)]
        if match:
            kin = [c for c in match if isinstance(c.get('pid'), int) and related(p['pid'], c['pid'], procs)]
            w = kin[0] if kin else match[0]
    if not shell and env.get('HERDR_ENV') == '1' and env.get('HERDR_PANE_ID'):
        sock = owned_socket(env.get('HERDR_SOCKET_PATH') or str(Path.home() / '.config/herdr/herdr.sock'))
        if sock:
            for q in procs.values():
                if q['name'] != 'herdr':
                    continue
                cw = window_for(q['pid'], procs, windows)
                ce = environment(q['pid'])
                cs = ce.get('HERDR_SOCKET_PATH') or str(Path.home() / '.config/herdr/herdr.sock')
                if cw and cs == sock:
                    w = cw
                    host = {'kind': 'herdr', 'socket': sock, 'workspace': env.get('HERDR_WORKSPACE_ID', ''), 'tab': env.get('HERDR_TAB_ID', ''), 'pane': env['HERDR_PANE_ID']}
                    break
    if not shell and not host and env.get('TMUX') and re.fullmatch(r'%\d+', env.get('TMUX_PANE', '')):
        sock = owned_socket(env['TMUX'].rsplit(',', 2)[0])
        if sock:
            pane = env['TMUX_PANE']
            # Attach only to a client already displaying this pane's session.
            session = query(['tmux', '-S', sock, 'display-message', '-p', '-t', pane, '#{session_id}']).strip()
            for line in (query(['tmux', '-S', sock, 'list-clients', '-F', '#{client_pid}\t#{session_id}\t#{client_name}']) if session else '').splitlines():
                parts = line.split('\t')
                if len(parts) == 3 and parts[0].isdigit() and parts[1] == session:
                    cw = window_for(int(parts[0]), procs, windows)
                    if cw:
                        w = cw
                        host = {'kind': 'tmux', 'socket': sock, 'pane': pane, 'client': parts[2]}
                        break
    return {'address': w['address'], 'title': str(w.get('title', ''))[:100], 'workspace': str(w.get('workspace', {}).get('name', '')), 'host': host} if w else {}

def public_target(t):
    # Snapshot holds display state; focus() re-resolves routing fresh.
    if not t or not t.get('address'):
        return {}
    h = t.get('host', {})
    host = {'kind': h.get('kind', ''), 'pane': h.get('pane', '')} if h.get('kind') in ('herdr', 'tmux') else {}
    return {'address': t.get('address', ''), 'title': t.get('title', ''), 'workspace': t.get('workspace', ''), 'host': host}

def public_row(r):
    o = {'pid': r['pid'], 'start': r['start'], 'name': r['name'], 'rss': r['rss'], 'swap': r['swap'], 'pss': r['pss'], 'target': public_target(r.get('target', {}))}
    if 'count' in r:
        o.update(count=r['count'], names=list(r.get('names', []))[:3])
    return o

def scanned(p):
    # Processes come and go while the scan runs. One that exited between its
    # status and its smaps read is not a hoarder and must not cost its group a
    # total. One that is merely unreadable, such as a root command inside our
    # own terminal, is still resident and still spoils the sum.
    return p['pss'] is not None or not p['owned'] or Path(f"/proc/{p['pid']}").exists()

def cgroup_scope(pid):
    # Only a unit leaf may group processes. The root cgroup and the slices
    # above it cover unrelated work, so anything else falls back to the
    # process itself rather than lumping the session into one row. The whole
    # identity is the key: the same leaf name under two different hierarchies
    # is two different units. Prefer the unified hierarchy, then named=systemd.
    entries = [line.split(':', 2) for line in read(f'/proc/{pid}/cgroup').splitlines()]
    entries = [e for e in entries if len(e) == 3 and e[2].startswith('/')]
    entries.sort(key=lambda e: e[:2] != ['0', ''])
    for hierarchy, controllers, path in entries:
        if (hierarchy == '0' and not controllers) or 'name=systemd' in controllers.split(','):
            if path.rsplit('/', 1)[-1].endswith(('.scope', '.service')):
                return ':'.join((hierarchy, controllers, path))
    return ''

def group_of(p, procs, windows):
    # One row per thing the user can click. window_for only walks the parent
    # chain against processes already read, so it is cheap enough to run for
    # every process; target_for is not, and runs once per displayed leader.
    w = window_for(p['pid'], procs, windows)
    if w:
        return 'window:' + w['address']
    scope = cgroup_scope(p['pid'])
    return 'scope:' + scope if scope else f"pid:{p['pid']}"

# A cgroup running more distinct programs than this is a desktop session, not
# an application. The compositor's own unit holds the shell, Xwayland, ssh,
# clipboard watchers and every helper launched without its own scope; calling
# that one app, named after whichever member is largest, would be a lie.
SESSION_PROGRAMS = 5

# History ranges served to the panel; keep in sync with Model.js RANGES.
HISTORY_RANGES = (3600, 86400, 604800)

def families(live, procs, windows):
    groups = {}
    for p in live:
        groups.setdefault(group_of(p, procs, windows), []).append(p)
    for key, members in list(groups.items()):
        if key.startswith('scope:') and len({m['name'] for m in members}) > SESSION_PROGRAMS:
            del groups[key]
            for m in members:
                groups[f"pid:{m['pid']}"] = [m]
    rows = []
    for members in groups.values():
        members.sort(key=lambda p: p['rss'], reverse=True)
        lead = members[0]
        # Resident sizes count shared pages once per process and must never be
        # added. Only a group whose every member reports Pss has a total.
        partial = any(m['pss'] is None for m in members)
        names = []
        for m in members:
            if m['name'] not in names:
                names.append(m['name'])
        rows.append({'pid': lead['pid'], 'start': lead['start'], 'name': lead['name'],
                     'rss': lead['rss'], 'swap': sum(m['swap'] for m in members),
                     'pss': None if partial else sum(m['pss'] for m in members),
                     'owned': lead['owned'], 'count': len(members), 'names': names[:3]})
    # A complete group ranks on its summed proportional RAM. One with an
    # unreadable member has no honest total, so it ranks on its largest
    # resident process, which is what the flat list would have shown anyway.
    rows.sort(key=lambda g: g['pss'] if g['pss'] is not None else g['rss'], reverse=True)
    return rows[:24]

def hoarders():
    query = CommandBudget()
    procs = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            p = process(entry.name)
            if p:
                procs[p['pid']] = p
    wins = clients(query)
    windows = {c['pid']: c for c in wins}
    live = [p for p in procs.values() if p['rss'] > 0]
    for p in live:
        try:
            p['owned'] = Path(f"/proc/{p['pid']}").stat().st_uid == os.getuid()
        except OSError:
            p['owned'] = False
        # Proportional RAM is the only figure a group may sum, so it is read
        # for every process we own, not just the ones the flat list shows.
        # Measured on a 369-process session: 140ms against 96ms for the top 24.
        p['pss'] = fields(read(f"/proc/{p['pid']}/smaps_rollup")).get('Pss') if p['owned'] else None
    live = [p for p in live if scanned(p)]

    resolved = {}
    def target(p):
        if p['pid'] not in resolved:
            resolved[p['pid']] = target_for(p, procs, wins, query) if p['owned'] else {}
        return resolved[p['pid']]

    rows = sorted(live, key=lambda p: p['rss'], reverse=True)[:24]
    groups = families(live, procs, windows)
    for p in rows:
        p['target'] = target(p)
    for g in groups:
        g['target'] = target(procs[g['pid']])
    return [public_row(p) for p in rows], [public_row(g) for g in groups]

def metrics(previous=None):
    m = fields(read('/proc/meminfo'))
    total = m.get('MemTotal', 0)
    if not total or 'MemAvailable' not in m:
        raise RuntimeError('Kernel memory telemetry unavailable')
    available = max(0, min(total, m['MemAvailable']))
    psi = {}
    for line in read('/proc/pressure/memory').splitlines():
        parts = line.split()
        psi[parts[0]] = {k: float(v) for k, v in (s.split('=') for s in parts[1:])}
    vm = {}
    for line in read('/proc/vmstat').splitlines():
        k, v = line.split()
        if k in ('pswpin', 'pswpout', 'pgmajfault'):
            vm[k] = int(v)
    ts = time.time()
    elapsed = ts - previous['ts'] if previous else 0
    rates = {k: max(0, vm.get(k, 0) - previous.get('vm', {}).get(k, vm.get(k, 0))) / elapsed if elapsed > 0 else 0 for k in ('pswpin', 'pswpout', 'pgmajfault')}
    swaps = []
    for line in read('/proc/swaps').splitlines()[1:]:
        s = line.split()
        if len(s) >= 5:
            swaps.append({'name': s[0], 'total': int(s[2])*1024, 'used': int(s[3])*1024, 'priority': int(s[4])})
    zram = {'original': 0, 'physical': 0}
    for f in Path('/sys/block').glob('zram*/mm_stat'):
        v = read(f).split()
        if len(v) >= 3:
            zram['original'] += int(v[0])
            zram['physical'] += int(v[2])
    return {'ts': ts, 'total': total, 'available': available, 'used': total-available,
            'availablePct': available/total*100, 'usedPct': (total-available)/total*100,
            'free': m.get('MemFree', 0), 'cache': max(0, m.get('Cached', 0)+m.get('SReclaimable', 0)+m.get('Buffers', 0)-m.get('Shmem', 0)),
            'dirty': m.get('Dirty', 0), 'writeback': m.get('Writeback', 0),
            'swapTotal': m.get('SwapTotal', 0), 'swapUsed': m.get('SwapTotal', 0)-m.get('SwapFree', 0),
            'psi': psi, 'rates': rates, 'vm': vm, 'swaps': swaps, 'zram': zram,
            'pageSize': os.sysconf('SC_PAGE_SIZE'), 'details': {k: m.get(k, 0) for k in ('AnonPages', 'Shmem', 'Slab', 'PageTables', 'Unevictable', 'Committed_AS')}}

# State files fall into two classes, and a symlink means a different thing to
# each. Replaced files are written with tempfile.mkstemp and Path.replace():
# rename(2) does not follow a symlink at the destination, so it replaces the
# link itself rather than writing through it. Refusing there would cost a
# deliberate dotfiles arrangement its setup and buy nothing atomic() has not
# already bought. snapshot.tmp is the fixed name an older release wrote to; it
# is listed so an existing one is repaired rather than left at its old mode.
REPLACED_STATE = ('snapshot.json', 'history.json', 'snapshot.tmp')
# Opened in place, by path, so a symlink is genuinely followed and written
# through: sqlite opens the database and its sidecars, and the two locks and
# the flush stamp are opened directly.
IN_PLACE_STATE = ('history.sqlite3', 'history.sqlite3-wal', 'history.sqlite3-shm',
                  'history.sqlite3-journal', 'collector.lock', 'flush.lock', 'last-flush')


def inspect_state(directory, name):
    """Vet one state file without following a link, repairing its mode.

    Returns None when the file is absent or fine, and a reason otherwise. The
    caller decides what an unsafe file costs, because that differs by file.
    """
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=directory)
    except FileNotFoundError:
        return None
    except OSError as e:
        # O_NOFOLLOW reports a symlink as ELOOP. Say what it is rather than
        # letting a bare errno reach the reader.
        return 'is a symlink' if e.errno == errno.ELOOP else str(e)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return 'is not a regular file'
        if info.st_uid != os.getuid():
            return 'is owned by another user'
        if info.st_nlink != 1:
            return 'has more than one hard link'
        os.fchmod(fd, 0o600)
        return None
    finally:
        os.close(fd)


def prepare_state(strict=True):
    """Make the state directory private and vet the files in it.

    Returns {name: reason} for files that are not safe to write. Ownership and
    O_NOFOLLOW on the directory itself are unconditional either way.

    strict=True is the interactive path -- snapshot, focus, flush -- where a
    person is waiting on the answer and an unsafe in-place file should stop
    them with a message. The daemon passes strict=False and decides per file:
    the unit is Restart=on-failure, so raising here would turn one actionable
    problem into an endless five-second restart cycle.
    """
    # The README promises a 0700 directory of 0600 files. mkdir's mode applies
    # only when it creates the directory, so an existing state directory, or a
    # file left behind by an older release, keeps whatever mode it already had.
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    unsafe = {}
    try:
        if os.fstat(directory).st_uid != os.getuid():
            raise RuntimeError('RAM Pulse state directory is not owned by this user.')
        os.fchmod(directory, 0o700)
        for name in REPLACED_STATE:
            reason = inspect_state(directory, name)
            if reason:
                unsafe[name] = reason
        for name in IN_PLACE_STATE:
            reason = inspect_state(directory, name)
            if reason:
                if strict:
                    raise RuntimeError('Unsafe RAM Pulse state file: ' + name + ' ' + reason)
                unsafe[name] = reason
    finally:
        os.close(directory)
    return unsafe

def db_open():
    db = sqlite3.connect(STATE / 'history.sqlite3', timeout=1)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, used REAL, swap REAL, psi REAL, total INTEGER, boot TEXT)')
        return db
    except BaseException:
        db.close()
        raise

_BOOT_ID = ''

def record(db, m):
    global _BOOT_ID
    boot = _BOOT_ID or read('/proc/sys/kernel/random/boot_id').strip()
    if boot:
        _BOOT_ID = boot
    db.execute('INSERT OR REPLACE INTO samples (ts,used,swap,psi,total,boot) VALUES (?,?,?,?,?,?)', (m['ts'], m['usedPct'], 100*m['swapUsed']/m['swapTotal'] if m['swapTotal'] else 0, m['psi'].get('some', {}).get('avg10', 0), m['total'], boot))
    db.execute('DELETE FROM samples WHERE ts < ?', (m['ts']-7*86400,))
    db.commit()

def history(db, seconds, now=None):
    now = now or time.time()
    bucket = max(15, seconds/240)
    # Boot is part of each bucket; never connect a line across a reboot.
    rows = db.execute('SELECT MIN(ts), AVG(used), MAX(used), AVG(swap), MAX(psi), COUNT(*), boot FROM samples WHERE ts>=? AND ts<=? GROUP BY CAST(ts/? AS INTEGER), boot ORDER BY MIN(ts)', (now-seconds, now, bucket)).fetchall()
    return {'seconds': seconds, 'bucket': bucket, 'now': now, 'points': rows, 'count': sum(r[5] for r in rows), 'peak': max((r[2] for r in rows), default=0)}

def atomic(name, value):
    # A fixed .tmp name inherits whatever mode a previous interrupted write
    # left on it; mkstemp always creates a fresh owner-only file.
    path = STATE / name
    payload = json.dumps(value, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    fd, filename = tempfile.mkstemp(prefix='.' + name + '.', suffix='.tmp', dir=STATE)
    tmp = Path(filename)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(payload)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)

def daemon():
    # prepare_state() still refuses an unsafe state directory outright --
    # ownership and O_NOFOLLOW on the directory itself are unconditional even
    # when strict=False. That refusal must not escape as an exception: the
    # unit is Restart=on-failure, so exiting nonzero here turns one actionable
    # problem (a symlinked or foreign-owned state directory) into an endless
    # five-second restart cycle. Report it and stop quietly instead, the same
    # way an unsafe collector.lock below does.
    try:
        unsafe = prepare_state(strict=False)
    except (OSError, RuntimeError) as e:
        print(f'RAM Pulse: not starting, unsafe state directory: {e}', flush=True)
        return
    # collector.lock is opened by path and is the first thing this function
    # touches, so an unsafe one cannot be worked around. Return rather than
    # raise: the unit is Restart=on-failure, so exiting zero leaves one clear
    # message in the journal instead of an endless five-second restart cycle.
    if 'collector.lock' in unsafe:
        print('RAM Pulse: not starting, collector.lock ' + unsafe['collector.lock'], flush=True)
        return
    # An unsafe database costs history, not the whole recorder. This is the
    # isolation the snapshot loop already applies to a corrupt database: keep
    # publishing current memory, and say in the dashboard why history stopped.
    blocked = sorted(n for n in unsafe if n.startswith('history.sqlite3'))
    warned = sorted(n for n in unsafe if not n.startswith('history.sqlite3'))
    with (STATE / 'collector.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        db = None
        previous = None
        last_history = last_procs = 0
        rows, groups = [], []
        errors = {}
        if blocked:
            errors['history'] = '; '.join(n + ' ' + unsafe[n] for n in blocked)
            print('RAM Pulse history: ' + errors['history'], flush=True)
        if warned:
            # Replaced by rename(2), so nothing is written through the link.
            # Still worth surfacing: the reader chose that layout or did not.
            errors['state'] = '; '.join(n + ' ' + unsafe[n] for n in warned)
            print('RAM Pulse state: ' + errors['state'], flush=True)
        try:
            while True:
                start = time.monotonic()
                try:
                    m = metrics(previous)
                    if start-last_history >= 15 and not blocked:
                        last_history = start
                        try:
                            if db is None:
                                db = db_open()
                            record(db, m)
                            atomic('history.json', {str(s): history(db, s, m['ts']) for s in HISTORY_RANGES})
                            errors.pop('history', None)
                        except (OSError, sqlite3.Error, RuntimeError, ValueError) as e:
                            errors['history'] = str(e)
                            print(f'RAM Pulse history: {type(e).__name__}: {e}', flush=True)
                            if db is not None:
                                db.close()
                                db = None
                    if start-last_procs >= 9:
                        last_procs = start
                        try:
                            rows, groups = hoarders()
                            errors.pop('processes', None)
                        except (OSError, RuntimeError, ValueError) as e:
                            rows, groups = [], []
                            errors['processes'] = str(e)
                            print(f'RAM Pulse processes: {type(e).__name__}: {e}', flush=True)
                    m['hoarders'] = rows
                    m['groups'] = groups
                    m['collectorErrors'] = dict(errors)
                    atomic('snapshot.json', {k: v for k, v in m.items() if k != 'vm'})
                    previous = m
                except (OSError, sqlite3.Error, RuntimeError, ValueError) as e:
                    print(f'RAM Pulse: {type(e).__name__}: {e}', flush=True)
                time.sleep(max(0.2, 3-(time.monotonic()-start)))
        finally:
            if db is not None:
                db.close()

def focus(pid, start):
    # Re-read identity and routing on click; an old snapshot cannot focus a
    # recycled PID or run a command supplied by a window title.
    p = process(pid)
    if not p or p['start'] != start or Path(f'/proc/{pid}').stat().st_uid != os.getuid():
        raise RuntimeError('Process exited or identity changed. Refresh the list.')
    procs = {int(f.name): q for f in Path('/proc').iterdir() if f.name.isdigit() for q in [process(f.name)] if q}
    target = target_for(p, procs, clients())
    if not target:
        raise RuntimeError('No existing window or attached session for this process.')
    host = target.get('host', {})
    # The socket was valid when the scan read it; re-check at use. A stale
    # or replaced path degrades to plain window focus, not a failed click.
    if host.get('socket') and not owned_socket(host['socket']):
        host = {}
    if host.get('kind') == 'herdr':
        for kind, pattern in [('workspace', r'w[\w-]{1,32}'), ('tab', r'w[\w-]{1,32}:t[\w-]{1,32}'), ('pane', r'w[\w-]{1,32}:p[\w-]{1,32}')]:
            value = host.get(kind, '')
            if not re.fullmatch(pattern, value, re.ASCII):
                continue
            request = {'id': 'ram-pulse:'+kind, 'method': kind+'.focus', 'params': {kind+'_id': value}}
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2)
                s.connect(host['socket'])
                s.sendall((json.dumps(request)+'\n').encode())
                reply = b''
                while b'\n' not in reply and len(reply) < 65536:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    reply += chunk
                response = json.loads(reply.split(b'\n')[0])
                if response.get('id') != request['id'] or 'error' in response or 'result' not in response:
                    raise RuntimeError('Herdr could not focus this pane.')
    elif host.get('kind') == 'tmux':
        prefix = ['tmux', '-S', host['socket']]
        for cmd in [['select-window', '-t', host['pane']], ['select-pane', '-t', host['pane']], ['switch-client', '-c', host['client'], '-t', host['pane']]]:
            result = subprocess.run(prefix+cmd, capture_output=True, timeout=2)
            if result.returncode:
                raise RuntimeError('tmux could not focus this pane.')
    version = run(['hyprctl', 'version', '-j'])
    try:
        v = json.loads(version)
        match = re.search(r'(\d+)\.(\d+)', v.get('tag', v.get('version', '')))
        lua = bool(match and (int(match[1]), int(match[2])) >= (0, 56))
    except (ValueError, TypeError):
        lua = False
    addr = target['address']
    args = ['hyprctl', 'dispatch'] + ([f'hl.dsp.focus({{ window = "address:{addr}" }})'] if lua else ['focuswindow', 'address:'+addr])
    response = run(args)
    if not response or 'error' in response.lower():
        raise RuntimeError('Window focus failed; the window may have closed.')
    return {'message': 'Focused '+p['name']}

def flush():
    # sync is data-safe, unprivileged, and never discards a page. It can block
    # behind storage I/O; the UI runs this in a separate asynchronous process.
    with (STATE / 'flush.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A flush is already in progress.')
        last = float(read(STATE / 'last-flush') or 0)
        if time.time()-last < 60:
            raise RuntimeError('Wait one minute between flushes.')
        before = metrics()
        (STATE / 'last-flush').write_text(str(time.time()))
        os.sync()
        after = metrics()
        return {'message': f"Pending writes: {before['dirty']/1048576:.1f} → {after['dirty']/1048576:.1f} MiB. Available: {before['available']/1073741824:.1f} → {after['available']/1073741824:.1f} GiB. Cache remains reusable."}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['daemon', 'snapshot', 'focus', 'flush'])
    parser.add_argument('pid', nargs='?', type=int)
    parser.add_argument('start', nargs='?')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.action == 'daemon':
            daemon()
            return
        prepare_state()
        if args.action == 'snapshot':
            value = {k: v for k, v in metrics().items() if k != 'vm'}
        else:
            value = focus(args.pid, args.start) if args.action == 'focus' else flush()
        print(json.dumps(value))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
