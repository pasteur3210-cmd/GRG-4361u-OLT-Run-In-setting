"""End-to-end simulated ONU cycle + real ContinuousPing worker/CSV writer.
No Serial hardware or network ICMP required.
"""
import csv
import json
import logging
from pathlib import Path
import tempfile
import threading
import unittest
from zipfile import ZipFile
from session_runner import run_session,read_journal

STATE='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\n'

class FakeOLT:
    def open(self):pass
    def _login_sequence(self):pass
    def command(self,cmd,timeout=45):
        if cmd=='show onu state':return STATE+'\ngpon-olt(config-pon-0/1)#\n'
        if cmd=='show onu time-stamp':return '1/12026:11:23 16:47:05N/AN/A1 00:20:29\ngpon-olt(config-pon-0/1)#\n'
        return 'ONU ID : 1\nRx optical level(ONU) : -26.78\nTx optical level : 6.96\nPower feed voltage : 3.30(V)\nLaser bias current : 41.0(mA)\nTemperature : 60.0(C)\ngpon-olt(config-pon-0/1)#\n'
    def close(self):pass

class MonitorIntegration(unittest.TestCase):
    def test_three_cycles_one_excel_no_ping_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            results=iter([False]*5+[True]*1000)
            def ping(ip):
                try:ok=next(results)
                except StopIteration:ok=True
                return ok,(1.0 if ok else None),''
            mapping={1:{'ip':'192.168.2.121','mac':'3872C0112255','lan_mac':'3872C0112255',
                        'gpon_sn':'CMTDc0112255','match_type':'DIRECT'}}
            # Loops are accelerated to validate independent Ping worker/Excel writer.
            r=run_session(FakeOLT,td,logging.getLogger('integration'),threading.Event(),loop=True,
                          interval_min=.002,duration_hr=.00007,mapping=mapping,ping_fn=ping,ping_interval=.007)
            cycles=read_journal(td)
            self.assertGreaterEqual(len(cycles),2)
            self.assertEqual(r['cycles'],len(cycles))
            self.assertEqual([c['cycle'] for c in cycles],list(range(1,len(cycles)+1)))
            self.assertTrue(all(c['result'] in ('PASS','FAIL') for c in cycles))
            with open(Path(td,'continuous_ping.csv'),encoding='utf-8-sig',newline='') as f:
                lines=list(csv.DictReader(f))
            self.assertGreaterEqual(len(lines),6)
            self.assertEqual(max(int(x['Max Consecutive Loss']) for x in lines),5)
            self.assertEqual(int(lines[-1]['Max Consecutive Loss']),5)
            with ZipFile(Path(td,'ONU_Master_Record.xlsx')) as z:
                self.assertIsNone(z.testzip())
                import re
                data=z.read('xl/worksheets/sheet1.xml').decode()
                self.assertEqual(len(re.findall(r'<row r=',data)),len(cycles)+1)
            self.assertTrue(Path(td,'continuous_ping_summary.csv').is_file())
            self.assertTrue(Path(td,'continuous_ping_events.csv').is_file())
