# V3600GS Connect V1.0.12 — ONU Run-in

Windows 11 / EXE with direct serial (no Tera Term Macro, no local Python required).

## Features
- Auto-discover USB-Enhanced-SERIAL COM device. 115200 baud, 8N1, no flow control.
- Four-stage OLT login (known compatible V1.0.8 direct-serial sequence), fixed GPON 0/1.
- Three commands per cycle: `show onu state`, `show onu time-stamp`, `show onu optical-info all`.
- `Phase State=working` -> ONU PASS; any other observed phase -> FAIL; no state -> UNKNOWN/ERROR, never PASS.
- ONU GPON SN, Admin/OMCC/Phase, Channel, timestamps and optical information recorded.
- Single Check and Loop Check (interval in minutes, duration in hours; 0=until Stop).
- One session folder per Start; one `ONU_Master_Record.xlsx` updated after every cycle.
- Dynamic ONU IDs (including sparse IDs and 10–16+ devices), fixed by ID across all cycles.
- Raw CLI per cycle; `cycles.jsonl` durable recovery journal; execution.log, status.txt, events.jsonl.
- Excel contains `01_Loop_Summary` (one row per cycle), `02_ONU_Detail`, `03_Field_Notes`, `04_Event_Log`.
- Session tries to reconnect on Serial failure in subsequent cycle, never reuses prior cycle's values.

## Workflow / scope
1. Close Tera Term if it uses the selected COM.
2. Start EXE, choose COM, Single or Loop.
3. For Loop set interval (e.g. 5 minutes), duration (e.g. 72 hours; 0 until manually stopped).
4. Start ONU Check. First cycle runs immediately. Monitor completed cycles and status.
5. Use Stop to end the run. Outputs remain beside the EXE in `records/Run_.../`.
6. Open Records Folder / Open Excel once the run ends.

This version **does not implement Ping yet**; Ping is a separate upcoming feature.
An ONU PASS means *observed working phase*, not an optical compliance pass.

## Build
Upload all GitHub ZIP contents to repository root, including `.github/workflows/build.yml`.
In Actions select `Build V3600GS Connect` -> `Run workflow`. Download
`V3600GS_Connect_V1.0.12` artifact containing an EXE. It embeds pyserial.

## Notes / safety
- Source and bundled program contain configured factory credentials; restrict repository access.
- Duration counts from start of session, not total on-test-time after retries. No overlapping cycles.
- Every cycle is first saved in `cycles.jsonl` and then Excel is safely rewritten.
- Close Excel during run: Windows may lock it, preventing updates. JSONL remains recoverable.
- If Excel is locked, close Excel and restart the app for a fresh session; use the included
  `rebuild_excel.py` (Python development environment) to rebuild an older session from JSONL.
- Host clock is used for Check Time. Ensure PC time is correct.

## Verification limits
Automated tests validate parsing, simulated Serial, Excel XML, state transitions, retry,
Stop and packaging. GitHub Windows build and physical 16-ONU / long-duration run require user-side testing.
