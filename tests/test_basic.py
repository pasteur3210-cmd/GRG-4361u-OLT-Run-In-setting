import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import com_number, build_macro, ttl_quoted, RECORDS

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
        for required in ['testlink', 'CONNECTED|SERIAL', 'PROMPT|LOGIN', 'LOGIN_PROMPT_TIMEOUT',
                         'qa123', 'enable', 'config terminal', 'interface gpon 0/1',
                         'gpon-olt(config-pon-0/1)#']:
            self.assertIn(required, ttl)
        self.assertNotIn("connect '/C=", ttl)

    def test_launch_arguments(self):
        from main import launch_arguments
        args = launch_arguments(Path('C:/Program Files (x86)/teraterm/ttermpro.exe'), 3,
                                Path('C:/My Tool/records/run/connect.ttl'))
        self.assertEqual(args[1], '/C=3')
        self.assertEqual(args[2], '/BAUD=115200')
        self.assertEqual(args[3], '/M=C:/My Tool/records/run/connect.ttl')

    def test_records_are_beside_executable(self):
        import main
        self.assertEqual(main.RECORDS, main.BASE / 'records')

    def test_release_version_matches_build_workflow(self):
        import main
        workflow = (Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'build.yml').read_text(encoding='utf-8')
        expected = f'V3600GS_Connect_V{main.APP_VERSION}'
        self.assertIn(f'--name {expected} main.py', workflow)
        self.assertIn(f'dist/{expected}.exe', workflow)
        self.assertIn(f'name: {expected}', workflow)
        self.assertNotIn('V3600GS_Connect_V1.0.4', workflow)

    def test_records_directory_creation(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            nested = Path(temp) / 'V3600GS_Connect' / 'records'
            nested.mkdir(parents=True, exist_ok=True)
            self.assertTrue(nested.is_dir())

    def test_ttl_escape(self):
        for bad in ["C:/can't/test", 'C:/bad\nname']:
            with self.assertRaises(ValueError):
                ttl_quoted(bad)

if __name__ == '__main__':
    unittest.main()


def test_macro_records_numeric_link_state(tmp_path):
    import main
    ttl = main.build_macro(3, tmp_path / "status.txt", tmp_path / "serial.log", tmp_path / "stage.txt")
    assert "link_state = result" in ttl
    assert "FAIL|TERATERM_MACRO_LINK|LINK_STATE=" in ttl
    assert "testlink" in ttl
    assert "LOGIN_PROMPT_TIMEOUT" in ttl
    assert "sendln" in ttl
