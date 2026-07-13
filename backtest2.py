#!/usr/bin/env python3
"""
BACKTEST 2 - the backtest that CAN actually be run.

WHY THIS FILE EXISTS
--------------------
backtest.py was built around a false constraint. The claim was: "the radar cannot be
validated, because OpenPrescribing only serves 60 months and the ADHD boom predates
the window." That is true of T4 ONLY, and T4 is the tier a buyer cares least about.

    T1 Google Trends        history to 2004
    T2 Companies House      history to the 1800s
    T3 CQC registrations    history to 2010 (the HSCA regime start)
    T4 OpenPrescribing      history to ~2021, and 403s datacentre IPs

Three of the four tiers - and the only three that precede a purchase - have more than
a decade of retrievable monthly history. So the tier ordering T1 -> T2 -> T3 CAN be
backtested against every UK private-pay boom since c.2015. This file does that.
T4 IS DROPPED ENTIRELY. It is not withheld, not zeroed, not imputed: it is absent, and
the report says so in words rather than emitting an empty column that looks like data.

THE ONE INSIGHT THAT MAKES T2 CHEAP
-----------------------------------
backtest.py PAGED THROUGH COMPANIES to build its T2 series - hundreds of calls per
niche, capped, and still incomplete. It never needed to. Companies House
advanced-search returns a `hits` TOTAL alongside the items:

    /advanced-search/companies?company_name_includes=menopause
        &incorporated_from=2019-03-01&incorporated_to=2019-03-31&size=1
    -> {"items": [...1 item...], "hits": 14}

`hits` is the monthly count. ONE call gives one month. 198 months x ~30 keywords is
~6,000 calls, which at the documented 600-per-5-minutes limit is about an hour, is
free, is resumable, and reaches back to 2010. That is the whole T2 problem solved.

THE THING THAT NEARLY INVALIDATED THE WHOLE STUDY
-------------------------------------------------
Building this surfaced a problem nobody had asked about, and it is the most important
output here. The estimator does not fire the month a boom starts - it fires once the
boom is undeniable. That lag is LONGER for series that are thin and noisy, and the tiers
are not equally thin: T1 is a smooth 0-100 index, T2 is ~6 new companies a month, T3 is
~3 new clinics a month.

So the pipeline reports T1 -> T2 -> T3 EVEN WHEN ALL THREE BOOMS HAPPEN IN THE SAME
MONTH. Run this file's own fixtures with a TRUE lead of zero and it still comes back with
T1 leading T2 by ~2 months and T2 leading T3 by ~4 months. Pure measurement artefact.

Which means a live run that measured "T2 leads T3 by 4 months" would be reporting NOTHING
AT ALL, and reporting it as a finding. So calibrate_null() measures that artefact, the
report scores every real gap against it, and any gap that fails to beat the null is
declared not-evidence. That is the difference between an instrument and a random number
generator, and it cost about forty lines.

IT ALSO BREAKS THE SIGN TEST, WHICH IS WORSE
--------------------------------------------
backtest_core's sign test asks "if the tiers were unordered, each niche is a coin flip -
what are the odds of this many landing in the predicted order?" and tests against p=0.5.
The null calibration shows that is simply false. With a TRUE lead of zero this pipeline
lands the niches "in the predicted order" 64-97% of the time - T1->T3 is the worst at
~97%, because T1 is smooth and T3 is thin, so T1 essentially ALWAYS appears to lead.

So a flawless 8/8 sweep on T1->T3 scores p=0.0039 against a coin flip and looks like a
discovery, when 8/8 IS THE EXPECTED RESULT OF NO EFFECT WHATSOEVER. Every sign test here
is therefore run against the CALIBRATED null instead, and both numbers are printed so the
size of the error is visible. Fixture 40 asserts this and exists to stop anyone
"simplifying" it back.

WHAT THIS FILE IS HONEST ABOUT, UP FRONT
----------------------------------------
1. n = 8 positives, 8 graveyard. This CANNOT establish the tier ordering. Nothing at
   this n can. It CAN falsify it, and falsification is the only thing worth running.
2. The GRAVEYARD is the point. Without a negative set there is no false-positive rate,
   and a signal with no false-positive rate is a horoscope. If CBD fires as loudly on
   T1/T2 as ADHD does, then T1 and T2 do not discriminate, and this file should say so
   in bold. It is set up to be able to.
3. Two things here can ABSTAIN rather than reject, and both are counted as abstentions,
   never as correct rejections:
     - OUT_OF_SCOPE: CQC has no power to register an ice bath. That is not the radar
       being clever.
     - BELOW_FLOOR: the series never gets big enough for the estimator to be allowed to
       fire on it. A tier that is blind to a niche has not rejected it. backtest.py did
       not distinguish this from a genuine rejection; this file does, and it materially
       changes the false-positive rate.

RUN
    python3 backtest2.py --selftest     # fixtures only. No network. Proves assembly +
                                        #   analysis recover an INJECTED 6-month lead.
    python3 backtest2.py                # full run. T2 + T3. No SerpApi spend.
    python3 backtest2.py --trends       # ...also T1. Costs <= 16 SerpApi calls ONCE,
                                        #   then caches to disk forever.
    python3 backtest2.py --max-calls 2000    # stop early; the cache resumes next run.

Requires CH_API_KEY (free, instant, from developer.company-information.service.gov.uk).
SERPAPI_KEY only for --trends.

Stdlib only.
"""

import os
import re
import sys
import json
import time
import math
import base64
import shutil
import zipfile
import calendar
import tempfile
import argparse
import datetime as dt
import itertools
import statistics
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # radar-app/
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# THE ESTIMATOR IS NOT REDEFINED HERE. backtest_core.py's onset_robust() is already
# validated against 21 synthetic fixtures (python3 backtest_core.py). Writing a second
# onset estimator would mean two things to trust instead of one.
from backtest_core import (                                    # noqa: E402
    onset_robust, onset_spec, rolling_sum, median_ci, power_note, binom_tail,
    FLOORS, LOW_COUNT, GROWTH_X,
    selftest as core_selftest,
)

DATA = os.path.join(HERE, "data")
OUT_JSON = os.path.join(HERE, "backtest2.json")
OUT_MD = os.path.join(HERE, "backtest2.md")
CH_CACHE = os.path.join(DATA, "backtest2_ch.json")          # {keyword: {"YYYY-MM": hits}}
CH_PROBE = os.path.join(DATA, "backtest2_ch_probe.json")
CQC_CACHE = os.path.join(DATA, "backtest2_cqc.json")
TRENDS_CACHE = os.path.join(DATA, "backtest_trends.json")   # SerpApi: paid once, ever
# backtest.py already cached SerpApi for 13 of our 16 terms, on the SAME 2012-2026
# window. Read it if it is there; it saves 13 of 16 calls. Never written to.
PARENT_TRENDS = os.path.join(ROOT, "data", "backtest_trends.json")

# ---------------------------------------------------------------- tier windows
# Each tier gets its OWN axis, because each source's history starts somewhere different
# and pretending otherwise would silently feed garbage into the estimator's baselines.
#
# T1 2012-01: matches backtest.py's SerpApi window EXACTLY, so its paid cache is reusable
#             byte-for-byte. Google Trends rescales its 0-100 index to whatever window
#             you ask for, so a cache fetched on a DIFFERENT window is not interchangeable
#             - that is why the window is pinned rather than widened.
# T2 2010-01: arbitrary; Companies House would happily go back to 1990. 2010 gives every
#             niche 3+ years of warm-up before the earliest boom we care about (cryo,
#             c.2016) and keeps the call budget at ~6k.
# T3 2014-01: NOT arbitrary, and this is the single most important data-quality decision
#             in the file. See HSCA_WAVES below.
T1_START, T2_START, T3_START = "2012-01", "2010-01", "2014-01"
END = "2026-06"                                  # last month treated as complete
TIERS = ["T1", "T2", "T3"]
TIER_NAME = {"T1": "INTENT (search)", "T2": "ENTRY (new companies)",
             "T3": "CAPACITY (new CQC clinics)"}

# CQC's HSCA registration regime did not start when clinics started. It was switched on
# in waves, and EVERY provider already trading on the switch-on date was stamped with the
# regime date as its "Location HSCA start date". So the file contains enormous artificial
# spikes: essentially the entire pre-existing independent-healthcare population appears to
# have "registered" in October 2010, and essentially every GP practice in England appears
# to have "opened" in April 2013.
#
# Feed that to a boom detector and it finds the biggest boom in recorded history, in every
# niche, in the same month. Starting the T3 axis at 2014-01 puts every wave outside the
# series - not just outside the scan, but outside the BASELINES too, which is the part
# that would otherwise poison onsets years later. Cost: T3 cannot see anything before
# ~2017. Every boom in the positive set is later than that. Verified at runtime, not
# assumed: the code flags any residual spike it finds.
HSCA_WAVES = {"2010-04": "NHS trusts", "2010-10": "adult social care + independent health",
              "2011-04": "primary dental + independent ambulance",
              "2012-04": "misc. late cohorts", "2013-04": "primary medical services (GPs)"}

CH_KEY = os.environ.get("CH_API_KEY", "").strip()
SERP_KEY = os.environ.get("SERPAPI_KEY", "").strip()
CH_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"
CQC_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"

# CH documents 600 requests / 5 minutes. Run at 500 to leave headroom for the live radar,
# which shares the key.
CH_RATE, CH_PER = 500, 300.0
DEFAULT_MAX_CALLS = 7000

POSITIVE, GRAVEYARD = "positive", "graveyard"
DIAG = {}


