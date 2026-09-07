# ProfitSignal

A zero-cost UK product opportunity scanner MVP.

## What it does
- Pulls the live Google Trends UK RSS feed.
- Filters for terms with product-buying signals.
- Scores opportunities instead of pretending every trend is sellable.
- Optionally validates demand/competition against eBay UK using the official Browse API.
- Shows a mobile-friendly dashboard with HOT / WATCH / RESEARCH / IGNORE scores.

## Run locally
```bash
cd ProfitSignal
pip install -r requirements.txt
python app.py
```
Then open http://localhost:5000

## eBay validation (optional)
Create an eBay developer app and set these environment variables:

```bash
EBAY_CLIENT_ID=...
EBAY_CLIENT_SECRET=...
```

Without them the scanner still works using live Google Trends data, but eBay listing count and median-price validation remain off.

## Render
This folder includes `render.yaml`. Deploy from the `JRowding/Projects` repository with root directory `ProfitSignal`, or create a Blueprint from the YAML.

## Next build targets
1. Add TikTok Shop / creator-marketplace trend input where accessible without violating platform rules.
2. Add supplier validation for legitimate UK-compatible dropship wholesalers.
3. Add landed-cost, marketplace-fee and estimated-margin modelling.
4. Store daily snapshots so acceleration can be measured rather than inferred from a single scan.
5. Add watchlist and alerting when a product crosses a chosen score/margin threshold.

The MVP intentionally refuses to manufacture fake opportunities. If the current UK trend feed contains no clear product-intent terms, it says so.
