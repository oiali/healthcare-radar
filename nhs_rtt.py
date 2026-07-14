#!/usr/bin/env python3
"""
TIER 0 - NHS RTT (Referral to Treatment) consultant-led waiting times.

WHY THIS IS TIER 0
------------------
Every other tier on the radar measures demand AFTER it has appeared (searches,
incorporations, clinic registrations, prescribing). RTT measures the CAUSE: when
the NHS wait for a specialty deteriorates, patients who can pay go private. So we
do NOT track total waiting-list volume - a big list that is being cleared quickly
sends nobody private. We track the COUNT OF PEOPLE WAITING OVER 18 WEEKS, and the
growth (g1/g3/g12) is measured on THAT count. Rising >18wk waits = private demand
about to appear.

VERIFIED SOURCE (checked 2026-07-13 against the real files, not from memory)
---------------------------------------------------------------------------
Landing page:  https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/
Year pages:    .../rtt-waiting-times/rtt-data-2026-27/  (and 2025-26, ...)
Monthly file:  "Full CSV data file <Mon><YY> (ZIP, 3M)"
  e.g. https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/
       Full-CSV-data-file-May26-ZIP-3M-3jBgba.zip

The URL CANNOT be constructed - it must be scraped. Two reasons, both verified:
  1. WordPress appends a random hash: ...-3jBgba.zip, ...-X7gGnn.zip, ...-WL5BiP.zip
  2. The /YYYY/MM/ upload folder is NOT the data month. Apr25 data lives under
     /2026/02/ because it was revised. Revised files are named "...-revised.zip"
     or "...-revised-2.zip" instead of carrying a hash.

FORMAT: .zip containing ONE plain CSV (e.g. "20260531-RTT-May-2026-full-extract.csv",
~80 MB uncompressed, ~157k rows, 121 columns). Plain CSV -> zipfile + csv from the
stdlib parse it fine. The other monthly files are .xlsx and are NOT used.

REAL COLUMNS (read off the actual May-2026 file):
  0  Period                      e.g. "RTT-May-2026"
  1..8   Provider/Commissioner parent + org codes and names
  7  Commissioner Org Code       <- used to drop NONC (see below)
  9  RTT Part Type               Part_1A | Part_1B | Part_2 | Part_2A | Part_3
  10 RTT Part Description        "Incomplete Pathways" == Part_2
  11 Treatment Function Code     C_100, C_110, ... C_999, X02..X06
  12 Treatment Function Name     "Trauma and Orthopaedic Service", ...
  13..117  "Gt 00 To 01 Weeks SUM 1" ... "Gt 103 To 104 Weeks SUM 1", "Gt 104 Weeks SUM 1"
  118 Total
  119 Patients with unknown clock start date
  120 Total All

THREE GOTCHAS, ALL FOUND THE HARD WAY AND ALL VERIFIED:
  (a) On Part_2 (Incomplete) rows, columns "Total" and "Patients with unknown clock
      start date" are EMPTY. Only "Total All" is populated. Reading "Total" gives a
      silent zero. We use "Total All".
  (b) Provider/commissioner names contain quoted commas. A naive line.split(",")
      silently drops ~47,000 of ~157,000 rows. csv.reader is mandatory.
  (c) The raw CSV includes NONC (non-English commissioner) pathways, which NHS
      England EXCLUDES from every published output. Dropping rows where
      Commissioner Org Code == "NONC" reproduces the published figures EXACTLY.

VALIDATION (May 2026, vs Table 1 of the official statistical press notice):
      specialty                     ours        published
      Total (all specialties)    7,153,655     7,153,655   65.6% within 18wk (ours 65.6%)
      Trauma and Orthopaedic       827,960       827,960   60.1% (ours 60.1%)
      Ophthalmology                624,531       624,531   74.1% (ours 74.1%)
      Ear Nose and Throat          594,331       594,331   58.9% (ours 58.9%)
      ...delta = 0 on every treatment function. The parse is exact.

HOW WE GET 1/3/12-MONTH HISTORY - and why
-----------------------------------------
Options considered:
  (a) Refetch the last 13 monthly files on every run. Works, but that is ~50 MB of
      download and ~1 GB of decompression EVERY DAY for data that changes monthly.
      Wasteful and slow in Actions.
  (c) Use NHS England's "RTT Overview Timeseries" file. REJECTED - verified it is
      England-level totals only (no treatment-function split) and it is .xlsx, so it
      cannot give per-specialty >18wk history at all.
  (b) CHOSEN: fetch only the months we actually need, and cache them.
      To compute g1/g3/g12 we need exactly FOUR months: latest, -1, -3, -12. We keep a
      snapshot of every month we have ever parsed in data/rtt_history.json, so the
      first run does up to 4 downloads and every later run normally does ZERO or ONE
      (the new month). History accrues, and past months are re-fetched only if NHS
      England republishes them under a new URL (a revision), which we detect by
      storing the source URL alongside each cached month.

HONEST LIMITS: see nhs_rtt_FINDINGS.md. Short version - NHS England only (not
Scotland/Wales/NI), monthly, ~6 weeks in arrears, and it is SPECIALTY-level, so most
of the radar's niches (weight loss, ADHD, menopause, hair, longevity...) are simply
invisible to RTT because they are not consultant-led elective secondary care.

Stdlib only: urllib, zipfile, csv, io, re, json, os, datetime.
"""

