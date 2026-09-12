# 台灣上市櫃特別股分析 V1.3

V1.3 重點：
- 股價：TWSE MIS / TPEx 自動更新
- 殖利率：依最新股價自動重算
- TWD IRS：Cbonds + GitHub Actions
- XIRR：以官方已公告「除息日」作為股息權利取得日期，搭配精確贖回日做日期化計算
- 若缺少未來已公告除息日期，網站明確顯示資料不足，不再以年配息近似值冒充日期化 XIRR
- FindBillion 僅作標的清單與交叉驗證來源之一

## V1.3 新增檔案
- `data/dividend_events.json`
- `scripts/update_dividends.py`
- `.github/workflows/update-dividends.yml`

GitHub Actions 的 dividend workflow 會從 TWSE 官方 OpenAPI 更新除權息事件；V1.3 只要有 `exDate` 與每股股息金額即可納入 XIRR，`paymentDate` 僅保留作參考，不參與計算。


## V1.3 XIRR 定義
本版依使用需求採「除息日基準 XIRR」：投資人只要在除息前持有並取得股息權利，即把該筆股息視為在除息日確定取得的經濟利益。此定義與以實際現金入帳日計算的傳統 XIRR 會有些微差異。
