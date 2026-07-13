#!/usr/bin/env python3
"""
TIER 3 (CAPACITY) - AESTHETICS. The CQC blind spot, closed as far as it can be.

WHY THIS MODULE EXISTS
----------------------
The radar's T3 capacity tier is CQC new-location registrations. For aesthetics
that tier is close to USELESS, and not by a small margin:

  "At present, anyone can perform non-surgical cosmetic procedures in England, as
   there are no specific restrictions on who is permitted to do so."
   - House of Commons Library, CBP-10331, 10 September 2025, s4.1

  "Whilst non-surgical procedures fall outside of [CQC's] remit..."
   - same briefing, s8.3

Botulinum toxin and dermal filler given for PURELY COSMETIC reasons are not the
CQC regulated activity "treatment of disease, disorder or injury" (TDDI): CQC's
scope-of-registration guidance excludes "interventions carried out purely for
cosmetic purposes". Laser/IPL for cosmetic purposes fell OUT of CQC scope in
England in 2010. So a clinic doing injectables + laser + peels needs no CQC
registration at all. It appears in the CQC file only if it ALSO does something
medical (e.g. toxin for hyperhidrosis/migraine, or minor surgery).

The England licensing scheme (Health and Care Act 2022 s.180) is STILL NOT IN
FORCE as at July 2026 - policy only, further consultation promised for 2026. So
there is no licence register to read either. Scotland passed its Bill in March
2026 but its offences do not commence until September 2027. See
aesthetics_FINDINGS.md for the full evidence trail.

Net: there is NO statutory register of UK aesthetics clinics. None. Anywhere.

WHAT WE DO INSTEAD
------------------
The only national, dated, machine-readable record of an aesthetics business
coming into existence is its INCORPORATION at Companies House. So we build a
purpose-built aesthetics formation index:

  * scan every company incorporated in a set of aesthetics-relevant SIC codes,
    month by month;
  * match company NAMES against a curated aesthetics vocabulary using
    WHOLE-WORD token matching, so "lip" cannot match "Lipscomb", "brow" cannot
    match "Brown", "skin" cannot match "Skinner" and "tox" cannot match
    "Toxicology";
  * count matches per keyword per calendar month, cache the months, and compute
    1 / 3 / 12-month formation vs THE SAME WINDOW A YEAR EARLIER (year-on-year,
    not sequential - company incorporations are violently seasonal).

This is an INDEX, not a census. It measures the rate of change of aesthetics
business formation. It does not tell you how many clinics exist. Be honest about
that when reading it.

Secondary (optional, tiny): the Save Face accredited-register size, taken from
their public sitemap.xml. robots.txt at https://www.saveface.co.uk/robots.txt
reads "User-agent: * / Disallow: /admin/ / Sitemap: .../sitemap.xml" - i.e. the
sitemap is explicitly advertised and everything outside /admin/ is permitted.
One GET per run. Save Face publishes no join dates, so growth can only accrue
from our own daily snapshots - g1/g3/g12 stay None until we have the history.

WHY NOT THE OTHER REGISTERS (all checked - see FINDINGS):
  JCCP        - POST-only postcode form, no enumerable listing, no dates.
  GMC/GDC/NMC - no aesthetics flag; a dermatologist and a GP look identical.
  LA licences - England scheme not commenced; London special-treatment licences
                predate injectables and are published per-borough, not centrally.
  Google Places - no formation date, ToS forbids the storage we'd need.

Stdlib only: urllib, json, os, re, base64, time, gzip, io, xml.etree, datetime.
"""

import os
import io
import re
import json
import gzip
import time
import base64
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date

NICHE = "Aesthetics / skin"

CH_KEY = os.environ.get("CH_API_KEY", "").strip()
CH_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"

HISTORY_FILE = os.environ.get("AESTHETICS_HISTORY_PATH", "data/aesthetics_history.json")
SAVEFACE_FILE = os.environ.get("AESTHETICS_SAVEFACE_PATH", "data/aesthetics_saveface.json")

