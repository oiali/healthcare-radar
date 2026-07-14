#!/usr/bin/env python3
"""
PANEL - the ADOPTION sensor.  Everything else in this radar is an ENTRY sensor.

THE FLAW THIS FIXES
-------------------
Every supply signal the radar currently has is NAME-MINING: new company
incorporations (Companies House), new clinic registrations (CQC). Both see the
moment somebody ARRIVES. Neither can see an operator who was already here and
started doing something new.

    An existing clinic that adds a service line files no company and registers
    no CQC location. It changes a page on its website.

That event is invisible to name-mining, and it is plausibly how ADHD actually
spread through UK private healthcare: existing psychiatrists, existing private
GP groups and existing mental-health clinics ADDING an assessment service - not
founders incorporating "ADHD Ltd". If that is right, then every supply sensor we
own catches the SECOND wave (the specialists who set up to serve a market that
already exists) and misses the first.

This module fixes a cohort of real UK private clinics and watches what SERVICES
they add, month by month, backfilled from the Internet Archive. That is
ADOPTION, not entry. And because the Archive holds the past, this sensor has
history on the day it is switched on - it does not need to wait three years to
become useful.

THE COHORT (data/panel_cohort.json)  - and why it is FROZEN
-----------------------------------------------------------
Source: the CQC "care directory" CSV. VERIFIED 14 Jul 2026 against
https://www.cqc.org.uk/about-us/transparency/using-cqc-data - "The file does not
contain email addresses. It does include links to websites". Header (verified):

    Name | Also known as | Address | Postcode | Phone number |
    Service's website (if available) | Service types | Date of latest check |
    Specialisms/services | Provider name | Local authority | Region |
    Location URL | CQC Location ID | CQC Provider ID

NOTE, because it matters and the rest of the repo does not do this: that is a
DIFFERENT FILE from the one investability.py / discovery2.py parse. They read
HSCA_Active_Locations.ods, which has the sector and the registration date but NO
website column. The care directory CSV has the websites but NO sector column. So
this module reads BOTH and joins them on CQC Location ID: websites from the CSV,
sector from the .ods. The .ods is already on disk every run (pull_and_build
downloads it), so the join is free.

Why the sector join is not optional: the care directory contains ~6,000 NHS GP
surgeries whose service type ("Doctors treatment service") is IDENTICAL to a
private GP clinic's. Without the sector column they would swamp the cohort and
the panel would be measuring the NHS. The .ods sector column separates them
("Primary Medical Services" = NHS GP; "Independent Healthcare Org" = private).
If the .ods is unavailable the module still builds a cohort, but it says loudly
that it is degraded and it applies a cruder NHS guard.

THE COHORT IS FROZEN ON FIRST BUILD. This is the whole methodological point. If
the cohort moves - if it is rebuilt from a fresh CQC file every month - then a
term's adopter count changes because the MEMBERSHIP changed, and you cannot tell
that apart from adoption. A rising line would mean nothing. So: build once,
persist, reuse. Rebuilding is an explicit act (--rebuild) and it resets the
history, and it should be done rarely and deliberately.

THE ARCHIVE (verified 14 Jul 2026, and one thing NOT verified)
--------------------------------------------------------------
  CDX index   http://web.archive.org/cdx/search/cdx?url=<site>&matchType=prefix
              &output=json&fl=timestamp,original&filter=statuscode:200
              &filter=mimetype:text/html&collapse=urlkey&from=<year>
  Snapshot    https://web.archive.org/web/<timestamp>id_/<url>
              ("id_" = the ORIGINAL bytes: no Archive banner, no rewritten links)

Free, keyless, machine-readable, and the data is under the Internet Archive's
terms of use, which permit this kind of research reading. The CDX endpoint is
the documented public index (github.com/internetarchive/wayback, wayback-cdx-
server). Robots position: the Archive stopped honouring robots.txt for playback
in 2017; the /cdx/search endpoint still applies exclusions. Either way we are
READING a public index, politely, at a low rate. We do not crawl the live
clinic sites at all - only the Archive's copy - so no clinic's robots.txt is
engaged and no clinic's server is touched.

RATE LIMITS - the part that dictates the whole design:
  * The Archive rate-limits hard. Community-documented limits have tightened:
    the CDX endpoint is now around 24-60 requests/minute.
  * Exceed it and you get HTTP 429. IGNORE the 429 and you get FIREWALL-BANNED
    for an hour, doubling on each repeat.
  * NOT VERIFIED: I could not reach web.archive.org from this sandbox at all -
    two fetches (CDX and the availability API) both timed out at 180s from a
    datacentre IP. That is either the Archive being slow or the Archive being
    hostile to datacentre traffic. GitHub Actions runners ARE datacentre IPs.
    So the module must assume the Archive can be slow, blocked, or absent, and
    it must still produce yesterday's answer when that happens. It does: every
    fetch is cached to disk, a 429/403 stops the run and sets a COOLDOWN, and
    panel() computes from the cache regardless.

Therefore: no retries, no parallelism, one request every PANEL_SLEEP seconds
(default 2.0 -> 30/minute, half the documented limit), a per-run budget, and a
persistent cache so a run that is cut off loses nothing.

THE SENSOR - and why it is URL PATHS first, page text second
------------------------------------------------------------
The obvious design is: fetch each clinic's homepage once a month for 36 months
and read the text. Cost: 300 clinics x 36 months = 10,800 fetches. At the
polite rate that is SIX HOURS of wall clock, it would have to be spread over
weeks, and it only sees the homepage anyway.

The cheap design is better AND stronger. One CDX query per clinic, with
matchType=prefix, returns EVERY URL the Archive ever captured on that domain,
with the timestamp of its first capture. A clinic that adds an ADHD service
creates a page at /services/adhd-assessment - and the URL PATH IS THE SERVICE
NAME. So:

    1 request per clinic (not 36) -> a 300-clinic cohort backfills in ~300
    requests, about 10 minutes, ONE run. And "first_seen" falls out for free,
    which is the number we actually care about.

Page text (--text) is the second sensor, off by default: it costs a fetch per
clinic per month and it catches services that never get their own URL (listed
on one long "our treatments" page). The two share the same term vocabulary and
the same distinct-adopter counting, and their evidence is merged.

TWO VOCABULARIES
  * the 25 known niches, via taxonomy.niche_of -> a per-niche adoption count.
  * an OPEN vocabulary: every n-gram that maps to NO known niche. This is the
    only sensor in the system that can see a service nobody pre-listed being
    taken up by existing providers. Junk dies at the gate: an open term must be
    adopted by MIN_ADOPTERS (3) DISTINCT clinics before it is emitted, and one
    clinic's idiosyncratic page slug never clears that.

WHAT IS COUNTED: DISTINCT CLINICS, never mentions. A clinic with nine ADHD pages
is one adopter. Ranked by ACCELERATION in distinct adopters (adopters added in
the last 12 months, minus adopters added in the 12 months before that), because
a service that 40 clinics have had for a decade is not news.

THE LEFT-CENSORING CORRECTION (the trap that would fake a boom)
---------------------------------------------------------------
The Archive's first capture of a URL is not the date the page appeared. It is
the date the ARCHIVE FIRST LOOKED. If a clinic's site was first crawled in 2021
and it had an ADHD page since 2015, a naive reading records "adopted ADHD in
2021" - and a cohort of clinics that the Archive happened to start crawling in
2021 would manufacture an ADHD boom out of nothing.

So: for each clinic we compute first_archived = the earliest capture of ANY page
on that domain. Any term whose first capture falls within GRACE (3) months of
that date is treated as PRE-EXISTING - it counts in the base, never as a new
adopter. Only a term that appears on a domain the Archive was ALREADY watching
counts as an adoption. That is a real correction and it is conservative: it
throws away genuine early adoptions to avoid inventing fake ones.

The residual error runs the other way and must be stated: the Archive crawls
deep pages LATER than it crawls homepages, so first_seen LAGS true adoption,
typically by weeks to months. This sensor is early relative to prescribing data
and to CQC registrations. It is not instant.

WHAT THIS STILL CANNOT SEE
  * A clinic that adds a service without adding a page (or on a page whose slug
    is /services/1a2b3c). Invisible.
  * Clinics with no website, or dead since (survivorship: the cohort is TODAY's
    clinics, so failures are absent).
  * A service listed only in an image, a PDF price list, or a JS-rendered menu.
  * Blogs and news are EXCLUDED deliberately (/blog/adhd-what-to-expect is
    content marketing, not a service line). This costs some real signal.

Degrades to None on any failure. Never crashes the build. Stdlib only.

    python3 panel.py --selftest    synthetic fixtures, no network
    python3 panel.py --cohort      build/refresh the frozen cohort
    python3 panel.py --backfill    spend one run's budget on the Archive
    python3 panel.py --adhd-test   THE decisive run: does the panel see ADHD?
"""

import os
import re
import io
import sys
import csv
import json
import time
import zipfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from collections import defaultdict
from datetime import date, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

DIAG = {}

UA = {"User-Agent": "uk-healthcare-radar/1.0 (research; low-rate; stdlib urllib)"}

CQC_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
CDX_URL = "http://web.archive.org/cdx/search/cdx"
WB_URL = "https://web.archive.org/web/"

DATA_DIR = os.environ.get("PANEL_DATA_DIR", "data")
COHORT_FILE = os.path.join(DATA_DIR, "panel_cohort.json")
PATHS_FILE = os.path.join(DATA_DIR, "panel_paths.json")
SNAPS_FILE = os.path.join(DATA_DIR, "panel_snapshots.json")
STATE_FILE = os.path.join(DATA_DIR, "panel_state.json")

