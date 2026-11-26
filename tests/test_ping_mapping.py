import json
import tempfile
import logging
import threading
import unittest
from pathlib import Path
from zipfile import ZipFile
from onu_parser import parse_onu_state
from ping_mapping import (normalize_ips,suffix,find_mac,wan_to_lan_mac,match_mac_to_onu,run_ping,ping_all,verify_mapping)
from excel_record import FIELDS,build_rows
from session_runner import run_session, read_journal

STATE='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\n1:2 enable enable working XGSPON CMTD99abe129\n'
S=parse_onu_state(STATE)
IP1='192.168.2.101';IP2='192.168.2.102'
ARP='Interface: 192.168.2.10 --- 0x10\n  Internet Address      Physical Address      Type\n  192.168.2.1           aa-bb-cc-ff-ee-dd     dynamic\n  192.168.2.101         aa-bb-cc-11-22-56     dynamic\n  192.168.2.102         aa-bb-cc-ab-e1-2a     dynamic\n'

def good_ping(ip,*,count,wait_ms=1000):
    return dict(result='PASS',loss=0,received=count,sent=count,error='',raw='TTL=64\n'*count)

class PingTests(unittest.TestCase):
    def test_ip_validation_and_duplicate(self):
        self.assertEqual(normalize_ips(IP1+'\n'+IP2),[IP1,IP2])
        for x in ['192.168.2.101;192.168.2.101','bad-ip','224.0.0.1','127.0.0.1']:
            with self.subTest(value=x),self.assertRaises(ValueError):normalize_ips(x)
    def test_mac_last_six(self):
        self.assertEqual(suffix('CMTDc0112255'),'112255')
        self.assertEqual(suffix('AA-BB-CC-11-22-55'),'112255')
        self.assertEqual(suffix('CMTD99abe129'),'ABE129')
    def test_wan_to_lan_actual_dut_samples(self):
        self.assertEqual(wan_to_lan_mac('38-72-c0-11-22-56'), '3872C0112255')
        self.assertEqual(wan_to_lan_mac('1c:64:99:ab:e1:2a'), '1C6499ABE129')
        self.assertEqual(suffix(wan_to_lan_mac('3872C0112256')),suffix('CMTDc0112255'))
        self.assertEqual(suffix(wan_to_lan_mac('1C6499ABE12A')),suffix('CMTD99abe129'))

    def test_full_48_bit_borrow(self):
        self.assertEqual(wan_to_lan_mac('3872C0112300'),'3872C01122FF')
        self.assertEqual(wan_to_lan_mac('000000010000'),'00000000FFFF')

    def test_invalid_wan_mac_never_matches(self):
        for x in ('', '0'*12, 'F'*12, '11:22:33', 'Z'*12):
            with self.subTest(value=x), self.assertRaises(ValueError):wan_to_lan_mac(x)

    def test_actual_two_dut_mapping(self):
        ips=['192.168.2.121','192.168.2.122']
        macs={'192.168.2.121':'3872C0112256','192.168.2.122':'1C6499ABE12A'}
        rows,matched,errors=verify_mapping(ips,S,ping_fn=good_ping,arp_fn=macs.__getitem__)
        self.assertEqual(errors,[])
        self.assertEqual([r['status'] for r in rows],['MATCH','MATCH'])
        self.assertEqual(matched[1]['lan_mac'],'3872C0112255')
        self.assertEqual(matched[1]['match_type'],'OFFSET_MINUS_1')
        self.assertEqual(matched[2]['lan_mac'],'1C6499ABE129')
        self.assertEqual(matched[1]['ip'],ips[0])
        self.assertEqual(matched[2]['ip'],ips[1])

    def test_direct_mac_matches_without_decrement(self):
        rows,matched,errors=verify_mapping([IP1],{1:S[1]},ping_fn=good_ping,
                        arp_fn=lambda ip:'3872C0112255')
        self.assertEqual(errors,[])
        self.assertEqual(rows[0]['status'],'MATCH')
        self.assertEqual(matched[1]['lan_mac'],'3872C0112255')
        self.assertEqual(matched[1]['match_type'],'DIRECT')


    def test_16_dynamic_mac_pairs(self):
        states={i:dict(gpon_sn='CMTD'+format(0x10000000+i,'08X')) for i in range(1,17)}
        ips=[f'192.168.2.{100+i}' for i in range(1,17)]
        arp={ip:f'{0x3872C0000000 + i*4 + 1:012X}' for i,ip in enumerate(ips,1)}
        # Adjust SN trailing six bytes to derived LAN (full 48-bit counter).
        for i in range(1,17):
            states[i]['gpon_sn']='CMTD'+format(0xC0000000+i*4,'08X')
        rows,matched,errors=verify_mapping(ips,states,ping_fn=good_ping,arp_fn=arp.__getitem__)
        self.assertEqual(errors,[])
        self.assertEqual(len(matched),16)
        self.assertTrue(all(r['status']=='MATCH' for r in rows))

    def test_arp_match_only_exact_ip(self):
        self.assertEqual(find_mac(ARP,IP1),'AABBCC112256')
        self.assertEqual(find_mac(ARP,IP2),'AABBCCABE12A')
        self.assertIsNone(find_mac(ARP,'192.168.2.103'))
    def test_good_and_fail_and_warning(self):
        class Result:
            returncode=0
            stderr=''
            stdout=''
        for received,expected in [(4,'PASS'),(3,'WARNING'),(2,'FAIL'),(1,'FAIL'),(0,'FAIL')]:
            with self.subTest(received=received):
                r=Result();r.stdout='Reply from 192.168.2.101: bytes=32 time<1ms TTL=64\n'*received
                self.assertEqual(run_ping(IP1,runner=lambda *a,**k:r)['result'],expected)
    def test_ping_process_error(self):
        class Result:
            returncode=2
            stderr='broken'
            stdout=''
        self.assertEqual(run_ping(IP1,runner=lambda *a,**k:Result())['result'],'ERROR')
    def test_parallel_many_ips(self):
        ips=[f'192.168.2.{i}' for i in range(101,117)]
        self.assertEqual(set(ping_all(ips,ping_fn=good_ping)),set(ips))
    def test_mapping_exact(self):
        rows,matched,errors=verify_mapping([IP1],{1:S[1]},ping_fn=good_ping,
                        arp_fn=lambda ip:'AABBCC112256')
        self.assertEqual(errors,[])
        self.assertEqual(matched[1]['gpon_sn'],'CMTDc0112255')
        self.assertEqual(rows[0]['status'],'MATCH')
    def test_mapping_missing_mac(self):
        rows,matched,errors=verify_mapping([IP1],{1:S[1]},ping_fn=good_ping,arp_fn=lambda ip:None)
        self.assertTrue(errors);self.assertFalse(matched)
        self.assertEqual(rows[0]['status'],'MAC NOT FOUND')
    def test_mapping_mismatch_no_auto_index(self):
        rows,matched,errors=verify_mapping([IP1],{1:S[1]},ping_fn=good_ping,
                        arp_fn=lambda ip:'AABBCCABCDEF')
        self.assertEqual(rows[0]['status'],'MISMATCH')
        self.assertTrue(errors);self.assertFalse(matched)
    def test_mapping_duplicate_suffix(self):
        states={1:S[1],2:dict(S[2],gpon_sn='CMTDDE112255')}
        rows,matched,errors=verify_mapping([IP1],states,ping_fn=good_ping,
                        arp_fn=lambda ip:'AABBCC112256')
        self.assertEqual(rows[0]['status'],'AMBIGUOUS')
        self.assertTrue(errors)
    def test_mapping_all_ip_and_onu_required(self):
        rows,matched,errors=verify_mapping([IP1],S,ping_fn=good_ping,
                        arp_fn=lambda ip:'AABBCC112256')
        self.assertTrue(errors)
    def test_mapping_ping_unreachable(self):
        def broken(ip,*,count,wait_ms=1000):return dict(result='FAIL',loss=1,received=0,sent=1,error='',raw='')
        rows,matched,errors=verify_mapping([IP1],{1:S[1]},ping_fn=broken,
                        arp_fn=lambda ip:'AABBCC112256')
        self.assertEqual(rows[0]['status'],'PING UNREACHABLE')
        self.assertFalse(matched);self.assertTrue(errors)
    def test_summary_columns_only_two_new_ping(self):
        labels=[name for _,name in FIELDS]
        for deleted in ['Admin State','OMCC State','Data Flag','Alarm','Response']:
            self.assertNotIn(deleted,labels)
        self.assertIn('IP PING Result',labels)
        self.assertIn('PING Loss',labels)
        cycle={'cycle':1,'time':'t','onus':S,'result':'PASS',
               'ping':{'1':{'result':'PASS','loss':0,'sent':4},'2':{'result':'TIMEOUT','loss':1,'sent':4}}}
        rows=build_rows([cycle],mapping={1:{'ip':IP1,'mac':'AABBCC112256','gpon_sn':S[1]['gpon_sn']},
                                             2:{'ip':IP2,'mac':'AABBCCABE12A','gpon_sn':S[2]['gpon_sn']}})
        header,data=rows[0][1]
        self.assertEqual(data[header.index('ONU2_PING Loss')],'1/4 (25.000%)')
        self.assertEqual(data[header.index('ONU1_IP PING Result')],'PASS')
        self.assertEqual(rows[2][0],'03_IP_Mapping')
    def test_cycle_ping_fail_overall_fail(self):
        from session_runner import cycle_result
        units={1:dict(S[1],data_flag='OK')}
        mapping={1:{'gpon_sn':S[1]['gpon_sn'],'ip':IP1}}
        self.assertEqual(cycle_result(units,'',{1},{'1':{'result':'TIMEOUT'}},mapping),'FAIL')
        self.assertEqual(cycle_result(units,'',{1},{'1':{'result':'ONLINE'}},mapping),'PASS')
        self.assertEqual(cycle_result(units,'',{1},{'1':{'result':'ERROR'}},mapping),'INCOMPLETE')
    def test_run_session_ping_journal_and_workbook(self):
        class Client:
            def open(self):pass
            def _login_sequence(self):pass
            def command(self,cmd,timeout):
                if cmd=='show onu state':return STATE+'\ngpon-olt(config-pon-0/1)#\n'
                if cmd=='show onu time-stamp':return '1/12026:11:23 16:47:05N/AN/A20:52:29\n'
                if cmd=='show onu optical-info all':return 'ONU ID : 1\nRx optical level(ONU) : -26.78\n'
            def close(self):pass
        mapping={1:{'ip':IP1,'mac':'AABBCC112256','gpon_sn':S[1]['gpon_sn']}}
        with tempfile.TemporaryDirectory() as td:
            result=run_session(Client,td,logging.getLogger('new'),threading.Event(),
                               mapping=mapping,ping_fn=lambda ip: (True,1.0,''))
            self.assertEqual(result['cycles'],1)
            self.assertTrue(Path(td,'mapping.json').exists())
            self.assertTrue(Path(td,'continuous_ping.csv').exists())
            self.assertEqual(read_journal(td)[0]['ping']['1']['result'],'ONLINE')
            with ZipFile(Path(td,'ONU_Master_Record.xlsx')) as z:
                self.assertIsNone(z.testzip())
                self.assertIn('03_IP_Mapping',z.read('xl/workbook.xml').decode())

