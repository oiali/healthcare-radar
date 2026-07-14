#!/usr/bin/env python3
"""
WEEKLY DIGEST - the alerting layer.

WHY THIS EXISTS
---------------
The dashboard refreshes every morning and then tells nobody anything. A radar you
have to remember to look at catches nothing. This turns the daily rebuild into one
weekly push notification that either names what crossed a line, or says - in one
line, and without apology - that nothing did.

The failure mode this module is written to avoid is NOT "missing a signal". It is
"crying wolf". A digest that finds something exciting every single Monday gets
filtered to a folder in a month and the radar is dead again. So the default answer
here is "nothing happened", and a claim has to get past three gates to be printed:

  1. THRESHOLD   the niche's volume-weighted 12-month growth for a tier crossed the
                 same +10% line the dashboard uses (RISING in pull_and_build.py).
  2. MARGIN      it cleared that line by >= 2 percentage points. A niche going from
                 9.8% to 10.3% has not "started firing", it has wobbled. Without
                 hysteresis, any niche sitting near the line generates a "crossed!"
                 and an "un-crossed!" on alternate weeks forever.
  3. VOLUME      the underlying counts are big enough for a percentage to mean
                 anything. See NOISE FLOOR below - this is the gate that does the
                 most work.

Everything blocked by gate 2 or 3 is printed anyway, under "ignore these", with the
reason. The digest defends him against its own output.

NOISE FLOOR - justification
---------------------------
Counts of new registrations/incorporations behave roughly like Poisson draws: the
standard deviation of a count n is about sqrt(n). So the noise on the count alone is:

    n = 3   -> +/- 58%      a "+200%" headline is under two sd of nothing
    n = 4   -> +/- 50%
    n = 8   -> +/- 35%
    n = 25  -> +/- 20%
    n = 100 -> +/- 10%

pull_and_build already drops rows with latest < 4 and refuses a 12-month growth
number unless the prior window had >= 3. That is not enough: a 4 -> 12 move clears
both of those filters and prints "+200%", and it is noise. MIN_BASE = 8 on BOTH the
current and the prior window is the floor here. At 8 vs 8 the noise band is roughly
+/-35% each side, so a move has to be large (~+50% or more) before it is even
arguably real - which is the honest state of a CQC/Companies House count for a niche
this small. It is not a strict statistical test and is not presented as one; it is a
floor chosen so that the digest stops quoting percentages it cannot defend.

The prior window is not in data.json, but it is recoverable exactly:
    prior = latest / (1 + g12/100)
because g12 was computed as pct(latest, prior). So both sides of the floor are
testable from the data we have.

At NICHE level (the tier aggregates in history.json) the floor is a minimum total
volume, and the units differ by tier because the underlying sources do:
    t1  Google Trends index, 0-100, integer. Below ~15 a single integer increment is
        a >5% move, and 2 -> 6 is "+200%". Floor: 15.
    t2  count of incorporations.            Floor: 8, per the Poisson argument.
    t3  count of CQC registrations.         Floor: 8, same.

HONEST LIMIT on that floor: history.json stores only the weighted growth per niche,
not the weight. So the volume gate can only be applied using THIS WEEK's volumes. If
a niche was thin last week and is fat this week, the gate passes. Stated in the
digest's own confidence line rather than hidden here.

WHAT THIS CANNOT SEE
--------------------
T4 (NHS prescribing, OpenPrescribing) is fetched client-side in the visitor's
browser because OpenPrescribing 403s datacentre IPs. It is therefore NOT in
data.json and NOT in this digest. Every digest says so. Do not read "nothing
crossed" as covering prescribing - it does not.

Also absent from the tier history: Adzuna job ads. pull_and_build.whats_moved()
builds its snapshots from trends/inc/cqc only, so t3 == CQC registrations alone.
Job ads appear in data.json but never in the week-on-week comparison.

Stdlib only. Public entry point:

    digest(data, history) -> (subject, body_markdown, body_html)

CLI:
    python3 digest.py --selftest        # synthetic fixtures, no network, PASS/FAIL
    python3 digest.py --write           # write digest.md + digest.html from data.json
    python3 digest.py --write --issue   # ...and open a GitHub Issue (Mondays only)
    python3 digest.py --write --issue --force   # ...on any day
"""

