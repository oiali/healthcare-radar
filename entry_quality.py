#!/usr/bin/env python3
"""
ENTRY QUALITY - is a new company a new OPERATOR, or an accounting event?

THE ATTACK THIS ANSWERS
-----------------------
Tier 2 of the radar counts NEW COMPANY INCORPORATIONS whose name contains a niche
term. A reviewer put it like this, and he is substantially right:

    "T2 measures incorporations. Incorporations are driven by cost of entry and
     employment status, not demand. A wave of locum physiotherapists incorporating
     personal service companies for tax reasons produces exactly your signal. So does
     a franchise filing 16 regional SPVs. T2 is a barrier-to-entry meter wearing a
     demand-signal costume."

A "personal service company" here means a one-person limited company that a
self-employed clinician sets up to be PAID THROUGH - it sells that person's labour to
someone else's clinic or to an agency. It is not a new clinic. It has no premises, no
staff and no patients of its own. An "SPV" is a special-purpose vehicle: one Ltd per
site, which is how franchises and small groups hold their estate - sixteen of them is
one operator, not sixteen.

Neither is a new entrant serving new demand. Both look identical to T2.

WHAT THIS MODULE DOES
---------------------
Splits a cohort of new incorporations into four buckets, and re-weights T2 so a
niche's count reflects REAL new operators only:

    real              a trading entity. Brand-style name, no person tell, not part of
                      a multi-company cluster.
    personal_service  a one-person company that sells a person, not a service line.
    spv_franchise     one of several companies incorporated by the same controller in
                      the same short window - one operator wearing N hats.
    unknown           we cannot tell. THIS IS A REAL ANSWER AND IT IS REPORTED, because
                      the unknown fraction IS the honest error bar on the whole tier.

HOW SURE CAN WE BE (read this before believing any number below)
---------------------------------------------------------------
The zero-cost pass uses only what the advanced-search endpoint already returns: name,
incorporation date, registered office, SIC codes. It can catch a person-named company
and a clustered SPV batch. It CANNOT distinguish a solo clinician contracting through
"The Movement Clinic Ltd" from a solo clinician opening a clinic called
"The Movement Clinic Ltd". Nothing at Companies House can. Those rows are marked
`real` with confidence `name-only`, and that population is reported separately so it
can be treated as suspect rather than as fact.

The paid pass (1-2 Companies House calls per company) adds officers and PSCs, which is
what turns a guess into a finding: a sole director, appointed on the day of
incorporation, who is also the sole person with significant control, and WHOSE SURNAME
IS IN THE COMPANY NAME, is a personal service company and there is very little room to
argue about it.

WHAT WE DO NOT CLAIM
--------------------
We do not claim to detect intent. A person-named company CAN be a real clinic - plenty
of good practices are called after their founder. That is why a person-named company is
only called `personal_service` when a SECOND signal agrees (sole officer at
incorporation / sole PSC / generic SIC / non-business registered office), and why a
person-named company whose sole director has a DIFFERENT surname is pushed back towards
`real` - the name is a brand, not the owner.

REUSE, NOT REIMPLEMENTATION
---------------------------
The owner-dedupe (shared director name+DOB, shared registered office, with the
accountant-address guard) already exists in targets.py and is imported, not copied.
This module adds ONE thing the dedupe deliberately does not do: it re-examines the
address groups the dedupe THREW AWAY as accountants' addresses. See PART 3 - the
difference between an accountant and a franchise is not the number of companies at the
address, it is whether their names are formulaic and their birthdays are the same week.

    python3 entry_quality.py --selftest            no network, synthetic fixtures
    python3 entry_quality.py --diagnose "physio"   LIVE. Answers the MSK question.
"""

import os
import re
import sys
import json
import math
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

# The owner-dedupe, the throttled CH client, the name normaliser and the address /
# officer keys all already exist and are already tested. Import them.
from targets import (                                    # noqa: E402
    CHClient, economic_owners, norm_name, _addr_key, _officer_key, _items,
    _parse_date, MAX_ADDR_GROUP,
)

DIAG = {}

# ---------------------------------------------------------------- knobs, in one place
SPV_MIN_CLUSTER = 4        # companies sharing a controller before we call it an SPV batch
SPV_WINDOW_DAYS = 120      # ...and incorporated within this many days of each other
FORMULAIC_MIN = 4          # names sharing a skeleton before we call the family formulaic
MIN_REAL_FOR_ROW = 4       # matches pull_and_build's own `if c < 4: continue`
GENERIC_SIC = "86900"      # "other human health activities" - the catch-all


# ============================================================================
# PART 1 - is this company NAMED AFTER A PERSON?
# ============================================================================
#
# The single most useful free signal. "J Smith Physiotherapy Ltd" is a person selling
# their labour. "The Movement Clinic Ltd" is a business trying to acquire patients.
# People who intend to build something that outlives them almost never name it after
# themselves; people who incorporate because their agency told them to, almost always
# do, because they are not naming a brand, they are naming an invoice.
#
# The rule looks ONLY at the tokens BEFORE the first trade word. "Sarah Jones Physio"
# has "sarah jones" in front of "physio" -> person. "Physio First" has nothing in front
# of "physio" -> not a person. This is what stops the trade word itself (which is in
# every name in the cohort, by construction, because that is how they were selected)
# from confusing the test.

_TRADE = set("""
physio physiotherapy physiotherapist osteopath osteopathy chiro chiropractic
chiropractor podiatry podiatrist rehab rehabilitation therapy therapies therapist
clinic clinics centre center practice surgery studio health healthcare wellness
wellbeing sports sport spine spinal back body bodies motion movement performance
recovery pilates massage sportscare musculoskeletal msk medical medicine care
dental dentist orthodontic aesthetics aesthetic skin clinicians consulting
consultancy services service solutions group holdings associates partners
""".split())

