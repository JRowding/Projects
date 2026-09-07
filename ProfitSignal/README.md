# ProfitSignal

A zero-cost UK product opportunity scanner designed around one rule: demand first, products second.

## Current version: v2

ProfitSignal now:
- Pulls the live Google Trends UK RSS feed.
- Filters out obvious news/sports/non-product noise.
- Detects product-intent terms across home, tech, pet, beauty, fitness, fashion and seasonal categories.
- Scores each candidate as HOT / WATCH / RESEARCH / IGNORE.
- Optionally validates UK competition and median market price with the official eBay Browse API.
- Stores rolling scan snapshots during the running Render instance so repeat appearances can earn/lose acceleration points.
- Gives a route hint such as dropship candidate, affiliate/avoid stock, or research supplier.
- Includes a browser-saved watchlist.
- Includes a manual margin calculator for supplier cost, shipping and marketplace fees.
- Exports the current scan to CSV.
- Remains mobile-friendly.
- Refuses to invent opportunities when the live feed has no credible product signals.

## Deploy on Render
Use the repository `JRowding/Projects` and set the root directory to `ProfitSignal`.

The included `render.yaml` starts:

```bash
python scanner_v2.py
```

Health endpoint:

```text
/health
```

## eBay validation (optional but recommended)
Create an eBay developer application and add these environment variables in Render:

```bash
EBAY_CLIENT_ID=...
EBAY_CLIENT_SECRET=...
```

Without them the core scanner still works, but marketplace listing counts and median prices are not validated.

## Important limitation
Google Trends RSS is a broad UK trend feed, not a dedicated shopping bestseller feed. v2 is therefore a genuine opportunity triage tool, not yet an autonomous proof-of-profit engine. The next major improvement is adding more lawful demand sources and supplier feeds so a product can be scored using sales velocity, landed supplier cost and marketplace demand together.

The rolling snapshot database uses Render's local filesystem on the free tier, so history can reset after a restart/redeploy. The browser watchlist persists locally on the user's device.

## Next serious build targets
1. Add another live product-demand source beyond Google Trends.
2. Add legitimate UK-compatible dropship/wholesale supplier feeds.
3. Calculate landed cost and true margin automatically where supplier data permits.
4. Add persistent external storage only if the scanner proves useful enough to justify it.
5. Add alerts when a watched product crosses a chosen score/margin threshold.
