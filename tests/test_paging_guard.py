"""V1.0.17 release gate: full-output, multi-page, cross-command integrity."""
import logging
import tempfile
import threading
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_basic  # pyserial double on machines without a hardware backend
import main
from onu_parser import parse_onu_state, parse_optical, parse_time_stamp
from session_runner import check_cycle, cycle_result


def fake_output(n):
    header='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n'
    state=header+''.join(f'1:{i} enable enable working XGSPON CMTD{i:08x}\n' for i in range(1,n+1))
    stamp='onu id  last regist time   last deregist time   last deregist reason   alive time\n'
    stamp+=''.join(f'1/{i} 2026:11:25 12:00:00 N/A N/A 1 03:04:05\n' for i in range(1,n+1))
    optical=''.join(f'ONU ID : {i}\nRx optical level(ONU) : -26.4\nTx optical level : 6.9\nPower feed voltage : 3.30(V)\nLaser bias current : 40.6(mA)\nTemperature : 62.1(C)\n' for i in range(1,n+1))
    return {'show onu state':state,'show onu time-stamp':stamp,'show onu optical-info all':optical}

class FakeSerial:
    def __init__(self,chunks):
        self.chunks=list(chunks);self.writes=[]
    def read(self,size):return self.chunks.pop(0) if self.chunks else b''
    def write(self,b):self.writes.append(b)
    def flush(self):pass

class CompleteClient:
    def __init__(self,data):self.data=data
    def command(self,command,timeout):return self.data[command]

class PaginationGateTests(unittest.TestCase):
    def assert_serial_pages(self,pager):
        # 20 ONUs distributed across 3 pages with split reads, ANSI and CR.
        data=fake_output(20)['show onu optical-info all']
        entries=data.split('ONU ID : ')
        part1=''.join('ONU ID : '+x for x in entries[1:8])
        part2=''.join('ONU ID : '+x for x in entries[8:15])
        part3=''.join('ONU ID : '+x for x in entries[15:])
        pages=[part1+pager,part2+pager,part3+'\r\ngpon-olt(config-pon-0/1)#\r\n']
        class GatedSerial:
            def __init__(self):
                self.page_idx=0;self.writes=[]
                self.chunks=self.split(pages[0])
            def split(self,page):
                return [page[i:i+7].encode() for i in range(0,len(page),7)]
            def read(self,size):return self.chunks.pop(0) if self.chunks else b''
            def write(self,data):
                self.writes.append(data)
                if data==b' ':
                    self.page_idx+=1
                    if self.page_idx<len(pages):
                        self.chunks.extend(self.split(pages[self.page_idx]))
            def flush(self):pass
        fake=GatedSerial()
        client=main.SerialLogin('COM3',logging.getLogger('pager-test'))
        client.link=fake
        self.assertEqual(len(parse_optical(client.command('show onu optical-info all',timeout=3))),20)
        self.assertEqual(fake.writes.count(b' '),2)
    def test_twenty_onus_split_more(self):self.assert_serial_pages('--More--\r\n')
    def test_twenty_onus_ansi_more(self):self.assert_serial_pages('\x1b[33m-- More --\x1b[0m\r\n')
    def test_twenty_onus_press_space(self):self.assert_serial_pages('Press SPACE to continue\r\n')
    def test_timeout_never_returns_partial(self):
        fake=FakeSerial([b'ONU ID : 1\nRx optical level(ONU): -26\n--More--'])
        client=main.SerialLogin('COM3',logging.getLogger('pager-test'));client.link=fake
        with self.assertRaisesRegex(main.LoginError,'incomplete multipage'):
            client.command('show onu optical-info all',timeout=0.02)
        self.assertEqual(fake.writes.count(b' '),1)
    def test_raw_state_stamp_optical_for_2_10_16_20(self):
        for n in (2,10,16,20):
            with self.subTest(n=n),tempfile.TemporaryDirectory() as td:
                data=fake_output(n)
                units,error=check_cycle(CompleteClient(data),td,1,logging.getLogger('gate'))
                self.assertEqual(error,'')
                self.assertEqual(len(units),n)
                self.assertEqual(cycle_result(units,error,set(units)),'PASS')
                self.assertEqual(len(list((Path(td)/'raw_cli').glob('*.log'))),3)
    def test_state_twenty_optical_only_eight_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            data=fake_output(20)
            data['show onu optical-info all']=fake_output(8)['show onu optical-info all']
            units,error=check_cycle(CompleteClient(data),td,1,logging.getLogger('gate'))
            self.assertIn('OPTICAL missing working ONU ID 9',error)
            self.assertEqual(cycle_result(units,error,set(units)),'INCOMPLETE')
    def test_state_twenty_timestamp_only_twelve_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            data=fake_output(20)
            data['show onu time-stamp']=fake_output(12)['show onu time-stamp']
            units,error=check_cycle(CompleteClient(data),td,1,logging.getLogger('gate'))
            self.assertIn('TIMESTAMP ONU ID mismatch',error)
            self.assertEqual(cycle_result(units,error,set(units)),'INCOMPLETE')
    def test_incomplete_optical_field_is_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            data=fake_output(10)
            data['show onu optical-info all']=data['show onu optical-info all'].replace('Temperature : 62.1(C)','Temperature : N/A',1)
            units,error=check_cycle(CompleteClient(data),td,1,logging.getLogger('gate'))
            self.assertIn('OPTICAL incomplete working ONU ID 1: temperature',error)
            self.assertEqual(cycle_result(units,error,set(units)),'INCOMPLETE')
    def test_malformed_state_row_not_silently_ignored(self):
        state=fake_output(10)['show onu state'].replace('1:6 enable enable working XGSPON CMTD00000006','1:6 error')
        with self.assertRaisesRegex(ValueError,'Malformed ONU state row'):
            parse_onu_state(state)
    def test_malformed_timestamp_row_not_silently_ignored(self):
        ts=fake_output(10)['show onu time-stamp'].replace('1/6 2026:11:25 12:00:00 N/A N/A 1 03:04:05','1/6 broken')
        with self.assertRaisesRegex(ValueError,'Malformed ONU time-stamp row'):
            parse_time_stamp(ts)
    def test_duplicate_optical_page_fails(self):
        data=fake_output(10)['show onu optical-info all']
        with self.assertRaisesRegex(ValueError,'Duplicate ONU ID'):
            parse_optical(data+'ONU ID : 1\n')
    def test_ansi_optical_parser(self):
        data=fake_output(2)['show onu optical-info all'].replace('ONU ID : 1','\x1b[32mONU ID : 1\x1b[0m')
        self.assertEqual(len(parse_optical(data)),2)

