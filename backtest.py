#!/usr/bin/env python3
"""
BACKTEST for the UK Healthcare Niche Radar.  Runs in GitHub Actions. Stdlib only.

THE CLAIM UNDER TEST
--------------------
The radar asserts a lead-lag ordering:
    T1 INTENT (Google search) -> T2 ENTRY (new companies)
    -> T3 CAPACITY (new CQC clinics) -> T4 CONSUMPTION (NHS prescribing)
Nobody has measured it. This measures it, on a POSITIVE set (niches that really did
boom in UK private-pay healthcare) and a GRAVEYARD set (niches that spiked in search
interest and then went nowhere commercially).

The graveyard is the whole point. A backtest that only looks at winners measures
sensitivity and nothing else - it cannot produce a false-positive rate, and a signal
with no false-positive rate is not a signal, it is a horoscope.

READ backtest_DESIGN.md BEFORE THE OUTPUT. Short version: n~7 cannot validate this.
It CAN falsify it, and that is what to look for.

WHAT IT DOES NOT DO
-------------------
It does not fetch OpenPrescribing (T4). OpenPrescribing returns HTTP 403 to
datacentre IPs, so it 403s from GitHub Actions and from any sandbox. T4 must be
fetched CLIENT-SIDE: run backtest_client.js in a browser console on
openprescribing.net, save the output to _agent/data/backtest_t4.json, and re-run
this script - it merges the file if present. Without it, every T4 claim is WITHHELD,
not zeroed.

RUN
    python3 backtest_core.py            # prove the estimator first (21 fixtures)
    python3 backtest.py --selftest      # same, via this entry point
    python3 backtest.py --no-trends     # full run, spends ZERO SerpApi quota
    python3 backtest.py                 # full run (needs CH_API_KEY; spends 16
                                        #   SerpApi calls ONCE, then caches forever)
"""