# Words that are common UK forenames. Deliberately a SHORT, HIGH-PRECISION list: a long
# list starts eating surnames and place names ("Preston", "Sutton", "Grant", "Ashley")
# and turns a genuine clinic into a false personal-service company, which is the error
# that matters here - it would delete real signal. Names that are also UK towns, common
# surnames or common brand words are EXCLUDED on purpose.
_FORENAMES = set("""
aaron abbie abdul adam adrian aisha alan alex alexander alice alison amanda amber amy
andrea andrew angela anna anne annie anthony antonio arthur ashleigh barbara benjamin
bethany brian callum cameron caroline catherine charlotte chloe christine christopher
claire connor craig daniel danielle darren david dawn deborah declan denise dominic
donna dylan edward eleanor elizabeth ellie emily emma eric ethan fiona frances gareth
gary gavin gemma geoffrey george georgia gerard gillian gordon grace graham hannah
harriet harry heather helen henry hollie holly hugh ian imran isabel jack jacqueline
james jamie jane janet jasmine jason jean jennifer jenny jeremy jessica joanne jodie
john jonathan joseph joshua julia julie karen katherine kathleen katie keith kelly
kerry kevin kieran kirsty laura lauren leanne leon lewis liam linda lindsey lisa
louise lucy luke lydia malcolm marcus margaret maria marie mark martin mary matthew
maureen megan melanie michael michelle mohammed muhammad nadia naomi natalie nathan
neil nicholas nicola nigel oliver olivia oscar owen patricia patrick paula pauline
peter philip philippa rachel rebecca rhys richard ricky robert robin roger rosie ruth
ryan sally samantha samuel sandra sarah scott sean shannon sharon sheila simon
sinead sophie stephanie stephen steven stuart susan suzanne teresa terence thomas
timothy tracey trevor vanessa vicky victoria vincent wendy william yvonne zoe
""".split())

_TITLE_RE = re.compile(r"^(dr|doctor|mr|mrs|miss|ms|prof|professor)\b", re.I)
_POSSESSIVE_RE = re.compile(r"\b[a-z]+['’]s\b", re.I)
_SUFFIX_TOKENS = set("""limited ltd llp plc cic co company the and of uk gb""".split())


def _tokens(name):
    """Company name -> lowercase word tokens, legal suffix and filler removed."""
    toks = re.findall(r"[a-z]+", (name or "").lower())
    return [t for t in toks if t not in _SUFFIX_TOKENS]


def _lead_tokens(name):
    """The tokens BEFORE the first trade word. That is where a person's name lives."""
    out = []
    for t in _tokens(name):
        if t in _TRADE:
            break
        out.append(t)
    return out


def person_name_signal(name):
    """-> (strength, reason) where strength is 'strong', 'weak' or None.

    strong  a form that is a person and essentially cannot be a brand:
            a title ("Dr A Patel Physio"), or initials + surname ("J Smith Physio",
            "J R Hartley Physiotherapy"). Nobody brands a clinic this way.
    weak    forename + surname ("Sarah Jones Physio"). Very often a person selling
            their labour - and sometimes a perfectly real practice named after its
            founder. Never enough on its own; must be corroborated.
    """
    raw = (name or "").strip()
    if not raw:
        return None, ""
    if _TITLE_RE.match(raw):
        return "strong", "name carries a personal title (Dr/Mr/Mrs...)"

    lead = _lead_tokens(raw)
    if not lead:
        return None, ""
    if len(lead) > 4:
        return None, ""                       # a long phrase is a brand, not a person

    # initials + surname: at least one single-letter token, then a word.
    initials = [t for t in lead if len(t) == 1]
    if initials and len(lead) - len(initials) == 1 and len(lead) <= 4:
        return "strong", "name is initials + surname (%s)" % " ".join(lead)

    if _POSSESSIVE_RE.search(raw):
        return "weak", "possessive name form (someone's practice)"

    if len(lead) == 2 and lead[0] in _FORENAMES and lead[1] not in _FORENAMES:
        return "weak", "name begins with a forename + surname (%s)" % " ".join(lead)
    if len(lead) == 1 and lead[0] in _FORENAMES:
        # "Sarah Physiotherapy Ltd" - a first name and nothing else.
        return "weak", "name begins with a bare forename (%s)" % lead[0]
    return None, ""


def surname_in_name(company_name, officer_name):
    """Does the sole director's SURNAME appear in the company name?

    This is the decisive test, and it needs no forename list, no heuristic and no luck.
    Companies House gives officers as "SMITH, John Andrew". If "smith" is a token of
    "J Smith Physiotherapy Ltd", the company is named after the person who owns it.
    """
    if not company_name or not officer_name:
        return None
    nm = (officer_name or "").strip().lower()
    sur = nm.partition(",")[0].strip() if "," in nm else (nm.split() or [""])[-1]
    sur = re.sub(r"[^a-z]", "", sur)
    if len(sur) < 3:
        return None
    return sur if sur in set(_tokens(company_name)) else None


# ============================================================================
# PART 2 - the registered office, and the SIC code
# ============================================================================
#
# WEAK SIGNALS, HONESTLY LABELLED. Neither can classify a company on its own and
# neither is allowed to.
#
# ADDRESS. A real clinic has premises: "Unit 4", "Suite 2", "The Old Mill", a business
# park, a high street parade. A personal service company is registered at the owner's
# house or at the accountant who set it up. We can spot the BUSINESS tokens reliably.
# We CANNOT reliably spot a residential address - "12 Church Lane" is a house, and it
# is also where a good number of genuine single-room clinics operate from. So the
# address signal is used in ONE direction only: business tokens are evidence FOR a real
# operator. Their absence is NOT evidence against one, it is just silence.
#
# SIC. A personal service company is set up by an accountant in four minutes and gets
# 86900 ("other human health activities") because that is the box the formation agent
# ticks. A clinic that has thought about what it is more often carries a second, more
# specific code. Also weak: plenty of real clinics are 86900 too.

_BUSINESS_ADDR = set("""
unit units suite suites floor floors office offices business park centre center
industrial estate chambers house mill works studio studios mall arcade parade precinct
retail plaza court wharf yard clinic hospital surgery
""".split())


def address_signal(addr):
    """-> ('business' | 'unclear', reason). Never returns 'residential'. See above."""
    if not isinstance(addr, dict):
        return "unclear", "no registered office in the record"
    blob = " ".join(str(addr.get(k) or "") for k in
                    ("premises", "address_line_1", "address_line_2"))
    toks = set(re.findall(r"[a-z]+", blob.lower()))
    hit = toks & _BUSINESS_ADDR
    if hit:
        return "business", "registered office looks like premises (%s)" % ", ".join(sorted(hit))
    return "unclear", "registered office has no business premises words - could be a "\
                      "home, could be a small clinic. Not treated as evidence either way."


def sic_signal(sics):
    """-> (True, reason) if the ONLY code is the generic 86900 catch-all."""
    codes = [str(s).strip() for s in (sics or []) if str(s).strip()]
    if codes == [GENERIC_SIC]:
        return True, "single generic SIC 86900 (the formation-agent default)"
    return False, ""