import os
import sys
import json
import html
import urllib.request
from datetime import date, timedelta

# ------------------------------------------------------------------ thresholds
RISING = 10.0          # must match pull_and_build.RISING - a tier "fires" at +10%
MARGIN = 2.0           # hysteresis: ignore crossings that clear the line by less
MIN_BASE = 8           # row-level: min count in BOTH windows before quoting a %
MIN_WEIGHT = {"t1": 15.0, "t2": 8.0, "t3": 8.0}   # niche-level volume floor
TOP_N = 3              # "entered the top of a tier" means the top 3
BASELINE_DAYS = 6      # a baseline snapshot must be at least this old
STALE_DAYS = 14        # ...and if it is older than this, say so

TIER = ("t1", "t2", "t3")
TIER_NAME = {"t1": "search interest",
             "t2": "new company incorporations",
             "t3": "new clinic registrations"}
TIER_SRC = {"t1": "Google Trends GB, 4-week mean vs the same 4 weeks 12 months ago",
            "t2": "Companies House, last 3 months vs the same 3 months a year ago",
            "t3": "CQC monthly file, last 12 months vs the 12 before"}
TIER_KEY = {"t1": "trends", "t2": "inc", "t3": "cqc"}

STATE_FILE = "data/digest_state.json"


# ------------------------------------------------------------------- utilities
def _f(v, dp=1):
    """Signed percentage, or 'n/a'."""
    if v is None:
        return "n/a"
    return "%+.*f%%" % (dp, v)


def _implied_base(row):
    """Recover the prior-window count from latest and g12. Exact, because g12 was
    computed as (latest/prior - 1) * 100. Returns None when g12 is missing."""
    g = row.get("g12")
    n = row.get("latest")
    if g is None or n is None:
        return None
    denom = 1.0 + g / 100.0
    if denom <= 0:
        return None
    return n / denom


def _weights(data):
    """{tier: {niche: total volume}} - reproduces pull_and_build.agg()'s weighting
    exactly (same row filter, same max(latest,1)), so the weight we test is the
    weight that produced the number in history.json."""
    out = {t: {} for t in TIER}
    for t in TIER:
        for r in data.get(TIER_KEY[t]) or []:
            n, g = r.get("niche"), r.get("g12")
            if not n or g is None:
                continue
            out[t][n] = out[t].get(n, 0.0) + max(r.get("latest") or 1, 1)
    return out


def _thin(tier, niche, weights):
    """True when this niche/tier's volume is below the floor for its units."""
    return weights.get(tier, {}).get(niche, 0.0) < MIN_WEIGHT[tier]


def _baseline(history):
    """(now_snapshot, prev_snapshot, note). prev is the newest snapshot at least
    BASELINE_DAYS old. None when there isn't one - which is the honest answer for
    the first fortnight of a new radar, and must not be papered over."""
    hist = [h for h in (history or []) if h.get("date")]
    hist.sort(key=lambda h: h["date"])
    if not hist:
        return None, None, "history.json is empty - no comparison possible."
    now = hist[-1]
    cut = (_d(now["date"]) - timedelta(days=BASELINE_DAYS)).isoformat()
    older = [h for h in hist[:-1] if h["date"] <= cut]
    if not older:
        return now, None, ("No baseline at least %d days old (history holds %d "
                           "day%s). Nothing can be called a change yet."
                           % (BASELINE_DAYS, len(hist), "" if len(hist) == 1 else "s"))
    prev = older[-1]
    gap = (_d(now["date"]) - _d(prev["date"])).days
    if gap > STALE_DAYS:
        return now, prev, ("Baseline is %d days old (%s), not 7. The daily job did "
                           "not run in between. Read the moves as 'since then', not "
                           "'this week'." % (gap, prev["date"]))
    return now, prev, None