if __name__=='__main__':unittest.main()

class AllThreeCommandsPaginationTests(unittest.TestCase):
    def test_all_three_commands_multiscreen_16_onus(self):
        data=fake_output(16)
        for command, parser in [('show onu state',parse_onu_state),
                                ('show onu time-stamp',parse_time_stamp),
                                ('show onu optical-info all',parse_optical)]:
            with self.subTest(command=command):
                lines=data[command].splitlines(keepends=True)
                # Split into three pages, never break a physical ONU block.
                if command=='show onu optical-info all':
                    groups=[''.join(lines[:36]),''.join(lines[36:72]),''.join(lines[72:])]
                else:
                    groups=[''.join(lines[:7]),''.join(lines[7:13]),''.join(lines[13:])]
                page_data=[groups[0]+'--More--\r\n',groups[1]+'--More--\r\n',
                           groups[2]+'\ngpon-olt(config-pon-0/1)#\n']
                class ThreePages:
                    def __init__(self):
                        self.page=0;self.writes=[];self.chunks=self.split(page_data[0])
                    def split(self,value):
                        data=value.encode();return [data[i:i+3] for i in range(0,len(data),3)]
                    def read(self,size):return self.chunks.pop(0) if self.chunks else b''
                    def write(self,b):
                        self.writes.append(b)
                        if b==b' ':
                            self.page+=1
                            self.chunks.extend(self.split(page_data[self.page]))
                    def flush(self):pass
                fake=ThreePages()
                client=main.SerialLogin('COM3',logging.getLogger('test'))
                client.link=fake
                raw=client.command(command,timeout=4)
                self.assertEqual(len(parser(raw)),16)
                self.assertEqual(fake.writes.count(b' '),2)

    def test_incomplete_state_and_timestamp_timeout(self):
        for command in ('show onu state','show onu time-stamp'):
            with self.subTest(command=command):
                fake=FakeSerial([fake_output(2)[command].encode()])
                client=main.SerialLogin('COM3',logging.getLogger('test'));client.link=fake
                with self.assertRaises(main.LoginError):client.command(command,timeout=.02)

    def test_error_on_duplicate_state_and_timestamp(self):
        data=fake_output(2)
        state=data['show onu state']+'1:2 enable enable working XGSPON CMTD00000002\n'
        with self.assertRaises(ValueError):parse_onu_state(state)
        ts=data['show onu time-stamp']+'1/2 2026:11:25 12:00:00 N/A N/A 1 03:04:05\n'
        with self.assertRaises(ValueError):parse_time_stamp(ts)