# ============================================================================
# PART 3 - the SPV / franchise cluster. Where targets.py's guard needs one more test.
# ============================================================================
#
# targets.economic_owners() groups companies that share a director (name+DOB) or a
# registered office, and it protects itself from the ACCOUNTANT problem: if more than
# MAX_ADDR_GROUP (4) companies share one address, that address is assumed to be an
# accountant or a formation agent, discarded as a link, and reported. That guard is
# correct and it is why 30 unrelated clinics using one bookkeeper are not merged into a
# fictitious 30-site group.
#
# But it has an obvious hole for THIS job: a franchise that files 16 SPVs from one head
# office trips the same guard. Sixteen > four, so the address is thrown away as an
# accountant's, and the franchise sails through as 16 independent new entrants - which
# is exactly the artefact we are hunting.
#
# The fix is NOT to raise the threshold (that would re-merge the accountants). It is to
# ask a second question about the discarded addresses. An accountant's client list and a
# franchise's SPV batch look completely different:
#
#     accountant   heterogeneous names, unrelated to one another, incorporated on
#                  scattered dates across years, because clients arrive one at a time.
#     franchise    FORMULAIC names - the same skeleton with one slot swapped
#                  ("Leeds Physio Ltd", "Derby Physio Ltd", "Bolton Physio Ltd") - and
#                  incorporation dates in a tight cluster, because a rollout is a
#                  project with a deadline.
#
# So: an address group rejected by the guard is re-admitted as an SPV batch ONLY if the
# names are formulaic AND the dates cluster. Both, not either. That keeps the
# accountant's 30 clinics apart and still catches the 16 SPVs.
#
# (The 16-SPVs-sharing-a-DIRECTOR case needs none of this - economic_owners already
# links those directly, because a person who directs 16 clinic companies IS a 16-clinic
# group, and that is a finding, not a false positive.)


def _skeletons(names):
    """Names -> {skeleton: [names]} where a skeleton is the name with ONE variable slot.

    "leeds physio", "derby physio", "bolton physio" all reduce to ("*", "physio").
    Built by dropping the first token, and separately the last, so both
    "<TOWN> Physio" and "Physio <TOWN>" families are found.
    """
    out = defaultdict(list)
    for n in names:
        toks = tuple(_tokens(norm_name(n)))
        if len(toks) < 2:
            continue
        out[("*",) + toks[1:]].append(n)
        out[toks[:-1] + ("*",)].append(n)
    return out


def formulaic_family(names, min_members=FORMULAIC_MIN):
    """-> (skeleton, [names]) if >= min_members names share a skeleton with DISTINCT
    fillers, else (None, []). The distinct-filler test matters: four companies all
    called "City Physio Ltd" are not a franchise, they are a duplicate-name mess."""
    best = (None, [])
    for skel, members in _skeletons(names).items():
        if len(members) < min_members:
            continue
        idx = skel.index("*")
        fillers = set()
        for n in members:
            toks = _tokens(norm_name(n))
            if idx < len(toks):
                fillers.add(toks[idx])
        if len(fillers) < min_members:
            continue                          # same filler repeated - not a family
        if len(members) > len(best[1]):
            best = (skel, members)
    return best


def _dates_cluster(dates, window_days=SPV_WINDOW_DAYS, min_members=SPV_MIN_CLUSTER):
    """True if at least min_members of these incorporation dates fall inside one window."""
    ds = sorted(d for d in dates if d)
    if len(ds) < min_members:
        return False
    for i in range(len(ds) - min_members + 1):
        if (ds[i + min_members - 1] - ds[i]).days <= window_days:
            return True
    return False


def spv_clusters(recs, uf_owners, uf_diag):
    """-> ({company_number: cluster_id}, [cluster, ...])

    Two routes in:
      1. economic_owners() already grouped them (shared director, or a small shared
         address). Any group of >= SPV_MIN_CLUSTER companies is an SPV batch.
      2. economic_owners() THREW THE ADDRESS AWAY as an accountant's (see above). We
         re-admit it only if the names are formulaic AND the dates cluster.
    """
    by_num = {r["company_number"]: r for r in recs if r.get("company_number")}
    assign, clusters = {}, []

    for _oid, o in (uf_owners or {}).items():
        members = [m for m in o.get("providers", []) if m in by_num]
        if len(members) < SPV_MIN_CLUSTER:
            continue
        # ONLY a shared DIRECTOR promotes a group straight to "SPV batch". A group that
        # economic_owners linked purely on a SHARED REGISTERED OFFICE is not enough:
        # four unrelated clinics that happen to use the same small accountant would be
        # merged, and four real new operators would be deleted from the count. That is
        # the same accountant problem, one size down, and it needs the same second test.
        # Address-only groups therefore fall through to route 2 below and must ALSO show
        # formulaic names and clustered dates before we believe they are one operator.
        reasons = o.get("link_reasons") or []
        if not any(str(x).startswith("shares director") for x in reasons):
            continue
        cid = "CL-%d" % len(clusters)
        clusters.append({
            "cluster_id": cid, "members": members, "n": len(members),
            "route": "shared controller",
            "why": "; ".join(reasons),
        })
        for m in members:
            assign[m] = cid

    # route 2 - the addresses the accountant-guard discarded
    by_addr = defaultdict(list)
    for r in recs:
        if r.get("addr_key") and r["company_number"] not in assign:
            by_addr[r["addr_key"]].append(r)
    for _ak, group in by_addr.items():
        # Both the groups the accountant-guard REJECTED as agents' addresses (too many
        # companies) and the small ones it accepted arrive here. Same test for both.
        if len(group) < SPV_MIN_CLUSTER:
            continue
        names = [g["company_name"] for g in group]
        skel, fam = formulaic_family(names)
        if not fam:
            continue                          # heterogeneous names -> an accountant. Leave it.
        fam_recs = [g for g in group if g["company_name"] in set(fam)]
        if not _dates_cluster([g.get("incorporated") for g in fam_recs]):
            continue                          # scattered dates -> an accountant. Leave it.
        cid = "CL-%d" % len(clusters)
        clusters.append({
            "cluster_id": cid, "members": [g["company_number"] for g in fam_recs],
            "n": len(fam_recs), "route": "formulaic names + clustered dates at one address",
            "why": "%d companies at one registered office share the name pattern %s and "
                   "were incorporated within %d days of each other - a rollout, not an "
                   "accountant's client list"
                   % (len(fam_recs), " ".join(skel or ()), SPV_WINDOW_DAYS),
        })
        for g in fam_recs:
            assign[g["company_number"]] = cid
    return assign, clusters


# ============================================================================
# PART 4 - officers and PSCs: the calls that turn a guess into a finding
# ============================================================================

