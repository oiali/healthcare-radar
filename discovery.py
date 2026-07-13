#!/usr/bin/env python3
"""
DISCOVERY - the open layer. The only place a niche you have not pre-listed can appear.

WHY THIS EXISTS
---------------
taxonomy.py holds 25 FIXED niches. niche_of(phrase) maps a phrase onto one of them, or
returns None. Every miner in the radar - the Companies House name n-grams, the CQC clinic
name n-grams, the aesthetics keyword index - runs niche_of over the phrases it finds and
reports them GROUPED BY NICHE. A phrase that matches nothing is not reported. It is
silently discarded.

That is a closed system. It can re-rank the 25 niches somebody already thought of. It
cannot surface the 26th. If ADHD had not been on the list in 2019, this radar would have
watched thousands of ADHD clinics incorporate and shown you nothing, because "adhd" would
have been an unclassified token dropped on the floor.

This module keeps the floor sweepings. The UNCLASSIFIED RESIDUE - every phrase rising in
company names and clinic names that maps to NO existing niche - is the only place a
genuinely new niche can be. Everything else on the dashboard is, by construction, a thing
you already knew about.

THE HARD PART IS NOT FINDING PHRASES. IT IS THROWING THEM AWAY.
--------------------------------------------------------------
The residue is mostly rubbish: founders' surnames (Skinner, Hartley), towns (Molesey),
brand words (Zenith, Lumiere) and generic business vocabulary. Hard-coding a blocklist of
surnames and place names is not a real answer - it is just a second closed system, and it
fails the moment a founder is called something you did not list. So the filter here is
STRUCTURAL, not lexical. Four properties separate a service from a name, and none of them
needs a list:

  1. DISTINCT OPERATORS (the key discriminator). A real niche is used by MANY UNRELATED
     operators - twelve people who have never met each other all call their clinic a
     "microbiome clinic" because that is what the thing IS. A brand is used by ONE
     operator, however many times: a 30-site chain called "Zenith Vitality" puts "zenith"
     on 30 clinic names, and a naive frequency count ranks it ABOVE a genuinely emerging
     niche used by 12 independent founders. So we count DISTINCT OWNERS, never mentions,
     and we bound MENTIONS PER OPERATOR (which is what catches a franchise, where the
     operator count alone is not enough).

  2. RISING, NOT STANDING. Surnames and place names are STATIONARY - the share of UK
     clinics with "Brown" in the name is the same this year as last. This is what kills a
     COMMON surname, which the operator gate alone would NOT kill: there really are forty
     unrelated Browns and they pass it easily.

  3. GEOGRAPHIC SPREAD. A place name is concentrated by definition. A service is national.

  4. THE EXISTING STOP LIST. pull_and_build.STOP already absorbs the generic business
     vocabulary. Reused verbatim - two copies of a stop list are two copies that drift.

INPUTS
------
discovery() takes the rows the existing miners already produce. But those rows count
MENTIONS, not OPERATORS - pull_and_build.cqc() counts LOCATIONS and never reads the
Provider ID column, so it literally cannot tell a 30-site chain from 30 independents. So
this module ships two miners of its own that DO carry operator identity, at zero extra
bandwidth (they read the same cqc.ods that is already on disk):

    mine_cqc_ods(path)                 -> phrases with DISTINCT PROVIDER counts + regions
    mine_company_names(recent, prior)  -> phrases with DISTINCT COMPANY counts

Feed those in and the filter has real evidence. Feed in the plain existing rows and it
degrades honestly: it says so, applies a higher bar, and tells the integrator what to wire
up. It never pretends a location count is an operator count.

Read discovery_FINDINGS.md for what this STILL cannot see. Stdlib only.
    python3 discovery.py --selftest     synthetic fixtures, no network
"""

import os
import re
import sys
import json
import math
import zipfile
import tempfile
from collections import Counter, defaultdict
from datetime import date

# discovery.py is designed to sit next to taxonomy.py in radar-app/. It currently lives
# one level down in _agent2/, so both directories go on the path - the same file then works
# in place today and after it is moved up.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

DIAG = {}

# The taxonomy is the DEFINITION of "already known". A phrase is residue iff niche_of()
# cannot place it.
try:
    from taxonomy import niche_of as _niche_of
except Exception as _e:                                  # pragma: no cover
    def _niche_of(_t):
        return None
    DIAG["taxonomy_import_failed"] = repr(_e)[:120]

# STOP is REUSED, not re-derived. If pull_and_build is not importable we fall back to a
# copy and SAY SO in DIAG - a silently smaller stop list means a tab full of "clinic".
try:
    from pull_and_build import STOP as _STOP
    _STOP_SOURCE = "pull_and_build.STOP"
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

STOP = set(_STOP)

# The ODS parser is investability.py's - covered-table-cells, number-columns-repeated and
# all. A second copy of that parser is a second copy that can drift.
try:
    from investability import ods_rows, _resolve_columns, _parse_date, _add_months
    _ODS_OK = True
except Exception as _e:                                  # pragma: no cover
    _ODS_OK = False
    DIAG["investability_import_failed"] = repr(_e)[:120]


# ================================================================= THE THRESHOLDS
# Judgement calls, stated as constants in one place with the reasoning, so they can be
# argued with rather than reverse-engineered.

