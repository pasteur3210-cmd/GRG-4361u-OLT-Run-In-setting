# Factory SOP V1.0.6

1. Extract GitHub Actions artifact and put EXE in a writable test directory.
2. Close all existing serial COM Tera Term windows.
3. Run EXE, check correct USB-Enhanced-SERIAL port is selected.
4. Click Connect & Auto Login once.
5. Expected Tera Term title: `COMx:115200baud`; expected CLI: `gpon-olt(config-pon-0/1)#`.
6. Check `records` right next to EXE. Inspect `execution.log`, run folder's `stage.txt`, `status.txt`, `serial.log`.
7. If no login, provide entire records folder. Do not interpret COM title alone as successful connectivity.

V1.0.6: Build gate validates Windows-style `/M=` macro path equivalence; the actual `/M` command remains unchanged.
