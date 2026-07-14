#!/usr/bin/env python3
"""
NHSBSA English Prescribing Dataset (EPD) - the deep-history replacement for T4.

Full write-up, ranking and the ADHD/GLP-1 test: sources_FINDINGS.md.

WHY
---
T4 reads OpenPrescribing, which serves only the last 60 months. Inside that window
a niche compounding for eight years and one that started rising last spring look
the same - and "how EARLY am I seeing this" is the only question the radar asks.
NHSBSA publishes the same prescribing data itself, back to January 2014, no key.

It also does what OpenPrescribing cannot: the whole month is queryable, so we can
ask the server for EVERY chemical at once and rank the formulary by growth. That
is a rising-drug detector for drugs nobody put on a list - the only auto-discovery
signal in the radar that sees DEMAND rather than ENTRY.

VERIFIED LIVE AGAINST THE REAL API, 13 JUL 2026
-----------------------------------------------
  https://opendata.nhsbsa.net/api/3/action/datastore_search_sql
      ?resource_id=<TABLE>&sql=<SQL>

No key, no account, answers a datacentre IP. Working SQL primitives (all tested):
backtick table quoting, SUM(), WHERE on the code, aliasing, GROUP BY <ordinal>,
GROUP BY 1,2, LIMIT. Response is nested TWICE - result.result.records:

  {"success": true, "result": {"success": "true",
     "result": {"records": [{"c": "0404000U0", "i": 120226}]}}}

TWO TABLES, AND THE SILENT TRAP BETWEEN THEM
--------------------------------------------
NHSBSA retired the original EPD in mid-2025 and replaced it with a SNOMED-coded
one. Same column NAME, different MEANING either side of July 2025:

  <= 2025-06   EPD_<YYYYMM>         `bnf_chemical_substance`      = the CODE
  >= 2025-07   EPD_SNOMED_<YYYYMM>  `bnf_chemical_substance`      = the NAME
                                    `bnf_chemical_substance_code` = the CODE

Query the new table with the old column and you do not get an error. You get
{"records": [{"i": null}]} - a null that a careless module turns into a zero, and
the dashboard then reports that ADHD prescribing collapsed to nothing. Verified by
doing it:

  EPD_SNOMED_202604 WHERE bnf_chemical_substance      = '0404000U0'  ->  null
  EPD_SNOMED_202604 WHERE bnf_chemical_substance_code = '0404000U0'  ->  120,226

Defence: every month is checked against a CANARY chemical (sertraline - boring,
huge, stable). A month without a plausible canary is REJECTED and left absent, so
its growth reads None. A month is never allowed to be silently zero. Same class of
bug as the dead BNF codes drugs.py exists to keep out.

LAG AND COVERAGE
----------------
Monthly, ~the 20th, two months in arrears (NHSBSA: "January data is published in
March"). Verified: on 13 Jul 2026 the newest table that resolves is
EPD_SNOMED_202604 (April 2026); May does not exist yet. Real lag ~2.5 months, NOT
the 12 months the radar currently assumes for T4.

England only, primary care, dispensed in the community. Cannot see private
prescriptions. Excludes dental prescribing and anything under a Patient Group
Direction (Pharmacy First, contraception, smoking cessation, flu jabs). It is a
proxy for how big a CONDITION is getting, not for what is being paid for privately.

COST: one request per month, all chemicals at once. A published month is immutable,
so it is cached forever. Steady state is one request a month.

Stdlib only: urllib, json, os, math, datetime.
"""

import os
import json
import math
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://opendata.nhsbsa.net/api/3/action/datastore_search_sql"
UA = {"User-Agent": "Mozilla/5.0 (compatible; healthcare-radar)"}

HISTORY_FILE = os.environ.get("EPD_HISTORY_PATH", "data/epd_history.json")

# First month NHSBSA publishes at all (verified: EPD_201401 answers).
FIRST_MONTH = (2014, 1)