# MIN_OPERATORS = 6 -- the gate, and the whole idea. Five people could be five friends, a
# franchise, or one person with five companies. Six UNRELATED operators independently
# choosing the same word is where the word starts to mean something to the market rather
# than to one founder. Deliberately LOW: a false positive costs one junk row a human
# ignores; a false negative costs the next ADHD, which is the entire point of the module.
MIN_OPERATORS = 6

# MIN_OPERATORS_ASSUMED = 12 -- when operator identity was ASSUMED rather than OBSERVED
# (true of Companies House rows, where each company is its own record; NOT true of CQC
# rows, where one chain owns many locations) the bar doubles. An assumed operator count is
# worth half an observed one.
MIN_OPERATORS_ASSUMED = 12

# MAX_MENTIONS_PER_OPERATOR = 3.0 -- the brand test, and the reason the operator gate alone
# is not enough. A 7-clinic franchise with 6 sites each clears a 6-operator gate easily; it
# scores 42/7 = 6.0 here and dies. A genuine service phrase is near 1.0 (each operator says
# it once, on their one clinic). 3.0 leaves room for a real two- or three-site
# owner-operator without letting a chain through.
MAX_MENTIONS_PER_OPERATOR = 3.0

# MIN_GROWTH_PCT = 25.0 -- the stationarity test, and the ONLY thing that can kill a common
# surname. The distinct-operator gate passes "brown" easily. What "brown" cannot do is
# GROW: its share of UK clinic names is a demographic constant.
MIN_GROWTH_PCT = 25.0

# MIN_REGIONS = 3 -- the place-name test. Applied ONLY where the source gives a region (the
# CQC file does; Companies House does not, without a per-company call the budget cannot
# afford). A service is national. "Molesey" is not.
MIN_REGIONS = 3

# EMERGING_MONTHS = 18 -- how recently a phrase must have FIRST appeared in our own history
# to count as emerging rather than merely rising. Longer than the gap between the earliest
# tier (search) and the tier this reads (company formation), so a niche caught on the way
# up is still flagged new by the time clinics start registering.
EMERGING_MONTHS = 18

# MIN_COUNT = 4 -- floor on raw mentions, matching the existing miners (which use c < 4).
# Below this the growth arithmetic is noise: 1 -> 2 is +100%.
MIN_COUNT = 4

MAX_ROWS = 40
HISTORY_VERSION = 1


# ===================================================================== utilities
def _pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / float(then) - 1.0) * 100.0


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


def _months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def _iso_to_date(s):
    try:
        p = [int(x) for x in str(s).split("-")[:3]]
        return date(p[0], p[1], p[2])
    except Exception:
        return None


def phrase_tokens(name):
    """Name -> the tokens the existing miners keep: alphabetic runs, >3 chars, not in STOP.

    Deliberately IDENTICAL to pull_and_build.name_terms() and pull_and_build.cqc(), so the
    residue reported here is the residue those miners actually threw away - not a different
    set of phrases produced by a different tokeniser.
    """
    return [t for t in re.findall(r"[a-z]+", (name or "").lower())
            if len(t) > 3 and t not in STOP]


def phrase_grams(name):
    """Unigrams + adjacent bigrams, as a SET.

    A set, because a name that repeats a word must not contribute it twice - the count is
    "how many NAMES contain this phrase", and mention-inflation from inside a single name
    is exactly what lets a brand outrank a niche.
    """
    toks = phrase_tokens(name)
    out = set(toks)
    for i in range(len(toks) - 1):
        out.add(toks[i] + " " + toks[i + 1])
    return out


def is_residue(phrase):
    """The definition of the residue: the taxonomy cannot place it."""
    return _niche_of(phrase) is None


# ========================================================= MINER: Companies House
def mine_company_names(recent, prior=()):
    """Company-name n-grams WITH operator identity.

    recent / prior: iterables of (company_id, company_name) for the trailing 12 months and
    the 12 before that. One company = one operator - TRUE at Companies House in a way it is
    NOT true at CQC, where one provider owns many locations. Still only a floor: a group
    that incorporates twelve Ltds counts as twelve "operators" here. That is why these
    counts are marked `assumed` and held to the doubled bar, and why the CQC miner - which
    has real provider IDs - is the one to trust.
    """
    cur, pre = defaultdict(set), defaultdict(set)
    for cid, nm in (recent or ()):
        for g in phrase_grams(nm):
            cur[g].add(cid)
    for cid, nm in (prior or ()):
        for g in phrase_grams(nm):
            pre[g].add(cid)

    rows = []
    for g, ids in cur.items():
        rows.append({
            "name": g, "niche": _niche_of(g), "latest": len(ids),
            "count_12m": len(ids), "count_prior_12m": len(pre.get(g, ())),
            "operators": len(ids), "operator_evidence": "assumed", "tier": "companies",
        })
    return rows