if __name__=='__main__':unittest.main()

class AdditionalRegression(unittest.TestCase):
    def test_identity_drift_cannot_pass(self):
        from session_runner import cycle_result
        one={1:dict(S[1],data_flag='OK')}
        mapping={1:{'gpon_sn':'CMTDFFFFFF55','ip':IP1}}
        self.assertEqual(cycle_result(one,'',{1},{'1':{'result':'PASS'}},mapping),'INCOMPLETE')
        two={1:dict(S[1],data_flag='OK'),2:dict(S[2],data_flag='OK')}
        mapping={1:{'gpon_sn':S[1]['gpon_sn'],'ip':IP1}}
        self.assertEqual(cycle_result(two,'',{1,2},{'1':{'result':'PASS'}},mapping),'INCOMPLETE')
    def test_ping_status_event_in_excel(self):
        d={1:{'gpon_sn':S[1]['gpon_sn'],'phase_state':'working','status':'PASS'}}
        cycles=[{'time':'t1','onus':d,'ping':{'1':{'result':'FAIL','loss':2}}},
                {'time':'t2','onus':d,'ping':{'1':{'result':'PASS','loss':0}}}]
        mapping={1:{'ip':IP1,'mac':'AABBCC112256','gpon_sn':S[1]['gpon_sn']}}
        event_sheet=build_rows(cycles,mapping=mapping)[3][1]
        self.assertTrue(any('PING RECOVERY' in row for row in event_sheet))


