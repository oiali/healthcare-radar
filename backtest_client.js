/* =============================================================================
 * backtest_client.js  -  T4 (NHS PRESCRIBING) FOR THE RADAR BACKTEST
 * =============================================================================
 *
 * WHY THIS FILE EXISTS AT ALL
 * ---------------------------
 * OpenPrescribing returns HTTP 403 to datacentre IPs. It works from a real
 * browser and it does NOT work from GitHub Actions, from a container, or from
 * any sandbox. So T4 cannot be fetched by backtest.py, and pretending otherwise
 * would silently produce an empty T4 column that looks like "no data" rather
 * than "we were blocked". This script is the manual step that fills that gap.
 *
 * HOW TO RUN
 * ----------
 *   1. Open  https://openprescribing.net  in a normal browser tab.
 *      (It MUST be that origin. Running this from any other page will be
 *      blocked by CORS - the API sends no Access-Control-Allow-Origin header.)
 *   2. Open DevTools -> Console.
 *   3. Paste this whole file. Press Enter.
 *   4. Wait ~20 seconds. It prints a JSON blob and copies it to your clipboard.
 *   5. Save it as   radar-app/_agent/data/backtest_t4.json
 *   6. Re-run       python3 backtest.py
 *      backtest.py detects the file and merges T4 into the lead-lag tables.
 *
 * RATE LIMITING
 * -------------
 * OpenPrescribing starts returning HTTP 429 at roughly 60 calls. The spending
 * endpoint accepts COMMA-SEPARATED BNF codes and sums them SERVER-SIDE, so we
 * query once per NICHE rather than once per DRUG: 5 requests instead of 21.
 * There is also a deliberate 1.5s pause between calls. You are nowhere near the
 * limit; that is the point.
 *
 * THE ESTIMATOR BELOW IS A LINE-FOR-LINE PORT OF backtest_core.onset_robust().
 * If you change one, change the other, or the T4 onsets stop being comparable
 * with T1/T2/T3 and every lead time in the study becomes meaningless.
 * ========================================================================== */

