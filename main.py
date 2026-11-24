"""V3600GS serial Tera Term connection proof of concept (Windows)."""
import datetime as dt
import traceback
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

BASE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
# Factory request: records live beside EXE. Run in a writable folder.
RECORDS = BASE / 'records'
TARGET_LABEL = 'USB-ENHANCED-SERIAL'
APP_VERSION = '1.0.6'


def find_teraterm():
    candidates = [
        Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'teraterm' / 'ttpmacro.exe',
        Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'teraterm5' / 'ttpmacro.exe',
        Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'teraterm' / 'ttpmacro.exe',
        Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'teraterm5' / 'ttpmacro.exe',
    ]
    candidates.insert(0, Path('C:/Program Files (x86)/teraterm/ttpmacro.exe'))
    found = shutil.which('ttpmacro.exe')
    if found:
        candidates.insert(0, Path(found))
    for p in candidates:
        if p.is_file():
            return str(p)
    return ''


def enumerate_ports():
    if list_ports is None:
        return []
    return sorted(((p.device, p.description or '', p.hwid or '') for p in list_ports.comports()),
                  key=lambda x: int(re.search(r'COM(\d+)', x[0], flags=re.I).group(1)) if re.search(r'COM(\d+)', x[0], flags=re.I) else 9999)


def com_number(device):
    match = re.fullmatch(r'COM(\d+)', device.strip(), flags=re.I)
    if not match:
        raise ValueError('Invalid COM port')
    value = int(match.group(1))
    if not 1 <= value <= 256:
        raise ValueError('COM port must be 1..256')
    return value


def ttl_quoted(value):
    """Only use trusted local filesystem path, with TTL single quote escaped."""
    if "'" in value or '\n' in value or '\r' in value:
        raise ValueError('Output path cannot contain apostrophes or newlines')
    return "'" + value.replace('/', '\\') + "'"


def build_macro(com, status_file, raw_log, stage_file=None):
    """TTL attached to TTERMPRO using /M; no connect command (V1.0.4 failed link=0)."""
    if stage_file is None:
        stage_file = status_file.with_name('stage.txt')
    status = ttl_quoted(str(status_file))
    stage = ttl_quoted(str(stage_file))
    raw = ttl_quoted(str(raw_log))
    return f"""; V3600GS V1.0.6 - TTERMPRO opens COM{com} at 115200 and attaches this TTL via /M=.
; Do not use TTL 'connect': V1.0.4 showed LINK_STATE=0 with this launch sequence.
filecreate fhandle {stage}
filewriteln fhandle 'STARTED|ATTACHED_MACRO'
fileclose fhandle
pause 1
testlink
link_state = result
if link_state = 2 goto SERIAL_READY
pause 2
testlink
link_state = result
if link_state = 2 goto SERIAL_READY
pause 2
testlink
link_state = result
if link_state <> 2 goto CONNECT_FAIL
:SERIAL_READY
filecreate fhandle {stage}
filewriteln fhandle 'CONNECTED|SERIAL'
fileclose fhandle
logopen {raw} 0 0
pause 1
sendln
timeout = 8
wait 'Login:' 'login:'
if result <> 0 goto LOGIN_PROMPT_OK
sendln
timeout = 12
wait 'Login:' 'login:'
if result = 0 goto LOGIN_PROMPT_FAIL
:LOGIN_PROMPT_OK
filecreate fhandle {stage}
filewriteln fhandle 'PROMPT|LOGIN'
fileclose fhandle
sendln 'qa123'
timeout = 10
wait 'Password:' 'password:'
if result = 0 goto LOGIN_FAIL
filecreate fhandle {stage}
filewriteln fhandle 'PROMPT|PASSWORD'
fileclose fhandle
sendln 'admin123'
timeout = 12
wait 'gpon-olt>'
if result = 0 goto LOGIN_FAIL
filecreate fhandle {stage}
filewriteln fhandle 'READY|USER_MODE'
fileclose fhandle
sendln 'enable'
timeout = 10
wait 'Password:' 'password:'
if result = 0 goto ENABLE_FAIL
sendln 'admin123'
timeout = 12
wait 'gpon-olt#'
if result = 0 goto ENABLE_FAIL
filecreate fhandle {stage}
filewriteln fhandle 'READY|ENABLE_MODE'
fileclose fhandle
sendln 'config terminal'
timeout = 10
wait 'gpon-olt(config)#'
if result = 0 goto CONFIG_FAIL
filecreate fhandle {stage}
filewriteln fhandle 'READY|CONFIG_MODE'
fileclose fhandle
sendln 'interface gpon 0/1'
timeout = 10
wait 'gpon-olt(config-pon-0/1)#'
if result = 0 goto INTERFACE_FAIL
filecreate fhandle {status}
filewriteln fhandle 'READY|gpon-olt(config-pon-0/1)#'
fileclose fhandle
end
:CONNECT_FAIL
filecreate fhandle {status}
int2str state_text link_state
stage_msg = 'FAIL|TERATERM_MACRO_LINK|LINK_STATE='
strconcat stage_msg state_text
filewriteln fhandle stage_msg
fileclose fhandle
end
:LOGIN_PROMPT_FAIL
filecreate fhandle {status}
filewriteln fhandle 'FAIL|LOGIN_PROMPT_TIMEOUT|SERIAL_CONNECTED'
fileclose fhandle
end
:LOGIN_FAIL
filecreate fhandle {status}
filewriteln fhandle 'FAIL|LOGIN'
fileclose fhandle
end
:ENABLE_FAIL
filecreate fhandle {status}
filewriteln fhandle 'FAIL|ENABLE'
fileclose fhandle
end
:CONFIG_FAIL
filecreate fhandle {status}
filewriteln fhandle 'FAIL|CONFIG'
fileclose fhandle
end
:INTERFACE_FAIL
filecreate fhandle {status}
filewriteln fhandle 'FAIL|GPON_INTERFACE'
fileclose fhandle
end
"""