def _d(s):
    return date(*[int(x) for x in s.split("-")[:3]])


def _val(snap, tier, niche):
    v = (snap.get(tier) or {}).get(niche)
    return v if isinstance(v, (int, float)) else None


# ---------------------------------------------------------------- the movements
def _crossings(now, prev, weights):
    """Returns (up, down, suppressed). A crossing is a tier's weighted 12-month
    growth moving across the +10% line since the baseline."""
    up, down, sup = [], [], []
    for t in TIER:
        names = set(now.get(t) or {}) | set(prev.get(t) or {})
        for n in sorted(names):
            a, b = _val(prev, t, n), _val(now, t, n)

            if b is None and a is not None:
                if a >= RISING:
                    sup.append("%s has dropped out of %s entirely (was %s). That is "
                               "the source no longer returning rows for it, not the "
                               "niche cooling. Do not read it either way."
                               % (n, TIER_NAME[t], _f(a)))
                continue
            if b is None:
                continue

            fires_now = b >= RISING
            entered = a is None and fires_now

            if entered:
                if _thin(t, n, weights):
                    sup.append("%s appears in %s at %s, but on a base of %d - too "
                               "thin to quote." % (n, TIER_NAME[t], _f(b),
                                                   int(weights[t].get(n, 0))))
                elif b < RISING + MARGIN:
                    sup.append("%s appears in %s at %s - inside the %.0fpp noise band "
                               "around the +10%% line. Not a crossing."
                               % (n, TIER_NAME[t], _f(b), MARGIN))
                else:
                    up.append({"niche": n, "tier": t, "was": None, "now": b,
                               "weight": weights[t].get(n, 0.0), "new_to_tier": True})
                continue

            fired_before = a >= RISING
            if fires_now == fired_before:
                continue

            adjacent = abs(b - RISING) < MARGIN or abs(a - RISING) < MARGIN
            thin = _thin(t, n, weights)
            rec = {"niche": n, "tier": t, "was": a, "now": b,
                   "weight": weights[t].get(n, 0.0), "new_to_tier": False}

            if thin:
                sup.append("%s %s %s in %s (%s -> %s) on a base of %d. Below the "
                           "volume floor of %g - the percentage is not measuring "
                           "anything." % (n, "crossed into" if fires_now else
                                          "fell out of", "firing", TIER_NAME[t],
                                          _f(a), _f(b), int(weights[t].get(n, 0)),
                                          MIN_WEIGHT[t]))
            elif adjacent:
                sup.append("%s moved %s -> %s in %s. It crossed +10%% but by less "
                           "than %.0fpp - that is a wobble on the line, not a signal."
                           % (n, _f(a), _f(b), TIER_NAME[t], MARGIN))
            elif fires_now:
                up.append(rec)
            else:
                down.append(rec)

    up.sort(key=lambda r: -(r["now"] or 0))
    down.sort(key=lambda r: (r["now"] or 0))
    return up, down, sup


def _tops(now, prev, weights, already):
    """Niches that entered the top TOP_N of a tier since the baseline. Ranked on the
    same weighted growth, and only counting niches that clear the volume floor -
    otherwise the top of every tier is whatever tiny thing bounced."""
    out = []
    for t in TIER:
        def rank(snap):
            rows = [(v, n) for n, v in (snap.get(t) or {}).items()
                    if isinstance(v, (int, float)) and not _thin(t, n, weights)]
            rows.sort(reverse=True)
            return [n for _, n in rows[:TOP_N]]
        a, b = rank(prev), rank(now)
        if not a:
            continue
        for i, n in enumerate(b):
            if n in a or (n, t) in already:
                continue
            out.append({"niche": n, "tier": t, "rank": i + 1,
                        "now": _val(now, t, n), "was": _val(prev, t, n)})
    return out