# ------------------------------------------------------------------ the budget
# THE REAL NUMBERS, so nobody discovers them in production:
#   paths mode  : 1 CDX request per clinic. 300 clinics = 300 requests.
#                 At PANEL_SLEEP=2.0s that is 10 minutes. The whole backfill is
#                 ONE run. Thereafter a domain is re-indexed only every
#                 REFRESH_DAYS (30), so steady state is ~10 requests a day.
#   text mode   : 1 CDX + 1 fetch per clinic per month. 300 x 36 = 10,800
#                 fetches = 6 HOURS at the polite rate. That does NOT run daily
#                 and it does not run in one job. With PANEL_TEXT_BUDGET=400 it
#                 fills in over ~27 runs and then only tracks forward (300
#                 fetches a month). It is OFF by default for exactly this
#                 reason. Transfer is ~300KB a page: the full text backfill
#                 moves ~3GB through the Archive. Do not do that casually.
COHORT_SIZE = int(os.environ.get("PANEL_COHORT_SIZE", "300"))
CDX_BUDGET = int(os.environ.get("PANEL_CDX_BUDGET", "400"))
TEXT_BUDGET = int(os.environ.get("PANEL_TEXT_BUDGET", "0"))
SLEEP = float(os.environ.get("PANEL_SLEEP", "2.0"))
IA_TIMEOUT = int(os.environ.get("PANEL_TIMEOUT", "30"))
REFRESH_DAYS = int(os.environ.get("PANEL_REFRESH_DAYS", "30"))
MIN_ADOPTERS = int(os.environ.get("PANEL_MIN_ADOPTERS", "3"))
MAX_BYTES = 3_000_000
MAX_ERRORS = 8

WINDOW = 12          # months in the "recent" window

# A clinic that already had the term when the Archive first crawled it. Its
# adoption DATE is unknown (left-censored), so it belongs in the BASE - it must
# never be counted as a new adopter, and it must never be dropped either (it
# genuinely has the service). This sentinel sorts before every real month, which
# is exactly the arithmetic we want: in every window it lands in the base.
CENSORED_YM = "0000-00"
GRACE = 3            # months of archive coverage before a term can count as NEW
CDX_FROM_YEAR = 2018
MAX_ROWS = 4000      # CDX rows per domain

# 429/403 -> the Archive is telling us to stop. Stop, and stay stopped: ignoring
# a 429 is what escalates to an hour-long firewall ban that doubles each time.
COOLDOWN_BASE = 3600


