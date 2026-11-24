import unittest
import tempfile
import threading
import logging
import json
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from onu_parser import parse_onu_state, merge_state_data
from session_runner import run_session, read_journal, rebuild_excel, cycle_result
from excel_record import build_rows, BASE_HEADERS, FIELDS

FIXTURES=Path(__file__).resolve().parent/'fixtures'
STATE=(FIXTURES/'show onu state.txt').read_text(encoding='utf-8')
STAMP=(FIXTURES/'show onu time-stamp.log').read_text(encoding='utf-8')
OPTICAL=(FIXTURES/'teraterm-show onu optical info all.log').read_text(encoding='utf-8')
PROMPT='\ngpon-olt(config-pon-0/1)#\n'

class MockClient:
    def __init__(self, scripts, calls):
        self.scripts=scripts
        self.calls=calls
        self.closed=False
    def open(self):self.calls.append('OPEN')
    def _login_sequence(self):self.calls.append('LOGIN')
    def command(self,cmd,timeout):
        self.calls.append(cmd)
        val=self.scripts[cmd]
        if isinstance(val,Exception):raise val
        return val
    def close(self):self.closed=True;self.calls.append('CLOSE')

class StateTests(unittest.TestCase):
    def test_actual_offline_and_recovered(self):
        first,second=STATE.split('gpon-olt(config-pon-0/1)# show onu state',2)[1:]
        before=parse_onu_state('gpon-olt(config-pon-0/1)# show onu state'+first)
        after=parse_onu_state(STATE)
        self.assertEqual(before[2]['phase_state'],'offline')
        self.assertEqual(before[2]['status'],'FAIL')
        self.assertEqual(before[2]['gpon_sn'],'CMTD99abe129')
        self.assertEqual(after[2]['phase_state'],'working')
        self.assertEqual(after[2]['status'],'PASS')
        self.assertEqual(after[1]['gpon_sn'],'CMTDc0112255')
    def test_admin_and_omcc_fields(self):
        s=parse_onu_state(STATE)
        self.assertEqual(s[1]['admin_state'],'enable')
        self.assertEqual(s[2]['omcc_state'],'enable')
        self.assertEqual(s[2]['channel'],'XGSPON')
    def test_never_treat_event_as_table(self):
        out=STATE+'\n2026/11/24 ONU Offline 1:2 CMTD99abe129\n'
        self.assertEqual(parse_onu_state(out)[2]['status'],'PASS')
    def test_missing_header_fails(self):
        with self.assertRaises(ValueError):parse_onu_state('ONU Online; total: 2')
    def test_sparse_16_and_20(self):
        body='OnuIndex  Admin State  OMCC State  Phase State  Channel  Serial Number\n'
        body+='\n'.join(f'1:{i} enable enable working XGSPON CMTD{i:08X}' for i in range(1,21))
        s=parse_onu_state(body)
        self.assertEqual(len(s),20)
        self.assertEqual(s[16]['phase_state'],'working')
    def test_missing_optical_does_not_change_offline_to_pass(self):
        s={2:{'onu_id':2,'status':'FAIL','phase_state':'offline'}}
        u=merge_state_data(s,{}, {})
        self.assertEqual(u[2]['status'],'FAIL')
        self.assertIn('OPTICAL',u[2]['data_flag'])
    def test_excel_new_fields_and_one_row_per_cycle(self):
        first=parse_onu_state(STATE.split('gpon-olt(config-pon-0/1)# show onu state')[0] if False else
               'OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\n1:2 enable disable offline unknown CMTD99abe129')
        second=parse_onu_state(STATE)
        cycles=[{'time':'10:00','onus':merge_state_data(first,{},{}),'result':'FAIL'},
                {'time':'10:05','onus':merge_state_data(second,{},{}),'result':'PASS'}]
        headers,*rows=build_rows(cycles)[0][1]
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][2],'FAIL')
        self.assertEqual(rows[1][2],'PASS')
        self.assertEqual(rows[0][headers.index('ONU2_Phase State')],'offline')
        self.assertEqual(rows[1][headers.index('ONU2_Phase State')],'working')
        self.assertEqual(rows[1][headers.index('ONU2_GPON SN')],'CMTD99abe129')
    def test_zero_state_is_error(self):
        self.assertEqual(cycle_result({},'',set()),'ERROR')
    def test_unknown_is_not_pass(self):
        self.assertEqual(cycle_result({1:{'status':'UNKNOWN','data_flag':'OK'}},'',{1}),'ERROR')

