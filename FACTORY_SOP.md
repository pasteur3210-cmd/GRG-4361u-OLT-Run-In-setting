# Factory SOP — V3600GS Connection Proof Test

1. Connect USB-Enhanced-SERIAL adapter to PC and console port of V3600GS; power on OLT.
2. Close existing Tera Term sessions on that COM port.
3. Start the EXE downloaded from GitHub Actions. Python is not required on this PC.
4. Verify Tera Term executable path. If not found, Browse to `C:\Program Files (x86)\teraterm\ttpmacro.exe`.
5. Click Refresh COM and choose USB-Enhanced-SERIAL COM port.
6. Click Connect & Auto Login; inspect the Tera Term window title for COM and `115200baud`.
7. Under Setup → Serial port, confirm 8 data bits, parity none, stop 1, flow control none (legacy environment compatibility check).
8. Wait for GUI READY and `gpon-olt(config-pon-0/1)#` in terminal.
9. If FAIL, provide a screenshot of Tera Term and the contents of `%LOCALAPPDATA%\V3600GS_Connect\records` (mask any secrets).
10. Once the login test passes, proceed with ONU CLI command collection.
