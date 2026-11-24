# V3600GS Connect V1.0.4

此版針對 V1.0.3 的 `FAIL|SERIAL_CONNECT` 增加實際 TTL 連線結果碼診斷與重新連線。Tera Term Macro 回傳 0 = 未連結、1 = 已連結但未連線、2 = 已連結且已連線。此階段仍需於實機驗證。

## 使用
1. 上傳本壓縮檔內容到 GitHub 根目錄，透過 Actions 編譯 EXE。
2. 在 Windows 11 關閉其他佔用 COM 的終端視窗後執行 EXE。
3. COM 自動識別，Serial 115200，按 Connect & Auto Login。
4. 失敗請用 Open Records Folder 取出 `execution.log`、每次執行資料夾的 `status.txt`、`stage.txt`、`connect.ttl` 和 `serial.log`（若有）。

**注意**：`connect.ttl` 含登入密碼，不要傳給不受信任的對象；如需分享，請先遮蔽密碼。
