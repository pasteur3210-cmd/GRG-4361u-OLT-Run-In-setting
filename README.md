# V3600GS Connect V1.0.13 — ONU Run-in + IP Mapping + Parallel Ping

Windows 11 GUI, one EXE, no Python installation required at the factory.

## Verified architecture
- Direct Serial COM (`USB-Enhanced-SERIAL`, 115200 / 8N1), **no Tera Term Macro**.
- Original four-stage login and three GPON 0/1 queries retained from V1.0.12.
- Pre-Run Verify matches **DUT IPv4 → Windows ARP MAC suffix (last 6 hex) → ONU GPON SN suffix**. Exact IP/MAC/GPON SN mapping must be unambiguous and cover every discovered ONU and configured IP before Start is enabled.
- Verify sends **one warmup Ping** per IP to populate ARP, and requires the IP to be reachable. If MAC cannot be obtained, check L2 topology / PC adapter / IP / DUT. Never assume the MAC of the default gateway is the DUT MAC.
- Every Single/Loop cycle executes `show onu state`, `show onu time-stamp`, `show onu optical-info all`, concurrently with **4 Ping packets per mapped IP**, in parallel across IPs (up to 16 concurrent workers).
- Ping criteria: lost 0/4 = PASS; 1/4 = WARNING; 2–4/4 = FAIL; unsuccessful Ping execution = ERROR. An observed ONU Phase State other than `working` = ONU FAIL. Missing/invalid data is never PASS.
- Dynamic ONU IDs, stable across cycles; never reassign mapping on ONU Offline/Recovery.
- Every Run Session has one `ONU_Master_Record.xlsx`, appended by full workbook regeneration from `cycles.jsonl`; one cycle row, no new Excel each cycle. JSONL is primary recovery record.
- Each ONU only adds **IP PING Result** / **PING Loss** in the main and detail Excel pages. Removed: Admin State, OMCC State, Data Flag, Alarm, Response. Raw CLI remains available.
- Separate `03_IP_Mapping`, `04_Event_Log` and `05_Field_Notes` sheets. `raw_ping` and `raw_cli` logs retained.
- Upon completion or stop, pre-run mapping is cleared; new Start requires verification again.

## GitHub Actions
Upload the **contents** of Clean ZIP to repository root, including `.github/workflows/build.yml`, and trigger `Build V3600GS Connect`. Artifact `V3600GS_Connect_V1.0.13` contains the EXE.

## Factory setup
1. Connect a Windows 11 PC to the local LAN of DUT IPs, and Serial to the V3600GS. Close Tera Term (it must not hold the COM port).
2. Start `V3600GS_Connect_V1.0.13.exe`. Confirm COM / Serial configuration.
3. Enter DUT IPv4 addresses (one per line) and click **Verify IP / MAC / GPON SN Mapping**.
4. Review table: only all `MATCH` enables Start; failures require network or DUT investigation. Verification stores logs under `records/Mapping_...`.
5. Choose Single Check or Loop, enter interval (min) and duration (hours; `0` until Stop), then click **Start ONU Check**.
6. Watch cycle count and state; Stop retains completed records. Excel under `records/Run_.../ONU_Master_Record.xlsx`.
7. Do **not** leave the workbook open in Excel during testing: Excel may lock the file. Rebuild from `cycles.jsonl` on a development PC using `rebuild_excel.py` if a save fails.

## Limits / cautions
- Pre-run MAC discovery uses Windows `arp -a <IP>`; it is valid only for DUTs reachable at layer 2 and only when the Ping-facing interface MAC actually shares the suffix with GPON SN. Unmatched units are blocked; no manual bypass.
- Device IP or COM changes invalidate verification.
- Optical values are **Record Only** until limits/units are approved.
- Windows EXE build and physical 10–16 DUT Ping run have **not** been exercised in the authoring environment. Python 3.13 offline unit tests do not substitute for actual Windows hardware validation.
