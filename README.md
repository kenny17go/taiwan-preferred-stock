# 台灣特別股分析 V1 — GitHub Pages 版

## 部署到 GitHub Pages

1. 建立一個新的 GitHub repository，例如 `taiwan-preferred-stock`。
2. 把這個 ZIP 解壓縮後，將**全部檔案與資料夾**上傳到 repository 根目錄。
3. GitHub → **Settings → Pages**。
4. Source 選 **Deploy from a branch**。
5. Branch 選 `main`，Folder 選 `/ (root)`，按 **Save**。
6. 等 GitHub Pages 完成部署後即可用網址開啟。

## TWD IRS 自動更新

- 網站讀取 `data/irs.json`，不需要人工輸入。
- `.github/workflows/update-irs.yml` 會在週一至週五台灣時間約 18:20 自動執行。
- 也可以到 GitHub → **Actions → Update TWD IRS → Run workflow** 手動立即更新一次。
- 更新程式讀取 Cbonds：`IRS TWD (Quarterly Money vs 3M TAIBOR)`。
- 若 Cbonds 暫時無法抓取，程式會保留上一筆成功資料，並將狀態標示為 `stale`。

## 注意

Cbonds 的網站結構、授權或存取規則若變更，自動擷取可能需要同步調整。網站會顯示資料日期與更新狀態，避免把舊資料誤認成即時行情。