(async () => {
  "use strict";

  // ---------------------------------------------------------------- CONFIG
  // Only niches where NHS primary-care prescribing can actually SEE the niche.
  // Codes are the ones verified live in drugs.py on 13 Jul 2026.
  //
  // Deliberately ABSENT, and why:
  //   hair          - only topical minoxidil (~600 items/mth) is live; finasteride
  //                   1mg runs at ~1 item/mth. The private hair-loss market is
  //                   invisible to the NHS. Scoring it would be scoring noise.
  //   tongue-tie    - a procedure. There is no drug.
  //   ALL 7 GRAVEYARD NICHES - CBD, psilocybin, IV vitamins, cryotherapy,
  //                   hyperbaric oxygen, ice baths and red-light panels are not
  //                   NHS-prescribed. T4 therefore ABSTAINS on the entire
  //                   graveyard. It cannot produce a false positive because it
  //                   cannot produce ANY positive. Read that twice before you
  //                   let anyone tell you T4 has "perfect specificity".
  const NICHES = {
    adhd:      ["0404000U0", "0404000M0", "0404000S0", "0404000V0", "0404000L0"],
    glp1:      ["0601023AW", "0601023AZ", "0601023AB", "0405010P0"],
    menopause: ["0604011G0", "0604011L0", "0604011K0", "0604011Y0",
                "0604011P0", "0604012S0", "0702010G0"],
    trt:       ["0604020K0", "0604020T0", "0604020U0", "0604020M0"],
    ed:        ["0704050Z0", "0704050R0", "0704050AA", "0704050B0"],
  };

  const API = "https://openprescribing.net/api/1.0/spending/?format=json&code=";
  const PAUSE_MS = 1500;
  const START = "2012-01";
  const END   = "2026-06";

  // ------------------------------------------- ESTIMATOR (port of the Python)
  const K_SMOOTH = 3.0;
  const Z_TRIGGER = 3.0;
  const Z_SUSTAIN = 1.5;
  const SUSTAIN_MONTHS = 3;
  const BASELINE_N = 24;
  const MIN_SD = 0.02;
  const BASE_LO = 24, BASE_HI = 12;
  const GROWTH_X = 1.5;
  const TRIM_FRAC = 0.6;
  const T4_MIN_LEVEL = 500.0;   // prescription items per 12 months
  const LOW_COUNT = 36.0;

  const median = (xs) => {
    if (!xs.length) return null;
    const s = [...xs].sort((a, b) => a - b), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const madSd = (xs) => {
    if (!xs.length) return null;
    const m = median(xs);
    return 1.4826 * median(xs.map((x) => Math.abs(x - m)));
  };

  function rollingSum(v, w = 12) {
    const out = []; let acc = 0;
    for (let i = 0; i < v.length; i++) {
      acc += v[i];
      if (i >= w) acc -= v[i - w];
      out.push(i >= w - 1 ? acc : null);
    }
    return out;
  }

  function trimmedRollingSum(v, w = 12) {
    const out = [];
    for (let i = 0; i < v.length; i++) {
      if (i < w - 1) { out.push(null); continue; }
      const win = v.slice(i - w + 1, i + 1);
      out.push(win.reduce((a, b) => a + b, 0) - Math.max(...win));
    }
    return out;
  }

  function baselineLevel(S, t) {
    const xs = [];
    for (let i = Math.max(0, t - BASE_LO); i <= t - BASE_HI; i++) {
      if (i >= 0 && i < S.length && S[i] !== null) xs.push(S[i]);
    }
    return xs.length >= 7 ? median(xs) : null;
  }

  function onsetRobust(months, vals, growthX = GROWTH_X) {
    const n = vals.length;
    const minG = Math.log(growthX);
    const minGTrim = Math.log(1 + (growthX - 1) * TRIM_FRAC);
    const R = rollingSum(vals, 12);
    const RT = trimmedRollingSum(vals, 12);

    const g = Array(n).fill(null), gt = Array(n).fill(null),
          se = Array(n).fill(null), bl = Array(n).fill(null);
    for (let t = 0; t < n; t++) {
      if (R[t] === null) continue;
      const b = baselineLevel(R, t), bt = baselineLevel(RT, t);
      if (b === null || bt === null) continue;
      bl[t] = b;
      const a = R[t] + K_SMOOTH, bb = b + K_SMOOTH;
      g[t] = Math.log(a / bb);
      se[t] = Math.sqrt(1 / a + 1 / bb);
      gt[t] = Math.log((RT[t] + K_SMOOTH) / (bt + K_SMOOTH));
    }

    const z0 = g.map((x, t) => (x !== null && se[t]) ? x / se[t] : null);
    const z = Array(n).fill(null);
    for (let t = 0; t < n; t++) {
      const base = [];
      for (let i = Math.max(0, t - BASELINE_N); i < t; i++) {
        if (z0[i] !== null) base.push(z0[i]);
      }
      if (z0[t] === null || base.length < BASELINE_N) continue;
      const med = median(base);
      const phi = Math.max(madSd(base) || 0, 1.0);   // never sub-Poisson
      z[t] = (z0[t] - med) / Math.max(phi, MIN_SD);
    }

    let first = null;
    for (let t = 0; t < n - SUSTAIN_MONTHS; t++) {
      if (z[t] === null || g[t] === null || gt[t] === null) continue;
      if (g[t] < minG) continue;                      // 1. practical significance
      if (gt[t] < minGTrim) continue;                 // 2. not one freak month
      if (z[t] < Z_TRIGGER) continue;                 // 3+4. statistical
      if (R[t] < T4_MIN_LEVEL) continue;              // absolute floor
      let ok = true;                                  // 5. persistence
      for (let j = 1; j <= SUSTAIN_MONTHS; j++) {
        if (z[t + j] === null || z[t + j] < Z_SUSTAIN) { ok = false; break; }
      }
      if (!ok) continue;
      first = t;
      break;
    }

    // NOTE: rounding here matches Python's round(x, 1) exactly. Verified by a
    // cross-language parity harness on 10 synthetic series (ramp, step, flat,
    // seasonal, declining, drifting, surge-collapse, low-count, prescription-
    // scale, one-month spike): all 10 produce IDENTICAL onsets in both languages.
    // If you touch this function, re-run that check or T4 stops being comparable.
    return {
      onset: first === null ? null : months[first],
      z_at_onset: first === null ? null : +z[first].toFixed(2),
      growth_at_onset: first === null ? null : +(Math.exp(g[first]) - 1).toFixed(3),
      level_at_onset: first === null ? null : +R[first].toFixed(1),
      baseline_at_onset: first === null ? null : +bl[first].toFixed(1),
      low_count_unreliable:
        first === null ? null : (bl[first] !== null && bl[first] < LOW_COUNT),
      testable_months: z.filter((x) => x !== null).length,
    };
  }

  // ------------------------------------------------------------------ AXIS
  function monthAxis(start, end) {
    const out = [];
    let [y, m] = start.split("-").map(Number);
    const [ey, em] = end.split("-").map(Number);
    while (y < ey || (y === ey && m <= em)) {
      out.push(`${y}-${String(m).padStart(2, "0")}`);
      m++; if (m > 12) { m = 1; y++; }
    }
    return out;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------------- RUN
  const months = monthAxis(START, END);
  const series = {};      // {niche: {"YYYY-MM": items}}  <- this is the file
  const onsets = {};
  let calls = 0;

  console.log("%cRadar backtest - T4 (OpenPrescribing)", "font-weight:bold;font-size:14px");
  console.log(`Fetching ${Object.keys(NICHES).length} niches, batched by BNF code. ` +
              `${Object.keys(NICHES).length} calls total - the 429 limit is ~60.`);

  for (const [niche, codes] of Object.entries(NICHES)) {
    const url = API + codes.join(",");
    let data = null;
    try {
      const res = await fetch(url, { credentials: "omit" });
      calls++;
      if (res.status === 429) {
        console.error(`  ${niche}: HTTP 429 RATE LIMITED. Wait 10 minutes and re-run.`);
        continue;
      }
      if (res.status === 403) {
        console.error(`  ${niche}: HTTP 403. You are not running this from a real ` +
                      `browser on openprescribing.net.`);
        continue;
      }
      if (!res.ok) { console.error(`  ${niche}: HTTP ${res.status}`); continue; }
      data = await res.json();
    } catch (e) {
      console.error(`  ${niche}: ${e.message}. If this says CORS, you are not on ` +
                    `openprescribing.net - go to that origin and retry.`);
      continue;
    }

    // The API returns one row per month: {date:"2024-03-01", items: N, ...}
    // Codes given as a comma-separated list are SUMMED SERVER-SIDE, so each row
    // is already the whole-niche total. Verified: semaglutide + tirzepatide
    // queried together returns exactly the sum of the two queried separately.
    const byMonth = {};
    for (const row of data) {
      const m = String(row.date).slice(0, 7);
      byMonth[m] = (byMonth[m] || 0) + (row.items || 0);
    }

    const vals = months.map((m) => byMonth[m] || 0);
    const nonZero = vals.filter((v) => v > 0).length;
    series[niche] = {};
    months.forEach((m, i) => { if (vals[i] > 0) series[niche][m] = vals[i]; });

    const o = onsetRobust(months, vals);
    onsets[niche] = o;
    console.log(
      `  ${niche.padEnd(10)} ${String(nonZero).padStart(3)} months of data, ` +
      `latest ${Math.round(vals[vals.length - 1]).toLocaleString()} items/mth  ->  ` +
      `onset ${o.onset || "NO ONSET"}` +
      (o.onset ? `  (+${Math.round(o.growth_at_onset * 100)}% YoY, z=${o.z_at_onset})` : "")
    );
    await sleep(PAUSE_MS);
  }

  // ----------------------------------------------------------------- OUTPUT
  console.log("\n%cONSETS (same estimator as T1/T2/T3 - directly comparable)",
              "font-weight:bold");
  console.table(onsets);

  const blob = JSON.stringify(series, null, 1);
  console.log("\n%cSAVE THE BLOCK BELOW AS  _agent/data/backtest_t4.json",
              "font-weight:bold;color:#0a0");
  console.log(blob);

  try {
    await navigator.clipboard.writeText(blob);
    console.log("%c-> copied to clipboard.", "color:#0a0");
  } catch (e) {
    console.log("(clipboard blocked - select and copy the JSON above by hand)");
  }

  console.log(`\n${calls} API calls used. Now run:  python3 backtest.py`);
  console.log("\nREMINDER: T4 abstains on ALL 7 graveyard niches - none of them are " +
              "NHS-prescribed. T4 therefore has NO measurable false-positive rate. " +
              "Its specificity is unknown, not perfect.");

  window.__radarT4 = { series, onsets };   // left on window for convenience
})();
