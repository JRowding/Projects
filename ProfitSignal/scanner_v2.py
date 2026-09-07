from flask import Flask, jsonify, request, render_template_string
import os, re, math, time, sqlite3, json, base64
from datetime import datetime, timezone
from urllib.parse import quote_plus
import requests
import feedparser

app = Flask(__name__)

GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=GB"
EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
DB_PATH = os.getenv("PROFITSIGNAL_DB", "/tmp/profitsignal.db")

PRODUCT_HINTS = {
    "home": ["lamp","light","storage","organizer","organiser","shelf","rack","heater","fan","vacuum","cleaner","mop","humidifier","dehumidifier","blanket","pillow","kitchen","cooker","air fryer","bottle","cup","mug","pan","knife","chair","desk"],
    "tech": ["charger","power bank","headphones","earbuds","speaker","keyboard","mouse","camera","projector","smartwatch","watch","tablet","phone","console","controller","cable","adapter","tracker","microphone","ring light"],
    "pet": ["dog","cat","pet","lead","leash","harness","feeder","litter","grooming","toy","bed","bowl"],
    "beauty": ["hair","skin","beauty","makeup","serum","cream","brush","trimmer","shaver","perfume","nails","dryer","straightener","curler"],
    "fitness": ["gym","fitness","massage","roller","weights","dumbbell","resistance","walking pad","yoga","protein shaker","exercise"],
    "fashion": ["bag","backpack","wallet","purse","jacket","coat","hoodie","shirt","dress","shoes","trainers","slippers","hat","gloves"],
    "seasonal": ["halloween","christmas","winter","rain","umbrella","school","university","festival","camping","garden","summer"]
}

STOP_TERMS = [
    " vs ","score","result","news","death","dies","war","election","weather","temperature","politics",
    "actor","actress","football club","match","fixtures","league table","earthquake","shooting","murder","trial",
    "obituary","lottery","horoscope","episode","season finale","concert tickets"
]


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        ts INTEGER NOT NULL, term TEXT NOT NULL, search_volume INTEGER NOT NULL,
        score INTEGER NOT NULL, category TEXT, ebay_total INTEGER, ebay_median REAL
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_snap_term_ts ON snapshots(term, ts)")
    return con


def parse_volume(raw):
    if not raw: return 0
    s = str(raw).upper().replace(",", "").replace("+", "").strip()
    m = re.search(r"([\d.]+)\s*([KMB]?)", s)
    if not m: return 0
    n = float(m.group(1)); mult = {"":1,"K":1_000,"M":1_000_000,"B":1_000_000_000}[m.group(2)]
    return int(n * mult)


def classify_product(term):
    t = " " + term.lower().strip() + " "
    if any(x in t for x in STOP_TERMS): return None, 0
    best_cat, best_hits = None, 0
    for cat, words in PRODUCT_HINTS.items():
        hits = sum(1 for w in words if w in t)
        if hits > best_hits: best_cat, best_hits = cat, hits
    return best_cat, best_hits


