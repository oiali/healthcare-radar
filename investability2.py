#!/usr/bin/env python3
"""
INVESTABILITY 2 - the same question, asked without the two lies in the first answer.

investability.py answers "is this niche fragmented, and is it deep enough to roll up?"
It is the number Omar would underwrite on. It is wrong in two specific ways, and BOTH of
them push in the same direction: they make every niche look MORE investable than it is.

LIE 1: A PROVIDER ID IS A LEGAL ENTITY, NOT AN ECONOMIC OWNER.
--------------------------------------------------------------
CQC registers COMPANIES. A private-equity-backed group holding twelve dental practices in
twelve separate Ltd companies appears in the CQC file as TWELVE single-site independent
providers. So:

    providers          overstated
    single_site_pct    overstated
    top-5 share        understated
    HHI                understated
    "Fragmented - roll-up runway"    printed in green, on a market somebody already owns

Every one of those errors FLATTERS. There is no version of this mistake that makes a niche
look worse than it is. And it is not a rounding error: it is the difference between a
runway and a queue.

The fix is not new - a sibling module already built it. _agent2/targets.py groups providers
into ECONOMIC OWNERS using Companies House officers (surname + forename + DOB month/year)
and registered office addresses, with a guard against the accountant trap (an address only
links providers if fewer than four share it, because thousands of unrelated small companies
use their accountant's office as their registered office). This module IMPORTS that dedupe.
It does not reimplement it. One implementation, one place to fix.

What this module adds is that it recomputes the FRAGMENTATION STATISTICS on the deduped
owners - and reports BOTH numbers side by side, so the size of the flattering bias is
visible on the dashboard rather than silently corrected away. If a niche goes from 240
"independent providers" to 180 economic owners, you should be looking at that 60, not at a
quietly adjusted number you cannot audit.

LIE 2: HHI CANNOT TELL A GOLD RUSH FROM A TIRED MARKET.
-------------------------------------------------------
A Herfindahl index is a snapshot of concentration. It says nothing about TIME. So it scores
these two identically, and they are opposite trades:

  FRAGMENTATION OF INFANCY   Nobody has consolidated it because there is nothing there yet.
                             The niche appeared eighteen months ago; 22% of the standing
                             stock registered in the last twelve months; the median operator
                             has been trading for two years. It is fragmented because it is
                             NEW. There is no tired 58-year-old owner looking for an exit -
                             everybody just started, everybody is growing, nobody will sell,
                             and the ones who would sell have no EBITDA to sell you. Buying
                             here is venture capital wearing a roll-up's clothes.

  FRAGMENTATION OF MATURITY  A real, tired, sellable population. 4% of the stock registered
                             last year; the median operator has been there eleven years; the
                             owners are ageing and there is no internal market for their
                             shares. It is fragmented because nobody has BOTHERED. THIS is
                             the roll-up.

The discriminator is not concentration. It is ENTRY RATE:

    entry rate = registrations in the last 12 months / the standing stock

A stock that is 22% one year old is a gold rush. A stock that is 4% one year old is a
mature population. Corroborated by the MEDIAN YEARS SINCE REGISTRATION of the stock. Both
are emitted, with a plain-English verdict that names which trade you are looking at.

WHAT IS STILL WRONG - read discovery_FINDINGS.md (part 2) before you underwrite anything.
The two that matter most: the owner dedupe is BUDGET-LIMITED (Companies House allows 600
requests / 5 minutes and every provider costs three), so it is a PARTIAL correction, and
the residual error STILL FLATTERS - dedupe can only ever merge entities, never split them,
so `owners_economic` is an UPPER BOUND on the truth. And an owner who uses nominee directors
and a virtual office is invisible to it entirely.

Stdlib only.
    python3 investability2.py --selftest    synthetic .ods + fake Companies House, no network
"""

import os
import re
import sys
import json
import zipfile
import tempfile
from collections import Counter, defaultdict
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

DIAG = {}

# ---------------------------------------------------------------------- imports
# EVERYTHING structural is borrowed. This module contributes arithmetic and a verdict, not
# a second copy of an ODS parser or a second owner-dedupe that can drift from the first.
try:
    from investability import (
        _hhi, _add_months, cqc_file_url, _download, MONTHS,
        MIN_TARGETS, THIN_TARGETS, DEEP_TARGETS, INDIE_MAX_SITES,
        HHI_CONCENTRATED, HHI_MODERATE, TOP5_CONCENTRATED, TOP5_MODERATE,
    )
    _INV_OK = True
except Exception as _e:                                   # pragma: no cover
    _INV_OK = False
    DIAG["fatal_import"] = "investability.py not importable: %r" % (_e,)

try:
    # THE OWNER DEDUPE. Imported, not rewritten. targets.economic_owners() carries the
    # accountant-address guard (MAX_ADDR_GROUP) and the DOB-keyed director link, and both
    # are already proved against fixtures in targets.py's own self-test.
    from targets import (
        scan_providers, economic_owners, CHClient, ch_match, ch_facts, looks_personal,
        CH_KEY, CH_DEFAULT_BUDGET,
    )
    _TGT_OK = True
except Exception as _e:                                   # pragma: no cover
    _TGT_OK = False
    DIAG["fatal_import_targets"] = "targets.py not importable: %r" % (_e,)


# ========================================================== INFANCY vs MATURITY
# The entry-rate cuts. Judgement calls, stated once, with the reasoning.
#
# INFANT_ENTRY_RATE = 15.0 -- if more than about one in seven of the operators standing in
# a niche today registered in the last twelve months, the population is not a population,
# it is an arrival. A stock growing at that rate has not had time to produce what a roll-up
# actually buys: an owner who has been doing this long enough to be bored of it, a P&L with
# a history, and a business that survives its founder taking a fortnight off. Nobody has
# consolidated this market because there was nothing to consolidate when they last looked.
#
# MATURE_ENTRY_RATE = 8.0 -- below this, entry is roughly replacement-rate. The population
# is standing, not arriving; its age is accumulating; owners are getting older inside it.
# This is what a rollable market looks like from the outside.
#
# Between the two: settling. Say so, and do not pretend to know.
INFANT_ENTRY_RATE = 15.0
MATURE_ENTRY_RATE = 8.0

