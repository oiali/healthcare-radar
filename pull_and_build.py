#!/usr/bin/env python3
"""
UK Healthcare Niche Radar - build script (runs daily on GitHub Actions).

Signals ordered early -> late in the demand chain:
  Public interest (Wikipedia pageviews)  - client-side, no key, live
  Search demand (Google Trends)          - server-side via SerpApi (SERPAPI_KEY), weekly
  Prescribing by drug (OpenPrescribing)  - client-side, no key, live
  New companies by niche (Companies House) - server-side, auto-discovered from names
  Job ads by live volume (Adzuna)        - server-side

Writes dashboard.html + data.json; persists data/adzuna_history.json + data/trends.json.
"""

import os, re, json, base64, shutil, zipfile, tempfile, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone, date, timedelta

UA = {"User-Agent": "healthcare-radar"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}


def get_json(url, headers=None, timeout=45):
    try:
        req = urllib.request.Request(url, headers={**UA, **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def get_text(url, timeout=45):
    try:
        req = urllib.request.Request(url, headers=BROWSER_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def download(url, path, timeout=240):
    req = urllib.request.Request(url, headers=BROWSER_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    return path


def pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / then - 1.0) * 100.0


def add_months(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# ============================ Companies House: auto-discover niches from names
CH_KEY = os.environ.get("CH_API_KEY", "").strip()
HEALTH_SICS = ["86900", "86220", "96020", "96040"]   # narrowed: private-clinic heavy
STOP = set(("the and of for to in a an ltd limited uk gb london clinic clinics health "
            "healthcare care medical medicine group holdings company co consulting consultancy "
            "practice practices centre center llp cic community trust nhs solutions services "
            "service management associates partners international global national services "
            "wellbeing well being ltd co uk therapy therapies treatment treatments and "
            "devon cornwall essex kent surrey sussex yorkshire lancashire cheshire midlands "
            "forest first best new prime elite smart digital online mobile home family city "
            "north south east west greater park house lodge road street hall court view green "
            "hill professional quality complete total pure life live your local premier").split())


def ch_page(sic, dfrom, dto, start):
    url = ("https://api.company-information.service.gov.uk/advanced-search/companies"
           f"?sic_codes={sic}&incorporated_from={dfrom}&incorporated_to={dto}"
           f"&size=100&start_index={start}")
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    return get_json(url, {"Authorization": "Basic " + auth})


def name_terms(dfrom, dto):
    cnt = Counter()
    for sic in HEALTH_SICS:
        start = 0
        for _ in range(12):                       # up to 1,200 names / SIC / window
            d = ch_page(sic, dfrom, dto, start)
            items = d.get("items") if d else None
            if not items:
                break
            for it in items:
                nm = (it.get("company_name") or "").lower()
                toks = [t for t in re.findall(r"[a-z]+", nm) if len(t) > 3 and t not in STOP]
                for i in range(len(toks) - 1):          # 2-word phrases only = niche-level, low noise
                    cnt[toks[i] + " " + toks[i + 1]] += 1
            start += 100
            if len(items) < 100:
                break
    return cnt


def incorporations():
    if not CH_KEY:
        return None
    t = date.today().replace(day=1)
    recent = name_terms(add_months(t, -3).isoformat(), t.isoformat())
    prior = name_terms(add_months(t, -15).isoformat(), add_months(t, -12).isoformat())
    rows = []
    for term, c in recent.items():
        if c < 4:                                 # min volume so it's signal not noise
            continue
        p = prior.get(term, 0)
        g12 = pct(c, p) if p > 0 else None         # None = brand-new term (flag below)
        rows.append({"name": term, "code": "new" if p == 0 else "", "latest": c,
                     "g1": None, "g3": None, "g12": g12, "accel": None, "isnew": p == 0})
    # new terms first (by volume), then by 12-mth growth
    rows.sort(key=lambda r: (r["isnew"], r["g12"] if r["g12"] is not None else 0, r["latest"]), reverse=True)
    return rows[:40]


# ============================================================ Adzuna job ads
AZ_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
AZ_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()
TERMS = ["aesthetics", "dermatology", "psychiatry", "ADHD", "menopause", "endocrinology",
         "physiotherapy", "dentist", "optometrist", "audiology", "podiatry", "gynaecology",
         "urology", "cosmetic surgery", "fertility IVF", "private GP"]


def adzuna():
    if not (AZ_ID and AZ_KEY):
        return None
    rows = []
    for term in TERMS:
        url = ("https://api.adzuna.com/v1/api/jobs/gb/search/1"
               f"?app_id={AZ_ID}&app_key={AZ_KEY}&what={urllib.parse.quote(term)}"
               "&results_per_page=1&content-type=application/json")
        d = get_json(url)
        if d and "count" in d:
            rows.append({"name": term.title(), "latest": d["count"]})
    rows.sort(key=lambda x: x["latest"], reverse=True)
    return rows


# ==================================================== Google Trends (SerpApi)
SERP = os.environ.get("SERPAPI_KEY", "").strip()
TREND_Q = ["Mounjaro", "Ozempic", "Wegovy", "ADHD assessment", "menopause clinic",
           "testosterone replacement", "hair transplant", "botox", "dermal filler",
           "IV drip", "erectile dysfunction", "weight loss injection", "peptide therapy",
           "private ADHD", "HRT"]
TR_FILE = "data/trends.json"


def trends():
    if not SERP:
        return None
    try:
        cached = json.load(open(TR_FILE))
    except Exception:
        cached = None
    # only refresh weekly (Mondays) or on first run - conserves SerpApi free quota
    if cached and cached.get("rows") and date.today().weekday() != 0:
        return cached.get("rows")
    rows = []
    for q in TREND_Q:
        url = ("https://serpapi.com/search.json?engine=google_trends"
               f"&q={urllib.parse.quote(q)}&geo=GB&data_type=TIMESERIES"
               "&date=today%2012-m&api_key=" + SERP)
        d = get_json(url)
        try:
            tl = d["interest_over_time"]["timeline_data"]
            v = [pt["values"][0]["extracted_value"] for pt in tl]
        except Exception:
            continue
        n = len(v)
        if n < 20:
            continue
        last = mean(v[-4:])
        rows.append({"name": q, "latest": round(last),
                     "g1": pct(last, mean(v[-8:-4])),
                     "g3": pct(last, mean(v[-17:-13])),
                     "g12": pct(last, mean(v[:4])), "accel": None})
    rows.sort(key=lambda x: (x["g12"] if x["g12"] is not None else -9e9), reverse=True)
    os.makedirs("data", exist_ok=True)
    json.dump({"rows": rows, "date": date.today().isoformat()}, open(TR_FILE, "w"), indent=1)
    return rows


# ===================================================== CQC new registrations
# CQC publishes a monthly "care directory with filters" (.ods) listing EVERY active
# location with its HSCA registration date. One 24MB download replaces 40k+ API calls.
# We keep locations registered recently, drop social care, and cluster 2-word phrases
# in their names -> the niches people are actually opening clinics for.
CQC_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
NS_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
NS_TX = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"])}


def cqc_file_url():
    html = get_text(CQC_PAGE)
    if not html:
        return None
    m = re.search(r'href="([^"]*HSCA_Active_Locations\.ods)"', html, re.I)
    if not m:
        return None
    u = m.group(1)
    return u if u.startswith("http") else "https://www.cqc.org.uk" + u


def ods_rows(path, max_cols=220):
    """Stream rows out of an .ods (zip + content.xml), expanding repeated cells."""
    with zipfile.ZipFile(path) as zf, zf.open("content.xml") as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != NS_T + "table-row":
                continue
            row = []
            for c in el.findall(NS_T + "table-cell"):
                rep = int(c.get(NS_T + "number-columns-repeated") or 1)
                v = c.get(NS_O + "date-value") or ""
                if v:
                    v = v[:10]
                else:
                    v = " ".join("".join(p.itertext()) for p in c.findall(NS_TX + "p")).strip()
                for _ in range(rep):
                    row.append(v)
                    if len(row) >= max_cols:
                        break
                if len(row) >= max_cols:
                    break
            el.clear()
            yield row


def parse_date(s):
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})[/\-]([A-Za-z]{3,9})[/\-](\d{4})", s)
    if m:
        mon = next((v for k, v in MONTHS.items() if k.startswith(m.group(2).lower()[:3])), None)
        if mon:
            return date(int(m.group(3)), mon, int(m.group(1)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


DIAG = {}


def cqc():
    url = cqc_file_url()
    DIAG["url"] = url or "PAGE FETCH FAILED or link not found"
    if not url:
        return None
    # anchor all windows on the file's publication date, not today (file is a monthly snapshot)
    m = re.search(r"/(\d{2})_([A-Za-z]+)_(\d{4})_HSCA", url)
    anchor = date(int(m.group(3)), MONTHS.get(m.group(2).lower(), 1), int(m.group(1))) if m else date.today()

    path = os.path.join(tempfile.gettempdir(), "cqc.ods")
    try:
        download(url, path)
        DIAG["bytes"] = os.path.getsize(path)
    except Exception as e:
        DIAG["download_error"] = repr(e)[:160]
        return None

    # windows in months back from the anchor
    W = {"m1": (1, 0), "m1p": (2, 1), "m3": (3, 0), "m3p": (6, 3), "m12": (12, 0), "m12p": (24, 12)}
    bounds = {k: (add_months(anchor, -a), add_months(anchor, -b)) for k, (a, b) in W.items()}
    cnt = {k: Counter() for k in W}

    i_name = i_date = i_type = None
    rows_seen = kept = 0
    sectors = Counter()

    DIAG["first_rows"] = []
    total = 0
    for row in ods_rows(path):
        total += 1
        if len(DIAG["first_rows"]) < 6:
            DIAG["first_rows"].append([c for c in row[:6]])
        if i_name is None:
            low = [c.strip().lower() for c in row]
            if any("location id" in c for c in low):
                def find(*subs):
                    for j, c in enumerate(low):
                        if all(s in c for s in subs):
                            return j
                    return None
                i_name = find("location", "name")
                i_date = find("hsca start date")
                if i_date is None:
                    i_date = find("start date")
                i_type = find("location", "type")
                if i_type is None:
                    i_type = find("sector")
                DIAG["header"] = [c for c in low if c][:30]
                DIAG["cols"] = {"name": i_name, "date": i_date, "type": i_type}
                if i_name is None or i_date is None:
                    DIAG["fatal"] = "name/date column not found"
                    return None
            continue

        rows_seen += 1
        if len(row) <= max(i_name, i_date):
            continue
        d = parse_date(row[i_date])
        if not d:
            continue
        sector = (row[i_type] if i_type is not None and len(row) > i_type else "")
        sectors[sector] += 1
        if "social care" in sector.lower():          # care homes / homecare = churn, not niches
            continue
        nm = (row[i_name] or "").lower()
        toks = [t for t in re.findall(r"[a-z]+", nm) if len(t) > 3 and t not in STOP]
        grams = {toks[j] + " " + toks[j + 1] for j in range(len(toks) - 1)}
        if not grams:
            continue
        hit = False
        for k, (lo, hi) in bounds.items():
            if lo <= d < hi:
                hit = True
                for g in grams:
                    cnt[k][g] += 1
        kept += hit

    DIAG["anchor"] = str(anchor)
    DIAG["rows_total"] = total
    DIAG["rows_data"] = rows_seen
    DIAG["in_window"] = kept
    DIAG["sectors"] = sectors.most_common(8)
    DIAG["grams_m12"] = len(cnt["m12"])
    DIAG["top_raw"] = cnt["m12"].most_common(8)

    rows = []
    for g, c12 in cnt["m12"].items():
        if c12 < 6:                                   # min volume so it's signal not noise
            continue
        # min base of 3 on the comparison window: below that a % is noise, not signal
        p12 = cnt["m12p"][g]
        g12 = pct(c12, p12) if p12 >= 3 else None
        g3 = pct(cnt["m3"][g], cnt["m3p"][g]) if cnt["m3p"][g] >= 3 else None
        g1 = pct(cnt["m1"][g], cnt["m1p"][g]) if cnt["m1p"][g] >= 3 else None
        rows.append({"name": g, "latest": c12, "g1": g1, "g3": g3, "g12": g12,
                     "accel": (g3 - g12) if (g3 is not None and g12 is not None) else None,
                     "isnew": p12 == 0})
    rows.sort(key=lambda r: (r["isnew"], r["g12"] if r["g12"] is not None else -9e9, r["latest"]),
              reverse=True)
    return rows[:40]


# ------------------------------------------------------------------- render
def main():
    inc = incorporations() or []
    jobs = adzuna() or []
    tr = trends() or []
    cq = cqc() or []
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    payload = json.dumps({"inc": inc, "jobs": jobs, "trends": tr, "cqc": cq,
                          "diag": DIAG}).replace("</", "<\\/")
    os.makedirs("data", exist_ok=True)
    json.dump({"updated": datetime.now(timezone.utc).isoformat(), "inc": inc, "jobs": jobs,
               "trends": tr, "cqc": cq, "diag": DIAG}, open("data.json", "w"), indent=2)
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(TEMPLATE.replace("{{UPDATED}}", updated).replace("{{DATA}}", payload))
    print(f"incorporations={len(inc)} jobs={len(jobs)} trends={len(tr)} cqc={len(cq)}")


TEMPLATE = r"""<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Healthcare Niche Radar</title><style>
:root{color-scheme:light}
body{margin:0;background:#fbfbfa;color:#1e2530;font-family:Calibri,"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:980px;margin:0 auto;padding:26px 22px 60px}
.head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid #e7e8ea;padding-bottom:12px}
h1{font-size:21px;margin:0;font-weight:700}.upd{font-size:12.5px;color:#8b929c}
.tabs{display:flex;gap:4px;margin:16px 0 4px;flex-wrap:wrap}
.tab{padding:7px 13px;font-size:13px;border:1px solid #e2e4e8;border-bottom:none;border-radius:7px 7px 0 0;background:#f1f2f4;color:#6b7280;cursor:pointer}
.tab.on{background:#fff;color:#1e2530;font-weight:700}
.panel{display:none;border:1px solid #e7e8ea;border-radius:0 7px 7px 7px;padding:14px}.panel.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid #eef0f2;text-align:right}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8b929c;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#1e2530}th.l,td.nm{text-align:left}
th.sorted{color:#1e2530}th .ar{opacity:.5;font-size:9px}
td.rk{color:#aab0b8;width:26px;text-align:center}td.nm{font-weight:600}
.niche{display:inline-block;font-weight:400;font-size:11.5px;color:#5b6470;background:#eef1f4;border-radius:20px;padding:1px 8px;margin-left:8px}
.newtag{background:#e6f1ff;color:#1c5fbf;font-size:10.5px;font-weight:700;border-radius:20px;padding:1px 7px;margin-left:8px}
.drug{border-bottom:1px dotted #9aa4b0;cursor:help}
td.num{font-variant-numeric:tabular-nums}td.g12{font-weight:700}
.accel{background:#fde7e7;color:#c23b3b;font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px}
.note{font-size:12px;color:#8b929c;margin-top:12px}.msg{color:#8b929c;font-size:13px;padding:14px 6px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:18px 0 8px}
.ov ul{margin:0 0 6px;padding-left:20px}.ov li{margin:5px 0}
.up{color:#1e7d46;font-weight:700}.dn{color:#c23b3b;font-weight:700}.big{font-size:13px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Server data updated {{UPDATED}} &middot; interest &amp; prescribing live &middot; click any % column to sort</span></div>
<div class="tabs">
  <div class="tab on" data-p="ov">Overview</div>
  <div class="tab" data-p="tr">Public interest (Google)</div>
  <div class="tab" data-p="pr">Prescribing</div>
  <div class="tab" data-p="in">New companies</div>
  <div class="tab" data-p="jb">Job ads</div>
  <div class="tab" data-p="cq">New clinics</div>
</div>
<div class="panel on ov" id="ov"><div id="ovbody" class="msg">Loading live signals&hellip;</div></div>
<div class="panel" id="tr"><div id="trbody" class="msg">Loading Google search demand&hellip;</div></div>
<div class="panel" id="pr"><div id="prbody" class="msg">Fetching live prescribing&hellip;</div></div>
<div class="panel" id="in"><div id="inbody"></div></div>
<div class="panel" id="jb"><div id="jbbody"></div></div>
<div class="panel" id="cq"><div id="cqbody"></div></div>
</div>
<script>
var RADAR = {{DATA}};
var DRUGS={
"0601023AW":["Semaglutide","Weight-loss / GLP-1","type-2 diabetes & obesity (Ozempic/Wegovy)"],
"0601023AZ":["Tirzepatide","Weight-loss / GLP-1","type-2 diabetes & obesity (Mounjaro)"],
"0601023AB":["Liraglutide","Weight-loss / GLP-1","obesity & diabetes (Saxenda/Victoza)"],
"0405010P0":["Orlistat","Weight-loss","obesity (lipase inhibitor)"],
"0405020U0":["Naltrexone-bupropion","Weight-loss","obesity (Mysimba)"],
"0404000U0":["Lisdexamfetamine","ADHD","ADHD - the adult-ADHD driver (Elvanse)"],
"0404000M0":["Methylphenidate","ADHD","ADHD stimulant"],
"0404000S0":["Atomoxetine","ADHD","ADHD (non-stimulant)"],
"0404000V0":["Guanfacine","ADHD","ADHD (non-stimulant)"],
"0604020K0":["Testosterone","Men's health / TRT","testosterone deficiency"],
"0604011Y0":["Tibolone","Menopause / HRT","menopausal symptoms"],
"0702010G0":["Estradiol (vaginal)","Menopause (GSM)","vaginal atrophy / genitourinary menopause"],
"0604020C0":["Finasteride","Hair loss / BPH","male-pattern hair loss & enlarged prostate"],
"0704050Z0":["Sildenafil","Erectile dysfunction","erectile dysfunction"],
"0407042T0":["Erenumab","Migraine (CGRP)","migraine prevention"],
"0407042R0":["Fremanezumab","Migraine (CGRP)","migraine prevention"],
"0407041AD":["Rimegepant","Migraine (gepant)","migraine treatment & prevention"],
"0407042U0":["Atogepant","Migraine (gepant)","migraine prevention"],
"0704020AE":["Mirabegron","Bladder / continence","overactive bladder"],
"0606020Z0":["Denosumab","Osteoporosis","osteoporosis (Prolia)"],
"1306010M0":["Isotretinoin","Acne / dermatology","severe acne (Roaccutane)"],
"0601023AG":["Dapagliflozin","Diabetes / SGLT2","type-2 diabetes, heart & kidney"],
"0601023AN":["Empagliflozin","Diabetes / SGLT2","type-2 diabetes, heart & kidney"],
"0403030Q0":["Sertraline","Mental health","depression & anxiety"],
"0401010AD":["Melatonin","Sleep","insomnia / sleep disorders"],
"0105030C0":["Risankizumab","Biologics (IBD / psoriasis)","Crohn's disease, psoriasis"]};
// Wikipedia article title -> niche
var WIKI={
"Tirzepatide":"Weight-loss / GLP-1","Semaglutide":"Weight-loss / GLP-1","Weight loss":"Weight-loss",
"Attention deficit hyperactivity disorder":"ADHD","Adult attention deficit hyperactivity disorder":"ADHD",
"Menopause":"Menopause / HRT","Hormone replacement therapy":"Menopause / HRT",
"Testosterone":"Men's health / TRT","Erectile dysfunction":"Sexual health",
"Migraine":"Migraine","Botulinum toxin":"Aesthetics","Dermal filler":"Aesthetics",
"Hair transplantation":"Hair restoration","Autism":"Autism","In vitro fertilisation":"Fertility",
"Ketamine":"Mental health / ketamine","Psilocybin therapy":"Psychedelics","Isotretinoin":"Acne / derm",
"Finasteride":"Hair loss","Rosacea":"Dermatology","Polycystic ovary syndrome":"Women's health",
"Perimenopause":"Menopause / HRT","Semaglutide":"Weight-loss / GLP-1","Peptide":"Peptides"};

function pct(a,b){return (b&&a!=null)?((a/b-1)*100):null;}
function fmt(x){return x==null?'&ndash;':(x>=0?'+':'')+Math.round(x)+'%';}
function num(x){return (x==null?0:x).toLocaleString('en-GB');}
function trend(r){if(r.g12==null)return'brand-new (no year-ago base)';
  var s=r.g12>=25?'rising fast':r.g12>=5?'rising':r.g12>=-5?'roughly flat':'declining';
  if(r.accel!=null&&r.accel>5&&r.g12>0)s+=' and accelerating';
  else if(r.accel!=null&&r.accel<-8&&r.g12>0)s+=' but the pace is cooling';
  return s+' (12-mth '+fmt(r.g12)+', 3-mth '+fmt(r.g3)+')';}

document.querySelectorAll('.tab').forEach(function(t){t.onclick=function(){
  document.querySelectorAll('.tab,.panel').forEach(function(e){e.classList.remove('on');});
  t.classList.add('on');document.getElementById(t.dataset.p).classList.add('on');};});

// opts: {drug:bool, noGrowth:bool, firstCol:str}
function tableRows(rows,latestLabel,opts){
  opts=opts||{};
  if(!rows||!rows.length)return '<div class="msg">No data yet.</div>';
  var cols='<th data-k="latest">'+latestLabel+'</th>';
  if(!opts.noGrowth)cols+='<th data-k="g1">1-mth</th><th data-k="g3">3-mth</th><th data-k="g12">12-mth</th>';
  var h='<table><thead><tr><th class="l">#</th><th class="l">'+(opts.firstCol||'Item')+'</th>'+cols+'<th class="l"></th></tr></thead><tbody>';
  rows.forEach(function(r,i){
    var acc=(r.accel!=null&&r.accel>5)?'<span class="accel">accelerating</span>':(r.isnew?'<span class="newtag">new</span>':'');
    var nameCell;
    if(opts.drug){var tip=r.name+' — treats '+r.treats+'. Niche: '+r.niche+'. '+trend(r);
      nameCell='<span class="drug" title="'+tip.replace(/"/g,'&quot;')+'">'+r.name+'</span><span class="niche">'+r.niche+'</span>';}
    else if(r.niche){nameCell=r.name+'<span class="niche">'+r.niche+'</span>';}
    else{nameCell=r.name;}
    var g='';
    if(!opts.noGrowth)g='<td class="num">'+fmt(r.g1)+'</td><td class="num">'+fmt(r.g3)+'</td><td class="num g12">'+fmt(r.g12)+'</td>';
    h+='<tr data-latest="'+r.latest+'" data-g1="'+(r.g1==null?-9999:r.g1)+'" data-g3="'+(r.g3==null?-9999:r.g3)+
      '" data-g12="'+(r.g12==null?-9999:r.g12)+'"><td class="rk">'+(i+1)+'</td><td class="nm">'+nameCell+
      '</td><td class="num">'+num(r.latest)+'</td>'+g+'<td class="l">'+acc+'</td></tr>';});
  return h+'</tbody></table>';
}
function wireSort(el){el.querySelectorAll('th[data-k]').forEach(function(th){th.onclick=function(){
  var tb=th.closest('table').querySelector('tbody');var k=th.dataset.k;
  th.closest('tr').querySelectorAll('th').forEach(function(x){x.classList.remove('sorted');});th.classList.add('sorted');
  Array.prototype.slice.call(tb.rows).sort(function(a,b){return (+b.dataset[k])-(+a.dataset[k]);})
    .forEach(function(r,i){r.cells[0].textContent=i+1;tb.appendChild(r);});};});}

// ---- server-baked tabs ----
document.getElementById('inbody').innerHTML=tableRows(RADAR.inc,'New (3m)',{firstCol:'Niche term'})+
  '<div class="note">Auto-discovered: the fastest-rising words/phrases in the <b>names</b> of newly-registered health companies (SICs 86900/86220/96020/96040), last 3 months vs a year ago. "new" = did not appear a year ago. Rough proxy, but it surfaces niches SIC codes bury. Click a column to sort.</div>';
document.getElementById('jbbody').innerHTML=tableRows(RADAR.jobs,'Live ads',{noGrowth:true,firstCol:'Specialty'})+
  '<div class="note">Live clinician job ads (Adzuna), ranked by current volume = where hiring demand sits now.</div>';
document.getElementById('trbody').innerHTML=(RADAR.trends&&RADAR.trends.length?
  tableRows(RADAR.trends,'Index',{firstCol:'Search term'}):'<div class="msg">Search-demand data will appear after the next weekly run.</div>')+
  '<div class="note">Google Trends search interest in the UK (via SerpApi), refreshed weekly. Ranked by 12-month growth; click a column to sort.</div>';
document.getElementById('cqbody').innerHTML=(RADAR.cqc&&RADAR.cqc.length?tableRows(RADAR.cqc,'New (12m)',{firstCol:'Clinic niche'}):'<div class="msg">No CQC data this run — check the run log.</div>')+'<div class="note"><b>Every clinic newly registered with CQC</b>, from CQC\'s monthly registration file. The 2-word phrases in their names are clustered into niches, then counted over 1 / 3 / 12 months against the same window a year before. Adult social care (care homes, homecare) is excluded — it\'s churn, not niche formation. A clinic registers <b>before</b> it can legally trade, so this is the supply side committing capital ~6–18 months ahead of revenue. "new" = the phrase did not exist a year ago. Click a column to sort.</div>';
document.querySelectorAll('.panel').forEach(wireSort);

// ---- Wikipedia public interest (client-side) ----
function ym(d){return d.getFullYear()+String(d.getMonth()+1).padStart(2,'0')+'0100';}
function loadWiki(){
  var now=new Date();var end=new Date(now.getFullYear(),now.getMonth(),1); // 1st of this month (exclude partial)
  var start=new Date(end.getFullYear()-2,end.getMonth(),1);
  var titles=Object.keys(WIKI);
  return Promise.all(titles.map(function(title){
    var u='https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/'+
      encodeURIComponent(title.replace(/ /g,'_'))+'/monthly/'+ym(start)+'/'+ym(end);
    return fetch(u).then(function(r){return r.ok?r.json():null;}).then(function(d){
      if(!d||!d.items||d.items.length<15)return null;
      var v=d.items.map(function(x){return x.views;});var n=v.length; // last item = last complete month
      function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
      var last3=mn(n-3,n),prev3=mn(n-6,n-3),prev6=mn(n-9,n-6),year3=mn(n-15,n-12);
      var g3=pct(last3,prev3),gp=pct(prev3,prev6);
      return {name:title,niche:WIKI[title],latest:Math.round(v[n-1]),g1:pct(v[n-1],v[n-2]),g3:g3,
              g12:pct(last3,year3),accel:(g3!=null&&gp!=null)?g3-gp:null};
    }).catch(function(){return null;});
  })).then(function(res){return res.filter(Boolean).sort(function(a,b){return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});});
}

// ---- prescribing (client-side) ----
function loadPresc(){
  return Promise.all(Object.keys(DRUGS).map(function(code){var m=DRUGS[code];
    return fetch('https://openprescribing.net/api/1.0/spending/?code='+code+'&format=json')
      .then(function(r){return r.ok?r.json():null;}).then(function(d){
        if(!d||d.length<15)return null;var v=d.map(function(x){return x.items;});var n=v.length;
        function mn(a,b){var s=v.slice(a,b);return s.reduce(function(x,y){return x+y;},0)/s.length;}
        var last3=mn(n-3,n),prev3=mn(n-6,n-3),prev6=mn(n-9,n-6),year3=mn(n-15,n-12);
        var g3=pct(last3,prev3),gp=pct(prev3,prev6);if(v[n-1]<300)return null;
        return {name:m[0],niche:m[1],treats:m[2],latest:Math.round(v[n-1]),g1:pct(v[n-1],v[n-2]),g3:g3,
                g12:pct(last3,year3),accel:(g3!=null&&gp!=null)?g3-gp:null,date:d[n-1].date};
      }).catch(function(){return null;});
  })).then(function(res){return res.filter(Boolean).sort(function(a,b){return (b.g12==null?-9e9:b.g12)-(a.g12==null?-9e9:a.g12);});});
}

function bul(r,unit){var a=(r.accel!=null&&r.accel>5)?' <span class="accel">accelerating</span>':(r.isnew?' <span class="newtag">new</span>':'');
  return '<li><b>'+r.name+'</b>'+(r.niche?' <span class="niche">'+r.niche+'</span>':'')+' '+
    (r.g12>=0?'<span class="up">':'<span class="dn">')+fmt(r.g12)+'</span> '+unit+a+'</li>';}

function overview(presc){
  var h='<div class="ov big">';
  if(RADAR.trends&&RADAR.trends.length){h+='<h3>Public interest &mdash; Google search demand (12-mth)</h3><ul>';
    RADAR.trends.slice(0,5).forEach(function(r){h+=bul(r,'in search interest');});h+='</ul>';}
  h+='<h3>Prescribing by drug/niche (12-mth)</h3><ul>';
  presc.slice(0,4).forEach(function(r){h+=bul(r,'in prescription volume');});h+='</ul>';
  h+='<h3>New companies by niche (12-mth)</h3><ul>';
  (RADAR.inc||[]).slice(0,4).forEach(function(r){h+=bul(r,'in new companies');});h+='</ul>';
  if(RADAR.cqc&&RADAR.cqc.length){h+='<h3>New CQC-registered clinics by niche (12-mth)</h3><ul>';
    RADAR.cqc.slice(0,4).forEach(function(r){h+=bul(r,'in new clinic registrations');});h+='</ul>';}
  var jb=(RADAR.jobs||[]).slice(0,3);
  h+='<h3>Where hiring is concentrated</h3><ul>';
  jb.forEach(function(r){h+='<li><b>'+r.name+'</b> &mdash; '+num(r.latest)+' live ads</li>';});h+='</ul>';
  h+='<div class="note">Signals ordered earliest&rarr;latest in the demand chain. Search demand (Google Trends) &amp; new-company niches refresh on the server; prescribing is fetched live in your browser. Not investment advice.</div></div>';
  return h;
}

loadPresc().then(function(p){
  if(!p.length){document.getElementById('prbody').innerHTML='<div class="msg">Could not load prescribing.</div>';document.getElementById('ovbody').innerHTML=overview([]);return;}
  document.getElementById('prbody').innerHTML=tableRows(p,'Items / mo',{drug:true,firstCol:'Drug'})+
    '<div class="note">Individual drugs (NHS items, England), each mapped to its niche. <b>Hover a drug</b> for what it treats &amp; its trend. Latest month '+p[0].date+', live in your browser. Click a column to sort.</div>';
  wireSort(document.getElementById('pr'));
  document.getElementById('ovbody').innerHTML=overview(p);
}).catch(function(){document.getElementById('prbody').innerHTML='<div class="msg">Could not load prescribing.</div>';document.getElementById('ovbody').innerHTML=overview([]);});
</script></body></html>"""


if __name__ == "__main__":
    main()
