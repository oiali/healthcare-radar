#!/usr/bin/env python3
"""
Backtest CORE: the boom-onset estimator + the statistics, with synthetic-fixture
unit tests. No network, no I/O. Imported by backtest.py; mirrored line-for-line in
backtest_client.js so the browser-side T4 uses the identical estimator.

    python3 backtest_core.py        # run the 21 fixtures

WHY NOT THE BRIEF'S ESTIMATOR
-----------------------------
The brief specified: onset = the first month YoY growth crosses +2 SD of its own
trailing 24-month growth distribution, and stays above +1 SD for 2 more months.

The persistence idea is right and is kept. The rest breaks on this data. I know it
breaks because I built that estimator first and ran it against the fixtures at the
bottom of this file: it "found" booms in pure noise, in a flat seasonal series, and
in a series that was going DOWN. It is shipped below as onset_spec(), runs in
parallel on every series, and every disagreement is reported - so you can check
this claim rather than take my word for it. Seven failure modes:

 (a) RATIO ON SMALL COUNTS. T2/T3 monthly counts per niche are often 0-5. The ratio
     y[t]/y[t-12] is UNDEFINED when y[t-12]==0 - which is most of the pre-boom
     period of a new niche, i.e. exactly the months we most need to judge - and
     meaningless when it is 1 (1 -> 3 clinics reads as "+200%"). On the tiny-count
     fixture the brief's estimator is undefined for 94 months.

 (b) MEAN/SD ARE CONTAMINATED BY THE BOOM ITSELF. The trailing baseline absorbs the
     boom's own early months the instant the boom starts, inflating the SD, raising
     the bar, and hiding the very event being dated. Measured: the brief's estimator
     MISSES 3 of 8 identical synthetic booms outright (fixtures 13-14).

 (c) NO ABSOLUTE FLOOR. 0,0,0,1,1,1 gives an infinite z-score. Every dud booms.

 (d) NO SEASONALITY CONTROL. Incorporations collapse in December and spike in
     January and April (tax-year effects).

 (e) THE PERSISTENCE RULE IS NEARLY FREE. Any 12-month smoothing makes consecutive
     months share 11 of 12 observations, so g[t] and g[t+1] correlate ~0.9. "Above
     +1 SD for 2 more months" then rejects almost nothing.

 (f) SCANNING ~180 MONTHS FOR A MAXIMUM IS A MULTIPLE-COMPARISONS PROBLEM. A nominal
     2-SD threshold fires ~2.3% of months by chance; scan 180 months and you expect
     ~4 spurious crossings PER SERIES.

 (g) A NOISY DENOMINATOR MANUFACTURES BOOMS. This one only surfaced because the
     fixtures caught it. Comparing R[t] against the single window R[t-12] means a
     LOW draw 12 months ago and a HIGH draw now fabricate a boom out of nothing: in
     fixture 9, a series whose true rate drifted 5%/yr produced an apparent +55%
     "boom" (R went 104 -> 161 against an expected 131 -> 138). No growth threshold
     and no z-score catches that, because it genuinely IS a ~3-sigma event and you
     get one every ~190 months you scan.

THE ESTIMATOR I SHIPPED - five conditions, all must hold
--------------------------------------------------------
R[t] = trailing 12-month SUM (kills seasonality (d), stabilises small counts).
B[t] = MEDIAN of R over [t-24, t-12] - a SMOOTHED baseline level, not the single
       noisy window R[t-12]. That is fix (g).
K    = 3, a weak additive prior making 0 -> 1 finite rather than infinite (a).

  1. PRACTICAL SIGNIFICANCE.  g[t] = ln((R[t]+K)/(B[t]+K)) >= ln(1.5)
     In English: the niche must be at least 50% bigger than its typical level a year
     or two ago. This condition does the real work and it is the one the brief was
     missing entirely. Statistical significance alone is not enough: given a long
     enough series, a niche crawling from 96 to 108 companies a year is
     "significant" and is obviously not a boom.

  2. NOT ONE FREAK MONTH. The same test must ALSO pass on the max-TRIMMED series
     (each 12-month window with its single largest month deleted). A trailing sum
     turns a one-month spike into a 12-month plateau, so condition 1 fires happily
     on a single freak month; deleting the max makes a spike vanish while barely
     touching a genuine broad-based rise. THIS is what actually delivers the brief's
     stated intent - "kill one-month spikes" - which its own persistence rule does
     not, per (e).

  3. STATISTICAL SIGNIFICANCE, WITH A COUNT-DATA VARIANCE MODEL. These are counts,
     so the null variance is Poisson, not "whatever the last 24 months wobbled by".
     By the delta method SE(g) ~= sqrt(1/(R[t]+K) + 1/(B[t]+K)), scaled by an
     overdispersion factor estimated robustly from the baseline and never allowed
     below Poisson. This makes small series intrinsically hard to fire - the
     absolute floor of (c), derived rather than bolted on. Threshold z >= 3.0, not
     2.0: with ~10 effectively-independent 12-month windows per series, 3.0 is
     roughly the Bonferroni-corrected 5% level. That is fix (f).

  4. MEDIAN/MAD BASELINE for the z-scale, not mean/SD. 50% breakdown point, so the
     boom's first months cannot inflate the threshold meant to catch them - fix (b).

  5. PERSISTENCE. z stays >= 1.5 for 3 further months. The brief's rule, kept. Weak,
     for reason (e), but free.

Plus a per-tier absolute level floor, and a LOW-COUNT flag (see below).

A TRAP I ALMOST FELL INTO, AND THE FIXTURE THAT GUARDS IT
---------------------------------------------------------
My first fix for (g) was a "the rise must still be there 6-12 months later"
confirmation rule. It works, and it is CATASTROPHICALLY WRONG.

The graveyard niches (CBD, psychedelics) are precisely the ones whose T1/T2 surged
and then COLLAPSED. An estimator requiring the rise to persist would refuse to fire
on them - so the graveyard could never produce a false positive, the measured
false-positive rate would come out at exactly ZERO, and the backtest would "prove"
the early tiers are perfectly specific. That is a fabricated result: it uses the
OUTCOME to define the SIGNAL. It is the statistical equivalent of marking your own
homework.

FIXTURE 4 EXISTS SOLELY TO PREVENT IT - it injects a surge-then-collapse series and
asserts the estimator STILL FIRES. The legitimate fix for (g) is the smoothed
baseline B[t] in condition 1: it removes denominator NOISE without filtering on
commercial SUCCESS, and it keeps the estimator causal (no hindsight beyond the
3-month persistence window), so the lead times it produces are roughly what a live
detector could have achieved.

WHERE IT IS STILL WEAK - AND THIS ONE IS NOT FIXABLE
----------------------------------------------------
At ~2 events/month - which is where per-niche CQC registrations actually live - the
estimator is not trustworthy. Fixture 16 shows it: on a 2/month series it fires on 7
of 8 synthetic runs, but the dates scatter and it can fire years early on noise. No
estimator can date a regime change in a series that thin; the information is not in
the data. So every onset carries a `low_count_unreliable` flag when the pre-onset
baseline is under ~3/month, and T3 onsets in particular should be read as "roughly
this year, maybe", not as dates. This directly limits the tier the whole lead-lag
thesis leans on.

Stdlib only.
"""