import os
import re
import sys
import json
import time
import base64
import shutil
import zipfile
import tempfile
import statistics
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from backtest_core import (
    onset_robust, onset_spec, binom_tail, median_ci, power_note,
    selftest as core_selftest, GROWTH_X, FLOORS, LOW_COUNT,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT_JSON = os.path.join(HERE, "backtest.json")
OUT_MD = os.path.join(HERE, "backtest.md")
T4_FILE = os.path.join(DATA, "backtest_t4.json")           # written by the browser
TRENDS_CACHE = os.path.join(DATA, "backtest_trends.json")  # SerpApi: fetched ONCE
CH_CACHE = os.path.join(DATA, "backtest_ch.json")
CQC_CACHE = os.path.join(DATA, "backtest_cqc.json")

UA = {"User-Agent": "healthcare-radar-backtest"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar-backtest)"}

START = date(2012, 1, 1)    # history starts here; first testable month is ~2015
END = date(2026, 6, 1)      # last month we treat as complete
TIERS = ["T1", "T2", "T3", "T4"]
DIAG = {}


# =========================================================================
#  1. THE NICHE SET
# =========================================================================
# Each niche declares, per tier, whether that tier can SEE it AT ALL. Read this
# before any number in the output.
#
# A tier that cannot see a niche has NOT "correctly rejected" it. It ABSTAINED.
# Counting abstentions as correct rejections is how you manufacture a 100%
# specificity score out of thin air, and it is the easiest way to lie with this
# backtest. CQC does not regulate ice baths; that is not the radar being clever. So
# every tier carries an explicit in-scope flag, and the scoring reports specificity
# BOTH ways: with abstentions counted as correct (flattering, wrong) and with
# abstentions excluded (honest).
#
# t3_scope - is the activity CQC-REGISTRABLE in England? CQC regulates "treatment of
#   disease, disorder or injury": prescribing, surgery, and IV administration of
#   prescription-only products (including 0.9% saline) are in scope. Cryotherapy,
#   red-light beds, ice baths and supplements are NOT regulated activities - no
#   registration exists to count, ever.
# t4_scope - does the niche appear in NHS PRIMARY-CARE prescribing? Private-only,
#   procedural, OTC and illegal products do not.

POSITIVE, GRAVEYARD, UNRESOLVED = "positive", "graveyard", "unresolved"

NICHES = [
    # ---------------------------------------------------------- POSITIVES (7)
    dict(key="adhd", label="ADHD (private assessment)", cls=POSITIVE,
         ch_terms=["adhd", "neurodiversity", "neurodivergent"],
         cqc_terms=["adhd", "neurodiversity", "neurodevelopmental"],
         trends_q="ADHD assessment",
         bnf=["0404000U0", "0404000M0", "0404000S0", "0404000V0", "0404000L0"],
         t3_scope=True, t4_scope=True,
         why="The user's benchmark ('I wanted to catch the ADHD boom 2 years ago'). NHS "
             "waiting lists plus Right to Choose drove a genuine private-assessment boom "
             "c.2021-2024; the 2023 Elvanse shortage is downstream evidence of it."),

    dict(key="glp1", label="Weight loss / GLP-1", cls=POSITIVE,
         ch_terms=["weight loss", "weightloss", "mounjaro", "wegovy", "ozempic",
                   "semaglutide", "tirzepatide", "slimming"],
         cqc_terms=["weight loss", "weight management", "obesity", "slimming", "bariatric"],
         trends_q="weight loss injection",
         bnf=["0601023AW", "0601023AZ", "0601023AB", "0405010P0"],
         t3_scope=True, t4_scope=True,
         why="Unambiguous. Wegovy UK launch Sep-2023, Mounjaro 2024. The largest "
             "private-pay healthcare event of the decade."),

    dict(key="menopause", label="Menopause / HRT", cls=POSITIVE,
         ch_terms=["menopause", "menopausal", "perimenopause", "hrt"],
         cqc_terms=["menopause", "menopausal", "perimenopause", "hrt"],
         trends_q="menopause clinic",
         bnf=["0604011G0", "0604011L0", "0604011K0", "0604011Y0",
              "0604011P0", "0604012S0", "0702010G0"],
         t3_scope=True, t4_scope=True,
         why="Davina McCall's 'Sex, Myths and the Menopause' (Channel 4, May-2021) is a "
             "clean, dateable exogenous shock, followed by a real HRT supply crisis in "
             "2022. As close to a natural experiment as this dataset offers - if the "
             "tiers ever fire in order, they should do it here."),

    dict(key="trt", label="Men's health / TRT", cls=POSITIVE,
         ch_terms=["testosterone", "trt", "men's health", "mens health", "male health"],
         cqc_terms=["testosterone", "men's health", "mens health", "andrology"],
         trends_q="testosterone replacement therapy",
         bnf=["0604020K0", "0604020T0", "0604020U0", "0604020M0"],
         t3_scope=True, t4_scope=True,
         why="Sustained private TRT clinic growth (Optimale, Balance My Hormones). NHS "
             "testosterone prescribing has risen steadily - a real boom, but a slower one."),

    dict(key="hair", label="Hair transplant / restoration", cls=POSITIVE,
         ch_terms=["hair transplant", "hair restoration", "hair clinic", "hair loss"],
         cqc_terms=["hair transplant", "hair restoration", "hair clinic"],
         trends_q="hair transplant",
         bnf=None,
         t3_scope=True, t4_scope=False,
         why="A real UK private-pay boom, plus a large Turkey-outbound market.",
         t4_note="OUT OF SCOPE DESPITE A CODE EXISTING. The only live BNF code is topical "
                 "minoxidil (~600 items/mth); finasteride 1mg runs at ~1 item/mth on the "
                 "NHS. The private hair-loss market is invisible to NHS prescribing, so "
                 "scoring T4 here would be scoring noise."),

    dict(key="ed", label="Sexual health / ED (telehealth)", cls=POSITIVE,
         ch_terms=["erectile", "sexual health", "mens clinic"],
         cqc_terms=["erectile", "sexual health", "andrology"],
         trends_q="erectile dysfunction treatment",
         bnf=["0704050Z0", "0704050R0", "0704050AA", "0704050B0"],
         t3_scope=True, t4_scope=True,
         why="The Numan / Manual / Hims-UK era, c.2019-2022. Sildenafil was reclassified "
             "to pharmacy-only (P) in the UK in 2018 - a dateable regulatory unlock."),

    dict(key="tonguetie", label="Tongue-tie / lactation", cls=POSITIVE,
         ch_terms=["tongue tie", "tongue-tie", "lactation", "frenulotomy"],
         cqc_terms=["tongue tie", "tongue-tie", "lactation", "infant feeding"],
         trends_q="tongue tie",
         bnf=None,
         t3_scope=True, t4_scope=False,
         why="A genuine private-pay boom driven by NHS provision gaps. Included "
             "SPECIFICALLY BECAUSE IT IS SMALL: it tests whether the estimator can see a "
             "real boom in a low-count series, which is the radar's structural weak spot. "
             "Expect its onset to carry a low_count_unreliable flag - that is the point."),

    # --------------------------------------------------------- GRAVEYARD (7)
    dict(key="cbd", label="CBD / cannabidiol", cls=GRAVEYARD,
         ch_terms=["cbd", "cannabidiol", "hemp"],
         cqc_terms=["cbd", "cannabidiol", "cannabis"],
         trends_q="CBD oil",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="THE KEY NEGATIVE. T1 spiked violently (2018-19) AND T2 fired loudly: roughly "
             "500 UK companies were attached to ~12,000 products on the FSA novel-foods "
             "list. The FSA validation backlog then froze the market and analysts estimate "
             "about HALF those companies have since disappeared. If T1+T2 fired this hard "
             "for a wipeout, T1+T2 alone cannot discriminate. This single case can falsify "
             "the early tiers on its own."),

    dict(key="psychedelics", label="Psychedelics / psilocybin", cls=GRAVEYARD,
         ch_terms=["psychedelic", "psilocybin", "psilocin"],
         cqc_terms=["psychedelic", "psilocybin"],
         trends_q="psilocybin therapy",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="T1 and T2 both fired - Compass Pathways' 2020 NASDAQ IPO at a $1.6bn "
             "valuation, Small Pharma, Beckley Psytech, plus a long tail of shells. "
             "Psilocybin is Schedule 1, so no lawful UK treatment clinic can exist and T3 "
             "CANNOT fire by construction. Tests whether T3 rescues a T2 false positive - "
             "and whether that rescue is real discrimination or just an artefact of the "
             "drug being illegal. (It is the latter. That distinction IS the report.)"),

    dict(key="ivdrip", label="IV vitamin drips", cls=GRAVEYARD,
         ch_terms=["iv drip", "vitamin drip", "iv therapy", "drip clinic", "iv infusion"],
         cqc_terms=["drip", "iv therapy", "intravenous"],
         trends_q="IV vitamin drip",
         bnf=None,
         t3_scope=True,          # <- the hard one: IV drips ARE CQC-registrable
         t4_scope=False,
         why="THE HARDEST NEGATIVE, and the one that matters most. CQC confirms that IV "
             "administration of prescription-only products (including 0.9% saline) for "
             "wellbeing IS a regulated activity - so unlike the rest of the graveyard, ALL "
             "THREE early tiers can fire here. And the live radar's own taxonomy already "
             "carries a 'Longevity / peptides / IV' niche, so the system WOULD surface it. "
             "Commercially it has produced no scaled UK operator and no roll-up in ~8 "
             "years. CONTESTABLE: Get A Drip and REVIV do exist, so this is 'commercially "
             "marginal', not 'zero'. Flagged as the negative most open to argument - and "
             "it is the ONLY informative negative T3 has."),

    dict(key="cryo", label="Cryotherapy (whole-body)", cls=GRAVEYARD,
         ch_terms=["cryotherapy", "cryo chamber"],
         cqc_terms=["cryotherapy"],
         trends_q="cryotherapy",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="Spiked c.2016-18 on athlete endorsement. Not a CQC regulated activity. No "
             "scaled UK operator emerged."),

    dict(key="hbot", label="Hyperbaric oxygen therapy", cls=GRAVEYARD,
         ch_terms=["hyperbaric"],
         cqc_terms=["hyperbaric"],
         trends_q="hyperbaric oxygen therapy",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="Recurrent biohacking-driven interest spikes. UK supply is dominated by "
             "decades-old charity-run MS therapy centres, not new commercial entrants. No "
             "private-pay roll-up has materialised."),

    dict(key="coldwater", label="Cold-water therapy / ice baths", cls=GRAVEYARD,
         ch_terms=["ice bath", "cold plunge", "cold water therapy", "wim hof"],
         cqc_terms=["ice bath", "cold plunge", "cold water"],
         trends_q="ice bath",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="An enormous T1 spike 2021-2024 (Wim Hof, Huberman). Zero clinical "
             "infrastructure. The purest test of 'T1 blares and nothing follows'."),

    dict(key="redlight", label="Red-light therapy", cls=GRAVEYARD,
         ch_terms=["red light therapy", "photobiomodulation"],
         cqc_terms=["red light", "photobiomodulation"],
         trends_q="red light therapy",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="Resolved into a consumer-DEVICE market (masks, panels), not a clinic market. "
             "Tests the case where demand is real but the delivery model is retail - which "
             "a clinic roll-up cannot buy."),

    # -------------------------------------------------------- UNRESOLVED (2)
    # Scored NOWHERE. Reported only. Putting a live bet into a hit-rate assumes the
    # answer to the question being asked.
    dict(key="nad", label="NAD+ infusions", cls=UNRESOLVED,
         ch_terms=["nad+", "nad plus", "nicotinamide"],
         cqc_terms=["nad"],
         trends_q="NAD+ infusion",
         bnf=None,
         t3_scope=True, t4_scope=False,
         why="Currently rising; outcome unknown. DELIBERATELY UNSCORED. This is what the "
             "radar is pointing at right now, and we will not know whether it is a boom or "
             "a dud for another ~3 years. Its presence here IS an argument: a backtest can "
             "only grade booms that have ALREADY RESOLVED, which means it can only ever "
             "validate the system on things that are already obvious."),

    dict(key="collagen", label="Collagen supplements", cls=UNRESOLVED,
         ch_terms=["collagen"],
         cqc_terms=["collagen"],
         trends_q="collagen supplement",
         bnf=None,
         t3_scope=False, t4_scope=False,
         why="UNSCORED because it is a CATEGORY ERROR, not a dud: it is an FMCG product and "
             "was never a clinic. Counting it as a correct rejection would be rewarding the "
             "radar for being blind to something it was never pointed at."),
]

BY_KEY = {n["key"]: n for n in NICHES}
POSITIVES = [n for n in NICHES if n["cls"] == POSITIVE]
GRAVEYARDS = [n for n in NICHES if n["cls"] == GRAVEYARD]


# =========================================================================
#  2. MONTH / IO HELPERS
# =========================================================================
def add_months(d, k):
    i = d.year * 12 + (d.month - 1) + k
    return date(i // 12, i % 12 + 1, 1)


def month_axis(start=START, end=END):
    out, d = [], start
    while d <= end:
        out.append(d.strftime("%Y-%m"))
        d = add_months(d, 1)
    return out


def months_between(a, b):
    """b - a, in months, on 'YYYY-MM' strings. Positive => b is LATER than a."""
    if not a or not b:
        return None
    return ((int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7])))


