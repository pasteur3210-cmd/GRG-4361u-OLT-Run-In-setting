> **V1.0.24 release note:** At session end, the `07_Session_Final` tab is selected automatically on opening the workbook. Per-cycle results in `01_Loop_Summary` are historical snapshots, not the authoritative final Run-in verdict. `04_Event_Log` contains finalized Continuous Ping trigger/recovery events.

# V3600GS Connect V1.0.21
Windows 11 direct Serial tool; no Tera Term required while running the compiled EXE. Auto COM selection, 115200 8N1, login, ONU state/time-stamp/optical queries, continuous multi-IP independent Ping, per-run Excel accumulation.

## Build
Upload the **contents** of the GitHub ZIP to repository root, including `.github/workflows/build.yml`; run Build V3600GS Connect via GitHub Actions. Install Tera Term only for separate troubleshooting; close its COM session before starting the tool.

## Mapping / Run
Select Expected DUT Count (1–16); Auto Scan checks the fixed static IP pool 192.168.2.121–192.168.2.136 (sparse IPs supported), then verifies IP/MAC/GPON SN Mapping. No DHCP or operator IP text entry. The ARP MAC must match LAN MAC directly or LAN MAC + 1 (full 48-bit subtraction), uniquely matching the GPON SN last six hex digits. Set Single or Loop Check; pre-run verification performs one Ping for ARP cache; after Start, Continuous Ping sends one probe per configured interval (default 1 second). Any timeout is recorded; no 4-packet threshold. Record appears beside EXE under `records/Run_.../`.

## Night Run precautions
Do not open the active Excel during a run. Confirm Windows automatic Sleep and scheduled restart are disabled, the OLT/USB adapter remains powered, and local Windows timezone is correct before starting. Metadata records the first cycle UTC offset and JSONL stores per-cycle offsets. Use `cycles.jsonl` for recovery if Excel cannot be updated.

## Verification boundary
139 automated unit/regression checks pass on the current development runtime; physical overnight stability, GitHub Windows Actions compile and US English Windows deployment remain field-gated.

## V1.0.19 — Continuous Ping and two-page GUI

* **Tab 1: OLT & IP Setup / ONU Check** — COM selection, fixed Serial login, IP/MAC/GPON SN verification, Single/Loop settings, Start/Stop, Excel and CLI record access.
* **Tab 2: Live Ping Monitor** — live status, RTT, successes, failures, loss %, last success/failure timestamps and **Max Consecutive Loss**. This is the historical maximum and **never resets when Ping recovers**. The Live Ping tab shares the same Run-in session and Stop control; it cannot open the COM port.
* Pre-run `Verify Mapping` retains a **single Ping probe per DUT** to populate the local ARP table. It is separate from the live monitor, not the old four-packet cycle check.
* When Run-in starts, one parallel Continuous Ping worker per mapped IP starts and keeps probing (default 1.0 seconds, configurable 0.5–60 seconds). Each probe appends to `continuous_ping.csv`; completed failure streaks append to `continuous_ping_events.csv`; end-of-session statistics are saved to `continuous_ping_summary.csv`.
* ONU checks continue at configured intervals, querying three OLT commands over the sole Serial owner. Each cycle takes a **point-in-time** snapshot of accumulated Ping totals, writes `cycles.jsonl`, then updates the existing `ONU_Master_Record.xlsx` using a **single Excel writer**. Only the existing `IP PING Result` and `PING Loss` fields are used for Ping; `PING Loss` now means cumulative `failed/sent (percentage)`, not `lost/4`.
* A current isolated `TIMEOUT` does NOT itself fail the Run-in. Max Consecutive Loss >=6 immediately latches FAIL; at 8/16/24/... hours accumulated losses must be <=50/100/150/... . Prior checkpoint FAIL never clears, even after ONLINE recovery. Before the first 8h checkpoint, nonfailed units show MONITORING; a passed checkpoint displays PASS. `INITIALIZING` and Ping command errors remain distinct from DUT acceptance decisions.
* The program does not continuously rewrite the Excel file for each Ping; monitoring CSV writers never open the workbook. For 16 DUTs at 1 probe/sec, plan enough disk capacity for millions of rows over a long run. Do not open the active Excel for editing during the run.
* Status at test end is `COMPLETED`, `STOPPED BY USER`, or the recorded save error; a manually stopped Run-in is not automatically a DUT FAIL.

## Compatibility / limitation

Run on Windows 11 with native Ping and direct Serial. GitHub Actions compiles using Python 3.11 and PyInstaller. This release builds on the 477-cycle V1.0.16 Night Run and 31-cycle V1.0.18 two-DUT field observations, with local regression tests; the compiled V1.0.21 EXE and sustained 16-IP live network monitoring still require Windows/OLT validation.


## Multi-page ONU CLI safety (V1.0.19 updated build)
Three commands (`show onu state`, `show onu time-stamp`, `show onu optical-info all`) share pagination with split/ANSI pager handling. A complete GPON CLI prompt is required; incomplete screens time out rather than being accepted. State/Time-stamp IDs must reconcile, and each `working` ONU must have the required Optical Rx, Tx, voltage, current, temperature values. Incomplete/malformed results flag the affected cycle rather than silently passing. First 10–16 DUT real-hardware validation remains required.