# =============================================================================
#  1. THE NICHE SET
# =============================================================================
# ch: Companies House keywords. Passed to company_name_includes VERBATIM. The FIRST one
#     is the PRIMARY - the whole analysis is re-run on primary-only as a robustness check,
#     because summing keyword hit-counts double-counts any company whose name contains two
#     of them ("Menopause & Perimenopause Clinic Ltd"). See T2_SUMMING_NOTE.
# cqc: matched against the CQC LOCATION NAME with a word-boundary matcher. Trailing "*"
#     means stem-match, bare means whole-word - the convention from taxonomy.py, which
#     exists precisely because a prefix-only matcher classified "Skinner & Partners" as an
#     aesthetics clinic.
# t3_scope: is this activity CQC-REGISTRABLE in England AT ALL? If not, T3 physically
#     cannot fire and MUST NOT be credited with a correct rejection.
NICHES = [
    # ------------------------------------------------------------- POSITIVES (8)
    dict(key="adhd", label="ADHD (private assessment)", cls=POSITIVE,
         ch=["adhd", "neurodiversity"],
         cqc=["adhd", "neurodiver*", "attention deficit"],
         trends_q="ADHD assessment", t3_scope=True,
         why="The benchmark case. NHS waits + Right to Choose drove a real private "
             "assessment boom c.2021-24; the 2023 Elvanse shortage is downstream proof."),

    dict(key="glp1", label="Weight loss / GLP-1", cls=POSITIVE,
         ch=["weight loss", "semaglutide"],
         cqc=["weight loss", "weight management", "obesity", "bariatric*"],
         trends_q="weight loss injection", t3_scope=True,
         why="Unambiguous. Wegovy UK launch Sep-2023, Mounjaro 2024. The largest "
             "private-pay healthcare event of the decade."),

    dict(key="menopause", label="Menopause / HRT", cls=POSITIVE,
         ch=["menopause", "perimenopause"],
         cqc=["menopaus*", "perimenopaus*", "hrt"],
         trends_q="menopause clinic", t3_scope=True,
         why="Davina McCall, Channel 4, May-2021 is a clean dateable exogenous shock, "
             "followed by the 2022 HRT supply crisis. The closest thing here to a natural "
             "experiment: if the tiers ever fire in order, they should do it here.",
         caveats=["'hrt' is excluded from the Companies House keywords: as a 3-letter "
                  "token it drags in unrelated names, and unlike backtest.py we get no "
                  "company names back to re-filter (see PRECISION PROBE)."]),

    dict(key="trt", label="Men's health / TRT", cls=POSITIVE,
         ch=["testosterone", "mens health"],
         cqc=["testosterone", "mens health", "androlog*", "hypogonad*"],
         trends_q="testosterone replacement therapy", t3_scope=True,
         why="Sustained private TRT clinic growth (Optimale, Balance My Hormones). Real, "
             "but a slower boom than the others - a useful hard case."),

    dict(key="hair", label="Hair transplant / restoration", cls=POSITIVE,
         ch=["hair transplant", "hair restoration"],
         cqc=["hair transplant", "hair restoration", "hair clinic"],
         trends_q="hair transplant", t3_scope=True,
         why="A real UK private-pay boom alongside a large Turkey-outbound market."),

    dict(key="autism", label="Autism assessment", cls=POSITIVE,
         ch=["autism", "autistic"],
         cqc=["autis*", "neurodevelopmental", "asd assessment"],
         trends_q="autism assessment", t3_scope=True,
         why="Same driver as ADHD (NHS waits, Right to Choose) with a ~1-2 year lag. "
             "Included as a semi-independent REPLICATION of the ADHD case rather than a "
             "wholly new one - and it is only semi-independent, because many providers "
             "assess both. Correlated evidence, not fresh evidence.",
         caveats=["Not independent of ADHD: many operators sell both assessments, so "
                  "these two niches share companies and clinics. Treating them as two "
                  "observations OVERSTATES n. Reported, and the sign test is shown with "
                  "and without it."]),

    dict(key="privategp", label="Private GP", cls=POSITIVE,
         ch=["private gp", "private doctor"],
         cqc=["private gp", "private doctor"],
         trends_q="private GP", t3_scope=True,
         why="A steady, well-documented private-pay shift after 2020 as NHS access "
             "deteriorated.",
         caveats=["T3 IS NEARLY USELESS HERE and the number should not be trusted. CQC's "
                  "GP population is overwhelmingly NHS, and April-2013 is when every NHS "
                  "practice in England was stamped into the register at once. Name-matching "
                  "on 'private gp' finds only the minority that self-label. Kept in, "
                  "flagged loudly, and the T3 stats are reported with and without it."])
         ,

    dict(key="ivf", label="IVF / fertility", cls=POSITIVE,
         ch=["fertility", "ivf"],
         cqc=["fertil*", "ivf", "reproductive medicine"],
         trends_q="IVF clinic", t3_scope=True,
         why="A long, real, private-pay growth market. Deliberately included as the SLOW "
             "case: if the tiers only line up for explosive booms, a signal that needs an "
             "explosion to work is not much of an early-warning system."),

    # ------------------------------------------------------------- GRAVEYARD (8)
    # Niches whose search interest spiked hard and which produced NO scaled UK operator
    # and NO roll-up. These are what generate the false-positive rate. Without them this
    # study measures sensitivity and nothing else, and sensitivity alone is worthless -
    # a detector that fires on everything has a 100% hit rate.
    dict(key="cbd", label="CBD / cannabidiol", cls=GRAVEYARD,
         ch=["cbd", "cannabidiol"],
         cqc=["cbd", "cannabidiol", "cannabis"],
         trends_q="CBD oil", t3_scope=False,
         why="THE KEY NEGATIVE, and the single case most likely to sink T1+T2 on its own. "
             "T1 spiked violently in 2018-19 AND T2 fired hard - roughly 500 UK companies "
             "sat behind the ~12,000 products on the FSA novel-foods list. The FSA backlog "
             "then froze the market and a large share of those companies have since "
             "dissolved. If the early tiers fired this loudly for a wipeout, the early "
             "tiers cannot discriminate. THIS IS THE RESULT TO LOOK FOR FIRST."),

    dict(key="ivdrip", label="IV vitamin drips", cls=GRAVEYARD,
         ch=["iv drip", "vitamin drip"],
         cqc=["drip", "iv therapy", "intravenous"],
         trends_q="IV vitamin drip", t3_scope=True,
         why="THE HARDEST AND MOST INFORMATIVE NEGATIVE. IV administration of a "
             "prescription-only product (0.9% saline included) for wellbeing IS a CQC "
             "regulated activity - so unlike the rest of the graveyard, ALL THREE tiers "
             "can fire here. It is also the ONLY graveyard niche that gives T3 an "
             "informative negative at all. Commercially it produced no scaled UK operator "
             "in ~8 years.",
         caveats=["CONTESTABLE. Get A Drip and REVIV do exist. This is 'commercially "
                  "marginal', not 'zero'. It is the negative most open to argument, and "
                  "T3's entire specificity claim rests on it."]),

    dict(key="cryo", label="Cryotherapy (whole-body)", cls=GRAVEYARD,
         ch=["cryotherapy"],
         cqc=["cryotherapy"],
         trends_q="cryotherapy", t3_scope=False,
         why="Spiked c.2016-18 on athlete endorsement. Not a CQC regulated activity. No "
             "scaled UK operator emerged."),

    dict(key="coldwater", label="Cold-water therapy / ice baths", cls=GRAVEYARD,
         ch=["ice bath", "cold plunge"],
         cqc=["ice bath", "cold plunge", "cold water"],
         trends_q="ice bath", t3_scope=False,
         why="An enormous T1 spike 2021-24 (Wim Hof, Huberman) with zero clinical "
             "infrastructure behind it. The purest test of 'T1 blares and nothing follows'."),

    dict(key="psychedelics", label="Psychedelics / psilocybin", cls=GRAVEYARD,
         ch=["psychedelic", "psilocybin"],
         cqc=["psychedelic", "psilocybin"],
         trends_q="psilocybin therapy", t3_scope=False,
         why="T1 and T2 both fired - Compass Pathways' 2020 IPO, Small Pharma, Beckley "
             "Psytech, plus a long tail of shells. Psilocybin is Schedule 1, so no lawful "
             "UK treatment clinic can exist and T3 cannot fire BY CONSTRUCTION.",
         caveats=["T3's 'correct rejection' here is worth NOTHING. The drug is illegal. "
                  "That is the Misuse of Drugs Act doing the work, not the radar. Counted "
                  "as an abstention."]),

    dict(key="nad", label="NAD+ infusions", cls=GRAVEYARD,
         ch=["nad+", "nicotinamide"],
         cqc=["nad"],
         trends_q="NAD+ infusion", t3_scope=True,
         why="Placed in the graveyard AS INSTRUCTED, but under protest - see the caveat. "
             "Longevity-clinic staple, no scaled UK operator to date.",
         caveats=["THIS LABEL MAY BE WRONG AND THE STUDY KNOWS IT. NAD+ is still RISING. "
                  "Calling a live, unresolved niche a 'dud' assumes the answer to the "
                  "question the radar exists to ask, and if NAD+ turns out to be a real "
                  "boom then every false positive it generates here is actually a true "
                  "positive. The headline false-positive rates are therefore reported "
                  "BOTH WITH AND WITHOUT NAD+, and the difference is the size of the "
                  "assumption. Do not quote one number."]),

    dict(key="hbot", label="Hyperbaric oxygen therapy", cls=GRAVEYARD,
         ch=["hyperbaric"],
         cqc=["hyperbaric"],
         trends_q="hyperbaric oxygen therapy", t3_scope=False,
         why="Recurrent biohacking spikes. UK supply is dominated by decades-old "
             "charity-run MS therapy centres, not new commercial entrants.",
         caveats=["t3_scope=False is CONTESTABLE: HBOT for a licensed indication would be "
                  "a regulated activity. The charity centres largely sit outside CQC. "
                  "Marked out of scope, i.e. T3 gets NO credit either way."]),

    dict(key="redlight", label="Red-light therapy", cls=GRAVEYARD,
         ch=["red light therapy", "photobiomodulation"],
         cqc=["red light", "photobiomodulation"],
         trends_q="red light therapy", t3_scope=False,
         why="Resolved into a consumer-DEVICE market (masks, panels), not a clinic market. "
             "Tests the case where demand is real but the delivery model is retail - which "
             "a clinic roll-up cannot buy."),
]

BY_KEY = {n["key"]: n for n in NICHES}
POSITIVES = [n for n in NICHES if n["cls"] == POSITIVE]
GRAVEYARDS = [n for n in NICHES if n["cls"] == GRAVEYARD]
ALL_KEYWORDS = sorted({k for n in NICHES for k in n["ch"]})