UA = {"User-Agent": "healthcare-radar (aesthetics supply-side index)"}

# We need 24 complete months to compute the 12m-vs-prior-12m comparison.
MONTHS_NEEDED = 24

# Companies House allows 600 requests / 5 min. We stay far below that.
PAGE_SIZE = 1000                 # documented range for `size` is 1..5000
MAX_PAGES_PER_RUN = 150          # first run backfills; steady state is ~10-25
SLEEP_BETWEEN_CALLS = 0.35

# ---------------------------------------------------------------- SIC codes
# Cast wide. Precision comes from the NAME match, not the SIC, so a broad net
# costs us pages, not false positives. Every one of these is a SIC that UK
# aesthetics businesses actually pick.
SIC_CODES = [
    "96020",   # Hairdressing and other beauty treatment  <- the main one
    "96040",   # Physical well-being activities
    "86900",   # Other human health activities
    "86220",   # Specialist medical practice activities
    "86210",   # General medical practice activities
    "86230",   # Dental practice activities (dentists inject; toxin/filler)
    "96090",   # Other service activities n.e.c. (catch-all founders use a lot)
    "47750",   # Retail sale of cosmetic and toilet articles
]

# ------------------------------------------------------------- the vocabulary
# Whole-word (token) matching. Multi-word entries match ADJACENT tokens.
# Grouped by precision so the FINDINGS can be honest about what is noisy.
#
# TIER A - unambiguous. If this token is in the name inside these SICs, it is an
# aesthetics business, full stop.
KW_PRECISE = [
    "botox", "botulinum", "profhilo", "polynucleotide", "polynucleotides",
    "sculptra", "juvederm", "restylane", "teoxane", "radiesse", "ellanse",
    "harmonyca", "microneedling", "microneedle", "dermaplaning", "dermaplane",
    "mesotherapy", "threadlift", "thread lift", "hifu", "ultherapy",
    "cryolipolysis", "coolsculpting", "emsculpt", "morpheus", "endolift",
    "tixel", "hyaluronic", "hyaluronidase", "aesthetic", "aesthetics",
    "aesthetica", "aesthetix", "esthetics", "esthetic", "medispa", "medispas",
    "med spa", "medi spa", "medical spa", "injectable", "injectables",
    "injector", "injectors", "skin booster", "skin boosters", "fat dissolving",
    "fat freezing", "anti wrinkle", "antiwrinkle", "lip filler", "lip fillers",
    "chemical peel", "chemical peels", "vampire facial", "exosome", "exosomes",
    "biostimulator", "skin clinic", "skin clinics", "laser clinic",
    "laser hair", "cosmetic clinic", "aesthetic clinic",
]

# TIER B - strong inside these SIC codes, would be noisy outside them.
KW_STRONG = [
    "filler", "fillers", "dermal", "cosmetic", "rejuvenation", "rejuvenate",
    "peel", "peels", "laser", "lasers", "ipl", "prp", "tox", "lift",
    "skin", "lip", "lips", "brow", "brows", "lash", "lashes", "facial",
    "facials", "glow", "contour", "sculpt", "plasma", "collagen",
    "complexion", "dermis", "youth", "flawless",
]

KEYWORDS = KW_PRECISE + KW_STRONG

# A keyword must reach this many hits in the trailing 12 months to earn a row.
MIN_LATEST = 3

# The one row that matters most: distinct companies matching ANY keyword.
TOTAL_ROW = "ALL aesthetics-named incorporations"

SF_SITEMAP = "https://www.saveface.co.uk/sitemap.xml"
SF_ROW = "Save Face accredited clinics (register size)"


