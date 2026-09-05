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
