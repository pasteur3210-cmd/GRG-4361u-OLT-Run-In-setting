"""V3600GS first-stage direct-serial connection and login tool.

The test PC must not have Tera Term holding the selected COM port while this app runs.
"""
from __future__ import annotations
import datetime as dt
import logging
import queue
import re
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import serial
from onu_parser import parse_time_stamp, parse_optical, merge_data
from excel_record import export_cycles
from serial.tools import list_ports

VERSION = "1.0.11"
BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RECORD_ROOT = BASE / "records"
BAUD = 115200
USER = "qa123"
LOGIN_PASSWORD = "admin123"
ENABLE_PASSWORD = "admin123"
TARGET_PROMPT = "gpon-olt(config-pon-0/1)#"


def available_ports():
    ports = [(p.device, p.description or "", p.hwid or "") for p in list_ports.comports()]
    return sorted(ports, key=lambda x: (0 if 'usb-enhanced-serial' in x[1].lower() else 1, x[0]))


def select_default(ports):
    preferred = [p for p in ports if 'usb-enhanced-serial' in p[1].lower()]
    return preferred[0][0] if len(preferred) == 1 else (ports[0][0] if len(ports)==1 else "")


def valid_port(name):
    return bool(re.fullmatch(r'COM[1-9][0-9]*', name, flags=re.I))


def safe_ascii(data):
    # Terminal original output can contain vendor-specific bytes.
    return data.decode('utf-8',errors='replace')


class LoginError(RuntimeError):
    pass