T2_SUMMING_NOTE = (
    "T2 sums the monthly hit-counts of a niche's keywords. A company called 'Menopause & "
    "Perimenopause Clinic Ltd' is therefore counted twice. This inflates the LEVEL. It "
    "does NOT move the onset DATE, because the estimator works on the log-ratio of the "
    "series to its own past: a constant multiplicative inflation c cancels in "
    "ln((cR+K)/(cB+K)) for any K small relative to R. It only bites if the overlap "
    "FRACTION changes over time. Guarded anyway: every onset is recomputed on the PRIMARY "
    "KEYWORD ALONE, which cannot double-count, and any disagreement is reported.")


# =============================================================================
#  2. MONTHS, MATCHING, IO
# =============================================================================
def m_add(m, k):
    i = int(m[:4]) * 12 + (int(m[5:7]) - 1) + k
    return "%04d-%02d" % (i // 12, i % 12 + 1)


def m_diff(a, b):
    """b - a in months. POSITIVE => b is LATER than a."""
    if not a or not b:
        return None
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def axis(start, end=END):
    out, m = [], start
    while m <= end:
        out.append(m)
        m = m_add(m, 1)
    return out


def month_bounds(m):
    y, mo = int(m[:4]), int(m[5:7])
    return "%s-01" % m, "%s-%02d" % (m, calendar.monthrange(y, mo)[1])


def _rx(key):
    """taxonomy.py's convention: 'foo*' = stem, 'foo' = whole word."""
    k = key.lower()
    if k.endswith("*"):
        return re.compile(r"\b" + re.escape(k[:-1]))
    return re.compile(r"\b" + re.escape(k) + r"\b")


_COMPILED = {k: [_rx(t) for t in n["cqc"]] for k, n in BY_KEY.items()}
_CH_RX = {k: _rx(k if " " in k or len(k) > 5 else k) for k in ALL_KEYWORDS}


def cqc_hit(key, name):
    t = (name or "").lower()
    return any(rx.search(t) for rx in _COMPILED[key])


def load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


class Throttle:
    """Sliding-window limiter. CH allows 600/5min; we run at 500."""

    def __init__(self, n=CH_RATE, per=CH_PER):
        self.n, self.per, self.hist = n, per, deque()

    def wait(self):
        now = time.time()
        while self.hist and now - self.hist[0] > self.per:
            self.hist.popleft()
        if len(self.hist) >= self.n:
            nap = self.per - (now - self.hist[0]) + 0.5
            if nap > 0:
                time.sleep(nap)
        self.hist.append(time.time())


def http_json(url, headers=None, timeout=45, retries=4):
    """-> (obj | None, err | None). Never raises."""
    hdr = {"User-Agent": "healthcare-radar-backtest2"}
    hdr.update(headers or {})
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            if e.code == 429:                                  # rate limited
                nap = 8.0 * (a + 1)
                try:
                    nap = max(nap, float(e.headers.get("Retry-After") or 0))
                except Exception:
                    pass
                time.sleep(min(nap, 90))
                continue
            if e.code in (401, 403):                           # never retryable
                return None, "HTTP %d" % e.code
            if a == retries - 1:
                return None, "HTTP %d" % e.code
        except Exception as e:
            if a == retries - 1:
                return None, type(e).__name__
        time.sleep(1.5 * (a + 1))
    return None, "exhausted"


def http_text(url, timeout=60):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (healthcare-radar-backtest2)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def download(url, path, timeout=600):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (healthcare-radar-backtest2)"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    return path


# =============================================================================
#  3. T2 - COMPANIES HOUSE, ONE CALL PER (KEYWORD, MONTH)
# =============================================================================
# Dissolved companies are INCLUDED, deliberately. A company incorporated in 2019 and
# dead by 2022 still fired the T2 signal in 2019. Filtering them out would be
# survivorship bias pointing the wrong way: it would delete exactly the graveyard
# cohorts this study is trying to catch. So no company_status filter is sent.
def ch_month_hits(keyword, month, throttle):
    lo, hi = month_bounds(month)
    q = urllib.parse.urlencode({"company_name_includes": keyword,
                                "incorporated_from": lo, "incorporated_to": hi,
                                "size": 1})
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    throttle.wait()
    d, err = http_json(CH_URL + "?" + q, {"Authorization": "Basic " + auth})
    if d is None:
        return None, err
    h = d.get("hits")
    if h is None:
        return None, "no-hits-field"
    try:
        return int(h), None
    except (TypeError, ValueError):
        return None, "bad-hits"


def ch_precision_probe(keyword, throttle):
    """THE COST OF THE hits TRICK, MEASURED.

    Paging returned company NAMES, so backtest.py could re-filter them with a strict
    word-boundary matcher and throw out 'CBDESIGN LTD'. A hits COUNT gives us no names,
    so we cannot re-filter - we are stuck with whatever Companies House thinks
    company_name_includes means. For a 3-letter keyword like 'cbd' or 'nad' that is a
    real precision risk, and an unmeasured precision risk is just a lie with a number
    attached.

    So: ONE call per keyword pulls 100 names across the whole window, and we report the
    share that survive our own strict matcher. NOT a random sample (CH's result ordering
    is unspecified), so this is a smell test, not an estimate. A keyword scoring < 0.8 is
    flagged CONTAMINATED in the report and its niche's T2 result should be discounted.
    """
    q = urllib.parse.urlencode({"company_name_includes": keyword,
                                "incorporated_from": "%s-01" % T2_START,
                                "incorporated_to": month_bounds(END)[1],
                                "size": 100})
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    throttle.wait()
    d, err = http_json(CH_URL + "?" + q, {"Authorization": "Basic " + auth})
    if d is None:
        return {"error": err}
    items = d.get("items") or []
    rx = _rx(keyword)
    names = [(it.get("company_name") or "") for it in items]
    ok = [nm for nm in names if rx.search(nm.lower())]
    bad = [nm for nm in names if not rx.search(nm.lower())][:6]
    return {"sampled": len(names),
            "precision": round(len(ok) / len(names), 3) if names else None,
            "examples_rejected": bad,
            "hits_total": d.get("hits")}


def fetch_t2(max_calls, force=False):
    """{keyword: {month: hits}}. Resumable: every cell is cached, so a run that dies or
    hits the budget cap picks up exactly where it stopped."""
    months = axis(T2_START)
    cache = {} if force else (load(CH_CACHE) or {})
    probes = {} if force else (load(CH_PROBE) or {})

    todo = [(k, m) for k in ALL_KEYWORDS for m in months
            if str(cache.get(k, {}).get(m, "")) == ""]
    DIAG["t2_cells_total"] = len(ALL_KEYWORDS) * len(months)
    DIAG["t2_cells_cached"] = DIAG["t2_cells_total"] - len(todo)

    if not CH_KEY:
        DIAG["t2"] = ("CH_API_KEY not set. T2 uses the cache only (%d/%d cells). Get a "
                      "free key at developer.company-information.service.gov.uk."
                      % (DIAG["t2_cells_cached"], DIAG["t2_cells_total"]))
        return cache, probes

    thr, calls, errs = Throttle(), 0, defaultdict(int)
    print("  T2: %d keywords x %d months = %d cells; %d cached, %d to fetch (cap %d)"
          % (len(ALL_KEYWORDS), len(months), DIAG["t2_cells_total"],
             DIAG["t2_cells_cached"], len(todo), max_calls))
    if len(todo) > max_calls:
        print("  T2: BUDGET CAP will bite. Re-run to resume - the cache persists.")

    try:
        for kw in ALL_KEYWORDS:
            if kw not in probes and calls < max_calls:
                probes[kw] = ch_precision_probe(kw, thr)
                calls += 1
        for i, (kw, m) in enumerate(todo):
            if calls >= max_calls:
                DIAG["t2_hit_budget_cap"] = True
                break
            h, err = ch_month_hits(kw, m, thr)
            calls += 1
            if h is None:
                errs[err] += 1
                if err in ("HTTP 401", "HTTP 403"):
                    DIAG["t2_fatal"] = ("Companies House returned %s - the key is missing, "
                                        "wrong, or unauthorised. Aborting T2." % err)
                    break
                continue
            cache.setdefault(kw, {})[m] = h
            if calls % 250 == 0:
                save(CH_CACHE, cache)
                print("    ... %d/%d calls, %d errors" % (calls, min(len(todo), max_calls),
                                                          sum(errs.values())))
    finally:
        save(CH_CACHE, cache)
        save(CH_PROBE, probes)

    DIAG["t2_calls_spent"] = calls
    DIAG["t2_errors"] = dict(errs)
    filled = sum(len(v) for v in cache.values())
    DIAG["t2_coverage"] = round(filled / max(1, DIAG["t2_cells_total"]), 3)
    DIAG["t2"] = "ok - %d/%d cells" % (filled, DIAG["t2_cells_total"])
    return cache, probes


def t2_series(niche, cache, primary_only=False):
    """Monthly incorporation count. None if the cache is too sparse to be honest about."""
    months = axis(T2_START)
    kws = niche["ch"][:1] if primary_only else niche["ch"]
    have = [k for k in kws if cache.get(k)]
    if not have:
        return None, 0.0
    vals, seen = [], 0
    for m in months:
        v = 0.0
        got = False
        for k in have:
            h = cache[k].get(m)
            if h is not None:
                v += float(h)
                got = True
        vals.append(v)
        seen += 1 if got else 0
    cov = seen / len(months)
    # A half-empty series is not a series. Better to withhold it than to let the estimator
    # read the missing months as zeros and call the recovery a boom.
    if cov < 0.9:
        return None, cov
    return vals, cov


# =============================================================================
#  4. T3 - CQC, WITH THE SURVIVORSHIP BIAS ACTUALLY FIXED
# =============================================================================
# The "care directory with filters" ODS lists only locations that are STILL ACTIVE. Every
# clinic that opened and then closed is simply absent. Build a monthly registration
# history from that file alone and older months are systematically understated, which
# manufactures a fake upward trend in EVERY niche and pushes EVERY T3 onset LATER.
#
# For a study whose entire output is the GAP BETWEEN ONSETS, a bias that moves one tier's
# onsets in a known direction is not a footnote - it is the result. It would inflate the
# apparent T2 -> T3 lead time, which is precisely the number a buyer would act on.
#
# CQC publishes a DEACTIVATED-LOCATIONS file on the same page, with HSCA start dates.
# Union the two and the history is complete. This module does that, measures the size of
# the correction, and reports every T3 onset BOTH WAYS. If the two columns differ, the
# active-only file was lying to you, and by how much is now a number.
NS_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
NS_TX = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}