# Corroborators, on the median years since registration of the standing stock.
# READ THE CENSORING CAVEAT BELOW BEFORE USING THESE. They are the second opinion, never
# the first - the entry rate is the measurement that survives the caveat.
MATURE_MEDIAN_YEARS = 8.0
INFANT_MEDIAN_YEARS = 4.0

# THE CENSORING CAVEAT, and it is not a footnote. The CQC "HSCA start date" is the date the
# location registered UNDER THE HEALTH AND SOCIAL CARE ACT 2008 - not the date the practice
# opened. Dental practices were all forced to register in 2011 and GP practices in 2013. So
# a dental practice trading since 1988 carries a start date of 2011 and reports as
# "15 years". The median years figure is therefore CENSORED at ~15 for those sectors, and
# the censoring runs in one direction only: it makes MATURE populations look YOUNGER than
# they are. Which means it biases the discriminator TOWARDS calling a mature niche infant -
# the safe direction for a buyer, but a real distortion, and the reason the entry rate
# leads. The entry rate is immune: locations registering in the last twelve months are
# genuinely new registrations, whatever happened in 2011.
HSCA_CENSOR_NOTE = ("CQC start dates are HSCA re-registration dates, not opening dates - "
                    "dentists all re-registered in 2011 and GPs in 2013, so median tenure "
                    "is censored at ~15 years and UNDERSTATES the age of a mature "
                    "population. The entry rate is not affected and is the number to lead "
                    "on.")

MATURITY_INFANT = "INFANT"
MATURITY_SETTLING = "SETTLING"
MATURITY_MATURE = "MATURE"

V_TOO_SMALL = "Too small to roll up"
V_MATURE_FRAG = "Fragmented and MATURE - real roll-up runway"
V_INFANT_FRAG = "Fragmented but INFANT - a gold rush, not a roll-up"
V_SETTLING_FRAG = "Fragmented, still settling - too early to call"
V_THIN = "Thin - regional platform at best"
V_CONSOLIDATING = "Consolidating"
V_CONSOLIDATED = "Already consolidated"

# Companies House costs 3 calls per provider for the dedupe (search -> profile -> officers).
# Charges and PSC are NOT fetched: they feed the seller-intent score in targets.py and buy
# this module nothing. At the default 300-call budget that is ~100 providers per run.
CALLS_PER_PROVIDER = 3


# ==================================================================== utilities
def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    return float(xs[mid]) if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def _pctf(n, d):
    return round(100.0 * n / d, 1) if d else None


def _years(start, anchor):
    if not start:
        return None
    y = anchor.year - start.year - (1 if (anchor.month, anchor.day) <
                                    (start.month, start.day) else 0)
    return max(0, y)


# ======================================================= the concentration maths
def _conc(unit_locs, unit_sites_total):
    """Concentration statistics over ANY ownership unit - a legal provider or an economic
    owner. Identical arithmetic both times, which is the entire point: the ONLY thing that
    changes between the flattering number and the honest one is what you call an owner.

    unit_locs:        {unit_id: locations IN THIS NICHE}
    unit_sites_total: {unit_id: locations FILE-WIDE, across every niche and sector}
    """
    total = sum(unit_locs.values())
    n = len(unit_locs)
    if not n or not total:
        return {"units": None, "locations": total, "lpp": None, "single_site_pct": None,
                "top5_share": None, "hhi": None, "indie": None, "indie_pct": None}

    counts = sorted(unit_locs.values(), reverse=True)
    single = sum(1 for c in counts if c == 1)
    # "Independent" is judged on the unit's FILE-WIDE site count, not its in-niche count.
    # A 60-site group with one clinic in your niche is not a single-site independent, and
    # counting it as one is exactly backwards. Same rule investability.py applies.
    indie = sum(1 for u in unit_locs if unit_sites_total.get(u, 1) <= INDIE_MAX_SITES)
    return {
        "units": n,
        "locations": total,
        "lpp": round(total / float(n), 2),
        "single_site_pct": _pctf(single, n),
        "top5_share": _pctf(sum(counts[:5]), total),
        "hhi": round(_hhi(counts, total), 4),
        "indie": indie,
        "indie_pct": _pctf(indie, n),
    }


def maturity(entry_rate, median_years):
    """-> (label, plain-English why). The infancy / maturity discriminator.

    Entry rate leads; median tenure corroborates. Where they disagree, the entry rate wins
    and the disagreement is REPORTED - because the one way median tenure fails (HSCA
    re-registration censoring) makes an old population look young, and that is exactly the
    error that would make us call a real roll-up a gold rush and walk away from it.
    """
    if entry_rate is None:
        return None, "no registration dates - maturity cannot be assessed"

    if entry_rate >= INFANT_ENTRY_RATE:
        lab = MATURITY_INFANT
        why = ("%.0f%% of the operators standing today registered in the last 12 months. "
               "This niche is fragmented because it is NEW, not because it is tired - "
               "nobody has consolidated it because there was nothing here to consolidate. "
               "There is no ageing owner-operator population to buy." % entry_rate)
    elif entry_rate <= MATURE_ENTRY_RATE:
        lab = MATURITY_MATURE
        why = ("only %.0f%% of the stock registered in the last 12 months - entry is at "
               "about replacement rate. This is a standing population that has been here "
               "long enough to have owners who want out." % entry_rate)
    else:
        lab = MATURITY_SETTLING
        why = ("%.0f%% of the stock registered in the last 12 months - faster than a mature "
               "market, slower than a gold rush. The niche is still forming; the owner "
               "population is not yet old enough to be selling." % entry_rate)

    if median_years is not None:
        why += " Median operator has been registered %.0f years." % median_years
        # Flag the disagreement rather than averaging it away.
        if lab == MATURITY_MATURE and median_years < INFANT_MEDIAN_YEARS:
            why += (" NOTE: entry rate says mature but the stock is young (%.0f yrs) - "
                    "a niche that grew fast and then stopped. Treat as SETTLING."
                    % median_years)
        elif lab == MATURITY_INFANT and median_years >= MATURE_MEDIAN_YEARS:
            why += (" NOTE: the stock is old (%.0f yrs) despite the high entry rate - an "
                    "established niche having a growth spurt, not a new one. That is a "
                    "better trade than a gold rush." % median_years)
    return lab, why


