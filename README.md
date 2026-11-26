# V3600GS Connect V1.0.17
Windows 11 direct Serial tool; no Tera Term required while running the compiled EXE. Auto COM selection, 115200 8N1, login, ONU state/time-stamp/optical queries, continuous multi-IP independent Ping, per-run Excel accumulation.

## Build
Upload the **contents** of the GitHub ZIP to repository root, including `.github/workflows/build.yml`; run Build V3600GS Connect via GitHub Actions. Install Tera Term only for separate troubleshooting; close its COM session before starting the tool.

## Mapping / Run
Put DUT IPs (same LAN), Verify IP/MAC/GPON SN Mapping. The ARP MAC must match LAN MAC directly or LAN MAC + 1 (full 48-bit subtraction), uniquely matching the GPON SN last six hex digits. Set Single or Loop Check; pre-run verification performs one Ping for ARP cache; after Start, Continuous Ping sends one probe per configured interval (default 1 second). Any timeout is recorded; no 4-packet threshold. Record appears beside EXE under `records/Run_.../`.

## Night Run precautions
Do not open the active Excel during a run. Confirm Windows automatic Sleep and scheduled restart are disabled, the OLT/USB adapter remains powered, and local Windows timezone is correct before starting. Metadata records the first cycle UTC offset and JSONL stores per-cycle offsets. Use `cycles.jsonl` for recovery if Excel cannot be updated.

## Verification boundary
107 automated unit/regression checks pass on the current development runtime; physical overnight stability, GitHub Windows Actions compile and US English Windows deployment remain field-gated.

## V1.0.17 — Continuous Ping and two-page GUI

* **Tab 1: OLT & IP Setup / ONU Check** — COM selection, fixed Serial login, IP/MAC/GPON SN verification, Single/Loop settings, Start/Stop, Excel and CLI record access.
* **Tab 2: Live Ping Monitor** — live status, RTT, successes, failures, loss %, last success/failure timestamps and **Max Consecutive Loss**. This is the historical maximum and **never resets when Ping recovers**. The Live Ping tab shares the same Run-in session and Stop control; it cannot open the COM port.
* Pre-run `Verify Mapping` retains a **single Ping probe per DUT** to populate the local ARP table. It is separate from the live monitor, not the old four-packet cycle check.
* When Run-in starts, one parallel Continuous Ping worker per mapped IP starts and keeps probing (default 1.0 seconds, configurable 0.5–60 seconds). Each probe appends to `continuous_ping.csv`; completed failure streaks append to `continuous_ping_events.csv`; end-of-session statistics are saved to `continuous_ping_summary.csv`.
* ONU checks continue at configured intervals, querying three OLT commands over the sole Serial owner. Each cycle takes a **point-in-time** snapshot of accumulated Ping totals, writes `cycles.jsonl`, then updates the existing `ONU_Master_Record.xlsx` using a **single Excel writer**. Only the existing `IP PING Result` and `PING Loss` fields are used for Ping; `PING Loss` now means cumulative `failed/sent (percentage)`, not `lost/4`.
* A current Ping `TIMEOUT` may mark that cycle's overall result FAIL; even when Ping recovers before the next ONU check, the individual failure and its highest streak remain in the CSV/event log. `INITIALIZING`/Ping tool errors are not treated as PASS.
* The program does not continuously rewrite the Excel file for each Ping; monitoring CSV writers never open the workbook. For 16 DUTs at 1 probe/sec, plan enough disk capacity for millions of rows over a long run. Do not open the active Excel for editing during the run.
* Status at test end is `COMPLETED`, `STOPPED BY USER`, or the recorded save error; a manually stopped Run-in is not automatically a DUT FAIL.

## Compatibility / limitation

Run on Windows 11 with native Ping and direct Serial. GitHub Actions compiles using Python 3.11 and PyInstaller. This release was reviewed with the supplied **477-cycle V1.0.16 Night Run logs** and unit/integration test doubles; the compiled V1.0.17 EXE and sustained 16-IP live network monitoring still require Windows/OLT validation.


## Multi-page ONU CLI safety (V1.0.17 updated build)
Three commands (`show onu state`, `show onu time-stamp`, `show onu optical-info all`) share pagination with split/ANSI pager handling. A complete GPON CLI prompt is required; incomplete screens time out rather than being accepted. State/Time-stamp IDs must reconcile, and each `working` ONU must have the required Optical Rx, Tx, voltage, current, temperature values. Incomplete/malformed results flag the affected cycle rather than silently passing. First 10–16 DUT real-hardware validation remains required.
