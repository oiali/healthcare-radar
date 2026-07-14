# Backtest 3: four tiers, twelve years, and the ADHD question

Generated 2026-07-14. **T4 is in this study**, back to Jan-2014, via NHSBSA's own English Prescribing Dataset. The 'we cannot backtest T4' excuse is retired.


> **PARTIAL RUN - THE DATA BELOW IS INCOMPLETE. Numbers in this report can change when the remaining cells arrive.**
>
> - T2 Companies House: **17.0% of cells fetched** (1010/5940). Keywords with >=90% coverage, and therefore usable this run: 1/30. Withheld (<90% fetched, shown as 'no data', never zero-filled): adhd, autistic, cannabidiol, cbd, cold plunge, cryotherapy, fertility, hair restoration, hair transplant, hyperbaric, ice bath, iv drip, ivf, menopause, mens health, nad+, neurodiversity, nicotinamide, perimenopause, photobiomodulation, private doctor, private gp, psilocybin, psychedelic, red light therapy, semaglutide, testosterone, vitamin drip, weight loss.
>
> - T4 NHSBSA EPD: 100.0% of months (148/148).
>
> - Every fetched cell is cached and committed. A (keyword, month) count is immutable, so re-running the workflow RESUMES; it never repeats paid work. Run again until this banner disappears.


## 0. Read this before any number below

**This study cannot establish that the tiers work.** n = 8 positives and 8 graveyard niches. Six tier-pairs are tested, so a Bonferroni-corrected alpha is 0.0083; a *flawless* 8/8 sweep scores p = 0.0039 against a coin flip. One niche out of order and it fails. And the coin-flip null is itself wrong (section 3a). The only thing an n of 16 can do is **falsify**. If the graveyard fires as loudly as the positives, that kills the early tiers, and that is a real result. If it does not, that is *not* proof the tiers work - it is a failure to disprove them at n=16.

**T4's false-positive rate does not exist.** All 8 graveyard niches abstain on T4 - none of CBD, IV drips, cryotherapy, ice baths, psilocybin, NAD+, hyperbaric oxygen or red-light therapy is an NHS-prescribed medicine. Zero informative negatives means no rate. Section 4 prints `n/a`, not `0.00`. Anyone who reports 0.00 for T4 is laundering an abstention into a correct rejection.

**T4 also abstains on 4 of the 8 positives** (private GP, autism, hair transplant, IVF) for reasons `drugs.py` had already verified and written down. T4's lead/lag numbers therefore rest on **n=4**: ADHD, GLP-1, menopause/HRT, TRT.

**Abstentions are not rejections.** A tier that legally or structurally cannot see a niche has abstained. Counting abstentions as correct rejections drives the false-positive rate to zero for free. Both the honest and the credulous rate are printed in section 4; the gap between them is the size of the lie you would otherwise have told.

**The niches are not independent.** ADHD and autism assessment share operators. Section 4 is re-run without autism, and without NAD+ (which has not resolved).


## 1. THE BENCHMARK: standing in 2022-03, would this radar have flagged ADHD?

The owner's test: *"I wanted to catch the ADHD boom 2 years ago."* So: freeze the clock at **2022-03**, allow the radar only the data that had actually been published by then, and ask each tier.

`knowable by` = the onset month **+ 3** (onset_robust will not confirm a boom until z stays elevated for 3 further months) **+ the source's own publication lag** (T4 is ~3 months in arrears; NHSBSA publishes January in March). A boom you can only date with hindsight is not an early warning.


| Tier | | Onset | Knowable by | Flagged by 2022-03? | YoY growth visible on the screen at 2022-03 | Notes |
|---|---|---|---|---|---|---|
| T1 | INTENT (search) | - | - | no | - | NO_DATA |
| T2 | ENTRY (new companies) | - | - | no | - | NO_DATA |
| T3 | CAPACITY (new CQC clinics) | - | - | no | - | NO_ONSET |
| T4 | CONSUMPTION (NHS prescribing) | - | - | no | +12% | NO_ONSET |

### Verdict: NO - not one tier had fired and become knowable by 2022-03