def verdict(indie_owners, hhi, top5, mat, entry_rate, median_years):
    """Density gate -> concentration -> MATURITY. The order is the argument.

    A niche too small to roll up is not rescued by being fragmented, so density gates first
    and absolutely. A niche somebody has already bought is not rescued by being mature. And
    a fragmented, deep, unconsolidated niche is STILL not a roll-up if everyone in it
    started last year - which is the case the old verdict could not see and scored green.
    """
    if indie_owners is None:
        return V_TOO_SMALL, "no ownership data - fragmentation cannot be assessed"
    if indie_owners < MIN_TARGETS:
        return (V_TOO_SMALL,
                "only %d independent ECONOMIC OWNERS nationally (need >=%d for a platform "
                "plus ~8-12 bolt-ons at a realistic hit rate)" % (indie_owners, MIN_TARGETS))

    if (hhi is not None and hhi >= HHI_CONCENTRATED) or \
       (top5 is not None and top5 >= TOP5_CONCENTRATED):
        return (V_CONSOLIDATED,
                "top-5 economic owners hold %.0f%% of locations (HHI %.2f) - the "
                "consolidation has already happened; you would be bidding against the "
                "people who did it" % (top5 or 0, hhi or 0))

    if (hhi is not None and hhi >= HHI_MODERATE) or \
       (top5 is not None and top5 >= TOP5_MODERATE):
        return (V_CONSOLIDATING,
                "top-5 economic owners hold %.0f%% (HHI %.2f) - groups are forming but %d "
                "independent owners remain; runway exists, competition for assets is real"
                % (top5 or 0, hhi or 0, indie_owners))

    if indie_owners < THIN_TARGETS:
        return (V_THIN,
                "fragmented (top-5 %.0f%%) but only %d independent owners - a regional "
                "platform and a few bolt-ons, not a national consolidation"
                % (top5 or 0, indie_owners))

    # Deep, fragmented, unconsolidated. NOW the only question left is whether the population
    # is old enough to sell you anything.
    base = ("%d independent economic owners, top-5 hold only %.0f%% (HHI %.2f)"
            % (indie_owners, top5 or 0, hhi or 0))
    if mat == MATURITY_INFANT:
        return (V_INFANT_FRAG,
                base + " - but %.0f%% of them registered in the last 12 months. This is a "
                "GOLD RUSH, not a roll-up: the fragmentation is infancy, not neglect. "
                "There is no tired owner population here to buy." % (entry_rate or 0))
    if mat == MATURITY_MATURE:
        return (V_MATURE_FRAG,
                base + " - and only %.0f%% registered last year, median tenure %s years. "
                "A standing, ageing, unconsolidated population. This is the trade."
                % (entry_rate or 0,
                   "?" if median_years is None else "%.0f" % median_years))
    return (V_SETTLING_FRAG,
            base + " - but entry is still running at %.0f%% a year. The population is "
            "forming, not tiring. Watch it; do not underwrite it yet." % (entry_rate or 0))


def score(indie_owners, hhi, top5, mat):
    """0-100 for RANKING niches against each other. Same 60/40 density/headroom split as
    investability._score, computed on ECONOMIC OWNERS - then discounted for infancy.

    The discount is a judgement, and a blunt one: a gold rush is scored at HALF of what its
    density and fragmentation alone would earn it, because density and fragmentation are
    measuring the wrong thing there. They are counting arrivals, not targets.
    """
    if indie_owners is None or indie_owners < MIN_TARGETS:
        return 0
    density = 100.0 * min(1.0, indie_owners / float(DEEP_TARGETS))
    h_hhi = 1.0 - min(1.0, (hhi or 0) / HHI_CONCENTRATED)
    h_top5 = 1.0 - min(1.0, (top5 or 0) / TOP5_CONCENTRATED)
    headroom = 100.0 * min(h_hhi, h_top5)
    raw = 0.6 * density + 0.4 * headroom
    factor = {MATURITY_INFANT: 0.5, MATURITY_SETTLING: 0.8}.get(mat, 1.0)
    return int(round(raw * factor))


# ============================================== Companies House: only what dedupe needs
def _enrich_for_dedupe(client, rows, anchor, per_niche_order):
    """Spend the Companies House budget on the ONE thing the dedupe needs: who the
    directors are and where the registered office is.

    3 calls per provider (search -> profile -> officers). NOT charges, NOT PSC: those feed
    the seller-intent score in targets.py and buy this module nothing.

    Providers whose name looks like a person ("Mr A Patel", "Smith & Partners") are skipped
    at ZERO cost - they are sole traders and partnerships, they have no Companies House
    record to find, and searching for them would burn three calls to learn nothing. They
    remain their own economic owner, which is almost certainly the truth.

    Order is round-robin ACROSS NICHES and deterministic WITHIN one (by provider id). Not
    by size, and not by anything correlated with being in a group: a biased enrichment order
    would produce a biased estimate of how much grouping there is, which is the one number
    this module exists to produce.
    """
    queue, i = [], 0
    while True:
        added = False
        for n in sorted(per_niche_order):
            if i < len(per_niche_order[n]):
                queue.append(per_niche_order[n][i])
                added = True
        if not added:
            break
        i += 1

    checked = skipped_personal = matched = 0
    for r in queue:
        if not client.live:
            break
        if looks_personal(r["provider_name"]):
            r["ch"] = {"status": "unmatched", "company_number": None, "company_name": None,
                       "confidence": None,
                       "note": "provider name looks like an individual or partnership - "
                               "no company to link, treated as its own owner"}
            skipped_personal += 1
            continue
        try:
            r["ch"] = ch_match(client, r["provider_name"], r.get("postcodes") or ())
            checked += 1
            if r["ch"]["status"] != "matched":
                continue
            r["ch_facts"] = ch_facts(client, r["ch"]["company_number"], anchor,
                                     want_charges=False, want_psc=False)
            matched += 1
        except Exception as e:
            # One malformed payload for one company must cost that company's signals, not
            # the whole run.
            DIAG.setdefault("ch_row_errors", []).append("%s: %r" % (r["provider_id"], e))
            r["ch"] = {"status": "error", "company_number": None, "company_name": None,
                       "confidence": None, "note": "lookup failed: %r" % e}

    DIAG["ch"] = {"searched": checked, "matched": matched,
                  "skipped_as_personal": skipped_personal,
                  "calls": client.calls, "budget": client.budget,
                  "blocked": client.blocked, "exhausted": client.exhausted}
    return checked + skipped_personal, matched


