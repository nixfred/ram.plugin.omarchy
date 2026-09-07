import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ram', Path(__file__).resolve().parents[1]/'ram_pulse.py')
ram = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ram)

class MemoryTests(unittest.TestCase):
    def test_state_directory_defaults_for_unset_or_empty_xdg_state_home(self):
        home = Path('/example/home')
        default = home / '.local/state/ram-pulse'
        for env, expected in [({}, default), ({'XDG_STATE_HOME': ''}, default),
                              ({'XDG_STATE_HOME': '/example/state'}, Path('/example/state/ram-pulse'))]:
            with self.subTest(env=env), patch.dict(ram.os.environ, env, clear=True), patch.object(Path, 'home', return_value=home):
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertEqual(module.STATE, expected)

    def test_memavailable_not_memfree_defines_usage(self):
        original = ram.read
        raw = 'MemTotal: 1000 kB\nMemAvailable: 400 kB\nMemFree: 20 kB\nCached: 300 kB\nSReclaimable: 100 kB\nShmem: 50 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n'
        with patch.object(ram,'read',side_effect=lambda p: raw if p=='/proc/meminfo' else original(p)):
            m=ram.metrics()
        self.assertEqual(m['used'],600*1024)
        self.assertEqual(m['availablePct'],40)
        self.assertEqual(m['cache'],350*1024)
        self.assertEqual(m['swapUsed'],0)

    def test_missing_telemetry_not_zero_memory(self):
        with patch.object(ram,'read',return_value=''):
            with self.assertRaises(RuntimeError):ram.metrics()

    def test_counter_reset_never_negative(self):
        prev=ram.metrics();prev['ts']-=3
        prev['vm']={k:10**30 for k in prev['vm']}
        self.assertTrue(all(v>=0 for v in ram.metrics(prev)['rates'].values()))

    def test_process_stat_with_parentheses(self):
        # Field 22 (starttime) is index 19 in the tail after comm.
        tail=['S','7']+['0']*17+['98765']+['0']*5
        with patch.object(ram,'read',side_effect=lambda p:'12 (strange (name)) '+' '.join(tail) if str(p).endswith('/stat') else 'VmRSS: 42 kB\nVmSwap: 3 kB'):
            p=ram.process(12)
        self.assertEqual(p['start'],'98765');self.assertEqual(p['ppid'],7)
        self.assertEqual(p['rss'],42*1024)

    def test_ancestry_cycle_is_bounded(self):
        self.assertIsNone(ram.window_for(5,{5:{'ppid':6},6:{'ppid':5}},{}))
        self.assertEqual(ram.window_for(5,{5:{'ppid':6}},{6:{'address':'0xabc'}})['address'],'0xabc')

    def test_cgroup_only_groups_on_a_unit_leaf(self):
        for raw, expect in [('0::/user.slice/app-brave-1.scope', '0::/user.slice/app-brave-1.scope'),
                            ('0::/user.slice/voxtype.service', '0::/user.slice/voxtype.service'),
                            ('0::/user.slice/user-1000.slice', ''),
                            ('0::/', ''), ('', '')]:
            with patch.object(ram, 'read', return_value=raw):
                self.assertEqual(ram.cgroup_scope(9), expect)

    def test_same_unit_name_under_two_hierarchies_is_not_one_app(self):
        members = [{'pid': n, 'ppid': 1, 'start': str(n), 'name': 'worker',
                    'rss': 100, 'pss': 50, 'swap': 0, 'owned': True} for n in (11, 12)]
        def read_scope(path):
            user = '1000' if '/11/' in str(path) else '1001'
            return f'0::/user.slice/user-{user}.slice/worker.service'
        with patch.object(ram, 'read', side_effect=read_scope):
            groups = ram.families(members, {p['pid']: p for p in members}, {})
        self.assertEqual(len(groups), 2)
        self.assertEqual([g['count'] for g in groups], [1, 1])

    def test_cgroup_prefers_the_unified_hierarchy_over_a_legacy_entry(self):
        raw = '5:name=systemd:/user.slice/legacy.service\n0::/user.slice/unified.service\n'
        with patch.object(ram, 'read', return_value=raw):
            self.assertEqual(ram.cgroup_scope(7), '0::/user.slice/unified.service')

    def test_cgroup_falls_back_to_a_named_systemd_hierarchy(self):
        raw = '9:memory:/user.slice/ignored.service\n5:name=systemd:/user.slice/legacy.service\n'
        with patch.object(ram, 'read', return_value=raw):
            self.assertEqual(ram.cgroup_scope(7), '5:name=systemd:/user.slice/legacy.service')

    def test_group_key_prefers_the_window_then_the_scope_then_the_process(self):
        procs = {5: {'pid': 5, 'ppid': 9}, 9: {'pid': 9, 'ppid': 1}}
        windows = {9: {'address': '0xabc'}}
        self.assertEqual(ram.group_of(procs[5], procs, windows), 'window:0xabc')
        with patch.object(ram, 'read', return_value='0::/user.slice/voxtype.service'):
            self.assertEqual(ram.group_of(procs[5], procs, {}), 'scope:0::/user.slice/voxtype.service')
        with patch.object(ram, 'read', return_value='0::/'):
            self.assertEqual(ram.group_of(procs[5], procs, {}), 'pid:5')

    def test_a_process_that_exited_mid_scan_is_dropped_not_counted(self):
        import os
        gone = {'pid': 99999999, 'owned': True, 'pss': None}
        here = {'pid': os.getpid(), 'owned': True, 'pss': None}
        self.assertFalse(ram.scanned(gone))
        # Unreadable but still running: a root command in our own terminal.
        self.assertTrue(ram.scanned(here))
        self.assertTrue(ram.scanned({'pid': 99999999, 'owned': False, 'pss': None}))
        self.assertTrue(ram.scanned({'pid': 99999999, 'owned': True, 'pss': 10}))

    def _member(self, pid, rss, pss, name='brave', swap=0):
        return {'pid': pid, 'ppid': 1, 'start': str(pid), 'name': name,
                'rss': rss, 'swap': swap, 'pss': pss, 'owned': True}

    def _under_window(self, *pids):
        procs = {n: {'pid': n, 'ppid': 9} for n in pids}
        procs[9] = {'pid': 9, 'ppid': 1}
        return procs, {9: {'address': '0xabc'}}

    def test_group_sums_pss_and_never_sums_rss(self):
        procs, windows = self._under_window(11, 12)
        live = [self._member(11, 500, 400, swap=7), self._member(12, 300, 90, swap=3)]
        g = ram.families(live, procs, windows)[0]
        self.assertEqual(g['pss'], 490)
        self.assertEqual(g['swap'], 10)
        # The largest single resident process, not 800.
        self.assertEqual(g['rss'], 500)
        self.assertEqual(g['count'], 2)
        self.assertEqual(g['pid'], 11)

    def test_group_with_an_unreadable_member_has_no_total(self):
        procs, windows = self._under_window(11, 12)
        live = [self._member(11, 500, 400), self._member(12, 300, None)]
        g = ram.families(live, procs, windows)[0]
        self.assertIsNone(g['pss'])
        self.assertEqual(g['count'], 2)

    def test_incomplete_group_ranks_on_resident_not_ahead_of_a_real_total(self):
        procs = {11: {'pid': 11, 'ppid': 0}, 12: {'pid': 12, 'ppid': 0}}
        live = [self._member(11, 100, 100, name='small'), self._member(12, 90, None, name='opaque')]
        with patch.object(ram, 'read', return_value='0::/'):
            names = [g['name'] for g in ram.families(live, procs, {})]
        self.assertEqual(names, ['small', 'opaque'])

    def test_a_session_wide_cgroup_is_not_an_app(self):
        procs = {n: {'pid': n, 'ppid': 0} for n in range(11, 18)}
        live = [self._member(n, 100*n, 10*n, name='prog%d' % n) for n in range(11, 18)]
        with patch.object(ram, 'read', return_value='0::/user.slice/wayland-wm@hyprland.desktop.service'):
            groups = ram.families(live, procs, {})
        self.assertEqual([g['count'] for g in groups], [1]*7)
        # Five distinct programs is still one application.
        with patch.object(ram, 'read', return_value='0::/user.slice/app-x.scope'):
            groups = ram.families(live[:5], procs, {})
        self.assertEqual([g['count'] for g in groups], [5])

    def test_group_names_are_distinct_and_capped(self):
        procs, windows = self._under_window(11, 12, 13, 14, 15)
        names = ['brave', 'brave', 'foot', 'bash', 'tail']
        live = [self._member(11+i, 100-i, 1, name=names[i]) for i in range(5)]
        g = ram.families(live, procs, windows)[0]
        self.assertEqual(g['count'], 5)
        self.assertEqual(g['names'], ['brave', 'foot', 'bash'])

    def test_environment_allowlist(self):
        with patch.object(ram,'read',return_value='TOKEN=secret\0HERDR_PANE_ID=w1:p2\0PASSWORD=secret\0'):
            self.assertEqual(ram.environment(1),{'HERDR_PANE_ID':'w1:p2'})

    def test_recycled_pid_cannot_focus(self):
        with patch.object(ram,'process',return_value={'start':'new'}),patch.object(ram,'run') as run:
            with self.assertRaises(RuntimeError):ram.focus(100,'old')
            run.assert_not_called()

    def test_history_retention_peak_and_boot_gaps(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ram,'STATE',Path(d)):
            db=ram.db_open()
            now=1000000
            def add(ts,used,boot):
                db.execute('INSERT INTO samples VALUES(?,?,?,?,?,?)',(ts,used,20,1,100,boot))
            add(now-604900,20,'old')
            add(now-20,30,'a');add(now-18,80,'a');add(now-17,50,'b')
            db.commit()
            h=ram.history(db,3600,now)
            self.assertEqual(h['count'],3);self.assertEqual(h['peak'],80)
            self.assertEqual({p[6] for p in h['points']},{'a','b'})
            m=ram.metrics();m.update(ts=now,usedPct=40)
            ram.record(db,m)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM samples WHERE ts<?',(now-604800,)).fetchone()[0],0)
            db.close()
            db=ram.db_open();self.assertEqual(ram.history(db,3600,now)['count'],4);db.close()

    def test_flush_is_sync_only_and_rate_limited(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ram,'STATE',Path(d)),patch.object(ram.os,'sync') as sync:
            self.assertIn('Cache remains reusable',ram.flush()['message'])
            sync.assert_called_once()
            with self.assertRaises(RuntimeError):ram.flush()

    def test_unknown_action_rejected(self):
        import subprocess
        p=subprocess.run(['python3',str(Path(ram.__file__)),'kill'],capture_output=True)
        self.assertEqual(p.returncode,2)

if __name__=='__main__':unittest.main()