# ==================================================================== MINER: CQC
# The miner that matters: the only source in the radar carrying an OWNERSHIP KEY.
# pull_and_build.cqc() streams this same file and counts LOCATIONS - it never reads the
# Provider ID column, so it cannot tell one 30-site chain from 30 independent clinics, and
# that is precisely the distinction the discovery layer lives or dies on. Same file, same
# parser, one extra column read, zero extra bandwidth.
def mine_cqc_ods(path, anchor=None, sector_filter="independent healthcare"):
    """-> rows with DISTINCT PROVIDER counts and REGION spread. [] if unreadable.

    Windows: locations whose HSCA start date falls in the last 12 months vs the 12 before.
    A FLOW, like the rest of the early tiers - we want what is being CREATED, not what
    exists. A new niche has no stock.
    """
    if not _ODS_OK:
        DIAG["cqc_miner"] = "investability.ods_rows unavailable"
        return []

    anchor = anchor or date.today()
    lo12, lo24 = _add_months(anchor, -12), _add_months(anchor, -24)

    cols = None
    cur_ops, pre_ops = defaultdict(set), defaultdict(set)   # phrase -> {provider_id}
    cur_locs, pre_locs = Counter(), Counter()               # phrase -> locations
    cur_regions = defaultdict(set)                          # phrase -> {region}
    seen = kept = 0

    def cell(row, key):
        j = cols.get(key)
        if j is None or j >= len(row):
            return ""
        return (row[j] or "").strip()

    try:
        for _sheet, row in ods_rows(path):
            if cols is None:
                # The first sheet in the real file is a README. The data sheet is the one
                # whose header row carries a cell exactly equal to "location id".
                if "location id" not in [(c or "").strip().lower() for c in row]:
                    continue
                cols = _resolve_columns(row)
                if not cols:
                    DIAG["cqc_miner"] = "header found but Location Name column missing"
                    return []
                continue

            seen += 1
            # Same policy as pull_and_build.cqc(): the private-pay clinic universe only.
            # Social care is churn; NHS and dental have formulaic naming that swamps every
            # n-gram count.
            if sector_filter and sector_filter not in cell(row, "sector").lower():
                continue
            d = _parse_date(cell(row, "start"))
            if not d:
                continue
            name = cell(row, "loc_name")
            if not name:
                continue
            grams = phrase_grams(name)
            if not grams:
                continue

            pid = cell(row, "prov_id") or None
            region = cell(row, "region")

            if lo12 <= d <= anchor:
                kept += 1
                for g in grams:
                    cur_locs[g] += 1
                    if pid:
                        cur_ops[g].add(pid)
                    if region:
                        cur_regions[g].add(region)
            elif lo24 <= d < lo12:
                for g in grams:
                    pre_locs[g] += 1
                    if pid:
                        pre_ops[g].add(pid)
    except Exception as e:
        DIAG["cqc_miner_error"] = repr(e)[:160]
        return []

    if cols is None:
        DIAG["cqc_miner"] = "no sheet with a 'location id' header cell"
        return []
    DIAG["cqc_miner"] = {"rows_seen": seen, "in_window": kept, "phrases": len(cur_locs)}

    rows = []
    for g, locs in cur_locs.items():
        rows.append({
            "name": g, "niche": _niche_of(g), "latest": locs,
            # Two year-on-year comparisons, kept SEPARATE on purpose. Locations-vs-locations
            # is what the existing miner measures, and a chain can manufacture it by opening
            # twenty sites. Operators-vs-operators cannot be faked, and it is the one
            # discovery() actually ranks on.
            "count_12m": locs,                              # LOCATIONS
            "count_prior_12m": pre_locs.get(g, 0),          # LOCATIONS, prior year
            "operators": len(cur_ops.get(g, ())),           # DISTINCT PROVIDERS
            "operators_prior": len(pre_ops.get(g, ())),     # DISTINCT PROVIDERS, prior
            "operator_evidence": "observed",                # real CQC Provider IDs
            "regions": sorted(cur_regions.get(g, ())),
            "tier": "cqc",
        })
    return rows


# =============================================== normalising whatever we are given
def _norm_row(r, tier):
    """One miner row -> the fields discovery() needs, filling gaps HONESTLY.

    The existing miners emit {name, latest, g12, isnew} and nothing else. That is a MENTION
    count with no operator identity, and for CQC rows a mention is a LOCATION, which a chain
    can manufacture at will. So:
      * count_prior_12m: taken if given, else backed out of g12, else None.
      * operators: taken if given. If absent -
          Companies House rows -> assumed = latest (one company, one record), marked
            `assumed` and held to the doubled bar.
          CQC / aesthetics rows -> NOT ASSUMED AT ALL. A location count and a keyword count
            are not operator counts, and pretending otherwise is precisely the error this
            module exists to prevent. operators stays None and the phrase can only surface
            on evidence from another tier.
    """
    if not isinstance(r, dict):
        return None
    name = (r.get("name") or "").strip().lower()
    if not name:
        return None

    count = r.get("count_12m")
    if count is None:
        count = r.get("latest")
    try:
        count = int(count or 0)
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
    else:
        try:
            ops = int(ops)
            ev = ev or "observed"
        except (TypeError, ValueError):
            ops, ev = None, "none"

    ops_prior = r.get("operators_prior")
    if ops_prior is None and tier == "companies" and r.get("count_prior_12m") is not None:
        ops_prior = r.get("count_prior_12m")      # one company, one record: same thing

    return {"name": name, "count": count, "prior": prior, "operators": ops,
            "operators_prior": ops_prior, "evidence": ev,
            "regions": set(r.get("regions") or ()), "tier": tier}


# ============================================================== history / trajectory
def _read_history(path):
    h = _load(path, None)
    if not isinstance(h, dict) or "phrases" not in h:
        h = {"version": HISTORY_VERSION, "phrases": {}, "runs": []}
    return h


