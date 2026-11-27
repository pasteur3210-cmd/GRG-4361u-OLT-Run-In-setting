# Factory SOP — V3600GS Connect V1.0.21
1. Connect V3600GS Console USB and verify `USB-Enhanced-SERIAL` COM, close Tera Term.
2. Set PC local timezone; plug into AC power. Set Windows 11 Power & battery > Screen, sleep & hibernate to keep system awake during the run, disable scheduled automatic restart, and verify USB/Network stability.
3. Launch EXE; select Expected DUT Count (1–16), then Auto Scan and Verify Mapping against the fixed IP pool 192.168.2.121–136. Only proceed when every required DUT is a unique MATCH.
4. Perform Single Check and verify ONU IDs, GPON SN, Phase State, Ping Loss and Alive Time including days (e.g. `1 00:04:03`).
5. Set Loop Interval and Duration (0 = until Stop). In the Live Ping Monitor tab set Ping Interval (default 1 sec, range 0.5–60). Return to the first tab and start run. Close any open `ONU_Master_Record.xlsx` so the running EXE can replace it.
6. Open the Live Ping Monitor tab to confirm realtime status, cumulative Failed/Loss % and **Max Consecutive Loss** (does not reset on recovery). After 2–3 ONU cycles, confirm `ONU_Master_Record.xlsx` and `cycles.jsonl` are growing. The live CSV is independent of Excel.
7. For night run, keep OLT and test PC powered; monitor externally for unexpected reboot or disconnect.
8. Stop in morning using either tab. Verify `status.txt`, `cycles.jsonl`, `ONU_Master_Record.xlsx`, `raw_cli/`, `continuous_ping.csv`, `continuous_ping_events.csv` and `continuous_ping_summary.csv`. No new per-cycle `raw_ping` files are created.
9. If Excel is damaged/locked, preserve all `cycles.jsonl` and raw logs; do not delete run folder. Rebuild with the provided `rebuild_excel.py` in the development environment.


## 10–16 ONU paging validation before factory rollout
1. Map all DUT IPs and confirm the ONU roster and GPON SN for every connected DUT.
2. Run Single Check before Loop Check. Open the `raw_cli/Loop_0001_*.log` trio and confirm every working ONU ID is present in State, Time-stamp, and Optical output.
3. If a cycle shows INCOMPLETE/ERROR, check the `cycles.jsonl` `error` field, preserve all raw CLI files, and do not treat the cycle as PASS. Examples include a CLI pager timeout, missing timestamp ONU, or missing optical measurements.
4. A known offline ONU is a DUT FAIL even when no optical values are available. The next cycle should continue unless Serial synchronization has been lost.
5. For a new 10–16 DUT setup, run a short monitored check before the overnight run; synthetic 16/20-unit regression does not guarantee that the OLT firmware uses one of the tested pager formats.

## Continuous Ping acceptance check
1. On tab **Live Ping Monitor**, `Test Result` is independent of current `Status`.
2. Before 8h a healthy DUT reads MONITORING, and after passing the first 8h cumulative-loss checkpoint it reads PASS.
3. At the 6th consecutive timeout it becomes FAIL immediately; after recovery Status may display ONLINE but Test Result remains FAIL (red row).
4. At 8h cumulative Failed >50 is FAIL; at 16h >100; at 24h >150; repeat every 8h with an additional 50 allowance. A failing earlier checkpoint remains failing forever in the session.
5. Confirm `continuous_ping_checkpoints.csv` and `continuous_ping_summary.csv` as well as `continuous_ping_events.csv` after stopping. `Allowed Loss` on GUI shows the **last completed** checkpoint allowance (0 before first 8h).
6. To force-test the immediate rule on two DUTs, disconnect one unit briefly until it records 6+ consecutive timeouts, then reconnect. The other unit must remain independent and Excel/OLT checks must continue.

