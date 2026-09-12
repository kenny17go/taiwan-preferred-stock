# V1.3 資料來源

- 市場價格：TWSE MIS / TPEx，自動更新。
- 殖利率：本站以年股息 ÷ 最新市場價格計算。
- TWD IRS：Cbonds，由既有 GitHub Actions 更新。
- 除權息日期：TWSE OpenAPI `/exchangeReport/TWT48U_ALL`。
- 股利分派資料：TWSE OpenAPI `/opendata/t187ap45_L`。
- 除息日期：優先使用 TWSE/TPEx 官方除權息資料；V1.3 只要具 exDate 與股息金額即可進入 XIRR。paymentDate 僅保留作參考。
- 發行／重設條件：公開說明書、重大訊息、交易所公告與發行公司公開資料。
- FindBillion：僅作特別股標的清單與資料交叉驗證來源之一，不再描述為本站市場資料來源。

## XIRR 規則
XIRR 的初始現金流為買入日的負市價；股息以「除息日」作正現金流日期；贖回款以精確贖回日作正現金流。此為「除息日基準 XIRR」，用來反映取得股息權利的時間點，而非實際現金入帳時間。