# ================================================================== small utils
def _load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def _save(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(obj, fh)
        os.replace(tmp, path)
        return True
    except Exception as e:
        DIAG.setdefault("write_errors", []).append("%s: %r" % (path, e))
        return False


def _get_text(url, timeout=45):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        DIAG.setdefault("http_errors", []).append("%s: %r" % (url[:60], e))
        return None


def _download(url, path, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return path


def _ym(ts):
    """Wayback timestamp '20220317104501' -> '2022-03'."""
    ts = str(ts or "")
    return (ts[:4] + "-" + ts[4:6]) if len(ts) >= 6 and ts[:6].isdigit() else None


def _ymi(ym):
    return int(ym[:4]) * 12 + (int(ym[5:7]) - 1)


def _ym_add(ym, delta):
    i = _ymi(ym) + delta
    return "%04d-%02d" % (i // 12, i % 12 + 1)


def _ym_now(anchor=None):
    d = anchor or date.today()
    return "%04d-%02d" % (d.year, d.month)


def _days_since(iso):
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 10 ** 6


# ============================================== THE COHORT: CQC care directory
# Hosts that are not a clinic's own site. A clinic whose "website" is its
# Facebook page tells us nothing about its service pages, and an nhs.uk address
# means the location is NHS whatever its service type says.
JUNK_HOSTS = (
    "nhs.uk", "gov.uk", "cqc.org.uk", "nhs.wales", "hscni.net",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "tiktok.com", "pinterest.com", "google.com", "google.co.uk",
    "yell.com", "yelp.com", "yelp.co.uk", "tripadvisor.co.uk", "doctify.com",
    "topdoctors.co.uk", "trustpilot.com", "bing.com", "example.com",
)

# CQC "Service types" that mean SOCIAL CARE or a custodial/education setting.
# None of these is a private-pay clinic that adds service lines to a website.
SOCIAL_TYPES = (
    "care home service", "domiciliary care", "supported living", "shared lives",
    "extra care housing", "residential substance misuse", "specialist college",
    "hospice", "prison healthcare", "nursing agency", "sheltered housing",
    "community based services for people who misuse substances",
)

# ...and the ones that ARE a clinic. Used ONLY as the degraded fallback when the
# .ods sector column is unavailable; the sector join is the real filter.
CLINICAL_TYPES = (
    "doctors consultation service", "doctors treatment service", "dental service",
    "diagnostic and screening service", "acute services", "mobile doctors service",
    "remote clinical advice service", "community healthcare service",
    "rehabilitation services", "slimming clinics", "clinic",
    "hospital services for people with mental health needs",
    "community based services for people with mental health needs",
)

# The .ods sector labels we keep. "Independent Healthcare Org" is the private
# sector proper. "Primary Dental Care" is kept because a dental practice is a
# private-pay business that visibly adds service lines (Invisalign, facial
# aesthetics, implants) - it is one of the best adoption sensors in the file.
# Everything else goes: "Primary Medical Services" is NHS general practice,
# "NHS Healthcare Organisation" is a trust, "Social Care Org" is social care,
# "Independent Ambulance" is not a clinic.
ALLOW_SECTORS = ("independent healthcare", "primary dental care")

NHS_NAME = re.compile(
    r"\b(nhs|foundation trust|nhs trust|integrated care board|health board|"
    r"clinical commissioning|ccg|icb)\b", re.I)


def _norm_header(cells):
    out = []
    for c in cells or []:
        c = (c or "").replace("’", "'").strip().lower()
        out.append(c if 0 < len(c) < 80 else "")
    return out


def _resolve_dir_columns(header):
    """Map the care directory header -> indices BY NAME, never by position.

    CQC has renamed columns before and will again. Exact match first, then an
    all-substrings-present fallback, so "Service's website (if available)" ->
    "Website" still resolves. Returns {} if the two load-bearing columns
    (website, name) are absent - better to return nothing than a cohort built
    from the wrong column.
    """
    low = _norm_header(header)

    def exact(*names):
        for n in names:
            if n in low:
                return low.index(n)
        return None

    def fuzzy(*subs):
        for j, c in enumerate(low):
            if c and all(s in c for s in subs):
                return j
        return None

    def find(names, subs):
        j = exact(*names)
        return j if j is not None else fuzzy(*subs)

    cols = {
        "name": find(("name", "location name"), ("name",)),
        "website": find(("service's website (if available)", "service's website",
                         "website"), ("website",)),
        "types": find(("service types", "service type"), ("service", "type")),
        "specialisms": find(("specialisms/services", "specialisms"), ("specialism",)),
        "prov_name": find(("provider name",), ("provider", "name")),
        "region": find(("region",), ("region",)),
        "postcode": find(("postcode", "post code"), ("post", "code")),
        "loc_id": find(("cqc location id", "location id"), ("location", "id")),
        "prov_id": find(("cqc provider id", "provider id"), ("provider", "id")),
    }
    if cols["website"] is None:
        cols["website"] = fuzzy("web")
    if cols["website"] is None or cols["name"] is None:
        return {}
    return cols


def directory_url(html=None):
    """Scrape CQC for the care directory CSV (or its zip). None if unreachable."""
    html = html if html is not None else _get_text(CQC_PAGE)
    if not html:
        return None
    for pat in (r'href="([^"]*CQC_directory\.csv)"', r'href="([^"]*CQC_directory\.zip)"',
                r'href="([^"]*directory[^"]*\.csv)"'):
        m = re.search(pat, html, re.I)
        if m:
            u = m.group(1)
            return u if u.startswith("http") else "https://www.cqc.org.uk" + u
    return None


def directory_rows(path):
    """Yield rows from the care directory csv, or from the csv inside its zip."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not names:
                return
            with z.open(names[0]) as fh:
                wrapped = io.TextIOWrapper(fh, encoding="utf-8-sig",
                                           errors="replace", newline="")
                for row in csv.reader(wrapped):
                    yield row
        return
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.reader(fh):
            yield row


def sector_map(rows=None, path=None):
    """{CQC Location ID: sector} from the HSCA .ods. None if unavailable.

    This is the join that keeps 6,000 NHS GP surgeries out of a panel of PRIVATE
    clinics. investability.py already owns the .ods parser and the column
    resolver; both are imported, never reimplemented.
    """
    try:
        from investability import ods_rows, _resolve_columns
    except Exception as e:
        DIAG["sector_map"] = "investability.py not importable: %r" % (e,)
        return None
    if rows is None:
        path = path or os.environ.get("CQC_ODS_PATH") or ""
        if not path:
            cached = os.path.join(tempfile.gettempdir(), "cqc.ods")
            if os.path.exists(cached) and os.path.getsize(cached) > 1_000_000:
                path = cached
        if not path or not os.path.exists(path):
            DIAG["sector_map"] = "no .ods on disk (set CQC_ODS_PATH)"
            return None
        try:
            rows = ods_rows(path)
        except Exception as e:
            DIAG["sector_map"] = "ods parse failed: %r" % (e,)
            return None

    cols = None
    out = {}
    for _sheet, row in rows:
        if cols is None:
            if "location id" not in [(c or "").strip().lower() for c in row]:
                continue
            cols = _resolve_columns(row)
            if not cols or cols.get("loc_id") is None or cols.get("sector") is None:
                DIAG["sector_map"] = "ods header has no location id / sector column"
                return None
            continue
        i, j = cols["loc_id"], cols["sector"]
        if len(row) <= max(i, j):
            continue
        lid = (row[i] or "").strip()
        if lid:
            out[lid] = (row[j] or "").strip()
    DIAG["sector_map"] = "%d locations" % len(out)
    return out or None


def _domain(url):
    """A clinic's website -> its host, or None if it is not usable as one."""
    u = (url or "").strip()
    if not u or u.lower().startswith("mailto"):
        return None
    if "://" not in u:
        u = "http://" + u
    try:
        host = urllib.parse.urlsplit(u).netloc.lower()
    except Exception:
        return None
    host = host.split("@")[-1].split(":")[0].strip()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or " " in host:
        return None
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return None
    for j in JUNK_HOSTS:
        if host == j or host.endswith("." + j):
            return None
    return host


def _keep(row, cols, smap):
    """Is this care-directory row an independent private clinic with a website?

    Returns (domain, reason_rejected). Exactly one of the two is None.
    """
    def cell(k):
        j = cols.get(k)
        return (row[j] or "").strip() if (j is not None and j < len(row)) else ""

    dom = _domain(cell("website"))
    if not dom:
        return None, "no usable website"
    if NHS_NAME.search(cell("prov_name") or "") or NHS_NAME.search(cell("name") or ""):
        return None, "NHS provider"

    types = (cell("types") or "").lower()
    if any(t in types for t in SOCIAL_TYPES):
        return None, "social care"

    lid = cell("loc_id")
    if smap:
        sector = (smap.get(lid) or "").lower()
        if not sector:
            return None, "not in the .ods (archived or NHS-only location)"
        if not any(s in sector for s in ALLOW_SECTORS):
            return None, "sector: " + sector
        return dom, None

    # DEGRADED PATH: no sector column. Keep only rows whose service type is
    # unambiguously clinical, and accept that NHS GP practices will leak in.
    if not any(t in types for t in CLINICAL_TYPES):
        return None, "no clinical service type (degraded filter)"
    return dom, None


def build_cohort(niche_of, path=None, size=None, rows=None, smap=None,
                 rebuild=False, only_niches=None, cohort_file=None):
    """The fixed panel of clinics. Built once, then FROZEN.

    A MOVING COHORT MAKES THE TREND MEANINGLESS. If the membership changes
    between runs, a term's adopter count moves because the panel moved, and no
    amount of arithmetic afterwards can separate that from real adoption. So the
    cohort is written once and reused; --rebuild is an explicit, history-
    resetting act.

    Sampling is DETERMINISTIC and STRATIFIED: round-robin across niches, and
    within a niche by CQC Location ID. Not by size, not by anything correlated
    with being an early adopter - a cohort biased towards big groups would
    measure big groups. Stratification is what guarantees the panel contains
    psychiatry and GP clinics at all, which is the whole ADHD question.

    One clinic = one DOMAIN. A 12-site group publishing one website is ONE
    adopter, not twelve; counting it twelve times would put a single company's
    decision into the "distinct clinics" number twelve times over.
    """
    cohort_file = cohort_file or COHORT_FILE
    if not rebuild:
        old = _load(cohort_file, None)
        if old and old.get("clinics"):
            DIAG["cohort"] = "reused frozen cohort of %d (built %s)" % (
                len(old["clinics"]), old.get("built"))
            return old["clinics"]

    size = size or COHORT_SIZE
    src = path or os.environ.get("CQC_DIRECTORY_PATH") or ""
    if rows is None:
        if not src:
            url = directory_url()
            DIAG["directory_url"] = url or "CQC page fetch failed"
            if not url:
                return None
            src = os.path.join(tempfile.gettempdir(),
                               "cqc_directory" + (".zip" if url.endswith(".zip") else ".csv"))
            try:
                _download(url, src)
            except Exception as e:
                DIAG["download_error"] = repr(e)[:200]
                return None
        try:
            rows = directory_rows(src)
        except Exception as e:
            DIAG["directory_parse_error"] = repr(e)[:200]
            return None

    if smap is None:
        smap = sector_map()
    if not smap:
        DIAG["cohort_degraded"] = (
            "NO SECTOR JOIN. The .ods was unavailable, so private clinics are being "
            "separated from NHS ones by service type and provider name alone. NHS GP "
            "surgeries WILL leak into the cohort. Fix by setting CQC_ODS_PATH.")

    cols = None
    rejected = defaultdict(int)
    seen_dom = {}
    for row in rows:
        if cols is None:
            low = _norm_header(row)
            if not any(("location id" in c or "website" in c) for c in low):
                continue
            cols = _resolve_dir_columns(row)
            if not cols:
                DIAG["fatal"] = "care directory header has no website column"
                return None
            DIAG["directory_cols"] = dict(cols)
            continue

        dom, why = _keep(row, cols, smap)
        if not dom:
            rejected[why] += 1
            continue

        def cell(k):
            j = cols.get(k)
            return (row[j] or "").strip() if (j is not None and j < len(row)) else ""

        name = cell("name")
        types = cell("types")
        niche = niche_of(name) or niche_of(types) or niche_of(cell("specialisms"))
        rec = {
            "domain": dom,
            "url": "http://" + dom + "/",
            "name": name,
            "provider_name": cell("prov_name"),
            "provider_id": cell("prov_id"),
            "location_id": cell("loc_id"),
            "region": cell("region"),
            "niche": niche,
            "types": types[:120],
            "sites": 1,
        }
        cur = seen_dom.get(dom)
        if cur is None:
            seen_dom[dom] = rec
        else:
            # Same website, another location: one clinic, more sites. Keep the
            # record with the lowest location id so the choice is deterministic,
            # and keep any niche either row managed to resolve.
            cur["sites"] += 1
            if not cur["niche"] and niche:
                cur["niche"] = niche
            if rec["location_id"] and rec["location_id"] < (cur["location_id"] or "zz"):
                sites = cur["sites"]
                rec["sites"] = sites
                rec["niche"] = cur["niche"] or niche
                seen_dom[dom] = rec

    if cols is None:
        DIAG["fatal"] = "care directory: no header row found"
        return None
    DIAG["directory_rejected"] = dict(rejected)
    DIAG["directory_clinics_with_site"] = len(seen_dom)
    if not seen_dom:
        return None

    pool = list(seen_dom.values())
    if only_niches:
        want = set(only_niches)
        pool = [c for c in pool if c["niche"] in want]
        if not pool:
            DIAG["fatal"] = "no clinics in the requested niches"
            return None

    # ---- deterministic, stratified round-robin
    by_niche = defaultdict(list)
    for c in pool:
        by_niche[c["niche"] or "(unclassified)"].append(c)
    for k in by_niche:
        by_niche[k].sort(key=lambda c: (c["location_id"] or "", c["domain"]))

    order = sorted(by_niche)
    cohort, i = [], 0
    while len(cohort) < size:
        added = False
        for k in order:
            if i < len(by_niche[k]):
                cohort.append(by_niche[k][i])
                added = True
                if len(cohort) >= size:
                    break
        if not added:
            break
        i += 1

    DIAG["cohort"] = "BUILT %d clinics from %d eligible (%d niches)" % (
        len(cohort), len(pool), len(by_niche))
    _save(cohort_file, {
        "built": date.today().isoformat(),
        "source": src or "in-memory rows",
        "sector_join": bool(smap),
        "size": len(cohort),
        "eligible_pool": len(pool),
        "note": ("FROZEN. Do not rebuild casually: a moving cohort makes every trend "
                 "in the panel uninterpretable, because a term's adopter count would "
                 "then change when the MEMBERSHIP changed. Rebuilding resets history."),
        "clinics": cohort,
    })
    return cohort


# ================================================================== THE ARCHIVE
def _http(url, timeout=None):
    """(status, body) or raises. No retries - a retry against a 429 is what gets
    the IP firewall-banned."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout or IA_TIMEOUT) as r:
            code = getattr(r, "status", None) or r.getcode()
            return code, r.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        return e.code, None


class Archive(object):
    """A polite, budgeted, self-stopping client for the Internet Archive.

    Politeness is not decoration here. The documented behaviour is: exceed the
    rate limit -> 429; keep going after a 429 -> the IP is firewall-banned for an
    hour, and the ban DOUBLES on each repeat. A build that ignores this loses the
    sensor for a day, then two, then four. So: one request every SLEEP seconds,
    a hard per-run budget, and a 429/403 stops the entire run dead and writes a
    cooldown that the NEXT run honours before it opens a socket.
    """

    def __init__(self, fetch=None, sleep=None, budget=None):
        self.fetch = fetch or _http
        self._sleep = sleep if sleep is not None else time.sleep
        self.budget = CDX_BUDGET if budget is None else budget
        self.calls = 0
        self.errors = 0
        self.blocked = False
        self.block_code = None

    @property
    def live(self):
        return (not self.blocked and self.calls < self.budget
                and self.errors < MAX_ERRORS)

    def get(self, url):
        if not self.live:
            return None, None
        if self.calls:
            self._sleep(SLEEP)
        self.calls += 1
        try:
            code, body = self.fetch(url)
        except Exception as e:
            self.errors += 1
            DIAG.setdefault("ia_errors", []).append(repr(e)[:100])
            return None, None
        if code in (429, 403, 503):
            self.blocked = True
            self.block_code = code
            DIAG["ia_blocked"] = (
                "HTTP %s from the Archive. Stopped this run and set a cooldown. "
                "Retrying through a 429 is what turns a throttle into an hour-long "
                "firewall ban." % code)
            return code, None
        if code != 200 or body is None:
            self.errors += 1
            return code, None
        return code, body


def cdx_paths(arc, domain, from_year=CDX_FROM_YEAR, limit=MAX_ROWS):
    """Every HTML URL the Archive ever captured on this domain, with the month of
    its FIRST capture. ONE request for a clinic's entire history.

    collapse=urlkey returns the first row of each URL group, and CDX returns rows
    in (urlkey, timestamp) order - so the row we get is that URL's earliest
    capture. filter=mimetype:text/html drops images and stylesheets, which are
    most of the index and none of the signal.

    -> [(ym, url), ...]   [] = archived but nothing matched   None = call failed
    """
    q = [("url", domain), ("matchType", "prefix"), ("output", "json"),
         ("fl", "timestamp,original"), ("filter", "statuscode:200"),
         ("filter", "mimetype:text/html"), ("collapse", "urlkey"),
         ("from", str(from_year)), ("limit", str(limit))]
    code, body = arc.get(CDX_URL + "?" + urllib.parse.urlencode(q))
    if body is None:
        return None
    txt = body.decode("utf-8", "replace").strip()
    if not txt:
        return []                       # domain simply is not in the Archive
    try:
        rows = json.loads(txt)
    except Exception:
        return None
    if not rows:
        return []
    head = [str(c).lower() for c in rows[0]]
    ti = head.index("timestamp") if "timestamp" in head else 0
    oi = head.index("original") if "original" in head else 1
    out = []
    for r in rows[1:]:
        if len(r) <= max(ti, oi):
            continue
        ym = _ym(r[ti])
        if ym:
            out.append((ym, str(r[oi])))
    return out


def cdx_months(arc, url, frm, to, limit=400):
    """One capture per month of ONE url. -> [(ym, timestamp, original)] or None.
    collapse=timestamp:6 collapses on YYYYMM, i.e. keeps the first capture in
    each month."""
    q = [("url", url), ("output", "json"), ("fl", "timestamp,original"),
         ("filter", "statuscode:200"), ("collapse", "timestamp:6"),
         ("from", frm), ("to", to), ("limit", str(limit))]
    code, body = arc.get(CDX_URL + "?" + urllib.parse.urlencode(q))
    if body is None:
        return None
    txt = body.decode("utf-8", "replace").strip()
    if not txt:
        return []
    try:
        rows = json.loads(txt)
    except Exception:
        return None
    if not rows:
        return []
    head = [str(c).lower() for c in rows[0]]
    ti = head.index("timestamp") if "timestamp" in head else 0
    oi = head.index("original") if "original" in head else 1
    out = []
    for r in rows[1:]:
        if len(r) <= max(ti, oi):
            continue
        ym = _ym(r[ti])
        if ym:
            out.append((ym, str(r[ti]), str(r[oi])))
    return out


def snapshot(arc, ts, url):
    """The ORIGINAL archived bytes ('id_'), not the Archive's rewritten page."""
    code, body = arc.get(WB_URL + str(ts) + "id_/" + url)
    if body is None:
        return None
    return body.decode("utf-8", "replace")


# ============================================================== HTML -> the page
class _Page(HTMLParser):
    """Visible text + every href. The hrefs are the point: with 'id_' the Archive
    serves the ORIGINAL html, so a homepage's nav menu is a list of that clinic's
    real service URLs on that month. The nav menu IS the service list."""

    SKIP = ("script", "style", "noscript", "svg", "head", "template")

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.parts = []
        self.links = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, d):
        if not self._skip:
            d = d.strip()
            if d:
                self.parts.append(d)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts))


