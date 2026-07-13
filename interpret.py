#!/usr/bin/env python3
"""
INTERPRET - read the radar as a BUYER, not as a venture investor.

WHAT WAS WRONG
--------------
The dashboard scored niches on a single axis called "Stage":

    1 Intent only -> 2 Entry (founders moving) -> 3 Build-out (capacity arriving)
    -> 4 Mainstream ("late - demand already served")

It rewarded EARLY and punished LATE. That is the correct instrument for someone
who FOUNDS a company. It is the wrong instrument, and often an inverted one, for
someone who BUYS companies. Three concrete inversions:

  * "2 Entry - founders moving" is shown as good news. For a buyer, founders
    moving in means competitors multiplying and asking prices going up.
  * "3 Build-out - capacity arriving" is shown as good news. It is the moment the
    supply of your acquisition targets is being diluted by fresh, unwilling-to-sell,
    fully-priced new entrants.
  * "4 Mainstream - likely priced in" is shown as a warning. A market with a large,
    ageing, standing population of owner-operators is the only kind of market a
    roll-up can exist in at all.

And the two engines cancelled: any niche early enough to be a "discovery" has no
clinics worth buying yet; any niche with a buyable population is no longer a
discovery. That is not two findings. It is one law, and the honest response is not
to fix the instrument - it is to admit the instrument was answering a question the
user does not have.

WHAT THIS DOES INSTEAD - TWO AXES, NOT ONE STAGE
------------------------------------------------
    DEMAND  - is there a market, and is it growing, flat, or rolling over?
    SUPPLY  - is there a population of businesses to BUY, and is it fragmented,
              still filling up with new entrants, or already consolidated?

The two axes are built from DIFFERENT tiers, and that is the point:

    DEMAND  <- T0 NHS waits, T1 search.        (T4 prescribing is AMBIGUOUS - see below)
    SUPPLY  <- CQC standing population (investability), T2 new companies,
               T3 new clinic registrations.

The old design read T1/T2/T3 as three independent confirmations of DEMAND. They
never were. T2 and T3 are the SUPPLY RESPONSE to demand. Splitting them is what
makes the whole thing legible - and it kills the T1 contamination problem
structurally, because T1's auto-discovered terms come from T2/T3, and T2/T3 no
longer vote on demand at all. The `independent` flag below is belt-and-braces on
top of that.

THE VALUABLE QUADRANT is not "earliest". It is:

    proven demand that is NOT falling
  + a deep population of independent owner-operators
  + new entrants have STOPPED arriving

"New entrants have stopped arriving" is the measurable proxy for "the boom is
over, price competition has arrived, and the owner who was turning patients away
in 2023 now wants out." It is computed as ENTRY RATE = new_12m / locations, both
of which investability.py already produces and currently throws away.

T4 IS AMBIGUOUS AND WE SAY SO
-----------------------------
Rising NHS prescribing has two readings and this data cannot separate them:
  (a) the condition is genuinely growing -> your private market grows too;
  (b) the NHS has started FUNDING the treatment -> your private market is
      being destroyed, because the patient can now get it free.
So T4 never votes on demand. It appears only as a caveat, with both readings
printed. When T4 rises while T1 (private search intent) FALLS, that pattern is
SUGGESTIVE of (b) - and it is flagged as suggestive, never as proof.

DENOMINATORS
------------
"+200%" on a base of two clinics is not a finding, it is a rumour with a decimal
point. Every tier here carries its base. A tier cannot "fire" unless:
  (1) it clears the substantive threshold (RISING, 10%), AND
  (2) its base clears MIN_BASE (10), AND
  (3) the move clears one standard deviation of Poisson counting noise on that
      base, i.e. 100/sqrt(base) percent.
Rule (3) is what kills "tongue-tie +200% (2 -> 6)": on a base of 2 the one-sigma
noise band is +/-71%, so nothing on a base of 2 can ever be believed.

Stdlib only.  Self-test:  python3 interpret.py --selftest
"""

import math

# ============================================================== THRESHOLDS
# Every number here is a judgement call. They are constants, in one place, with
# the reasoning, so they can be argued with rather than reverse-engineered.
# See interpret_FINDINGS.md section 4 for the full defence of each one.

# --- demand ---------------------------------------------------------------
# RISING: inherited unchanged from the existing dashboard (pull_and_build.RISING)
# so the new read does not silently move the goalposts at the same time as it
# changes the interpretation. It is NOT backtested. It never was.
RISING = 10.0
# BOOM: a 12-month move this large in search interest is not drift, it is a
# stampede. Judgement. Its only job is to trigger the "you will pay for that
# growth" warning, so being wrong here is cheap.
BOOM = 40.0
# FALLING: symmetric with RISING.
FALLING = -10.0

# --- denominators ---------------------------------------------------------
# MIN_BASE = 10: below ten, a percentage is theatre. At a base of 10 the
# one-sigma Poisson band is already +/-32%, so even here a "+15%" means nothing.
# The noise floor below does the real work; MIN_BASE is a hard stop under it.
MIN_BASE = 10