The last two columns are the honest complication and they must be read together. The **onset detector** answers 'is a NEW boom starting?'. It is deliberately blind to a niche that has been compounding at the same rate for years - that is what stops it screaming at everything large. The **YoY column** is what would actually have been on the dashboard. A tier can be silent and the niche can still be visibly, enormously growing. Neither number alone answers the owner's question; both together do.


The same table for every positive niche is in `backtest3.json` under `standing_all`. Section 2 gives the raw onsets.


## 2. Onsets

| Niche | Class | T1 intent | T2 entry | T3 capacity | T4 prescribing |
|---|---|---|---|---|---|
| ADHD (private assessment) | positive | _no data_ | _no data_ | no onset | no onset |
| Weight loss / GLP-1 | positive | _no data_ | _no data_ | no onset | **2025-04** |
| Menopause / HRT | positive | _no data_ | _no data_ | no onset | **2022-05** |
| Men's health / TRT | positive | _no data_ | _no data_ | _abstains: below floor_ | no onset |
| Hair transplant / restoration | positive | _no data_ | _no data_ | no onset | _abstains: out of scope_ |
| Autism assessment | positive | _no data_ | no onset | no onset | _abstains: out of scope_ |
| Private GP | positive | _no data_ | _no data_ | no onset | _abstains: out of scope_ |
| IVF / fertility | positive | _no data_ | _no data_ | no onset | _abstains: out of scope_ |
| CBD / cannabidiol | graveyard | _no data_ | _no data_ | _abstains: out of scope_ | _abstains: out of scope_ |
| IV vitamin drips | graveyard | _no data_ | _no data_ | _abstains: below floor_ | _abstains: out of scope_ |
| Cryotherapy (whole-body) | graveyard | _no data_ | _no data_ | _abstains: out of scope_ | _abstains: out of scope_ |
| Cold-water therapy / ice baths | graveyard | _no data_ | _no data_ | _abstains: out of scope_ | _abstains: out of scope_ |
| Psychedelics / psilocybin | graveyard | _no data_ | _no data_ | _abstains: out of scope_ | _abstains: out of scope_ |
| NAD+ infusions | graveyard | _no data_ | _no data_ | _abstains: below floor_ | _abstains: out of scope_ |
| Hyperbaric oxygen therapy | graveyard | _no data_ | _no data_ | _abstains: out of scope_ | _abstains: out of scope_ |
| Red-light therapy | graveyard | _no data_ | _no data_ | _abstains: out of scope_ | _abstains: out of scope_ |

`(!)` the series was too thin at onset (< 36 events/yr) for the DATE to be trustworthy - that it fired is meaningful, the month is not.  
`(<)` **left-censored**: it fired in the first months it was allowed to, so the boom was probably already running before the data starts. The onset is a lower bound.


### 2a. 'Already booming' - the state that would otherwise have been read as a correct rejection

`onset_robust` does not detect growth. It detects **acceleration** - a break from a niche's own recent growth regime. Feed it a series compounding at a steady +3% a month from its very first observation and **it never fires at all**, because its z-scale is the median and MAD of that niche's own recent z-history, and a smooth exponential has a flat z-history. That is a feature: it is what stops the detector screaming at every niche that is merely large.


But it has a consequence that had not been written down anywhere, and it lands squarely on the benchmark case. **A niche that was already in a sustained boom before the data window opened reports NO ONSET - which in a results table is indistinguishable from the estimator having correctly REJECTED it.** T4's history starts in Jan-2014, and lisdexamfetamine was already at 737 items/month and climbing hard. Score a T4 silence on ADHD as 'T4 did not flag ADHD' and you have reported the exact opposite of the truth.


No niche/tier combination came out ALREADY_BOOMING in this run.


## 3. Lead times (positives only), scored against the null

A **positive** gap means the earlier tier fired first - the radar's claim. Adjacent pairs are the actual claim (T1->T2->T3->T4); the rest are shown because if T4 fires FIRST that is a fact about the tier model, not a bug.


| Pair | n | Median gap | Range | 95% CI | In order | **Null gap (true lead=0)** | Null p90 | **Beats the null?** |
|---|---|---|---|---|---|---|---|---|
| T1->T2 *(adjacent)* | 0 | - | - | **none exists at this n** | 0/0 | +11 | +19 | - |
| T1->T3 | 0 | - | - | **none exists at this n** | 0/0 | - | - | - |
| T1->T4 | 0 | - | - | **none exists at this n** | 0/0 | +3.0 | +4 | - |
| T2->T3 *(adjacent)* | 0 | - | - | **none exists at this n** | 0/0 | - | - | - |
| T2->T4 | 0 | - | - | **none exists at this n** | 0/0 | +-8 | +45 | - |
| T3->T4 *(adjacent)* | 0 | - | - | **none exists at this n** | 0/0 | - | - | - |

