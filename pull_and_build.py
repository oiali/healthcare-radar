#!/usr/bin/env python3
"""
UK Healthcare Niche Radar - build script (runs daily on GitHub Actions).

Sources are STACKED by how early they fire in the demand chain:

  T0  PRESSURE    NHS RTT waits worsening (NHS England)        the causal driver
  T1  INTENT      Google search interest (SerpApi)             weeks,   0 lag
  T2  ENTRY       New company incorporations (Companies House) months,  days lag
                  + a dedicated aesthetics miner, because botox/filler-only clinics
                    are NOT CQC-registrable and are invisible to T3
  T3  CAPACITY    New CQC clinic registrations + job ads       6-18 mth, monthly
  T4  CONSUMPTION NHS prescribing (OpenPrescribing)            12+ mth, 2-mth lag

Plus an INVESTABILITY layer: target density + fragmentation per niche, because a
rising niche with no acquirable population of independent operators is not a roll-up.

Every source is mapped onto a SHARED niche taxonomy so the same niche can be
tracked across all four tiers. The Stack tab shows, per niche, which tiers have
fired -> how far along the chain it is -> whether it is still early.

Writes dashboard.html + data.json.
Persists data/trends.json, data/trend_terms.json, data/adzuna_history.json,
data/history.json (for the week-on-week "what moved" panel).
"""

import os, re, json, base64, shutil, zipfile, tempfile, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone, date, timedelta

UA = {"User-Agent": "healthcare-radar"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}
DIAG = {}


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


