#!/usr/bin/env python3
"""
T1-OPEN: the search-side open layer. Rising Google queries for broad UK health seeds.

WHY THIS FILE EXISTS
--------------------
T1 today is a watchlist: ~15 terms Omar picked, plus 5 phrases fed back from the
supply tiers. A watchlist can only confirm suspicions we already hold. Google
Trends' "related queries - RISING" panel is the opposite: give it a broad seed
("adhd", "private clinic", "weight loss") and GOOGLE tells us which specific
queries under that seed are growing fastest right now, including "Breakout"
terms (>5,000% growth, usually queries that barely existed before). Nobody has
to think of the term first. That makes this the earliest possible discovery
signal in the radar: it fires when the PUBLIC starts asking, before anyone
incorporates a company, registers a clinic, or writes a prescription.

Each harvested query is passed through the shared taxonomy. Queries that map to
a niche we already track are confirmation. Queries that map to NOTHING are the
point of the module - the discovery rows. "retatrutide" (the likely next
weight-loss drug, not in the taxonomy) would land there today, exactly as
"ozempic" would have in 2022 and "adhd assessment" in 2021.

THE API (VERIFIED against serpapi.com/google-trends-related-queries, 13 Jul 2026)
---------------------------------------------------------------------------------
  GET https://serpapi.com/search.json?engine=google_trends
      &data_type=RELATED_QUERIES      one seed per search - this is what a search buys
      &q=<seed>&geo=GB&hl=en&date=today 12-m&api_key=...

  {"related_queries": {"rising": [{"query": "usagi coffee",
                                   "value": "Breakout",        <- a STRING
                                   "extracted_value": 8700},   <- % growth, int
                                  {"query": "crep and coffee",
                                   "value": "+4,500%",         <- comma, plus, percent
                                   "extracted_value": 4500}],
                       "top": [...]}}

  "value" is the label Google shows: a percentage ("+250%", "+4,500%") or a
  breakout label, which Google LOCALISES ("Breakout" in English, "Record" in
  French). The parser therefore treats any non-numeric label as a breakout
  rather than matching the English word. "extracted_value" stays numeric even
  for breakouts. "top" is ignored: top = share of volume (watchlist territory),
  rising = growth (discovery territory).

THE BUDGET, WHICH DECIDES EVERYTHING
------------------------------------
SerpApi free tier. Pricing page (verified 13 Jul 2026) now says 250 searches a
month, but the account may be on the older 100/month allowance and the existing
T1 watchlist already burns ~20 every Monday (~80-100/month). So this module
assumes it may only ever have ~20 searches a month, and defends that three ways:

  1. WEEKLY GATE   - refreshes at most once every REFRESH_DAYS (6) days,
                     however often the daily build runs.
  2. MONTHLY LEDGER- counts its own successful calls per calendar month in the
                     cache and hard-stops at monthly_cap (default 18: three
                     budget-6 refreshes, then silence until the month rolls).
  3. SEED ROTATION - each refresh polls the `budget` least-recently-polled
                     seeds, so ~26 seeds are all covered about once a month at
                     6 calls a week. Rising-vs-12-months moves slowly; a
                     monthly cadence per seed loses little.

SerpApi's own counting rule (verified, pricing FAQ): errored/failed searches are
NOT counted; empty result sets ARE. A seed with no data comes back as JSON with
an "error" field - whether that bills is ambiguous, so the ledger counts it
(conservative). Hard HTTP failures (quota exhausted, network) are not counted,
and two in a row abort the refresh so a dead key never eats the loop.

MEMORY
------
Every query ever harvested is cached permanently with first_seen/last_seen, so
the module can tell a genuinely NEW riser (is_new=True: never seen before -
look at it today) from one that has been rising for months (still valuable: a
trend with stamina). Caveat: the first time a SEED is ever polled, everything
under it is is_new by construction - judge the first week of a new seed gently.

JUNK
----
Filtered structurally where possible: a query must contain at least one
substantive token beyond its seed, grammar filler and a short, honest stoplist
(nhs / login / near me / reviews / lyrics / jobs ...). So "adhd near me" and
"adhd uk" die structurally (nothing left once the seed is removed), while
"private adhd", "adhd assessment cost" and single-token discoveries like
"retatrutide" survive. Junk is filtered at OUTPUT, not at harvest - the cache
keeps the raw truth, so a better filter later re-scores history for free.

Degrades to None on any failure. Never crashes the build. Stdlib only.
Self-test: python3 trends_open.py  (synthetic fixtures, no network needed).
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

# The module starts life in _agent4/ next to nothing; in production it sits in
# the repo root next to taxonomy.py. Try the plain import first, then the
# parent directory, then degrade to "everything is a discovery row" rather
# than kill a build over a mapping.
try:
    from taxonomy import niche_of
except ImportError:                                          # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from taxonomy import niche_of
    except ImportError:
        def niche_of(_text):
            return None

UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}
REFRESH_DAYS = 6          # at most one paid refresh per ~week, even on a daily cron
MAX_ROWS = 200            # plenty; rising lists are ~25 per seed and mostly overlap
MAX_CACHE_QUERIES = 20000 # ~years of churn; pruned oldest-first past this

# ------------------------------------------------------------------- SEEDS
# Broad on purpose. A seed is a DOOR, not a term we track: Google decides what
# is rising behind it. Two rings: the widest private-pay funnels (where a niche
# nobody has named yet must first appear), then category doors whose rising
# lists surface the next specific thing inside areas we already watch.
DEFAULT_SEEDS = [
    # widest private-pay funnels
    "private clinic", "private assessment", "private prescription", "private scan",
    "clinic", "therapy", "treatment", "injections", "supplements",
    # category doors
    "weight loss", "weight loss injection", "adhd", "autism", "menopause",
    "testosterone", "hair loss", "skin", "botox", "hormone", "anxiety",
    "sleep", "blood test", "fertility", "gut health", "longevity", "private gp",
]

# ------------------------------------------------------------------- JUNK
# Small and honest, not a taxonomy of the internet. Structure does the rest.
STOP_TOKENS = frozenset((
    "nhs", "login", "portal", "gov",
    "review", "reviews",
    "wikipedia", "wiki", "youtube", "reddit", "tiktok", "instagram",
    "facebook", "twitter", "snapchat", "netflix", "spotify",
    "amazon", "ebay", "gumtree",
    "lyrics", "song", "album", "film", "movie", "imdb", "trailer", "cast",
    "job", "jobs", "salary", "apprenticeship", "course", "courses",
    "university", "degree",
))
STOP_PHRASES = ("near me", "log in", "sign in", "opening times",
                "phone number", "contact number", "email address")
# grammar/dictionary filler - never counts as substance (tokens <3 chars never do)
FILLER = frozenset((
    "the", "and", "for", "with", "from", "that", "this", "what", "when",
    "where", "which", "why", "how", "who", "can", "could", "should", "would",
    "does", "did", "was", "were", "have", "has", "had", "not", "near", "you",
    "your", "get", "much", "many", "mean", "meaning", "definition", "define",
))

_TOKEN_RX = re.compile(r"[a-z0-9]+")
# a rise label is numeric if it is only digits/commas/dots with optional +/%
_NUMERIC_RX = re.compile(r"^\+?\s*[\d.,]+\s*%?$")


def _tokens(text):
    return _TOKEN_RX.findall((text or "").lower())


def is_junk(query, seed_tokens):
    """True if the query is navigational noise or adds nothing beyond its seed."""
    q = (query or "").lower()
    for p in STOP_PHRASES:
        if p in q:
            return True
    toks = _tokens(q)
    if not toks or any(t in STOP_TOKENS for t in toks):
        return True
    substance = [t for t in toks
                 if len(t) >= 3 and not t.isdigit()
                 and t not in seed_tokens and t not in FILLER]
    return not substance


# ------------------------------------------------------------------- PARSER
def rise_of(item):
    """(rise, magnitude) for one rising[] item.

    rise      = numeric % growth, or the string 'breakout'
    magnitude = number used for ranking (breakouts keep their extracted %)
    Breakout is detected by the label being NON-numeric, not by matching the
    English word, because Google localises it ('Record' in French UI).
    Returns (None, None) for an unparseable item - skip it, don't crash.
    """
    v = item.get("value")
    ev = item.get("extracted_value")
    label = v.strip() if isinstance(v, str) else None
    if label and not _NUMERIC_RX.match(label):
        mag = float(ev) if isinstance(ev, (int, float)) else 5000.0
        return "breakout", mag
    if isinstance(ev, (int, float)):
        return float(ev), float(ev)
    if label:
        try:
            n = float(label.replace("+", "").replace("%", "").replace(",", "").strip())
            return n, n
        except ValueError:
            return None, None
    return None, None


def parse_related(payload, seed):
    """SerpApi RELATED_QUERIES payload -> raw rows. No filtering here: the cache
    keeps everything harvested; junk is decided at output time."""
    rq = (payload or {}).get("related_queries") or {}
    rows = []
    for item in rq.get("rising") or []:
        if not isinstance(item, dict):
            continue
        q = " ".join((item.get("query") or "").lower().split())
        if not q:
            continue
        rise, mag = rise_of(item)
        if rise is None:
            continue
        rows.append({"query": q, "seed": seed, "rise": rise, "rise_value": mag})
    return rows


def _rank(rise, mag):
    """Sort key: any breakout above any numeric value, then by magnitude."""
    return (1 if rise == "breakout" else 0, mag if mag is not None else 0.0)


# ------------------------------------------------------------------- CACHE
def _load(path):
    try:
        with open(path) as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            d.setdefault("seeds", {})
            d.setdefault("queries", {})
            d.setdefault("spend", {})
            return d
    except Exception:
        pass
    return {"seeds": {}, "queries": {}, "spend": {}}


def _save(path, store):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(store, fh, indent=1)
    os.replace(tmp, path)         # never leave the permanent memory half-written


def _prune(store):
    qs = store["queries"]
    if len(qs) > MAX_CACHE_QUERIES:
        keep = sorted(qs.items(), key=lambda kv: kv[1].get("last_seen") or "")
        store["queries"] = dict(keep[-int(MAX_CACHE_QUERIES * 0.75):])
    months = sorted(store["spend"])
    for m in months[:-13]:
        store["spend"].pop(m, None)


def _merge(store, rows, today_iso):
    """Fold one seed's harvest into permanent memory. first_seen is written once
    and never touched again - that is the whole point of the memory."""
    for r in rows:
        e = store["queries"].setdefault(r["query"], {"first_seen": today_iso, "seeds": []})
        stale = e.get("last_seen") != today_iso
        if stale or _rank(r["rise"], r["rise_value"]) >= _rank(e.get("rise"), e.get("rise_value")):
            e["rise"], e["rise_value"], e["seed"] = r["rise"], r["rise_value"], r["seed"]
        e["last_seen"] = today_iso
        e["sightings"] = e.get("sightings", 0) + 1
        if r["seed"] not in e["seeds"]:
            e["seeds"].append(r["seed"])


# ------------------------------------------------------------------- FETCH
def _fetch_serpapi(seed, api_key, date_range, timeout=30):
    url = ("https://serpapi.com/search.json?engine=google_trends"
           "&data_type=RELATED_QUERIES&geo=GB&hl=en"
           "&date=" + urllib.parse.quote(date_range) +
           "&q=" + urllib.parse.quote(seed) +
           "&api_key=" + api_key)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------------- OUTPUT
def _rows_from_store(store):
    """A row is CURRENT if it appeared the last time (any of) its seeds were
    polled - i.e. Google still lists it as rising. Older entries stay in memory
    (they keep first_seen honest) but are not returned."""
    seeds_log = store["seeds"]
    out = []
    for q, e in store["queries"].items():
        seeds = e.get("seeds") or ([e["seed"]] if e.get("seed") else [])
        last_polls = [(seeds_log.get(s) or {}).get("last_polled") for s in seeds]
        if not e.get("last_seen") or e["last_seen"] not in [p for p in last_polls if p]:
            continue
        seed_toks = set()
        for s in seeds:
            seed_toks.update(_tokens(s))
        if is_junk(q, seed_toks):
            continue
        out.append({
            "query": q,
            "seed": e.get("seed"),
            "rise": e.get("rise"),
            "rise_value": e.get("rise_value"),
            "niche": niche_of(q),                    # None = a DISCOVERY row
            "first_seen": e.get("first_seen"),
            "is_new": e.get("first_seen") == e.get("last_seen"),
        })
    out.sort(key=lambda r: _rank(r["rise"], r["rise_value"]), reverse=True)
    return out[:MAX_ROWS]


# ------------------------------------------------------------------- MAIN
def trends_open(seeds=None, budget=6, cache="data/trends_open.json",
                monthly_cap=18, date_range="today 12-m",
                _fetch=None, _today=None):
    """Harvest RISING Google queries for a rotating set of broad UK health seeds.

    Returns [{"query":..., "seed":..., "rise": <pct or 'breakout'>,
              "rise_value": <number for ranking>,
              "niche": <niche_of(query) or None>,
              "first_seen": "YYYY-MM-DD", "is_new": bool}]
    sorted breakouts-first, or None if nothing is available at all.

    Rows where niche is None are the DISCOVERY rows: search terms rising fast
    that map to NO niche we already track. That is the point of the module.

    budget      = max SerpApi calls per refresh (one call = one seed).
    monthly_cap = hard ceiling on calls per calendar month, whatever the cron does.
    Refreshes at most every REFRESH_DAYS days; otherwise serves the cache free.
    _fetch/_today exist for the offline self-test only.
    """
    try:
        return _trends_open(seeds, budget, cache, monthly_cap, date_range,
                            _fetch, _today)
    except Exception:
        return None                     # a dead open layer must never kill the build


def _trends_open(seeds, budget, cache, monthly_cap, date_range, _fetch, _today):
    seeds = list(seeds) if seeds else list(DEFAULT_SEEDS)
    today = _today or date.today()
    tiso = today.isoformat()
    mkey = tiso[:7]
    store = _load(cache)

    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    can_fetch = bool(api_key) or _fetch is not None

    due = True
    last = store.get("last_refresh")
    if last:
        try:
            due = (today - date.fromisoformat(last)).days >= REFRESH_DAYS
        except ValueError:
            due = True

    room = max(0, min(int(budget or 0), int(monthly_cap) - store["spend"].get(mkey, 0)))

    if can_fetch and due and room > 0:
        fetch = _fetch or (lambda s: _fetch_serpapi(s, api_key, date_range))
        # least-recently-polled first; never-polled seeds first of all, in list order
        order = sorted(range(len(seeds)),
                       key=lambda i: ((store["seeds"].get(seeds[i]) or {})
                                      .get("last_polled") or "", i))
        made, fails = 0, 0
        for i in order[:room]:
            seed = seeds[i]
            try:
                payload = fetch(seed)
            except Exception:
                fails += 1                 # quota gone / network down: not billed,
                if fails >= 2:             # seed stays due; two in a row = give up
                    break
                continue
            fails = 0
            rows = parse_related(payload, seed)
            # Reached the API and got a completed search back (data or a polite
            # "no results" error). Count it - the conservative reading of
            # SerpApi's "empty result sets count" rule.
            store["spend"][mkey] = store["spend"].get(mkey, 0) + 1
            log = store["seeds"].setdefault(seed, {"polls": 0})
            log["last_polled"] = tiso
            log["polls"] = log.get("polls", 0) + 1
            log["rows"] = len(rows)
            _merge(store, rows, tiso)
            made += 1
            if _fetch is None:
                time.sleep(1.0)            # free tier allows 50/hour; be gentle anyway
        if made:
            store["last_refresh"] = tiso   # all-failed refresh stays due for tomorrow
        _prune(store)
        _save(cache, store)

    out = _rows_from_store(store)
    if not out and not store["queries"]:
        return None                        # nothing cached, nothing fetched
    return out


# ==================================================================== TESTS
# Synthetic fixtures shaped exactly like the VERIFIED SerpApi response
# (serpapi.com/google-trends-related-queries, fetched 13 Jul 2026). No network.

def _fx(rising):
    return {"search_metadata": {"status": "Success"},
            "related_queries": {"rising": rising,
                                "top": [{"query": "ignored", "value": "100",
                                         "extracted_value": 100}]}}


_FIXTURES = {
    "adhd": _fx([
        {"query": "ADHD assessment", "value": "Breakout", "extracted_value": 8700,
         "link": "x", "serpapi_link": "x"},
        {"query": "private adhd assessment", "value": "+4,500%", "extracted_value": 4500},
        {"query": "adhd medication shortage", "value": "+2,750%"},   # no extracted_value
        {"query": "adhd near me", "value": "+300%", "extracted_value": 300},
        {"query": "adhd nhs", "value": "+250%", "extracted_value": 250},
        {"query": "adhd uk", "value": "+200%", "extracted_value": 200},
        {"query": "adhd", "value": "+50%", "extracted_value": 50},
        {"query": "adhd reddit", "value": "+150%", "extracted_value": 150},
    ]),
    "therapy": _fx([
        {"query": "red light therapy", "value": "Record", "extracted_value": 7050},
        {"query": "ketamine therapy", "value": "+250%", "extracted_value": 250},
        {"query": "group therapy lyrics", "value": "+900%", "extracted_value": 900},
    ]),
    "weight loss": _fx([
        {"query": "retatrutide", "value": "Breakout", "extracted_value": 12000},
        {"query": "mounjaro price", "value": "+900%", "extracted_value": 900},
    ]),
}
_EMPTY = {"search_metadata": {"status": "Success"},
          "error": "Google Trends hasn't returned any results for this query."}


def _selftest():
    import tempfile
    fails = []

    def check(name, cond):
        print(("PASS  " if cond else "FAIL  ") + name)
        if not cond:
            fails.append(name)

    # ---- parser: breakout handling, localisation, comma percentages
    r, m = rise_of({"value": "Breakout", "extracted_value": 8700})
    check("breakout label -> 'breakout', keeps magnitude", r == "breakout" and m == 8700.0)
    r, m = rise_of({"value": "Record", "extracted_value": 7050})
    check("localised breakout label handled without crashing", r == "breakout")
    r, m = rise_of({"value": "+4,500%", "extracted_value": 4500})
    check("comma percentage -> 4500", r == 4500.0)
    r, m = rise_of({"value": "+2,750%"})
    check("percentage parsed from label when extracted_value missing", r == 2750.0)
    r, m = rise_of({})
    check("unparseable item skipped, not crashed", r is None)
    check("breakout ranks above any numeric value",
          _rank("breakout", 5000) > _rank(9999999.0, 9999999.0))

    # ---- junk filter: structural residue + small stoplist
    check("'adhd near me' junk", is_junk("adhd near me", {"adhd"}))
    check("'adhd uk' junk (nothing beyond seed)", is_junk("adhd uk", {"adhd"}))
    check("'adhd nhs' junk (stoplist)", is_junk("adhd nhs", {"adhd"}))
    check("'adhd reddit' junk (platform)", is_junk("adhd reddit", {"adhd"}))
    check("seed itself junk", is_junk("adhd", {"adhd"}))
    check("'private adhd' kept", not is_junk("private adhd", {"adhd"}))
    check("'adhd assessment cost' kept", not is_junk("adhd assessment cost", {"adhd"}))
    check("single-token discovery kept", not is_junk("retatrutide", {"weight", "loss"}))

    # ---- niche mapping through the real taxonomy
    check("'mounjaro price' maps to a tracked niche",
          niche_of("mounjaro price") == "Weight loss / GLP-1")
    check("'retatrutide' is a DISCOVERY row (no niche)", niche_of("retatrutide") is None)
    check("'red light therapy' is a DISCOVERY row", niche_of("red light therapy") is None)

    tmp = tempfile.mkdtemp()
    cpath = os.path.join(tmp, "trends_open.json")
    calls = []

    def fake_fetch(seed):
        calls.append(seed)
        return _FIXTURES.get(seed, _EMPTY)

    # ---- refresh 1: harvest, rank, discover
    rows = trends_open(seeds=["adhd", "therapy", "weight loss"], budget=6,
                       cache=cpath, _fetch=fake_fetch, _today=date(2026, 7, 13))
    check("refresh 1 returns rows", bool(rows))
    check("all three seeds polled once", sorted(calls) == ["adhd", "therapy", "weight loss"])
    got = {r["query"] for r in rows}
    check("junk removed from output",
          not ({"adhd near me", "adhd uk", "adhd nhs", "adhd", "group therapy lyrics",
                "adhd reddit"} & got))
    check("signal kept", {"adhd assessment", "private adhd assessment", "retatrutide",
                          "red light therapy", "mounjaro price"} <= got)
    check("sorted breakouts-first, by magnitude",
          [r["query"] for r in rows[:3]] == ["retatrutide", "adhd assessment",
                                             "red light therapy"])
    disc = [r for r in rows if r["niche"] is None]
    check("discovery rows split out by niche=None",
          {"retatrutide", "red light therapy"} <= {r["query"] for r in disc})
    check("everything new on first sight", all(r["is_new"] for r in rows))
    check("cache written", os.path.exists(cpath))

    # ---- same week: served from cache, zero calls
    n = len(calls)
    rows2 = trends_open(seeds=["adhd", "therapy", "weight loss"], budget=6,
                        cache=cpath, _fetch=fake_fetch, _today=date(2026, 7, 15))
    check("mid-week run costs zero calls", len(calls) == n)
    check("mid-week run still serves rows", bool(rows2))

    # ---- refresh 2, a week on: first_seen survives, is_new flips, new term flagged
    _FIXTURES["adhd"]["related_queries"]["rising"].append(
        {"query": "adhd titration", "value": "Breakout", "extracted_value": 6000})
    rows3 = trends_open(seeds=["adhd", "therapy", "weight loss"], budget=6,
                        cache=cpath, _fetch=fake_fetch, _today=date(2026, 7, 20))
    by_q = {r["query"]: r for r in rows3}
    check("first_seen persists across refreshes",
          by_q["adhd assessment"]["first_seen"] == "2026-07-13")
    check("re-sighted riser no longer is_new", not by_q["adhd assessment"]["is_new"])
    check("genuinely new riser flagged is_new", by_q["adhd titration"]["is_new"])

    # ---- rotation: budget 2 over 5 seeds covers all five, least-recent first
    calls.clear()
    cpath2 = os.path.join(tmp, "rot.json")
    five = ["s1", "s2", "s3", "s4", "s5"]
    trends_open(seeds=five, budget=2, cache=cpath2, _fetch=fake_fetch,
                _today=date(2026, 1, 1))
    trends_open(seeds=five, budget=2, cache=cpath2, _fetch=fake_fetch,
                _today=date(2026, 1, 8))
    trends_open(seeds=five, budget=2, cache=cpath2, _fetch=fake_fetch,
                _today=date(2026, 1, 15))
    check("rotation covers every seed before repeating",
          calls[:5] == five and calls[5] == "s1")

    # ---- monthly ledger: cap binds across refreshes in the same month
    calls.clear()
    cpath3 = os.path.join(tmp, "cap.json")
    trends_open(seeds=five, budget=6, cache=cpath3, monthly_cap=4,
                _fetch=fake_fetch, _today=date(2026, 3, 2))
    trends_open(seeds=five, budget=6, cache=cpath3, monthly_cap=4,
                _fetch=fake_fetch, _today=date(2026, 3, 9))
    check("monthly cap binds (4 calls, not 12)", len(calls) == 4)
    trends_open(seeds=five, budget=6, cache=cpath3, monthly_cap=4,
                _fetch=fake_fetch, _today=date(2026, 4, 1))
    check("new month reopens the budget", len(calls) > 4)

    # ---- failure paths: never crash, degrade to cache, then to None
    def dead_fetch(seed):
        raise OSError("network down / out of searches")

    rows4 = trends_open(seeds=["adhd"], budget=6, cache=cpath,
                        _fetch=dead_fetch, _today=date(2026, 8, 1))
    check("dead API still serves cached rows", bool(rows4))
    rows5 = trends_open(seeds=["adhd"], budget=6,
                        cache=os.path.join(tmp, "fresh.json"),
                        _fetch=dead_fetch, _today=date(2026, 8, 1))
    check("dead API + empty cache -> None, no crash", rows5 is None)
    spend_before = _load(cpath)["spend"].get("2026-08", 0)
    check("failed calls never counted as spend", spend_before == 0)
    rows6 = trends_open(seeds=["oddseed"], budget=6,
                        cache=os.path.join(tmp, "empty.json"),
                        _fetch=lambda s: _EMPTY, _today=date(2026, 8, 1))
    check("no-data seed handled (billed, no rows, no crash)", rows6 is None)
    check("corrupt cache tolerated",
          _load(os.path.join(tmp, "nonexistent.json"))["queries"] == {})

    print("=" * 64)
    print("{} FAILED".format(len(fails)) if fails else "ALL CHECKS PASSED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
