#!/usr/bin/env python3
"""
BACKTEST 3 - the four-tier backtest, with T4 finally in it.

WHAT CHANGED SINCE BACKTEST 2, AND WHY IT MATTERS
-------------------------------------------------
backtest2.py dropped T4 entirely, on the grounds that OpenPrescribing serves only 60
months and 403s datacentre IPs, so the 2021-23 ADHD boom - the case that motivated the
whole system - sat outside the observable window. That excuse is now dead. NHSBSA
publishes the English Prescribing Dataset itself, back to January 2014, with no key,
and it answers datacentre IPs. _agent3/nhsbsa_epd.py already talks to it and is
verified live. So T4 has 12 years of monthly history and is IN this study.

Verified live, 13 Jul 2026, lisdexamfetamine (the ADHD stimulant), England, items/month:
    Jan-2014        737
    Jan-2020     16,460
    Jan-2022     27,728
    Apr-2026    120,226

THREE THINGS FOUND ON THE WAY, IN ORDER OF HOW MUCH THEY THREATEN THE HEADLINE
-------------------------------------------------------------------------------
0. THE ESTIMATOR DETECTS ACCELERATION, NOT GROWTH. onset_robust's z-scale is the median
   and MAD of a niche's OWN recent z-history, so a series compounding smoothly has a flat
   z-history and NEVER FIRES. Fixture 23 proves it on a series growing a steady +3%/month
   from its first observation: no onset, ever. That is a feature - it is what stops the
   detector screaming at everything merely large - but it has a consequence nobody had
   written down, and it lands squarely on the benchmark case:

       A niche that was ALREADY BOOMING before the data window opened reports NO_ONSET,
       which in a results table is INDISTINGUISHABLE FROM A CORRECT REJECTION.

   T4's history opens in Jan-2014 with lisdexamfetamine already at 737 items/month and
   climbing hard. Score a T4 silence on ADHD as "T4 did not flag ADHD" and you have
   reported the exact opposite of the truth. So this file adds a sixth state,
   ALREADY_BOOMING - an ABSTENTION, on the positives and the graveyard alike - and reports
   alongside it the year-on-year growth that would actually have been VISIBLE ON THE
   SCREEN at the cutoff. A tier can be silent while the niche is growing 40% a year. Both
   numbers are printed, because neither one alone is honest.

1. backtest2.py DOES NOT RUN. Its assemble() calls calibrate_null() on line 1548 and
   that function is never defined anywhere in the file. `python3 -m py_compile` passes;
   the live path raises NameError. So the null calibration its own docstring leans on
   (and which this file's brief instructed us to carry forward) was never actually
   computed by anything. backtest3 supplies calibrate_null() and MEASURES it. The
   numbers it produces are this file's, not inherited claims.

2. The null is worse than backtest2 guessed, for a reason its docstring missed. It
   attributed the artefact entirely to "thin series take longer to cross a threshold".
   True, but the bigger driver is WARM-UP: each tier's history starts in a different
   year, and onset_robust needs ~54 months of history before it can fire at all.

       T1 Google Trends     from 2012-01   ->  cannot fire before ~2016-07
       T2 Companies House   from 2010-01   ->  cannot fire before ~2014-07
       T3 CQC               from 2014-01   ->  cannot fire before ~2018-07
       T4 NHSBSA EPD        from 2014-01   ->  cannot fire before ~2018-07

   A boom in 2018-01 can therefore be dated by T2 immediately and CANNOT BE DATED BY T3
   OR T4 UNTIL JULY 2018, no matter what those series do. That is six months of "T2
   leads T3" manufactured by nothing but the start date of a spreadsheet. calibrate_null
   here runs on the REAL axes with the REAL floors, so it captures this. Every measured
   gap is scored against it.

THE HEADLINE QUESTION THIS FILE EXISTS TO ANSWER
------------------------------------------------
"Standing in early 2022, would this radar have flagged ADHD?" Section 1 of the report
answers it tier by tier, with the month each tier crossed AND the month that crossing
became KNOWABLE (onset + the estimator's 3-month persistence window + the source's own
publication lag). An onset you could only see with hindsight is not a signal.

WHAT T4 CANNOT DO, STATED UP FRONT
----------------------------------
T4 abstains on the ENTIRE graveyard - 8 of 8. None of CBD, IV drips, cryotherapy, ice
baths, psilocybin, NAD+, hyperbaric oxygen or red-light therapy is an NHS-prescribed
medicine. So T4's false-positive rate is not low. It is UNDEFINED: 0 informative
negatives. T4 cannot be validated as a discriminator by this study at all, and any
report that shows "T4 FP rate: 0.00" is lying by omission. It is shown as n/a.

T4 also abstains on 4 of the 8 POSITIVES, and drugs.py already documented why (that
file verified every code twice against the live BNF and OpenPrescribing APIs):
  - private GP      no drug is specific to seeing a GP privately
  - autism          no autism-specific chemical exists
  - hair transplant only topical minoxidil (~600 items/mth); finasteride 1mg is
                    effectively unprescribed on the NHS, so the private hair-loss
                    market is invisible. drugs.NICHES_THIN_PROXY says exactly this.
  - IVF             fertility drugs are specialist/hospital-issued; EPD is primary
                    care only. drugs.NICHES_THIN_PROXY says exactly this.

That leaves T4 with FOUR informative niches: ADHD, GLP-1, menopause/HRT, TRT. Four.
Any lead/lag statistic on T4 rests on n=4 and is reported as such.

RUN
    python3 backtest3.py --selftest      # no network. Fixtures with a KNOWN injected
                                         #   lead; proves the pipeline recovers it and
                                         #   that calibrate_null still fires.
    python3 backtest3.py                 # full run: T2 + T3 + T4. No SerpApi spend.
    python3 backtest3.py --trends        # ...also T1. Cached forever after the first.
    python3 backtest3.py --cutoff 2022-03    # move the "standing in early 2022" line.
    python3 backtest3.py --minutes 50        # wall-clock budget: when spent, SAVE the
                                             #   caches, write a partial report, exit 0.
                                             #   The next run RESUMES; nothing repeats.

Needs CH_API_KEY for T2 (free, instant). T4 needs nothing. T1 needs SERPAPI_KEY.
Writes _agent3/backtest3.md and _agent3/backtest3.json.

Stdlib only.
"""

import os
import re
import sys
import json
import math
import random
import argparse
import datetime as dt
import itertools
import statistics
import urllib.parse
import urllib.request
import time
import shutil
import tempfile
import threading
import traceback
import concurrent.futures as _futures
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))       # .../radar-app/_agent3
ROOT = os.path.dirname(HERE)                            # .../radar-app
AGENT2 = os.environ.get("BT2_DIR", os.path.join(ROOT, "_agent2"))
for _p in (ROOT, HERE, AGENT2):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# THE ESTIMATOR IS NOT REDEFINED. backtest_core.onset_robust is validated against 21
# synthetic fixtures (`python3 backtest_core.py` -> 21/21). Two onset estimators would
# mean two things to trust instead of one.
from backtest_core import (                                          # noqa: E402
    onset_robust, onset_spec, rolling_sum, median_ci, power_note, binom_tail,
    FLOORS, LOW_COUNT, GROWTH_X, SUSTAIN_MONTHS, K_SMOOTH,
    selftest as core_selftest,
)

# backtest2 is reused wholesale for the things it got right and that were expensive to
# get right: the Companies House hits-count fetcher, the hardened .ods parser, the CQC
# active+deactivated survivorship merge, the niche definitions, and the exact tests.
# NOT reused: assemble(), which is broken (see the header), and its 3-tier analysis.
try:
    import backtest2 as bt2                                          # noqa: E402
except Exception as _e:                                             # pragma: no cover
    sys.stderr.write(
        "FATAL: cannot import backtest2 from %s (%r).\n"
        "backtest3 reuses its Companies House fetcher, its .ods parser and its CQC\n"
        "survivorship merge rather than reimplementing them. Set BT2_DIR to the\n"
        "directory containing backtest2.py.\n" % (AGENT2, _e))
    raise

import nhsbsa_epd as epd                                             # noqa: E402

try:
    import drugs                                                     # noqa: E402
except Exception:                                                    # pragma: no cover
    drugs = None

# --- shared helpers, taken from backtest2 rather than re-typed ---------------
m_add, m_diff, axis = bt2.m_add, bt2.m_diff, bt2.axis
load, save = bt2.load, bt2.save
fisher_1t, perm_test = bt2.fisher_1t, bt2.perm_test
POSITIVE, GRAVEYARD = bt2.POSITIVE, bt2.GRAVEYARD

DATA = os.path.join(HERE, "data")
OUT_JSON = os.path.join(HERE, "backtest3.json")
OUT_MD = os.path.join(HERE, "backtest3.md")
EPD_CACHE = os.path.join(DATA, "backtest3_epd.json")     # {"YYYY-MM": {code: items}}

# Every cache is REPOINTED into _agent3/data so this file never writes into a sibling
# agent's directory - but the sibling's caches are SEEDED IN first, so a full T2 backfill
# already paid for (thousands of Companies House calls) is not paid for twice.
_SEED = [(os.path.join(AGENT2, "data", "backtest2_ch.json"),
          os.path.join(DATA, "backtest3_ch.json")),
         (os.path.join(AGENT2, "data", "backtest2_ch_probe.json"),
          os.path.join(DATA, "backtest3_ch_probe.json")),
         (os.path.join(AGENT2, "data", "backtest2_cqc.json"),
          os.path.join(DATA, "backtest3_cqc.json")),
         (os.path.join(AGENT2, "data", "backtest_trends.json"),
          os.path.join(DATA, "backtest3_trends.json"))]


def _repoint_caches():
    for src, dst in _SEED:
        if os.path.exists(src) and not os.path.exists(dst):
            obj = load(src)
            if obj is not None:
                save(dst, obj)
    bt2.CH_CACHE = os.path.join(DATA, "backtest3_ch.json")
    bt2.CH_PROBE = os.path.join(DATA, "backtest3_ch_probe.json")
    bt2.CQC_CACHE = os.path.join(DATA, "backtest3_cqc.json")
    bt2.TRENDS_CACHE = os.path.join(DATA, "backtest3_trends.json")


# =============================================================================
#  1. TIERS, WINDOWS, AND THE LAGS THAT DECIDE WHAT "KNOWABLE" MEANS
# =============================================================================
T1_START, T2_START, T3_START = bt2.T1_START, bt2.T2_START, bt2.T3_START   # 2012/2010/2014
T4_START = "2014-01"          # NHSBSA EPD's first month. Verified: EPD_201401 answers.
END = bt2.END                 # 2026-06

TIERS = ["T1", "T2", "T3", "T4"]
TIER_NAME = {"T1": "INTENT (search)", "T2": "ENTRY (new companies)",
             "T3": "CAPACITY (new CQC clinics)", "T4": "CONSUMPTION (NHS prescribing)"}
TIER_START = {"T1": T1_START, "T2": T2_START, "T3": T3_START, "T4": T4_START}

# The radar's claim is T1 -> T2 -> T3 -> T4. These are the adjacent links; all six
# ordered pairs are computed, because if T4 turns out to fire FIRST that is a finding
# about the tier model, not a bug to be hidden.
ADJACENT = [("T1", "T2"), ("T2", "T3"), ("T3", "T4")]
PAIRS = [(a, b) for i, a in enumerate(TIERS) for b in TIERS[i + 1:]]

# PUBLICATION LAG: how stale the freshest available month is, per source. This is the
# difference between "the boom started in month M" and "you could have KNOWN in month M".
#   T1  Google Trends   ~live.
#   T2  Companies House ~live; a new incorporation is searchable within days.
#   T3  CQC             the locations .ods is refreshed monthly.
#   T4  NHSBSA EPD      ~2.5 months in arrears ("January data is published in March"),
#                       verified: on 13 Jul 2026 the newest table was April 2026. Rounded
#                       UP to 3, because rounding this one down flatters T4.
PUB_LAG = {"T1": 0, "T2": 0, "T3": 1, "T4": 3}

# An onset at month M is only KNOWABLE at M + SUSTAIN_MONTHS, because onset_robust's
# fifth condition requires z to stay elevated for 3 further months. The estimator is
# otherwise strictly causal (every baseline looks backwards) - and fixture 4 below
# PROVES that by re-running it on truncated data and demanding the same answer. Without
# that proof, every "we would have caught it" claim in this file would be hindsight.
def knowable_by(tier, onset):
    if not onset:
        return None
    return m_add(onset, SUSTAIN_MONTHS + PUB_LAG[tier])


# =============================================================================
#  2. THE NICHE SET - backtest2's, PLUS T4 SCOPE
# =============================================================================
# The 8 positives and 8 graveyard niches, their Companies House keywords, their CQC name
# matchers and their T3 scope are inherited from backtest2 VERBATIM. Redefining them here
# would let the two files drift apart and would invite exactly the kind of quiet
# re-labelling that makes a backtest worthless.
#
# What is added is T4: which BNF chemicals stand for the niche, and - far more often -
# why NO chemical does.
#
# EVERY CODE BELOW IS TAKEN FROM drugs.py BY NICHE NAME. Not one is typed by hand here.
# drugs.py verified each code TWICE against live APIs and keeps a DEAD_CODES list of
# codes that exist in the BNF but return an empty series. A hand-typed code is how you
# get a silent zero that looks like "prescribing collapsed".
def _codes(niche_label):
    if drugs is None:
        return []
    return sorted(drugs.NICHE_CODES.get(niche_label, []))


NO = False
YES = True

# key -> (in_scope, reason). The reasons are the whole point: an abstention that is not
# explained is indistinguishable from a rejection, and a rejection is worth credit.
T4_SCOPE = {
    # ---------------------------------------------------------------- positives
    "adhd": (YES, "ADHD stimulants and non-stimulants: %s. The cleanest T4 signal in "
                  "the set." % ", ".join(_codes("ADHD"))),
    "glp1": (YES, "semaglutide / tirzepatide / liraglutide / orlistat: %s. CAVEAT: NHS "
                  "GLP-1 prescribing is mostly for TYPE-2 DIABETES, and the private "
                  "weight-loss market is invisible to EPD by definition. T4 here measures "
                  "the molecule, not the market."
                  % ", ".join(_codes("Weight loss / GLP-1"))),
    "menopause": (YES, "HRT: %s. NHS-dispensed HRT is a good proxy for menopause demand - "
                       "the 2022 supply crisis is in this series."
                       % ", ".join(_codes("Menopause / HRT"))),
    "trt": (YES, "testosterone: %s. Weaker than it looks: much private TRT is prescribed "
                 "privately and dispensed privately, so it never enters EPD."
                 % ", ".join(_codes("Men's health / TRT"))),

    "hair": (NO, "ABSTAINS. drugs.py: 'only topical minoxidil (~600 items/mth). The "
                 "finasteride-1mg code 1309000W0 is effectively unused on the NHS "
                 "(1 item/mth), so the private/OTC hair-loss market is invisible here.' "
                 "A hair TRANSPLANT is a surgical procedure and is not prescribed at all. "
                 "Firing or not firing on NHS minoxidil would tell you nothing about the "
                 "niche, so T4 does not get to vote."),
    "autism": (NO, "ABSTAINS. There is no autism-specific chemical. Autistic patients are "
                   "prescribed ADHD and antipsychotic medicines, so any proxy would be "
                   "measuring a different niche."),
    "privategp": (NO, "ABSTAINS. drugs.py lists 'Private GP' in NICHES_NO_PRESCRIBING: "
                      "'no drug is specific to seeing a GP privately.' Worse, EPD counts "
                      "NHS primary-care dispensing, so a shift of patients OUT of the NHS "
                      "would move this series DOWN. Wrong sign, not just no signal."),
    "ivf": (NO, "ABSTAINS. drugs.py: 'Clomifene (~76 items/mth) and chorionic "
                "gonadotrophin (~4 items/mth) are specialist-issued, so IVF / fertility "
                "demand is NOT visible.' EPD is primary care only."),

    # ---------------------------------------------------------------- graveyard
    # All eight abstain. This is not T4 being clever; it is T4 being blind. Counting any
    # of these as a 'correct rejection' would be the single easiest lie in the file.
    "cbd": (NO, "ABSTAINS. The only licensed CBD medicine in the UK is Epidyolex, for "
                "Dravet and Lennox-Gastaut syndrome - childhood epilepsies. Its "
                "prescribing measures paediatric neurology, not the CBD wellness boom. "
                "There is no code in drugs.py and one will not be invented here. NOTE "
                "THE CONSEQUENCE: on the single most dangerous false positive in the "
                "study, T4 HAS NO OPINION. It could not have saved you from CBD."),
    "ivdrip": (NO, "ABSTAINS. IV vitamin drips are private and are not dispensed in NHS "
                   "primary care."),
    "cryo": (NO, "ABSTAINS. Not a medicine."),
    "coldwater": (NO, "ABSTAINS. Not a medicine."),
    "psychedelics": (NO, "ABSTAINS. Psilocybin is Schedule 1. It cannot appear in NHS "
                         "primary-care dispensing, so T4's silence is the Misuse of Drugs "
                         "Act talking, not the radar."),
    "nad": (NO, "ABSTAINS. NAD+ infusions are private. Nicotinamide IS in the BNF (a "
                "vitamin, and a topical acne treatment) but its prescribing has nothing "
                "to do with longevity clinics; using it would be a category error, and "
                "drugs.py has no code for it."),
    "hbot": (NO, "ABSTAINS. Oxygen under pressure is a procedure, not a prescription."),
    "redlight": (NO, "ABSTAINS. A device, not a medicine."),
}