def enrich_officers(client, recs, want_psc=True, limit=None):
    """Fetch officers (+PSCs) for recs, in place. 1-2 CH calls each. Budgeted.

    Rows we could not enrich keep `officers_checked: False`, and every downstream
    decision knows the difference between "one director" and "we never asked".
    """
    n = 0
    for r in recs:
        if limit is not None and n >= limit:
            break
        num = r.get("company_number")
        if not num or not client or not client.live:
            continue
        offs = client.officers(num)
        n += 1
        if offs is None:
            continue                          # budget, 404 or transport - NOT "no officers"
        active = []
        for o in _items(offs):
            if o.get("resigned_on"):
                continue
            if (o.get("officer_role") or "").lower() not in (
                    "director", "llp-member", "llp-designated-member"):
                continue                      # secretaries are not owners
            active.append(o)
        r["officers_checked"] = True
        r["n_directors"] = len(active)
        r["director_keys"] = [k for k in (_officer_key(o) for o in active) if k]
        r["director_names"] = [o.get("name") for o in active]
        if len(active) == 1:
            o = active[0]
            r["sole_director_name"] = o.get("name")
            app = _parse_date(o.get("appointed_on"))
            inc = r.get("incorporated")
            r["appointed_at_incorporation"] = bool(
                app and inc and abs((app - inc).days) <= 7)
        if want_psc and client.live:
            p = client.psc(num)
            n += 1
            if p is not None:
                live = [i for i in _items(p) if not i.get("ceased_on")]
                r["psc_checked"] = True
                r["psc_count"] = len(live)
                r["psc_names"] = [i.get("name") for i in live]
                r["psc_individual"] = any(
                    "individual" in (i.get("kind") or "") for i in live)
    DIAG["officers_enriched"] = sum(1 for r in recs if r.get("officers_checked"))
    return recs


# ============================================================================
# PART 5 - THE CLASSIFIER
# ============================================================================

def _normalise(c):
    """A Companies House advanced-search item -> the record we reason about."""
    ro = c.get("registered_office_address") or c.get("address") or {}
    name = c.get("company_name") or c.get("title") or ""
    inc = c.get("date_of_creation")
    inc = inc if isinstance(inc, date) else _parse_date(inc)
    return {
        "company_number": c.get("company_number"),
        "company_name": name,
        "incorporated": inc,
        "sic_codes": c.get("sic_codes") or [],
        "status": (c.get("company_status") or "").lower(),
        "reg_office": ro,
        "addr_key": _addr_key(ro),
        "officers_checked": False,
        "psc_checked": False,
    }


def classify_incorporations(companies, client=None, want_psc=True, enrich_limit=None):
    """Split new incorporations into REAL new operators vs artefacts.

    companies: raw Companies House advanced-search items (or the normalised dicts).
    client:    an optional targets.CHClient. WITHOUT one this runs the zero-cost pass
               only - names, addresses, SIC, clustering - and far more rows land in
               "unknown". That is not a bug, it is the honest cost of not looking.

    Returns {"real": [...], "personal_service": [...], "spv_franchise": [...],
             "unknown": [...], "diag": {...}}
    A term's T2 count should be based on REAL only.
    """
    recs = [_normalise(c) for c in (companies or [])]
    recs = [r for r in recs if r["company_name"]]

    if client is not None and getattr(client, "live", False):
        enrich_officers(client, recs, want_psc=want_psc, limit=enrich_limit)

    # -- clustering: reuse targets.economic_owners, do not reimplement -----------
    rows = [{
        "provider_id": r["company_number"] or ("X" + str(i)),
        "provider_name": r["company_name"],
        "sites": 1,
        "ch": {"status": "matched"},
        "ch_facts": {"director_keys": r.get("director_keys") or [],
                     "reg_office_key": r.get("addr_key")},
    } for i, r in enumerate(recs)]
    _pid2owner, owners, owner_diag = economic_owners(rows)
    assign, clusters = spv_clusters(recs, owners, owner_diag)

    out = {"real": [], "personal_service": [], "spv_franchise": [], "unknown": []}
    addr_counts = Counter(r["addr_key"] for r in recs if r.get("addr_key"))

    for r in recs:
        num = r["company_number"]
        why = []

        # ---- 1. SPV / franchise wins outright. It is a group fact, not a name fact.
        if num in assign:
            cl = next(c for c in clusters if c["cluster_id"] == assign[num])
            r["label"] = "spv_franchise"
            r["confidence"] = "high" if cl["route"] == "shared controller" else "medium"
            r["cluster_id"] = cl["cluster_id"]
            r["why"] = ["one of %d companies in the same batch: %s" % (cl["n"], cl["why"])]
            out["spv_franchise"].append(r)
            continue

        # ---- 2. gather the evidence
        strength, name_reason = person_name_signal(r["company_name"])
        if name_reason:
            why.append(name_reason)

        officer_surname = None
        if r.get("sole_director_name"):
            officer_surname = surname_in_name(r["company_name"], r["sole_director_name"])
            if officer_surname:
                strength = "strong"           # decisive: the owner IS the name
                why.append("sole director's surname '%s' is in the company name"
                           % officer_surname)
            elif strength == "weak":
                # The name looks like a person, but a DIFFERENT person runs it. That
                # makes the name a brand. Push back towards real.
                strength = None
                why.append("name looks personal, but the sole director's surname is not "
                           "in it - the name is a brand, not the owner")

        support = []
        if r.get("appointed_at_incorporation") and r.get("n_directors") == 1:
            support.append("sole director, appointed on the day of incorporation")
        if r.get("psc_checked") and r.get("psc_count") == 1 and r.get("n_directors") == 1:
            support.append("the one director is also the only person with significant "
                           "control - nobody else has any stake")
        generic, sic_reason = sic_signal(r["sic_codes"])
        if generic:
            support.append(sic_reason)
        addr_kind, addr_reason = address_signal(r["reg_office"])
        if addr_kind == "unclear" and addr_counts.get(r["addr_key"], 0) <= 2:
            support.append("registered office shows no business premises (weak)")

        r["support"] = support

        # ---- 3. decide. Conservative: the NAME signal is mandatory for a PSC call.
        #
        # A one-person company with a BRAND name is indistinguishable, at Companies
        # House, from a solo clinician opening a real clinic. We do not guess. It goes
        # to `real` if we looked at the officers, `unknown` if we did not.
        if strength == "strong" and (support or r.get("officers_checked")):
            r["label"] = "personal_service"
            r["confidence"] = "high" if officer_surname else "medium"
        elif strength == "strong":
            r["label"] = "personal_service"
            r["confidence"] = "low (name only - officers not checked)"
        elif strength == "weak" and len(support) >= 2:
            r["label"] = "personal_service"
            r["confidence"] = "medium"
        elif strength == "weak":
            r["label"] = "unknown"
            r["confidence"] = "name looks personal but nothing corroborates it"
        elif r.get("officers_checked"):
            r["label"] = "real"
            r["confidence"] = "medium (trading name, officers checked)"
            why.append("brand-style name, not part of a batch")
            if addr_kind == "business":
                r["confidence"] = "high (trading name + business premises)"
                why.append(addr_reason)
        else:
            r["label"] = "real"
            r["confidence"] = "low (name only - officers not checked)"
            why.append("brand-style name, but we did not look at the officers")

        r["why"] = why + (["also: " + s for s in support] if support else [])
        out[r["label"]].append(r)

    n = len(recs) or 1
    soft = [r for r in out["real"] if str(r.get("confidence", "")).startswith("low")]
    diag = {
        "n_companies": len(recs),
        "n_real": len(out["real"]),
        "n_personal_service": len(out["personal_service"]),
        "n_spv_franchise": len(out["spv_franchise"]),
        "n_unknown": len(out["unknown"]),
        "unknown_pct": round(100.0 * len(out["unknown"]) / n, 1),
        # THE HONEST ERROR BAR. "unknown" plus every "real" we only believe because of
        # its name. Both are rows we did not actually verify.
        "unverified_pct": round(100.0 * (len(out["unknown"]) + len(soft)) / n, 1),
        "real_name_only": len(soft),
        "officers_checked": sum(1 for r in recs if r.get("officers_checked")),
        "officers_checked_pct": round(
            100.0 * sum(1 for r in recs if r.get("officers_checked")) / n, 1),
        "clusters": clusters,
        "owner_dedupe": owner_diag,
    }
    out["diag"] = diag
    DIAG.update({k: v for k, v in diag.items() if k not in ("clusters", "owner_dedupe")})
    return out