# --- supply ---------------------------------------------------------------
# Deliberately IDENTICAL to investability.py's constants. Do not re-derive them
# here: two modules disagreeing about what "too small" means is worse than either
# being wrong. Restated for the record:
#   MIN_TARGETS  30 - a platform plus ~8-12 bolt-ons, at a realistic ~1-in-5 hit
#                     rate on approaches to owner-operators, needs a pool in the
#                     high tens. Below 30 there is no acquirable population.
#   THIN_TARGETS 100 - between 30 and 99 you can build a regional platform, not a
#                     national consolidation. Say which.
#   TOP5 40% / HHI 0.20 - the conventional "highly concentrated" bands. Someone
#                     has already done the roll-up; you would be bidding against
#                     them.
MIN_TARGETS = 30
THIN_TARGETS = 100
TOP5_CONCENTRATED = 40.0
HHI_CONCENTRATED = 0.20

# ENTRY RATE = new registrations in the last 12 months / total standing stock.
# This is the NEW number and it is the WEAKEST-EVIDENCED number in the module.
# There is no published UK benchmark for clinic formation-to-stock ratio, so
# these two cuts are reasoned, not measured:
#   a steady-state market must register enough new sites to replace closures plus
#   modest net growth - call that mid-single-digit percent of stock per year;
#   a market where MORE THAN ONE SITE IN SEVEN opened in the last twelve months is
#   not steady-state, it is a gold rush, and you are bidding into it.
# If a single number in this file turns out to be wrong, it will be one of these
# two. They are the first thing to backtest.
ENTRY_HOT = 0.15
ENTRY_WARM = 0.08

# ================================================================== LABELS
# Plain English. No coined names, no branded quadrant jargon. Each label answers
# the only question that matters: which of the user's two businesses is this
# niche even eligible for - BUY (acquire clinics) or BUILD (open one)?
Q_BUY = "buy_window"
Q_WAIT = "wait_or_build"
Q_LATE = "too_late"
Q_BUILD = "build_only"
Q_DECLINING = "declining"
Q_NOTHING = "nothing_here"
Q_NODATA = "no_data"

LABELS = {
    Q_BUY:       "Buy - proven demand, owners still independent",
    Q_WAIT:      "Wait or build - new clinics still arriving",
    Q_LATE:      "Too late - someone has already consolidated it",
    Q_BUILD:     "Build, not buy - there are no clinics to acquire",
    Q_DECLINING: "Buy for cash only - demand is falling",
    Q_NOTHING:   "Nothing here yet",
    Q_NODATA:    "Not enough data to say",
}

# Sort order for the table: lower = more interesting to a BUYER.
RANK = {Q_BUY: 0, Q_WAIT: 1, Q_DECLINING: 2, Q_BUILD: 3, Q_LATE: 4,
        Q_NOTHING: 5, Q_NODATA: 6}

ELIGIBLE = {
    Q_BUY: "buy", Q_WAIT: "build", Q_LATE: "neither", Q_BUILD: "build",
    Q_DECLINING: "buy", Q_NOTHING: "neither", Q_NODATA: "neither",
}


# ======================================================= denominator machinery
def noise_pct(base):
    """One standard deviation of Poisson counting noise on a count of `base`,
    expressed as a percentage of that count: 100 * sqrt(base) / base.

    base=2   -> 71%   (a "+200%" here means nothing)
    base=10  -> 32%
    base=40  -> 16%
    base=100 -> 10%
    base=400 -> 5%

    One sigma is a WEAK bar - it is roughly an 84% one-sided confidence. Two sigma
    would be the scientific bar and would silence almost every tier on this
    dashboard, because the counts are genuinely that small. One sigma is the
    honest compromise and it is stated, not hidden.
    """
    if not base or base <= 0:
        return None
    return 100.0 * math.sqrt(base) / float(base)


def _base_of(bases, tier):
    b = (bases or {}).get(tier) or {}
    if not isinstance(b, dict):
        return {}
    return b


def show_pct(bases, tier):
    """Should the dashboard print a % for this tier at all, or only raw counts?"""
    b = _base_of(bases, tier)
    if b.get("index"):            # a 0-100 index (T1 search) has no count base
        return True
    n = b.get("base")
    if n is None:                 # base not recorded - print it, but caveat it
        return True
    return n >= MIN_BASE


def tier_fires(g, bases, tier):
    """(fires, why_not). A tier fires only if it clears the substantive
    threshold AND its base is big enough to believe the number."""
    if g is None:
        return False, "no reading"
    b = _base_of(bases, tier)
    n = b.get("base")
    is_index = bool(b.get("index"))

    if not is_index and n is not None and n < MIN_BASE:
        return False, "base too small (%s -> %s); a %% here is noise" % (
            n, b.get("latest", "?"))

    thresh = RISING
    if not is_index and n:
        nf = noise_pct(n)
        if nf is not None and nf > thresh:
            thresh = nf
    if g >= thresh:
        return True, None
    if n is not None and not is_index and thresh > RISING:
        return False, "+%.0f%% is inside the noise band for a base of %s (+/-%.0f%%)" % (
            g, n, thresh)
    return False, "not rising"


