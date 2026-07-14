#!/usr/bin/env python3
"""
UK Healthcare Niche Radar - build script (runs daily on GitHub Actions).

A GENERAL TREND TRACKER. Not a roll-up / M&A tool. The one question it answers:
    what UK private-pay healthcare niche is rising, and how early am I seeing it?

Sources, ordered by how early they fire:

  CATALYSTS  New UK medicine licences (MHRA via GOV.UK)   YEARS ahead, when a drug
             creates a market. Wegovy was licensed 24 Sep 2021, ~23 months before the
             UK weight-loss boom. Blind to ADHD (no new molecule) - a panel, not a tier.
  T0  NHS RTT waits worsening (NHS England)               the upstream pressure that
             pushes people private at all. Elective care only - blind to weight-loss/ADHD.
  T1  Google search interest (SerpApi)                    weeks, no lag
      + RISING QUERIES harvested from broad seeds = the search-side open layer
  T2  New company incorporations (Companies House)        months
      + a dedicated aesthetics miner, because botox/filler-only clinics are NOT
        CQC-registrable and are therefore invisible to T3
  T3  New CQC clinic registrations                        6-18 months
  T4  NHS prescribing (NHSBSA English Prescribing Dataset) ~2.5-month lag, 12 YEARS of
      history. Runs server-side. (OpenPrescribing served only 60 months and 403s
      datacentre IPs - that window is why the ADHD boom once looked un-backtestable.)

THE OPEN LAYER is the point. A fixed taxonomy of 25 niches can only ever re-rank things
we already thought of; it can never surface the next ADHD. So three sources feed a
DISCOVERY surface of things that map to NO known niche: rising company/clinic name
phrases, rising Google queries, and rising NHS chemicals.

Market structure (who is in a niche: many small operators vs already consolidated) is
CONTEXT only. It never decides a verdict.

Writes dashboard.html + data.json. Persists data/*.json for week-on-week change.
"""

import os, re, json, base64, shutil, zipfile, tempfile, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone, date, timedelta

UA = {"User-Agent": "healthcare-radar"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}
DIAG = {}
# data.json key -> "ok" | "failed", one entry per source-backed payload key. A FAILED
# source must never render as a legitimate empty result ("no new licences found this
# run") - that is the bug class behind the NHSBSA null that once read as "prescribing
# collapsed to zero". The front-end reads this to say "source failed today" instead
# of "there is nothing here".
STATUS = {}


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
from drugs import DRUGS, NICHES_NO_PRESCRIBING   # noqa: E402


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


# Words that are noise as a UNIGRAM but carry the niche when they are the SECOND word
# of a phrase. Omar's own example of the granularity he wants is "peptide therapy" -
# which the original STOP list made structurally impossible to emit.
SERVICE_TAIL = set(("therapy therapies treatment treatments clinic clinics care "
                    "medicine surgery assessment assessments screening testing "
                    "injection injections infusion infusions").split())
STOP_BIGRAM = STOP - SERVICE_TAIL


def grams(name):
    """unigrams + bi/trigrams. A phrase never spans a word we dropped - the old version
    stripped stopwords first and THEN paired, so 'Botox and Filler Clinic' emitted the
    phrase 'botox filler', which nobody had actually written. Short words like 'and'
    must therefore BREAK a run, not vanish before we look."""
    toks = re.findall(r"[a-z]+", (name or "").lower())
    def drop(t):
        return len(t) <= 3 or t in STOP_BIGRAM
    out = {t for t in toks if len(t) > 3 and t not in STOP and t not in SERVICE_TAIL}
    run = []
    for t in toks + [None]:
        if t is not None and not drop(t):
            run.append(t)
            continue
        for i in range(len(run)):                      # phrases live INSIDE a run
            if run[i] in SERVICE_TAIL:
                continue
            if i + 1 < len(run):
                out.add(run[i] + " " + run[i + 1])
            if i + 2 < len(run):
                out.add(run[i] + " " + run[i + 1] + " " + run[i + 2])
        run = []
    return out


