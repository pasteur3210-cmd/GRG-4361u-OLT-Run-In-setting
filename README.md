# V3600GS Connect V1.0.1 (Phase 1)

Windows 11 standalone EXE source package. Tera Term 4.x legacy-oriented connection and CLI initialization only; **no ONU monitoring or Ping in this version**.

## Prerequisites on test PC
- Windows 11, USB serial driver, connected V3600GS console.
- Installed Tera Term with `ttermpro.exe` and `ttpmacro.exe` (expected: `C:\Program Files (x86)\teraterm\`).
- **No Python required** on the test PC when using GitHub Actions-built EXE.

## Build on GitHub
1. Create a GitHub repository; upload the contents of this ZIP **at repository root**, including hidden `.github/workflows/build.yml`.
2. Use Actions > Build V3600GS Connect > Run workflow (or push to `main`).
3. Open successful run > Artifacts > `V3600GS_Connect_V1.0.1` > download and unzip the EXE.
4. Execute `V3600GS_Connect_V1.0.1.exe` on the Windows test PC.

## Manual smoke test (V3600GS hardware required)
1. Close Tera Term if it already uses the target COM port.
2. Launch EXE; ensure `ttpmacro.exe` path detected, or use Browse.
3. Click **Refresh COM**; verify `USB-Enhanced-SERIAL` selected. If multiple candidates appear, manually choose the correct COM.
4. Click **Connect & Auto Login**. New Tera Term window should open at 115200 baud, not 9600.
5. Expected final CLI prompt: `gpon-olt(config-pon-0/1)#`.
6. EXE status should show `READY|gpon-olt(config-pon-0/1)#`.
7. On failure, collect `records` under `%LOCALAPPDATA%\V3600GS_Connect\records` (remove credentials if any command-echo is present).

## Fixed phase-1 settings
- Serial: 115200, expected 8-N-1, no flow control. The launch command passes `/C=N /BAUD=115200`; *check 8-N-1 and no flow control using Setup > Serial port on this older Tera Term*. Some older versions may not accept the newer extra serial CLI flags.
- Login user: `qa123`; Login password: locally configured; Enable password: locally configured. This test version uses the user-provided test credential string in the generated TTL; **do not publish the repository** if passwords should not be disclosed.
- `enable`, `config terminal`, `interface gpon 0/1`.
- Waits for each expected CLI prompt with a timeout; checks status automatically.

## Notes and limitations
- This program automates **your locally installed Tera Term**, not a bundled Tera Term executable.
- A Tera Term window being open is not proof of successful login; GUI READY and final CLI prompt must both be checked.
- The 2011-era build cannot be executed here; TTL syntax/hardware compatibility requires on-site validation.
- Tera Term owns the COM port. Do not separately open the same port in Python or another Tera Term session.
- Username/password are currently built into source by request. Generated macro is deleted when the runner exits; Windows file backup/antivirus or log echo can still retain sensitive material. Treat local test artifacts appropriately.
