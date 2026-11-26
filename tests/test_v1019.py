import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from ping_mapping import STATIC_IP_POOL, discover_static_mapping
from excel_record import build_rows
import main


def state(i,mac_suffix):
    return {'gpon_sn':'CMTD'+mac_suffix, 'phase_state':'working'}

class DiscoveryTests(unittest.TestCase):
    def test_exact_pool(self):
        self.assertEqual(len(STATIC_IP_POOL),16)
        self.assertEqual(STATIC_IP_POOL[0],'192.168.2.121')
        self.assertEqual(STATIC_IP_POOL[-1],'192.168.2.136')

    def fake_ping(self,active):
        def ping(ip,**kwargs):
            return {'result':'PASS' if ip in active else 'FAIL','sent':1,'loss':0 if ip in active else 1}
        return ping

    def test_sparse_five(self):
        ips=['192.168.2.'+str(x) for x in (121,123,128,130,136)]
        states={i:state(i,f'{i*16:06X}') for i in range(1,6)}
        arp={ip:('3872C0'+states[n]['gpon_sn'][-6:]) for n,ip in enumerate(ips,1)}
        rows,mapping,errors=discover_static_mapping(states,5,ping_fn=self.fake_ping(ips),arp_fn=lambda ip:arp.get(ip))
        self.assertEqual(errors,[])
        self.assertEqual(len(mapping),5)
        self.assertEqual({x['ip'] for x in mapping.values()},set(ips))

    def test_one_and_sixteen(self):
        for count in (1,2,10,16):
            ips=list(STATIC_IP_POOL[:count])
            states={i:state(i,f'{i*16:06X}') for i in range(1,count+1)}
            arp={ip:('3872C0'+states[n]['gpon_sn'][-6:]) for n,ip in enumerate(ips,1)}
            rows,mapping,errors=discover_static_mapping(states,count,ping_fn=self.fake_ping(ips),arp_fn=lambda ip:arp.get(ip))
            self.assertFalse(errors,errors)
            self.assertEqual(len(mapping),count)

    def test_missing_responsive_dut_blocks(self):
        ips=[STATIC_IP_POOL[0]]
        states={1:state(1,'112233'),2:state(2,'445566')}
        rows,mapping,errors=discover_static_mapping(states,2,ping_fn=self.fake_ping(ips),arp_fn=lambda ip:'3872C0112233')
        self.assertTrue(errors)
        self.assertEqual(len(mapping),1)
        self.assertTrue(any('EXPECTED 2' in e for e in errors))

    def test_expected_count_mismatch_blocks(self):
        ips=[STATIC_IP_POOL[0]]
        states={1:state(1,'112233')}
        _,_,errors=discover_static_mapping(states,2,ping_fn=self.fake_ping(ips),arp_fn=lambda ip:'3872C0112233')
        self.assertTrue(any('OLT reports' in e for e in errors))

    def test_responding_unrelated_ip_blocks(self):
        ips=[STATIC_IP_POOL[0],STATIC_IP_POOL[7]]
        states={1:state(1,'112233')}
        _,_,errors=discover_static_mapping(states,1,ping_fn=self.fake_ping(ips),arp_fn=lambda ip:'3872C0112233' if ip==ips[0] else 'AA0011223344')
        self.assertTrue(errors)

    def test_invalid_count(self):
        for count in (0,17,True,'2'):
            with self.assertRaises(ValueError):
                discover_static_mapping({},count)