## V1.0.19 Pre-run static IP automatic detection
1. Prepare the DUTs with fixed IPs selected from 192.168.2.121–192.168.2.136 (DHCP not used). Ensure the test PC is on the same Layer-2 LAN.
2. Select **Expected DUT Count**, from 1 to 16. DUT IPs need not be sequential.
3. Click **Auto Scan & Verify IP / MAC / GPON SN**. Confirm each DUT IP maps to a unique OLT ONU ID and GPON SN, using the existing ARP MAC matching rules.
4. If `MAPPING FAILED / INCOMPLETE`, do not start: verify the expected count, ONU state, static IP conflicts, cables and failed Ping. An unreachable expected DUT must not be omitted from the test.
5. Start Run-in after verification. The second **Live Ping Monitor** tab shares the current session; it does not open a separate Serial connection or modify the Excel directly.
6. In Excel `04_Event_Log`, check timestamp-change / PON reconnect history separately from current `working` state. OLT/PC clocks can differ; do not interpret their raw timestamps as a unified clock.
7. Before the first 8-hour checkpoint, `Allowed Loss` shows `50 (8h PENDING)`; cumulative checkpoint FAIL is evaluated at elapsed 8/16/24 hours, while ≥6 consecutive losses fail immediately.

## V1.0.19.1: Short scheduled Run-in result
- A test set for 1 hour must keep Continuous Ping running for the full configured 1 hour, even when the last ONU CLI cycle (for example the 12th 5-minute check) completes earlier.
- At successful scheduled completion a row without any FAIL trigger may show `PASS`, but confirm `Final Assessment=SHORT_RUN_UNDER_8H` in `continuous_ping_summary.csv`; it does **not** constitute 8-hour loss-limit validation.
- If the user presses Stop early, MONITORING remains unless an actual FAIL was already latched.
- The 8/16/24h checkpoints are still required for the cumulative packet-loss rule.
- Run-in status and per-IP final results are in `status.txt` and `continuous_ping_summary.csv` beside the normal Session records.

## V1.0.21 Production Information
1. On the first tab, enter **PO** (optional, initially blank), **Model Name** (defaults to `GRG-4361`; editable but cannot be blank), and **Operator** (optional, initially blank).
2. Complete mapping before clicking Start. Production Information is captured at the moment Start is pressed and cannot be modified while the test is running.
3. To verify traceability, open the run folder `production_info.json`, `ONU_Master_Record.xlsx` sheets `01_Loop_Summary` and `06_Run_Metadata`, and `continuous_ping_summary.csv`: all must contain identical PO / Model / Operator values.
4. For the next batch, change the Production Information and perform a new mapping; previous Session files remain untouched.
5. Navigate via the single large tab row: **dark blue + white text = active**, **light gray = inactive**. Switching between tabs does not start/stop any test.
6. The 8h and 16h acceptance checkpoints still require corresponding wall-clock field tests; do not certify those conditions using a 1-hour run.


## V1.0.21 GUI restyling (behavior unchanged)
Use the two pale-color tabs (blue OLT, mint Ping) and the read-only summary at top of OLT screen. All operations, output files and validation rules are the same as V1.0.20. On Windows displays with nondefault scaling verify no controls are clipped before production use.

## V1.0.22 shorter workstation screens
Use the scrollbar at the right side of the OLT page to reach RESULT / STATUS and Execution Log if the Windows taskbar or display scaling limits the viewport. Switching to Live Ping Monitor does not interrupt the test. Check the HD icon on the Windows EXE file, titlebar and taskbar after building with GitHub Actions.


## V1.0.23 CT icon update
The earlier HD icon is replaced by the approved dark-grey CT monogram on a white background, file `CT.ico`, used by PyInstaller for the EXE and by Tk for the titlebar/taskbar. All V1.0.22 workarea scrolling and existing test functions are retained unchanged.


## V1.0.23.1 GitHub build dependency hotfix
GitHub Actions now installs Pillow==11.3.0 from requirements-build.txt and verifies its import before unit tests. Previous CT icon, scrolled OLT GUI and all testing functions are unchanged. GitHub Windows EXE build still needs an actual workflow run.


## V1.0.23.3 Mapping Display
After Auto Scan, check Expected/Discovered/MATCH values. Scroll the results table to inspect all 10-16 devices. A table scroll bar does not change mapping or Run-in decisions.
