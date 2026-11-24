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
from onu_parser import parse_time_stamp, parse_optical, merge_state_data, parse_onu_state
from excel_record import export_cycles
from session_runner import run_session, rebuild_excel
from ping_mapping import normalize_ips, verify_mapping
from serial.tools import list_ports

VERSION = "1.0.14"
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
            self.stage('QUERY_ONU_STATE')
            state_raw = self.command('show onu state', timeout=25)
            (folder/'onu_state.log').write_text(state_raw, encoding='utf-8')
            self.stage('QUERY_ONU_TIMESTAMP')
            timestamp_raw = self.command('show onu time-stamp', timeout=25)
            (folder/'onu_time_stamp.log').write_text(timestamp_raw, encoding='utf-8')
            self.stage('QUERY_ONU_OPTICAL')
            optical_raw = self.command('show onu optical-info all', timeout=40)
            (folder/'onu_optical_info.log').write_text(optical_raw, encoding='utf-8')
            timestamp=parse_time_stamp(timestamp_raw)
            optical=parse_optical(optical_raw)
            state=parse_onu_state(state_raw)
            merged=merge_state_data(state,timestamp,optical)
            self.log.info('PARSE|STATE=%s|TIMESTAMP=%s|OPTICAL=%s|MERGED=%s',len(state),len(timestamp),len(optical),len(merged))
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
    def __init__(self, root):
        self.root = root
        root.title('V3600GS Connect V'+VERSION+' — ONU Run-in')
        root.geometry('1100x780')
        self.messages = queue.Queue()
        self.stop_flag = threading.Event()
        self.running = False
        self.port_var = tk.StringVar()
        self.mode = tk.StringVar(value='single')
        self.interval_var = tk.StringVar(value='5')
        self.duration_var = tk.StringVar(value='72')
        self.state = tk.StringVar(value='READY — select COM and run')
        self.cycle_state = tk.StringVar(value='Completed cycles: 0')
        self.last_excel = None
        self.verified_mapping = None
        self.verified_snapshot = None
        self.ip_text = None
        frm=ttk.Frame(root,padding=16)
        frm.pack(fill='both',expand=True)
        ttk.Label(frm,text='V3600GS ONU Run-in — Direct Serial',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(frm,text='COM Port — USB-Enhanced-SERIAL preferred').pack(anchor='w',pady=(12,2))
        row=ttk.Frame(frm);row.pack(fill='x')
        self.combo=ttk.Combobox(row,textvariable=self.port_var,state='readonly',width=75)
        self.combo.pack(side='left',fill='x',expand=True)
        self.refresh_button=ttk.Button(row,text='Refresh COM',command=self.refresh)
        self.refresh_button.pack(side='left',padx=8)
        ttk.Label(frm,text='Serial: 115200 / 8N1 | Login → Enable → Config → GPON 0/1').pack(anchor='w',pady=(10,4))
        settings=ttk.LabelFrame(frm,text='Test Settings',padding=9)
        settings.pack(fill='x',pady=(4,8))
        modes=ttk.Frame(settings);modes.pack(fill='x')
        ttk.Radiobutton(modes,text='Single Check',value='single',variable=self.mode,command=self.update_mode).pack(side='left',padx=(0,16))
        ttk.Radiobutton(modes,text='Loop Check',value='loop',variable=self.mode,command=self.update_mode).pack(side='left')
        nums=ttk.Frame(settings); nums.pack(fill='x',pady=(8,0))
        ttk.Label(nums,text='Check Interval (minutes):').pack(side='left')
        self.interval_input=ttk.Entry(nums,textvariable=self.interval_var,width=9)
        self.interval_input.pack(side='left',padx=(5,24))
        ttk.Label(nums,text='Duration (hours, 0 = until Stop):').pack(side='left')
        self.duration_input=ttk.Entry(nums,textvariable=self.duration_var,width=9)
        self.duration_input.pack(side='left',padx=(5,0))
        mappingframe=ttk.LabelFrame(frm,text='Pre-Run DUT IP / MAC / GPON SN Verification',padding=8)
        mappingframe.pack(fill='x',pady=(3,7))
        ttk.Label(mappingframe,text='DUT IP list (one IPv4 per line; same LAN as test PC)').pack(anchor='w')
        self.ip_text=tk.Text(mappingframe,height=3,width=65)
        self.ip_text.pack(fill='x',pady=(2,5))
        self.ip_text.bind('<KeyRelease>',self.invalidate_mapping)
        mbuttons=ttk.Frame(mappingframe);mbuttons.pack(fill='x')
        self.verify_btn=ttk.Button(mbuttons,text='Verify IP / MAC / GPON SN Mapping',command=self.verify)
        self.verify_btn.pack(side='left')
        self.mapping_label=tk.StringVar(value='Mapping NOT VERIFIED — verify before Start')
        ttk.Label(mbuttons,textvariable=self.mapping_label).pack(side='left',padx=12)
        self.map_tree=ttk.Treeview(mappingframe,columns=('ip','mac','lan','onu','sn','ping','status'),show='headings',height=4)
        for key,label,width in [('ip','DUT IP',130),('mac','WAN MAC (ARP)',145),('lan','LAN MAC (-1)',145),('onu','ONU ID',80),('sn','GPON SN',150),('ping','Pre-Ping',90),('status','Mapping',170)]:
            self.map_tree.heading(key,text=label)
            self.map_tree.column(key,width=width,stretch=True)
        self.map_tree.pack(fill='x',pady=(5,0))
        buttons=ttk.Frame(frm);buttons.pack(fill='x',pady=(8,9))
        self.start_btn=ttk.Button(buttons,text='Start ONU Check',command=self.start,state='disabled')
        self.start_btn.pack(side='left')
        self.stop_btn=ttk.Button(buttons,text='Stop',command=self.stop,state='disabled')
        self.stop_btn.pack(side='left',padx=10)
        ttk.Button(buttons,text='Open Records Folder',command=self.open_records).pack(side='right')
        self.excel_btn=ttk.Button(buttons,text='Open Excel',command=self.open_excel,state='disabled')
        self.excel_btn.pack(side='right',padx=10)
        ttk.Label(frm,textvariable=self.state,foreground='#005ea8',font=('Segoe UI',10,'bold')).pack(anchor='w')
        ttk.Label(frm,textvariable=self.cycle_state).pack(anchor='w',pady=(3,0))
        self.out=tk.Text(frm,height=12,wrap='word',state='disabled')
        self.out.pack(fill='both',expand=True,pady=(8,0))
        self.port_var.trace_add('write',lambda *_:self.invalidate_mapping())
        self.refresh()
        self.update_mode()
        root.after(100,self.poll)

    def display(self,message):
        self.out.configure(state='normal')
        self.out.insert('end',str(message)+'\n')
        self.out.see('end')
        self.out.configure(state='disabled')

    def invalidate_mapping(self,event=None):
        self.verified_mapping=None
        self.verified_snapshot=None
        self.mapping_label.set('Mapping NOT VERIFIED — verify before Start')
        self.start_btn.configure(state='disabled')

    def mapping_snapshot(self):
        return (self.options.get(self.port_var.get(),''),self.ip_text.get('1.0','end').strip())

    def verify(self):
        if self.running:return
        port,iptext=self.mapping_snapshot()
        if not valid_port(port):
            messagebox.showerror('COM Port','Select COM port');return
        try:
            ips=normalize_ips(iptext)
        except ValueError as exc:
            messagebox.showerror('DUT IP List',str(exc));return
        self.invalidate_mapping()
        self.running=True
        self.stop_flag.clear()
        self.verify_btn.configure(state='disabled')
        self.combo.configure(state='disabled')
        self.refresh_button.configure(state='disabled')
        self.state.set('VERIFYING MAPPING — ONU state and IP / MAC ...')
        logger_folder=RECORD_ROOT/('Mapping_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        try:logger=make_logger(logger_folder)
        except OSError as exc:
            self.running=False
            self.verify_btn.configure(state='normal')
            self.combo.configure(state='readonly')
            self.refresh_button.configure(state='normal')
            messagebox.showerror('Record',str(exc));return
        snapshot=(port,iptext)
        def worker():
            try:
                client=SerialLogin(port,logger,self.stop_flag,on_stage=lambda x:self.messages.put(('stage',x)))
                try:
                    client.open();client._login_sequence()
                    raw=client.command('show onu state',timeout=35)
                    (logger_folder/'onu_state.log').write_text(raw,encoding='utf-8')
                    states=parse_onu_state(raw)
                finally:client.close()
                rows,mapping,errors=verify_mapping(ips,states)
                (logger_folder/'mapping_check.json').write_text(
                    __import__('json').dumps({'rows':rows,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
                logger.info('MAPPING_FINISHED|IPS=%s|MATCH=%s|ERRORS=%s',len(ips),len(mapping),len(errors))
                self.messages.put(('MAPPING_DONE',{'rows':rows,'mapping':mapping,'errors':errors,'snapshot':snapshot}))
            except Exception as exc:
                logger.exception('MAPPING_ERROR')
                self.messages.put(('MAPPING_DONE',{'rows':[],'mapping':{},'errors':[str(exc)],'snapshot':snapshot}))
            finally:
                for h in list(logger.handlers):h.close();logger.removeHandler(h)
        threading.Thread(target=worker,daemon=True).start()

    def refresh(self):
        self.invalidate_mapping()
        ports=available_ports()
        self.options={f'{dev} — {desc}':dev for dev,desc,_ in ports}
        self.combo['values']=list(self.options)
        preferred=select_default(ports)
        key=next((k for k,v in self.options.items() if v==preferred),'')
        self.port_var.set(key)
        self.display(('Auto-selected '+preferred) if preferred else 'Choose COM Port')

    def update_mode(self):
        state='normal' if self.mode.get()=='loop' and not self.running else 'disabled'
        self.interval_input.configure(state=state)
        self.duration_input.configure(state=state)

    def start(self):
        if self.running:return
        port=self.options.get(self.port_var.get(),'')
        if not valid_port(port):
            messagebox.showerror('COM Port','Choose a valid COM port first');return
        if not self.verified_mapping or self.verified_snapshot != self.mapping_snapshot():
            self.invalidate_mapping()
            messagebox.showerror('Mapping','Verify IP / MAC / GPON SN before Start.');return
        mapping={k:dict(v) for k,v in self.verified_mapping.items()}
        loop=self.mode.get()=='loop'
        try:
            interval=float(self.interval_var.get()) if loop else 5.0
            duration=float(self.duration_var.get()) if loop else 0.0
            if not (0<interval<=1440 and 0<=duration<=8760):raise ValueError()
        except ValueError:
            messagebox.showerror('Test Settings','Interval: >0 to 1440 min; Duration: 0 to 8760 hours')
            return
        try:
            folder=RECORD_ROOT/('Run_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
            logger=make_logger(folder)
        except OSError as exc:
            messagebox.showerror('Record',f'Cannot create folder beside EXE: {exc}');return
        self.running=True
        self.stop_flag.clear()
        self.start_btn.configure(state='disabled')
        self.verify_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        self.combo.configure(state='disabled')
        self.refresh_button.configure(state='disabled')
        self.excel_btn.configure(state='disabled')
        self.last_excel=None
        self.update_mode()
        self.cycle_state.set('Completed cycles: 0')
        self.state.set('RUNNING — '+('Loop Check' if loop else 'Single Check'))
        self.display('START | '+port+' | records: '+str(folder))
        logger.info('START|VERSION=%s|PORT=%s|MODE=%s|INTERVAL_MIN=%s|DURATION_HR=%s',
                    VERSION,port,'LOOP' if loop else 'SINGLE',interval,duration)
        def worker():
            def notify(kind,msg):self.messages.put((kind,msg))
            try:
                factory=lambda: SerialLogin(port,logger,self.stop_flag,
                                              on_stage=lambda stage:self.messages.put(('stage',stage)))
                run_session(factory,folder,logger,self.stop_flag,loop=loop,
                            interval_min=interval,duration_hr=duration,notify=notify,mapping=mapping)
            except Exception as exc:
                logger.exception('SESSION_ERROR')
                self.messages.put(('DONE',{'status':'ERROR: '+str(exc),'cycles':0,
                                           'folder':str(folder),'last_result':None}))
            finally:
                for handler in list(logger.handlers):
                    handler.close();logger.removeHandler(handler)
        threading.Thread(target=worker,daemon=True).start()

    def stop(self):
        if not self.running:return
        self.stop_flag.set()
        self.state.set('STOP REQUESTED — finishing current save')
        self.stop_btn.configure(state='disabled')
        self.display('User requested Stop; recorded cycles will be retained')

    def open_records(self):
        try:
            RECORD_ROOT.mkdir(parents=True,exist_ok=True)
            import os
            if sys.platform=='win32':os.startfile(str(RECORD_ROOT))
            else:messagebox.showinfo('Records folder',str(RECORD_ROOT))
        except Exception as exc:messagebox.showerror('Records folder',str(exc))

    def open_excel(self):
        try:
            if not self.last_excel or not self.last_excel.exists():
                raise FileNotFoundError('No completed Excel record')
            import os
            if sys.platform=='win32':os.startfile(str(self.last_excel))
            else:messagebox.showinfo('Excel file',str(self.last_excel))
        except Exception as exc:messagebox.showerror('Open Excel',str(exc))

    def poll(self):
        try:
            while True:
                kind,msg=self.messages.get_nowait()
                if kind=='stage':
                    self.display(msg)
                elif kind=='CHECKING':
                    self.state.set(str(msg))
                    self.display(msg)
                elif kind=='CYCLE':
                    self.display(msg)
                    m=re.match(r'Cycle (\d+)',str(msg))
                    if m:self.cycle_state.set('Completed cycles: '+m.group(1))
                    self.state.set(str(msg))
                elif kind=='SAVE ERROR':
                    self.state.set('SAVE ERROR — see execution.log')
                    self.display(msg)
                elif kind=='MAPPING_DONE':
                    self.running=False
                    self.verify_btn.configure(state='normal')
                    self.combo.configure(state='readonly')
                    self.refresh_button.configure(state='normal')
                    for existing in self.map_tree.get_children():self.map_tree.delete(existing)
                    for row in msg['rows']:
                        self.map_tree.insert('', 'end', values=(row['ip'],row['mac'],row.get('lan_mac',''),row['onu_id'] or '',
                                             row['gpon_sn'],row['ping'],row['status']))
                    if not msg['errors'] and self.mapping_snapshot()==msg['snapshot']:
                        self.verified_mapping=msg['mapping']
                        self.verified_snapshot=msg['snapshot']
                        self.mapping_label.set(f'VERIFIED — {len(msg["mapping"])} DUT / ONU')
                        self.start_btn.configure(state='normal')
                        self.state.set('MAPPING VERIFIED — ready for Start')
                    else:
                        self.invalidate_mapping()
                        self.state.set('MAPPING FAILED — '+ '; '.join(msg['errors'][:3]))
                        self.display(self.state.get())
                    self.update_mode()
                elif kind=='DONE':
                    self.running=False
                    self.invalidate_mapping()  # Every new run requires fresh pre-run mapping.
                    self.verify_btn.configure(state='normal')
                    self.stop_btn.configure(state='disabled')
                    self.combo.configure(state='readonly')
                    self.refresh_button.configure(state='normal')
                    self.update_mode()
                    self.last_excel=Path(msg['folder'])/'ONU_Master_Record.xlsx'
                    if self.last_excel.is_file():self.excel_btn.configure(state='normal')
                    state=msg['status']
                    self.state.set(f'{state} — {msg["cycles"]} cycles; last result: {msg["last_result"]}')
                    self.display(self.state.get())
        except queue.Empty:pass
        self.root.after(100,self.poll)


def main():
    root=tk.Tk()
    GUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