def _watchlist(now, weights):
    """Still early: the lead tiers are lit and the lag tier is not.

    T1 (search) and T2 (new companies) are the lead indicators; T3 (CQC clinic
    registrations) is the lag. People are looking and founders are moving, but the
    capacity has not been built yet - so you are seeing it before it is obvious.
    Once T3 lights up, everyone who reads the same signal is looking at it too.

    A niche with NO T3 value at all is not the same as a niche whose T3 is flat, and
    the two are labelled differently: absence of capacity and absence of measurement
    look identical here and the radar cannot tell them apart. The known case is
    aesthetics - a botox/filler-only clinic is not CQC-registrable at all - so a dark
    T3 there is meaningless, and it is called out by name.
    """
    out = []
    for n in sorted(set(now.get("t1") or {}) | set(now.get("t2") or {})):
        lit = [t for t in ("t1", "t2")
               if (_val(now, t, n) or -99) >= RISING and not _thin(t, n, weights)]
        if not lit:
            continue
        t3 = _val(now, "t3", n)
        if t3 is not None and t3 >= RISING:
            continue
        out.append({"niche": n, "lit": lit,
                    "t1": _val(now, "t1", n), "t2": _val(now, "t2", n), "t3": t3,
                    "t3_absent": t3 is None})
    out.sort(key=lambda r: (-len(r["lit"]), -(r["t1"] or r["t2"] or 0)))
    return out


def _new_phrases(data, state):
    """Phrases that are in the data now and were not at the last digest.

    'isnew' in data.json means "no matching registrations in the same window a year
    ago" - it does NOT mean "new since last week", and it is true of the same rows
    every day. Reporting it weekly would be a standing list dressed up as news. So
    novelty is measured against digest_state.json, which this module writes. On the
    first run there is no state and the section is suppressed outright rather than
    dumping forty phrases and calling them all new.
    """
    if not state or not state.get("phrases"):
        return None, "First digest - no phrase baseline yet. From next week this "\
                     "section reports phrases that were not in the data last week."
    seen = state["phrases"]
    out = []
    for t in ("t2", "t3"):
        key = TIER_KEY[t]
        prior = set(seen.get(t) or [])
        for r in data.get(key) or []:
            nm = r.get("name")
            base = r.get("latest") or 0
            if not nm or nm in prior:
                continue
            if base < MIN_BASE:
                continue
            out.append({"name": nm, "tier": t, "latest": base,
                        "niche": r.get("niche"), "isnew": bool(r.get("isnew"))})
    out.sort(key=lambda r: -r["latest"])
    return out[:5], None


def _thin_rows(data):
    """Row-level percentages that fail the base floor. These are the numbers most
    likely to catch his eye on the dashboard and they are the ones worth the least."""
    bad = []
    for t in ("t2", "t3"):
        for r in data.get(TIER_KEY[t]) or []:
            g, n = r.get("g12"), r.get("latest") or 0
            if g is None or g < 50:
                continue
            p = _implied_base(r)
            if p is None:
                continue
            if n < MIN_BASE or p < MIN_BASE:
                bad.append({"name": r.get("name"), "tier": t, "g12": g,
                            "now": n, "prior": int(round(p))})
    bad.sort(key=lambda r: -r["g12"])
    return bad[:5]


def update_state(data, state=None):
    """The phrase memory the novelty test needs. Kept small on purpose."""
    ph = {}
    for t in ("t2", "t3"):
        ph[t] = sorted({r.get("name") for r in (data.get(TIER_KEY[t]) or [])
                        if r.get("name")})
    return {"phrases": ph, "date": date.today().isoformat()}