def parse_page(html):
    """-> (visible_text, [href, ...]). Never raises: archived HTML is often broken."""
    p = _Page()
    try:
        p.feed(html or "")
    except Exception:
        pass
    return p.text(), p.links


# ============================================================ TERMS: the vocabulary
ASSET = re.compile(
    r"\.(jpe?g|png|gif|svg|webp|ico|css|js|pdf|xml|json|zip|mp4|mp3|woff2?|ttf|eot)$",
    re.I)

# Path segments that are never a service, and whose CHILDREN are never a service.
# /blog/adhd-assessment-what-to-expect is content marketing, not a service line,
# and treating it as one would let a clinic "adopt" every condition it ever wrote
# a post about. This is a deliberate loss of real signal to kill a large fake one.
JUNK_SEG = frozenset("""
wp-content wp-includes wp-json wp-admin wp-login feed rss atom sitemap sitemap_index
xmlrpc cdn-cgi assets static media uploads images image img css js fonts author tag
tags category categories page pages comment comments trackback amp print search login
logout register signup cart checkout basket account my-account privacy privacy-policy
cookie cookies cookie-policy terms terms-and-conditions disclaimer accessibility news
blog blogs article articles press media-centre insights resources careers career jobs
job vacancies vacancy recruitment team our-team meet-the-team staff people about
about-us contact contact-us get-in-touch find-us locations location branches
testimonials reviews review faq faqs gallery events event shop store product products
thank-you thanks 404 index home portal patient-portal videos video podcast webinar
downloads download ebook guides guide glossary complaints policies policy legal gdpr
sitemap-index feeds tel mailto
""".split())

# The head-nouns of a clinical service. A slug containing one of these is a
# service page even if its parent segment is not /services/.
SERVICE_HEAD = frozenset("""
clinic clinics assessment assessments treatment treatments therapy therapies service
services screening screenings test tests testing consultation consultations surgery
injection injections scan scans imaging transplant removal programme program diagnosis
review medication titration package packages check checks specialist specialists doctor
consultant care procedure procedures
""".split())

# Parent segments under which anything is a service.
SERVICE_PARENTS = frozenset("""
services service treatments treatment conditions clinics clinic procedures therapies
therapy specialisms specialities specialties what-we-treat what-we-do our-services
our-treatments treatments-we-offer conditions-we-treat
""".split())

# Grammar, geography and website furniture. A term made ONLY of these is not a
# service. Place names are here because clinic slugs are full of them
# (/adhd-clinic-london) and they would otherwise become the top "rising service"
# in the country.
STOP = frozenset("""
a an the and or of for to in on at by with our your my we us you it is are be new best
top leading expert expertise private priv nhs uk gb england scotland wales britain
british london manchester birmingham leeds glasgow edinburgh bristol liverpool cardiff
belfast sheffield nottingham leicester newcastle brighton oxford cambridge harley
street road lane avenue centre center house clinic-uk near me home page site web online
book booking bookings now here more info information about contact prices price cost
costs fees fee free how what why when where who which get make take see find learn read
help welcome hello meet team staff opening hours covid coronavirus join refer referral
gift voucher finance insurance self pay virtual tour video media awards partners
sponsors charity story stories journey results before after question questions answers
patient patients client clients customer people man men woman women adult adults child
children kids family families year years old age aged
offer offers offered offering provide provides provided providing deliver delivers
delivering include includes included including available range wide full comprehensive
bespoke tailored trusted award awarded winning specialising specialised specializing
here also plus over under from into using use used need needs want wants
""".split())
# The last block above is MARKETING FILLER, and it is not cosmetic. Without it the
# sentence "we offer shockwave therapy" yields the 3-gram "offer shockwave therapy",
# which then SUBSUMES the real service name "shockwave therapy" (same adopters, longer
# string) and the panel prints a verb as if it were a treatment.


def _tokens(seg):
    seg = re.sub(r"\.(html?|php|aspx?|htm)$", "", (seg or "").lower())
    out = []
    for t in re.split(r"[^a-z0-9']+", seg):
        if not t or t.isdigit():
            continue
        if len(t) < 3 and t not in ("iv", "ed", "gp"):
            continue
        out.append(t)
    return out


def _grams(toks, nmax=3):
    """Contiguous 1..3-grams, but only those carrying a SUBSTANTIVE token.

    A term must say something. "clinic" is a head-noun with no content; "london"
    is a place; "adhd" is a service. So every emitted gram must contain at least
    one token that is neither grammar/geography (STOP) nor a bare clinical
    head-noun (SERVICE_HEAD). That single rule kills "meet team", "our clinic",
    "book now" and "private london" structurally, and keeps "adhd",
    "adhd assessment", "shockwave therapy" and "retatrutide".
    """
    out = set()
    n = len(toks)
    for size in range(1, nmax + 1):
        for i in range(0, n - size + 1):
            g = toks[i:i + size]
            if any(t in STOP for t in g):
                continue
            if not any(t not in SERVICE_HEAD for t in g):
                continue
            term = " ".join(g)
            if len(term) < 4:
                continue
            out.add(term)
    return out


def path_terms(url):
    """A URL -> the service terms it claims. The SLUG IS THE SERVICE NAME.

    /services/adhd-assessment/    -> {"adhd", "adhd assessment"}
    /blog/adhd-what-to-expect     -> {}   (blog: content, not a service line)
    /wp-content/uploads/x.jpg     -> {}
    /about-us/meet-the-team       -> {}   (every token is furniture)
    """
    u = url or ""
    try:
        sp = urllib.parse.urlsplit(u if "://" in u else "http://" + u)
        path = urllib.parse.unquote(sp.path or "/")
    except Exception:
        return set()
    if ASSET.search(path):
        return set()
    segs = [s for s in path.split("/") if s and s != "."]
    if not segs or len(segs) > 4:
        return set()                    # homepage, or an archive page deep in a blog
    low = [s.lower() for s in segs]
    if any(s in JUNK_SEG for s in low):
        return set()                    # junk anywhere in the path kills the path
    leaf = low[-1]
    parent = low[-2] if len(low) >= 2 else ""
    toks = _tokens(leaf)
    if not toks:
        return set()
    is_service = (parent in SERVICE_PARENTS) or any(t in SERVICE_HEAD for t in toks)
    if not is_service and len(segs) > 2:
        # Deep, not under a service parent, no service head-noun. Not a service.
        return set()
    # A bare top-level slug (/adhd/, /menopause/) IS usually a service, so it is
    # kept - and the noise that lets in dies at the MIN_ADOPTERS gate, which is
    # where open-vocabulary noise is supposed to die. Rejecting it here instead
    # would also reject every genuinely NEW service, which is the point of the
    # module.
    return _grams(toks)


def text_terms(text, niche_of, links=None):
    """Terms from a page's visible text and its nav links.

    Free text is far noisier than a URL path - a clinic that MENTIONS ADHD in a
    sentence has not adopted it. So the text path is deliberately narrow: a term
    is only taken from prose when it sits directly against a clinical head-noun
    ("adhd assessment", "shockwave therapy"), or when the taxonomy already knows
    it. The nav links go through the same path_terms() as everything else, and
    they are the stronger half of this signal.
    """
    out = set()
    for href in (links or []):
        out |= path_terms(href)
    t = re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower())
    toks = [x for x in t.split() if x]
    for i, tok in enumerate(toks):
        if tok not in SERVICE_HEAD:
            continue
        for size in (2, 3):
            j = i - size + 1
            if j < 0:
                continue
            g = toks[j:i + 1]
            if any(x in STOP for x in g):
                continue
            if not any(x not in SERVICE_HEAD for x in g):
                continue
            term = " ".join(g)
            if len(term) >= 6:
                out.add(term)
    # Anything the taxonomy recognises is worth keeping even as a bare word.
    for tok in set(toks):
        if len(tok) >= 4 and tok not in STOP and tok not in SERVICE_HEAD:
            if niche_of(tok):
                out.add(tok)
    return out


# ==================================================== the resumable backfill
def _norm_path(url):
    try:
        sp = urllib.parse.urlsplit(url if "://" in url else "http://" + url)
    except Exception:
        return None
    p = urllib.parse.unquote(sp.path or "/")
    p = re.sub(r"/+", "/", p)
    return p or "/"


