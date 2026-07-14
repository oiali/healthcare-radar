#!/usr/bin/env python3
"""
CATALYSTS - new UK medicine licences that can CREATE a private-pay market.

Some booms are created by a drug licence, and the licence lands YEARS before
the boom: MHRA granted the GB marketing authorisations for Wegovy
(semaglutide, weight management) on 24 September 2021 - roughly two years
before the UK weight-loss boom peaked, when nothing else on the radar could
see anything. LIMIT, STATED PLAINLY: this detector is BLIND TO ADHD - no new
molecule created that boom (awareness on old drugs). A one-sided SIDE PANEL,
never a scoring tier.

Two keyless GOV.UK routes (both verified live 13 Jul 2026; full provenance,
URLs and the Wegovy back-test are in catalysts_FINDINGS.md):

A. ANNOUNCEMENTS - Search API (www.gov.uk/api/search.json), MHRA org,
   press_release/news_story formats, approval verbs. Near-zero lag, but MHRA
   only began press-releasing notable approvals ~2023/24 - this route alone
   would NOT have caught Wegovy in 2021 (verified: no 2021 release exists).
B. THE REGISTER - the "Marketing authorisations: lists of granted licences"
   collection: yearly Content-API pages (2021->today) holding fortnightly/
   monthly PDF lists of EVERY grant, published ~1-6 weeks late. Columns:
   PL Number | Grant Date | MA Holder | Licensed Name(s) | Active
   Ingredient | Quantity | Units | Legal Status | Territory. There is NO
   indication column, so conditions are inferred from a substance/brand
   vocabulary. VERIFIED: the Sept 2021 PDF contains "PLGB 04668/0433
   24/09/2021 NOVO NORDISK AS WEGOVY 2.4 MG ... SEMAGLUTIDE ... POM GB" -
   this route fires on Wegovy in Oct 2021, ~23 months early. PDF text
   extraction is best-effort stdlib, tested on a same-shape synthetic
   fixture, NOT on live MHRA bytes; a PDF that yields no rows is skipped,
   never guessed at.

THE POPULATION FILTER: the licence pipeline is dominated by rare oncology
and generics (the same Sept 2021 list has seven lenalidomide strengths),
which will never create a private-pay market. So (1) a whitelist of
large-population conditions decides what survives - precision over recall,
on purpose: a missed condition is recoverable elsewhere on the radar, while
a panel full of rare-oncology rows is unreadable; and (2) UK generics are
named after their substance ("SITAGLIPTIN 25 MG..."), so a register row
whose substance token appears twice (product name + ingredient column) is a
generic re-licence and is dropped ("WEGOVY ... SEMAGLUTIDE" = once = kept).

ROBOTS (fetched 13 Jul 2026): www.gov.uk disallows only /*/print$ and
/search/all* - /api/ is permitted, content is OGL-licensed;
assets.publishing.service.gov.uk serves no robots.txt (no restrictions);
products.mhra.gov.uk allows everything but is a client-side app whose
backend (medicines.api.mhra.gov.uk) timed out / answered empty -> NOT used.
All endpoints above answered this build's cloud (datacentre) egress.

Returns None only if NEITHER route could be reached. Stdlib only.
"""

import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zlib

try:
    from taxonomy import niche_of
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from taxonomy import niche_of
    except ImportError:                     # degrade: None niches are honest
        def niche_of(text):
            return None

SEARCH_API = "https://www.gov.uk/api/search.json"
YEAR_API = ("https://www.gov.uk/api/content/government/publications/"
            "marketing-authorisations-granted-in-%d")
MHRA_ORG = "medicines-and-healthcare-products-regulatory-agency"
UA = "uk-healthcare-radar/1.0 (trend research; python stdlib)"
REGISTER_FIRST_YEAR = 2021        # yearly pages start 2021 (monthly before)