# ==================================================================== the read
def read_demand(t0, t1, t4, bases):
    """Demand trajectory. T0 (NHS waits) and T1 (search) only.

    T4 (NHS prescribing) is EXCLUDED on purpose - it is ambiguous (see module
    docstring) and letting it vote would mean coding a possible sell signal as a
    maturity signal.

    T1 is expected to be the INDEPENDENT aggregate: terms auto-discovered from the
    supply tiers (T2/T3) must be excluded upstream, or the confirmation is circular.
    bases["t1"]["independent_items"] == 0 means every T1 term was auto-found, and
    T1 is then disqualified from voting here.
    """
    b1 = _base_of(bases, "t1")
    t1_indep = b1.get("independent_items")
    t1_usable = t1 if (t1_indep is None or t1_indep > 0) else None

    f0, _ = tier_fires(t0, bases, "t0")
    f1, _ = tier_fires(t1_usable, bases, "t1")
    fires = [x for x in (f0, f1) if x]

    if t1_usable is None and t0 is None:
        return "unknown", 0
    if t1_usable is not None and t1_usable <= FALLING:
        return "falling", 0
    if t1_usable is not None and t1_usable >= BOOM:
        return "booming", len(fires)
    if fires:
        return "growing", len(fires)
    return "flat", 0


def entry_rate(invest):
    """Share of the standing clinic stock that registered in the last 12 months.

    THE number for a buyer, and investability.py already computes both halves of
    it (new_12m, locations) and discards the ratio. High = a gold rush, and every
    owner you approach knows it. Low = the rush is over.
    """
    if not invest:
        return None
    loc = invest.get("locations")
    new = invest.get("new_12m")
    if not loc or new is None:
        return None
    return float(new) / float(loc)


def read_supply(t2, t3, invest, bases):
    """Supply maturity FOR ACQUISITION PURPOSES. Returns (state, entry_rate)."""
    if not invest:
        return "unknown", None
    if invest.get("cqc_blind"):
        # Aesthetics: a botox/filler-only clinic is not a CQC-regulated activity,
        # so it is not registrable and CQC literally cannot see it. Reporting
        # "no acquirable population" here would be a lie told with a straight face.
        return "unobservable", entry_rate(invest)

    indie = invest.get("indie_providers")
    if indie is None:
        return "unknown", entry_rate(invest)

    er = entry_rate(invest)

    if indie < MIN_TARGETS:
        return "none", er

    top5 = invest.get("top5_share")
    hhi = invest.get("hhi")
    if (top5 is not None and top5 >= TOP5_CONCENTRATED) or \
       (hhi is not None and hhi >= HHI_CONCENTRATED):
        return "consolidated", er

    if er is not None:
        if er >= ENTRY_HOT:
            return "filling", er
    else:
        # No entry rate available. Fall back to the flow tiers: if BOTH new
        # companies and new clinics are firing, entrants are arriving.
        f2, _ = tier_fires(t2, bases, "t2")
        f3, _ = tier_fires(t3, bases, "t3")
        if f2 and f3:
            return "filling", None

    return "fragmented", er


