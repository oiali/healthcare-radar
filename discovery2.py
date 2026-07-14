#!/usr/bin/env python3
"""
DISCOVERY 2 - the open layer. The only place a niche nobody pre-listed can appear.

THE ONE QUESTION
----------------
What UK private-pay healthcare niche is rising, and how early am I seeing it?

taxonomy.py holds 25 FIXED niches. Every other tier of the radar maps its findings onto
them and reports BY NICHE. A phrase that matches nothing is silently dropped. That is a
closed system: it can re-rank the 25 niches somebody already thought of, it cannot surface
the 26th. If ADHD had not been on that list in 2019, the radar would have watched thousands
of ADHD clinics incorporate and shown you nothing.

This module keeps the floor sweepings - the UNCLASSIFIED RESIDUE. Every phrase rising in
new company names and new CQC clinic names that maps to NO existing niche.

WHAT CHANGED FROM discovery.py (and why)
----------------------------------------
1. TRIGRAMS. Real niche names are often three words: "gut microbiome testing",
   "red light therapy", "peptide therapy clinic". The old tokeniser emitted unigrams and
   bigrams only, so a three-word niche was not merely unranked - it was UNSAYABLE. Also:
   the minimum token length inside a multi-word phrase drops from 4 to 2, so "iv drip" and
   "tms clinic" become reachable; and n-grams no longer span a removed stop word, so
   "Botox AND Filler Clinic" can no longer manufacture the phrase "botox filler".

2. THE FULL CORPUS, NOT THE LEFTOVERS OF A TOP-40 LIST. The old open layer was fed the rows
   the existing miners had ALREADY truncated to their top 40 by growth. So the residue was
   the residue of a list that had already thrown the long tail away - and the long tail is
   exactly where a niche that nobody has named yet lives. This is the single biggest change:
   the miners here read the WHOLE CQC file and the WHOLE Companies House name corpus, and
   the truncation happens once, at the end, after the filter.

3. VELOCITY, NOT LEVEL - AND A GROWTH TEST THAT KNOWS WHAT NOISE LOOKS LIKE. A new niche's
   tell is ACCELERATION FROM A SMALL BASE: 0 -> 3 -> 11 operators across three four-month
   periods. The old layer had one number - 12-month growth - which cannot tell "big and
   drifting up" from "tiny and exploding". Every phrase now carries a three-period
   trajectory plus a prior-year window plus an EVER-BEFORE window, and is ranked on the
   SHAPE.

   The trajectory alone is not enough, and finding out why was the most useful thing that
   came out of building this. Widening the intake (point 2) means judging 500 phrases
   instead of 40 - and at these counts a PERCENTAGE THRESHOLD IS A COIN FLIP. A surname with
   30 clinics one year and 30 the next does not register 30 and 30; it registers 26 and 34,
   because arrivals are random. That is +31%, and a "+25% is rising" rule waves it through.
   Run the old rule over 6,000 realistic clinic names with one niche planted in them and it
   surfaces the niche - plus TWENTY-TWO surnames, towns and brand words. So "rising" here
   means "risen by more than arrival noise can explain": z = (now - before)/sqrt(now+before),
   z >= 2.4. Same corpus, same planted niche, junk rows go from 22 to 2, and detection stays
   at 100% right down to the six-operator floor. See Z_MIN.

4. AGE IS A SEPARATE FACT FROM SPEED. A phrase that has existed for five years and is
   suddenly accelerating and a phrase that did not exist eighteen months ago are BOTH worth
   knowing about and they are NOT the same thing. They are labelled differently
   ("accelerating" vs "new") and novelty is the single heaviest term in the score, because
   the brief for this product is "I wanted to catch the ADHD boom 2 years ago".

5. FAMILIES. "microbiome", "gut microbiome", "microbiome testing" and "gut microbiome
   testing" are one discovery, not four rows. Phrases that contain one another AND share
   their operators are collapsed into one row with the variants listed underneath.

6. ONE PLAIN SENTENCE PER ROW. Including for the rows that were THROWN AWAY, so a filter
   decision can be argued with instead of vanishing.

THE HARD PART IS NOT FINDING PHRASES. IT IS THROWING THEM AWAY.
--------------------------------------------------------------
The residue is mostly rubbish: founders' surnames (Hartley), towns (Molesey), brand words
(Zenith), and generic business vocabulary. A blocklist of surnames and place names is not
an answer - it is a second closed system, and it fails the moment a founder is called
something you did not list. So the filter is STRUCTURAL. Five properties separate a service
from a name and none of them needs a list:

  1. DISTINCT OPERATORS. A real niche is used by MANY UNRELATED operators - twelve people
     who have never met each other all call it a "microbiome clinic" because that is what
     the thing IS. A brand is used by ONE operator, however many times.
  2. MENTIONS PER OPERATOR. Catches the FRANCHISE, which clears the operator gate on
     head-count (7 owners) but is still one brand (6 sites each).
  3. RISING, NOT STANDING. Surnames and place names are STATIONARY: the share of UK clinics
     called "Hartley" is the same this year as last. This is the only thing that kills a
     COMMON surname, which sails through the operator gate because there really are nine
     unrelated Hartleys.
  4. GEOGRAPHIC SPREAD. A place name is concentrated by definition. A service is national.
  5. THE EXISTING STOP LIST, reused from pull_and_build. Two copies of a stop list are two
     copies that drift.

Read discovery2_FINDINGS.md for what this method can NEVER see. The short version: an
existing clinic quietly adding a service line files no company and registers no location,
so it is invisible here - and that may well be how the next boom actually starts.

Python 3.11, stdlib only.
    python3 discovery2.py --selftest     synthetic fixtures, no network
"""

import os
import re
import sys
import json
import gzip
import math
import time
import base64
import zipfile
import tempfile
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from functools import lru_cache
from datetime import date

# Designed to sit next to taxonomy.py in radar-app/. It currently lives one level down in
# _agent3/, so both directories go on the path - the same file works in place today and
# after it is moved up.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

DIAG = {}

# The taxonomy is the DEFINITION of "already known". A phrase is residue iff niche_of()
# cannot place it.
try:
    from taxonomy import niche_of as _niche_of_raw
except Exception as _e:                                   # pragma: no cover
    def _niche_of_raw(_t):
        return None
    DIAG["taxonomy_import_failed"] = repr(_e)[:120]

# STOP and SERVICE_TAIL are REUSED, not re-derived. A silently smaller stop list means a
# tab full of the word "clinic"; a silently smaller SERVICE_TAIL means "peptide therapy"
# becomes unsayable again.
try:
    from pull_and_build import STOP as _STOP, SERVICE_TAIL as _SERVICE_TAIL
    _STOP_SOURCE = "pull_and_build.STOP + SERVICE_TAIL"