# ============================================================================
# PART 6 - RE-WEIGHTING T2, and the confidence interval nobody put on it
# ============================================================================
#
# T2's growth number is a ratio of two SMALL COUNTS. "MSK/physio +123% (13 -> 29)" is
# 16 extra companies. Sixteen. That is one franchise rollout, exactly, and it is well
# inside the noise you would get from tossing coins.
#
# So adjust_t2 does two things, and the second matters as much as the first:
#   1. recomputes the count from REAL companies only;
#   2. attaches a Poisson interval, because a ratio of counts this small without an
#      interval is not a statistic, it is a rumour. With 13 and 29, the 95% band on
#      +123% runs from roughly +16% to +330%. Take five personal service companies out
#      of the 29 and the band crosses zero - the signal stops existing.
#
# HONEST DENOMINATOR WARNING. If you clean the RECENT window and not the PRIOR window,
# you are dividing a cleaned number by a dirty one, and the growth rate you get is
# meaningless (it is biased DOWN). Pass prior_result. If you do not, we still recompute
# the count, but g12 is set to None and the row is flagged, because a wrong number is
# worse than no number.


def _term_hits(name, term):
    """Does this company name contain the T2 term? Unigram or phrase, as pull_and_build
    emits them - a phrase must appear as CONSECUTIVE tokens, not scattered."""
    toks = _tokens(name)
    parts = (term or "").lower().split()
    if not parts or not toks:
        return False
    for i in range(len(toks) - len(parts) + 1):
        if toks[i:i + len(parts)] == parts:
            return True
    return False


def _real_counts(result):
    """{term-able company} -> we cannot know the terms in advance, so count on demand."""
    return [r["company_name"] for r in (result or {}).get("real", [])]


def poisson_ratio_ci(now, then, z=1.96):
    """95% interval on the growth rate of two counts. Log-ratio, Poisson variance.

    -> (low_pct, high_pct, significant). `significant` means the interval excludes zero
    growth, i.e. the rise survives the fact that these are counts of 13 and 29.
    """
    if not now or not then or now < 1 or then < 1:
        return None, None, False
    se = math.sqrt(1.0 / now + 1.0 / then)
    lr = math.log(float(now) / float(then))
    lo, hi = math.exp(lr - z * se), math.exp(lr + z * se)
    return (lo - 1.0) * 100.0, (hi - 1.0) * 100.0, lo > 1.0


def adjust_t2(rows, classifier_result, prior_result=None):
    """Re-weight the T2 rows so a niche's count reflects real new operators.

    rows: pull_and_build.incorporations()'s rows -
          {name, niche, latest, g12, isnew, ...}
    Returns a NEW list. Every row keeps its original numbers under `*_raw` so the
    dashboard can show what was taken away and why.
    """
    recent_names = _real_counts(classifier_result)
    prior_names = _real_counts(prior_result) if prior_result else None

    # what we removed, per term, and for what reason
    removed = {"personal_service": defaultdict(int), "spv_franchise": defaultdict(int),
               "unknown": defaultdict(int)}
    out = []
    for row in (rows or []):
        r = dict(row)
        term = r.get("name") or ""
        real_now = sum(1 for n in recent_names if _term_hits(n, term))

        for lab in ("personal_service", "spv_franchise", "unknown"):
            for rec in (classifier_result or {}).get(lab, []):
                if _term_hits(rec["company_name"], term):
                    removed[lab][term] += 1

        raw_now = r.get("latest")
        r["latest_raw"] = raw_now
        r["latest"] = real_now
        r["removed_personal_service"] = removed["personal_service"][term]
        r["removed_spv_franchise"] = removed["spv_franchise"][term]
        r["unclassified"] = removed["unknown"][term]
        total_seen = (real_now + r["removed_personal_service"]
                      + r["removed_spv_franchise"] + r["unclassified"])
        r["artefact_pct"] = round(
            100.0 * (r["removed_personal_service"] + r["removed_spv_franchise"])
            / total_seen, 1) if total_seen else None
        r["unknown_pct"] = round(
            100.0 * r["unclassified"] / total_seen, 1) if total_seen else None

        r["g12_raw"] = r.get("g12")
        if prior_names is not None:
            real_then = sum(1 for n in prior_names if _term_hits(n, term))
            r["prior_real"] = real_then
            if real_then >= 3:
                r["g12"] = (real_now / float(real_then) - 1.0) * 100.0
                lo, hi, sig = poisson_ratio_ci(real_now, real_then)
                r["g12_lo"], r["g12_hi"], r["significant"] = lo, hi, sig
            else:
                r["g12"] = None
                r["significant"] = False
                r["warn"] = "fewer than 3 real companies in the prior window - no rate"
        else:
            # cleaned numerator over a dirty denominator is not a growth rate.
            r["g12"] = None
            r["significant"] = False
            r["warn"] = ("prior window was NOT classified - growth rate withheld. "
                         "Classify both windows or show the count only.")

        if real_now < MIN_REAL_FOR_ROW:
            r["suppressed"] = True
            r["warn"] = ("only %d real new operators after artefacts removed - below the "
                         "floor of %d that pull_and_build already applies to raw counts"
                         % (real_now, MIN_REAL_FOR_ROW))
        out.append(r)

    out.sort(key=lambda x: (bool(x.get("significant")),
                            x.get("g12") if x.get("g12") is not None else -1e9,
                            x.get("latest") or 0), reverse=True)
    return out