## V1.0.19 — Continuous Ping acceptance (scheme A)
* Independent judgment per DUT; historical `Max Consecutive Loss >= 6` triggers FAIL immediately.
* Evaluate cumulative number of timeouts at exact elapsed-session checkpoints: 8h 50, 16h 100, 24h 150, then +50 per 8h. Greater than limit is FAIL; equal passes. Tests are NOT independent 8h bins.
* Checkpoints use each worker's monotonic elapsed time; wall-clock/NTP adjustments do not influence their schedule. A new probe that completes after a boundary is excluded from the previous checkpoint.
* A FAIL latches until a **new Run-in session**. Current connectivity (`ONLINE`/`TIMEOUT`) is a separate field; an ONLINE unit may remain Test Result FAIL.
* GUI Live Ping rows are red for FAIL, green for passed checkpoints, yellow for not-yet-completed first checkpoint, and separate from communication status.
* CSV audit: `continuous_ping.csv` (per sample + decision), `continuous_ping_checkpoints.csv` (8h checkpoint outcomes), `continuous_ping_events.csv` (recovery and threshold failures), `continuous_ping_summary.csv` (final latched status, reason, time, totals).
* ONU `cycles.jsonl` contains each DUT's current test_result and fail_reason. Existing Excel Ping fields remain the same two columns. No additional 4-packet ONU-cycle Ping has been reintroduced.

## V1.0.19 factory changes
* Exactly two prominently styled tabs on one navigation row; switching tabs does not restart the test.
* The only pre-run operator selection is Expected DUT Count (1–16) and COM port; scan all reserved STATIC IPs 192.168.2.121–136, including nonadjacent active DUTs. ARP MAC↔GPON SN mapping uses strict DIRECT/OFFSET_MINUS_1 rules. Count mismatch, unreachable expected DUT, duplicate/ambiguous MAC or unexpected responsive IP blocks Run-in. Do not rely on ping scanning alone.
* `04_Event_Log` compares last register/deregister values across cycles even when Phase State remains working; adds `PON RECONNECT / TIMESTAMP CHANGE` and preserves original OLT timestamp values. `events.jsonl` records the same event with PC observation time. OLT and PC clocks may not be synchronized.
* Before first 8-hour checkpoint GUI shows `50 (8h PENDING)` instead of `0 (0h)`; historical FAIL rule unchanged.
* The 8h/16h accumulation in V1.0.19 remains awaiting longer real DUT validation; these limits were regression-tested with simulated clocks.

### V1.0.19.1 timed-session hotfix
A one-hour scheduled run now waits the full hour before ending Continuous Ping. A clean short run shows PASS upon completion with `SHORT_RUN_UNDER_8H` in `continuous_ping_summary.csv`; this is distinct from passing the 8-hour/16-hour cumulative loss checkpoints. Early manual Stop does not automatically convert MONITORING into PASS. See CHANGELOG in the Complete Package.

## V1.0.21 — Production identification and high-contrast tabs
* Three editable fields appear on **OLT & IP Setup / ONU Check** below the Serial/COM setup: **PO** (blank), **Model Name** (`GRG-4361` by default, can edit), and **Operator** (blank). Model Name must not be empty. Each field is limited to 100 characters without control characters.
* The three values are captured and frozen at Start; they do not change when the operator edits the form after completion. They are persisted in `production_info.json`, the `production_info` field of every `cycles.jsonl` entry and `status.txt`, the first Excel sheet (three appended columns), Excel sheet `06_Run_Metadata`, and `continuous_ping_summary.csv` (three appended columns).
* Rebuilding Excel from the original `cycles.jsonl` and session metadata retains those fields.
* Exactly **one** top navigation group. Native Notebook tabs are hidden. The selected navigation button is **dark blue with white bold text**; inactive button is **light gray with dark text**, including on Windows themes that ignore ttk tab backgrounds.
* V1.0.19.1's short-session completion, live Ping acceptance thresholds, PON reconnect event recording, fixed-IP discovery and multi-page CLI protection are unchanged. An overnight/8h/16h physical DUT validation is not replaced by unit tests.


## V1.0.21 GUI restyling (behavior unchanged)
Use the two pale-color tabs (blue OLT, mint Ping) and the read-only summary at top of OLT screen. All operations, output files and validation rules are the same as V1.0.20. On Windows displays with nondefault scaling verify no controls are clipped before production use.

## V1.0.22 Display / icon
The OLT & IP Setup / ONU Check tab scrolls vertically when the content is taller than the viewport; use the right-hand scrollbar or mouse wheel. `HD.ico` is the user-supplied icon included in the GitHub package; the Windows GitHub Actions workflow embeds it into the executable and bundles it for the Tk window titlebar and taskbar.


## V1.0.23 CT icon update
The earlier HD icon is replaced by the approved dark-grey CT monogram on a white background, file `CT.ico`, used by PyInstaller for the EXE and by Tk for the titlebar/taskbar. All V1.0.22 workarea scrolling and existing test functions are retained unchanged.


## V1.0.23.1 GitHub build dependency hotfix
GitHub Actions now installs Pillow==11.3.0 from requirements-build.txt and verifies its import before unit tests. Previous CT icon, scrolled OLT GUI and all testing functions are unchanged. GitHub Windows EXE build still needs an actual workflow run.


## V1.0.23.3
Mapping table is vertically/horizontally scrollable for 1-16 DUTs. Expected/Discovered/MATCH counters appear above the table. All runtime functions unchanged.
