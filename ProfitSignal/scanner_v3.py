from flask import Flask, jsonify, request, render_template_string
import os, re, math, time, base64
from datetime import datetime
from urllib.parse import quote_plus
import requests, feedparser

app = Flask(__name__)

GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=GB"
EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

PRODUCT_HINTS = {
    "home": ["lamp","light","storage","organizer","organiser","shelf","rack","heater","fan","vacuum","cleaner","mop","humidifier","dehumidifier","blanket","pillow","kitchen","air fryer","bottle","cup","mug","pan","chair","desk","airer"],
    "tech": ["charger","power bank","headphones","earbuds","speaker","keyboard","mouse","camera","projector","smartwatch","watch","tablet","phone","console","controller","cable","adapter","tracker","microphone","ring light"],
    "pet": ["dog","cat","pet","lead","leash","harness","feeder","litter","grooming","toy","bed","bowl","hair remover"],
    "beauty": ["hair","skin","beauty","makeup","serum","cream","brush","trimmer","shaver","perfume","nails","dryer","straightener","curler"],
    "fitness": ["gym","fitness","massage","roller","weights","dumbbell","resistance","walking pad","yoga","exercise"],
    "fashion": ["bag","backpack","wallet","purse","jacket","coat","hoodie","shirt","dress","shoes","trainers","slippers","hat","gloves"],
    "seasonal": ["halloween","christmas","winter","rain","umbrella","school","university","camping","garden","thermal"]
}
STOP_TERMS = [" vs ","score","result","news","death","dies","war","election","weather","temperature","politics","actor","actress","football club","match","fixtures","league table","earthquake","shooting","murder","trial","obituary","lottery","horoscope","episode","concert tickets"]

EVERGREEN = [
    ("rechargeable wardrobe light","home"),("under sink organiser","home"),("heated clothes airer","home"),
    ("portable dehumidifier","home"),("pet hair remover","pet"),("rechargeable lint remover","home"),
    ("portable power bank","tech"),("magnetic phone holder","tech"),("travel mug","home"),
    ("lunch box","home"),("shoe dryer","seasonal"),("thermal blanket","seasonal")
]
SEASONAL = {
    9: [("back to school lunch box","seasonal"),("student desk organiser","home"),("compact dehumidifier","home")],
    10: [("halloween projector light","seasonal"),("heated clothes airer","home"),("thermal blanket","seasonal")],
    11: [("hand warmer rechargeable","seasonal"),("heated throw blanket","seasonal"),("christmas projector light","seasonal")],
    12: [("christmas projector light","seasonal"),("rechargeable hand warmer","seasonal"),("gift travel mug","home")],
}


