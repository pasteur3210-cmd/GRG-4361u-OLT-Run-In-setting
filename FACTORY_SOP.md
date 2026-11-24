# V3600GS Connect V1.0.7 — 測試 SOP
1. OLT 已上電，連接 USB-Enhanced-SERIAL，確認 Device Manager 存在對應 COM。
2. 關閉使用該 COM 的其他 Tera Term 視窗。
3. 開啟 EXE，確認偵測到 COM；按 `Connect & Auto Login` 一次。
4. Tera Term 應顯示 `COMx:115200baud`；等待 Macro 自動執行。成功條件 `gpon-olt(config-pon-0/1)#` 且 GUI 顯示 `READY`。
5. 若失敗，將 EXE 同目錄 `records` 中本次資料夾與 execution.log 打包。請勿反覆按 Connect。
6. TTL 內含固定登入帳號密碼；測試紀錄和 ZIP 必須存放在受控資料夾，不上傳公用儲存庫的 records。