import os
import io
import re
import csv
import json
import zipfile
import urllib.request
from datetime import date

RTT_PAGE = ("https://www.england.nhs.uk/statistics/statistical-work-areas/"
            "rtt-waiting-times/")
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}

HISTORY_FILE = os.environ.get("RTT_HISTORY_PATH", "data/rtt_history.json")

# Only these months are needed for g1/g3/g12. Everything else is already cached.
LAGS = (0, 1, 3, 12)

# How many months of a first-run backfill we are willing to do in one Action.
MAX_DOWNLOADS_PER_RUN = 6

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}

# The all-specialties roll-up row that already exists inside the file. It must NOT be
# summed with the others (double counting), and it is not a niche.
TOTAL_TFN = "Total"

# --------------------------------------------------------------- niche mapping
# Deliberate, explicit mapping onto the dashboard's shared taxonomy. Strings match
# pull_and_build.NICHES exactly. Anything without a genuine private-pay analogue maps
# to None on purpose - a forced mapping would invent a signal that isn't there.
NICHE_BY_SPECIALTY = {
    "Trauma and Orthopaedic Service":    "MSK / physio",
    "Rheumatology Service":              "MSK / physio",          # also feeds Osteoporosis / bone
    "Dermatology Service":               "Dermatology / acne",
    "Plastic Surgery Service":           "Aesthetics / skin",     # cosmetic/reconstructive
    "Ophthalmology Service":             "Eye / optical",
    "Ear Nose and Throat Service":       "Audiology / hearing",   # ENT is broader than hearing
    "Oral Surgery Service":              "Dental / orthodontics",
    "Gynaecology Service":               "Fertility / women's health",  # also Menopause / HRT
    "Urology Service":                   "Bladder / continence",  # also Men's health, Sexual health
    "Neurology Service":                 "Neurology",             # also Migraine
    "Other - Mental Health Services":    "Mental health / psychiatry",

    # Deliberately unmapped - no clean private-pay niche in the taxonomy:
    "General Surgery Service":           None,
    "Neurosurgical Service":             None,
    "Cardiothoracic Surgery Service":    None,
    "General Internal Medicine Service": None,
    "Gastroenterology Service":          None,
    "Cardiology Service":                None,
    "Respiratory Medicine Service":      None,   # sleep/OSA is only a sliver of this
    "Elderly Medicine Service":          None,
    "Other - Medical Services":          None,
    "Other - Paediatric Services":       None,
    "Other - Surgical Services":         None,
    "Other - Other Services":            None,
}


