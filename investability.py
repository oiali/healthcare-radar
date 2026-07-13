#!/usr/bin/env python3
"""
INVESTABILITY - is a rising niche actually a BUY-AND-BUILD target?

WHY THIS EXISTS
---------------
Every other tier of the radar answers "is this niche RISING?". None of them answers
"could you actually ROLL IT UP?". Those are different questions and the second one
kills most of the answers to the first. The screening rule this module implements is
the user's own, and it is deliberately NOT "how recurring is the revenue":

    rank roll-up niches by TARGET DENSITY + CONSOLIDATION HEADROOM.

  (a) TARGET DENSITY      - how many acquirable independent operators actually exist.
                            "Tongue-tie is +200%" is worthless if there are eleven
                            providers in the country. Growth cannot manufacture
                            targets. Density is the gate; everything else is a
                            tie-break.
  (b) CONSOLIDATION       - are those operators still mostly one-site owner-operators
      HEADROOM              (good: the runway is in front of you) or has somebody
                            already bought them into three big groups (bad: you are
                            late, and you are now bidding against the incumbent)?

STOCK, NOT FLOW. The rest of the dashboard counts NEW registrations in a time window
because it is measuring momentum. This module counts the ENTIRE ACTIVE POPULATION,
because density is a stock. A niche that registered 40 new clinics last year but only
has 45 in total is not a roll-up; a niche that registered 40 and has 2,000 is.

SOURCE - CQC "care directory with filters" (HSCA_Active_Locations.ods)
----------------------------------------------------------------------
Monthly ~24MB ODS, ~57k rows, one row per ACTIVE registered location. Discovered by
scraping https://www.cqc.org.uk/about-us/transparency/using-cqc-data for a link
matching HSCA_Active_Locations.ods (same discovery pull_and_build.py already uses in
production, so the regex is known-good). An .ods is a ZIP containing content.xml, so
zipfile + xml.etree parse it with the stdlib alone.

THE KEY INSIGHT, and the whole reason this module can exist at all: that file carries
BOTH a Location ID and a **Provider ID**. Provider = the legal entity that owns the
location. So for any niche we can compute, from one file, with no vendor data:

    locations, DISTINCT PROVIDERS, locations-per-provider, % single-site providers,
    top-5 provider share, and a Herfindahl index of ownership concentration.

Many providers each owning one site = fragmented = runway.
Five providers owning half the sites = consolidated = you are late.

COLUMN NAMES
------------
VERIFIED (these are load-bearing in pull_and_build.py, which runs daily against the
real file and works): the header row of the data sheet contains a cell exactly equal
to "location id"; "Location Name"; "Location HSCA start date"; "Location Type/Sector".
Also verified: the FIRST sheet is a README, not data - you must pick the sheet whose
header contains "location id", or you parse prose.

UNVERIFIED-BUT-DOCUMENTED: "Provider ID", "Provider Name", "Location Region",
"Location Local Authority". CQC's own description of the care-directory files lists
provider id / provider name / region / local authority as fields, and the task brief
states these exact spellings, but I could not open the 24MB binary myself to read the
header row (no network in this sandbox). So EVERY column here is resolved by fuzzy
match against the header, never by fixed index, and if Provider ID is missing the
module degrades to a locations-only answer with providers=None rather than crashing
or - much worse - silently reporting a wrong number.

SECTOR POLICY (explicit, because silently dropping sectors would be a lie)
-------------------------------------------------------------------------
Location Type/Sector values: "Social Care Org", "Primary Dental Care",
"Primary Medical Services", "Independent Healthcare Org", "NHS Healthcare
Organisation", "Independent Ambulance".

  EXCLUDED  Social Care Org       care homes / domiciliary care. A different asset
                                  class entirely - different regulator risk, different
                                  buyer universe, different multiples, mostly property
                                  plays. Including them would swamp the file (they are
                                  the single largest sector) and would make every
                                  niche look deeper than it is.
  EXCLUDED  NHS Healthcare Org    you cannot buy an NHS trust. Worse than useless:
                                  trusts own dozens of locations each, so leaving them
                                  in would make a niche look CONSOLIDATED when the
                                  concentration is entirely public-sector.
  KEPT      Independent Healthcare Org, Primary Dental Care, Primary Medical Services,
            Independent Ambulance.

Both exclusions are COUNTED and reported (DIAG["excluded_sectors"], and every niche
carries a per-sector location breakdown), so nothing disappears quietly.

Primary Medical Services is kept but flagged: those are overwhelmingly NHS-contracted
GP practices. They ARE bought and sold (partnership buy-ins, APMS), but it is a
different deal type with NHS contract consent baked into it. Check `by_sector` before
you believe a density number that is mostly PMS.

HONEST LIMITS - read investability_FINDINGS.md before you trust a number. The three
that matter: CQC cannot see non-registrable aesthetics (a botox-only clinic is not
CQC-registrable, so aesthetics is structurally undercounted here - that is what the
Companies House cross-check is for); a Provider ID is a LEGAL entity, not an economic
owner (a private-equity group holding twelve Ltd companies looks like twelve
independents); and matching a niche off the location's NAME only finds operators who
brand themselves by the niche.

Stdlib only: urllib, zipfile, xml.etree, re, os, json, base64, time, tempfile, shutil.
Self-test:  python3 investability.py --selftest    (builds a synthetic .ods, no network)
Live run:   python3 investability.py               (needs network; CH_API_KEY optional)
"""

import os
import re
import json
import time
import base64
import shutil
import zipfile
import tempfile
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date

# ------------------------------------------------------------------ constants
CQC_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}

NS_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
NS_TX = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"])}

# Diagnostics, same pattern as pull_and_build.DIAG. Populated on every call so a
# surprising number can always be traced back to the parse that produced it.
DIAG = {}

# --------------------------------------------------------------- sector policy
SECTOR_SOCIAL = "social care"          # matches "Social Care Org"
SECTOR_NHS = "nhs"                     # matches "NHS Healthcare Organisation"

# When a location's NAME yields no niche, fall back to CQC's own sector label - but
# ONLY where the sector label IS the niche. Primary Dental Care means "this is a
# dentist" with regulator-grade certainty, and roughly a third of dental practices are
# named after the dentist ("Mr A Patel"), which no keyword can catch. Without this,
# dental - the deepest and most obvious roll-up market in UK healthcare - would be
# undercounted by more than it is measured.
#
# Deliberately NOT done for Primary Medical Services -> "Private GP": those are NHS
# GP surgeries. Mapping them into the private-GP niche would invent a private-pay
# population that does not exist. Same reasoning for Independent Ambulance: it is a
# sector, not one of the taxonomy's niches.
SECTOR_NICHE_FALLBACK = {
    "primary dental care": "Dental / orthodontics",
}

