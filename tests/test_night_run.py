"""V1.0.16 release gate: field logs and night-run recovery."""
import datetime as dt
import json
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from onu_parser import parse_time_stamp, parse_onu_state, parse_optical, merge_state_data
from excel_record import build_rows, export_cycles
from ping_mapping import find_mac, run_ping
from session_runner import run_session, read_journal

FIX=Path(__file__).resolve().parent/'fixtures'
STATE='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\n1:2 enable enable working XGSPON CMTD99abe129\n'
OPT='ONU ID : 1\nRx optical level(ONU) : -25.0\n\nONU ID : 2\nRx optical level(ONU) : -25.5\n'
STAMP=(FIX/'night_run_timestamp_ansi.log').read_bytes().decode('utf-8')

class NightRunReleaseTests(unittest.TestCase):
    def test_real_ansi_day_uptime_and_reason(self):
        t=parse_time_stamp(STAMP)
        self.assertEqual(t[1]['alive'],'1 00:04:03')
        self.assertEqual(t[1]['dereg_reason'],'N/A')
        self.assertEqual(t[2]['alive'],'02:16:41')
        self.assertEqual(t[2]['dereg_reason'],'Onu Los')

    def test_multiple_day_and_zero_day_and_boundary(self):
        cases=[('1/1 2026:11:23 16:47:05 N/A N/A 2 00:00:00', '2 00:00:00'),
               ('1/1 2026:11:23 16:47:05 N/A N/A 12 23:59:59','12 23:59:59'),
               ('1/1 2026:11:23 16:47:05 N/A N/A 23:59:59','23:59:59'),
               ('1/1 2026:11:23 16:47:05 N/A Onu Los 1 00:00:01','1 00:00:01')]
        for text,expected in cases:
            with self.subTest(expected=expected):
                v=parse_time_stamp(text)[1]
                self.assertEqual(v['alive'],expected)
                self.assertEqual(v['dereg_reason'], 'Onu Los' if 'Onu Los' in text else 'N/A')

    def test_actual_ansi_output_export_and_timezone_metadata(self):
        merged=merge_state_data(parse_onu_state(STATE),parse_time_stamp(STAMP),parse_optical(OPT))
        cycles=[{'cycle':1,'time':'2026-11-24 23:59:59','time_zone':'+08:00','onus':merged,'result':'PASS'},
                {'cycle':2,'time':'2026-11-25 00:03:00','time_zone':'+08:00','onus':merged,'result':'PASS'}]
        sheets=dict(build_rows(cycles))
        rows=sheets['01_Loop_Summary']
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[1][rows[0].index('ONU1_Alive Time')],'1 00:04:03')
        self.assertEqual(rows[1][rows[0].index('ONU1_Dereg Reason')],'N/A')
        self.assertEqual(rows[2][1],'2026-11-25 00:03:00')
        self.assertIn(['UTC Offset at first cycle','+08:00'],sheets['06_Run_Metadata'])
        with tempfile.TemporaryDirectory() as td:
            p=export_cycles(Path(td)/'ONU_Master_Record.xlsx',cycles)
            with ZipFile(p) as z:
                self.assertIsNone(z.testzip())
                a=z.read('xl/worksheets/sheet1.xml')
                self.assertIn(b'1 00:04:03',a)
                self.assertIn(b'2026-11-25 00:03:00',a)
                for n in [x for x in z.namelist() if x.endswith('.xml')]:ET.fromstring(z.read(n))

    def test_no_timezone_available_is_honest(self):
        m=dict(build_rows([{'cycle':1,'time':'x','onus':{},'result':'ERROR'}]))
        self.assertIn(['UTC Offset at first cycle','NOT RECORDED'],m['06_Run_Metadata'])

    def test_english_windows_arp(self):
        raw='Interface: 192.168.1.34 --- 0xc\n  Internet Address      Physical Address      Type\n  192.168.2.121         38-72-c0-11-22-56     dynamic\n'
        self.assertEqual(find_mac(raw,'192.168.2.121'),'3872C0112256')

    def test_english_windows_ping_timeout_and_replies(self):
        class R: returncode=1; stderr=''; stdout='Request timed out.\n'*4
        self.assertEqual(run_ping('192.168.2.121',runner=lambda *a,**k:R())['result'],'FAIL')
        R.returncode=0
        R.stdout='Reply from 192.168.2.121: bytes=32 time<1ms TTL=64\n'*3+'Request timed out.\n'
        self.assertEqual(run_ping('192.168.2.121',runner=lambda *a,**k:R())['result'],'WARNING')

    def test_stop_during_cycle_keeps_completed_cycle(self):
        stop=threading.Event()
        class C:
            def open(self):pass
            def _login_sequence(self):pass
            def command(self,cmd,timeout):
                if cmd=='show onu optical-info all':stop.set();return OPT
                if cmd=='show onu time-stamp':return STAMP
                return STATE
            def close(self):pass
        with tempfile.TemporaryDirectory() as td:
            out=run_session(C,td,logging.getLogger('night-stop'),stop,loop=True,
                            interval_min=1,duration_hr=0)
            self.assertEqual(out['status'],'STOPPED BY USER')
            self.assertEqual(out['cycles'],1)
            self.assertEqual(len(read_journal(td)),1)
            self.assertTrue((Path(td)/'ONU_Master_Record.xlsx').exists())

    def test_rebuild_survives_stale_workbook(self):
        from session_runner import append_journal,rebuild_excel
        with tempfile.TemporaryDirectory() as td:
            base={'time':'2026-11-24 23:59:59','time_zone':'+08:00','onus':{1:{'onu_id':1,'status':'PASS','data_flag':'OK','alive':'1 00:04:03'}},'result':'PASS'}
            for n in range(1,4):append_journal(td,dict(base,cycle=n))
            path=rebuild_excel(td)
            with ZipFile(path) as z:
                doc=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                self.assertEqual(len(doc.findall('{*}sheetData/{*}row')),4)

if __name__=='__main__':unittest.main()