# ===================================================================== the digest
def digest(data, history, state=None):
    """(subject, body_markdown, body_html). See module docstring for the gates."""
    data = data or {}
    now, prev, note = _baseline(history)
    weights = _weights(data)
    today = _d(now["date"]) if now else date.today()
    upd = (data.get("updated") or "")[:16].replace("T", " ")

    sec = []          # [{"title", "lead", "bullets"}]
    headline = "nothing crossed a threshold"
    np_note = None

    # ---- 1. what crossed a line
    if prev is None:
        sec.append({"title": "What crossed a line",
                    "lead": note or "No baseline.", "bullets": []})
        headline = "no baseline yet"
        up = down = tops = []
        sup = []
    else:
        up, down, sup = _crossings(now, prev, weights)
        tops = _tops(now, prev, weights, {(r["niche"], r["tier"]) for r in up})

        bl = []
        for r in up:
            if r["new_to_tier"]:
                bl.append("%s now fires on %s at %s. It had no reading on this tier "
                          "at the baseline, so this is a first appearance above the "
                          "line, not an acceleration. Volume behind it: %d."
                          % (r["niche"], TIER_NAME[r["tier"]], _f(r["now"]),
                             int(r["weight"])))
            else:
                also = [TIER_NAME[t] for t in TIER
                        if t != r["tier"] and (_val(now, t, r["niche"]) or -99) >= RISING]
                tail = (" Already firing on " + " and ".join(also) + "."
                        if also else " It is not firing on any other tier.")
                bl.append("%s started firing on %s: %s, was %s on %s. Volume behind "
                          "it: %d.%s"
                          % (r["niche"], TIER_NAME[r["tier"]], _f(r["now"]),
                             _f(r["was"]), prev["date"], int(r["weight"]), tail))
        for r in tops:
            bl.append("%s entered the top %d of %s (rank %d, %s, was %s). It was "
                      "already above the line - this is a ranking change, weaker "
                      "than a crossing."
                      % (r["niche"], TOP_N, TIER_NAME[r["tier"]], r["rank"],
                         _f(r["now"]), _f(r["was"])))

        np_rows, np_note = _new_phrases(data, state)
        if np_rows:
            for r in np_rows:
                bl.append("New phrase in %s: \"%s\" (%d, %s). Not in the data at the "
                          "last digest.%s"
                          % (TIER_NAME[r["tier"]], r["name"], r["latest"],
                             r["niche"] or "no niche mapped",
                             " No matching registrations a year ago either."
                             if r["isnew"] else ""))

        if bl:
            n_up = len(up)
            headline = "%d crossing%s" % (n_up, "" if n_up == 1 else "s") if n_up \
                else "no crossings, %d ranking change%s" % (len(tops),
                                                            "" if len(tops) == 1 else "s")
            sec.append({"title": "What crossed a line", "lead": None, "bullets": bl})
        else:
            # One line. No padding, no "but here are some things anyway".
            sec.append({"title": "What crossed a line",
                        "lead": "Nothing crossed a threshold this week.",
                        "bullets": []})

    # ---- 2. what's cooling
    if prev is not None:
        if down:
            bl = ["%s stopped firing on %s: %s, was %s on %s. Volume behind it: %d."
                  % (r["niche"], TIER_NAME[r["tier"]], _f(r["now"]), _f(r["was"]),
                     prev["date"], int(r["weight"])) for r in down]
            sec.append({"title": "What is cooling", "lead": None, "bullets": bl})
            headline += ", %d cooling" % len(down)
        else:
            sec.append({"title": "What is cooling",
                        "lead": "Nothing stopped firing this week.", "bullets": []})

    # ---- 3. the early-stage watchlist
    wl = _watchlist(now or {}, weights)
    if wl:
        bl = []
        for r in wl:
            lit = " and ".join(TIER_NAME[t] for t in r["lit"])
            if r["t3_absent"]:
                t3s = ("no clinic-registration reading at all - CQC returned no rows "
                       "for it. That is either capacity not yet built or capacity the "
                       "regulator cannot see, and the radar cannot tell you which")
                if "esthetic" in r["niche"]:
                    t3s += (". For this niche it is the second: botox and filler-only "
                            "clinics are not CQC-registrable, so tier 3 is blind here")
            else:
                t3s = "clinic registrations at %s, below the line" % _f(r["t3"])
            bl.append("%s: %s lit (search %s, companies %s); %s."
                      % (r["niche"], lit, _f(r["t1"]), _f(r["t2"]), t3s))
        sec.append({"title": "Early-stage watchlist (early tiers lit, clinics not)",
                    "lead": "Demand and founders present, capacity not yet built. "
                            "This is the window in which the operators are still "
                            "cheap. It is a standing list, not a weekly event.",
                    "bullets": bl})
    else:
        sec.append({"title": "Early-stage watchlist (early tiers lit, clinics not)",
                    "lead": "Empty. No niche currently has an early tier above the "
                            "line with clinic registrations below it.",
                    "bullets": []})

    # ---- 4. what to ignore
    ig = list(sup)
    for r in _thin_rows(data):
        ig.append("\"%s\" in %s shows %s, but that is %d -> %d. On counts this small "
                  "the noise alone is about +/-%d%%. Ignore the percentage; the "
                  "absolute number is the only thing being said."
                  % (r["name"], TIER_NAME[r["tier"]], _f(r["g12"]), r["prior"],
                     r["now"], int(round(100 / max(r["prior"], 1) ** 0.5))))
    if ig:
        sec.append({"title": "Ignore these",
                    "lead": "Signals that look like something and are not:",
                    "bullets": ig})
    else:
        sec.append({"title": "Ignore these",
                    "lead": "Nothing was suppressed this week.", "bullets": []})

    # ---- 5. confidence
    conf = [
        "Verified: the counts. Search index, Companies House incorporations and CQC "
        "registrations are read from the sources as-is.",
        "Inferred: the niche labels. Every row is mapped to a niche by keyword match "
        "on a company or clinic name. Names lie, and short keys collide with "
        "surnames. Treat any single-niche number as indicative.",
        "Assumed: that a +10% weighted 12-month growth means anything. It is a line "
        "drawn by hand, not a fitted threshold.",
        "Tier 4 (NHS prescribing) now runs on the server, from NHSBSA's own data "
        "with 12 years of history, so it IS in this digest. It used to be fetched in "
        "your browser and was invisible here.",
        "Job ads have been removed entirely: Adzuna's terms forbid using their data "
        "in aggregation, including vacancy counts, which was exactly our use.",
        "Windows differ by tier and are not comparable: %s; %s; %s."
        % (TIER_SRC["t1"], TIER_SRC["t2"], TIER_SRC["t3"]),
        "CQC publishes monthly. A tier-3 move is a step when the new file lands, not "
        "a weekly trend.",
        "The volume floor is applied using this week's volumes. history.json stores "
        "the growth per niche but not the volume behind it, so a niche that was thin "
        "at the baseline and is not thin now passes the gate.",
    ]
    if np_note:
        conf.insert(0, np_note)
    if note and prev is not None:
        conf.insert(0, note)
    sec.append({"title": "Confidence", "lead": None, "bullets": conf})

    subject = "Radar %s: %s" % (today.strftime("%d %b %Y"), headline)
    lead = ("Week to %s. Data last refreshed %s UTC. Baseline: %s."
            % (today.strftime("%d %b %Y"), upd or "unknown",
               prev["date"] if prev else "none"))
    return subject, _md(subject, lead, sec), _html(subject, lead, sec)