### 3a. The null, and why the sign test in every previous version was wrong

`calibrate_null()` simulates 200 niches whose **four tiers all boom in the same calendar month** - a true lead of exactly **zero** - and pushes them through the real axes, the real level floors and the real estimator. Whatever comes out is manufactured entirely by the measurement.


Three things manufacture it, and the second is the big one:

1. **Thin series cross a threshold later than smooth ones.** T1 is a smooth 0-100 index; T3 is ~3 clinics a month.

2. **The tiers' histories start in different years, and the estimator needs ~54 months of warm-up before it can fire at all.** T2 starts in 2010 and can fire from ~2014-07. T3 and T4 start in 2014 and *cannot fire before ~2018-07*, however loud the boom is. A 2018 boom therefore shows a ~6-month 'T2 leads T3' that is nothing but the start date of a spreadsheet. **backtest2.py's docstring missed this and attributed the whole artefact to thinness.**

3. **The level floors differ per tier** (T1 120, T2 12, T3 6, T4 500 per 12 months), so tiers become able to fire at different points in a niche's growth.


| Pair | Null median gap | Null p90 | Null: %% landing 'in the predicted order' | Measured | Excess over null |
|---|---|---|---|---|---|
| T1->T2 | **+11** | +19 | **79%** | - | - |
| T1->T3 | - | - | - | - | - |
| T1->T4 | **+3.0** | +4 | **100%** | - | - |
| T2->T3 | - | - | - | - | - |
| T2->T4 | **+-8** | +45 | **21%** | - | - |
| T3->T4 | - | - | - | - | - |

**Look at the 'in the predicted order' column.** Under a *zero* true lead this pipeline still puts the tiers in the radar's predicted order most of the time. So the classic sign test - 'each niche is a coin flip, p=0.5' - is testing against a null that is simply false, and it is false in the direction that flatters the thesis. A perfect 8/8 sweep would score p=0.0039 against a coin flip and look like a discovery when **8/8 is the expected result of no effect at all**.


| Pair | In order | Naive p (vs coin flip) - **WRONG** | Calibrated null | **Calibrated p - USE THIS** |
|---|---|---|---|---|

Null fire rates (share of zero-lead simulations in which each tier fired at all): `{"T1": 1.0, "T2": 0.145, "T3": 0.0, "T4": 1.0}`. Null left-censoring rates: `{"T1": 0.0, "T2": 0.0, "T3": null, "T4": 0.135}`.


The null was calibrated to **the levels and growth multiples OBSERVED in this run**.


## 4. THE POINT OF THE WHOLE FILE: does the graveyard fire too?

| Tier | Hit rate (positives) | FP rate - **HONEST** | FP rate - credulous | Fisher p (does it discriminate?) | Graveyard abstained |
|---|---|---|---|---|---|
| T1 INTENT (search) | None (0 informative) | **n/a - NO INFORMATIVE NEGATIVES** | 0.0 | None | 8 of 8 |
| T2 ENTRY (new companies) | 0.0 (1 informative) | **n/a - NO INFORMATIVE NEGATIVES** | 0.0 | None | 8 of 8 |
| T3 CAPACITY (new CQC clinics) | 0.0 (7 informative) | **n/a - NO INFORMATIVE NEGATIVES** | 0.0 | None | 8 of 8 |
| T4 CONSUMPTION (NHS prescribing) | 0.5 (4 informative) | **n/a - NO INFORMATIVE NEGATIVES** | 0.0 | None | 8 of 8 |

**Read the Fisher column, not the hit rate.** A tier that fires on 8/8 booms and 6/6 duds has a perfect hit rate and zero information. Fisher asks the only question that matters: does this tier fire on real booms *more often* than on duds? A p near 1.0 means no. A merely non-significant p at n=16 means **this study could not tell** - which is not the same as 'it works'.

