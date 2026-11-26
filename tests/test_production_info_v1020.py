"""V1.0.20 metadata persistence, report consistency, and GUI navigation contract."""
import csv
import json
import logging
from pathlib import Path
import tempfile
import threading
import unittest
from zipfile import ZipFile
from production_info import validate_production_info
from excel_record import build_rows
from session_runner import rebuild_excel, run_session, read_journal
from test_continuous_integration import FakeOLT

MAPPING={1:{'ip':'192.168.2.121','mac':'3872C0112255','lan_mac':'3872C0112255',
            'gpon_sn':'CMTDc0112255','match_type':'DIRECT'}}

class ProductionInfoTests(unittest.TestCase):
    def test_defaults_and_optional_blanks(self):
        self.assertEqual(validate_production_info('', 'GRG-4361', ''),
                         {'PO':'','Model':'GRG-4361','Operator':''})

    def test_other_model_and_trim(self):
        self.assertEqual(validate_production_info(' PO-123 ',' GRG-4372u ',' EMP123 '),
                         {'PO':'PO-123','Model':'GRG-4372u','Operator':'EMP123'})

    def test_reject_blank_model_and_controls(self):
        with self.assertRaises(ValueError):validate_production_info('','  ','')
        with self.assertRaises(ValueError):validate_production_info('PO\nInjected','GRG-4361','')
        with self.assertRaises(ValueError):validate_production_info('','GRG-4361','x'*101)

    def test_summary_columns_and_metadata(self):
        info={'PO':'PO-26-123','Model':'GRG-4361','Operator':'QA-07'}
        cycle={'cycle':1,'time':'2026-11-26 17:00:00','onus':{},'result':'ERROR','production_info':info}
        sheets=dict(build_rows([cycle],mapping=MAPPING,production_info=info))
        hdr,data=sheets['01_Loop_Summary']
        self.assertEqual(hdr[-3:],['PO','Model Name','Operator'])
        self.assertEqual(data[-3:],['PO-26-123','GRG-4361','QA-07'])
        self.assertIn(['PO','PO-26-123'],sheets['06_Run_Metadata'])
        self.assertIn(['Model Name','GRG-4361'],sheets['06_Run_Metadata'])
        self.assertIn(['Operator','QA-07'],sheets['06_Run_Metadata'])

    def test_simulated_session_rebuild_and_ping_csv(self):
        info={'PO':'PO-88601','Model':'GRG-4361','Operator':'OP-123'}
        with tempfile.TemporaryDirectory() as td:
            result=run_session(FakeOLT,td,logging.getLogger('production-v1020'),threading.Event(),
                               loop=True,interval_min=.0007,duration_hr=.00003,
                               mapping=MAPPING,ping_fn=lambda ip:(True,1.0,''),ping_interval=.008,
                               production_info=info)
            self.assertEqual(result['production_info'],info)
            self.assertEqual(json.loads((Path(td)/'production_info.json').read_text()),info)
            cycles=read_journal(td)
            self.assertTrue(cycles)
            self.assertEqual(cycles[0]['production_info'],info)
            with (Path(td)/'continuous_ping_summary.csv').open(encoding='utf-8-sig',newline='') as fp:
                ping=list(csv.DictReader(fp))[0]
            self.assertEqual((ping['PO'],ping['Model Name'],ping['Operator']),
                             ('PO-88601','GRG-4361','OP-123'))
            rebuild_excel(td)
            with ZipFile(Path(td)/'ONU_Master_Record.xlsx') as z:
                self.assertIsNone(z.testzip())
                summary=z.read('xl/worksheets/sheet1.xml').decode()
                metadata=z.read('xl/worksheets/sheet6.xml').decode()
                for value in info.values():
                    self.assertIn(value,summary)
                    self.assertIn(value,metadata)

    def test_navigation_uses_single_custom_tab_set(self):
        source=(Path(__file__).parent.parent/'main.py').read_text(encoding='utf-8')
        self.assertIn("style.layout('RuninHidden.TNotebook.Tab', [])",source)
        self.assertIn("bg='#0757a6'",source)
        self.assertIn("fg='#ffffff'",source)
        self.assertEqual(source.count('self.nav_btns.append(btn)'),1)

if __name__=='__main__':unittest.main()
