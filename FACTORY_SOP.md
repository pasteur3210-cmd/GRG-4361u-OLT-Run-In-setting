# V3600GS Connect V1.0.10 — Factory SOP

1. Close all Tera Term sessions that use the target Serial COM port.
2. Run `V3600GS_Connect_V1.0.10.exe` from a writable folder.
3. Confirm the automatically selected `USB-Enhanced-SERIAL` COM port.
4. Click **Login + ONU Check Once (Excel)**. Do not click Stop while the CLI commands are running.
5. Wait for **ONU CHECK COMPLETED**.
6. Click **Open Records Folder**, open the latest timestamped subfolder and inspect `ONU_Check_Record.xlsx`.
7. Open `01_Loop_Summary`: one row/cycle, dynamic ONU-ID columns (e.g. 1–16); read `02_ONU_Detail` for the actual returned ONU IDs.
8. When an ONU is absent in a multi-cycle export, its own columns show `MISSING THIS CYCLE` (never automatically Offline).
8. If FAIL, preserve the complete latest folder, including `execution.log`, `status.txt` and raw CLI outputs where available; share it for diagnosis.

Important: `DATA RECORDED (STATUS UNVERIFIED)` means optical/timestamp data was captured; it is **not an ONU Online PASS**. No acceptance thresholds are configured yet.
