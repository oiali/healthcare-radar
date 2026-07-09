#!/usr/bin/env python3
"""
UK Healthcare Niche Radar - live build.

Three sources, each ranked by 1 / 3 / 12-month growth + an acceleration flag:
  - NHS prescribing (OpenPrescribing)            - no key
  - New company incorporations by SIC (Companies House) - needs CH_API_KEY
  - Clinician job ads (Adzuna)                   - needs ADZUNA_APP_ID / ADZUNA_APP_KEY

Writes dashboard.html + data.json; accumulates data/adzuna_history.json so the
job-ad trend builds over time. Runs on GitHub Actions (has internet). A source
whose key is missing is skipped and its tab shows an "add key" note. Cannot be
tested in the build sandbox - the first Actions run is the real validation.
"""

import os, json, time, base64, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, date, timedelta
from statistics import mean

try:
    from curl_cffi import requests as _cffi  # browser-TLS client, passes Cloudflare
except Exception:
    _cffi = None

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
      "Accept": "application/json, text/plain, */*",
      "Accept-Encoding": "identity"}


def get_json(url, headers=None, timeout=30, retries=2):
    hdrs = {**UA, **(headers or {})}
    for attempt in range(retries + 1):
        try:
            if _cffi is not None:
                r = _cffi.get(url, headers=hdrs, timeout=timeout, impersonate="chrome")
                if r.status_code == 200:
                    return r.json()
            else:
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1.5)
    return None


def pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / then - 1.0) * 100.0