# ============================================================================
# PART 7 - THE LIVE DIAGNOSIS. One run, one answer.
# ============================================================================
#
# Mirrors pull_and_build.HEALTH_SICS. NOT imported, because importing that module to
# read one constant would drag its whole pull with it. The selftest READS the file as
# text and fails if the two lists have drifted apart, which is the cheap half of the
# benefit with none of the coupling.
HEALTH_SICS = ["86900", "86220", "96020", "96040",
               "86210", "86230", "47730", "47782", "86101"]
CH_PAGE_SIZE = 1000


def _add_months(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def fetch_window(client, dfrom, dto, sics=None, max_pages=12):
    """Every company incorporated in [dfrom, dto) under the health SIC codes.

    Same endpoint, same shape and the same paging as pull_and_build's name_terms(), but
    it KEEPS THE COMPANIES instead of throwing them away and counting n-grams. That
    discard is the whole reason T2 cannot currently tell a clinic from an invoice.
    """
    seen, out = set(), []
    for sic in (sics or HEALTH_SICS):
        start = 0
        for _ in range(max_pages):
            path = ("/advanced-search/companies?sic_codes=%s&incorporated_from=%s"
                    "&incorporated_to=%s&size=%d&start_index=%d"
                    % (sic, dfrom, dto, CH_PAGE_SIZE, start))
            d = client.get(path)
            items = _items(d)
            if not items:
                break
            for it in items:
                num = it.get("company_number")
                if num and num not in seen:      # a company can carry several SIC codes
                    seen.add(num)
                    out.append(it)
            start += CH_PAGE_SIZE
            if len(items) < CH_PAGE_SIZE:
                break
    return out


def diagnose(term, budget=600, want_psc=True, anchor=None):
    """LIVE. Answers, definitively, whether a T2 term is real or an artefact.

    Reproduces T2's exact windows: the last 3 whole months against the same 3 months a
    year earlier - which is what pull_and_build.incorporations() compares.
    """
    anchor = anchor or date.today().replace(day=1)
    client = CHClient(budget=budget)
    if not client.live:
        print("NO CH_API_KEY - cannot diagnose. Set CH_API_KEY and re-run.")
        return None

    w_recent = (_add_months(anchor, -3).isoformat(), anchor.isoformat())
    w_prior = (_add_months(anchor, -15).isoformat(), _add_months(anchor, -12).isoformat())

    print("=" * 78)
    print("T2 DIAGNOSIS: %r" % term)
    print("  recent window %s -> %s" % w_recent)
    print("  prior  window %s -> %s   (T2's own comparison)" % w_prior)
    print("=" * 78)

    recent_all = fetch_window(client, *w_recent)
    prior_all = fetch_window(client, *w_prior)
    recent = [c for c in recent_all if _term_hits(c.get("company_name"), term)]
    prior = [c for c in prior_all if _term_hits(c.get("company_name"), term)]

    print("\nRAW (what the dashboard shows today):")
    print("  prior %d  ->  recent %d   = %s" % (
        len(prior), len(recent),
        "%+.0f%%" % ((len(recent) / len(prior) - 1) * 100) if prior else "n/a"))
    lo, hi, sig = poisson_ratio_ci(len(recent), len(prior))
    if lo is not None:
        print("  95%% interval on that: %+.0f%% to %+.0f%%   significant: %s"
              % (lo, hi, "YES" if sig else "NO - this rise is inside the noise"))
    print("\n  BASE RATE - all health-SIC incorporations, same windows: %d -> %d (%s)"
          % (len(prior_all), len(recent_all),
             "%+.0f%%" % ((len(recent_all) / len(prior_all) - 1) * 100)
             if prior_all else "n/a"))
    print("  (T2 has no control group. If EVERY health incorporation moved the same "
          "way,\n   the term did not rise - the register did.)")

    res = classify_incorporations(recent, client=client, want_psc=want_psc)
    pri = classify_incorporations(prior, client=client, want_psc=want_psc)
    d = res["diag"]

    print("\nTHE %d RECENT COMPANIES, ONE BY ONE:" % len(recent))
    print("-" * 78)
    for lab in ("personal_service", "spv_franchise", "unknown", "real"):
        for r in res[lab]:
            print("  [%-16s] %-42s %s" % (lab, (r["company_name"] or "")[:42],
                                          r.get("confidence")))
            for w in (r.get("why") or [])[:3]:
                print("      - %s" % w)
    print("-" * 78)
    print("  real %d | personal service %d | SPV/franchise %d | unknown %d"
          % (d["n_real"], d["n_personal_service"], d["n_spv_franchise"], d["n_unknown"]))
    print("  officers actually checked: %d%%   UNVERIFIED FRACTION: %d%%"
          % (d["officers_checked_pct"], d["unverified_pct"]))
    for cl in d["clusters"]:
        print("  CLUSTER %s (%d): %s" % (cl["cluster_id"], cl["n"], cl["why"]))

    rr, pr = len(res["real"]), len(pri["real"])
    print("\nCLEANED (real new operators only):")
    print("  prior %d  ->  recent %d   = %s" % (
        pr, rr, "%+.0f%%" % ((rr / pr - 1) * 100) if pr else "n/a"))
    lo, hi, sig = poisson_ratio_ci(rr, pr)
    if lo is not None:
        print("  95%% interval: %+.0f%% to %+.0f%%" % (lo, hi))
        print("\n  VERDICT: %s" % (
            "the rise SURVIVES cleaning and is outside the noise band." if sig else
            "the rise DOES NOT SURVIVE. Once artefacts are removed the interval "
            "includes zero:\n           there is no evidence this niche is rising."))
    else:
        print("\n  VERDICT: too few real companies in one window to compute a rate at "
              "all.\n           That is itself the answer - T2 cannot support a claim "
              "about this term.")
    print("\n  CH calls used: %d" % client.calls)
    return {"raw_recent": len(recent), "raw_prior": len(prior),
            "real_recent": rr, "real_prior": pr,
            "base_recent": len(recent_all), "base_prior": len(prior_all),
            "recent": res, "prior": pri, "calls": client.calls}


# ============================================================================
# PART 8 - SELFTEST. No network. Synthetic fixtures through the real code path.
# ============================================================================

_FAKE = {}          # "/company/NNN/officers" -> payload


def _fake_fetch(url):
    path = url.split("service.gov.uk", 1)[-1]
    return (200, _FAKE[path]) if path in _FAKE else (404, None)


def _co(num, name, inc, addr, sics=("86900",), directors=(), pscs=None):
    """Build one synthetic company + register its officers/PSC with the fake CH."""
    _FAKE["/company/%s/officers?items_per_page=100" % num] = {"items": [
        {"name": d[0], "officer_role": "director", "appointed_on": d[1],
         "date_of_birth": {"year": d[2], "month": d[3]}} for d in directors]}
    _FAKE["/company/%s/persons-with-significant-control?items_per_page=100" % num] = {
        "items": [{"name": p, "kind": "individual-person-with-significant-control"}
                  for p in (pscs if pscs is not None else [d[0] for d in directors])]}
    return {"company_number": num, "company_name": name, "date_of_creation": inc,
            "company_status": "active", "sic_codes": list(sics),
            "registered_office_address": addr}


def _client():
    return CHClient(key="TEST", budget=5000, fetch=_fake_fetch, sleep=lambda s: None)


def selftest():
    ok = [True]

    def check(label, cond, detail=""):
        print("  %-4s %s%s" % ("PASS" if cond else "FAIL", label,
                               ("  <- " + detail) if (detail and not cond) else ""))
        if not cond:
            ok[0] = False

    home = {"premises": "14", "address_line_1": "Elm Grove",
            "locality": "Leeds", "postal_code": "LS6 2AA"}
    biz = {"premises": "Unit 4", "address_line_1": "Kirkstall Business Park",
           "locality": "Leeds", "postal_code": "LS5 3BB"}

    print("\n[1] a person-named personal service company is CAUGHT")
    _FAKE.clear()
    cos = [
        _co("11000001", "J Smith Physiotherapy Ltd", "2026-05-04", home,
            directors=[("SMITH, John", "2026-05-04", 1988, 3)]),
        _co("11000002", "Sarah Jones Physio Ltd", "2026-05-11", home,
            directors=[("JONES, Sarah", "2026-05-11", 1991, 7)]),
        _co("11000003", "Dr A Patel Physiotherapy Limited", "2026-06-02", home,
            directors=[("PATEL, Anita", "2026-06-02", 1985, 9)]),
    ]
    r = classify_incorporations(cos, client=_client())
    caught = {c["company_name"] for c in r["personal_service"]}
    check("J Smith Physiotherapy Ltd", "J Smith Physiotherapy Ltd" in caught,
          "labels: %s" % {c["company_name"]: c["label"] for c in
                          r["real"] + r["unknown"] + r["personal_service"]})
    check("Sarah Jones Physio Ltd", "Sarah Jones Physio Ltd" in caught)
    check("Dr A Patel Physiotherapy Limited",
          "Dr A Patel Physiotherapy Limited" in caught)
    check("...and all three are high/medium confidence, not guesses",
          all(not str(c["confidence"]).startswith("low")
              for c in r["personal_service"]))

    print("\n[2] a real clinic is NOT caught")
    _FAKE.clear()
    cos = [
        _co("12000001", "The Movement Clinic Ltd", "2026-04-15", biz,
            sics=("86900", "93130"),
            directors=[("OKONKWO, Grace", "2026-04-15", 1984, 2),
                       ("HALL, Peter", "2026-04-20", 1979, 11)]),
        _co("12000002", "Northside Physiotherapy Centre Limited", "2026-05-02", biz,
            directors=[("BEGUM, Rukhsana", "2026-05-02", 1990, 6)]),
        # the hard one: a brand name, ONE director, generic SIC. A solo founder opening
        # a real clinic looks exactly like this, so it must NOT be called an artefact.
        _co("12000003", "Kinetic Rehab Studio Ltd", "2026-06-09", biz,
            directors=[("WRIGHT, Tom", "2026-06-09", 1993, 1)]),
        # and the trap: a person-LOOKING name whose director is somebody else entirely.
        _co("12000004", "Grace Harper Physio Ltd", "2026-06-20", biz,
            directors=[("NDLOVU, Blessing", "2026-06-20", 1986, 4)]),
    ]
    r = classify_incorporations(cos, client=_client())
    reals = {c["company_name"] for c in r["real"]}
    check("The Movement Clinic Ltd -> real", "The Movement Clinic Ltd" in reals)
    check("Northside Physiotherapy Centre Ltd -> real",
          "Northside Physiotherapy Centre Limited" in reals)
    check("Kinetic Rehab Studio Ltd (solo founder, brand name) -> real",
          "Kinetic Rehab Studio Ltd" in reals,
          "got %s" % [(c["company_name"], c["label"]) for c in
                      r["personal_service"] + r["unknown"]])
    check("Grace Harper Physio Ltd (name is a brand, not the director) -> real",
          "Grace Harper Physio Ltd" in reals)
    check("nothing was called a personal service company",
          not r["personal_service"], "%s" % [c["company_name"]
                                             for c in r["personal_service"]])

    print("\n[3] a 16-SPV franchise sharing one director is CAUGHT")
    _FAKE.clear()
    towns = ["Leeds", "Derby", "Bolton", "Exeter", "Norwich", "Ipswich", "Luton",
             "Swindon", "Preston", "Dudley", "Wigan", "Halifax", "Crewe", "Yeovil",
             "Telford", "Bangor"]
    hq = {"premises": "Suite 9", "address_line_1": "Franchise House",
          "locality": "Milton Keynes", "postal_code": "MK9 1AA"}
    cos = [_co("13%06d" % i, "%s Physio Ltd" % t, "2026-04-%02d" % (2 + i), hq,
               directors=[("BRANSON, Michael", "2026-04-%02d" % (2 + i), 1975, 5)])
           for i, t in enumerate(towns)]
    r = classify_incorporations(cos, client=_client())
    check("all 16 flagged spv_franchise", len(r["spv_franchise"]) == 16,
          "got %d spv, %d real, %d unknown" % (len(r["spv_franchise"]),
                                               len(r["real"]), len(r["unknown"])))
    check("zero of them counted as real new operators", len(r["real"]) == 0)

    print("\n[3b] ...and CAUGHT even with NO officer data (names + dates + address only)")
    r = classify_incorporations(cos, client=None)
    check("16 SPVs still flagged from the free pass alone",
          len(r["spv_franchise"]) == 16,
          "got %d - the formulaic-name + clustered-date route failed"
          % len(r["spv_franchise"]))

    print("\n[4] an accountant's address shared by 30 unrelated clinics does NOT merge")
    _FAKE.clear()
    acct = {"premises": "3rd Floor", "address_line_1": "Ledger House",
            "locality": "Manchester", "postal_code": "M1 4XY"}
    words = ["Apex", "Bramble", "Cedar", "Dovecote", "Elmwood", "Foxglove", "Granite",
             "Harbour", "Ivybridge", "Juniper", "Kestrel", "Larkspur", "Meridian",
             "Nightingale", "Orchard", "Pinnacle", "Quarry", "Redwood", "Saltaire",
             "Thistle", "Umber", "Verdant", "Willowbank", "Xenia", "Yarrow", "Zephyr",
             "Anchor", "Beacon", "Compass", "Drift"]
    tails = ["Physiotherapy Clinic Ltd", "Physio Centre Ltd", "Physiotherapy Practice Ltd",
             "Sports Physio Studio Ltd", "Physiotherapy Rehab Centre Ltd"]
    cos = []
    for i, w in enumerate(words):
        cos.append(_co("14%06d" % i, "%s %s" % (w, tails[i % len(tails)]),
                       "20%02d-%02d-1%d" % (21 + (i % 5), 1 + (i % 12), i % 10), acct,
                       directors=[("SURNAME%02d, Person%02d" % (i, i),
                                   "20%02d-%02d-1%d" % (21 + (i % 5), 1 + (i % 12), i % 10),
                                   1970 + i % 25, 1 + i % 12)]))
    r = classify_incorporations(cos, client=_client())
    check("none of the 30 flagged as an SPV batch", len(r["spv_franchise"]) == 0,
          "%d merged - the accountant guard leaked" % len(r["spv_franchise"]))
    check("all 30 survive as real new operators", len(r["real"]) == 30,
          "real=%d psc=%d unknown=%d" % (len(r["real"]), len(r["personal_service"]),
                                         len(r["unknown"])))

    print("\n[5] the honest error bar is reported, not hidden")
    _FAKE.clear()
    cos = [_co("15%06d" % i, n, "2026-0%d-0%d" % (2 + i, 1 + i),
               {"premises": str(10 + i), "address_line_1": "Road %d" % i,
                "postal_code": "AB%d 1CD" % i})
           for i, n in enumerate(["The Movement Clinic Ltd", "Kinetic Rehab Studio Ltd",
                                  "Northside Physiotherapy Centre Ltd",
                                  "Spinal Health Practice Ltd"])]
    r = classify_incorporations(cos, client=None)          # no officer data at all
    d = r["diag"]
    check("with no officer data, 100% of rows are flagged unverified",
          d["unverified_pct"] == 100.0, "got %s" % d["unverified_pct"])
    check("officers_checked_pct is 0 and says so", d["officers_checked_pct"] == 0.0)

    print("\n[6] the arithmetic")
    lo, hi, sig = poisson_ratio_ci(29, 13)
    check("13 -> 29 (+123%%) is only just significant: band %+.0f%% .. %+.0f%%"
          % (lo, hi), sig and lo < 30, "lo=%.0f" % lo)
    lo2, hi2, sig2 = poisson_ratio_ci(24, 13)
    check("remove just 5 of the 29 and it STOPS being significant (%+.0f%% .. %+.0f%%)"
          % (lo2, hi2), not sig2)
    check("term matching finds a unigram", _term_hits("Leeds Physio Ltd", "physio"))
    check("term matching needs a phrase to be consecutive",
          _term_hits("Sports Injury Clinic Ltd", "sports injury")
          and not _term_hits("Sports Massage and Injury Ltd", "sports injury"))

    print("\n[7] adjust_t2 re-weights, and refuses to divide clean by dirty")
    _FAKE.clear()
    recent = [_co("16%06d" % i, n, "2026-05-05", biz) for i, n in enumerate(
        ["Apex Physio Clinic Ltd", "Beacon Physio Centre Ltd", "Cedar Physio Studio Ltd",
         "Drift Physio Practice Ltd", "J Smith Physio Ltd", "Dr R Kaur Physio Ltd"])]
    prior_cos = [_co("17%06d" % i, n, "2025-05-05", biz) for i, n in enumerate(
        ["Elm Physio Clinic Ltd", "Fern Physio Centre Ltd", "Gorse Physio Studio Ltd",
         "P Ahmed Physio Ltd"])]
    rec = classify_incorporations(recent, client=_client())
    pri = classify_incorporations(prior_cos, client=_client())
    rows = [{"name": "physio", "niche": "MSK / physio", "latest": 6, "g12": 50.0}]
    a = adjust_t2(rows, rec)[0]
    check("raw 6 -> real 4 (two person-named companies removed)",
          a["latest"] == 4 and a["removed_personal_service"] == 2,
          "latest=%s psc=%s" % (a["latest"], a["removed_personal_service"]))
    check("growth rate WITHHELD when the prior window was not classified",
          a["g12"] is None and "prior window was NOT classified" in a.get("warn", ""))
    b = adjust_t2(rows, rec, prior_result=pri)[0]
    check("with both windows classified: 3 -> 4, not 4 -> 6",
          b["latest"] == 4 and b["prior_real"] == 3,
          "latest=%s prior=%s" % (b["latest"], b.get("prior_real")))
    check("and it is NOT significant (%s)" % ("%+.0f%%" % b["g12"]),
          b["significant"] is False)

    print("\n[8] the SIC list has not drifted from pull_and_build")
    try:
        src = open(os.path.join(os.path.dirname(_HERE), "pull_and_build.py"),
                   encoding="utf-8", errors="replace").read()
        m = re.search(r"HEALTH_SICS\s*=\s*\[(.*?)\]", src, re.S)
        theirs = re.findall(r'"(\d+)"', m.group(1)) if m else []
        check("HEALTH_SICS matches pull_and_build (%d codes)" % len(theirs),
              theirs == HEALTH_SICS, "theirs=%s ours=%s" % (theirs, HEALTH_SICS))
    except Exception as e:
        check("could read pull_and_build.py to compare SIC codes", False, repr(e))

    print("\n%s" % ("ALL PASS" if ok[0] else "*** FAILURES ABOVE ***"))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--diagnose", metavar="TERM",
                    help='e.g. --diagnose "physio"')
    ap.add_argument("--budget", type=int, default=600)
    ap.add_argument("--json", metavar="PATH")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.diagnose:
        out = diagnose(a.diagnose, budget=a.budget)
        if out and a.json:
            slim = {k: v for k, v in out.items() if k not in ("recent", "prior")}
            slim["diag_recent"] = out["recent"]["diag"]
            slim["diag_prior"] = out["prior"]["diag"]
            json.dump(slim, open(a.json, "w"), indent=2, default=str)
        sys.exit(0 if out else 1)
    ap.print_help()