def refresh_paths(arc, cohort, idx):
    """Spend this run's CDX budget. Resumable by construction: a domain that is
    not reached today is simply first in the queue tomorrow, and nothing already
    fetched is re-bought for REFRESH_DAYS.

    Only paths that YIELD a term are stored. A clinic's index can run to
    thousands of URLs and almost all of them are images, pagination and blog
    posts; keeping them would grow the cache to tens of megabytes and buy
    nothing. The domain's FIRST-CAPTURE month is computed over ALL rows before
    that filter, because it is the left-censoring anchor and must reflect when
    the Archive started watching the SITE, not when it first saw a service page.
    """
    due = []
    for c in cohort:
        d = c["domain"]
        rec = idx.get(d)
        if not rec:
            due.append((0, d))
        elif _days_since(rec.get("fetched") or "") >= REFRESH_DAYS:
            due.append((1, d))
    due.sort()

    got = 0
    for _pri, d in due:
        if not arc.live:
            break
        rows = cdx_paths(arc, d)
        if rows is None:
            continue                    # failed call: do NOT cache a failure
        first = min((ym for ym, _u in rows), default=None)
        keep, seen = [], set()
        for ym, u in rows:
            p = _norm_path(u)
            if not p or (p in seen):
                continue
            if not path_terms(p):
                continue
            seen.add(p)
            keep.append([ym, p])
        keep.sort()
        idx[d] = {"fetched": date.today().isoformat(), "first": first,
                  "n_urls": len(rows), "urls": keep[:400]}
        got += 1
    DIAG["cdx"] = {"domains_due": len(due), "domains_indexed_this_run": got,
                   "calls": arc.calls, "budget": arc.budget,
                   "blocked": arc.blocked}
    return got


def refresh_text(arc, cohort, snaps, months, anchor_ym, budget):
    """The optional second sensor: the homepage, month by month.

    Ordering is BREADTH-FIRST across clinics and, within a clinic, the months
    that decide the answer come first: NOW, then NOW-12. After two passes over
    the cohort the panel already has a now-vs-prior comparison for every clinic;
    the deep history fills in behind it. A depth-first backfill would give you a
    perfect 36-month history of the first eleven clinics and nothing else.
    """
    if budget <= 0:
        return 0
    start = _ym_add(anchor_ym, -months)
    want = [anchor_ym, _ym_add(anchor_ym, -WINDOW), _ym_add(anchor_ym, -2 * WINDOW)]
    spent = 0

    # pass 1: make sure every clinic has a month index (1 CDX call each)
    for c in cohort:
        if not arc.live or spent >= budget:
            break
        d = c["domain"]
        rec = snaps.setdefault(d, {})
        cdxr = rec.get("cdx") or {}
        if cdxr.get("months") is not None and \
                _days_since(cdxr.get("fetched") or "") < REFRESH_DAYS:
            continue
        ms = cdx_months(arc, c["url"], start.replace("-", ""), anchor_ym.replace("-", ""))
        spent += 1
        if ms is None:
            continue
        rec["cdx"] = {"fetched": date.today().isoformat(), "months": ms}

    # pass 2: the months that decide the answer, then the rest, oldest first
    def queue():
        for target in want:
            for c in cohort:
                yield c, target
        for c in cohort:
            for ym in [_ym_add(start, i) for i in range(months + 1)]:
                yield c, ym

    for c, target in queue():
        if not arc.live or spent >= budget:
            break
        d = c["domain"]
        rec = snaps.get(d) or {}
        ms = (rec.get("cdx") or {}).get("months") or []
        terms = rec.setdefault("terms", {})
        hit = next((m for m in ms if m[0] == target), None)
        if not hit or target in terms:
            continue
        html = snapshot(arc, hit[1], hit[2])
        spent += 1
        if html is None:
            continue
        txt, links = parse_page(html)
        ts = text_terms(txt, _NICHE_OF or (lambda x: None), links)
        terms[target] = sorted(ts)[:200]
        snaps[d] = rec
    DIAG["text"] = {"fetches": spent, "budget": budget, "blocked": arc.blocked}
    return spent


# ================================================================ the arithmetic
def _observations(cohort, idx, snaps, months, anchor_ym):
    """-> (first, censored, dom_first, covered)

    first[term][domain] = the month that clinic FIRST showed the term.
    censored[term] = clinics that already had it when the Archive arrived.

    THE LEFT-CENSORING CORRECTION lives here, and it is the difference between a
    trend and an artefact. The Archive's first capture of a page is the date the
    ARCHIVE FIRST LOOKED, not the date the page appeared. So a term first seen
    within GRACE months of the Archive's first-ever capture of that domain is
    treated as PRE-EXISTING: it counts in the base, never as a new adopter. It
    costs us real early adoptions. It stops the panel inventing a boom out of
    the Archive's own crawl schedule, which is the failure that would make this
    whole module worthless and look convincing while doing it.
    """
    first = defaultdict(dict)
    censored = defaultdict(set)
    dom_first = {}
    covered = 0

    for c in cohort:
        d = c["domain"]
        rec = idx.get(d) or {}
        urls = rec.get("urls") or []
        snap_terms = (snaps.get(d) or {}).get("terms") or {}

        df = rec.get("first")
        if not df and urls:
            df = min(ym for ym, _p in urls)
        if snap_terms:
            m = min(snap_terms)
            df = m if (not df or m < df) else df
        if not df:
            continue                    # this clinic is not in the Archive at all
        dom_first[d] = df
        covered += 1

        seen = {}
        for ym, p in urls:
            for t in path_terms(p):
                if t not in seen or ym < seen[t]:
                    seen[t] = ym
        for ym, terms in snap_terms.items():
            for t in terms:
                if t not in seen or ym < seen[t]:
                    seen[t] = ym

        grace_end = _ym_add(df, GRACE)
        for t, ym in seen.items():
            if _ymi(ym) <= _ymi(grace_end):
                censored[t].add(d)
                ym = CENSORED_YM
            cur = first[t].get(d)
            first[t][d] = ym if (cur is None or ym < cur) else cur

    return first, censored, dom_first, covered


_WORD = {}


def _subsumes(short, long_):
    """Is `short` contained in `long_` as whole words? ('adhd' in 'adhd assessment')"""
    rx = _WORD.get(short)
    if rx is None:
        rx = re.compile(r"\b" + re.escape(short) + r"\b")
        _WORD[short] = rx
    return short != long_ and bool(rx.search(long_))


def _why(term, now_n, cohort_n, new12, newprev, cens, first_seen):
    s = ("%d of the %d clinics in the panel now have a '%s' page; %d of them added it "
         "in the last 12 months, against %d in the 12 months before."
         % (now_n, cohort_n, term, new12, newprev))
    if newprev == 0 and new12 >= MIN_ADOPTERS:
        s += " Nobody in the panel had it before that."
    elif new12 > newprev:
        s += " The rate of adoption is rising."
    elif new12 < newprev:
        s += " The rate of adoption is slowing."
    if cens:
        s += (" (%d more had it before the Archive started watching them, so their "
              "adoption date is unknown and they are counted in the base, not as "
              "new.)" % cens)
    return s


def _rows(first, censored, months, anchor_ym, cohort_n, niche_of, by_dom):
    w0 = _ym_add(anchor_ym, -WINDOW)
    w1 = _ym_add(anchor_ym, -2 * WINDOW)
    out = []
    for term, doms in first.items():
        now_n = len(doms)
        observed = [ym for ym in doms.values() if ym != CENSORED_YM]
        seen_first = min(observed) if observed else None
        prior = sum(1 for ym in doms.values() if ym <= w0)
        base2 = sum(1 for ym in doms.values() if ym <= w1)
        new12 = now_n - prior
        newprev = prior - base2
        if new12 < 1:
            continue                    # not rising: not what this module is for
        niche = niche_of(term)
        if niche is None:
            # OPEN VOCABULARY. One clinic's odd page slug is not a trend; three
            # independent clinics doing the same new thing is the earliest real
            # signal this system can produce.
            if now_n < MIN_ADOPTERS:
                continue
        elif now_n < 2:
            continue
        cens = len(censored.get(term) or ())
        adopters = sorted((ym, d) for d, ym in doms.items() if ym > w0)
        out.append({
            "term": term,
            "niche": niche,
            "clinics_now": now_n,
            "clinics_prior": prior,
            "growth": (round(new12 / float(prior), 3) if prior else float(new12)),
            "first_seen": seen_first,
            "new_adopters": [by_dom.get(d, {}).get("name") or d for _ym, d in adopters][:8],
            "why": _why(term, now_n, cohort_n, new12, newprev, cens, seen_first),
            "new_12m": new12,
            "new_prev_12m": newprev,
            "accel": new12 - newprev,
            "open": niche is None,
            "censored": cens,
            "cohort_n": cohort_n,
            "adopter_domains": sorted(doms),
        })

    # Drop a term that a longer term completely explains: if every clinic with
    # "adhd" is a clinic with "adhd assessment", the short term is a shadow of
    # the long one and printing both is printing the same finding twice.
    out.sort(key=lambda r: -len(r["term"]))
    kill = set()
    for i, a in enumerate(out):
        if a["term"] in kill:
            continue
        for b in out[i + 1:]:
            if b["term"] in kill:
                continue
            if _subsumes(b["term"], a["term"]) and \
                    set(b["adopter_domains"]) == set(a["adopter_domains"]):
                kill.add(b["term"])
    out = [r for r in out if r["term"] not in kill]

    out.sort(key=lambda r: (-r["accel"], -r["new_12m"], -r["clinics_now"], r["term"]))
    for r in out:
        r.pop("adopter_domains", None)
    return out[:200]


# ===================================================================== the entry
_NICHE_OF = None


def _cooldown_active(state, now=None):
    return float(state.get("cooldown_until") or 0) > (now if now is not None
                                                      else time.time())


def _set_cooldown(state, code):
    """A 429 doubles on repeat, so our backoff doubles too. This is the difference
    between losing the sensor for an hour and losing it for a week."""
    n = int(state.get("consecutive_blocks") or 0) + 1
    wait = COOLDOWN_BASE * (2 ** min(n - 1, 5))
    state["consecutive_blocks"] = n
    state["cooldown_until"] = time.time() + wait
    state["last_block"] = {"code": code, "wait_s": wait,
                           "at": datetime.now().isoformat(timespec="seconds")}
    return state


