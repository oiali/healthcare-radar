#!/usr/bin/env python3
"""
TARGETS - the name list. Who could you actually BUY, and who might actually SELL.

WHY THIS EXISTS
---------------
Every other module on this radar answers a DEMAND question: is this niche rising, are
people searching for it, are GPs prescribing for it, are clinics registering. All of
that is one decision, made once: which niche.

The business is not one decision. It is ~200 decisions: which owner do I call on
Monday. And the binding constraint in a UK lower-mid-market roll-up has never been
sector selection - it is proprietary, off-market deal flow. Brokered assets are priced;
the money is in the clinic that was never listed, whose owner is 61 and has not thought
about it yet.

We were ALREADY HOLDING the list. investability.py streams the CQC active-locations
file - every registered location in England, with a Provider ID, a Provider Name, an
address and a registration date - computes summary statistics from it, and throws the
rows away. This module emits the rows.

    investability.py answers:  "is this niche fragmented?"          (one number)
    targets.py answers:        "here are the 240 people who own it" (a call list)

WHAT IT DOES
------------
  1. TARGET LIST. Every CQC provider in a niche owning <= max_sites locations
     file-wide. That is the acquirable population, by name, with postcode and how
     long they have been registered.

  2. OWNER DEDUPE. A Provider ID is a LEGAL entity, not an economic owner. A group
     holding twelve Ltd companies shows up in CQC as twelve independents - which means
     every fragmentation statistic on the dashboard FLATTERS investability, and it is
     exactly the number you would underwrite on. We fix this by pulling Companies House
     officers and registered offices for the providers on the list and grouping any
     that share a director (name + date of birth) or a registered office address.
     Providers that turn out to belong to a multi-entity group are flagged
     `independent: False` and pushed DOWN the list, not quietly counted as targets.

  3. SELLER-INTENT SCORE. Rank the acquirable population by how likely the owner is to
     be receptive in the next ~18 months. Ageing sole director, no visible successor,
     long-held single site, debt just cleared, a co-director who has walked, filings
     drifting. Every point of the score comes with a plain-English reason string, so
     the list defends itself: "sole director, 61; single site since 2009; charge
     satisfied Mar-2026; no officer under 45".

WHAT IT IS NOT
--------------
The seller-intent score is a PRIORITISATION HEURISTIC. It is not a prediction and it
has NO BACKTEST - we do not have a labelled set of UK clinic owners who did and did not
sell, so not one weight in it has been fitted to an outcome. It is a way of deciding who
to call first out of 240 names, and that is the entire claim. A score of 71 does not
mean a 71% chance of a sale. It means "call this one before the one on 34".

Read targets_FINDINGS.md before you trust any of it. The three that will bite:
name-matching CQC providers to Companies House by name has false positives; Companies
House publishes an officer's date of birth as MONTH AND YEAR only, so every "age 61" is
"61 or 62"; and the CQC "HSCA start date" is a re-registration date, not the date the
practice opened - dentists all re-registered in 2011 and GPs in 2013, so "years
registered" understates tenure for anyone older than the Health and Social Care Act.

STDLIB ONLY. No network in the build sandbox, so the parser, the dedupe and the scorer
are all proved against synthetic fixtures (a hand-built .ods, and a fake Companies House
that serves canned JSON through the same client code path the live one uses).

    python3 targets.py --selftest    builds fixtures, runs everything, no network
    python3 targets.py               live (needs network; CH_API_KEY for parts 2 & 3)
    python3 targets.py --niche "Dental / orthodontics" --csv out.csv
"""

import os
import re
import sys
import csv
import json
import time
import base64
import shutil
import zipfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict, deque
from datetime import date

# ---------------------------------------------------------------------- imports
# targets.py is designed to sit NEXT TO investability.py (radar-app/). It currently
# lives one level down in _agent2/, so both this directory and its parent go on the
# path. That way the same file works in place today and after it is moved up, and there
# is exactly ONE implementation of the ODS parser in the repo - this module deliberately
# does not re-implement it, because a second copy of a parser that handles
# covered-table-cells and number-columns-repeated is a second copy that can drift.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

DIAG = {}

try:
    from investability import (
        ods_rows, _resolve_columns, clean_name, _sector_class, _parse_date, _add_months,
        SECTOR_NICHE_FALLBACK, cqc_file_url, _download, MONTHS,
    )
    _INV_OK = True
except Exception as _e:                        # must never take the dashboard down
    _INV_OK = False
    DIAG["fatal_import"] = "investability.py not importable: %r" % (_e,)

CH_KEY = os.environ.get("CH_API_KEY", "").strip()
CH_BASE = "https://api.company-information.service.gov.uk"


# ============================================================================
# PART 0 - CQC: build the target list
# ============================================================================

# max_sites DEFAULT = 2. investability.py uses <=3 for "is this niche fragmented",
# which is the right cut for a POPULATION statistic. This is a CALL LIST, and the cut
# is deliberately tighter, because the two questions are different:
#
#   "how many independents exist"  -> be generous; a 3-site owner-operator is still
#                                     part of the fragmented tail you are counting.
#   "who do I ring on Monday"      -> be tight; a 3-site owner has usually built a
#                                     little group, has a manager layer, knows what an
#                                     EBITDA multiple is, and will run a process. The
#                                     1-2 site owner-operator is the off-market call.
#
# Both are exposed: max_sites is an argument. Raise it to 3 to reconcile with
# investability's indie_providers count.
DEFAULT_MAX_SITES = 2

# Site count is measured FILE-WIDE, across every niche and every kept sector - not
# within the niche. A 60-site group that happens to own one dermatology clinic is not
# a single-site dermatology independent, and counting it as one is exactly backwards.
# (Same rule investability.py applies, same reason.)


def _resolve_target_columns(header):
    """investability's resolver + the postcode column, which it does not need and we do.

    Postcode is load-bearing here for two reasons: it is how Omar decides whether a name
    is even worth a call (geography is the whole logic of a bolt-on), and it is a weak
    corroborator for the Companies House name match. Resolved by name, never by index,
    and preferring the LOCATION postcode over any provider postcode column.
    """
    cols = _resolve_columns(header)
    if not cols:
        return {}
    low = [(c or "").strip().lower() for c in header]
    short = [c if 0 < len(c) < 70 else "" for c in low]

    pc = None
    for want in ("location postal code", "location post code", "location postcode"):
        if want in short:
            pc = short.index(want)
            break
    if pc is None:                                    # prefer a LOCATION postcode col
        for j, c in enumerate(short):
            if c and "post" in c and "code" in c and "location" in c:
                pc = j
                break
    if pc is None:                                    # ...then any postcode column
        for j, c in enumerate(short):
            if c and ("postcode" in c or ("post" in c and "code" in c)):
                pc = j
                break
    cols["postcode"] = pc
    return cols


def _cell(row, cols, key):
    j = cols.get(key)
    if j is None or j >= len(row):
        return ""
    return (row[j] or "").strip()


def scan_providers(niche_of, path, niches=None, anchor=None,
                   sector_fallback=True, name_guard=True):
    """One streaming pass. Returns ({prov_id: provider}, meta) or (None, None).

    provider = {
      provider_id, provider_name,
      sites_total,            # locations file-wide, all niches, kept sectors only
      niches: {niche: [location, ...]},
      locations: [ {name, postcode, region, start (date|None), niche} ],
      first_registered,       # earliest HSCA start date across its locations
    }
    """
    anchor = anchor or date.today()
    cols = None
    provs = {}
    seen = matched = 0
    excluded = Counter()
    want = set(niches) if niches else None

    for _sheet, row in ods_rows(path):
        if cols is None:
            # The first sheet in the real file is a README. The data sheet is the one
            # whose header row carries a cell exactly equal to "location id".
            if "location id" not in [(c or "").strip().lower() for c in row]:
                continue
            cols = _resolve_target_columns(row)
            if not cols:
                DIAG["fatal"] = "header found but Location Name column missing"
                return None, None
            DIAG["cols"] = dict(cols)
            continue

        seen += 1
        name = _cell(row, cols, "loc_name")
        if not name:
            continue

        sector_raw = _cell(row, cols, "sector")
        klass = _sector_class(sector_raw)
        if klass in ("social_care", "nhs"):
            # Care homes are a different asset class; you cannot buy an NHS trust.
            # Same policy as investability.py, and it is COUNTED, not silently dropped.
            excluded[sector_raw or klass] += 1
            continue

        pid = _cell(row, cols, "prov_id")
        if not pid:
            continue                       # no ownership key -> cannot be a target row
        pname = _cell(row, cols, "prov_name")

        p = provs.get(pid)
        if p is None:
            p = provs[pid] = {
                "provider_id": pid, "provider_name": pname,
                "sites_total": 0, "locations": [], "niches": defaultdict(list),
                "first_registered": None,
            }
        if pname and not p["provider_name"]:
            p["provider_name"] = pname
        p["sites_total"] += 1              # counted BEFORE any niche filter, on purpose

        start = _parse_date(_cell(row, cols, "start"))
        if start and (p["first_registered"] is None or start < p["first_registered"]):
            p["first_registered"] = start

        lookup = clean_name(name) if name_guard else name
        niche = niche_of(lookup)
        if niche is None and sector_fallback:
            niche = SECTOR_NICHE_FALLBACK.get((sector_raw or "").strip().lower())
        if niche is None:
            continue
        if want and niche not in want:
            # Still counted in sites_total above - that is the point. A provider's group
            # size must not depend on which niche we happened to ask about.
            continue

        matched += 1
        loc = {"name": name, "postcode": _cell(row, cols, "postcode"),
               "region": _cell(row, cols, "region"), "start": start, "niche": niche}
        p["locations"].append(loc)
        p["niches"][niche].append(loc)

    if cols is None:
        DIAG["fatal"] = "no sheet with a 'location id' header cell"
        return None, None

    meta = {"rows_seen": seen, "rows_matched": matched,
            "providers_with_a_niche": sum(1 for p in provs.values() if p["niches"]),
            "excluded_sectors": dict(excluded), "anchor": anchor.isoformat()}
    DIAG.update(meta)
    return provs, meta


# ============================================================================
# PART 1 - Companies House client: throttled, budgeted, and unable to run away
# ============================================================================

# THE LIMIT IS 600 REQUESTS PER 5 MINUTES and blowing it gets the key rate-limited for
# everyone using it. Three independent guards, because one is not enough:
#
#   1. MIN_INTERVAL   - a floor on the gap between calls. 0.55s -> ~545 req/5min, i.e.
#                       we cannot exceed the limit even if every other guard is wrong.
#   2. SLIDING WINDOW - a hard count of calls in the last 300s. If we are within the
#                       safety margin (540 of 600) we sleep until the window drains.
#                       Belt and braces with (1), and it is what catches a burst.
#   3. RUN BUDGET     - a hard cap on TOTAL calls per run (default 300). This is the one
#                       that matters for the API bill and for the GitHub Actions runtime:
#                       it means a niche with 4,000 providers cannot turn a 6-minute
#                       build into a 90-minute one. When the budget runs out we simply
#                       stop enriching and return CQC-only rows, clearly marked.
#
# Plus a 429 circuit breaker: five consecutive 429s and we stop calling CH entirely for
# the rest of the run. If Companies House is telling us to go away, we go away.
CH_RATE_LIMIT = 600
CH_WINDOW_S = 300.0
CH_SAFETY = 540          # act as if the limit were 540, not 600
CH_MIN_INTERVAL = 0.55
CH_DEFAULT_BUDGET = int(os.environ.get("CH_BUDGET", "300") or 300)