T4_CODES = {
    "adhd": _codes("ADHD"),
    "glp1": _codes("Weight loss / GLP-1"),
    "menopause": _codes("Menopause / HRT"),
    "trt": _codes("Men's health / TRT"),
}

# Unscored, but computed and published anyway: the two THIN proxies. They are NOT allowed
# to vote (T4_SCOPE says NO) because the proxy does not measure the niche - but hiding the
# series entirely would look like we had something to hide. They appear in the JSON under
# "t4_unscored_diagnostic" and nowhere else.
T4_UNSCORED = {
    "hair": _codes("Hair restoration"),
    "ivf": _codes("Fertility / women's health"),
}

NICHES = []
for _n in bt2.NICHES:
    _s, _why = T4_SCOPE[_n["key"]]
    NICHES.append(dict(_n, t4_scope=_s, t4_why=_why, t4=T4_CODES.get(_n["key"], [])))

BY_KEY = {n["key"]: n for n in NICHES}
POSITIVES = [n for n in NICHES if n["cls"] == POSITIVE]
GRAVEYARDS = [n for n in NICHES if n["cls"] == GRAVEYARD]

DIAG = bt2.DIAG          # backtest2's fetchers write here; share the dict


# =============================================================================
#  2b. THE T2 FETCHER, REBUILT SO A CI JOB ACTUALLY FINISHES
# =============================================================================
# WHAT KILLED THE FIRST RUN. bt2.fetch_t2 is SERIAL: one HTTP round-trip at a time. Its
# throttle permits 500 requests / 5 min, but a serial loop's true rate is 1/latency -
# ~0.3 req/s from a GitHub Actions runner - so ~5,970 cells took ~6 hours, the job hit
# the Actions 6h limit, was killed before the commit step, and the cache died with the
# runner. Every run started from zero. Three fixes, all here:
#
#   1. PARALLEL: N workers behind ONE thread-safe sliding-window throttle, so the pipe
#      runs at the documented limit (we stay at bt2.CH_RATE = 500/5min, inside CH's
#      600/5min). 5,970 cells / (500/300s) = ~60 minutes of rate time, ONCE, EVER -
#      every (keyword, month) hits-count is immutable and cached forever.
#   2. WALL-CLOCK BUDGET: --minutes sets a deadline; when it passes the fetch saves,
#      flags itself, and the run still writes a (labelled) partial report and exits 0.
#      The workflow commits the cache with `if: always()`, so the next run RESUMES.
#      Three 50-minute runs that finish beat one 6-hour run that dies.
#   3. PRIORITY: keywords are fetched most-load-bearing-first (ADHD, then the other
#      positives' primaries, then the graveyard primaries), keyword-by-keyword, so a
#      partial cache answers the benchmark question before it answers anything else.

PROGRESS = os.path.join(DATA, "backtest3_progress.json")
T2_WORKERS = 8
_RESERVE_S = 8 * 60      # wall-clock held back for the null calibration + the report


class SafeThrottle:
    """Thread-safe sliding-window limiter. bt2.Throttle is correct but assumes one
    caller; this serialises the window under a lock so N workers share ONE budget.
    Same numbers as bt2: 500 req / 300 s, inside Companies House's documented 600."""

    def __init__(self, n=None, per=None, clock=time.monotonic, sleep=time.sleep):
        self.n = n or bt2.CH_RATE
        self.per = per or bt2.CH_PER
        self.hist = deque()
        self.lock = threading.Lock()
        self.clock, self.sleep = clock, sleep

    def wait(self):
        while True:
            with self.lock:
                now = self.clock()
                while self.hist and now - self.hist[0] > self.per:
                    self.hist.popleft()
                if len(self.hist) < self.n:
                    self.hist.append(now)
                    return
                nap = self.per - (now - self.hist[0]) + 0.25
            self.sleep(max(nap, 0.05))


class _NoThrottle:                       # injected by the selftest; never sleeps
    def wait(self):
        pass


def _t2_keyword_order():
    """Fetch order = how much the REPORT needs each keyword. ADHD's primary first (the
    benchmark question), then every other positive's primary, then the graveyard
    primaries (specificity is the most important possible result), then secondaries.
    A run that dies early therefore dies holding the most informative partial dataset;
    half-fetched keywords are withheld by the coverage floor, never zero-filled."""
    order, seen = [], set()
    ranked = ([BY_KEY["adhd"]] + [n for n in POSITIVES if n["key"] != "adhd"]
              + GRAVEYARDS)
    for n in ranked:
        k = n["ch"][0]
        if k not in seen:
            seen.add(k)
            order.append(k)
    for n in ranked:
        for k in n["ch"][1:]:
            if k not in seen:
                seen.add(k)
                order.append(k)
    for k in bt2.ALL_KEYWORDS:           # safety net: anything not reachable via NICHES
        if k not in seen:
            seen.add(k)
            order.append(k)
    return order


def _t2_one(fetch, kw, m, thr):
    try:
        return fetch(kw, m, thr)
    except Exception as e:               # counted as an error, never hidden
        return None, "EXC:%s" % type(e).__name__


def fetch_t2_parallel(max_calls, force=False, deadline=None, fetch_fn=None,
                      probe_fn=None, workers=T2_WORKERS, save_every=200,
                      clock=time.monotonic, throttle=None):
    """{keyword: {month: hits}} - same shape, same cache files as bt2.fetch_t2, but
    parallel, deadline-aware and priority-ordered (see the section header above).

    Resumable BY CONSTRUCTION: a cell is fetched only if absent from the cache, the
    cache is saved every `save_every` cells AND in a finally-block, and a cell's value
    is immutable (the number of companies incorporated in March 2019 will never
    change). So kill this anywhere, restart it, and it converges on the identical
    cache without refetching - the selftest proves exactly that, offline, by injecting
    fetch_fn/probe_fn/throttle/clock."""
    months = axis(T2_START)
    cache = {} if force else (load(bt2.CH_CACHE) or {})
    probes = {} if force else (load(bt2.CH_PROBE) or {})
    fetch = fetch_fn or bt2.ch_month_hits
    probe = probe_fn or bt2.ch_precision_probe
    thr = throttle or SafeThrottle()

    kw_order = _t2_keyword_order()
    todo_n = sum(1 for k in kw_order for m in months
                 if cache.get(k, {}).get(m) is None)
    DIAG["t2_cells_total"] = len(kw_order) * len(months)
    DIAG["t2_cells_cached"] = DIAG["t2_cells_total"] - todo_n
    DIAG.pop("t2_hit_budget_cap", None)
    DIAG.pop("t2_deadline_hit", None)

    if fetch_fn is None and not bt2.CH_KEY:
        DIAG["t2"] = ("CH_API_KEY not set. T2 uses the cache only (%d/%d cells). Get a "
                      "free key at developer.company-information.service.gov.uk."
                      % (DIAG["t2_cells_cached"], DIAG["t2_cells_total"]))
        return cache, probes

    def spent():
        return deadline is not None and clock() >= deadline

    calls, errs, unsaved, fatal = 0, {}, 0, None
    print("  T2: %d keywords x %d months = %d cells; %d cached, %d to fetch "
          "(cap %d, %d workers, 500/5min shared)"
          % (len(kw_order), len(months), DIAG["t2_cells_total"],
             DIAG["t2_cells_cached"], todo_n, max_calls, workers))

    ex = _futures.ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        for kw in kw_order:
            if fatal or spent() or calls >= max_calls:
                break
            if kw not in probes and calls < max_calls:
                probes[kw] = probe(kw, thr)
                calls += 1
            missing = [m for m in months if cache.get(kw, {}).get(m) is None]
            i = 0
            while i < len(missing):
                if fatal or spent() or calls >= max_calls:
                    break
                chunk = missing[i:i + min(128, max_calls - calls)]
                i += len(chunk)
                futs = {ex.submit(_t2_one, fetch, kw, m, thr): m for m in chunk}
                for f in _futures.as_completed(futs):
                    m = futs[f]
                    h, err = f.result()   # a BaseException propagates; finally saves
                    calls += 1
                    if h is None:
                        errs[err] = errs.get(err, 0) + 1
                        if err in ("HTTP 401", "HTTP 403"):
                            fatal = ("Companies House returned %s - the key is "
                                     "missing, wrong, or unauthorised. Aborting T2."
                                     % err)
                        continue
                    cache.setdefault(kw, {})[m] = h
                    unsaved += 1
                if unsaved >= save_every:
                    save(bt2.CH_CACHE, cache)
                    save(bt2.CH_PROBE, probes)
                    unsaved = 0
                    print("    ... %d calls this run, %d errors, cache saved"
                          % (calls, sum(errs.values())))
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
        save(bt2.CH_CACHE, cache)
        save(bt2.CH_PROBE, probes)

    if fatal:
        DIAG["t2_fatal"] = fatal
    if calls >= max_calls:
        DIAG["t2_hit_budget_cap"] = True
    if spent():
        DIAG["t2_deadline_hit"] = True
    DIAG["t2_calls_spent"] = calls
    DIAG["t2_errors"] = errs
    filled = sum(1 for k in kw_order for m in months
                 if cache.get(k, {}).get(m) is not None)
    DIAG["t2_cells_new_this_run"] = filled - DIAG["t2_cells_cached"]
    DIAG["t2_coverage"] = round(filled / max(1, DIAG["t2_cells_total"]), 3)
    left = DIAG["t2_cells_total"] - filled
    DIAG["t2"] = ("ok - %d/%d cells" % (filled, DIAG["t2_cells_total"]) if left == 0
                  else "PARTIAL - %d/%d cells (%d left; re-run to resume, the cache "
                       "persists)" % (filled, DIAG["t2_cells_total"], left))
    return cache, probes


def _completeness(t2, t4):
    """How much of the study's data this run actually holds. Printed at the TOP of the
    report, because a partial dataset presented as the full study is the report
    lying."""
    months2 = axis(T2_START)
    kws = sorted(bt2.ALL_KEYWORDS)
    cells = sum(1 for k in kws for m in months2 if t2.get(k, {}).get(m) is not None)
    total = len(kws) * len(months2)
    cov = {k: sum(1 for m in months2 if t2.get(k, {}).get(m) is not None)
           / float(len(months2)) for k in kws}
    usable = sorted(k for k in kws if cov[k] >= 0.9)
    latest = DIAG.get("t4_latest_published") or END
    months4 = [m for m in axis(T4_START, END) if m <= latest]
    have4 = sum(1 for m in months4 if m in t4)
    return {"t2_cells_fetched": cells, "t2_cells_total": total,
            "t2_pct": round(100.0 * cells / max(1, total), 1),
            "t2_keywords_usable": usable,
            "t2_keywords_partial_or_missing": sorted(set(kws) - set(usable)),
            "t4_months_fetched": have4, "t4_months_total": len(months4),
            "t4_pct": round(100.0 * have4 / max(1, len(months4)), 1),
            "t3_survivorship_corrected": bool(DIAG.get("cqc_survivorship_corrected")),
            "t2_complete": cells == total,
            "t4_complete": have4 >= 0.9 * max(1, len(months4)),
            "complete": (cells == total
                         and have4 >= 0.9 * max(1, len(months4)))}


def _completeness_lines(c):
    """The banner write_md() puts directly under the title."""
    if c is None:
        return []
    if c["complete"]:
        return ["\n> **Data completeness: FULL.** T2 %d/%d cells (100%%), T4 %d/%d "
                "months (%.0f%%), T3 survivorship-corrected: %s.\n"
                % (c["t2_cells_fetched"], c["t2_cells_total"], c["t4_months_fetched"],
                   c["t4_months_total"], c["t4_pct"],
                   "yes" if c["t3_survivorship_corrected"] else "NO")]
    L = ["\n> **PARTIAL RUN - THE DATA BELOW IS INCOMPLETE. Numbers in this report "
         "can change when the remaining cells arrive.**\n>"]
    L.append("> - T2 Companies House: **%s%% of cells fetched** (%d/%d). Keywords "
             "with >=90%% coverage, and therefore usable this run: %d/%d. Withheld "
             "(<90%% fetched, shown as 'no data', never zero-filled): %s.\n>"
             % (c["t2_pct"], c["t2_cells_fetched"], c["t2_cells_total"],
                len(c["t2_keywords_usable"]),
                len(c["t2_keywords_usable"])
                + len(c["t2_keywords_partial_or_missing"]),
                ", ".join(c["t2_keywords_partial_or_missing"]) or "none"))
    L.append("> - T4 NHSBSA EPD: %s%% of months (%d/%d).\n>"
             % (c["t4_pct"], c["t4_months_fetched"], c["t4_months_total"]))
    L.append("> - Every fetched cell is cached and committed. A (keyword, month) "
             "count is immutable, so re-running the workflow RESUMES; it never "
             "repeats paid work. Run again until this banner disappears.\n")
    return L



def _validate_codes():
    """Fail loudly rather than fetch garbage.

    A BNF chemical code is 9 characters. Anything shorter is a section, not a chemical,
    and will silently sum the wrong thing. Anything in drugs.DEAD_CODES returns an empty
    series that looks like zero prescribing. And anything not in drugs.DRUGS was typed by
    a human, which is the failure mode drugs.py exists to prevent.
    """
    errs = []
    for key, codes in list(T4_CODES.items()) + list(T4_UNSCORED.items()):
        if not codes:
            errs.append("%s: no BNF codes resolved from drugs.py" % key)
        for c in codes:
            if not re.match(r"^[0-9A-Z]{9}$", c):
                errs.append("%s: %r is not a 9-char BNF chemical code" % (key, c))
            if drugs and c in getattr(drugs, "DEAD_CODES", {}):
                errs.append("%s: %s is in drugs.DEAD_CODES - it returns an empty series"
                            % (key, c))
            if drugs and c not in getattr(drugs, "DRUGS", {}):
                errs.append("%s: %s is not a verified code in drugs.DRUGS" % (key, c))
    return errs


# =============================================================================
#  3. T4 - NHSBSA EPD, MONTHLY, BACK TO 2014
# =============================================================================
# nhsbsa_epd.py fetches ONE MONTH AT A TIME and returns EVERY chemical in it (~2,800 rows
# a month). For the dashboard that is right - it powers the rising-drug discovery. For a
# 148-month backfill it is several hundred megabytes of transfer to keep 21 numbers.
#
# So we ask a narrower question of the same API: only our codes, plus the canary. The
# table/column resolution - which is where the trap is - is NOT reimplemented; it comes
# from epd.resource_for(), so the July-2025 SNOMED schema switch is handled by the module
# that verified it live.
#
# THE TRAP, RESTATED, because a careless query here would be catastrophic and silent:
# NHSBSA renamed `bnf_chemical_substance` from a CODE to a NAME in July 2025. Query the
# new table with the old column and you do not get an error - you get {"i": null}. Turn
# that null into a zero and the dashboard reports that ADHD prescribing collapsed to
# nothing in July 2025. Every month here is checked against a canary chemical
# (sertraline: boring, huge, stable). A month whose canary is absent is REJECTED and left
# ABSENT. It is never allowed to be zero.
CANARY = epd.CANARY_CODE
MAX_EPD_CALLS = 200


def epd_sql(key, codes):
    """One month, our codes only, summed server-side.

    The codes are interpolated into SQL, so they are validated against a strict pattern
    first. They come from our own dict, not from user input, but a 9-char whitelist costs
    one line and removes the question.
    """
    table, code_col, _name = epd.resource_for(key)
    want = sorted(set(list(codes) + [CANARY]))
    for c in want:
        if not re.match(r"^[0-9A-Z]{9}$", c):
            raise ValueError("refusing to build SQL with a non-BNF code: %r" % c)
    inlist = ",".join("'%s'" % c for c in want)
    return ("SELECT %s c,SUM(items) i FROM `%s` WHERE %s IN (%s) GROUP BY 1"
            % (code_col, table, code_col, inlist))


def epd_url(key, codes):
    table, _c, _n = epd.resource_for(key)
    return epd.BASE + "?" + urllib.parse.urlencode({"resource_id": table,
                                                    "sql": epd_sql(key, codes)})


def epd_fetch_month(key, codes, getter=None):
    """-> {code: items} or None.

    None means "we do not know", NEVER "it was zero". Two layers of defence:
      1. the narrow WHERE-IN query, whose response is parsed by epd.parse_records() - the
         same parser that raises on a 200-with-an-error-body;
      2. if that fails for ANY reason (an unsupported SQL form, a bad month), fall back to
         epd.fetch_month(), the whole-month GROUP BY that was verified against the live
         API. Slower, bigger, but known to work.
    In both cases the canary must be present or the month is discarded.
    """
    get = getter or epd._get_json
    try:
        counts, _names = epd.parse_records(get(epd_url(key, codes)))
        if epd.canary_ok(counts):
            return counts
    except Exception:
        pass
    got = epd.fetch_month(key, getter=getter)          # full-month fallback
    if not got:
        return None
    counts, _names = got
    keep = set(list(codes) + [CANARY])
    return {c: v for c, v in counts.items() if c in keep}


def epd_latest(today=None):
    return epd.latest_published(today)