# ================================================================== main entry
def interpret(niche, t0, t1, t2, t3, t4, invest, bases):
    """Read one niche as a buyer.

    niche   str
    t0..t4  volume-weighted 12-month % growth per tier, or None.
            t1 MUST already exclude auto-discovered terms (see decontaminate()).
    invest  the investability.py dict for this niche, or None/{}.
            May additionally carry "cqc_blind": True where CQC structurally
            cannot see the supply (aesthetics).
    bases   {tier: {"latest": int, "base": int, "items": int,
                    "index": bool, "independent_items": int}}
            Any part may be missing; the read degrades and says so.

    ->  {quadrant, label, eligible_for, why: [str], caveats: [str],
         demand, supply, entry_rate, score, rank, tiers}
    """
    invest = invest or {}
    bases = bases or {}

    demand, dfires = read_demand(t0, t1, t4, bases)
    supply, er = read_supply(t2, t3, invest, bases)

    indie = invest.get("indie_providers")
    locs = invest.get("locations")
    top5 = invest.get("top5_share")

    why = []
    caveats = []

    # ---------------------------------------------------------------- quadrant
    # Precedence is the whole argument, so it is written as one visible ladder.
    if supply in ("unknown", "unobservable"):
        q = Q_NODATA
    elif supply == "consolidated":
        q = Q_LATE                    # beats everything: even booming demand is
                                      # worthless if you are bidding against the
                                      # group that already bought the market.
    elif supply == "none":
        q = Q_BUILD if demand in ("growing", "booming") else Q_NOTHING
    elif supply == "filling":
        q = Q_WAIT
    elif demand == "falling":
        q = Q_DECLINING
    else:
        q = Q_BUY

    # -------------------------------------------------------------------- why
    if q == Q_BUY:
        why.append("%s independent operators to approach, and nobody has bought "
                   "them: the top 5 owners hold only %s%% of sites."
                   % (indie, _pc(top5)))
        if er is not None:
            why.append("New entry has cooled: only %.0f%% of the standing clinic "
                       "stock registered in the last 12 months. The rush is over, "
                       "which is when owners take a call." % (er * 100))
        if demand == "flat":
            why.append("Demand is proven but no longer accelerating. For a buyer "
                       "that is the point, not a problem - it is what compresses "
                       "the multiple you pay.")
        elif demand == "growing":
            why.append("Demand is still growing, so you get organic growth on top "
                       "of the multiple you arbitrage.")
        elif demand == "booming":
            why.append("Demand is booming. That growth is visible to every seller, "
                       "so expect to pay for it in the entry multiple.")
        elif demand == "unknown":
            why.append("No independent demand signal fired - the standing "
                       "population of %s clinics is the only evidence that people "
                       "pay for this." % (locs if locs is not None else "?"))
        if indie is not None and indie < THIN_TARGETS:
            why.append("Only %s independents nationally: a regional platform with "
                       "a few bolt-ons, not a national consolidation." % indie)

    elif q == Q_WAIT:
        if er is not None:
            why.append("%.0f%% of every clinic in this niche opened in the last 12 "
                       "months. Founders are pouring in." % (er * 100))
        else:
            why.append("New companies and new clinic registrations are both rising: "
                       "founders are pouring in.")
        why.append("Every one of those entrants is a competitor you did not have "
                   "last year, and a seller who has no reason to sell.")
        why.append("Entry price is rising. If you want this niche now, opening a "
                   "site is cheaper than buying one. Buying gets better when the "
                   "arrivals stop.")

    elif q == Q_LATE:
        why.append("The top 5 owners already hold %s%% of the sites. The roll-up "
                   "has been done." % _pc(top5))
        why.append("You would be bidding against the people who did it, with worse "
                   "information and a smaller balance sheet.")

    elif q == Q_BUILD:
        why.append("THIS IS NOT A ROLL-UP. There are only %s independent operators "
                   "in the whole country - below the %s you need for a platform "
                   "plus bolt-ons. You cannot buy your way in because there is "
                   "nothing to buy." % (indie if indie is not None else "?",
                                        MIN_TARGETS))
        why.append("Demand is %s, so the idea may be sound - but the only way to "
                   "act on it is to OPEN a clinic. That is a different business "
                   "from the one you run." % demand)
        caveats.append("Building is a different risk profile: you carry the demand "
                       "risk yourself, there is no day-one cash flow, no seller to "
                       "diligence, and no multiple arbitrage - the entire return "
                       "has to come from operating a startup.")

    elif q == Q_DECLINING:
        if t1 is not None:
            why.append("Search interest is DOWN %.0f%%. The demand is going away."
                       % abs(t1))
        else:
            why.append("Demand is falling.")
        why.append("There are still %s fragmented independents, so you could buy "
                   "cash flow cheaply - but a shrinking market does not re-rate. "
                   "You would buy at 4x and sell at 4x." % indie)
        caveats.append("A roll-up in a declining market earns its return from cost "
                       "synergies alone. It is a cash-extraction play, not a "
                       "buy-and-build. Different exit, probably no trade buyer.")

    elif q == Q_NOTHING:
        why.append("No demand signal that survives its own denominator, and only "
                   "%s independent operators. Nothing to buy and no reason to build."
                   % (indie if indie is not None else "?"))

    else:  # Q_NODATA
        if supply == "unobservable":
            why.append("CQC cannot see this niche. A botox/filler-only clinic is "
                       "not carrying out a CQC-regulated activity, so it never "
                       "registers - the supply population here is real but "
                       "invisible, and a 'no operators' reading would be a lie.")
            caveats.append("Use the Companies House aesthetics miner (T2) as the "
                           "supply proxy for this niche. It captures an estimated "
                           "20-35% of formation. Do not read the CQC numbers.")
        else:
            why.append("No usable supply data, so the only honest answer is that "
                       "this cannot be assessed.")

    # ---------------------------------------------------------------- caveats
    # 1. T4 is ambiguous. Always. State BOTH readings and refuse to pick one.
    f4, _ = tier_fires(t4, bases, "t4")
    if f4:
        caveats.append(
            "NHS prescribing is up %.0f%%, and this data CANNOT tell you which of "
            "two opposite things that means: (a) the condition is growing, which "
            "grows your private market too; or (b) the NHS has started funding the "
            "treatment, which DESTROYS your private market because the patient can "
            "now get it free. Check for NICE or NHS England guidance in the window "
            "before you read it either way." % t4)
        if t1 is not None and t1 <= FALLING:
            caveats.append(
                "Warning: NHS prescribing is rising while private search interest "
                "is FALLING. That is the pattern you would expect if the NHS had "
                "taken the patients. Suggestive, not proof - go and check.")

    # 2. T1 contamination.
    b1 = _base_of(bases, "t1")
    ind = b1.get("independent_items")
    items1 = b1.get("items")
    if ind is not None and items1:
        if ind == 0:
            caveats.append(
                "Every search term for this niche was AUTO-DISCOVERED from the "
                "supply tiers, so T1 agreeing with T2/T3 proves nothing - it is "
                "the same data twice. T1 has been excluded from the demand read.")
        elif ind < items1:
            caveats.append(
                "%d of %d search terms here were auto-discovered from T2/T3 and do "
                "not count toward conviction (they would be confirming themselves). "
                "%d independent term(s) remain." % (items1 - ind, items1, ind))

    # 3. Denominators that are too thin to print a % from.
    for tier in ("t0", "t1", "t2", "t3", "t4"):
        b = _base_of(bases, tier)
        n = b.get("base")
        if n is None:
            continue
        if b.get("index"):
            continue
        if n < MIN_BASE:
            caveats.append(
                "%s: base is only %s (now %s). No percentage is shown because none "
                "would mean anything - one extra clinic would move it by %.0f%%."
                % (tier.upper(), n, b.get("latest", "?"), 100.0 / n))

    # 4. Entry is picking up but has not yet crossed the line.
    if q == Q_BUY and er is not None and er >= ENTRY_WARM:
        caveats.append(
            "Entry is warming (%.0f%% of the stock is new). Not a gold rush yet, "
            "but the window is closing, not opening." % (er * 100))

    # 5. Thin population.
    if indie is not None and MIN_TARGETS <= indie < THIN_TARGETS and q == Q_BUY:
        caveats.append(
            "%s independents is enough for a regional platform, not a national "
            "consolidation. Size the ambition to the population." % indie)

    # 6. The structural bias that flatters every buy verdict.
    if q in (Q_BUY, Q_DECLINING):
        caveats.append(
            "A CQC Provider ID is a legal entity, not an economic owner. A "
            "private-equity group holding twelve Ltd companies looks like twelve "
            "independents here, so fragmentation is systematically overstated.")

    return {
        "niche": niche,
        "quadrant": q,
        "label": LABELS[q],
        "eligible_for": ELIGIBLE[q],
        "why": why,
        "caveats": caveats,
        "demand": demand,
        "supply": supply,
        "entry_rate": er,
        "score": _score(q, demand, indie, top5, invest.get("hhi"), er),
        "rank": RANK[q],
        "tiers": {t: {"fires": tier_fires(v, bases, t)[0],
                      "show_pct": show_pct(bases, t),
                      "base": _base_of(bases, t).get("base"),
                      "latest": _base_of(bases, t).get("latest")}
                  for t, v in (("t0", t0), ("t1", t1), ("t2", t2),
                               ("t3", t3), ("t4", t4))},
    }


