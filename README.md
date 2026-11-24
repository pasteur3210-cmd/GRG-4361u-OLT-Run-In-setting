# V3600GS Connect V1.0.16
Windows 11 direct Serial tool; no Tera Term required while running the compiled EXE. Auto COM selection, 115200 8N1, login, ONU state/time-stamp/optical queries, 4-packet multi-IP parallel Ping, per-run Excel accumulation.

## Build
Upload the **contents** of the GitHub ZIP to repository root, including `.github/workflows/build.yml`; run Build V3600GS Connect via GitHub Actions. Install Tera Term only for separate troubleshooting; close its COM session before starting the tool.

## Mapping / Run
Put DUT IPs (same LAN), Verify IP/MAC/GPON SN Mapping. The ARP MAC must match LAN MAC directly or LAN MAC + 1 (full 48-bit subtraction), uniquely matching the GPON SN last six hex digits. Set Single or Loop Check; default Ping 4 packets, 2 or more lost is FAIL. Record appears beside EXE under `records/Run_.../`.

## Night Run precautions
Do not open the active Excel during a run. Confirm Windows automatic Sleep and scheduled restart are disabled, the OLT/USB adapter remains powered, and local Windows timezone is correct before starting. Metadata records the first cycle UTC offset and JSONL stores per-cycle offsets. Use `cycles.jsonl` for recovery if Excel cannot be updated.

## Verification boundary
83+ automated unit/regression checks pass on the current development runtime; physical overnight stability, GitHub Windows Actions compile and US English Windows deployment remain field-gated.