def fetch_google_trends():
    r = requests.get(GOOGLE_TRENDS_RSS, timeout=15, headers={"User-Agent":"ProfitSignal/2.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        raw = entry.get("ht_approx_traffic") or entry.get("approx_traffic") or ""
        volume = parse_volume(raw)
        cat, hits = classify_product(title)
        items.append({
            "term": title, "search_volume": volume, "volume_raw": raw or "n/a",
            "category": cat or "general", "product_signal": hits,
            "source": "Google Trends UK",
            "trend_url": f"https://trends.google.com/trends/explore?geo=GB&q={quote_plus(title)}"
        })
    return items


_ebay_token_cache = {"token":None,"expires":0}
def ebay_token():
    cid = os.getenv("EBAY_CLIENT_ID"); secret = os.getenv("EBAY_CLIENT_SECRET")
    if not cid or not secret: return None
    if _ebay_token_cache["token"] and time.time() < _ebay_token_cache["expires"] - 60:
        return _ebay_token_cache["token"]
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    r = requests.post(EBAY_TOKEN_URL, headers={"Authorization":f"Basic {auth}","Content-Type":"application/x-www-form-urlencoded"}, data={"grant_type":"client_credentials","scope":"https://api.ebay.com/oauth/api_scope"}, timeout=15)
    r.raise_for_status(); d = r.json()
    _ebay_token_cache["token"] = d["access_token"]; _ebay_token_cache["expires"] = time.time()+int(d.get("expires_in",7200))
    return _ebay_token_cache["token"]


def ebay_validate(term):
    token = ebay_token()
    if not token: return None
    r = requests.get(EBAY_SEARCH_URL, params={"q":term,"limit":50,"filter":"buyingOptions:{FIXED_PRICE}"}, headers={"Authorization":f"Bearer {token}","X-EBAY-C-MARKETPLACE-ID":"EBAY_GB"}, timeout=15)
    r.raise_for_status(); d = r.json(); listings = d.get("itemSummaries",[])
    prices=[]
    for item in listings:
        try:
            if item.get("price",{}).get("currency") == "GBP": prices.append(float(item["price"]["value"]))
        except Exception: pass
    prices.sort(); median = prices[len(prices)//2] if prices else None
    return {"listing_count":int(d.get("total",0)),"sample_count":len(listings),"median_price":median,"market_url":f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(term)}"}


def previous_volume(term):
    try:
        con=db(); row=con.execute("SELECT search_volume,ts FROM snapshots WHERE term=? ORDER BY ts DESC LIMIT 1",(term,)).fetchone(); con.close()
        return (int(row["search_volume"]),int(row["ts"])) if row else (None,None)
    except Exception: return (None,None)


def score_item(item, ebay=None, prev=None):
    vol=item.get("search_volume",0); signal=item.get("product_signal",0)
    trend=min(40, 8 + max(0,math.log10(max(vol,10))-1)*8)
    intent=min(22, signal*12)
    market=8; price_pts=0; comp_pen=0; accel=0
    if prev and prev>0 and vol>0:
        ratio=vol/prev
        if ratio>=4: accel=15
        elif ratio>=2: accel=10
        elif ratio>=1.25: accel=5
        elif ratio<0.75: accel=-5
    if ebay:
        count=ebay.get("listing_count",0); median=ebay.get("median_price")
        market=18 if count>0 else 0
        if count>100000: comp_pen=20
        elif count>25000: comp_pen=14
        elif count>5000: comp_pen=8
        elif count>1000: comp_pen=4
        if median:
            if 12<=median<=40: price_pts=12
            elif 7<=median<=70: price_pts=8
            else: price_pts=3
    total=round(max(0,min(100,trend+intent+market+price_pts+accel-comp_pen)))
    return total, accel


def verdict(s):
    if s>=75:return "HOT"
    if s>=55:return "WATCH"
    if s>=38:return "RESEARCH"
    return "IGNORE"


def route_hint(ebay):
    if not ebay or not ebay.get("median_price"): return "Validate market"
    price=ebay["median_price"]; count=ebay.get("listing_count",0)
    if price>=15 and count<5000:return "Dropship candidate"
    if count>=25000:return "Affiliate / avoid stock"
    return "Research supplier"


def save_snapshot(rows):
    now=int(time.time())
    try:
        con=db()
        for x in rows:
            e=x.get("ebay") or {}
            con.execute("INSERT INTO snapshots(ts,term,search_volume,score,category,ebay_total,ebay_median) VALUES(?,?,?,?,?,?,?)",(now,x["term"],x["search_volume"],x["score"],x["category"],e.get("listing_count"),e.get("median_price")))
        con.execute("DELETE FROM snapshots WHERE ts < ?",(now-60*60*24*30,)); con.commit(); con.close()
    except Exception: pass


def run_scan(validate_ebay=False):
    results=[]
    for item in fetch_google_trends():
        if item["product_signal"]<=0: continue
        prev,_=previous_volume(item["term"])
        ebay=None
        if validate_ebay:
            try: ebay=ebay_validate(item["term"])
            except Exception: ebay=None
        s,accel=score_item(item,ebay,prev)
        results.append({**item,"score":s,"verdict":verdict(s),"acceleration_points":accel,"previous_volume":prev,"ebay":ebay,"route":route_hint(ebay)})
    results.sort(key=lambda x:(x["score"],x["search_volume"]),reverse=True)
    save_snapshot(results)
    return results

PAGE=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ProfitSignal</title><style>
:root{--bg:#071018;--panel:#0e1b26;--line:#20303f;--text:#edf6ff;--muted:#8ea5b7;--good:#2ee6a6;--warn:#ffd166;--bad:#ff6b6b;--blue:#57a6ff}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#061019,#0a1520);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}.wrap{max-width:1120px;margin:auto;padding:20px}.hero{display:flex;justify-content:space-between;align-items:end;gap:16px;margin:14px 0 20px}.brand{font-size:32px;font-weight:900}.brand span{color:var(--good)}.sub,.muted{color:var(--muted)}.pill{border:1px solid var(--line);padding:9px 12px;border-radius:999px;color:var(--muted);font-size:13px}.controls{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:14px}button,input,select{border-radius:11px;padding:11px 13px;font:inherit}button{border:0;font-weight:750;cursor:pointer;background:var(--good);color:#042117}.secondary{background:#122331;color:var(--text);border:1px solid var(--line)}input,select{background:#0a1520;border:1px solid var(--line);color:var(--text)}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}.stat,.card,.calc{background:rgba(14,27,38,.92);border:1px solid var(--line);border-radius:16px}.stat{padding:14px}.n{font-size:25px;font-weight:900}.label{font-size:11px;color:var(--muted);margin-top:4px}.card{padding:16px;margin:11px 0}.top{display:flex;justify-content:space-between;gap:14px}.name{font-size:18px;font-weight:850}.meta{font-size:12px;color:var(--muted);margin-top:5px}.score{font-size:28px;font-weight:900;text-align:right}.HOT{color:var(--good)}.WATCH{color:var(--warn)}.RESEARCH{color:var(--blue)}.IGNORE{color:var(--bad)}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:13px}.mini{background:#0a1520;border:1px solid #1a2a38;border-radius:11px;padding:10px}.mini b{display:block;margin-top:3px;font-size:13px}.mini span{font-size:10px;color:var(--muted)}a{color:#8fc4ff;text-decoration:none}.actions{display:flex;gap:7px;margin-top:12px;flex-wrap:wrap}.actions button{padding:8px 10px;font-size:12px}.calc{padding:14px;margin:15px 0;display:none}.calc-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.empty{padding:38px;text-align:center;color:var(--muted)}.foot{font-size:11px;line-height:1.5;color:var(--muted);padding:15px 2px 35px}.star{background:#142536;color:#ffd166;border:1px solid var(--line)}@media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}.grid,.calc-grid{grid-template-columns:repeat(2,1fr)}.hero{align-items:flex-start;flex-direction:column}.wrap{padding:13px}}
</style></head><body><div class="wrap"><div class="hero"><div><div class="brand">Profit<span>Signal</span> <small style="font-size:12px;color:#8ea5b7">v2</small></div><div class="sub">UK product scanner · demand first, products second.</div></div><div class="pill" id="status">Ready</div></div>
<div class="controls"><button onclick="scan(false)">Scan UK trends</button><button class="secondary" onclick="scan(true)">Scan + eBay</button><button class="secondary" onclick="showWatch()">Watchlist</button><button class="secondary" onclick="exportCSV()">Export CSV</button><select id="filter" onchange="applyFilter()"><option value="ALL">All scores</option><option>HOT</option><option>WATCH</option><option>RESEARCH</option></select></div>
<div class="stats"><div class="stat"><div class="n" id="found">0</div><div class="label">Signals</div></div><div class="stat"><div class="n" id="hot">0</div><div class="label">Hot</div></div><div class="stat"><div class="n" id="watch">0</div><div class="label">Watch</div></div><div class="stat"><div class="n" id="saved">0</div><div class="label">Saved</div></div><div class="stat"><div class="n" id="ebay">—</div><div class="label">eBay API</div></div></div>
<div class="calc" id="calc"><b id="calcTitle">Margin calculator</b><div class="calc-grid" style="margin-top:10px"><input id="sell" type="number" step="0.01" placeholder="Selling £"><input id="cost" type="number" step="0.01" placeholder="Supplier £"><input id="ship" type="number" step="0.01" placeholder="Shipping £"><input id="fee" type="number" step="0.1" value="13" placeholder="Fees %"><button onclick="calcMargin()">Calculate</button></div><div id="calcOut" class="muted" style="margin-top:10px"></div></div>
<div id="results"><div class="empty">Run a scan. ProfitSignal will only show terms with a product-intent signal.</div></div><div class="foot">Scores are triage, not guarantees. Before selling, validate supplier legitimacy, UK delivery time, returns, fees, IP/trademark risk and platform policy. No account-selling or retail-arbitrage fulfilment is assumed.</div></div><script>
let rows=[];const watchKey='profitsignal-watch-v2';const fmt=n=>n?new Intl.NumberFormat('en-GB').format(n):'n/a';const money=n=>n==null?'n/a':'£'+Number(n).toFixed(2);function watches(){try{return JSON.parse(localStorage.getItem(watchKey)||'[]')}catch(e){return[]}}function saveW(a){localStorage.setItem(watchKey,JSON.stringify(a));document.getElementById('saved').textContent=a.length}
async function scan(e){const s=document.getElementById('status');s.textContent='Scanning…';document.getElementById('results').innerHTML='<div class="empty">Scanning live UK signals…</div>';try{const r=await fetch('/api/scan?ebay='+(e?'1':'0'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Scan failed');rows=d.results;document.getElementById('found').textContent=rows.length;document.getElementById('hot').textContent=rows.filter(x=>x.verdict==='HOT').length;document.getElementById('watch').textContent=rows.filter(x=>x.verdict==='WATCH').length;document.getElementById('ebay').textContent=d.ebay_configured?'LIVE':'OFF';document.getElementById('saved').textContent=watches().length;s.textContent='Updated '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});applyFilter()}catch(err){s.textContent='Error';document.getElementById('results').innerHTML='<div class="empty">'+esc(err.message)+'</div>'}}
function applyFilter(){const f=document.getElementById('filter').value;render(f==='ALL'?rows:rows.filter(x=>x.verdict===f))}function render(a){const box=document.getElementById('results');if(!a.length){box.innerHTML='<div class="empty">No qualifying signals in this view. That is better than inventing an opportunity.</div>';return}const saved=watches();box.innerHTML=a.map(x=>{const e=x.ebay;const is=saved.includes(x.term);const accel=x.acceleration_points>0?'+'+x.acceleration_points:x.acceleration_points;return `<div class="card"><div class="top"><div><div class="name">${esc(x.term)}</div><div class="meta">${esc(x.category)} · ${esc(x.route)} · <a target="_blank" href="${x.trend_url}">Google Trends ↗</a>${e?` · <a target="_blank" href="${e.market_url}">eBay ↗</a>`:''}</div></div><div><div class="score ${x.verdict}">${x.score}</div><div class="label">${x.verdict}</div></div></div><div class="grid"><div class="mini"><span>Search volume</span><b>${fmt(x.search_volume)}</b></div><div class="mini"><span>Prior volume</span><b>${fmt(x.previous_volume)}</b></div><div class="mini"><span>Acceleration</span><b>${accel||0} pts</b></div><div class="mini"><span>eBay listings</span><b>${e?fmt(e.listing_count):'not checked'}</b></div><div class="mini"><span>Median price</span><b>${e?money(e.median_price):'not checked'}</b></div></div><div class="actions"><button class="star" onclick='toggleWatch(${JSON.stringify(x.term)})'>${is?'★ Saved':'☆ Watch'}</button><button class="secondary" onclick='openCalc(${JSON.stringify(x.term)},${e&&e.median_price?e.median_price:'null'})'>Margin calculator</button></div></div>`}).join('')}
function toggleWatch(t){let a=watches();a=a.includes(t)?a.filter(x=>x!==t):[...a,t];saveW(a);applyFilter()}function showWatch(){const w=watches();render(rows.filter(x=>w.includes(x.term)))}function openCalc(t,p){document.getElementById('calc').style.display='block';document.getElementById('calcTitle').textContent='Margin calculator · '+t;document.getElementById('sell').value=p||'';document.getElementById('calc').scrollIntoView({behavior:'smooth'})}function calcMargin(){const sell=+document.getElementById('sell').value||0,cost=+document.getElementById('cost').value||0,ship=+document.getElementById('ship').value||0,fee=+document.getElementById('fee').value||0;const fees=sell*fee/100,profit=sell-cost-ship-fees,margin=sell?profit/sell*100:0;document.getElementById('calcOut').innerHTML=`Estimated net before tax: <b>${money(profit)}</b> · Margin: <b>${margin.toFixed(1)}%</b> · Marketplace fees modelled: ${money(fees)}`}
function exportCSV(){if(!rows.length)return;const cols=['term','category','search_volume','score','verdict','route','previous_volume'];let csv=cols.join(',')+'\n'+rows.map(r=>cols.map(k=>'"'+String(r[k]??'').replaceAll('"','""')+'"').join(',')).join('\n');const b=new Blob([csv],{type:'text/csv'}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='profitsignal.csv';a.click();URL.revokeObjectURL(u)}function esc(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}document.getElementById('saved').textContent=watches().length;
</script></body></html>'''

@app.get("/")
def home(): return render_template_string(PAGE)

@app.get("/api/scan")
def api_scan():
    try:
        requested=request.args.get("ebay")=="1"; configured=bool(os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))
        results=run_scan(validate_ebay=requested and configured)
        return jsonify({"results":results,"ebay_configured":configured,"source":GOOGLE_TRENDS_RSS,"generated_at":datetime.now(timezone.utc).isoformat()})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.get("/api/history")
def history():
    term=request.args.get("term","").strip()
    if not term:return jsonify({"error":"term required"}),400
    try:
        con=db(); data=[dict(r) for r in con.execute("SELECT ts,search_volume,score,ebay_total,ebay_median FROM snapshots WHERE term=? ORDER BY ts ASC LIMIT 100",(term,)).fetchall()]; con.close(); return jsonify({"term":term,"history":data})
    except Exception as e:return jsonify({"error":str(e)}),500

@app.get("/health")
def health(): return jsonify({"ok":True,"version":2})

if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")))