# ------------------------------------------------ THE SURNAME LANDMINE (real bug)
# pull_and_build.niche_of does:  re.search(r"\b" + re.escape(key), text)
# There is a LEADING word boundary and NO TRAILING one, so every keyword is a PREFIX
# match. That is deliberate and correct for stems like "dermatolog" / "menopaus" /
# "psychiatr". It is a disaster for the SHORT WHOLE-WORD keys, because UK clinics are
# overwhelmingly named after their owner, and:
#
#     "brow"  (Aesthetics)  matches  BROWN, Browne, Browning, Brownlow   <- top-5 UK surname
#     "skin"  (Aesthetics)  matches  SKINNER
#     "lip"   (Aesthetics)  matches  Lipton, Lipscomb, Lipman
#     "lash"  (Aesthetics)  matches  Lashley
#     "mole"  (Dermatology) matches  Molesworth, MOLESEY  <- East/West Molesey, Surrey
#     "scan"  (Diagnostics) matches  Scanlon, Scanlan
#     "hair"  (Hair)        matches  Hairsine
#     "smile" (Dental)      matches  Smiley
#
# Verified against the live taxonomy: niche_of("Brown Dental Surgery") returns
# "Aesthetics / skin". Not dental. And because Aesthetics sits 7th in NICHES while
# Dental sits 15th and Eye 24th, first-match-wins means these collisions do not just
# add noise - they TRANSFER locations OUT of the niches below and INTO aesthetics.
#
# This barely matters to the rest of the dashboard, which shows raw n-grams from a few
# hundred NEW registrations and where a human reads the word "brown" and ignores it. It
# matters enormously HERE, because this module runs niche_of across ~40,000 location
# names and rolls them into one headline density number, with no n-gram for a human to
# sanity-check. So we strip the known offenders as WHOLE WORDS before calling niche_of.
#
# This is a MITIGATION, not the fix. The fix is one line in pull_and_build.NICHES:
# change "brow" -> "eyebrow", "lip" -> "lip filler", "mole" -> "mole check", and either
# accept or bound "skin"/"scan"/"hair". I was told not to touch that file, so this guard
# lives here and is reported. Set name_guard=False to see the unguarded numbers.
NAME_NOISE = frozenset("""
brown browne browning brownlee brownlow
skinner skinners
lipton lipscomb lipman lippitt
lashley
peel peele
molesworth molesey
scanlon scanlan
weightman
hairsine
smiley
""".split())

# ...but never strip when the name contains a genuine clinical phrase built from the
# same token. "Chemical Peel Studio" must stay in aesthetics even though "peel" is also
# a surname; "The Mole Clinic" is a real derm brand.
PROTECT_PHRASES = (
    "chemical peel", "skin peel", "lip filler", "lip augmentation", "lip enhancement",
    "brow lift", "eyebrow", "lash lift", "mole check", "mole clinic", "mole screening",
)

_NOISE_RE = re.compile(r"\b(" + "|".join(sorted(NAME_NOISE)) + r")\b", re.I)


def clean_name(name):
    """Strip surname/placename tokens that collide with short taxonomy keys."""
    t = (name or "")
    low = t.lower()
    if any(p in low for p in PROTECT_PHRASES):
        return t
    return _NOISE_RE.sub(" ", t)


# ----------------------------------------------------------------- THRESHOLDS
# All five numbers below are judgement calls. They are stated as constants, in one
# place, with the reasoning, so they can be argued with rather than reverse-engineered.
#
# MIN_TARGETS = 30 -- the density GATE. Reasoning, from the deal side, not the data
# side: a buy-and-build needs a platform plus ~8-12 bolt-ons to be worth the fund's
# time. Owner-managed healthcare businesses are mostly not for sale - the owner is a
# clinician in their forties who likes their job - so a realistic hit rate on
# approaches is on the order of 1 in 5, and a good chunk of any list is unbuyable
# anyway (too small, wrong city, no succession issue). Landing ~10 deals therefore
# needs a POOL in the high tens at absolute minimum. Below 30 independent operators
# nationally there is simply no acquirable population and the niche is not a roll-up,
# however fast it is growing. This is the tongue-tie test and it should fail things.
#
# THIN_TARGETS = 100 -- between 30 and 99 you can build something, but it is a
# regional platform with a handful of bolt-ons, not a national consolidation. Say so.
# Above 100 there is enough population to plan a multi-region buy-and-build.
#
# DEEP_TARGETS = 300 -- purely a scoring ceiling: past ~300 independents, extra density
# stops being the binding constraint (deal execution capacity does), so the density
# score saturates.
MIN_TARGETS = 30
THIN_TARGETS = 100
DEEP_TARGETS = 300

# INDIE_MAX_SITES = 3 -- what counts as an "acquirable independent". Not "exactly one
# site": a two- or three-site owner-operator is if anything a BETTER platform target
# than a single site (proven it can replicate). A provider holding four or more
# locations anywhere in the CQC universe is behaving like a group, not an
# owner-operator, and is a competitor/consolidator rather than a target. Measured on
# the provider's TOTAL locations across the whole file, not just this niche - otherwise
# a 60-site group with one clinic in your niche counts as an "independent single-site
# operator", which is exactly backwards.
INDIE_MAX_SITES = 3

# HHI on a 0-1 scale of provider shares of LOCATIONS. The 0.10 / 0.20 cuts are the
# conventional unconcentrated / moderately concentrated / highly concentrated bands
# (i.e. 1,000 and 2,000 on the 0-10,000 scale used in merger analysis). NOTE the
# current CMA Merger Assessment Guidelines (2021) reference the HHI but do NOT publish
# bright-line thresholds - the 1,000/2,000 cuts come from the older UK guidance and
# the equivalent US horizontal merger guidelines. So this is a CONVENTION, borrowed,
# and it is being used to RANK niches against each other, not as any kind of legal
# test. It is also computed on national site counts, not revenue share in a local
# catchment, which is what a competition authority would actually care about.
HHI_CONCENTRATED = 0.20
HHI_MODERATE = 0.10

# TOP5_* -- the cruder, more readable companion to HHI, and the one to trust if the two
# disagree, because it is robust to the long tail. If the five largest owners already
# hold 40%+ of the sites, the consolidation has happened and you are buying at the top
# or bidding against the people who did it. Under 20% the market is genuinely open.
TOP5_CONCENTRATED = 40.0
TOP5_MODERATE = 20.0

VERDICT_TOO_SMALL = "Too small to roll up"
VERDICT_THIN = "Thin - regional platform at best"
VERDICT_FRAGMENTED = "Fragmented - roll-up runway"
VERDICT_CONSOLIDATING = "Consolidating"
VERDICT_CONSOLIDATED = "Already consolidated"