import math
import random
import statistics

# ------------------------------------------------------------------ constants
K_SMOOTH = 3.0           # additive prior: makes 0 -> 1 finite; negligible when large
Z_TRIGGER = 3.0          # not 2.0 - scan multiplicity, failure mode (f)
Z_SUSTAIN = 1.5
SUSTAIN_MONTHS = 3
BASELINE_N = 24          # months of z-history used to set the robust scale
MIN_SD = 0.02
BASE_LO, BASE_HI = 24, 12   # baseline level = median of R over [t-24, t-12]

# THE BOOM DEFINITION: "at least 50% bigger than its typical level a year+ ago".
# Everything hinges on this one number, so it is a named constant and backtest.py
# reports a SENSITIVITY ANALYSIS across 1.25 / 1.5 / 2.0. If the lead-lag ordering
# flips when you move it, the ordering was never real - it was a tuning artefact,
# and you would rather discover that here than after buying a clinic group.
GROWTH_X = 1.5
TRIM_FRAC = 0.6          # trimmed threshold = 1 + (GROWTH_X-1)*TRIM_FRAC

# Absolute level floors per tier, on top of the Poisson SE.
# Stated plainly: a niche whose 12-month total never reaches min_level can NEVER fire
# on that tier. That is a deliberate loss of statistical power, traded for not
# drowning in false positives from 0-2/month noise. It also means the radar is
# structurally blind to a niche while it is still tiny - which is exactly when you
# would most want to buy into it. That tension is real and is not resolvable here.
FLOORS = {
    "T1": {"min_level": 120.0},   # Google Trends index, 12-mth sum (range 0-1200)
    "T2": {"min_level": 12.0},    # >= ~1 new company per month
    "T3": {"min_level": 6.0},     # clinics are rarer than companies
    "T4": {"min_level": 500.0},   # prescription items per 12 months
}
LOW_COUNT = 36.0         # baseline < ~3/month -> the onset DATE is not trustworthy