def fetch_t4(max_calls=MAX_EPD_CALLS, force=False, getter=None, today=None,
             deadline=None, clock=time.monotonic, workers=4):
    """{month: {code: items}}. Resumable; a published month is immutable, so cached
    months are never refetched and the deep backfill fills in over a few runs."""
    hist = {} if force else (load(EPD_CACHE) or {})
    if drugs is None:
        DIAG["t4"] = "drugs.py not importable - T4 WITHHELD (no verified BNF codes)."
        return hist

    all_codes = sorted({c for v in T4_CODES.values() for c in v}
                       | {c for v in T4_UNSCORED.values() for c in v})
    latest = epd_latest(today)
    months = [m for m in axis(T4_START, END) if m <= latest]
    todo = [m for m in months if m not in hist]
    DIAG["t4_months_total"] = len(months)
    DIAG["t4_months_cached"] = len(months) - len(todo)
    DIAG["t4_latest_published"] = latest
    DIAG["t4_codes"] = len(all_codes)

    if not todo:
        DIAG["t4"] = "cache hit - %d/%d months, 0 calls" % (len(months), len(months))
        return hist

    print("  T4: %d months 2014-01..%s; %d cached, %d to fetch (cap %d)"
          % (len(months), latest, DIAG["t4_months_cached"], len(todo), max_calls))
    calls, bad = 0, []
    DIAG.pop("t4_deadline_hit", None)

    def _spent():
        if deadline is not None and clock() >= deadline:
            DIAG["t4_deadline_hit"] = True
            return True
        return False

    if getter is not None or workers <= 1:      # deterministic path; the selftest uses it
        for m in todo:
            if calls >= max_calls:
                DIAG["t4_hit_budget_cap"] = True
                break
            if _spent():
                break
            got = epd_fetch_month(m, all_codes, getter=getter)
            calls += 1
            if got is None:
                bad.append(m)             # ABSENT, not zero. The distinction is the point.
                continue
            hist[m] = got
            if calls % 24 == 0:
                save(EPD_CACHE, hist)
                print("    ... %d/%d months" % (calls, min(len(todo), max_calls)))
    else:
        # A published month is immutable and this is a bulk open-data endpoint; a
        # handful of concurrent month-reads is polite and ~4x faster than the serial
        # loop that used to sit here (each month is one big HTTP round-trip).
        ex = _futures.ThreadPoolExecutor(max_workers=workers)
        try:
            i = 0
            while i < len(todo):
                if calls >= max_calls:
                    DIAG["t4_hit_budget_cap"] = True
                    break
                if _spent():
                    break
                chunk = todo[i:i + min(workers * 3, max_calls - calls)]
                i += len(chunk)
                futs = {ex.submit(epd_fetch_month, m, all_codes): m for m in chunk}
                for f in _futures.as_completed(futs):
                    m = futs[f]
                    try:
                        got = f.result()
                    except Exception:
                        got = None
                    calls += 1
                    if got is None:
                        bad.append(m)     # ABSENT, not zero. The distinction is the point.
                    else:
                        hist[m] = got
                save(EPD_CACHE, hist)
                print("    ... %d/%d months" % (calls, min(len(todo), max_calls)))
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
    save(EPD_CACHE, hist)

    DIAG["t4_calls_spent"] = calls
    DIAG["t4_months_unread"] = bad[:12]
    DIAG["t4_months_unread_n"] = len(bad)
    have = [m for m in months if m in hist]
    cov = len(have) / max(1, len(months))
    DIAG["t4_coverage"] = round(cov, 3)
    # "ok - 0/148 months" is not ok. Say so. A tier that read nothing must not produce a
    # cheerful diagnostic line that a reader skims past.
    if cov >= 0.9:
        DIAG["t4"] = "ok - %d/%d months" % (len(have), len(months))
    elif DIAG.get("t4_hit_budget_cap"):
        DIAG["t4"] = ("PARTIAL - %d/%d months; the call budget stopped the backfill. A "
                      "published month is immutable, so re-run and it resumes. T4 series "
                      "are WITHHELD below 90%% coverage rather than zero-filled."
                      % (len(have), len(months)))
    else:
        DIAG["t4"] = ("UNUSABLE - only %d/%d months could be read (%.0f%%). T4 is WITHHELD, "
                      "not zeroed. Every T4 cell in the report will read 'no data', which is "
                      "the truth." % (len(have), len(months), 100 * cov))
    if bad:
        # A month can go unread for two very different reasons and they must not be
        # conflated: the network failed (boring), or the CANARY rejected it (alarming - it
        # means NHSBSA has changed the schema and we would otherwise be reading nulls as
        # zeros). We cannot tell them apart from here, so we say both, loudly.
        DIAG["t4_unread_warning"] = (
            "%d month(s) could not be read and were DROPPED, never zeroed. Either the "
            "request failed, or the month failed the sertraline canary. If the count is "
            "large and the network was fine, NHSBSA has changed its schema again and "
            "epd.resource_for() must be fixed BEFORE any T4 number is trusted - the "
            "failure mode it guards against is a table of nulls that reads as 'prescribing "
            "collapsed to zero'." % len(bad))
    return hist


def t4_series(niche, hist, codes=None, latest=None):
    """Monthly items for a niche. -> (months, vals, coverage) or (months, None, coverage).

    The axis runs to the LATEST MONTH NHSBSA HAS PUBLISHED, not to the latest month we
    happen to hold. That distinction is the whole point: a month we are missing is a HOLE,
    and a series with holes is not a series - the estimator would read a hole as a zero and
    then read the recovery as a boom. Anchoring the axis to max(cache) would make a cache
    holding three months look like a complete three-month series with 100% coverage.
    Below 90% coverage the series is WITHHELD.
    """
    codes = codes if codes is not None else niche.get("t4") or []
    if not codes or not hist:
        return [], None, 0.0
    last = latest or min(END, epd_latest())
    months = [m for m in axis(T4_START, END) if m <= last]
    if not months:
        return [], None, 0.0
    vals, seen = [], 0
    for m in months:
        row = hist.get(m)
        if row is None:
            vals.append(0.0)
        else:
            vals.append(float(sum(row.get(c, 0) for c in codes)))
            seen += 1
    cov = seen / len(months)
    if cov < 0.9:
        return months, None, cov
    return months, vals, cov


# =============================================================================
#  4. TIER STATE - and the two abstentions that stop the FP rate being a lie
# =============================================================================
def scope_of(n, tier):
    if tier == "T3":
        return (bool(n["t3_scope"]),
                "not a CQC-registrable activity - T3 ABSTAINS, it does not reject")
    if tier == "T4":
        return bool(n["t4_scope"]), n["t4_why"]
    return True, ""


def growth_ratio_at(vals, i):
    """The estimator's own condition-1 ratio, (R[i]+K) / (median baseline + K), exposed as
    a plain descriptive number. Not a second estimator - it is the SAME arithmetic
    onset_robust uses (12-month rolling sum against the median of that sum over
    [i-24, i-12]), pulled out so we can ask it a question onset_robust does not answer:
    'how fast was this niche ALREADY growing on the first month we were able to look?'
    """
    R = rolling_sum(vals, 12)
    if i is None or not (0 <= i < len(R)) or R[i] is None:
        return None
    xs = [R[j] for j in range(max(0, i - 24), i - 12 + 1)
          if 0 <= j < len(R) and R[j] is not None]
    if len(xs) < 7:
        return None
    b = statistics.median(xs)
    return (R[i] + K_SMOOTH) / (b + K_SMOOTH)


def tier_state(n, tier, months, vals, growth_x=GROWTH_X):
    """FIRED / NO_ONSET / ALREADY_BOOMING / OUT_OF_SCOPE / BELOW_FLOOR / NO_DATA.

    NO_ONSET        the tier COULD have fired and did not, and the niche was NOT already
                    booming when the window opened. A real rejection. On the graveyard this
                    is a true negative and it is worth credit.
    OUT_OF_SCOPE    the tier is structurally incapable of seeing this niche (CQC cannot
                    register an ice bath; the NHS does not dispense cryotherapy).
                    ABSTENTION.
    BELOW_FLOOR     the series never reaches the tier's minimum level, so onset_robust is
                    FORBIDDEN to fire whatever it does. ABSTENTION - and the easy one to
                    miss, because in a table it looks exactly like a correct rejection.
    ALREADY_BOOMING see below. ABSTENTION, and the one nobody had noticed.

    Score any abstention as a rejection and the false-positive rate goes to zero without
    the radar doing anything at all.

    ALREADY_BOOMING - THE STATE THIS FILE HAD TO ADD, AND WHY IT MATTERS MOST FOR T4
    --------------------------------------------------------------------------------
    onset_robust does NOT detect growth. It detects ACCELERATION - a break from the
    niche's own recent growth regime. Fixture 23 demonstrates this on a series compounding
    at a steady +3%/month from its very first month: the estimator NEVER FIRES, because its
    z-scale is the median/MAD of the niche's OWN recent z-history, and a smooth exponential
    has a flat z-history. That is not a bug (it is what stops the detector screaming at
    every niche that is merely large), but it has a consequence nobody had written down:

      A niche that was ALREADY IN A SUSTAINED BOOM before the data window opens will be
      reported as NO_ONSET - which is indistinguishable, in a results table, from the
      estimator having correctly REJECTED it.

    That is a catastrophic confusion, and it lands squarely on the benchmark case.
    Lisdexamfetamine went 737 items/month in Jan-2014 - the FIRST month NHSBSA publishes -
    to 16,460 by Jan-2020. T4's history opens with the ADHD boom already several years old.
    If we scored a T4 silence on ADHD as "T4 did not flag ADHD", we would be reporting the
    exact opposite of the truth.

    So: if the niche was ALREADY growing at >= growth_x on the FIRST MONTH THE ESTIMATOR
    COULD LOOK, and no onset is found inside the window, the state is ALREADY_BOOMING. It
    is an abstention, not a rejection, and not a hit either: the onset is CENSORED - it
    happened before the data starts. `growth_at_first_testable` is reported so the size of
    the pre-existing boom is visible.
    """
    in_scope, why = scope_of(n, tier)
    if not in_scope:
        return {"state": "OUT_OF_SCOPE", "onset": None, "note": why}
    if not vals or sum(vals) == 0:
        return {"state": "NO_DATA", "onset": None}

    floor = FLOORS.get(tier, {}).get("min_level", 0.0)
    peak = max([x for x in rolling_sum(vals, 12) if x is not None] or [0.0])
    if peak < floor:
        return {"state": "BELOW_FLOOR", "onset": None, "peak_12m": round(peak, 1),
                "floor": floor, "total": round(sum(vals), 1),
                "note": ("the series NEVER reaches this tier's minimum level (%.0f per 12 "
                         "months), so the estimator is structurally forbidden to fire. An "
                         "ABSTENTION, not a rejection: the tier is blind here - which is "
                         "exactly the state a radar is in while a niche is still small "
                         "enough to be cheap to buy." % floor)}

    rb = onset_robust(months, vals, tier, growth_x=growth_x)
    sp = onset_spec(months, vals)

    # FIRST TESTABLE MONTH. onset_robust needs ~54 months of history before z exists at
    # all. It reports how many months were testable; z is defined on a contiguous suffix
    # (each of its preconditions is monotone in t), so the first testable index is exactly
    # len - testable. Fixture 24 asserts the ~54.
    ft_idx = len(vals) - rb["testable_months"] if rb["testable_months"] else None
    ft = months[ft_idx] if (ft_idx is not None and 0 <= ft_idx < len(months)) else None
    g_ft = growth_ratio_at(vals, ft_idx)

    # LEFT-CENSORING (it DID fire, but in the first months it was allowed to). The onset is
    # then a LOWER BOUND on how early you could have seen it, not a date.
    lc = bool(rb["onset_idx"] is not None and ft_idx is not None
              and rb["onset_idx"] - ft_idx <= 2)

    # ALREADY_BOOMING (it did NOT fire, because it had been booming since before we could
    # look). Read the docstring. This is an abstention.
    already = bool(rb["onset"] is None and g_ft is not None and g_ft >= growth_x)

    state = "FIRED" if rb["onset"] else ("ALREADY_BOOMING" if already else "NO_ONSET")
    return {"state": state,
            "onset": rb["onset"],
            "onset_idx": rb["onset_idx"],
            "knowable_by": knowable_by(tier, rb["onset"]),
            "z_at_onset": rb["z_at_onset"], "peak_z": rb["peak_z"],
            "growth_at_onset": rb["growth_at_onset"],
            "level_at_onset": rb["level_at_onset"],
            "baseline_at_onset": rb["baseline_at_onset"],
            "low_count_unreliable": rb["low_count_unreliable"],
            "first_testable": ft,
            "growth_at_first_testable": round(g_ft, 2) if g_ft is not None else None,
            "left_censored": lc,
            "already_booming": already,
            "peak_12m": round(peak, 1),
            "total": round(sum(vals), 1),
            "spec_onset": sp["onset"],
            "spec_undefined_months": sp["undefined_months"],
            "agrees_with_spec": rb["onset"] == sp["onset"],
            "note": (("the niche was ALREADY growing %.2fx year-on-year on %s, the FIRST "
                      "month the estimator could look at all, and never accelerated beyond "
                      "its own regime afterwards. The onset is CENSORED - it predates the "
                      "data. This is an ABSTENTION. It is NOT a rejection, and it is NOT "
                      "the tier failing to see the niche: the tier can see it perfectly "
                      "well and it is enormous. It simply cannot DATE it."
                      % (g_ft, ft)) if already else None)}


def build_series(t1, t2, t3, t4, primary_only=False):
    """{niche_key: {tier: (months, vals)}}. The ONE place raw sources become series."""
    out = {}
    for n in NICHES:
        s = {}
        if n["key"] in t1:
            s["T1"] = (axis(T1_START), t1[n["key"]])
        v, _cov = bt2.t2_series(n, t2, primary_only=primary_only)
        if v:
            s["T2"] = (axis(T2_START), v)
        if n["key"] in t3:
            s["T3"] = (axis(T3_START), t3[n["key"]]["corrected"])
        m4, v4, _c4 = t4_series(n, t4)
        if v4:
            s["T4"] = (m4, v4)
        out[n["key"]] = s
    return out


def evaluate(series, growth_x=GROWTH_X):
    res = {}
    for n in NICHES:
        s = series.get(n["key"], {})
        tiers = {}
        for t in TIERS:
            months, vals = s.get(t, (axis(TIER_START[t]), None))
            tiers[t] = tier_state(n, t, months, vals, growth_x=growth_x)
        res[n["key"]] = {"key": n["key"], "label": n["label"], "class": n["cls"],
                         "why": n["why"], "caveats": n.get("caveats", []),
                         "t4_why": n["t4_why"], "tiers": tiers}
    return res


# =============================================================================
#  5. CALIBRATE THE NULL - the function backtest2 promised and never wrote
# =============================================================================
# THE PROBLEM. onset_robust does not fire the month a boom starts. It fires once the boom
# is undeniable. How long that takes depends on the SERIES, not on the world:
#
#   - a thin, noisy series takes longer to clear a z threshold than a smooth one;
#   - a tier whose history starts later has a later FIRST TESTABLE MONTH and literally
#     cannot fire before it, however loud the boom is;
#   - a tier with a higher level FLOOR cannot fire until the niche is big enough.
#
# All three differ between tiers. So the pipeline reports "T1 leads T2 leads T3 leads T4"
# EVEN WHEN ALL FOUR BOOMS HAPPEN IN THE SAME MONTH. A live run measuring "T2 leads T3 by
# 4 months" would then be reporting NOTHING AT ALL, and reporting it as a finding.
#
# calibrate_null() simulates niches whose FOUR TIERS ALL BOOM IN THE SAME CALENDAR MONTH -
# a TRUE lead of exactly zero - pushes them through the REAL axes, the REAL floors and the
# REAL estimator, and measures what comes out. Anything a live run reports has to beat
# this to be evidence of anything.
def _counts(n, rate_fn, seed):
    """Poisson counts, with a normal approximation above lambda=200.

    NOT a detail. backtest_core._poisson_series uses Knuth's method, which computes
    exp(-lambda): at lambda=5,000 - which is where PRESCRIBING lives - that underflows to
    exactly 0.0, the loop then runs until the running product underflows too, and it
    returns a number around 700 instead of around 5,000. It does not crash. It returns
    garbage, quietly, and only for the tier with the biggest counts. Guard, don't inherit.
    """
    rnd = random.Random(seed)
    out = []
    for t in range(n):
        lam = max(rate_fn(t), 0.0)
        if lam > 200.0:
            out.append(float(max(0.0, round(rnd.gauss(lam, math.sqrt(lam))))))
            continue
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            p *= rnd.random()
            if p <= L:
                break
        out.append(float(k - 1))
    return out


def _ramp(base, mult, boom_i, span=18):
    return lambda t: (base if t < boom_i
                      else base * (1.0 + (mult - 1.0) * min(1.0, (t - boom_i) / span)))


# Default shapes: roughly what a real UK niche produces per month, pre-boom, per tier.
# T1 is a 0-100 index; the rest are counts. assemble() overrides these with the levels and
# growth multiples actually OBSERVED in the run, so the null is calibrated to this data
# and not to a guess. The defaults are what the offline selftest uses.
NULL_SHAPES = {"T1": {"base": 5.0, "mult": 18.0, "index": True},
               "T2": {"base": 6.0, "mult": 5.0, "index": False},
               "T3": {"base": 3.0, "mult": 5.0, "index": False},
               "T4": {"base": 4000.0, "mult": 4.0, "index": False}}

NULL_REPS = 200
NULL_BOOM_RANGE = ("2017-01", "2023-01")     # where a real UK boom could plausibly start


