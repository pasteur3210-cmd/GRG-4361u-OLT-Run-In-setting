import csv
import logging
from pathlib import Path
import tempfile
import threading
import time
import unittest
from zipfile import ZipFile
from continuous_ping import ContinuousPing
from session_runner import run_session,read_journal
from excel_record import build_rows

class LivePingTest(unittest.TestCase):
    def mapping(self,n=2):
        return {i:{'ip':f'192.168.2.{100+i}','gpon_sn':f'CMTDABC{i:06X}','mac':f'AABBCC{i:06X}'} for i in range(1,n+1)}

    def test_max_consecutive_never_resets(self):
        cases=iter([False]*5+[True]*2+[False]*3+[True]+[False]*6+[True])
        def fn(ip):
            try:v=next(cases)
            except StopIteration:v=True
            return v,1.5 if v else None,''
        with tempfile.TemporaryDirectory() as td:
            stop=threading.Event();m=ContinuousPing(self.mapping(1),td,stop,interval=.01,ping_fn=fn)
            m.start();time.sleep(.26);m.stop();r=m.snapshot()[1]
            self.assertGreaterEqual(r['sent'],17)
            self.assertEqual(r['max_consecutive'],6)
            self.assertEqual(r['consecutive'],0)
            self.assertEqual(r['status'],'ONLINE')
            with open(Path(td)/'continuous_ping_events.csv',encoding='utf-8-sig',newline='') as f:
                rows=list(csv.DictReader(f))
                self.assertTrue(any(x['Consecutive Loss']=='5' for x in rows))
                self.assertTrue(any(x['Consecutive Loss']=='6' for x in rows))

    def test_16_parallel_and_csv(self):
        with tempfile.TemporaryDirectory() as td:
            stop=threading.Event();m=ContinuousPing(self.mapping(16),td,stop,interval=.05,ping_fn=lambda ip:(True,2.0,''))
            m.start();time.sleep(.17);s=m.snapshot();m.stop()
            self.assertEqual(len(s),16)
            self.assertTrue(all(r['sent']>=1 for r in s.values()))
            with open(Path(td)/'continuous_ping_summary.csv',encoding='utf-8-sig',newline='') as f:
                self.assertEqual(len(list(csv.DictReader(f))),16)

    def test_error_not_packet_loss(self):
        with tempfile.TemporaryDirectory() as td:
            stop=threading.Event();m=ContinuousPing(self.mapping(1),td,stop,interval=.05,ping_fn=lambda ip:(None,None,'network tool unavailable'))
            m.start();time.sleep(.08);m.stop()
            r=m.snapshot()[1]
            self.assertEqual(r['status'],'ERROR');self.assertEqual(r['failed'],0);self.assertEqual(r['sent'],0)

    def test_csv_and_xlsx_are_separate_writers(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            stop=threading.Event();m=ContinuousPing(self.mapping(1),td,stop,interval=.01,ping_fn=lambda ip:(True,1.0,''))
            m.start()
            for i in range(3):
                time.sleep(.035)
                snap=m.cycle_snapshot()['1']
                self.assertGreater(snap['sent'],0)
                rows=build_rows([{'cycle':1,'time':'t','onus':{},'result':'INCOMPLETE','ping':{'1':snap}}],mapping=self.mapping(1))
                self.assertIn('ONU1_IP PING Result',rows[0][1][0])
            m.stop()
            self.assertFalse((Path(td)/'ONU_Master_Record.xlsx').exists())

    def test_single_session_not_four_packet_batch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            stop=threading.Event();called=[]
            class Client:
                def open(self):pass
                def _login_sequence(self):pass
                def command(self,cmd,timeout):
                    called.append(cmd)
                    if cmd=='show onu state':return 'OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDABC000001\ngpon-olt(config-pon-0/1)#\n'
                    if cmd=='show onu time-stamp':return '1/12026:11:23 16:47:05N/AN/A20:52:29\ngpon-olt(config-pon-0/1)#\n'
                    return 'ONU ID : 1\nRx optical level(ONU) : -26.78\nTx optical level : 6.96\ngpon-olt(config-pon-0/1)#\n'
                def close(self):pass
            mapping={1:{'ip':'192.168.2.101','mac':'ABCABC000001','gpon_sn':'CMTDABC000001'}}
            with patch('session_runner.ContinuousPing') as cls:
                mon=cls.return_value
                mon.cycle_snapshot.return_value={'1':{'result':'ONLINE','loss':0,'sent':12,'received':12}}
                r=run_session(Client,td,logging.getLogger('v17test'),stop,mapping=mapping)
                self.assertEqual(r['cycles'],1)
                mon.start.assert_called_once();mon.stop.assert_called_once()
                self.assertEqual(len(called),3)
                self.assertEqual(read_journal(td)[0]['ping']['1']['sent'],12)

    def test_xlsx_has_cumulative_loss(self):
        mapping={1:{'ip':'192.168.2.101','gpon_sn':'CMTDABC000001','mac':'ABCABC000001'}}
        cycle={'cycle':1,'time':'2026-11-26 01:00:00','onus':{},'result':'INCOMPLETE',
               'ping':{'1':{'result':'ONLINE','sent':200,'loss':5}}}
        summary=build_rows([cycle],mapping=mapping)[0][1]
        header,row=summary
        self.assertEqual(row[header.index('ONU1_PING Loss')],'5/200')

if __name__=='__main__':unittest.main()

class PingProtocolTests(unittest.TestCase):
    def test_win_ping_success_and_timeout(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from continuous_ping import ping_once
        def ok(*a,**kw):return SimpleNamespace(returncode=0,stdout='Reply from 192.168.2.121: bytes=32 time=2ms TTL=64',stderr='')
        def bad(*a,**kw):return SimpleNamespace(returncode=1,stdout='Request timed out.',stderr='')
        with patch('continuous_ping.sys.platform','win32'),patch('continuous_ping.subprocess.run',side_effect=ok) as run:
            self.assertEqual(ping_once('192.168.2.121')[0],True)
            self.assertEqual(run.call_args.args[0],['ping','-n','1','-w','1000','192.168.2.121'])
        with patch('continuous_ping.sys.platform','win32'),patch('continuous_ping.subprocess.run',side_effect=bad):
            self.assertEqual(ping_once('192.168.2.121')[0],False)

    def test_no_reset_on_ping_recovery_across_cycle_snapshot(self):
        calls=iter([False,False,False,False,False,True,True,True])
        def fn(ip):
            try:v=next(calls)
            except StopIteration:v=True
            return v,1 if v else None,''
        with tempfile.TemporaryDirectory() as td:
            m=ContinuousPing({1:{'ip':'192.168.2.121'}},td,threading.Event(),interval=.01,ping_fn=fn)
            m.start();time.sleep(.15);snap=m.cycle_snapshot()['1'];m.stop()
            self.assertEqual(snap['max_consecutive'],5)
            self.assertEqual(snap['result'],'ONLINE')
            self.assertEqual(snap['loss'],5)