def panel(niche_of, cohort=None, months=36, anchor=None, archive=None, refresh=True,
          text=None, cdx_budget=None, text_budget=None, rebuild=False,
          only_niches=None, cohort_file=None, paths_file=None, snaps_file=None,
          state_file=None, cohort_kwargs=None):
    """Adoption, not entry: which SERVICES are existing UK private clinics adding?

    [{"term", "niche" (or None for an open-vocabulary term), "clinics_now",
      "clinics_prior", "growth", "first_seen" (ISO month), "new_adopters" [names],
      "why", "new_12m", "new_prev_12m", "accel", "open", "censored", "cohort_n"}]
    ranked by acceleration in DISTINCT ADOPTERS. None if unavailable.

    Reads from cache and returns an answer even when the Archive is unreachable,
    rate-limiting us, or in a cooldown. The only way this returns None is if
    there is no cohort and no cached history at all.
    """
    global _NICHE_OF
    DIAG.clear()
    _NICHE_OF = niche_of
    try:
        paths_file = paths_file or PATHS_FILE
        snaps_file = snaps_file or SNAPS_FILE
        state_file = state_file or STATE_FILE
        anchor_ym = _ym_now(anchor)

        if cohort is None:
            cohort = build_cohort(niche_of, rebuild=rebuild, only_niches=only_niches,
                                  cohort_file=cohort_file, **(cohort_kwargs or {}))
        if not cohort:
            DIAG.setdefault("fatal", "no cohort could be built")
            return None

        idx = _load(paths_file, {}) or {}
        snaps = _load(snaps_file, {}) or {}
        state = _load(state_file, {}) or {}

        use_text = (TEXT_BUDGET > 0) if text is None else bool(text)
        tbud = TEXT_BUDGET if text_budget is None else text_budget

        if refresh:
            if _cooldown_active(state):
                DIAG["cooldown"] = (
                    "the Archive blocked us (HTTP %s) and the cooldown has not "
                    "expired. No request was made. The panel below is computed from "
                    "cache - which is exactly what the cache is for."
                    % ((state.get("last_block") or {}).get("code")))
            else:
                arc = archive or Archive(budget=cdx_budget)
                refresh_paths(arc, cohort, idx)
                if use_text and tbud > 0 and arc.live:
                    arc.budget = arc.calls + tbud
                    refresh_text(arc, cohort, snaps, months, anchor_ym, tbud)
                _save(paths_file, idx)
                if use_text:
                    _save(snaps_file, snaps)
                if arc.blocked:
                    _set_cooldown(state, arc.block_code)
                elif arc.calls:
                    state["consecutive_blocks"] = 0
                    state["last_ok"] = datetime.now().isoformat(timespec="seconds")
                _save(state_file, state)

        first, censored, dom_first, covered = _observations(
            cohort, idx, snaps, months, anchor_ym)
        by_dom = dict((c["domain"], c) for c in cohort)

        DIAG["panel"] = {
            "cohort": len(cohort),
            "clinics_with_archive_history": covered,
            "coverage_pct": round(100.0 * covered / len(cohort), 1) if cohort else 0,
            "distinct_terms_observed": len(first),
            "anchor_month": anchor_ym,
            "months": months,
            "text_sensor": use_text,
        }
        if covered < len(cohort):
            DIAG["backfill_incomplete"] = (
                "%d of %d clinics have no Archive history yet. Until that reaches "
                "~100%%, every adopter count below is an UNDERCOUNT and the ranking "
                "is provisional. Run --backfill again." % (len(cohort) - covered,
                                                           len(cohort)))
        if not first:
            DIAG.setdefault("note", "no observations - the backfill has not run yet")
            return None

        return _rows(first, censored, months, anchor_ym, covered, niche_of, by_dom)

    except Exception as e:
        DIAG["fatal"] = repr(e)[:300]
        return None


def adhd_history(niche_of, cohort, idx, anchor=None):
    """THE TEST THAT DECIDES WHETHER THIS MODULE IS WORTH SHIPPING.

    Year by year: how many clinics in the panel had an ADHD page? If the answer
    climbs through 2021-22, this sensor would have seen the ADHD boom while it
    was happening - which is the only claim that matters.
    """
    per_year = defaultdict(set)
    firsts = {}
    for c in cohort:
        d = c["domain"]
        rec = idx.get(d) or {}
        df = rec.get("first")
        best = None
        for ym, p in (rec.get("urls") or []):
            for t in path_terms(p):
                if niche_of(t) == "ADHD":
                    if best is None or ym < best:
                        best = ym
        if not best:
            continue
        censored = bool(df and _ymi(best) <= _ymi(_ym_add(df, GRACE)))
        firsts[d] = (best, censored, c.get("name") or d)
        for y in range(int(best[:4]), (anchor or date.today()).year + 1):
            per_year[y].add(d)
    return per_year, firsts


# ==================================================================== SELF-TEST
REAL_HEADER = [
    "Name", "Also known as", "Address", "Postcode", "Phone number",
    "Service's website (if available)", "Service types", "Date of latest check",
    "Specialisms/services", "Provider name", "Local authority", "Region",
    "Location URL", "CQC Location ID", "CQC Provider ID",
]

CLINIC = "Doctors consultation service"
NHSGP = "Doctors treatment service"
CAREHOME = "Care home service with nursing"


def _dirrow(name, site, types, prov, lid):
    return [name, "", "1 High St", "N1 1AA", "020", site, types, "2025-01-01",
            "", prov, "Camden", "London", "https://www.cqc.org.uk/l/" + lid,
            lid, "P-" + lid]


def _fixture_directory():
    """A synthetic CQC care directory with every trap the real one contains."""
    rows = [list(REAL_HEADER)]
    smap = {}

    # 40 private psychiatry / mental-health clinics - the ADHD cohort.
    for i in range(1, 41):
        lid = "L-PSY-%03d" % i
        rows.append(_dirrow("Wellbeck Psychiatry %d" % i, "https://www.psy%02d.co.uk" % i,
                            CLINIC, "Wellbeck Psychiatry %d Ltd" % i, lid))
        smap[lid] = "Independent Healthcare Org"
    # 20 private GPs.
    for i in range(1, 21):
        lid = "L-GP-%03d" % i
        rows.append(_dirrow("Kingsway Private GP %d" % i, "http://gp%02d.co.uk" % i,
                            CLINIC, "Kingsway GP %d Ltd" % i, lid))
        smap[lid] = "Independent Healthcare Org"
    # 20 dentists (Primary Dental Care is kept - dentists visibly add services).
    for i in range(1, 21):
        lid = "L-DEN-%03d" % i
        rows.append(_dirrow("Ashgrove Dental %d" % i, "https://dent%02d.co.uk" % i,
                            "Dental service", "Ashgrove Dental %d Ltd" % i, lid))
        smap[lid] = "Primary Dental Care"

    # ---- THE TRAPS ----------------------------------------------------------
    # NHS GP surgeries. IDENTICAL service type to a private GP. Only the sector
    # column tells them apart, and there are ~6,000 of them in the real file.
    for i in range(1, 31):
        lid = "L-NHSGP-%03d" % i
        rows.append(_dirrow("Riverside Surgery %d" % i, "https://riverside%02d.co.uk" % i,
                            NHSGP, "Riverside Surgery %d" % i, lid))
        smap[lid] = "Primary Medical Services"
    # An NHS trust, a care home, a hospice.
    rows.append(_dirrow("St Elsewhere Hospital", "https://sthosp.nhs.uk",
                        "Acute services with overnight beds",
                        "St Elsewhere NHS Foundation Trust", "L-NHS-1"))
    smap["L-NHS-1"] = "NHS Healthcare Organisation"
    rows.append(_dirrow("Meadowbank Care Home", "https://meadowbank.co.uk", CAREHOME,
                        "Meadowbank Care Ltd", "L-SOC-1"))
    smap["L-SOC-1"] = "Social Care Org"
    rows.append(_dirrow("St Mary's Hospice", "https://stmaryshospice.org.uk",
                        "Hospice services", "St Mary's Hospice Ltd", "L-HOS-1"))
    smap["L-HOS-1"] = "Independent Healthcare Org"
    # No website; a Facebook "website"; an nhs.uk website on an independent.
    rows.append(_dirrow("Quiet Clinic", "", CLINIC, "Quiet Ltd", "L-NOSITE-1"))
    smap["L-NOSITE-1"] = "Independent Healthcare Org"
    rows.append(_dirrow("Facebook Clinic", "https://www.facebook.com/fbclinic", CLINIC,
                        "FB Ltd", "L-FB-1"))
    smap["L-FB-1"] = "Independent Healthcare Org"
    rows.append(_dirrow("Hosted Clinic", "https://something.nhs.uk/clinic", CLINIC,
                        "Hosted Ltd", "L-NHSSITE-1"))
    smap["L-NHSSITE-1"] = "Independent Healthcare Org"
    # ONE GROUP, TWO LOCATIONS, ONE WEBSITE. Must collapse to a single adopter:
    # counting it twice would put one company's decision into the panel twice.
    for k, lid in enumerate(("L-GRP-1", "L-GRP-2")):
        rows.append(_dirrow("Harborne Clinic Site %d" % (k + 1),
                            "https://harborne-group.co.uk",
                            CLINIC, "Harborne Group Ltd", lid))
        smap[lid] = "Independent Healthcare Org"
    return rows, smap


