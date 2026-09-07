from flask import Flask, jsonify, request, render_template_string
import os, re, math, time
import requests
import feedparser
from urllib.parse import quote_plus

app = Flask(__name__)

GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=GB"
EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

PRODUCT_HINTS = {
    "home": ["lamp", "light", "storage", "organizer", "organiser", "shelf", "rack", "heater", "fan", "vacuum", "cleaner", "mop", "humidifier", "dehumidifier", "blanket", "pillow", "kitchen", "cooker", "air fryer"],
    "tech": ["charger", "power bank", "headphones", "earbuds", "speaker", "keyboard", "mouse", "camera", "projector", "smartwatch", "watch", "tablet", "phone", "console", "controller"],
    "pet": ["dog", "cat", "pet", "lead", "leash", "harness", "feeder", "litter", "grooming"],
    "beauty": ["hair", "skin", "beauty", "makeup", "serum", "cream", "brush", "trimmer", "shaver", "perfume"],
    "fitness": ["gym", "fitness", "massage", "roller", "weights", "dumbbell", "resistance", "walking pad"],
    "seasonal": ["halloween", "christmas", "winter", "rain", "umbrella", "school", "university", "football"]
}

STOP_TERMS = ["vs", "score", "result", "news", "death", "dies", "war", "election", "weather", "temperature", "politics", "actor", "actress", "football club"]


def parse_volume(raw):
    if not raw:
        return 0
    s = str(raw).upper().replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*([KMB]?)", s)
    if not m:
        return 0
    n = float(m.group(1))
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[m.group(2)]
    return int(n * mult)


def classify_product(term):
    t = term.lower()
    if any(x in t for x in STOP_TERMS):
        return None, 0
    best_cat, best_hits = None, 0
    for cat, words in PRODUCT_HINTS.items():
        hits = sum(1 for w in words if w in t)
        if hits > best_hits:
            best_cat, best_hits = cat, hits
    return best_cat, best_hits


