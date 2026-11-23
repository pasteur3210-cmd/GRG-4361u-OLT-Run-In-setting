import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import com_number, build_macro, ttl_quoted

class Tests(unittest.TestCase):
    def test_valid_port(self):
        self.assertEqual(com_number('COM3'), 3)
        self.assertEqual(com_number('com256'), 256)
    def test_invalid_port(self):
        for s in ['COM0', 'COM257', '3', 'COM3 & exit']:
            with self.assertRaises(ValueError):
                com_number(s)
    def test_macro(self):
        ttl = build_macro(3, Path('C:/temp/status.txt'), Path('C:/temp/raw.log'))
        for s in ['/C=3', '/BAUD=115200', 'qa123', 'enable', 'config terminal', 'interface gpon 0/1', 'gpon-olt(config-pon-0/1)#', 'FAIL|LOGIN']:
            self.assertIn(s, ttl)
        self.assertNotIn('/CDATABIT=', ttl)  # legacy compatible launch arguments
        self.assertNotIn('messagebox', ttl)  # avoid modal block
    def test_ttl_escape(self):
        for bad in ["C:/can't/test", 'C:/bad\nname']:
            with self.assertRaises(ValueError):
                ttl_quoted(bad)

if __name__ == '__main__':
    unittest.main()
