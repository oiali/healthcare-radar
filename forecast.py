#!/usr/bin/env python3
"""
PRE-REGISTERED FORWARD FORECAST LOG - the only mechanism that can earn this radar trust.

WHY
---
The backtest can only falsify, never validate: ~8 positives and ~8 negatives cannot
reach significance, and a backtest looks backwards, so it can be tuned until it
agrees with us. A pre-registered forward forecast cannot be. So, once a week, this
module freezes the radar's actual, current, unedited top-3 "rising earliest" claim,
writes down a falsifiable prediction with a 12-month horizon, pairs each pick with a
RANDOM control niche from the same board, and then - week after week - grades every
call whose horizon has matured, against data the radar itself collects anyway.

Until enough calls have matured, the honest scorecard reads "too few matured calls
to say anything", and it says exactly that rather than reporting a meaningless 100%
from a sample of one.

WHAT A CALL IS
--------------
The dashboard's Stack (template.py readStage) sorts niches by how EARLY the demand
chain says you are seeing them. The top of that sort IS the radar's claim. A pick is
eligible only if its stage makes a rising-and-not-yet-mainstream claim: "Emerging",
"Search only" (early) or "Building out". "Mainstream" claims it already happened and
"Cooling" claims it is over - neither is a forecast of rising, so grading them as
one would be unfair in BOTH directions. That eligibility rule is fixed here, in
code, before any call is graded - it cannot be adjusted later to rescue a score
without the adjustment being visible in this file's git history.

THE PREDICTION (designed to be gradeable by the radar's own later data, no judgement)
-------------------------------------------------------------------------------------
At call time we record, per niche, how many of tiers T1-T4 it "fires" on in
data/history.json terms (volume-weighted 12-month growth >= +10%, exactly
pull_and_build.whats_moved()'s fired() rule). The prediction:

    within 365 days, history.json will show this niche firing on MORE tiers than
    it fires on today.

i.e. the demand chain progresses - search-only grows companies, company-formation
grows clinics, and so on. Graded HIT if either (a) the history snapshot nearest the
maturity date (within +/-45 days) shows more tiers firing, or (b) the weekly runs
saw the progression twice, at least 7 days apart, inside the horizon (recorded as
"watch" entries - necessary because history.json is a rolling ~60-day window, so a
progression at month 5 that cools by month 12 would otherwise be invisible AND the
radar's "I saw it early" would be ungradeable). MISS if the maturity snapshot exists
and shows no progression and no confirmed sightings. UNGRADEABLE if the radar itself
was dark (no snapshot near maturity, no confirmed sightings) - that is a fact about
the instrument, not the niche, and it is excluded from the score rather than
counted either way.

THE CONTROL
-----------
Alongside the picks, an equal number of niches drawn at RANDOM from the same board
(everything the stack could see, minus the picks), seeded deterministically from the
ISO week + the sorted board, so the draw is reproducible from the entry itself and
cannot be re-rolled until it flatters. Controls are graded by the IDENTICAL rule.
The only number that will ever matter is: do the picks' hits beat the controls'
hits? If they do not, the radar has no skill and the scorecard says so in words.

IMMUTABILITY
------------
The log is a hash chain. Each entry stores its body, the previous entry's hash, and
sha256(prev_hash + canonical_json(body)). Editing any past entry breaks every hash
after it; this module then REFUSES to append or score, and says why, loudly.
Honest limit: a chain proves tampering happened, it cannot prove who; and someone
with the file could rebuild the whole chain from scratch. The defence against that
is that data/forecast_log.json is committed to git by the daily Actions run, so a
rebuilt chain diverges from the public history. Chain here, git there - together
they make silent rewriting effectively impossible, which is the requirement.
Appends are also refused if they would be backdated (date must never decrease).

Stdlib only. Entry point:

    forecast(data, history_path="data/forecast_log.json", today=None)
        -> (this_week_rows, graded_rows, scorecard)

data          the dict pull_and_build.main() builds (keys: waits, trends, inc, aes,
              cqc, presc, invest, status, ...).
history_path  the forecast log (per the agreed signature; the radar's own
              data/history.json is read separately, see radar_history_path).
today         date / "YYYY-MM-DD" / None -> date.today(). For tests.

CLI:  python3 forecast.py --selftest     synthetic fixtures, no network, PASS/FAIL
"""

import hashlib
import json
import math
import os
import random
from datetime import date, datetime, timedelta

