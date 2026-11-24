# V3600GS Connect V1.0.11 — ONU Single Check + Excel

## Scope
Built on V1.0.8 direct Serial connection tested on real V3600GS. Adds two read-only CLI commands after login:

- `show onu time-stamp`
- `show onu optical-info all`

Button **Login + ONU Check Once (Excel)** connects COM, auto-logins, executes both commands, saves the raw CLI output and an `.xlsx` file, then releases COM. The former **Connect & Auto Login** button is retained as a separate smoke test.

Connection: auto-detect USB-Enhanced-SERIAL COM, 115200 / 8N1 / no flow control, account/enable credentials as agreed, GPON interface fixed 0/1.

## Output
EXE-directory/records/YYYYMMDD_HHMMSS_microseconds/

- `execution.log` (stage and errors)
- `onu_time_stamp.log`
- `onu_optical_info.log`
- `ONU_Check_Record.xlsx` (01_Loop_Summary, 02_ONU_Detail, 03_Field_Notes)
- `status.txt`

**This is a single-check first delivery**. The Excel layout dynamically creates columns for the ONU IDs actually returned (including 10–16 or more), one row per cycle. Multiple cycles passed to the exporter share stable ONU-ID columns, and missing devices do not cause shifts. Recurring loop scheduling and parallel multi-IP Ping are NOT YET implemented; they are planned follow-on functions. The current `Status` is `NOT VERIFIED` because these two CLI commands do not prove online/offline. `N/A` values remain `N/A`.

## GitHub Actions
Upload **all the files** from the GitHub ZIP to the repository root, including `.github/workflows/build.yml`. Run the `Build V3600GS Connect` workflow, download the `V3600GS_Connect_V1.0.11` artifact, extract `V3600GS_Connect_V1.0.11.exe`. No Python installation is needed on the factory PC; close Tera Term first.

## Verification
Run the same commands as workflow:

```
python -m compileall -q main.py onu_parser.py excel_record.py tests
python -m unittest discover -s tests -v
```

The tests cover the supplied actual device logs, including `1/12026:...N/AN/A...` merged columns, two CLI commands, dynamic 2/16/20 ONU Excel structure, login sequence, and version naming. GitHub Windows PyInstaller build and V3600GS real CLI data acquisition need validation on the user's computer.


V1.0.11: 修復原始 Serial ANSI ESC[nC、CR 的 time-stamp 欄位解析。
