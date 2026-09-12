# 台灣上市櫃特別股分析 V1.5

V1.5 重點：

- 29 檔特別股重新建立契約生命週期資料：發行日、首次可贖回日、可贖回狀態、重設週期、下一重設日。
- 可贖回日在未來：計算「贖回情境 IRR」。
- 已超過首次可贖回日且仍存續：標示「已進入可贖回期間」，不再硬指定一個假的下一贖回日，也不硬算單一 YTC。
- XIRR 的股息日期採除息日。未來除息日尚未公告時，以最近除息月份/日期做季節性估算，並標示為估算。
- 修正 `update_dividends.py`：支援 TWSE OpenAPI 的 `Code / Date / CashDividend` 欄位，並保留歷史已收錄除息事件，不再因預告 API 更新而清空。
- 市場價格、殖利率仍由 `update-market.yml` 自動更新；TWD IRS 繼續由原本 `update-irs.yml` 更新。

## 重要說明

「首次可贖回日」不等於之後每個重設日都只有那一天可贖回。若契約是「自首次可贖回日起，公司得隨時收回」，V1.5 會標成「已進入可贖回期間」。下一重設日只是利率重設節點，不會冒充成唯一的下一贖回日。

## 從 V1.3.2 升級

覆蓋：

- `index.html`
- `data/preferred_stocks.json`
- `scripts/update_market.py`
- `scripts/update_dividends.py`

建議一併保留/上傳：

- `.github/workflows/update-market.yml`
- `.github/workflows/update-dividends.yml`
- `.github/workflows/update-irs.yml`
- `data/irs.json`
- `data/dividend_events.json`
- `icons/`
- `manifest.webmanifest`

上傳後先手動執行一次 **Update dividend dates**，再執行 **Update preferred stock market data**，讓官方除息事件先寫入，再用最新股價重算 IRR/XIRR。

## V1.5
保留 V1.5 的贖回／重設生命週期與 IRR/XIRR 計算邏輯，補回完整列表中的重設公式、目前 IRS、推估重設利率、推估重設股息、重設後殖利率、贖回價格、贖回價差與綜合評分，並擴充排序選項。


## V1.5 新增
- 完整列表新增「不贖回永久收益率」。
- 完整列表新增「IRS=0 壓力收益率」。
- 個股詳細頁加入 IRS -0.5%、-1.0%、0% 三種不贖回壓力情境。
- 排序可依不贖回永久收益率、IRS=0 壓力收益率。
- 固定股息型特別股的不贖回永久收益率等於目前年股息／市價。
- IRS 重設型則以目前 IRS + 固定加碼估算；IRS=0 僅為壓力測試，不代表契約保證最低收益。