def _pc(x):
    return "%.0f" % x if x is not None else "?"


def _score(q, demand, indie, top5, hhi, er):
    """0-100, for RANKING niches against each other WITHIN the buy list.

    Weights: 40% how many targets exist, 35% how much of the market is still
    unbought, 25% how cold the entry rate is. Growth is deliberately NOT the
    biggest term - it is worth 0 to a buyer if there is nothing to buy, and it
    raises the price when there is. See interpret_FINDINGS.md section 5.
    """
    if q not in (Q_BUY, Q_DECLINING):
        # Build ideas are scored on demand alone; they are a different business
        # and must not be ranked against buy targets on the same number.
        if q == Q_BUILD:
            return {"booming": 60, "growing": 40}.get(demand, 0)
        return 0
    if indie is None:
        return 0
    density = 100.0 * min(1.0, indie / float(THIN_TARGETS * 3))   # saturates ~300
    h5 = 1.0 - min(1.0, (top5 or 0.0) / TOP5_CONCENTRATED)
    hh = 1.0 - min(1.0, (hhi or 0.0) / HHI_CONCENTRATED)
    headroom = 100.0 * min(h5, hh)
    cool = 100.0 * (1.0 - min(1.0, (er if er is not None else ENTRY_WARM) / ENTRY_HOT))
    s = 0.40 * density + 0.35 * headroom + 0.25 * cool
    if demand == "falling":
        s *= 0.5          # you can still buy it, but it must not out-rank a live one
    elif demand == "booming":
        s *= 0.9          # you will pay for that growth
    return int(round(s))


# ============================================== T1 DECONTAMINATION (finding 5)
def decontaminate(trend_rows):
    """Split T1 search rows into independent vs auto-discovered.

    pull_and_build.discovered_terms() feeds the top phrases found in T2 (new
    company names) and T3 (new CQC clinic names) back into the T1 search query
    list, and tags them found=True. That is a good way to surface a niche nobody
    pre-listed. It is a terrible way to CONFIRM one: if T1 only lights up because
    T2 told it what to search for, then "T1 and T2 agree" is plumbing, not
    evidence.

    So: keep them, show them, and give them ZERO votes.

    -> (independent_rows, discovered_rows)
    """
    ind, disc = [], []
    for r in trend_rows or []:
        (disc if r.get("found") else ind).append(r)
    return ind, disc


def agg_independent(rows):
    """Volume-weighted 12-month growth per niche, INDEPENDENT TERMS ONLY.
    Mirrors pull_and_build.agg() but drops found=True rows. Also returns the
    denominators, because a growth number without its base is a rumour."""
    m, bases = {}, {}
    for r in rows or []:
        n, g = r.get("niche"), r.get("g12")
        if not n:
            continue
        b = bases.setdefault(n, {"items": 0, "independent_items": 0,
                                 "latest": 0, "index": True})
        b["items"] += 1
        if r.get("found"):
            continue                       # counted, but does not vote
        b["independent_items"] += 1
        b["latest"] += r.get("latest") or 0
        if g is None:
            continue
        w = max(r.get("latest") or 1, 1)
        a = m.setdefault(n, [0.0, 0.0])
        a[0] += w
        a[1] += w * g
    out = {k: v[1] / v[0] for k, v in m.items() if v[0]}
    return out, bases


# ==================================================================== SELF-TEST
def _inv(indie=None, locs=None, new12=None, top5=None, hhi=None, **kw):
    d = {"indie_providers": indie, "locations": locs, "new_12m": new12,
         "top5_share": top5, "hhi": hhi}
    d.update(kw)
    return d


def _b(**kw):
    """bases builder: _b(t1=(base, latest, index), t3=(6, 18))"""
    out = {}
    for k, v in kw.items():
        if v is None:
            continue
        base, latest = v[0], v[1]
        d = {"base": base, "latest": latest}
        if len(v) > 2 and v[2]:
            d["index"] = True
        out[k] = d
    return out


CASES = []