def _update_history(hist, rows, today):
    """Record every RESIDUE phrase seen this run, kept or dropped.

    This is the whole point of persisting anything: first_seen is what makes 'emerging' mean
    something, and you can only know a phrase is new if you were writing down the ones that
    were not. A phrase filtered out today for having four operators may have twenty next
    quarter, and its first_seen must be today, not then.
    """
    ph = hist.setdefault("phrases", {})
    iso = today.isoformat()
    for r in rows:
        e = ph.get(r["name"])
        if e is None:
            e = ph[r["name"]] = {"first_seen": iso, "last_seen": iso, "trail": []}
        e["last_seen"] = iso
        trail = [t for t in (e.get("trail") or []) if t.get("date") != iso]
        trail.append({"date": iso, "count": r["count"], "operators": r["operators"]})
        e["trail"] = trail[-24:]
    runs = hist.setdefault("runs", [])
    if iso not in runs:
        runs.append(iso)
    hist["runs"] = runs[-400:]
    return hist


def _trajectory(entry, count, ops, today):
    """Growth from OUR OWN history, for a source that gives no prior-year window.

    The CQC and Companies House miners give one directly, which is better. This is the
    fallback for a snapshot-only source - and it is why the history file exists. Compares
    against the most recent trail point at least ~9 months old.
    """
    if not entry:
        return None
    old = None
    for t in (entry.get("trail") or []):
        d = _iso_to_date(t.get("date"))
        if d and _months_between(d, today) >= 9:
            old = t
    if not old:
        return None
    return _pct(ops if ops is not None else count,
                old.get("operators") or old.get("count"))


# ======================================================================= the filter
def _judge(p):
    """-> (keep, reason). The reason is emitted EITHER WAY, so a phrase that was dropped
    can be argued with instead of vanishing - which is the exact failure this module fixes.
    """
    name = p["name"]

    # 0. residue only. If the taxonomy can place it, it is not a discovery.
    if not is_residue(name):
        return False, "already in the taxonomy (%s)" % _niche_of(name)

    # 1. shape: nothing the miners' own tokeniser would not have kept.
    words = name.split()
    if not words or any(len(w) <= 3 or w in STOP for w in words):
        return False, "stop word or too short"
    if len(words) > 2:
        return False, "longer than a bigram - the miners do not produce these"

    # 2. volume floor. Below this the growth arithmetic is noise.
    if p["count"] < MIN_COUNT:
        return False, "only %d mention(s) - below the noise floor" % p["count"]

    # 3. THE GATE: distinct operators. A real niche is used by many unrelated operators;
    # a brand is used many times by one.
    ops = p["operators"]
    if ops is None:
        return False, ("no operator evidence - this source counts mentions, not owners "
                       "(wire mine_cqc_ods() to fix)")
    bar = MIN_OPERATORS if p["evidence"] == "observed" else MIN_OPERATORS_ASSUMED
    if ops < bar:
        return False, ("only %d distinct operator(s), need %d (%s evidence)"
                       % (ops, bar, p["evidence"]))

    # 4. the brand test. Catches the FRANCHISE, which clears the gate above on head-count
    # but is still one brand: 7 operators x 6 sites = 42 mentions = 6.0 per operator.
    per = p["count"] / float(ops)
    if per > MAX_MENTIONS_PER_OPERATOR:
        return False, ("%.1f mentions per operator - this is one chain's brand, not a "
                       "service used by an industry" % per)

    # 5. the place-name test. Only where we HAVE regions; never inferred.
    regions = p["regions"]
    if regions and len(regions) < MIN_REGIONS:
        return False, ("appears in only %d region(s) (%s) - looks like a place name or a "
                       "local operator, not a national service"
                       % (len(regions), ", ".join(sorted(regions)[:3])))

    # 6. the stationarity test. This is what kills common surnames, which sail through the
    # operator gate because there really are forty unrelated Browns.
    growth, is_new = p["growth"], p["is_new"]
    if not is_new:
        if growth is None:
            return False, ("no year-on-year comparison yet - cannot tell rising from "
                           "standing (needs a prior-year window, or one more run)")
        if growth < MIN_GROWTH_PCT:
            return False, ("up only %.0f%% year on year - standing, not rising. A surname "
                           "or a place name looks exactly like this" % growth)

    if is_new:
        return True, "NEW: %d distinct operators, none a year ago" % ops
    return True, "%d distinct operators, up %.0f%% year on year" % (ops, growth)


