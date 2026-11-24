# V3600GS Connect V1.0.4 – 實機 SOP

1. 關閉所有 Tera Term 視窗，確保 COM 未被占用。確認 USB-Enhanced-SERIAL 已連接並讓 OLT 開機。
2. 開啟 EXE，檢查自動辨識的 COM，按 Connect & Auto Login 一次。
3. 確認 Tera Term 115200 / 8N1 / None；成功應進入 `gpon-olt(config-pon-0/1)#`。
4. 若失敗，在 GUI 按 Open Records Folder；將 `execution.log`、`status.txt`、`stage.txt` 與 `serial.log`（有才提供）壓縮回傳。
5. `FAIL|SERIAL_CONNECT|LINK_STATE=0` 代表 Macro 沒有連結 Tera Term；`=1` 代表 Macro 已連結但 Serial 未建立；`=2` 理論不應進入該 FAIL。`FAIL|LOGIN_PROMPT_TIMEOUT|SERIAL_CONNECTED` 表示連線成立但 OLT 未回應 Enter。
6. 若需提供 `connect.ttl`，請先移除檔案中的登入密碼。
