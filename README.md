# KIOXIA WATCH Ver.8 SIGNAL LAB

Ver.8 turns the full-auto data pipeline into a descriptive signal-analysis dashboard.

## Added in Ver.8
- NEXT JPX SESSION panel based on the latest independently available US/macro observations
- Threshold studies: SOX +1%/+2%, SNDK +3%, MU +3%, NVDA +3%, combined semiconductor conditions, and rates/FX combinations
- For every condition: sample size, Kioxia next-session up rate, average return, and median return
- Similar-regime matching using bucketed SOX/SNDK/MU/NVDA moves
- Data-quality / coverage monitoring remains visible
- No missing-value imputation; missing observations stay missing

## Interpretation
All percentages are historical descriptive statistics, not forecasts or probabilities of future performance. Small samples are explicitly flagged.

## Automation
Keep the existing `.github/workflows/update.yml`. The current GitHub Actions schedule can continue to call `scripts/update_market.py` and deploy the site.
