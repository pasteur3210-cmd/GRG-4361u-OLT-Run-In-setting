# FACTORY SOP — V3600GS Connect V1.0.15

1. Close Tera Term. Connect OLT console cable and local DUT LAN to the test PC.
2. Run EXE (no local Python needed). Select detected `USB-Enhanced-SERIAL` COM port; serial is 115200 / 8N1.
3. Paste IPv4 addresses **one per line**; verify no duplicates.
4. Click `Verify IP / MAC / GPON SN Mapping` and wait for table results. Check all IP, MAC, ONU ID, GPON SN, and MATCH status. A MAC/IP missing or suffix mismatching must be resolved before running; do not guess mapping.
5. Configure Single or Loop, Interval and Duration (`0` = until Stop), then click `Start ONU Check`.
6. Each complete cycle records three ONU commands and four Windows Ping packets per DUT. 0 lost PASS; 1 WARNING; 2+ FAIL.
7. A session writes to `records/Run_<timestamp>/ONU_Master_Record.xlsx` cumulatively, with `cycles.jsonl` journal, `mapping.json`, `raw_cli/` and `raw_ping/`.
8. Do not keep the Excel workbook open while testing. Use `Stop` to finish and retain completed cycles. New runs require fresh mapping verification.
9. If an error occurs, provide the entire `records/Mapping_...` or `Run_...` folder and GUI screenshot to engineering.

**Engineering warning:** A successful Ping/IP pairing depends on the Windows ARP MAC representing the actual DUT interface. These are DUT-side network checks, not proof of ONU optical compliance.

## V1.0.15 Mapping check
- Before starting, enter the actual IPs and select Verify Mapping.
- GUI shows observed **ARP MAC**, verified **LAN MAC**, **Match Type** (DIRECT or OFFSET_MINUS_1), ONU ID and GPON SN.
- Real example: 192.168.2.121 WAN 3872C0112256 -> LAN 3872C0112255 -> ONU 1; 192.168.2.122 WAN 1C6499ABE12A -> LAN 1C6499ABE129 -> ONU 2.
- Mapping FAIL blocks Start; check IP/MAC/L2 topology. No manual force-PASS.