def calibrate_null(shapes=None, reps=NULL_REPS, seed=20260713, growth_x=GROWTH_X,
                   tiers=TIERS):
    """TRUE LEAD = ZERO. What does this pipeline report anyway?

    Returns per-pair: the median apparent gap, its p90, and the share of replications in
    which the tiers landed 'in the predicted order' - which is the correct null for the
    sign test, and it is NOT 0.5.
    """
    shapes = shapes or NULL_SHAPES
    rnd = random.Random(seed)
    lo, hi = NULL_BOOM_RANGE
    span = m_diff(lo, hi)
    gaps = {"%s->%s" % (a, b): [] for a, b in PAIRS}
    fired = {t: 0 for t in tiers}
    censored = {t: 0 for t in tiers}

    for r in range(reps):
        boom = m_add(lo, rnd.randint(0, max(0, span)))
        onsets = {}
        for t in tiers:
            ax = axis(TIER_START[t])
            if boom not in ax:
                continue
            sh = shapes.get(t) or NULL_SHAPES[t]
            bi = ax.index(boom)
            rate = _ramp(sh["base"], sh["mult"], bi)
            if sh.get("index"):
                # Google Trends: a smooth integer-truncated 0-100 index, not a count.
                vals = [float(int(min(100.0, rate(i))
                                  + ((i * 7919 + r * 13) % 5) / 5.0))
                        for i in range(len(ax))]
            else:
                # NOT hash(t): Python randomises str hashing per process (PYTHONHASHSEED),
                # which would make this "deterministic" calibration silently irreproducible
                # from one run to the next.
                vals = _counts(len(ax), rate, seed=seed + r * 17 + 991 * TIERS.index(t))
            o = onset_robust(ax, vals, t, growth_x=growth_x)
            if o["onset"]:
                onsets[t] = o["onset"]
                fired[t] += 1
                ft = len(vals) - o["testable_months"] if o["testable_months"] else None
                if ft is not None and o["onset_idx"] - ft <= 2:
                    censored[t] += 1
        for a, b in PAIRS:
            if a in onsets and b in onsets:
                gaps["%s->%s" % (a, b)].append(m_diff(onsets[a], onsets[b]))

    out = {}
    for pair, v in gaps.items():
        if not v:
            out[pair] = None
            continue
        v = sorted(v)
        out[pair] = {
            "n": len(v),
            "median_gap_months": statistics.median(v),
            "mean_gap_months": round(statistics.fmean(v), 2),
            "p90": v[min(len(v) - 1, int(0.9 * len(v)))],
            "p10": v[int(0.1 * len(v))],
            "pct_in_predicted_order": round(100.0 * sum(1 for x in v if x > 0) / len(v), 1),
        }
    return {"reps": reps, "true_lead_months": 0, "pairs": out,
            "tier_fire_rate": {t: round(fired[t] / reps, 3) for t in tiers},
            "tier_left_censored_rate": {t: (round(censored[t] / fired[t], 3)
                                            if fired[t] else None) for t in tiers},
            "shapes": shapes,
            "boom_window": list(NULL_BOOM_RANGE),
            "note": ("Every one of these niches booms in ALL FOUR TIERS IN THE SAME MONTH. "
                     "The true lead is exactly zero. Any gap below is manufactured by the "
                     "measurement: different history start dates (T3/T4 begin in 2014 and "
                     "cannot fire before ~2018-07), different level floors, and different "
                     "noise. A measured gap that does not clear the p90 column is not "
                     "evidence of a lead.")}


def observed_shapes(series):
    """Calibrate the null to THIS data instead of to a guess.

    base = the median across niches of the mean of the first 24 months of the series.
    mult = the median across niches of (mean of the last 24 months / base), clipped to
           [2, 25] so one runaway niche cannot define the null for everybody.
    """
    out = {}
    for t in TIERS:
        bases, mults = [], []
        for n in NICHES:
            s = series.get(n["key"], {}).get(t)
            if not s:
                continue
            vals = s[1]
            if not vals or len(vals) < 60:
                continue
            b = statistics.fmean(vals[:24])
            e = statistics.fmean(vals[-24:])
            if b <= 0.01:
                continue
            bases.append(b)
            mults.append(min(25.0, max(2.0, e / b)))
        if not bases:
            continue
        out[t] = {"base": round(statistics.median(bases), 2),
                  "mult": round(statistics.median(mults), 2),
                  "index": (t == "T1")}
    for t in TIERS:                       # never leave a tier undefined
        out.setdefault(t, NULL_SHAPES[t])
    return out


# =============================================================================
#  6. THE HEADLINE: STANDING IN EARLY 2022, WOULD IT HAVE FLAGGED ADHD?
# =============================================================================
# Two things have to be true for the answer to be YES, and only one of them is about the
# onset date:
#   (a) the tier fired at some month M <= cutoff; and
#   (b) M was KNOWABLE by the cutoff - i.e. M + 3 months of persistence + the source's own
#       publication lag <= cutoff.
# An onset you could only date in hindsight is not an early warning. It is a memoir.
def truncated_onset(n, tier, months, vals, cutoff, growth_x=GROWTH_X):
    """Re-run the estimator on ONLY the data that existed at `cutoff`.

    This is the honest version of the question. The estimator is designed to be causal
    (every baseline looks backwards), so this SHOULD return the same onset as the full-data
    run whenever the onset was knowable in time. If it ever does not, the full-data onsets
    are contaminated by hindsight and none of them can be quoted. Fixture 4 proves the
    equivalence on synthetic data; this function proves it on the real data, per niche, and
    any mismatch is reported as a defect rather than smoothed over.
    """
    if not vals:
        return {"state": "NO_DATA", "onset": None}
    last = m_add(cutoff, -PUB_LAG[tier])          # the freshest month actually published
    keep = [i for i, m in enumerate(months) if m <= last]
    if len(keep) < 60:
        return {"state": "TOO_SHORT", "onset": None,
                "note": "fewer than 60 months of history existed by %s - the estimator "
                        "cannot fire at all" % cutoff}
    k = keep[-1] + 1
    return tier_state(n, tier, months[:k], vals[:k], growth_x=growth_x)


def yoy_at(months, vals, when):
    """What the DASHBOARD would have shown, as opposed to what the ONSET DETECTOR would
    have shouted. 12-month sum at `when` versus the 12-month sum a year earlier.

    This exists because of ALREADY_BOOMING. A tier can be completely silent (no onset to
    find - the boom predates the data) while the niche is sitting there on the screen
    growing 40% a year. Reporting only the detector's verdict would then understate what a
    human looking at the radar in early 2022 would actually have seen, which is not honest
    in the other direction.
    """
    if not vals or not months or when not in months:
        return None
    i = months.index(when)
    R = rolling_sum(vals, 12)
    if i < 12 or R[i] is None or R[i - 12] in (None, 0):
        return None
    return round(100.0 * (R[i] / R[i - 12] - 1.0), 1)


def standing_at(res, series, cutoff, key="adhd"):
    n = BY_KEY[key]
    rows, mismatches = [], []
    for t in TIERS:
        full = res[key]["tiers"][t]
        s = series.get(key, {}).get(t)
        tr = truncated_onset(n, t, s[0], s[1], cutoff) if s else {"state": "NO_DATA",
                                                                  "onset": None}
        kb = full.get("knowable_by")
        flagged = bool(full.get("onset") and kb and kb <= cutoff)
        # The estimator claims to be causal. Check it, on the real series, right here.
        agree = (tr.get("onset") == full.get("onset")) if flagged else None
        if agree is False:
            mismatches.append({"tier": t, "full": full.get("onset"),
                               "as_of_cutoff": tr.get("onset")})
        # What a human would have SEEN, using only data published by the cutoff.
        seen_m = m_add(cutoff, -PUB_LAG[t])
        rows.append({
            "tier": t, "name": TIER_NAME[t], "state": full["state"],
            "onset": full.get("onset"), "knowable_by": kb,
            "pub_lag_months": PUB_LAG[t], "persistence_months": SUSTAIN_MONTHS,
            "flagged_by_cutoff": flagged,
            "left_censored": full.get("left_censored"),
            "already_booming": full.get("already_booming"),
            "growth_at_first_testable": full.get("growth_at_first_testable"),
            "low_count_unreliable": full.get("low_count_unreliable"),
            "yoy_visible_at_cutoff_pct": yoy_at(s[0], s[1], seen_m) if s else None,
            "freshest_month_published_at_cutoff": seen_m,
            "onset_recomputed_on_data_available_at_cutoff": tr.get("onset"),
            "causal_check_agrees": agree,
            "first_testable": full.get("first_testable"),
            "note": full.get("note"),
        })
    fired = [r["tier"] for r in rows if r["flagged_by_cutoff"]]
    booming = [r["tier"] for r in rows if r["already_booming"]]
    if fired:
        verdict = ("YES - %d of 4 tiers had fired AND were knowable by %s: %s"
                   % (len(fired), cutoff, ", ".join(fired)))
    elif booming:
        verdict = ("NOT AS AN ONSET ALERT. No tier raised a NEW-boom flag by %s - but %s "
                   "had been booming since before the data window opens, so there was no "
                   "onset left inside the window to detect. The niche was visible and "
                   "large; the detector simply had nothing to date. Read the 'YoY visible "
                   "at the cutoff' column: that is what would have been on the screen."
                   % (cutoff, "/".join(booming)))
    else:
        verdict = "NO - not one tier had fired and become knowable by %s" % cutoff
    return {"niche": key, "label": n["label"], "cutoff": cutoff, "tiers": rows,
            "tiers_flagged_by_cutoff": fired,
            "tiers_already_booming": booming,
            "n_flagged": len(fired),
            "verdict": verdict,
            "hindsight_leaks": mismatches}


# =============================================================================
#  7. ANALYSIS
# =============================================================================
def analyse(res, drop=(), null=None):
    pos = [n for n in POSITIVES if n["key"] not in drop]
    grv = [n for n in GRAVEYARDS if n["key"] not in drop]
    out = {"excluded": list(drop)}

    gaps = {}
    for a, b in PAIRS:
        detail = []
        for n in pos:
            ta, tb = res[n["key"]]["tiers"][a], res[n["key"]]["tiers"][b]
            if ta.get("onset") and tb.get("onset"):
                detail.append({"niche": n["key"], "from": ta["onset"], "to": tb["onset"],
                               "gap_months": m_diff(ta["onset"], tb["onset"]),
                               "unreliable": bool(ta.get("low_count_unreliable")
                                                  or tb.get("low_count_unreliable")
                                                  or ta.get("left_censored")
                                                  or tb.get("left_censored"))})
        v = [d["gap_months"] for d in detail]
        ok = sum(1 for x in v if x > 0)
        g = {"n": len(v), "detail": detail,
             "median_gap_months": statistics.median(v) if v else None,
             "range": [min(v), max(v)] if v else None,
             "median_95ci": median_ci(v),
             "n_in_predicted_order": ok,
             "sign_test_p_naive_vs_coinflip": round(binom_tail(ok, len(v)), 4) if v else None,
             "power": power_note(len(v), hyps=len(PAIRS)) if v else None,
             "adjacent": (a, b) in ADJACENT}

        # SCORE AGAINST THE CALIBRATED NULL, NOT AGAINST ZERO AND NOT AGAINST A COIN FLIP.
        nb = ((null or {}).get("pairs") or {}).get("%s->%s" % (a, b))
        g["null_median_gap_months"] = nb["median_gap_months"] if nb else None
        g["null_p90"] = nb["p90"] if nb else None
        g["null_order_rate"] = None
        if nb and g["median_gap_months"] is not None:
            g["excess_over_null_months"] = g["median_gap_months"] - nb["median_gap_months"]
            g["beats_null"] = bool(g["median_gap_months"] > nb["p90"])
            p0 = min(max(nb["pct_in_predicted_order"] / 100.0, 0.5), 0.99)
            g["null_order_rate"] = round(p0, 3)
            g["sign_test_p_calibrated"] = round(binom_tail(ok, len(v), p0), 4) if v else None
        else:
            g["excess_over_null_months"] = None
            g["beats_null"] = None
            g["sign_test_p_calibrated"] = None
        gaps["%s->%s" % (a, b)] = g
    out["lead_times"] = gaps

    tiers = {}
    for t in TIERS:
        def by(group, *states):
            return [n["key"] for n in group if res[n["key"]]["tiers"][t]["state"] in states]

        # ALREADY_BOOMING is an ABSTENTION on BOTH sides. On the positives, because a boom
        # that predates the data cannot be dated (crediting it as a "hit" would be
        # rewarding the radar for seeing something it could not have seen starting). On the
        # graveyard, because a dud that was already inflating before the window opened and
        # was never re-detected is not a niche the tier REJECTED - it is one the tier could
        # not date either. Counting it as a true negative would be exactly the laundering
        # this file exists to prevent.
        ABSTAIN = ("OUT_OF_SCOPE", "BELOW_FLOOR", "NO_DATA", "ALREADY_BOOMING")
        tp, fn = by(pos, "FIRED"), by(pos, "NO_ONSET")
        p_abs = by(pos, *ABSTAIN)
        fp, tn = by(grv, "FIRED"), by(grv, "NO_ONSET")
        g_abs = by(grv, *ABSTAIN)
        npos, nneg = len(tp) + len(fn), len(fp) + len(tn)

        amp = perm_test([res[n["key"]]["tiers"][t].get("peak_z") for n in pos
                         if res[n["key"]]["tiers"][t].get("peak_z") is not None],
                        [res[n["key"]]["tiers"][t].get("peak_z") for n in grv
                         if res[n["key"]]["tiers"][t].get("peak_z") is not None])

        tiers[t] = {
            "name": TIER_NAME[t],
            "hits": tp, "misses": fn, "false_positives": fp, "true_negatives": tn,
            "positives_abstained": p_abs, "graveyard_abstained": g_abs,
            "hit_rate": round(len(tp) / npos, 2) if npos else None,
            "informative_positives": npos, "informative_negatives": nneg,
            # HONEST: abstentions are OUT of the denominator. If nneg is 0 the rate does
            # not exist and must be printed as n/a, never as 0.00.
            "fp_rate_honest": round(len(fp) / nneg, 2) if nneg else None,
            # CREDULOUS: every abstention counted as a correct rejection. Shown ONLY so the
            # size of that lie is visible next to the honest number.
            "fp_rate_credulous": round(len(fp) / len(grv), 2) if grv else None,
            "discrimination_fisher_p": fisher_1t(len(tp), len(fn), len(fp), len(tn)),
            "amplitude_test_peak_z": amp,
            "left_censored": [n["key"] for n in pos + grv
                              if res[n["key"]]["tiers"][t].get("left_censored")],
            "already_booming": [n["key"] for n in pos + grv
                                if res[n["key"]]["tiers"][t]["state"] == "ALREADY_BOOMING"],
            "specificity_measurable": bool(nneg),
            "abstention_warning": (
                "This tier's specificity rests on %d of %d graveyard niches; %d ABSTAINED. "
                "%s" % (nneg, len(grv), len(g_abs),
                        "WITH ZERO INFORMATIVE NEGATIVES ITS FALSE-POSITIVE RATE DOES NOT "
                        "EXIST. It has not been shown to discriminate; it has not been "
                        "TESTED." if not nneg else
                        "If most of the graveyard is invisible to a tier, its apparent "
                        "specificity is an artefact of scope, not evidence.")) if g_abs
            else None,
        }
    out["tiers"] = tiers

    out["disconfirming"] = [
        {"niche": n["key"], "label": n["label"], "tier": t,
         "onset": res[n["key"]]["tiers"][t]["onset"],
         "knowable_by": res[n["key"]]["tiers"][t].get("knowable_by"),
         "peak_z": res[n["key"]]["tiers"][t].get("peak_z"),
         "growth_at_onset": res[n["key"]]["tiers"][t].get("growth_at_onset")}
        for n in grv for t in TIERS if res[n["key"]]["tiers"][t]["state"] == "FIRED"]
    out["low_count_onsets"] = [
        {"niche": k, "tier": t, "onset": v["onset"], "baseline": v.get("baseline_at_onset")}
        for k, r in res.items() for t, v in r["tiers"].items()
        if v.get("low_count_unreliable")]
    out["left_censored_onsets"] = [
        {"niche": k, "tier": t, "onset": v["onset"], "first_testable": v.get("first_testable")}
        for k, r in res.items() for t, v in r["tiers"].items() if v.get("left_censored")]
    out["already_booming"] = [
        {"niche": k, "class": r["class"], "tier": t,
         "first_testable": v.get("first_testable"),
         "growth_at_first_testable": v.get("growth_at_first_testable")}
        for k, r in res.items() for t, v in r["tiers"].items()
        if v["state"] == "ALREADY_BOOMING"]
    out["estimator_disagreements"] = [
        {"niche": k, "tier": t, "robust": v.get("onset"), "spec": v.get("spec_onset"),
         "spec_blind_months": v.get("spec_undefined_months")}
        for k, r in res.items() for t, v in r["tiers"].items()
        if v["state"] in ("FIRED", "NO_ONSET") and not v.get("agrees_with_spec", True)]
    return out