# ------------------------------------------- Companies House cross-check terms
# WHY: CQC systematically cannot see whole niches. A clinic doing botox and dermal
# filler only is not carrying out a CQC-regulated activity and is therefore NOT
# CQC-registrable - so "Aesthetics / skin", the single biggest private-pay niche in the
# country, is close to invisible in the CQC file. Counting ACTIVE companies whose name
# contains a niche keyword, inside the health SIC codes, catches those operators.
#
# It is a crude proxy and it is a cross-check, never the density measure: a company is
# not a clinic (dormant-ish one-man Ltds, holding companies, and companies that never
# traded all count), and the keyword must appear in the registered NAME.
#
# Keys MUST match the niche labels in pull_and_build.NICHES exactly.
CH_TERMS = {
    "Weight loss / GLP-1":         ["weight loss", "weight management"],
    "ADHD":                        ["adhd"],
    "Menopause / HRT":             ["menopause"],
    "Men's health / TRT":          ["testosterone", "mens health"],
    "Hair restoration":            ["hair transplant", "hair clinic", "hair loss"],
    "Tongue-tie / lactation":      ["tongue tie", "lactation"],
    "Aesthetics / skin":           ["aesthetics", "aesthetic"],
    "Dermatology / acne":          ["dermatology", "skin clinic"],
    "MSK / physio":                ["physiotherapy", "chiropractic", "osteopathy"],
    "Mental health / psychiatry":  ["psychology", "psychiatry", "counselling"],
    "Sexual health / ED":          ["sexual health"],
    "Diagnostics / imaging":       ["diagnostic", "ultrasound", "imaging"],
    "Fertility / women's health":  ["fertility", "gynaecology"],
    "Sleep":                       ["sleep"],
    "Dental / orthodontics":       ["dental", "dentist", "orthodontic"],
    "Longevity / peptides / IV":   ["longevity", "wellness", "iv drip"],
    "Migraine":                    ["migraine"],
    "Bladder / continence":        ["urology", "continence"],
    "Osteoporosis / bone":         ["osteoporosis"],
    "Diabetes":                    ["diabetes"],
    "Allergy":                     ["allergy"],
    "Neurology":                   ["neurology"],
    "Audiology / hearing":         ["hearing", "audiology"],
    "Eye / optical":               ["optician", "optometry", "eye clinic"],
    "Private GP":                  ["private gp", "gp practice"],
}

CH_KEY = os.environ.get("CH_API_KEY", "").strip()
HEALTH_SICS = ["86900", "86220", "96020", "96040"]   # same set pull_and_build uses