def case(name, expect_q, expect_elig, **kw):
    CASES.append((name, expect_q, expect_elig, kw))


# --- the buy window, in its three demand flavours -------------------------
case("Dental-like: flat demand, 620 fragmented indies, cold entry",
     Q_BUY, "buy",
     t0=2.0, t1=1.0, t2=3.0, t3=4.0, t4=None,
     invest=_inv(indie=620, locs=1800, new12=70, top5=11.0, hhi=0.02),
     bases=_b(t1=(48, 49, True), t2=(40, 41), t3=(30, 31)))

case("Physio-like: growing demand, deep fragmented, cold entry",
     Q_BUY, "buy",
     t0=14.0, t1=18.0, t2=6.0, t3=5.0, t4=None,
     invest=_inv(indie=410, locs=900, new12=45, top5=9.0, hhi=0.01),
     bases=_b(t0=(400000, 456000), t1=(40, 47, True), t2=(30, 32), t3=(25, 26)))

case("Booming demand but supply NOT yet flooding -> buy, and you pay for growth",
     Q_BUY, "buy",
     t0=None, t1=65.0, t2=5.0, t3=4.0, t4=None,
     invest=_inv(indie=350, locs=800, new12=40, top5=12.0, hhi=0.02),
     bases=_b(t1=(30, 50, True), t2=(30, 32), t3=(25, 26)))

case("Thin but real: 45 indies -> buy, regional platform only",
     Q_BUY, "buy",
     t0=None, t1=12.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=45, locs=120, new12=6, top5=15.0, hhi=0.03),
     bases=_b(t1=(40, 45, True)))

case("Exactly at the gate: 30 indies -> still a buy",
     Q_BUY, "buy",
     t0=None, t1=15.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=30, locs=90, new12=4, top5=18.0, hhi=0.04),
     bases=_b(t1=(40, 46, True)))

case("No demand signal at all, but 500 clinics are open and trading -> buy",
     Q_BUY, "buy",
     t0=None, t1=None, t2=None, t3=None, t4=None,
     invest=_inv(indie=500, locs=1400, new12=60, top5=10.0, hhi=0.02),
     bases={})

# --- booming demand + booming supply: the awkward one ---------------------
case("Weight-loss-like: demand booming AND 22% of the stock is new -> wait/build",
     Q_WAIT, "build",
     t0=None, t1=95.0, t2=160.0, t3=140.0, t4=48.0,
     invest=_inv(indie=340, locs=700, new12=154, top5=14.0, hhi=0.03),
     bases=_b(t1=(35, 68, True), t2=(50, 130), t3=(40, 96), t4=(180000, 266400)))

case("Entry rate exactly ON the hot line (15%) -> wait/build",
     Q_WAIT, "build",
     t0=None, t1=30.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=200, locs=1000, new12=150, top5=12.0, hhi=0.02),
     bases=_b(t1=(40, 52, True)))

case("Entry rate unknown, but T2 AND T3 both fire -> wait/build (fallback path)",
     Q_WAIT, "build",
     t0=None, t1=25.0, t2=45.0, t3=38.0, t4=None,
     invest=_inv(indie=200, locs=None, new12=None, top5=12.0, hhi=0.02),
     bases=_b(t1=(40, 50, True), t2=(60, 87), t3=(50, 69)))

case("Entry rate unknown and only T2 fires -> NOT enough to call it filling",
     Q_BUY, "buy",
     t0=None, t1=25.0, t2=45.0, t3=1.0, t4=None,
     invest=_inv(indie=200, locs=None, new12=None, top5=12.0, hhi=0.02),
     bases=_b(t1=(40, 50, True), t2=(60, 87), t3=(50, 51)))

# --- already consolidated -------------------------------------------------
case("Top-5 hold 62% -> too late, whatever demand is doing",
     Q_LATE, "neither",
     t0=25.0, t1=70.0, t2=50.0, t3=40.0, t4=None,
     invest=_inv(indie=300, locs=900, new12=40, top5=62.0, hhi=0.15),
     bases=_b(t0=(400000, 500000), t1=(30, 51, True), t2=(40, 60), t3=(30, 42)))

case("HHI 0.25 alone triggers consolidated even with a low top-5",
     Q_LATE, "neither",
     t0=None, t1=20.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=300, locs=900, new12=40, top5=30.0, hhi=0.25),
     bases=_b(t1=(40, 48, True)))

case("Consolidated AND flooding with entrants -> consolidated still wins",
     Q_LATE, "neither",
     t0=None, t1=80.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=300, locs=900, new12=300, top5=55.0, hhi=0.18),
     bases=_b(t1=(30, 54, True)))

# --- greenfield: demand but nothing to buy. The honest resolution. ---------
case("Tongue-tie with a REAL search signal: 11 indies -> BUILD, not buy",
     Q_BUILD, "build",
     t0=None, t1=120.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=11, locs=26, new12=6, top5=45.0, hhi=0.09),
     bases=_b(t1=(20, 44, True)))

case("29 indies: one short of the gate -> still BUILD, not buy",
     Q_BUILD, "build",
     t0=None, t1=55.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=29, locs=70, new12=8, top5=20.0, hhi=0.05),
     bases=_b(t1=(30, 47, True)))

