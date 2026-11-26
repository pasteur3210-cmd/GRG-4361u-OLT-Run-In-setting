# Factory SOP — V3600GS Connect V1.0.17
1. Connect V3600GS Console USB and verify `USB-Enhanced-SERIAL` COM, close Tera Term.
2. Set PC local timezone; plug into AC power. Set Windows 11 Power & battery > Screen, sleep & hibernate to keep system awake during the run, disable scheduled automatic restart, and verify USB/Network stability.
3. Launch EXE, enter DUT IPs on same L2 network; click Verify Mapping. Only proceed on unique MATCH rows.
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
