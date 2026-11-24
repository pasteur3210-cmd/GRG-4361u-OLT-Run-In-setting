import unittest
import logging
import tempfile
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
# importing test_basic installs serial double if pyserial unavailable
import test_basic
import main
from onu_parser import parse_time_stamp,parse_optical,merge_data
from excel_record import export_cycles, build_rows

DATA=Path(__file__).resolve().parents[1]/'tests'/'fixtures'

class FakeCLISerial(test_basic.FakeSerial):
    def __init__(self, responses):
        super().__init__(responses)

class ONUDataTests(unittest.TestCase):
    def test_actual_timestamp_compacted(self):
        data=parse_time_stamp((DATA/'show onu time-stamp.log').read_text())
        self.assertEqual(data[1]['port_id'],'1/1')
        self.assertEqual(data[2]['last_regist'],'2026:11:23 16:47:48')
        self.assertEqual(data[1]['dereg_reason'],'N/A')
        self.assertEqual(data[1]['alive'],'20:52:29')
    def test_actual_optical(self):
        data=parse_optical((DATA/'teraterm-show onu optical info all.log').read_text())
        self.assertEqual(data[1]['rx'],-26.78)
        self.assertEqual(data[2]['tx'],6.95)
        self.assertEqual(data[1]['temperature'],65.172)
        self.assertEqual(data[2]['voltage'],3.28)
    def test_no_false_online(self):
        tm=parse_time_stamp((DATA/'show onu time-stamp.log').read_text())
        op=parse_optical((DATA/'teraterm-show onu optical info all.log').read_text())
        combined=merge_data(tm,op)
        self.assertEqual(combined[1]['status'],'NOT VERIFIED')
        self.assertEqual(combined[2]['data_flag'],'OK')
    def test_missing_optical_flag(self):
        self.assertEqual(merge_data({1:{'onu_id':1}}, {})[1]['data_flag'],'MISSING_OPTICAL')
    def test_corrupt_timestamp_fails(self):
        with self.assertRaises(ValueError):parse_time_stamp('invalid output')
    def test_xlsx_zip_xml(self):
        data=merge_data(parse_time_stamp((DATA/'show onu time-stamp.log').read_text()),parse_optical((DATA/'teraterm-show onu optical info all.log').read_text()))
        with tempfile.TemporaryDirectory() as td:
            p=export_cycles(Path(td)/'test.xlsx',[{'time':'2026-11-24 12:00:00','onus':data}])
            with ZipFile(p) as z:
                self.assertIsNone(z.testzip())
                ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                ET.fromstring(z.read('xl/workbook.xml'))
                self.assertIn(b'-26.78',z.read('xl/worksheets/sheet1.xml'))
                self.assertIn(b'ONU2_Temp(C)',z.read('xl/worksheets/sheet1.xml'))
                self.assertNotIn(b'ONU10_Temp(C)',z.read('xl/worksheets/sheet1.xml'))
    def test_dynamic_sixteen_onus(self):
        ons={i:{'status':'NOT VERIFIED','data_flag':'OK','rx':-25-i/100} for i in range(1,17)}
        sheets=build_rows([{'time':'2026-11-24 13:00:00','onus':ons}])
        hdr=sheets[0][1][0]; row=sheets[0][1][1]
        self.assertEqual(len(hdr),4+16*14)
        self.assertEqual(row[3],16)
        self.assertIn('ONU16_ONU Rx',hdr)
        self.assertNotIn('ONU17_ONU Rx',hdr)
        self.assertEqual(row[hdr.index('ONU16_ONU Rx')],-25.16)
    def test_dynamic_twenty_nonconsecutive_ids(self):
        ons={i:{'status':'NOT VERIFIED','data_flag':'OK','rx':-i} for i in range(1,21)}
        sheets=build_rows([{'time':'t','onus':ons}])
        self.assertEqual(len(sheets[0][1][0]),4+20*14)
        sparse=build_rows([{'time':'t','onus':{1:ons[1],3:ons[3],16:ons[16]}}])
        self.assertEqual(len(sparse[0][1][0]),4+3*14)
        self.assertIn('ONU16_ONU Rx',sparse[0][1][0])
        self.assertNotIn('ONU2_ONU Rx',sparse[0][1][0])
    def test_missing_onu_stays_at_own_column(self):
        a={1:{'data_flag':'OK','rx':-24},2:{'data_flag':'OK','rx':-25},16:{'data_flag':'OK','rx':-26}}
        b={1:{'data_flag':'OK','rx':-23},16:{'data_flag':'OK','rx':-27}}
        rows=build_rows([{'time':'t1','onus':a},{'time':'t2','onus':b}])[0][1]
        headers=rows[0]
        self.assertEqual(rows[2][headers.index('ONU2_Data Flag')],'MISSING THIS CYCLE')
        self.assertIsNone(rows[2][headers.index('ONU2_ONU Rx')])
        self.assertEqual(rows[2][headers.index('ONU16_ONU Rx')],-27)
        self.assertEqual(rows[2][2],'DATA INCOMPLETE')
    def test_sixteen_ids_parse_timestamp_and_optical(self):
        t='\n'.join(f'1/{i}2026:11:23 16:47:05N/AN/A20:52:29' for i in range(1,17))
        o='\n\n'.join(f'ONU ID : {i}\nRx optical level(ONU) : -25.00\nTx optical level : 6.97' for i in range(1,17))
        ts=parse_time_stamp(t);opt=parse_optical(o)
        self.assertEqual(len(ts),16)
        self.assertEqual(len(opt),16)
        self.assertEqual(ts[16]['port_id'],'1/16')
        self.assertEqual(merge_data(ts,opt)[16]['rx'],-25.0)
    def test_export_sixteen_valid_xml(self):
        data={i:{'status':'NOT VERIFIED','data_flag':'OK','rx':-25} for i in range(1,17)}
        with tempfile.TemporaryDirectory() as td:
            p=export_cycles(Path(td)/'16.xlsx',[{'time':'t','onus':data}])
            with ZipFile(p) as z:
                self.assertIsNone(z.testzip())
                text=z.read('xl/worksheets/sheet1.xml')
                ET.fromstring(text)
                self.assertIn(b'ONU16_ONU Rx',text)
    def test_run_check_commands(self):
        tm=(DATA/'show onu time-stamp.log').read_text()
        op=(DATA/'teraterm-show onu optical info all.log').read_text()
        fake=FakeCLISerial([b'Login:',b'Password:',b'gpon-olt>',b'Password:',b'gpon-olt#',b'gpon-olt(config)#',b'gpon-olt(config-pon-0/1)#',tm.encode(),op.encode()])
        with tempfile.TemporaryDirectory() as td:
            client=main.SerialLogin('COM3',logging.getLogger('test-onu'),serial_factory=lambda **kw:fake)
            result, data=client.run(check=True,output_folder=td)
            self.assertEqual(len(data),2)
            self.assertEqual(result,main.TARGET_PROMPT)
            self.assertIn(b'show onu time-stamp\r',fake.writes)
            self.assertIn(b'show onu optical-info all\r',fake.writes)
            self.assertTrue((Path(td)/'onu_time_stamp.log').exists())
            self.assertTrue(fake.closed)

if __name__=='__main__':unittest.main()