def _fixture_plan():
    """What the Archive holds. Domain -> first capture + the pages it ever saw.

    THE ADHD STORY, built to be exactly the thing we claim to be able to see:
      2 clinics had an ADHD page in 2019 (early)
      3 more added one in 2021
      12 more added one in 2022      <- the boom
    Plus controls: a flat service (no adoption), a one-clinic oddity (noise), an
    OPEN-VOCABULARY drug nobody pre-listed, and one left-censored clinic whose
    site the Archive only started crawling in 2022.
    """
    plan = {}

    def site(dom, first, pages):
        plan[dom] = {"first": first, "pages": [(first, "/")] + pages,
                     "months": [first, "2022-01", "2023-01"]}

    adhd_year = {}
    for i in range(1, 3):
        adhd_year[i] = "2019-06"
    for i in range(3, 6):
        adhd_year[i] = "2021-05"
    for i in range(6, 18):
        adhd_year[i] = "2022-04"

    for i in range(1, 41):
        dom = "psy%02d.co.uk" % i
        pages = [("2018-02", "/services/talking-therapy"),
                 ("2018-02", "/about-us/meet-the-team"),
                 ("2018-02", "/blog/adhd-in-adults-what-to-expect")]
        if i in adhd_year:
            ym = adhd_year[i]
            pages.append((ym, "/services/adhd-assessment"))
            # A second ADHD page. The clinic is still ONE adopter.
            pages.append((ym, "/services/adhd-assessment-for-adults"))
        if 20 <= i <= 23:
            pages.append(("2022-09", "/treatments/retatrutide"))   # open vocabulary
        if i == 30:
            pages.append(("2022-03", "/services/bespoke-quantum-alignment"))  # noise
        site(dom, "2018-01", pages)

    # LEFT-CENSORED: the Archive only found this site in 2022, and it already had
    # an ADHD page. It must NOT be counted as a 2022 adopter.
    plan["psy40.co.uk"] = {
        "first": "2022-02",
        "pages": [("2022-02", "/"), ("2022-02", "/services/adhd-assessment")],
        "months": ["2022-02", "2023-01"]}

    for i in range(1, 21):
        site("gp%02d.co.uk" % i, "2018-01",
             [("2018-01", "/services/flu-vaccination"),      # flat control
              ("2018-01", "/services/private-gp-appointment")])
    for i in range(1, 21):
        site("dent%02d.co.uk" % i, "2018-01", [("2018-01", "/treatments/implants")])
    site("harborne-group.co.uk", "2018-01", [("2018-01", "/services/physiotherapy")])
    return plan


def _fake_archive(plan, block_after=None, snapshots=None, counter=None):
    counter = counter if counter is not None else {"n": 0}

    def fetch(url):
        counter["n"] += 1
        if block_after is not None and counter["n"] > block_after:
            return 429, None
        if url.startswith(CDX_URL):
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            u = (qs.get("url") or [""])[0]
            prefix = (qs.get("matchType") or [""])[0] == "prefix"
            dom = u if prefix else _domain(u)
            p = plan.get(dom)
            if p is None:
                return 200, b""
            rows = [["timestamp", "original"]]
            if prefix:
                for ym, path in p["pages"]:
                    rows.append([ym.replace("-", "") + "01120000",
                                 "http://" + dom + path])
            else:
                for ym in p.get("months", []):
                    rows.append([ym.replace("-", "") + "01120000",
                                 "http://" + dom + "/"])
            return 200, json.dumps(rows).encode()
        if url.startswith(WB_URL):
            m = re.match(re.escape(WB_URL) + r"(\d+)id_/(.*)$", url)
            if not m:
                return 404, None
            html = (snapshots or {}).get((_domain(m.group(2)), _ym(m.group(1))))
            return (200, html.encode()) if html else (404, None)
        return 404, None
    return fetch


SNAP_HTML = """<!doctype html><html><head><title>X</title>
<style>.a{color:red}</style><script>var adhd="hidden";</script></head><body>
<nav><a href="/services/adhd-assessment">ADHD Assessment</a>
<a href="/services/menopause-clinic">Menopause</a>
<a href="/blog/adhd-tips">Blog</a></nav>
<h1>Welcome</h1><p>We offer shockwave therapy and adult ADHD assessment.</p>
</body></html>"""


def selftest():
    try:
        from taxonomy import niche_of
    except Exception as e:
        print("FAIL: taxonomy.py not importable from %s (%r)" % (_HERE, e))
        return 1

    fails = []

    def chk(label, got, want):
        ok = (got == want)
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("  %s %-58s %s" % ("PASS" if ok else "FAIL", label, got))

    tmp = tempfile.mkdtemp(prefix="panel_")
    F = lambda n: os.path.join(tmp, n)
    rows, smap = _fixture_directory()
    plan = _fixture_plan()
    anchor = date(2023, 1, 15)

    # ------------------------------------------------------------ 1. the cohort
    print("\n[1] the cohort: a private-clinic panel, not an NHS one")
    coh = build_cohort(niche_of, rows=list(rows), smap=smap, size=300,
                       cohort_file=F("c1.json"))
    doms = set(c["domain"] for c in coh)
    chk("81 eligible clinics kept", len(coh), 81)
    chk("30 NHS GP surgeries EXCLUDED by the sector join",
        any(d.startswith("riverside") for d in doms), False)
    chk("NHS trust excluded", "sthosp.nhs.uk" in doms, False)
    chk("care home excluded", "meadowbank.co.uk" in doms, False)
    chk("hospice excluded", "stmaryshospice.org.uk" in doms, False)
    chk("clinic with no website excluded", len([c for c in coh if not c["domain"]]), 0)
    chk("a Facebook page is not a website", any("facebook" in d for d in doms), False)
    chk("an nhs.uk site on an 'independent' is still NHS",
        any(d.endswith("nhs.uk") for d in doms), False)
    grp = [c for c in coh if c["domain"] == "harborne-group.co.uk"]
    chk("2 locations, 1 website -> ONE adopter, not two", len(grp), 1)
    chk("...and its site count is kept", grp[0]["sites"], 2)
    chk("niches resolved (psychiatry present - the ADHD question needs it)",
        sum(1 for c in coh if c["niche"] == "Mental health / psychiatry"), 40)

    print("\n[1b] the cohort is FROZEN - a moving panel makes the trend meaningless")
    coh2 = build_cohort(niche_of, rows=[], smap={}, cohort_file=F("c1.json"))
    chk("second call reuses the frozen file, ignores the new source",
        [c["domain"] for c in coh2] == [c["domain"] for c in coh], True)
    small = build_cohort(niche_of, rows=list(rows), smap=smap, size=9,
                         cohort_file=F("c2.json"))
    chk("sampling is STRATIFIED: a 9-clinic panel still reaches every niche",
        set(c["niche"] for c in small) >= {"Mental health / psychiatry", "Private GP",
                                           "Dental / orthodontics"}, True)
    chk("...and DETERMINISTIC",
        [c["domain"] for c in build_cohort(niche_of, rows=list(rows), smap=smap, size=9,
                                           cohort_file=F("c3.json"))]
        == [c["domain"] for c in small], True)

    print("\n[1c] degraded mode: no .ods sector column")
    dgr = build_cohort(niche_of, rows=list(rows), smap={}, size=300,
                       cohort_file=F("c4.json"))
    dd = set(c["domain"] for c in dgr)
    chk("without the sector join, NHS GPs LEAK IN (this is why the join exists)",
        any(d.startswith("riverside") for d in dd), True)
    chk("...and the module says so, loudly", "cohort_degraded" in DIAG, True)

    # -------------------------------------------------- 2. the term vocabulary
    print("\n[2] a URL path is a service claim - and most paths are not")
    chk("/services/adhd-assessment", sorted(path_terms("/services/adhd-assessment")),
        ["adhd", "adhd assessment"])
    chk("/adhd-clinic-london (place name stripped)",
        sorted(path_terms("/adhd-clinic-london")), ["adhd", "adhd clinic"])
    chk("BLOG POSTS ARE NOT SERVICES", path_terms("/blog/adhd-what-to-expect"), set())
    chk("/news/we-now-offer-adhd", path_terms("/news/we-now-offer-adhd"), set())
    chk("/about-us/meet-the-team", path_terms("/about-us/meet-the-team"), set())
    chk("/wp-content/uploads/x.jpg", path_terms("/wp-content/uploads/x.jpg"), set())
    chk("homepage claims nothing", path_terms("/"), set())
    chk("'clinic' alone is not a service", path_terms("/our-clinic"), set())
    chk("open vocabulary survives: /treatments/retatrutide",
        path_terms("/treatments/retatrutide"), {"retatrutide"})
    chk("a novel service phrase survives whole",
        "shockwave therapy" in path_terms("/treatments/shockwave-therapy"), True)
    chk("taxonomy tags a known term", niche_of("adhd assessment"), "ADHD")
    chk("...and does NOT tag an unknown one (this is the open layer)",
        niche_of("retatrutide"), None)

    # ------------------------------------------------- 3. snapshot parsing (text)
    print("\n[3] archived HTML -> visible text + the nav menu")
    txt, links = parse_page(SNAP_HTML)
    chk("script contents stripped", "hidden" in txt, False)
    chk("style contents stripped", "color" in txt, False)
    chk("visible text kept", "shockwave therapy" in txt.lower(), True)
    chk("nav hrefs captured (the nav menu IS the service list)", len(links), 3)
    tt = text_terms(txt, niche_of, links)
    chk("nav link -> service term", "adhd assessment" in tt, True)
    chk("prose next to a head-noun -> service term", "shockwave therapy" in tt, True)
    chk("blog link in the nav is still not a service",
        any("tips" in t for t in tt), False)

    # ------------------------------------------ 4. THE ADHD TEST, on the fixture
    print("\n[4] THE TEST: does the panel see an adoption wave it was not told about?")
    arc = Archive(fetch=_fake_archive(plan), sleep=lambda s: None, budget=500)
    res = panel(niche_of, cohort=coh, months=48, anchor=anchor, archive=arc,
                paths_file=F("p.json"), snaps_file=F("s.json"), state_file=F("st.json"))
    chk("panel returns rows", bool(res), True)
    top = res[0] if res else {}
    chk("TOP RISING SERVICE IS ADHD ASSESSMENT", top.get("term"), "adhd assessment")
    chk("...tagged to the ADHD niche", top.get("niche"), "ADHD")
    chk("18 clinics in the panel now have an ADHD page", top.get("clinics_now"), 18)
    chk("6 had one a year ago", top.get("clinics_prior"), 6)
    chk("12 ADOPTED IT IN THE LAST 12 MONTHS", top.get("new_12m"), 12)
    chk("...against 3 the year before", top.get("new_prev_12m"), 3)
    chk("acceleration = +9 distinct clinics", top.get("accel"), 9)
    chk("first seen 2019-06, long before the boom", top.get("first_seen"), "2019-06")
    chk("named adopters are listed", len(top.get("new_adopters") or []) > 0, True)
    chk("DISTINCT CLINICS, not mentions (2 ADHD pages each = 1 adopter)",
        top.get("clinics_now") <= len(coh), True)
    chk("the 40 clinics with an ADHD BLOG POST are not counted as adopters",
        top.get("clinics_now"), 18)

    print("\n[4b] left-censoring: the Archive's crawl schedule must not fake a boom")
    chk("the clinic the Archive only found in 2022 is flagged, not counted as new",
        top.get("censored"), 1)
    naive = 13     # what a naive reading would have called "new in the last 12m"
    chk("naive count would have been 13, corrected count is 12",
        top.get("new_12m") == naive - 1, True)

    print("\n[4c] the OPEN vocabulary: a service nobody pre-listed")
    ret = next((r for r in res if r["term"] == "retatrutide"), None)
    chk("'retatrutide' surfaces with no niche", bool(ret) and ret["niche"] is None, True)
    chk("...flagged as an open-vocabulary find", bool(ret) and ret["open"], True)
    chk("...4 distinct adopters", (ret or {}).get("clinics_now"), 4)
    chk("one clinic's odd page slug is NOT a trend",
        any("quantum" in r["term"] for r in res), False)
    chk("a service everybody already had does not rank (no acceleration)",
        any("flu vaccination" == r["term"] for r in res), False)
    chk("the shadow term 'adhd' is folded into 'adhd assessment'",
        any(r["term"] == "adhd" for r in res), False)
    print("\n  ROWS:")
    for r in res[:4]:
        print("   %-22s %-28s now=%-3d prior=%-3d new12=%-3d accel=%+d"
              % (r["term"], r["niche"] or "(OPEN - no known niche)",
                 r["clinics_now"], r["clinics_prior"], r["new_12m"], r["accel"]))
    print("\n  WHY (the sentence the dashboard prints):\n   %s" % top.get("why"))

    # ------------------------------------------------------------- 5. text mode
    print("\n[5] the second sensor: monthly homepage snapshots")
    # Three clinics whose homepage in 2023 advertises a service that NEVER gets its
    # own URL. The path sensor is blind to it by construction. The text sensor is
    # not, and the two must merge into one adopter count.
    sub = [c for c in coh if c["domain"] in ("psy20.co.uk", "psy21.co.uk",
                                             "psy22.co.uk")]
    snaps = dict(((c["domain"], "2023-01"), SNAP_HTML) for c in sub)
    arc2 = Archive(fetch=_fake_archive(plan, snapshots=snaps), sleep=lambda s: None,
                   budget=400)
    r2 = panel(niche_of, cohort=sub, months=48, anchor=anchor, archive=arc2,
               text=True, text_budget=200, cdx_budget=100,
               paths_file=F("p2.json"), snaps_file=F("s2.json"),
               state_file=F("st2.json"))
    st = _load(F("s2.json"), {})
    got = set()
    for _ym, ts in ((st.get("psy20.co.uk") or {}).get("terms") or {}).items():
        got |= set(ts)
    chk("snapshots parsed into terms", "adhd assessment" in got, True)
    chk("...including one that has NO url of its own", "shockwave therapy" in got, True)
    sw = next((r for r in (r2 or []) if r["term"] == "shockwave therapy"), None)
    chk("the text sensor reaches the panel: 3 distinct adopters",
        (sw or {}).get("clinics_now"), 3)
    chk("...as an open-vocabulary find", bool(sw) and sw["open"], True)
    chk("...and the path sensor's own finding still stands",
        any(r["term"] == "retatrutide" for r in (r2 or [])), True)

    # ------------------------------------------------ 6. the Archive says no
    print("\n[6] HTTP 429: stop, cool down, and still answer from cache")
    arc3 = Archive(fetch=_fake_archive(plan, block_after=5), sleep=lambda s: None,
                   budget=500)
    r3 = panel(niche_of, cohort=coh, months=48, anchor=anchor, archive=arc3,
               paths_file=F("p3.json"), snaps_file=F("s3.json"), state_file=F("st3.json"))
    chk("the client stopped dead on the 429", arc3.blocked, True)
    chk("...it did NOT keep hammering (that is what gets you banned)",
        arc3.calls <= 6, True)
    chk("a cooldown was written for the next run",
        float(_load(F("st3.json"), {}).get("cooldown_until") or 0) > time.time(), True)
    chk("the build did not crash", isinstance(r3, (list, type(None))), True)
    arc4 = Archive(fetch=_fake_archive(plan), sleep=lambda s: None, budget=500)
    r4 = panel(niche_of, cohort=coh, months=48, anchor=anchor, archive=arc4,
               paths_file=F("p3.json"), snaps_file=F("s3.json"), state_file=F("st3.json"))
    chk("next run honours the cooldown: ZERO requests made", arc4.calls, 0)
    chk("...and still returns the cached panel", "cooldown" in DIAG, True)

    print("\n[7] resumable: a budget that runs out is not a run that failed")
    arcA = Archive(fetch=_fake_archive(plan), sleep=lambda s: None, budget=10)
    panel(niche_of, cohort=coh, months=48, anchor=anchor, archive=arcA,
          paths_file=F("p4.json"), snaps_file=F("s4.json"), state_file=F("st4.json"))
    n1 = len(_load(F("p4.json"), {}))
    arcB = Archive(fetch=_fake_archive(plan), sleep=lambda s: None, budget=10)
    panel(niche_of, cohort=coh, months=48, anchor=anchor, archive=arcB,
          paths_file=F("p4.json"), snaps_file=F("s4.json"), state_file=F("st4.json"))
    n2 = len(_load(F("p4.json"), {}))
    chk("run 1 indexed 10 clinics", n1, 10)
    chk("run 2 CONTINUES from there (it does not re-buy them)", n2, 20)
    chk("...and nothing already fetched was re-requested", arcB.calls, 10)

    print("\n[8] garbage in, None out - never a crash, never a wrong number")
    chk("no cohort -> None",
        panel(niche_of, cohort=[], paths_file=F("z.json"), state_file=F("zz.json")),
        None)
    chk("no archive history -> None",
        panel(niche_of, cohort=coh, refresh=False, paths_file=F("empty.json"),
              snaps_file=F("e2.json"), state_file=F("e3.json")), None)
    chk("a directory file with no website column -> None",
        build_cohort(niche_of, rows=[["a", "b"], ["1", "2"]], smap=smap,
                     cohort_file=F("bad.json")), None)

    print("\n" + "=" * 74)
    if fails:
        print("SELFTEST FAILED (%d)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST PASSED")
    return 0