class LoopTests(unittest.TestCase):
    def fake_scripts(self, state=STATE, optical=OPTICAL):
        return {'show onu state':state+PROMPT,'show onu time-stamp':STAMP,
                'show onu optical-info all':optical}
    def run_for_n(self,n, scripts=None):
        with tempfile.TemporaryDirectory() as td:
            calls=[];evt=threading.Event();messages=[]
            def notify(kind, msg):
                messages.append((kind,msg))
                if kind=='CYCLE' and int(msg.split(' ')[1])>=n:evt.set()
            factory=lambda:MockClient(scripts or self.fake_scripts(),calls)
            summary=run_session(factory,td,logging.getLogger('test-runin'),evt,
                                loop=True,interval_min=0.00001,duration_hr=0,
                                notify=notify)
            journal=read_journal(td)
            with ZipFile(Path(td)/'ONU_Master_Record.xlsx') as z:
                self.assertIsNone(z.testzip())
                worksheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                rows=worksheet.findall('{*}sheetData/{*}row')
                self.assertEqual(len(rows),n+1)
            return summary,journal,calls,messages
    def test_loop_3_cycles_one_workbook_and_one_login(self):
        summary,cycles,calls,_=self.run_for_n(3)
        self.assertEqual(len(cycles),3)
        self.assertEqual(calls.count('LOGIN'),1)
        self.assertEqual(calls.count('show onu state'),3)
        self.assertEqual(summary['status'],'STOPPED BY USER')
    def test_stop_finishes_cleanly(self):
        summary,cycles,_,_=self.run_for_n(2)
        self.assertEqual(summary['cycles'],2)
        self.assertEqual([x['cycle'] for x in cycles],[1,2])
    def test_single_check_one_cycle(self):
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            summary=run_session(lambda:MockClient(self.fake_scripts(),calls),td,
                                logging.getLogger('test-runin'),threading.Event())
            self.assertEqual(summary['cycles'],1)
            self.assertEqual(summary['status'],'COMPLETED')
            self.assertTrue(Path(td,'ONU_Master_Record.xlsx').is_file())
            self.assertTrue(Path(td,'raw_cli','Loop_0001_onu_state.log').is_file())
    def test_offline_to_online_event(self):
        first='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\n1:2 enable disable offline unknown CMTD99abe129\n'+PROMPT
        second=STATE+PROMPT
        class ChangingClient(MockClient):
            count=0
            def command(self,cmd,timeout):
                if cmd=='show onu state':
                    self.count+=1
                    return first if self.count==1 else second
                return super().command(cmd,timeout)
        with tempfile.TemporaryDirectory() as td:
            evt=threading.Event()
            def notify(kind,msg):
                if kind=='CYCLE' and msg.startswith('Cycle 2 '):evt.set()
            calls=[]
            run_session(lambda:ChangingClient(self.fake_scripts(),calls),td,
                        logging.getLogger('test-runin'),evt,loop=True,
                        interval_min=0.00001,duration_hr=0,notify=notify)
            entries=read_journal(td)
            self.assertEqual(entries[0]['result'],'FAIL')
            self.assertEqual(entries[1]['result'],'PASS')
            events=[json.loads(s) for s in Path(td,'events.jsonl').read_text().splitlines()]
            self.assertEqual(events[0]['previous'],'offline')
            self.assertEqual(events[0]['current'],'working')
    def test_missing_state_query_is_logged_and_recovered(self):
        class FlakyClient(MockClient):
            n=0
            def command(self,cmd,timeout):
                if cmd=='show onu state':
                    FlakyClient.n+=1
                    if FlakyClient.n==1:raise RuntimeError('link lost')
                return super().command(cmd,timeout)
        FlakyClient.n=0
        with tempfile.TemporaryDirectory() as td:
            stop=threading.Event();calls=[]
            def notify(kind,msg):
                if kind=='CYCLE' and msg.startswith('Cycle 2 '):stop.set()
            run_session(lambda:FlakyClient(self.fake_scripts(),calls),td,
                        logging.getLogger('test-runin'),stop,loop=True,
                        interval_min=0.00001,duration_hr=0,notify=notify)
            cycles=read_journal(td)
            self.assertEqual(cycles[0]['result'],'ERROR')
            self.assertEqual(cycles[1]['result'],'PASS')
            self.assertEqual(calls.count('LOGIN'),2)
    def test_rebuild_from_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            run_session(lambda:MockClient(self.fake_scripts(),[]),td,
                        logging.getLogger('test-runin'),threading.Event())
            p=Path(td,'ONU_Master_Record.xlsx')
            p.unlink()
            rebuild_excel(td)
            self.assertTrue(p.exists())
    def test_invalid_schedule(self):
        with self.assertRaises(ValueError):
            run_session(lambda:None,'foo',logging.getLogger('x'),threading.Event(),interval_min=0)

if __name__=='__main__':unittest.main()

class EventSheetTests(unittest.TestCase):
    def test_offline_then_recovery_in_excel_event_sheet(self):
        units1={2:{'status':'FAIL','phase_state':'offline','gpon_sn':'CMTD99abe129','data_flag':'OK'}}
        units2={2:{'status':'PASS','phase_state':'working','gpon_sn':'CMTD99abe129','data_flag':'OK'}}
        sheets=build_rows([{'time':'t1','onus':units1,'result':'FAIL'},
                           {'time':'t2','onus':units2,'result':'PASS'}])
        events=dict(sheets)['04_Event_Log']
        self.assertEqual(events[1][-1],'INITIAL ABNORMAL')
        self.assertEqual(events[2][-1],'RECOVERY')