def ods_rows(path, max_cols=260):
    """Stream (sheet, [cells]) from an .ods. Same hardened parser as investability.py:
    number-columns-repeated, covered-table-cell (which OCCUPIES a column and will shift
    every column right of it if dropped), and number-rows-repeated all handled."""
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
            for c in el:
                if c.tag == NS_T + "table-cell":
                    v = c.get(NS_O + "date-value") or ""
                    v = v[:10] if v else " ".join(
                        "".join(p.itertext()) for p in c.findall(NS_TX + "p")).strip()
                elif c.tag == NS_T + "covered-table-cell":
                    v = ""
                else:
                    continue
                try:
                    rep = int(c.get(NS_T + "number-columns-repeated") or 1)
                except ValueError:
                    rep = 1
                for _ in range(max(1, min(rep, max_cols))):
                    row.append(v)
                    if len(row) >= max_cols:
                        break
                if len(row) >= max_cols:
                    break
            try:
                rrep = int(el.get(NS_T + "number-rows-repeated") or 1)
            except ValueError:
                rrep = 1
            rrep = 1 if not any(row) else max(1, min(rrep, 50))
            el.clear()
            for _ in range(rrep):
                yield sheet, row


def parse_date(s):
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})[/\- ]([A-Za-z]{3,9})[/\- ](\d{4})", s)
    if m:
        mon = next((v for k, v in _MONTHS.items()
                    if k.startswith(m.group(2).lower()[:3])), None)
        if mon:
            try:
                return dt.date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)      # UK d/m/Y
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def cqc_urls():
    html = http_text(CQC_PAGE)
    if not html:
        return None, None

    def hunt(*pats):
        for p in pats:
            m = re.search(p, html, re.I)
            if m:
                u = m.group(1)
                return u if u.startswith("http") else "https://www.cqc.org.uk" + u
        return None

    return (hunt(r'href="([^"]*HSCA_Active_Locations\.ods)"',
                 r'href="([^"]*[Aa]ctive[_ ]?[Ll]ocations[^"]*\.ods)"'),
            hunt(r'href="([^"]*[Dd]eactivated[^"]*\.ods)"',
                 r'href="([^"]*[Aa]rchived[^"]*[Ll]ocations[^"]*\.ods)"'))


def cqc_read(url, tag):
    """-> [(name, postcode, start_date)]. [] on any failure, with a DIAG entry."""
    if not url:
        DIAG["cqc_%s_err" % tag] = "file URL not found on the CQC transparency page"
        return []
    path = os.path.join(tempfile.gettempdir(), "bt2_cqc_%s.ods" % tag)
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 10000:
            download(url, path)
    except Exception as e:
        DIAG["cqc_%s_err" % tag] = repr(e)[:160]
        return []

    out, cols = [], None
    try:
        for _sheet, row in ods_rows(path):
            if cols is None:
                low = [(c or "").strip().lower() for c in row]
                short = [c if 0 < len(c) < 70 else "" for c in low]
                if "location id" not in short:
                    continue

                def find(exact, *subs):
                    if exact in short:
                        return short.index(exact)
                    for j, c in enumerate(short):
                        if c and all(s in c for s in subs):
                            return j
                    return None

                cols = {"name": find("location name", "location", "name"),
                        "pc": find("location postal code", "postal code"),
                        "start": find("location hsca start date", "hsca start date")}
                if cols["start"] is None:
                    cols["start"] = find("", "start date")
                if cols["name"] is None or cols["start"] is None:
                    DIAG["cqc_%s_err" % tag] = (
                        "header found but Location Name / HSCA start date column missing - "
                        "CQC has renamed a column. FIX THE COLUMN MAP; do not ship the run.")
                    return []
                DIAG["cqc_%s_cols" % tag] = cols
                continue
            need = max(c for c in cols.values() if c is not None)
            if len(row) <= need:
                continue
            d = parse_date(row[cols["start"]])
            if d:
                pc = row[cols["pc"]] if cols["pc"] is not None else ""
                out.append((row[cols["name"]] or "", (pc or "").strip().upper(), d))
    except Exception as e:
        DIAG["cqc_%s_err" % tag] = "parse failed: %s" % repr(e)[:120]
        return []
    if cols is None:
        DIAG["cqc_%s_err" % tag] = "no sheet with a 'location id' header cell"
    DIAG["cqc_%s_rows" % tag] = len(out)
    DIAG["cqc_%s_has_postcode" % tag] = bool(cols and cols.get("pc") is not None)
    return out


def _dedupe(rows):
    """CQC archives a location and issues a NEW one on re-registration (legal-entity
    change, address move). Union the active and deactivated files naively and that single
    clinic becomes TWO 'new registrations'.

    Identity = (normalised name, postcode); keep the EARLIEST start date, because T3
    measures market ENTRY and a clinic enters once. Postcode is what stops this from
    collapsing a 200-site chain into one site - same name, different postcode, still two
    entries. If CQC ever drops the postcode column we fall back to (name, month), which
    is weaker, and we say so.
    """
    best = {}
    for nm, pc, d in rows:
        sig = (re.sub(r"[^a-z0-9]+", " ", (nm or "").lower()).strip(),
               pc or d.strftime("%Y-%m"))
        if sig not in best or d < best[sig][1]:
            best[sig] = (nm, d)
    return [v[1] for v in best.values()], len(rows) - len(best)


def fetch_t3(force=False):
    cached = None if force else load(CQC_CACHE)
    if cached:
        DIAG.update(cached.get("diag", {}))
        DIAG["t3"] = "cache hit"
        return cached["niches"]

    a_url, d_url = cqc_urls()
    DIAG["cqc_active_url"], DIAG["cqc_deactivated_url"] = a_url, d_url
    active, deact = cqc_read(a_url, "active"), cqc_read(d_url, "deact")
    DIAG["cqc_survivorship_corrected"] = bool(deact)
    if not deact:
        DIAG["cqc_WARNING"] = (
            "DEACTIVATED-LOCATIONS FILE NOT LOADED. T3 is ACTIVE-ONLY and therefore "
            "survivorship-biased: closed clinics are missing, older months are understated, "
            "and EVERY T3 onset is biased LATE - which inflates the very T2->T3 lead time "
            "this study is trying to measure. T3 lead times from this run are NOT SAFE TO "
            "QUOTE. Find the file on the CQC transparency page and re-run.")

    months = axis(T3_START)
    idx = {m: i for i, m in enumerate(months)}
    out = {}
    for n in NICHES:
        def pick(rows):
            return [(nm, pc, d) for nm, pc, d in rows if cqc_hit(n["key"], nm)]

        a_rows, d_rows = pick(active), pick(deact)
        a_dates, a_dup = _dedupe(a_rows)
        c_dates, c_dup = _dedupe(a_rows + d_rows)

        def hist(dates):
            v = [0.0] * len(months)
            pre, waves = 0, defaultdict(int)
            for d in dates:
                m = d.strftime("%Y-%m")
                if m in HSCA_WAVES:
                    waves[m] += 1
                i = idx.get(m)
                if i is None:
                    pre += 1                    # before T3_START - excluded on purpose
                else:
                    v[i] += 1
            return v, pre, dict(waves)

        av, a_pre, _ = hist(a_dates)
        cv, c_pre, c_waves = hist(c_dates)
        out[n["key"]] = {
            "active_only": av, "corrected": cv,
            "n_active": len(a_dates), "n_recovered": len(c_dates) - len(a_dates),
            "dedup_collapsed": c_dup, "dedup_collapsed_active": a_dup,
            "excluded_pre_%s" % T3_START: c_pre,
            "hsca_wave_rows": c_waves,
        }
        print("  T3 %-12s %4d active + %4d recovered  (%d dupes collapsed, "
              "%d rows pre-%s excluded)"
              % (n["key"], len(a_dates), len(c_dates) - len(a_dates), c_dup, c_pre,
                 T3_START))

    save(CQC_CACHE, {"diag": {k: v for k, v in DIAG.items() if k.startswith("cqc")},
                     "niches": out})
    return out


# =============================================================================
#  5. T1 - GOOGLE TRENDS. OPT-IN, PAID ONCE, CACHED FOREVER.
# =============================================================================
# COST: exactly one SerpApi call per term, because SerpApi accepts a custom date range and
# returns the whole 14-year monthly series in that one call. 16 terms = 16 calls, ONE TIME.
# The free tier is ~100/month and the live weekly job already eats ~80.
#
# BUT: backtest.py has ALREADY PAID for 13 of these 16 terms, on this exact window. Its
# cache is read first, so a --trends run costs 3 calls, not 16.
#
# The window is pinned to backtest.py's for that reason and one other: Google Trends
# rescales its 0-100 index across whatever range you request, so a series pulled on
# 2010-2026 is NOT the same series pulled on 2012-2026, and mixing them would be a silent
# unit error. Every term here uses the identical window, which is what a lead-lag
# COMPARISON actually needs, even though the absolute index values are meaningless.
def fetch_t1(enabled, force=False):
    own = {} if force else (load(TRENDS_CACHE) or {})
    inherited = load(PARENT_TRENDS) or {}
    merged = dict(inherited)
    merged.update(own)                     # our own cache wins on any collision

    want = {n["key"] for n in NICHES}
    have = {k for k in want if merged.get(k)}
    missing = sorted(want - have)
    DIAG["t1_inherited_from_backtest1"] = sorted(set(inherited) & want)

    if not missing:
        DIAG["t1"] = "cache hit for all %d terms - 0 SerpApi calls spent" % len(want)
        return {k: merged[k] for k in have}
    if not enabled:
        DIAG["t1"] = ("SKIPPED. %d/%d terms cached; %s missing. Re-run with --trends to "
                      "spend %d SerpApi calls (once, ever). T1 is WITHHELD for the missing "
                      "terms, not zeroed." % (len(have), len(want), missing, len(missing)))
        return {k: merged[k] for k in have}
    if not SERP_KEY:
        DIAG["t1"] = "--trends given but SERPAPI_KEY is not set. T1 WITHHELD."
        return {k: merged[k] for k in have}

    months = axis(T1_START)
    idx = {m: i for i, m in enumerate(months)}
    rng = "%s-01 %s-01" % (T1_START, END)
    calls = 0
    for key in missing:
        n = BY_KEY[key]
        url = ("https://serpapi.com/search.json?engine=google_trends&geo=GB"
               "&data_type=TIMESERIES&q=%s&date=%s&api_key=%s"
               % (urllib.parse.quote(n["trends_q"]), urllib.parse.quote(rng), SERP_KEY))
        d, err = http_json(url, timeout=90)
        calls += 1
        vals, got = [0.0] * len(months), 0
        try:
            for pt in d["interest_over_time"]["timeline_data"]:
                ts = pt.get("timestamp")
                m = (dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m")
                     if ts else None)
                i = idx.get(m)
                if i is not None:
                    vals[i] = float(pt["values"][0]["extracted_value"])
                    got += 1
        except Exception:
            print("  T1 %-12s FAILED (%s)" % (key, err or "bad payload"))
            continue
        if got < 24:
            print("  T1 %-12s only %d points - discarded" % (key, got))
            continue
        own[key], merged[key] = vals, vals
        print("  T1 %-12s ok (%d points)" % (key, got))
    save(TRENDS_CACHE, own)
    DIAG["serpapi_calls_spent"] = calls
    DIAG["t1"] = "fetched %d new term(s); %d spent" % (len(own), calls)
    return {k: v for k, v in merged.items() if k in want and v}