# First month of the SNOMED-era table and its different schema (verified).
SNOMED_FROM = (2025, 7)

# Sertraline. Chosen because it is boring, huge and stable - exactly what a canary
# should be. If a month does not show at least this many items of it, we did not
# really read that month, whatever the HTTP status said.
CANARY_CODE = "0403030Q0"
CANARY_MIN = 100000

# The lags the dashboard needs. 60 = the five-year view OpenPrescribing tops out at;
# we keep it so the two tiers can be compared like for like.
LAGS = (0, 1, 3, 12, 60)

# Politeness / Actions budget. A month is immutable, so a partial backfill is not a
# failure - it just means the deep history fills in over the next few runs.
MAX_FETCHES_PER_RUN = 8

# A month that FAILS (404 / timeout / null-trap) is tombstoned for this many days
# under hist["_failed"]. Without it, absence and failure looked identical to
# refresh(), so a permanently-missing month was refetched EVERY day - up to
# 8 x 120s timeouts of pure hang, spending the whole budget on the same doomed keys.
FAILED_RETRY_DAYS = 7
FAILED_KEY = "_failed"

# A "rising chemical" must clear this in the latest month before we will show it.
# Below it, percentage growth is noise: 3 items becoming 9 is +200% and means nothing.
DISCOVERY_MIN_ITEMS = 2000

# Codes that are not medicines (dressings, appliances, stoma products). They are in
# the data and they are not niches. Real BNF chemical codes are 9 characters.
def _is_chemical(code):
    return isinstance(code, str) and len(code) == 9


# --------------------------------------------------------------------- month keys
def _key(y, m):
    return "%04d-%02d" % (y, m)


