# V3600GS Connect V1.0.7

第一階段連線 / 自動登入驗證工具：Windows 11 EXE，測試電腦毋須 Python，但須安裝舊版 Tera Term。

## 關鍵修正
- 不再使用 `ttermpro.exe /C=3 /BAUD=115200 /M=...`（舊版不相容）。
- 由 `ttpmacro.exe` 載入 `connect.ttl`，TTL 執行 `connect '/C=3 /BAUD=115200'`。
- TTL 暫存於可寫入的 ASCII、無空白目錄（優先 `C:\Users\Public\V3600GS_Macro`）；完成/失敗紀錄同步到 EXE 旁的 `records`。
- 自動登入只在 Serial link 建立後繼續，依 Prompt 檢查 Login → enable → config terminal → interface gpon 0/1。
- 並不包含 ONU/Ping 功能。

## 使用
1. 上傳 GitHub ZIP 全部檔案，包含隱藏 `.github` 資料夾。
2. Actions → Build V3600GS Connect → Run workflow，下載 EXE。
3. 將 EXE 放在可寫入資料夾，不要放 Program Files。關閉其他 COM3 Tera Term 視窗。
4. Connect & Auto Login；如失敗，將 EXE 同層 `records` 資料夾壓縮回傳。

**驗證限制**：自動化單元測試不等同 Windows GitHub Actions 真實編譯或 V3600GS 實機登入成功。舊版 Tera Term 的 Macro/Serial 相容性仍待現場驗證。