class DualMacRuleRegression(unittest.TestCase):
    def test_two_actual_arp_formats_both_accepted(self):
        cases=[('3872C0112255','DIRECT','3872C0112255',1),
               ('3872C0112256','OFFSET_MINUS_1','3872C0112255',1),
               ('1C6499ABE129','DIRECT','1C6499ABE129',2),
               ('1C6499ABE12A','OFFSET_MINUS_1','1C6499ABE129',2)]
        for mac,kind,lan,onu in cases:
            with self.subTest(mac=mac):
                _,matched,errors=verify_mapping([IP1],{onu:S[onu]},ping_fn=good_ping,arp_fn=lambda ip:mac)
                self.assertEqual(errors,[])
                self.assertEqual(matched[onu]['match_type'],kind)
                self.assertEqual(matched[onu]['lan_mac'],lan)

    def test_invalid_direct_and_offset_mismatch(self):
        _,matched,errors=verify_mapping([IP1],{1:S[1]},ping_fn=good_ping,arp_fn=lambda ip:'3872C0112257')
        self.assertFalse(matched)
        self.assertTrue(errors)

    def test_direct_and_offset_match_different_onus_is_ambiguous(self):
        states={1:dict(gpon_sn='CMTD00112255'),2:dict(gpon_sn='CMTD00112256')}
        rows,matched,errors=verify_mapping([IP1],states,ping_fn=good_ping,arp_fn=lambda ip:'3872C0112256')
        self.assertEqual(rows[0]['status'],'AMBIGUOUS')
        self.assertFalse(matched)
        self.assertTrue(errors)

    def test_borrow_offset(self):
        states={1:dict(gpon_sn='CMTD001122FF')}
        rows,matched,errors=verify_mapping([IP1],states,ping_fn=good_ping,arp_fn=lambda ip:'3872C0112300')
        self.assertEqual(errors,[])
        self.assertEqual(matched[1]['lan_mac'],'3872C01122FF')

    def test_duplicate_different_arp_mac_same_onu_blocked(self):
        ips=[IP1,IP2]
        macs={IP1:'3872C0112255',IP2:'3872C0112256'}
        rows,matched,errors=verify_mapping(ips,{1:S[1]},ping_fn=good_ping,arp_fn=macs.__getitem__)
        self.assertEqual(len(matched),1)
        self.assertEqual(rows[1]['status'],'DUPLICATE ONU')
        self.assertTrue(errors)

    def test_direct_16_units(self):
        states={i:{'gpon_sn':f'CMTD{0xC0000000+i*4:08X}'} for i in range(1,17)}
        ips=[f'192.168.2.{100+i}' for i in range(1,17)]
        macs={ip:f'{0x3872C0000000+i*4:012X}' for i,ip in enumerate(ips,1)}
        rows,matched,errors=verify_mapping(ips,states,ping_fn=good_ping,arp_fn=macs.__getitem__)
        self.assertFalse(errors)
        self.assertEqual(len(matched),16)
        self.assertTrue(all(r['match_type']=='DIRECT' for r in rows))

    def test_mapping_excel_has_method_column(self):
        from excel_record import build_rows
        mapping={1:{'gpon_sn':S[1]['gpon_sn'],'ip':IP1,'mac':'3872C0112255','lan_mac':'3872C0112255','match_type':'DIRECT'}}
        sheet=dict(build_rows([],mapping=mapping))['03_IP_Mapping']
        self.assertIn('Match Type',sheet[0])
        self.assertEqual(sheet[1][sheet[0].index('Match Type')],'DIRECT')

    def test_arp_zero_not_accepted_even_if_suffix_matches(self):
        states={1:{'gpon_sn':'CMTD00000000'}}
        rows,matched,errors=verify_mapping([IP1],states,ping_fn=good_ping,arp_fn=lambda ip:'000000000000')
        self.assertFalse(matched)
        self.assertEqual(rows[0]['status'],'INVALID ARP MAC')