# ========================================================================== main
def investability2(niche_of, path=None, niches=None, ch=True,
                   ch_budget=None, ch_client=None, anchor=None,
                   sector_fallback=True, name_guard=True):
    """Fragmentation recomputed on ECONOMIC OWNERS, plus the infancy/maturity read.

    Returns {niche: {
        locations,
        providers_legal,          # distinct CQC Provider IDs - the FLATTERING number
        owners_economic,          # after the Companies House dedupe - the honest one
        legal:    {units, single_site_pct, top5_share, hhi, lpp, indie, indie_pct},
        economic: {  ...same shape, computed on owners...  },
        bias:     {providers_overstated_by, providers_overstated_pct,
                   single_site_pct_overstated_by, hhi_understated_by,
                   top5_understated_by},
        hidden_groups, providers_in_hidden_groups,
        owners_economic_estimated,   # ESTIMATE: extrapolated to the unchecked remainder
        dedupe_coverage_pct, dedupe_status,
        entry_rate_pct, owner_entry_rate_pct, median_years_registered, new_12m,
        maturity, maturity_why,
        verdict, why, score, caveats
    }} or {} if the source cannot be read.

    With ch=False, or no CH_API_KEY, the dedupe does not run: owners_economic is None, the
    legal numbers are reported UNCHANGED, and dedupe_status says so loudly. It does NOT
    quietly present the flattering numbers as if they were the honest ones.
    """
    DIAG.clear()
    if not (_INV_OK and _TGT_OK):
        DIAG["fatal"] = "investability.py / targets.py not importable"
        return {}

    anchor = anchor or date.today()

    # ---------------------------------------------------------------------- the file
    path = path or os.environ.get("CQC_ODS_PATH") or None
    if not path:
        cached = os.path.join(tempfile.gettempdir(), "cqc.ods")
        if os.path.exists(cached) and os.path.getsize(cached) > 1_000_000:
            path = cached
            DIAG["source"] = "reused " + cached
    if not path:
        try:
            url = cqc_file_url()
            DIAG["url"] = url or "CQC page fetch failed"
            if not url:
                return {}
            m = re.search(r"/(\d{2})_([A-Za-z]+)_(\d{4})_HSCA", url)
            if m:
                try:
                    anchor = date(int(m.group(3)), MONTHS.get(m.group(2).lower(), 1),
                                  int(m.group(1)))
                except ValueError:
                    pass
            path = os.path.join(tempfile.gettempdir(), "cqc.ods")
            _download(url, path)
            DIAG["source"] = "downloaded " + url
        except Exception as e:
            DIAG["download_error"] = repr(e)[:200]
            return {}

    # -------------------------------------------------- one streaming pass, reused
    try:
        provs, meta = scan_providers(niche_of, path, niches=niches, anchor=anchor,
                                     sector_fallback=sector_fallback,
                                     name_guard=name_guard)
    except Exception as e:
        DIAG["parse_error"] = repr(e)[:200]
        return {}
    if not provs:
        return {}
    DIAG.update(meta or {})

    # -------------------------------------------------------------- rows for dedupe
    # ONE row per provider (a legal entity), whatever niches it appears in. A provider in
    # two niches is one company and must be deduped once, not twice.
    rows, by_niche = {}, defaultdict(list)
    for p in provs.values():
        if not p["niches"]:
            continue
        pcs = [l["postcode"] for l in p["locations"] if l["postcode"]]
        r = {
            "provider_id": p["provider_id"],
            "provider_name": p["provider_name"] or p["provider_id"],
            "postcodes": pcs,
            "sites": p["sites_total"],
            "ch": {"status": "not_checked", "company_number": None, "company_name": None,
                   "confidence": None, "note": "Companies House not consulted"},
            "ch_facts": {},
        }
        rows[p["provider_id"]] = r
        for n in p["niches"]:
            by_niche[n].append(r)
    for n in by_niche:
        by_niche[n].sort(key=lambda r: r["provider_id"])

    if not rows:
        return {}

    # ----------------------------------------------------------- Companies House
    client = ch_client or (CHClient(budget=ch_budget or CH_DEFAULT_BUDGET) if ch else None)
    dedupe_ran = bool(client is not None and client.key)
    if dedupe_ran:
        _enrich_for_dedupe(client, list(rows.values()), anchor, by_niche)
        pid2owner, owners, odiag = economic_owners(list(rows.values()))
        DIAG["economic_owners"] = odiag
    else:
        # NOT "everyone is their own owner because we checked". "We did not check."
        pid2owner = dict((pid, "OWN-" + pid) for pid in rows)
        owners = dict(("OWN-" + pid, {"owner_id": "OWN-" + pid, "providers": [pid],
                                      "n_providers": 1, "sites": r["sites"],
                                      "is_group": False, "link_reasons": []})
                      for pid, r in rows.items())
        DIAG["companies_house"] = ("skipped (no CH_API_KEY)" if not CH_KEY
                                   else "skipped (ch=False)")

    # An owner's FILE-WIDE site count is the sum of its providers' file-wide site counts.
    # That is what decides whether the OWNER is an acquirable independent or a group.
    owner_sites_total = Counter()
    for pid, r in rows.items():
        owner_sites_total[pid2owner.get(pid, "OWN-" + pid)] += r["sites"]
    prov_sites_total = dict((pid, r["sites"]) for pid, r in rows.items())

    # -------------------------------------------------------------- per-niche maths
    out = {}
    for niche, agg_rows in by_niche.items():
        p = provs
        prov_locs, owner_locs = Counter(), Counter()
        starts, new_12m = [], 0
        owner_first = {}                        # owner -> earliest registration in niche
        cutoff = _add_months(anchor, -12)

        for r in agg_rows:
            pid = r["provider_id"]
            locs = p[pid]["niches"][niche]
            oid = pid2owner.get(pid, "OWN-" + pid)
            prov_locs[pid] += len(locs)
            owner_locs[oid] += len(locs)
            for l in locs:
                d = l.get("start")
                if d:
                    starts.append(_years(d, anchor))
                    if d >= cutoff:
                        new_12m += 1
                    if oid not in owner_first or d < owner_first[oid]:
                        owner_first[oid] = d

        legal = _conc(prov_locs, prov_sites_total)
        econ = _conc(owner_locs, owner_sites_total) if dedupe_ran else None

        # ---- infancy vs maturity
        locations = legal["locations"]
        entry_rate = _pctf(new_12m, locations)
        new_owners = sum(1 for oid, d in owner_first.items() if d >= cutoff)
        owner_entry = _pctf(new_owners, len(owner_locs))
        med_years = _median(starts)
        mat, mat_why = maturity(entry_rate, med_years)

        # ---- the honest verdict, on economic owners where we have them
        indie = (econ or legal)["indie"]
        hhi = (econ or legal)["hhi"]
        top5 = (econ or legal)["top5_share"]
        v, why = verdict(indie, hhi, top5, mat, entry_rate, med_years)

        # ---- THE BIAS, made visible. Not corrected away.
        hidden = [o for o in owners.values() if o["is_group"]
                  and any(pid in prov_locs for pid in o["providers"])]
        bias = None
        if econ:
            bias = {
                "providers_overstated_by": legal["units"] - econ["units"],
                "providers_overstated_pct": _pctf(legal["units"] - econ["units"],
                                                  econ["units"]),
                "single_site_pct_overstated_by": (
                    None if (legal["single_site_pct"] is None
                             or econ["single_site_pct"] is None)
                    else round(legal["single_site_pct"] - econ["single_site_pct"], 1)),
                "hhi_understated_by": (
                    None if (legal["hhi"] is None or econ["hhi"] is None)
                    else round(econ["hhi"] - legal["hhi"], 4)),
                "top5_understated_by": (
                    None if (legal["top5_share"] is None or econ["top5_share"] is None)
                    else round(econ["top5_share"] - legal["top5_share"], 1)),
            }

        # ---- coverage, and an ESTIMATE of where the number would land at full coverage.
        checked = sum(1 for r in agg_rows if r["ch"]["status"] != "not_checked")
        coverage = _pctf(checked, len(agg_rows))
        est_owners = None
        if econ and checked and legal["units"]:
            # Among the providers we DID check, what fraction collapsed into somebody else?
            checked_ids = set(r["provider_id"] for r in agg_rows
                              if r["ch"]["status"] != "not_checked")
            collapsed = sum(1 for o in owners.values() if o["is_group"]
                            for pid in o["providers"][1:] if pid in checked_ids)
            rate = collapsed / float(len(checked_ids)) if checked_ids else 0.0
            est_owners = int(round(legal["units"] * (1.0 - rate)))
        caveats = []
        if not dedupe_ran:
            caveats.append("OWNER DEDUPE DID NOT RUN (no CH_API_KEY). Every number here is "
                           "the LEGAL-ENTITY number and it FLATTERS: a group holding twelve "
                           "Ltds is counted as twelve independents.")
        else:
            if coverage is not None and coverage < 100:
                caveats.append(
                    "Owner dedupe covered %.0f%% of the providers in this niche (Companies "
                    "House budget). The correction is PARTIAL, and dedupe can only ever "
                    "MERGE entities - so %d economic owners is an UPPER BOUND and the "
                    "residual error still flatters." % (coverage, econ["units"]))
            caveats.append("An owner using nominee directors and a virtual office is "
                           "invisible to this dedupe. So is one that holds its practices "
                           "through companies with no common director and no shared "
                           "registered office.")
        caveats.append(HSCA_CENSOR_NOTE)

        out[niche] = {
            "locations": locations,
            "providers_legal": legal["units"],
            "owners_economic": econ["units"] if econ else None,
            "legal": legal,
            "economic": econ,
            "bias": bias,
            "hidden_groups": len(hidden),
            "providers_in_hidden_groups": sum(
                1 for o in hidden for pid in o["providers"] if pid in prov_locs),
            "owners_economic_estimated": est_owners,
            "dedupe_coverage_pct": coverage,
            "dedupe_status": ("run" if dedupe_ran else "not run"),
            "new_12m": new_12m,
            "entry_rate_pct": entry_rate,
            "owner_entry_rate_pct": owner_entry,
            "median_years_registered": med_years,
            "maturity": mat,
            "maturity_why": mat_why,
            "verdict": v,
            "why": why,
            "score": score(indie, hhi, top5, mat),
            "caveats": caveats,
        }
    return out