def parse_volume(raw):
    if not raw: return 0
    s = str(raw).upper().replace(",", "").replace("+", "").strip()
    m = re.search(r"([\d.]+)\s*([KMB]?)", s)
    if not m: return 0
    n = float(m.group(1)); mult = {"":1,"K":1000,"M":1000000,"B":1000000000}[m.group(2)]
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
    r = requests.get(GOOGLE_TRENDS_RSS, timeout=15, headers={"User-Agent":"ProfitSignal/3.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    rows=[]
    for e in feed.entries:
        title=e.get("title","").strip()
        raw=e.get("ht_approx_traffic") or e.get("approx_traffic") or ""
        cat,hits=classify_product(title)
        rows.append({"term":title,"search_volume":parse_volume(raw),"volume_raw":raw or "n/a","category":cat or "general","product_signal":hits,"source":"Google Trends UK","source_type":"live_trend","trend_url":f"https://trends.google.com/trends/explore?geo=GB&q={quote_plus(title)}"})
    return rows

_token={"value":None,"expires":0}
def ebay_token():
    cid=os.getenv("EBAY_CLIENT_ID"); secret=os.getenv("EBAY_CLIENT_SECRET")
    if not cid or not secret: return None
    if _token["value"] and time.time() < _token["expires"]-60: return _token["value"]
    auth=base64.b64encode(f"{cid}:{secret}".encode()).decode()
    r=requests.post(EBAY_TOKEN_URL,headers={"Authorization":f"Basic {auth}","Content-Type":"application/x-www-form-urlencoded"},data={"grant_type":"client_credentials","scope":"https://api.ebay.com/oauth/api_scope"},timeout=15)
    r.raise_for_status(); d=r.json(); _token["value"]=d["access_token"]; _token["expires"]=time.time()+int(d.get("expires_in",7200)); return _token["value"]


def ebay_validate(term):
    token=ebay_token()
    if not token: return None
    r=requests.get(EBAY_SEARCH_URL,params={"q":term,"limit":50,"filter":"buyingOptions:{FIXED_PRICE}"},headers={"Authorization":f"Bearer {token}","X-EBAY-C-MARKETPLACE-ID":"EBAY_GB"},timeout=15)
    r.raise_for_status(); d=r.json(); prices=[]
    for item in d.get("itemSummaries",[]):
        try:
            p=item.get("price",{}); 
            if p.get("currency")=="GBP": prices.append(float(p["value"]))
        except Exception: pass
    prices.sort(); med=prices[len(prices)//2] if prices else None
    return {"listing_count":int(d.get("total",0)),"sample_count":len(prices),"median_price":med,"market_url":f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(term)}"}


def score(row, ebay=None):
    live=row["source_type"]=="live_trend"; vol=row.get("search_volume",0); signal=row.get("product_signal",0)
    points = 18 if not live else min(58, 18 + max(0, math.log10(max(vol,10))-1)*10 + signal*10)
    if ebay:
        count=ebay.get("listing_count",0); med=ebay.get("median_price")
        if count>0: points += 18
        if med:
            if 12 <= med <= 40: points += 14
            elif 7 <= med <= 70: points += 8
        if count > 100000: points -= 20
        elif count > 25000: points -= 13
        elif count > 5000: points -= 7
        elif count > 1000: points -= 3
    return max(0,min(100,round(points)))


def verdict(s, source_type):
    if source_type != "live_trend" and s < 55: return "RESEARCH"
    if s>=75:return "HOT"
    if s>=55:return "WATCH"
    if s>=35:return "RESEARCH"
    return "IGNORE"


def candidate_rows():
    month=datetime.now().month
    seen=set(); rows=[]
    for term,cat in SEASONAL.get(month,[]) + EVERGREEN:
        if term in seen: continue
        seen.add(term)
        rows.append({"term":term,"search_volume":0,"volume_raw":"candidate","category":cat,"product_signal":1,"source":"ProfitSignal candidate bank","source_type":"market_candidate","trend_url":f"https://trends.google.com/trends/explore?geo=GB&q={quote_plus(term)}"})
    return rows


def run_scan(validate_ebay=False):
    raw=fetch_google_trends()
    direct=[x for x in raw if x["product_signal"]>0]
    used_fallback=len(direct)<4
    working=direct[:20]
    if used_fallback:
        existing={x["term"].lower() for x in working}
        working += [x for x in candidate_rows() if x["term"].lower() not in existing]
    results=[]
    for row in working:
        e=None
        if validate_ebay:
            try: e=ebay_validate(row["term"])
            except Exception: e=None
        s=score(row,e)
        results.append({**row,"score":s,"verdict":verdict(s,row["source_type"]),"ebay":e,"route":"Validate supplier" if not e else ("Research supplier" if e.get("listing_count",0)<25000 else "Affiliate / high competition")})
    results.sort(key=lambda x:(x["source_type"]=="live_trend",x["score"],x["search_volume"]),reverse=True)
    return results,{"google_rows":len(raw),"direct_product_signals":len(direct),"fallback_used":used_fallback}

PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ProfitSignal</title><style>
:root{--bg:#071018;--panel:#0e1b26;--line:#20303f;--text:#edf6ff;--muted:#8ea5b7;--good:#2ee6a6;--warn:#ffd166;--blue:#57a6ff}*{box-sizing:border-box}body{margin:0;background:#071018;color:var(--text);font-family:system-ui,-apple-system,Segoe UI,sans-serif}.wrap{max-width:1100px;margin:auto;padding:18px}.hero{display:flex;justify-content:space-between;gap:12px;align-items:end}.brand{font-size:32px;font-weight:900}.brand span{color:var(--good)}.muted,.meta{color:var(--muted)}button{padding:11px 14px;border:0;border-radius:11px;font-weight:800;background:var(--good);color:#042117;cursor:pointer}.secondary{background:#132431;color:white;border:1px solid var(--line)}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.stat,.card,.diag{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:14px}.n{font-size:24px;font-weight:900}.label{font-size:11px;color:var(--muted)}.diag{margin:12px 0;font-size:12px;color:var(--muted)}.card{margin:10px 0}.top{display:flex;justify-content:space-between;gap:12px}.name{font-size:18px;font-weight:850}.score{font-size:27px;font-weight:900}.HOT{color:var(--good)}.WATCH{color:var(--warn)}.RESEARCH{color:var(--blue)}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}.mini{background:#0a1520;border:1px solid #1a2a38;border-radius:10px;padding:9px}.mini span{font-size:10px;color:var(--muted)}.mini b{display:block;margin-top:3px}.badge{display:inline-block;padding:3px 7px;border-radius:99px;font-size:10px;margin-left:5px;background:#16293a;color:#9fc7e8}a{color:#8fc4ff;text-decoration:none}.empty{padding:35px;text-align:center;color:var(--muted)}@media(max-width:720px){.hero{align-items:flex-start;flex-direction:column}.stats,.grid{grid-template-columns:repeat(2,1fr)}.wrap{padding:12px}}
</style></head><body><div class="wrap"><div class="hero"><div><div class="brand">Profit<span>Signal</span> <small style="font-size:12px;color:#8ea5b7">v3</small></div><div class="muted">UK product opportunity scanner</div></div><div id="status" class="muted">Ready</div></div><div class="controls"><button onclick="scan(false)">Scan products</button><button class="secondary" onclick="scan(true)">Scan + eBay</button></div><div class="stats"><div class="stat"><div class="n" id="found">0</div><div class="label">Cards</div></div><div class="stat"><div class="n" id="live">0</div><div class="label">Live trend signals</div></div><div class="stat"><div class="n" id="hot">0</div><div class="label">Hot / watch</div></div><div class="stat"><div class="n" id="ebay">—</div><div class="label">eBay API</div></div></div><div class="diag" id="diag">Run a scan to see source diagnostics.</div><div id="results"><div class="empty">Scanning automatically…</div></div></div><script>
const fmt=n=>n?new Intl.NumberFormat('en-GB').format(n):'n/a';
async function scan(useEbay){status.textContent='Scanning…';try{const r=await fetch('/api/scan?ebay='+(useEbay?'1':'0'));const d=await r.json();if(!r.ok)throw new Error(d.error||'Scan failed');found.textContent=d.results.length;live.textContent=d.results.filter(x=>x.source_type==='live_trend').length;hot.textContent=d.results.filter(x=>x.verdict==='HOT'||x.verdict==='WATCH').length;ebay.textContent=d.ebay_configured?'LIVE':'OFF';diag.textContent=`Google rows scanned: ${d.diagnostics.google_rows} · direct product signals: ${d.diagnostics.direct_product_signals} · fallback candidates: ${d.diagnostics.fallback_used?'ON':'OFF'}`;status.textContent='Updated '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});render(d.results)}catch(e){status.textContent='Error';results.innerHTML='<div class="empty">'+e.message+'</div>'}}
function render(rows){if(!rows.length){results.innerHTML='<div class="empty">No candidates returned.</div>';return}results.innerHTML=rows.map(x=>{const e=x.ebay;const badge=x.source_type==='live_trend'?'LIVE TREND':'MARKET CANDIDATE';return `<div class="card"><div class="top"><div><div class="name">${esc(x.term)} <span class="badge">${badge}</span></div><div class="meta">${esc(x.category)} · ${esc(x.source)} · <a target="_blank" href="${x.trend_url}">Google Trends ↗</a>${e?` · <a target="_blank" href="${e.market_url}">eBay ↗</a>`:''}</div></div><div><div class="score ${x.verdict}">${x.score}</div><div class="label">${x.verdict}</div></div></div><div class="grid"><div class="mini"><span>Search volume</span><b>${x.source_type==='live_trend'?fmt(x.search_volume):'Needs validation'}</b></div><div class="mini"><span>eBay listings</span><b>${e?fmt(e.listing_count):'Not checked'}</b></div><div class="mini"><span>Median price</span><b>${e&&e.median_price?'£'+e.median_price.toFixed(2):'Not checked'}</b></div><div class="mini"><span>Next route</span><b>${esc(x.route)}</b></div></div></div>`}).join('')}
function esc(s){return String(s).replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]))}
scan(false);
</script></body></html>'''

@app.get('/')
def home(): return render_template_string(PAGE)

@app.get('/api/scan')
def api_scan():
    try:
        configured=bool(os.getenv('EBAY_CLIENT_ID') and os.getenv('EBAY_CLIENT_SECRET'))
        use=request.args.get('ebay')=='1' and configured
        rows,diag=run_scan(use)
        return jsonify({'results':rows,'diagnostics':diag,'ebay_configured':configured,'version':3})
    except Exception as e:
        return jsonify({'error':str(e),'version':3}),500

@app.get('/health')
def health(): return jsonify({'ok':True,'version':3})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
