"""Regression: V1.0.19.1 scheduled duration and final Ping result."""
import csv
import logging
from pathlib import Path
import tempfile
import threading
import time
import unittest
from continuous_ping import ContinuousPing
from ping_judgement import initial_fields, on_completed
from session_runner import run_session

class FinalDecisionTests(unittest.TestCase):
    def record(self, **kw):
        return dict(status='ONLINE',sent=100,failed=0,max_consecutive=0,**initial_fields(),**kw)

    def test_scheduled_short_run_changes_monitoring_to_pass(self):
        a=self.record()
        self.assertEqual(on_completed(a,'t',completed=True),'SHORT_RUN_UNDER_8H')
        self.assertEqual(a['test_result'],'PASS')
        self.assertEqual(a['checkpoints_completed'],0)

    def test_manual_stop_stays_monitoring(self):
        a=self.record()
        self.assertEqual(on_completed(a,'t',completed=False),'STOPPED_BEFORE_COMPLETION')
        self.assertEqual(a['test_result'],'MONITORING')

    def test_existing_fail_remains_latched(self):
        a=self.record();a.update(test_result='FAIL', fail_reason='MAX_CONSECUTIVE_LOSS_EXCEEDED',fail_time='first')
        self.assertEqual(on_completed(a,'t',completed=True),'FAIL_LATCHED')
        self.assertEqual((a['test_result'],a['fail_time']),('FAIL','first'))

    def test_no_samples_cannot_pass(self):
        a=self.record();a['sent']=0
        self.assertEqual(on_completed(a,'t',completed=True),'NO_VALID_PING_DATA')
        self.assertEqual(a['test_result'],'MONITORING')

    def test_final_csv_and_callback(self):
        m={1:{'ip':'192.168.2.121'}}
        notifications=[]
        with tempfile.TemporaryDirectory() as td:
            mon=ContinuousPing(m,td,threading.Event(),interval=.02,ping_fn=lambda ip:(True,1.0,''),callback=lambda onu,row:notifications.append(row['test_result']))
            mon.start();time.sleep(.08);mon.stop(completed=True)
            self.assertEqual(mon.snapshot()[1]['test_result'],'PASS')
            self.assertEqual(notifications[-1],'PASS')
            with (Path(td)/'continuous_ping_summary.csv').open(encoding='utf-8-sig') as f:
                r=list(csv.DictReader(f))[0]
            self.assertEqual(r['Test Result'],'PASS')
            self.assertEqual(r['Final Assessment'],'SHORT_RUN_UNDER_8H')

    def test_real_session_waits_until_configured_duration(self):
        class Client:
            def open(self):pass
            def _login_sequence(self):pass
            def command(self, cmd,timeout):
                if cmd=='show onu state':return 'OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\ngpon-olt(config-pon-0/1)#\n'
                if cmd=='show onu time-stamp':return 'onu id : 1\nlast regist time : 2026-11-26 10:00:00\nlast deregist time : N/A\nlast deregist reason : N/A\nalive time : 00:01:00\ngpon-olt(config-pon-0/1)#\n'
                return 'ONU ID : 1\nRx optical level(ONU) : -26.78\nTx optical level : 6.96\nPower feed voltage : 3.30(V)\nLaser bias current : 40.632(mA)\nTemperature : 62.188(C)\ngpon-olt(config-pon-0/1)#\n'
            def close(self):pass
        with tempfile.TemporaryDirectory() as td:
            target=.38
            start=time.monotonic()
            outcome=run_session(Client,td,logging.getLogger('short-run'),threading.Event(),loop=True,
                  interval_min=.0018,duration_hr=target/3600,
                  mapping={1:{'ip':'192.168.2.121','gpon_sn':'CMTDc0112255','mac':'3872C0112255'}},
                  ping_interval=.02,ping_fn=lambda ip:(True,1.0,''))
            elapsed=time.monotonic()-start
            self.assertGreaterEqual(elapsed,target-.012)
            self.assertEqual(outcome['status'],'COMPLETED')
            self.assertEqual(outcome['ping_final']['1']['test_result'],'PASS')
            self.assertEqual(outcome['ping_final_assessment'][1],'SHORT_RUN_UNDER_8H')
            self.assertGreaterEqual(outcome['cycles'],3)

if __name__=='__main__':unittest.main()

class FinalCheckpointTests(unittest.TestCase):
    def test_8h_checkpoint_reconciled_at_stop(self):
        with tempfile.TemporaryDirectory() as td:
            mon=ContinuousPing({1:{'ip':'192.168.2.121'}},td,threading.Event(),interval=.03,ping_fn=lambda ip:(True,1.0,''))
            mon.start();time.sleep(.06)
            # Simulated time advance; no 8-hour wall-clock sleep required.
            with mon.lock:
                mon._start_monotonic -= 8*3600
            mon.stop(completed=True)
            r=mon.snapshot()[1]
            self.assertGreaterEqual(r['checkpoints_completed'],1)
            self.assertEqual(r['test_result'],'PASS')
            with (Path(td)/'continuous_ping_checkpoints.csv').open(encoding='utf-8-sig') as f:
                checks=list(csv.DictReader(f))
            self.assertEqual(checks[0]['Elapsed Hours'],'8')
            self.assertEqual(checks[0]['Checkpoint Result'],'PASS')