# ==================================================================== SELF-TEST
def _fixture(path, anchor):
    """A synthetic CQC file with two niches that a Herfindahl index CANNOT tell apart, and
    a hidden owner that a Provider ID count CANNOT see.

    Both niches are sized like the real thing (250 operators each), because the density
    gates in investability.py are calibrated for the real thing: a 40-provider toy fixture
    trips "thin - regional platform at best" before the maturity test ever runs, and would
    prove nothing.

      DENTAL - fragmentation of MATURITY.
        250 providers, one site each, nearly all registered 15-20 years ago; 12 registered
        in the last 12 months -> entry rate 4.8%, median tenure 15 years.
        AMONG THEM: P-PE-01..12, twelve separate Ltd companies, one site each, all sharing
        one director (HOLDING, Marcus). CQC sees TWELVE INDEPENDENT SINGLE-SITE DENTISTS.
        They are one PE-backed group. That is the whole finding.
        ALSO: five genuinely independent dentists (P-ACC-1..5) sharing their ACCOUNTANT's
        registered office. A naive address union-find merges them into a fake five-site
        group and deletes five real targets. The MAX_ADDR_GROUP guard must not.

      LONGEVITY - fragmentation of INFANCY.
        250 providers, one site each, NOBODY grouped - so it is MORE fragmented than dental
        on every classical measure (lower HHI, lower top-5, 100% single-site). But 190 of
        the 250 registered in the last 12 months -> entry rate 76%, median tenure 0 years.
        The old verdict scores this ABOVE dental. It is not a roll-up at all.
    """
    from targets import REAL_HEADER, _c, _r, _HEAD, _TAIL

    old = _add_months(anchor, -12 * 15).isoformat()
    older = _add_months(anchor, -12 * 20).isoformat()
    recent = _add_months(anchor, -6).isoformat()
    D = []

    # ---- DENTAL, 250 providers -------------------------------------------------------
    # 12 Ltds, one director between them: the hidden PE group.
    for i in range(1, 13):
        D.append(("LD%03d" % i, old, "Bridgeway Dental %d" % i, "Primary Dental Care",
                  "London", "N1 %dAA" % (i % 10), "P-PE-%02d" % i,
                  "Bridgeway Dental %d Ltd" % i))
    # 5 real independents sharing an accountant's registered office: the trap.
    for i in range(1, 6):
        D.append(("LA%03d" % i, older, "Ashgrove Dental %d" % i, "Primary Dental Care",
                  "North West", "M1 %dBB" % i, "P-ACC-%d" % i,
                  "Ashgrove Dental %d Ltd" % i))
    # 233 genuine independents. 12 of them registered in the last 12 months -> 12/250.
    for i in range(1, 234):
        start = recent if i <= 12 else old
        D.append(("LO%03d" % i, start, "Fairview Dental %d" % i, "Primary Dental Care",
                  "South West", "BS1 %dCC" % (i % 10), "P-IND-%03d" % i,
                  "Fairview Dental %d Ltd" % i))

    # ---- LONGEVITY, 250 providers, none grouped, 190 of them brand new ----------------
    for i in range(1, 251):
        start = recent if i <= 190 else old
        D.append(("LL%03d" % i, start, "Peptide Longevity Lab %d" % i,
                  "Independent Healthcare Org", "London", "W1 %dDD" % (i % 10),
                  "P-LON-%03d" % i, "Peptide Longevity Lab %d Ltd" % i))

    body = [_r([_c(h) for h in REAL_HEADER], blanks=1000)]
    for (lid, st, nm, sec, reg, pc, pid, pn) in D:
        body.append(_r([_c(lid), _c(st, "date"), _c(nm), _c(sec), _c(""), _c(""),
                        _c(reg), _c("LA " + reg), _c(pc), _c(pid), _c(pn), _c(sec)],
                       blanks=3))
    xml = (_HEAD + '<table:table table:name="README">'
           + _r([_c("README sheet - not the data.")]) + "</table:table>"
           + '<table:table table:name="HSCA_Active_Locations">' + "".join(body)
           + "</table:table>" + _TAIL)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", xml)
    return D