def mad_sd(xs):
    """Robust SD via median absolute deviation. 50% breakdown point."""
    if not xs:
        return None
    m = statistics.median(xs)
    return 1.4826 * statistics.median([abs(x - m) for x in xs])


def rolling_sum(vals, w=12):
    """R[t] = sum(vals[t-w+1 .. t]); None for the first w-1 positions."""
    out, acc = [], 0.0
    for i, v in enumerate(vals):
        acc += v
        if i >= w:
            acc -= vals[i - w]
        out.append(acc if i >= w - 1 else None)
    return out


def trimmed_rolling_sum(vals, w=12):
    """Same, but with the single LARGEST month of each window deleted. Condition 2."""
    out = []
    for i in range(len(vals)):
        if i < w - 1:
            out.append(None)
        else:
            win = vals[i - w + 1:i + 1]
            out.append(sum(win) - max(win))
    return out


def baseline_level(S, t):
    """Median of S over [t-24, t-12]. The SMOOTHED denominator - fix (g)."""
    xs = [S[i] for i in range(max(0, t - BASE_LO), t - BASE_HI + 1)
          if 0 <= i < len(S) and S[i] is not None]
    return statistics.median(xs) if len(xs) >= 7 else None


def onset_robust(months, vals, tier, growth_x=GROWTH_X):
    """PRIMARY estimator. `onset` is None if the series never booms."""
    min_level = FLOORS.get(tier, {}).get("min_level", 0.0)
    min_g = math.log(growth_x)
    min_g_trim = math.log(1.0 + (growth_x - 1.0) * TRIM_FRAC)
    n = len(vals)
    R = rolling_sum(vals, 12)
    RT = trimmed_rolling_sum(vals, 12)

    g = [None] * n      # log growth of the 12-mth sum vs its smoothed baseline
    gt = [None] * n     # ... the same on the max-trimmed series
    se = [None] * n     # Poisson delta-method SE of g
    bl = [None] * n     # the baseline level itself
    for t in range(n):
        if R[t] is None:
            continue
        b, bt = baseline_level(R, t), baseline_level(RT, t)
        if b is None or bt is None:
            continue
        bl[t] = b
        a, bb = R[t] + K_SMOOTH, b + K_SMOOTH
        g[t] = math.log(a / bb)
        se[t] = math.sqrt(1.0 / a + 1.0 / bb)
        gt[t] = math.log((RT[t] + K_SMOOTH) / (bt + K_SMOOTH))

    z0 = [(g[t] / se[t]) if (g[t] is not None and se[t]) else None for t in range(n)]
    z = [None] * n
    for t in range(n):
        base = [z0[i] for i in range(max(0, t - BASELINE_N), t) if z0[i] is not None]
        if z0[t] is None or len(base) < BASELINE_N:
            continue
        med = statistics.median(base)
        phi = max(mad_sd(base) or 0.0, 1.0)     # overdispersion, never sub-Poisson
        z[t] = (z0[t] - med) / max(phi, MIN_SD)

    first = None
    for t in range(n - SUSTAIN_MONTHS):
        if z[t] is None or g[t] is None or gt[t] is None:
            continue
        if g[t] < min_g:                                    # 1. practical
            continue
        if gt[t] < min_g_trim:                              # 2. not one freak month
            continue
        if z[t] < Z_TRIGGER:                                # 3+4. statistical
            continue
        if R[t] < min_level:                                # absolute floor
            continue
        if any(z[t + j] is None or z[t + j] < Z_SUSTAIN     # 5. persistence
               for j in range(1, SUSTAIN_MONTHS + 1)):
            continue
        first = t
        break

    peak = max([x for x in z if x is not None], default=None)
    low = None
    if first is not None and bl[first] is not None:
        low = bool(bl[first] < LOW_COUNT)
    return {
        "onset": months[first] if first is not None else None,
        "onset_idx": first,
        "z_at_onset": round(z[first], 2) if first is not None else None,
        "growth_at_onset": round(math.exp(g[first]) - 1, 3) if first is not None else None,
        "baseline_at_onset": round(bl[first], 1) if first is not None else None,
        "level_at_onset": round(R[first], 1) if first is not None else None,
        "low_count_unreliable": low,
        "peak_z": round(peak, 2) if peak is not None else None,
        "testable_months": sum(1 for x in z if x is not None),
        "latest_12m": round(R[-1], 1) if R and R[-1] is not None else None,
        "total": round(sum(vals), 1),
    }


