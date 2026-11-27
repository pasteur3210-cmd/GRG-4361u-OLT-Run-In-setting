"""Release gate: late Ping FAIL must be reflected in final Excel, never rewrite cycle history."""
import csv
import json
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from excel_record import build_rows
from session_runner import run_session,rebuild_excel,read_journal

MAPPING={1:{'ip':'192.168.2.121','mac':'3872C0112255','lan_mac':'3872C0112255',
            'gpon_sn':'CMTDc0112255','match_type':'DIRECT'}}
STATE='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\n'
STAMP='onu id     last regist time        last deregist time      last deregist reason      alive time\n1/1        2026:11:23 16:47:05 N/A N/A 00:20:29\n'
OPTICAL='ONU ID : 1\nRx optical level(ONU) : -26.99\nTx optical level : 6.96\nPower feed voltage : 3.30(V)\nLaser bias current : 41.528(mA)\nTemperature : 65.172(C)\n'
class OLT:
    def open(self):pass
    def _login_sequence(self):pass
    def command(self,cmd,timeout=45):
        if cmd=='show onu state':return STATE
        if cmd=='show onu time-stamp':return STAMP
        return OPTICAL
    def close(self):pass


def read_sheet(z,num):
    root=ET.fromstring(z.read(f'xl/worksheets/sheet{num}.xml'))
    return [[c.findtext('{*}is/{*}t') if c.get('t')=='inlineStr' else c.findtext('{*}v')
             for c in row.findall('{*}c')] for row in root.findall('{*}sheetData/{*}row')]

class SessionFinalTests(unittest.TestCase):
    def test_historical_cycles_untouched_and_final_fail_rendered(self):
        cycle={'cycle':1,'time':'2026-11-27 14:20:00','onus':{1:{'status':'PASS','phase_state':'working','gpon_sn':'CMTDc0112255','data_flag':'OK'}},'result':'PASS','ping':{'1':{'result':'ONLINE','loss':0,'sent':12}}}
        final={'status':'STOPPED BY USER','cycles':1,'last_result':'FAIL','ping_final':{'1':{'result':'ONLINE','sent':100,'loss':45,'max_consecutive':45,'test_result':'FAIL','fail_reason':'MAX_CONSECUTIVE_LOSS_EXCEEDED'}},'ping_final_assessment':{'1':'FAIL'}}
        events=[{'Start':'2026-11-27T14:22:10+08:00','Recovery':'2026-11-27T14:22:55+08:00','ONU ID':'1','DUT IP':'192.168.2.121','Consecutive Loss':'45','Elapsed Seconds':'45','Status':'RECOVERED'},
                {'Start':'2026-11-27T14:22:15+08:00','Recovery':'','ONU ID':'1','DUT IP':'192.168.2.121','Consecutive Loss':'6','Elapsed Seconds':'0','Status':'RUN_IN_FAIL_CONSECUTIVE'}]
        sheets=dict(build_rows([cycle],mapping=MAPPING,final_summary=final,ping_events=events))
        self.assertEqual(sheets['01_Loop_Summary'][1][2],'PASS')
        self.assertEqual(sheets['07_Session_Final'][2],['Final Run-in Result','FAIL'])
        self.assertEqual(sheets['07_Session_Final'][11][0],'ONU ID')
        self.assertEqual(sheets['07_Session_Final'][12][8],'FAIL')
        self.assertEqual(len(sheets['04_Event_Log']),3)
    def test_end_to_end_fail_after_only_olt_cycle_and_rebuild(self):
        from unittest.mock import patch
        class LatePingMonitor:
            def __init__(self,mapping,folder,stop_event,**kwargs):
                self.folder=Path(folder);self.final_assessment={};self.stopped=False
            def start(self):pass
            def cycle_snapshot(self):
                return {'1':{'result':'ONLINE','sent':100,'loss':45,'max_consecutive':45,
                         'test_result':'FAIL','fail_reason':'MAX_CONSECUTIVE_LOSS_EXCEEDED'}} if self.stopped else {'1':{'result':'ONLINE','sent':2,'loss':0,'max_consecutive':0,'test_result':'MONITORING'}}
            def stop(self,**kwargs):
                self.stopped=True;self.final_assessment={1:'FAIL'}
                with (self.folder/'continuous_ping_events.csv').open('w',newline='',encoding='utf-8-sig') as f:
                    w=csv.writer(f);w.writerow(['Start','Recovery','ONU ID','DUT IP','Consecutive Loss','Elapsed Seconds','Status'])
                    w.writerow(['2026-11-27T14:22:15+08:00','',1,'192.168.2.121',6,0,'RUN_IN_FAIL_CONSECUTIVE'])
                    w.writerow(['2026-11-27T14:22:10+08:00','2026-11-27T14:22:55+08:00',1,'192.168.2.121',45,45,'RECOVERED'])
        with tempfile.TemporaryDirectory() as td, patch('session_runner.ContinuousPing',LatePingMonitor):
            result=run_session(OLT,td,logging.getLogger('final-run'),threading.Event(),
                               loop=False,mapping=MAPPING,
                               production_info={'PO':'14045678','Model':'GRG-4361','Operator':'QA'})
            self.assertEqual(result['cycles'],1)
            self.assertEqual(result['status'],'COMPLETED')
            self.assertEqual(result['last_result'],'FAIL')
            self.assertEqual(read_journal(td)[0]['result'],'PASS')
            with ZipFile(Path(td)/'ONU_Master_Record.xlsx') as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(len(read_sheet(z,1)),2)
                self.assertEqual(read_sheet(z,1)[1][2],'PASS')
                self.assertIn('activeTab="6"',z.read('xl/workbook.xml').decode())
                final=read_sheet(z,7)
                self.assertEqual(final[2],['Final Run-in Result','FAIL'])
                self.assertEqual(final[12][8],'FAIL')
                self.assertTrue(any('CONTINUOUS PING RUN_IN_FAIL_CONSECUTIVE' in str(row) for row in read_sheet(z,4)))
            rebuild_excel(td)
            with ZipFile(Path(td)/'ONU_Master_Record.xlsx') as z:
                self.assertEqual(read_sheet(z,7)[2],['Final Run-in Result','FAIL'])
    def test_missing_stop_files_do_not_create_fake_final(self):
        with tempfile.TemporaryDirectory() as td:
            from session_runner import append_journal
            append_journal(td,{'cycle':1,'time':'now','onus':{1:{'status':'PASS','phase_state':'working'}},'result':'PASS'})
            rebuild_excel(td)
            with ZipFile(Path(td)/'ONU_Master_Record.xlsx') as z:
                self.assertEqual(len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]),6)