- **T1**: This tier's specificity rests on 0 of 8 graveyard niches; 8 ABSTAINED. WITH ZERO INFORMATIVE NEGATIVES ITS FALSE-POSITIVE RATE DOES NOT EXIST. It has not been shown to discriminate; it has not been TESTED.

- **T2**: This tier's specificity rests on 0 of 8 graveyard niches; 8 ABSTAINED. WITH ZERO INFORMATIVE NEGATIVES ITS FALSE-POSITIVE RATE DOES NOT EXIST. It has not been shown to discriminate; it has not been TESTED.

- **T3**: This tier's specificity rests on 0 of 8 graveyard niches; 8 ABSTAINED. WITH ZERO INFORMATIVE NEGATIVES ITS FALSE-POSITIVE RATE DOES NOT EXIST. It has not been shown to discriminate; it has not been TESTED.

- **T4**: This tier's specificity rests on 0 of 8 graveyard niches; 8 ABSTAINED. WITH ZERO INFORMATIVE NEGATIVES ITS FALSE-POSITIVE RATE DOES NOT EXIST. It has not been shown to discriminate; it has not been TESTED.


### 4a. Do the early tiers fire as LOUDLY for the duds?

Hit/miss is binary and throws away the amplitude. The live radar *ranks* niches by signal strength, so if the graveyard's `peak_z` is the same size as the positives', the ranking carries no information even if the firing does.


| Tier | Median peak z, positives | Median peak z, graveyard | Difference | Exact permutation p |
|---|---|---|---|---|
| T1 | - | - | - | not computable (too few niches fired) |
| T2 | - | - | - | not computable (too few niches fired) |
| T3 | - | - | - | not computable (too few niches fired) |
| T4 | - | - | - | not computable (too few niches fired) |

### 4b. The disconfirming cases

**NONE.** No graveyard niche fired on any tier. **Before celebrating, read the abstention column above.** If the graveyard mostly abstained, this says nothing at all - the tiers were not tested, they were excused.


## 5. T4 in detail - what it can and cannot see

Source: NHSBSA Open Data Portal, English Prescribing Dataset, 2014-01 to 2026-04. No API key. One request per month, cached forever (a published month is immutable).


**The schema trap.** NHSBSA renamed `bnf_chemical_substance` from a CODE to a NAME in July 2025. Querying the new table with the old column returns `null`, not an error - and a careless module turns that null into a zero and reports that ADHD prescribing collapsed. Every month here is validated against a canary chemical (sertraline). A month that fails is **dropped, never zeroed**. Months rejected this run: ?.


**What EPD structurally cannot see:** private prescriptions (so private TRT, private weight-loss jabs and private ADHD scripts are invisible), Scotland, Wales and Northern Ireland, secondary/hospital-issued drugs (so IVF), dental prescribing, and anything supplied under a Patient Group Direction.


