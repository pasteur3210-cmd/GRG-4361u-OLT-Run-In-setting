"""Regression gates for the mapping-table presentation-only update."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'main.py').read_text(encoding='utf-8')

class MappingScrollLayoutTests(unittest.TestCase):
    def test_visible_vertical_and_horizontal_bars(self):
        for token in ("self.mapping_vscroll=ttk.Scrollbar", "self.mapping_hscroll=ttk.Scrollbar",
                      "orient='vertical',command=self.map_tree.yview", "orient='horizontal',command=self.map_tree.xview",
                      'yscrollcommand=self.mapping_vscroll.set', 'xscrollcommand=self.mapping_hscroll.set'):
            self.assertIn(token,SOURCE)
    def test_mapping_height_is_bounded_and_better_than_four_rows(self):
        self.assertIn('height=7,style=\'Modern.Treeview\'',SOURCE)
        self.assertIn("self.map_tree.grid(row=0,column=0,sticky='nsew')",SOURCE)
        self.assertIn("self.mapping_vscroll.grid(row=0,column=1,sticky='ns')",SOURCE)
    def test_summary_shows_all_three_counts(self):
        for token in ('self.mapping_counts_var', 'Expected:', 'Discovered:', 'MATCH:',
                      "matched=sum(1 for row in msg['rows'] if row['status']=='MATCH')"):
            self.assertIn(token,SOURCE)
    def test_scroll_does_not_steal_mapping_wheel_events(self):
        self.assertIn('if widget is self.map_tree:',SOURCE)
        self.assertIn('if widget is self.olt_canvas:',SOURCE)
        self.assertLess(SOURCE.index('if widget is self.map_tree:'),SOURCE.index('if widget is self.olt_canvas:'))
    def test_runtime_modules_remain_separate(self):
        ast.parse(SOURCE)
        for filename in ('session_runner.py','onu_parser.py','continuous_ping.py','excel_record.py','ping_mapping.py','ping_judgement.py','production_info.py'):
            self.assertTrue((ROOT/filename).exists())

if __name__=='__main__':unittest.main()