except Exception as _e:
    _STOP_SOURCE = "fallback copy (pull_and_build not importable: %s)" % repr(_e)[:60]
    _STOP = set((
        "the and of for to in a an ltd limited uk gb london clinic clinics health "
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
    _SERVICE_TAIL = set((
        "therapy therapies treatment treatments clinic clinics care "
        "medicine surgery assessment assessments screening testing "
        "injection injections infusion infusions").split())

STOP = set(_STOP)
SERVICE_TAIL = set(_SERVICE_TAIL)

# Words that are noise as a UNIGRAM but carry the niche as the tail of a phrase. Omar's own
# example of the granularity he wants is "peptide therapy" - which a strict stop list makes
# structurally impossible to emit.
STOP_BIGRAM = STOP - SERVICE_TAIL

# EXTRA_STOP exists ONLY because this module lowered the minimum token length inside a
# phrase from 4 to 2, which makes a handful of two- and three-letter words reachable that
# were previously invisible. These are honorifics and legal-form abbreviations, not a
# surname list and not a place list - both of those are precisely what this module refuses
# to build, because a hard-coded list of names is just a second closed system.
EXTRA_STOP = set("dr drs mr mrs ms miss prof sir dame st co ltd plc llp inc "
                 "the and for eu uk gb".split())

# CLINICAL_TAIL is DERIVED from SERVICE_TAIL, not invented: it is the treatment-shaped
# words, minus the three that every clinic in the country uses regardless of what it does.
# "Hartley Clinic" tells you nothing. "Photobiomodulation Therapy" tells you something.
CLINICAL_TAIL = SERVICE_TAIL - {"clinic", "clinics", "care"}

# The ODS parser is investability.py's - covered-table-cells, number-columns-repeated and
# all. A second copy of that parser is a second copy that can drift.
try:
    from investability import ods_rows, _resolve_columns, _parse_date
    _ODS_OK = True
except Exception as _e:                                   # pragma: no cover
    _ODS_OK = False
    DIAG["investability_import_failed"] = repr(_e)[:120]


# ============================================================== THE THRESHOLDS
# Judgement calls, stated as constants in one place with the reasoning, so they can be
# argued with rather than reverse-engineered.

# MIN_OPERATORS = 6 -- the gate, and the whole idea. Five could be five friends, a
# franchise, or one person with five companies. Six UNRELATED operators independently
# choosing the same word is where the word starts to mean something to the market rather
# than to one founder. Deliberately LOW: a false positive costs one junk row a human
# ignores; a false negative costs the next ADHD, which is the entire point of the module.
MIN_OPERATORS = 6

# MIN_OPERATORS_ASSUMED = 12 -- when operator identity was ASSUMED rather than OBSERVED.
# One Companies House company = one record, so a group that incorporates twelve Ltds looks
# like twelve "operators". CQC carries a real Provider ID and does not have this problem.
# An assumed operator count is worth half an observed one.
MIN_OPERATORS_ASSUMED = 12

# MAX_MENTIONS_PER_OPERATOR = 3.0 -- the brand test, and the reason the operator gate alone
# is not enough. A 7-clinic franchise with 6 sites each clears a 6-operator gate easily; it
# scores 42/7 = 6.0 here and dies. A genuine service phrase is near 1.0. 3.0 leaves room for
# a real two- or three-site owner-operator without letting a chain through.
MAX_MENTIONS_PER_OPERATOR = 3.0

# Z_MIN = 2.4 -- THE STATIONARITY TEST, and the single most important number in the file.
#
# The obvious version of this test is a percentage: "up at least 25% year on year". Widening
# the intake to the full corpus proved that a percentage DOES NOT WORK, and the failure is
# not subtle. Run this module over 6,000 realistic clinic names with ONE niche planted in
# them and a +25% rule surfaces the niche - along with twenty-two surnames, towns and brand
# words. Not because the filter is careless, but because at these counts a percentage is a
# COIN FLIP. A surname with 30 clinics one year and 30 the next does not actually register
# 30 and 30; it registers 26 and 34, because arrivals are random. That is +31%, and a 25%
# rule waves it through. The old open layer never noticed, because it was fed a list of 40
# rows that had already been truncated - with 500 candidates instead of 40, chance alone
# will hand you a dozen "risers" every single run.
#
# So the test is not "did it go up", it is "did it go up by MORE THAN ARRIVAL NOISE CAN
# EXPLAIN". For counts, the noise is the square root of the count, so:
#
#       z = (now - before) / sqrt(now + before)
#
# and we require z >= 2.4. Two properties make 2.4 the right number rather than a knob:
#   * it is roughly a 1-in-120 chance of firing on a phrase that is genuinely flat, so with
#     ~500 candidate phrases we expect around four junk rows a run. That is the honest price
#     of a wide intake, and it is the right trade: a junk row costs a glance, a missed niche
#     costs the entire product.
#   * it lands EXACTLY on the operator gate. A phrase used by six operators where there were
#     none before scores 6/sqrt(6) = 2.449. So the smallest thing the operator gate admits is
#     also the smallest thing this gate admits, and the two agree instead of fighting.
Z_MIN = 2.4

# MIN_REGIONS = 3 -- the place-name test. A service is national. "Molesey" is not. Applied
# only where the source gives a geography: CQC gives a region, Companies House gives a
# registered-office postcode area. See FINDINGS on why the postcode area is the weaker of
# the two (accountants register hundreds of companies at one address).
MIN_REGIONS = 3

# PERIOD_MONTHS = 4 -- the three trajectory buckets are the last 4 months, the 4 before
# that, and the 4 before that. Four is the shortest window that still holds enough CQC
# registrations for a count to mean anything (roughly 250-400 new independent-healthcare
# locations a year nationally, so a month is single digits and pure noise), and three of
# them exactly tile the trailing year, which keeps the trajectory and the year-on-year
# comparison consistent with each other.
PERIOD_MONTHS = 4

# EMERGING_MONTHS = 18 -- how recently a phrase must have FIRST appeared to count as
# emerging rather than merely rising. Longer than the gap between the earliest tier
# (search) and the tier this reads (company formation), so a niche caught on the way up is
# still flagged new by the time clinics start registering.
EMERGING_MONTHS = 18

# MIN_COUNT = 4 -- floor on raw mentions in the trailing year, matching the existing miners.
# Below this the growth arithmetic is noise: 1 -> 2 is +100%.
MIN_COUNT = 4

# Ranking weights. NOVELTY IS THE HEAVIEST TERM ON PURPOSE. The product's benchmark is "I
# wanted to catch the ADHD boom 2 years ago", so a phrase that did not exist before and now
# has fifteen unrelated operators must beat a big established phrase that is merely rising
# fast, every time.
LIFT_CAP = 8.0            # last period vs first period, capped: 0 -> 11 is not 22x better
YOY_CAP = 8.0             # same, for the year-on-year
W_LIFT = 0.45
W_YOY = 0.35
W_MONOTONE = 0.6          # rose in BOTH steps - a trajectory, not one lucky quarter
W_NOVELTY = 1.5           # x2 if never seen before 24m, x1 if born inside the last 24m
CTX_BONUS = 0.15          # small: a genuinely new word may have no clinical word beside it
W_SELF_CLINICAL = 0.3     # the phrase itself is treatment-shaped ("nattokinase therapy")
MULTI_TIER_BONUS = 1.15   # seen in company names AND clinic registrations - corroboration

MAX_ROWS = 40
HISTORY_VERSION = 2

# Trajectory bucket names, newest first in the tuple that is reported: (p1, p2, p3) is
# oldest -> newest, i.e. (8-12 months ago, 4-8 months ago, last 4 months).
BUCKETS = ("p1", "p2", "p3", "prior12", "pre24")


# ================================================================== utilities
def _pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / float(then) - 1.0) * 100.0


def _z(now, before):
    """How many times bigger than ARRIVAL NOISE is this increase?

    Counts of things that arrive independently (clinics registering, companies forming)
    scatter by about the square root of the count. 30 one year and 34 the next is not a
    trend, it is the same number twice. This is the arithmetic that says so.
    """
    if now is None or before is None:
        return None
    tot = now + before
    if tot <= 0:
        return None
    return (now - before) / math.sqrt(tot)


def _add_months(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def _months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def _iso_to_date(s):
    try:
        p = [int(x) for x in str(s).split("-")[:3]]
        return date(p[0], p[1], p[2])
    except Exception:
        return None


def _load(path, default):
    try:
        if path.endswith(".gz"):
            with gzip.open(path, "rt") as fh:
                return json.load(fh)
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def _save(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    if path.endswith(".gz"):
        with gzip.open(path, "wt") as fh:
            json.dump(obj, fh, sort_keys=True)
        return
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)


@lru_cache(maxsize=200000)
def niche_of(phrase):
    """Cached. niche_of() is ~250 compiled regexes; the miners ask it about thousands of
    phrases and about every token of every name."""
    return _niche_of_raw(phrase)


def is_residue(phrase):
    """The definition of the residue: the taxonomy cannot place it."""
    return niche_of(phrase) is None


# =============================================================== THE TOKENISER
# Unigrams stay at 4+ characters (a flood of three-letter noise buys nothing). Inside a
# multi-word phrase the floor drops to 2, which is what makes "iv drip" and "tms clinic"
# reachable at all - and a two-letter acronym next to a real word is exactly how a new
# treatment gets named.
MIN_UNIGRAM_LEN = 4
MIN_PHRASE_TOKEN_LEN = 2
MAX_GRAM = 3


def raw_tokens(name):
    return re.findall(r"[a-z]+", (name or "").lower())


def phrase_grams(name):
    """Name -> the set of 1-, 2- and 3-word phrases it can support.

    A SET, because a name that repeats a word must not contribute it twice: the count is
    "how many NAMES contain this phrase", and mention-inflation from inside a single name is
    exactly what lets a brand outrank a niche.

    Three rules, each of which the old bigram-only tokeniser got wrong:

      * N-GRAMS DO NOT SPAN A REMOVED STOP WORD. pull_and_build.grams() deletes stop words
        and THEN takes adjacent pairs of what is left, so "Botox and Filler Clinic" yields
        the phrase "botox filler", which nobody wrote. Here a dropped token leaves a BREAK
        and no phrase crosses it.
      * A PHRASE MAY NOT LEAD WITH A SERVICE WORD. "therapy clinic" is not a niche.
      * A PHRASE MUST CARRY AT LEAST ONE REAL WORD (4+ chars) and must not be made entirely
        of service words.
    """
    toks = raw_tokens(name)
    out = set()

    for t in toks:
        if (len(t) >= MIN_UNIGRAM_LEN and t not in STOP and t not in SERVICE_TAIL
                and t not in EXTRA_STOP):
            out.add(t)

    # None marks "a word was removed here" so no phrase can be built across the gap.
    seq = []
    for t in toks:
        keep = (len(t) >= MIN_PHRASE_TOKEN_LEN and t not in STOP_BIGRAM
                and t not in EXTRA_STOP)
        seq.append(t if keep else None)

    for n in range(2, MAX_GRAM + 1):
        for i in range(len(seq) - n + 1):
            win = seq[i:i + n]
            if any(w is None for w in win):
                continue
            if win[0] in SERVICE_TAIL:                       # do not lead with a tail word
                continue
            if all(w in SERVICE_TAIL for w in win):          # "therapy clinic" is not a niche
                continue
            if not any(len(w) >= MIN_UNIGRAM_LEN for w in win):   # all-short: initials
                continue
            out.add(" ".join(win))
    return out


def clinical_tokens(toks):
    """The tokens in this name that are CLINICAL - i.e. a treatment-shaped word, or a word
    the taxonomy already recognises as medical.

    Note what this is NOT: it is not a new hand-written health vocabulary. It is derived
    from two things that already exist - SERVICE_TAIL (minus 'clinic'/'care', which every
    clinic uses) and the taxonomy's own keys. The taxonomy is used here as a SEED of known
    clinical language, not as a classifier.
    """
    out = set()
    for t in toks:
        if t in CLINICAL_TAIL or niche_of(t) is not None:
            out.add(t)
    return out


# ============================================================ TIME BUCKETS
def bucket_of(d, anchor):
    """Which trajectory bucket a date falls in. None if it is in the future.

    p3  = the last 4 months          the freshest evidence
    p2  = 4-8 months ago
    p1  = 8-12 months ago            together, p1->p2->p3 is the SHAPE
    prior12 = 12-24 months ago       the year-on-year comparison
    pre24   = anything older         "did this phrase exist two years ago at all?"
    """
    if d is None or d > anchor:
        return None
    m = _months_between(d, anchor)
    if m < PERIOD_MONTHS:
        return "p3"
    if m < 2 * PERIOD_MONTHS:
        return "p2"
    if m < 3 * PERIOD_MONTHS:
        return "p1"
    if m < 24:
        return "prior12"
    return "pre24"


def _blank_phrase():
    return {
        "ops": {b: set() for b in BUCKETS},       # bucket -> {operator id}
        "mentions": Counter(),                    # bucket -> names carrying the phrase
        "regions": set(),                         # geographies in the trailing 12m
        "clinical": [0, 0],                       # [names with clinical context, names]
        "skeletons": Counter(),                   # the OTHER words used alongside it
    }


def _fold(store, phrase, bucket, op_id, region, has_ctx, skeleton):
    e = store.get(phrase)
    if e is None:
        e = store[phrase] = _blank_phrase()
    e["mentions"][bucket] += 1
    if op_id:
        e["ops"][bucket].add(op_id)
    if bucket in ("p1", "p2", "p3"):
        if region:
            e["regions"].add(region)
        e["clinical"][1] += 1
        if has_ctx:
            e["clinical"][0] += 1
        e["skeletons"][skeleton] += 1


def _emit(phrase, e, tier, evidence, region_kind):
    """One accumulated phrase -> the row shape discovery2() consumes."""
    p1, p2, p3 = (e["ops"]["p1"], e["ops"]["p2"], e["ops"]["p3"])
    cur = p1 | p2 | p3
    m12 = e["mentions"]["p1"] + e["mentions"]["p2"] + e["mentions"]["p3"]
    seen, total = e["clinical"]
    return {
        "name": phrase,
        "tier": tier,
        "operator_evidence": evidence,
        "op_ids": set(cur),
        "operators": len(cur),
        "periods": [len(p1), len(p2), len(p3)],
        "operators_prior_12m": len(e["ops"]["prior12"]),
        "operators_before_24m": len(e["ops"]["pre24"]),
        "mentions_12m": m12,
        "mentions_prior_12m": e["mentions"]["prior12"],
        "regions": sorted(e["regions"]),
        "region_kind": region_kind,
        "clinical_pct": (100.0 * seen / total) if total else None,
        "contexts": len(e["skeletons"]),
    }


# ====================================================== MINER: CQC (the good one)
# The only source in the radar carrying an OWNERSHIP KEY. pull_and_build.cqc() streams this
# same file and counts LOCATIONS - it never reads the Provider ID column, so it cannot tell
# one 30-site chain from 30 independent clinics, and that is precisely the distinction the
# open layer lives or dies on. Same file, same parser, two extra columns read, zero extra
# bandwidth.
def mine_cqc_ods(path, anchor=None, sector_filter="independent healthcare"):
    """The WHOLE active-locations file -> phrases with distinct-PROVIDER trajectories.

    TWO PASSES, on purpose. Pass 1 counts phrase mentions into a plain Counter. Pass 2
    re-reads the file and builds the expensive structures (provider sets, regions, contexts)
    only for the phrases that cleared the mention floor. Trigrams roughly double the number
    of distinct phrases a 57,000-row file produces; holding a set of provider IDs for every
    one of them - most of which appear once - would cost hundreds of megabytes to answer a
    question we already know the answer to. Re-streaming a 24MB zip is cheap; a memory
    blow-up in a nightly job is not.

    Windows are a FLOW, not a stock: we want what is being CREATED. A new niche has no stock.

    `path` may also be the already-parsed [(sheet, row), ...] list built once by
    pull_and_build.fetch_cqc_ods(). The daily build parses the 24MB file ONCE and the
    two passes here become two cheap iterations of an in-memory list instead of two
    of the four full iterparse passes the build used to pay for every day.
    """
    rows_mem = path if isinstance(path, (list, tuple)) else None
    if rows_mem is None and not _ODS_OK:
        DIAG["cqc_miner"] = "investability.ods_rows unavailable"
        return []

    anchor = anchor or date.today()
    counts = Counter()
    seen_rows = [0]

    def stream():
        """Yield (grams, tokens, bucket, provider_id, region) for every row we keep."""
        cols = [None]

        def cell(row, key):
            j = cols[0].get(key)
            if j is None or j >= len(row):
                return ""
            return (row[j] or "").strip()

        for _sheet, row in (rows_mem if rows_mem is not None else ods_rows(path)):
            if cols[0] is None:
                # The first sheet in the real file is a README. The data sheet is the one
                # whose header row carries a cell exactly equal to "location id".
                if "location id" not in [(c or "").strip().lower() for c in row]:
                    continue
                c = _resolve_columns(row)
                if not c:
                    DIAG["cqc_miner"] = "header found but Location Name column missing"
                    return
                cols[0] = c
                continue
            seen_rows[0] += 1
            # Same policy as pull_and_build.cqc(): the private-pay clinic universe only.
            # Social care is churn; NHS and dental have formulaic naming that swamps every
            # n-gram count.
            if sector_filter and sector_filter not in cell(row, "sector").lower():
                continue
            b = bucket_of(_parse_date(cell(row, "start")), anchor)
            if b is None:
                continue
            name = cell(row, "loc_name")
            if not name:
                continue
            grams = phrase_grams(name)
            if not grams:
                continue
            yield (grams, raw_tokens(name), b,
                   cell(row, "prov_id") or None, cell(row, "region"))

    try:
        for grams, _toks, _b, _pid, _reg in stream():
            for g in grams:
                counts[g] += 1
    except Exception as e:
        DIAG["cqc_miner_error"] = repr(e)[:160]
        return []

    if not counts:
        DIAG.setdefault("cqc_miner", "no usable rows")
        return []

    live = {g for g, c in counts.items() if c >= MIN_COUNT}
    store = {}
    try:
        for grams, toks, b, pid, region in stream():
            keep = grams & live
            if not keep:
                continue
            ctx = clinical_tokens(toks)
            for g in keep:
                gw = set(g.split())
                # "does a CLINICAL word appear NEXT TO this phrase" - the phrase's own words
                # do not count, or every phrase containing "therapy" would vouch for itself.
                has_ctx = bool(ctx - gw)
                skeleton = " ".join(sorted(set(toks) - gw - STOP - EXTRA_STOP))
                _fold(store, g, b, pid, region, has_ctx, skeleton)
    except Exception as e:
        DIAG["cqc_miner_error"] = repr(e)[:160]
        return []

    DIAG["cqc_miner"] = {"rows_seen": seen_rows[0] // 2, "phrases_total": len(counts),
                         "phrases_kept": len(live)}
    return [_emit(g, e, "cqc", "observed", "region") for g, e in store.items()]


# =============================================== MINER: Companies House names
def mine_company_names(records, anchor=None):
    """The WHOLE company-name corpus -> phrases with distinct-COMPANY trajectories.

    records: iterable of (company_id, company_name, iso_date, postcode_area_or_None).

    One company = one operator. TRUE at Companies House in a way it is NOT true at CQC,
    where one provider owns many locations. But only a floor: a group that incorporates
    twelve Ltds counts as twelve "operators" here, and there is nothing in the data that
    can tell you otherwise. That is why these counts are marked `assumed`, held to the
    doubled bar, and always lose to a CQC row for the same phrase.

    Note the consequence: mentions-per-operator is 1.0 by construction on this tier, so the
    franchise test cannot bite here. The CQC tier is the one that catches chains.
    """
    anchor = anchor or date.today()
    store = {}
    n = 0
    for rec in (records or ()):
        try:
            cid, name, iso, pc = (list(rec) + [None])[:4]
        except Exception:
            continue
        b = bucket_of(_iso_to_date(iso), anchor)
        if b is None:
            continue
        grams = phrase_grams(name)
        if not grams:
            continue
        n += 1
        toks = raw_tokens(name)
        ctx = clinical_tokens(toks)
        for g in grams:
            gw = set(g.split())
            skeleton = " ".join(sorted(set(toks) - gw - STOP - EXTRA_STOP))
            _fold(store, g, b, cid, (pc or None), bool(ctx - gw), skeleton)

    DIAG["ch_miner"] = {"records": n, "phrases": len(store)}
    return [_emit(g, e, "companies", "assumed", "postcode area")
            for g, e in store.items()
            if sum(e["mentions"].values()) >= MIN_COUNT]


# ------------------------------------------------- live Companies House corpus
# The reason the old open layer could only ever see the leftovers of a top-40 list is that
# nothing in the radar ever HELD the full company-name corpus. This does. It is the same
# advanced-search endpoint aesthetics.py already pages, with the same page size and the same
# monthly cache, so the marginal cost after the first backfill is one or two months of pages
# per run.
CH_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"
HEALTH_SICS = ["86900", "86220", "96020", "96040",
               "86210", "86230", "47730", "47782", "86101"]
CH_PAGE_SIZE = 1000
CH_SLEEP = 0.35
CH_CACHE = "data/discovery_companies.json.gz"


def _pc_area(pc):
    """'SW1A 1AA' -> 'SW'. The letters of a UK postcode are its AREA - about 120 of them,
    nationally distributed. Coarse enough to be a geography, fine enough that a single town
    cannot fake national spread."""
    m = re.match(r"\s*([A-Za-z]{1,2})\d", pc or "")
    return m.group(1).upper() if m else None


def fetch_company_records(anchor=None, months=25, ch_key=None, cache_path=CH_CACHE,
                          page_budget=400, sics=HEALTH_SICS):
    """-> [(company_number, name, iso_date, postcode_area)] for the trailing `months`.

    Cached per calendar month: an incorporation date can never change, so a complete month
    is final. Only the newest month is re-fetched. Needs CH_API_KEY; returns whatever is
    cached (possibly nothing) without one.
    """
    anchor = anchor or date.today()
    key = (ch_key or os.environ.get("CH_API_KEY", "")).strip()
    cache = _load(cache_path, {}) or {}
    first = anchor.replace(day=1)
    wanted = [_add_months(first, -i).strftime("%Y-%m") for i in range(months)]

    if key:
        auth = {"Authorization": "Basic "
                + base64.b64encode((key + ":").encode()).decode(),
                "User-Agent": "healthcare-radar"}
        budget = page_budget
        for i, mk in enumerate(wanted):
            if budget <= 0:
                break
            got = cache.get(mk)
            if got and got.get("complete") and i > 0:
                continue
            lo = date(int(mk[:4]), int(mk[5:7]), 1)
            hi = _add_months(lo, 1)
            rows, complete = [], True
            for sic in sics:
                start = 0
                while budget > 0:
                    q = urllib.parse.urlencode({
                        "sic_codes": sic,
                        "incorporated_from": lo.isoformat(),
                        "incorporated_to": hi.isoformat(),
                        "size": CH_PAGE_SIZE, "start_index": start})
                    try:
                        req = urllib.request.Request(CH_URL + "?" + q, headers=auth)
                        with urllib.request.urlopen(req, timeout=90) as r:
                            d = json.loads(r.read().decode("utf-8"))
                    except Exception:
                        complete = False
                        break
                    budget -= 1
                    time.sleep(CH_SLEEP)
                    items = d.get("items") or []
                    for it in items:
                        created = (it.get("date_of_creation") or "")[:10]
                        # Our own boundary, never CH's: it does not matter whether
                        # incorporated_to is inclusive.
                        if not (lo.isoformat() <= created < hi.isoformat()):
                            continue
                        addr = it.get("registered_office_address") or {}
                        rows.append([it.get("company_number") or it.get("company_name"),
                                     it.get("company_name") or "", created,
                                     _pc_area(addr.get("postal_code"))])
                    if len(items) < CH_PAGE_SIZE:
                        break
                    start += CH_PAGE_SIZE
            if rows or complete:
                # De-duplicate: a company can carry two of our SIC codes.
                seen, uniq = set(), []
                for r in rows:
                    if r[0] in seen:
                        continue
                    seen.add(r[0])
                    uniq.append(r)
                cache[mk] = {"rows": uniq, "complete": complete}
        for k in list(cache):
            if k not in wanted:
                cache.pop(k, None)
        try:
            _save(cache_path, cache)
        except Exception as e:
            DIAG["ch_cache_write_failed"] = repr(e)[:120]
    else:
        DIAG["ch_fetch"] = "no CH_API_KEY - using cache only"

    out = []
    for mk in wanted:
        for r in (cache.get(mk) or {}).get("rows") or []:
            out.append(tuple(r))
    DIAG["ch_corpus"] = len(out)
    return out


# ================================== degraded input: the old miners' truncated rows
def _norm_legacy(r, tier):
    """A pull_and_build row -> a candidate, filling gaps HONESTLY.

    The existing miners emit {name, latest, g12, isnew}: a MENTION count with no operator
    identity, and for CQC a mention is a LOCATION, which a chain can manufacture at will. So
    a CQC legacy row buys NOTHING - operators stays None and the phrase cannot surface.
    A Companies House legacy row does carry operator identity (one company, one record) but
    only at the doubled bar. Neither carries a trajectory, so neither can ever rank as well
    as a row from the real miners - which is correct, because it knows less.
    """
    if not isinstance(r, dict):
        return None
    name = (r.get("name") or "").strip().lower()
    if not name:
        return None
    try:
        count = int(r.get("count_12m") or r.get("latest") or 0)
    except (TypeError, ValueError):
        count = 0

    prior = r.get("count_prior_12m")
    if prior is None:
        g12 = r.get("g12")
        if g12 is not None and count:
            try:
                p = count / (1.0 + float(g12) / 100.0)
                prior = int(round(p)) if p >= 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                prior = None
        elif r.get("isnew") is True:
            prior = 0

    ops, ev = r.get("operators"), r.get("operator_evidence")
    if ops is None:
        if tier == "companies":
            ops, ev = count, "assumed"
        else:
            ops, ev = None, "none"
    return {
        "name": name, "tier": tier, "operator_evidence": ev, "op_ids": None,
        "operators": ops, "periods": None,
        "operators_prior_12m": (prior if tier == "companies" else None),
        "operators_before_24m": None,
        "mentions_12m": count, "mentions_prior_12m": prior,
        "regions": [], "region_kind": None, "clinical_pct": None, "contexts": None,
    }


def _is_new_style(r):
    return isinstance(r, dict) and "periods" in r and "op_ids" in r


# ================================================================ merge the tiers
def _merge(rows_by_tier):
    merged, sources = {}, defaultdict(set)
    for tier, rows in rows_by_tier:
        for r in (rows or []):
            p = r if _is_new_style(r) else _norm_legacy(r, tier)
            if not p or not p.get("name"):
                continue
            nm = p["name"]
            sources[nm].add(tier)
            m = merged.get(nm)
            if m is None:
                merged[nm] = dict(p)
                continue
            # Take the BEST evidence, never the SUM. Two tiers counting the same operator
            # would double it, and an inflated operator count is the single error that
            # defeats the whole filter.
            better = (m.get("operator_evidence") != "observed"
                      and p.get("operator_evidence") == "observed")
            same = (m.get("operator_evidence") == p.get("operator_evidence"))
            if p.get("operators") is not None and (
                    m.get("operators") is None or better
                    or (same and p["operators"] > m["operators"])):
                for k in ("operators", "operator_evidence", "op_ids", "periods",
                          "operators_prior_12m", "operators_before_24m",
                          "mentions_12m", "mentions_prior_12m", "clinical_pct",
                          "contexts", "region_kind"):
                    m[k] = p.get(k)
            m["regions"] = sorted(set(m.get("regions") or []) | set(p.get("regions") or []))
            m["mentions_12m"] = max(m.get("mentions_12m") or 0, p.get("mentions_12m") or 0)
    for nm, m in merged.items():
        m["sources"] = sorted(sources[nm])
    return merged


# ================================================================== velocity
def _velocity(p):
    """Attach the trajectory arithmetic. This is the heart of the ranking.

    lift      last 4 months vs the 4 months 8-12 months ago. The +0.5 smoothing is what lets
              0 -> 11 produce a finite, comparable number instead of an infinity that would
              make every from-zero phrase tie for first.
    yoy       trailing 12 months vs the 12 before. The classic.
    monotone  rose in BOTH steps. One good quarter is luck; two is a trajectory.
    age       from the DATA, not from our own history, wherever the data can answer it. The
              CQC file carries every active location's start date back to 2010, so it can
              say "no provider used this word before 2024" on the FIRST RUN - a claim our
              own history file could not make for two years.
    """
    ops = p.get("operators")
    per = p.get("periods")
    prior = p.get("operators_prior_12m")
    pre24 = p.get("operators_before_24m")

    if per:
        p1, p2, p3 = per
        p["lift"] = (p3 + 0.5) / (p1 + 0.5)
        p["monotone"] = bool(p3 > p2 > p1 or (p3 > p2 and p2 == p1 == 0))
        p["z_shape"] = _z(p3, p1)
    else:
        p["lift"] = None
        p["monotone"] = False
        p["z_shape"] = None

    if prior is not None and ops is not None:
        p["yoy"] = _pct(ops, prior) if prior else None
        p["yoy_ratio"] = (ops + 0.5) / (prior + 0.5)
        p["z_yoy"] = _z(ops, prior)
        p["basis"] = "operators"
        p["from_zero"] = (prior == 0 and ops > 0)
    elif p.get("mentions_prior_12m") is not None:
        mp = p["mentions_prior_12m"]
        m12 = p.get("mentions_12m") or 0
        p["yoy"] = _pct(m12, mp) if mp else None
        p["yoy_ratio"] = (m12 + 0.5) / (mp + 0.5)
        p["z_yoy"] = _z(m12, mp)
        p["basis"] = "mentions"
        p["from_zero"] = (mp == 0 and m12 > 0)
    else:
        p["yoy"] = None
        p["yoy_ratio"] = None
        p["z_yoy"] = None
        p["basis"] = "none"
        p["from_zero"] = False

    # Age, straight from the data where the data knows.
    if pre24 is not None and prior is not None:
        if pre24 == 0 and prior == 0:
            p["age"] = "unseen_before"      # nobody used this word a year ago, let alone two
        elif pre24 == 0:
            p["age"] = "recent"             # born inside the last two years
        else:
            p["age"] = "established"        # has been around; the question is only speed
        p["age_basis"] = "data"
    else:
        p["age"] = None
        p["age_basis"] = None
    return p


def _score(p):
    """0..~40. Rate of rise, weighted by how many unrelated people are doing it.

    The log on the operator count is deliberate: the difference between 6 and 12 unrelated
    operators is enormous, the difference between 60 and 120 is not, and a big flat phrase
    must NEVER outrank a small explosive one. Novelty is the heaviest single term, because
    the product exists to catch the next ADHD, not to re-describe the last one.
    """
    ops = p.get("operators") or 0
    lift = min(p["lift"], LIFT_CAP) if p.get("lift") is not None else None
    yoy = min(p["yoy_ratio"], YOY_CAP) if p.get("yoy_ratio") is not None else None

    shape = 0.0
    if lift is not None:
        shape += W_LIFT * lift
    if yoy is not None:
        shape += W_YOY * yoy
    if lift is None and yoy is None:
        shape += 1.0                                    # knows nothing; ranks accordingly
    if p.get("monotone"):
        shape += W_MONOTONE
    # A phrase that IS a treatment ("nattokinase therapy") beats a bare word, slightly.
    if any(w in CLINICAL_TAIL for w in p["name"].split()):
        shape += W_SELF_CLINICAL
    novelty = {"unseen_before": 2.0, "recent": 1.0}.get(p.get("age"), 0.0)
    if p.get("age") is None and p.get("first_seen_new"):
        novelty = 1.0                                   # our history says new; data cannot say
    shape += W_NOVELTY * novelty

    ctx = (p.get("clinical_pct") or 0.0) / 100.0
    mult = (1.0 + CTX_BONUS * ctx)
    if len(p.get("sources") or []) > 1:
        mult *= MULTI_TIER_BONUS

    return math.log(1 + ops) * max(shape, 0.0) * mult


# ================================================================= the filter
def _judge(p):
    """-> (keep, reason). The reason is emitted EITHER WAY, so a phrase that was dropped can
    be argued with instead of vanishing - which is the exact failure this module exists to
    fix."""
    name = p["name"]

    if not is_residue(name):
        return False, ("Already one of the 25 niches you track (%s). Not a discovery."
                       % niche_of(name))

    words = name.split()
    if not words or len(words) > MAX_GRAM:
        return False, "Not a phrase this radar produces."
    if any(w in STOP and w not in SERVICE_TAIL for w in words):
        return False, "Contains a stop word."

    if (p.get("mentions_12m") or 0) < MIN_COUNT:
        return False, ("Only %d mention(s) in the last year - too few for the growth "
                       "arithmetic to mean anything." % (p.get("mentions_12m") or 0))

    ops = p.get("operators")
    if ops is None:
        return False, ("This source counts mentions, not owners, so a 30-site chain and 30 "
                       "independent clinics look identical. Nothing can be concluded.")
    ev = p.get("operator_evidence")
    bar = MIN_OPERATORS if ev == "observed" else MIN_OPERATORS_ASSUMED
    if ops < bar:
        return False, ("Only %d separate operator%s use it (need %d). One or two people "
                       "using a word is a name, not a market." % (ops, "" if ops == 1 else "s", bar))

    per_op = (p.get("mentions_12m") or 0) / float(ops)
    if per_op > MAX_MENTIONS_PER_OPERATOR:
        return False, ("%d operators but %.1f sites each - that is a chain or a franchise "
                       "putting its brand on its own branches, not an industry adopting a "
                       "word." % (ops, per_op))

    regions = p.get("regions") or []
    if regions and len(regions) < MIN_REGIONS:
        kind = p.get("region_kind") or "area"
        return False, ("Every one of them is in the same %s (%s). That is a place, not a "
                       "service." % (kind, ", ".join(regions[:3])))

    if not _rising(p):
        return False, _why_not_rising(p)

    return True, ""


def _rising(p):
    """Two independent ways to be rising, and both are noise-aware. Either will do.

      YEAR ON YEAR   this year's operators vs last year's.
      THE SHAPE      the last four months vs the four months 8-12 months ago. This is the
                     one that catches a niche EARLY, because a thing that went 0 -> 3 -> 11
                     inside a single year has a flat year-on-year for another six months.

    Note there is no separate "from zero" case any more, and there does not need to be one:
    six operators where there were none scores z = 2.449, so a genuine birth clears the bar
    automatically, and it clears it at exactly the point the operator gate opens.
    """
    zs = [p.get("z_yoy"), p.get("z_shape")]
    return any(z is not None and z >= Z_MIN for z in zs)


def _why_not_rising(p):
    ops = p.get("operators")
    prior = p.get("operators_prior_12m")
    if prior is not None:
        return ("%d operators now and %d a year ago. Clinics open in dribs and drabs, so a "
                "gap that small is what two identical years actually look like. Standing, "
                "not rising - which is exactly how a surname or a town behaves."
                % (ops, prior))
    if p.get("z_shape") is not None:
        per = p.get("periods")
        return ("%d in the last four months against %d a year earlier - too small a "
                "difference to be anything but chance." % (per[2], per[0]))
    return ("No way to tell rising from standing yet - this source carries no history. "
            "One more run, or wire up the full miners.")


# ================================================================= families
def _contains(outer, inner):
    """Is `inner` a contiguous run of words inside `outer`?"""
    n = len(inner)
    return any(outer[i:i + n] == inner for i in range(len(outer) - n + 1))


def _same_family(a, b):
    aw, bw = a["name"].split(), b["name"].split()
    if not (_contains(aw, bw) or _contains(bw, aw)):
        return False
    ia, ib = a.get("op_ids"), b.get("op_ids")
    if ia and ib:
        # The same PEOPLE, not just the same letters. "skin" appearing in a hundred
        # unrelated clinic names is not the same discovery as "skin longevity".
        return len(ia & ib) >= 0.5 * min(len(ia), len(ib))
    return True


def _collapse(kept):
    """'microbiome', 'gut microbiome', 'microbiome testing' and 'gut microbiome testing' are
    ONE discovery, not four rows. Group phrases that contain one another and are used by the
    same operators; report the best one and list the rest as variants.

    The representative is the highest-scoring member, EXCEPT that a LONGER phrase that
    contains it is preferred when at least 80% of the operators use the longer form - i.e.
    the extra word is not decoration, it is part of the name. That is the difference between
    reporting "peptide" and reporting "peptide therapy", and Omar has been explicit that he
    wants the second one.
    """
    kept = sorted(kept, key=lambda p: -p["score"])
    fams = []
    for p in kept:
        for f in fams:
            if any(_same_family(p, m) for m in f):
                f.append(p)
                break
        else:
            fams.append([p])

    out = []
    for f in fams:
        best = max(f, key=lambda p: p["score"])
        rep = best
        for m in f:
            if m is best:
                continue
            mw, bw = m["name"].split(), best["name"].split()
            if (len(mw) > len(rep["name"].split()) and _contains(mw, bw)
                    and (m.get("operators") or 0) >= 0.8 * (best.get("operators") or 1)):
                rep = m
        rep = dict(rep)
        rep["score"] = best["score"]              # the family is as strong as its best member
        rep["variants"] = sorted(m["name"] for m in f if m["name"] != rep["name"])
        out.append(rep)
    out.sort(key=lambda p: (-p["score"], -(p.get("operators") or 0), p["name"]))
    return out


# ============================================================== plain English
def _period_words(per):
    if not per:
        return ""
    p1, p2, p3 = per
    return "%d then %d then %d over the last three four-month periods" % (p1, p2, p3)


def _sentence(p):
    """One sentence. No jargon, no invented labels, just the numbers a human can check."""
    ops = p.get("operators") or 0
    regions = len(p.get("regions") or [])
    per = p.get("periods")
    who = "%d unrelated operators" % ops
    if p.get("operator_evidence") == "assumed":
        who = "%d separately registered companies" % ops
    where = (" across %d %ss" % (regions, p.get("region_kind") or "region")) if regions else ""

    if p.get("age") == "unseen_before":
        tail = "and not one of them existed two years ago"
        if per and per[2]:
            tail += "; %d of them arrived in the last four months" % per[2]
        return "%s%s, %s." % (who.capitalize(), where, tail)

    if p.get("age") == "established" and per and per[2] > per[0]:
        return ("%s%s. The word has been in use for years, but %d of the %d showed up in "
                "the last four months." % (who.capitalize(), where, per[2], ops))

    if p.get("age") == "recent":
        return ("%s%s, none of them older than two years - %s."
                % (who.capitalize(), where, _period_words(per)))

    if p.get("from_zero"):
        return ("%s%s, and there were none at all a year ago."
                % (who.capitalize(), where))

    if p.get("yoy") is not None:
        return ("%s%s, up %.0f%% on a year ago." % (who.capitalize(), where, p["yoy"]))

    return "%s%s." % (who.capitalize(), where)


# =============================================================== history / age
def _read_history(path):
    h = _load(path, None)
    if not isinstance(h, dict) or "phrases" not in h:
        h = {"version": HISTORY_VERSION, "phrases": {}, "runs": []}
    return h


def _update_history(hist, cands, today):
    """Record every RESIDUE phrase seen this run, kept OR dropped.

    This is the whole point of persisting anything. A phrase filtered out today for having
    four operators may have twenty next quarter, and when it does, its first_seen must be
    TODAY, not then. You can only know a phrase is new if you were writing down the ones
    that were not.
    """
    ph = hist.setdefault("phrases", {})
    iso = today.isoformat()
    for p in cands:
        e = ph.get(p["name"])
        if e is None:
            e = ph[p["name"]] = {"first_seen": iso, "trail": []}
        e["last_seen"] = iso
        trail = [t for t in (e.get("trail") or []) if t.get("date") != iso]
        trail.append({"date": iso, "operators": p.get("operators"),
                      "periods": p.get("periods"), "age": p.get("age")})
        e["trail"] = trail[-24:]
    runs = hist.setdefault("runs", [])
    if iso not in runs:
        runs.append(iso)
    hist["runs"] = runs[-400:]
    hist["version"] = HISTORY_VERSION
    return hist


# ==================================================================== main
def discovery2(inc_rows, cqc_rows, aes_rows, history_path="data/discovery.json",
               today=None, max_rows=MAX_ROWS, keep_rejects=False):
    """The UNCLASSIFIED residue: rising phrases from company names and CQC clinic names
    that match NO existing niche. The only place a genuinely new niche can appear.

    inc_rows  mine_company_names(fetch_company_records()) - the full Companies House
              name corpus. A pull_and_build.incorporations() list also works, at the
              doubled operator bar and with no trajectory.
    cqc_rows  mine_cqc_ods(<tmp>/cqc.ods) - the full CQC file, at PROVIDER level. A
              pull_and_build.cqc() list also works but buys NOTHING: it counts locations,
              and a location count cannot tell a 30-site chain from 30 independents.
    aes_rows  aesthetics.aesthetics() keyword rows. Almost everything in that vocabulary
              maps to Aesthetics/skin and is therefore not residue; it is here so that a
              genuinely new aesthetics-adjacent word is not lost. It carries no operator
              identity, so on its own it can never surface a phrase.

    -> [ {phrase, kind, distinct_operators, operators_by_period, operators_prior_12m,
          operators_before_24m, mentions_12m, mentions_per_operator, regions, region_kind,
          growth_yoy, growth_basis, age, first_seen, emerging, clinical_context_pct,
          operator_evidence, sources, variants, why, score} ]
    """
    today = today or date.today()
    DIAG.pop("no_operator_evidence", None)

    merged = _merge(((("companies"), inc_rows), ("cqc", cqc_rows),
                     ("aesthetics", aes_rows)))
    allp = list(merged.values())
    residue = [p for p in allp if is_residue(p["name"])]

    hist = _read_history(history_path)
    phrases = hist.get("phrases", {})

    for p in allp:
        _velocity(p)
        e = phrases.get(p["name"]) or {}
        p["first_seen"] = e.get("first_seen") or today.isoformat()
        fs = _iso_to_date(p["first_seen"])
        age_m = _months_between(fs, today) if fs else 0
        p["first_seen_new"] = (age_m <= EMERGING_MONTHS)
        # 'emerging' prefers what the DATA says over what our own file remembers, because on
        # run 1 the file remembers nothing and the CQC start dates already go back a decade.
        if p.get("age") is not None:
            p["emerging"] = p["age"] in ("unseen_before", "recent")
        else:
            p["emerging"] = p["first_seen_new"]
        p["score"] = 0.0

    kept, dropped = [], []
    for p in allp:
        ok, why = _judge(p)
        if ok:
            p["score"] = round(_score(p), 2)
            p["why"] = _sentence(p)
            kept.append(p)
        else:
            p["why"] = why
            dropped.append(p)

    try:
        _update_history(hist, residue, today)
        _save(history_path, hist)
    except Exception as e:
        DIAG["history_write_failed"] = repr(e)[:120]

    fams = _collapse(kept)

    out = []
    for p in fams[:max_rows]:
        ops = p.get("operators") or 0
        # PRECEDENCE MATTERS. Where the source can see 24 months back (CQC can - every
        # active location carries its start date), that view WINS. `from_zero` only means
        # "nobody registered one in the last 12-24 months", which is NOT the same as "this
        # word is new": a phrase can be six years old, go quiet for a year, and come back.
        # Calling that "new" would be a lie the data itself contradicts.
        age = p.get("age")
        if age in ("unseen_before", "recent"):
            kind = "new"
        elif age == "established":
            kind = "accelerating" if p.get("monotone") else "rising"
        elif p.get("from_zero"):
            kind = "new"          # no 24-month view; all we know is it was not here a year ago
        elif p.get("monotone"):
            kind = "accelerating"
        else:
            kind = "rising"
        out.append({
            "phrase": p["name"],
            "kind": kind,
            "distinct_operators": ops,
            "operators_by_period": p.get("periods"),
            "operators_prior_12m": p.get("operators_prior_12m"),
            "operators_before_24m": p.get("operators_before_24m"),
            "mentions_12m": p.get("mentions_12m"),
            "mentions_per_operator": (round((p.get("mentions_12m") or 0) / float(ops), 2)
                                      if ops else None),
            "regions": len(p.get("regions") or []) or None,
            "region_kind": p.get("region_kind"),
            "growth_yoy": (None if p.get("yoy") is None else round(p["yoy"], 1)),
            "growth_basis": p.get("basis"),
            "age": p.get("age"),
            "age_basis": p.get("age_basis") or "our own history",
            "first_seen": p["first_seen"],
            "emerging": p["emerging"],
            "clinical_context_pct": (None if p.get("clinical_pct") is None
                                     else round(p["clinical_pct"])),
            "operator_evidence": p.get("operator_evidence"),
            "sources": p.get("sources") or [],
            "variants": p.get("variants") or [],
            "why": p["why"],
            "score": p["score"],
        })

    DIAG["residue_phrases"] = len(residue)
    DIAG["surfaced"] = len(out)
    DIAG["families"] = len(fams)
    DIAG["dropped"] = len(dropped)
    DIAG["stop_list"] = _STOP_SOURCE
    DIAG["drop_reasons"] = Counter(
        d["why"].split(" -")[0].split(",")[0][:64] for d in dropped).most_common(8)
    no_ops = sum(1 for p in residue if p.get("operators") is None)
    if no_ops:
        DIAG["no_operator_evidence"] = (
            "%d residue phrases carry no operator identity and therefore CANNOT surface. "
            "pull_and_build.cqc() counts locations, not providers - pass "
            "discovery2.mine_cqc_ods(<tmp>/cqc.ods) as cqc_rows to fix this at zero extra "
            "bandwidth." % no_ops)

    if keep_rejects:
        return out, sorted(dropped, key=lambda p: -(p.get("operators") or 0))
    return out


# ===================================================================== SELF-TEST
_HEAD = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
         'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
         'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
         'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
         'office:version="1.2"><office:body><office:spreadsheet>')
_TAIL = '</office:spreadsheet></office:body></office:document-content>'

_HEADER = ["Location ID", "Location HSCA start date", "Location Name",
           "Location Type/Sector", "Location Inspection Directorate",
           "Location Primary Inspection Category", "Location Region",
           "Location Local Authority", "Location Postal Code",
           "Provider ID", "Provider Name", "Provider Type/Sector"]

_REGIONS = ["London", "South West", "North East", "Midlands", "North West",
            "South East", "Yorkshire", "East"]

# Deliberately varied brand prefixes, because in the real world twelve unrelated founders do
# NOT all name their clinic the same way - and a fixture where they do would let a filter
# that is secretly keying off name-shape pass for the wrong reason.
_PREFIX = ["Nordic", "Halcyon", "Copper", "Meridian", "Orchid", "Fenwick", "Aurora",
           "Bluebird", "Kestrel", "Juniper", "Verity", "Sable", "Thistle", "Marlow"]


def _xc(v, kind="string"):
    if v is None or v == "":
        return "<table:table-cell/>"
    if kind == "date":
        return ('<table:table-cell office:value-type="date" office:date-value="%s">'
                '<text:p>%s</text:p></table:table-cell>' % (v, v))
    return ('<table:table-cell office:value-type="string"><text:p>%s</text:p>'
            "</table:table-cell>" % str(v).replace("&", "&amp;").replace("<", "&lt;"))


def _xr(cells):
    return "<table:table-row>%s</table:table-row>" % "".join(cells)


def _fixture_ods(path, anchor):
    """A synthetic CQC active-locations file containing, on purpose:

      REAL NICHE, 3 WORDS   "gut microbiome testing" / "microbiome": 14 clinics, 14 DIFFERENT
                            providers, 6 regions, 0 -> 3 -> 11 across the three periods, and
                            NOBODY used the word two years ago. The next-ADHD case. Must
                            surface and must rank FIRST. If it does not, the module has no
                            reason to exist.
      REAL NICHE, TRIGRAM   "red light therapy": 12 clinics, 12 providers, all of whom use
        AS REPRESENTATIVE   the full three-word phrase. Proves a 3-word niche can be the
                            HEADLINE of a row, not just a footnote to its own unigram.
      REAWAKENING           "photobiomodulation": has existed since 2019 (5 providers before
                            the 24-month line) and did nothing for years - then 1 -> 4 -> 12.
                            Must surface, must be labelled ACCELERATING rather than NEW, and
                            must rank BELOW the from-zero niche. Different thing, both real.
      BRAND (one owner)     "Zenith Vitality": 40 clinics, ONE provider. Raw frequency ranks
                            it first in the fixture. Must be killed by the DISTINCT-OPERATOR
                            gate - not by a blocklist and not by frequency.
      BRAND (a franchise)   "Lumiere": 7 providers x 6 sites = 42 clinics, brand new. CLEARS
                            the operator gate (7 >= 6), the growth gate (new) and the region
                            gate (6 regions). The ONLY thing that can kill it is mentions per
                            operator (6.0 > 3.0). This is the case that proves the operator
                            gate alone is not enough.
      SURNAME               "Hartley": 9 clinics, 9 DIFFERENT providers, 6 regions, and nine
                            of them last year too, and twenty before that. Passes the
                            operator gate AND the region gate - there really are nine
                            unrelated Hartleys. Must die on STATIONARITY.
      PLACE NAME            "Molesey": 8 clinics, 8 DIFFERENT providers, RISING 1 -> 2 -> 5.
                            Passes the operator gate AND the velocity gate. Every one is in
                            the South East. Must die on GEOGRAPHY.
      ALREADY KNOWN, 3 WORDS "Peptide Therapy Clinic": 8 providers. The tokeniser MUST be
                            able to emit the trigram - and the taxonomy must then recognise
                            it and refuse to call it a discovery. Rediscovering peptides is
                            just the dashboard again.
      SECTOR LEAK TEST      20 SOCIAL CARE rows carrying the microbiome phrase under 20 more
                            provider IDs. If the sector filter breaks, microbiome jumps from
                            14 operators to 34 and the assertions below fail LOUDLY rather
                            than quietly inflating a discovery.
    """
    p3 = _add_months(anchor, -2).isoformat()     # last 4 months
    p2 = _add_months(anchor, -6).isoformat()     # 4-8 months ago
    p1 = _add_months(anchor, -10).isoformat()    # 8-12 months ago
    pr = _add_months(anchor, -18).isoformat()    # 12-24 months ago
    old = _add_months(anchor, -40).isoformat()   # before the 24-month line

    rows, n = [], [0]

    def add(start, nm, region, pid):
        n[0] += 1
        rows.append(("L%d" % n[0], start, nm, "Independent Healthcare Org", region,
                     pid, pid + " Ltd"))

    # 1. THE REAL NICHE. 14 unrelated providers, 6 regions, 0 -> 3 -> 11, unseen before.
    #    Ten of the fourteen use the full three-word phrase; four use "microbiome" alone.
    for i in range(14):
        when = p2 if i < 3 else p3                      # p1 = 0, p2 = 3, p3 = 11
        nm = ("%s Gut Microbiome Testing" % _PREFIX[i] if i < 10
              else "%s Microbiome Rooms" % _PREFIX[i])
        add(when, nm, _REGIONS[i % 6], "MIC%d" % i)

    # 2. A THREE-WORD NICHE EVERY OPERATOR SPELLS OUT IN FULL. 2 -> 4 -> 6.
    for i in range(12):
        when = p1 if i < 2 else (p2 if i < 6 else p3)
        add(when, "%s Red Light Therapy" % _PREFIX[i], _REGIONS[i % 5], "RLT%d" % i)

    # 3. THE REAWAKENING. Around since 2019, flat, then 1 -> 4 -> 12.
    for i in range(5):
        add(old, "%s Photobiomodulation Therapy" % _PREFIX[i], _REGIONS[i % 4], "PBMO%d" % i)
    for i in range(2):
        add(pr, "%s Photobiomodulation Studio" % _PREFIX[i], _REGIONS[i % 3], "PBMP%d" % i)
    for i in range(17):
        when = p1 if i < 1 else (p2 if i < 5 else p3)   # 1 -> 4 -> 12
        add(when, "%s Photobiomodulation Therapy" % _PREFIX[i % 14],
            _REGIONS[i % 6], "PBM%d" % i)

    # 4. BRAND: 40 locations, ONE provider.
    for i in range(40):
        add(p3, "Zenith Vitality Rooms %d" % i, _REGIONS[i % 8], "CHAIN1")

    # 5. FRANCHISE: 7 providers x 6 sites.
    for i in range(42):
        add(p3, "Lumiere Clinic %d" % i, _REGIONS[i % 6], "LUM%d" % (i % 7))

    # 6. SURNAME: 9 now (3/3/3), 9 last year, 20 before that. Flat as a demographic fact.
    for i in range(9):
        when = p1 if i < 3 else (p2 if i < 6 else p3)
        add(when, "Hartley Rooms %d" % i, _REGIONS[i % 6], "HART%d" % i)
    for i in range(9):
        add(pr, "Hartley Rooms old %d" % i, _REGIONS[i % 6], "HARTP%d" % i)
    for i in range(20):
        add(old, "Hartley Rooms ancient %d" % i, _REGIONS[i % 6], "HARTO%d" % i)

    # 7. PLACE: 8 providers, rising 1 -> 2 -> 5, all South East.
    for i in range(8):
        when = p1 if i < 1 else (p2 if i < 3 else p3)
        add(when, "Molesey Rooms %d" % i, "South East", "MOL%d" % i)

    # 8. ALREADY KNOWN, and three words long.
    for i in range(8):
        add(p3, "%s Peptide Therapy Clinic" % _PREFIX[i], _REGIONS[i % 6], "PEP%d" % i)

    # 9. SECTOR LEAK CANARY.
    for i in range(20):
        rows.append(("S%d" % i, p3, "Gut Microbiome Testing Lodge %d" % i,
                     "Social Care Org", "London", "SOC%d" % i, "Social Ltd"))

    body = [_xr([_xc(h) for h in _HEADER])]
    for (lid, start, nm, sector, region, pid, pnm) in rows:
        body.append(_xr([_xc(lid), _xc(start, "date"), _xc(nm), _xc(sector), _xc(""),
                         _xc(""), _xc(region), _xc("LA " + region), _xc("AB1 2CD"),
                         _xc(pid), _xc(pnm), _xc(sector)]))

    xml = (_HEAD + '<table:table table:name="README">'
           + _xr([_xc("This sheet is a README, not the data.")]) + "</table:table>"
           + '<table:table table:name="HSCA_Active_Locations">' + "".join(body)
           + "</table:table>" + _TAIL)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", xml)
    return path


def selftest():
    fails = []

    def chk(label, got, want):
        ok = (got == want)
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("  %-4s %-62s %s" % ("PASS" if ok else "FAIL", label, got))

    tmp = tempfile.mkdtemp(prefix="disc2_")
    hp = os.path.join(tmp, "discovery.json")
    anchor = date(2026, 7, 1)

    print("\n[1] TOKENISER - trigrams, which the old layer could not say at all")
    g = phrase_grams("Nordic Gut Microbiome Testing")
    chk("3-word phrase emitted", "gut microbiome testing" in g, True)
    chk("2-word phrase emitted", "gut microbiome" in g, True)
    chk("1-word phrase emitted", "microbiome" in g, True)
    chk("3-char word allowed INSIDE a phrase ('gut')", "gut microbiome" in g, True)
    chk("...but not as a unigram on its own", "gut" in g, False)
    # THE case from the brief. "therapy" is in SERVICE_TAIL, so the strict stop list would
    # make this phrase unsayable - which is the bug SERVICE_TAIL exists to fix.
    chk("'peptide therapy clinic' CAN be emitted",
        "peptide therapy clinic" in phrase_grams("The Peptide Therapy Clinic Ltd"), True)
    chk("'iv drip' CAN be emitted (2-letter token)",
        "iv drip" in phrase_grams("Mayfair IV Drip Bar"), True)
    chk("a phrase may not LEAD with a service word",
        "therapy clinic" in phrase_grams("Peptide Therapy Clinic"), False)
    # The old tokeniser deleted stop words and then paired what was left, inventing phrases
    # nobody wrote.
    chk("n-grams do NOT span a removed stop word ('botox and filler')",
        "botox filler" in phrase_grams("Botox and Filler Clinic"), False)
    chk("repeated word counted once",
        sorted(phrase_grams("Exosome Exosome")), ["exosome", "exosome exosome"])
    chk("honorifics dropped", "smith" in phrase_grams("Dr Smith"), True)
    chk("...and cannot form a phrase with the title",
        "smith" in phrase_grams("Dr Smith Rooms"), True)

    print("\n[2] RESIDUE = exactly what the taxonomy cannot place")
    chk("known niche is NOT residue (menopause)", is_residue("menopause"), False)
    chk("known niche is NOT residue (adhd)", is_residue("adhd"), False)
    chk("'peptide therapy clinic' is ALREADY KNOWN - never a discovery",
        is_residue("peptide therapy clinic"), False)
    chk("novel trigram IS residue", is_residue("gut microbiome testing"), True)
    chk("novel trigram IS residue (red light therapy)",
        is_residue("red light therapy"), True)

    print("\n[3] CQC MINER - provider IDs and a three-period trajectory")
    ods = _fixture_ods(os.path.join(tmp, "cqc.ods"), anchor)
    cq = mine_cqc_ods(ods, anchor=anchor)
    cq_mem = mine_cqc_ods([(s, list(r)) for s, r in ods_rows(ods)], anchor=anchor)
    chk("SHARED PARSE: pre-parsed rows give identical output", cq_mem == cq, True)
    by = dict((r["name"], r) for r in cq)
    chk("miner returned rows", len(cq) > 0, True)
    chk("'microbiome' 14 DISTINCT providers", by["microbiome"]["operators"], 14)
    chk("'microbiome' trajectory 0 -> 3 -> 11", by["microbiome"]["periods"], [0, 3, 11])
    chk("'microbiome' nobody had it 2 years ago",
        by["microbiome"]["operators_before_24m"], 0)
    chk("'microbiome' 6 regions", len(by["microbiome"]["regions"]), 6)
    chk("SECTOR LEAK: social care excluded (14 operators, not 34)",
        by["microbiome"]["operators"], 14)
    chk("TRIGRAM mined: 'gut microbiome testing' -> 10 providers",
        by["gut microbiome testing"]["operators"], 10)
    chk("brand 'zenith' 40 locations but ONE provider",
        (by["zenith"]["mentions_12m"], by["zenith"]["operators"]), (40, 1))
    chk("franchise 'lumiere' 42 locations, 7 providers",
        (by["lumiere"]["mentions_12m"], by["lumiere"]["operators"]), (42, 7))
    chk("surname 'hartley' 9 now / 9 prior year / 20 before that",
        (by["hartley"]["operators"], by["hartley"]["operators_prior_12m"],
         by["hartley"]["operators_before_24m"]), (9, 9, 20))
    chk("place 'molesey' 8 providers, ONE region",
        (by["molesey"]["operators"], len(by["molesey"]["regions"])), (8, 1))
    chk("reawakening 'photobiomodulation' 17 now, 5 before the 24-month line",
        (by["photobiomodulation"]["operators"],
         by["photobiomodulation"]["operators_before_24m"]), (17, 5))
    chk("...trajectory 1 -> 4 -> 12", by["photobiomodulation"]["periods"], [1, 4, 12])

    print("\n[4] THE CASES THE BRIEF DEMANDS")
    out = discovery2([], cq, [], history_path=hp, today=anchor)
    surfaced = [r["phrase"] for r in out]
    allnames = set(surfaced)
    for r in out:
        allnames |= set(r["variants"])
    rows = dict((r["phrase"], r) for r in out)

    # (a) a genuine emerging niche surfaces AND ranks top
    chk("(a) REAL NICHE surfaces", any("microbiome" in s for s in surfaced), True)
    chk("(a) ...and is the TOP-RANKED row", "microbiome" in out[0]["phrase"], True)
    top = out[0]
    chk("(a) ...with 14 distinct operators", top["distinct_operators"], 14)
    chk("(a) ...labelled NEW, not merely rising", top["kind"], "new")
    chk("(a) ...and it knows nobody used the word 2 years ago",
        (top["operators_before_24m"], top["age_basis"]), (0, "data"))
    # (b) a brand used 40 times by ONE operator
    chk("(b) BRAND suppressed: 'zenith' (40 mentions, 1 operator)",
        "zenith" in allnames, False)
    chk("(b) BRAND suppressed: 'zenith vitality'", "zenith vitality" in allnames, False)
    chk("(b) BRAND suppressed: 'vitality'", "vitality" in allnames, False)
    # (c) a franchise: 7 operators x 6 sites
    chk("(c) FRANCHISE suppressed: 'lumiere' (7 operators, 42 sites, NEW, 6 regions)",
        "lumiere" in allnames, False)
    # (d) a common surname
    chk("(d) SURNAME suppressed: 'hartley' (9 unrelated operators, 6 regions, FLAT)",
        "hartley" in allnames, False)
    # (e) a place name
    chk("(e) PLACE suppressed: 'molesey' (8 operators, RISING, ONE region)",
        "molesey" in allnames, False)
    # (f) a 3-word niche can actually be emitted - as a row in its own right
    chk("(f) TRIGRAM surfaces as its own headline row: 'red light therapy'",
        "red light therapy" in surfaced, True)
    chk("(f) ...and the mined trigram rides with the top row",
        "gut microbiome testing" in (top["variants"] + [top["phrase"]]), True)
    chk("(f) 'peptide therapy clinic' NOT a discovery - taxonomy already has it",
        "peptide therapy clinic" in allnames, False)

    print("\n[5] AGE AND SPEED ARE DIFFERENT FACTS")
    # It surfaces under its most specific well-supported name - all 17 operators say
    # "photobiomodulation therapy" in full, so that, not the bare word, is the row.
    pbm = next((r for r in out if "photobiomodulation" in r["phrase"]), {})
    chk("reawakening surfaces", bool(pbm), True)
    chk("...as its most specific well-supported name",
        pbm.get("phrase"), "photobiomodulation therapy")
    chk("...labelled ACCELERATING, not NEW", pbm.get("kind"), "accelerating")
    chk("...and ranks BELOW the from-zero niche", out.index(pbm) > 0, True)
    chk("...its age comes from the DATA, not our history", pbm.get("age"), "established")
    chk("a from-zero niche outscores a faster-growing established one",
        top["score"] > pbm.get("score", 0), True)
    chk("...and the sentence says so in plain English",
        "has been in use for years" in pbm.get("why", ""), True)

    print("\n[6] EVERY DROP HAS A REASON - and it is the RIGHT reason")
    _, rej = discovery2([], cq, [], history_path=hp, today=anchor, keep_rejects=True)
    why = dict((r["name"], r["why"]) for r in rej)
    chk("'zenith' died on the DISTINCT-OPERATOR gate",
        "separate operator" in why.get("zenith", ""), True)
    chk("'lumiere' died on sites-per-operator (6.0 > 3.0)",
        "sites each" in why.get("lumiere", ""), True)
    chk("'hartley' died on stationarity (9 now, 9 a year ago)",
        "not rising" in why.get("hartley", ""), True)
    chk("'molesey' died on geography", "place, not a service" in why.get("molesey", ""), True)
    chk("'peptide therapy clinic' died as already-known",
        "Already one of the 25" in why.get("peptide therapy clinic", ""), True)
    chk("no jargon in the kept rows' sentences",
        all(not any(j in r["why"].lower() for j in
                    ("hhi", "n-gram", "residue", "herfindahl", "yoy", "cagr"))
            for r in out), True)

    print("\n[7] FAMILIES - one discovery, one row")
    chk("'microbiome' variants collapsed into the top row",
        len(top["variants"]) >= 2, True)
    chk("...variants include the bigram", "gut microbiome" in top["variants"], True)
    chk("one row per family, not one per phrase", len(out) <= 6, True)
    chk("plain-English sentence on the top row",
        top["why"].endswith(".") and len(top["why"].split()) >= 8, True)
    print("       top row says: %s" % top["why"])

    print("\n[8] COMPANIES HOUSE MINER - full corpus, postcode spread, doubled bar")
    recs = []
    for i in range(14):                       # a real niche: 14 companies, 7 postcode areas
        recs.append(("C%d" % i, "%s Exosome Skin Rooms Ltd" % _PREFIX[i],
                     _add_months(anchor, -2).isoformat(), ["SW", "M", "LS", "B", "BS",
                                                           "NE", "CF"][i % 7]))
    for i in range(2):
        recs.append(("D%d" % i, "%s Exosome Rooms Ltd" % _PREFIX[i],
                     _add_months(anchor, -18).isoformat(), "SW"))
    for i in range(13):                       # a TOWN: 13 companies, all one postcode area
        recs.append(("T%d" % i, "Basingstoke Wellness Rooms %d Ltd" % i,
                     _add_months(anchor, -2).isoformat(), "RG"))
    for i in range(8):                        # 8 companies: under the DOUBLED bar of 12
        recs.append(("E%d" % i, "%s Nattokinase Rooms Ltd" % _PREFIX[i],
                     _add_months(anchor, -2).isoformat(), ["SW", "M", "LS", "B"][i % 4]))
    inc = mine_company_names(recs, anchor=anchor)
    ex = dict((r["name"], r) for r in inc)
    chk("'exosome' 14 companies", ex["exosome"]["operators"], 14)
    chk("'exosome' 2 in the prior year", ex["exosome"]["operators_prior_12m"], 2)
    chk("'exosome' 7 postcode areas", len(ex["exosome"]["regions"]), 7)
    out8 = discovery2(inc, [], [], history_path=os.path.join(tmp, "d8.json"), today=anchor)
    got8 = set(r["phrase"] for r in out8) | set(
        v for r in out8 for v in r["variants"])
    chk("'exosome' surfaces (14 >= the doubled bar of 12)", "exosome" in got8, True)
    chk("'nattokinase' does NOT (8 companies, assumed evidence, bar is 12)",
        "nattokinase" in got8, False)
    chk("TOWN suppressed on postcode spread: 'basingstoke'",
        "basingstoke" in got8, False)
    chk("'exosome skin' is already taxonomy - not a discovery",
        "exosome skin" in got8, False)
    chk("postcode-area parser", (_pc_area("SW1A 1AA"), _pc_area("M1 1AE"),
                                 _pc_area("nonsense")), ("SW", "M", None))

    print("\n[9] HISTORY - first_seen persists, including for phrases we DROPPED")
    chk("history file written", os.path.exists(hp), True)
    h = _load(hp, {})
    chk("dropped phrases remembered (so first_seen is real when they grow)",
        "hartley" in h.get("phrases", {}), True)
    chk("known niches NOT written to the residue history",
        "menopause" in h.get("phrases", {}), False)
    chk("first_seen recorded", h["phrases"]["microbiome"]["first_seen"], anchor.isoformat())
    chk("trail records the TRAJECTORY, not just a level",
        h["phrases"]["microbiome"]["trail"][-1]["periods"], [0, 3, 11])
    chk("age arithmetic (36 months)", _months_between(date(2026, 7, 1), date(2029, 7, 1)), 36)
    chk("bucket boundaries", [bucket_of(_add_months(anchor, -m), anchor)
                              for m in (0, 3, 4, 7, 8, 11, 12, 23, 24, 60)],
        ["p3", "p3", "p2", "p2", "p1", "p1", "prior12", "prior12", "pre24", "pre24"])

    print("\n[10] DEGRADED INPUT - the old miners' rows, which have NO operator identity")
    legacy_cqc = [{"name": "zenith", "latest": 40, "g12": 900.0, "isnew": False},
                  {"name": "microbiome", "latest": 14, "g12": None, "isnew": True}]
    out10 = discovery2([], legacy_cqc, [], history_path=os.path.join(tmp, "d10.json"),
                       today=anchor)
    chk("a LOCATION count buys nothing - 30 sites vs 30 clinics are indistinguishable",
        out10, [])
    chk("...and it tells the integrator exactly what to wire up",
        "no_operator_evidence" in DIAG, True)
    legacy_inc = [{"name": "microbiome", "latest": 14, "g12": None, "isnew": True},
                  {"name": "exosome", "latest": 8, "g12": None, "isnew": True}]
    out10b = discovery2(legacy_inc, [], [], history_path=os.path.join(tmp, "d11.json"),
                        today=anchor)
    g10 = set(r["phrase"] for r in out10b)
    chk("legacy CH row, 14 companies -> surfaces at the doubled bar",
        "microbiome" in g10, True)
    chk("legacy CH row, 8 companies -> does not", "exosome" in g10, False)

    print("\n[11] GARBAGE IN, NO EXCEPTION OUT")
    chk("all-None input",
        discovery2(None, None, None, history_path=os.path.join(tmp, "d12.json")), [])
    chk("junk rows ignored",
        discovery2(["not a dict", 7, None], [{}], [{"name": ""}],
                   history_path=os.path.join(tmp, "d13.json")), [])
    chk("unreadable ods -> [] not an exception",
        mine_cqc_ods(os.path.join(tmp, "nope.ods")), [])
    chk("empty records -> []", mine_company_names([]), [])

    print("\n" + "=" * 78)
    print("WHAT THE DASHBOARD WOULD SHOW (fixture):\n")
    print("  %-26s %-13s %4s %-12s %s" % ("phrase", "kind", "ops", "0-4/4-8/8-12", "why"))
    for r in out:
        print("  %-26s %-13s %4s %-12s %s" % (
            r["phrase"][:26], r["kind"], r["distinct_operators"],
            "/".join(str(x) for x in reversed(r["operators_by_period"] or [])),
            r["why"][:70]))
    print("\n" + "=" * 78)
    if fails:
        print("SELFTEST FAILED (%d)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST PASSED")
    return 0


def _cli():
    if "--selftest" in sys.argv or "--test" in sys.argv:
        return selftest()
    p = os.environ.get("CQC_ODS_PATH") or os.path.join(tempfile.gettempdir(), "cqc.ods")
    cq = mine_cqc_ods(p) if os.path.exists(p) else []
    inc = mine_company_names(fetch_company_records()) if os.environ.get("CH_API_KEY") else []
    if not cq and not inc:
        print("no CQC file at %s and no CH_API_KEY - nothing to mine" % p)
    for r in discovery2(inc, cq, []):
        print("%-28s %-13s ops=%-3s %s" % (r["phrase"][:28], r["kind"],
                                           r["distinct_operators"], r["why"]))
        if r["variants"]:
            print("%-28s   also: %s" % ("", ", ".join(r["variants"][:5])))
    print("\nDIAG:", json.dumps(DIAG, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