def _fake_ch(anchor):
    """Canned Companies House, served through the REAL CHClient - so the throttle, the
    budget, the cache and the 404 path are all on the tested code path."""
    from targets import CH_BASE, norm_name
    import urllib.parse as up

    def dob(age, month=6):
        return {"month": month,
                "year": anchor.year - age - (1 if anchor.month < month else 0)}

    def addr(prem, l1, pc):
        return {"premises": prem, "address_line_1": l1, "postal_code": pc}

    def alpha(i):
        """1 -> A, 26 -> Z, 27 -> AA. Officer names must be distinguishable WITHOUT DIGITS.

        targets._officer_key strips every non-letter from an officer's name before keying
        on it, so "FAIRVIEW, Owner 3" and "FAIRVIEW, Owner 18" are THE SAME PERSON to the
        dedupe. That is correct behaviour (a name is letters), but it means a fixture that
        numbers its directors would silently fabricate shared directors and merge unrelated
        companies - which is exactly the false positive the dedupe is supposed to avoid, and
        it would have been proved "working" by a broken test. Names here are therefore
        alphabetic and unique.
        """
        s = ""
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    COS, OFF, PROF = {}, {}, {}

    def company(name, num, ad, officers):
        COS[name] = (num, ad)
        OFF[num] = officers
        PROF[num] = {"company_number": num, "company_name": name,
                     "company_status": "active", "date_of_creation": "2009-03-02",
                     "registered_office_address": ad,
                     "accounts": {"next_accounts": {"overdue": False}},
                     "confirmation_statement": {"overdue": False},
                     "previous_company_names": []}

    # THE HIDDEN GROUP: twelve companies, twelve DIFFERENT registered offices, but ONE
    # director on every board. Only the DOB-keyed director link can find this - which is
    # exactly how a real PE roll-up looks from the outside.
    for i in range(1, 13):
        company("Bridgeway Dental %d Ltd" % i, "0200%04d" % i,
                addr(str(i), "Bridge St %d" % i, "N1 %dAA" % (i % 10)),
                [{"name": "HOLDING, Marcus", "officer_role": "director",
                  "date_of_birth": dob(52, 4)},
                 {"name": "LOCUM%s, Dentist%s" % (alpha(i), alpha(i)),
                  "officer_role": "director", "date_of_birth": dob(40 + (i % 20), 3)}])

    # THE ACCOUNTANT TRAP: five unrelated dentists, five different sole directors, ONE
    # shared registered office (their accountant's). Must NOT be merged.
    for i in range(1, 6):
        company("Ashgrove Dental %d Ltd" % i, "0210%04d" % i,
                addr("10", "Accountancy House", "M60 1AA"),
                [{"name": "ASHER%s, Owner%s" % (alpha(i), alpha(i)),
                  "officer_role": "director", "date_of_birth": dob(55 + i, 5)}])

    # 233 genuinely independent dentists and 250 longevity clinics: no shared director, no
    # shared office. Names are ALPHABETIC and unique - see alpha().
    for i in range(1, 234):
        company("Fairview Dental %d Ltd" % i, "0220%04d" % i,
                addr(str(i), "Fair Rd %d" % i, "BS1 %dCC" % (i % 10)),
                [{"name": "FAIRO%s, Owner%s" % (alpha(i), alpha(i)),
                  "officer_role": "director", "date_of_birth": dob(50 + (i % 15), 7)}])
    for i in range(1, 251):
        company("Peptide Longevity Lab %d Ltd" % i, "0230%04d" % i,
                addr(str(i), "Long Rd %d" % i, "W1 %dDD" % (i % 10)),
                [{"name": "LONGO%s, Founder%s" % (alpha(i), alpha(i)),
                  "officer_role": "director", "date_of_birth": dob(30 + (i % 10), 9)}])

    def fetch(url):
        p = url[len(CH_BASE):]
        if p.startswith("/search/companies"):
            q = up.unquote(up.parse_qs(up.urlparse(p).query).get("q", [""])[0])
            items = [{"title": nm, "company_number": num, "company_status": "active",
                      "address": ad}
                     for nm, (num, ad) in COS.items() if norm_name(nm) == norm_name(q)]
            return 200, {"items": items}
        m = re.match(r"^/company/(\d+)(/[a-z\-]+)?", p)
        if m:
            num, sub = m.group(1), (m.group(2) or "")
            if num not in PROF:
                return 404, None
            if sub == "":
                return 200, PROF[num]
            if sub == "/officers":
                return 200, {"items": OFF.get(num, [])}
        return 404, None

    return fetch