# ============================================================== keyword matcher
def tokens(name):
    """Company name -> lowercase alphabetic tokens.

    Digits are dropped ("MORPHEUS8 CLINIC" -> ["morpheus", "clinic"]), and every
    separator (space, hyphen, ampersand, apostrophe, dot) breaks a token. This is
    what makes the whole-word guarantee hold.
    """
    return re.findall(r"[a-z]+", (name or "").lower())


def _phrase_hits(toks, phrase_words):
    n = len(phrase_words)
    for i in range(len(toks) - n + 1):
        if toks[i:i + n] == phrase_words:
            return True
    return False


# Pre-split the vocabulary once.
_SINGLE = {k for k in KEYWORDS if " " not in k}
_PHRASE = [(k, k.split()) for k in KEYWORDS if " " in k]


def match_keywords(name):
    """Return the set of vocabulary entries this company name matches.

    WHOLE-WORD ONLY. This is the whole point:
        "LIPSCOMB HOLDINGS LTD"   -> set()          (not "lip")
        "BROWN AND SONS LTD"      -> set()          (not "brow")
        "SKINNER PROPERTIES LTD"  -> set()          (not "skin")
        "TOXICOLOGY SERVICES LTD" -> set()          (not "tox")
        "THE LIP CLINIC LTD"      -> {"lip"}
        "MEDI-SPA HARLEY ST LTD"  -> {"medi spa"}
    """
    toks = tokens(name)
    if not toks:
        return set()
    tset = set(toks)
    out = {k for k in _SINGLE if k in tset}
    for k, words in _PHRASE:
        if _phrase_hits(toks, words):
            out.add(k)
    return out


# ==================================================================== utilities
def _pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / then - 1.0) * 100.0


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


def _mkey(y, m):
    return "%04d-%02d" % (y, m)


