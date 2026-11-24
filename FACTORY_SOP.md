# Factory SOP — V3600GS Connect V1.0.16
1. Connect V3600GS Console USB and verify `USB-Enhanced-SERIAL` COM, close Tera Term.
2. Set PC local timezone; plug into AC power. Set Windows 11 Power & battery > Screen, sleep & hibernate to keep system awake during the run, disable scheduled automatic restart, and verify USB/Network stability.
3. Launch EXE, enter DUT IPs on same L2 network; click Verify Mapping. Only proceed on unique MATCH rows.
4. Perform Single Check and verify ONU IDs, GPON SN, Phase State, Ping Loss and Alive Time including days (e.g. `1 00:04:03`).
5. Set Loop Interval and Duration (0 = until Stop), start run. Close any open `ONU_Master_Record.xlsx` so the running EXE can replace it.
6. Verify after 2–3 cycles that one `Run_.../ONU_Master_Record.xlsx` has cumulative rows and `cycles.jsonl` is growing.
7. For night run, keep OLT and test PC powered; monitor externally for unexpected reboot or disconnect.
8. Stop in morning; ensure `status.txt`, `cycles.jsonl`, Excel, raw_cli/raw_ping are present. Check cycle count, elapsed test time, failed cycles, missing loops and any save errors.
9. If Excel is damaged/locked, preserve all `cycles.jsonl` and raw logs; do not delete run folder. Rebuild with the provided `rebuild_excel.py` in the development environment.