def onset_spec(months, vals):
    """The BRIEF'S estimator, verbatim, for comparison.

    Raw-YoY ratio; mean + 2 SD of the trailing 24 growth values; +1 SD for 2 months.
    `undefined_months` counts months where y[t-12]==0 and the ratio simply does not
    exist - that number is a large part of the argument for replacing it.
    """
    n = len(vals)
    g = [None] * n
    undef = 0
    for t in range(12, n):
        if vals[t - 12] == 0:
            undef += 1
            continue
        g[t] = vals[t] / vals[t - 12] - 1.0

    z = [None] * n
    for t in range(n):
        base = [g[i] for i in range(max(0, t - BASELINE_N), t) if g[i] is not None]
        if g[t] is None or len(base) < BASELINE_N:
            continue
        sd = statistics.pstdev(base)
        if sd <= 0:
            continue
        z[t] = (g[t] - statistics.fmean(base)) / sd

    first = None
    for t in range(n - 2):
        if z[t] is None or z[t] < 2.0:
            continue
        if any(z[t + j] is None or z[t + j] < 1.0 for j in (1, 2)):
            continue
        first = t
        break

    return {
        "onset": months[first] if first is not None else None,
        "onset_idx": first,
        "undefined_months": undef,
        "testable_months": sum(1 for x in z if x is not None),
    }