| Niche | T4 | Why |
|---|---|---|
| ADHD (private assessment) | **IN SCOPE** | ADHD stimulants and non-stimulants: 0404000L0, 0404000M0, 0404000S0, 0404000U0, 0404000V0. The cleanest T4 signal in the set. |
| Weight loss / GLP-1 | **IN SCOPE** | semaglutide / tirzepatide / liraglutide / orlistat: 0405010P0, 0601023AB, 0601023AW, 0601023AZ. CAVEAT: NHS GLP-1 prescribing is mostly for TYPE-2 DIABETES, and the private weight-loss market is invisible to EPD by definition. T4 here measures the molecule, not the market. |
| Menopause / HRT | **IN SCOPE** | HRT: 0604011G0, 0604011K0, 0604011L0, 0604011P0, 0604011Y0, 0604012S0, 0702010G0. NHS-dispensed HRT is a good proxy for menopause demand - the 2022 supply crisis is in this series. |
| Men's health / TRT | **IN SCOPE** | testosterone: 0604020K0, 0604020M0, 0604020T0, 0604020U0. Weaker than it looks: much private TRT is prescribed privately and dispensed privately, so it never enters EPD. |
| Hair transplant / restoration | abstains | ABSTAINS. drugs.py: 'only topical minoxidil (~600 items/mth). The finasteride-1mg code 1309000W0 is effectively unused on the NHS (1 item/mth), so the private/OTC hair-loss market is invisible here.' A hair TRANSPLANT is a surgical procedure and is not prescribed at all. Firing or not firing on NHS minoxidil would tell you nothing about the niche, so T4 does not get to vote. |
| Autism assessment | abstains | ABSTAINS. There is no autism-specific chemical. Autistic patients are prescribed ADHD and antipsychotic medicines, so any proxy would be measuring a different niche. |
| Private GP | abstains | ABSTAINS. drugs.py lists 'Private GP' in NICHES_NO_PRESCRIBING: 'no drug is specific to seeing a GP privately.' Worse, EPD counts NHS primary-care dispensing, so a shift of patients OUT of the NHS would move this series DOWN. Wrong sign, not just no signal. |
| IVF / fertility | abstains | ABSTAINS. drugs.py: 'Clomifene (~76 items/mth) and chorionic gonadotrophin (~4 items/mth) are specialist-issued, so IVF / fertility demand is NOT visible.' EPD is primary care only. |
| CBD / cannabidiol | abstains | ABSTAINS. The only licensed CBD medicine in the UK is Epidyolex, for Dravet and Lennox-Gastaut syndrome - childhood epilepsies. Its prescribing measures paediatric neurology, not the CBD wellness boom. There is no code in drugs.py and one will not be invented here. NOTE THE CONSEQUENCE: on the single most dangerous false positive in the study, T4 HAS NO OPINION. It could not have saved you from CBD. |
| IV vitamin drips | abstains | ABSTAINS. IV vitamin drips are private and are not dispensed in NHS primary care. |
| Cryotherapy (whole-body) | abstains | ABSTAINS. Not a medicine. |
| Cold-water therapy / ice baths | abstains | ABSTAINS. Not a medicine. |
| Psychedelics / psilocybin | abstains | ABSTAINS. Psilocybin is Schedule 1. It cannot appear in NHS primary-care dispensing, so T4's silence is the Misuse of Drugs Act talking, not the radar. |
| NAD+ infusions | abstains | ABSTAINS. NAD+ infusions are private. Nicotinamide IS in the BNF (a vitamin, and a topical acne treatment) but its prescribing has nothing to do with longevity clinics; using it would be a category error, and drugs.py has no code for it. |
| Hyperbaric oxygen therapy | abstains | ABSTAINS. Oxygen under pressure is a procedure, not a prescription. |
| Red-light therapy | abstains | ABSTAINS. A device, not a medicine. |

**Unscored diagnostics.** The two thin proxies are computed but not allowed to vote, because the proxy does not measure the niche. Published so nothing is hidden:

- `hair` (1309000H0): onset none, state NO_ONSET.

- `ivf` (0211000P0, 0604012P0): onset none, state NO_ONSET.


## 6. The CQC survivorship correction, measured

The CQC active-locations file contains only clinics **still open**. Used alone it understates every historical month, invents an upward trend in every niche, and biases every T3 onset LATE - which inflates the T2->T3 lead, the single number a buyer would act on. CQC publishes a deactivated-locations file on the same page; both are merged here, and re-registrations are de-duplicated on (name, postcode) keeping the earliest date, because a clinic enters the market once.


| Niche | Active | Recovered from the deactivated file | Understated by | Onset: active-only | Onset: corrected | Onset moved |
|---|---|---|---|---|---|---|
| ADHD (private assessment) | 40 | 2 | 4.8% | - | - | - |
| Weight loss / GLP-1 | 9 | 5 | 35.7% | - | - | - |
| Menopause / HRT | 22 | 13 | 37.1% | - | - | - |
| Men's health / TRT | 3 | 1 | 25.0% | - | - | - |
| Hair transplant / restoration | 19 | 12 | 34.5% | - | - | - |
| Autism assessment | 49 | 76 | 45.8% | - | - | - |
| Private GP | 27 | 15 | 34.1% | - | - | - |
| IVF / fertility | 15 | 37 | 66.7% | - | - | - |
| IV vitamin drips | 5 | 1 | 16.7% | - | - | - |
| NAD+ infusions | 1 | 0 | 0.0% | - | - | - |

Every number in the last column should be >= 0: a missing clinic is always in the past, so an active-only file can only ever tell you a boom started **later** than it did. **If that column is materially non-zero, no T3 result computed from an active-only file - including whatever the live radar shows today - is safe to quote.**


