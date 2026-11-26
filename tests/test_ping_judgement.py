"""Boundary and regression verification for V1.0.18 acceptance rules."""
import csv
import tempfile
import threading
import time
import unittest
from pathlib import Path
from continuous_ping import ContinuousPing
from ping_judgement import initial_fields, on_sample, on_elapsed
from session_runner import cycle_result


def row(failed=0,max_consecutive=0):
    return dict(failed=failed,max_consecutive=max_consecutive,**initial_fields())

class AcceptanceRuleTests(unittest.TestCase):
    def test_max_consecutive_5_is_not_fail_6_is_latched(self):
        r=row(5,5)
        self.assertIsNone(on_sample(r,'t1'))
        self.assertEqual(r['test_result'],'MONITORING')
        r['max_consecutive']=6
        self.assertEqual(on_sample(r,'t2'),'MAX_CONSECUTIVE_LOSS_EXCEEDED')
        self.assertEqual(r['test_result'],'FAIL')
        self.assertEqual(r['fail_time'],'t2')
        r['max_consecutive']=6
        self.assertIsNone(on_sample(r,'t3'))
        self.assertEqual(r['test_result'],'FAIL')
        self.assertEqual(r['fail_time'],'t2')

    def test_cumulative_boundary_8_16_24_hours(self):
        r=row(failed=50)
        self.assertEqual(on_elapsed(r,8*3600-0.01,'t0'),[])
        e=on_elapsed(r,8*3600,'t1')
        self.assertEqual((e[0]['checkpoint_result'],r['test_result'],r['allowed_loss']),('PASS','PASS',50))
        r['failed']=100
        e=on_elapsed(r,16*3600,'t2')
        self.assertEqual((e[0]['checkpoint_result'],r['allowed_loss']),('PASS',100))
        r['failed']=151
        e=on_elapsed(r,24*3600,'t3')
        self.assertEqual((e[0]['checkpoint_result'],r['test_result'],r['allowed_loss']),('FAIL','FAIL',150))
        self.assertEqual(r['fail_reason'],'CUMULATIVE_LOSS_LIMIT_EXCEEDED')
        r['failed']=151
        on_elapsed(r,32*3600,'t4')
        self.assertEqual(r['test_result'],'FAIL')
        self.assertEqual(r['fail_time'],'t3')

    def test_51_at_first_8h_fails_not_before(self):
        r=row(failed=51)
        self.assertEqual(on_elapsed(r,7*3600,'before'),[])
        self.assertEqual(r['test_result'],'MONITORING')
        e=on_elapsed(r,8*3600,'checkpoint')
        self.assertEqual(e[0]['checkpoint_result'],'FAIL')
        self.assertEqual(r['test_result'],'FAIL')

    def test_cumulative_not_independent_windows(self):
        r=row(failed=35)
        on_elapsed(r,8*3600,'8h')
        r['failed']=95 # additional 60 is allowed under cumulative scheme A
        e=on_elapsed(r,16*3600,'16h')
        self.assertEqual((e[0]['checkpoint_result'],r['test_result']),('PASS','PASS'))

    def test_previous_8h_fail_is_never_reversed(self):
        r=row(failed=60)
        on_elapsed(r,8*3600,'8h')
        r['failed']=90
        on_elapsed(r,16*3600,'16h')
        self.assertEqual(r['test_result'],'FAIL')
        self.assertEqual(r['fail_time'],'8h')

    def test_missed_checkpoints_each_recorded_and_locked(self):
        r=row(failed=160)
        events=on_elapsed(r,24*3600,'now')
        self.assertEqual(len(events),3)
        self.assertEqual([e['allowed'] for e in events],[50,100,150])
        self.assertEqual(r['test_result'],'FAIL')

    def test_no_extra_four_packet_cycle_failure(self):
        units={1:dict(phase_state='working',status='PASS',data_flag='OK',gpon_sn='CMTDABC000001')}
        mapping={1:{'gpon_sn':'CMTDABC000001'}}
        self.assertEqual(cycle_result(units,'',{1}, {'1':{'result':'TIMEOUT','test_result':'MONITORING'}},mapping),'PASS')
        self.assertEqual(cycle_result(units,'',{1}, {'1':{'result':'ONLINE','test_result':'FAIL'}},mapping),'FAIL')

    def test_real_worker_consecutive_fail_and_summary(self):
        outcomes=iter([False]*6+[True]*100)
        def fake(ip):
            try:v=next(outcomes)
            except StopIteration:v=True
            return v, 1 if v else None,''
        with tempfile.TemporaryDirectory() as td:
            mon=ContinuousPing({1:{'ip':'192.168.2.121'}},td,threading.Event(),interval=.01,ping_fn=fake)
            mon.start();time.sleep(.13);mon.stop()
            r=mon.snapshot()[1]
            self.assertEqual(r['status'],'ONLINE')
            self.assertEqual((r['test_result'],r['max_consecutive'],r['failed']),('FAIL',6,6))
            with (Path(td)/'continuous_ping_summary.csv').open(encoding='utf-8-sig') as f:
                record=list(csv.DictReader(f))[0]
                self.assertEqual(record['Test Result'],'FAIL')
                self.assertEqual(record['Fail Reason'],'MAX_CONSECUTIVE_LOSS_EXCEEDED')
            with (Path(td)/'continuous_ping.csv').open(encoding='utf-8-sig') as f:
                samples=list(csv.DictReader(f))
                self.assertEqual(samples[-1]['Test Result'],'FAIL')
            self.assertTrue((Path(td)/'continuous_ping_checkpoints.csv').exists())

if __name__=='__main__':unittest.main()