# ============================================================================ main
def discovery(inc_rows, cqc_rows, aes_rows, history_path="data/discovery.json",
              today=None, max_rows=MAX_ROWS, keep_rejects=False):
    """The UNCLASSIFIED residue: rising phrases from company names and CQC clinic
    names that match NO existing niche. This is the only place a genuinely new
    niche can appear. Returns rows sorted by how fast they are rising, with the
    raw counts, first-seen date, and an 'emerging' flag.

    Returns [ {phrase, distinct_operators, count_12m, count_prior_12m, growth,
               growth_basis, first_seen, emerging, sources, operator_evidence, regions,
               why, rank_score} ]

    inc_rows  Companies House name n-grams: pull_and_build.incorporations()'s rows, or -
              much better - mine_company_names(), which carries company identity.
    cqc_rows  CQC clinic-name n-grams: pull_and_build.cqc()'s rows, or - much better -
              mine_cqc_ods(), which carries the PROVIDER ID and the region and is therefore
              the only input that can tell a 30-site chain from 30 independents.
    aes_rows  aesthetics.aesthetics() keyword rows. In practice almost everything in that
              vocabulary maps to Aesthetics / skin and is therefore not residue; it is here
              so a genuinely NEW aesthetics-adjacent word (the next "polynucleotide") is
              not lost.

    history_path persists first_seen, so 'emerging' means something from run 2 onwards. On
    a cold start nothing is flagged emerging on AGE alone - but a phrase with no prior-year
    count at all is still flagged new.
    """
    today = today or date.today()
    DIAG.pop("no_operator_evidence", None)

    # -------------------------------------------------------------- normalise + merge
    merged, src_seen = {}, defaultdict(set)
    for rows, tier in ((inc_rows, "companies"), (cqc_rows, "cqc"),
                       (aes_rows, "aesthetics")):
        for r in (rows or []):
            p = _norm_row(r, tier)
            if p is None:
                continue
            src_seen[p["name"]].add(tier)
            m = merged.get(p["name"])
            if m is None:
                merged[p["name"]] = p
                continue
            # Take the BEST evidence, never the SUM: two tiers counting the same operator
            # would double it, and an inflated operator count is the single error that
            # defeats the whole filter.
            m["count"] = max(m["count"], p["count"])
            if p["prior"] is not None:
                m["prior"] = (p["prior"] if m["prior"] is None
                              else max(m["prior"], p["prior"]))
            if p["operators"] is not None:
                upgrade = (m["evidence"] != "observed" and p["evidence"] == "observed")
                same_ev = (m["evidence"] == p["evidence"])
                if (m["operators"] is None or upgrade
                        or (same_ev and p["operators"] > m["operators"])):
                    m["operators"], m["evidence"] = p["operators"], p["evidence"]
                    if p["operators_prior"] is not None:
                        m["operators_prior"] = p["operators_prior"]
            if p["operators_prior"] is not None and m["operators_prior"] is None:
                m["operators_prior"] = p["operators_prior"]
            m["regions"] |= p["regions"]

    # EVERY phrase is judged, including the ones the taxonomy CAN place - so that "already
    # in the taxonomy" appears as an explicit, countable drop reason rather than a silent
    # pre-filter. Only the RESIDUE is written to history: we are keeping a record of the
    # unknown, not a second copy of the dashboard.
    allp = list(merged.values())
    residue = [p for p in allp if is_residue(p["name"])]

    hist = _read_history(history_path)
    phrases = hist.get("phrases", {})

    # ------------------------------------------------------------ growth + emergence
    for p in allp:
        # Prefer OPERATOR-on-OPERATOR wherever the miner gave us one (CQC does). That is
        # the honest year-on-year. Locations-vs-locations lets a chain that opened twenty
        # sites this year look like an emerging niche.
        op_prior = p["operators_prior"]
        if op_prior is not None and p["operators"] is not None:
            p["growth"] = _pct(p["operators"], op_prior)
            p["is_new"] = (op_prior == 0 and p["operators"] > 0)
            p["_basis"] = "operators"
        elif p["prior"] is not None:
            p["growth"] = _pct(p["count"], p["prior"])
            p["is_new"] = (p["prior"] == 0 and p["count"] > 0)
            p["_basis"] = "mentions"
        else:
            p["growth"] = _trajectory(phrases.get(p["name"]), p["count"],
                                      p["operators"], today)
            p["is_new"] = False
            p["_basis"] = "own history" if p["growth"] is not None else "none"

        e = phrases.get(p["name"])
        p["first_seen"] = (e or {}).get("first_seen") or today.isoformat()
        fs = _iso_to_date(p["first_seen"])
        age_m = _months_between(fs, today) if fs else 0
        p["emerging"] = bool(p["is_new"] or age_m <= EMERGING_MONTHS)

    kept, dropped = [], []
    for p in allp:
        ok, why = _judge(p)
        p["why"] = why
        (kept if ok else dropped).append(p)

    # History records every RESIDUE phrase, kept or dropped - but nothing the taxonomy
    # already knows about.
    try:
        _update_history(hist, residue, today)
        _save(history_path, hist)
    except Exception as e:
        DIAG["history_write_failed"] = repr(e)[:120]

    # ------------------------------------------------------------------------- rank
    # Rate of rise AND distinct-operator count. A previously-unseen phrase has infinite
    # growth and would swamp the list, so rise is CAPPED and then weighted by the LOG of the
    # operator count: the difference between 6 and 12 unrelated operators is meaningful, the
    # difference between 60 and 120 is not, and a big flat phrase must never outrank a small
    # explosive one.
    RISE_CAP = 300.0

    def rank(p):
        g = p["growth"]
        rise = RISE_CAP if (p["is_new"] or g is None) else min(g, RISE_CAP)
        return rise * (1.0 + math.log(1 + (p["operators"] or 0)))

    for p in kept:
        p["rank_score"] = round(rank(p), 1)
    kept.sort(key=lambda p: (-p["rank_score"], -(p["operators"] or 0), p["name"]))

    out = []
    for p in kept[:max_rows]:
        out.append({
            "phrase": p["name"],
            "distinct_operators": p["operators"],
            "count_12m": p["count"],
            "count_prior_12m": p["prior"],
            "growth": (None if p["growth"] is None else round(p["growth"], 1)),
            "growth_basis": p["_basis"],
            "first_seen": p["first_seen"],
            "emerging": p["emerging"],
            "sources": sorted(src_seen.get(p["name"], ())),
            "operator_evidence": p["evidence"],
            "regions": len(p["regions"]) or None,
            "why": p["why"],
            "rank_score": p["rank_score"],
        })

    DIAG["residue_phrases"] = len(residue)
    DIAG["surfaced"] = len(out)
    DIAG["dropped"] = len(dropped)
    DIAG["stop_list"] = _STOP_SOURCE
    DIAG["drop_reasons"] = Counter(
        d["why"].split(" -")[0].split(",")[0][:60] for d in dropped).most_common(8)
    no_ops = sum(1 for p in residue if p["operators"] is None)
    if no_ops:
        DIAG["no_operator_evidence"] = (
            "%d residue phrases carry no operator identity and therefore CANNOT be "
            "surfaced. pull_and_build.cqc() counts locations, not providers - pass "
            "discovery.mine_cqc_ods(<tmp>/cqc.ods) as cqc_rows to fix this at zero extra "
            "bandwidth." % no_ops)

    if keep_rejects:
        return out, sorted(dropped, key=lambda p: -(p["operators"] or 0))
    return out