# Thresholds are DELIBERATE COPIES of the radar's own, frozen here so that a later
# re-tune of the dashboard cannot silently move the goalposts on already-written
# predictions. RISING/MIN_BASE match pull_and_build.py / template.py today.
RISING = 10.0            # a tier "fires" at >= +10% 12-month growth
MIN_BASE = 10            # stack read: no % believed on a count base under 10
BOOM, FALLING = 40.0, -10.0
TOP_N = 3                # the weekly call is the top 3 of the stack
HORIZON_DAYS = 365       # every prediction gets 12 months
MATURITY_WINDOW_DAYS = 45  # nearest snapshot to maturity must be within this
CONFIRM_GAP_DAYS = 7     # two sightings this far apart = confirmed progression
MIN_MATURED = 8          # below this many graded picks, no verdict is possible
GENESIS = "0" * 64
TIERS = ("t1", "t2", "t3", "t4")
STRANK = {"emerging": 5, "early": 4, "building": 3, "mainstream": 2,
          "cooling": 1, "quiet": 0, "nodata": 0}
PICKABLE = ("emerging", "early", "building")   # the stages that CLAIM "rising"
VOTING_SOURCES = ("trends", "inc", "cqc", "presc")
MIN_OK_SOURCES = 2       # fewer voting sources ok today -> the board is broken, no call


# ====================================================================== the stack
# Ports of template.py's aggB / fires / readDemand / readStage, so the call is the
# dashboard's ACTUAL claim, not a parallel model of it. Kept line-for-line faithful.

def _agg_simple(rows):
    """pull_and_build.agg(): volume-weighted 12-month growth per niche. This is the
    unit history.json is written in, so predictions are expressed and graded in it."""
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


def _agg_b(rows, index=False, independent_only=False):
    """template.py aggB(): per-niche growth AND its recoverable base, because the
    stack refuses to believe a % on a thin count. -> (growth{}, base_info{})."""
    m = {}
    for r in rows or []:
        n = r.get("niche")
        if not n:
            continue
        a = m.setdefault(n, {"latest": 0.0, "base": 0.0, "items": 0, "indep": 0})
        a["items"] += 1
        if independent_only and r.get("found"):
            continue                      # auto-discovered T1 terms get no vote
        a["indep"] += 1
        if r.get("g12") is None:
            continue                      # no growth -> no recoverable base
        L = r.get("latest") or 0
        denom = 1.0 + r["g12"] / 100.0
        if denom == 0:
            continue
        B = L / denom
        if not math.isfinite(B) or B < 0:
            continue
        a["latest"] += L
        a["base"] += B
    g, b = {}, {}
    for k, a in m.items():
        b[k] = {"latest": round(a["latest"]), "base": round(a["base"]),
                "items": a["items"], "independent_items": a["indep"], "index": index}
        g[k] = (a["latest"] / a["base"] - 1) * 100.0 if a["base"] > 0 else None
    return g, b


def _fires_stack(g, binfo):
    """template.py fires(): +10%, but a count-based tier must also clear one sigma
    of Poisson noise on its base, and a base under MIN_BASE never fires."""
    if g is None:
        return False
    binfo = binfo or {}
    n, ix = binfo.get("base"), bool(binfo.get("index"))
    if not ix and n is not None and n < MIN_BASE:
        return False
    th = RISING
    if not ix and n:
        nf = 100.0 * math.sqrt(n) / n
        if nf > th:
            th = nf
    return g >= th


def _read_demand(t0, t1, B):
    lit = []
    if _fires_stack(t1, B.get("t1")):
        lit.append(t1)
    if _fires_stack(t0, B.get("t0")):
        lit.append(t0)
    if not lit:
        if t1 is None and t0 is None:
            return "unknown"
        v = t1 if t1 is not None else t0
        return "falling" if v <= FALLING else "flat"
    return "booming" if max(lit) >= BOOM else "growing"


def _read_stage(t0, t1, t2, t3, t4, B):
    """template.py readStage(): the LATEST firing tier says how far it has travelled."""
    f1 = _fires_stack(t1, B.get("t1"))
    f2 = _fires_stack(t2, B.get("t2"))
    f3 = _fires_stack(t3, B.get("t3"))
    f4 = _fires_stack(t4, B.get("t4"))
    lit = sum([f1, f2, f3, f4])
    d = _read_demand(t0, t1, B)
    if lit == 0:
        q = "quiet" if (t1 is not None or t2 is not None or t3 is not None) else "nodata"
    elif f4:
        q = "mainstream" if (f1 or f2) else "cooling"
    elif f3:
        q = "building" if (f1 or f2) else "cooling"
    elif f2:
        q = "emerging"
    else:
        q = "early"
    if d == "falling" and not f1 and not f2:
        q = "cooling"
    return q


