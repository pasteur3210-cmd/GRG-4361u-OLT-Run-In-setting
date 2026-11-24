# V3600GS Connect V1.0.8 — Direct Serial

本版移除 Tera Term Macro 自動控制。GUI EXE 直接使用 pyserial 開啟 USB-Enhanced-SERIAL COM (115200/8N1)，完成 Login → Enable → config terminal → interface gpon 0/1。

**自動連線前必須關閉 Tera Term，因 COM Port 不可被兩個應用程式同時占用。** 人工操作時可關閉/完成 EXE 登入後，再自行開啟 Tera Term。

## 操作
1. 在 Windows 11 安裝 USB Console 驅動，連接 OLT。
2. 以 GitHub Actions 編譯 EXE；Windows 測試電腦不需要安裝 Python。
3. 將 EXE 放在可寫入資料夾（例如 Desktop 或 D:\Test），不要放在 Program Files。
4. 關閉 Tera Term，執行 EXE。選擇 USB-Enhanced-SERIAL，按 **Connect & Auto Login**。
5. 看到 **LOGIN READY | gpon-olt(config-pon-0/1)#** 代表完成這次連線與登入驗證。
6. 失敗時，將 EXE 同層 `records` 資料夾壓縮提供分析。

**重要限制**：本版只驗證 Login 到 GPON 0/1，不進行 ONU 查詢或 Ping；登入驗證後會釋放 Serial Port，不持有連線。後續 ONU 監測將使用長駐連線版。

本版沒有 Tera Term 視窗；原始訊息不記錄帳號密碼。固定測試密碼目前儲存在 EXE，僅用於專用測試環境。