_T_NICHES = [("Longevity / peptides / IV", ["peptide", "longevity"]),
             ("Dental / orthodontics", ["dental", "dentist"])]


def _t_niche_of(text):
    t = (text or "").lower()
    for nm, keys in _T_NICHES:
        for k in keys:
            if re.search(r"\b" + re.escape(k), t):
                return nm
    return None


def selftest():
    if not (_INV_OK and _TGT_OK):
        print("FAIL: investability.py / targets.py not importable from %s" % _HERE)
        return 1

    fails = []

    def chk(label, got, want):
        ok = (got == want)
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("  %s %-54s %s" % ("PASS" if ok else "FAIL", label, got))

    tmp = tempfile.mkdtemp(prefix="inv2_")
    ods = os.path.join(tmp, "cqc.ods")
    anchor = date(2026, 7, 1)
    _fixture(ods, anchor)

    # ------------------------------------------------------- 1. maturity discriminator
    print("\n[1] the infancy / maturity discriminator")
    chk("22% entry -> INFANT", maturity(22.0, 2.0)[0], MATURITY_INFANT)
    chk("4% entry  -> MATURE", maturity(4.0, 12.0)[0], MATURITY_MATURE)
    chk("11% entry -> SETTLING", maturity(11.0, 5.0)[0], MATURITY_SETTLING)
    chk("no dates -> None, not a guess", maturity(None, None)[0], None)
    chk("mature entry + young stock is FLAGGED, not averaged",
        "Treat as SETTLING" in maturity(4.0, 2.0)[1], True)
    chk("infant entry + old stock is FLAGGED as a growth spurt",
        "growth spurt" in maturity(30.0, 12.0)[1], True)

    # ------------------------------------------------------------------ 2. verdicts
    print("\n[2] the verdict tells the two trades apart")
    v_mat = verdict(200, 0.02, 8.0, MATURITY_MATURE, 4.0, 12.0)[0]
    v_inf = verdict(200, 0.02, 8.0, MATURITY_INFANT, 22.0, 1.0)[0]
    chk("deep + fragmented + MATURE -> roll-up runway", v_mat, V_MATURE_FRAG)
    chk("deep + fragmented + INFANT -> gold rush, NOT a roll-up", v_inf, V_INFANT_FRAG)
    chk("...and they are DIFFERENT verdicts on identical HHI/top-5", v_mat != v_inf, True)
    chk("deep + fragmented + SETTLING -> too early",
        verdict(200, 0.02, 8.0, MATURITY_SETTLING, 11.0, 5.0)[0], V_SETTLING_FRAG)
    chk("density gate still bites first (29 owners)",
        verdict(29, 0.0, 0.0, MATURITY_MATURE, 2.0, 20.0)[0], V_TOO_SMALL)
    chk("consolidated still bites before maturity",
        verdict(200, 0.30, 55.0, MATURITY_MATURE, 2.0, 20.0)[0], V_CONSOLIDATED)
    chk("gold rush scores BELOW the identical mature niche",
        score(200, 0.02, 8.0, MATURITY_INFANT) < score(200, 0.02, 8.0, MATURITY_MATURE),
        True)

    # -------------------------------------------- 3. NO Companies House: honest, not quiet
    print("\n[3] no CH key: the flattering numbers are reported AS flattering")
    r0 = investability2(_t_niche_of, path=ods, ch=False, anchor=anchor)
    d0 = r0["Dental / orthodontics"]
    chk("250 legal providers", d0["providers_legal"], 250)
    chk("owners_economic is None - not silently equal to providers",
        d0["owners_economic"], None)
    chk("dedupe_status says so", d0["dedupe_status"], "not run")
    chk("caveat is explicit that the numbers FLATTER",
        any("FLATTERS" in c for c in d0["caveats"]), True)
    chk("un-deduped, dental looks 100% single-site", d0["legal"]["single_site_pct"], 100.0)

    # ------------------------------ 4. THE FINDING: 12 Ltds, 1 owner. The whole point.
    print("\n[4] owner dedupe: twelve 'independents' are one economic owner")
    client = CHClient(key="TEST", budget=5000, fetch=_fake_ch(anchor),
                      sleep=lambda s: None)
    res = investability2(_t_niche_of, path=ods, ch=True, ch_client=client, anchor=anchor)
    d = res["Dental / orthodontics"]

    chk("CQC says 250 independent legal providers", d["providers_legal"], 250)
    # The 12 Bridgeway Ltds collapse into ONE owner: 250 - 12 + 1 = 239.
    chk("Companies House says 239 economic owners", d["owners_economic"], 239)
    chk("hidden groups found", d["hidden_groups"], 1)
    chk("providers inside them", d["providers_in_hidden_groups"], 12)
    chk("the bias is REPORTED, not corrected away",
        d["bias"]["providers_overstated_by"], 11)
    chk("provider count overstated by 4.6%", d["bias"]["providers_overstated_pct"], 4.6)

    # The accountant trap: five real independents sharing one registered office. If the
    # guard failed they would collapse into a fake five-site group and owners would be 235.
    chk("ACCOUNTANT TRAP: the 5 shared-address dentists stay independent",
        d["owners_economic"], 239)
    ag = (DIAG.get("economic_owners") or {}).get("agent_addresses_ignored") or []
    chk("...and the shared address is REPORTED as an agent address", len(ag) >= 1, True)

    # Fragmentation moves in the flattering direction, exactly as predicted.
    chk("single-site % falls once owners are real",
        d["economic"]["single_site_pct"] < d["legal"]["single_site_pct"], True)
    chk("HHI RISES once owners are real (the legal HHI understates)",
        d["economic"]["hhi"] > d["legal"]["hhi"], True)
    chk("top-5 share RISES once owners are real",
        d["economic"]["top5_share"] > d["legal"]["top5_share"], True)
    chk("legal top-5 (5 x 1 site of 250)", d["legal"]["top5_share"], 2.0)
    chk("economic top-5 (12 + 1 + 1 + 1 + 1 of 250)", d["economic"]["top5_share"], 6.4)
    chk("the 12-site owner is NOT counted as an acquirable independent",
        d["economic"]["indie"], 238)

    # ------------------------------------- 5. two niches, same HHI, opposite trades
    print("\n[5] identical fragmentation, opposite trades")
    lon = res["Longevity / peptides / IV"]
    chk("dental: 12 of 250 registered last year", d["new_12m"], 12)
    chk("dental entry rate 4.8%", d["entry_rate_pct"], 4.8)
    chk("dental is MATURE", d["maturity"], MATURITY_MATURE)
    chk("dental median tenure 15 years", d["median_years_registered"], 15.0)
    chk("longevity: 190 of 250 registered last year", lon["new_12m"], 190)
    chk("longevity entry rate 76%", lon["entry_rate_pct"], 76.0)
    chk("longevity is INFANT", lon["maturity"], MATURITY_INFANT)
    chk("longevity median tenure 0 years", lon["median_years_registered"], 0.0)

    # On EVERY classical measure longevity looks like the better roll-up. It is not one.
    chk("longevity is MORE fragmented: 100% single-site", 
        lon["economic"]["single_site_pct"], 100.0)
    chk("longevity HHI is LOWER than dental's (looks BETTER on the old metric)",
        lon["economic"]["hhi"] < d["economic"]["hhi"], True)
    chk("longevity top-5 is LOWER than dental's (looks BETTER too)",
        lon["economic"]["top5_share"] < d["economic"]["top5_share"], True)
    chk("longevity has MORE independent owners than dental",
        lon["economic"]["indie"] > d["economic"]["indie"], True)

    # ...and the verdict tells them apart anyway. This is the whole module.
    chk("dental verdict: MATURE roll-up runway", d["verdict"], V_MATURE_FRAG)
    chk("longevity verdict: GOLD RUSH, not a roll-up", lon["verdict"], V_INFANT_FRAG)
    chk("longevity scores BELOW dental despite better fragmentation on every metric",
        lon["score"] < d["score"], True)

    # ------------------------------------------------------------- 6. coverage honesty
    print("\n[6] partial coverage is reported, and the residual error still flatters")
    small = CHClient(key="TEST", budget=60, fetch=_fake_ch(anchor), sleep=lambda s: None)
    res2 = investability2(_t_niche_of, path=ods, ch=True, ch_client=small, anchor=anchor)
    d2 = res2["Dental / orthodontics"]
    chk("budget ran out", small.exhausted, True)
    chk("coverage is reported and is < 100%", d2["dedupe_coverage_pct"] < 100.0, True)
    chk("owners found >= fully-deduped owners (so it is an UPPER BOUND)",
        d2["owners_economic"] >= d["owners_economic"], True)
    chk("caveat states the bound explicitly",
        any("UPPER BOUND" in c for c in d2["caveats"]), True)
    chk("an ESTIMATE of the full-coverage number is offered, clearly labelled",
        d2["owners_economic_estimated"] is not None, True)

    # -------------------------------------------------------------- 7. never crash
    print("\n[7] garbage in, {} out")
    bad = os.path.join(tmp, "bad.ods")
    open(bad, "wb").write(b"not a zip")
    chk("corrupt file -> {}", investability2(_t_niche_of, path=bad, ch=False), {})

    print("\n" + "=" * 72)
    if fails:
        print("SELFTEST FAILED (%d)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST PASSED")
    return 0