def fetch_google_trends():
    r = requests.get(GOOGLE_TRENDS_RSS, timeout=15, headers={"User-Agent": "ProfitSignal/1.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        volume_raw = entry.get("ht_approx_traffic") or entry.get("approx_traffic") or ""
        volume = parse_volume(volume_raw)
        cat, hits = classify_product(title)
        items.append({
            "term": title,
            "search_volume": volume,
            "volume_raw": volume_raw or "n/a",
            "category": cat or "general",
            "product_signal": hits,
            "source": "Google Trends UK",
            "trend_url": f"https://trends.google.com/trends/explore?geo=GB&q={quote_plus(title)}"
        })
    return items


_ebay_token_cache = {"token": None, "expires": 0}

def ebay_token():
    cid = os.getenv("EBAY_CLIENT_ID")
    secret = os.getenv("EBAY_CLIENT_SECRET")
    if not cid or not secret:
        return None
    if _ebay_token_cache["token"] and time.time() < _ebay_token_cache["expires"] - 60:
        return _ebay_token_cache["token"]
    import base64
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    r = requests.post(EBAY_TOKEN_URL, headers={
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }, data={"grant_type":"client_credentials", "scope":"https://api.ebay.com/oauth/api_scope"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    _ebay_token_cache["token"] = data["access_token"]
    _ebay_token_cache["expires"] = time.time() + int(data.get("expires_in", 7200))
    return _ebay_token_cache["token"]


def ebay_validate(term):
    token = ebay_token()
    if not token:
        return None
    r = requests.get(EBAY_SEARCH_URL, params={"q": term, "limit": 20, "filter": "buyingOptions:{FIXED_PRICE}"}, headers={
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"
    }, timeout=15)
    r.raise_for_status()
    data = r.json()
    listings = data.get("itemSummaries", [])
    prices = []
    for item in listings:
        try:
            prices.append(float(item["price"]["value"]))
        except Exception:
            pass
    prices.sort()
    median = prices[len(prices)//2] if prices else None
    return {
        "listing_count": int(data.get("total", 0)),
        "sample_count": len(listings),
        "median_price": median,
        "market_url": f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(term)}"
    }


def score(item, ebay=None):
    vol = item.get("search_volume", 0)
    product_signal = item.get("product_signal", 0)
    trend_points = min(45, 8 + (math.log10(max(vol, 10)) - 1) * 9)
    intent_points = min(25, product_signal * 14)
    market_points = 8
    competition_penalty = 0
    price_points = 0
    if ebay:
        count = ebay.get("listing_count", 0)
        median = ebay.get("median_price")
        market_points = 20 if count > 0 else 0
        if count > 100000:
            competition_penalty = 18
        elif count > 25000:
            competition_penalty = 12
        elif count > 5000:
            competition_penalty = 7
        elif count > 0:
            competition_penalty = 2
        if median:
            if 12 <= median <= 40: price_points = 12
            elif 7 <= median <= 70: price_points = 8
            else: price_points = 3
    total = round(max(0, min(100, trend_points + intent_points + market_points + price_points - competition_penalty)))
    return total


def verdict(s):
    if s >= 75: return "HOT"
    if s >= 55: return "WATCH"
    if s >= 38: return "RESEARCH"
    return "IGNORE"


def run_scan(validate_ebay=False):
    trends = fetch_google_trends()
    results = []
    for item in trends:
        if item["product_signal"] <= 0:
            continue
        ebay = None
        if validate_ebay:
            try:
                ebay = ebay_validate(item["term"])
            except Exception:
                ebay = None
        s = score(item, ebay)
        row = {**item, "score": s, "verdict": verdict(s), "ebay": ebay}
        results.append(row)
    results.sort(key=lambda x: (x["score"], x["search_volume"]), reverse=True)
    return results


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProfitSignal</title>
<style>
:root{--bg:#071018;--panel:#0e1b26;--line:#20303f;--text:#edf6ff;--muted:#8ea5b7;--good:#2ee6a6;--warn:#ffd166;--bad:#ff6b6b;--blue:#57a6ff}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#061019,#0a1520);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:auto;padding:22px}.hero{display:flex;justify-content:space-between;align-items:end;gap:20px;margin:14px 0 22px}.brand{font-size:32px;font-weight:850}.brand span{color:var(--good)}.sub{color:var(--muted);margin-top:6px}.pill{border:1px solid var(--line);background:#0b1721;padding:9px 12px;border-radius:999px;color:var(--muted);font-size:13px}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}button{border:0;border-radius:12px;padding:12px 16px;font-weight:750;cursor:pointer;background:var(--good);color:#042117}.secondary{background:#122331;color:var(--text);border:1px solid var(--line)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.stat,.card{background:rgba(14,27,38,.9);border:1px solid var(--line);border-radius:16px}.stat{padding:16px}.n{font-size:26px;font-weight:850}.label{font-size:12px;color:var(--muted);margin-top:4px}
.card{padding:16px;margin:12px 0}.top{display:flex;justify-content:space-between;gap:14px}.name{font-size:18px;font-weight:800}.meta{font-size:13px;color:var(--muted);margin-top:5px}.score{font-size:28px;font-weight:900;min-width:58px;text-align:right}.HOT{color:var(--good)}.WATCH{color:var(--warn)}.RESEARCH{color:var(--blue)}.IGNORE{color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}.mini{background:#0a1520;border:1px solid #1a2a38;border-radius:12px;padding:11px}.mini b{display:block;font-size:14px;margin-top:3px}.mini span{font-size:11px;color:var(--muted)}a{color:#8fc4ff;text-decoration:none}.empty{padding:40px;text-align:center;color:var(--muted)}.foot{color:var(--muted);font-size:12px;padding:18px 2px 40px;line-height:1.5}
@media(max-width:720px){.stats,.grid{grid-template-columns:repeat(2,1fr)}.hero{align-items:flex-start;flex-direction:column}.brand{font-size:28px}.wrap{padding:14px}}
</style></head><body><div class="wrap">
<div class="hero"><div><div class="brand">Profit<span>Signal</span></div><div class="sub">UK product trend scanner · demand first, products second.</div></div><div class="pill" id="status">Ready</div></div>
<div class="controls"><button onclick="scan(false)">Scan UK trends</button><button class="secondary" onclick="scan(true)">Scan + eBay validation</button></div>
<div class="stats"><div class="stat"><div class="n" id="found">0</div><div class="label">Product signals</div></div><div class="stat"><div class="n" id="hot">0</div><div class="label">Hot opportunities</div></div><div class="stat"><div class="n" id="watch">0</div><div class="label">Worth watching</div></div><div class="stat"><div class="n" id="ebay">—</div><div class="label">eBay API</div></div></div>
<div id="results"><div class="empty">Tap <b>Scan UK trends</b> to pull the current Google Trends UK feed.</div></div>
<div class="foot">MVP scoring combines search volume, product-intent clues and optional eBay marketplace validation. It deliberately does not pretend that a trend equals profit. Supplier cost, fees, delivery speed, IP risk and actual conversion still need validating before listing anything.</div>
</div><script>
const fmt=n=>n?new Intl.NumberFormat('en-GB').format(n):'n/a';
async function scan(validate){const s=document.getElementById('status');s.textContent='Scanning…';document.getElementById('results').innerHTML='<div class="empty">Scanning live UK trends…</div>';try{const r=await fetch('/api/scan?ebay='+(validate?'1':'0'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Scan failed');document.getElementById('found').textContent=d.results.length;document.getElementById('hot').textContent=d.results.filter(x=>x.verdict==='HOT').length;document.getElementById('watch').textContent=d.results.filter(x=>x.verdict==='WATCH').length;document.getElementById('ebay').textContent=d.ebay_configured?'LIVE':'OFF';s.textContent='Updated '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});render(d.results)}catch(e){s.textContent='Error';document.getElementById('results').innerHTML='<div class="empty">'+e.message+'</div>'}}
function render(rows){const box=document.getElementById('results');if(!rows.length){box.innerHTML='<div class="empty">No obvious product-intent terms in the current Google UK trend feed. That is a valid result, not a fake opportunity.</div>';return}box.innerHTML=rows.map(x=>{const e=x.ebay;return `<div class="card"><div class="top"><div><div class="name">${esc(x.term)}</div><div class="meta">${esc(x.category)} · ${esc(x.source)} · <a target="_blank" href="${x.trend_url}">open trend ↗</a>${e?` · <a target="_blank" href="${e.market_url}">eBay ↗</a>`:''}</div></div><div><div class="score ${x.verdict}">${x.score}</div><div class="label">${x.verdict}</div></div></div><div class="grid"><div class="mini"><span>Search volume</span><b>${fmt(x.search_volume)}</b></div><div class="mini"><span>Product signal</span><b>${x.product_signal}</b></div><div class="mini"><span>eBay listings</span><b>${e?fmt(e.listing_count):'not checked'}</b></div><div class="mini"><span>Median eBay price</span><b>${e&&e.median_price?'£'+e.median_price.toFixed(2):'not checked'}</b></div></div></div>`}).join('')}
function esc(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
</script></body></html>'''

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.get("/api/scan")
def api_scan():
    try:
        use_ebay = request.args.get("ebay") == "1"
        configured = bool(os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))
        results = run_scan(validate_ebay=use_ebay and configured)
        return jsonify({"results": results, "ebay_configured": configured, "source": GOOGLE_TRENDS_RSS})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