# ========================================================================= main
def _print(res):
    if not res:
        print("panel: no rows")
        return
    print("%-28s %-26s %5s %5s %5s %6s  %s" % (
        "term", "niche", "now", "prior", "new12", "accel", "first"))
    for r in res[:25]:
        print("%-28s %-26s %5d %5d %5d %+6d  %s" % (
            r["term"][:28], (r["niche"] or "(OPEN)")[:26], r["clinics_now"],
            r["clinics_prior"], r["new_12m"], r["accel"], r["first_seen"]))
    print("\nTop row: %s" % res[0]["why"])


def _adhd_test(niche_of):
    """THE decisive live run. Restricts the panel to private psychiatry and GP
    clinics, indexes them against the Archive, and prints the year-by-year count
    of clinics with an ADHD page. If that line climbs through 2021-22, this
    sensor would have seen the ADHD boom as it happened.

    Cost: one CDX request per clinic. A 120-clinic sub-cohort is ~4 minutes.
    """
    coh = build_cohort(niche_of, size=int(os.environ.get("PANEL_COHORT_SIZE", "120")),
                       only_niches=("Mental health / psychiatry", "Private GP"),
                       cohort_file=os.path.join(DATA_DIR, "panel_cohort_adhd.json"))
    if not coh:
        print("could not build the psychiatry/GP cohort")
        print(json.dumps(DIAG, indent=1, default=str))
        return 1
    print("cohort: %d private psychiatry / GP clinics with websites" % len(coh))
    pf = os.path.join(DATA_DIR, "panel_paths_adhd.json")
    res = panel(niche_of, cohort=coh, months=60, paths_file=pf,
                state_file=os.path.join(DATA_DIR, "panel_state.json"))
    idx = _load(pf, {})
    per_year, firsts = adhd_history(niche_of, coh, idx)
    print("\nCLINICS IN THE PANEL WITH AN ADHD PAGE, BY YEAR")
    print("(the count is cumulative: a clinic stays counted once it has one)")
    for y in sorted(per_year):
        n = len(per_year[y])
        print("  %d  %-40s %3d  (%.0f%% of the panel)"
              % (y, "#" * min(40, n), n, 100.0 * n / len(coh)))
    cens = sum(1 for v in firsts.values() if v[1])
    print("\n%d of %d clinics with an ADHD page were already showing it when the "
          "Archive first crawled them - their adoption date is unknown and they are "
          "counted in the base, never as new adopters." % (cens, len(firsts)))
    if res:
        adhd = [r for r in res if r["niche"] == "ADHD"]
        if adhd:
            print("\n%s" % adhd[0]["why"])
    print("\nDIAG: %s" % json.dumps(DIAG, indent=1, default=str))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv or "--test" in sys.argv:
        raise SystemExit(selftest())
    try:
        from taxonomy import niche_of
    except Exception:
        print("taxonomy.py not importable")
        raise SystemExit(1)

    if "--cohort" in sys.argv:
        c = build_cohort(niche_of, rebuild="--rebuild" in sys.argv)
        print("cohort: %s clinics" % (len(c) if c else "NONE"))
        if c:
            byn = defaultdict(int)
            for x in c:
                byn[x["niche"] or "(unclassified)"] += 1
            for k in sorted(byn, key=lambda k: -byn[k]):
                print("  %-30s %3d" % (k, byn[k]))
        print(json.dumps(DIAG, indent=1, default=str))
        raise SystemExit(0)

    if "--adhd-test" in sys.argv:
        raise SystemExit(_adhd_test(niche_of))

    out = panel(niche_of, text="--text" in sys.argv,
                rebuild="--rebuild" in sys.argv)
    if out is None:
        print("panel: unavailable")
        print(json.dumps(DIAG, indent=1, default=str))
    else:
        _print(out)
        print("\nDIAG: %s" % json.dumps(DIAG, indent=1, default=str))