# --- thin base: the "+200% is two clinics" case ---------------------------
case("Tongue-tie as it ACTUALLY reads: T3 +200% on a base of 2 -> fires nothing",
     Q_NOTHING, "neither",
     t0=None, t1=None, t2=None, t3=200.0, t4=None,
     invest=_inv(indie=11, locs=26, new12=6, top5=45.0, hhi=0.09),
     bases=_b(t3=(2, 6)))

case("T2 +159% on a base of 7 -> below MIN_BASE, cannot fire",
     Q_NOTHING, "neither",
     t0=None, t1=None, t2=159.0, t3=None, t4=None,
     invest=_inv(indie=12, locs=30, new12=3, top5=30.0, hhi=0.08),
     bases=_b(t2=(7, 18)))

case("T1 +25% on an index base -> Poisson floor does NOT apply to an index",
     Q_BUILD, "build",
     t0=None, t1=25.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=12, locs=30, new12=3, top5=30.0, hhi=0.08),
     bases=_b(t1=(30, 38, True)))

case("T3 +25% on a base of 40 -> noise floor is 16%, so it DOES fire",
     Q_WAIT, "build",
     t0=None, t1=25.0, t2=30.0, t3=25.0, t4=None,
     invest=_inv(indie=200, locs=None, new12=None, top5=12.0, hhi=0.02),
     bases=_b(t1=(40, 50, True), t2=(40, 52), t3=(40, 50)))

case("T3 +25% on a base of 12 -> noise floor is 29%, so it does NOT fire",
     Q_BUY, "buy",
     t0=None, t1=25.0, t2=30.0, t3=25.0, t4=None,
     invest=_inv(indie=200, locs=None, new12=None, top5=12.0, hhi=0.02),
     bases=_b(t1=(40, 50, True), t2=(40, 52), t3=(12, 15)))

# --- declining -----------------------------------------------------------
case("Demand rolling over but supply fragmented -> buy for cash, not a roll-up",
     Q_DECLINING, "buy",
     t0=None, t1=-28.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=280, locs=800, new12=25, top5=13.0, hhi=0.02),
     bases=_b(t1=(60, 43, True)))

# --- nothing / no data ---------------------------------------------------
case("No demand, no population -> nothing here",
     Q_NOTHING, "neither",
     t0=None, t1=2.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=8, locs=20, new12=1, top5=60.0, hhi=0.20),
     bases=_b(t1=(40, 41, True)))

case("Everything None -> no data, and we say so",
     Q_NODATA, "neither",
     t0=None, t1=None, t2=None, t3=None, t4=None, invest=None, bases={})

case("Locations exist but no Provider ID column -> cannot assess, do not guess",
     Q_NODATA, "neither",
     t0=None, t1=40.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=None, locs=900, new12=90, top5=None, hhi=None),
     bases=_b(t1=(30, 42, True)))

case("Aesthetics: CQC structurally blind -> refuse to answer, do not say 'no targets'",
     Q_NODATA, "neither",
     t0=None, t1=35.0, t2=60.0, t3=None, t4=None,
     invest=_inv(indie=14, locs=40, new12=9, top5=25.0, hhi=0.06, cqc_blind=True),
     bases=_b(t1=(40, 54, True), t2=(50, 80)))

# --- T1 contamination ----------------------------------------------------
case("T1 fires but EVERY term was auto-found -> T1 gets no vote",
     Q_BUY, "buy",
     t0=None, t1=90.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=300, locs=800, new12=40, top5=10.0, hhi=0.02),
     bases={"t1": {"base": 30, "latest": 57, "index": True,
                   "items": 3, "independent_items": 0}})

case("Contaminated T1 + no population -> NOT a build idea either; evidence is circular",
     Q_NOTHING, "neither",
     t0=None, t1=90.0, t2=None, t3=None, t4=None,
     invest=_inv(indie=9, locs=22, new12=4, top5=40.0, hhi=0.12),
     bases={"t1": {"base": 30, "latest": 57, "index": True,
                   "items": 2, "independent_items": 0}})

# --- T4 ambiguity --------------------------------------------------------
case("T4 rising while T1 falls -> NHS-substitution warning must appear",
     Q_DECLINING, "buy",
     t0=None, t1=-30.0, t2=None, t3=None, t4=60.0,
     invest=_inv(indie=250, locs=700, new12=20, top5=12.0, hhi=0.02),
     bases=_b(t1=(60, 42, True), t4=(120000, 192000)))

case("T4 rising while T1 also rises -> both readings stated, neither asserted",
     Q_BUY, "buy",
     t0=None, t1=30.0, t2=None, t3=None, t4=45.0,
     invest=_inv(indie=250, locs=700, new12=20, top5=12.0, hhi=0.02),
     bases=_b(t1=(40, 52, True), t4=(100000, 145000)))