# =========================================================== small utilities
def _get_text(url, timeout=45):
    try:
        req = urllib.request.Request(url, headers=BROWSER_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def _download(url, path, timeout=300):
    req = urllib.request.Request(url, headers=BROWSER_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    return path


def _parse_date(s):
    """CQC dates arrive as ISO (from office:date-value) or dd/mm/yyyy or 01/Mar/2024."""
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
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _add_months(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


# ================================================================ ODS parsing
def cqc_file_url():
    """Scrape CQC for the monthly HSCA_Active_Locations.ods. None if unreachable."""
    html = _get_text(CQC_PAGE)
    if not html:
        return None
    m = re.search(r'href="([^"]*HSCA_Active_Locations\.ods)"', html, re.I)
    if not m:
        return None
    u = m.group(1)
    return u if u.startswith("http") else "https://www.cqc.org.uk" + u


def ods_rows(path, max_cols=260):
    """Stream (sheet_name, [cell, ...]) out of an .ods without loading it all.

    An .ods is a ZIP whose content.xml holds every sheet. Three ODS quirks are handled
    here because all three will otherwise corrupt the parse silently:

      * number-columns-repeated: ODS run-length-encodes repeated cells. Trailing blanks
        are routinely written as one cell repeated 1024 (or 16384) times. Expanding
        that literally would allocate a 16k-wide row per row. Capped at max_cols.
      * covered-table-cell: the continuation cells of a merged range. They still OCCUPY
        a column, so they must be emitted as empty strings or every column to their
        right shifts left. Children are walked in document order for this reason -
        findall("table-cell") would drop them and silently misalign the row.
      * number-rows-repeated: same trick applied to whole rows. Capped, and blank rows
        are emitted once regardless.

    Date cells carry the machine-readable value in office:date-value; the text:p is
    whatever the locale rendered. Prefer the attribute.
    """
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
                    if v:
                        v = v[:10]
                    else:
                        v = " ".join("".join(p.itertext())
                                     for p in c.findall(NS_TX + "p")).strip()
                elif c.tag == NS_T + "covered-table-cell":
                    v = ""
                else:
                    continue
                try:
                    rep = int(c.get(NS_T + "number-columns-repeated") or 1)
                except ValueError:
                    rep = 1
                rep = max(1, min(rep, max_cols))
                for _ in range(rep):
                    row.append(v)
                    if len(row) >= max_cols:
                        break
                if len(row) >= max_cols:
                    break

            try:
                rrep = int(el.get(NS_T + "number-rows-repeated") or 1)
            except ValueError:
                rrep = 1
            # A repeated row is only ever real data if it has content; blank filler rows
            # get repeated tens of thousands of times and must not be materialised.
            rrep = 1 if not any(row) else max(1, min(rrep, 50))

            el.clear()
            for _ in range(rrep):
                yield sheet, row


def _resolve_columns(header):
    """Map header cells -> indices, BY NAME, never by position.

    Exact match first (so "provider id" cannot lose to some other column that merely
    contains both words), then an all-substrings-present fallback so a CQC rename like
    "Provider ID" -> "Provider Id (Deprecated)" still resolves.

    Returns {} if the mandatory Location Name column is absent.
    """
    low = [(c or "").strip().lower() for c in header]
    # Guard against a prose paragraph in the README sheet being mistaken for a header.
    short = [c if 0 < len(c) < 70 else "" for c in low]

    def exact(name):
        return short.index(name) if name in short else None

    def fuzzy(*subs):
        for j, c in enumerate(short):
            if c and all(s in c for s in subs):
                return j
        return None

    def find(name, *subs):
        j = exact(name)
        return j if j is not None else fuzzy(*subs)

    cols = {
        "loc_id":   find("location id", "location", "id"),
        "loc_name": find("location name", "location", "name"),
        "prov_id":  find("provider id", "provider", "id"),
        "prov_name": find("provider name", "provider", "name"),
        "sector":   find("location type/sector", "type", "sector"),
        "start":    find("location hsca start date", "hsca start date"),
        "region":   find("location region", "location", "region"),
        "la":       find("location local authority", "local authority"),
    }
    if cols["sector"] is None:
        cols["sector"] = fuzzy("sector")
    if cols["start"] is None:
        cols["start"] = fuzzy("start date")
    if cols["loc_name"] is None:
        return {}
    return cols


def _sector_class(raw):
    """acquirable | social_care | nhs. Unknown/blank is treated as acquirable and
    counted separately - dropping it would be a silent deletion, and in practice this
    bucket is ~0 rows."""
    t = (raw or "").strip().lower()
    if not t:
        return "unknown"
    if SECTOR_SOCIAL in t:
        return "social_care"
    if SECTOR_NHS in t:
        return "nhs"
    return "acquirable"


# ============================================================ CQC aggregation
def scan_cqc(niche_of, path, anchor=None, sector_fallback=True, name_guard=True):
    """One streaming pass over the whole active-location file.

    Returns (niches, provider_total, meta) or (None, None, None) if the data sheet
    cannot be found. `provider_total` is every retained provider's location count
    across the ENTIRE file - that is what makes the "is this an independent or a group"
    test meaningful across niches.
    """
    anchor = anchor or date.today()
    cutoff_12m = _add_months(anchor, -12)

    cols = None
    sheet_used = ""
    provider_total = Counter()
    excluded = Counter()
    seen = matched = unknown_sector = guarded = 0

    # niche -> aggregates
    niches = defaultdict(lambda: {
        "locations": 0,
        "prov_locs": Counter(),        # provider_id -> locations in THIS niche
        "prov_names": {},
        "by_sector": Counter(),
        "regions": Counter(),
        "new_12m": 0,
    })

    for sheet, row in ods_rows(path):
        if cols is None:
            # The first sheet is a README. The data sheet is the one whose header row
            # contains a cell exactly "location id".
            if "location id" not in [(c or "").strip().lower() for c in row]:
                continue
            cols = _resolve_columns(row)
            if not cols:
                DIAG["fatal"] = "header found but Location Name column missing"
                return None, None, None
            sheet_used = sheet
            DIAG["sheet"] = sheet
            DIAG["cols"] = dict(cols)
            DIAG["header_len"] = len(row)
            continue

        seen += 1
        i_name = cols["loc_name"]
        if len(row) <= i_name:
            continue

        sector_raw = (row[cols["sector"]]
                      if cols["sector"] is not None and len(row) > cols["sector"] else "")
        klass = _sector_class(sector_raw)
        if klass in ("social_care", "nhs"):
            excluded[sector_raw or klass] += 1
            continue
        if klass == "unknown":
            unknown_sector += 1

        name = row[i_name] or ""
        if not name.strip():
            continue

        # Provider ID is the ownership key. If CQC ever drops the column, prov_id is
        # None everywhere and the concentration stats come back as None rather than as
        # a confidently wrong "everything is fragmented".
        prov_id = (row[cols["prov_id"]]
                   if cols["prov_id"] is not None and len(row) > cols["prov_id"] else "")
        prov_id = (prov_id or "").strip() or None
        prov_name = (row[cols["prov_name"]]
                     if cols["prov_name"] is not None and len(row) > cols["prov_name"]
                     else "") or ""

        if prov_id:
            provider_total[prov_id] += 1

        # See NAME_NOISE. Without this, "Brown Dental Surgery" is an aesthetics clinic.
        lookup = name
        if name_guard:
            lookup = clean_name(name)
            if lookup != name:
                guarded += 1

        niche = niche_of(lookup)
        if niche is None and sector_fallback:
            niche = SECTOR_NICHE_FALLBACK.get((sector_raw or "").strip().lower())
        if niche is None:
            continue

        matched += 1
        a = niches[niche]
        a["locations"] += 1
        a["by_sector"][sector_raw or "(blank)"] += 1
        if prov_id:
            a["prov_locs"][prov_id] += 1
            if prov_name:
                a["prov_names"][prov_id] = prov_name.strip()
        if cols["region"] is not None and len(row) > cols["region"]:
            reg = (row[cols["region"]] or "").strip()
            if reg:
                a["regions"][reg] += 1
        if cols["start"] is not None and len(row) > cols["start"]:
            d = _parse_date(row[cols["start"]])
            if d and d >= cutoff_12m:
                a["new_12m"] += 1

    if cols is None:
        DIAG["fatal"] = "no sheet with a 'location id' header cell"
        return None, None, None

    meta = {
        "sheet": sheet_used,
        "rows_seen": seen,
        "rows_matched_to_a_niche": matched,
        "match_rate_pct": round(100.0 * matched / seen, 1) if seen else 0.0,
        "excluded_sectors": dict(excluded),
        "unknown_sector_rows": unknown_sector,
        "anchor": anchor.isoformat(),
        "sector_fallback": sector_fallback,
        "name_guard": name_guard,
        "names_rewritten_by_guard": guarded,
    }
    DIAG.update(meta)
    return niches, provider_total, meta


# ================================================================== the metrics
def _hhi(counts, total):
    """Herfindahl index of provider shares of locations, 0-1. Floor is 1/n (perfectly
    even), ceiling is 1.0 (one provider owns everything)."""
    if not total:
        return None
    return sum((c / total) ** 2 for c in counts)


def _verdict(indie, hhi, top5):
    """Density gates first, THEN concentration. Order is the whole argument.

    A niche that is too small is not rescued by being fragmented - eleven fragmented
    tongue-tie clinics are still eleven clinics. So the density gate runs first and is
    absolute. Only once there is a population worth the name does it matter whether
    somebody else has already bought it.
    """
    if indie is None:
        return VERDICT_TOO_SMALL, "no Provider ID column - ownership cannot be assessed"
    if indie < MIN_TARGETS:
        return (VERDICT_TOO_SMALL,
                "only %d independent operators nationally (need >=%d for a platform "
                "plus ~8-12 bolt-ons at a realistic hit rate)" % (indie, MIN_TARGETS))

    concentrated = (hhi is not None and hhi >= HHI_CONCENTRATED) or \
                   (top5 is not None and top5 >= TOP5_CONCENTRATED)
    if concentrated:
        return (VERDICT_CONSOLIDATED,
                "top-5 providers hold %.0f%% of locations (HHI %.2f) - the "
                "consolidation has already happened; you would be bidding against the "
                "people who did it" % (top5 or 0, hhi or 0))

    moderate = (hhi is not None and hhi >= HHI_MODERATE) or \
               (top5 is not None and top5 >= TOP5_MODERATE)
    if moderate:
        return (VERDICT_CONSOLIDATING,
                "top-5 hold %.0f%% (HHI %.2f) - groups are forming but %d independents "
                "remain; runway exists, competition for assets is real"
                % (top5 or 0, hhi or 0, indie))

    if indie < THIN_TARGETS:
        return (VERDICT_THIN,
                "fragmented (top-5 %.0f%%) but only %d independents - enough for a "
                "regional platform and a few bolt-ons, not a national consolidation"
                % (top5 or 0, indie))

    return (VERDICT_FRAGMENTED,
            "%d independent operators, top-5 hold only %.0f%% (HHI %.2f) - deep "
            "population, nobody has consolidated it" % (indie, top5 or 0, hhi or 0))


def _score(indie, hhi, top5):
    """0-100, purely for RANKING niches against each other on the user's rule:
    60% target density, 40% consolidation headroom. Density is weighted higher because
    it is the gate - and a niche that fails the gate scores 0 outright, so a thin niche
    can never out-rank a deep one on fragmentation alone."""
    if indie is None or indie < MIN_TARGETS:
        return 0
    density = 100.0 * min(1.0, indie / float(DEEP_TARGETS))
    # Headroom: full marks at zero concentration, zero marks at/above the "already
    # consolidated" cut. Take the WORSE of the two concentration reads.
    h_from_hhi = 1.0 - min(1.0, (hhi or 0) / HHI_CONCENTRATED)
    h_from_top5 = 1.0 - min(1.0, (top5 or 0) / TOP5_CONCENTRATED)
    headroom = 100.0 * min(h_from_hhi, h_from_top5)
    return int(round(0.6 * density + 0.4 * headroom))


def _metrics(agg, provider_total):
    loc = agg["locations"]
    pl = agg["prov_locs"]
    providers = len(pl) or None

    if not providers:
        # Locations exist but no Provider ID - report what we have, assert nothing.
        return {
            "locations": loc, "providers": None, "lpp": None,
            "single_site_pct": None, "top5_share": None, "hhi": None,
            "indie_providers": None, "indie_pct": None,
        }

    counts = sorted(pl.values(), reverse=True)
    top5 = 100.0 * sum(counts[:5]) / loc if loc else None
    single = sum(1 for c in counts if c == 1)

    # THE test that matters: is this provider an owner-operator or an arm of a group?
    # Judged on their site count across the WHOLE file, not just inside this niche.
    indie = sum(1 for p in pl if provider_total.get(p, 1) <= INDIE_MAX_SITES)

    return {
        "locations": loc,
        "providers": providers,
        "lpp": round(loc / providers, 2),
        "single_site_pct": round(100.0 * single / providers, 1),
        "top5_share": round(top5, 1) if top5 is not None else None,
        "hhi": round(_hhi(counts, loc), 4),
        "indie_providers": indie,
        "indie_pct": round(100.0 * indie / providers, 1),
    }


# ========================================================== Companies House
def _ch_hits(term, timeout=30):
    """Total ACTIVE companies in the health SIC codes whose name contains `term`.

    Reads the `hits` total, not the page of items, so it costs one request. sic_codes is
    passed as a repeated parameter; if the API ORs them we get a deduplicated total, and
    if it honours only the last we get an undercount - either way we never DOUBLE COUNT
    a company that carries two health SICs, which summing four separate calls would.
    Conservative by construction.
    """
    if not CH_KEY:
        return None
    q = ["company_name_includes=" + urllib.parse.quote(term),
         "company_status=active", "size=1"]
    q += ["sic_codes=" + s for s in HEALTH_SICS]
    url = ("https://api.company-information.service.gov.uk/advanced-search/companies?"
           + "&".join(q))
    auth = base64.b64encode((CH_KEY + ":").encode()).decode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": "Basic " + auth, "User-Agent": "healthcare-radar"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            h = d.get("hits")
            return int(h) if h is not None else None
        except Exception:
            time.sleep(1.5 * (attempt + 1))   # 429s are the common case; back off
    return None


def companies_for(niche):
    """(count, term_used). MAX across the niche's keywords, never the sum - "weight"
    and "weight loss" overlap, and summing them would invent operators."""
    best, best_term = None, None
    for term in CH_TERMS.get(niche, []):
        n = _ch_hits(term)
        time.sleep(0.25)                       # CH allows 600 req / 5 min
        if n is None:
            continue
        if best is None or n > best:
            best, best_term = n, term
    return best, best_term


# ======================================================================= main
def investability(niche_of, path=None, include_companies=True, sector_fallback=True,
                  name_guard=True, anchor=None):
    """niche_of(text) -> niche label or None  (passed in from pull_and_build)

    Returns {niche: {
        "locations": int,          # CQC active locations in this niche (stock)
        "providers": int,          # distinct CQC Provider IDs owning them
        "lpp": float,              # locations per provider
        "single_site_pct": float,  # % of those providers owning exactly 1 loc IN NICHE
        "top5_share": float,       # % of locations held by the 5 largest providers
        "hhi": float,              # Herfindahl of provider concentration, 0-1
        "companies": int|None,     # active Companies House cos matching (cross-check)
        "verdict": str,
        ... plus: indie_providers, indie_pct, why, score, by_sector, regions,
                  new_12m, top_providers, ch_term
    }}
    Returns None if the source cannot be reached.

    path: an already-downloaded .ods. pull_and_build.cqc() downloads the same file to
    <tmp>/cqc.ods on every run, so pass that path in and this module costs ZERO extra
    download. If path is None we look at $CQC_ODS_PATH, then <tmp>/cqc.ods, and only
    then scrape + download.
    """
    DIAG.clear()

    path = path or os.environ.get("CQC_ODS_PATH") or None
    if not path:
        cached = os.path.join(tempfile.gettempdir(), "cqc.ods")
        if os.path.exists(cached) and os.path.getsize(cached) > 1_000_000:
            path = cached
            DIAG["source"] = "reused " + cached
    if not path:
        url = cqc_file_url()
        DIAG["url"] = url or "CQC page fetch failed / link not found"
        if not url:
            return None
        # The filename carries the extract date: 01_July_2026_HSCA_Active_Locations.ods
        m = re.search(r"/(\d{2})_([A-Za-z]+)_(\d{4})_HSCA", url)
        if m and anchor is None:
            try:
                anchor = date(int(m.group(3)), MONTHS.get(m.group(2).lower(), 1),
                              int(m.group(1)))
            except ValueError:
                anchor = None
        path = os.path.join(tempfile.gettempdir(), "cqc.ods")
        try:
            _download(url, path)
            DIAG["bytes"] = os.path.getsize(path)
            DIAG["source"] = "downloaded " + url
        except Exception as e:
            DIAG["download_error"] = repr(e)[:200]
            return None

    try:
        niches, provider_total, _meta = scan_cqc(
            niche_of, path, anchor=anchor, sector_fallback=sector_fallback,
            name_guard=name_guard)
    except Exception as e:                      # a corrupt/renamed file must not take
        DIAG["parse_error"] = repr(e)[:200]     # the whole dashboard build down
        return None
    if niches is None:
        return None

    out = {}
    for niche, agg in niches.items():
        m = _metrics(agg, provider_total)
        verdict, why = _verdict(m["indie_providers"], m["hhi"], m["top5_share"])
        top = sorted(agg["prov_locs"].items(), key=lambda kv: -kv[1])[:5]
        m.update({
            "companies": None,
            "ch_term": None,
            "verdict": verdict,
            "why": why,
            "score": _score(m["indie_providers"], m["hhi"], m["top5_share"]),
            "by_sector": dict(agg["by_sector"]),
            "regions": len(agg["regions"]),
            "new_12m": agg["new_12m"],
            "top_providers": [
                {"name": agg["prov_names"].get(p, p),
                 "locations": c,
                 "total_locations": provider_total.get(p, c)} for p, c in top],
        })
        out[niche] = m

    # CH is a bolt-on. It must never be able to fail the whole module: any exception or
    # missing key just leaves companies=None, and the CQC answer stands on its own.
    if include_companies and CH_KEY:
        for niche in out:
            try:
                n, term = companies_for(niche)
                out[niche]["companies"] = n
                out[niche]["ch_term"] = term
            except Exception:
                pass
        DIAG["companies_house"] = "queried"
    else:
        DIAG["companies_house"] = "skipped (no CH_API_KEY)" if not CH_KEY else "skipped"

    return out


# ============================================================== SELF-TEST
# No network in the build sandbox, so the parser is proved against a synthetic .ods
# built here with zipfile + hand-written XML: README sheet FIRST (as in the real file),
# then HSCA_Active_Locations with the real column names, and every ODS booby-trap that
# can silently corrupt a row - repeated cells, a merged/covered cell, a repeated blank
# row, a 1000-wide trailing blank fill, a date carried in office:date-value, and text
# split across a nested text:span.
_CONTENT_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<office:document-content '
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'office:version="1.2"><office:body><office:spreadsheet>'
)
_CONTENT_TAIL = '</office:spreadsheet></office:body></office:document-content>'

REAL_HEADER = [
    "Location ID", "Location HSCA start date", "Location Name", "Location Type/Sector",
    "Location Inspection Directorate", "Location Primary Inspection Category",
    "Location Region", "Location Local Authority", "Location Postal Code",
    "Provider ID", "Provider Name", "Provider Type/Sector",
]


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _cell(v, kind="string"):
    if v is None or v == "":
        return '<table:table-cell/>'
    if kind == "date":
        return ('<table:table-cell office:value-type="date" office:date-value="%s">'
                '<text:p>%s</text:p></table:table-cell>' % (v, v))
    return ('<table:table-cell office:value-type="string"><text:p>%s</text:p>'
            '</table:table-cell>' % _esc(str(v)))


def _row(cells, trailing_blank_repeat=0, rows_repeated=0):
    attrs = ' table:number-rows-repeated="%d"' % rows_repeated if rows_repeated else ''
    body = "".join(cells)
    if trailing_blank_repeat:
        body += ('<table:table-cell table:number-columns-repeated="%d"/>'
                 % trailing_blank_repeat)
    return "<table:table-row%s>%s</table:table-row>" % (attrs, body)


def build_fixture(path):
    """Synthetic HSCA_Active_Locations.ods. Returns the list of logical data rows so a
    test can hand-check the aggregates."""
    today = date.today()
    recent = _add_months(today, -3).isoformat()      # inside the 12-month window
    old = _add_months(today, -60).isoformat()        # well outside it

    # (loc_id, start, loc_name, sector, region, prov_id, prov_name)
    D = [
        # --- Dental. Bigcorp is a 4-site group; five one-site owner-operators.
        ("L1", old,    "Bigcorp Dental Care Leeds",  "Primary Dental Care", "North East",  "P1", "Bigcorp Dental Ltd"),
        ("L2", old,    "Bigcorp Dental Care York",   "Primary Dental Care", "North East",  "P1", "Bigcorp Dental Ltd"),
        ("L3", recent, "Bigcorp Dental Care Hull",   "Primary Dental Care", "North East",  "P1", "Bigcorp Dental Ltd"),
        ("L4", recent, "Bigcorp Dental Care Ripon",  "Primary Dental Care", "North East",  "P1", "Bigcorp Dental Ltd"),
        ("L5", old,    "Smith Dental Practice",      "Primary Dental Care", "London",      "P2", "Smith Dental Ltd"),
        ("L6", old,    "Jones Dental Practice",      "Primary Dental Care", "London",      "P3", "Jones Dental Ltd"),
        ("L7", old,    "Brown Dental Surgery",       "Primary Dental Care", "South West",  "P4", "Brown Dental Ltd"),
        ("L8", old,    "Green Dental Surgery",       "Primary Dental Care", "South West",  "P5", "Green Dental Ltd"),
        ("L9", recent, "Grey Dental Surgery",        "Primary Dental Care", "Midlands",    "P6", "Grey Dental Ltd"),
        # Named after the dentist - no keyword can catch it. Only the sector fallback
        # finds it. With sector_fallback=False this row is NOT dental.
        ("L10", old,   "Mr A Patel",                 "Primary Dental Care", "London",      "P7", "A Patel"),

        # --- Aesthetics. Alpha also owns two non-niche sites, so its TOTAL is 4 and it
        # must NOT be scored as an independent even though it has 2 sites in the niche.
        ("L11", recent, "Alpha Aesthetics Clinic",   "Independent Healthcare Org", "London", "P8", "Alpha Aesthetics Ltd"),
        ("L12", recent, "Alpha Aesthetics Bristol",  "Independent Healthcare Org", "South West", "P8", "Alpha Aesthetics Ltd"),
        ("L13", old,    "Beta Skin Clinic",          "Independent Healthcare Org", "London", "P9", "Beta Skin Ltd"),

        # --- No niche in the name, not dental: only feeds provider_total. This is what
        # pushes Alpha's group total to 4.
        ("L14", old,    "Alpha House",               "Independent Healthcare Org", "London", "P8", "Alpha Aesthetics Ltd"),
        ("L15", old,    "Alpha Lodge",               "Independent Healthcare Org", "London", "P8", "Alpha Aesthetics Ltd"),
        ("L16", old,    "Riverside Medical Centre",  "Primary Medical Services", "London", "P10", "Riverside Partners"),

        # --- MUST BE EXCLUDED. Both carry "Dental" in the name on purpose: if the
        # sector filter is broken, dental counts go up and the test fails loudly.
        ("L17", old,    "Meadowview Dental Care Home", "Social Care Org", "London", "P11", "Meadowview Care Ltd"),
        ("L18", old,    "St Elsewhere Dental Hospital", "NHS Healthcare Organisation", "London", "P12", "St Elsewhere NHS Trust"),
    ]

    readme = "".join([
        _row([_cell("CQC care directory with filters")]),
        _row([_cell("This sheet is a README. It is NOT the data. "
                    "It contains no location id header.")]),
        _row([_cell("Contact: enquiries@cqc.org.uk")]),
        _row([]),
    ])

    # Header written with a merged/covered cell and a repeated blank in the middle of
    # the sheet body, to prove column alignment survives both.
    hdr = _row([_cell(h) for h in REAL_HEADER], trailing_blank_repeat=1000)

    body = [hdr]
    for i, (lid, start, name, sector, region, pid, pname) in enumerate(D):
        cells = [
            _cell(lid),
            _cell(start, "date"),                       # office:date-value path
            _cell(name),
            _cell(sector),
            _cell(""),                                  # Inspection Directorate: blank
            _cell(""),                                  # Primary Inspection Category
            _cell(region),
            _cell("LA " + region),
            _cell("AB1 2CD"),
            _cell(pid),
            _cell(pname),
            _cell(sector),
        ]
        if i == 0:
            # Merged-range continuation cell: occupies a column, holds nothing. If it
            # were dropped, every column after it would shift and Provider ID would
            # read a postcode.
            cells.insert(5, '<table:covered-table-cell/>')
            cells.pop(6)
        body.append(_row(cells, trailing_blank_repeat=3))
    body.append(_row([], rows_repeated=60000))          # blank filler row, repeated

    xml = (_CONTENT_HEAD
           + '<table:table table:name="README">' + readme + '</table:table>'
           + '<table:table table:name="HSCA_Active_Locations">' + "".join(body)
           + '</table:table>'
           + _CONTENT_TAIL)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("META-INF/manifest.xml",
                   '<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
                   'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"'
                   '/>')
        z.writestr("content.xml", xml)
    return D


# A cut-down stand-in for pull_and_build.niche_of, using the same first-match-wins
# keyword logic so the test exercises the real calling convention.
_TEST_NICHES = [
    ("Aesthetics / skin", ["aesthetic", "botox", "skin", "filler"]),
    ("Dental / orthodontics", ["dental", "dentist", "orthodont"]),
]


def _test_niche_of(text):
    t = (text or "").lower()
    for name, keys in _TEST_NICHES:
        for k in keys:
            if re.search(r"\b" + re.escape(k), t):
                return name
    return None


def selftest():
    tmp = tempfile.mkdtemp(prefix="invtest_")
    ods = os.path.join(tmp, "fixture.ods")
    build_fixture(ods)
    fails = []

    def chk(label, got, want):
        ok = (got == want)
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("  %s %-42s %s" % ("ok  " if ok else "FAIL", label, got))

    # ---- 1. parser: does it find the right SHEET and the right COLUMNS?
    print("\n[1] sheet + column resolution")
    hdr, sheet_of_hdr = None, None
    for sheet, row in ods_rows(ods):
        if "location id" in [(c or "").strip().lower() for c in row]:
            hdr, sheet_of_hdr = row, sheet
            break
    chk("data sheet selected", sheet_of_hdr, "HSCA_Active_Locations")
    cols = _resolve_columns(hdr)
    chk("Location ID col", cols["loc_id"], 0)
    chk("Location HSCA start date col", cols["start"], 1)
    chk("Location Name col", cols["loc_name"], 2)
    chk("Location Type/Sector col", cols["sector"], 3)
    chk("Location Region col", cols["region"], 6)
    chk("Provider ID col", cols["prov_id"], 9)
    chk("Provider Name col", cols["prov_name"], 10)
    # The 1000-wide blank fill must be capped, not materialised.
    chk("header row width capped", len(hdr) <= 260, True)

    # ---- 2. covered-table-cell alignment: row 1 must still read Provider ID "P1"
    print("\n[2] merged/covered cell does not shift columns")
    first = None
    started = False
    for sheet, row in ods_rows(ods):
        if not started:
            if "location id" in [(c or "").strip().lower() for c in row]:
                started = True
            continue
        first = row
        break
    chk("row1 Location ID", first[cols["loc_id"]], "L1")
    chk("row1 Provider ID", first[cols["prov_id"]], "P1")
    chk("row1 start date (office:date-value)",
        bool(_parse_date(first[cols["start"]])), True)

    # ---- 3. sector exclusions
    print("\n[3] sector policy")
    niches, ptot, meta = scan_cqc(_test_niche_of, ods, sector_fallback=True)
    chk("Social Care Org excluded", "Social Care Org" in meta["excluded_sectors"], True)
    chk("NHS excluded",
        "NHS Healthcare Organisation" in meta["excluded_sectors"], True)
    chk("excluded count", sum(meta["excluded_sectors"].values()), 2)
    chk("care home NOT counted as dental",
        all("Meadowview" not in p for p in niches["Dental / orthodontics"]["prov_names"].values()),
        True)

    # ---- 4. provider_total spans niches (Alpha: 2 aesthetics + 2 unmatched = 4)
    print("\n[4] provider totals are file-wide, not niche-wide")
    chk("P8 total locations", ptot["P8"], 4)
    chk("P1 total locations", ptot["P1"], 4)
    chk("P2 total locations", ptot["P2"], 1)
    chk("P11 (care home) absent from totals", "P11" not in ptot, True)
    chk("P12 (NHS trust) absent from totals", "P12" not in ptot, True)

    # ---- 5. the arithmetic, hand-computed, WITH the sector fallback on.
    # Dental = 10 locations / 7 providers: P1 x4, P2..P7 x1 each.
    #   lpp             = 10/7                       = 1.43
    #   single_site_pct = 6/7                        = 85.7
    #   top5_share      = (4+1+1+1+1)/10             = 80.0
    #   hhi             = (4/10)^2 + 6*(1/10)^2      = 0.16 + 0.06 = 0.22
    #   indie (<=3 sites group-wide) = P2..P7        = 6
    print("\n[5] metrics, sector_fallback=True (dental=10 locs, 7 providers)")
    d = _metrics(niches["Dental / orthodontics"], ptot)
    chk("locations", d["locations"], 10)
    chk("providers", d["providers"], 7)
    chk("lpp", d["lpp"], 1.43)
    chk("single_site_pct", d["single_site_pct"], 85.7)
    chk("top5_share", d["top5_share"], 80.0)
    chk("hhi", d["hhi"], 0.22)
    chk("indie_providers", d["indie_providers"], 6)
    chk("new_12m", niches["Dental / orthodontics"]["new_12m"], 3)
    chk("regions", len(niches["Dental / orthodontics"]["regions"]), 4)

    # Aesthetics: 3 locations, P8 x2 (group of 4 file-wide!), P9 x1.
    #   hhi = (2/3)^2 + (1/3)^2 = 0.4444 + 0.1111 = 0.5556
    #   indie = 1  <- P8 is NOT independent: 4 sites file-wide, despite 2 in-niche
    print("\n[6] a 2-site in-niche provider that is really a 4-site group")
    a = _metrics(niches["Aesthetics / skin"], ptot)
    chk("locations", a["locations"], 3)
    chk("providers", a["providers"], 2)
    chk("single_site_pct (in-niche)", a["single_site_pct"], 50.0)
    chk("hhi", a["hhi"], 0.5556)
    chk("indie_providers (group-wide test)", a["indie_providers"], 1)

    # ---- 7. sector fallback OFF: "Mr A Patel" drops out of dental.
    # Dental = 9 locations / 6 providers: P1 x4, P2..P6 x1.
    #   top5 = (4+1+1+1+1)/9 = 88.9 ; hhi = (4/9)^2 + 5*(1/9)^2 = 0.2593
    print("\n[7] metrics, sector_fallback=False (dental=9 locs, 6 providers)")
    n2, pt2, _ = scan_cqc(_test_niche_of, ods, sector_fallback=False)
    d2 = _metrics(n2["Dental / orthodontics"], pt2)
    chk("locations", d2["locations"], 9)
    chk("providers", d2["providers"], 6)
    chk("single_site_pct", d2["single_site_pct"], 83.3)
    chk("top5_share", d2["top5_share"], 88.9)
    chk("hhi", d2["hhi"], 0.2593)

    # ---- 8. verdicts. The fixture is deliberately tiny, so EVERY niche in it must be
    # rejected. If a 10-location fixture ever produced "roll-up runway", the gate is
    # broken - and that is the exact failure mode this whole module exists to prevent.
    print("\n[8] verdicts")
    vd, _ = _verdict(d["indie_providers"], d["hhi"], d["top5_share"])
    chk("tiny dental -> too small", vd, VERDICT_TOO_SMALL)
    chk("tiny dental scores 0", _score(d["indie_providers"], d["hhi"], d["top5_share"]), 0)

    # Synthetic populations, to prove each band is reachable and ordered correctly.
    chk("500 indies, top5 8%, hhi .02 -> runway",
        _verdict(500, 0.02, 8.0)[0], VERDICT_FRAGMENTED)
    chk("60 indies, top5 8% -> thin", _verdict(60, 0.02, 8.0)[0], VERDICT_THIN)
    chk("400 indies, top5 25% -> consolidating",
        _verdict(400, 0.05, 25.0)[0], VERDICT_CONSOLIDATING)
    chk("400 indies, top5 55% -> already consolidated",
        _verdict(400, 0.09, 55.0)[0], VERDICT_CONSOLIDATED)
    chk("400 indies, hhi .30 -> already consolidated (hhi alone triggers)",
        _verdict(400, 0.30, 10.0)[0], VERDICT_CONSOLIDATED)
    chk("29 indies, perfectly fragmented -> STILL too small",
        _verdict(29, 0.0, 0.0)[0], VERDICT_TOO_SMALL)
    chk("no provider column -> too small, not a guess",
        _verdict(None, None, None)[0], VERDICT_TOO_SMALL)

    s_deep = _score(400, 0.02, 8.0)
    s_thin = _score(40, 0.0, 0.0)
    s_cons = _score(400, 0.19, 39.0)
    chk("deep+fragmented beats thin+perfect", s_deep > s_thin, True)
    chk("deep+fragmented beats deep+consolidated", s_deep > s_cons, True)
    chk("all scores in 0..100",
        all(0 <= s <= 100 for s in (s_deep, s_thin, s_cons)), True)

    # ---- 10. end-to-end through the public entry point, no network.
    print("\n[10] investability() end-to-end on the fixture")
    res = investability(_test_niche_of, path=ods, include_companies=False)
    chk("returns a dict", isinstance(res, dict), True)
    chk("niches found", sorted(res), ["Aesthetics / skin", "Dental / orthodontics"])
    r = res["Dental / orthodontics"]
    for k in ("locations", "providers", "lpp", "single_site_pct", "top5_share", "hhi",
              "companies", "verdict"):
        chk("key present: " + k, k in r, True)
    chk("companies is None without a key", r["companies"], None)
    chk("top provider named", r["top_providers"][0]["name"], "Bigcorp Dental Ltd")
    chk("top provider flagged as a 4-site group",
        r["top_providers"][0]["total_locations"], 4)
    chk("by_sector reported", r["by_sector"], {"Primary Dental Care": 10})

    # ---- 11. the surname landmine. This stub reproduces the LIVE taxonomy exactly:
    # prefix matching (leading \b only) and Aesthetics ordered ABOVE Dental. Without the
    # guard, "Brown Dental Surgery" and "Skinner ... Dental" are stolen into aesthetics.
    print("\n[11] surname guard (reproduces the real niche_of prefix bug)")
    real_order = [
        ("Aesthetics / skin", ["aesthetic", "botox", "skin", "lip", "brow", "peel"]),
        ("Dental / orthodontics", ["dental", "dentist", "orthodont"]),
    ]

    def buggy_niche_of(text):
        t = (text or "").lower()
        for nm, keys in real_order:
            for k in keys:
                if re.search(r"\b" + re.escape(k), t):     # NO trailing \b - the bug
                    return nm
        return None

    chk("unguarded: 'Brown Dental Surgery' -> aesthetics (the bug)",
        buggy_niche_of("Brown Dental Surgery"), "Aesthetics / skin")
    chk("guarded: 'Brown Dental Surgery' -> dental",
        buggy_niche_of(clean_name("Brown Dental Surgery")), "Dental / orthodontics")
    chk("guarded: 'Skinner & Partners Dental' -> dental",
        buggy_niche_of(clean_name("Skinner & Partners Dental Practice")),
        "Dental / orthodontics")
    chk("guarded: 'Lipscomb Opticians' -> no false aesthetics",
        buggy_niche_of(clean_name("Lipscomb Opticians")), None)
    # ...and the guard must NOT destroy genuine aesthetics names.
    chk("genuine 'Chemical Peel Studio' survives",
        buggy_niche_of(clean_name("Chemical Peel Studio")), "Aesthetics / skin")
    chk("genuine 'The Brow Bar' survives",
        buggy_niche_of(clean_name("The Brow Bar")), "Aesthetics / skin")
    chk("genuine 'Lip Filler Clinic' survives",
        buggy_niche_of(clean_name("Lip Filler Clinic")), "Aesthetics / skin")
    chk("genuine 'Skin Clinic' survives (only 'skinner' is noise, not 'skin')",
        buggy_niche_of(clean_name("Skin Clinic London")), "Aesthetics / skin")

    # End to end: the fixture's "Brown Dental Surgery" must land in DENTAL, not
    # aesthetics, once the guard is on.
    g_on = investability(buggy_niche_of, path=ods, include_companies=False,
                         name_guard=True)
    g_off = investability(buggy_niche_of, path=ods, include_companies=False,
                          name_guard=False)
    chk("guard ON  -> dental locations", g_on["Dental / orthodontics"]["locations"], 10)
    chk("guard OFF -> dental loses Brown", g_off["Dental / orthodontics"]["locations"], 9)
    chk("guard OFF -> aesthetics inflated",
        g_off["Aesthetics / skin"]["locations"] > g_on["Aesthetics / skin"]["locations"],
        True)

    # ---- 12. totality: garbage in must return None, never raise.
    print("\n[12] never crash")
    bad = os.path.join(tmp, "bad.ods")
    with open(bad, "wb") as f:
        f.write(b"this is not a zip file")
    chk("corrupt file -> None", investability(_test_niche_of, path=bad,
                                              include_companies=False), None)
    empty = os.path.join(tmp, "empty.ods")
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("content.xml", _CONTENT_HEAD
                   + '<table:table table:name="README">'
                   + _row([_cell("no data here")]) + '</table:table>' + _CONTENT_TAIL)
    chk("no data sheet -> None", investability(_test_niche_of, path=empty,
                                               include_companies=False), None)

    shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("\nSELFTEST FAILED (%d)\n  %s" % (len(fails), "\n  ".join(fails)))
        return False
    print("\nSELFTEST PASSED - all assertions green")
    return True


# ---------------------------------------------------------------------- CLI
def _print(res):
    print("%-28s %6s %6s %5s %7s %6s %6s %5s  %s" % (
        "niche", "locs", "provs", "lpp", "1site%", "top5%", "HHI", "score", "verdict"))
    for n, r in sorted(res.items(), key=lambda kv: -kv[1]["score"]):
        print("%-28s %6s %6s %5s %6s%% %5s%% %6s %5s  %s" % (
            n[:28], r["locations"], r["providers"] or "-", r["lpp"] or "-",
            r["single_site_pct"] or "-", r["top5_share"] or "-", r["hhi"] or "-",
            r["score"], r["verdict"]))
        print("%-28s   indies=%s  %s" % ("", r["indie_providers"], r["why"]))


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)
    try:
        from pull_and_build import niche_of as real_niche_of
    except Exception:
        real_niche_of = _test_niche_of
        print("(pull_and_build not importable - using the cut-down test taxonomy)")
    out = investability(real_niche_of)
    if out is None:
        print("investability: CQC source unreachable")
        print(json.dumps(DIAG, indent=1, default=str))
    else:
        _print(out)
        print("\nDIAG:", json.dumps(DIAG, indent=1, default=str))
