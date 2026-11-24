import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

class Tests(unittest.TestCase):
    def test_valid_port(self):
        self.assertEqual(main.com_number('COM3'), 3)
        self.assertEqual(main.com_number('com256'), 256)
    def test_invalid_port(self):
        for x in ['COM0', 'COM257', '3', 'COM3 & exit']:
            with self.assertRaises(ValueError): main.com_number(x)
    def test_ttl_uses_standalone_connect(self):
        ttl = main.build_macro(3, Path('C:/temp/status.txt'), Path('C:/temp/serial.log'))
        self.assertIn("connect '/C=3 /BAUD=115200'", ttl)
        self.assertNotIn('/DS', ttl)
        self.assertNotIn('/M=', ttl)
        self.assertIn('testlink', ttl)
        self.assertIn('LINK_STATE=', ttl)
    def test_ttl_four_login_stages(self):
        ttl = main.build_macro(3, Path('C:/temp/status.txt'), Path('C:/temp/serial.log'))
        for term in ('PROMPT|LOGIN','qa123','admin123','enable','config terminal',
                     'interface gpon 0/1', 'READY|gpon-olt(config-pon-0/1)#'):
            self.assertIn(term, ttl)
    def test_macro_launch_arguments(self):
        args = main.launch_arguments(Path('C:/Program Files (x86)/teraterm/ttpmacro.exe'),
                                     Path('C:/Users/Public/V3600GS_Macro/123/connect.ttl'))
        self.assertEqual(len(args), 2)
        self.assertTrue(args[0].endswith('ttpmacro.exe'))
        self.assertTrue(args[1].endswith('connect.ttl'))
        self.assertFalse(any('/M=' in x for x in args))
    def test_record_location(self):
        self.assertEqual(main.RECORDS, main.BASE / 'records')
    def test_stage_record_copies(self):
        with tempfile.TemporaryDirectory() as base:
            source=Path(base)/'stage'; target=Path(base)/'records'
            source.mkdir(); target.mkdir()
            for name in ['stage.txt','status.txt','serial.log','connect.ttl']:
                (source/name).write_text(name)
            main.copy_staging_records(source,target)
            for name in ['stage.txt','status.txt','serial.log','connect.ttl']:
                self.assertEqual((target/name).read_text(),name)
    def test_staging_no_unicode_space(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(main.sys,'platform','win32'), patch.dict(main.os.environ, {'PUBLIC':temp}, clear=False):
                if str(temp).isascii() and ' ' not in temp:
                    self.assertEqual(main.macro_work_root(), Path(temp)/'V3600GS_Macro')
    def test_ttl_quoted_rejects_unsafe(self):
        for bad in ["C:/can't/test",'C:/bad\nname']:
            with self.assertRaises(ValueError): main.ttl_quoted(bad)
    def test_version_build_match(self):
        wf=(Path(__file__).resolve().parents[1]/'.github/workflows/build.yml').read_text()
        version='V3600GS_Connect_V'+main.APP_VERSION
        self.assertIn('--name '+version+' main.py',wf)
        self.assertIn('dist/'+version+'.exe',wf)
        self.assertIn('name: '+version,wf)
    def test_fresh_records_directory(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'records'; p.mkdir(parents=True,exist_ok=True)
            self.assertTrue(p.is_dir())

if __name__=='__main__': unittest.main()