class SerialLogin:
    """Stateful serial access; does not depend on Tera Term or TTL Macro."""
    def __init__(self, port, logger, stop_flag=None, serial_factory=serial.Serial, on_stage=None):
        self.port = port
        self.log = logger
        self.stop = stop_flag or threading.Event()
        self.serial_factory = serial_factory
        self.on_stage = on_stage or (lambda stage: None)
        self.link = None
        self.rx = ""

    def stage(self, name):
        self.log.info('STAGE|%s', name)
        self.on_stage(name)

    def open(self):
        self.stage('OPEN_SERIAL')
        self.link = self.serial_factory(port=self.port, baudrate=BAUD, bytesize=serial.EIGHTBITS,
                                        parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                        timeout=0.2, write_timeout=2, xonxoff=False, rtscts=False, dsrdtr=False)
        self.stage('SERIAL_OPEN')

    def close(self):
        if self.link is not None:
            try: self.link.close()
            except Exception: self.log.exception('SERIAL_CLOSE_ERROR')
            self.link = None

    def write(self, command, *, secret=False):
        if self.stop.is_set(): raise LoginError('User stopped')
        # For passwords, do not include the content in any application log.
        self.log.info('TX|%s', '<REDACTED>' if secret else repr(command))
        self.link.write((command+'\r').encode('ascii'))
        self.link.flush()

    def wait_for(self, patterns, timeout, *, phase):
        if isinstance(patterns,str): patterns=[patterns]
        self.stage('WAIT_'+phase)
        deadline=time.monotonic()+timeout
        fresh = ""
        while time.monotonic()<deadline:
            if self.stop.is_set():raise LoginError('User stopped')
            data=self.link.read(4096)
            if data:
                msg=safe_ascii(data)
                self.rx+=msg
                fresh+=msg
                # Never log terminal raw text during password prompts. Raw output may echo secrets.
                # Only log safe stage names and receive byte counts.
                self.log.info('RX_BYTES|%s|%s', phase, len(data))
                for pattern in patterns:
                    if re.search(pattern,fresh,re.I):
                        self.stage('MATCH_'+phase)
                        return
            else:
                # On buffer rotation, retain recent text while keeping scanner offset stable.
                if len(self.rx)>20000:
                    self.rx=self.rx[-2048:]
        raise LoginError('Timeout waiting for '+phase)

    def run(self, check=False, output_folder=None):
        """Login; optionally check both ONU commands before closing COM."""
        try:
            self.open()
            result = self._login_sequence()
            if not check:
                return result
            if output_folder is None:
                raise ValueError('output_folder is required for check')
            folder = Path(output_folder)
            self.stage('QUERY_ONU_TIMESTAMP')
            timestamp_raw = self.command('show onu time-stamp', timeout=25)
            (folder/'onu_time_stamp.log').write_text(timestamp_raw, encoding='utf-8')
            self.stage('QUERY_ONU_OPTICAL')
            optical_raw = self.command('show onu optical-info all', timeout=40)
            (folder/'onu_optical_info.log').write_text(optical_raw, encoding='utf-8')
            timestamp=parse_time_stamp(timestamp_raw)
            optical=parse_optical(optical_raw)
            merged=merge_data(timestamp,optical)
            self.log.info('PARSE|TIMESTAMP=%s|OPTICAL=%s|MERGED=%s',len(timestamp),len(optical),len(merged))
            return result,merged
        finally:
            self.close()

    def command(self, cmd, timeout=25):
        """Capture until complete GPON prompt; reject partial/truncated output."""
        self.stage('SEND_'+cmd.upper().replace(' ','_').replace('-','_'))
        self.write(cmd)
        deadline=time.monotonic()+timeout
        result=''
        more=re.compile(r'(?:--\s*more\s*--|--More--)',re.I)
        prompt=re.compile(r'(?:^|[\r\n])\s*gpon-olt\(config-pon-0/1\)#\s*$',re.I)
        while time.monotonic()<deadline:
            if self.stop.is_set():raise LoginError('User stopped')
            b=self.link.read(4096)
            if not b:continue
            text=safe_ascii(b)
            result+=text
            self.log.info('CLI_RX|%s|%s',cmd,len(b))
            if len(result)>2000000:raise LoginError('CLI output exceeded 2 MB')
            if more.search(result[-120:]):
                self.link.write(b' ')
                self.link.flush()
                result=more.sub('',result)
            if prompt.search(result):
                self.stage('CLI_COMPLETE_'+cmd.upper().replace(' ','_').replace('-','_'))
                return result
        raise LoginError('Timeout waiting for CLI prompt after '+cmd)

    def _login_sequence(self):
        self.stage('SEND_WAKEUP')
        self.write('')
        try:
            self.wait_for([r'Login\s*:',r'Password\s*:',r'gpon-olt(?:\([^\r\n]*\))?[>#]'],5,phase='INITIAL_PROMPT')
        except LoginError:
            self.write('')
            self.wait_for([r'Login\s*:',r'Password\s*:',r'gpon-olt(?:\([^\r\n]*\))?[>#]'],8,phase='INITIAL_PROMPT_RETRY')
        prompt=self.rx[-1000:]
        if re.search(r'gpon-olt\(config-pon-0/1\)#\s*$',prompt,re.I):
            self.stage('READY');return TARGET_PROMPT
        if re.search(r'gpon-olt\(config\)#\s*$',prompt,re.I):return self.enter_interface()
        if re.search(r'gpon-olt#\s*$',prompt,re.I):return self.enter_config()
        if re.search(r'gpon-olt>\s*$',prompt,re.I):return self.enable()
        if re.search(r'Password\s*:\s*$',prompt,re.I):
            raise LoginError('Password prompt at startup; unknown state')
        if not re.search(r'Login\s*:',prompt,re.I):
            raise LoginError('Unrecognized initial CLI prompt')
        self.stage('SEND_USERNAME')
        self.write(USER)
        self.wait_for(r'Password\s*:',10,phase='LOGIN_PASSWORD_PROMPT')
        self.stage('SEND_LOGIN_PASSWORD')
        self.write(LOGIN_PASSWORD,secret=True)
        self.wait_for(r'gpon-olt>\s*',12,phase='USER_PROMPT')
        return self.enable()

    def enable(self):
        self.stage('SEND_ENABLE')
        self.write('enable')
        self.wait_for(r'Password\s*:',10,phase='ENABLE_PASSWORD_PROMPT')
        self.stage('SEND_ENABLE_PASSWORD')
        self.write(ENABLE_PASSWORD,secret=True)
        self.wait_for(r'gpon-olt#\s*',12,phase='ENABLE_PROMPT')
        return self.enter_config()

    def enter_config(self):
        self.stage('SEND_CONFIG_TERMINAL')
        self.write('config terminal')
        self.wait_for(r'gpon-olt\(config\)#\s*',12,phase='CONFIG_PROMPT')
        return self.enter_interface()

    def enter_interface(self):
        self.stage('SEND_INTERFACE_GPON_0_1')
        self.write('interface gpon 0/1')
        self.wait_for(r'gpon-olt\(config-pon-0/1\)#\s*',12,phase='GPON_PROMPT')
        self.stage('READY')
        return TARGET_PROMPT