# ------------------------------------------------------------------- utilities
def _get(url, timeout=180):
    req = urllib.request.Request(url, headers=BROWSER_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_text(url, timeout=90):
    return _get(url, timeout).decode("utf-8", "replace")


def _pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / then - 1.0) * 100.0


def _month_key(year, month):
    return "%04d-%02d" % (year, month)


def _shift(key, back):
    y, m = int(key[:4]), int(key[5:7])
    idx = y * 12 + (m - 1) - back
    return _month_key(idx // 12, idx % 12 + 1)


def _load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def _save(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)


def _num(s):
    s = (s or "").strip().replace(",", "")
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


# ------------------------------------------------------- discovery (must scrape)
def discover_months():
    """Scrape NHS England for {'YYYY-MM': zip_url}. Returns {} if unreachable.

    The landing page links to per-financial-year pages; each year page lists that
    year's monthly 'Full CSV data file' ZIPs. We read the 3 most recent year pages,
    which always covers >= 13 months even in April when the current year page has
    only one month on it.
    """
    try:
        landing = _get_text(RTT_PAGE)
    except Exception:
        return {}

    # NB the landing page emits these links BOTH with and without a trailing slash
    # (sidebar nav vs body copy), so the slash must be optional.
    years = sorted(set(re.findall(r"/rtt-waiting-times/(rtt-data-(\d{4})-\d{2})/?", landing)),
                   key=lambda t: t[1], reverse=True)
    if not years:
        return {}

    found = {}
    for slug, _y in years[:3]:
        try:
            html = _get_text(RTT_PAGE + slug + "/")
        except Exception:
            continue
        for href in re.findall(r'href="([^"]*Full-CSV[^"]*\.zip)"', html, re.I):
            fn = href.rsplit("/", 1)[-1]
            m = re.search(r"Full-CSV-data-file-([A-Za-z]{3})(\d{2})", fn, re.I)
            if not m:
                continue
            mon = MONTHS.get(m.group(1).lower())
            if not mon:
                continue
            key = _month_key(2000 + int(m.group(2)), mon)
            # A revised file supersedes the original for the same month.
            score = (1 if re.search(r"revised", fn, re.I) else 0, len(fn))
            if key not in found or score > found[key][1]:
                found[key] = (href, score)
    return {k: v[0] for k, v in found.items()}


# ------------------------------------------------------------------ parse a month
def parse_month(url):
    """Download one monthly ZIP and aggregate England-level incomplete pathways.

    Returns {treatment_function_name: {"total":n, "over18":n, "over52":n}}.
    Streams the CSV out of the ZIP - the file is ~80 MB uncompressed.
    """
    blob = _get(url)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError("no CSV inside %s" % url)
        with zf.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header = next(reader)

            # Resolve every column BY NAME so an added/moved column cannot silently
            # shift our indices.
            ix = {name.strip(): i for i, name in enumerate(header)}
            i_part = ix["RTT Part Type"]
            i_comm = ix["Commissioner Org Code"]
            i_tfn = ix["Treatment Function Name"]
            i_totalall = ix["Total All"]
            i_18 = ix["Gt 18 To 19 Weeks SUM 1"]
            i_52 = ix["Gt 52 To 53 Weeks SUM 1"]
            # Week buckets run up to (but not including) the "Total" column.
            i_end = ix["Total"]

            out = {}
            for row in reader:
                if len(row) <= i_totalall:
                    continue
                if row[i_part] != "Part_2":            # incomplete pathways only
                    continue
                if row[i_comm] == "NONC":              # excluded from all NHS outputs
                    continue
                a = out.setdefault(row[i_tfn], {"total": 0, "over18": 0, "over52": 0})
                a["total"] += _num(row[i_totalall])
                a["over18"] += sum(_num(row[i]) for i in range(i_18, i_end))
                a["over52"] += sum(_num(row[i]) for i in range(i_52, i_end))
    return out


# ----------------------------------------------------------------------- history
def _refresh_history(months):
    """Fetch only the months we need and don't already have. Persist and return."""
    hist = _load(HISTORY_FILE, {}) or {}
    if not months:
        return hist

    latest = max(months)
    wanted = [_shift(latest, b) for b in LAGS]

    fetched = 0
    for key in wanted:
        url = months.get(key)
        if not url:
            continue                                    # month not published (yet)
        cached = hist.get(key)
        if cached and cached.get("url") == url and cached.get("data"):
            continue                                    # already have it, not revised
        if fetched >= MAX_DOWNLOADS_PER_RUN:
            break
        try:
            hist[key] = {"url": url, "data": parse_month(url)}
            fetched += 1
        except Exception:
            continue                                    # leave the gap; growth -> None

    if fetched:
        _save(HISTORY_FILE, hist)
    return hist


# -------------------------------------------------------------------------- main
def rtt():
    """Returns list of rows:
    [{"name": <specialty>, "niche": <mapped niche or None>, "latest": <total waiting>,
      "g1": <% change in the >18wk wait count, 1 month>, "g3": <...3 month>,
      "g12": <...12 month>, "over18": <count>, "pct18": <percent over 18 weeks>}]
    Returns None if the source cannot be reached.

    NOTE g1/g3/g12 are growth in the OVER-18-WEEK COUNT, not in the waiting list.
    NOTE pct18 is the percent waiting OVER 18 weeks. NHS England publishes the
         complement (% WITHIN 18 weeks) = 100 - pct18.
    """
    months = discover_months()
    if not months:
        return None                                     # NHS England unreachable

    hist = _refresh_history(months)

    # Use the newest month we have actually PARSED, which is normally the newest month
    # published. If NHS England ships a new file we cannot read (schema change, bad
    # download), we fall back to the newest good month rather than blanking the whole
    # tier - every row carries "period" so the staleness is visible, not hidden.
    parsed = [k for k, v in hist.items() if (v or {}).get("data")]
    if not parsed:
        return None
    latest = max(parsed)

    cur = hist[latest]["data"]

    def prior(back):
        h = hist.get(_shift(latest, back))
        return (h or {}).get("data") or {}

    m1, m3, m12 = prior(1), prior(3), prior(12)

    rows = []
    for tfn, a in cur.items():
        total, over18 = a["total"], a["over18"]
        if not total:
            continue
        is_total = (tfn == TOTAL_TFN)
        rows.append({
            "name": "All specialties (England)" if is_total else tfn,
            # The roll-up row is a benchmark, not a niche - never map it.
            "niche": None if is_total else NICHE_BY_SPECIALTY.get(tfn),
            # latest MUST be the quantity g1/g3/g12 are computed on, or the dashboard's
            # denominator recovery (base = latest / (1 + g12/100)) produces a fiction.
            # We measure DETERIORATION IN ACCESS, so that quantity is the over-18-week
            # count, not the total waiting list. The total is still carried, as `total`.
            "latest": over18,
            "g1": _pct(over18, (m1.get(tfn) or {}).get("over18")),
            "g3": _pct(over18, (m3.get(tfn) or {}).get("over18")),
            "g12": _pct(over18, (m12.get(tfn) or {}).get("over18")),
            "over18": over18,
            "total": total,
            "pct18": round(100.0 * over18 / total, 1),
            # extras, consistent with the other tiers
            "over52": a["over52"],
            "accel": None,
            "period": latest,
            "is_total": is_total,
        })

    for r in rows:
        if r["g3"] is not None and r["g12"] is not None:
            r["accel"] = r["g3"] - r["g12"]

    # Worst access deterioration first; that is the signal, not size.
    rows.sort(key=lambda r: (not r["is_total"],
                             r["g12"] if r["g12"] is not None else -9e9), reverse=True)
    return rows


if __name__ == "__main__":
    out = rtt()
    if out is None:
        print("RTT: source unreachable")
    else:
        print("period=%s  specialties=%d" % (out[0]["period"], len(out)))
        print