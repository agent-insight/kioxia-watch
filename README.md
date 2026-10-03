# KIOXIA WATCH Ver.5 AUTO

Automated GitHub Pages research dashboard.

## Automatic schedule (Asia/Tokyo)
- Weekdays 07:30 — ingest overnight US/macro data
- Weekdays 16:30 — refresh after the Tokyo cash session

## Sources
- SOX: FRED NASDAQSOX (Nasdaq)
- US 10Y: FRED DGS10 (Federal Reserve)
- USD/JPY: FRED DEXJPUS (Federal Reserve)
- SNDK / MU / NVDA / WDC: Stooq daily CSV when available
- Kioxia base history: existing normalized TSE/Yahoo Japan dataset

Missing observations remain null. No interpolation or fabricated prices.

The workflow explicitly deploys GitHub Pages after updating because a push made with GITHUB_TOKEN does not itself trigger a Pages build.