# =============================================================================
#  6. ASSEMBLY
# =============================================================================
def tier_state(n, tier, vals, months, growth_x=GROWTH_X):
    """FIRED / NO_ONSET / OUT_OF_SCOPE / BELOW_FLOOR / NO_DATA.

    The distinction between NO_ONSET and the two ABSTENTIONS is the ethical core of the
    scoring, and backtest.py did not draw the second one:

      NO_ONSET     the tier COULD have fired on this niche and did not. A real rejection.
                   Counts as a true negative on the graveyard.
      OUT_OF_SCOPE the tier is legally incapable of seeing this niche (CQC cannot register
                   an ice bath). An ABSTENTION.
      BELOW_FLOOR  the series never reaches the tier's minimum level, so the estimator is
                   FORBIDDEN to fire on it no matter what it does. Also an ABSTENTION -
                   and this one is easy to miss, because it looks exactly like a correct
                   rejection in the output.

    Score abstentions as correct rejections and you can drive the false-positive rate to
    zero without the radar doing anything at all. That is the single easiest way to lie
    with this study, so both are counted, listed, and excluded from the honest rate.
    """
    if tier == "T3" and not n["t3_scope"]:
        return {"state": "OUT_OF_SCOPE", "onset": None,
                "note": "not a CQC-registrable activity - T3 ABSTAINS, it does not reject"}
    if not vals or sum(vals) == 0:
        return {"state": "NO_DATA", "onset": None}

    floor = FLOORS.get(tier, {}).get("min_level", 0.0)
    peak_level = max([x for x in rolling_sum(vals, 12) if x is not None] or [0.0])
    if peak_level < floor:
        return {"state": "BELOW_FLOOR", "onset": None, "peak_12m": round(peak_level, 1),
                "floor": floor, "total": round(sum(vals), 1),
                "note": ("the series NEVER reaches this tier's minimum level (%.0f per 12 "
                         "months), so the estimator is structurally forbidden to fire on "
                         "it. This is an ABSTENTION, not a rejection - the tier is blind "
                         "here, which is exactly the condition a radar is in while a niche "
                         "is still small enough to be cheap." % floor)}

    rb = onset_robust(months, vals, tier, growth_x=growth_x)
    sp = onset_spec(months, vals)
    return {"state": "FIRED" if rb["onset"] else "NO_ONSET",
            "onset": rb["onset"],
            "z_at_onset": rb["z_at_onset"], "peak_z": rb["peak_z"],
            "growth_at_onset": rb["growth_at_onset"],
            "level_at_onset": rb["level_at_onset"],
            "baseline_at_onset": rb["baseline_at_onset"],
            "low_count_unreliable": rb["low_count_unreliable"],
            "peak_12m": round(peak_level, 1),
            "total": round(sum(vals), 1),
            "first_testable": (months[next((i for i in range(len(months))
                                            if i >= 36), 0)] if len(months) > 36 else None),
            "spec_onset": sp["onset"],
            "spec_undefined_months": sp["undefined_months"],
            "agrees_with_spec": rb["onset"] == sp["onset"]}


def build_series(t1, t2, t3, primary_only=False):
    """{niche_key: {tier: (months, vals)}}. The ONE place raw sources become series."""
    out = {}
    for n in NICHES:
        s = {}
        if n["key"] in t1:
            s["T1"] = (axis(T1_START), t1[n["key"]])
        v, cov = t2_series(n, t2, primary_only=primary_only)
        if v:
            s["T2"] = (axis(T2_START), v)
        if n["key"] in t3:
            s["T3"] = (axis(T3_START), t3[n["key"]]["corrected"])
        out[n["key"]] = s
    return out


def evaluate(series, growth_x=GROWTH_X):
    res = {}
    for n in NICHES:
        s = series.get(n["key"], {})
        tiers = {}
        for t in TIERS:
            months, vals = s.get(t, (axis(T2_START), None))
            tiers[t] = tier_state(n, t, vals, months, growth_x=growth_x)
        res[n["key"]] = {"key": n["key"], "label": n["label"], "class": n["cls"],
                         "why": n["why"], "caveats": n.get("caveats", []),
                         "tiers": tiers}
    return res


# =============================================================================
#  7. STATISTICS
# =============================================================================
def fisher_1t(a, b, c, d):
    """One-sided Fisher exact. Table [[a,b],[c,d]] = [[pos_fired, pos_not],
    [neg_fired, neg_not]]. P(as many or more positives firing, by chance).

    This is THE test. If a tier fires on the positives and the graveyard at
    indistinguishable rates, that tier has no discriminating power, whatever its hit rate
    looks like. n=8v8 is small but a Fisher test is exact - it does not need n to be large,
    it just cannot see a small effect. So a non-significant p here means "this study could
    not detect discrimination", NOT "there is none".
    """
    n = a + b + c + d
    if n == 0 or (a + b) == 0 or (c + d) == 0 or (a + c) == 0:
        return None
    p = 0.0
    for i in range(a, min(a + b, a + c) + 1):
        p += (math.comb(a + b, i) * math.comb(c + d, a + c - i)) / math.comb(n, a + c)
    return round(min(1.0, p), 4)


def perm_test(xs, ys, iters=None):
    """Exact permutation test on the difference in medians (xs = positives).

    Enumerates every way to split the pooled values when that is cheap (C(16,8)=12870),
    so there is no sampling error and no seed to fiddle with. One-sided: P(a random split
    gives the positives a median at least this much bigger).
    """
    xs = [x for x in xs if x is not None]
    ys = [y for y in ys if y is not None]
    if len(xs) < 2 or len(ys) < 2:
        return None
    obs = statistics.median(xs) - statistics.median(ys)
    pool = xs + ys
    k, n = len(xs), len(xs) + len(ys)
    if math.comb(n, k) > 200000:
        return None
    ge = tot = 0
    for combo in itertools.combinations(range(n), k):
        sel = set(combo)
        a = [pool[i] for i in sel]
        b = [pool[i] for i in range(n) if i not in sel]
        if statistics.median(a) - statistics.median(b) >= obs - 1e-12:
            ge += 1
        tot += 1
    return {"observed_diff": round(obs, 2), "p_one_sided": round(ge / tot, 4),
            "n_positive": len(xs), "n_graveyard": len(ys),
            "median_positive": round(statistics.median(xs), 2),
            "median_graveyard": round(statistics.median(ys), 2)}


def analyse(res, drop=()):
    """drop = niche keys to exclude (used for the without-NAD+ and without-autism reruns)."""
    pos = [n for n in POSITIVES if n["key"] not in drop]
    grv = [n for n in GRAVEYARDS if n["key"] not in drop]
    out = {"excluded": list(drop)}

    # ---- lead/lag on the positives ------------------------------------------
    gaps = {}
    for a, b in (("T1", "T2"), ("T2", "T3"), ("T1", "T3")):
        detail = []
        for n in pos:
            ta, tb = res[n["key"]]["tiers"][a], res[n["key"]]["tiers"][b]
            if ta.get("onset") and tb.get("onset"):
                detail.append({"niche": n["key"], "from": ta["onset"], "to": tb["onset"],
                               "gap_months": m_diff(ta["onset"], tb["onset"]),
                               "unreliable": bool(ta.get("low_count_unreliable")
                                                  or tb.get("low_count_unreliable"))})
        v = [d["gap_months"] for d in detail]
        ok = sum(1 for x in v if x > 0)
        ci = median_ci(v)
        gaps["%s->%s" % (a, b)] = {
            "n": len(v), "detail": detail,
            "median_gap_months": statistics.median(v) if v else None,
            "range": [min(v), max(v)] if v else None,
            "median_95ci": ci,
            "n_in_predicted_order": ok,
            "sign_test_p": round(binom_tail(ok, len(v)), 4) if v else None,
            "power": power_note(len(v)) if v else None,
        }
    out["lead_times"] = gaps

    # ---- per-tier scoring, with abstentions quarantined ----------------------
    tiers = {}
    for t in TIERS:
        def by(group, *states):
            return [n["key"] for n in group if res[n["key"]]["tiers"][t]["state"] in states]

        tp, fn = by(pos, "FIRED"), by(pos, "NO_ONSET")
        p_abs = by(pos, "OUT_OF_SCOPE", "BELOW_FLOOR", "NO_DATA")
        fp, tn = by(grv, "FIRED"), by(grv, "NO_ONSET")
        g_abs = by(grv, "OUT_OF_SCOPE", "BELOW_FLOOR", "NO_DATA")
        npos, nneg = len(tp) + len(fn), len(fp) + len(tn)

        amp = perm_test([res[n["key"]]["tiers"][t].get("peak_z")
                         for n in pos if res[n["key"]]["tiers"][t].get("peak_z") is not None],
                        [res[n["key"]]["tiers"][t].get("peak_z")
                         for n in grv if res[n["key"]]["tiers"][t].get("peak_z") is not None])

        tiers[t] = {
            "name": TIER_NAME[t],
            "hits": tp, "misses": fn, "false_positives": fp, "true_negatives": tn,
            "positives_abstained": p_abs, "graveyard_abstained": g_abs,
            "hit_rate": round(len(tp) / npos, 2) if npos else None,
            "informative_positives": npos, "informative_negatives": nneg,
            # HONEST: abstentions excluded from the denominator.
            "fp_rate_honest": round(len(fp) / nneg, 2) if nneg else None,
            # CREDULOUS: every abstention counted as a correct rejection. Shown ONLY so the
            # gap between the columns is impossible to miss.
            "fp_rate_credulous": round(len(fp) / len(grv), 2) if grv else None,
            "discrimination_fisher_p": fisher_1t(len(tp), len(fn), len(fp), len(tn)),
            "amplitude_test_peak_z": amp,
            "abstention_warning": (
                "This tier's specificity rests on %d of %d graveyard niches. %d ABSTAINED "
                "(out of scope, below the level floor, or no data). If most of the "
                "graveyard is invisible to a tier, its apparent specificity is an artefact "
                "of regulatory scope and count thresholds, NOT evidence that it "
                "discriminates." % (nneg, len(grv), len(g_abs))) if g_abs else None,
        }
    out["tiers"] = tiers

    # ---- the disconfirming cases, pulled out by name ------------------------
    out["disconfirming"] = [
        {"niche": n["key"], "label": n["label"], "tier": t,
         "onset": res[n["key"]]["tiers"][t]["onset"],
         "peak_z": res[n["key"]]["tiers"][t].get("peak_z"),
         "growth_at_onset": res[n["key"]]["tiers"][t].get("growth_at_onset")}
        for n in grv for t in TIERS
        if res[n["key"]]["tiers"][t]["state"] == "FIRED"
    ]
    out["low_count_onsets"] = [
        {"niche": k, "tier": t, "onset": v["onset"], "baseline": v.get("baseline_at_onset")}
        for k, r in res.items() for t, v in r["tiers"].items()
        if v.get("low_count_unreliable")
    ]
    out["estimator_disagreements"] = [
        {"niche": k, "tier": t, "robust": v.get("onset"), "spec": v.get("spec_onset"),
         "spec_blind_months": v.get("spec_undefined_months")}
        for k, r in res.items() for t, v in r["tiers"].items()
        if v["state"] in ("FIRED", "NO_ONSET") and not v.get("agrees_with_spec", True)
    ]
    return out


