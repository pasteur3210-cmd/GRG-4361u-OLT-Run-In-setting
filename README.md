# V3600GS Connect V1.0.5 — Windows 11

## Purpose
Prove COM auto-detection, Tera Term serial session and four-stage login, without adding ONU/Ping checks.

## Critical fix from V1.0.4
V1.0.4 execution.log showed `CONNECT_RESULT|0` and `LINK_STATE=0`. The old process started `ttpmacro.exe` first and relied on a TTL `connect` command. V1.0.5 starts `ttermpro.exe` with `/C=COM_NUMBER`, `/BAUD=115200` and `/M=full_path_to_macro`, so Tera Term owns the COM port and attaches the macro. It DOES NOT open the port separately with pyserial.

## Factory steps
1. Keep Tera Term installed at `C:\Program Files (x86)\teraterm`. Close existing COM3 Tera Term sessions.
2. Place EXE in a **writable directory** (e.g. Desktop, D: test folder). Do not place EXE in Program Files.
3. Launch EXE → select USB-Enhanced-SERIAL COM → Connect & Auto Login.
4. Check Tera Term for `gpon-olt(config-pon-0/1)#`.
5. Check `records` folder next to EXE for `execution.log` and timestamped run folders.
6. On FAIL, archive the entire `records` directory and provide the GUI/terminal screenshot.

## Credentials
Login and enable passwords are hard-coded for this agreed lab setup; they are intentionally not written to text logs. `connect.ttl` necessarily contains credentials and should be handled as sensitive.

## Limits
No physical OLT/Windows Tera Term verification is possible here. Script syntax/unit checks cannot guarantee successful session attachment on the 2011 Tera Term build.