# ---------------------------------------------------------------------- render
def _md(subject, lead, sections):
    out = ["# " + subject, "", lead, ""]
    for s in sections:
        out.append("## " + s["title"])
        out.append("")
        if s["lead"]:
            out.append(s["lead"])
            out.append("")
        for b in s["bullets"]:
            out.append("- " + b)
        if s["bullets"]:
            out.append("")
    out.append("---")
    out.append("Dashboard: https://oiali.github.io/healthcare-radar/")
    return "\n".join(out).rstrip() + "\n"


def _html(subject, lead, sections):
    e = html.escape
    p = ['<!doctype html><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         "<title>%s</title>" % e(subject),
         "<style>body{max-width:46em;margin:2.5em auto;padding:0 1.2em;"
         "font:16px/1.55 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;"
         "color:#1c1c1c;background:#fff}"
         "h1{font-size:1.35em;font-weight:600;margin:0 0 .2em}"
         "h2{font-size:1em;font-weight:600;margin:2em 0 .5em;color:#000}"
         "p.lead{color:#555;margin:0 0 2em}"
         "ul{padding-left:1.1em;margin:.4em 0}li{margin:.45em 0}"
         "hr{border:0;border-top:1px solid #ddd;margin:2.5em 0 1em}"
         "a{color:#0a58ca}</style>",
         "<h1>%s</h1>" % e(subject),
         '<p class="lead">%s</p>' % e(lead)]
    for s in sections:
        p.append("<h2>%s</h2>" % e(s["title"]))
        if s["lead"]:
            p.append("<p>%s</p>" % e(s["lead"]))
        if s["bullets"]:
            p.append("<ul>" + "".join("<li>%s</li>" % e(b) for b in s["bullets"])
                     + "</ul>")
    p.append('<hr><p><a href="./">Dashboard</a></p>')
    return "\n".join(p) + "\n"


