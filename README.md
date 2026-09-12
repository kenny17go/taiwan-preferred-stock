# 台灣特別股分析 V1.2

V1.2 新增「股價＋殖利率＋IRR/YTC」自動更新，並整合專屬 App Icon。

## 自動更新
- TWD IRS：沿用 `.github/workflows/update-irs.yml`
- 特別股市場資料：新增 `.github/workflows/update-market.yml`
- 平日台灣時間約 14:45 執行市場更新
- 股價來源：TWSE MIS，程式亦嘗試 TPEx market code 作為 fallback
- 殖利率：年股息 ÷ 最新股價
- IRR/YTC：只有在「未來可贖回日＋贖回價＋年股息」完整時自動估算；採年配息近似模型，不等同精確 XIRR

## Icon / PWA
- `icons/icon-192.png`
- `icons/icon-512.png`
- `icons/apple-touch-icon.png`
- `icons/favicon-64.png`
- `manifest.webmanifest`

iPhone Safari 加到主畫面後會使用新的台灣特別股圖示。

## 上傳 GitHub
把本資料夾內所有檔案覆蓋/新增至 repository 根目錄。請保留 `.github` 隱藏資料夾。
上傳後可到 Actions 手動執行一次 `Update preferred stock market data` 驗證。