def _shift(key, back):
    """Month key shifted BACK months."""
    y, m = int(key[:4]), int(key[5:7])
    idx = y * 12 + (m - 1) - back
    return _mkey(idx // 12, idx % 12 + 1)


def _first_of(key):
    return date(int(key[:4]), int(key[5:7]), 1)


def _next_first(key):
    return _first_of(_shift(key, -1))


def _get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ======================================================== Companies House fetch
def _ch_auth():
    return {"Authorization": "Basic " + base64.b64encode((CH_KEY + ":").encode()).decode()}


def fetch_month(mkey, page_budget):
    """Count keyword hits among all companies incorporated in month `mkey`.

    Returns (counts_dict, pages_used, complete_bool).

    We query [first-of-month, first-of-NEXT-month] and then filter locally on
    each item's own date_of_creation, so it does not matter whether Companies
    House treats `incorporated_to` as inclusive or exclusive - we never rely on
    it for the boundary.
    """
    lo, hi = _first_of(mkey), _next_first(mkey)
    counts = {}
    matched_companies = set()
    scanned = 0
    pages = 0
    complete = True

    for sic in SIC_CODES:
        start = 0
        while True:
            if pages >= page_budget:
                return counts, pages, False           # ran out of budget: not final
            q = urllib.parse.urlencode({
                "sic_codes": sic,
                "incorporated_from": lo.isoformat(),
                "incorporated_to": hi.isoformat(),
                "size": PAGE_SIZE,
                "start_index": start,
            })
            try:
                blob = _get(CH_URL + "?" + q, _ch_auth(), timeout=90)
                data = json.loads(blob.decode("utf-8"))
            except Exception:
                complete = False
                break
            pages += 1
            time.sleep(SLEEP_BETWEEN_CALLS)

            items = data.get("items") or []
            if not items:
                break
            for it in items:
                created = (it.get("date_of_creation") or "")[:10]
                if not (lo.isoformat() <= created < hi.isoformat()):
                    continue                          # our own boundary, not CH's
                scanned += 1
                num = it.get("company_number") or it.get("company_name")
                hits = match_keywords(it.get("company_name"))
                if not hits:
                    continue
                matched_companies.add(num)
                for k in hits:
                    counts[k] = counts.get(k, 0) + 1
            if len(items) < PAGE_SIZE:
                break
            start += PAGE_SIZE

    counts[TOTAL_ROW] = len(matched_companies)
    counts["_scanned"] = scanned
    return counts, pages, complete


def refresh_history(anchor):
    """Cache monthly counts. Fetch only what is missing, newest month first.

    `anchor` is the first day of the CURRENT month, so the newest month we ever
    count is the last COMPLETE one (partial months would corrupt every window).

    An incorporation date can never change, so a complete month is final. We
    still re-fetch the most recent complete month once, on the next run, to sweep
    up anything Companies House indexed late.
    """
    hist = _load(HISTORY_FILE, {}) or {}
    latest = _shift(_mkey(anchor.year, anchor.month), 1)

    wanted = [_shift(latest, b) for b in range(MONTHS_NEEDED)]
    budget = MAX_PAGES_PER_RUN
    changed = False

    for i, mk in enumerate(wanted):
        if budget <= 0:
            break
        cached = hist.get(mk)
        # re-fetch: never cached, cached but incomplete, or it is the newest
        # month and we only saw it once (late-indexing sweep).
        stale = (cached is None
                 or not cached.get("complete")
                 or (i == 0 and cached.get("sweeps", 0) < 2))
        if not stale:
            continue
        counts, used, complete = fetch_month(mk, budget)
        budget -= used
        if used == 0 and not complete:
            continue                                  # CH unreachable; leave gap
        sweeps = (cached or {}).get("sweeps", 0) + 1 if complete else 0
        hist[mk] = {"counts": counts, "complete": complete, "sweeps": sweeps}
        changed = True

    if changed:
        _save(HISTORY_FILE, hist)
    return hist, latest


# ======================================================================= windows
def _window(hist, latest, back_from, n):
    """Sum a keyword's counts over `n` months ending `back_from` months before
    (and including) `latest`. Returns a dict, or None if ANY month is missing -
    a partial window would silently understate growth, which is worse than a gap.
    """
    keys = [_shift(latest, back_from + i) for i in range(n)]
    out = {}
    for k in keys:
        h = hist.get(k)
        if not h or not h.get("complete"):
            return None
        for kw, c in (h.get("counts") or {}).items():
            out[kw] = out.get(kw, 0) + c
    return out


# ========================================================= Save Face (secondary)
def _saveface_count():
    """Count clinic profiles in the Save Face public sitemap.

    robots.txt (verified 2026-07-13): "User-agent: * / Disallow: /admin/ /
    Sitemap: https://www.saveface.co.uk/sitemap.xml". The sitemap is explicitly
    advertised; /admin/ is the only disallowed path. One GET.

    Clinic profiles live at /en/clinic/<slug> (verified: e.g. /en/clinic/
    chandos-house). Handles a plain urlset, a sitemapindex, and gzip.
    Returns None on any failure - this source is a bonus, never a dependency.
    """
    try:
        seen = set()
        queue = [SF_SITEMAP]
        pages = 0
        while queue and pages < 25:
            url = queue.pop(0)
            pages += 1
            raw = _get(url, timeout=45)
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            root = ET.fromstring(raw)
            tag = root.tag.split("}")[-1]
            locs = [e.text.strip() for e in root.iter()
                    if e.tag.split("}")[-1] == "loc" and e.text]
            if tag == "sitemapindex":
                queue.extend(locs)
                continue
            for u in locs:
                if "/clinic/" in u:
                    seen.add(u)
        return len(seen) or None
    except Exception:
        return None


def _saveface_row():
    n = _saveface_count()
    if not n:
        return None
    hist = _load(SAVEFACE_FILE, {}) or {}
    today = date.today().isoformat()
    hist[today] = n
    for k in sorted(hist)[:-500]:
        hist.pop(k, None)
    _save(SAVEFACE_FILE, hist)

    def back(days):
        target = (date.fromordinal(date.today().toordinal() - days)).isoformat()
        older = [k for k in sorted(hist) if k <= target]
        return hist[older[-1]] if older else None

    return {
        "name": SF_ROW,
        "niche": NICHE,
        "latest": n,
        "g1": _pct(n, back(30)),
        "g3": _pct(n, back(90)),
        "g12": _pct(n, back(365)),
        "accel": None,
        "source": ("saveface.co.uk sitemap.xml (/en/clinic/*); robots.txt permits "
                   "- only /admin/ disallowed, sitemap advertised. No join dates "
                   "published, so growth accrues from our own daily snapshots."),
    }


# ========================================================================= main
def aesthetics():
    """Returns list of rows:
      [{"name": <phrase or operator>, "niche": "Aesthetics / skin",
        "latest": int, "g1": float|None, "g3": float|None, "g12": float|None,
        "source": str}]
    or None if unavailable.

    latest = matching incorporations in the trailing 12 complete months.
    g1  = last 1 month  vs the SAME month a year earlier
    g3  = last 3 months vs the SAME 3 months a year earlier
    g12 = last 12 months vs the 12 months before that
    Year-on-year throughout, because UK incorporations are strongly seasonal and
    a sequential comparison would just re-report January.

    Any of g1/g3/g12 is None until every month in BOTH sides of that comparison
    has been cached. On a cold start that means g1 lands first and g12 last.
    """
    rows = []

    sf = _saveface_row()

    if not CH_KEY:
        return ([sf] if sf else None)

    anchor = date.today().replace(day=1)
    hist, latest = refresh_history(anchor)
    if not any(v.get("complete") for v in hist.values()):
        return ([sf] if sf else None)

    w1, w1p = _window(hist, latest, 0, 1), _window(hist, latest, 12, 1)
    w3, w3p = _window(hist, latest, 0, 3), _window(hist, latest, 12, 3)
    w12, w12p = _window(hist, latest, 0, 12), _window(hist, latest, 12, 12)

    if w12 is None:
        # Not enough history yet for the headline window. Fall back to whatever
        # trailing months we DO have, so the tier is not blank on day one.
        have = 0
        for i in range(MONTHS_NEEDED):
            h = hist.get(_shift(latest, i))
            if not h or not h.get("complete"):
                break
            have += 1
        w12 = _window(hist, latest, 0, have) if have else None
    if w12 is None:
        return ([sf] if sf else None)

    sic_txt = "/".join(SIC_CODES)
    src = ("Companies House advanced search, SIC %s; incorporation date; "
           "whole-word company-name match against a curated aesthetics "
           "vocabulary. An INDEX of formation, not a clinic census - most "
           "aesthetics clinics are not CQC-registrable and no statutory "
           "register exists (HC Act 2022 s.180 not in force as at Jul 2026)."
           % sic_txt)

    def growth(kw, cur, prior):
        if cur is None or prior is None:
            return None
        p = prior.get(kw, 0)
        return _pct(cur.get(kw, 0), p) if p > 0 else None

    for kw in [TOTAL_ROW] + KEYWORDS:
        n = w12.get(kw, 0)
        if kw != TOTAL_ROW and n < MIN_LATEST:
            continue
        g1 = growth(kw, w1, w1p)
        g3 = growth(kw, w3, w3p)
        g12 = growth(kw, w12, w12p)
        rows.append({
            "name": kw,
            "niche": NICHE,
            "latest": n,
            "g1": g1,
            "g3": g3,
            "g12": g12,
            "accel": (g3 - g12) if (g3 is not None and g12 is not None) else None,
            "isnew": (w12p or {}).get(kw, 0) == 0 if w12p is not None else None,
            "source": src,
            "tier": "precise" if kw in KW_PRECISE else (
                "total" if kw == TOTAL_ROW else "strong"),
        })

    # Headline row first, then fastest-growing, then biggest.
    head = [r for r in rows if r["name"] == TOTAL_ROW]
    rest = [r for r in rows if r["name"] != TOTAL_ROW]
    rest.sort(key=lambda r: (r["g12"] is not None,
                             r["g12"] if r["g12"] is not None else 0,
                             r["latest"]), reverse=True)
    out = head + rest[:45]
    if sf:
        out.append(sf)
    return out or None


# ==================================================================== self-test
def _selftest():
    """Synthetic tests. No network. `python3 aesthetics.py --test`."""
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # ---- 1. FALSE POSITIVES: the whole reason for whole-word matching.
    fp = [
        ("LIPSCOMB HOLDINGS LTD", "lip"),
        ("LIPSCOMBE & CO LIMITED", "lip"),
        ("BROWN AND SONS LTD", "brow"),
        ("BROWNING ESTATES LIMITED", "brow"),
        ("SKINNER PROPERTIES LTD", "skin"),
        ("LASHAM MOTORS LIMITED", "lash"),
        ("TOXICOLOGY SERVICES LTD", "tox"),
        ("PEELING PAINT LTD", "peel"),
        ("FILLERY LIMITED", "filler"),
        ("GLOWORM NURSERIES LTD", "glow"),
        ("LIFTING GEAR UK LTD", "lift"),
        ("PLASMACUT ENGINEERING LTD", "plasma"),
        ("CONTOURING SOLUTIONS LTD", "contour"),
        ("SCULPTURE GALLERY LIMITED", "sculpt"),
        ("FACIALLY LTD", "facial"),
        ("IPLAYER MEDIA LTD", "ipl"),
        ("BOTOXIN RESEARCH LTD", "botox"),
    ]
    for nm, kw in fp:
        check(kw not in match_keywords(nm),
              "FALSE POSITIVE: %r matched %r" % (nm, kw))

    # ---- 2. TRUE POSITIVES.
    tp = [
        ("BOTOX BAR LONDON LTD", "botox"),
        ("THE LIP CLINIC LTD", "lip"),
        ("DR SMITH AESTHETICS LIMITED", "aesthetics"),
        ("PROFHILO UK LTD", "profhilo"),
        ("MED SPA HARLEY STREET LTD", "med spa"),
        ("MEDI-SPA MANCHESTER LIMITED", "medi spa"),
        ("MEDISPA LEEDS LTD", "medispa"),
        ("LASER & IPL STUDIO LTD", "laser"),
        ("LASER & IPL STUDIO LTD", "ipl"),
        ("MORPHEUS8 SKIN CLINIC LTD", "morpheus"),
        ("MORPHEUS8 SKIN CLINIC LTD", "skin clinic"),
        ("THE BROW BAR LTD", "brow"),
        ("LASH & BROW STUDIO LIMITED", "lash"),
        ("POLYNUCLEOTIDE CLINIC LTD", "polynucleotide"),
        ("SKIN BOOSTER LOUNGE LTD", "skin booster"),
        ("ANTI-WRINKLE CLINIC LTD", "anti wrinkle"),
        ("THE TOX BAR LTD", "tox"),
        ("PRP AESTHETICS LTD", "prp"),
        ("HIFU & THREAD LIFT CO LTD", "hifu"),
        ("HIFU & THREAD LIFT CO LTD", "thread lift"),
        ("FAT DISSOLVING CLINIC LIMITED", "fat dissolving"),
        ("O'BRIEN'S SKIN CLINIC LTD", "skin"),
    ]
    for nm, kw in tp:
        check(kw in match_keywords(nm),
              "MISSED: %r should match %r (got %s)" % (nm, kw, sorted(match_keywords(nm))))

    # ---- 3. Tokeniser.
    check(tokens("MEDI-SPA (LONDON) LTD.") == ["medi", "spa", "london", "ltd"],
          "tokeniser: separators")
    check(tokens("MORPHEUS8") == ["morpheus"], "tokeniser: digits dropped")
    check(tokens("") == [], "tokeniser: empty")
    check(tokens(None) == [], "tokeniser: None")

    # ---- 4. Window maths + growth, on a synthetic 24-month history.
    latest = "2026-06"
    hist = {}
    for i in range(24):
        mk = _shift(latest, i)
        # 10 botox/month in the recent year, 5/month in the prior year
        n = 10 if i < 12 else 5
        hist[mk] = {"complete": True, "sweeps": 2,
                    "counts": {"botox": n, TOTAL_ROW: n * 3}}
    check(_window(hist, latest, 0, 12)["botox"] == 120, "w12 sum")
    check(_window(hist, latest, 12, 12)["botox"] == 60, "w12p sum")
    check(_window(hist, latest, 0, 1)["botox"] == 10, "w1 sum")
    check(_window(hist, latest, 12, 1)["botox"] == 5, "w1p sum")
    check(abs(_pct(120, 60) - 100.0) < 1e-9, "pct: +100%")
    check(_pct(10, 0) is None, "pct: divide-by-zero -> None")

    # a hole in the window must yield None, never a wrong number
    holed = dict(hist)
    holed["2026-01"] = {"complete": False, "counts": {}}
    check(_window(holed, latest, 0, 12) is None, "incomplete month must void the window")
    del holed["2025-03"]
    check(_window(holed, latest, 12, 12) is None, "missing month must void the window")

    # ---- 5. Month key arithmetic.
    check(_shift("2026-01", 1) == "2025-12", "shift across year boundary")
    check(_shift("2026-01", 12) == "2025-01", "shift 12")
    check(_shift("2026-06", -1) == "2026-07", "shift forward")
    check(_next_first("2026-12") == date(2027, 1, 1), "next_first across year end")
    check(_first_of("2026-07") == date(2026, 7, 1), "first_of")

    # ---- 6. Sitemap parser (the Save Face path), fed synthetic XML.
    xml = (b'<?xml version="1.0" encoding="UTF-8"?>'
           b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           b'<url><loc>https://www.saveface.co.uk/en/clinic/a-clinic</loc></url>'
           b'<url><loc>https://www.saveface.co.uk/en/clinic/b-clinic</loc></url>'
           b'<url><loc>https://www.saveface.co.uk/en/page/faqs</loc></url>'
           b'</urlset>')
    root = ET.fromstring(xml)
    locs = [e.text for e in root.iter() if e.tag.split("}")[-1] == "loc"]
    check(len([u for u in locs if "/clinic/" in u]) == 2,
          "sitemap: should find exactly 2 clinic URLs, got %s" % locs)

    # ---- 7. Vocabulary hygiene: no duplicates, no empties, all lowercase.
    check(len(KEYWORDS) == len(set(KEYWORDS)), "duplicate keyword in vocabulary")
    check(all(k and k == k.lower() for k in KEYWORDS), "keyword not lowercase")
    check(all(re.fullmatch(r"[a-z]+( [a-z]+)*", k) for k in KEYWORDS),
          "keyword contains a character the tokeniser would destroy")

    if fails:
        print("SELFTEST FAILED (%d)" % len(fails))
        for f in fails:
            print("  -", f)
        return 1
    print("selftest OK - %d checks, %d keywords (%d precise / %d strong)"
          % (len(fp) + len(tp) + 20, len(KEYWORDS), len(KW_PRECISE), len(KW_STRONG)))
    return 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(_selftest())
    out = aesthetics()
    if out is None:
        print("aesthetics: unavailable (no CH_API_KEY, and Save Face unreachable)")
    else:
        print("%-42s %8s %9s %9s %9s" % ("name", "12m", "g1", "g3", "g12"))
        for r in out:
            f = lambda v: "-" if v is None else "%+.1f%%" % v
            print("%-42s %8s %9s %9s %9s" % (
                r["name"][:42], r["latest"], f(r["g1"]), f(r["g3"]), f(r["g12"])))