## 7. Robustness of the T2 construction

T2 sums the monthly hit-counts of a niche's keywords. A company called 'Menopause & Perimenopause Clinic Ltd' is therefore counted twice. This inflates the LEVEL. It does NOT move the onset DATE, because the estimator works on the log-ratio of the series to its own past: a constant multiplicative inflation c cancels in ln((cR+K)/(cB+K)) for any K small relative to R. It only bites if the overlap FRACTION changes over time. Guarded anyway: every onset is recomputed on the PRIMARY KEYWORD ALONE, which cannot double-count, and any disagreement is reported.


No niche's T2 onset changes under the primary-keyword-only rebuild. Double-counting is not driving the dates.


### 7a. Keyword precision probe

The Companies House `hits`-count trick returns no company names, so we cannot re-filter what CH decided `company_name_includes` meant. One extra call per keyword pulls 100 names and re-applies a strict word-boundary matcher. Not a random sample, so this is a smell test, not an estimate.


| Keyword | Precision on 100 sampled names | Examples wrongly matched |
|---|---|---|
| `private gp` | **50%** | BEECHBROOK PRIVATE DEBT III GP LP, CORNERSTONE PRIVATE EQUITY GP 4 LLP, SCHRODERS CAPITAL PRIVATE EQUITY FOUNDER PARTNER (GP) LIMITED, EXPONENT PRIVATE EQUITY PARTNERS GP OF GP II LLP, CORNERSTONE PRIVATE EQUITY GP II LIMITED, LIONHEART GP UK PRIVATE LIMITED |

**These keywords are contaminated**, their niches' T2 counts are inflated by unrelated companies, and those T2 onsets should be discounted. `cbd` and `nad` are 3-letter tokens and are the obvious risks.


## 8. Is the answer just the threshold I picked?


| Pair | growth >= 1.25x | growth >= 1.5x (shipped) | growth >= 2.0x |
|---|---|---|---|
| T1->T2 | median None (n=0, 0 in order) | median None (n=0, 0 in order) | median None (n=0, 0 in order) |
| T2->T3 | median None (n=0, 0 in order) | median None (n=0, 0 in order) | median None (n=0, 0 in order) |
| T3->T4 | median None (n=0, 0 in order) | median None (n=0, 0 in order) | median None (n=0, 0 in order) |

If the **sign** of a median gap flips across that row, the ordering is an artefact of the threshold, not a fact about the world, and must not be reported as a finding.


## 9. Sensitivity to two contested labels


| Scenario | T1 FP | T2 FP | T3 FP | T4 FP |
|---|---|---|---|---|
| as shipped | n/a | n/a | n/a | n/a |
| without NAD+ (unresolved - may not be a dud at all) | n/a | n/a | n/a | n/a |
| without autism (not independent of ADHD) | n/a | n/a | n/a | n/a |

NAD+ is in the graveyard although it has **not resolved**. If it becomes a real boom, its false positives here are actually true positives. Quote the range, never the point.


## 10. Where the estimator choice changes the answer


| Niche | Tier | Robust (shipped) | The original brief's estimator | Months its YoY divides by zero |
|---|---|---|---|---|
| adhd | T4 | none | 2019-08 | 0 |
| glp1 | T4 | 2025-04 | 2018-10 | 0 |
| menopause | T4 | 2022-05 | 2021-08 | 0 |
| trt | T4 | none | 2023-10 | 0 |

## 11. Why each graveyard niche is in the graveyard


**CBD / cannabidiol** - THE KEY NEGATIVE, and the single case most likely to sink T1+T2 on its own. T1 spiked violently in 2018-19 AND T2 fired hard - roughly 500 UK companies sat behind the ~12,000 products on the FSA novel-foods list. The FSA backlog then froze the market and a large share of those companies have since dissolved. If the early tiers fired this loudly for a wipeout, the early tiers cannot discriminate. THIS IS THE RESULT TO LOOK FOR FIRST.