def build_stack(data):
    """The dashboard's Stack, sorted exactly as buildStack() sorts it: earliest
    stage first, then by how hard T1 then T2 is moving."""
    g0, b0 = _agg_b(data.get("waits"))
    g1, b1 = _agg_b(data.get("trends"), index=True, independent_only=True)
    g2, b2 = _agg_b((data.get("inc") or []) + (data.get("aes") or []))
    g3, b3 = _agg_b(data.get("cqc"))
    g4, b4 = _agg_b(data.get("presc"))
    names = set()
    for o in (g0, g1, g2, g3, g4):
        names |= set(o)
    names |= set(data.get("invest") or {})
    rows = []
    for n in sorted(names):
        B = {"t0": b0.get(n), "t1": b1.get(n), "t2": b2.get(n),
             "t3": b3.get(n), "t4": b4.get(n)}
        t = (g0.get(n), g1.get(n), g2.get(n), g3.get(n), g4.get(n))
        q = _read_stage(t[0], t[1], t[2], t[3], t[4], B)
        rows.append({"niche": n, "stage": q, "rank": STRANK[q],
                     "tiers": {"t0": t[0], "t1": t[1], "t2": t[2],
                               "t3": t[3], "t4": t[4]},
                     "bases": B})
    rows.sort(key=lambda r: (r["rank"],
                             r["tiers"]["t1"] if r["tiers"]["t1"] is not None else -9e9,
                             r["tiers"]["t2"] if r["tiers"]["t2"] is not None else -9e9),
              reverse=True)
    return rows


# =================================================== history.json grading units
def _hist_tiers_from_data(data):
    """The same aggregation whats_moved() writes into history.json (T1 independent
    terms only, T2 = incorporations WITHOUT the aesthetics miner, T3 = CQC,
    T4 = tracked prescribing) - so what we predict is what we will later read."""
    tr = [r for r in (data.get("trends") or []) if not r.get("found")]
    return {"t1": _agg_simple(tr), "t2": _agg_simple(data.get("inc")),
            "t3": _agg_simple(data.get("cqc")), "t4": _agg_simple(data.get("presc"))}


def _fired_count(snap, niche):
    """whats_moved().fired(): on how many of T1-T4 is this niche >= +10%?"""
    c = 0
    for t in TIERS:
        v = (snap.get(t) or {}).get(niche)
        if isinstance(v, (int, float)) and v >= RISING:
            c += 1
    return c


# ================================================================ the hash chain
def _canon(body):
    """One canonical byte-form per body, so the hash is reproducible by anyone."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _entry_hash(prev_hash, body):
    return hashlib.sha256((prev_hash + _canon(body)).encode("utf-8")).hexdigest()


def _load_log(path):
    """-> (records, problem). Verifies the whole chain. problem is None, or a
    plain-English description of exactly where the log stopped being trustworthy."""
    if not os.path.exists(path):
        return [], None
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except Exception as e:
        return [], ("the forecast log at %s is unreadable (%r). Refusing to write: "
                    "overwriting a corrupt log would destroy the record." % (path, e))
    recs = raw.get("entries") or []
    prev = GENESIS
    for i, rec in enumerate(recs):
        body = rec.get("body")
        if (rec.get("prev_hash") != prev
                or not isinstance(body, dict)
                or _entry_hash(prev, body) != rec.get("hash")):
            return recs, ("TAMPER DETECTED at entry %d (type %s, date %s): its "
                          "content no longer matches its recorded hash, or its link "
                          "to the previous entry is broken. A past call has been "
                          "edited. Nothing in this log can be trusted"
                          % (i, (body or {}).get("type"), (body or {}).get("date")))
        prev = rec["hash"]
    return recs, None


def _append(path, recs, bodies):
    """Chain the new bodies onto the verified records and write atomically.
    Backdating is refused: an entry whose date precedes the last entry's date is a
    rewrite of history wearing an append's clothes."""
    if not bodies:
        return recs
    last_date = recs[-1]["body"].get("date", "") if recs else ""
    prev = recs[-1]["hash"] if recs else GENESIS
    out = list(recs)
    for b in bodies:
        if b.get("date", "") < last_date:
            raise ValueError("backdated entry refused: %s < %s"
                             % (b.get("date"), last_date))
        last_date = b["date"]
        rec = {"prev_hash": prev, "body": b, "hash": _entry_hash(prev, b)}
        out.append(rec)
        prev = rec["hash"]
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"note": "APPEND-ONLY pre-registered forecast log. Each entry is "
                           "hash-chained to the previous one; editing any past entry "
                           "is detectable and stops the module. See _agent7/forecast.py.",
                   "entries": out}, fh, indent=1)
    os.replace(tmp, path)
    return out


