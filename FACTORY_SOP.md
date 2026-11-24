# FACTORY SOP — V1.0.8

1. 關閉所有 Tera Term 視窗，以免占用 COM。
2. USB Console 連接 OLT，確認裝置管理員出現 USB-Enhanced-SERIAL。
3. 開啟 EXE，選擇適當 COM，按 Connect & Auto Login。
4. 觀察 GUI 每個登入階段；正確結果為 LOGIN READY。
5. 若 FAIL，點 Open Records Folder，打包 execution.log、status.txt。
6. 測試機更換時須重新確認 COM。