# =============================================================================
#  8. REPORT
# =============================================================================
def cell(tt):
    s = tt["state"]
    if s == "FIRED":
        return "**%s**%s" % (tt["onset"], " (!)" if tt.get("low_count_unreliable") else "")
    return {"NO_ONSET": "no onset", "OUT_OF_SCOPE": "_abstains: out of scope_",
            "BELOW_FLOOR": "_abstains: below floor_", "NO_DATA": "_no data_"}.get(s, s)


def write_md(p):
    res, a = p["niches"], p["analysis"]
    L = []
    A = L.append
    A("# Backtest 2: does T1 -> T2 -> T3 actually lead?\n")
    A("Generated %s. T4 is **not in this study at all** - see section 6.\n"
      % p["generated"][:10])

    A("\n## 0. What this can and cannot do. Read it before any number below.\n")
    A("**It cannot validate the tier ordering.** n = %d positives and %d graveyard niches. "
      "A flawless sweep of 8 gives p = 0.0039, which does clear a Bonferroni-corrected "
      "alpha - but only if it is flawless. One niche out of order and it fails. This "
      "experiment has exactly one power: to FALSIFY. If the graveyard fires as loudly as "
      "the positives, that is a real finding and it kills the early tiers. If it does not, "
      "that is *not* proof the tiers work - it is a failure to disprove them at n=16.\n"
      % (len(POSITIVES), len(GRAVEYARDS)))
    A("**Abstentions are not rejections.** A tier that legally cannot see a niche (CQC and "
      "ice baths) or whose series never clears the estimator's level floor has ABSTAINED. "
      "Counting those as correct rejections drives the false-positive rate to zero for "
      "free. Both are quarantined; the honest and the credulous rates are both printed in "
      "section 3, and the gap between them is the size of the lie you would otherwise "
      "have told.\n")
    A("**The niches are not independent.** ADHD and autism assessment share operators. "
      "Treating them as two observations overstates n. Section 3 is re-run without autism.\n")
    if p["diag"].get("cqc_survivorship_corrected"):
        A("- T3 **is** survivorship-corrected. Section 5 measures how much that mattered.\n")
    else:
        A("- **T3 IS NOT SURVIVORSHIP-CORRECTED in this run.** %s\n"
          % p["diag"].get("cqc_WARNING", ""))
    if p["diag"].get("t2_hit_budget_cap"):
        A("- **T2 hit the call budget cap.** Coverage %s. Re-run to resume; the cache "
          "persists.\n" % p["diag"].get("t2_coverage"))

    A("\n## 1. Onsets\n")
    A("| Niche | Class | T1 intent | T2 entry | T3 capacity |")
    A("|---|---|---|---|---|")
    for n in NICHES:
        r = res[n["key"]]
        A("| %s | %s | %s |" % (r["label"], r["class"],
                                " | ".join(cell(r["tiers"][t]) for t in TIERS)))
    A("\n`(!)` = the series was too thin at onset (< %d events/yr) for the DATE to be "
      "trustworthy. That it fired is meaningful; the month is not.\n" % LOW_COUNT)

    A("\n## 2. Lead times (positive set only)\n")
    A("A **positive** gap means the earlier tier fired first - the radar's claim.\n")
    A("| Pair | n | Median gap (months) | Range | 95% CI for the median | In predicted "
      "order | Sign-test p |")
    A("|---|---|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        ci = g["median_95ci"]
        A("| %s | %d | %s | %s | %s | %d/%d | %s |" % (
            pair, g["n"], g["median_gap_months"] if g["n"] else "-",
            ("%d to %d" % tuple(g["range"])) if g["range"] else "-",
            ("%d to %d" % (ci[0], ci[1])) if ci else "**none exists at this n**",
            g["n_in_predicted_order"], g["n"], g["sign_test_p"] if g["n"] else "-"))

    A("\n### 2a. THE NULL: what gap does this pipeline report when there is NO lead?\n")
    A("**Do not read the table above without this one.** The estimator does not fire the "
      "month a boom starts - it fires once the boom is undeniable. That lag is longer for "
      "series that are thin and noisy, and the tiers are not equally thin: T1 is a smooth "
      "0-100 index, T2 is ~6 new companies a month, T3 is ~3 new clinics a month. So the "
      "pipeline reports a lead-lag ordering **even when all three booms happen in the same "
      "month**. Some of the ordering is manufactured by the measurement, not by the world.\n")
    nb = p["null_calibration"]
    A("\nBelow: synthetic niches with a TRUE lead of **zero**, %d replications, pushed "
      "through this exact pipeline.\n" % nb["reps"])
    A("| Pair | Null median gap (true lead = 0) | Null p90 | Measured gap | Excess over "
      "null | Beats the null? |")
    A("|---|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        n0 = (nb["pairs"] or {}).get(pair)
        if not n0:
            continue
        A("| %s | **+%s** | +%s | %s | %s | %s |" % (
            pair, n0["median_gap_months"], n0["p90"],
            g["median_gap_months"] if g["n"] else "-",
            ("%+d" % g["excess_over_null_months"])
            if g.get("excess_over_null_months") is not None else "-",
            "**YES**" if g.get("beats_null") else ("no" if g.get("beats_null") is False
                                                   else "-")))
    A("\n**A measured gap that does not exceed the null p90 is not evidence of a lead.** "
      "It is what simultaneous booms look like when one of the series is thinner than the "
      "other. If T2->T3 fails to beat the null, then the claim 'new companies appear "
      "before new clinics' is not supported by this data even if the raw median gap is "
      "positive - and that is a result, not a technicality.\n")

    A("\n### 2b. The sign test was testing against the wrong null\n")
    A("The sign test in section 2 asks: 'if the tiers were unordered, each niche is a coin "
      "flip, so what are the odds of getting this many in the predicted order?' **That "
      "question is wrong**, and it is wrong in the direction that flatters the thesis.\n")
    A("With a TRUE lead of zero, this pipeline still puts the niches 'in the predicted "
      "order' at the rates below - not 50%. The detection-lag artefact orders them for "
      "free. So the honest sign test uses the CALIBRATED rate as its null, not a coin "
      "flip.\n")
    A("| Pair | In predicted order | Naive null (coin flip) | **Calibrated null (true "
      "lead = 0)** | Naive p | **Calibrated p** |")
    A("|---|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        if not g["n"]:
            continue
        A("| %s | %d/%d | 50%% | **%.0f%%** | %s | **%s** |" % (
            pair, g["n_in_predicted_order"], g["n"], 100 * g.get("null_order_rate", 0.5),
            g.get("sign_test_p_naive_vs_coinflip"), g.get("sign_test_p_calibrated")))
    A("\nWhere the calibrated null is high - T1->T3 especially - **a clean sweep proves "
      "nothing**, because a clean sweep is exactly what zero lead produces. Quote the "
      "calibrated p. The naive column is shown only so the size of the error is visible.\n")

    A("\n## 3. THE POINT OF THE WHOLE FILE: does the graveyard fire too?\n")
    A("| Tier | Hit rate (positives) | FP rate - HONEST | FP rate - credulous | Fisher p "
      "(does it discriminate?) | Graveyard abstained |")
    A("|---|---|---|---|---|---|")
    for t in TIERS:
        s = a["tiers"][t]
        A("| %s %s | %s (%d informative) | **%s** (%d informative) | %s | %s | %d of %d |"
          % (t, TIER_NAME[t], s["hit_rate"], s["informative_positives"],
             s["fp_rate_honest"], s["informative_negatives"], s["fp_rate_credulous"],
             s["discrimination_fisher_p"], len(s["graveyard_abstained"]), len(GRAVEYARDS)))
    A("\n**Read the Fisher column, not the hit rate.** A tier that fires on 8/8 booms and "
      "6/6 duds has a perfect hit rate and zero information. The Fisher p asks the only "
      "question that matters: does this tier fire on real booms MORE OFTEN than on duds? "
      "A p near 1.0 means no. A p that is merely non-significant at n=16 means this study "
      "could not tell - which is not the same as 'it works'.\n")
    for t in TIERS:
        if a["tiers"][t].get("abstention_warning"):
            A("- **%s**: %s\n" % (t, a["tiers"][t]["abstention_warning"]))

    A("\n### 3a. Do the early tiers fire as LOUDLY for the duds?\n")
    A("Hit/miss is binary and throws away the amplitude. If the graveyard's `peak_z` is "
      "the same size as the positives', then even a tier that discriminates on *whether* "
      "it fires carries no usable information in *how hard* it fires - so you cannot rank "
      "opportunities by signal strength, which is what the live radar actually does.\n")
    A("| Tier | Median peak z, positives | Median peak z, graveyard | Difference | "
      "Exact permutation p |")
    A("|---|---|---|---|---|")
    for t in TIERS:
        m = a["tiers"][t].get("amplitude_test_peak_z")
        if not m:
            A("| %s | - | - | - | not computable (too few niches fired) |" % t)
            continue
        A("| %s | %s | %s | %s | %s |" % (t, m["median_positive"], m["median_graveyard"],
                                          m["observed_diff"], m["p_one_sided"]))

    A("\n### 3b. The disconfirming cases\n")
    if a["disconfirming"]:
        A("Graveyard niches that FIRED. Each one is a false positive the live radar would "
          "have handed you as a lead.\n")
        A("| Niche | Tier | Onset | peak z | Growth at onset |")
        A("|---|---|---|---|---|")
        for d in a["disconfirming"]:
            A("| %s | %s | %s | %s | %s |" % (d["label"], d["tier"], d["onset"],
                                              d["peak_z"], d["growth_at_onset"]))
        A("\nIf CBD is in that list on T1 and T2, **the early tiers cannot discriminate on "
          "their own** and the radar's T1/T2 alerts are leads, not signals.\n")
    else:
        A("**NONE.** No graveyard niche fired on any tier. Before celebrating, check the "
          "abstention column in section 3: if the graveyard mostly abstained, this says "
          "nothing at all.\n")

    A("\n## 4. Sensitivity: is the answer just the threshold I picked?\n")
    A("| Pair | growth>=1.25x | growth>=1.5x (shipped) | growth>=2.0x |")
    A("|---|---|---|---|")
    for pair in ("T1->T2", "T2->T3", "T1->T3"):
        cells = []
        for gx in ("1.25", "1.5", "2.0"):
            g = p["sensitivity"][gx][pair]
            cells.append("median %s (n=%d, %d in order)"
                         % (g["median_gap_months"], g["n"], g["n_in_predicted_order"]))
        A("| %s | %s |" % (pair, " | ".join(cells)))
    A("\nIf the SIGN of a median gap flips across that row, the ordering is an artefact of "
      "the threshold, not a fact about the world, and **must not be reported as a "
      "finding**.\n")

    A("\n## 5. The survivorship correction, measured\n")
    A("The CQC active-locations file contains only clinics that are STILL OPEN. Used alone "
      "it understates every historical month, invents an upward trend in every niche, and "
      "biases every T3 onset LATE - which would inflate the T2->T3 lead time, the single "
      "number a buyer would act on.\n")
    A("| Niche | Active | Recovered from deactivated file | Understatement if uncorrected | "
      "Onset: active-only | Onset: corrected | Onset moved by |")
    A("|---|---|---|---|---|---|---|")
    for n in NICHES:
        sv = res[n["key"]].get("t3_survivorship")
        if not sv or not sv["n_active"]:
            continue
        mv = m_diff(sv["onset_corrected"], sv["onset_active_only"])
        A("| %s | %d | %d | %s%% | %s | %s | %s |" % (
            n["label"], sv["n_active"], sv["n_recovered"], sv["understatement_pct"],
            sv["onset_active_only"] or "-", sv["onset_corrected"] or "-",
            ("%+d months" % mv) if mv is not None else "-"))
    A("\nEvery number in the last column should be >= 0: a missing clinic is always in the "
      "past, so the uncorrected file can only ever tell you a boom started LATER than it "
      "did. **If that column is materially non-zero, no T3 result from an active-only "
      "file - including anything the live radar computes today - is safe to quote.**\n")

    A("\n## 6. Why T4 is not here\n")
    A("OpenPrescribing (a) returns HTTP 403 to datacentre IPs, so no CI runner or sandbox "
      "can reach it, and (b) serves roughly 60 months of history through its API, so the "
      "2021-23 ADHD boom - the case that motivated this entire system - is partly outside "
      "the window it can even show you. Both are true, and they are also the reason the "
      "'we cannot backtest this' excuse was wrong: **that constraint applies to T4 only**. "
      "T1, T2 and T3 have 14, 16 and 12 years of retrievable monthly history respectively, "
      "and they are the three tiers that precede a purchase. Emitting an empty T4 column "
      "would look like a measurement. There is no T4 column.\n")

    A("\n## 7. Robustness of the T2 construction\n")
    A(T2_SUMMING_NOTE + "\n")
    dis = p.get("t2_primary_only_disagreements") or []
    if dis:
        A("\n**Niches where the primary-keyword-only series gives a different T2 onset:**\n")
        A("| Niche | T2 onset (all keywords) | T2 onset (primary keyword only) |")
        A("|---|---|---|")
        for d in dis:
            A("| %s | %s | %s |" % (d["niche"], d["all"] or "no onset",
                                    d["primary"] or "no onset"))
        A("\nWhere these differ, the T2 onset is partly an artefact of keyword choice.\n")
    else:
        A("\nNo niche's T2 onset changes when the series is rebuilt from its primary "
          "keyword alone. Double-counting is not driving the dates.\n")

    pr = p.get("t2_precision") or {}
    dirty = {k: v for k, v in pr.items()
             if isinstance(v, dict) and (v.get("precision") is not None
                                         and v["precision"] < 0.8)}
    A("\n### 7a. Keyword precision probe\n")
    A("The `hits`-count trick returns no company names, so - unlike backtest.py, which "
      "paged and could re-filter - we cannot check what Companies House actually matched. "
      "One extra call per keyword pulls 100 names and re-applies our strict word-boundary "
      "matcher. Not a random sample, so this is a smell test, not an estimate.\n")
    if dirty:
        A("| Keyword | Precision on 100 sampled names | Examples wrongly matched |")
        A("|---|---|---|")
        for k, v in sorted(dirty.items()):
            A("| `%s` | **%.0f%%** | %s |" % (k, 100 * v["precision"],
                                              ", ".join(v.get("examples_rejected") or [])))
        A("\n**These keywords are contaminated.** Their niches' T2 counts are inflated by "
          "unrelated companies and the T2 onset for those niches should be discounted "
          "accordingly.\n")
    elif pr:
        A("All keywords scored >= 80%% precision on the sampled names.\n")
    else:
        A("Probe not run (no Companies House key, or cache-only run).\n")

    A("\n## 8. Where the estimator choice changes the answer\n")
    if a["estimator_disagreements"]:
        A("| Niche | Tier | Robust (shipped) | The original brief's estimator | Months its "
          "YoY divides by zero |")
        A("|---|---|---|---|---|")
        for d in a["estimator_disagreements"]:
            A("| %s | %s | %s | %s | %s |" % (d["niche"], d["tier"], d["robust"] or "none",
                                              d["spec"] or "none", d["spec_blind_months"]))
    else:
        A("None. The two estimators agree wherever both can see.\n")

    A("\n## 9. Sensitivity of the headline to two contested labels\n")
    A("| Scenario | T1 FP rate | T2 FP rate | T3 FP rate |")
    A("|---|---|---|---|")
    for name, alt in (("as shipped", a), ("without NAD+ (unresolved, may not be a dud)",
                                          p["analysis_no_nad"]),
                      ("without autism (not independent of ADHD)", p["analysis_no_autism"])):
        A("| %s | %s | %s | %s |" % (name,
                                     alt["tiers"]["T1"]["fp_rate_honest"],
                                     alt["tiers"]["T2"]["fp_rate_honest"],
                                     alt["tiers"]["T3"]["fp_rate_honest"]))
    A("\nNAD+ is placed in the graveyard although it has **not resolved**. If it becomes a "
      "real boom, its false positives here are actually true positives. Quote the range, "
      "never the point.\n")

    A("\n## 10. Why each graveyard niche is in the graveyard\n")
    for n in GRAVEYARDS:
        A("**%s** - %s\n" % (n["label"], n["why"]))
        for c in n.get("caveats", []):
            A("  - *Caveat:* %s\n" % c)

    A("\n## 11. Diagnostics\n")
    A("```\n%s\n```\n" % json.dumps(p["diag"], indent=1)[:4000])

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# =============================================================================
#  9. BUILD
# =============================================================================
def assemble(t1, t2, t3, probes=None):
    series = build_series(t1, t2, t3)
    res = evaluate(series)

    # survivorship: recompute every T3 onset on the ACTIVE-ONLY file and diff the dates
    m3 = axis(T3_START)
    for n in NICHES:
        c = t3.get(n["key"])
        if not c or not n["t3_scope"]:
            continue
        av, cv = c["active_only"], c["corrected"]
        oa = tier_state(n, "T3", av, m3) if sum(av) else {"onset": None}
        res[n["key"]]["t3_survivorship"] = {
            "n_active": c["n_active"], "n_recovered": c["n_recovered"],
            "understatement_pct": (round(100.0 * (sum(cv) - sum(av)) / sum(cv), 1)
                                   if sum(cv) else None),
            "dedup_collapsed": c["dedup_collapsed"],
            "onset_active_only": oa.get("onset"),
            "onset_corrected": res[n["key"]]["tiers"]["T3"].get("onset"),
        }

    # T2 built from the primary keyword only - cannot double-count by construction
    prim = evaluate(build_series(t1, t2, t3, primary_only=True))
    dis = [{"niche": n["key"], "all": res[n["key"]]["tiers"]["T2"].get("onset"),
            "primary": prim[n["key"]]["tiers"]["T2"].get("onset")}
           for n in NICHES
           if res[n["key"]]["tiers"]["T2"].get("onset")
           != prim[n["key"]]["tiers"]["T2"].get("onset")]

    sens = {}
    for gx in (1.25, 1.5, 2.0):
        r = evaluate(series, growth_x=gx)
        sens["%s" % gx] = analyse(r)["lead_times"]

    # THE NULL. What gap does this pipeline report when the true lead is ZERO? Anything a
    # live run measures has to beat this to count as evidence of a lead at all.
    print("\ncalibrating the null (synthetic, no network)...")
    null = calibrate_null()
    main = analyse(res)
    for pair, g in main["lead_times"].items():
        nb = (null["pairs"] or {}).get(pair)
        g["null_median_gap_months"] = nb["median_gap_months"] if nb else None
        g["null_p90"] = nb["p90"] if nb else None
        if nb and g["median_gap_months"] is not None:
            g["excess_over_null_months"] = g["median_gap_months"] - nb["median_gap_months"]
            g["beats_null"] = bool(g["median_gap_months"] > nb["p90"])
        else:
            g["excess_over_null_months"] = None
            g["beats_null"] = None

        # THE SIGN TEST WAS TESTING AGAINST THE WRONG NULL, AND IT WOULD HAVE
        # MANUFACTURED SIGNIFICANCE.
        #
        # binom_tail() defaults to p=0.5: "if the tiers were unordered, each niche is a
        # coin flip". That is FALSE for this pipeline. The null calibration above shows
        # that with a TRUE lead of exactly zero, the tiers still come out "in the predicted
        # order" 64-97% of the time, because the thinner tier is always detected later.
        # T1->T3 is the worst: ~97% in-order under a zero lead.
        #
        # So an 8/8 sweep on T1->T3 scores p=0.0039 against p=0.5 and looks like a
        # discovery, when 8/8 is simply THE EXPECTED RESULT OF NO EFFECT AT ALL. The
        # correct null is the calibrated order rate, not a coin flip. Both are reported;
        # the calibrated one is the only one that means anything.
        p0 = (nb["pct_in_predicted_order"] / 100.0) if nb else 0.5
        p0 = min(max(p0, 0.5), 0.99)          # never claim a null EASIER than a coin flip
        g["null_order_rate"] = round(p0, 3)
        g["sign_test_p_naive_vs_coinflip"] = g["sign_test_p"]
        g["sign_test_p_calibrated"] = (
            round(binom_tail(g["n_in_predicted_order"], g["n"], p0), 4) if g["n"] else None)

    p = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(),
         "windows": {"T1": [T1_START, END], "T2": [T2_START, END], "T3": [T3_START, END]},
         "t4": "EXCLUDED BY DESIGN - see backtest2.md section 6",
         "n": {"positives": len(POSITIVES), "graveyard": len(GRAVEYARDS)},
         "estimator": "backtest_core.onset_robust (21 synthetic fixtures, unchanged)",
         "hsca_waves_excluded": HSCA_WAVES,
         "t2_summing_note": T2_SUMMING_NOTE,
         "t2_precision": probes or {},
         "t2_primary_only_disagreements": dis,
         "null_calibration": null,
         "diag": DIAG,
         "niches": res,
         "analysis": main,
         "analysis_no_nad": analyse(res, drop=("nad",)),
         "analysis_no_autism": analyse(res, drop=("autism",)),
         "sensitivity": sens}
    save(OUT_JSON, p)
    write_md(p)
    return p


def build(args):
    print("Backtest2  T1 %s.. | T2 %s.. | T3 %s..  -> %s\n"
          % (T1_START, T2_START, T3_START, END))
    print("T2 Companies House (monthly hit-counts)")
    t2, probes = fetch_t2(args.max_calls, force=args.refresh)
    print("\nT3 CQC (active + deactivated, survivorship-corrected)")
    t3 = fetch_t3(force=args.refresh)
    print("\nT1 Google Trends")
    t1 = fetch_t1(args.trends, force=args.refresh)
    print("  %s" % DIAG.get("t1"))
    p = assemble(t1, t2, t3, probes)
    print("\nwrote %s\nwrote %s" % (OUT_JSON, OUT_MD))

    a = p["analysis"]
    print("\n" + "=" * 74)
    for t in TIERS:
        s = a["tiers"][t]
        print("%s %-24s hit %s (%d)   FP %s (%d)   Fisher p=%s"
              % (t, TIER_NAME[t], s["hit_rate"], s["informative_positives"],
                 s["fp_rate_honest"], s["informative_negatives"],
                 s["discrimination_fisher_p"]))
    print("\nLEAD TIMES vs THE NULL (the null is what a ZERO true lead still reports):")
    for pair, g in a["lead_times"].items():
        print("  %-8s measured %+5s   null %+5s   excess %+5s   %s"
              % (pair, g["median_gap_months"], g.get("null_median_gap_months"),
                 g.get("excess_over_null_months"),
                 "BEATS NULL" if g.get("beats_null") else "does NOT beat the null"))
        print("           in-order %d/%d   sign-test p: %s vs a coin flip (WRONG), "
              "%s vs the calibrated %.0f%% null (USE THIS)"
              % (g["n_in_predicted_order"], g["n"],
                 g.get("sign_test_p_naive_vs_coinflip"), g.get("sign_test_p_calibrated"),
                 100 * g.get("null_order_rate", 0.5)))
    if a["disconfirming"]:
        print("\nDISCONFIRMING - graveyard niches that FIRED:")
        for d in a["disconfirming"]:
            print("  %-10s %s  onset %s  peak_z %s"
                  % (d["tier"], d["label"], d["onset"], d["peak_z"]))
    else:
        print("\nNo graveyard niche fired anywhere. CHECK THE ABSTENTION COUNTS before "
              "believing that.")
    print("=" * 74)
    return 0


# =============================================================================
#  10. SELFTEST - no network. Fixtures with a KNOWN injected lead structure.
# =============================================================================
# The sandbox this was written in has no DNS, so the live path cannot be exercised here.
# What CAN be proved without a network is the thing most likely to be silently wrong: the
# ASSEMBLY and ANALYSIS. So we synthesise raw source payloads in the exact shape the real
# fetchers return, inject a lead structure we choose (T1 leads T2 by 6, T2 leads T3 by 6),
# push them through the REAL build_series/evaluate/analyse - not a parallel copy - and
# check the pipeline recovers it.
#
# Recovery is not exact and should not be: onset_robust has a detection lag (it needs the
# boom to persist), so a 6-month injected gap comes back as roughly 6 months, not exactly.
# The test asserts the ORDER is right and the magnitude is in the right neighbourhood. A
# test that demanded exactness would be testing the noise.
def _pois(n, rate, seed):
    import random
    rnd = random.Random(seed)
    out = []
    for t in range(n):
        lam = max(rate(t), 0.0)
        L, k, pp = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            pp *= rnd.random()
            if pp <= L:
                break
        out.append(float(k - 1))
    return out


def _ramp(base, mult, boom, span=18):
    return lambda t: base if t < boom else base * (1 + (mult - 1) * min(1.0, (t - boom) / span))


def _fixture(lead=6, seed0=0):
    """Raw payloads in the shape fetch_t1 / fetch_t2 / fetch_t3 return.

    POSITIVES get a boom in all three tiers, staggered by `lead` months in CALENDAR time.
    GRAVEYARD gets a boom on T1 and T2 and NOTHING on T3 - the CBD/psychedelics shape. If
    the analysis cannot show a false-positive rate on that, the analysis is broken.

    The count levels are chosen to match reality, not to make the test pass: ~6/month new
    companies and ~3/month new CQC registrations is roughly what a real UK niche produces.
    That thinness is why the null calibration below comes out non-zero.
    """
    a1, a2, a3 = axis(T1_START), axis(T2_START), axis(T3_START)
    t1, t2, t3 = {}, {}, {}
    # true T1 boom month, per niche - deliberately spread so the medians are not one number
    truth = {}
    for i, n in enumerate(NICHES):
        b1 = "%d-01" % (2018 + (i % 3))                  # 2018 / 2019 / 2020
        b2, b3 = m_add(b1, lead), m_add(b1, 2 * lead)
        truth[n["key"]] = {"T1": b1, "T2": b2, "T3": b3}
        i1, i2, i3 = a1.index(b1), a2.index(b2), a3.index(b3)

        # T1: a Trends-shaped 0-100 index (integer-truncated), like backtest_core fixture 3
        t1[n["key"]] = [float(int(min(100.0, 4.0 + 96.0 * max(0, t - i1) / 24.0)
                                  + ((t * 7919) % 5) / 5.0)) for t in range(len(a1))]
        # T2: Poisson incorporations, 6/mth -> 30/mth
        vals2 = _pois(len(a2), _ramp(6.0, 5.0, i2), seed=seed0 + 100 + i)
        # T3: Poisson registrations, 3/mth -> 15/mth. GRAVEYARD GETS NO T3 BOOM AT ALL.
        rate3 = _ramp(3.0, 5.0, i3) if n["cls"] == POSITIVE else (lambda t: 3.0)
        vals3 = _pois(len(a3), rate3, seed=seed0 + 200 + i)

        # T2 raw payload is keyed by KEYWORD, so split the series across the niche's
        # keywords - this exercises the real multi-keyword summing path.
        kws = n["ch"]
        for j, kw in enumerate(kws):
            share = [(v if j == 0 else 0.0) if len(kws) == 1 else
                     (math.floor(v * (0.7 if j == 0 else 0.3 / (len(kws) - 1))))
                     for v in vals2]
            t2.setdefault(kw, {})
            for k, m in enumerate(a2):
                t2[kw][m] = t2[kw].get(m, 0) + int(share[k])
        t3[n["key"]] = {"active_only": vals3, "corrected": vals3,
                        "n_active": int(sum(vals3)), "n_recovered": 0,
                        "dedup_collapsed": 0}
    t2 = {k: v for k, v in t2.items() if isinstance(v, dict)}
    return t1, t2, t3, truth


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Radar backtest v2 (T1/T2/T3, long history)")
    ap.add_argument("--trends", action="store_true",
                    help="also run T1 Google Trends (costs SerpApi searches; cached forever)")
    ap.add_argument("--no-trends", dest="trends", action="store_false")
    ap.add_argument("--max-calls", type=int, default=6000,
                    help="cap on Companies House calls this run (resumable via cache)")
    ap.add_argument("--refresh", "--force", dest="refresh", action="store_true",
                    help="ignore caches")
    ap.set_defaults(trends=False)
    args = ap.parse_args()
    return build(args)


if __name__ == "__main__":
    main()