# ==================================================================== the control
def _draw_controls(week_key, pool, k):
    """k random niches from the board, seeded from the ISO week + the sorted board
    itself. Deterministic and reproducible from the entry alone: re-running the draw
    with the recorded pool must yield the recorded controls. There is no way to
    re-roll it without changing the week or the board - i.e. no cherry-picking."""
    pool = sorted(set(pool))
    seed_material = "radar-forecast-control|%s|%s" % (week_key, ",".join(pool))
    seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    return rng.sample(pool, min(k, len(pool))), seed_material


# =============================================================== call construction
def _selection(niche, role, pos, stack_by, snap_tiers, today):
    """Everything we will need to grade this niche later, frozen now."""
    r = stack_by.get(niche) or {"stage": "quiet", "tiers": {}, "bases": {}}
    hvals = {t: (snap_tiers.get(t) or {}).get(niche) for t in TIERS}
    fired = sum(1 for t in TIERS
                if isinstance(hvals[t], (int, float)) and hvals[t] >= RISING)
    mature = (today + timedelta(days=HORIZON_DAYS)).isoformat()
    if fired >= len(TIERS):
        pred = ("Already fires on all four measured tiers at call time, so no later "
                "tier exists to predict. Recorded, but will be graded 'ungradeable'.")
    else:
        pred = ("By %s, data/history.json will show %s firing (volume-weighted "
                "12-month growth >= +%d%%) on MORE of tiers T1-T4 than the %d it "
                "fires on today - shown either by the snapshot nearest %s (within "
                "%d days) or by two sightings at least %d days apart inside the "
                "horizon." % (mature, niche, int(RISING), fired, mature,
                              MATURITY_WINDOW_DAYS, CONFIRM_GAP_DAYS))
    return {"niche": niche, "role": role, "stack_position": pos,
            "stage": r["stage"], "tiers": r.get("tiers"), "bases": r.get("bases"),
            "history_tiers": hvals, "fired_at_call": fired, "prediction": pred}