# ======================================================================== SELF-TEST
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

      REAL EMERGING NICHE  "microbiome" / "microbiome sequencing": 12 clinics, 12 DIFFERENT
                           providers, 6 regions, none there a year ago. niche_of() cannot
                           place it. Must SURFACE - the next-ADHD case. If it does not
                           surface, the module has no reason to exist.
      BRAND (one owner)    "Zenith Vitality": 30 clinics, ONE provider. Raw frequency ranks
                           it FIRST in the fixture. Must be SUPPRESSED by the DISTINCT-
                           OPERATOR gate - not by a blocklist, and not by frequency.
      BRAND (a franchise)  "Lumiere": 7 providers x 6 sites = 42 clinics, brand new. It
                           CLEARS the distinct-operator gate (7 >= 6), the growth gate (new)
                           and the region gate (6 regions). The ONLY thing that can kill it
                           is MENTIONS PER OPERATOR (6.0 > 3.0). This is the case that
                           proves the operator gate alone is not enough.
      SURNAME              "Hartley": 9 clinics, 9 DIFFERENT providers, 6 regions. Passes
                           the operator gate AND the region gate - there really are nine
                           unrelated Hartleys - but there were nine last year too. Must be
                           SUPPRESSED on STATIONARITY, the only thing that kills a surname.
      PLACE NAME           "Molesey": 8 clinics, 8 DIFFERENT providers, GROWING 2 -> 8.
                           Passes the operator gate AND the growth gate. But every one is in
                           the South East. Must be SUPPRESSED on GEOGRAPHY.
      KNOWN NICHE          "menopause": 10 clinics. Dropped as already in the taxonomy - a
                           discovery layer that rediscovers the menopause is just the
                           dashboard again.

    Names are built so the tokeniser yields the phrase under test and little else: "clinic",
    "rooms", "care", "home" and "therapy" are ALL already in STOP - which is exactly why the
    real miners produce such sparse n-grams.
    """
    recent = _add_months(anchor, -6).isoformat()
    prior = _add_months(anchor, -18).isoformat()
    rows, n = [], [0]

    def add(start, nm, region, pid):
        n[0] += 1
        rows.append(("L%d" % n[0], start, nm, "Independent Healthcare Org", region,
                     pid, pid + " Ltd"))

    for i in range(12):      # 1. REAL NICHE: 12 unrelated operators, 6 regions, 0 prior
        add(recent, "Microbiome Sequencing Clinic %d" % i, _REGIONS[i % 6], "MIC%d" % i)
    for i in range(30):      # 2a. BRAND: ONE provider, 30 locations
        add(recent, "Zenith Vitality Clinic %d" % i, _REGIONS[i % 8], "CHAIN1")
    for i in range(42):      # 2b. FRANCHISE: 7 providers x 6 sites each
        add(recent, "Lumiere Clinic %d" % i, _REGIONS[i % 6], "LUM%d" % (i % 7))
    for i in range(9):       # 3. SURNAME: 9 operators, 6 regions - and 9 last year too
        add(recent, "Hartley Clinic %d" % i, _REGIONS[i % 6], "HART%d" % i)
    for i in range(9):
        add(prior, "Hartley Clinic old %d" % i, _REGIONS[i % 6], "HARTOLD%d" % i)
    for i in range(8):       # 4. PLACE: 8 operators, rising 2 -> 8, ONE region
        add(recent, "Molesey Clinic %d" % i, "South East", "MOL%d" % i)
    for i in range(2):
        add(prior, "Molesey Clinic old %d" % i, "South East", "MOLOLD%d" % i)
    for i in range(10):      # 5. ALREADY KNOWN
        add(recent, "The Menopause Clinic %d" % i, _REGIONS[i % 5], "MEN%d" % i)
    # 6. Sector filter: 20 SOCIAL CARE rows carrying the SAME phrase with 20 more provider
    # IDs. If the filter breaks, "microbiome" jumps from 12 operators to 32 and the test
    # below fails loudly rather than quietly inflating a discovery.
    for i in range(20):
        rows.append(("S%d" % i, recent, "Microbiome Sequencing Lodge %d" % i,
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
        print("  %s %-56s %s" % ("PASS" if ok else "FAIL", label, got))

    tmp = tempfile.mkdtemp(prefix="disc_")
    hist_path = os.path.join(tmp, "discovery.json")
    anchor = date(2026, 7, 1)

    print("\n[1] tokeniser matches the miners' own")
    chk("stop words dropped", phrase_tokens("The London Clinic Ltd"), [])
    chk("short tokens dropped", phrase_tokens("Ace Ltd"), [])
    chk("bigrams built",
        "microbiome sequencing" in phrase_grams("Microbiome Sequencing Clinic"), True)
    # "therapy" is ALREADY in STOP, so the miners can never produce "peptide therapy" as a
    # bigram. A hard limit on what this layer can see, and why the fixture cannot use a
    # "<word> therapy" phrase.
    chk("a STOP word cannot appear inside a bigram",
        "peptide therapy" in phrase_grams("Peptide Therapy Rooms"), False)
    chk("repeated word counted once",
        sorted(phrase_grams("Exosome Exosome")), ["exosome", "exosome exosome"])

    print("\n[2] the residue is exactly what the taxonomy cannot place")
    chk("known niche is NOT residue (menopause)", is_residue("menopause"), False)
    chk("known niche is NOT residue (adhd)", is_residue("adhd"), False)
    # "peptide" is ALREADY in the taxonomy (Longevity / peptides / IV) and must never be
    # reported as a discovery. Pinned because it is the mistake the first fixture made.
    chk("'peptide' is already known - not residue", is_residue("peptide"), False)
    chk("novel word IS residue (microbiome)", is_residue("microbiome"), True)
    chk("novel word IS residue (exosome)", is_residue("exosome"), True)

    print("\n[3] CQC miner reads PROVIDER IDs, not just location counts")
    ods = _fixture_ods(os.path.join(tmp, "cqc.ods"), anchor)
    cqc_rows = mine_cqc_ods(ods, anchor=anchor)
    by = dict((r["name"], r) for r in cqc_rows)
    chk("miner returned rows", len(cqc_rows) > 0, True)
    chk("'microbiome' 12 locations", by["microbiome"]["count_12m"], 12)
    chk("'microbiome' 12 DISTINCT providers", by["microbiome"]["operators"], 12)
    chk("'microbiome' 0 providers a year ago", by["microbiome"]["operators_prior"], 0)
    chk("'microbiome' spread over 6 regions", len(by["microbiome"]["regions"]), 6)
    chk("brand 'zenith' 30 locations", by["zenith"]["count_12m"], 30)
    chk("brand 'zenith' but ONE provider", by["zenith"]["operators"], 1)
    chk("franchise 'lumiere' 42 locations, 7 providers",
        (by["lumiere"]["count_12m"], by["lumiere"]["operators"]), (42, 7))
    chk("social care excluded (operators 12, not 32)", by["microbiome"]["operators"], 12)
    chk("'hartley' 9 now, 9 a year ago (flat)",
        (by["hartley"]["operators"], by["hartley"]["operators_prior"]), (9, 9))
    chk("'molesey' 8 now, 2 prior, 1 region",
        (by["molesey"]["operators"], by["molesey"]["operators_prior"],
         len(by["molesey"]["regions"])), (8, 2, 1))

    print("\n[4] the cases the brief demands")
    out = discovery([], cqc_rows, [], history_path=hist_path, today=anchor)
    surfaced = set(r["phrase"] for r in out)
    rows_by = dict((r["phrase"], r) for r in out)
    chk("REAL NICHE surfaces: 'microbiome'", "microbiome" in surfaced, True)
    chk("REAL NICHE surfaces: 'microbiome sequencing'",
        "microbiome sequencing" in surfaced, True)
    chk("  ...with 12 distinct operators",
        rows_by.get("microbiome", {}).get("distinct_operators"), 12)
    chk("  ...flagged emerging", rows_by.get("microbiome", {}).get("emerging"), True)
    chk("  ...and it is the top-ranked row",
        out[0]["phrase"] in ("microbiome", "microbiome sequencing", "sequencing"), True)
    chk("BRAND suppressed: 'zenith' (30 mentions, 1 operator)", "zenith" in surfaced, False)
    chk("BRAND suppressed: 'zenith vitality'", "zenith vitality" in surfaced, False)
    chk("BRAND suppressed: 'vitality'", "vitality" in surfaced, False)
    chk("FRANCHISE suppressed: 'lumiere' (7 operators, 42 sites, NEW, 6 regions)",
        "lumiere" in surfaced, False)
    chk("SURNAME suppressed: 'hartley' (9 unrelated operators, but FLAT)",
        "hartley" in surfaced, False)
    chk("PLACE suppressed: 'molesey' (8 operators, RISING, ONE region)",
        "molesey" in surfaced, False)
    chk("KNOWN NICHE not a discovery: 'menopause'", "menopause" in surfaced, False)

    # ...and each died for the RIGHT reason, not by luck. This is the part that matters: a
    # filter that gets the right answer for the wrong reason will get the next one wrong.
    _, rej = discovery([], cqc_rows, [], history_path=hist_path, today=anchor,
                       keep_rejects=True)
    why = dict((r["name"], r["why"]) for r in rej)
    chk("'zenith' killed by the DISTINCT-OPERATOR gate (1 operator)",
        "distinct operator" in why.get("zenith", ""), True)
    chk("'lumiere' killed on mentions-per-operator (6.0 > 3.0)",
        "mentions per operator" in why.get("lumiere", ""), True)
    chk("'hartley' killed on stationarity",
        "standing, not rising" in why.get("hartley", ""), True)
    chk("'molesey' killed on geography", "region" in why.get("molesey", ""), True)
    chk("'menopause' killed as already-known (explicit, countable drop)",
        "already in the taxonomy" in why.get("menopause", ""), True)

    print("\n[5] history persists first_seen and drives 'emerging'")
    chk("history file written", os.path.exists(hist_path), True)
    h = _load(hist_path, {})
    chk("dropped phrases remembered too (so first_seen is real later)",
        "hartley" in h.get("phrases", {}), True)
    chk("known niches NOT written to the residue history",
        "menopause" in h.get("phrases", {}), False)
    chk("first_seen recorded", h["phrases"]["microbiome"]["first_seen"],
        anchor.isoformat())
    chk("trail records OPERATORS, not just mentions",
        h["phrases"]["microbiome"]["trail"][-1]["operators"], 12)
    age = _months_between(date(2026, 7, 1), date(2029, 7, 1))
    chk("age arithmetic (36 months)", age, 36)
    chk("36 months > EMERGING_MONTHS -> not emerging on age alone",
        age > EMERGING_MONTHS, True)

    print("\n[6] degraded input: existing miner rows, which have NO operator identity")
    # pull_and_build.cqc() emits LOCATION counts. A location count cannot distinguish a
    # 30-site chain from 30 independents, so it must buy NOTHING - not even for a phrase
    # that looks explosive.
    legacy_cqc = [{"name": "zenith", "latest": 30, "g12": 900.0, "isnew": False},
                  {"name": "microbiome", "latest": 12, "g12": None, "isnew": True}]
    out2 = discovery([], legacy_cqc, [], history_path=os.path.join(tmp, "d2.json"),
                     today=anchor)
    chk("nothing surfaces from location counts alone", out2, [])
    chk("and it tells the integrator what to wire up",
        "no_operator_evidence" in DIAG, True)

    # A Companies House row DOES carry operator identity - but only at the DOUBLED bar,
    # because a group can incorporate twelve Ltds.
    legacy_inc = [{"name": "microbiome", "latest": 14, "g12": None, "isnew": True},
                  {"name": "exosome", "latest": 8, "g12": None, "isnew": True}]
    out3 = discovery(legacy_inc, [], [], history_path=os.path.join(tmp, "d3.json"),
                     today=anchor)
    got = set(r["phrase"] for r in out3)
    chk("CH row, 14 companies -> surfaces (assumed bar is 12)", "microbiome" in got, True)
    chk("CH row, 8 companies -> does NOT (assumed evidence, doubled bar)",
        "exosome" in got, False)

    print("\n[7] mine_company_names carries company identity")
    recent = [("C%d" % i, "Exosome Skin Rooms %d" % i) for i in range(14)]
    prior = [("D%d" % i, "Exosome Skin Rooms %d" % i) for i in range(2)]
    inc = mine_company_names(recent, prior)
    ex = dict((r["name"], r) for r in inc)
    chk("'exosome' 14 companies", ex["exosome"]["operators"], 14)
    chk("'exosome' 2 a year ago", ex["exosome"]["count_prior_12m"], 2)
    out4 = discovery(inc, [], [], history_path=os.path.join(tmp, "d4.json"), today=anchor)
    got4 = dict((r["phrase"], r) for r in out4)
    chk("'exosome' surfaces (+600%)", "exosome" in got4, True)
    chk("  ...growth reported", got4.get("exosome", {}).get("growth"), 600.0)
    chk("'exosome skin' is already taxonomy - not a discovery",
        "exosome skin" in got4, False)

    print("\n[8] garbage in, no exception out")
    chk("all-None input",
        discovery(None, None, None, history_path=os.path.join(tmp, "d5.json")), [])
    chk("junk rows ignored",
        discovery(["not a dict", 7, None], [{}], [{"name": ""}],
                  history_path=os.path.join(tmp, "d6.json")), [])
    chk("unreadable ods -> [] not an exception",
        mine_cqc_ods(os.path.join(tmp, "nope.ods")), [])

    print("\n" + "=" * 72)
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
    if not os.path.exists(p):
        print("no CQC file at %s - run pull_and_build first, or set CQC_ODS_PATH" % p)
        return 1
    rows = discovery([], mine_cqc_ods(p), [])
    print("%-26s %4s %6s %7s %9s  %s" % ("phrase", "ops", "12m", "prior", "growth", "why"))
    for r in rows:
        print("%-26s %4s %6s %7s %8s%%  %s" % (
            r["phrase"][:26], r["distinct_operators"], r["count_12m"],
            r["count_prior_12m"],
            "-" if r["growth"] is None else "%+.0f" % r["growth"], r["why"][:46]))
    print("\nDIAG:", json.dumps(DIAG, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