def selftest():
    fails = []
    print("=" * 78)
    print("interpret.py self-test - %d cases" % len(CASES))
    print("=" * 78)
    for name, exp_q, exp_e, kw in CASES:
        r = interpret(name, kw.get("t0"), kw.get("t1"), kw.get("t2"),
                      kw.get("t3"), kw.get("t4"),
                      kw.get("invest"), kw.get("bases"))
        ok = (r["quadrant"] == exp_q and r["eligible_for"] == exp_e)
        if not ok:
            fails.append("%s: got %s/%s want %s/%s"
                         % (name, r["quadrant"], r["eligible_for"], exp_q, exp_e))
        print("%s  %-8s %-7s  %s" % ("PASS" if ok else "FAIL",
                                     r["eligible_for"], r["quadrant"], name))

    print("-" * 78)
    print("targeted assertions")
    nchk = [0]

    def chk(label, got, want):
        nchk[0] += 1
        ok = got == want
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("%s  %-58s %s" % ("PASS" if ok else "FAIL", label, got))

    # denominators
    chk("noise on base 2 is +/-71%", round(noise_pct(2)), 71)
    chk("noise on base 100 is +/-10%", round(noise_pct(100)), 10)
    chk("base 2 -> suppress the %", show_pct(_b(t3=(2, 6)), "t3"), False)
    chk("base 40 -> print the %", show_pct(_b(t3=(40, 50)), "t3"), True)
    chk("index tier always prints a %", show_pct(_b(t1=(3, 9, True)), "t1"), True)
    chk("+200% on base 2 does not fire",
        tier_fires(200.0, _b(t3=(2, 6)), "t3")[0], False)
    chk("+15% on base 400 DOES fire",
        tier_fires(15.0, _b(t3=(400, 460)), "t3")[0], True)
    chk("+15% on base 40 does NOT fire (noise floor 16%)",
        tier_fires(15.0, _b(t3=(40, 46)), "t3")[0], False)

    # entry rate
    chk("entry rate 154/700", round(entry_rate(_inv(locs=700, new12=154)), 3), 0.22)
    chk("entry rate None when locations missing",
        entry_rate(_inv(locs=None, new12=10)), None)

    # T4 must never vote on demand
    d, _ = read_demand(None, None, 900.0, {})
    chk("T4 alone cannot make demand 'growing'", d, "unknown")

    # T4 caveats
    r = interpret("x", None, -30.0, None, None, 60.0,
                  _inv(indie=250, locs=700, new12=20, top5=12.0, hhi=0.02),
                  _b(t1=(60, 42, True), t4=(120000, 192000)))
    chk("NHS-substitution warning fires",
        any("NHS had" in c for c in r["caveats"]), True)
    chk("both readings of T4 are stated",
        any("DESTROYS your private market" in c for c in r["caveats"]), True)

    # contamination
    r = interpret("x", None, 90.0, None, None, None,
                  _inv(indie=300, locs=800, new12=40, top5=10.0, hhi=0.02),
                  {"t1": {"base": 30, "latest": 57, "index": True,
                          "items": 3, "independent_items": 0}})
    chk("fully auto-found T1 is excluded from demand", r["demand"], "unknown")
    chk("...and it is declared", any("AUTO-DISCOVERED" in c for c in r["caveats"]),
        True)
    r = interpret("x", None, 90.0, None, None, None,
                  _inv(indie=300, locs=800, new12=40, top5=10.0, hhi=0.02),
                  {"t1": {"base": 30, "latest": 57, "index": True,
                          "items": 3, "independent_items": 1}})
    chk("partly auto-found T1 still votes", r["demand"], "booming")
    chk("...but the dilution is declared",
        any("do not count toward conviction" in c for c in r["caveats"]), True)

    ind, disc = decontaminate([{"name": "a", "found": True},
                               {"name": "b"}, {"name": "c", "found": False}])
    chk("decontaminate splits found from independent",
        (len(ind), len(disc)), (2, 1))
    a, bb = agg_independent([
        {"niche": "N", "g12": 100.0, "latest": 50, "found": True},
        {"niche": "N", "g12": 10.0, "latest": 50}])
    chk("auto-found rows do not move the T1 aggregate", a["N"], 10.0)
    chk("...but they are still counted in items",
        (bb["N"]["items"], bb["N"]["independent_items"]), (2, 1))

    # build ideas are labelled as a DIFFERENT BUSINESS
    r = interpret("x", None, 120.0, None, None, None,
                  _inv(indie=11, locs=26, new12=6, top5=45.0, hhi=0.09),
                  _b(t1=(20, 44, True)))
    chk("build idea says THIS IS NOT A ROLL-UP",
        any("NOT A ROLL-UP" in w for w in r["why"]), True)
    chk("build idea warns it is a different risk profile",
        any("different risk profile" in c for c in r["caveats"]), True)

    # ranking: the buy window must out-rank a boom
    buy = interpret("cold", None, 5.0, None, None, None,
                    _inv(indie=400, locs=1000, new12=40, top5=10.0, hhi=0.02),
                    _b(t1=(48, 50, True)))
    hot = interpret("hot", None, 90.0, None, None, None,
                    _inv(indie=400, locs=1000, new12=200, top5=10.0, hhi=0.02),
                    _b(t1=(30, 57, True)))
    chk("a cooled fragmented niche out-ranks a booming one", buy["rank"] < hot["rank"],
        True)
    chk("...and the booming one is routed to BUILD", hot["eligible_for"], "build")

    # every case yields a legal eligible_for
    chk("eligible_for is always buy/build/neither",
        set(ELIGIBLE.values()), {"buy", "build", "neither"})
    chk("every quadrant has a label", sorted(LABELS) == sorted(RANK) ==
        sorted(ELIGIBLE), True)

    print("=" * 78)
    if fails:
        print("FAILED (%d)" % len(fails))
        for f in fails:
            print("   " + f)
        return False
    print("PASS - %d cases + %d assertions, 0 failures" % (len(CASES), nchk[0]))
    return True


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(0 if selftest() else 1)