def load(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default


def save(path, obj):
    os.makedirs("data", exist_ok=True)
    json.dump(obj, open(path, "w"), indent=1)


# ==================================================== SHARED NICHE TAXONOMY
# Fixed matcher: keys ending "*" are stem matches (dermatolog*), all others must
# match as WHOLE WORDS. The old prefix-only matcher mis-classified 30 of 35 test
# names ("Skinner"->skin->Aesthetics, "Brown"->brow, "Lipscomb"->lip).
from taxonomy import NICHES, niche_of          # noqa: E402
from drugs import DRUGS, NICHE_QUERY, NICHES_NO_PRESCRIBING   # noqa: E402


# ============================ Companies House: auto-discover niches from names
CH_KEY = os.environ.get("CH_API_KEY", "").strip()
# 86210 general medical practice is the highest-value addition: it is where the
# ADHD / menopause / GLP-1 telehealth operators actually register. 47730 dispensing
# chemist catches the online-pharmacy weight-loss/hair/ED model. 96090 deliberately
# EXCLUDED (catch-all: tattooists, dating agencies). 96020 kept but is itself a
# flood risk - mostly high-street hairdressers - which the STOP list absorbs.
HEALTH_SICS = ["86900", "86220", "96020", "96040",
               "86210", "86230", "47730", "47782", "86101"]
STOP = set(("the and of for to in a an ltd limited uk gb london clinic clinics health "
            "healthcare care medical medicine group holdings company co consulting consultancy "
            "practice practices centre center llp cic community trust nhs solutions services "
            "service management associates partners international global national services "
            "wellbeing well being ltd co uk therapy therapies treatment treatments and "
            "devon cornwall essex kent surrey sussex yorkshire lancashire cheshire midlands "
            "forest first best new prime elite smart digital online mobile home family city "
            "north south east west greater park house lodge road street hall court view green "
            "hill professional quality complete total pure life live your local premier "
            "head office site main branch room rooms suite villa manor "
            "hospital hospitals private clinical doctor doctors surgeon surgeons nurse "
            "clear trading integrated little address remote connect harmony retreat "
            "grove square royal gate cross mount chapel abbey priory spring meadow "
            "leigh vale bank field brook stone white black gold silver star crown "
            "manchester birmingham bristol oxford cotswold dartford worcester epsom "
            "leeds liverpool sheffield nottingham glasgow cardiff edinburgh brighton "
            "reading coventry leicester newcastle norwich cambridge york derby stoke "
            "wolverhampton swansea belfast aberdeen dundee harley wimpole chelsea "
            "kensington marylebone mayfair richmond croydon bromley watford slough "
            "wales scotland ireland england britain british anglia "
            "until headquarters central partnership unit units floor").split())


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
        for _ in range(12):
            d = ch_page(sic, dfrom, dto, start)
            items = d.get("items") if d else None
            if not items:
                break
            for it in items:
                nm = (it.get("company_name") or "").lower()
                toks = [t for t in re.findall(r"[a-z]+", nm) if len(t) > 3 and t not in STOP]
                for i in range(len(toks)):
                    cnt[toks[i]] += 1
                    if i < len(toks) - 1:
                        cnt[toks[i] + " " + toks[i + 1]] += 1
            start += 100
            if len(items) < 100:
                break
    return cnt


def incorporations():
    """T2 ENTRY - founders registering companies to serve a niche."""
    if not CH_KEY:
        return None
    t = date.today().replace(day=1)
    recent = name_terms(add_months(t, -3).isoformat(), t.isoformat())
    prior = name_terms(add_months(t, -15).isoformat(), add_months(t, -12).isoformat())
    rows = []
    for term, c in recent.items():
        if c < 4:
            continue
        p = prior.get(term, 0)
        rows.append({"name": term, "niche": niche_of(term), "latest": c,
                     "g1": None, "g3": None,
                     "g12": pct(c, p) if p >= 3 else None,
                     "accel": None, "isnew": p == 0})
    rows.sort(key=lambda r: (r["g12"] is not None,
                             r["g12"] if r["g12"] is not None else 0, r["latest"]), reverse=True)
    return rows[:40]


# ==================================================== T3b Adzuna job ads
AZ_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
AZ_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()
AZ_FILE = "data/adzuna_history.json"
TERMS = ["aesthetics", "dermatology", "psychiatry", "ADHD", "menopause", "endocrinology",
         "physiotherapy", "dentist", "optometrist", "audiology", "podiatry", "gynaecology",
         "urology", "cosmetic surgery", "fertility IVF", "private GP"]


def adzuna():
    """T3 CAPACITY (support) - hiring to serve demand. Growth accrues from our own history."""
    if not (AZ_ID and AZ_KEY):
        return None
    hist = load(AZ_FILE, {}) or {}
    today = date.today().isoformat()
    snap = hist.get(today, {})
    for term in TERMS:
        if term in snap:
            continue
        url = ("https://api.adzuna.com/v1/api/jobs/gb/search/1"
               f"?app_id={AZ_ID}&app_key={AZ_KEY}&what={urllib.parse.quote(term)}"
               "&results_per_page=1&content-type=application/json")
        d = get_json(url)
        if d and "count" in d:
            snap[term] = d["count"]
    hist[today] = snap
    # keep 400 days
    for k in sorted(hist)[:-400]:
        hist.pop(k, None)
    save(AZ_FILE, hist)

    def back(days):
        target = (date.today() - timedelta(days=days)).isoformat()
        keys = [k for k in sorted(hist) if k <= target]
        return hist.get(keys[-1]) if keys else None

    b30, b90, b365 = back(30), back(90), back(365)
    rows = []
    for term, c in snap.items():
        rows.append({"name": term.title(), "niche": niche_of(term), "latest": c,
                     "g1": pct(c, (b30 or {}).get(term)),
                     "g3": pct(c, (b90 or {}).get(term)),
                     "g12": pct(c, (b365 or {}).get(term)),
                     "accel": None})
    rows.sort(key=lambda x: x["latest"], reverse=True)
    return rows


# ==================================================== T1 INTENT: Google Trends
SERP = os.environ.get("SERPAPI_KEY", "").strip()
CORE_Q = ["Mounjaro", "Wegovy", "ADHD assessment", "menopause clinic",
          "testosterone replacement", "hair transplant", "botox", "dermal filler",
          "erectile dysfunction", "weight loss injection", "peptide therapy",
          "private ADHD", "HRT", "tongue tie", "private ultrasound"]
TR_FILE = "data/trends.json"
TERMS_FILE = "data/trend_terms.json"


def discovered_terms(inc_rows, cqc_rows, limit=5):
    """Feed the phrases DISCOVERED by the supply-side sources back into search.
    This is what stops T1 being a fixed watchlist of terms I picked."""
    cands = []
    for r in (cqc_rows or []) + (inc_rows or []):
        n = r.get("name") or ""
        if len(n.split()) < 2:          # need a real phrase to be a searchable query
            continue
        cands.append((r.get("latest") or 0, n))
    cands.sort(reverse=True)
    out = []
    for _, n in cands:
        if n not in out and n not in CORE_Q:
            out.append(n)
        if len(out) >= limit:
            break
    return out


def trends(extra):
    """T1 INTENT - earliest signal. Weekly refresh to conserve SerpApi quota."""
    if not SERP:
        return None
    terms = CORE_Q + [t for t in extra if t not in CORE_Q]
    save(TERMS_FILE, {"core": CORE_Q, "discovered": extra, "date": date.today().isoformat()})
    cached = load(TR_FILE)
    if cached and cached.get("rows") and date.today().weekday() != 0:
        return cached.get("rows")
    rows = []
    for q in terms:
        url = ("https://serpapi.com/search.json?engine=google_trends"
               f"&q={urllib.parse.quote(q)}&geo=GB&data_type=TIMESERIES"
               "&date=today%2012-m&api_key=" + SERP)
        d = get_json(url)
        try:
            tl = d["interest_over_time"]["timeline_data"]
            v = [pt["values"][0]["extracted_value"] for pt in tl]
        except Exception:
            continue
        if len(v) < 20:
            continue
        last = mean(v[-4:])
        g3 = pct(last, mean(v[-17:-13]))
        rows.append({"name": q, "niche": niche_of(q), "latest": round(last),
                     "g1": pct(last, mean(v[-8:-4])),
                     "g3": g3,
                     "g12": pct(last, mean(v[:4])),
                     "accel": None,
                     "found": q not in CORE_Q})
    rows.sort(key=lambda x: (x["g12"] if x["g12"] is not None else -9e9), reverse=True)
    save(TR_FILE, {"rows": rows, "date": date.today().isoformat()})
    return rows


# ============================ T3 CAPACITY: CQC new clinic registrations
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
    """Stream (sheet, row). The CQC file's first sheet is a README, not data."""
    sheet = ""
    with zipfile.ZipFile(path) as zf, zf.open("content.xml") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            if ev == "start":
                if el.tag == NS_T + "table":
                    sheet = el.get(NS_T + "name") or ""
                continue
            if el.tag != NS_T + "table-row":
                continue
            row = []
            for c in el.findall(NS_T + "table-cell"):
                rep = int(c.get(NS_T + "number-columns-repeated") or 1)
                v = c.get(NS_O + "date-value") or ""
                v = v[:10] if v else " ".join(
                    "".join(p.itertext()) for p in c.findall(NS_TX + "p")).strip()
                for _ in range(rep):
                    row.append(v)
                    if len(row) >= max_cols:
                        break
                if len(row) >= max_cols:
                    break
            el.clear()
            yield sheet, row


def parse_date(s):
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})[/\-]([A-Za-z]{3,9})[/\-](\d{4})", s)
    if m:
        mon = next((v for k, v in MONTHS.items()
                    if k.startswith(m.group(2).lower()[:3])), None)
        if mon:
            return date(int(m.group(3)), mon, int(m.group(1)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def cqc():
    url = cqc_file_url()
    DIAG["url"] = url or "page fetch failed / link not found"
    if not url:
        return None
    m = re.search(r"/(\d{2})_([A-Za-z]+)_(\d{4})_HSCA", url)
    anchor = (date(int(m.group(3)), MONTHS.get(m.group(2).lower(), 1), int(m.group(1)))
              if m else date.today())
    path = os.path.join(tempfile.gettempdir(), "cqc.ods")
    try:
        download(url, path)
        DIAG["bytes"] = os.path.getsize(path)
    except Exception as e:
        DIAG["download_error"] = repr(e)[:160]
        return None

    W = {"m1": (1, 0), "m1p": (2, 1), "m3": (3, 0), "m3p": (6, 3),
         "m12": (12, 0), "m12p": (24, 12)}
    bounds = {k: (add_months(anchor, -a), add_months(anchor, -b)) for k, (a, b) in W.items()}
    cnt = {k: Counter() for k in W}
    i_name = i_date = i_type = None
    rows_seen = kept = 0
    sectors = Counter()

    for sheet, row in ods_rows(path):
        if i_name is None:
            low = [c.strip().lower() for c in row]
            short = [c if len(c) < 70 else "" for c in low]
            if "location id" not in short:
                continue

            def find(*subs):
                for j, c in enumerate(short):
                    if c and all(s in c for s in subs):
                        return j
                return None
            i_name = find("location", "name")
            i_date = find("hsca start date") or find("start date")
            i_type = find("location", "type") or find("sector")
            DIAG["sheet"] = sheet
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
        # private-pay clinic universe only. Social care = churn; NHS + dental = formulaic
        # naming that swamps everything.
        if "independent healthcare" not in sector.lower():
            continue
        toks = [t for t in re.findall(r"[a-z]+", (row[i_name] or "").lower())
                if len(t) > 3 and t not in STOP]
        grams = set(toks) | {toks[j] + " " + toks[j + 1] for j in range(len(toks) - 1)}
        if not grams:
            continue
        hit = False
        for k, (lo, hi) in bounds.items():
            if lo <= d < hi:
                hit = True
                for g in grams:
                    cnt[k][g] += 1
        kept += hit

    DIAG.update({"anchor": str(anchor), "rows_data": rows_seen, "in_window": kept,
                 "sectors": sectors.most_common(8), "grams": len(cnt["m12"])})

    rows = []
    for g, c12 in cnt["m12"].items():
        if c12 < 4:
            continue
        p12 = cnt["m12p"][g]
        g12 = pct(c12, p12) if p12 >= 3 else None
        g3 = pct(cnt["m3"][g], cnt["m3p"][g]) if cnt["m3p"][g] >= 3 else None
        g1 = pct(cnt["m1"][g], cnt["m1p"][g]) if cnt["m1p"][g] >= 3 else None
        rows.append({"name": g, "niche": niche_of(g), "latest": c12,
                     "g1": g1, "g3": g3, "g12": g12,
                     "accel": (g3 - g12) if (g3 is not None and g12 is not None) else None,
                     "isnew": p12 == 0})
    rows.sort(key=lambda r: (r["g12"] is not None,
                             r["g12"] if r["g12"] is not None else 0, r["latest"]), reverse=True)
    return rows[:40]


# ==================================== week-on-week memory: what actually moved
HIST_FILE = "data/history.json"
RISING = 10.0          # a tier "fires" at >= +10% 12-mth


def agg(rows):
    """volume-weighted 12-mth growth per niche"""
    m = {}
    for r in rows or []:
        n, g = r.get("niche"), r.get("g12")
        if not n or g is None:
            continue
        w = max(r.get("latest") or 1, 1)
        a = m.setdefault(n, [0.0, 0.0])
        a[0] += w
        a[1] += w * g
    return {k: v[1] / v[0] for k, v in m.items() if v[0]}


def whats_moved(tr, inc, cq):
    """Compare the early tiers (T1-T3) to ~7 days ago. T4 is client-side so excluded."""
    snap = {"date": date.today().isoformat(),
            "t1": agg(tr), "t2": agg(inc), "t3": agg(cq)}
    hist = load(HIST_FILE, []) or []
    hist = [h for h in hist if h.get("date") != snap["date"]] + [snap]
    hist = hist[-60:]
    save(HIST_FILE, hist)

    target = (date.today() - timedelta(days=7)).isoformat()
    older = [h for h in hist[:-1] if h["date"] <= target]
    if not older:
        return []
    prev = older[-1]

    def fired(h, n):
        return sum(1 for t in ("t1", "t2", "t3")
                   if (h.get(t) or {}).get(n) is not None and h[t][n] >= RISING)
    names = set()
    for t in ("t1", "t2", "t3"):
        names |= set(snap[t])
    out = []
    for n in names:
        now, was = fired(snap, n), fired(prev, n)
        if now > was and now >= 1:
            out.append({"niche": n, "from": was, "to": now, "since": prev["date"]})
    out.sort(key=lambda x: (x["to"], x["to"] - x["from"]), reverse=True)
    return out[:8]


# ------------------------------------------------------------------- render
def safe(fn, label, *a, **k):
    """A dead source must degrade the dashboard, never kill the build."""
    try:
        r = fn(*a, **k)
        print(f"  {label}: {len(r) if hasattr(r,'__len__') else 'ok'}")
        return r
    except Exception as e:
        print(f"  {label}: FAILED {repr(e)[:120]}")
        DIAG.setdefault("failed_sources", []).append(label)
        return None


def main():
    import nhs_rtt, aesthetics as aes_mod, investability as inv_mod

    inc = safe(incorporations, "T2 incorporations") or []
    cq = safe(cqc, "T3 cqc") or []
    aes = safe(aes_mod.aesthetics, "T2b aesthetics") or []
    waits = safe(nhs_rtt.rtt, "T0 nhs waits") or []
    # investability re-uses the CQC .ods already on disk - one extra pass, no bandwidth
    invest = safe(inv_mod.investability, "investability", niche_of,
                  path=os.path.join(tempfile.gettempdir(), "cqc.ods")) or {}
    tr = safe(trends, "T1 trends", discovered_terms(inc, cq + aes)) or []
    jobs = safe(adzuna, "T3b jobs") or []
    moved = whats_moved(tr, inc, cq)

    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    data = {"waits": waits, "trends": tr, "inc": inc, "aes": aes, "cqc": cq,
            "jobs": jobs, "moved": moved, "invest": invest, "diag": DIAG,
            "drugq": NICHE_QUERY, "drugs": DRUGS, "nopresc": NICHES_NO_PRESCRIBING}
    payload = json.dumps(data).replace("</", "<\\/")
    save("data.json", dict(updated=datetime.now(timezone.utc).isoformat(), **data))
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(TEMPLATE.replace("{{UPDATED}}", updated).replace("{{DATA}}", payload))

    # Weekly digest (Mondays) - gated inside digest.py
    try:
        import digest as dg
        subject, md, html = dg.digest(data, load(HIST_FILE, []) or [])
        open("digest.md", "w", encoding="utf-8").write(md or "# No digest this run\n")
        open("digest.html", "w", encoding="utf-8").write(
            html or "<!DOCTYPE html><meta charset=utf-8><p>No digest this run.</p>")
        print("  digest written:", subject)
    except Exception as e:
        print("  digest FAILED:", repr(e)[:120])
        open("digest.html", "w", encoding="utf-8").write(
            "<!DOCTYPE html><meta charset=utf-8><p>Digest failed to build.</p>")

    print(f"waits={len(waits)} trends={len(tr)} inc={len(inc)} aes={len(aes)} "
          f"cqc={len(cq)} jobs={len(jobs)} invest={len(invest)} moved={len(moved)}")


from template import TEMPLATE


if __name__ == "__main__":
    main()
