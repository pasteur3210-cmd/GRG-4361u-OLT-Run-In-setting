import unittest
from pathlib import Path
import main

class WorkareaIconTests(unittest.TestCase):
    def test_icon_shipped(self):
        self.assertGreater((Path(main.__file__).parent/'CT.ico').stat().st_size,1024)
    def test_workarea_scroll_and_icon_workflow(self):
        source=Path(main.__file__).read_text(encoding='utf-8')
        workflow=(Path(main.__file__).parent/'.github/workflows/build.yml').read_text(encoding='utf-8')
        for mark in ('olt_canvas','Scrollbar(','_scroll_olt_if_hovered','winfo_screenheight','apply_window_icon','iconbitmap','SetCurrentProcessExplicitAppUserModelID'):
            self.assertIn(mark,source)
        self.assertIn('--icon CT.ico',workflow)
        self.assertIn('--add-data "CT.ico;."',workflow)

if __name__=='__main__':unittest.main()
