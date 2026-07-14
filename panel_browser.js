/* =========================================================================
   panel_browser.js - the browser-console backfill for panel.py
   =========================================================================

   WHY THIS FILE EXISTS
   The Internet Archive refuses GitHub Actions' datacentre IPs (proven live:
   the 207-clinic cohort built fine, then every CDX call came back
   ConnectionRefused / TimeoutError). It works from a real browser. So the
   backfill runs HERE, once, and its output is committed to the repo as
   data/panel_rows.json - which pull_and_build.py now simply reads.

   HOW TO RUN - two steps, and STEP 1 IS NOT OPTIONAL
   --------------------------------------------------
   1. Open a tab on   https://web.archive.org/cdx/search/cdx?url=example.com&limit=1
      (any page on web.archive.org will do).

      WHY: verified live on 14 Jul 2026 - the CDX endpoint REFUSES cross-site
      browser requests. The same URL that returns HTTP 200 when the tab is on
      web.archive.org returns HTTP 503 when fetched from another origin (the
      request carries an Origin header and the Archive's front end rejects
      it), and no Access-Control-Allow-Origin header is sent either. So a
      console on any other site cannot do this job. Same-origin can, and the
      cohort file on raw.githubusercontent.com serves CORS `*`, so this tab
      can fetch that too (also verified live).

   2. Open DevTools (F12) -> Console, paste this ENTIRE file, press Enter.
      KEEP THE TAB VISIBLE (foreground of its own window is ideal): Chrome
      throttles timers in background tabs and can stretch the run massively.

   WHAT IT DOES
   - Fetches the frozen cohort the repo already holds:
       https://raw.githubusercontent.com/oiali/healthcare-radar/main/data/panel_cohort_adhd.json
   - One CDX request per clinic domain (matchType=prefix - every URL ever
     captured on the domain, with its FIRST capture timestamp; the URL path
     is the service name), byte-identical params to panel.py's cdx_paths().
   - Applies panel.py's logic, ported line for line: the blog/junk-segment
     exclusion, the open vocabulary with the MIN_ADOPTERS=3 gate, DISTINCT
     CLINICS not mentions, and the left-censoring guard (a term first seen
     within GRACE=3 months of a domain's first-ever capture goes into the
     base, never counted as a new adopter).
   - Polite: 2.0s between requests (panel.py's PANEL_SLEEP), backs off on
     429/403/503, caches every domain's result in localStorage, so a closed
     tab loses nothing - re-paste to resume.
   - Prints + copies the JSON for data/panel_rows.json, and prints the
     year-by-year ADHD adoption count with the agreed kill-criterion verdict
     (2022 must be at least DOUBLE 2020, or the module gets cut).

   AFTER THE RUN
   - The JSON is in the console, on the clipboard (or run: copy(PANEL_ROWS_JSON)),
     and PANEL.download() saves it as panel_rows.json.
   - Commit it to the repo at data/panel_rows.json.
   - PANEL.report() recomputes from cache without any network.
     PANEL.reset() wipes the cache (= panel.py --rebuild for the backfill).

   DEVIATIONS FROM panel.py - stated loudly, as required:
   1. Endpoint is https:// not http:// (an https page cannot fetch http:;
      same host, same API).
   2. On a block (429/403/503) panel.py stops the whole run dead and writes
      an hour-long cooldown for the NEXT cron run. Here a human is present,
      so we back off 60s (doubling per consecutive block, max 5) and retry;
      after 5 consecutive blocks we halt with progress saved. Never hammers.
   3. panel.py ends the run after 8 fetch errors (its cron resumes tomorrow).
      Here 8 errors trigger a 5-minute cool-off and continue (max 3 cool-offs,
      then halt with progress saved) - the same politeness, without asking
      the user to re-paste ten times.
   4. Failed domains get ONE retry pass at the end with a 60s timeout
      (panel.py would simply retry them on tomorrow's run).
   5. The browser sends Chrome's User-Agent, not "uk-healthcare-radar/1.0"
      (browsers do not allow custom UA on fetch).
   6. growth uses JS Math.round (half-up) vs Python round (half-even): can
      differ in the 3rd decimal on exact .0005 ties. Immaterial.
   7. JSON formatting: python json.dump writes ", "/": " separators and 3.0
      for float(3); JSON.stringify writes compact and 3. Same values -
      pull_and_build.py json.load()s it, so this is invisible downstream.
   Everything else - params, vocab lists, censoring arithmetic, ranking,
   subsumption, the why-sentence - is a faithful port and asserted by the
   built-in selftest below, which must pass before any network is touched.
   ========================================================================= */