def launch_arguments(ttermpro, com, macro_file):
    """Tera Term is the owner of COM and launches the attached TTL via /M."""
    return [str(ttermpro), f'/C={com}', '/BAUD=115200', f'/M={macro_file}']


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('V3600GS Connect V1.0.6')
        self.geometry('900x465')
        self.resizable(True, False)
        self.path = tk.StringVar(value=find_teraterm())
        self.selected = tk.StringVar()
        self.status = tk.StringVar(value='Not connected')
        self.last_status_file = None
        self.last_macro_file = None
        self.last_stage_file = None
        self.last_run_dir = None
        self.last_stage = None
        self.launch_process = None
        self._poll_count = 0
        self.ports = []
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Tera Term Macro (ttpmacro.exe)').grid(row=0, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.path, width=58).grid(row=1, column=0, sticky='ew')
        ttk.Button(frame, text='Browse...', command=self.browse).grid(row=1, column=1, padx=6)
        ttk.Label(frame, text='Serial device (USB-Enhanced-SERIAL preferred)').grid(row=2, column=0, sticky='w', pady=(16,0))
        self.combo = ttk.Combobox(frame, textvariable=self.selected, width=69, state='readonly')
        self.combo.grid(row=3, column=0, sticky='ew')
        ttk.Button(frame, text='Refresh COM', command=self.refresh).grid(row=3, column=1, padx=6)
        ttk.Label(frame, text='Fixed: 115200 baud | 8 data bits | no parity | 1 stop bit | no flow control').grid(row=4, column=0, columnspan=2, sticky='w', pady=15)
        ttk.Label(frame, text='Login: qa123 → enable → config terminal → interface gpon 0/1').grid(row=5, column=0, columnspan=2, sticky='w')
        ttk.Button(frame, text='Connect & Auto Login', command=self.launch).grid(row=6, column=0, sticky='w', pady=16)
        ttk.Button(frame, text='Check Result', command=self.check_result).grid(row=6, column=1, sticky='w')
        ttk.Button(frame, text='Open Records Folder', command=self.open_records).grid(row=9, column=0, sticky='w', pady=4)
        ttk.Label(frame, text=f'Records: {RECORDS} (beside EXE)', foreground='#335577').grid(row=10, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(frame, textvariable=self.status, wraplength=630).grid(row=7, column=0, columnspan=2, sticky='w')
        ttk.Label(frame, text='Close any other Tera Term session using the selected COM port first.', foreground='#985a00').grid(row=8, column=0, columnspan=2, sticky='w', pady=10)
        frame.columnconfigure(0, weight=1)
        self.refresh()

    def open_records(self):
        try:
            RECORDS.mkdir(parents=True, exist_ok=True)
            if sys.platform == 'win32':
                os.startfile(str(RECORDS))
            else:
                self.status.set(str(RECORDS))
        except Exception as exc:
            messagebox.showerror('Records folder', f'{type(exc).__name__}: {exc}')

    def audit(self, message):
        """Write diagnostic events before calling TTPMACRO, including failure paths."""
        RECORDS.mkdir(parents=True, exist_ok=True)
        log_path = RECORDS / 'execution.log'
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(f"{dt.datetime.now().isoformat(timespec='seconds')} | {message}\n")

    def browse(self):
        result = filedialog.askopenfilename(title='Select ttpmacro.exe', filetypes=[('Executable', '*.exe')])
        if result:
            self.path.set(result)

    def refresh(self):
        self.ports = enumerate_ports()
        labels = [f'{p[0]} — {p[1]} [{p[2]}]' for p in self.ports]
        self.combo['values'] = labels
        matched = [i for i, p in enumerate(self.ports) if TARGET_LABEL in (p[1] + ' ' + p[2]).upper()]
        if len(matched) == 1:
            self.combo.current(matched[0])
            self.status.set(f'Auto-selected {self.ports[matched[0]][0]}')
        elif len(matched) > 1:
            self.selected.set('')
            self.status.set('Multiple USB-Enhanced-SERIAL ports found. Select the correct COM manually.')
        else:
            self.selected.set('')
            self.status.set('No unique USB-Enhanced-SERIAL device found. Select manually (or install pyserial).')

    def launch(self):
        try:
            self.audit(f'CONNECT_CLICK | Version={APP_VERSION}')
            macro_exe = Path(self.path.get().strip().strip('"'))
            if not macro_exe.is_file() or macro_exe.name.lower() != 'ttpmacro.exe':
                raise ValueError('Cannot locate ttpmacro.exe. Check the Tera Term Macro path.')
            if not (macro_exe.parent / 'ttermpro.exe').is_file():
                raise ValueError('ttermpro.exe not found next to ttpmacro.exe.')
            if not self.selected.get():
                raise ValueError('Please select a COM port first.')
            chosen = next((p[0] for p, label in zip(self.ports, self.combo['values']) if label == self.selected.get()), None)
            if not chosen:
                raise ValueError('COM port selection changed. Refresh and select it again.')
            number = com_number(chosen)
            stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            run_dir = RECORDS / stamp
            run_dir.mkdir(parents=True, exist_ok=True)
            self.last_run_dir = run_dir
            status_file = run_dir / 'status.txt'
            stage_file = run_dir / 'stage.txt'
            macro_file = run_dir / 'connect.ttl'
            raw_log = run_dir / 'serial.log'
            encoding = 'mbcs' if sys.platform == 'win32' else 'utf-8'
            macro_file.write_text(build_macro(number, status_file, raw_log, stage_file), encoding=encoding)
            self.audit(f'MACRO_CREATED | COM={chosen} | File={macro_file} | Baud=115200')
            ttermpro = macro_exe.parent / 'ttermpro.exe'
            args = launch_arguments(ttermpro, number, macro_file)
            self.audit(f'TERATERM_LAUNCH | COM={chosen} | BAUD=115200 | MACRO={macro_file}')
            self.launch_process = subprocess.Popen(args, cwd=str(macro_exe.parent))
            self.audit(f'TERATERM_STARTED | PID={self.launch_process.pid}')
            self.last_status_file = status_file
            self.last_stage_file = stage_file
            self.last_macro_file = macro_file
            self.last_stage = None
            self._poll_count = 0
            self.status.set(f'Tera Term started (PID {self.launch_process.pid}); COM={chosen}; Macro attached via /M; records: {RECORDS}')
            self.after(700, self.poll_result)
        except Exception as exc:
            self.status.set(f'LAUNCH ERROR: {type(exc).__name__}: {exc}')
            try:
                self.audit(f'LAUNCH_ERROR | {type(exc).__name__}: {exc}')
            except Exception:
                pass
            messagebox.showerror('Connect & Auto Login failed',
                f'{type(exc).__name__}: {exc}\n\nRecords: {RECORDS}')

    def poll_result(self):
        self._poll_count += 1
        if self.last_stage_file and self.last_stage_file.exists():
            try:
                stage = self.last_stage_file.read_text(encoding='ascii', errors='replace').strip()
                if stage != self.last_stage:
                    self.last_stage = stage
                    self.audit('MACRO_STAGE | ' + stage)
                    self.status.set(stage + ' | ' + str(self.last_run_dir))
            except OSError:
                pass
        if self.last_status_file and self.last_status_file.exists():
            self.check_result()
            return
        if self.launch_process is not None and self.launch_process.poll() is not None:
            self.audit(f'TERATERM_EXIT_WITHOUT_STATUS | code={self.launch_process.returncode}')
            self.status.set('Tera Term closed without login status; inspect records: ' + str(RECORDS))
            return
        # No silent infinite wait. Allow initial connection and all prompt timeouts (~80 s).
        if self._poll_count >= 150:
            self.audit('TIMEOUT_WAITING_FOR_RESULT')
            self.status.set('TIMEOUT: no result after ~105 s. Inspect the Tera Term window and records: ' + str(RECORDS))
            return
        if self._poll_count % 8 == 0 and not self.last_stage:
            self.status.set(f'Macro running; waiting for OLT prompts ({round(self._poll_count * 0.7)} s). '
                            f'Records: {RECORDS}')
        self.after(700, self.poll_result)

    def _cleanup_macro(self):
        # Keep connect.ttl for diagnosing old Tera Term compatibility.
        return

    def check_result(self):
        if not self.last_status_file:
            messagebox.showinfo('Result', 'Start a connection first.')
            return
        if self.last_status_file.exists():
            result = self.last_status_file.read_text(encoding='utf-8', errors='replace').strip()
            if getattr(self, '_reported_status', None) != (self.last_status_file, result):
                self._reported_status = (self.last_status_file, result)
                self.audit('MACRO_RESULT | ' + result)
            self.status.set(result + '   |   Records: ' + str(RECORDS))
        else:
            self.status.set('No result file yet. Check Tera Term window and records: ' + str(RECORDS))


if __name__ == '__main__':
    if sys.platform != 'win32':
        print('This GUI is intended for Windows; opening a UI for development only.')
    App().mainloop()
