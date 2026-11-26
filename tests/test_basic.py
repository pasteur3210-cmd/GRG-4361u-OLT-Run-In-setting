import unittest
import tempfile
import logging
from pathlib import Path
from unittest.mock import patch
# Local regression can run against a minimal serial test double when pyserial is absent.
# GitHub Actions installs the real pyserial dependency before these tests.
import sys
import types
try:
    import serial
except ModuleNotFoundError:
    serial = types.ModuleType('serial')
    serial.EIGHTBITS=8
    serial.PARITY_NONE='N'
    serial.STOPBITS_ONE=1
    serial.Serial=lambda **kwargs: None
    serial_tools=types.ModuleType('serial.tools')
    serial_list_ports=types.ModuleType('serial.tools.list_ports')
    serial_list_ports.comports=lambda: []
    serial_tools.list_ports=serial_list_ports
    serial.tools=serial_tools
    sys.modules['serial']=serial
    sys.modules['serial.tools']=serial_tools
    sys.modules['serial.tools.list_ports']=serial_list_ports
import main

class FakeSerial:
    def __init__(self, responses, **kwargs):
        self.args=kwargs
        self.responses=list(responses)
        self.writes=[]
        self.closed=False
    def read(self,n):
        return self.responses.pop(0) if self.responses else b''
    def write(self,data):
        self.writes.append(data)
    def flush(self):pass
    def close(self):self.closed=True

class Tests(unittest.TestCase):
    def test_version(self):self.assertEqual(main.VERSION,'1.0.17')
    def test_baud(self):self.assertEqual(main.BAUD,115200)
    def test_port(self):
        self.assertTrue(main.valid_port('COM3'))
        self.assertFalse(main.valid_port('COM0'))
        self.assertFalse(main.valid_port('COMX'))
    def test_selection(self):
        self.assertEqual(main.select_default([('COM2','Other',''),('COM8','USB-Enhanced-SERIAL','')]),'COM8')
        self.assertEqual(main.select_default([('COM2','USB-Enhanced-SERIAL',''),('COM8','USB-Enhanced-SERIAL','')]),'')
    def test_records_beside_exe(self):self.assertEqual(main.RECORD_ROOT.parent,main.BASE)
    def test_safe_ascii(self):self.assertIn('Hi',main.safe_ascii(b'Hi\xff'))
    def test_login_sequence(self):
        fake=FakeSerial([b'Login:',b'Password:',b'gpon-olt>',b'Password:',b'gpon-olt#',b'gpon-olt(config)#',b'gpon-olt(config-pon-0/1)#'])
        logger=logging.getLogger('unit-test')
        client=main.SerialLogin('COM3',logger,serial_factory=lambda **kwargs:fake)
        self.assertEqual(client.run(),main.TARGET_PROMPT)
        self.assertEqual(fake.writes,[b'\r',b'qa123\r',b'admin123\r',b'enable\r',b'admin123\r',b'config terminal\r',b'interface gpon 0/1\r'])
        self.assertEqual(fake.closed,True)
        self.assertEqual(fake.args['baudrate'] if fake.args else main.BAUD,main.BAUD)
    def test_already_at_user_prompt(self):
        fake=FakeSerial([b'gpon-olt>',b'Password:',b'gpon-olt#',b'gpon-olt(config)#',b'gpon-olt(config-pon-0/1)#'])
        client=main.SerialLogin('COM3',logging.getLogger('unit-test'),serial_factory=lambda **kwargs:fake)
        self.assertEqual(client.run(),main.TARGET_PROMPT)
        self.assertNotIn(b'qa123\r',fake.writes)
    def test_split_login_prompt(self):
        fake=FakeSerial([b'Log',b'in:',b'Pass',b'word:',b'gpon-',b'olt>',b'Password:',b'gpon-olt#',b'gpon-olt(config)#',b'gpon-olt(config-pon-0/1)#'])
        client=main.SerialLogin('COM3',logging.getLogger('unit-test'),serial_factory=lambda **kwargs:fake)
        self.assertEqual(client.run(),main.TARGET_PROMPT)

    def test_timeout(self):
        fake=FakeSerial([])
        client=main.SerialLogin('COM3',logging.getLogger('unit-test'),serial_factory=lambda **kwargs:fake)
        with patch.object(client,'wait_for',side_effect=main.LoginError('Timeout')):
            with self.assertRaises(main.LoginError):client.run()
        self.assertTrue(fake.closed)
    def test_version_workflow(self):
        yaml=Path(__file__).parent.parent/'.github/workflows/build.yml'
        content=yaml.read_text(encoding='utf-8')
        self.assertIn('V3600GS_Connect_V1.0.17.exe',content)
        self.assertIn('V3600GS_Connect_V1.0.17 main.py',content)
    def test_no_ttl_dependency(self):
        source=Path(main.__file__).read_text(encoding='utf-8')
        self.assertNotIn('ttpmacro.exe',source.lower())
        self.assertIn('serial.Serial',source)

if __name__=='__main__':unittest.main()