CH_PAGE_SIZE = 1000     # documented `size` range is 1..5000. aesthetics.py and
                        # discovery2 page this same endpoint at 1000; 100 here was a
                        # free 10x on the daily call count.


def ch_page(sic, dfrom, dto, start):
    url = ("https://api.company-information.service.gov.uk/advanced-search/companies"
           f"?sic_codes={sic}&incorporated_from={dfrom}&incorporated_to={dto}"
           f"&size={CH_PAGE_SIZE}&start_index={start}")
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
                for g in grams(it.get("company_name")):
                    cnt[g] += 1
            start += CH_PAGE_SIZE
            if len(items) < CH_PAGE_SIZE:
                break
    return cnt


PRIOR_FILE = "data/ch_prior.json"


def _prior_terms(dfrom, dto):
    """The '3 months a year ago' comparison window is IMMUTABLE - an incorporation
    date can never change - yet it was re-mined from Companies House in full every
    day. Cached keyed by the window dates: one mine per month, when the window rolls
    forward."""
    cached = load(PRIOR_FILE) or {}
    if cached.get("window") == [dfrom, dto] and cached.get("counts"):
        return Counter(cached["counts"])
    cnt = name_terms(dfrom, dto)
    if cnt:             # never freeze a CH outage in as "zero prior incorporations"
        save(PRIOR_FILE, {"window": [dfrom, dto], "counts": dict(cnt)})
    return cnt


def ch_total(dfrom, dto):
    """How many NEW HEALTH COMPANIES were incorporated in this window, in total?

    THE CONTROL GROUP. Without it, T2 is not a demand signal at all. The whole UK
    register swings +/-10-12% a year on things that have nothing to do with healthcare
    demand: Companies House raised its incorporation fee from GBP 12 to 50 in May 2024
    and 50 to 100 in Feb 2026, and made identity verification compulsory in Nov 2025.
    A term that grew +30% in a year when ALL health incorporations grew +30% has not
    grown at all. We were reporting that difference as demand. This fixes it.
    """
    tot = 0
    for sic in HEALTH_SICS:
        d = ch_page(sic, dfrom, dto, 0)
        if isinstance(d, dict) and d.get("hits") is not None:
            tot += int(d["hits"])
    return tot or None


def poisson_ci(now, prior):
    """95% interval on a ratio of two small counts (Poisson). 13 -> 29 is +123% --
    and its interval is +16% to +329%. Reporting the point estimate alone is a lie
    about precision. Returns (lo_pct, hi_pct) or None."""
    import math
    if not now or not prior or prior <= 0:
        return None
    # log-ratio SE for two Poisson counts
    se = math.sqrt(1.0 / now + 1.0 / prior)
    r = float(now) / prior
    lo = math.exp(math.log(r) - 1.96 * se)
    hi = math.exp(math.log(r) + 1.96 * se)
    return ((lo - 1) * 100.0, (hi - 1) * 100.0)


