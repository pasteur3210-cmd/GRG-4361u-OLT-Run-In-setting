import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

class CTIconTests(unittest.TestCase):
    def test_ct_icon_actual_ico_white_background(self):
        im = Image.open(ROOT/'CT.ico')
        self.assertEqual(im.format, 'ICO')
        self.assertEqual(im.size, (256,256))
        self.assertGreaterEqual(min(im.getpixel((0,0))[:3]), 250)
        self.assertTrue({(16,16),(32,32),(48,48),(256,256)}.issubset(im.info['sizes']))
    def test_tk_and_pyinstaller_references(self):
        main = (ROOT/'main.py').read_text(encoding='utf-8')
        build = (ROOT/'.github/workflows/build.yml').read_text(encoding='utf-8')
        self.assertIn("icon_path=icon_base/'CT.ico'", main)
        self.assertIn('iconbitmap(default=str(icon_path))', main)
        self.assertIn('SetCurrentProcessExplicitAppUserModelID', main)
        self.assertIn('--icon CT.ico',build)
        self.assertIn('--add-data "CT.ico;."',build)
        self.assertIn('V3600GS_Connect_V1.0.23.4',build)
        self.assertNotIn('HD.ico',build)