# ================================================== LARGE-POPULATION FILTER
# condition -> (rough UK population, one plain line;  terms that identify it)
# Population figures are rounded public-body/charity estimates - order of
# magnitude only, and labelled "est." wherever they surface.
CONDITIONS = {
    "obesity / weight management": {
        "population": "about 13 million UK adults live with obesity (est.)",
        "terms": ["obesity", "obese", "weight loss", "weight management",
                  "semaglutide", "tirzepatide", "liraglutide", "orlistat",
                  "retatrutide", "cagrilintide", "orforglipron", "amycretin",
                  "wegovy", "mounjaro", "saxenda", "glp-1", "glp 1"],
    },
    "type 2 diabetes": {
        "population": "about 5.8 million people in the UK have diabetes (est.)",
        "terms": ["diabetes", "insulin", "dapagliflozin", "empagliflozin",
                  "metformin", "sitagliptin", "gliclazide"],
    },
    "ADHD": {
        "population": "roughly 2.6 million people in the UK may have ADHD (est.)",
        "terms": ["adhd", "attention deficit", "lisdexamfetamine",
                  "methylphenidate", "atomoxetine", "guanfacine",
                  "dexamfetamine", "centanafadine"],
    },
    "menopause": {
        "population": "about 13 million UK women are peri- or post-menopausal (est.)",
        "terms": ["menopause", "menopausal", "vasomotor symptoms", "hrt",
                  "hormone replacement", "estradiol", "estetrol",
                  "fezolinetant", "elinzanetant", "veoza"],
    },
    "depression / anxiety": {
        "population": "about 1 in 6 adults in England has anxiety or depression in any week (est.)",
        "terms": ["depression", "depressive", "anxiety", "antidepressant",
                  "esketamine", "psilocybin", "zuranolone"],
    },
    "dementia": {
        "population": "about 1 million people in the UK live with dementia (est.)",
        "terms": ["dementia", "alzheimer", "lecanemab", "donanemab",
                  "donepezil", "memantine"],
    },
    "migraine": {
        "population": "about 10 million people in the UK get migraines (est.)",
        "terms": ["migraine", "rimegepant", "atogepant", "zavegepant",
                  "erenumab", "fremanezumab", "galcanezumab", "eptinezumab"],
    },
    "eczema / atopic dermatitis": {
        "population": "eczema affects about 1 in 10 UK adults and 1 in 5 children (est.)",
        "terms": ["eczema", "atopic dermatitis", "dupilumab", "abrocitinib",
                  "tralokinumab", "lebrikizumab", "upadacitinib"],
    },
    "psoriasis": {
        "population": "about 1.1 million people in the UK have psoriasis (est.)",
        "terms": ["psoriasis", "bimekizumab", "deucravacitinib"],
    },
    "acne": {
        "population": "acne affects most teenagers; severe cases drive private dermatology (est.)",
        "terms": ["acne", "isotretinoin", "clascoterone"],
    },
    "hair loss": {
        "population": "about half of men have pattern hair loss by age 50 (est.)",
        "terms": ["hair loss", "alopecia", "finasteride", "minoxidil",
                  "ritlecitinib", "baricitinib"],
    },
    "erectile dysfunction": {
        "population": "over 4 million UK men experience erectile dysfunction (est.)",
        "terms": ["erectile dysfunction", "erectile", "sildenafil",
                  "tadalafil", "vardenafil"],
    },
    "insomnia": {
        "population": "about 1 in 3 UK adults reports insomnia symptoms (est.)",
        "terms": ["insomnia", "daridorexant", "lemborexant", "suvorexant",
                  "melatonin"],
    },
    "irritable bowel syndrome": {
        "population": "about 1 in 10 people in the UK has IBS symptoms (est.)",
        "terms": ["irritable bowel", "ibs", "linaclotide"],
    },
    "arthritis / joint pain": {
        "population": "about 10 million people in the UK have arthritis or a similar condition (est.)",
        "terms": ["osteoarthritis", "arthritis"],
    },
    "osteoporosis": {
        "population": "about 3.5 million people in the UK have osteoporosis (est.)",
        "terms": ["osteoporosis", "romosozumab", "abaloparatide", "denosumab"],
    },
    "high blood pressure": {
        "population": "about 14 million people in the UK have high blood pressure (est.)",
        "terms": ["hypertension", "blood pressure", "aprocitentan",
                  "baxdrostat", "zilebesiran"],
    },
    "asthma / COPD": {
        "population": "about 5.4 million people in the UK receive asthma treatment; 1.2 million have COPD (est.)",
        "terms": ["asthma", "copd", "tezepelumab", "benralizumab",
                  "ensifentrine"],
    },
    "fertility": {
        "population": "about 1 in 7 UK couples has difficulty conceiving (est.)",
        "terms": ["fertility", "ivf", "in vitro fertilisation"],
    },
    "incontinence / overactive bladder": {
        "population": "about 14 million people in the UK have bladder-control problems (est.)",
        "terms": ["incontinence", "overactive bladder", "mirabegron",
                  "vibegron"],
    },
    "allergy": {
        "population": "about 1 in 3 people in the UK lives with at least one allergy (est.)",
        "terms": ["allergy", "allergic rhinitis", "hay fever", "anaphylaxis",
                  "omalizumab", "peanut allergy"],
    },
    "addiction / smoking": {
        "population": "about 6 million UK adults smoke; about 600,000 in England are alcohol-dependent (est.)",
        "terms": ["smoking cessation", "nicotine dependence", "varenicline",
                  "cytisine", "cytisinicline", "opioid dependence",
                  "alcohol dependence", "buprenorphine"],
    },
    "sleep apnoea": {
        "population": "well over 1 million UK adults are thought to have sleep apnoea, most undiagnosed (est.)",
        "terms": ["sleep apnoea", "sleep apnea", "excessive daytime sleepiness",
                  "pitolisant", "solriamfetol"],
    },
}

