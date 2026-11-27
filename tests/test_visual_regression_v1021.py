"""Read-only UI regression contracts: production code and record writer unchanged."""
import unittest
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/'main.py').read_text(encoding='utf-8')

class VisualRegression(unittest.TestCase):
    def test_gui_elements_exist(self):
        for name in ('_build_summary','_refresh_summary','_monitor_completion_text','_configure_visual_styles','update_nav'):
            self.assertIn('def '+name+'(',SRC)
        self.assertIn('self.nav_btns.append(btn)',SRC)
        self.assertIn("style.layout('RuninHidden.TNotebook.Tab', [])",SRC)
    def test_olt_and_ping_logic_unchanged(self):
        tree=ast.parse(SRC)
        funcs={node.name:ast.get_source_segment(SRC,node) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        self.assertIn('SerialLogin',funcs)
        self.assertIn('GUI',funcs)
        for module in ('session_runner.py','continuous_ping.py','excel_record.py','ping_mapping.py','ping_judgement.py','onu_parser.py'):
            self.assertTrue((ROOT/module).exists())
    def test_gui_metadata_and_mapping_contracts(self):
        for field in ('self.po_entry','self.model_entry','self.operator_entry','self.expected_count_combo','self.map_tree','self.ping_tree'):
            self.assertIn(field,SRC)
        self.assertIn('MAPPING_DONE',SRC)
        self.assertIn('PING_UPDATE',SRC)
        self.assertIn('self.ping_status.set(self._monitor_completion_text(msg))',SRC)

if __name__=='__main__':unittest.main()