def bucket(months, dates):
    idx = {m: i for i, m in enumerate(months)}
    vals = [0.0] * len(months)
    for d in dates:
        i = idx.get(d.strftime("%Y-%m"))
        if i is not None:
            vals[i] += 1
    return vals


def get_json(url, headers=None, timeout=45, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if getattr(e, "code", None) == 429:      # CH: 600 req / 5 min
                time.sleep(8 * (a + 1))
                continue
            if a == retries - 1:
                return None
            time.sleep(1.5 * (a + 1))
    return None


def get_text(url, timeout=60):
    try:
        req = urllib.request.Request(url, headers=BROWSER_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def download(url, path, timeout=300):
    req = urllib.request.Request(url, headers=BROWSER_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    return path


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


def has_term(name, terms):
    """Word-boundary matching. Short keys ('cbd', 'nad', 'hrt') MUST be whole-word or
    they match every company with those letters buried inside a longer word - the exact
    bug taxonomy.py was written to fix ('Skinner & Partners' -> Aesthetics)."""
    t = (name or "").lower()
    for k in terms:
        pat = r"\b" + re.escape(k) + (r"\b" if len(k) <= 4 else r"")
        if re.search(pat, t):
            return True
    return False


# =========================================================================
#  3. T2 - COMPANIES HOUSE: monthly incorporations by name keyword
# =========================================================================
# advanced-search/companies supports company_name_includes + incorporated_from/to. We
# partition BY YEAR so we never deep-page, then bucket date_of_creation into months.
# ~300-800 requests; CH allows 600 per 5 minutes, so we throttle. This is the cheapest
# and richest historical series available and it is the backbone of the study.
#
# Dissolved companies are DELIBERATELY INCLUDED. A company that incorporated in 2019
# and died in 2022 still fired the T2 signal in 2019, and excluding it would be
# survivorship bias pointing the other way - it would erase precisely the graveyard
# cohorts we are trying to catch.
CH_KEY = os.environ.get("CH_API_KEY", "").strip()
CH_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"


def ch_search(term, y_from, y_to, start):
    q = urllib.parse.urlencode({
        "company_name_includes": term,
        "incorporated_from": y_from, "incorporated_to": y_to,
        "size": 100, "start_index": start,
    })
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    return get_json(CH_URL + "?" + q, {"Authorization": "Basic " + auth})


def fetch_ch(niches):
    if not CH_KEY:
        DIAG["t2"] = "CH_API_KEY not set - T2 WITHHELD"
        return {}
    cached = load(CH_CACHE)
    if cached:
        DIAG["t2"] = "cache hit"
        return cached

    out, calls = {}, 0
    for n in niches:
        seen = {}                       # company_number -> (date_of_creation, status)
        for term in n["ch_terms"]:
            for yr in range(START.year, END.year + 1):
                start = 0
                for _page in range(15):     # cap: 1,500 per niche-term-year
                    d = ch_search(term, "%d-01-01" % yr, "%d-12-31" % yr, start)
                    calls += 1
                    if calls % 100 == 0:
                        time.sleep(30)      # stay well under 600 / 5 min
                    items = (d or {}).get("items") or []
                    if not items:
                        break
                    for it in items:
                        num, nm = it.get("company_number"), it.get("company_name") or ""
                        doc = it.get("date_of_creation")
                        if not (num and doc):
                            continue
                        # CH's name search is loose. Re-apply our own word-boundary matcher
                        # so "CBD" does not drag in "CBDESIGN LTD".
                        if not has_term(nm, n["ch_terms"]):
                            continue
                        seen[num] = (doc, it.get("company_status") or "")
                    start += 100
                    if len(items) < 100:
                        break
        out[n["key"]] = {"rows": [[v[0], v[1]] for v in seen.values()], "n": len(seen)}
        print("  T2 %-14s %5d companies" % (n["key"], len(seen)))
    DIAG["t2_calls"] = calls
    save(CH_CACHE, out)
    return out


def ch_cohort_survival(rec):
    """Share of each incorporation-year cohort now dissolved.

    Cohorts MUST be age-matched to be comparable - a 2024 cohort has had no time to die
    - so this is reported per cohort year and only compared DOWN a column.

    HINDSIGHT ONLY. You cannot know a fresh cohort's survival rate, and a fresh cohort
    is exactly the one the live radar cares about. Diagnostic, not predictive. Included
    because it is likely the sharpest discriminator in the whole file, and hiding it
    because it is not actionable would be dishonest.
    """
    by_year = {}
    for doc, st in rec.get("rows") or []:
        b = by_year.setdefault(doc[:4], [0, 0])
        b[0] += 1
        low = (st or "").lower()
        if "dissolved" in low or "liquidation" in low:
            b[1] += 1
    return {y: {"n": v[0], "dead": v[1],
                "dead_pct": round(100.0 * v[1] / v[0], 1) if v[0] else None}
            for y, v in sorted(by_year.items())}


# =========================================================================
#  4. T3 - CQC: monthly clinic registrations, SURVIVORSHIP-CORRECTED
# =========================================================================
# The active-locations bulk file lists only locations that are STILL ACTIVE. A clinic
# that opened in 2017 and closed in 2021 is simply gone from it. So a naive monthly
# history built from that file alone UNDERSTATES older months and manufactures a fake
# upward trend in EVERY niche - which would push every T3 onset LATER and make every T3
# series look like a boom. For a lead-lag study whose entire output is the GAP between
# onsets, that is not a footnote. It is fatal.
#
# It is also FIXABLE, and this is the main methodological win in the file. CQC publishes
# a "Deactivated locations" ODS on the same transparency page, containing archived
# locations WITH their HSCA start date. Union the two files and the historical
# registration count is complete. We do that, we compute the correction size, and we
# report the T3 onset BOTH WAYS - so the bias is quantified rather than waved at.
#
# Residual caveat we CANNOT fix: CQC also archives a location on RE-REGISTRATION
# (legal-entity change, address move), so some archived rows are the same clinic twice.
# That inflates counts slightly in both eras. We de-duplicate on (name, start-month),
# which blunts it but will not catch a genuine relocation.
CQC_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
NS_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
NS_TX = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"])}


def cqc_urls():
    """(active_ods, deactivated_ods). Either may be None."""
    html = get_text(CQC_PAGE)
    if not html:
        return None, None

    def hunt(pat):
        m = re.search(pat, html, re.I)
        if not m:
            return None
        u = m.group(1)
        return u if u.startswith("http") else "https://www.cqc.org.uk" + u

    return (hunt(r'href="([^"]*HSCA_Active_Locations\.ods)"'),
            hunt(r'href="([^"]*[Dd]eactivated[^"]*\.ods)"')
            or hunt(r'href="([^"]*[Aa]rchived[^"]*[Ll]ocations[^"]*\.ods)"'))


def ods_rows(path, max_cols=220):
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
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})[/\-]([A-Za-z]{3,9})[/\-](\d{4})", s)
    if m:
        mon = next((v for k, v in MONTHS.items()
                    if k.startswith(m.group(2).lower()[:3])), None)
        if mon:
            return date(int(m.group(3)), mon, int(m.group(1)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def cqc_locations(url, tag):
    """-> [(location_name, hsca_start_date)] from one ODS file."""
    if not url:
        return []
    path = os.path.join(tempfile.gettempdir(), "cqc_%s.ods" % tag)
    try:
        download(url, path)
    except Exception as e:
        DIAG["cqc_%s_err" % tag] = repr(e)[:140]
        return []
    out, i_name, i_date = [], None, None
    for _sheet, row in ods_rows(path):
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
            if i_name is None or i_date is None:
                DIAG["cqc_%s_err" % tag] = "name/date column not found"
                return []
            continue
        if len(row) <= max(i_name, i_date):
            continue
        d = parse_date(row[i_date])
        if d:
            out.append((row[i_name] or "", d))
    DIAG["cqc_%s_rows" % tag] = len(out)
    return out


def fetch_cqc(niches):
    cached = load(CQC_CACHE)
    if cached:
        DIAG["t3"] = "cache hit"
        return cached

    a_url, d_url = cqc_urls()
    DIAG["cqc_active_url"], DIAG["cqc_deactivated_url"] = a_url, d_url
    active, deact = cqc_locations(a_url, "active"), cqc_locations(d_url, "deact")
    DIAG["cqc_survivorship_corrected"] = bool(deact)
    if not deact:
        DIAG["cqc_WARNING"] = ("Deactivated-locations file NOT found. T3 is ACTIVE-ONLY "
                               "and therefore survivorship-biased: older months are "
                               "understated and every T3 onset is biased LATE. Treat all "
                               "T3 lead times as unsafe.")
    months = month_axis()
    out = {}
    for n in niches:
        def pick(rows):
            seen, keep = set(), []
            for nm, d in rows:
                if not has_term(nm, n["cqc_terms"]):
                    continue
                sig = (nm.strip().lower(), d.strftime("%Y-%m"))   # de-dup re-registrations
                if sig in seen:
                    continue
                seen.add(sig)
                keep.append(d)
            return keep

        a, d = pick(active), pick(deact)
        out[n["key"]] = {
            "active_only": bucket(months, a),
            "corrected": bucket(months, a + d),
            "n_active": len(a), "n_deactivated": len(d),
        }
        print("  T3 %-14s %4d active + %4d archived" % (n["key"], len(a), len(d)))
    save(CQC_CACHE, out)
    return out


# =========================================================================
#  5. T1 - GOOGLE TRENDS via SerpApi  (QUOTA-GUARDED, FETCHED ONCE, EVER)
# =========================================================================
# COST: exactly ONE SerpApi call per niche. 16 niches = 16 CALLS, ONE TIME.
# The free tier is ~100 searches/month and the live weekly job already burns ~80,
# leaving ~20. 16 fits inside 20 - but only just, and only once. So:
#   * the result is cached to disk permanently and NEVER re-fetched;
#   * --no-trends skips it entirely;
#   * if the cache exists, not a single call is spent.
# It does NOT exceed budget, but it eats ~80% of the headroom. If that is too tight,
# skip ONE weekly refresh in the month you run this.
#
# A REAL CAVEAT, not a footnote: Google Trends RESCALES its 0-100 index across whatever
# date range you request. Ask for 2012-2026 and a niche that 50x'd shows its pre-boom
# months as 0s and 1s - integer truncation. The 12-month rolling sum in the estimator
# absorbs most of this (it works on a 0-1200 range, not 0-100), but T1 onsets remain the
# LEAST TRUSTWORTHY DATES IN THIS FILE, and the direction of the error depends on the
# window requested. Every term uses the SAME window, so the error is at least consistent
# across niches - which is what a lead-lag COMPARISON needs, even if the absolute dates
# are soft.
SERP = os.environ.get("SERPAPI_KEY", "").strip()


def fetch_trends(niches, allow=True):
    cached = load(TRENDS_CACHE)
    if cached:
        DIAG["t1"] = "cache hit - 0 SerpApi calls spent"
        return cached
    if not allow or not SERP:
        DIAG["t1"] = "SKIPPED (--no-trends or no SERPAPI_KEY). T1 WITHHELD."
        return {}

    months = month_axis()
    idx = {m: i for i, m in enumerate(months)}
    out, calls = {}, 0
    rng = "%s %s" % (START.isoformat(), END.isoformat())
    for n in niches:
        url = ("https://serpapi.com/search.json?engine=google_trends"
               "&q=%s&geo=GB&data_type=TIMESERIES&date=%s&api_key=%s"
               % (urllib.parse.quote(n["trends_q"]), urllib.parse.quote(rng), SERP))
        d = get_json(url)
        calls += 1
        vals = [0.0] * len(months)
        ok = 0
        try:
            for pt in d["interest_over_time"]["timeline_data"]:
                ts = pt.get("timestamp")
                m = datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m") if ts else None
                i = idx.get(m)
                if i is not None:
                    vals[i] = float(pt["values"][0]["extracted_value"])
                    ok += 1
        except Exception:
            print("  T1 %-14s FAILED" % n["key"])
            continue
        out[n["key"]] = vals
        print("  T1 %-14s ok (%d points)" % (n["key"], ok))
    DIAG["serpapi_calls_spent"] = calls
    save(TRENDS_CACHE, out)
    return out


# =========================================================================
#  6. BUILD
# =========================================================================
def series_for(n, months, tr, ch, cqc, t4):
    s = {}
    if n["key"] in tr:
        s["T1"] = tr[n["key"]]
    if n["key"] in ch:
        s["T2"] = bucket(months, [parse_date(r[0]) for r in ch[n["key"]]["rows"]
                                  if parse_date(r[0])])
    if n["key"] in cqc:
        s["T3"] = cqc[n["key"]]["corrected"]
    if n["key"] in t4 and n["t4_scope"]:
        idx = {m: i for i, m in enumerate(months)}
        v = [0.0] * len(months)
        for m, items in (t4[n["key"]] or {}).items():
            if m in idx:
                v[idx[m]] = float(items)
        s["T4"] = v
    return s


def tier_state(n, tier, series, months, growth_x=GROWTH_X):
    in_scope = True
    if tier == "T3":
        in_scope = n["t3_scope"]
    if tier == "T4":
        in_scope = n["t4_scope"]
    if not in_scope:
        return {"state": "OUT_OF_SCOPE", "onset": None,
                "note": "this tier structurally cannot observe this niche - it ABSTAINS, "
                        "it does not reject"}
    vals = series.get(tier)
    if not vals or sum(vals) == 0:
        return {"state": "NO_DATA", "onset": None}
    rb = onset_robust(months, vals, tier, growth_x=growth_x)
    sp = onset_spec(months, vals)
    return {
        "state": "FIRED" if rb["onset"] else "NO_ONSET",
        "onset": rb["onset"],
        "z_at_onset": rb["z_at_onset"],
        "growth_at_onset": rb["growth_at_onset"],
        "level_at_onset": rb["level_at_onset"],
        "baseline_at_onset": rb["baseline_at_onset"],
        "low_count_unreliable": rb["low_count_unreliable"],
        "peak_z": rb["peak_z"],
        "latest_12m": rb["latest_12m"],
        "total": rb["total"],
        "spec_onset": sp["onset"],
        "spec_undefined_months": sp["undefined_months"],
        "agrees_with_spec": rb["onset"] == sp["onset"],
    }


def assemble(months, tr, ch, cqc, t4):
    results = {}
    for n in NICHES:
        s = series_for(n, months, tr, ch, cqc, t4)
        row = {"key": n["key"], "label": n["label"], "class": n["cls"],
               "why": n["why"], "tiers": {}}
        if n.get("t4_note"):
            row["t4_note"] = n["t4_note"]
        for tier in TIERS:
            row["tiers"][tier] = tier_state(n, tier, s, months)

        if n["key"] in cqc:
            c = cqc[n["key"]]
            a, corr = c["active_only"], c["corrected"]
            pre = sum(1 for m in months if m < "2019-01")
            row["t3_survivorship"] = {
                "n_active": c["n_active"],
                "n_archived_recovered": c["n_deactivated"],
                "understatement_pct": (round(100.0 * (sum(corr) - sum(a)) / sum(corr), 1)
                                       if sum(corr) else None),
                "pre2019_understatement_pct": (
                    round(100.0 * (sum(corr[:pre]) - sum(a[:pre])) / sum(corr[:pre]), 1)
                    if sum(corr[:pre]) else None),
                "onset_active_only": (onset_robust(months, a, "T3")["onset"]
                                      if sum(a) else None),
                "onset_corrected": row["tiers"]["T3"].get("onset"),
            }
        if n["key"] in ch:
            row["t2_cohort_survival"] = ch_cohort_survival(ch[n["key"]])
        results[n["key"]] = row

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "window": {"start": months[0], "end": months[-1]},
        "estimator": {
            "primary": "robust log-level shift vs a SMOOTHED baseline: trailing-12m sum -> "
                       "log growth vs median(R[t-24..t-12]) -> Poisson SE with robust "
                       "overdispersion -> z>=3 + 3-month persistence + max-trimmed "
                       "confirmation + per-tier level floor",
            "boom_definition": ">= %.0f%% bigger than the typical level a year+ ago"
                               % ((GROWTH_X - 1) * 100),
            "floors": FLOORS,
            "low_count_threshold_per_year": LOW_COUNT,
            "spec": "the brief's estimator (raw YoY, mean/SD baseline) is computed in "
                    "parallel on every series; disagreements are reported",
        },
        "diag": DIAG,
        "niches": results,
        "analysis": analyse(results),
        "sensitivity": sensitivity(months, tr, ch, cqc, t4),
    }
    save(OUT_JSON, payload)
    write_md(payload)
    return payload


def build(no_trends=False):
    months = month_axis()
    print("Backtest window %s .. %s (%d months)\n" % (months[0], months[-1], len(months)))
    print("T2 Companies House")
    ch = fetch_ch(NICHES)
    print("\nT3 CQC")
    cqc = fetch_cqc(NICHES)
    print("\nT1 Google Trends")
    tr = fetch_trends(NICHES, allow=not no_trends)
    t4 = load(T4_FILE, {}) or {}
    DIAG["t4"] = ("merged from %s" % T4_FILE) if t4 else (
        "ABSENT - OpenPrescribing 403s from datacentre IPs. Run backtest_client.js in a "
        "browser and save its output to data/backtest_t4.json. Every T4 result below is "
        "WITHHELD, not zero.")

    p = assemble(months, tr, ch, cqc, t4)
    print("\nwrote %s\nwrote %s" % (OUT_JSON, OUT_MD))
    return p


def sensitivity(months, tr, ch, cqc, t4):
    """Re-run the whole thing at three boom thresholds.

    If the lead-lag ORDERING flips when the threshold moves, the ordering was never a
    fact about the world - it was a fact about the number I picked. This is the cheapest
    guard against tuning the estimator until it agrees with the thesis, and it costs
    nothing because everything is already in memory.
    """
    out = {}
    for gx in (1.25, 1.5, 2.0):
        res = {}
        for n in NICHES:
            s = series_for(n, months, tr, ch, cqc, t4)
            res[n["key"]] = {"tiers": {t: tier_state(n, t, s, months, growth_x=gx)
                                       for t in TIERS}}
        gaps = {}
        for a, b in (("T1", "T2"), ("T2", "T3"), ("T3", "T4")):
            v = []
            for n in POSITIVES:
                oa = res[n["key"]]["tiers"].get(a, {}).get("onset")
                ob = res[n["key"]]["tiers"].get(b, {}).get("onset")
                if oa and ob:
                    v.append(months_between(oa, ob))
            gaps["%s->%s" % (a, b)] = {
                "n": len(v),
                "median_gap": statistics.median(v) if v else None,
                "n_in_predicted_order": sum(1 for x in v if x > 0),
            }
        out["growth_x=%s" % gx] = gaps
    return out


def analyse(results):
    out = {}

    # ---- pairwise lead times. More usable than everything-vs-T4, because most niches
    #      have no T4 at all - and a gap needs BOTH ends to exist.
    gaps = {}
    for a, b in (("T1", "T2"), ("T2", "T3"), ("T3", "T4"), ("T1", "T3"), ("T1", "T4")):
        detail = []
        for n in POSITIVES:
            r = results[n["key"]]["tiers"]
            oa, ob = r.get(a, {}).get("onset"), r.get(b, {}).get("onset")
            if oa and ob:
                detail.append({
                    "niche": n["key"], "from": oa, "to": ob,
                    "gap_months": months_between(oa, ob),
                    "either_end_unreliable": bool(r[a].get("low_count_unreliable")
                                                  or r[b].get("low_count_unreliable")),
                })
        v = [d["gap_months"] for d in detail]
        ci = median_ci(v)
        correct = sum(1 for x in v if x > 0)
        gaps["%s->%s" % (a, b)] = {
            "n": len(v), "detail": detail,
            "median_gap_months": statistics.median(v) if v else None,
            "mean_gap_months": round(statistics.fmean(v), 1) if v else None,
            "range": [min(v), max(v)] if v else None,
            "median_95ci": ci,
            "median_95ci_note": (None if ci else (
                "NO 95%% CI EXISTS at n=%d. Even the widest possible distribution-free "
                "interval - the entire min-to-max range - reaches only %.1f%% coverage. "
                "That is arithmetic, not pessimism."
                % (len(v), 100 * (1 - 2 * 0.5 ** len(v)))
                if v else "no niche has both ends of this pair")),
            "n_in_predicted_order": correct,
            "sign_test_p_one_sided": round(binom_tail(correct, len(v)), 4) if v else None,
            "power": power_note(len(v)) if v else None,
        }
    out["lead_times"] = gaps

    # ---- per-tier scoring
    tiers = {}
    for tier in TIERS:
        def st(group, want):
            return [n["key"] for n in group
                    if results[n["key"]]["tiers"].get(tier, {}).get("state") == want]

        tp, fn = st(POSITIVES, "FIRED"), st(POSITIVES, "NO_ONSET")
        p_abs = (st(POSITIVES, "OUT_OF_SCOPE") + st(POSITIVES, "NO_DATA"))
        fp, tn = st(GRAVEYARDS, "FIRED"), st(GRAVEYARDS, "NO_ONSET")
        g_abs = (st(GRAVEYARDS, "OUT_OF_SCOPE") + st(GRAVEYARDS, "NO_DATA"))

        n_pos, n_neg = len(tp) + len(fn), len(fp) + len(tn)
        tiers[tier] = {
            "hit_rate": round(len(tp) / n_pos, 2) if n_pos else None,
            "hits": tp, "misses": fn, "positives_abstained": p_abs,
            "false_positives": fp, "true_negatives": tn, "graveyard_abstained": g_abs,
            # HONEST: abstentions excluded.
            "false_positive_rate_informative": round(len(fp) / n_neg, 2) if n_neg else None,
            "informative_negatives": n_neg,
            # FLATTERING: abstentions counted as correct rejections. Reported ONLY so the
            # gap between the two columns is visible.
            "false_positive_rate_credulous": (round(len(fp) / len(GRAVEYARDS), 2)
                                              if GRAVEYARDS else None),
            "warning": ("Specificity for this tier rests on %d of %d graveyard niches; %d "
                        "ABSTAINED (out of scope / no data). If most of the graveyard is "
                        "invisible to a tier, its apparent specificity is an artefact of "
                        "regulatory scope, NOT evidence of discriminating power."
                        % (n_neg, len(GRAVEYARDS), len(g_abs))) if g_abs else None,
        }
    out["tiers"] = tiers

    # ---- where the choice of estimator changes the answer
    out["estimator_disagreements"] = [
        {"niche": k, "tier": t, "robust": v.get("onset"), "spec": v.get("spec_onset"),
         "spec_undefined_months": v.get("spec_undefined_months")}
        for k, r in results.items() for t, v in r["tiers"].items()
        if v.get("state") in ("FIRED", "NO_ONSET") and not v.get("agrees_with_spec", True)
    ]

    # ---- onsets whose DATE we do not trust
    out["low_count_onsets"] = [
        {"niche": k, "tier": t, "onset": v.get("onset"),
         "baseline_per_year": v.get("baseline_at_onset")}
        for k, r in results.items() for t, v in r["tiers"].items()
        if v.get("low_count_unreliable")
    ]
    return out


# =========================================================================
#  7. MARKDOWN REPORT
# =========================================================================
def write_md(p):
    r, a = p["niches"], p["analysis"]
    L = []
    A = L.append
    A("# Radar backtest: does T1 -> T2 -> T3 -> T4 actually hold?\n")
    A("Generated %s. Window %s to %s. Boom = %s.\n"
      % (p["generated"][:10], p["window"]["start"], p["window"]["end"],
         p["estimator"]["boom_definition"]))

    A("\n## 0. Read this before any table below\n")
    A("- **n = %d positives, %d graveyard niches.** Section 4 shows what that n can "
      "support. Short version: it cannot validate the claim, only falsify it.\n"
      % (len(POSITIVES), len(GRAVEYARDS)))
    A("- A tier that **abstains** (OUT_OF_SCOPE / NO_DATA) has **not** correctly rejected "
      "anything. CQC does not regulate ice baths; that is not the radar being clever. "
      "Abstentions are excluded from the honest false-positive rate.\n")
    if "ABSENT" in str(p["diag"].get("t4", "")):
        A("- **T4 IS ABSENT from this run.** OpenPrescribing 403s from datacentre IPs. Run "
          "`backtest_client.js` in a browser, save the output to `data/backtest_t4.json`, "
          "re-run. Every T4 cell below is *withheld*, not zero.\n")
    if p["diag"].get("cqc_survivorship_corrected"):
        A("- T3 **is** survivorship-corrected (the CQC deactivated-locations file was found "
          "and merged). Section 5 quantifies how much that mattered.\n")
    else:
        A("- **T3 is NOT survivorship-corrected** - the deactivated-locations file was not "
          "found. Older months are understated and every T3 onset is biased LATE. Treat T3 "
          "lead times as unsafe.\n")

    A("\n## 1. Onsets\n")
    A("| Niche | Class | T1 intent | T2 entry | T3 capacity | T4 scripts |")
    A("|---|---|---|---|---|---|")
    for n in NICHES:
        row, cells = r[n["key"]], []
        for t in TIERS:
            tt = row["tiers"].get(t, {})
            s = tt.get("state")
            if s == "FIRED":
                cells.append("**%s**%s" % (tt["onset"],
                                           " (!)" if tt.get("low_count_unreliable") else ""))
            elif s == "NO_ONSET":
                cells.append("no onset")
            elif s == "OUT_OF_SCOPE":
                cells.append("_abstains_")
            else:
                cells.append("no data")
        A("| %s | %s | %s |" % (row["label"], row["class"], " | ".join(cells)))
    A("\n`(!)` = the series was too thin at onset (< %d events/yr) for the DATE to be "
      "trustworthy. That it fired is meaningful; the month is not.\n" % LOW_COUNT)

    A("\n## 2. Lead times (positive set only)\n")
    A("A **positive** gap means the first tier fired EARLIER - i.e. the radar's claim holds.\n")
    A("| Pair | n | Median gap (mths) | Range | 95% CI for the median | In predicted order "
      "| Sign-test p |")
    A("|---|---|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        ci = g["median_95ci"]
        A("| %s | %d | %s | %s | %s | %s/%s | %s |" % (
            pair, g["n"], g["median_gap_months"] if g["n"] else "-",
            ("%d to %d" % tuple(g["range"])) if g["range"] else "-",
            ("%d to %d" % (ci[0], ci[1])) if ci else "**none exists**",
            g["n_in_predicted_order"], g["n"],
            g["sign_test_p_one_sided"] if g["n"] else "-"))

    A("\n## 3. Per-tier scoring\n")
    A("| Tier | Hit rate (positives) | FP rate - HONEST | FP rate - credulous | Graveyard "
      "niches that abstained |")
    A("|---|---|---|---|---|")
    for t in TIERS:
        s = a["tiers"][t]
        A("| %s | %s | %s (of %d informative) | %s | %d of %d |" % (
            t, s["hit_rate"], s["false_positive_rate_informative"],
            s["informative_negatives"], s["false_positive_rate_credulous"],
            len(s["graveyard_abstained"]), len(GRAVEYARDS)))
    A("\n**The two FP columns are the crux of the whole report.** *Credulous* counts every "
      "abstention as a correct rejection - it is the number you get if you forget that CQC "
      "has no power to register an ice bath. *Honest* counts only the niches a tier could "
      "actually have fired on. Where the honest column rests on 1-2 niches it is not a "
      "rate, it is an anecdote with a decimal point.\n")
    for t in TIERS:
        if a["tiers"][t].get("warning"):
            A("- **%s**: %s\n" % (t, a["tiers"][t]["warning"]))

    A("\n## 4. What this n permits\n")
    for pair, g in a["lead_times"].items():
        if g.get("power"):
            A("- **%s** (n=%d): %s\n" % (pair, g["n"], g["power"]["verdict"]))

    A("\n## 5. Survivorship correction (T3)\n")
    A("| Niche | Active | Archived recovered | Historic understatement if uncorrected | "
      "Pre-2019 understatement | Onset: active-only | Onset: corrected |")
    A("|---|---|---|---|---|---|---|")
    for n in NICHES:
        sv = r[n["key"]].get("t3_survivorship")
        if not sv or not sv["n_active"]:
            continue
        A("| %s | %d | %d | %s%% | %s%% | %s | %s |" % (
            n["label"], sv["n_active"], sv["n_archived_recovered"],
            sv["understatement_pct"], sv["pre2019_understatement_pct"],
            sv["onset_active_only"] or "-", sv["onset_corrected"] or "-"))
    A("\nWhere the last two columns differ, the active-only file would have handed you the "
      "**wrong onset date - and always a later one**, because every missing clinic is in "
      "the past. That is the survivorship bias, measured rather than asserted.\n")

    A("\n## 6. Does the answer survive moving the boom threshold?\n")
    A("| Pair | growth>=1.25x | growth>=1.5x (shipped) | growth>=2.0x |")
    A("|---|---|---|---|")
    for pair in list(p["sensitivity"]["growth_x=1.5"].keys()):
        cells = []
        for gx in ("growth_x=1.25", "growth_x=1.5", "growth_x=2.0"):
            g = p["sensitivity"][gx][pair]
            cells.append("median %s (n=%d, %d in order)"
                         % (g["median_gap"], g["n"], g["n_in_predicted_order"]))
        A("| %s | %s |" % (pair, " | ".join(cells)))
    A("\nIf the sign of a median gap flips across this row, that ordering is an artefact of "
      "the threshold I chose and **must not be reported as a finding**.\n")

    A("\n## 7. Where the estimator choice changes the answer\n")
    if a["estimator_disagreements"]:
        A("| Niche | Tier | Robust (shipped) | The brief's estimator | Months where the "
          "brief's YoY divides by zero |")
        A("|---|---|---|---|---|")
        for d in a["estimator_disagreements"]:
            A("| %s | %s | %s | %s | %s |" % (
                d["niche"], d["tier"], d["robust"] or "no onset",
                d["spec"] or "no onset", d["spec_undefined_months"]))
        A("\nRead the last column: those are months where the brief's raw-YoY ratio divides "
          "by zero and that estimator is simply blind.\n")
    else:
        A("None - the two estimators agree everywhere they can both see. Reassuring.\n")

    A("\n## 8. T2 cohort survival (hindsight only - NOT usable live)\n")
    A("Share of each year's incorporation cohort now dissolved. Compare only DOWN a column: "
      "a 2023 cohort has not had time to die. **This cannot be used by the live radar** - "
      "you cannot know a fresh cohort's survival rate, and a fresh cohort is exactly the one "
      "you care about. Diagnostic, not predictive.\n")
    yrs = [str(y) for y in range(2016, 2023)]
    A("| Niche | " + " | ".join(yrs) + " |")
    A("|---" * (len(yrs) + 1) + "|")
    for n in NICHES:
        sv = r[n["key"]].get("t2_cohort_survival") or {}
        cells = []
        for y in yrs:
            c = sv.get(y)
            cells.append("%s%% (n=%d)" % (c["dead_pct"], c["n"]) if c and c["n"] >= 3 else "-")
        A("| %s | %s |" % (n["label"], " | ".join(cells)))

    A("\n## 9. Why each graveyard niche is in the graveyard\n")
    for n in GRAVEYARDS + [x for x in NICHES if x["cls"] == UNRESOLVED]:
        A("**%s** (%s) - %s\n" % (n["label"], n["cls"], n["why"]))

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# =========================================================================
def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        return core_selftest()
    build(no_trends="--no-trends" in args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