def add_months(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def metrics_series(v):
    """1/3/12-month growth + acceleration from a monthly value series (ascending)."""
    n = len(v)
    if n < 4:
        return None
    def avg(a, b):
        s = v[a:b]
        return mean(s) if s else None
    last3 = avg(n - 3, n)
    prev3 = avg(n - 6, n - 3) if n >= 6 else None
    prev6 = avg(n - 9, n - 6) if n >= 9 else None
    year3 = avg(n - 15, n - 12) if n >= 15 else None
    g3 = pct(last3, prev3)
    accel = (g3 - pct(prev3, prev6)) if (g3 is not None and pct(prev3, prev6) is not None) else None
    return {"latest": round(v[-1]), "g1": pct(v[-1], v[-2]), "g3": g3,
            "g12": pct(last3, year3), "accel": accel}


def rank(rows):
    rows.sort(key=lambda r: (r["g12"] if r["g12"] is not None else -9e9,
                             r["g3"] if r["g3"] is not None else -9e9), reverse=True)
    return rows


# ---------------------------------------------------------------- prescribing
SECTIONS = {
    "0101": "Dyspepsia & reflux", "0103": "Ulcer healing", "0106": "Laxatives",
    "0202": "Diuretics", "0204": "Beta-blockers", "0205": "Hypertension & heart failure",
    "0206": "Nitrates & calcium blockers", "0208": "Anticoagulants", "0212": "Lipid-regulating",
    "0301": "Bronchodilators", "0302": "Respiratory corticosteroids", "0304": "Antihistamines & allergy",
    "0401": "Hypnotics & anxiolytics", "0402": "Antipsychotics", "0403": "Antidepressants",
    "0404": "CNS stimulants & ADHD", "0406": "Nausea & vertigo", "0407": "Analgesics",
    "0408": "Antiepileptics", "0409": "Parkinson's", "0410": "Substance dependence", "0411": "Dementia",
    "0501": "Antibacterials", "0503": "Antivirals", "0601": "Diabetes", "0602": "Thyroid",
    "0603": "Endocrine corticosteroids", "0604": "Sex hormones (HRT, testosterone)",
    "0606": "Metabolic bone / bisphosphonates", "0607": "Other endocrine",
    "0701": "Obstetrics & gynaecology", "0703": "Contraceptives", "0704": "Bladder, urinary & ED",
    "0801": "Cytotoxics", "0802": "Immunomodulators & biologics", "0901": "Anaemia & blood",
    "1001": "Rheumatic disease & NSAIDs", "1106": "Glaucoma", "1201": "Ear", "1203": "Oropharynx",
    "1301": "Emollients & barrier", "1305": "Psoriasis & eczema", "1306": "Acne", "1404": "Vaccines",
}
MIN_ITEMS = 2000


def prescribing():
    rows = []
    for code, name in SECTIONS.items():
        data = get_json(f"https://openprescribing.net/api/1.0/spending/?code={code}&format=json")
        time.sleep(0.3)
        if not isinstance(data, list) or not data:
            continue
        try:
            v = [float(x["items"]) for x in sorted(data, key=lambda z: z["date"])]
        except Exception:
            continue
        m = metrics_series(v)
        if not m or m["latest"] < MIN_ITEMS:
            continue
        rows.append({"name": name, "code": code, **m})
    return rank(rows)


# ---------------------------------------------------------- companies house
CH_KEY = os.environ.get("CH_API_KEY", "").strip()
SIC = {
    "86101": "Hospital activities", "86102": "Medical nursing home", "86210": "General practice",
    "86220": "Specialist medical practice", "86230": "Dental practice", "86900": "Other human health",
    "96020": "Hairdressing & beauty", "96040": "Physical well-being",
    "87100": "Residential nursing care", "87300": "Residential care (elderly/disabled)",
    "88100": "Social work (elderly/disabled)", "88990": "Other social work",
}


def ch_hits(sic, dfrom, dto):
    url = ("https://api.company-information.service.gov.uk/advanced-search/companies"
           f"?sic_codes={sic}&incorporated_from={dfrom}&incorporated_to={dto}&size=1")
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    d = get_json(url, {"Authorization": "Basic " + auth})
    return d.get("hits") if d else None


def incorporations():
    if not CH_KEY:
        return None
    t = date.today().replace(day=1)
    def r(a, b): return add_months(t, a).isoformat(), add_months(t, b).isoformat()
    rows = []
    for sic, name in SIC.items():
        now3 = ch_hits(sic, *r(-3, 0)); prev3 = ch_hits(sic, *r(-6, -3))
        prev6 = ch_hits(sic, *r(-9, -6)); year3 = ch_hits(sic, *r(-15, -12))
        time.sleep(0.2)
        if now3 is None:
            continue
        g3 = pct(now3, prev3)
        accel = (g3 - pct(prev3, prev6)) if (g3 is not None and pct(prev3, prev6) is not None) else None
        rows.append({"name": name, "code": sic, "latest": now3, "g1": None,
                     "g3": g3, "g12": pct(now3, year3), "accel": accel})
    return rank(rows)


# ------------------------------------------------------------------- adzuna
AZ_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
AZ_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()
TERMS = ["aesthetics", "dermatology", "psychiatry", "ADHD", "menopause", "endocrinology",
         "physiotherapy", "dentist", "optometrist", "audiology", "podiatry", "gynaecology",
         "urology", "cosmetic surgery", "fertility IVF", "private GP"]
HIST = "data/adzuna_history.json"


def adzuna():
    if not (AZ_ID and AZ_KEY):
        return None
    os.makedirs("data", exist_ok=True)
    try:
        hist = json.load(open(HIST))
    except Exception:
        hist = {}
    today = date.today().isoformat()
    for term in TERMS:
        url = ("https://api.adzuna.com/v1/api/jobs/gb/search/1"
               f"?app_id={AZ_ID}&app_key={AZ_KEY}&what={urllib.parse.quote(term)}"
               "&results_per_page=1&content-type=application/json")
        d = get_json(url)
        time.sleep(0.3)
        if not d or "count" not in d:
            continue
        hist.setdefault(term, [])
        hist[term] = [h for h in hist[term] if h[0] != today] + [[today, d["count"]]]
        hist[term].sort()
    json.dump(hist, open(HIST, "w"), indent=1)

    rows = []
    for term, series in hist.items():
        if not series:
            continue
        latest = series[-1][1]
        def ago(days):
            tgt = (date.today() - timedelta(days=days)).isoformat()
            cand = [c for dt, c in series if dt <= tgt]
            return cand[-1] if cand else None
        rows.append({"name": term.title(), "code": "", "latest": latest,
                     "g1": pct(latest, ago(30)), "g3": pct(latest, ago(90)),
                     "g12": pct(latest, ago(365)), "accel": None})
    rows.sort(key=lambda r: (r["g3"] if r["g3"] is not None else -9e9,
                             r["g1"] if r["g1"] is not None else -9e9), reverse=True)
    return rows


# -------------------------------------------------------------------- render
def fmt(x):
    return "&ndash;" if x is None else f"{x:+.0f}%"


def table(rows, latest_label):
    if rows is None:
        return ('<p class="empty">Add the key in GitHub Secrets to activate this source '
                '(CH_API_KEY for incorporations, ADZUNA_APP_ID / ADZUNA_APP_KEY for job ads).</p>')
    if not rows:
        return '<p class="empty">No data yet - the trend builds after a few daily runs.</p>'
    body = []
    for i, r in enumerate(rows):
        acc = '<span class="accel">accelerating</span>' if (r["accel"] and r["accel"] > 5) else ""
        code = f'<span class="code">{r["code"]}</span>' if r["code"] else ""
        body.append(
            f'<tr data-g1="{r["g1"] if r["g1"] is not None else -9999}" '
            f'data-g3="{r["g3"] if r["g3"] is not None else -9999}" '
            f'data-g12="{r["g12"] if r["g12"] is not None else -9999}" '
            f'data-items="{r["latest"]}">'
            f'<td class="rk">{i+1}</td><td class="nm">{r["name"]}{code}</td>'
            f'<td class="num">{r["latest"]:,}</td><td class="num">{fmt(r["g1"])}</td>'
            f'<td class="num">{fmt(r["g3"])}</td><td class="num g12">{fmt(r["g12"])}</td>'
            f'<td class="acc">{acc}</td></tr>')
    return (f'<table><thead><tr><th class="l">#</th><th class="l">Area</th>'
            f'<th data-k="items">{latest_label}</th><th data-k="g1">1-mth</th>'
            f'<th data-k="g3">3-mth</th><th data-k="g12">12-mth</th><th class="l">&nbsp;</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table>')


def render(pres, inc, jobs):
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return TEMPLATE \
        .replace("{{UPDATED}}", updated) \
        .replace("{{T_PRES}}", table(pres, "Items / mo")) \
        .replace("{{T_INC}}", table(inc, "New (3m)")) \
        .replace("{{T_JOBS}}", table(jobs, "Live ads"))


TEMPLATE = """<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Healthcare Niche Radar</title><style>
:root{color-scheme:light}
body{margin:0;background:#fbfbfa;color:#1e2530;font-family:Calibri,"Segoe UI",system-ui,sans-serif;font-size:15px;line-height:1.45}
.wrap{max-width:920px;margin:0 auto;padding:26px 22px 60px}
.head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;border-bottom:2px solid #e7e8ea;padding-bottom:12px}
h1{font-size:21px;margin:0;font-weight:700}.upd{font-size:12.5px;color:#8b929c}
.tabs{display:flex;gap:4px;margin:16px 0 4px}
.tab{padding:7px 14px;font-size:13.5px;border:1px solid #e2e4e8;border-bottom:none;border-radius:7px 7px 0 0;background:#f1f2f4;color:#6b7280;cursor:pointer}
.tab.on{background:#fff;color:#1e2530;font-weight:700}
.panel{display:none;border:1px solid #e7e8ea;border-radius:0 7px 7px 7px;padding:6px 4px}
.panel.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid #eef0f2;text-align:right}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#8b929c;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#1e2530}th.l,td.nm{text-align:left}
td.rk{color:#aab0b8;width:26px;text-align:center}td.nm{font-weight:600}
.code{color:#aab0b8;font-weight:400;font-size:12px;margin-left:8px}
td.num{font-variant-numeric:tabular-nums}td.g12{font-weight:700}
.accel{background:#fde7e7;color:#c23b3b;font-size:11px;font-weight:700;padding:2px 7px;border-radius:20px}
.empty{color:#8b929c;font-size:13px;padding:16px 12px}
.foot{font-size:11.5px;color:#9aa0a8;margin-top:16px}
</style></head><body><div class="wrap">
<div class="head"><h1>UK Healthcare Niche Radar</h1><span class="upd">Updated {{UPDATED}}</span></div>
<div class="tabs">
  <div class="tab on" data-p="p0">Prescribing</div>
  <div class="tab" data-p="p1">New incorporations</div>
  <div class="tab" data-p="p2">Job ads</div>
</div>
<div class="panel on" id="p0">{{T_PRES}}</div>
<div class="panel" id="p1">{{T_INC}}</div>
<div class="panel" id="p2">{{T_JOBS}}</div>
<div class="foot">Ranked by 12-month growth. "Accelerating" = the 3-month growth rate is rising vs the previous 3-month period. Click any timeframe column to re-rank. Prescribing = NHS items (England, monthly); incorporations = Companies House new registrations by SIC (last 3 months); job ads = Adzuna live-ad counts (trend builds over time).</div>
</div><script>
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab,.panel').forEach(e=>e.classList.remove('on'));
  t.classList.add('on');document.getElementById(t.dataset.p).classList.add('on');});
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{
  const tb=th.closest('table').querySelector('tbody'),k=th.dataset.k;
  [...tb.rows].sort((a,b)=>(+b.dataset[k])-(+a.dataset[k])).forEach((r,i)=>{r.cells[0].textContent=i+1;tb.appendChild(r);});});
</script></body></html>"""


def main():
    _t = get_json("https://openprescribing.net/api/1.0/spending/?code=0404&format=json")
    print("DEBUG OP:", (len(_t) if isinstance(_t, list) else _t), "cffi=", _cffi is not None)
    pres = prescribing()
    inc = incorporations()
    jobs = adzuna()
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(),
                   "prescribing": pres, "incorporations": inc, "jobs": jobs}, f, indent=2)
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(render(pres, inc, jobs))
    print(f"prescribing={len(pres) if pres else 0} "
          f"incorporations={len(inc) if inc else 'no-key'} "
          f"jobs={len(jobs) if jobs else 'no-key'}")


if __name__ == "__main__":
    main()
