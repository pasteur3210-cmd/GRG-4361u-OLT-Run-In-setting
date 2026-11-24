# Factory SOP — V1.0.12

1. Close Tera Term. Connect V3600GS Serial to USB and power on OLT.
2. Run `V3600GS_Connect_V1.0.12.exe`, confirm auto-detected COM and fixed 115200 baud.
3. Choose **Single Check** for one round, or **Loop Check** for repeated monitoring.
4. For Loop set `Check Interval` in minutes and `Duration` in hours (0 means until Stop).
5. Click **Start ONU Check** and observe CHECKING, cycle number and `PASS / FAIL / INCOMPLETE / ERROR`.
6. A successful single check ends with `COMPLETED — 1 cycles`. No need to press Stop.
7. Loop automatically ends at duration or stops when Stop is pressed; Stop is not FAIL.
8. Use `Open Records Folder`; each Start produces exactly one `records/Run_...` folder.
9. Inspect `ONU_Master_Record.xlsx` first tab; each cycle is a row and each ONU has stable ID-based columns.
10. If FAIL, check `ONU*_Phase State` / `ONU*_ONU Result`; for ERROR inspect raw CLI and execution.log.
11. If Excel is open while test is running, close it: file lock can block updates. JSONL retains cycles.
12. Record all observed OLT and PC faults; send complete session folder for diagnosis.

IMPORTANT: State PASS means `Phase State = working`, not product qualification. Optical data is record-only pending specification. Ping not included.