def incorporations():
    """T2 ENTRY - founders registering companies to serve a niche.

    READ THIS TIER WITH CARE. An incorporation costs GBP 100 and proves only that
    somebody typed a name into a form. It measures COST OF ENTRY as much as demand,
    so every number here is reported (a) net of the all-health base rate, and
    (b) with a 95% interval, because the counts are tiny.
    """
    if not CH_KEY:
        return None
    t = date.today().replace(day=1)
    w_now = (add_months(t, -3).isoformat(), t.isoformat())
    w_old = (add_months(t, -15).isoformat(), add_months(t, -12).isoformat())

    recent = name_terms(*w_now)
    prior = _prior_terms(*w_old)

    base_now, base_old = ch_total(*w_now), ch_total(*w_old)
    base_g = pct(base_now, base_old) if (base_now and base_old) else None
    DIAG["t2_base"] = {"now": base_now, "prior": base_old, "growth": base_g}

    rows = []
    for term, c in recent.items():
        if c < 4:
            continue
        p = prior.get(term, 0)
        g12 = pct(c, p) if p >= 3 else None
        ci = poisson_ci(c, p) if p >= 3 else None
        # EXCESS over the base rate: how much faster than health incorporations
        # as a whole. This, not g12, is the number that means anything.
        excess = None
        if g12 is not None and base_g is not None:
            excess = ((1 + g12 / 100.0) / (1 + base_g / 100.0) - 1) * 100.0
        rows.append({"name": term, "niche": niche_of(term), "latest": c,
                     "g1": None, "g3": None,
                     "g12": excess if excess is not None else g12,
                     "raw_g12": g12, "excess": excess,
                     "base_growth": base_g,
                     "ci_lo": ci[0] if ci else None, "ci_hi": ci[1] if ci else None,
                     "accel": None, "isnew": p == 0})
    rows.sort(key=lambda r: (r["g12"] is not None,
                             r["g12"] if r["g12"] is not None else 0, r["latest"]), reverse=True)
    return rows[:40]


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
    This is what stops T1 being a fixed watchlist of terms I picked.

    Only real, searchable phrases may pass. aesthetics.py's synthetic aggregate rows
    ("ALL aesthetics-named incorporations", "Save Face accredited clinics (register
    size)") carry the biggest `latest` values in the list, so unfiltered they sat
    permanently in the top discovered slots and burned ~2 paid SerpApi searches a
    week on queries that can never return a timeline."""
    try:
        from aesthetics import TOTAL_ROW as _AT, SF_ROW as _AS
        summary_rows = {_AT, _AS}
    except Exception:                   # keep the filter even if the import breaks
        summary_rows = {"ALL aesthetics-named incorporations",
                        "Save Face accredited clinics (register size)"}
    cands = []
    for r in (cqc_rows or []) + (inc_rows or []):
        n = r.get("name") or ""
        if n in summary_rows:           # aesthetics' summary rows are not phrases
            continue
        if len(n.split()) < 2:          # need a real phrase to be a searchable query
            continue
        if "(" in n or ")" in n or n.startswith("ALL "):
            continue                    # aggregate / annotated rows are not queries
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
    cached = load(TR_FILE) or {}
    last = cached.get("date")
    fresh = False
    if last:
        try:
            fresh = (date.today() - date.fromisoformat(last)).days < 7
        except Exception:
            fresh = False
    if fresh:                      # refreshed within the last 7 days - do NOT spend quota
        return cached.get("rows") or []
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
    save(TR_FILE, {"rows": rows, "date": date.today().isoformat()})   # stamped even if empty
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


CQC_ODS_PATH = os.path.join(tempfile.gettempdir(), "cqc.ods")


def load_ods_rows(path):
    """Parse the .ods content.xml ONCE into an in-memory [(sheet, [cell, ...])] list.

    investability.ods_rows is the careful parser (covered-table-cells, repeated rows)
    that targets.scan_providers and discovery2 already stream with, so every consumer
    of the shared parse sees identical rows; the local ods_rows is only the fallback
    if that import breaks. Cell strings are interned through a memo - the file is
    ~57k rows whose sector/region/flag cells repeat massively, so the list costs tens
    of MB rather than hundreds."""
    try:
        from investability import ods_rows as _parser
    except Exception:
        _parser = ods_rows
    memo = {}
    out = []
    for sheet, row in _parser(path):
        out.append((memo.setdefault(sheet, sheet),
                    [memo.setdefault(c, c) for c in row]))
    return out


def fetch_cqc_ods():
    """Download the CQC active-locations file and parse it ONCE for every consumer.

    Returns {"anchor": date, "rows": [(sheet, row), ...]} or None. This 24MB file
    used to be iterparsed FOUR times per build (cqc(), investability2's provider
    scan, discovery2's two-pass mine) at ~1-2 min per pass on an Actions runner -
    the single biggest piece of the 20-minute builds."""
    url = cqc_file_url()
    DIAG["url"] = url or "page fetch failed / link not found"
    if not url:
        return None
    m = re.search(r"/(\d{2})_([A-Za-z]+)_(\d{4})_HSCA", url)
    anchor = (date(int(m.group(3)), MONTHS.get(m.group(2).lower(), 1), int(m.group(1)))
              if m else date.today())
    try:
        download(url, CQC_ODS_PATH)
        DIAG["bytes"] = os.path.getsize(CQC_ODS_PATH)
    except Exception as e:
        DIAG["download_error"] = repr(e)[:160]
        return None
    try:
        rows = load_ods_rows(CQC_ODS_PATH)
    except Exception as e:
        DIAG["parse_error"] = repr(e)[:160]
        return None
    DIAG["ods_rows_parsed"] = len(rows)
    return {"anchor": anchor, "rows": rows}


def cqc(ods):
    """T3 CAPACITY - new clinic registrations, counted off the SHARED parse."""
    if not ods:
        return None
    anchor = ods["anchor"]

    W = {"m1": (1, 0), "m1p": (2, 1), "m3": (3, 0), "m3p": (6, 3),
         "m12": (12, 0), "m12p": (24, 12)}
    bounds = {k: (add_months(anchor, -a), add_months(anchor, -b)) for k, (a, b) in W.items()}
    cnt = {k: Counter() for k in W}
    i_name = i_date = i_type = None
    rows_seen = kept = 0
    sectors = Counter()

    for sheet, row in ods["rows"]:
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
        gs = grams(row[i_name])
        if not gs:
            continue
        hit = False
        for k, (lo, hi) in bounds.items():
            if lo <= d < hi:
                hit = True
                for g in gs:
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


def whats_moved(tr, inc, cq, presc=None):
    """Compare the early tiers (T1-T3) to ~7 days ago. T4 is client-side so excluded."""
    snap = {"date": date.today().isoformat(),
            "t1": agg(tr), "t2": agg(inc), "t3": agg(cq), "t4": agg(presc or [])}
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
        return sum(1 for t in ("t1", "t2", "t3", "t4")
                   if (h.get(t) or {}).get(n) is not None and h[t][n] >= RISING)
    names = set()
    for t in ("t1", "t2", "t3", "t4"):
        names |= set(snap[t])
    out = []
    for n in names:
        now, was = fired(snap, n), fired(prev, n)
        if now > was and now >= 1:
            out.append({"niche": n, "from": was, "to": now, "since": prev["date"]})
    out.sort(key=lambda x: (x["to"], x["to"] - x["from"]), reverse=True)
    return out[:8]


# ------------------------------------------------------------------- render
SOURCE_BUDGET = int(os.environ.get("SOURCE_BUDGET_SECS", "420"))   # 7 minutes each


class _Timeout(Exception):
    pass


def safe(fn, label, *a, **k):
    """A dead source must degrade the dashboard, never kill or hang the build.

    HARD WALL-CLOCK BUDGET. A source that is BLOCKED rather than broken (connections
    refused, sockets timing out - which is what the Internet Archive and OpenPrescribing
    both do to GitHub's datacentre IPs) will sit there retrying until the 6-hour job
    limit kills it. That happened: two consecutive daily builds had to be cancelled and
    the dashboard went stale. Per-request timeouts do not save you. Only a wall clock does.
    """
    import signal
    key = k.pop("key", None)

    def _bang(signum, frame):
        raise _Timeout()

    old = None
    try:
        old = signal.signal(signal.SIGALRM, _bang)
        signal.alarm(SOURCE_BUDGET)
    except Exception:
        old = None                      # not POSIX - run without the wall clock
    t0 = datetime.now(timezone.utc)
    try:
        r = fn(*a, **k)
        secs = (datetime.now(timezone.utc) - t0).total_seconds()
        if r is None:
            print(f"  {label}: unavailable (source returned None) [{secs:.0f}s]")
            DIAG.setdefault("failed_sources", []).append(label)
            if key:
                STATUS[key] = "failed"
            return None
        print(f"  {label}: {len(r) if hasattr(r, '__len__') else 'ok'} [{secs:.0f}s]")
        if key:
            STATUS[key] = "ok"
        return r
    except _Timeout:
        print(f"  {label}: TIMED OUT after {SOURCE_BUDGET}s - abandoned, build continues")
        DIAG.setdefault("failed_sources", []).append(label + " (timed out)")
        DIAG.setdefault("timed_out", []).append(label)
        if key:
            STATUS[key] = "failed"
        return None
    except Exception as e:
        print(f"  {label}: FAILED {repr(e)[:120]}")
        DIAG.setdefault("failed_sources", []).append(label)
        if key:
            STATUS[key] = "failed"
        return None
    finally:
        try:
            signal.alarm(0)
            if old is not None:
                signal.signal(signal.SIGALRM, old)
        except Exception:
            pass


def main():
    import nhs_rtt, aesthetics as aes_mod, investability2 as inv2
    import discovery2 as disc_mod, interpret as interp
    import nhsbsa_epd, trends_open as t_open, catalysts as cat_mod

    inc = safe(incorporations, "T2 incorporations", key="inc") or []
    ods = safe(fetch_cqc_ods, "CQC ods (one download, ONE shared parse)")
    cq = safe(cqc, "T3 cqc", ods, key="cqc") or []
    aes = safe(aes_mod.aesthetics, "T2b aesthetics", key="aes") or []
    waits = safe(nhs_rtt.rtt, "T0 nhs waits", key="waits") or []

    # Investability on ECONOMIC OWNERS, not legal entities. A PE group holding 12 Ltds
    # looked like 12 independents - that flattered every fragmentation number, and it is
    # the number he would underwrite on. Also splits fragmentation-of-infancy (a gold
    # rush nobody has consolidated because it just appeared) from fragmentation-of-
    # maturity (a real, tired, sellable population). Opposite trades; HHI scored them alike.
    invest = safe(inv2.investability2, "investability (economic owners)", niche_of,
                  path=CQC_ODS_PATH, rows=(ods or {}).get("rows"),
                  ch_budget=250, key="invest") or {}
    if not invest:
        STATUS["invest"] = "failed"     # investability2 signals failure with {}

    # THE OPEN LAYER. 25 fixed niches structurally cannot surface the next ADHD.
    # This is the residue: rising phrases that match NO known niche - the only place
    # a genuinely new niche can appear. Distinct-operator count is the discriminator
    # that separates a real service from one company's brand.
    ops = safe(disc_mod.mine_cqc_ods, "cqc operator-level mine",
               (ods or {}).get("rows") or CQC_ODS_PATH) or {}
    disc = safe(disc_mod.discovery2, "discovery (open layer)", inc, ops or cq, aes,
                key="disc") or []
    if not ops:
        # Without the CQC operator corpus the open layer cannot surface anything:
        # an empty disc here is a FAILED source, not "nothing cleared the bar".
        STATUS["disc"] = "failed"
    ods = None        # ~57k parsed rows; every consumer has run - release them

    # T4 now runs SERVER-SIDE off NHSBSA's own Open Data Portal: 12 years of history
    # (back to Jan 2014), no API key, and it answers datacentre IPs. OpenPrescribing
    # served only 60 months and 403s Actions, which is why T4 used to be client-side.
    # Real lag is ~2.5 months, not the 12+ we assumed.
    presc = safe(nhsbsa_epd.epd, "T4 prescribing (NHSBSA)", key="presc") or []
    tracked = [r for r in presc if r.get("kind") != "discovery"]
    drugdisc = [r for r in presc if r.get("kind") == "discovery"]
    STATUS["drugdisc"] = STATUS.get("presc", "failed")

    # SEARCH-SIDE OPEN LAYER: Google's own RISING queries, harvested from broad seeds on
    # a rotating budget. A fixed watchlist can never surface a term nobody thought of;
    # this can. Rows whose niche is None are the discovery rows.
    topen = safe(t_open.trends_open, "T1b rising queries", key="topen") or []

    # CATALYSTS: new UK medicine licences for LARGE-population conditions. The earliest,
    # hardest signal there is - a licence lands years before the market. Wegovy was
    # licensed 24 Sep 2021, ~23 months before the UK weight-loss boom. Blind to ADHD
    # (no new molecule created it), so it is a side panel, never a scoring tier.
    cats = safe(cat_mod.catalysts, "Catalysts (MHRA licences)", key="cats") or []

    # ADOPTION, not entry - the one sensor that can see an EXISTING clinic add a service
    # (it files no company and registers no location; it changes a page on its website).
    #
    # BUT: the Internet Archive REFUSES GitHub's datacentre IPs. Verified - the cohort
    # built fine (207 clinics) and then every single CDX call came back
    # ConnectionRefused / timed out. Same class of block as OpenPrescribing. So the panel
    # is NOT fetched here. It is backfilled from a real browser and committed, and this
    # just reads the result. Never let a blocked source hang the daily build.
    pnl = load("data/panel_rows.json", []) or []
    STATUS["panel"] = "ok" if pnl else "failed"
    DIAG["panel"] = ("read %d rows from the committed backfill" % len(pnl)) if pnl else \
        "no backfill yet - the Internet Archive blocks datacentre IPs, so this must be run from a browser"

    tr = safe(trends, "T1 trends", discovered_terms(inc, cq + aes), key="trends") or []
    # Terms fed back from T2/T3 keep found=True and are shown, but get ZERO votes: if T1
    # only lights up because T2 told it what to search for, "T1 and T2 agree" is plumbing,
    # not evidence. The front-end enforces this via aggB(independentOnly).
    tr_indep, tr_found = interp.decontaminate(tr)
    DIAG["t1_independent"] = len(tr_indep)
    DIAG["t1_auto_found"] = len(tr_found)
    jobs = []          # Adzuna REMOVED: its ToS forbids aggregation/vacancy counts.
    moved = whats_moved(tr_indep, inc, cq, tracked)

    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    data = {"waits": waits, "trends": tr, "inc": inc, "aes": aes, "cqc": cq,
            "jobs": jobs, "moved": moved, "invest": invest, "disc": disc,
            "presc": tracked, "drugdisc": drugdisc, "topen": topen, "cats": cats,
            "panel": pnl,
            "status": STATUS, "diag": DIAG, "drugs": DRUGS,
            "nopresc": NICHES_NO_PRESCRIBING}
    payload = json.dumps(data).replace("</", "<\\/")
    save("data.json", dict(updated=datetime.now(timezone.utc).isoformat(), **data))
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(TEMPLATE.replace("{{UPDATED}}", updated).replace("{{DATA}}", payload))

    # THE PRE-REGISTERED FORECAST LOG. A backtest looks backwards and can be tuned until
    # it agrees with us. A forward call, timestamped and hash-chained before the fact,
    # cannot be. Each week it freezes the radar's top 3 AND draws a random control niche
    # from the same board: if the picks do not beat random, the radar has no skill and
    # the log will say so. This is the only mechanism that can ever earn this thing trust,
    # and the clock only starts once. It will say "too few matured calls to say anything"
    # for about a year. That is correct, and it must keep saying it.
    try:
        import forecast as fc
        picks, graded, card = fc.forecast(data)
        DIAG["forecast"] = {"picks": len(picks or []), "graded": len(graded or []),
                            "verdict": (card or {}).get("verdict")}
        print("  forecast:", (card or {}).get("verdict", "logged"))
    except Exception as e:
        print("  forecast FAILED:", repr(e)[:120])

    try:
        import digest as dg
        subject, md, html = dg.digest(data, load(HIST_FILE, []) or [])
        open("digest.md", "w", encoding="utf-8").write(md or "# No digest this run\n")
        open("digest.html", "w", encoding="utf-8").write(
            html or "<!DOCTYPE html><meta charset=utf-8><p>No digest this run.</p>")
        print("  digest:", subject)
    except Exception as e:
        print("  digest FAILED:", repr(e)[:120])
        open("digest.html", "w", encoding="utf-8").write(
            "<!DOCTYPE html><meta charset=utf-8><p>Digest failed to build.</p>")

    print(f"waits={len(waits)} trends={len(tr)} inc={len(inc)} aes={len(aes)} cqc={len(cq)} "
          f"presc={len(tracked)} drugdisc={len(drugdisc)} invest={len(invest)} "
          f"discovery={len(disc)} topen={len(topen)} catalysts={len(cats)} "
          f"panel={len(pnl)} moved={len(moved)}")


from template import TEMPLATE


if __name__ == "__main__":
    main()