def _shift(key, back):
    y, m = int(key[:4]), int(key[5:7])
    i = y * 12 + (m - 1) - back
    return _key(i // 12, i % 12 + 1)


def _tuple(key):
    return (int(key[:4]), int(key[5:7]))


def _pct(now, then):
    if now is None or then in (None, 0):
        return None
    return (now / float(then) - 1.0) * 100.0


# ------------------------------------------------------- table + column resolution
def resource_for(key):
    """Which table holds this month, and which column carries the CHEMICAL CODE.

    Returns (resource_id, code_column, name_column_or_None).
    The name column only exists on the SNOMED-era table; on the old table we never
    ask for a name, because we have not verified what it is called and guessing a
    column name is how you get a silent empty series.
    """
    ym = _tuple(key)
    stamp = "%04d%02d" % ym
    if ym >= SNOMED_FROM:
        return ("EPD_SNOMED_" + stamp, "bnf_chemical_substance_code",
                "bnf_chemical_substance")
    return ("EPD_" + stamp, "bnf_chemical_substance", None)


def sql_for(key):
    """Every chemical in one month, summed server-side. One request per month."""
    table, code_col, name_col = resource_for(key)
    if name_col:
        return ("SELECT %s c,%s n,SUM(items) i FROM `%s` GROUP BY 1,2"
                % (code_col, name_col, table))
    return "SELECT %s c,SUM(items) i FROM `%s` GROUP BY 1" % (code_col, table)


def url_for(key):
    table, _c, _n = resource_for(key)
    return BASE + "?" + urllib.parse.urlencode({"resource_id": table,
                                                "sql": sql_for(key)})


# ------------------------------------------------------------------------ parsing
def parse_records(payload):
    """Pull result.result.records out of a CKAN datastore_search_sql response.

    Returns (counts, names). Raises ValueError if the response is not a success,
    so a 200-with-an-error-body can never be mistaken for an empty month.
    """
    if not isinstance(payload, dict) or not payload.get("success"):
        raise ValueError("API did not report success")
    inner = (payload.get("result") or {}).get("result")
    if not isinstance(inner, dict):
        # This is the shape you get from e.g. {"result": {"message": "resource_id
        # is mandatory"}} - a 200 that is really an error.
        raise ValueError("no result.result in response")
    recs = inner.get("records")
    if not isinstance(recs, list):
        raise ValueError("no records list")

    counts, names = {}, {}
    for r in recs:
        code = r.get("c")
        items = r.get("i")
        if not _is_chemical(code) or items is None:
            continue
        try:
            counts[code] = counts.get(code, 0) + int(items)
        except (TypeError, ValueError):
            continue
        n = r.get("n")
        if n and code not in names:
            names[code] = str(n).strip()
    return counts, names


def canary_ok(counts):
    """Did we really read this month, or did we read a column that means something
    else and get a table full of nulls?"""
    return counts.get(CANARY_CODE, 0) >= CANARY_MIN


# ------------------------------------------------------------------------ fetching
def _get_json(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_month(key, getter=None):
    """One month, every chemical. Returns (counts, names) or None.

    None means 'we do not know', never 'it was zero'. Callers must keep that
    distinction: an absent month makes growth None, it does not make growth -100%.
    """
    get = getter or _get_json
    try:
        payload = get(url_for(key))
        counts, names = parse_records(payload)
    except Exception:
        return None
    if not canary_ok(counts):
        return None
    return counts, names


# ------------------------------------------------------------------------- history
def _load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save(path, obj):
    """Best-effort. The cache is a speed-up, not a dependency: if the disk is
    read-only we still have the data in memory for this run, and taking the whole
    tier down over a failed write would be a worse bug than refetching."""
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(obj, fh, sort_keys=True)
        return True
    except Exception:
        return False


def latest_published(today=None):
    """Newest month that should exist. NHSBSA runs two months in arrears and loads
    around the 20th, so before the 20th we do not even ask for the newest month.
    Verified on 13 Jul 2026: April 2026 was the newest table that resolved."""
    t = today or date.today()
    back = 2 if t.day >= 20 else 3
    return _shift(_key(t.year, t.month), back)


def wanted_months(latest):
    """The months we need, most valuable first.

    The five lag months buy the dashboard's growth figures. The January anchors buy
    the long view - the thing OpenPrescribing structurally cannot give us. Anchors
    are fetched a few per run and then cached forever.
    """
    need = [_shift(latest, b) for b in LAGS]
    anchors = ["%04d-01" % y for y in range(FIRST_MONTH[0], _tuple(latest)[0] + 1)]
    out = []
    for k in need + anchors:
        if _tuple(k) >= FIRST_MONTH and _tuple(k) <= _tuple(latest) and k not in out:
            out.append(k)
    return out


def refresh(latest, hist, getter=None, budget=MAX_FETCHES_PER_RUN, today=None):
    """Fetch what is missing, up to the budget. Cached months are never refetched -
    a published month is immutable.

    A month that fails is recorded under hist[FAILED_KEY] with a retry-after date and
    is not asked for again until that date. A doomed month must cost one attempt a
    week, not two minutes of hang every day. Success clears the tombstone, so a month
    that was merely published late is picked up on the next retry."""
    today = today or date.today()
    failed = hist.get(FAILED_KEY)
    if not isinstance(failed, dict):
        failed = {}
    fetched = 0
    for key in wanted_months(latest):
        if key in hist:
            continue
        retry_after = failed.get(key)
        if retry_after and today.isoformat() < retry_after:
            continue
        if fetched >= budget:
            break
        got = fetch_month(key, getter)
        fetched += 1
        if got is None:
            failed[key] = (today + timedelta(days=FAILED_RETRY_DAYS)).isoformat()
            continue
        failed.pop(key, None)
        counts, names = got
        hist[key] = {"counts": counts, "names": names}
    if failed:
        hist[FAILED_KEY] = failed
    else:
        hist.pop(FAILED_KEY, None)
    return hist, fetched


# ---------------------------------------------------------------------- row building
def _items(hist, key, code):
    m = hist.get(key)
    if not m:
        return None
    return (m.get("counts") or {}).get(code)


def _niche_items(hist, key, codes):
    """Sum a niche's drugs for one month. If the month is absent, None - NOT zero."""
    m = hist.get(key)
    if not m:
        return None
    counts = m.get("counts") or {}
    return sum(counts.get(c, 0) for c in codes)


def build_rows(hist, niche_codes, latest):
    """Tracked niches: one row each, same shape as every other tier."""
    rows = []
    for niche in sorted(niche_codes):
        codes = niche_codes[niche]
        now = _niche_items(hist, latest, codes)
        if not now:
            continue
        g = {}
        for b in LAGS[1:]:
            g[b] = _pct(now, _niche_items(hist, _shift(latest, b), codes))
        rows.append({
            "name": niche,
            "niche": niche,
            "latest": now,
            "g1": g[1], "g3": g[3], "g12": g[12], "g60": g[60],
            "accel": (g[3] - g[12]) if (g[3] is not None and g[12] is not None) else None,
            "kind": "tracked",
            "period": latest,
        })
    rows.sort(key=lambda r: (r["g12"] is None, -(r["g12"] or 0)))
    return rows


def build_discovery(hist, latest, known_codes):
    """Rising chemicals nobody put on a list.

    This is the bit OpenPrescribing cannot do. We already hold every chemical for
    every cached month, so ranking the whole formulary by growth costs nothing
    extra. Anything already tracked is excluded - by definition it is not a
    discovery.

    Ranked by a z-score, not a percentage, for the same reason discovery2.py does:
    over ~2,800 chemicals a percentage threshold is a coin flip, and small counts
    will hand you a dozen fake risers every run.
    """
    cur = hist.get(latest)
    if not cur:
        return []
    counts = cur.get("counts") or {}
    names = cur.get("names") or {}
    prev = (hist.get(_shift(latest, 12)) or {}).get("counts")
    if not prev:
        return []

    rows = []
    for code, now in counts.items():
        if code in known_codes or now < DISCOVERY_MIN_ITEMS:
            continue
        then = prev.get(code, 0)
        if now <= then:
            continue
        z = (now - then) / math.sqrt(now + then) if (now + then) else 0.0
        rows.append({
            "name": names.get(code) or code,
            "niche": None,                      # it is not in the taxonomy - that is the point
            "latest": now,
            "g1": _pct(now, _items(hist, _shift(latest, 1), code)),
            "g3": _pct(now, _items(hist, _shift(latest, 3), code)),
            "g12": _pct(now, then),
            "g60": _pct(now, _items(hist, _shift(latest, 60), code)),
            "accel": None,
            "kind": "discovery",
            "code": code,
            "z": z,
            "period": latest,
        })
    for r in rows:
        if r["g3"] is not None and r["g12"] is not None:
            r["accel"] = r["g3"] - r["g12"]
    rows.sort(key=lambda r: -r["z"])
    return rows


# ------------------------------------------------------------------------------ main
def epd(niche_codes=None, getter=None, history_file=None):
    """Returns rows, or None if the source cannot be reached.

      [{"name":..., "niche":..., "latest":..., "g1":..., "g3":..., "g12":...}, ...]

    Tracked-niche rows carry kind="tracked"; rising chemicals nobody listed carry
    kind="discovery" and niche=None.
    """
    if niche_codes is None:
        try:
            import drugs                                    # the radar's verified codes
            niche_codes = drugs.NICHE_CODES
        except Exception:
            return None

    path = history_file or HISTORY_FILE
    hist = _load(path)
    latest = latest_published()

    hist, fetched = refresh(latest, hist, getter)
    if fetched and hist:
        _save(path, hist)

    # If the newest month is not in yet (NHSBSA slips), fall back to the newest month
    # we actually hold rather than blanking the tier. Keys beginning "_" are
    # bookkeeping (failure tombstones), never month data.
    have = sorted(k for k in hist if not k.startswith("_"))
    if not have:
        return None
    if latest not in hist:
        latest = have[-1]

    known = set()
    for codes in niche_codes.values():
        known.update(codes)

    rows = build_rows(hist, niche_codes, latest)
    if not rows:
        return None
    return rows + build_discovery(hist, latest, known)


# ============================================================== TESTS (no network)
def _tests():
    ok, fail = [], []

    def check(name, cond):
        (ok if cond else fail).append(name)

    # ---- 1. table + column switch at the July-2025 boundary (VERIFIED live)
    check("Jun-2025 -> old table EPD_202506",
          resource_for("2025-06")[0] == "EPD_202506")
    check("Jun-2025 -> code column is bnf_chemical_substance",
          resource_for("2025-06")[1] == "bnf_chemical_substance")
    check("Jul-2025 -> SNOMED table EPD_SNOMED_202507",
          resource_for("2025-07")[0] == "EPD_SNOMED_202507")
    check("Jul-2025 -> code column is bnf_chemical_substance_code",
          resource_for("2025-07")[1] == "bnf_chemical_substance_code")
    check("Apr-2026 -> EPD_SNOMED_202604 (the table verified live)",
          resource_for("2026-04")[0] == "EPD_SNOMED_202604")
    check("old table asks for no name column",
          resource_for("2022-01")[2] is None)

    # ---- 2. the SQL we actually send
    check("old SQL groups by the code only",
          sql_for("2022-01") ==
          "SELECT bnf_chemical_substance c,SUM(items) i FROM `EPD_202201` GROUP BY 1")
    check("SNOMED SQL takes code AND name",
          sql_for("2026-04") ==
          "SELECT bnf_chemical_substance_code c,bnf_chemical_substance n,"
          "SUM(items) i FROM `EPD_SNOMED_202604` GROUP BY 1,2")
    check("url carries resource_id and is encoded",
          "resource_id=EPD_SNOMED_202604" in url_for("2026-04")
          and "%60" in url_for("2026-04"))

    # ---- 3. month arithmetic
    check("shift back 1 crosses the year", _shift("2026-01", 1) == "2025-12")
    check("shift back 12", _shift("2026-04", 12) == "2025-04")
    check("shift back 60 is five years", _shift("2026-04", 60) == "2021-04")
    check("latest_published before the 20th goes back 3",
          latest_published(date(2026, 7, 13)) == "2026-04")
    check("latest_published after the 20th goes back 2",
          latest_published(date(2026, 7, 21)) == "2026-05")

    # ---- 4. parsing the real (doubly-nested) response shape
    good = {"success": True, "result": {"success": "true", "result": {"records": [
        {"c": "0404000U0", "n": "Lisdexamfetamine", "i": 120226},
        {"c": "0403030Q0", "n": "Sertraline hydrochloride", "i": 900000},
        {"c": "2315", "i": 86308},                      # appliance, not a chemical
        {"c": "0601023AW", "n": "Semaglutide", "i": 500000},
    ]}}}
    counts, names = parse_records(good)
    check("parses the doubly-nested records", counts.get("0404000U0") == 120226)
    check("drops non-chemical codes (2315)", "2315" not in counts)
    check("keeps names when present", names.get("0601023AW") == "Semaglutide")

    # a 200 that is really an error must RAISE, not look like an empty month
    try:
        parse_records({"success": True,
                       "result": {"success": "false",
                                  "message": "resource_id is mandatory"}})
        check("200-with-error-body raises", False)
    except ValueError:
        check("200-with-error-body raises", True)

    # ---- 5. THE SILENT-NULL TRAP - the whole reason this module has a canary.
    # This is the literal response the live API gave for the WRONG column on the
    # SNOMED table: a null, not an error.
    nulls = {"success": True, "result": {"success": "true", "result": {"records": [
        {"c": "0404000U0", "i": None},
        {"c": "0403030Q0", "i": None},
    ]}}}
    ncounts, _ = parse_records(nulls)
    check("null items are dropped, not counted as 0", ncounts == {})
    check("canary rejects a month of nulls", not canary_ok(ncounts))
    check("canary passes a real month", canary_ok(counts))
    check("canary rejects a suspiciously thin month",
          not canary_ok({"0403030Q0": 12}))
    check("fetch_month returns None (not zeros) on the null trap",
          fetch_month("2026-04", getter=lambda u: nulls) is None)
    check("fetch_month returns None when the network dies",
          fetch_month("2026-04", getter=_boom) is None)

    # ---- 6. growth maths, using the REAL verified lisdexamfetamine series
    # (England, items/month, straight off the live API on 13 Jul 2026)
    #   Jan-2014     737
    #   Jan-2020  16,460
    #   Jan-2022  27,728
    #   Jun-2025  84,287
    #   Apr-2026 120,226
    hist = {
        "2014-01": {"counts": {"0404000U0": 737, "0403030Q0": 500000}, "names": {}},
        "2021-04": {"counts": {"0404000U0": 22000, "0403030Q0": 800000}, "names": {}},
        "2025-04": {"counts": {"0404000U0": 84000, "0403030Q0": 900000}, "names": {}},
        "2026-01": {"counts": {"0404000U0": 110000, "0403030Q0": 900000}, "names": {}},
        "2026-03": {"counts": {"0404000U0": 115000, "0403030Q0": 900000}, "names": {}},
        "2026-04": {"counts": {"0404000U0": 120226, "0601023AW": 500000,
                               "0403030Q0": 900000, "0999999X9": 9000},
                    "names": {"0404000U0": "Lisdexamfetamine",
                              "0999999X9": "Some New Thing"}},
    }
    nc = {"ADHD": ["0404000U0"], "Weight loss / GLP-1": ["0601023AW"]}
    rows = build_rows(hist, nc, "2026-04")
    adhd = [r for r in rows if r["name"] == "ADHD"][0]
    check("row has the shared shape",
          all(k in adhd for k in ("name", "niche", "latest", "g1", "g3", "g12")))
    check("latest is the real Apr-2026 figure", adhd["latest"] == 120226)
    check("g12 = +43% (84,000 -> 120,226)", abs(adhd["g12"] - 43.13) < 0.1)
    check("g60 spans five years (22,000 -> 120,226)", abs(adhd["g60"] - 446.5) < 1.0)
    check("accel = g3 - g12", abs(adhd["accel"] - (adhd["g3"] - adhd["g12"])) < 1e-9)

    # a niche whose comparison month we never got must read None, not -100%
    gap = {"2026-04": hist["2026-04"]}
    grow = build_rows(gap, nc, "2026-04")[0]
    check("missing history -> g12 is None, never -100%", grow["g12"] is None)

    # ---- 7. discovery: rising chemicals nobody listed
    known = {"0404000U0", "0601023AW"}
    hist["2025-04"]["counts"]["0999999X9"] = 3000
    disc = build_discovery(hist, "2026-04", known)
    codes = [r["code"] for r in disc]
    check("discovery surfaces an untracked riser", "0999999X9" in codes)
    check("discovery excludes tracked codes",
          not (known & set(codes)))
    check("discovery rows are named, not coded",
          disc[0]["name"] == "Some New Thing")
    check("discovery rows carry niche=None (not in the taxonomy)",
          disc[0]["niche"] is None)
    check("discovery row has the shared shape",
          all(k in disc[0] for k in ("name", "niche", "latest", "g1", "g3", "g12")))

    # noise floor: a tiny chemical tripling is not a discovery
    hist["2026-04"]["counts"]["0888888X8"] = 30
    hist["2025-04"]["counts"]["0888888X8"] = 10
    check("tiny counts are below the noise floor",
          "0888888X8" not in [r["code"] for r in build_discovery(hist, "2026-04", known)])

    # ---- 8. the module fails closed
    check("epd() returns None when every fetch fails",
          epd(niche_codes=nc, getter=_boom, history_file="/nonexistent/x.json") is None)

    # ---- 9. wanted_months asks for the growth months FIRST
    w = wanted_months("2026-04")
    check("growth months come before the deep backfill",
          w[:5] == ["2026-04", "2026-03", "2026-01", "2025-04", "2021-04"])
    check("backfill reaches 2014", "2014-01" in w)
    check("never asks for a month before Jan-2014",
          all(_tuple(k) >= FIRST_MONTH for k in w))
    check("never asks for the future",
          all(_tuple(k) <= (2026, 4) for k in w))

    # ---- 10. budget is respected, and a cached month is never refetched
    calls = []

    def counting_getter(url):
        calls.append(url)
        return good

    h2, n2 = refresh("2026-04", {}, counting_getter, budget=3)
    check("refresh stops at the budget", n2 == 3 and len(calls) == 3)
    del calls[:]
    refresh("2026-04", h2, counting_getter, budget=3)
    check("cached months are not refetched", len(calls) == 3)   # 3 NEW ones, not the 3 held

    # ---- 11. failed months are TOMBSTONED, not refetched every day
    t0 = date(2026, 7, 14)
    calls3 = []

    def dead_getter(url):
        calls3.append(url)
        raise IOError("NHSBSA down")

    n_want = len(wanted_months("2026-04"))
    h3, _ = refresh("2026-04", {}, dead_getter, budget=99, today=t0)
    check("every wanted month attempted once on day 1", len(calls3) == n_want)
    check("failed months carry a retry-after date",
          (h3.get(FAILED_KEY) or {}).get("2026-04") == "2026-07-21")
    check("no month entry is created for a failure",
          all(k == FAILED_KEY for k in h3))
    del calls3[:]
    refresh("2026-04", h3, dead_getter, budget=99, today=t0)
    check("inside the window a tombstoned month costs ZERO fetches",
          len(calls3) == 0)
    del calls3[:]
    refresh("2026-04", h3, dead_getter, budget=99, today=date(2026, 7, 21))
    check("on the retry-after date it is tried again", len(calls3) == n_want)
    # the day-21 failures re-tombstoned everything until the 28th
    h4, _ = refresh("2026-04", h3, counting_getter, budget=99, today=date(2026, 7, 28))
    check("a success clears the tombstone",
          "2026-04" not in (h4.get(FAILED_KEY) or {}))
    check("tombstones never read as month data",
          _niche_items({FAILED_KEY: {"2026-04": "2026-07-21"}}, "2026-04",
                       ["0404000U0"]) is None)
    import tempfile as _tf
    _d = _tf.mkdtemp(prefix="epd_t11_")
    _hp = os.path.join(_d, "h.json")
    with open(_hp, "w") as _fh:
        json.dump({FAILED_KEY: {"2099-01": "2099-01-08"},
                   "2026-04": hist["2026-04"]}, _fh)
    _out = epd(niche_codes=nc, getter=_boom, history_file=_hp)
    check("epd never mistakes the _failed record for the latest month",
          _out is not None and all(r.get("period") == "2026-04" for r in _out))

    print("\n%d passed, %d failed" % (len(ok), len(fail)))
    for f in fail:
        print("  FAIL  " + f)
    if not fail:
        print("  PASS  all %d" % len(ok))
    return not fail


def _boom(url):
    raise IOError("no network")


def _main():
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(0 if _tests() else 1)
    out = epd()
    if out is None:
        print("EPD: unreachable")
        return
    for r in out[:20]:
        print("%-9s %-34s %9s  g12=%s" % (
            r["kind"], r["name"][:34], r["latest"],
            "n/a" if r["g12"] is None else "%+.0f%%" % r["g12"]))


if __name__ == "__main__":
    _main()