def _real_fetch(url, key, timeout=25):
    """-> (status, json|None). Never raises. 404 is a normal answer, not an error."""
    auth = base64.b64encode((key + ":").encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": "Basic " + auth,
        "User-Agent": "healthcare-radar/targets",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            body = None
        return e.code, body
    except Exception:
        return 0, None                      # DNS/TLS/timeout: indistinguishable, and we
                                            # treat all of them the same way - give up.


class CHClient(object):
    """Companies House REST client. Throttled, budgeted, cached, and injectable.

    `fetch` is a seam, not decoration: the build sandbox has no network, so the
    self-test injects a fake that serves canned JSON through this exact code - the
    throttle, the budget, the cache, the 404 handling and the 429 breaker are all on the
    tested path. The only untested line in the whole module is the urlopen call itself.
    """

    def __init__(self, key=None, budget=CH_DEFAULT_BUDGET, fetch=None,
                 sleep=time.sleep, clock=time.monotonic):
        self.key = (key if key is not None else CH_KEY) or ""
        self.budget = int(budget)
        self.calls = 0
        self.cache = {}
        self.stats = Counter()
        self._times = deque()
        self._last = 0.0
        self._429s = 0
        self.blocked = False
        self.exhausted = False
        self._fetch = fetch or (lambda u: _real_fetch(u, self.key))
        self._sleep = sleep
        self._clock = clock

    @property
    def live(self):
        return bool(self.key) and not self.blocked and not self.exhausted

    def _throttle(self):
        now = self._clock()
        gap = CH_MIN_INTERVAL - (now - self._last)
        if gap > 0:
            self._sleep(gap)
            now = self._clock()
        while self._times and now - self._times[0] > CH_WINDOW_S:
            self._times.popleft()
        if len(self._times) >= CH_SAFETY:
            wait = CH_WINDOW_S - (now - self._times[0]) + 0.5
            self.stats["window_sleeps"] += 1
            self._sleep(max(0.0, wait))
            now = self._clock()
            while self._times and now - self._times[0] > CH_WINDOW_S:
                self._times.popleft()
        self._last = now
        self._times.append(now)

    def get(self, path):
        """GET an absolute path e.g. /company/12345678/officers -> dict, or None.

        None means: no key, budget spent, breaker tripped, 404, or a transport failure.
        Callers MUST treat None as 'unknown', never as 'no'. That distinction is the
        difference between "this company has no charges" and "we never asked".
        """
        if not self.key:
            self.stats["no_key"] += 1
            return None
        if self.blocked:
            self.stats["blocked"] += 1
            return None
        if self.calls >= self.budget:
            self.exhausted = True
            self.stats["budget_exhausted"] += 1
            return None
        if path in self.cache:
            self.stats["cache_hits"] += 1
            return self.cache[path]

        url = CH_BASE + path
        for attempt in range(3):
            self._throttle()
            self.calls += 1
            self.stats["http"] += 1
            try:
                status, body = self._fetch(url)
            except Exception:
                # _real_fetch cannot raise, but an injected/patched one might, and a
                # transport that throws must not take the build down.
                status, body = 0, None

            if status == 200:
                self._429s = 0
                self.cache[path] = body
                return body
            if status == 404:
                # A genuine, cacheable "no". /charges 404s for any company that has
                # never granted one - that is an ANSWER, and worth caching.
                self._429s = 0
                self.stats["404"] += 1
                self.cache[path] = None
                return None
            if status == 429:
                self._429s += 1
                self.stats["429"] += 1
                if self._429s >= 5:
                    # CH is telling us to stop. Stop. A retry storm here is how a key
                    # gets suspended, and the dashboard is worth less than the key.
                    self.blocked = True
                    self.stats["breaker_tripped"] += 1
                    return None
                self._sleep(min(30.0, 2.0 * (attempt + 1)))
                continue
            if status in (401, 403):
                # Bad key. Do not hammer - one is enough to know.
                self.blocked = True
                self.stats["auth_failed"] += 1
                return None
            self.stats["err_%s" % status] += 1
            self._sleep(1.0 * (attempt + 1))

        # DELIBERATELY NOT CACHED. A 429 or a timeout is a FAILURE, not an answer, and
        # caching it as None would freeze a transient error into a permanent "this
        # company has no officers" for the rest of the run - and would also hide the
        # repeat 429s from the circuit breaker, which is how the breaker fails to fire.
        return None

    # -- the five endpoints we use, each one call ---------------------------------
    def search(self, name):
        return self.get("/search/companies?q=%s&items_per_page=20"
                        % urllib.parse.quote(name))

    def profile(self, num):
        return self.get("/company/%s" % urllib.parse.quote(str(num)))

    def officers(self, num):
        return self.get("/company/%s/officers?items_per_page=100"
                        % urllib.parse.quote(str(num)))

    def charges(self, num):
        return self.get("/company/%s/charges?items_per_page=100"
                        % urllib.parse.quote(str(num)))

    def psc(self, num):
        return self.get("/company/%s/persons-with-significant-control"
                        "?items_per_page=100" % urllib.parse.quote(str(num)))


# ============================================================================
# PART 2 - name matching: the honest kind
# ============================================================================

# The CQC file gives a provider NAME. It does not give a company number. There is no
# official crosswalk. So we match by name, and the ONLY defensible way to do that at
# this scale is an exact match on a NORMALISED string, with everything ambiguous thrown
# away rather than guessed.
#
# Normalisation strips ONLY what Companies House itself treats as noise for its "same
# as" name rule: legal-form suffixes, punctuation, "the", and &/and. It deliberately
# does NOT strip disambiguators like "(UK)" or a trailing number, because
# "Smile Dental (UK) Ltd" and "Smile Dental Ltd" are two different companies and
# collapsing them is precisely the false positive that would put the wrong owner's name
# on a call list.
#
# Result is one of:
#   matched     exactly one ACTIVE company whose normalised name equals the provider's
#   ambiguous   more than one - we do not pick. Two real companies, one real owner,
#               50/50, and a coin flip here means calling a stranger about their
#               retirement. Left for a human.
#   unmatched   zero. Overwhelmingly this means the provider is a SOLE TRADER, an NHS
#               partnership or an individual ("Dr A Patel", "Smith & Jones") - which is
#               not a failure of the matcher, it is a true fact about the target: they
#               have no company, so there is no Companies House signal to be had. It is
#               NOT a reason to drop them from the list; a sole trader dentist is an
#               excellent target. It just means their score is structural only.
_SUFFIXES = (
    "limited", "ltd", "limted", "public limited company", "plc", "p l c",
    "llp", "limited liability partnership", "lp",
    "cic", "community interest company", "cio",
    "company", "co", "incorporated", "inc",
)
_SUFFIX_RE = re.compile(
    r"\s+(" + "|".join(re.escape(s) for s in sorted(_SUFFIXES, key=len, reverse=True))
    + r")$")


def _items(payload):
    """Every list we read out of a Companies House response goes through here.

    A JSON API is an EXTERNAL INPUT and must be treated like one. If `items` comes back
    as a string, iterating it yields characters and the first `.get()` throws - which is
    exactly the bug the fixtures caught. This is the only place that knows the shape, and
    anything that is not a list of dicts becomes an empty list.
    """
    if not isinstance(payload, dict):
        return []
    it = payload.get("items")
    if not isinstance(it, list):
        return []
    return [x for x in it if isinstance(x, dict)]


def norm_name(name):
    t = (name or "").strip().lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[\.\,\'\"`’]", "", t)          # punctuation that carries no meaning
    t = re.sub(r"[^a-z0-9\(\)]+", " ", t)            # keep parens: "(uk)" disambiguates
    t = re.sub(r"^the\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    for _ in range(3):                               # "Foo Ltd Company" -> "foo"
        t2 = _SUFFIX_RE.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    return t


# A provider name that looks like a PERSON or a partnership will never match a company,
# and searching for it burns a request from a budget of 300. Skip it, and say why.
_PERSONAL_RE = re.compile(
    # NOTE the (\band\b|&) rather than \b(and|&): "&" is not a word character, so a \b
    # in front of it can never match after a space, and "Smith & Partners" would have
    # sailed through as a company - burning a search call and matching nothing.
    r"^(dr|mr|mrs|miss|ms|prof|professor)\b|(\band\b|&)\s+(partners|associates)\b"
    r"|\bpartnership\b|\bpractice\b$", re.I)
_CORPORATE_RE = re.compile(
    r"\b(limited|ltd|llp|plc|cic|c\.i\.c|group|holdings|healthcare|clinics?|"
    r"dental|medical|company)\b", re.I)


def looks_personal(name):
    """True if this is almost certainly a natural person / partnership, not a company."""
    t = (name or "").strip()
    if not t:
        return True
    if _CORPORATE_RE.search(t):
        return False
    if _PERSONAL_RE.search(t):
        return True
    # "A Patel", "J R Hartley" - initials + surname, no corporate token anywhere.
    return bool(re.match(r"^([A-Z]\.?\s+){1,3}[A-Z][a-z]+$", t))


def ch_match(client, provider_name, postcodes=()):
    """-> {status, company_number, company_name, confidence, note}

    Confidence is deliberately coarse and honest:
      high       exact normalised name AND the registered office postcode matches one of
                 the provider's CQC location postcodes. Two independent agreements.
      name-only  exact normalised name, nothing else corroborates it. This is the common
                 case and it is where the false positives live - a genuinely different
                 company that happens to have registered the same trading name in a
                 different town. Treat with suspicion before you dial.
    """
    if looks_personal(provider_name):
        return {"status": "unmatched", "company_number": None, "company_name": None,
                "confidence": None,
                "note": "provider name looks like an individual or partnership - "
                        "probably not incorporated, so no Companies House record exists"}

    want = norm_name(provider_name)
    if not want:
        return {"status": "unmatched", "company_number": None, "company_name": None,
                "confidence": None, "note": "empty provider name"}

    res = client.search(provider_name)
    if not res:
        return {"status": "unmatched", "company_number": None, "company_name": None,
                "confidence": None,
                "note": "Companies House not searched (no key / budget spent / no result)"}

    hits = []
    for it in _items(res):
        if norm_name(it.get("title")) != want:
            continue
        status = (it.get("company_status") or "").lower()
        if status and status != "active":
            continue                      # a dissolved company does not own a live clinic
        hits.append(it)

    if not hits:
        return {"status": "unmatched", "company_number": None, "company_name": None,
                "confidence": None,
                "note": "no ACTIVE company with this exact name - likely a sole trader, "
                        "a partnership, or trading under a different registered name"}
    if len(hits) > 1:
        return {"status": "ambiguous", "company_number": None, "company_name": None,
                "confidence": None,
                "note": "%d active companies share this exact name - not guessing; "
                        "resolve by hand before calling" % len(hits)}

    h = hits[0]
    num = h.get("company_number")
    addr = h.get("address") or {}
    pc = (addr.get("postal_code") or "").replace(" ", "").upper()
    mine = {(p or "").replace(" ", "").upper() for p in postcodes if p}
    high = bool(pc and pc in mine)
    return {
        "status": "matched", "company_number": num, "company_name": h.get("title"),
        "confidence": "high" if high else "name-only",
        "note": ("registered office postcode matches a CQC location postcode"
                 if high else
                 "matched on exact company NAME only - no second signal agrees. "
                 "Check the company is really this clinic before you dial."),
    }


# ============================================================================
# PART 3 - the Companies House facts we score on
# ============================================================================
def _dob_age(dob, anchor):
    """CH publishes an officer's date of birth as MONTH + YEAR only (deliberately - it
    is a fraud control). So every age here is +/- 1 year. Compute the LOWER bound: if
    they might be 61 or 62, we say 61. Under-claiming is the safe direction for a signal
    that is used to decide who to phone about their retirement."""
    if not isinstance(dob, dict):
        return None
    y, m = dob.get("year"), dob.get("month")
    try:
        y, m = int(y), int(m)
    except (TypeError, ValueError):
        return None
    if not (1900 < y < anchor.year) or not (1 <= m <= 12):
        return None
    age = anchor.year - y - (1 if anchor.month < m else 0)
    return age if 16 <= age <= 110 else None


_DIRECTOR_ROLES = ("director", "llp-member", "llp-designated-member",
                   "corporate-director", "corporate-llp-member")


def ch_facts(client, number, anchor, want_charges=True, want_psc=True):
    """Pull the profile / officers / charges / PSC we score on. 2-4 calls.

    Every field can be None, and None means "we did not or could not look", NOT "no".
    """
    f = {
        "company_number": number, "company_status": None, "incorporated": None,
        "reg_office": None, "reg_office_key": None,
        "accounts_overdue": None, "cs_overdue": None,
        "name_changed_recently": None,
        "directors": [], "director_keys": [], "n_active_directors": None,
        "sole_director": None, "oldest_director_age": None, "youngest_director_age": None,
        "resigned_24m": 0, "psc_count": None, "psc_ages": [],
        "charge_satisfied_recent": None, "charge_created_recent": None,
        "calls": 0, "partial": False,
    }

    prof = client.profile(number)
    f["calls"] += 1
    if not isinstance(prof, dict):
        f["partial"] = True
        return f

    f["company_status"] = prof.get("company_status")
    f["incorporated"] = _parse_date(prof.get("date_of_creation"))
    def sub(d, k):
        v = d.get(k) if isinstance(d, dict) else None
        return v if isinstance(v, dict) else {}

    ro = sub(prof, "registered_office_address")
    f["reg_office"] = ", ".join([str(ro.get(k)) for k in
                                 ("premises", "address_line_1", "address_line_2",
                                  "locality", "postal_code") if ro.get(k)])
    f["reg_office_key"] = _addr_key(ro)

    nxt = sub(sub(prof, "accounts"), "next_accounts")
    f["accounts_overdue"] = bool(nxt.get("overdue")) if "overdue" in nxt else None
    cs = sub(prof, "confirmation_statement")
    f["cs_overdue"] = bool(cs.get("overdue")) if "overdue" in cs else None

    prev = prof.get("previous_company_names")
    prev = [p for p in prev if isinstance(p, dict)] if isinstance(prev, list) else []
    cutoff = _add_months(anchor, -24)
    f["name_changed_recently"] = any(
        (_parse_date(p.get("ceased_on")) or date(1900, 1, 1)) >= cutoff for p in prev)

    offs = client.officers(number)
    f["calls"] += 1
    if offs is None:
        f["partial"] = True
    else:
        cutoff24 = _add_months(anchor, -24)
        active, ages = [], []
        for o in _items(offs):
            role = (o.get("officer_role") or "").lower()
            res = _parse_date(o.get("resigned_on"))
            if res:
                # A co-director walking out is a signal in its own right - the classic
                # two-partner practice where one has had enough. Count it, whatever the
                # role, but only recent ones.
                if res >= cutoff24 and role in _DIRECTOR_ROLES:
                    f["resigned_24m"] += 1
                continue
            if role not in _DIRECTOR_ROLES:
                continue                          # secretaries are not owners. Excluding
                                                  # them also kills a big dedupe false
                                                  # positive: the shared accountant who
                                                  # is company secretary to 200 clients.
            age = _dob_age(o.get("date_of_birth"), anchor)
            active.append({"name": o.get("name"), "age": age,
                           "appointed": _parse_date(o.get("appointed_on"))})
            if age is not None:
                ages.append(age)
            k = _officer_key(o)
            if k:
                f["director_keys"].append(k)
        f["directors"] = active
        f["n_active_directors"] = len(active)
        f["sole_director"] = (len(active) == 1)
        f["oldest_director_age"] = max(ages) if ages else None
        f["youngest_director_age"] = min(ages) if ages else None

    if want_psc:
        p = client.psc(number)
        f["calls"] += 1
        if p is None:
            f["partial"] = True
        else:
            items = [i for i in _items(p) if not i.get("ceased_on")]
            f["psc_count"] = len(items)
            f["psc_ages"] = [a for a in
                             (_dob_age(i.get("date_of_birth"), anchor) for i in items)
                             if a is not None]

    if want_charges:
        c = client.charges(number)
        f["calls"] += 1
        if c is None:
            # 404 on /charges is the NORMAL answer for a company that has never had one.
            # We cannot distinguish that from a failed call, so we record "unknown" and
            # the scorer gives it nothing either way. Absence of evidence, not evidence.
            f["partial"] = True
        else:
            c24 = _add_months(anchor, -24)
            c12 = _add_months(anchor, -12)
            sat = cre = False
            for it in _items(c):
                st = (it.get("status") or "").lower()
                sd = _parse_date(it.get("satisfied_on"))
                cd = _parse_date(it.get("created_on") or it.get("delivered_on"))
                if sd and sd >= c24 and ("satisf" in st):
                    sat = True
                    f["charge_satisfied_on"] = sd
                if cd and cd >= c12 and st == "outstanding":
                    cre = True
            f["charge_satisfied_recent"] = sat
            f["charge_created_recent"] = cre
    return f


def _addr_key(addr):
    """A registered office address, normalised into a comparison key.

    Deliberately built from premises + line 1 + postcode ONLY. Locality and county are
    noise ("London" vs "Greater London"), and line 2 is where "Floor 3" lives.
    """
    if not isinstance(addr, dict):
        return None
    pc = re.sub(r"[^A-Z0-9]", "", (addr.get("postal_code") or "").upper())
    l1 = re.sub(r"[^a-z0-9]+", " ",
                ((addr.get("premises") or "") + " " +
                 (addr.get("address_line_1") or "")).lower()).strip()
    if not pc and not l1:
        return None
    return (pc + "|" + l1).strip("|")


def _officer_key(o):
    """A director, identified strongly enough to link two companies.

    Name ALONE is not enough - there are hundreds of John Smiths and linking two clinics
    because both have a director called John Smith would fabricate a group. So the key is
    surname + first forename + date of birth (month+year). CH publishes DOB for every
    natural-person director appointed since 1 Oct 2015 and for essentially all live ones.
    If there is NO DOB (corporate directors, some legacy records) we return None and the
    officer is simply not used as a link. Missing a real link is a small error; inventing
    a fake one puts a real independent on the "PE-owned, skip" pile.
    """
    if not isinstance(o, dict):
        return None
    dob = o.get("date_of_birth")
    if not isinstance(dob, dict) or not dob.get("year") or not dob.get("month"):
        return None
    nm = (o.get("name") or "").strip().lower()
    if not nm:
        return None
    nm = re.sub(r"[^a-z, ]", "", nm)
    if "," in nm:                                     # CH format: "SMITH, John Andrew"
        sur, _, fore = nm.partition(",")
    else:
        parts = nm.split()
        sur, fore = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (nm, "")
    first = (fore.strip().split() or [""])[0]
    sur = sur.strip()
    if not sur:
        return None
    return "%s|%s|%s-%s" % (sur, first, dob.get("year"), dob.get("month"))


# ============================================================================
# PART 4 - OWNER DEDUPE. A Provider ID is a legal entity, not an economic owner.
# ============================================================================

# THE BUG THIS FIXES, stated plainly: a PE-backed group that holds twelve dental
# practices in twelve separate Ltd companies appears in CQC as TWELVE single-site
# independent providers. Every fragmentation statistic on this dashboard therefore
# flatters investability - single_site_pct too high, HHI too low, "roll-up runway" -
# and it is the number you would underwrite on. It is also the number that decides
# whether Omar spends a fortnight ringing twelve owners who all report to the same
# board and none of whom can sell him anything.
#
# We group providers into ECONOMIC OWNERS by two links:
#
#   DIRECTOR   two companies share a director (surname + forename + DOB month/year).
#              Strong. This is how the real groups look: one or two principals sitting
#              on every board.
#   ADDRESS    two companies share a registered office (premises + line 1 + postcode).
#              Weaker, and dangerous - see below.
#
# THE ACCOUNTANT PROBLEM, which is the reason this is not a naive union-find:
# thousands of unrelated small companies use their ACCOUNTANT'S or a formation agent's
# office as their registered office. Left alone, the address link would merge fifty
# independent dentists in Kent into one imaginary fifty-site group, and Omar would strike
# every one of them off his list. So an address is only allowed to LINK providers if
# fewer than MAX_ADDR_GROUP of them share it; above that it is treated as an agent's
# address, discarded as a link, and REPORTED (DIAG["agent_addresses"]) so the assumption
# is visible rather than buried.
#
# The same logic does not apply to directors: a person who is genuinely a director of
# nine clinic companies IS a nine-clinic group, and that is not a false positive, that is
# the finding. But we bound it anyway (MAX_DIR_GROUP) to catch a normalisation bug
# swallowing the file, and we report it rather than acting on it silently.
MAX_ADDR_GROUP = 4
MAX_DIR_GROUP = 25


class _UF(object):
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def economic_owners(rows, max_addr_group=MAX_ADDR_GROUP, max_dir_group=MAX_DIR_GROUP):
    """rows: [ {provider_id, provider_name, ch: {...}, sites, ...} ]
    -> ({provider_id: owner_id}, {owner_id: owner}, diag)

    An owner is a set of providers judged to share one economic controller. Providers
    with no Companies House match are ALWAYS their own owner - we have no evidence of a
    link, and "no evidence" must not become "no link is possible", so an unmatched
    provider is reported as `independent: True, independence_evidence: "unverified"`
    rather than as a verified independent. The difference matters: it is the honest
    version of "we could not check".
    """
    by_dir, by_addr = defaultdict(list), defaultdict(list)
    for r in rows:
        f = r.get("ch_facts") or {}
        pid = r["provider_id"]
        for k in (f.get("director_keys") or []):
            by_dir[k].append(pid)
        ak = f.get("reg_office_key")
        if ak:
            by_addr[ak].append(pid)

    uf = _UF()
    for r in rows:
        uf.find(r["provider_id"])

    links = defaultdict(set)                          # pid -> human-readable link reasons
    agent_addrs, mega_dirs = [], []

    for k, pids in by_dir.items():
        pids = sorted(set(pids))
        if len(pids) < 2:
            continue
        if len(pids) > max_dir_group:
            mega_dirs.append({"key": k, "providers": len(pids)})
            continue
        for p in pids[1:]:
            uf.union(pids[0], p)
        who = k.split("|")[0].title()
        for p in pids:
            links[p].add("shares director %s with %d other provider(s)"
                         % (who, len(pids) - 1))

    for k, pids in by_addr.items():
        pids = sorted(set(pids))
        if len(pids) < 2:
            continue
        if len(pids) > max_addr_group:
            # Almost certainly an accountant or a formation agent. Linking on it would
            # invent a group and destroy a page of genuine targets.
            agent_addrs.append({"key": k, "providers": len(pids)})
            continue
        for p in pids[1:]:
            uf.union(pids[0], p)
        for p in pids:
            links[p].add("shares registered office with %d other provider(s)"
                         % (len(pids) - 1))

    groups = defaultdict(list)
    for r in rows:
        groups[uf.find(r["provider_id"])].append(r)

    pid2owner, owners = {}, {}
    for root, members in groups.items():
        oid = "OWN-" + root
        sites = sum(m.get("sites") or 0 for m in members)
        matched = [m for m in members
                   if (m.get("ch") or {}).get("status") == "matched"]
        owners[oid] = {
            "owner_id": oid,
            "providers": [m["provider_id"] for m in members],
            "provider_names": [m["provider_name"] for m in members],
            "n_providers": len(members),
            "sites": sites,
            "is_group": len(members) > 1,
            "link_reasons": sorted({x for m in members
                                    for x in links.get(m["provider_id"], ())}),
            "ch_matched_entities": len(matched),
        }
        for m in members:
            pid2owner[m["provider_id"]] = oid

    diag = {
        "owners": len(owners),
        "multi_entity_owners": sum(1 for o in owners.values() if o["is_group"]),
        "providers_in_groups": sum(o["n_providers"] for o in owners.values()
                                   if o["is_group"]),
        "agent_addresses_ignored": agent_addrs,
        "mega_director_links_ignored": mega_dirs,
    }
    return pid2owner, owners, diag


# ============================================================================
# PART 5 - SELLER-INTENT SCORE
# ============================================================================
#
# WHAT THIS IS: a ranking heuristic, 0-100, for the order in which to make 240 phone
# calls. WHAT IT IS NOT: a probability, a prediction, or anything that has been tested
# against an outcome. There is no labelled dataset of UK clinic owners who did and did
# not sell within 18 months, so NOT ONE of the weights below has been fitted to
# anything. They are priors, argued from how owner-managed businesses in this country
# actually change hands, and they are written as constants in one place so they can be
# argued with rather than reverse-engineered. If Omar makes 100 calls and logs the
# outcomes, THAT is the dataset, and these numbers should be refitted to it and this
# comment deleted.
#
# THE MODEL, in one sentence: the overwhelming majority of owner-managed UK healthcare
# businesses are sold because of a LIFE EVENT, not a valuation - retirement, a partner
# leaving, ill health, boredom at 15 years in. So the score looks for the fingerprints
# of a life event, not for financial distress or growth.
#
# THE SIGNALS, and why each one is weighted where it is:
#
#  +22  DIRECTOR AGED 60+        The single strongest free signal in the file. There is
#  +14  DIRECTOR AGED 55-59      no internal market for a one-clinic company: the owner
#   +6  DIRECTOR AGED 50-54      cannot retire without selling, and the clock is not
#                                negotiable. 60+ scores highest because that is when the
#                                conversation stops being hypothetical. Under 50 scores
#                                nothing - not negative, just nothing.
#
#  +14  SOLE DIRECTOR            No partner to buy them out, no succession inside the
#                                business, and nobody to veto a sale. A sole director is
#                                also a person you can actually get on the phone. It
#                                stacks with age deliberately: "sole director, 61" is the
#                                archetype, and the two signals together are worth more
#                                than either apart.
#
#   +8  NO VISIBLE SUCCESSOR     No active director under 45, and no second individual
#                                PSC. Distinguishes the 61-year-old who has brought their
#                                associate onto the board (succession is handled; they
#                                will not sell to you) from the 61-year-old who has not
#                                (they have no exit but a trade sale).
#
#  +12  CHARGE SATISFIED <24m    A bank charge redeemed and not replaced. Owners clear
#                                debt to tidy the balance sheet before a sale, and any
#                                lender will require redemption at completion anyway. It
#                                is only +12 rather than +20 because the innocent
#                                explanation is just as common: the loan reached the end
#                                of its term. Suggestive, not probative.
#
#   +8  DIRECTOR RESIGNED <24m   A co-director has left. In a two-partner practice this
#                                is very often the first half of a break-up, and the
#                                remaining partner now owns a business they did not plan
#                                to own alone - which is one of the most reliable routes
#                                to an off-market sale there is.
#
#  +12  REGISTERED 15+ YEARS     Long tenure. Nothing left to prove, no growth story
#   +7  REGISTERED 10-14 YEARS   being written, and the owner is by definition older
#   +3  REGISTERED 7-9 YEARS     than when they started. See the HSCA caveat below: this
#                                signal is measured from Companies House incorporation
#                                where we have it, because the CQC date is a
#                                re-registration date and lies for anyone older than 2011.
#
#   +4  SINGLE SITE              One site is a lifestyle business, not a platform. The
#   +2  TWO OR THREE SITES       owner is a clinician, not a chief executive, and has no
#                                machine for absorbing a fourth site. Small weight: it is
#                                more a definition of the target than a signal of intent.
#
#   +6  ACCOUNTS OVERDUE         Filing discipline slipping. Weak and ambiguous - it can
#   +3  CONF. STATEMENT OVERDUE  mean a disengaged owner with one eye on the door, or it
#                                can mean a chaotic one who will be a nightmare in
#                                diligence. Kept because disengagement is real, weighted
#                                low because it is a coin flip which one you have got.
#
#   +3  NAME CHANGED <24m        Faintest signal here. Sometimes a pre-sale tidy-up.
#                                Usually just a rebrand. Included for completeness and
#                                weighted so it can never move a name up the list alone.
#
# NEGATIVE:
#  -25  PART OF A MULTI-ENTITY   The dedupe found this "independent" is one of several
#       ECONOMIC OWNER           companies under one controller. It is not an
#                                owner-operator; the seller would be a board, at a price,
#                                in a process. Heavily penalised rather than deleted,
#                                because a group of three might still sell - but it must
#                                never sit at the top of an off-market call list.
#  -10  REGISTERED < 3 YEARS     They just started. They are building, not exiting.
#   -8  SOLE DIRECTOR UNDER 40   A young owner with a young business. Cancels much of the
#                                sole-director credit, which otherwise rewards exactly the
#                                wrong person.
#   -6  NEW CHARGE <12m          Just borrowed money. You do not take on debt in the year
#                                you sell; you take it on to invest.
#
# Maximum attainable is ~92, not 100, and that is intentional: nothing in a public
# filing can tell you someone is definitely selling, so nothing should score like it can.
#
# THE CQC-ONLY CAP. A provider we could not match to Companies House (a sole trader, or
# a name that came back ambiguous) has only the structural signals available - tenure and
# site count. Those alone cap out at 16, and we cap such rows at 35 regardless. A row
# must never climb the list because we FAILED to look at it. Absence of evidence is not
# evidence of a motivated seller.
W_AGE_60, W_AGE_55, W_AGE_50 = 22, 14, 6
W_SOLE = 14
W_NO_SUCCESSOR = 8
W_CHARGE_SATISFIED = 12
W_RESIGNED = 8
W_YEARS_15, W_YEARS_10, W_YEARS_7 = 12, 7, 3
W_SINGLE_SITE, W_SMALL_GROUP = 4, 2
W_ACCOUNTS_OVERDUE, W_CS_OVERDUE = 6, 3
W_NAME_CHANGE = 3
P_GROUP = -25
P_NEW = -10
P_YOUNG_SOLE = -8
P_NEW_CHARGE = -6
CQC_ONLY_CAP = 35

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mon(d):
    return "%s-%d" % (_MONTH_ABBR[d.month - 1], d.year) if d else "?"


def structural_score(sites, years, anchor=None):
    """The part of the score that needs NO Companies House call. Runs for every provider
    in the file, and is what the enrichment budget is spent in priority order OF."""
    s, why = 0, []
    if years is not None:
        if years >= 15:
            s += W_YEARS_15
            why.append("registered %d years" % years)
        elif years >= 10:
            s += W_YEARS_10
            why.append("registered %d years" % years)
        elif years >= 7:
            s += W_YEARS_7
            why.append("registered %d years" % years)
        elif years < 3:
            s += P_NEW
            why.append("registered only %d year(s) - building, not exiting" % years)
    if sites == 1:
        s += W_SINGLE_SITE
        why.append("single site")
    elif sites and sites <= 3:
        s += W_SMALL_GROUP
        why.append("%d sites" % sites)
    return s, why


def seller_score(row, anchor):
    """-> (score 0-100, reasons [str], confidence str). Total; never raises."""
    f = row.get("ch_facts") or {}
    m = (row.get("ch") or {}).get("status")

    # Tenure: prefer Companies House incorporation over the CQC HSCA date.
    # WHY THIS MATTERS AND IS NOT A DETAIL: the Health and Social Care Act 2008 forced
    # every dental practice to register with CQC in 2011 and every GP practice in 2013.
    # So a practice trading since 1988 carries a CQC start date of 2011 and looks 15
    # years old when it is 38. Companies House incorporation is the better tenure proxy
    # wherever we have it, and where we do not, the CQC number is a FLOOR, not a
    # measurement. Both are reported.
    years = row.get("years_registered")
    inc = f.get("incorporated")
    if inc:
        yrs_ch = anchor.year - inc.year - (1 if (anchor.month, anchor.day) <
                                           (inc.month, inc.day) else 0)
        if yrs_ch >= 0:
            years = max(years or 0, yrs_ch)
            row["years_incorporated"] = yrs_ch

    score, why = structural_score(row.get("sites"), years, anchor)

    if m != "matched":
        note = {"ambiguous": "Companies House name is ambiguous - not scored on CH data",
                "unmatched": "no Companies House match (likely sole trader/partnership) "
                             "- structural signals only"}.get(
                    m, "Companies House not consulted - structural signals only")
        why.append(note)
        return max(0, min(CQC_ONLY_CAP, score)), why, "low (CQC only)"

    age = f.get("oldest_director_age")
    n_dir = f.get("n_active_directors")
    sole = bool(f.get("sole_director"))

    if age is not None:
        if age >= 60:
            score += W_AGE_60
        elif age >= 55:
            score += W_AGE_55
        elif age >= 50:
            score += W_AGE_50
        if age >= 50:
            why.append("%s director aged %d%s"
                       % ("sole" if sole else "oldest",
                          age, "+" if age >= 60 else ""))

    if sole:
        score += W_SOLE
        if age is None or age < 50:
            why.append("sole director")
        if age is not None and age < 40:
            score += P_YOUNG_SOLE
            why.append("...but only %d - unlikely to be exiting" % age)

    # No successor: nobody young on the board, and no second individual PSC to hand to.
    young = f.get("youngest_director_age")
    pscs = f.get("psc_count")
    if age is not None and age >= 50:
        no_young = (young is None or young >= 45)
        no_second_psc = (pscs is None or pscs <= 1)
        if no_young and no_second_psc and n_dir is not None and n_dir <= 2:
            score += W_NO_SUCCESSOR
            why.append("no director under 45 and no second PSC - no visible successor")

    if f.get("charge_satisfied_recent"):
        score += W_CHARGE_SATISFIED
        why.append("charge satisfied %s - debt cleared" % _mon(f.get("charge_satisfied_on")))
    if f.get("charge_created_recent"):
        score += P_NEW_CHARGE
        why.append("new charge registered in last 12m - just borrowed, likely investing")

    if f.get("resigned_24m"):
        score += W_RESIGNED
        why.append("%d director resignation(s) in last 24m" % f["resigned_24m"])

    if f.get("accounts_overdue"):
        score += W_ACCOUNTS_OVERDUE
        why.append("accounts overdue at Companies House")
    if f.get("cs_overdue"):
        score += W_CS_OVERDUE
        why.append("confirmation statement overdue")
    if f.get("name_changed_recently"):
        score += W_NAME_CHANGE
        why.append("company name changed in last 24m")

    if row.get("independent") is False:
        score += P_GROUP
        why.append("NOT INDEPENDENT - part of a %d-entity economic owner"
                   % (row.get("owner_entities") or 2))

    st = (f.get("company_status") or "").lower()
    if st and st != "active":
        why.append("Companies House status is '%s' - verify before contact" % st)
        score = min(score, 20)

    conf = "medium"
    if f.get("partial"):
        conf = "medium (partial CH data - budget or endpoint)"
    if (row.get("ch") or {}).get("confidence") == "name-only":
        conf = "medium (CH matched on name only)"
    if (row.get("ch") or {}).get("confidence") == "high":
        conf = "high (CH name + postcode agree)"
    return max(0, min(100, score)), why, conf


# ============================================================================
# PART 6 - the public entry point
# ============================================================================
def targets(niche_of, path=None, niches=None, max_sites=DEFAULT_MAX_SITES,
            ch=True, ch_budget=CH_DEFAULT_BUDGET, ch_client=None,
            anchor=None, sector_fallback=True, name_guard=True,
            per_niche_cap=None):
    """The call list.

    Returns {niche: [row, ...]}, each row sorted by seller_score DESC:

        provider_id, provider_name, location_name, postcode, region,
        sites, first_registered, years_registered,
        seller_score, seller_reasons: [str],
        + independent, economic_owner, owner_entities, ch (match record),
          score_confidence

    Returns {} - never None, never an exception - if the source cannot be read, so a
    caller can always do `for niche, rows in targets(...).items()`.

    path: an already-downloaded CQC .ods. pull_and_build.cqc() puts one at
    <tmp>/cqc.ods every run and investability() already reuses it, so passing that path
    costs ZERO extra bandwidth. Falls back to $CQC_ODS_PATH, then the cached temp file,
    then a fresh scrape + download.

    ch=False (or no CH_API_KEY) gives you PART 1 only: the target list, ranked on the
    structural signals. That is still the most useful screen on the dashboard, and it
    needs no key and no network beyond the file itself.
    """
    DIAG.clear()
    if not _INV_OK:
        DIAG["fatal"] = "investability.py not importable - targets.py needs its ODS parser"
        return {}

    anchor = anchor or date.today()

    # ---------------------------------------------------------------- the file
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
                    anchor = date(int(m.group(3)),
                                  MONTHS.get(m.group(2).lower(), 1), int(m.group(1)))
                except ValueError:
                    pass
            path = os.path.join(tempfile.gettempdir(), "cqc.ods")
            _download(url, path)
            DIAG["source"] = "downloaded " + url
        except Exception as e:
            DIAG["download_error"] = repr(e)[:200]
            return {}

    try:
        provs, meta = scan_providers(niche_of, path, niches=niches, anchor=anchor,
                                     sector_fallback=sector_fallback,
                                     name_guard=name_guard)
    except Exception as e:
        DIAG["parse_error"] = repr(e)[:200]      # a corrupt file must not take the whole
        return {}                                # dashboard build down with it
    if provs is None:
        return {}

    # ------------------------------------------------- the acquirable population
    # sites_total is FILE-WIDE. A 40-site group with one clinic in the niche is not a
    # single-site independent, and this is where that gets enforced.
    rows = []
    for p in provs.values():
        if not p["niches"]:
            continue
        if p["sites_total"] > max_sites:
            continue
        first = p["first_registered"]
        yrs = None
        if first:
            yrs = anchor.year - first.year - (1 if (anchor.month, anchor.day) <
                                              (first.month, first.day) else 0)
            yrs = max(0, yrs)
        pcs = [l["postcode"] for l in p["locations"] if l["postcode"]]
        base, base_why = structural_score(p["sites_total"], yrs, anchor)
        for niche, locs in p["niches"].items():
            rows.append({
                "provider_id": p["provider_id"],
                "provider_name": p["provider_name"] or p["provider_id"],
                "location_name": locs[0]["name"],
                "all_locations": [l["name"] for l in p["locations"]],
                "postcode": (locs[0]["postcode"] or (pcs[0] if pcs else "")),
                "postcodes": pcs,
                "region": locs[0]["region"],
                "sites": p["sites_total"],
                "first_registered": first.isoformat() if first else None,
                "years_registered": yrs,
                "niche": niche,
                "_prescreen": base,
                "_why": base_why,
                "independent": True,
                "independence_evidence": "unverified",
                "economic_owner": None,
                "owner_entities": 1,
                "ch": {"status": "not_checked", "company_number": None,
                       "company_name": None, "confidence": None,
                       "note": "Companies House not consulted"},
                "ch_facts": {},
            })

    DIAG["target_rows"] = len(rows)
    DIAG["max_sites"] = max_sites
    if not rows:
        return {}

    # ---------------------------------------------------------- Companies House
    client = ch_client or (CHClient(budget=ch_budget) if ch else None)
    if client is not None and client.key:
        _enrich(client, rows, anchor)
        pid2owner, owners, odiag = economic_owners(_unique_by_provider(rows))
        for r in rows:
            oid = pid2owner.get(r["provider_id"])
            if not oid:
                continue
            o = owners[oid]
            r["economic_owner"] = oid
            r["owner_entities"] = o["n_providers"]
            if o["is_group"]:
                r["independent"] = False
                r["independence_evidence"] = "; ".join(o["link_reasons"]) or "shared owner"
            elif (r["ch"] or {}).get("status") == "matched":
                # We looked at its officers and its registered office and found no link
                # to any other provider on this list. That is a real, if bounded, check.
                r["independence_evidence"] = \
                    "no shared director or registered office with any other target"
        DIAG["economic_owners"] = odiag
        DIAG["ch_calls"] = client.calls
        DIAG["ch_stats"] = dict(client.stats)
        DIAG["ch_budget"] = client.budget
        DIAG["ch_blocked"] = client.blocked
        DIAG["ch_exhausted"] = client.exhausted
        _ECON_OWNERS.clear()
        _ECON_OWNERS.update(owners)
    else:
        DIAG["companies_house"] = ("skipped (no CH_API_KEY)" if not CH_KEY
                                   else "skipped (ch=False)")
        _ECON_OWNERS.clear()

    # -------------------------------------------------------------------- score
    for r in rows:
        try:
            s, why, conf = seller_score(r, anchor)
        except Exception as e:                       # a weird CH payload must not kill
            s, why, conf = 0, ["scoring failed: %r" % (e,)], "none"
        r["seller_score"] = s
        r["seller_reasons"] = why
        r["score_confidence"] = conf
        r.pop("_prescreen", None)
        r.pop("_why", None)

    out = defaultdict(list)
    for r in rows:
        out[r["niche"]].append(r)
    for n in out:
        # Deterministic: score, then site count, then name. Never dependent on dict order,
        # because a call list that reshuffles itself every build is a call list nobody
        # trusts.
        out[n].sort(key=lambda r: (-r["seller_score"], r["sites"],
                                   r["provider_name"] or ""))
        if per_niche_cap:
            del out[n][per_niche_cap:]
    return dict(out)


_ECON_OWNERS = {}


def owners_report():
    """The economic-owner view of the last targets() call: which 'independents' were
    actually one owner wearing several hats."""
    return dict(_ECON_OWNERS)


def _unique_by_provider(rows):
    """rows are per (provider, niche); a provider in two niches is one legal entity and
    must be deduped ONCE, not twice."""
    seen, out = set(), []
    for r in rows:
        if r["provider_id"] in seen:
            continue
        seen.add(r["provider_id"])
        out.append(r)
    return out


def _enrich(client, rows, anchor):
    """Spend the CH budget where it buys the most, in two passes.

    A full enrichment is 4 calls (search, profile, officers, PSC) plus 1 for charges. At
    a 300-call budget that is 60 providers, and a dental niche has thousands. So:

      PASS A (70% of budget): search -> profile -> officers, in PRESCREEN order. These
        three calls buy the two highest-value facts in the whole model - who the
        directors are and how old they are - AND the two dedupe keys (director identity,
        registered office). Get this for as many providers as possible.
      PASS B (the rest): PSC and charges, for the providers that scored highest AFTER
        pass A. Charges and PSC only refine a name that is already near the top; spending
        them on a 28-year-old sole director with three years' tenure is a wasted call.

    This is the difference between knowing the age of 60 owners and knowing everything
    about 40. Age is the signal. Take the 60.
    """
    uniq = _unique_by_provider(rows)

    # Fair across niches: a niche with 4,000 dentists must not eat the entire budget and
    # leave the 40 sleep clinics unenriched. Round-robin by niche, in prescreen order.
    by_niche = defaultdict(list)
    for r in uniq:
        by_niche[r["niche"]].append(r)
    for n in by_niche:
        by_niche[n].sort(key=lambda r: -r["_prescreen"])
    queue, i = [], 0
    while True:
        added = False
        for n in sorted(by_niche):
            if i < len(by_niche[n]):
                queue.append(by_niche[n][i])
                added = True
        if not added:
            break
        i += 1

    pass_a_budget = int(client.budget * 0.70)
    enriched = []

    # ---- PASS A: identity + officers
    # Each provider is enriched inside its own try/except. One malformed payload for one
    # company must cost us THAT company's signals, not the entire call list.
    for r in queue:
        if not client.live or client.calls >= pass_a_budget:
            break
        try:
            r["ch"] = ch_match(client, r["provider_name"], r.get("postcodes") or ())
            if r["ch"]["status"] != "matched":
                continue
            r["ch_facts"] = ch_facts(client, r["ch"]["company_number"], anchor,
                                     want_charges=False, want_psc=False)
            enriched.append(r)
        except Exception as e:
            DIAG.setdefault("ch_row_errors", []).append(
                "%s: %r" % (r["provider_id"], e))
            r["ch"] = {"status": "error", "company_number": None, "company_name": None,
                       "confidence": None, "note": "Companies House lookup failed: %r" % e}
            r["ch_facts"] = {}

    DIAG["ch_pass_a"] = {"providers_searched": sum(
        1 for r in uniq if r["ch"]["status"] != "not_checked"),
        "matched": len(enriched), "calls": client.calls}

    # ---- PASS B: charges + PSC for the ones that now look interesting
    def _interim(r):
        try:
            return seller_score(r, anchor)[0]
        except Exception:
            return 0

    enriched.sort(key=lambda r: -_interim(r))
    done = 0
    for r in enriched:
        if not client.live:
            break
        try:
            num = r["ch"]["company_number"]
            extra = ch_facts(client, num, anchor, want_charges=True, want_psc=True)
            # ch_facts re-reads profile/officers from the CLIENT CACHE (0 extra HTTP), so
            # the only new calls here are charges + PSC. Merge, keeping what we had.
            for k, v in extra.items():
                if v not in (None, [], 0, False) or k not in r["ch_facts"]:
                    r["ch_facts"][k] = v
            done += 1
        except Exception as e:
            DIAG.setdefault("ch_row_errors", []).append(
                "%s (pass B): %r" % (r["provider_id"], e))
    DIAG["ch_pass_b"] = {"providers_deepened": done, "calls_total": client.calls}

    # Anything we never got to keeps status "not_checked" and is scored structurally.
    # It is NOT silently treated as "no signals found".
    for r in rows:
        if r["ch"]["status"] == "not_checked":
            continue
    # propagate the enrichment from the deduped row back onto every (provider, niche) row
    by_pid = {r["provider_id"]: r for r in uniq}
    for r in rows:
        src = by_pid.get(r["provider_id"])
        if src is not None and src is not r:
            r["ch"] = src["ch"]
            r["ch_facts"] = src["ch_facts"]


# ============================================================================
# FIXTURES + SELF-TEST. No network in the build sandbox, so everything is proved
# against synthetic data: a real-shaped .ods, and a fake Companies House.
# ============================================================================
_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>'
         '<office:document-content '
         'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
         'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
         'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
         'office:version="1.2"><office:body><office:spreadsheet>')
_TAIL = '</office:spreadsheet></office:body></office:document-content>'

# The REAL header, in the real order, with the real spellings - including
# "Location Postal Code", which is the one column targets.py needs and
# investability.py does not.
REAL_HEADER = [
    "Location ID", "Location HSCA start date", "Location Name", "Location Type/Sector",
    "Location Inspection Directorate", "Location Primary Inspection Category",
    "Location Region", "Location Local Authority", "Location Postal Code",
    "Provider ID", "Provider Name", "Provider Type/Sector",
]


def _x(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _c(v, kind="string"):
    if v is None or v == "":
        return "<table:table-cell/>"
    if kind == "date":
        return ('<table:table-cell office:value-type="date" office:date-value="%s">'
                '<text:p>%s</text:p></table:table-cell>' % (v, v))
    return ('<table:table-cell office:value-type="string"><text:p>%s</text:p>'
            '</table:table-cell>' % _x(v))


def _r(cells, blanks=0, rep=0):
    a = ' table:number-rows-repeated="%d"' % rep if rep else ''
    b = "".join(cells)
    if blanks:
        b += '<table:table-cell table:number-columns-repeated="%d"/>' % blanks
    return "<table:table-row%s>%s</table:table-row>" % (a, b)


def build_ods(path, anchor):
    """Synthetic HSCA_Active_Locations.ods with the real structure and a cast chosen to
    make every branch of this module fire."""
    old = _add_months(anchor, -12 * 17).isoformat()     # 17 years - a mature single site
    mid = _add_months(anchor, -12 * 11).isoformat()
    new = _add_months(anchor, -12 * 2).isoformat()      # 2 years - too new

    # (loc_id, start, name, sector, region, postcode, prov_id, prov_name)
    D = [
        # ---- the ARCHETYPE: sole director, 61, single site, 17 years, charge cleared.
        ("L1", old, "Kingsway Dental Practice", "Primary Dental Care",
         "London", "SW1A 1AA", "P1", "Kingsway Dental Ltd"),

        # ---- a young owner, new practice. Must rank near the bottom.
        ("L2", new, "Bright Smile Dental Studio", "Primary Dental Care",
         "London", "E1 6AN", "P2", "Bright Smile Dental Ltd"),

        # ---- THE HIDDEN GROUP. Three separate Ltd companies, three separate Provider
        # IDs, one site each -> CQC says "three independent single-site dentists".
        # They share a director (HOLDING, Marcus, b.1975-4). The dedupe MUST find this
        # and flag all three as not independent, or Omar rings three strangers who all
        # report to the same board.
        ("L3", mid, "Riverbank Dental Care", "Primary Dental Care",
         "South East", "GU1 1AA", "P3", "Riverbank Dental Care Ltd"),
        ("L4", mid, "Oakfield Dental Care", "Primary Dental Care",
         "South East", "GU2 2BB", "P4", "Oakfield Dental Care Ltd"),
        ("L5", mid, "Parkview Dental Care", "Primary Dental Care",
         "South East", "GU3 3CC", "P5", "Parkview Dental Care Ltd"),

        # ---- five genuinely independent dentists who all use the SAME ACCOUNTANT as
        # their registered office. A naive address union-find merges them into an
        # imaginary five-site group and deletes five real targets. The MAX_ADDR_GROUP
        # guard must keep them independent.
        ("L6", old, "Ashcroft Dental Surgery", "Primary Dental Care",
         "North West", "M1 1AA", "P6", "Ashcroft Dental Surgery Ltd"),
        ("L7", old, "Beechwood Dental Surgery", "Primary Dental Care",
         "North West", "M2 2BB", "P7", "Beechwood Dental Surgery Ltd"),
        ("L8", old, "Cedars Dental Surgery", "Primary Dental Care",
         "North West", "M3 3CC", "P8", "Cedars Dental Surgery Ltd"),
        ("L9", old, "Denton Dental Surgery", "Primary Dental Care",
         "North West", "M4 4DD", "P9", "Denton Dental Surgery Ltd"),
        ("L10", old, "Elmtree Dental Surgery", "Primary Dental Care",
         "North West", "M5 5EE", "P10", "Elmtree Dental Surgery Ltd"),

        # ---- a sole trader. No company, no CH record. Must be UNMATCHED, must STAY on
        # the list (a sole-trader dentist is a fine target), and must be capped.
        ("L11", old, "Mr A Patel", "Primary Dental Care",
         "London", "N1 1AA", "P11", "Mr A Patel"),

        # ---- an AMBIGUOUS name: two active companies called "Premier Dental Ltd".
        # We must refuse to pick one.
        ("L12", old, "Premier Dental", "Primary Dental Care",
         "Wales", "CF1 1AA", "P12", "Premier Dental Ltd"),

        # ---- a 5-site group. Above max_sites, must NOT appear on the list at all.
        ("L13", old, "Megacorp Dental A", "Primary Dental Care", "Midlands", "B1 1AA",
         "P13", "Megacorp Dental Ltd"),
        ("L14", old, "Megacorp Dental B", "Primary Dental Care", "Midlands", "B2 2BB",
         "P13", "Megacorp Dental Ltd"),
        ("L15", old, "Megacorp Dental C", "Primary Dental Care", "Midlands", "B3 3CC",
         "P13", "Megacorp Dental Ltd"),
        ("L16", old, "Megacorp Dental D", "Primary Dental Care", "Midlands", "B4 4DD",
         "P13", "Megacorp Dental Ltd"),
        ("L17", old, "Megacorp Dental E", "Primary Dental Care", "Midlands", "B5 5EE",
         "P13", "Megacorp Dental Ltd"),

        # ---- FILE-WIDE SITE COUNT. P14 has ONE aesthetics clinic... and three other
        # sites in other niches. Its group total is 4, so it must be EXCLUDED at
        # max_sites=2 even though it looks single-site inside aesthetics. This is the
        # test that breaks a naive in-niche count.
        ("L18", old, "Lumiere Aesthetics Clinic", "Independent Healthcare Org",
         "London", "W1A 1AA", "P14", "Lumiere Group Ltd"),
        ("L19", old, "Lumiere House", "Independent Healthcare Org",
         "London", "W1A 2AA", "P14", "Lumiere Group Ltd"),
        ("L20", old, "Lumiere Lodge", "Independent Healthcare Org",
         "London", "W1A 3AA", "P14", "Lumiere Group Ltd"),
        ("L21", old, "Lumiere Court", "Independent Healthcare Org",
         "London", "W1A 4AA", "P14", "Lumiere Group Ltd"),

        # ---- a real single-site aesthetics independent, 55yo sole director, accounts
        # overdue, one director resigned.
        ("L22", mid, "Ivy Aesthetics Clinic", "Independent Healthcare Org",
         "South West", "BS1 1AA", "P15", "Ivy Aesthetics Ltd"),

        # ---- MUST BE EXCLUDED BY SECTOR. Both carry "Dental" on purpose: if the sector
        # filter breaks, a care home and an NHS trust land on the call list.
        ("L23", old, "Meadowview Dental Care Home", "Social Care Org",
         "London", "SE1 1AA", "P16", "Meadowview Care Ltd"),
        ("L24", old, "St Elsewhere Dental Hospital", "NHS Healthcare Organisation",
         "London", "SE2 2BB", "P17", "St Elsewhere NHS Trust"),
    ]

    readme = "".join([
        _r([_c("CQC care directory with filters")]),
        _r([_c("This first sheet is a README. It is not the data and has no "
               "location id header cell.")]),
        _r([]),
    ])
    body = [_r([_c(h) for h in REAL_HEADER], blanks=1000)]
    for i, (lid, st, nm, sec, reg, pc, pid, pn) in enumerate(D):
        cells = [_c(lid), _c(st, "date"), _c(nm), _c(sec), _c(""), _c(""),
                 _c(reg), _c("LA " + reg), _c(pc), _c(pid), _c(pn), _c(sec)]
        if i == 0:
            # A merged-range continuation cell. It OCCUPIES a column. Drop it and every
            # column to its right shifts left - Provider ID would read a postcode.
            cells.insert(5, "<table:covered-table-cell/>")
            cells.pop(6)
        body.append(_r(cells, blanks=3))
    body.append(_r([], rep=60000))                   # repeated blank filler rows

    xml = (_HEAD
           + '<table:table table:name="README">' + readme + '</table:table>'
           + '<table:table table:name="HSCA_Active_Locations">' + "".join(body)
           + '</table:table>' + _TAIL)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", xml)
    return D


# ---------------------------------------------------------------- fake Companies House
def build_ch(anchor):
    """Canned Companies House JSON, keyed by URL path. Served through the REAL CHClient,
    so the throttle, the budget, the cache, the 404 path and the 429 breaker are all on
    the tested code path - the only thing swapped out is urlopen."""
    def dob(age, month=6):
        return {"month": month, "year": anchor.year - age -
                (1 if anchor.month < month else 0)}

    def off(name, age, role="director", appointed="2009-01-01", resigned=None,
            month=6):
        o = {"name": name, "officer_role": role, "appointed_on": appointed,
             "date_of_birth": dob(age, month)}
        if resigned:
            o["resigned_on"] = resigned
        return o

    def addr(prem, l1, pc):
        return {"premises": prem, "address_line_1": l1, "locality": "Town",
                "postal_code": pc}

    sat = _add_months(anchor, -4).isoformat()        # charge satisfied 4 months ago
    res = _add_months(anchor, -8).isoformat()        # co-director resigned 8 months ago
    acc = _add_months(anchor, -18).isoformat()

    # name -> (number, address, status)
    COS = {
        "Kingsway Dental Ltd":        ("01000001", addr("1", "Kingsway", "SW1A 1AA"), "active"),
        "Bright Smile Dental Ltd":    ("01000002", addr("2", "High St", "E1 6AN"), "active"),
        "Riverbank Dental Care Ltd":  ("01000003", addr("3", "Mill Lane", "GU1 1AA"), "active"),
        "Oakfield Dental Care Ltd":   ("01000004", addr("4", "Oak Rd", "GU2 2BB"), "active"),
        "Parkview Dental Care Ltd":   ("01000005", addr("5", "Park Rd", "GU3 3CC"), "active"),
        "Ashcroft Dental Surgery Ltd":  ("01000006", addr("10", "Accountancy House", "M60 1AA"), "active"),
        "Beechwood Dental Surgery Ltd": ("01000007", addr("10", "Accountancy House", "M60 1AA"), "active"),
        "Cedars Dental Surgery Ltd":    ("01000008", addr("10", "Accountancy House", "M60 1AA"), "active"),
        "Denton Dental Surgery Ltd":    ("01000009", addr("10", "Accountancy House", "M60 1AA"), "active"),
        "Elmtree Dental Surgery Ltd":   ("01000010", addr("10", "Accountancy House", "M60 1AA"), "active"),
        "Ivy Aesthetics Ltd":         ("01000015", addr("7", "Ivy Way", "BS1 1AA"), "active"),
    }

    OFFICERS = {
        # The archetype: sole director, 61.
        "01000001": [off("HARPER, Susan Jane", 61)],
        # Young owner. Sole director but 32 -> the young-sole penalty must fire.
        "01000002": [off("NGUYEN, Kim", 32, appointed="2024-02-01")],
        # THE GROUP: one man, three boards. Different local co-director each time, so
        # only the DOB-keyed director link can find it.
        "01000003": [off("HOLDING, Marcus", 50, month=4),
                     off("SMITH, John", 41)],
        "01000004": [off("HOLDING, Marcus", 50, month=4),
                     off("JONES, Alice", 39)],
        "01000005": [off("HOLDING, Marcus", 50, month=4)],
        # Five independents, five different sole directors, ONE shared accountant address.
        "01000006": [off("ASHCROFT, Peter", 62)],
        "01000007": [off("BEECH, Mary", 58)],
        "01000008": [off("CEDAR, Paul", 57)],
        "01000009": [off("DENTON, Rachel", 56)],
        "01000010": [off("ELM, George", 63)],
        # Aesthetics: 55, sole now, co-director resigned 8 months ago, accounts overdue.
        "01000015": [off("IVY, Helen", 55),
                     off("PARTNER, Gone", 52, resigned=res)],
    }

    PROFILES = {}
    for nm, (num, ad, st) in COS.items():
        PROFILES[num] = {
            "company_number": num, "company_name": nm, "company_status": st,
            "date_of_creation": "2009-03-02",
            "registered_office_address": ad,
            "accounts": {"next_accounts": {"overdue": False, "due_on": acc},
                         "last_accounts": {"made_up_to": acc}},
            "confirmation_statement": {"overdue": False},
            "previous_company_names": [],
        }
    PROFILES["01000002"]["date_of_creation"] = _add_months(anchor, -24).isoformat()
    PROFILES["01000015"]["accounts"]["next_accounts"]["overdue"] = True
    PROFILES["01000015"]["previous_company_names"] = [
        {"name": "Ivy Skin Ltd", "ceased_on": _add_months(anchor, -10).isoformat()}]

    CHARGES = {
        "01000001": {"items": [{"status": "fully-satisfied", "satisfied_on": sat,
                                "created_on": "2015-06-01"}]},
        "01000002": {"items": [{"status": "outstanding",
                                "created_on": _add_months(anchor, -6).isoformat()}]},
    }
    PSC = {num: {"items": [{"name": (OFFICERS.get(num) or [{}])[0].get("name", "x"),
                            "kind": "individual-person-with-significant-control",
                            "date_of_birth": (OFFICERS.get(num) or [{}])[0]
                            .get("date_of_birth")}]}
           for num in PROFILES}

    def fetch(url):
        p = url[len(CH_BASE):]
        if p.startswith("/search/companies"):
            q = urllib.parse.unquote(
                urllib.parse.parse_qs(urllib.parse.urlparse(p).query).get("q", [""])[0])
            items = []
            for nm, (num, ad, st) in COS.items():
                if norm_name(nm) == norm_name(q):
                    items.append({"title": nm, "company_number": num,
                                  "company_status": st, "address": ad})
            # The AMBIGUOUS case: two live companies with the same registered name.
            if norm_name(q) == norm_name("Premier Dental Ltd"):
                items = [
                    {"title": "Premier Dental Limited", "company_number": "01000012",
                     "company_status": "active", "address": addr("1", "A St", "CF1 1AA")},
                    {"title": "Premier Dental Ltd", "company_number": "01000013",
                     "company_status": "active", "address": addr("9", "B St", "LS1 1AA")},
                ]
            return 200, {"items": items, "total_results": len(items)}
        m = re.match(r"^/company/(\d+)(/[a-z\-]+)?", p)
        if m:
            num, sub = m.group(1), (m.group(2) or "")
            if num not in PROFILES:
                return 404, None
            if sub == "":
                return 200, PROFILES[num]
            if sub == "/officers":
                return 200, {"items": OFFICERS.get(num, [])}
            if sub == "/charges":
                # 404 is the NORMAL answer for a company that never had a charge.
                return (200, CHARGES[num]) if num in CHARGES else (404, None)
            if sub == "/persons-with-significant-control":
                return 200, PSC.get(num, {"items": []})
        return 404, None

    return fetch


# ------------------------------------------------------------------------ tests
_T_NICHES = [("Aesthetics / skin", ["aesthetic", "botox", "skin", "filler"]),
             ("Dental / orthodontics", ["dental", "dentist", "orthodont"])]


def _t_niche_of(text):
    t = (text or "").lower()
    for nm, keys in _T_NICHES:
        for k in keys:
            if re.search(r"\b" + re.escape(k), t):
                return nm
    return None


def selftest():
    if not _INV_OK:
        print("FAIL: investability.py is not importable from %s" % _HERE)
        return False

    anchor = date(2026, 7, 1)
    tmp = tempfile.mkdtemp(prefix="targets_")
    ods = os.path.join(tmp, "fixture.ods")
    build_ods(ods, anchor)
    fails = []

    def chk(label, got, want):
        ok = (got == want)
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("  %-5s %-52s %s" % ("ok" if ok else "FAIL", label, got))

    def row(rows, pid):
        return next((r for r in rows if r["provider_id"] == pid), None)

    # ================================================= 1. the parser
    print("\n[1] ODS parse: sheet, columns, postcode, merged cells")
    hdr = None
    for _s, r in ods_rows(ods):
        if "location id" in [(c or "").strip().lower() for c in r]:
            hdr = r
            break
    cols = _resolve_target_columns(hdr)
    chk("Location Name col", cols["loc_name"], 2)
    chk("Provider ID col", cols["prov_id"], 9)
    chk("Provider Name col", cols["prov_name"], 10)
    chk("Location Postal Code col (targets-only)", cols["postcode"], 8)

    provs, meta = scan_providers(_t_niche_of, ods, anchor=anchor)
    chk("providers parsed", len(provs), 15)
    chk("care home excluded", "P16" not in provs, True)
    chk("NHS trust excluded", "P17" not in provs, True)
    chk("merged cell did not shift cols (P1 postcode)",
        provs["P1"]["locations"][0]["postcode"], "SW1A 1AA")
    chk("P14 site count is FILE-WIDE not in-niche", provs["P14"]["sites_total"], 4)
    chk("P13 Megacorp site count", provs["P13"]["sites_total"], 5)
    chk("P1 first_registered parsed", provs["P1"]["first_registered"].year, 2009)

    # ================================================= 2. the acquirable population
    print("\n[2] target list = providers with <= max_sites, file-wide")
    res = targets(_t_niche_of, path=ods, anchor=anchor, ch=False)
    dent = res.get("Dental / orthodontics", [])
    aes = res.get("Aesthetics / skin", [])
    chk("dental targets", len(dent), 12)
    chk("Megacorp (5 sites) NOT on the list", row(dent, "P13"), None)
    chk("Lumiere (1 in-niche, 4 file-wide) NOT on list", row(aes, "P14"), None)
    chk("aesthetics targets", len(aes), 1)
    chk("sole trader Mr A Patel IS on the list", row(dent, "P11") is not None, True)
    chk("row carries postcode", row(dent, "P1")["postcode"], "SW1A 1AA")
    chk("row carries region", row(dent, "P1")["region"], "London")
    chk("row carries years_registered", row(dent, "P1")["years_registered"], 17)
    chk("max_sites=3 lets a 3-site group in? (none here)",
        len(targets(_t_niche_of, path=ods, anchor=anchor, ch=False,
                    max_sites=3).get("Dental / orthodontics", [])), 12)
    chk("max_sites=5 admits Megacorp",
        row(targets(_t_niche_of, path=ods, anchor=anchor, ch=False,
                    max_sites=5)["Dental / orthodontics"], "P13") is not None, True)
    chk("niches= filter works",
        sorted(targets(_t_niche_of, path=ods, anchor=anchor, ch=False,
                       niches=["Aesthetics / skin"])), ["Aesthetics / skin"])

    # ================================================= 3. name normalisation
    print("\n[3] name matching: normalise, and refuse to guess")
    chk("Ltd == Limited", norm_name("Smile Dental Ltd"), norm_name("Smile Dental Limited"))
    chk("& == and", norm_name("Smith & Jones Dental"), "smith and jones dental")
    chk("'The' stripped", norm_name("The Dental Studio Ltd"), "dental studio")
    chk("(UK) NOT stripped - it disambiguates",
        norm_name("Smile Dental (UK) Ltd") != norm_name("Smile Dental Ltd"), True)
    chk("individual detected", looks_personal("Mr A Patel"), True)
    chk("individual detected (initials)", looks_personal("A Patel"), True)
    chk("partnership detected", looks_personal("Smith & Partners"), True)
    chk("company NOT personal", looks_personal("Kingsway Dental Ltd"), False)

    # ================================================= 4. CH client discipline
    print("\n[4] Companies House client: budget, cache, 429 breaker, throttle")
    slept = []
    fake = build_ch(anchor)
    c = CHClient(key="TEST", budget=5, fetch=fake, sleep=lambda s: slept.append(s))
    for _ in range(8):
        c.profile("01000001")
    chk("cache means 8 reads cost 1 call", c.calls, 1)
    c2 = CHClient(key="TEST", budget=3, fetch=fake, sleep=lambda s: slept.append(s))
    for i in range(10):
        c2.profile("0100000%d" % (i % 9 + 1))
    chk("hard budget cap respected", c2.calls <= 3, True)
    chk("budget exhaustion flagged", c2.exhausted, True)
    chk("throttle sleeps between calls", any(s > 0 for s in slept), True)

    hits = [0]

    def always429(url):
        hits[0] += 1
        return 429, None
    c3 = CHClient(key="TEST", budget=100, fetch=always429, sleep=lambda s: None)
    for _ in range(6):
        c3.profile("01000001")
    chk("429 breaker trips", c3.blocked, True)
    chk("breaker stops the calls (not 100)", hits[0] < 20, True)
    # REGRESSION: the breaker only fires because failures are NOT cached. Cache a 429 as
    # None and the second call short-circuits, the breaker never counts to 5, and a
    # transient rate-limit is frozen into "this company has no data" for the whole run.
    chk("a 429 is NOT cached as an answer", c3.cache.get("/company/01000001"), None)
    chk("...i.e. the path is absent from the cache entirely",
        "/company/01000001" in c3.cache, False)
    # ...but a 404 IS a real answer and IS cached (a company with no charges 404s).
    c3b = CHClient(key="TEST", budget=100, fetch=lambda u: (404, None),
                   sleep=lambda s: None)
    c3b.charges("01000001")
    c3b.charges("01000001")
    chk("a 404 IS cached (it is an answer, not a failure)", c3b.calls, 1)

    c4 = CHClient(key="", budget=100, fetch=fake)
    chk("no key -> no calls, no crash", (c4.profile("01000001"), c4.calls), (None, 0))
    c5 = CHClient(key="TEST", budget=100, fetch=lambda u: (500, None),
                  sleep=lambda s: None)
    chk("500s -> None, never raises", c5.profile("01000001"), None)
    c6 = CHClient(key="TEST", budget=100,
                  fetch=lambda u: (_ for _ in ()).throw(ValueError("boom")),
                  sleep=lambda s: None)
    try:
        got, raised = c6.profile("01000001"), False
    except Exception:
        got, raised = None, True
    chk("a transport that RAISES is contained", (got, raised), (None, False))

    # ================================================= 5. DOB -> age
    print("\n[5] officer age from month+year DOB (lower bound)")
    chk("born Jun-1965, anchor Jul-2026 -> 61", _dob_age({"month": 6, "year": 1965},
                                                         anchor), 61)
    chk("born Dec-1965, anchor Jul-2026 -> 60 (lower bound)",
        _dob_age({"month": 12, "year": 1965}, anchor), 60)
    chk("missing dob -> None", _dob_age(None, anchor), None)
    chk("junk dob -> None", _dob_age({"month": "x", "year": None}, anchor), None)

    # ================================================= 6. dedupe
    print("\n[6] OWNER DEDUPE: the hidden group, and the accountant trap")
    live = targets(_t_niche_of, path=ods, anchor=anchor, max_sites=2,
                   ch_client=CHClient(key="TEST", budget=300, fetch=build_ch(anchor),
                                      sleep=lambda s: None))
    dent = live["Dental / orthodontics"]
    aes = live["Aesthetics / skin"]
    owners = owners_report()

    grp = [o for o in owners.values() if o["is_group"]]
    chk("exactly one multi-entity owner found", len(grp), 1)
    chk("...and it is the 3 Ltds sharing a director",
        sorted(grp[0]["providers"]) if grp else None, ["P3", "P4", "P5"])
    chk("link reason names the director",
        any("Holding" in r for r in grp[0]["link_reasons"]) if grp else False, True)
    for pid in ("P3", "P4", "P5"):
        chk("%s flagged NOT independent" % pid, row(dent, pid)["independent"], False)
        chk("%s owner_entities" % pid, row(dent, pid)["owner_entities"], 3)

    # THE TRAP: five real independents sharing one accountant's registered office.
    for pid in ("P6", "P7", "P8", "P9", "P10"):
        chk("%s (shared accountant addr) STILL independent" % pid,
            row(dent, pid)["independent"], True)
    chk("agent address was spotted and reported",
        len(DIAG["economic_owners"]["agent_addresses_ignored"]), 1)
    chk("...and it is the accountant's",
        "M601AA" in DIAG["economic_owners"]["agent_addresses_ignored"][0]["key"], True)
    chk("agent address covered 5 providers",
        DIAG["economic_owners"]["agent_addresses_ignored"][0]["providers"], 5)

    # A 2-provider shared address IS a link (below the guard) - prove the guard is a
    # threshold, not a switch that disables address linking altogether.
    two = [{"provider_id": "A", "provider_name": "A Ltd", "sites": 1,
            "ch": {"status": "matched"},
            "ch_facts": {"reg_office_key": "AA11AA|1 the street", "director_keys": []}},
           {"provider_id": "B", "provider_name": "B Ltd", "sites": 1,
            "ch": {"status": "matched"},
            "ch_facts": {"reg_office_key": "AA11AA|1 the street", "director_keys": []}}]
    _p2o, ow2, _d2 = economic_owners(two)
    chk("2 providers at one address DO get linked",
        sum(1 for o in ow2.values() if o["is_group"]), 1)

    # ================================================= 7. matching outcomes
    print("\n[7] match status: matched / ambiguous / unmatched")
    chk("P1 matched", row(dent, "P1")["ch"]["status"], "matched")
    chk("P1 confidence high (name + postcode agree)",
        row(dent, "P1")["ch"]["confidence"], "high")
    chk("P11 sole trader -> unmatched", row(dent, "P11")["ch"]["status"], "unmatched")
    chk("P12 duplicate name -> ambiguous, NOT guessed",
        row(dent, "P12")["ch"]["status"], "ambiguous")
    chk("ambiguous row keeps no company number",
        row(dent, "P12")["ch"]["company_number"], None)
    chk("P11 still on the list (unmatched != dropped)",
        row(dent, "P11") is not None, True)

    # ================================================= 8. the score
    print("\n[8] SELLER-INTENT: does the right name come first?")
    top = dent[0]
    chk("top of the dental list is Kingsway (sole dir 61, 17y, charge cleared)",
        top["provider_id"], "P1")
    chk("...and the reasons say why",
        any("61" in r for r in top["seller_reasons"]), True)
    chk("...charge satisfied is called out",
        any("charge satisfied" in r.lower() for r in top["seller_reasons"]), True)
    chk("...no successor is called out",
        any("successor" in r.lower() for r in top["seller_reasons"]), True)
    print("       -> %s: %d  %s" % (top["provider_name"], top["seller_score"],
                                    "; ".join(top["seller_reasons"])))

    p2 = row(dent, "P2")
    chk("young new owner scores low", p2["seller_score"] < 20, True)
    chk("...and says so",
        any("unlikely to be exiting" in r for r in p2["seller_reasons"]), True)
    chk("young owner ranks below the 61yo",
        dent.index(p2) > dent.index(top), True)

    p11 = row(dent, "P11")
    chk("unmatched sole trader capped at %d" % CQC_ONLY_CAP,
        p11["seller_score"] <= CQC_ONLY_CAP, True)
    chk("...confidence marked low", p11["score_confidence"], "low (CQC only)")
    chk("...cannot outrank a fully-evidenced seller",
        p11["seller_score"] < top["seller_score"], True)

    grp_row = row(dent, "P3")
    chk("group member penalised", any("NOT INDEPENDENT" in r
                                      for r in grp_row["seller_reasons"]), True)
    chk("group member ranks below the true independents",
        grp_row["seller_score"] < row(dent, "P6")["seller_score"], True)

    ivy = row(aes, "P15")
    chk("aesthetics: resignation counted",
        any("resignation" in r for r in ivy["seller_reasons"]), True)
    chk("aesthetics: overdue accounts counted",
        any("accounts overdue" in r for r in ivy["seller_reasons"]), True)
    chk("aesthetics: name change counted",
        any("name changed" in r for r in ivy["seller_reasons"]), True)

    chk("every score in 0..100",
        all(0 <= r["seller_score"] <= 100 for r in dent + aes), True)
    chk("list is sorted by score desc",
        all(dent[i]["seller_score"] >= dent[i + 1]["seller_score"]
            for i in range(len(dent) - 1)), True)
    chk("every row has at least one reason",
        all(r["seller_reasons"] for r in dent + aes), True)

    # tenure: CH incorporation beats the CQC HSCA re-registration date
    chk("years_incorporated preferred where CH has it",
        row(dent, "P1").get("years_incorporated"), 17)

    # ================================================= 9. budget behaviour
    print("\n[9] a tiny budget degrades gracefully, it does not lie")
    tiny = CHClient(key="TEST", budget=4, fetch=build_ch(anchor), sleep=lambda s: None)
    small = targets(_t_niche_of, path=ods, anchor=anchor, ch_client=tiny)
    sd = small["Dental / orthodontics"]
    unchecked = [r for r in sd if r["ch"]["status"] == "not_checked"]
    chk("budget respected", tiny.calls <= 4, True)
    chk("most rows honestly marked not_checked", len(unchecked) > 5, True)
    chk("unchecked rows scored structurally only",
        all(r["score_confidence"] == "low (CQC only)" for r in unchecked), True)
    chk("unchecked rows still capped",
        all(r["seller_score"] <= CQC_ONLY_CAP for r in unchecked), True)
    chk("still returns a usable list", len(sd), 12)

    # ================================================= 10. totality
    print("\n[10] never crash")
    bad = os.path.join(tmp, "bad.ods")
    with open(bad, "wb") as f:
        f.write(b"not a zip")
    chk("corrupt file -> {}", targets(_t_niche_of, path=bad, ch=False), {})
    empty = os.path.join(tmp, "empty.ods")
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("content.xml", _HEAD + '<table:table table:name="README">'
                   + _r([_c("nothing")]) + '</table:table>' + _TAIL)
    chk("no data sheet -> {}", targets(_t_niche_of, path=empty, ch=False), {})
    chk("no CH key -> target list still built",
        len(targets(_t_niche_of, path=ods, anchor=anchor,
                    ch_client=CHClient(key="", budget=10, fetch=fake))
            .get("Dental / orthodontics", [])), 12)

    broken = CHClient(key="TEST", budget=50,
                      fetch=lambda u: (200, {"items": "not-a-list"}),
                      sleep=lambda s: None)
    r = targets(_t_niche_of, path=ods, anchor=anchor, ch_client=broken)
    chk("garbage CH payload -> still returns a list", len(r) >= 1, True)
    chk("...and no row is unscored",
        all("seller_score" in x for v in r.values() for x in v), True)

    shutil.rmtree(tmp, ignore_errors=True)
    print("")
    if fails:
        print("SELFTEST FAILED (%d)\n  %s" % (len(fails), "\n  ".join(fails)))
        return False
    print("SELFTEST PASSED - parser, dedupe and scorer all green")
    return True


# ------------------------------------------------------------------------- CLI
def to_csv(res, path):
    """The Monday-morning artefact: open it, sort by score, start at the top."""
    cols = ["niche", "seller_score", "provider_name", "location_name", "postcode",
            "region", "sites", "years_registered", "independent", "ch_status",
            "company_number", "score_confidence", "seller_reasons"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for niche, rows in sorted(res.items()):
            for r in rows:
                w.writerow([niche, r["seller_score"], r["provider_name"],
                            r["location_name"], r["postcode"], r["region"], r["sites"],
                            r["years_registered"], r["independent"],
                            r["ch"]["status"], r["ch"]["company_number"],
                            r["score_confidence"], "; ".join(r["seller_reasons"])])
    return path


def _print(res, limit=25):
    for niche, rows in sorted(res.items(), key=lambda kv: -len(kv[1])):
        print("\n=== %s  (%d acquirable targets)" % (niche, len(rows)))
        print("%4s  %-38s %-9s %-5s %s" % ("scr", "provider", "postcode", "sites",
                                           "why"))
        for r in rows[:limit]:
            print("%4d  %-38s %-9s %-5s %s"
                  % (r["seller_score"], (r["provider_name"] or "")[:38],
                     (r["postcode"] or "")[:9], r["sites"],
                     "; ".join(r["seller_reasons"])[:90]))
        if len(rows) > limit:
            print("      ... and %d more" % (len(rows) - limit))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)

    want = None
    if "--niche" in sys.argv:
        want = [sys.argv[sys.argv.index("--niche") + 1]]
    try:
        from taxonomy import niche_of as real_niche_of
    except Exception:
        try:
            from pull_and_build import niche_of as real_niche_of
        except Exception:
            real_niche_of = _t_niche_of
            print("(taxonomy not importable - using the cut-down test taxonomy)")

    out = targets(real_niche_of, niches=want)
    if not out:
        print("targets: no list built")
        print(json.dumps(DIAG, indent=1, default=str))
    else:
        _print(out)
        if "--csv" in sys.argv:
            p = to_csv(out, sys.argv[sys.argv.index("--csv") + 1])
            print("\nwrote %s" % p)
        print("\nDIAG:", json.dumps(DIAG, indent=1, default=str))