# brand -> substance, used only to print nicer names ("Wegovy (semaglutide)")
BRANDS = {
    "wegovy": "semaglutide", "mounjaro": "tirzepatide",
    "saxenda": "liraglutide", "ozempic": "semaglutide",
    "cibinqo": "abrocitinib", "ozawade": "pitolisant",
    "veoza": "fezolinetant", "quviviq": "daridorexant",
    "leqembi": "lecanemab", "kisunla": "donanemab",
}

# Route A gates: a title/description must contain an approval word and no
# noise word. MHRA also press-releases recalls, warnings and consultations.
APPROVAL_WORDS = ("approve", "approval", "licensed", "licence granted",
                  "authorised", "authorisation granted", "green light")
NOISE_WORDS = ("recall", "falsified", "fake", "warning", "warns", "misuse",
               "side effect", "shortage", "defect", "consultation",
               "reminds", "guidance for", "safety review", "contraception")


# ======================================================== NETWORK (one door)
def _fetch(url, timeout=30):
    """GET url -> bytes, or None. The single network door (tests stub it)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def _fetch_json(url):
    raw = _fetch(url)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None


# ==================================================== CONDITION / NAME MATCH
def _norm(text):
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip() + " "


def _match_condition(text):
    """Longest whole-word/phrase vocabulary hit -> (condition, matched term)."""
    t = _norm(text)
    best = (None, "")
    for cond, spec in CONDITIONS.items():
        for term in spec["terms"]:
            if (" " + term + " ") in t and len(term) > len(best[1]):
                best = (cond, term)
    return best


def _pretty_name(text, matched_term):
    """'Wegovy (semaglutide)' if a known brand is present, else the term."""
    t = _norm(text)
    for brand, substance in BRANDS.items():
        if (" " + brand + " ") in t:
            return "%s (%s)" % (brand.capitalize(), substance)
    return matched_term.capitalize()


def _record(name, cond, date_iso, source_url, headline=None):
    spec = CONDITIONS[cond]
    lead = (headline.rstrip(". ") if headline
            else "Newly licensed in the UK for " + cond)
    return {
        "name": name,
        "condition": cond,
        "niche": niche_of("%s %s %s" % (name, cond, headline or "")),
        "date": date_iso,
        "population": spec["population"],
        "why": "%s; %s." % (lead, spec["population"]),
        "source_url": source_url,
    }


# ========================================== ROUTE A - MHRA announcements
def _news_pages(since_iso):
    """Yield result items from the Search API, both formats, paged."""
    for fmt in ("press_release", "news_story"):
        start = 0
        while start < 800:                       # safety cap
            q = urllib.parse.urlencode({
                "filter_organisations": MHRA_ORG,
                "filter_format": fmt,
                "filter_public_timestamp": "from:" + since_iso,
                "order": "-public_timestamp",
                "fields": "title,description,link,public_timestamp,format",
                "count": "200", "start": str(start),
            })
            page = _fetch_json(SEARCH_API + "?" + q)
            if page is None or "results" not in page:
                yield None                       # signal: this route errored
                return
            for item in page["results"]:
                yield item
            start += 200
            if start >= int(page.get("total", 0)):
                break


def _parse_news_item(item):
    """One search-API item -> record or None."""
    title = item.get("title") or ""
    desc = item.get("description") or ""
    text = title + " " + desc
    low = text.lower()
    if not any(w in low for w in APPROVAL_WORDS):
        return None
    if any(w in low for w in NOISE_WORDS):
        return None
    cond, term = _match_condition(text)
    if cond is None:
        return None                              # not a large-population story
    date_iso = (item.get("public_timestamp") or "")[:10] or None
    link = item.get("link") or ""
    url = "https://www.gov.uk" + link if link.startswith("/") else link
    return _record(_pretty_name(text, term), cond, date_iso, url,
                   headline=title.strip())


def _from_news(since_iso):
    """-> (records, route_ok)."""
    out, ok = [], True
    for item in _news_pages(since_iso):
        if item is None:
            ok = False
            break
        rec = _parse_news_item(item)
        if rec:
            out.append(rec)
    return out, ok


# ====================================== ROUTE B - the granted-licence lists
_TJ_ARRAY = re.compile(rb"\[((?:\((?:\\.|[^\\()])*\)|[^\]])*)\]\s*TJ")
_PDF_STR = re.compile(rb"\((?:\\.|[^\\()])*\)")


def _pdf_str(body):
    body = re.sub(rb"\\([0-7]{1,3})",
                  lambda g: bytes([int(g.group(1), 8) & 0xFF]), body)
    return (body.replace(b"\\(", b"(").replace(b"\\)", b")")
                .replace(b"\\\\", b"\\")).decode("latin-1", "replace")


def _pdf_text(data):
    """Best-effort text from a simple PDF (Flate streams, Tj/TJ operators).

    TJ arrays put kerning numbers between strings: a small |kern| is letter
    spacing INSIDE a word (join directly, healing 'WEGO','VY' -> 'WEGOVY'),
    a large |kern| is a word gap (join with a space; 100/1000 em is the
    usual cut). Verified against a synthetic fixture of the same operator
    family only, NOT against live MHRA bytes - a real PDF that yields no PL
    rows is simply skipped by the caller.
    """
    if not data or b"%PDF" not in data[:1024]:
        return ""
    pieces = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass                                  # already-plain stream
        if b"Tj" not in raw and b"TJ" not in raw:
            continue
        for arr in _TJ_ARRAY.finditer(raw):       # kern-aware TJ arrays
            body, joined, last = arr.group(1), "", 0
            for sm in _PDF_STR.finditer(body):
                kern = re.search(rb"-?\d+(?:\.\d+)?", body[last:sm.start()])
                if joined and kern and abs(float(kern.group(0).decode())) >= 100:
                    joined += " "
                joined += _pdf_str(sm.group(0)[1:-1])
                last = sm.end()
            pieces.append(joined)
        rest = _TJ_ARRAY.sub(b" ", raw)           # then the plain Tj strings
        for s in _PDF_STR.findall(rest):
            pieces.append(_pdf_str(s[1:-1]))
    return " ".join(p for p in pieces if p)


ROW_ANCHOR = re.compile(r"\bPL(?:GB|NI)?\s*\d{5}\s*/\s*\d{4}\b")
ROW_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def _register_rows(text):
    """Split extracted list text into per-licence row strings."""
    hits = list(ROW_ANCHOR.finditer(text))
    rows = []
    for i, h in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        rows.append(text[h.start():end])
    return rows


def _parse_register_row(row):
    """One PL row -> record or None (population filter + generic heuristic)."""
    cond, term = _match_condition(row)
    if cond is None:
        return None
    # generics are named after their substance, so the substance token
    # appears twice (product name + ingredient column). Branded = once.
    if len(re.findall(r"\b%s\b" % re.escape(term), _norm(row))) >= 2:
        return None
    m = ROW_DATE.search(row)
    date_iso = "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None
    return _record(_pretty_name(row, term), cond, date_iso, None)


def _attachment_in_window(title, filename, since):
    """Keep an attachment unless its title/filename clearly pre-dates the
    window. Row-level grant dates do the precise filtering afterwards."""
    text = "%s %s" % (title or "", filename or "")
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", text)]
    return (max(years) >= since.year) if years else True


def _from_register(since, cache_path):
    """-> (records, route_ok). Parsed PDFs are cached: lists never change."""
    cache = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f).get("attachments", {})
        except Exception:
            cache = {}
    records, touched_net, changed = [], False, False
    today = dt.date.today()
    for year in range(max(since.year, REGISTER_FIRST_YEAR), today.year + 1):
        doc = _fetch_json(YEAR_API % year)
        if doc is None:
            continue                              # year page missing/unreachable
        touched_net = True
        atts = (doc.get("details") or {}).get("attachments") or []
        for att in atts:
            url = att.get("url")
            if not url or not _attachment_in_window(
                    att.get("title"), att.get("filename"), since):
                continue
            if url in cache:                      # already parsed once
                rows = cache[url]
            else:
                data = _fetch(url)
                if data is None:
                    continue
                rows = []
                for row in _register_rows(_pdf_text(data)):
                    rec = _parse_register_row(row)
                    if rec:
                        rec["source_url"] = url
                        rows.append(rec)
                cache[url] = rows
                changed = True
            records.extend(dict(r) for r in rows)
    if cache_path and changed:
        try:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"attachments": cache}, f, indent=1)
        except Exception:
            pass                                  # cache is a nicety only
    return records, touched_net


# ==================================================================== PUBLIC
def catalysts(months=24, cache="data/catalysts.json"):
    """New UK medicine licences / approvals that could CREATE a private-pay
    market. Returns [{"name", "condition", "niche", "date", "population",
    "why", "source_url"}] sorted newest first, or None if no source could
    be reached. Dates are grant dates (register route) or GOV.UK publication
    timestamps (announcement route) - treat the latter as approximate.
    """
    since = dt.date.today() - dt.timedelta(days=int(months * 30.44))
    since_iso = since.isoformat()
    news, ok_a = _from_news(since_iso)
    reg, ok_b = _from_register(since, cache)
    if not ok_a and not ok_b:
        return None
    merged = {}
    for rec in reg + news:                        # register first: real dates
        if rec["date"] and rec["date"] < since_iso:
            continue
        key = (rec["name"].lower(), rec["condition"])
        prev = merged.get(key)
        if prev is None or (rec["date"] or "9") < (prev["date"] or "9"):
            merged[key] = rec                     # keep the EARLIEST sighting
    return sorted(merged.values(), key=lambda r: r["date"] or "", reverse=True)


# ================================================================= SELF-TEST
def _make_pdf(lines):
    """Minimal one-page PDF whose content stream shows each line with Tj,
    plus one kerned TJ array - the same operator family as real Word/GOV.UK
    exports. Used ONLY to test the extractor's parsing, not MHRA's bytes."""
    ops = ["BT /F1 8 Tf 10 800 Td"]
    for ln in lines:
        safe = ln.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        ops.append("(%s) Tj 0 -12 Td" % safe)
    ops.append("[(PLGB 04668/0433  24/09/2021  NOVO NORDISK AS  WEGO) -15 "
               "(VY 2.4 MG, SOLUTION FOR INJECTION IN PRE-FILLED PEN  "
               "SEMAGLUTIDE  3.2  MILLIGRAMS PER MILLILITRE  POM  GB) ] TJ")
    ops.append("ET")
    stream = zlib.compress(" ".join(ops).encode("latin-1"))
    return (b"%PDF-1.4\n1 0 obj<</Length " + str(len(stream)).encode() +
            b"/Filter/FlateDecode>>\nstream\n" + stream +
            b"endstream\nendobj\ntrailer<<>>\n%%EOF")


# real rows quoted from the verified September 2021 list (source_url in
# catalysts_FINDINGS.md); oncology/generic rows are the filter's test food.
_FIX_ROWS = [
    "PL 29831/0716  03/09/2021  WOCKHARDT UK LIMITED  LENALIDOMIDE 2.5 MG "
    "HARD CAPSULES  LENALIDOMIDE  2.5  MILLIGRAMS  POM  UK",
    "PL 08553/0719  08/09/2021  DR REDDY'S LABORATORIES (UK) LIMITED  "
    "SUNITINIB DR. REDDY'S 12.5MG HARD CAPSULES  SUNITINIB MALATE  16.71  "
    "MILLIGRAMS  POM  UK",
    "PLGB 00057/1703  08/09/2021  PFIZER LIMITED  CIBINQO 50 MG FILM-COATED "
    "TABLETS  ABROCITINIB  50  MILLIGRAMS  POM  GB",
    "PLGB 18813/0004  15/09/2021  BIOPROJET UK LIMITED  OZAWADE 4.5MG "
    "FILM-COATED TABLET  PITOLISANT HYDROCHLORIDE  5 MILLIGRAMS  POM  GB",
    "PLGB 54365/0001  15/09/2021  RHYTHM PHARMACEUTICALS LIMITED  IMCIVREE "
    "10 MG/ML SOLUTION FOR INJECTION  SETMELANOTIDE  10  MILLIGRAMS PER "
    "MILLILITRE  POM  GB",
    "PL 20075/1399  15/09/2021  ACCORD HEALTHCARE LIMITED  METFORMIN "
    "HYDROCHLORIDE 500 MG FILM-COATED TABLETS  METFORMIN HYDROCHLORIDE  500  "
    "MILLIGRAMS  POM  UK",
    "PLGB 04668/0429  24/09/2021  NOVO NORDISK AS  WEGOVY 0.25 MG, SOLUTION "
    "FOR INJECTION IN PRE-FILLED PEN  SEMAGLUTIDE  0.5  MILLIGRAMS PER "
    "MILLILITRE  POM  GB",
    "PLGB 04668/0430  24/09/2021  NOVO NORDISK AS  WEGOVY 0.5 MG, SOLUTION "
    "FOR INJECTION IN PRE-FILLED PEN  SEMAGLUTIDE  1 MILLIGRAMS PER "
    "MILLILITRE  POM  GB",
]

# real titles quoted from the verified live Search API responses
_FIX_NEWS = [
    {"title": "MHRA approves GLP -1 receptor agonist semaglutide to reduce "
              "risk of serious heart problems in obese or overweight adults",
     "description": "", "format": "press_release",
     "link": "/government/news/mhra-approves-glp-1-receptor-agonist-semaglutide",
     "public_timestamp": "2024-07-23T14:20:59Z"},
    {"title": "Four-dose Mounjaro “KwikPen” approved by MHRA for "
              "diabetes and weight management",
     "description": "", "format": "press_release",
     "link": "/government/news/four-dose-mounjaro-kwikpen",
     "public_timestamp": "2024-01-25T17:00:19Z"},
    {"title": "MHRA warns of unsafe fake weight loss pens",
     "description": "", "format": "press_release",
     "link": "/government/news/mhra-warns", "public_timestamp": "2023-10-25T23:00:00Z"},
    {"title": "MHRA approves lenmeldy for metachromatic leukodystrophy",
     "description": "rare disease gene therapy", "format": "press_release",
     "link": "/government/news/rare", "public_timestamp": "2024-03-01T00:00:00Z"},
]


def _selftest():
    checks, fails = [], 0

    def ok(name, cond):
        nonlocal fails
        checks.append(("PASS" if cond else "FAIL", name))
        fails += 0 if cond else 1

    # -- population filter + niche mapping, no I/O ------------------------
    ok("obesity text -> Weight loss / GLP-1 niche",
       _record("Wegovy (semaglutide)", "obesity / weight management",
               "2021-09-24", None)["niche"] == "Weight loss / GLP-1")
    ok("adhd term maps", _match_condition("centanafadine for ADHD")[0] == "ADHD")
    ok("rare oncology is dropped", _match_condition(
        "LENMELDY for metachromatic leukodystrophy")[0] is None)
    # "arthritis" itself is absent from the taxonomy, but the condition
    # label carries "joint pain" and the taxonomy's whole-word "joint"
    # catches it -> MSK / physio. A fair mapping, found by the matcher.
    ok("arthritis condition maps via 'joint' to MSK / physio",
       _match_condition("new osteoarthritis tablet")[0] is not None and
       _record("x", "arthritis / joint pain", None, None)["niche"] == "MSK / physio")

    # -- register route on a synthetic PDF of REAL Sept-2021 rows ---------
    pdf = _make_pdf(_FIX_ROWS)
    rows = _register_rows(_pdf_text(pdf))
    ok("pdf extractor finds all 9 PL rows", len(rows) == len(_FIX_ROWS) + 1)
    recs = [r for r in (_parse_register_row(x) for x in rows) if r]
    names = sorted({r["name"] for r in recs})
    ok("Wegovy caught from the register",
       any(r["name"] == "Wegovy (semaglutide)" and r["date"] == "2021-09-24"
           for r in recs))
    ok("kerned TJ row still reads WEGOVY",
       sum(1 for r in recs if r["name"] == "Wegovy (semaglutide)") == 3)
    ok("Cibinqo (eczema) caught and mapped to Dermatology / acne",
       any(r["name"] == "Cibinqo (abrocitinib)" and
           r["niche"] == "Dermatology / acne" for r in recs))
    ok("Ozawade (sleep apnoea) caught and mapped to Sleep",
       any(r["name"] == "Ozawade (pitolisant)" and r["niche"] == "Sleep"
           for r in recs))
    ok("lenalidomide / sunitinib / setmelanotide dropped (small population)",
       not any("lenalidomide" in n.lower() or "sunitinib" in n.lower() or
               "setmelanotide" in n.lower() for n in names))
    ok("metformin generic dropped (substance named twice)",
       not any("metformin" in n.lower() for n in names))

    # -- announcement route on real-shaped fixtures ------------------------
    news = [r for r in (_parse_news_item(i) for i in _FIX_NEWS) if r]
    ok("two real approval headlines kept", len(news) == 2)
    ok("fake-pen warning and rare-disease approval excluded",
       not any("fake" in (r["why"] or "").lower() for r in news) and
       not any("lenmeldy" in (r["name"] or "").lower() for r in news))
    ok("news date comes from public_timestamp",
       any(r["date"] == "2024-07-23" for r in news))
    ok("why is one plain sentence with a population",
       all(r["why"].endswith(".") and "est." in r["why"] and
           "\n" not in r["why"] for r in news + recs))

    # -- dedupe + merge -----------------------------------------------------
    merged = {}
    for rec in recs:
        key = (rec["name"].lower(), rec["condition"])
        prev = merged.get(key)
        if prev is None or (rec["date"] or "9") < (prev["date"] or "9"):
            merged[key] = rec
    ok("three Wegovy strengths collapse to one record",
       sum(1 for k in merged if k[0] == "wegovy (semaglutide)") == 1)

    # -- failure semantics: no network => None ------------------------------
    global _fetch
    real = _fetch
    _fetch = lambda url, timeout=30: None
    try:
        ok("catalysts() degrades to None when nothing is reachable",
           catalysts(months=1, cache=None) is None)
    finally:
        _fetch = real

    for status, name in checks:
        print("%s  %s" % (status, name))
    print("=" * 64)
    print("%d/%d passed" % (len(checks) - fails, len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--live" in sys.argv:
        rows = catalysts()
        if rows is None:
            print("catalysts: no source reachable")
        else:
            for r in rows:
                print(json.dumps(r, indent=1))
            print("%d catalyst(s)" % len(rows))
    else:
        raise SystemExit(_selftest())