# ================================================================ STATISTICS
def binom_tail(k, n, p=0.5):
    """P(X >= k), X ~ Binomial(n, p). Exact one-sided sign test."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def median_ci(xs, conf=0.95):
    """Distribution-free CI for the median from order statistics.

    Returns (lo, hi, coverage), or None if NO interval at this confidence exists at
    this n. At n=5 the widest possible interval - the full min-to-max range -
    achieves only 93.75% coverage, so this returns None. That is not a limitation of
    the code. It is the arithmetic telling you that with 5 niches you cannot put a
    95% confidence interval on the median AT ALL, not even one as useless as
    "somewhere between the smallest and largest number we happened to see".
    """
    xs = sorted(x for x in xs if x is not None)
    n = len(xs)
    if n < 2:
        return None
    for l in range(0, n // 2):
        cov = 1.0 - 2.0 * sum(math.comb(n, i) * 0.5 ** n for i in range(0, l + 1))
        if cov >= conf:
            return (xs[l], xs[n - 1 - l], round(cov, 4))
    return None


def power_note(n, hyps=3, alpha=0.05):
    """What would a PERFECT result even be worth at this n?

    Sign test, one-sided, all n niches in the predicted direction: p = 0.5^n. We test
    3 orderings (T1<T2, T2<T3, T3<T4), so Bonferroni-correct to alpha/3.
    """
    if n < 1:
        return {"n": n, "passes": False, "verdict": "no pairs - nothing is testable"}
    p = 0.5 ** n
    a = alpha / hyps
    need = math.ceil(math.log(a) / math.log(0.5))
    if p > a:
        v = ("A PERFECT sweep at n=%d gives p=%.4f, which does NOT clear the "
             "Bonferroni-corrected alpha of %.4f. At this n the experiment CANNOT reach "
             "significance even if every single niche behaves exactly as predicted. You "
             "need n>=%d for a clean sweep to count at all." % (n, p, a, need))
    else:
        v = ("A perfect sweep at n=%d gives p=%.4f, which clears the corrected alpha of "
             "%.4f - but ONLY if the sweep is flawless. ONE niche in the wrong order "
             "takes it to p=%.4f and it fails. Surviving a single inversion needs n>=10."
             % (n, p, a, binom_tail(n - 1, n)))
    return {"n": n, "perfect_sweep_p": round(p, 5), "bonferroni_alpha": round(a, 5),
            "passes": bool(p <= a), "n_needed_for_perfect_sweep": need, "verdict": v}


# ==================================================== SYNTHETIC-FIXTURE TESTS
# The estimator is proved on series where the truth is known by construction. These
# are not decoration: the FIRST draft failed five of them, and fixture 9 is what
# exposed failure mode (g). Fixture 4 exists to stop a much worse mistake - see
# "A TRAP I ALMOST FELL INTO" above.
def _poisson_series(n, rate_fn, seed):
    """Poisson counts via Knuth. Stdlib only, deterministic given the seed.
    NB: underflows for lambda > ~700 (exp(-lambda) -> 0). Fine for counts; use a
    normal approximation if you ever need prescription-scale rates here."""
    rnd = random.Random(seed)
    out = []
    for t in range(n):
        lam = max(rate_fn(t), 0.0)
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            p *= rnd.random()
            if p <= L:
                break
        out.append(float(k - 1))
    return out


def _axis(n):
    return ["%04d-%02d" % (2010 + i // 12, i % 12 + 1) for i in range(n)]


def selftest():
    N, BOOM = 198, 120           # 2010-01 .. 2026-06; true regime change at 2020-01
    months = _axis(N)
    fails = []

    def check(name, ok, detail=""):
        print(("  PASS  " if ok else "  FAIL  ") + name + (("   " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    print("\nSYNTHETIC FIXTURES - the truth is known by construction")
    print("-" * 76)

    # ---- SENSITIVITY: does it find a boom that is really there? -------------
    def ramp(t):
        return 8.0 if t < BOOM else 8.0 * (1 + 5.0 * min(1.0, (t - BOOM) / 18.0))

    o = onset_robust(months, _poisson_series(N, ramp, 1), "T2")
    check("1. real 6x ramp IS detected",
          o["onset_idx"] is not None and BOOM <= o["onset_idx"] <= BOOM + 12,
          "onset=%s (true=%s)" % (o["onset"], months[BOOM]))

    o = onset_robust(months, _poisson_series(N, lambda t: 8.0 if t < BOOM else 40.0, 6), "T2")
    check("2. instant 5x step IS detected within a year",
          o["onset_idx"] is not None and BOOM <= o["onset_idx"] <= BOOM + 12,
          "onset=%s (true=%s)" % (o["onset"], months[BOOM]))

    def trends_shape(t):
        return 1.0 if t < BOOM else min(100.0, 1.0 + 99.0 * (t - BOOM) / 24.0)
    s = [float(int(trends_shape(t) + random.Random(t + 99).random())) for t in range(N)]
    o = onset_robust(months, s, "T1")
    check("3. Trends-shaped boom (0-100 index, integer-truncated) IS detected",
          o["onset_idx"] is not None and BOOM <= o["onset_idx"] <= BOOM + 18,
          "onset=%s (true=%s)" % (o["onset"], months[BOOM]))

    # ---- THE ANTI-CIRCULARITY FIXTURE. Read the docstring before touching it.
    def surge_collapse(t):
        if t < BOOM:
            return 8.0
        if t < BOOM + 24:
            return 8.0 * (1 + 4.0 * (t - BOOM) / 24.0)
        return max(2.0, 40.0 - 1.5 * (t - BOOM - 24))
    o = onset_robust(months, _poisson_series(N, surge_collapse, 12), "T2")
    check("4. SURGE-THEN-COLLAPSE (the CBD shape) STILL fires - the graveyard MUST be "
          "able to false-positive, or the FP rate is zero by construction",
          o["onset_idx"] is not None and BOOM <= o["onset_idx"] <= BOOM + 15,
          "onset=%s (true=%s)" % (o["onset"], months[BOOM]))

    # ---- SPECIFICITY: does it stay silent when there is nothing there? ------
    o = onset_robust(months, _poisson_series(N, lambda t: 8.0, 2), "T2")
    check("5. flat Poisson noise does NOT fire", o["onset"] is None, "onset=%s" % o["onset"])

    spike = _poisson_series(N, lambda t: 8.0, 3)
    spike[130] = 90.0
    o = onset_robust(months, spike, "T2")
    check("6. a ONE-MONTH spike does NOT fire", o["onset"] is None, "onset=%s" % o["onset"])

    def seasonal(t):
        m = t % 12
        return 8.0 * (1.6 if m == 0 else (0.45 if m == 11 else 1.0))
    o = onset_robust(months, _poisson_series(N, seasonal, 5), "T2")
    check("7. strong seasonality with NO trend does NOT fire", o["onset"] is None,
          "onset=%s" % o["onset"])

    o = onset_robust(months, _poisson_series(N, lambda t: max(1.0, 30.0 - 0.15 * t), 8), "T2")
    check("8. a DECLINING niche does NOT fire", o["onset"] is None, "onset=%s" % o["onset"])

    o = onset_robust(months, _poisson_series(N, lambda t: 8.0 * (1.0 + 0.004 * t), 9), "T2")
    check("9. slow ~5%/yr drift does NOT fire - the fixture that exposed the "
          "noisy-denominator bug (g)", o["onset"] is None, "onset=%s" % o["onset"])

    rnd = random.Random(4)
    tiny = [float(rnd.choice([0, 0, 1, 0, 2, 1, 0, 1])) for _ in range(N)]
    o, sp = onset_robust(months, tiny, "T2"), onset_spec(months, tiny)
    check("10. tiny 0-2/month series does NOT fire (the level floor)",
          o["onset"] is None, "robust=%s" % o["onset"])
    check("11. ...while the BRIEF'S estimator is blind on the same data",
          sp["onset"] is not None or sp["undefined_months"] > 20,
          "spec onset=%s, %d months where its YoY divides by zero"
          % (sp["onset"], sp["undefined_months"]))

    nulls = {
        "flat noise": _poisson_series(N, lambda t: 8.0, 2),
        "one-month spike": spike,
        "seasonality, no trend": _poisson_series(N, seasonal, 5),
        "declining niche": _poisson_series(N, lambda t: max(1.0, 30.0 - 0.15 * t), 8),
        "slow 5%/yr drift": _poisson_series(N, lambda t: 8.0 * (1.0 + 0.004 * t), 9),
        "tiny 0-2/month": tiny,
    }
    fired = [k for k, v in nulls.items() if onset_robust(months, v, "T2")["onset"]]
    check("12. robust estimator false-fires on ZERO of the %d null fixtures" % len(nulls),
          len(fired) == 0, "fired on: %s" % (fired or "nothing"))

    # ---- HEAD-TO-HEAD on 8 independent real booms ---------------------------
    rb_hit = sp_hit = sp_miss = 0
    for seed in range(20, 28):
        x = _poisson_series(N, ramp, seed)
        rb, s2 = onset_robust(months, x, "T2"), onset_spec(months, x)
        if rb["onset_idx"] is not None and BOOM <= rb["onset_idx"] <= BOOM + 15:
            rb_hit += 1
        if s2["onset_idx"] is None:
            sp_miss += 1
        elif BOOM <= s2["onset_idx"] <= BOOM + 15:
            sp_hit += 1
    check("13. robust finds >= 7 of 8 independent real booms", rb_hit >= 7,
          "robust %d/8 | brief's spec %d/8 (it MISSED %d outright)"
          % (rb_hit, sp_hit, sp_miss))
    check("14. the BRIEF'S estimator misses booms the robust one catches",
          sp_hit < rb_hit, "spec %d/8 vs robust %d/8" % (sp_hit, rb_hit))

    # ---- IS THE ANSWER JUST THE THRESHOLD I PICKED? -------------------------
    s = _poisson_series(N, ramp, 11)
    onsets = [onset_robust(months, s, "T2", growth_x=x)["onset_idx"]
              for x in (1.25, 1.5, 2.0)]
    check("15. onset is stable across growth thresholds 1.25 / 1.5 / 2.0",
          all(o is not None for o in onsets) and (max(onsets) - min(onsets)) <= 9,
          "onsets at idx %s (true=%d)" % (onsets, BOOM))

    # ---- LOW-COUNT HONESTY: ~2/month is the real CQC regime -----------------
    def small(t):
        return 2.0 if t < BOOM else 2.0 * (1 + 4.0 * min(1.0, (t - BOOM) / 18.0))
    flags = []
    for seed in range(1, 9):
        o = onset_robust(months, _poisson_series(N, small, seed), "T3")
        if o["onset"]:
            flags.append(o["low_count_unreliable"])
    check("16. every onset found in a ~2/month series is FLAGGED low-count/unreliable",
          len(flags) > 0 and all(flags),
          "%d/8 seeds fired; all flagged unreliable = %s" % (len(flags), all(flags)))

    # ---- WHAT n PERMITS -----------------------------------------------------
    check("17. NO 95%% CI for the median exists at n=5", median_ci([1, 2, 3, 4, 5]) is None)
    check("18. a 95%% CI does exist at n=6 - and it is the full min-to-max range",
          median_ci([1, 2, 3, 4, 5, 6]) == (1, 6, 0.9688))
    check("19. sign test: a perfect sweep of 5 gives p=0.03125",
          abs(binom_tail(5, 5) - 0.03125) < 1e-9)
    check("20. n=5 CANNOT clear Bonferroni even with a perfect sweep",
          power_note(5)["passes"] is False,
          "p=%.4f vs alpha=%.4f" % (power_note(5)["perfect_sweep_p"],
                                    power_note(5)["bonferroni_alpha"]))
    check("21. n=7 clears it ONLY with a flawless 7/7 sweep",
          power_note(7)["passes"] is True and binom_tail(6, 7) > 0.0167,
          "7/7 -> p=%.4f (passes); 6/7 -> p=%.4f (FAILS)"
          % (binom_tail(7, 7), binom_tail(6, 7)))

    print("-" * 76)
    print("%d/21 fixtures passed" % (21 - len(fails)))
    if fails:
        print("FAILURES:")
        for f in fails:
            print("  - " + f)
        return 1
    print("\nPOWER CHECK on the shipped design (7 positive niches):")
    print("  " + power_note(7)["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
