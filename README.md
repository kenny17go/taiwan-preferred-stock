# 台灣上市櫃特別股分析 V1.1

V1.1 延續 V1 的 GitHub Pages + GitHub Actions 架構，並把特別股資料移到 `data/preferred_stocks.json`，方便後續持續維護。

## V1.1 重點

- 載入 FindBillion「特別股詳細列表」目前列示的 29 檔特別股。
- 保留市場總覽、完整列表、排行榜、特別股 PK、重設/IRR 試算、贖回日曆、觀察清單。
- 重設試算器的 TWD IRS 不再人工輸入，直接讀取 `data/irs.json`。
- 已核對的重設公式會以 `TWD IRS 7Y + X.XXXX%` 顯示並用最新 IRS 即時計算。
- 未取得可核對契約來源的標的一律顯示「待核對」，不反推或猜測固定加碼利差。
- FindBillion 的「預估不收回重設利率 / 股息 / 殖利率」另保留作為市場資料參考。

## GitHub Pages 更新方式

若你已經有 V1 在 GitHub Pages 上運作，V1.1 最少只需要：

1. 以本版 `index.html` 覆蓋 repository 根目錄的 `index.html`。
2. 把 `data/preferred_stocks.json` 上傳到既有 `data` 資料夾。
3. 原本 `data/irs.json`、`scripts/update_irs.py` 與 `.github/workflows/update-irs.yml` 保留即可。

完整 ZIP 也包含原本 IRS 自動更新檔案，可用於全新部署。

## 資料註記

市場資料基準：FindBillion 特別股詳細列表（頁面標示最後更新 2026-08-08）。

本網站僅供研究與資料整理，不構成投資建議。特別股發行條件、重設公式、贖回條件應以發行公司公開說明書、重大訊息與交易所公告為準。