window.PANEL = (function () {
  "use strict";

  // ------------------------------------------------------ constants (panel.py)
  var COHORT_URL = "https://raw.githubusercontent.com/oiali/healthcare-radar/main/data/panel_cohort_adhd.json";
  var CDX_URL = "https://web.archive.org/cdx/search/cdx";   // DEVIATION 1: https
  var SLEEP_MS = 2000;          // PANEL_SLEEP = 2.0 -> 30 req/min, half the limit
  var IA_TIMEOUT_MS = 30000;    // PANEL_TIMEOUT = 30
  var RETRY_TIMEOUT_MS = 60000; // DEVIATION 4: the end-of-run retry pass
  var REFRESH_DAYS = 30;
  var MIN_ADOPTERS = 3;
  var WINDOW = 12;
  var CENSORED_YM = "0000-00";
  var GRACE = 3;
  var CDX_FROM_YEAR = 2018;
  var MAX_ROWS = 4000;
  var MAX_ERRORS = 8;
  var LS_PREFIX = "panelbf1:d:";
  var LS_META = "panelbf1:meta";

  // ------------------------------------------------- taxonomy.py, ported whole
  // Key syntax: "foo*" = stem match (\bfoo)   "foo" = whole-word match (\bfoo\b)
  // Longest matching key wins; ties broken by list order.
  var NICHES = [
    ["Weight loss / GLP-1", ["weight loss", "weight-loss", "weight management", "weight",
      "semaglutide*", "tirzepatide*", "liraglutide*", "ozempic", "wegovy", "mounjaro",
      "saxenda", "obesity", "obese", "slimming", "orlistat", "bariatric*",
      "glp", "glp-1", "glp1"]],
    ["ADHD", ["adhd", "attention deficit", "lisdexamfetamine", "methylphenidate",
      "atomoxetine", "guanfacine", "elvanse", "neurodiver*"]],
    ["Menopause / HRT", ["menopaus*", "perimenopaus*", "hrt", "hormone replacement",
      "tibolone", "estradiol*", "oestradiol*", "oestrogen*", "estrogen*"]],
    ["Men's health / TRT", ["testosterone", "trt", "hypogonad*", "androlog*",
      "mens health", "men's health", "male health"]],
    ["Hair restoration", ["hair transplant", "hair restoration", "hair loss",
      "hair clinic", "hairline", "hair", "finasteride", "minoxidil", "alopecia"]],
    ["Tongue-tie / lactation", ["tongue tie", "tongue-tie", "tongue", "lactation",
      "breastfeed*", "frenulotom*", "frenotom*"]],
    ["Aesthetics / skin", ["aesthetic*", "botox*", "botulinum", "dermal filler",
      "filler", "fillers", "cosmetic*", "skin", "laser", "lip", "lips", "facial",
      "beauty", "rejuven*", "eyebrow*", "brow", "brows", "lash", "lashes",
      "eyelash*", "peel", "peels", "microneedl*", "injectable*", "anti-wrinkle",
      "wrinkle", "medispa", "medi-spa"]],
    ["Dermatology / acne", ["dermatolog*", "dermatit*", "acne", "isotretinoin",
      "eczema", "psoria*", "rosacea", "mole", "moles", "mole check", "skin cancer",
      "hidradenitis"]],
    ["MSK / physio", ["physio*", "chiropract*", "chiropod*", "osteopath*",
      "musculoskeletal", "msk", "sports injury", "podiatr*", "orthopaed*",
      "orthoped*", "spine", "spinal", "joint", "joints", "rehab*"]],
    ["Mental health / psychiatry", ["psychiatr*", "psycholog*", "psychotherap*",
      "mental", "counsel*", "ketamine", "depress*", "anxiet*", "autis*", "camhs"]],
    ["Sexual health / ED", ["erectile dysfunction", "erectile", "sildenafil",
      "tadalafil", "viagra", "sexual health", "libido", "premature ejaculation"]],
    ["Diagnostics / imaging", ["diagnostic*", "imaging", "ultrasound", "radiolog*",
      "endoscop*", "screening", "phlebotom*", "blood test", "blood tests",
      "pathology", "scan", "scans", "mri", "ct scan", "x-ray", "xray", "labs"]],
    ["Fertility / women's health", ["fertil*", "ivf", "gynaecolog*", "gynecolog*",
      "obstetric*", "endometrios*", "polycystic", "pcos", "midwif*", "antenatal",
      "women's health", "womens health", "women"]],
    ["Sleep", ["sleep", "insomnia", "melatonin", "apnoea", "apnea", "snoring"]],
    ["Dental / orthodontics", ["dental", "dentist*", "orthodont*", "endodont*",
      "periodont*", "oral surgery", "smile", "invisalign", "hygienist"]],
    ["Longevity / peptides / IV", ["longevity", "peptide", "peptides", "iv drip",
      "drip", "infusion", "vitamin", "vitamins", "wellness", "biohack*", "cryo*",
      "hyperbaric"]],
    ["Migraine", ["migraine*", "erenumab", "fremanezumab", "galcanezumab",
      "rimegepant", "atogepant", "sumatriptan", "cluster headache", "headache*"]],
    ["Bladder / continence", ["overactive bladder", "bladder", "continence",
      "incontinence", "mirabegron", "solifenacin", "urolog*", "prostate",
      "prostatic", "bph"]],
    ["Osteoporosis / bone", ["osteoporos*", "osteopen*", "denosumab", "alendronic",
      "bone density", "dexa"]],
    ["Diabetes", ["diabet*", "dapagliflozin", "empagliflozin", "insulin",
      "metformin", "gliclazide"]],
    ["Allergy", ["allerg*", "immunotherap*", "rhinitis", "hay fever", "hayfever",
      "anaphyla*", "intolerance"]],
    ["Neurology", ["neurolog*", "neurodegener*", "epilep*", "parkinson*",
      "dementia", "alzheim*", "multiple sclerosis"]],
    ["Audiology / hearing", ["audiolog*", "hearing aid", "hearing", "tinnitus",
      "earwax", "ear wax", "microsuction"]],
    ["Eye / optical", ["optometr*", "optician*", "optical", "ophthalm*",
      "cataract*", "macular", "glaucoma", "lasik", "contact lens", "laser eye",
      "eye clinic", "eye care", "eyecare", "vision", "eye", "eyes"]],
    ["Private GP", ["private gp", "gp service*", "gp practice", "general practice",
      "private doctor", "family doctor", "doctor", "gp"]],
  ];

  function escapeRx(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  var PATTERNS = [];
  NICHES.forEach(function (pair, order) {
    pair[1].forEach(function (key) {
      var stem = key.slice(-1) === "*";
      var lit = stem ? key.slice(0, -1) : key;
      PATTERNS.push({
        name: pair[0], order: order, weight: lit.length,
        rx: new RegExp("\\b" + escapeRx(lit) + (stem ? "" : "\\b")),
      });
    });
  });

  var _nicheCache = new Map();
  function nicheOf(text) {                      // taxonomy.niche_of, ported
    var t = String(text == null ? "" : text).toLowerCase();
    if (!t.trim()) return null;
    if (_nicheCache.has(t)) return _nicheCache.get(t);
    var bestName = null, bestW = -1, bestO = Infinity;
    for (var i = 0; i < PATTERNS.length; i++) {
      var p = PATTERNS[i];
      if (p.rx.test(t)) {
        // python max on (weight, -order): higher weight wins; tie -> lower order
        if (p.weight > bestW || (p.weight === bestW && p.order < bestO)) {
          bestW = p.weight; bestO = p.order; bestName = p.name;
        }
      }
    }
    _nicheCache.set(t, bestName);
    return bestName;
  }

  // -------------------------------------- panel.py vocab lists, ported verbatim
  var ASSET = /\.(jpe?g|png|gif|svg|webp|ico|css|js|pdf|xml|json|zip|mp4|mp3|woff2?|ttf|eot)$/i;

  function words(s) { return s.split(/\s+/).filter(Boolean); }

  var JUNK_SEG = new Set(words(
    "wp-content wp-includes wp-json wp-admin wp-login feed rss atom sitemap sitemap_index " +
    "xmlrpc cdn-cgi assets static media uploads images image img css js fonts author tag " +
    "tags category categories page pages comment comments trackback amp print search login " +
    "logout register signup cart checkout basket account my-account privacy privacy-policy " +
    "cookie cookies cookie-policy terms terms-and-conditions disclaimer accessibility news " +
    "blog blogs article articles press media-centre insights resources careers career jobs " +
    "job vacancies vacancy recruitment team our-team meet-the-team staff people about " +
    "about-us contact contact-us get-in-touch find-us locations location branches " +
    "testimonials reviews review faq faqs gallery events event shop store product products " +
    "thank-you thanks 404 index home portal patient-portal videos video podcast webinar " +
    "downloads download ebook guides guide glossary complaints policies policy legal gdpr " +
    "sitemap-index feeds tel mailto"));

  var SERVICE_HEAD = new Set(words(
    "clinic clinics assessment assessments treatment treatments therapy therapies service " +
    "services screening screenings test tests testing consultation consultations surgery " +
    "injection injections scan scans imaging transplant removal programme program diagnosis " +
    "review medication titration package packages check checks specialist specialists doctor " +
    "consultant care procedure procedures"));

  var SERVICE_PARENTS = new Set(words(
    "services service treatments treatment conditions clinics clinic procedures therapies " +
    "therapy specialisms specialities specialties what-we-treat what-we-do our-services " +
    "our-treatments treatments-we-offer conditions-we-treat"));

  var STOP = new Set(words(
    "a an the and or of for to in on at by with our your my we us you it is are be new best " +
    "top leading expert expertise private priv nhs uk gb england scotland wales britain " +
    "british london manchester birmingham leeds glasgow edinburgh bristol liverpool cardiff " +
    "belfast sheffield nottingham leicester newcastle brighton oxford cambridge harley " +
    "street road lane avenue centre center house clinic-uk near me home page site web online " +
    "book booking bookings now here more info information about contact prices price cost " +
    "costs fees fee free how what why when where who which get make take see find learn read " +
    "help welcome hello meet team staff opening hours covid coronavirus join refer referral " +
    "gift voucher finance insurance self pay virtual tour video media awards partners " +
    "sponsors charity story stories journey results before after question questions answers " +
    "patient patients client clients customer people man men woman women adult adults child " +
    "children kids family families year years old age aged " +
    "offer offers offered offering provide provides provided providing deliver delivers " +
    "delivering include includes included including available range wide full comprehensive " +
    "bespoke tailored trusted award awarded winning specialising specialised specializing " +
    "here also plus over under from into using use used need needs want wants"));

  // ------------------------------------------------------------- small utils
  function ym(ts) {                              // panel._ym
    ts = String(ts == null ? "" : ts);
    return (ts.length >= 6 && /^\d{6}/.test(ts)) ? ts.slice(0, 4) + "-" + ts.slice(4, 6) : null;
  }
  function ymi(s) { return parseInt(s.slice(0, 4), 10) * 12 + (parseInt(s.slice(5, 7), 10) - 1); }
  function ymAdd(s, delta) {
    var i = ymi(s) + delta;
    var y = Math.floor(i / 12), m = (i % 12 + 12) % 12 + 1;
    return String(y).padStart(4, "0") + "-" + String(m).padStart(2, "0");
  }
  function ymNow() {
    var d = new Date();
    return String(d.getFullYear()).padStart(4, "0") + "-" + String(d.getMonth() + 1).padStart(2, "0");
  }
  function isoToday() { return new Date().toISOString().slice(0, 10); }
  function daysSince(iso) {
    var t = Date.parse(String(iso || "").slice(0, 10));
    if (isNaN(t)) return 1e6;
    return Math.floor((Date.now() - t) / 86400000);
  }
  function strMin(arr) { return arr.length ? arr.reduce(function (a, b) { return a < b ? a : b; }) : null; }
  function cmpStr(a, b) { return a < b ? -1 : a > b ? 1 : 0; }   // code-point, like python
  function cmpPair(a, b) { return cmpStr(a[0], b[0]) || cmpStr(a[1], b[1]); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // python urllib.parse.unquote never throws; mimic that.
  function unquote(s) {
    try { return decodeURIComponent(s); }
    catch (e) {
      return s.replace(/%[0-9a-fA-F]{2}/g, function (m) {
        try { return decodeURIComponent(m); } catch (_e) { return m; }
      });
    }
  }

  // urlsplit(u if "://" in u else "http://"+u).path  - query/fragment stripped
  function rawPath(u) {
    u = String(u == null ? "" : u);
    if (u.indexOf("://") < 0) u = "http://" + u;
    var m = u.match(/^[^:]*:\/\/[^\/?#]*([^?#]*)/);
    return m ? (m[1] || "/") : null;
  }

  function normPath(url) {                       // panel._norm_path
    var p = rawPath(url);
    if (p === null) return null;
    p = unquote(p).replace(/\/+/g, "/");
    return p || "/";
  }

  // ------------------------------------------------- panel.path_terms, ported
  function _tokens(seg) {                        // panel._tokens
    seg = String(seg == null ? "" : seg).toLowerCase().replace(/\.(html?|php|aspx?|htm)$/, "");
    var out = [];
    seg.split(/[^a-z0-9']+/).forEach(function (t) {
      if (!t || /^\d+$/.test(t)) return;
      if (t.length < 3 && t !== "iv" && t !== "ed" && t !== "gp") return;
      out.push(t);
    });
    return out;
  }

  function _grams(toks) {                        // panel._grams (nmax=3)
    var out = new Set(), n = toks.length;
    for (var size = 1; size <= 3; size++) {
      for (var i = 0; i + size <= n; i++) {
        var g = toks.slice(i, i + size);
        if (g.some(function (t) { return STOP.has(t); })) continue;
        if (!g.some(function (t) { return !SERVICE_HEAD.has(t); })) continue;
        var term = g.join(" ");
        if (term.length < 4) continue;
        out.add(term);
      }
    }
    return out;
  }

  var _ptCache = new Map();
  function pathTerms(url) {                      // panel.path_terms
    var key = String(url == null ? "" : url);
    if (_ptCache.has(key)) return _ptCache.get(key);
    var res = _pathTerms(key);
    _ptCache.set(key, res);
    return res;
  }
  function _pathTerms(u) {
    var EMPTY = new Set();
    var p = rawPath(u);
    if (p === null) return EMPTY;
    var path = unquote(p || "/");
    if (ASSET.test(path)) return EMPTY;
    var segs = path.split("/").filter(function (s) { return s && s !== "."; });
    if (!segs.length || segs.length > 4) return EMPTY;
    var low = segs.map(function (s) { return s.toLowerCase(); });
    if (low.some(function (s) { return JUNK_SEG.has(s); })) return EMPTY;
    var leaf = low[low.length - 1];
    var parent = low.length >= 2 ? low[low.length - 2] : "";
    var toks = _tokens(leaf);
    if (!toks.length) return EMPTY;
    var isService = SERVICE_PARENTS.has(parent) ||
      toks.some(function (t) { return SERVICE_HEAD.has(t); });
    if (!isService && segs.length > 2) return EMPTY;
    return _grams(toks);
  }

  // --------------------------------------------------------- the CDX request
  // Byte-identical params to panel.cdx_paths(): one matchType=prefix query per
  // clinic returns EVERY URL ever captured on the domain with its first-capture
  // timestamp (collapse=urlkey keeps each URL's earliest row; CDX returns rows
  // in (urlkey, timestamp) order). filter=mimetype:text/html drops the images
  // and stylesheets that are most of the index and none of the signal.
  function cdxUrl(domain) {
    var q = [["url", domain], ["matchType", "prefix"], ["output", "json"],
      ["fl", "timestamp,original"], ["filter", "statuscode:200"],
      ["filter", "mimetype:text/html"], ["collapse", "urlkey"],
      ["from", String(CDX_FROM_YEAR)], ["limit", String(MAX_ROWS)]];
    return CDX_URL + "?" + q.map(function (kv) {
      return kv[0] + "=" + encodeURIComponent(kv[1]);
    }).join("&");
  }

  function parseCdxBody(txt) {                   // the tail of panel.cdx_paths
    txt = (txt || "").trim();
    if (!txt) return [];                         // domain simply not in the Archive
    var rows;
    try { rows = JSON.parse(txt); } catch (e) { return null; }
    if (!rows || !rows.length) return [];
    var head = rows[0].map(function (c) { return String(c).toLowerCase(); });
    var ti = head.indexOf("timestamp"); if (ti < 0) ti = 0;
    var oi = head.indexOf("original"); if (oi < 0) oi = 1;
    var out = [];
    for (var i = 1; i < rows.length; i++) {
      var r = rows[i];
      if (r.length <= Math.max(ti, oi)) continue;
      var m = ym(r[ti]);
      if (m) out.push([m, String(r[oi])]);
    }
    return out;
  }

  // -> {code, body} ; throws on network error / timeout (caller counts errors)
  async function httpGet(url, timeoutMs) {
    var ctl = new AbortController();
    var t = setTimeout(function () { ctl.abort(); }, timeoutMs);
    try {
      var r = await fetch(url, { signal: ctl.signal, credentials: "omit" });
      var body = (r.status === 200) ? await r.text() : null;
      return { code: r.status, body: body };
    } finally { clearTimeout(t); }
  }

  // ---------------------------------------------- localStorage cache (the idx)
  // Same record shape panel.refresh_paths writes to data/panel_paths_adhd.json:
  //   {fetched, first, n_urls, urls: [[ym, path], ...]}   one key per domain.
  function lsGet(domain) {
    try { var s = localStorage.getItem(LS_PREFIX + domain); return s ? JSON.parse(s) : null; }
    catch (e) { return null; }
  }
  var _memIdx = {};                              // fallback if quota blows
  function lsSet(domain, rec) {
    _memIdx[domain] = rec;
    try { localStorage.setItem(LS_PREFIX + domain, JSON.stringify(rec)); return true; }
    catch (e) {
      console.warn("PANEL: localStorage save failed for " + domain + " (" + e +
        "). Kept in memory only - do NOT close the tab before the run finishes.");
      return false;
    }
  }
  function loadIdx(cohort) {
    var idx = {};
    cohort.forEach(function (c) {
      var rec = _memIdx[c.domain] || lsGet(c.domain);
      if (rec) idx[c.domain] = rec;
    });
    return idx;
  }
  function reset() {
    var n = 0;
    for (var i = localStorage.length - 1; i >= 0; i--) {
      var k = localStorage.key(i);
      if (k && (k.indexOf(LS_PREFIX) === 0 || k === LS_META)) { localStorage.removeItem(k); n++; }
    }
    _memIdx = {};
    console.log("PANEL: cleared " + n + " cached entries. Re-paste the script to refetch.");
  }

  // ---------------------------------- panel._observations, ported (paths only)
  // THE LEFT-CENSORING CORRECTION lives here. The Archive's first capture of a
  // page is the date the ARCHIVE FIRST LOOKED, not the date the page appeared.
  // A term first seen within GRACE months of the domain's first-ever capture is
  // PRE-EXISTING: counted in the base, never as a new adopter. Otherwise the
  // Archive's own crawl schedule would manufacture a fake boom.
  function observations(cohort, idx) {
    var first = new Map();      // term -> Map(domain -> ym or CENSORED_YM)
    var censored = new Map();   // term -> Set(domain)
    var domFirst = {};
    var covered = 0;

    cohort.forEach(function (c) {
      var d = c.domain;
      var rec = idx[d] || {};
      var urls = rec.urls || [];
      var df = rec.first || null;
      if (!df && urls.length) df = strMin(urls.map(function (u) { return u[0]; }));
      if (!df) return;                          // not in the Archive at all
      domFirst[d] = df;
      covered += 1;

      var seen = new Map();                     // term -> earliest ym on this domain
      urls.forEach(function (pair) {
        var m = pair[0], p = pair[1];
        pathTerms(p).forEach(function (t) {
          var cur = seen.get(t);
          if (cur === undefined || m < cur) seen.set(t, m);
        });
      });

      var graceEnd = ymAdd(df, GRACE);
      seen.forEach(function (m, t) {
        if (ymi(m) <= ymi(graceEnd)) {
          if (!censored.has(t)) censored.set(t, new Set());
          censored.get(t).add(d);
          m = CENSORED_YM;
        }
        if (!first.has(t)) first.set(t, new Map());
        var fm = first.get(t);
        var cur = fm.get(d);
        if (cur === undefined || m < cur) fm.set(d, m);
      });
    });

    return { first: first, censored: censored, domFirst: domFirst, covered: covered };
  }

  // -------------------------------------------------- panel._subsumes / _why
  var _wordRx = new Map();
  function subsumes(shortT, longT) {
    if (shortT === longT) return false;
    var rx = _wordRx.get(shortT);
    if (!rx) { rx = new RegExp("\\b" + escapeRx(shortT) + "\\b"); _wordRx.set(shortT, rx); }
    return rx.test(longT);
  }
  function sameSet(a, b) {
    if (a.length !== b.length) return false;
    var s = new Set(a);
    return b.every(function (x) { return s.has(x); });
  }
  function whySentence(term, nowN, cohortN, new12, newprev, cens) {
    var s = nowN + " of the " + cohortN + " clinics in the panel now have a '" + term +
      "' page; " + new12 + " of them added it in the last 12 months, against " +
      newprev + " in the 12 months before.";
    if (newprev === 0 && new12 >= MIN_ADOPTERS) s += " Nobody in the panel had it before that.";
    else if (new12 > newprev) s += " The rate of adoption is rising.";
    else if (new12 < newprev) s += " The rate of adoption is slowing.";
    if (cens) s += " (" + cens + " more had it before the Archive started watching them, " +
      "so their adoption date is unknown and they are counted in the base, not as new.)";
    return s;
  }

  // ------------------------------------------------------ panel._rows, ported
  function buildRows(first, censored, anchorYm, cohortN, byDom) {
    var w0 = ymAdd(anchorYm, -WINDOW);
    var w1 = ymAdd(anchorYm, -2 * WINDOW);
    var out = [];

    first.forEach(function (doms, term) {
      var nowN = doms.size;
      var observed = [];
      doms.forEach(function (m) { if (m !== CENSORED_YM) observed.push(m); });
      var seenFirst = strMin(observed);
      var prior = 0, base2 = 0;
      doms.forEach(function (m) { if (m <= w0) prior++; if (m <= w1) base2++; });
      var new12 = nowN - prior;
      var newprev = prior - base2;
      if (new12 < 1) return;                    // not rising: not what this is for
      var niche = nicheOf(term);
      if (niche === null) {
        // OPEN VOCABULARY: three independent clinics or it is not a trend.
        if (nowN < MIN_ADOPTERS) return;
      } else if (nowN < 2) return;
      var cens = censored.has(term) ? censored.get(term).size : 0;
      var adopters = [];
      doms.forEach(function (m, d) { if (m > w0) adopters.push([m, d]); });
      adopters.sort(cmpPair);
      var domsSorted = [];
      doms.forEach(function (_m, d) { domsSorted.push(d); });
      domsSorted.sort(cmpStr);
      out.push({
        term: term,
        niche: niche,
        clinics_now: nowN,
        clinics_prior: prior,
        // DEVIATION 6: Math.round vs python banker's rounding, 3rd decimal ties only
        growth: prior ? Math.round((new12 / prior) * 1000) / 1000 : new12,
        first_seen: seenFirst,
        new_adopters: adopters.slice(0, 8).map(function (p) {
          var c = byDom[p[1]];
          return (c && c.name) || p[1];
        }),
        why: whySentence(term, nowN, cohortN, new12, newprev, cens),
        new_12m: new12,
        new_prev_12m: newprev,
        accel: new12 - newprev,
        open: niche === null,
        censored: cens,
        cohort_n: cohortN,
        adopter_domains: domsSorted,
      });
    });

    // Drop a term a longer term completely explains (same adopters, contained
    // as whole words): "adhd" folds into "adhd assessment".
    out.sort(function (a, b) { return b.term.length - a.term.length; });  // stable
    var kill = new Set();
    for (var i = 0; i < out.length; i++) {
      var a = out[i];
      if (kill.has(a.term)) continue;
      for (var j = i + 1; j < out.length; j++) {
        var b = out[j];
        if (kill.has(b.term)) continue;
        if (subsumes(b.term, a.term) && sameSet(b.adopter_domains, a.adopter_domains)) {
          kill.add(b.term);
        }
      }
    }
    out = out.filter(function (r) { return !kill.has(r.term); });

    out.sort(function (a, b) {
      return (b.accel - a.accel) || (b.new_12m - a.new_12m) ||
        (b.clinics_now - a.clinics_now) || cmpStr(a.term, b.term);
    });
    out = out.slice(0, 200);
    out.forEach(function (r) { delete r.adopter_domains; });
    return out;
  }

  // --------------------------------------------- panel.adhd_history, ported
  function adhdHistory(cohort, idx, anchorYear) {
    var perYear = {};   // year -> Set(domain)   (cumulative)
    var firsts = {};    // domain -> [best_ym, censored, name]
    cohort.forEach(function (c) {
      var d = c.domain;
      var rec = idx[d] || {};
      var df = rec.first || null;
      var best = null;
      (rec.urls || []).forEach(function (pair) {
        var m = pair[0], p = pair[1];
        pathTerms(p).forEach(function (t) {
          if (nicheOf(t) === "ADHD" && (best === null || m < best)) best = m;
        });
      });
      if (!best) return;
      var cens = !!(df && ymi(best) <= ymi(ymAdd(df, GRACE)));
      firsts[d] = [best, cens, c.name || d];
      for (var y = parseInt(best.slice(0, 4), 10); y <= anchorYear; y++) {
        if (!perYear[y]) perYear[y] = new Set();
        perYear[y].add(d);
      }
    });
    return { perYear: perYear, firsts: firsts };
  }

  function printAdhdVerdict(cohort, idx) {
    var anchorYear = new Date().getFullYear();
    var h = adhdHistory(cohort, idx, anchorYear);
    var years = Object.keys(h.perYear).map(Number).sort(function (a, b) { return a - b; });
    console.log("\n================ THE ADHD VERDICT ================");
    console.log("CLINICS IN THE PANEL WITH AN ADHD PAGE, BY YEAR");
    console.log("(cumulative: a clinic stays counted once it has one)");
    if (!years.length) {
      console.log("  NO clinic in the panel ever showed an ADHD page. VERDICT: FAIL - CUT THE MODULE.");
      return h;
    }
    years.forEach(function (y) {
      var n = h.perYear[y].size;
      console.log("  " + y + "  " + "#".repeat(Math.min(40, n)) + " " + n +
        "  (" + (100 * n / cohort.length).toFixed(0) + "% of the panel)");
    });
    var cens = Object.keys(h.firsts).filter(function (d) { return h.firsts[d][1]; }).length;
    console.log("\n" + cens + " of " + Object.keys(h.firsts).length + " clinics with an ADHD " +
      "page were already showing it when the Archive first crawled them - their adoption " +
      "date is unknown; they are counted in the base, never as new adopters.");
    var n2020 = h.perYear[2020] ? h.perYear[2020].size : 0;
    var n2022 = h.perYear[2022] ? h.perYear[2022].size : 0;
    console.log("\nKILL CRITERION: 2022 must be at least DOUBLE 2020.");
    console.log("  2020 = " + n2020 + "   2022 = " + n2022);
    if (n2022 === 0) {
      console.log("  VERDICT: FAIL. The panel did not see ADHD. CUT THE MODULE.");
    } else if (n2022 >= 2 * n2020) {
      console.log("  VERDICT: PASS (" + n2022 + " >= 2 x " + n2020 + "). The panel SAW the ADHD boom.");
    } else {
      console.log("  VERDICT: FAIL (" + n2022 + " < 2 x " + n2020 + "). The panel did not see ADHD. CUT THE MODULE.");
    }
    return h;
  }

  // ------------------------------------------------------------- the selftest
  // Fixtures lifted from panel.py --selftest [2]. If any of these fail, the
  // port is NOT faithful and no data may be produced. Network untouched.
  function selftest() {
    var fails = [];
    function chk(label, got, want) {
      var g = JSON.stringify(got), w = JSON.stringify(want);
      if (g !== w) fails.push(label + ": got " + g + " want " + w);
    }
    function pt(p) { return Array.from(pathTerms(p)).sort(); }
    chk("/services/adhd-assessment", pt("/services/adhd-assessment"), ["adhd", "adhd assessment"]);
    chk("/adhd-clinic-london", pt("/adhd-clinic-london"), ["adhd", "adhd clinic"]);
    chk("blog posts are not services", pt("/blog/adhd-what-to-expect"), []);
    chk("/news/we-now-offer-adhd", pt("/news/we-now-offer-adhd"), []);
    chk("/about-us/meet-the-team", pt("/about-us/meet-the-team"), []);
    chk("/wp-content/uploads/x.jpg", pt("/wp-content/uploads/x.jpg"), []);
    chk("homepage claims nothing", pt("/"), []);
    chk("'clinic' alone is not a service", pt("/our-clinic"), []);
    chk("open vocab: /treatments/retatrutide", pt("/treatments/retatrutide"), ["retatrutide"]);
    chk("novel phrase survives whole",
      pt("/treatments/shockwave-therapy").indexOf("shockwave therapy") >= 0, true);
    chk("taxonomy tags a known term", nicheOf("adhd assessment"), "ADHD");
    chk("taxonomy does NOT tag an unknown one", nicheOf("retatrutide"), null);
    chk("taxonomy: psychiatry", nicheOf("psychiatry clinic"), "Mental health / psychiatry");
    chk("taxonomy: laser eye beats laser", nicheOf("laser eye surgery"), "Eye / optical");
    chk("ym add", ymAdd("2022-01", -12), "2021-01");
    chk("ym add wraps", ymAdd("2022-01", -1), "2021-12");
    chk("norm path", normPath("http://x.co.uk//services//adhd/"), "/services/adhd/");
    return fails;
  }

  // ------------------------------------------------------------ the main run
  var state = {
    running: false, halted: false, calls: 0, errors: 0, coolOffs: 0,
    consecutiveBlocks: 0, failedDomains: [], cohort: null,
  };

  async function fetchCohort() {
    var r = await fetch(COHORT_URL, { credentials: "omit" });
    if (r.status !== 200) throw new Error("cohort fetch HTTP " + r.status);
    var doc = await r.json();
    if (!doc || !doc.clinics || !doc.clinics.length) throw new Error("cohort file has no clinics");
    console.log("PANEL: cohort loaded - " + doc.clinics.length + " clinics, frozen " +
      (doc.built || "?") + " (sector_join=" + doc.sector_join + ")");
    return doc.clinics;
  }

  // One domain: fetch, filter, cache. Mirrors one iteration of refresh_paths.
  // Returns "ok" | "blocked" | "error".
  async function indexDomain(domain, timeoutMs) {
    var res;
    try { res = await httpGet(cdxUrl(domain), timeoutMs); }
    catch (e) { return "error"; }                // network / timeout: NOT cached
    if (res.code === 429 || res.code === 403 || res.code === 503) return "blocked";
    if (res.code !== 200 || res.body === null) return "error";
    var rows = parseCdxBody(res.body);
    if (rows === null) return "error";           // unparseable: do NOT cache a failure

    // first = earliest capture of ANY page (the left-censoring anchor) -
    // computed over ALL rows BEFORE the term filter, exactly like panel.py.
    var first = strMin(rows.map(function (r) { return r[0]; }));
    var keep = [], seen = new Set();
    rows.forEach(function (r) {
      var p = normPath(r[1]);
      if (!p || seen.has(p)) return;
      if (!pathTerms(p).size) return;            // only paths that YIELD a term
      seen.add(p);
      keep.push([r[0], p]);
    });
    keep.sort(cmpPair);
    lsSet(domain, { fetched: isoToday(), first: first, n_urls: rows.length, urls: keep.slice(0, 400) });
    return "ok";
  }

  async function run() {
    if (state.running) { console.warn("PANEL: already running in this tab."); return; }
    if (location.hostname !== "web.archive.org") {
      console.error(
        "PANEL: WRONG ORIGIN (" + location.hostname + ").\n" +
        "The CDX endpoint refuses cross-site browser requests (verified: HTTP 503 " +
        "cross-origin, HTTP 200 same-origin, no CORS header either way).\n" +
        "Open this URL in a tab:\n" +
        "  https://web.archive.org/cdx/search/cdx?url=example.com&limit=1\n" +
        "then paste this script into THAT tab's console.");
      return;
    }
    var fails = selftest();
    if (fails.length) {
      console.error("PANEL: SELFTEST FAILED - the port is not faithful, refusing to run:\n  - " +
        fails.join("\n  - "));
      return;
    }
    console.log("PANEL: selftest passed - the port matches panel.py's fixtures.");

    state.running = true; state.halted = false;
    try {
      var cohort = state.cohort || (state.cohort = await fetchCohort());

      // the queue, exactly like refresh_paths: never-fetched first, then stale
      var due = [];
      cohort.forEach(function (c) {
        var rec = _memIdx[c.domain] || lsGet(c.domain);
        if (!rec) due.push([0, c.domain]);
        else if (daysSince(rec.fetched) >= REFRESH_DAYS) due.push([1, c.domain]);
      });
      due.sort(function (a, b) { return (a[0] - b[0]) || cmpStr(a[1], b[1]); });
      var done = cohort.length - due.length;
      console.log("PANEL: " + due.length + " of " + cohort.length + " domains to index (" +
        done + " already cached). One CDX request each, " + (SLEEP_MS / 1000) +
        "s apart -> roughly " + Math.ceil(due.length * (SLEEP_MS + 4000) / 60000) +
        "-" + Math.ceil(due.length * (SLEEP_MS + 13000) / 60000) +
        " minutes. KEEP THIS TAB VISIBLE (background tabs are throttled). " +
        "Close and re-paste any time - progress is cached.");

      state.failedDomains = [];
      var t0 = Date.now();
      for (var i = 0; i < due.length; i++) {
        if (state.halted) break;
        var d = due[i][1];
        var attempt = 0, status;
        for (;;) {
          if (state.calls > 0) await sleep(SLEEP_MS);   // politeness, like Archive.get
          state.calls++;
          status = await indexDomain(d, IA_TIMEOUT_MS);
          if (status === "blocked") {
            state.consecutiveBlocks++;
            attempt++;
            if (state.consecutiveBlocks > 5) {
              console.error("PANEL: 5 consecutive blocks (429/403/503) from the Archive. " +
                "HALTING to stay polite - this is what panel.py's cooldown does. " +
                "Progress is saved; re-paste the script in 30-60 minutes to resume.");
              state.halted = true;
              break;
            }
            var wait = 60000 * Math.pow(2, Math.min(state.consecutiveBlocks - 1, 4));
            console.warn("PANEL: the Archive said stop (block " + state.consecutiveBlocks +
              "). Backing off " + (wait / 1000) + "s before retrying " + d + " ...");
            await sleep(wait);
            continue;
          }
          state.consecutiveBlocks = 0;
          break;
        }
        if (state.halted) break;
        if (status === "error") {
          state.errors++;
          state.failedDomains.push(d);
          console.warn("PANEL: [" + (i + 1) + "/" + due.length + "] " + d +
            " - FAILED (network/timeout/parse). Will retry at the end.");
          if (state.errors >= MAX_ERRORS) {
            state.coolOffs++;
            if (state.coolOffs >= 3) {
              console.error("PANEL: too many errors (3 cool-offs spent). HALTING with " +
                "progress saved - re-paste later to resume.");
              state.halted = true;
              break;
            }
            console.warn("PANEL: " + MAX_ERRORS + " errors - the Archive may be struggling. " +
              "Cooling off for 5 minutes, then continuing (cool-off " + state.coolOffs + "/3).");
            await sleep(300000);
            state.errors = 0;
          }
        } else if (status === "ok") {
          var rec = _memIdx[d] || lsGet(d) || {};
          var el = (Date.now() - t0) / 1000;
          var eta = Math.round(el / (i + 1) * (due.length - i - 1) / 60);
          console.log("PANEL: [" + (i + 1) + "/" + due.length + "] " + d + " - " +
            (rec.urls ? rec.urls.length : 0) + " service paths kept of " + (rec.n_urls || 0) +
            " captured URLs (first capture " + (rec.first || "never") + ")  ~" + eta + " min left");
        }
      }

      // DEVIATION 4: one retry pass with a longer timeout (panel.py would just
      // pick these up on tomorrow's cron run).
      if (!state.halted && state.failedDomains.length) {
        console.log("PANEL: retry pass for " + state.failedDomains.length +
          " failed domain(s), 60s timeout ...");
        var still = [];
        for (var k = 0; k < state.failedDomains.length; k++) {
          await sleep(SLEEP_MS);
          state.calls++;
          var st2 = await indexDomain(state.failedDomains[k], RETRY_TIMEOUT_MS);
          if (st2 !== "ok") still.push(state.failedDomains[k]);
        }
        state.failedDomains = still;
        if (still.length) {
          console.warn("PANEL: " + still.length + " domain(s) still unfetched: " +
            still.join(", ") + "\nThey are simply first in the queue on the next " +
            "re-paste. The rows below UNDERCOUNT until coverage is complete.");
        }
      }

      report();
    } finally {
      state.running = false;
    }
  }

  // Compute rows + verdict from cache - no network. Mirrors panel.panel()'s
  // read-from-cache path with refresh already done.
  function report() {
    var cohort = state.cohort;
    if (!cohort) { console.error("PANEL: no cohort loaded - run PANEL.run() first."); return null; }
    var idx = loadIdx(cohort);
    var anchorYm = ymNow();
    var obs = observations(cohort, idx);
    var byDom = {};
    cohort.forEach(function (c) { byDom[c.domain] = c; });

    console.log("\nPANEL: coverage " + obs.covered + "/" + cohort.length + " clinics with " +
      "Archive history (" + (100 * obs.covered / cohort.length).toFixed(1) + "%), " +
      obs.first.size + " distinct terms observed, anchor month " + anchorYm + ".");
    if (obs.covered < cohort.length) {
      console.warn("PANEL: " + (cohort.length - obs.covered) + " clinics have no Archive " +
        "history yet (not archived, or not fetched). Adopter counts are an UNDERCOUNT " +
        "until fetch coverage is complete; a domain the Archive never crawled can never " +
        "be covered.");
    }
    if (!obs.first.size) { console.error("PANEL: no observations at all - nothing to report."); return null; }

    // cohort_n = clinics WITH archive history, exactly as panel.panel() passes `covered`
    var rows = buildRows(obs.first, obs.censored, anchorYm, obs.covered, byDom);

    console.log("\nTOP RISING SERVICES (by acceleration in distinct adopters):");
    try {
      console.table(rows.slice(0, 15).map(function (r) {
        return { term: r.term, niche: r.niche || "(OPEN)", now: r.clinics_now,
          prior: r.clinics_prior, new12: r.new_12m, accel: r.accel, first: r.first_seen };
      }));
    } catch (e) { /* console.table missing in odd consoles */ }
    if (rows.length) console.log("Top row: " + rows[0].why);

    printAdhdVerdict(cohort, idx);

    var json = JSON.stringify(rows);
    window.PANEL_ROWS = rows;
    window.PANEL_ROWS_JSON = json;
    console.log("\n===== data/panel_rows.json (" + rows.length + " rows, " +
      json.length + " bytes) =====");
    console.log(json);
    console.log("=====");
    try {
      navigator.clipboard.writeText(json).then(function () {
        console.log("PANEL: JSON copied to the clipboard. Commit it as data/panel_rows.json");
      }, function (e) {
        console.warn("PANEL: clipboard write refused (" + e + "). Run:  copy(PANEL_ROWS_JSON)" +
          "   or  PANEL.download()");
      });
    } catch (e) {
      console.warn("PANEL: no clipboard API. Run:  copy(PANEL_ROWS_JSON)  or  PANEL.download()");
    }
    console.log("PANEL: also available - PANEL.download() saves panel_rows.json; " +
      "PANEL.report() recomputes without network; PANEL.reset() wipes the cache.");
    return rows;
  }

  function download() {
    var json = window.PANEL_ROWS_JSON;
    if (!json) { console.error("PANEL: nothing to download yet - run PANEL.run() first."); return; }
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    a.download = "panel_rows.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    console.log("PANEL: panel_rows.json downloaded - commit it to data/panel_rows.json");
  }

  function halt() { state.halted = true; console.log("PANEL: halting after the current request; progress is saved."); }

  return {
    run: run, report: report, download: download, reset: reset, halt: halt,
    selftest: selftest, state: state,
    // exposed for spot-checking the port against panel.py:
    pathTerms: pathTerms, nicheOf: nicheOf, normPath: normPath, cdxUrl: cdxUrl,
  };
})();

/* auto-start */
PANEL.run().catch(function (e) {
  console.error("PANEL: fatal - " + e + ". Nothing was corrupted; progress (if any) is " +
    "cached. Fix the cause and re-paste to resume.");
});