def make_logger(folder):
    folder.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('v3600gs.run.'+folder.name)
    logger.setLevel(logging.INFO)
    logger.propagate=False
    handler=logging.FileHandler(folder/'execution.log',encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(handler)
    return logger


class GUI:
    def __init__(self,root):
        self.root=root
        self.root.title('V3600GS Connect V'+VERSION+' — ONU Check')
        self.root.geometry('860x490')
        self.messages=queue.Queue()
        self.stop_flag=threading.Event()
        self.running=False
        self.port_var=tk.StringVar()
        self.state=tk.StringVar(value='READY TO CONNECT (Tera Term must be closed)')
        frm=ttk.Frame(root,padding=18)
        frm.pack(fill='both',expand=True)
        ttk.Label(frm,text='V3600GS Direct Serial (without Tera Term Macro)',font=('Segoe UI',13,'bold')).pack(anchor='w')
        ttk.Label(frm,text='COM Port — USB-Enhanced-SERIAL preferred').pack(anchor='w',pady=(18,2))
        row=ttk.Frame(frm);row.pack(fill='x')
        self.combo=ttk.Combobox(row,textvariable=self.port_var,state='readonly',width=75)
        self.combo.pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Refresh COM',command=self.refresh).pack(side='left',padx=8)
        ttk.Label(frm,text='Fixed: 115200 baud | 8 data bits | no parity | 1 stop bit | no flow control').pack(anchor='w',pady=(14,3))
        ttk.Label(frm,text='Login qa123 → enable → config terminal → interface gpon 0/1').pack(anchor='w')
        actions=ttk.Frame(frm);actions.pack(fill='x',pady=18)
        self.connect=ttk.Button(actions,text='Connect & Auto Login',command=self.start)
        self.connect.pack(side='left')
        self.check_btn=ttk.Button(actions,text='Login + ONU Check Once (Excel)',command=lambda:self.start(check=True))
        self.check_btn.pack(side='left',padx=10)
        ttk.Button(actions,text='Stop',command=self.stop).pack(side='left',padx=10)
        ttk.Button(actions,text='Open Records Folder',command=self.open_records).pack(side='right')
        ttk.Label(frm,textvariable=self.state,foreground='#005ea8').pack(anchor='w')
        self.out=tk.Text(frm,height=8,wrap='word',state='disabled')
        self.out.pack(fill='both',expand=True,pady=(8,0))
        self.refresh()
        root.after(100,self.poll)

    def display(self,message):
        self.out.configure(state='normal')
        self.out.insert('end',message+'\n')
        self.out.see('end')
        self.out.configure(state='disabled')
        self.state.set(message)

    def refresh(self):
        ports=available_ports()
        self.options={f'{dev} — {desc}':dev for dev,desc,_ in ports}
        self.combo['values']=list(self.options)
        preferred=select_default(ports)
        key=next((k for k,v in self.options.items() if v==preferred), '')
        self.port_var.set(key)
        self.display(('Auto-selected '+preferred) if preferred else 'Select a COM port; no unique USB-Enhanced-SERIAL detected')

    def start(self,check=False):
        if self.running:return
        port=self.options.get(self.port_var.get(),'')
        if not valid_port(port):
            messagebox.showerror('COM Port','Choose a valid COM port first');return
        try:
            RECORD_ROOT.mkdir(parents=True,exist_ok=True)
            folder=RECORD_ROOT/dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            logger=make_logger(folder)
        except OSError as exc:
            messagebox.showerror('Records folder',f'Cannot create records beside EXE: {exc}')
            return
        self.running=True
        self.connect.configure(state='disabled')
        self.check_btn.configure(state='disabled')
        self.stop_flag.clear()
        self.display(('Checking ONUs via ' if check else 'Connecting ')+port+' (close Tera Term first)...')
        logger.info('START|VERSION=%s|PORT=%s',VERSION,port)
        def worker():
            try:
                client=SerialLogin(port,logger,self.stop_flag,on_stage=lambda stage:self.messages.put(('stage',stage)))
                returned=client.run(check=check,output_folder=folder)
                if check:
                    result, units=returned
                    cycle={'time':dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'onus':units}
                    outfile=export_cycles(folder/'ONU_Check_Record.xlsx',[cycle])
                    logger.info('EXCEL_CREATED|%s|ONU_COUNT=%d',outfile,len(units))
                    self.messages.put(('stage',f'EXCEL SAVED | {outfile} | ONU count={len(units)}'))
                else:
                    result=returned
                logger.info('RESULT|PASS|%s',result)
                (folder/'status.txt').write_text('PASS|'+result+'\n',encoding='utf-8')
                self.messages.put(('done',('ONU CHECK COMPLETED | ' if check else 'LOGIN READY | ')+result))
            except Exception as exc:
                logger.exception('RESULT|FAIL|%s',type(exc).__name__)
                (folder/'status.txt').write_text('FAIL|'+type(exc).__name__+'|'+str(exc)+'\n',encoding='utf-8')
                self.messages.put(('done','FAIL | '+str(exc)))
            finally:
                for handler in list(logger.handlers):
                    handler.close();logger.removeHandler(handler)
        threading.Thread(target=worker,daemon=True).start()

    def stop(self):
        self.stop_flag.set()
        self.display('STOP requested')

    def open_records(self):
        try:
            RECORD_ROOT.mkdir(parents=True,exist_ok=True)
            import os
            if sys.platform=='win32':os.startfile(str(RECORD_ROOT))
            else:messagebox.showinfo('Records folder',str(RECORD_ROOT))
        except Exception as exc:messagebox.showerror('Records folder',str(exc))

    def poll(self):
        try:
            while True:
                typ,msg=self.messages.get_nowait()
                if typ=='stage':self.display(msg)
                else:
                    self.running=False
                    self.connect.configure(state='normal')
                    self.check_btn.configure(state='normal')
                    self.display(msg)
        except queue.Empty:pass
        self.root.after(100,self.poll)


def main():
    root=tk.Tk()
    GUI(root)
    root.mainloop()

if __name__=='__main__':main()