def _print(res):
    print("%-26s %5s %6s %7s %6s %6s %6s %5s  %s" % (
        "niche", "locs", "legal", "owners", "1site%", "top5%", "entry%", "score",
        "verdict"))
    for n, r in sorted(res.items(), key=lambda kv: -kv[1]["score"]):
        e = r["economic"] or r["legal"]
        print("%-26s %5s %6s %7s %5s%% %5s%% %5s%% %5s  %s" % (
            n[:26], r["locations"], r["providers_legal"],
            r["owners_economic"] if r["owners_economic"] is not None else "-",
            e["single_site_pct"], e["top5_share"], r["entry_rate_pct"], r["score"],
            r["verdict"]))
        print("%-26s   %s" % ("", r["why"]))
        print("%-26s   %s" % ("", r["maturity_why"]))


if __name__ == "__main__":
    if "--selftest" in sys.argv or "--test" in sys.argv:
        raise SystemExit(selftest())
    try:
        from taxonomy import niche_of as real_niche_of
    except Exception:
        real_niche_of = _t_niche_of
        print("(taxonomy not importable - using the cut-down test taxonomy)")
    out = investability2(real_niche_of)
    if not out:
        print("investability2: CQC source unreachable")
        print(json.dumps(DIAG, indent=1, default=str))
    else:
        _print(out)
        print("\nDIAG:", json.dumps(DIAG, indent=1, default=str))
