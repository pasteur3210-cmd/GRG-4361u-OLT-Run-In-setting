# V3600GS Connect V1.0.3

First-stage Tera Term Serial auto-login. Windows 11, GitHub Actions EXE; no Python required on test PC.

## Where are records?
Records are **not** saved beside the EXE. Use GUI **Open Records Folder**, or press Win+R and enter:
`%LOCALAPPDATA%\V3600GS_Connect\records`

`execution.log` records button click, macro creation, process launch, prompt milestones and errors. A time-stamped folder stores the generated `connect.ttl`, `stage.txt`, `status.txt`, and `serial.log` when available. The generated TTL contains embedded credentials, **do not share it unredacted**.

## Operation
1. Close other sessions holding the COM port.
2. Start EXE, verify USB-Enhanced-SERIAL port selected.
3. Click Connect & Auto Login once.
4. Observe Tera Term, 115200, user-mode → enable → config → GPON 0/1.
5. If unsuccessful, open records folder and share `execution.log`, `stage.txt`, `status.txt`, redacted `serial.log`, plus screenshot (do not share `connect.ttl`).

## Verification status
Syntax / tests can run in GitHub Actions. Physical serial + 2011 Tera Term **not validated** without factory setup.