# ------------------------------------------------------------- GitHub delivery
def open_issue(subject, body_md):
    """POST an issue with the built-in GITHUB_TOKEN. No new secrets.

    Assignee AND @mention are both set on purpose - they are two independent
    notification paths (see digest_FINDINGS.md). If either the labels or the
    assignee are rejected we retry with a bare issue rather than lose the alert.
    """
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not (tok and repo):
        print("digest: no GITHUB_TOKEN/GITHUB_REPOSITORY - issue not created")
        return False
    owner = repo.split("/")[0]
    body = body_md + "\ncc @%s\n" % owner
    url = "https://api.github.com/repos/%s/issues" % repo
    hdr = {"Authorization": "Bearer " + tok,
           "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28",
           "Content-Type": "application/json",
           "User-Agent": "healthcare-radar-digest"}

    for payload in ({"title": subject, "body": body, "assignees": [owner],
                     "labels": ["radar-digest"]},
                    {"title": subject, "body": body}):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            print("digest: opened issue #%s %s" % (d.get("number"),
                                                   d.get("html_url")))
            return True
        except Exception as ex:
            print("digest: issue POST failed (%r) - retrying bare" % (ex,))
    return False


# -------------------------------------------------------------------- CLI/main
def _load(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def main(argv):
    force = "--force" in argv or os.environ.get("DIGEST_FORCE") == "1"
    data = _load("data.json", {}) or {}
    hist = _load("data/history.json", []) or []
    state = _load(STATE_FILE)

    subject, md, page = digest(data, hist, state)
    print(subject)

    if "--write" in argv:
        with open("digest.md", "w", encoding="utf-8") as fh:
            fh.write(md)
        with open("digest.html", "w", encoding="utf-8") as fh:
            fh.write(page)
        print("digest: wrote digest.md, digest.html")

    if "--issue" in argv:
        if date.today().weekday() != 0 and not force:
            print("digest: not Monday - no issue (DIGEST_FORCE=1 to override)")
            return 0
        os.makedirs("data/digests", exist_ok=True)
        with open("data/digests/%s.md" % date.today().isoformat(), "w",
                  encoding="utf-8") as fh:
            fh.write(md)
        if not open_issue(subject, md):
            # Loud on purpose. A silent failure here is the exact disease this
            # module was written to cure.
            print("::error::digest: the weekly alert did NOT go out")
            return 1
        # State is "the data as at the last digest that was SENT". Advance it only
        # once one actually went out - otherwise a failed Monday quietly eats the
        # phrase baseline and next week under-reports what is new.
        os.makedirs("data", exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(update_state(data, state), fh, indent=1)
        print("digest: state advanced -> " + STATE_FILE)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from digest_selftest import selftest
        raise SystemExit(0 if selftest() else 1)
    raise SystemExit(main(sys.argv[1:]))