**IV vitamin drips** - THE HARDEST AND MOST INFORMATIVE NEGATIVE. IV administration of a prescription-only product (0.9% saline included) for wellbeing IS a CQC regulated activity - so unlike the rest of the graveyard, ALL THREE tiers can fire here. It is also the ONLY graveyard niche that gives T3 an informative negative at all. Commercially it produced no scaled UK operator in ~8 years.

  - *Caveat:* CONTESTABLE. Get A Drip and REVIV do exist. This is 'commercially marginal', not 'zero'. It is the negative most open to argument, and T3's entire specificity claim rests on it.


**Cryotherapy (whole-body)** - Spiked c.2016-18 on athlete endorsement. Not a CQC regulated activity. No scaled UK operator emerged.


**Cold-water therapy / ice baths** - An enormous T1 spike 2021-24 (Wim Hof, Huberman) with zero clinical infrastructure behind it. The purest test of 'T1 blares and nothing follows'.


**Psychedelics / psilocybin** - T1 and T2 both fired - Compass Pathways' 2020 IPO, Small Pharma, Beckley Psytech, plus a long tail of shells. Psilocybin is Schedule 1, so no lawful UK treatment clinic can exist and T3 cannot fire BY CONSTRUCTION.

  - *Caveat:* T3's 'correct rejection' here is worth NOTHING. The drug is illegal. That is the Misuse of Drugs Act doing the work, not the radar. Counted as an abstention.


**NAD+ infusions** - Placed in the graveyard AS INSTRUCTED, but under protest - see the caveat. Longevity-clinic staple, no scaled UK operator to date.

  - *Caveat:* THIS LABEL MAY BE WRONG AND THE STUDY KNOWS IT. NAD+ is still RISING. Calling a live, unresolved niche a 'dud' assumes the answer to the question the radar exists to ask, and if NAD+ turns out to be a real boom then every false positive it generates here is actually a true positive. The headline false-positive rates are therefore reported BOTH WITH AND WITHOUT NAD+, and the difference is the size of the assumption. Do not quote one number.


**Hyperbaric oxygen therapy** - Recurrent biohacking spikes. UK supply is dominated by decades-old charity-run MS therapy centres, not new commercial entrants.

  - *Caveat:* t3_scope=False is CONTESTABLE: HBOT for a licensed indication would be a regulated activity. The charity centres largely sit outside CQC. Marked out of scope, i.e. T3 gets NO credit either way.


**Red-light therapy** - Resolved into a consumer-DEVICE market (masks, panels), not a clinic market. Tests the case where demand is real but the delivery model is retail - which a clinic roll-up cannot buy.


## 12. Diagnostics

```
{
 "t4_months_total": 148,
 "t4_months_cached": 148,
 "t4_latest_published": "2026-04",
 "t4_codes": 23,
 "t4": "cache hit - 148/148 months, 0 calls",
 "t2_cells_total": 5940,
 "t2_cells_cached": 1010,
 "t2_deadline_hit": true,
 "t2_calls_spent": 1366,
 "t2_errors": {
  "HTTP 404": 1303,
  "exhausted": 63
 },
 "t2_cells_new_this_run": 0,
 "t2_coverage": 0.17,
 "t2": "PARTIAL - 1010/5940 cells (4930 left; re-run to resume, the cache persists)",
 "cqc_active_url": "https://www.cqc.org.uk/sites/default/files/2026-07/01_July_2026_HSCA_Active_Locations.ods",
 "cqc_deactivated_url": "https://www.cqc.org.uk/sites/default/files/2026-07/01_July_2026_Deactivated_Locations.ods",
 "cqc_active_cols": {
  "name": 4,
  "pc": 27,
  "start": 1
 },
 "cqc_active_rows": 56870,
 "cqc_active_has_postcode": true,
 "cqc_deact_cols": {
  "name": 2,
  "pc": 25,
  "start": 4
 },
 "cqc_deact_rows": 64880,
 "cqc_deact_has_postcode": true,
 "cqc_survivorship_corrected": true,
 "t3": "cache hit",
 "t1_inherited_from_backtest1": [],
 "t1": "SKIPPED. 0/16 terms cached; ['adhd', 'autism', 'cbd', 'coldwater', 'cryo', 'glp1', 'hair', 'hbot', 'ivdrip', 'ivf', 'menopause', 'nad', 'privategp', 'psychedelics', 'redlight', 'trt'] missing. Re-run with --trends to spend 16 SerpApi calls (once, ever). T1 is WITHHELD for the missing terms, not zeroed."
}
```