# ====================================================================== scorecard
def _wilson(k, n, z=1.96):
    """95% interval on a proportion. Behaves sanely at tiny n, which is the point:
    1 hit from 1 call gives (0.21, 1.00) - an interval that says 'anything'."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - hw), min(1.0, centre + hw))


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


def _pc(x):
    return "%d%%" % round(100.0 * x)


def _scorecard(grade_bodies, call_bodies, today, notes):
    tiso = today.isoformat()
    res = [r for g in grade_bodies for r in g.get("results") or []]
    pk = [r for r in res if r["role"] == "pick" and r["outcome"] in ("hit", "miss")]
    ct = [r for r in res if r["role"] == "control" and r["outcome"] in ("hit", "miss")]
    ung = sum(1 for r in res if r["outcome"] == "ungradeable")
    n_p, h_p = len(pk), sum(1 for r in pk if r["outcome"] == "hit")
    n_c, h_c = len(ct), sum(1 for r in ct if r["outcome"] == "hit")
    ci_p, ci_c = _wilson(h_p, n_p), _wilson(h_c, n_c)
    leads = [r["days_to_progress"] for r in pk
             if r["outcome"] == "hit" and r.get("days_to_progress") is not None]
    graded_weeks = {g["week"] for g in grade_bodies}
    open_calls = [c for c in call_bodies
                  if c["week"] not in graded_weeks and c["matures"] > tiso]
    next_mat = min((c["matures"] for c in open_calls), default=None)

    if n_p == 0:
        verdict = ("No matured calls yet - the log is %d call%s of promises, zero "
                   "evidence either way. First call matures %s. Until calls mature, "
                   "this file proves discipline, not skill."
                   % (len(call_bodies), "" if len(call_bodies) == 1 else "s",
                      next_mat or "when the first weekly call is written"))
    elif n_p < MIN_MATURED:
        verdict = ("TOO FEW MATURED CALLS TO SAY ANYTHING. %d graded pick%s (%d hit%s) "
                   "- the 95%% interval on the hit rate is %s to %s, which spans "
                   "%s of the possible range. A rate quoted from this would be noise "
                   "dressed as a result. No verdict before ~%d graded picks."
                   % (n_p, "" if n_p == 1 else "s", h_p, "" if h_p == 1 else "s",
                      _pc(ci_p[0]), _pc(ci_p[1]),
                      "almost all" if (ci_p[1] - ci_p[0]) > 0.6 else "too much",
                      MIN_MATURED))
    elif n_c == 0:
        verdict = ("%d picks graded but no graded controls - the log cannot say "
                   "whether the radar beats a random pick, which is the only test "
                   "that matters. Something is wrong with the control pipeline."
                   % n_p)
    else:
        pr, cr = h_p / n_p, h_c / n_c
        if pr <= cr:
            verdict = ("THE RADAR HAS SHOWN NO SKILL SO FAR: picks hit %s (%d/%d), "
                       "random picks from the same board hit %s (%d/%d). On this "
                       "evidence the top of the dashboard is no better than a "
                       "random niche off the same page."
                       % (_pc(pr), h_p, n_p, _pc(cr), h_c, n_c))
        elif ci_p[0] <= ci_c[1]:
            verdict = ("Picks are ahead of random (%s vs %s) but the 95%% intervals "
                       "overlap (%s-%s vs %s-%s). Still consistent with luck. Keep "
                       "logging." % (_pc(pr), _pc(cr), _pc(ci_p[0]), _pc(ci_p[1]),
                                     _pc(ci_c[0]), _pc(ci_c[1])))
        else:
            verdict = ("Picks beat random with non-overlapping 95%% intervals: "
                       "%s (%d/%d, %s-%s) vs %s (%d/%d, %s-%s). This is the first "
                       "grade of actual evidence for skill."
                       % (_pc(pr), h_p, n_p, _pc(ci_p[0]), _pc(ci_p[1]),
                          _pc(cr), h_c, n_c, _pc(ci_c[0]), _pc(ci_c[1])))
    return {"as_of": tiso, "tampered": False,
            "calls_total": len(call_bodies), "calls_open": len(open_calls),
            "next_maturity": next_mat,
            "picks_matured": n_p, "pick_hits": h_p,
            "pick_rate": (h_p / n_p) if n_p else None,
            "pick_ci95": [round(ci_p[0], 3), round(ci_p[1], 3)],
            "controls_matured": n_c, "control_hits": h_c,
            "control_rate": (h_c / n_c) if n_c else None,
            "control_ci95": [round(ci_c[0], 3), round(ci_c[1], 3)],
            "ungradeable": ung,
            "median_lead_days": _median(leads),
            "verdict": verdict, "notes": notes}


# ================================================================== the entry point
def forecast(data, history_path="data/forecast_log.json", today=None,
             radar_history=None, radar_history_path="data/history.json"):
    """Write this week's PRE-REGISTERED call, then grade every past call that has
    matured. Returns (this_week_rows, graded_rows, scorecard). Never raises for a
    tampered log - it reports it and refuses to write, because the report IS the
    point."""
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = date.fromisoformat(today[:10])
    elif isinstance(today, datetime):
        today = today.date()
    tiso = today.isoformat()
    data = data or {}
    notes = []

    recs, problem = _load_log(history_path)
    if problem:
        verdict = (problem + ". No entry will be written and no score will be "
                   "computed. Restore the log from git history - it is committed "
                   "by the daily run precisely so that this is always possible.")
        print("  forecast: " + verdict)
        return [], [], {"as_of": tiso, "tampered": True, "verdict": verdict,
                        "calls_total": None, "picks_matured": None, "notes": []}

    if radar_history is None:
        try:
            with open(radar_history_path) as fh:
                radar_history = json.load(fh)
        except Exception:
            radar_history = []
    hist = sorted([h for h in (radar_history or []) if h.get("date")],
                  key=lambda h: h["date"])

    iso = today.isocalendar()
    week = "%04d-W%02d" % (iso[0], iso[1])
    bodies = []           # everything this run appends, in order

    calls = [r["body"] for r in recs if r["body"].get("type") == "call"]
    watches = [r["body"] for r in recs if r["body"].get("type") == "watch"]
    grade_bodies = [r["body"] for r in recs if r["body"].get("type") == "grade"]
    graded_weeks = {g["week"] for g in grade_bodies}
    week_done = any(b.get("week") == week for b in calls) or \
        any(r["body"].get("type") == "no_call" and r["body"].get("week") == week
            for r in recs)

    # ---- 1. THE CALL: freeze this week's top-3, once, on the first run of the week
    this_call = next((c for c in calls if c.get("week") == week), None)
    if not week_done:
        status = data.get("status") or {}
        ok = [k for k in VOTING_SOURCES if status.get(k) == "ok"]
        stack = build_stack(data)
        picks = [r for r in stack if r["stage"] in PICKABLE][:TOP_N]
        if status and len(ok) < MIN_OK_SOURCES:
            reason = ("only %d of %d voting sources loaded today (ok: %s). A call "
                      "frozen off a broken board would later be graded as if it were "
                      "a real claim. No call this week."
                      % (len(ok), len(VOTING_SOURCES), ", ".join(ok) or "none"))
            bodies.append({"type": "no_call", "date": tiso, "week": week,
                           "reason": reason})
            notes.append("no call this week: " + reason)
        elif not picks:
            reason = ("nothing on the board makes a rising-and-not-yet-mainstream "
                      "claim (no niche at stage Emerging / Search only / Building "
                      "out). An honest radar is allowed to have nothing to say.")
            bodies.append({"type": "no_call", "date": tiso, "week": week,
                           "reason": reason})
            notes.append("no call this week: " + reason)
        else:
            snap_tiers = _hist_tiers_from_data(data)
            picked = {r["niche"] for r in picks}
            pool = [r["niche"] for r in stack
                    if r["stage"] != "nodata" and r["niche"] not in picked]
            controls, seed_material = _draw_controls(week, pool, len(picks))
            stack_by = {r["niche"]: r for r in stack}
            sels = [_selection(r["niche"], "pick", i + 1, stack_by, snap_tiers, today)
                    for i, r in enumerate(picks)]
            sels += [_selection(n, "control", None, stack_by, snap_tiers, today)
                     for n in controls]
            this_call = {"type": "call", "date": tiso, "week": week,
                         "horizon_days": HORIZON_DAYS,
                         "matures": (today + timedelta(days=HORIZON_DAYS)).isoformat(),
                         "selections": sels,
                         "pool": sorted(set(pool)), "control_seed": seed_material,
                         "sources": dict(status)}
            bodies.append(this_call)
            calls = calls + [this_call]
    all_calls = calls

    # ---- 2. WATCHES: history.json only holds ~60 days, so record progressions as
    # they happen or lose them. First sighting + one confirmation >= 7 days later.
    latest = hist[-1] if hist else None
    if latest:
        for c in all_calls:
            if c["week"] in graded_weeks:
                continue
            if not (c["date"] < latest["date"] <= c["matures"]):
                continue
            for sel in c["selections"]:
                if sel["fired_at_call"] >= len(TIERS):
                    continue
                now_f = _fired_count(latest, sel["niche"])
                if now_f <= sel["fired_at_call"]:
                    continue
                ws = [w for w in watches
                      if w["week"] == c["week"] and w["niche"] == sel["niche"]]
                if any(w.get("snapshot_date") == latest["date"] for w in ws):
                    continue
                if len(ws) == 0:
                    nth = 1
                elif len(ws) == 1 and (date.fromisoformat(latest["date"])
                                       - date.fromisoformat(ws[0]["snapshot_date"])
                                       ).days >= CONFIRM_GAP_DAYS:
                    nth = 2
                else:
                    continue          # already confirmed, or too soon to confirm
                w = {"type": "watch", "date": tiso, "week": c["week"],
                     "niche": sel["niche"], "role": sel["role"], "nth": nth,
                     "snapshot_date": latest["date"], "fired_now": now_f,
                     "fired_at_call": sel["fired_at_call"]}
                bodies.append(w)
                watches.append(w)

    # ---- 3. GRADING: every call whose horizon has matured, graded once, by the
    # rule written into the prediction itself. Same rule for pick and control.
    new_grades = []
    for c in all_calls:
        if c["week"] in graded_weeks or tiso < c["matures"]:
            continue
        target = date.fromisoformat(c["matures"])
        cand = [h for h in hist
                if abs((date.fromisoformat(h["date"]) - target).days)
                <= MATURITY_WINDOW_DAYS]
        msnap = min(cand, key=lambda h: abs((date.fromisoformat(h["date"])
                                             - target).days)) if cand else None
        results = []
        for sel in c["selections"]:
            n, base = sel["niche"], sel["fired_at_call"]
            ws = sorted([w for w in watches
                         if w["week"] == c["week"] and w["niche"] == n
                         and w["snapshot_date"] <= c["matures"]],
                        key=lambda w: w["snapshot_date"])
            confirmed = (len(ws) >= 2
                         and (date.fromisoformat(ws[-1]["snapshot_date"])
                              - date.fromisoformat(ws[0]["snapshot_date"])
                              ).days >= CONFIRM_GAP_DAYS)
            first = lead = None
            if base >= len(TIERS):
                out, why = "ungradeable", ("fired on all four tiers at call time - "
                                           "no later tier existed to predict")
            elif msnap is None and not confirmed:
                out, why = "ungradeable", ("no history snapshot within %d days of "
                                           "maturity and no confirmed sightings. The "
                                           "radar was dark, not the niche - excluded "
                                           "from the score rather than counted either "
                                           "way" % MATURITY_WINDOW_DAYS)
            elif confirmed or (msnap is not None
                               and _fired_count(msnap, n) > base):
                out = "hit"
                if ws:
                    first = ws[0]["snapshot_date"]
                else:
                    firsts = [h["date"] for h in hist
                              if c["date"] < h["date"] <= msnap["date"]
                              and _fired_count(h, n) > base]
                    first = firsts[0] if firsts else msnap["date"]
                lead = (date.fromisoformat(first)
                        - date.fromisoformat(c["date"])).days
                why = ("fired on more tiers than at call (was %d)%s"
                       % (base, ", confirmed by two sightings" if confirmed else
                          ", shown at the maturity snapshot"))
            else:
                out = "miss"
                why = ("no progression: still firing on <= %d tier(s) at the "
                       "maturity snapshot (%s), no confirmed sightings in between"
                       % (base, msnap["date"]))
            results.append({"niche": n, "role": sel["role"], "outcome": out,
                            "fired_at_call": base, "first_evidence": first,
                            "days_to_progress": lead, "note": why})
        g = {"type": "grade", "date": tiso, "week": c["week"],
             "call_date": c["date"], "matured": c["matures"],
             "snapshot_used": msnap["date"] if msnap else None,
             "results": results}
        bodies.append(g)
        new_grades.append(g)
        graded_weeks.add(c["week"])
    grade_bodies = grade_bodies + new_grades

    # ---- 4. write, score, return
    if bodies:
        try:
            recs = _append(history_path, recs, bodies)
        except ValueError as e:
            notes.append("append refused: %s" % e)
            print("  forecast: append refused - %s" % e)

    sc = _scorecard(grade_bodies, all_calls, today, notes)
    this_week_rows = []
    if this_call:
        for sel in this_call["selections"]:
            row = dict(sel)
            row.update({"week": this_call["week"], "date": this_call["date"],
                        "matures": this_call["matures"]})
            this_week_rows.append(row)
    graded_rows = [dict(r, week=g["week"], call_date=g["call_date"],
                        graded=g["date"])
                   for g in grade_bodies for r in g.get("results") or []]

    act = ("call frozen: " + ", ".join(s["niche"] for s in this_call["selections"]
                                       if s["role"] == "pick")
           if this_call and this_call["date"] == tiso else
           "call already on file for %s" % week if this_call else
           "no call this week")
    print("  forecast: %s | %d calls, %d graded picks | %s"
          % (act, sc["calls_total"], sc["picks_matured"], sc["verdict"][:110]))
    return this_week_rows, graded_rows, sc


# ======================================================================== selftest
def _fixture_data(single=False):
    """Synthetic board. ADHD = Emerging (T2 fires on a solid base). Skin boosters =
    Search only. Longevity = Building out (T1 + T3). The rest are quiet pool."""
    d = {
        "waits": [],
        "trends": [
            {"name": "adhd assessment", "niche": "ADHD", "latest": 60, "g12": 5.0},
            {"name": "menopause clinic", "niche": "Menopause", "latest": 40, "g12": 0.0},
            {"name": "hair transplant", "niche": "Hair", "latest": 30, "g12": -2.0},
            {"name": "veneers", "niche": "Dental", "latest": 25, "g12": 1.0},
            {"name": "iv drip", "niche": "IV therapy", "latest": 20, "g12": 2.0},
        ],
        "inc": [{"name": "adhd", "niche": "ADHD", "latest": 40, "g12": 50.0},
                {"name": "meno", "niche": "Menopause", "latest": 20, "g12": 2.0}],
        "aes": [], "cqc": [], "presc": [], "invest": {},
        "status": {"trends": "ok", "inc": "ok", "cqc": "ok", "presc": "ok"},
    }
    if not single:
        d["trends"] += [
            {"name": "skin boosters", "niche": "Skin boosters", "latest": 55, "g12": 30.0},
            {"name": "longevity clinic", "niche": "Longevity", "latest": 45, "g12": 25.0},
        ]
        d["cqc"] += [{"name": "longevity", "niche": "Longevity", "latest": 30, "g12": 20.0}]
    return d


def selftest():
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        print("  %s  %s" % ("PASS" if cond else "FAIL", name))
        ok = ok and bool(cond)

    tmp = tempfile.mkdtemp(prefix="forecast_test_")
    log = os.path.join(tmp, "forecast_log.json")
    fx = _fixture_data()

    # 1. a call is written, with picks in stack order and one control per pick
    rows, graded, sc = forecast(fx, log, today="2026-07-13", radar_history=[])
    picks = [r for r in rows if r["role"] == "pick"]
    ctrls = [r for r in rows if r["role"] == "control"]
    check("call written with 3 picks", [p["niche"] for p in picks]
          == ["ADHD", "Skin boosters", "Longevity"])
    check("one control per pick, drawn from the pool, never a pick",
          len(ctrls) == 3 and not ({c["niche"] for c in ctrls}
                                   & {p["niche"] for p in picks}))
    recs, prob = _load_log(log)
    check("chain verifies after first write", prob is None and len(recs) == 1)

    # 2. the same call is NOT rewritten on a second run in the same week
    rows2, _, _ = forecast(fx, log, today="2026-07-14", radar_history=[])
    recs2, _ = _load_log(log)
    check("second run in same week appends nothing",
          len(recs2) == 1 and recs2[0]["hash"] == recs[0]["hash"])
    check("second run returns the same frozen call",
          [r["niche"] for r in rows2] == [r["niche"] for r in rows])

    # 3. a matured call is graded correctly (ADHD + Skin boosters progress, the
    # rest do not; controls stay quiet)
    mat_hist = [
        {"date": "2027-07-12",
         "t1": {"ADHD": 20.0, "Skin boosters": 30.0, "Longevity": 25.0},
         "t2": {"ADHD": 50.0},
         "t3": {"ADHD": 30.0, "Skin boosters": 15.0, "Longevity": 20.0},
         "t4": {}}]
    _, graded, sc = forecast(fx, log, today="2027-07-14", radar_history=mat_hist)
    by = {(r["week"], r["niche"]): r for r in graded}
    g_adhd = by.get(("2026-W29", "ADHD"))
    g_skin = by.get(("2026-W29", "Skin boosters"))
    g_long = by.get(("2026-W29", "Longevity"))
    c_out = [r["outcome"] for r in graded
             if r["week"] == "2026-W29" and r["role"] == "control"]
    check("matured pick that progressed grades HIT",
          g_adhd and g_adhd["outcome"] == "hit" and g_skin
          and g_skin["outcome"] == "hit")
    check("matured pick that did not progress grades MISS",
          g_long and g_long["outcome"] == "miss")
    check("quiet controls grade MISS by the identical rule",
          c_out == ["miss", "miss", "miss"])
    check("lead time recorded from first evidence",
          g_adhd["days_to_progress"] == 364)
    check("scorecard refuses a verdict on n=3 and says so",
          sc["picks_matured"] == 3 and "TOO FEW" in sc["verdict"].upper())

    # 4. a hash-chain tamper is DETECTED and the module refuses to continue
    with open(log) as fh:
        raw = json.load(fh)
    raw["entries"][0]["body"]["selections"][0]["niche"] = "Menopause"  # the fraud
    with open(log, "w") as fh:
        json.dump(raw, fh)
    n_before = len(raw["entries"])
    rows_t, graded_t, sc_t = forecast(fx, log, today="2027-07-20",
                                      radar_history=mat_hist)
    with open(log) as fh:
        after = json.load(fh)
    check("tamper detected", sc_t.get("tampered") is True
          and "TAMPER" in sc_t["verdict"])
    check("tampered log is not appended to and returns no rows",
          len(after["entries"]) == n_before and rows_t == [] and graded_t == [])

    # 5. at n=1 the scorecard says 'too few to say' and the CI spans nearly all
    log2 = os.path.join(tmp, "forecast_log_single.json")
    fx1 = _fixture_data(single=True)
    forecast(fx1, log2, today="2026-07-13", radar_history=[])
    _, _, sc1 = forecast(fx1, log2, today="2027-07-14", radar_history=[
        {"date": "2027-07-12", "t1": {"ADHD": 20.0}, "t2": {"ADHD": 50.0},
         "t3": {}, "t4": {}}])
    lo, hi = sc1["pick_ci95"]
    check("n=1: 'too few' verdict, no naked 100%",
          sc1["picks_matured"] == 1 and sc1["pick_hits"] == 1
          and "TOO FEW" in sc1["verdict"].upper() and (hi - lo) > 0.6)

    # 6. the control draw is deterministic given the seed inputs
    pool = ["Menopause", "Hair", "Dental", "IV therapy", "Sleep"]
    a, seed_a = _draw_controls("2026-W29", pool, 3)
    b, seed_b = _draw_controls("2026-W29", list(reversed(pool)), 3)
    c, _ = _draw_controls("2026-W30", pool, 3)
    check("same week + same board -> same controls, order-independent",
          a == b and seed_a == seed_b)
    recorded = raw["entries"][0]["body"]
    redraw, _ = _draw_controls(recorded["week"], recorded["pool"], 3)
    check("recorded pool + week reproduces the recorded controls (pre-tamper "
          "entry 0)", redraw == [s["niche"] for s in recorded["selections"]
                                 if s["role"] == "control"])

    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)
    print("usage: python3 forecast.py --selftest")