class EventsTests(unittest.TestCase):
    def unit(self,dereg,reg):
        return dict(status='PASS',gpon_sn='CMTD112233',phase_state='working',
                    last_deregist=dereg,last_regist=reg,data_flag='OK')

    def test_pon_reconnect_logged_even_when_working(self):
        a=self.unit('2026:11:26 10:47:48','2026:11:26 10:48:13')
        b=self.unit('2026:11:26 12:23:36','2026:11:26 12:24:16')
        cycles=[dict(cycle=1,time='12:00',onus={1:a},result='PASS'),
                dict(cycle=2,time='13:00',onus={1:b},result='PASS')]
        sheets=dict(build_rows(cycles))
        events=sheets['04_Event_Log'][1:]
        self.assertEqual(len([x for x in events if x[-1]=='PON RECONNECT / TIMESTAMP CHANGE']),1)
        self.assertIn('12:23:36',str(events))

    def test_unchanged_timestamps_no_duplicate_event(self):
        a=self.unit('2026:11:26 10:47:48','2026:11:26 10:48:13')
        cycles=[dict(cycle=n,time='12:00',onus={1:a},result='PASS') for n in (1,2,3)]
        self.assertEqual(len(dict(build_rows(cycles))['04_Event_Log']),1)

    def test_gui_no_manual_ip_and_one_notebook(self):
        source=Path(main.__file__).read_text()
        self.assertNotIn('self.ip_text=tk.Text',source)
        self.assertEqual(source.count('ttk.Notebook('),1)
        self.assertIn('Expected DUT Count',source)
        self.assertIn('8h PENDING',source)

if __name__=='__main__':unittest.main()

class SessionReconnectIntegration(unittest.TestCase):
    def test_two_working_cycles_register_change_is_recorded_to_json_and_excel(self):
        import logging, threading
        from zipfile import ZipFile
        from session_runner import run_session, read_journal
        state='OnuIndex Admin State OMCC State Phase State Channel Serial Number\n1:1 enable enable working XGSPON CMTDc0112255\ngpon-olt(config-pon-0/1)#\n'
        opt='ONU ID : 1\nRx optical level(ONU) : -26.78\nTx optical level : 6.96\nPower feed voltage : 3.30(V)\nLaser bias current : 41.0(mA)\nTemperature : 60.0(C)\ngpon-olt(config-pon-0/1)#\n'
        stamps=('1/12026:11:26 10:48:13'+'2026:11:26 10:47:48'+'Onu Los'+'00:20:29\n',
                '1/12026:11:26 12:24:16'+'2026:11:26 12:23:36'+'Onu Los'+'00:01:29\n')
        # Use a structured timestamp layout to match V3600GS parser fixtures.
        stamps=('1/1 2026:11:26 10:48:13 2026:11:26 10:47:48 Onu Los 00:20:29\n',
                '1/1 2026:11:26 12:24:16 2026:11:26 12:23:36 Onu Los 00:01:29\n')
        class Fake:
            def __init__(self):self.cycle=0
            def open(self):pass
            def _login_sequence(self):pass
            def close(self):pass
            def command(self,cmd,timeout):
                if cmd=='show onu state':
                    self.cycle+=1
                    return state
                if cmd=='show onu time-stamp':return stamps[min(self.cycle-1,1)]+'gpon-olt(config-pon-0/1)#\n'
                return opt
        with tempfile.TemporaryDirectory() as td:
            stop=__import__('threading').Event()
            def notify(kind,msg):
                if kind=='CYCLE' and msg.startswith('Cycle 2 '):stop.set()
            result=run_session(Fake,td,logging.getLogger('v1019-fixture'),stop,loop=True,
                               interval_min=.00001,notify=notify)
            cycles=read_journal(td)
            self.assertEqual(len(cycles),2)
            self.assertEqual([x['result'] for x in cycles],['PASS','PASS'])
            events=[json.loads(line) for line in (Path(td)/'events.jsonl').read_text().splitlines()]
            self.assertEqual(len([e for e in events if e.get('kind')=='PON_RECONNECT']),1)
            with ZipFile(Path(td)/'ONU_Master_Record.xlsx') as z:
                combined=''.join(z.read(n).decode() for n in z.namelist() if n.startswith('xl/worksheets/'))
                self.assertIn('PON RECONNECT / TIMESTAMP CHANGE',combined)