# =============================================================================
#  8. REPORT
# =============================================================================
def cell(tt):
    s = tt["state"]
    if s == "FIRED":
        f = ""
        if tt.get("low_count_unreliable"):
            f += " (!)"
        if tt.get("left_censored"):
            f += " (<)"
        return "**%s**%s" % (tt["onset"], f)
    return {"NO_ONSET": "no onset",
            "ALREADY_BOOMING": "_abstains: already booming_",
            "OUT_OF_SCOPE": "_abstains: out of scope_",
            "BELOW_FLOOR": "_abstains: below floor_", "NO_DATA": "_no data_"}.get(s, s)


def write_md(p):
    res, a, nb = p["niches"], p["analysis"], p["null_calibration"]
    L = []
    A = L.append
    A("# Backtest 3: four tiers, twelve years, and the ADHD question\n")
    A("Generated %s. **T4 is in this study**, back to Jan-2014, via NHSBSA's own English "
      "Prescribing Dataset. The 'we cannot backtest T4' excuse is retired.\n"
      % p["generated"][:10])
    for _ln in _completeness_lines(p.get("completeness")):
        A(_ln)

    # ---------------------------------------------------------------- 0
    A("\n## 0. Read this before any number below\n")
    A("**This study cannot establish that the tiers work.** n = %d positives and %d "
      "graveyard niches. Six tier-pairs are tested, so a Bonferroni-corrected alpha is "
      "0.0083; a *flawless* 8/8 sweep scores p = 0.0039 against a coin flip. One niche out "
      "of order and it fails. And the coin-flip null is itself wrong (section 3a). The only "
      "thing an n of 16 can do is **falsify**. If the graveyard fires as loudly as the "
      "positives, that kills the early tiers, and that is a real result. If it does not, "
      "that is *not* proof the tiers work - it is a failure to disprove them at n=16.\n"
      % (len(POSITIVES), len(GRAVEYARDS)))
    A("**T4's false-positive rate does not exist.** All 8 graveyard niches abstain on T4 - "
      "none of CBD, IV drips, cryotherapy, ice baths, psilocybin, NAD+, hyperbaric oxygen "
      "or red-light therapy is an NHS-prescribed medicine. Zero informative negatives means "
      "no rate. Section 4 prints `n/a`, not `0.00`. Anyone who reports 0.00 for T4 is "
      "laundering an abstention into a correct rejection.\n")
    A("**T4 also abstains on 4 of the 8 positives** (private GP, autism, hair transplant, "
      "IVF) for reasons `drugs.py` had already verified and written down. T4's lead/lag "
      "numbers therefore rest on **n=4**: ADHD, GLP-1, menopause/HRT, TRT.\n")
    A("**Abstentions are not rejections.** A tier that legally or structurally cannot see a "
      "niche has abstained. Counting abstentions as correct rejections drives the "
      "false-positive rate to zero for free. Both the honest and the credulous rate are "
      "printed in section 4; the gap between them is the size of the lie you would "
      "otherwise have told.\n")
    A("**The niches are not independent.** ADHD and autism assessment share operators. "
      "Section 4 is re-run without autism, and without NAD+ (which has not resolved).\n")
    if not p["diag"].get("cqc_survivorship_corrected"):
        A("- **T3 IS NOT SURVIVORSHIP-CORRECTED in this run.** %s\n"
          % p["diag"].get("cqc_WARNING", ""))
    if p["diag"].get("t4_unread_warning"):
        A("- **T4 canary:** %s\n" % p["diag"]["t4_unread_warning"])
    if p["diag"].get("t2_hit_budget_cap"):
        A("- **T2 hit the call budget cap.** Coverage %s. Re-run to resume.\n"
          % p["diag"].get("t2_coverage"))

    # ---------------------------------------------------------------- 1 HEADLINE
    st = p["standing"]
    A("\n## 1. THE BENCHMARK: standing in %s, would this radar have flagged ADHD?\n"
      % st["cutoff"])
    A("The owner's test: *\"I wanted to catch the ADHD boom 2 years ago.\"* So: freeze the "
      "clock at **%s**, allow the radar only the data that had actually been published by "
      "then, and ask each tier.\n" % st["cutoff"])
    A("`knowable by` = the onset month **+ 3** (onset_robust will not confirm a boom until "
      "z stays elevated for 3 further months) **+ the source's own publication lag** (T4 is "
      "~3 months in arrears; NHSBSA publishes January in March). A boom you can only date "
      "with hindsight is not an early warning.\n")
    A("\n| Tier | | Onset | Knowable by | Flagged by %s? | YoY growth visible on the screen "
      "at %s | Notes |" % (st["cutoff"], st["cutoff"]))
    A("|---|---|---|---|---|---|---|")
    for r in st["tiers"]:
        notes = []
        if r["state"] != "FIRED":
            notes.append(r["state"])
        if r["already_booming"]:
            notes.append("**the boom PREDATES the data window** - it was already growing "
                         "%sx a year on %s, the first month the estimator could look. "
                         "There is no onset inside the window to find. This is an "
                         "ABSTENTION, not a rejection."
                         % (r["growth_at_first_testable"], r["first_testable"]))
        if r["left_censored"]:
            notes.append("LEFT-CENSORED: fired in the first months it was allowed to "
                         "(earliest possible %s) - the onset is a LOWER BOUND, not a date"
                         % (r["first_testable"] or "?"))
        if r["low_count_unreliable"]:
            notes.append("series too thin for the date to be trusted")
        if r["causal_check_agrees"] is False:
            notes.append("**HINDSIGHT LEAK** - recomputing on data available at the cutoff "
                         "gives %s" % r["onset_recomputed_on_data_available_at_cutoff"])
        A("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["tier"], r["name"], r["onset"] or "-", r["knowable_by"] or "-",
            "**YES**" if r["flagged_by_cutoff"] else "no",
            ("%+.0f%%" % r["yoy_visible_at_cutoff_pct"])
            if r["yoy_visible_at_cutoff_pct"] is not None else "-",
            "; ".join(notes) or "-"))
    A("\n### Verdict: %s\n" % st["verdict"])
    A("\nThe last two columns are the honest complication and they must be read together. "
      "The **onset detector** answers 'is a NEW boom starting?'. It is deliberately blind "
      "to a niche that has been compounding at the same rate for years - that is what stops "
      "it screaming at everything large. The **YoY column** is what would actually have "
      "been on the dashboard. A tier can be silent and the niche can still be visibly, "
      "enormously growing. Neither number alone answers the owner's question; both "
      "together do.\n")
    if st["hindsight_leaks"]:
        A("**WARNING - the estimator is not behaving causally on this data.** %s. Every "
          "onset in this report is then suspect and none of the lead times can be "
          "quoted.\n" % st["hindsight_leaks"])
    A("\nThe same table for every positive niche is in `backtest3.json` under "
      "`standing_all`. Section 2 gives the raw onsets.\n")

    # ---------------------------------------------------------------- 2 ONSETS
    A("\n## 2. Onsets\n")
    A("| Niche | Class | T1 intent | T2 entry | T3 capacity | T4 prescribing |")
    A("|---|---|---|---|---|---|")
    for n in NICHES:
        r = res[n["key"]]
        A("| %s | %s | %s |" % (r["label"], r["class"],
                                " | ".join(cell(r["tiers"][t]) for t in TIERS)))
    A("\n`(!)` the series was too thin at onset (< %d events/yr) for the DATE to be "
      "trustworthy - that it fired is meaningful, the month is not.  \n"
      "`(<)` **left-censored**: it fired in the first months it was allowed to, so the "
      "boom was probably already running before the data starts. The onset is a lower "
      "bound.\n" % LOW_COUNT)
    lc = a["left_censored_onsets"]
    if lc:
        A("\n**Left-censored onsets (%d).** These are not dates and must not be differenced "
          "to produce lead times:\n" % len(lc))
        for d in lc:
            A("- `%s` %s: fired %s, but the first month the estimator could fire at all was "
              "%s.\n" % (d["tier"], d["niche"], d["onset"], d["first_testable"]))

    ab = a["already_booming"]
    A("\n### 2a. 'Already booming' - the state that would otherwise have been read as a "
      "correct rejection\n")
    A("`onset_robust` does not detect growth. It detects **acceleration** - a break from a "
      "niche's own recent growth regime. Feed it a series compounding at a steady +3% a "
      "month from its very first observation and **it never fires at all**, because its "
      "z-scale is the median and MAD of that niche's own recent z-history, and a smooth "
      "exponential has a flat z-history. That is a feature: it is what stops the detector "
      "screaming at every niche that is merely large.\n")
    A("\nBut it has a consequence that had not been written down anywhere, and it lands "
      "squarely on the benchmark case. **A niche that was already in a sustained boom "
      "before the data window opened reports NO ONSET - which in a results table is "
      "indistinguishable from the estimator having correctly REJECTED it.** T4's history "
      "starts in Jan-2014, and lisdexamfetamine was already at 737 items/month and climbing "
      "hard. Score a T4 silence on ADHD as 'T4 did not flag ADHD' and you have reported the "
      "exact opposite of the truth.\n")
    if ab:
        A("\nSo these are quarantined as ABSTENTIONS, on the positives and the graveyard "
          "alike:\n")
        A("\n| Niche | Class | Tier | First month the estimator could look | Growth ALREADY "
          "running by then |")
        A("|---|---|---|---|---|")
        for d in ab:
            A("| %s | %s | %s | %s | **%sx** |" % (d["niche"], d["class"], d["tier"],
                                                   d["first_testable"],
                                                   d["growth_at_first_testable"]))
        A("\nAn abstention here is not the tier failing to see the niche. The tier can see "
          "it perfectly well and it is enormous. The tier simply cannot **date** it, and "
          "dating it is the only thing this study measures.\n")
    else:
        A("\nNo niche/tier combination came out ALREADY_BOOMING in this run.\n")

    # ---------------------------------------------------------------- 3 LEADS
    A("\n## 3. Lead times (positives only), scored against the null\n")
    A("A **positive** gap means the earlier tier fired first - the radar's claim. Adjacent "
      "pairs are the actual claim (T1->T2->T3->T4); the rest are shown because if T4 fires "
      "FIRST that is a fact about the tier model, not a bug.\n")
    A("\n| Pair | n | Median gap | Range | 95% CI | In order | **Null gap (true lead=0)** | "
      "Null p90 | **Beats the null?** |")
    A("|---|---|---|---|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        ci = g["median_95ci"]
        n0 = (nb["pairs"] or {}).get(pair)
        A("| %s%s | %d | %s | %s | %s | %d/%d | %s | %s | %s |" % (
            pair, " *(adjacent)*" if g["adjacent"] else "", g["n"],
            g["median_gap_months"] if g["n"] else "-",
            ("%d to %d" % tuple(g["range"])) if g["range"] else "-",
            ("%d to %d" % (ci[0], ci[1])) if ci else "**none exists at this n**",
            g["n_in_predicted_order"], g["n"],
            ("+%s" % n0["median_gap_months"]) if n0 else "-",
            ("+%s" % n0["p90"]) if n0 else "-",
            "**YES**" if g.get("beats_null") else ("no" if g.get("beats_null") is False
                                                   else "-")))

    A("\n### 3a. The null, and why the sign test in every previous version was wrong\n")
    A("`calibrate_null()` simulates %d niches whose **four tiers all boom in the same "
      "calendar month** - a true lead of exactly **zero** - and pushes them through the "
      "real axes, the real level floors and the real estimator. Whatever comes out is "
      "manufactured entirely by the measurement.\n" % nb["reps"])
    A("\nThree things manufacture it, and the second is the big one:\n")
    A("1. **Thin series cross a threshold later than smooth ones.** T1 is a smooth 0-100 "
      "index; T3 is ~3 clinics a month.\n")
    A("2. **The tiers' histories start in different years, and the estimator needs ~54 "
      "months of warm-up before it can fire at all.** T2 starts in 2010 and can fire from "
      "~2014-07. T3 and T4 start in 2014 and *cannot fire before ~2018-07*, however loud "
      "the boom is. A 2018 boom therefore shows a ~6-month 'T2 leads T3' that is nothing "
      "but the start date of a spreadsheet. **backtest2.py's docstring missed this and "
      "attributed the whole artefact to thinness.**\n")
    A("3. **The level floors differ per tier** (T1 120, T2 12, T3 6, T4 500 per 12 months), "
      "so tiers become able to fire at different points in a niche's growth.\n")
    A("\n| Pair | Null median gap | Null p90 | Null: %% landing 'in the predicted order' | "
      "Measured | Excess over null |")
    A("|---|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        n0 = (nb["pairs"] or {}).get(pair)
        if not n0:
            A("| %s | - | - | - | - | - |" % pair)
            continue
        A("| %s | **+%s** | +%s | **%.0f%%** | %s | %s |" % (
            pair, n0["median_gap_months"], n0["p90"], n0["pct_in_predicted_order"],
            g["median_gap_months"] if g["n"] else "-",
            ("%+d" % g["excess_over_null_months"])
            if g.get("excess_over_null_months") is not None else "-"))
    A("\n**Look at the 'in the predicted order' column.** Under a *zero* true lead this "
      "pipeline still puts the tiers in the radar's predicted order most of the time. So "
      "the classic sign test - 'each niche is a coin flip, p=0.5' - is testing against a "
      "null that is simply false, and it is false in the direction that flatters the "
      "thesis. A perfect 8/8 sweep would score p=0.0039 against a coin flip and look like a "
      "discovery when **8/8 is the expected result of no effect at all**.\n")
    A("\n| Pair | In order | Naive p (vs coin flip) - **WRONG** | Calibrated null | "
      "**Calibrated p - USE THIS** |")
    A("|---|---|---|---|---|")
    for pair, g in a["lead_times"].items():
        if not g["n"]:
            continue
        A("| %s | %d/%d | %s | %s%% | **%s** |" % (
            pair, g["n_in_predicted_order"], g["n"],
            g.get("sign_test_p_naive_vs_coinflip"),
            int(100 * (g.get("null_order_rate") or 0.5)),
            g.get("sign_test_p_calibrated")))
    A("\nNull fire rates (share of zero-lead simulations in which each tier fired at all): "
      "`%s`. Null left-censoring rates: `%s`.\n"
      % (json.dumps(nb["tier_fire_rate"]), json.dumps(nb["tier_left_censored_rate"])))
    A("\nThe null was calibrated to **%s**.\n" % p["null_shapes_source"])

    # ---------------------------------------------------------------- 4 GRAVEYARD
    A("\n## 4. THE POINT OF THE WHOLE FILE: does the graveyard fire too?\n")
    A("| Tier | Hit rate (positives) | FP rate - **HONEST** | FP rate - credulous | "
      "Fisher p (does it discriminate?) | Graveyard abstained |")
    A("|---|---|---|---|---|---|")
    for t in TIERS:
        s = a["tiers"][t]
        fph = ("**%s** (%d informative)" % (s["fp_rate_honest"], s["informative_negatives"])
               if s["specificity_measurable"] else "**n/a - NO INFORMATIVE NEGATIVES**")
        A("| %s %s | %s (%d informative) | %s | %s | %s | %d of %d |"
          % (t, TIER_NAME[t], s["hit_rate"], s["informative_positives"], fph,
             s["fp_rate_credulous"], s["discrimination_fisher_p"],
             len(s["graveyard_abstained"]), len(GRAVEYARDS)))
    A("\n**Read the Fisher column, not the hit rate.** A tier that fires on 8/8 booms and "
      "6/6 duds has a perfect hit rate and zero information. Fisher asks the only question "
      "that matters: does this tier fire on real booms *more often* than on duds? A p near "
      "1.0 means no. A merely non-significant p at n=16 means **this study could not tell** "
      "- which is not the same as 'it works'.\n")
    for t in TIERS:
        if a["tiers"][t].get("abstention_warning"):
            A("- **%s**: %s\n" % (t, a["tiers"][t]["abstention_warning"]))

    A("\n### 4a. Do the early tiers fire as LOUDLY for the duds?\n")
    A("Hit/miss is binary and throws away the amplitude. The live radar *ranks* niches by "
      "signal strength, so if the graveyard's `peak_z` is the same size as the positives', "
      "the ranking carries no information even if the firing does.\n")
    A("\n| Tier | Median peak z, positives | Median peak z, graveyard | Difference | "
      "Exact permutation p |")
    A("|---|---|---|---|---|")
    for t in TIERS:
        m = a["tiers"][t].get("amplitude_test_peak_z")
        if not m:
            A("| %s | - | - | - | not computable (too few niches fired) |" % t)
            continue
        A("| %s | %s | %s | %s | %s |" % (t, m["median_positive"], m["median_graveyard"],
                                          m["observed_diff"], m["p_one_sided"]))

    A("\n### 4b. The disconfirming cases\n")
    if a["disconfirming"]:
        A("Graveyard niches that FIRED. Each is a false positive the live radar would have "
          "handed you as a lead, with the month it would have handed it to you.\n")
        A("\n| Niche | Tier | Onset | Knowable by | peak z | Growth at onset |")
        A("|---|---|---|---|---|---|")
        for d in a["disconfirming"]:
            A("| %s | %s | %s | %s | %s | %s |" % (d["label"], d["tier"], d["onset"],
                                                   d.get("knowable_by") or "-",
                                                   d["peak_z"], d["growth_at_onset"]))
        cbd = [d for d in a["disconfirming"] if d["niche"] == "cbd"]
        if cbd:
            A("\n**CBD fired on %s.** That was the case flagged in advance as the one most "
              "likely to sink the early tiers, and it did. Roughly 500 UK CBD companies "
              "were incorporated behind the FSA novel-foods list and a large share have "
              "since dissolved. A tier that fired on CBD as loudly as on ADHD is a **lead "
              "generator, not a signal** - it tells you where attention is, not where a "
              "business is.\n" % ", ".join(sorted(d["tier"] for d in cbd)))
    else:
        A("**NONE.** No graveyard niche fired on any tier. **Before celebrating, read the "
          "abstention column above.** If the graveyard mostly abstained, this says nothing "
          "at all - the tiers were not tested, they were excused.\n")

    # ---------------------------------------------------------------- 5 T4
    A("\n## 5. T4 in detail - what it can and cannot see\n")
    A("Source: NHSBSA Open Data Portal, English Prescribing Dataset, %s to %s. No API key. "
      "One request per month, cached forever (a published month is immutable).\n"
      % (T4_START, p["windows"]["T4"][1]))
    A("\n**The schema trap.** NHSBSA renamed `bnf_chemical_substance` from a CODE to a NAME "
      "in July 2025. Querying the new table with the old column returns `null`, not an "
      "error - and a careless module turns that null into a zero and reports that ADHD "
      "prescribing collapsed. Every month here is validated against a canary chemical "
      "(sertraline). A month that fails is **dropped, never zeroed**. Months rejected this "
      "run: %s.\n" % p["diag"].get("t4_months_unread_n", "?"))
    A("\n**What EPD structurally cannot see:** private prescriptions (so private TRT, "
      "private weight-loss jabs and private ADHD scripts are invisible), Scotland, Wales "
      "and Northern Ireland, secondary/hospital-issued drugs (so IVF), dental prescribing, "
      "and anything supplied under a Patient Group Direction.\n")
    A("\n| Niche | T4 | Why |")
    A("|---|---|---|")
    for n in NICHES:
        A("| %s | %s | %s |" % (n["label"], "**IN SCOPE**" if n["t4_scope"] else "abstains",
                                n["t4_why"]))
    dg = p.get("t4_unscored_diagnostic") or {}
    if dg:
        A("\n**Unscored diagnostics.** The two thin proxies are computed but not allowed to "
          "vote, because the proxy does not measure the niche. Published so nothing is "
          "hidden:\n")
        for k, v in sorted(dg.items()):
            A("- `%s` (%s): onset %s, state %s.\n"
              % (k, ", ".join(v["codes"]), v.get("onset") or "none", v.get("state")))

    # ---------------------------------------------------------------- 6 T3
    A("\n## 6. The CQC survivorship correction, measured\n")
    A("The CQC active-locations file contains only clinics **still open**. Used alone it "
      "understates every historical month, invents an upward trend in every niche, and "
      "biases every T3 onset LATE - which inflates the T2->T3 lead, the single number a "
      "buyer would act on. CQC publishes a deactivated-locations file on the same page; "
      "both are merged here, and re-registrations are de-duplicated on (name, postcode) "
      "keeping the earliest date, because a clinic enters the market once.\n")
    A("\n| Niche | Active | Recovered from the deactivated file | Understated by | "
      "Onset: active-only | Onset: corrected | Onset moved |")
    A("|---|---|---|---|---|---|---|")
    for n in NICHES:
        sv = res[n["key"]].get("t3_survivorship")
        if not sv or not sv.get("n_active"):
            continue
        mv = m_diff(sv["onset_corrected"], sv["onset_active_only"])
        A("| %s | %d | %d | %s%% | %s | %s | %s |" % (
            n["label"], sv["n_active"], sv["n_recovered"], sv["understatement_pct"],
            sv["onset_active_only"] or "-", sv["onset_corrected"] or "-",
            ("%+d months" % mv) if mv is not None else "-"))
    A("\nEvery number in the last column should be >= 0: a missing clinic is always in the "
      "past, so an active-only file can only ever tell you a boom started **later** than it "
      "did. **If that column is materially non-zero, no T3 result computed from an "
      "active-only file - including whatever the live radar shows today - is safe to "
      "quote.**\n")

    # ---------------------------------------------------------------- 7 T2
    A("\n## 7. Robustness of the T2 construction\n")
    A(bt2.T2_SUMMING_NOTE + "\n")
    dis = p.get("t2_primary_only_disagreements") or []
    if dis:
        A("\n**T2 onsets that change when the series is rebuilt from the primary keyword "
          "alone** (which cannot double-count by construction):\n")
        A("\n| Niche | All keywords | Primary keyword only |")
        A("|---|---|---|")
        for d in dis:
            A("| %s | %s | %s |" % (d["niche"], d["all"] or "no onset",
                                    d["primary"] or "no onset"))
        A("\nWhere these differ, the T2 onset is partly an artefact of keyword choice.\n")
    else:
        A("\nNo niche's T2 onset changes under the primary-keyword-only rebuild. "
          "Double-counting is not driving the dates.\n")

    pr = p.get("t2_precision") or {}
    dirty = {k: v for k, v in pr.items()
             if isinstance(v, dict) and v.get("precision") is not None
             and v["precision"] < 0.8}
    A("\n### 7a. Keyword precision probe\n")
    A("The Companies House `hits`-count trick returns no company names, so we cannot "
      "re-filter what CH decided `company_name_includes` meant. One extra call per keyword "
      "pulls 100 names and re-applies a strict word-boundary matcher. Not a random sample, "
      "so this is a smell test, not an estimate.\n")
    if dirty:
        A("\n| Keyword | Precision on 100 sampled names | Examples wrongly matched |")
        A("|---|---|---|")
        for k, v in sorted(dirty.items()):
            A("| `%s` | **%.0f%%** | %s |" % (k, 100 * v["precision"],
                                              ", ".join(v.get("examples_rejected") or [])))
        A("\n**These keywords are contaminated**, their niches' T2 counts are inflated by "
          "unrelated companies, and those T2 onsets should be discounted. `cbd` and `nad` "
          "are 3-letter tokens and are the obvious risks.\n")
    elif pr:
        A("\nAll keywords scored >= 80% precision on the sampled names.\n")
    else:
        A("\nProbe not run (no Companies House key, or a cache-only run).\n")

    # ---------------------------------------------------------------- 8 SENS
    A("\n## 8. Is the answer just the threshold I picked?\n")
    A("\n| Pair | growth >= 1.25x | growth >= 1.5x (shipped) | growth >= 2.0x |")
    A("|---|---|---|---|")
    for a2, b2 in ADJACENT:
        pair = "%s->%s" % (a2, b2)
        cells = []
        for gx in ("1.25", "1.5", "2.0"):
            g = p["sensitivity"][gx][pair]
            cells.append("median %s (n=%d, %d in order)"
                         % (g["median_gap_months"], g["n"], g["n_in_predicted_order"]))
        A("| %s | %s |" % (pair, " | ".join(cells)))
    A("\nIf the **sign** of a median gap flips across that row, the ordering is an artefact "
      "of the threshold, not a fact about the world, and must not be reported as a "
      "finding.\n")

    # ---------------------------------------------------------------- 9 SENS labels
    A("\n## 9. Sensitivity to two contested labels\n")
    A("\n| Scenario | %s |" % " | ".join("%s FP" % t for t in TIERS))
    A("|---|%s" % ("---|" * len(TIERS)))
    for name, alt in (("as shipped", a),
                      ("without NAD+ (unresolved - may not be a dud at all)",
                       p["analysis_no_nad"]),
                      ("without autism (not independent of ADHD)", p["analysis_no_autism"])):
        A("| %s | %s |" % (name, " | ".join(
            str(alt["tiers"][t]["fp_rate_honest"]) if alt["tiers"][t]["specificity_measurable"]
            else "n/a" for t in TIERS)))
    A("\nNAD+ is in the graveyard although it has **not resolved**. If it becomes a real "
      "boom, its false positives here are actually true positives. Quote the range, never "
      "the point.\n")

    # ---------------------------------------------------------------- 10
    A("\n## 10. Where the estimator choice changes the answer\n")
    if a["estimator_disagreements"]:
        A("\n| Niche | Tier | Robust (shipped) | The original brief's estimator | Months its "
          "YoY divides by zero |")
        A("|---|---|---|---|---|")
        for d in a["estimator_disagreements"]:
            A("| %s | %s | %s | %s | %s |" % (d["niche"], d["tier"], d["robust"] or "none",
                                              d["spec"] or "none", d["spec_blind_months"]))
    else:
        A("\nNone. The two estimators agree wherever both can see.\n")

    A("\n## 11. Why each graveyard niche is in the graveyard\n")
    for n in GRAVEYARDS:
        A("\n**%s** - %s\n" % (n["label"], n["why"]))
        for c in n.get("caveats", []):
            A("  - *Caveat:* %s\n" % c)

    A("\n## 12. Diagnostics\n")
    A("```\n%s\n```\n" % json.dumps(p["diag"], indent=1)[:4500])

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# =============================================================================
#  9. ASSEMBLE
# =============================================================================
def assemble(t1, t2, t3, t4, probes=None, cutoff="2022-03", null_reps=NULL_REPS,
             comp=None):
    series = build_series(t1, t2, t3, t4)
    res = evaluate(series)

    # T3 survivorship: recompute every T3 onset on the ACTIVE-ONLY file and diff the dates.
    m3 = axis(T3_START)
    for n in NICHES:
        c = t3.get(n["key"])
        if not c or not n["t3_scope"]:
            continue
        av, cv = c["active_only"], c["corrected"]
        oa = tier_state(n, "T3", m3, av) if sum(av) else {"onset": None}
        res[n["key"]]["t3_survivorship"] = {
            "n_active": c["n_active"], "n_recovered": c["n_recovered"],
            "understatement_pct": (round(100.0 * (sum(cv) - sum(av)) / sum(cv), 1)
                                   if sum(cv) else None),
            "dedup_collapsed": c.get("dedup_collapsed"),
            "onset_active_only": oa.get("onset"),
            "onset_corrected": res[n["key"]]["tiers"]["T3"].get("onset")}

    # T2 rebuilt from the primary keyword alone - cannot double-count by construction.
    prim = evaluate(build_series(t1, t2, t3, t4, primary_only=True))
    dis = [{"niche": n["key"], "all": res[n["key"]]["tiers"]["T2"].get("onset"),
            "primary": prim[n["key"]]["tiers"]["T2"].get("onset")}
           for n in NICHES
           if res[n["key"]]["tiers"]["T2"].get("onset")
           != prim[n["key"]]["tiers"]["T2"].get("onset")]

    # The thin T4 proxies: computed, published, NOT scored.
    unscored = {}
    for k, codes in T4_UNSCORED.items():
        m4, v4, cov = t4_series(BY_KEY[k], t4, codes=codes)
        if not v4:
            unscored[k] = {"codes": codes, "state": "NO_DATA", "coverage": round(cov, 2)}
            continue
        fake = dict(BY_KEY[k], t4_scope=True, t4_why="")
        st = tier_state(fake, "T4", m4, v4)
        unscored[k] = {"codes": codes, "state": st["state"], "onset": st.get("onset"),
                       "peak_z": st.get("peak_z"), "coverage": round(cov, 2),
                       "why_not_scored": BY_KEY[k]["t4_why"]}

    # THE NULL. Calibrated to the levels and growth multiples actually observed here.
    print("\ncalibrating the null (synthetic, no network, %d reps)..." % null_reps)
    shapes = observed_shapes(series)
    src = "the levels and growth multiples OBSERVED in this run"
    if not any(t in shapes for t in TIERS):
        shapes, src = NULL_SHAPES, "the built-in default shapes (no series were available)"
    null = calibrate_null(shapes=shapes, reps=null_reps)

    main = analyse(res, null=null)

    sens = {}
    for gx in (1.25, 1.5, 2.0):
        sens["%s" % gx] = analyse(evaluate(series, growth_x=gx), null=null)["lead_times"]

    standing = standing_at(res, series, cutoff, key="adhd")
    standing_all = {n["key"]: standing_at(res, series, cutoff, key=n["key"])
                    for n in POSITIVES}

    t4_end = max([m for m in t4] or [T4_START])
    p = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(),
         "cutoff": cutoff,
         "windows": {"T1": [T1_START, END], "T2": [T2_START, END],
                     "T3": [T3_START, END], "T4": [T4_START, t4_end]},
         "n": {"positives": len(POSITIVES), "graveyard": len(GRAVEYARDS),
               "t4_informative_positives": sum(1 for n in POSITIVES if n["t4_scope"]),
               "t4_informative_negatives": sum(1 for n in GRAVEYARDS if n["t4_scope"])},
         "estimator": "backtest_core.onset_robust (21 synthetic fixtures, unchanged)",
         "pub_lag_months": PUB_LAG,
         "persistence_months": SUSTAIN_MONTHS,
         "hsca_waves_excluded": bt2.HSCA_WAVES,
         "t2_summing_note": bt2.T2_SUMMING_NOTE,
         "t2_precision": probes or {},
         "t2_primary_only_disagreements": dis,
         "t4_scope": {k: {"in_scope": v[0], "why": v[1]} for k, v in T4_SCOPE.items()},
         "t4_unscored_diagnostic": unscored,
         "null_calibration": null,
         "null_shapes_source": src,
         "standing": standing,
         "standing_all": standing_all,
         "completeness": comp,
         "diag": dict(DIAG),
         "niches": res,
         "analysis": main,
         "analysis_no_nad": analyse(res, drop=("nad",), null=null),
         "analysis_no_autism": analyse(res, drop=("autism",), null=null),
         "sensitivity": sens}
    save(OUT_JSON, p)
    write_md(p)
    return p


def _crash_md(exc):
    """FAIL LOUDLY, NEVER SILENTLY. If the run dies, backtest3.md must still exist and
    say how far it got - a six-hour job that leaves nothing behind is the exact failure
    mode this revision exists to kill."""
    L = ["# Backtest 3: RUN CRASHED\n",
         "Generated %s. The run raised before a report could be assembled. This file "
         "exists so the failure is visible in the repo, not just in a CI log that "
         "expires.\n" % dt.datetime.now(dt.timezone.utc).isoformat()[:19],
         "\n## What happened\n```\n",
         "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:],
         "```\n",
         "\n## How far the fetchers got (DIAG)\n```json\n",
         json.dumps(dict(DIAG), indent=1, default=str)[:6000],
         "\n```\n",
         "\nEvery fetched cell is cached under `data/`. A re-run RESUMES from the "
         "committed caches; it does not start over.\n"]
    try:
        with open(OUT_MD, "w", encoding="utf-8") as f:
            f.write("".join(L))
        print("CRASH - wrote %s" % OUT_MD, file=sys.stderr)
    except Exception:
        pass


def build(args):
    # Whatever happens, backtest3.md exists afterwards: either the report or a crash
    # note saying how far the run got. A clean SystemExit(0) passes through untouched.
    try:
        return _build(args)
    except BaseException as e:
        if isinstance(e, SystemExit) and e.code in (0, None):
            raise
        _crash_md(e)
        raise


def _build(args):
    _repoint_caches()
    t0 = time.monotonic()
    errs = _validate_codes()
    if errs:
        print("FATAL - the BNF codes did not validate against drugs.py:")
        for e in errs:
            print("  " + e)
        return 2

    deadline = None
    if getattr(args, "minutes", 0):
        deadline = t0 + args.minutes * 60.0 - _RESERVE_S
        print("WALL-CLOCK BUDGET %.0f min: fetchers get %.0f min, the last %.0f min "
              "are reserved for the null calibration and the report. When the budget "
              "is spent the run SAVES, writes a clearly-labelled PARTIAL report and "
              "exits 0; the next run resumes from the committed caches.\n"
              % (args.minutes, max(0.0, (deadline - t0) / 60.0), _RESERVE_S / 60.0))

    print("Backtest3   T1 %s.. | T2 %s.. | T3 %s.. | T4 %s..  -> %s\n"
          % (T1_START, T2_START, T3_START, T4_START, END))
    print("T4 NHSBSA English Prescribing Dataset (monthly, no key)")
    t4 = fetch_t4(max_calls=args.max_epd_calls, force=args.refresh, deadline=deadline)
    print("  %s" % DIAG.get("t4"))
    print("\nT2 Companies House (monthly hit-counts, parallel + resumable)")
    t2, probes = fetch_t2_parallel(args.max_calls, force=args.refresh,
                                   deadline=deadline, workers=args.t2_workers)
    print("  %s" % DIAG.get("t2"))
    print("\nT3 CQC (active + deactivated, survivorship-corrected)")
    t3 = bt2.fetch_t3(force=args.refresh)
    print("\nT1 Google Trends (opt-in)")
    t1 = bt2.fetch_t1(args.trends, force=args.refresh)
    print("  %s" % DIAG.get("t1"))

    # A keyword fetched for only SOME months would poison t2_series: months where one
    # of a niche's keywords is missing sum to an undercount that reads as a dip, and
    # the recovery reads as a boom. So a keyword is either >=90%-fetched or it is
    # withheld from THIS RUN's analysis entirely - it stays in the cache and completes
    # next run. Withheld, never zero-filled.
    months2 = axis(T2_START)
    floor2 = 0.9 * len(months2)
    partial_kws = sorted(
        k for k, v in t2.items()
        if 0 < sum(1 for m in months2 if v.get(m) is not None) < floor2)
    t2_use = {k: v for k, v in t2.items() if k not in set(partial_kws)}
    if partial_kws:
        print("\n  T2: WITHHOLDING %d partially-fetched keyword(s) from this run's "
              "analysis (<90%% of months; they resume next run): %s"
              % (len(partial_kws), ", ".join(partial_kws)))

    comp = _completeness(t2, t4)
    p = assemble(t1, t2_use, t3, t4, probes, cutoff=args.cutoff,
                 null_reps=args.null_reps, comp=comp)
    save(PROGRESS, {"complete": comp["complete"],
                    "made_progress": (DIAG.get("t2_cells_new_this_run", 0) > 0
                                      or DIAG.get("t4_calls_spent", 0) > 0),
                    "t2_cells_fetched": comp["t2_cells_fetched"],
                    "t2_cells_total": comp["t2_cells_total"],
                    "t2_cells_new_this_run": DIAG.get("t2_cells_new_this_run", 0),
                    "t4_months_fetched": comp["t4_months_fetched"],
                    "t4_months_total": comp["t4_months_total"],
                    "wall_minutes": round((time.monotonic() - t0) / 60.0, 1),
                    "generated": dt.datetime.now(dt.timezone.utc).isoformat()})
    print("\nwrote %s\nwrote %s\nwrote %s" % (OUT_JSON, OUT_MD, PROGRESS))

    a = p["analysis"]
    st = p["standing"]
    print("\n" + "=" * 78)
    print("THE BENCHMARK - standing in %s, would the radar have flagged ADHD?" % st["cutoff"])
    for r in st["tiers"]:
        print("  %-3s %-28s onset %-8s knowable %-8s  %s%s"
              % (r["tier"], r["name"], r["onset"] or "-", r["knowable_by"] or "-",
                 "FLAGGED" if r["flagged_by_cutoff"] else "not in time / no onset",
                 "  [LEFT-CENSORED]" if r["left_censored"] else ""))
    print("  VERDICT: %s" % st["verdict"])

    print("\n" + "-" * 78)
    for t in TIERS:
        row = a["tiers"][t]
        fp = ("%s (%d neg)" % (row["fp_rate_honest"], row["informative_negatives"])
              if row["specificity_measurable"] else "n/a - NO INFORMATIVE NEGATIVES")
        print("%s %-28s hit %-5s (%d pos)   FP %-28s Fisher p=%s"
              % (t, TIER_NAME[t], row["hit_rate"], row["informative_positives"], fp,
                 row["discrimination_fisher_p"]))

    print("\nLEAD TIMES vs THE CALIBRATED NULL (the null is what a ZERO true lead reports):")
    for pair, g in a["lead_times"].items():
        if not g["n"]:
            continue
        print("  %-8s measured %+5s   null %+5s (p90 %+s)   %s"
              % (pair, g["median_gap_months"], g.get("null_median_gap_months"),
                 g.get("null_p90"),
                 "BEATS NULL" if g.get("beats_null") else "does NOT beat the null"))
        print("           in order %d/%d   p=%s vs a coin flip (WRONG), p=%s vs the "
              "calibrated %d%% null (USE THIS)"
              % (g["n_in_predicted_order"], g["n"], g.get("sign_test_p_naive_vs_coinflip"),
                 g.get("sign_test_p_calibrated"),
                 int(100 * (g.get("null_order_rate") or 0.5))))

    if a["disconfirming"]:
        print("\nDISCONFIRMING - graveyard niches that FIRED:")
        for d in a["disconfirming"]:
            print("  %-3s %-30s onset %-8s peak_z %s"
                  % (d["tier"], d["label"], d["onset"], d["peak_z"]))
    else:
        print("\nNo graveyard niche fired anywhere. CHECK THE ABSTENTION COUNTS before "
              "believing that.")
    print("=" * 78)

    if not comp["complete"]:
        print("\n" + "!" * 78)
        print("THIS RUN IS PARTIAL: T2 %s%% of cells, T4 %s%% of months. The report "
              "says so at the" % (comp["t2_pct"], comp["t4_pct"]))
        print("top. Caches are saved and committed; RE-RUN THE WORKFLOW TO RESUME. "
              "Exit 0 (a partial")
        print("run that finished cleanly is a success, not a failure).")
        print("!" * 78)
    return 0


# =============================================================================
#  10. SELFTEST - no network. Fixtures with a KNOWN injected lead structure.
# =============================================================================
# The sandbox this was written in has NO DNS, so the live path cannot be exercised. What
# CAN be proved offline is the part most likely to be silently wrong: ASSEMBLY, the T4
# query construction, and the ANALYSIS. So we synthesise raw payloads in the exact shape
# the real fetchers return, inject a lead structure we choose, push them through the REAL
# build_series/evaluate/analyse - not a parallel copy - and check the pipeline recovers it.
#
# Recovery is not exact and should not be: onset_robust has a detection lag. The fixtures
# assert the ORDER and the neighbourhood. A test demanding exactness would be testing noise.
def _fixture(lead=6, seed0=0):
    """Raw payloads shaped like fetch_t1 / fetch_t2 / fetch_t3 / fetch_t4 return.

    POSITIVES boom in all four tiers, staggered by `lead` months of CALENDAR time.
    GRAVEYARD booms on T1 and T2 and NOTHING on T3/T4 - the CBD shape. If the analysis
    cannot produce a false-positive rate from that, the analysis is broken.

    Levels match reality rather than convenience: ~6 new companies/month, ~3 new CQC
    registrations/month, ~4,000 prescription items/month. That thinness is precisely why
    the null calibration comes out non-zero.
    """
    a1, a2, a3, a4 = (axis(T1_START), axis(T2_START), axis(T3_START), axis(T4_START))
    t1, t2, t3, t4 = {}, {}, {}, {}
    truth = {}
    for i, n in enumerate(NICHES):
        b1 = "%d-01" % (2018 + (i % 3))
        b2, b3, b4 = m_add(b1, lead), m_add(b1, 2 * lead), m_add(b1, 3 * lead)
        truth[n["key"]] = {"T1": b1, "T2": b2, "T3": b3, "T4": b4}
        i1, i2, i3, i4 = a1.index(b1), a2.index(b2), a3.index(b3), a4.index(b4)

        t1[n["key"]] = [float(int(min(100.0, 4.0 + 96.0 * max(0, t - i1) / 24.0)
                                  + ((t * 7919) % 5) / 5.0)) for t in range(len(a1))]
        vals2 = _counts(len(a2), _ramp(6.0, 5.0, i2), seed=seed0 + 100 + i)
        rate3 = _ramp(3.0, 5.0, i3) if n["cls"] == POSITIVE else (lambda t: 3.0)
        vals3 = _counts(len(a3), rate3, seed=seed0 + 200 + i)
        rate4 = _ramp(4000.0, 4.0, i4) if n["cls"] == POSITIVE else (lambda t: 4000.0)
        vals4 = _counts(len(a4), rate4, seed=seed0 + 300 + i)

        for j, kw in enumerate(n["ch"]):
            share = [(v if len(n["ch"]) == 1 else
                      math.floor(v * (0.7 if j == 0 else 0.3 / (len(n["ch"]) - 1))))
                     for v in vals2]
            t2.setdefault(kw, {})
            for k, m in enumerate(a2):
                t2[kw][m] = t2[kw].get(m, 0) + int(share[k])
        t3[n["key"]] = {"active_only": vals3, "corrected": vals3,
                        "n_active": int(sum(vals3)), "n_recovered": 0,
                        "dedup_collapsed": 0}
        # T4 payload is keyed by MONTH -> {code: items}, like fetch_t4 returns. Only the
        # four in-scope niches have codes, so only they get a T4 series - which is itself
        # the point being tested.
        codes = T4_CODES.get(n["key"]) or []
        if codes:
            for k, m in enumerate(a4):
                row = t4.setdefault(m, {})
                per = vals4[k] / len(codes)
                for c in codes:
                    row[c] = row.get(c, 0) + per
                row[CANARY] = 900000
    return t1, t2, t3, t4, truth


def selftest(quick=False):
    fails, n_ok = [], 0

    def check(name, ok, detail=""):
        nonlocal n_ok
        print(("  PASS  " if ok else "  FAIL  ") + name + (("   " + detail) if detail else ""))
        if ok:
            n_ok += 1
        else:
            fails.append(name)

    print("\n" + "=" * 78)
    print("BACKTEST3 SELFTEST - no network. The truth is known by construction.")
    print("=" * 78)

    # ---- 0. the inherited estimator still passes its own 21 fixtures ---------
    print("\n[0] backtest_core's own fixtures (the estimator is NOT redefined here)")
    check("0. backtest_core selftest passes 21/21", core_selftest() == 0)

    # ---- 1. the BNF codes are drugs.py's, not hand-typed ---------------------
    print("\n[1] T4 codes")
    errs = _validate_codes()
    check("1. every T4 BNF code resolves from drugs.py, is 9 chars, and is not a DEAD_CODE",
          not errs, "; ".join(errs[:3]) if errs else
          "%d codes across %d in-scope niches" % (
              len({c for v in T4_CODES.values() for c in v}), len(T4_CODES)))
    check("2. T4 abstains on ALL 8 graveyard niches - so its FP rate is UNDEFINED, not zero",
          all(not BY_KEY[n["key"]]["t4_scope"] for n in GRAVEYARDS),
          "informative negatives for T4 = %d"
          % sum(1 for n in GRAVEYARDS if n["t4_scope"]))
    check("3. T4 is in scope for exactly the 4 niches with a real NHS proxy",
          sorted(k for k in T4_SCOPE if T4_SCOPE[k][0])
          == ["adhd", "glp1", "menopause", "trt"])

    # ---- 2. the T4 query, including the July-2025 schema switch --------------
    print("\n[2] The NHSBSA schema trap")
    s_old = epd_sql("2022-01", ["0404000U0"])
    s_new = epd_sql("2026-04", ["0404000U0"])
    check("4. pre-Jul-2025 months query EPD_<YYYYMM> with `bnf_chemical_substance`",
          "`EPD_202201`" in s_old and "bnf_chemical_substance IN" in s_old
          and "bnf_chemical_substance_code" not in s_old)
    check("5. post-Jul-2025 months query EPD_SNOMED_<YYYYMM> with "
          "`bnf_chemical_substance_code` - the column that is a CODE, not a NAME",
          "`EPD_SNOMED_202604`" in s_new and "bnf_chemical_substance_code IN" in s_new)
    check("6. the canary chemical is added to EVERY query",
          CANARY in s_old and CANARY in s_new)
    try:
        epd_sql("2022-01", ["'; DROP TABLE x; --"])
        check("7. a non-BNF code is refused before it reaches the SQL", False)
    except ValueError:
        check("7. a non-BNF code is refused before it reaches the SQL", True)

    nulls = {"success": True, "result": {"success": "true", "result": {"records": [
        {"c": "0404000U0", "i": None}, {"c": CANARY, "i": None}]}}}
    check("8. a month of NULLs (the real response for the wrong column) is REJECTED, not "
          "read as zero prescribing",
          epd_fetch_month("2026-04", ["0404000U0"], getter=lambda u: nulls) is None)
    good = {"success": True, "result": {"success": "true", "result": {"records": [
        {"c": "0404000U0", "i": 27728}, {"c": CANARY, "i": 900000}]}}}
    got = epd_fetch_month("2022-01", ["0404000U0"], getter=lambda u: good)
    check("9. a real month parses (Jan-2022 lisdexamfetamine = 27,728, the live figure)",
          got and got.get("0404000U0") == 27728)
    check("10. a network failure yields None (unknown), never 0 (collapsed)",
          epd_fetch_month("2022-01", ["0404000U0"],
                          getter=lambda u: (_ for _ in ()).throw(IOError("no dns"))) is None)
    # A cache holding one month must NOT look like a complete one-month series. The axis is
    # anchored to what NHSBSA has PUBLISHED, not to what we happen to hold, so the other
    # ~147 months are HOLES and the series is withheld.
    holes = {"2014-01": {"0404000U0": 737, CANARY: 900000}}
    _m, v, cov = t4_series(BY_KEY["adhd"], holes, latest="2026-04")
    check("11. a cache with holes is WITHHELD, not zero-filled - the axis runs to the "
          "latest PUBLISHED month, not the latest month we hold (coverage %.2f < 0.9)" % cov,
          v is None and cov < 0.05)
    full = {m: {"0404000U0": 700 + 800 * i, CANARY: 900000}
            for i, m in enumerate(axis(T4_START, "2026-04"))}
    _m, v, cov = t4_series(BY_KEY["adhd"], full, latest="2026-04")
    check("11b. a complete cache yields a %d-month series" % len(full),
          v is not None and len(v) == len(full) and cov == 1.0)

    # ---- 3. assembly recovers an INJECTED lead ------------------------------
    print("\n[3] Assembly: does the pipeline recover a lead structure we injected?")
    LEAD = 6
    t1, t2, t3, t4, truth = _fixture(lead=LEAD)
    series = build_series(t1, t2, t3, t4)
    res = evaluate(series)

    got_t4 = [n["key"] for n in NICHES if res[n["key"]]["tiers"]["T4"]["state"] == "FIRED"]
    check("12. all four tiers produce series and the four T4-scoped positives fire",
          set(got_t4) == {"adhd", "glp1", "menopause", "trt"}, "T4 fired: %s" % sorted(got_t4))

    onsets_ok = 0
    for n in POSITIVES:
        for t in TIERS:
            tt = res[n["key"]]["tiers"][t]
            if tt["state"] != "FIRED":
                continue
            d = m_diff(truth[n["key"]][t], tt["onset"])
            if d is not None and -3 <= d <= 24:
                onsets_ok += 1
    check("13. every onset that fired lands within [-3, +24] months of the TRUE injected "
          "boom (detection lag, not error)", onsets_ok >= 14,
          "%d onsets in range" % onsets_ok)

    null = calibrate_null(reps=30 if quick else 60, seed=7)
    an = analyse(res, null=null)
    for a1_, b1_ in ADJACENT:
        g = an["lead_times"]["%s->%s" % (a1_, b1_)]
        check("14%s. %s->%s recovers a POSITIVE median gap from the injected +%d"
              % (a1_[-1], a1_, b1_, LEAD),
              g["n"] > 0 and g["median_gap_months"] is not None
              and g["median_gap_months"] > 0,
              "median %s (n=%d)" % (g["median_gap_months"], g["n"]))

    # ---- 4. CAUSALITY. This is the fixture the headline claim rests on. ------
    print("\n[4] Causality: is the estimator using hindsight?")
    # If onset_robust ever peeks forward beyond its 3-month persistence window, then every
    # "we would have caught it in 2022" claim in this report is a lie. Re-run it on data
    # TRUNCATED at a cutoff and demand the identical onset.
    leaks, tested = [], 0
    for n in POSITIVES:
        for t in TIERS:
            tt = res[n["key"]]["tiers"][t]
            if tt["state"] != "FIRED":
                continue
            kb = tt["knowable_by"]
            cut = m_add(kb, 6)                       # comfortably after it was knowable
            s = series[n["key"]][t]
            tr = truncated_onset(n, t, s[0], s[1], cut)
            tested += 1
            if tr.get("onset") != tt["onset"]:
                leaks.append((n["key"], t, tt["onset"], tr.get("onset")))
    check("15. the onset computed on TRUNCATED data equals the onset computed on the full "
          "series, for all %d fired tiers - the estimator is causal and the 'standing in "
          "2022' claim is not hindsight" % tested, not leaks, "leaks: %s" % leaks[:3])

    # ---- 5. THE NULL. Does a TRUE lead of ZERO still report a lead? ----------
    print("\n[5] calibrate_null - the function backtest2 promised and never wrote")
    nz = calibrate_null(reps=40 if quick else 120, seed=99)
    nonzero = [(k, v["median_gap_months"]) for k, v in nz["pairs"].items()
               if v and v["median_gap_months"] != 0]
    check("16. with a TRUE lead of ZERO the pipeline STILL reports non-zero gaps - the "
          "artefact is real and every measured gap must be scored against it",
          len(nonzero) > 0, "%s" % nonzero[:4])
    skewed = [(k, v["pct_in_predicted_order"]) for k, v in nz["pairs"].items()
              if v and v["pct_in_predicted_order"] > 55.0]
    check("17. under a ZERO true lead the tiers still land 'in the predicted order' well "
          "above 50%% of the time - so the coin-flip sign test is testing a FALSE null",
          len(skewed) > 0, "%s" % skewed[:4])
    a_p = an["lead_times"]["T2->T3"]
    check("18. the calibrated sign-test p is >= the naive one (the correction can only ever "
          "make the result HARDER to believe, never easier)",
          a_p.get("sign_test_p_calibrated") is None
          or a_p["sign_test_p_calibrated"] >= a_p["sign_test_p_naive_vs_coinflip"] - 1e-9,
          "naive %s vs calibrated %s" % (a_p.get("sign_test_p_naive_vs_coinflip"),
                                         a_p.get("sign_test_p_calibrated")))
    check("19. the null's warm-up effect is visible: T3 (history from 2014) fires no more "
          "often than T2 (history from 2010) under an identical boom",
          nz["tier_fire_rate"]["T2"] >= nz["tier_fire_rate"]["T3"] - 0.05,
          json.dumps(nz["tier_fire_rate"]))

    # ---- 6. the graveyard must be ABLE to false-positive ---------------------
    print("\n[6] Specificity: can the graveyard produce a false-positive rate at all?")
    fp12 = [d for d in an["disconfirming"] if d["tier"] in ("T1", "T2")]
    check("20. the CBD-shaped fixture (booms on T1+T2, nothing on T3/T4) DOES produce false "
          "positives on the early tiers - if it could not, the FP rate would be zero by "
          "construction and the study would be worthless", len(fp12) > 0,
          "%d graveyard firings on T1/T2" % len(fp12))
    check("21. T4's FP rate is reported as UNMEASURABLE (n/a), never as 0.00",
          an["tiers"]["T4"]["specificity_measurable"] is False
          and an["tiers"]["T4"]["fp_rate_honest"] is None)
    t3s = an["tiers"]["T3"]
    check("22. abstaining graveyard niches are REMOVED from the honest denominator and are "
          "NOT counted as true negatives",
          t3s["informative_negatives"] == len(GRAVEYARDS) - len(t3s["graveyard_abstained"])
          and not (set(t3s["graveyard_abstained"]) & set(t3s["true_negatives"])),
          "%d graveyard, %d abstained, %d informative negatives"
          % (len(GRAVEYARDS), len(t3s["graveyard_abstained"]),
             t3s["informative_negatives"]))
    # ...and the arithmetic gap that quarantine prevents. Force ONE abstaining-heavy tier to
    # produce a false positive and watch the two rates diverge.
    res2 = json.loads(json.dumps(res))
    res2["ivdrip"]["tiers"]["T3"]["state"] = "FIRED"
    res2["ivdrip"]["tiers"]["T3"]["onset"] = "2019-01"
    a2 = analyse(res2, null=null)["tiers"]["T3"]
    check("22b. with 1 false positive and %d of 8 graveyard niches abstaining, the HONEST FP "
          "rate is %s and the CREDULOUS one is %s - counting abstentions as correct "
          "rejections would understate the false-positive rate by %.1fx"
          % (len(a2["graveyard_abstained"]), a2["fp_rate_honest"], a2["fp_rate_credulous"],
             (a2["fp_rate_honest"] / a2["fp_rate_credulous"])
             if a2["fp_rate_credulous"] else 0),
          a2["fp_rate_honest"] > a2["fp_rate_credulous"])

    # ---- 7. THE ESTIMATOR DETECTS ACCELERATION, NOT GROWTH -------------------
    print("\n[7] The property that decides the ADHD verdict: acceleration, not growth")
    ax = axis(T4_START)
    # A series compounding at a steady +3%/month (= 1.43x a year) from its VERY FIRST month.
    # This is, to a first approximation, ADHD prescribing.
    smooth = [4000.0 * (1.03 ** i) for i in range(len(ax))]
    stt = tier_state(BY_KEY["adhd"], "T4", ax, smooth)
    check("23. a series compounding SMOOTHLY at 1.43x/yr from its first month NEVER FIRES - "
          "onset_robust detects ACCELERATION, not growth, because its z-scale is the niche's "
          "own recent z-history and a smooth exponential has a flat one",
          stt["onset"] is None,
          "onset=%s, growth already running at the first testable month = %sx"
          % (stt["onset"], stt.get("growth_at_first_testable")))
    check("23b. ...and it is therefore reported as ALREADY_BOOMING, an ABSTENTION - NOT as "
          "NO_ONSET, which in a results table is indistinguishable from a correct rejection. "
          "That confusion would land squarely on ADHD.",
          stt["state"] == "ALREADY_BOOMING"
          and stt.get("growth_at_first_testable") is not None
          and stt["growth_at_first_testable"] >= 1.5,
          "state=%s, growth at first testable=%sx"
          % (stt["state"], stt.get("growth_at_first_testable")))
    # The same series with a genuine acceleration bolted on. It MUST fire - otherwise
    # ALREADY_BOOMING would be swallowing real signal.
    accel = [v * (1.0 if i < 96 else 1.06 ** (i - 96)) for i, v in enumerate(smooth)]
    sta = tier_state(BY_KEY["adhd"], "T4", ax, accel)
    check("23c. the SAME series with a real acceleration bolted on at month 96 DOES fire - "
          "so ALREADY_BOOMING is not swallowing signal, it is naming a CENSORED onset",
          sta["state"] == "FIRED", "onset=%s" % sta.get("onset"))
    check("24. the first testable month is ~54 months after a series starts - so T3 and T4 "
          "(history from 2014) are structurally BLIND before ~mid-2018",
          stt.get("first_testable") is not None and stt["first_testable"] >= "2018-01",
          "first testable = %s" % stt.get("first_testable"))
    flat = tier_state(BY_KEY["adhd"], "T4", ax, [4000.0] * len(ax))
    check("25. a FLAT series is a genuine NO_ONSET - not ALREADY_BOOMING, not left-censored. "
          "The abstention states are not a catch-all for silence.",
          flat["state"] == "NO_ONSET" and not flat.get("left_censored")
          and not flat.get("already_booming"))

    # ---- 8. the headline machinery ------------------------------------------
    print("\n[8] The headline question")
    st = standing_at(res, series, "2022-03", key="adhd")
    check("26. standing_at() returns a verdict for all four tiers, each with an explicit "
          "knowable-by month AND the YoY growth that was visible on the screen",
          len(st["tiers"]) == 4
          and all("knowable_by" in r and "yoy_visible_at_cutoff_pct" in r
                  for r in st["tiers"]))
    check("27. knowable_by = onset + 3 months persistence + the source's publication lag",
          knowable_by("T4", "2021-01") == "2021-07"      # 3 + 3
          and knowable_by("T2", "2021-01") == "2021-04"  # 3 + 0
          and knowable_by("T1", "2021-01") == "2021-04")
    check("28. no hindsight leaks in the fixture's standing-at check",
          not st["hindsight_leaks"], "%s" % st["hindsight_leaks"][:2])
    st2 = standing_at(
        {"adhd": {"tiers": {t: (tier_state(BY_KEY["adhd"], "T4", ax, smooth) if t == "T4"
                                else {"state": "NO_ONSET", "onset": None})
                            for t in TIERS}}},
        {"adhd": {"T4": (ax, smooth)}}, "2022-03")
    check("29. an ALREADY_BOOMING tier does NOT get reported as a flat 'NO'. The verdict "
          "says the onset is CENSORED (it predates the data), and the YoY column shows what "
          "would have been on the screen anyway. Reporting this as 'the radar did not flag "
          "ADHD' would be the exact opposite of the truth.",
          st2["tiers_already_booming"] == ["T4"]
          and not st2["verdict"].startswith("NO -")
          and "predates" in st2["verdict"] or "before the data window" in st2["verdict"],
          "verdict: %s" % st2["verdict"][:90])

    # ---- 9. the large-count Poisson trap ------------------------------------
    print("\n[9] The generator trap that would have corrupted the T4 null")
    big = _counts(400, lambda t: 5000.0, seed=3)
    mean_big = statistics.fmean(big)
    check("30. _counts() uses a normal approximation above lambda=200. backtest_core's "
          "Knuth sampler underflows exp(-5000) to 0.0 and silently returns ~700 instead of "
          "~5000 - which would have corrupted the T4 null and nothing else",
          4700 < mean_big < 5300, "mean of a lambda=5000 draw = %.0f" % mean_big)
    check("31. calibrate_null is REPRODUCIBLE - it does not use hash(), which Python "
          "randomises per process",
          calibrate_null(reps=8, seed=5)["pairs"]["T2->T3"]
          == calibrate_null(reps=8, seed=5)["pairs"]["T2->T3"])

    # ---- 10. honest arithmetic about n --------------------------------------
    print("\n[10] What n even permits")
    pw = power_note(4, hyps=len(PAIRS))
    check("32. T4's lead/lag rests on n=4 and CANNOT reach significance even if perfect",
          pw["passes"] is False,
          "a perfect 4/4 -> p=%.4f vs a Bonferroni alpha of %.4f"
          % (pw["perfect_sweep_p"], pw["bonferroni_alpha"]))
    check("33. no 95%% CI for a median exists at n=5", median_ci([1, 2, 3, 4, 5]) is None)

    # ---- 11. RESUMABILITY - the property the six-hour CI corpse was missing --
    print("\n[11] Resumability: killed mid-run + restarted == uninterrupted, no refetch")
    global EPD_CACHE, OUT_MD
    tmp = tempfile.mkdtemp(prefix="bt3resume")
    old_cch, old_cpr, old_epd, old_out = bt2.CH_CACHE, bt2.CH_PROBE, EPD_CACHE, OUT_MD
    old_diag = dict(DIAG)
    nothr = _NoThrottle()

    def hits(kw, m):                       # deterministic fake Companies House
        return (len(kw) * 31 + int(m[:4]) * 7 + int(m[5:7])) % 23

    fk_log = []

    def fk(kw, m, thr):
        fk_log.append((kw, m))
        return hits(kw, m), None

    def pk(kw, thr):
        return {"sampled": 100, "precision": 1.0, "examples_rejected": [],
                "hits_total": 9}

    months2 = axis(T2_START)
    ncells = len(bt2.ALL_KEYWORDS) * len(months2)
    try:
        # A: one uninterrupted run = the ground truth every kill must converge on
        bt2.CH_CACHE = os.path.join(tmp, "a.json")
        bt2.CH_PROBE = os.path.join(tmp, "a_probe.json")
        ca, _pa = fetch_t2_parallel(10 ** 9, fetch_fn=fk, probe_fn=pk, workers=7,
                                    throttle=nothr, save_every=10 ** 9)
        check("34. offline T2 fetch fills every cell (%d keywords x %d months = %d)"
              % (len(bt2.ALL_KEYWORDS), len(months2), ncells),
              sum(len(v) for v in ca.values()) == ncells
              and DIAG.get("t2_coverage") == 1.0)

        # B: budget-killed at 41%, then resumed
        bt2.CH_CACHE = os.path.join(tmp, "b.json")
        bt2.CH_PROBE = os.path.join(tmp, "b_probe.json")
        fk_log.clear()
        cb1, _ = fetch_t2_parallel(int(ncells * 0.41), fetch_fn=fk, probe_fn=pk,
                                   workers=7, throttle=nothr)
        n1 = sum(len(v) for v in cb1.values())
        disk = load(bt2.CH_CACHE) or {}
        check("35. a budget-killed run STOPS, flags itself, and had SAVED its cells to "
              "disk before returning",
              DIAG.get("t2_hit_budget_cap") is True and 0 < n1 < ncells and disk == cb1,
              "%d/%d cells on disk" % (n1, ncells))
        cb2, _ = fetch_t2_parallel(10 ** 9, fetch_fn=fk, probe_fn=pk, workers=7,
                                   throttle=nothr, save_every=10 ** 9)
        check("36. the resumed run converges on the IDENTICAL cache an uninterrupted "
              "run produces, and no (keyword, month) cell was ever fetched twice",
              cb2 == ca and len(fk_log) == len(set(fk_log)) == ncells,
              "%d fetches for %d cells across both runs" % (len(fk_log), ncells))

        # C: a HARD kill mid-flight (a worker raises), then resume
        bt2.CH_CACHE = os.path.join(tmp, "c.json")
        bt2.CH_PROBE = os.path.join(tmp, "c_probe.json")
        boom = [0]

        def fk_die(kw, m, thr):
            boom[0] += 1
            if boom[0] == 977:
                raise KeyboardInterrupt("simulated kill")
            return hits(kw, m), None

        died = False
        try:
            fetch_t2_parallel(10 ** 9, fetch_fn=fk_die, probe_fn=pk, workers=7,
                              throttle=nothr)
        except KeyboardInterrupt:
            died = True
        disk = load(bt2.CH_CACHE) or {}
        cc, _ = fetch_t2_parallel(10 ** 9, fetch_fn=fk, probe_fn=pk, workers=7,
                                  throttle=nothr, save_every=10 ** 9)
        check("37. a run KILLED mid-flight still saves its cache on the way down, and "
              "the restart converges on the identical full cache",
              died and disk and cc == ca,
              "%d cells survived the kill" % sum(len(v) for v in disk.values()))

        # D: the wall-clock deadline (--minutes), on a fake clock
        bt2.CH_CACHE = os.path.join(tmp, "d.json")
        bt2.CH_PROBE = os.path.join(tmp, "d_probe.json")
        fake_t = [0.0]

        def fk_slow(kw, m, thr):
            fake_t[0] += 0.4
            return hits(kw, m), None

        cd1, _ = fetch_t2_parallel(10 ** 9, fetch_fn=fk_slow, probe_fn=pk, workers=1,
                                   throttle=nothr, deadline=600.0,
                                   clock=lambda: fake_t[0])
        nd = sum(len(v) for v in cd1.values())
        check("38. --minutes: when the wall-clock budget is spent the fetch saves, "
              "flags DIAG['t2_deadline_hit'], and returns a resumable partial",
              DIAG.get("t2_deadline_hit") is True and 0 < nd < ncells,
              "%d/%d cells before the deadline" % (nd, ncells))
        cd2, _ = fetch_t2_parallel(10 ** 9, fetch_fn=fk, probe_fn=pk, workers=7,
                                   throttle=nothr, save_every=10 ** 9)
        check("39. ...and resuming after a deadline kill also converges on the "
              "identical cache", cd2 == ca)

        # E: completeness accounting + the report banner
        comp = _completeness(cd1, {})
        check("40. completeness arithmetic: a partial T2 cache reports the right cell "
              "count and marks the run INCOMPLETE",
              comp["t2_cells_fetched"] == nd and not comp["complete"]
              and comp["t2_pct"] == round(100.0 * nd / ncells, 1))
        lines = "".join(_completeness_lines(comp))
        check("41. the report banner for a partial run says PARTIAL, gives the T2 "
              "percentage, and says withheld keywords are never zero-filled",
              "PARTIAL RUN" in lines and ("%s%%" % comp["t2_pct"]) in lines
              and "never zero-filled" in lines)
        had_latest = DIAG.get("t4_latest_published")
        DIAG["t4_latest_published"] = "2026-04"
        compf = _completeness(ca, {m: {} for m in axis(T4_START, "2026-04")})
        check("42. a full T2 cache + full T4 cache reports complete=True and the "
              "banner collapses to one 'FULL' line",
              compf["complete"] and "FULL" in "".join(_completeness_lines(compf)))
        if had_latest is None:
            DIAG.pop("t4_latest_published", None)
        else:
            DIAG["t4_latest_published"] = had_latest

        # F: fetch_t4 honours the deadline too (serial getter path, fake clock)
        EPD_CACHE = os.path.join(tmp, "epd.json")
        seed = {"2014-01": {"0404000U0": 737, CANARY: 900000}}
        save(EPD_CACHE, seed)
        got_hist = fetch_t4(
            getter=lambda u: (_ for _ in ()).throw(IOError("must not be called")),
            deadline=0.0, clock=lambda: 1.0)
        check("43. fetch_t4 with the budget already spent makes ZERO calls and returns "
              "the cache untouched (a month is never half-fetched)",
              got_hist == seed and DIAG.get("t4_deadline_hit") is True
              and DIAG.get("t4_calls_spent", 0) == 0)

        # G: the crash path - if the run dies, backtest3.md must still appear
        OUT_MD = os.path.join(tmp, "crash.md")
        try:
            raise RuntimeError("synthetic crash for the selftest")
        except RuntimeError as e:
            _crash_md(e)
        txt = open(OUT_MD, encoding="utf-8").read()
        check("44. a crash still writes backtest3.md, naming the exception and how far "
              "the fetchers got",
              "RUN CRASHED" in txt and "RuntimeError" in txt and "DIAG" in txt)
    finally:
        bt2.CH_CACHE, bt2.CH_PROBE, EPD_CACHE, OUT_MD = (old_cch, old_cpr, old_epd,
                                                         old_out)
        DIAG.clear()
        DIAG.update(old_diag)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "-" * 78)
    print("%d/%d fixtures passed" % (n_ok, n_ok + len(fails)))
    if fails:
        print("FAILURES:")
        for f in fails:
            print("  - " + f)
        return 1
    print("\nALL PASS. Note what this does and does NOT prove. It proves the ASSEMBLY, the")
    print("T4 query, the CAUSALITY of the estimator and the NULL CALIBRATION are correct.")
    print("It proves NOTHING about whether the radar works. Only a live run can do that,")
    print("and at n=16 even a live run can only FALSIFY.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Radar backtest v3 (T1/T2/T3/T4, 2014-2026)")
    ap.add_argument("--selftest", action="store_true", help="fixtures only; no network")
    ap.add_argument("--quick", action="store_true", help="fewer null reps in the selftest")
    ap.add_argument("--trends", action="store_true",
                    help="also run T1 Google Trends (SerpApi; cached forever)")
    ap.add_argument("--max-calls", type=int, default=6000,
                    help="cap on Companies House calls this run (resumable)")
    ap.add_argument("--max-epd-calls", type=int, default=MAX_EPD_CALLS,
                    help="cap on NHSBSA month-fetches this run (resumable)")
    ap.add_argument("--null-reps", type=int, default=NULL_REPS)
    ap.add_argument("--cutoff", default="2022-03",
                    help="the 'standing here, would it have flagged?' month")
    ap.add_argument("--refresh", "--force", dest="refresh", action="store_true",
                    help="ignore caches")
    ap.add_argument("--minutes", type=float, default=0.0,
                    help="wall-clock budget in minutes; when spent, save the caches, "
                         "write a PARTIAL report and exit 0 (re-running resumes). "
                         "0 = no budget. CI passes 50.")
    ap.add_argument("--t2-workers", type=int, default=T2_WORKERS,
                    help="parallel Companies House fetchers behind ONE shared "
                         "500-per-5-min throttle")
    ap.set_defaults(trends=False)
    args = ap.parse_args()
    if args.selftest:
        return selftest(quick=args.quick)
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())
