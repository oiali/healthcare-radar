#!/usr/bin/env python3
"""
T4 CONSUMPTION - NHS prescribing (OpenPrescribing) BNF chemical codes.

EVERY code in DRUGS was verified TWICE on 13 Jul 2026:
  1. it exists as type="chemical" in
     https://openprescribing.net/api/1.0/bnf_code/?q=<name>&format=json
  2. it returns a LIVE monthly series from
     https://openprescribing.net/api/1.0/spending/?code=<code>&format=json
     -> >= 15 months of data AND a non-trivial latest 'items' count.

Codes that exist in the BNF but return a dead / empty / one-item series are in
DEAD_CODES with the reason, and are NOT in DRUGS. A dead code silently returns
nothing and shows the niche a FALSE DASH - the exact bug this file removes.

Shape matches template.py exactly:  DRUGS = {code: [name, niche, treats]}
Stdlib only.
"""

# ============================================================ VERIFIED CODES
DRUGS = {
    # ---- Weight loss / GLP-1 ---------------------------------------------
    "0601023AW": ["Semaglutide", "Weight loss / GLP-1", "type-2 diabetes & obesity (Ozempic / Wegovy)"],
    "0601023AZ": ["Tirzepatide", "Weight loss / GLP-1", "type-2 diabetes & obesity (Mounjaro)"],
    "0601023AB": ["Liraglutide", "Weight loss / GLP-1", "obesity & diabetes (Saxenda / Victoza)"],
    "0405010P0": ["Orlistat", "Weight loss / GLP-1", "obesity - blocks fat absorption (Xenical)"],

    # ---- ADHD -------------------------------------------------------------
    "0404000U0": ["Lisdexamfetamine", "ADHD", "ADHD - the adult-ADHD demand driver (Elvanse)"],
    "0404000M0": ["Methylphenidate", "ADHD", "ADHD stimulant (Concerta / Ritalin)"],
    "0404000S0": ["Atomoxetine", "ADHD", "ADHD, non-stimulant (Strattera)"],
    "0404000V0": ["Guanfacine", "ADHD", "ADHD, non-stimulant (Intuniv)"],
    "0404000L0": ["Dexamfetamine", "ADHD", "ADHD stimulant (Amfexa)"],

    # ---- Menopause / HRT --------------------------------------------------
    "0604011G0": ["Estradiol", "Menopause / HRT", "menopausal symptoms - oestrogen-only HRT"],
    "0604011L0": ["Estradiol w/ progestogen", "Menopause / HRT", "menopausal symptoms - combined HRT"],
    "0604011K0": ["Estradiol valerate", "Menopause / HRT", "menopausal symptoms - oral HRT"],
    "0604011Y0": ["Tibolone", "Menopause / HRT", "menopausal symptoms (Livial)"],
    "0604011P0": ["Oestrogens conjugated", "Menopause / HRT", "menopausal symptoms (Premarin)"],
    "0604012S0": ["Progesterone", "Menopause / HRT", "micronised progesterone, the HRT partner (Utrogestan)"],
    "0702010G0": ["Estradiol (vaginal)", "Menopause / HRT", "vaginal atrophy / genitourinary menopause"],

    # ---- Men's health / TRT -----------------------------------------------
    "0604020K0": ["Testosterone", "Men's health / TRT", "testosterone deficiency - gels & patches (Testogel)"],
    "0604020T0": ["Testosterone undecanoate", "Men's health / TRT", "testosterone deficiency - 12-weekly depot (Nebido)"],
    "0604020U0": ["Testosterone esters", "Men's health / TRT", "testosterone deficiency - injection (Sustanon)"],
    "0604020M0": ["Testosterone enantate", "Men's health / TRT", "testosterone deficiency - injection"],

    # ---- Hair restoration (THIN - see NICHES_THIN_PROXY) -------------------
    "1309000H0": ["Minoxidil (topical)", "Hair restoration", "male & female pattern hair loss (Regaine)"],

    # ---- Dermatology / acne -----------------------------------------------
    "1306020J0": ["Isotretinoin (oral)", "Dermatology / acne", "severe acne - the private-derm driver (Roaccutane)"],
    "1306010H0": ["Adapalene", "Dermatology / acne", "acne - topical retinoid (Differin)"],
    "1306010Z0": ["Adapalene/benzoyl peroxide", "Dermatology / acne", "acne - topical combination (Epiduo)"],
    "0501030L0": ["Lymecycline", "Dermatology / acne", "acne - oral antibiotic"],
    "1306020C0": ["Co-cyprindiol", "Dermatology / acne", "severe acne & hirsutism in women (Dianette)"],
    "1305020D0": ["Calcipotriol", "Dermatology / acne", "psoriasis - topical vitamin D analogue"],
    "1305030C0": ["Tacrolimus (topical)", "Dermatology / acne", "eczema / atopic dermatitis (Protopic)"],

    # ---- Mental health / psychiatry ---------------------------------------
    "0403030Q0": ["Sertraline", "Mental health / psychiatry", "depression & anxiety - the UK's #1 SSRI"],
    "0403030E0": ["Fluoxetine", "Mental health / psychiatry", "depression & anxiety (Prozac)"],
    "0403030D0": ["Citalopram", "Mental health / psychiatry", "depression & anxiety"],
    "0403030X0": ["Escitalopram", "Mental health / psychiatry", "depression & generalised anxiety"],
    "0403040X0": ["Mirtazapine", "Mental health / psychiatry", "depression, esp. with insomnia"],
    "0403040W0": ["Venlafaxine", "Mental health / psychiatry", "depression & anxiety (SNRI)"],
    "0403040Y0": ["Duloxetine", "Mental health / psychiatry", "depression, anxiety & neuropathic pain"],
    "0402010AB": ["Quetiapine", "Mental health / psychiatry", "bipolar & psychosis (Seroquel)"],
    "0402010AD": ["Aripiprazole", "Mental health / psychiatry", "psychosis & bipolar (Abilify)"],

    # ---- Sexual health / ED -----------------------------------------------
    "0704050Z0": ["Sildenafil", "Sexual health / ED", "erectile dysfunction (Viagra)"],
    "0704050R0": ["Tadalafil", "Sexual health / ED", "erectile dysfunction, long-acting (Cialis)"],
    "0704050AA": ["Vardenafil", "Sexual health / ED", "erectile dysfunction (Levitra)"],
    "0704050B0": ["Alprostadil", "Sexual health / ED", "erectile dysfunction - 2nd line (Caverject)"],

    # ---- Sleep ------------------------------------------------------------
    "0401010AD": ["Melatonin", "Sleep", "insomnia & circadian sleep disorders"],
    "0401010Z0": ["Zopiclone", "Sleep", "short-term insomnia (Z-drug)"],
    "0401010Y0": ["Zolpidem", "Sleep", "short-term insomnia (Z-drug)"],

    # ---- Migraine ---------------------------------------------------------
    "0407041T0": ["Sumatriptan", "Migraine", "acute migraine attack (Imigran)"],
    "0407041AD": ["Rimegepant", "Migraine", "acute migraine & prevention (Vydura)"],
    "0407042U0": ["Atogepant", "Migraine", "migraine prevention, oral CGRP (Aquipta)"],
    "040801050": ["Topiramate", "Migraine", "migraine prevention (also epilepsy)"],

    # ---- Bladder / continence / prostate ----------------------------------
    "0704020AE": ["Mirabegron", "Bladder / continence", "overactive bladder (Betmiga)"],
    "0704020AB": ["Solifenacin", "Bladder / continence", "overactive bladder (Vesicare)"],
    "0704020N0": ["Tolterodine", "Bladder / continence", "overactive bladder (Detrusitol)"],
    "0704020J0": ["Oxybutynin", "Bladder / continence", "overactive bladder / urge incontinence"],
    "0704010U0": ["Tamsulosin", "Bladder / continence", "enlarged prostate (BPH) - the men's-urology driver"],
    "0604020C0": ["Finasteride (5mg)", "Bladder / continence", "enlarged prostate (BPH) - Proscar, NOT the hair-loss dose"],
    "0604020B0": ["Dutasteride", "Bladder / continence", "enlarged prostate (BPH) - Avodart"],

    # ---- Osteoporosis / bone ----------------------------------------------
    "0606020A0": ["Alendronic acid", "Osteoporosis / bone", "osteoporosis - first-line bisphosphonate"],
    "0606020R0": ["Risedronate", "Osteoporosis / bone", "osteoporosis - bisphosphonate"],
    "0606020Z0": ["Denosumab", "Osteoporosis / bone", "osteoporosis - 6-monthly injection (Prolia)"],
    "0604011X0": ["Raloxifene", "Osteoporosis / bone", "post-menopausal osteoporosis (SERM)"],

    # ---- Diabetes ---------------------------------------------------------
    "0601022B0": ["Metformin", "Diabetes", "type-2 diabetes - first-line"],
    "0601023AG": ["Dapagliflozin", "Diabetes", "type-2 diabetes, heart & kidney (Forxiga)"],
    "0601023AN": ["Empagliflozin", "Diabetes", "type-2 diabetes, heart & kidney (Jardiance)"],
    "0601021M0": ["Gliclazide", "Diabetes", "type-2 diabetes - sulfonylurea"],

    # ---- Allergy ----------------------------------------------------------
    "0304010I0": ["Cetirizine", "Allergy", "hay fever & chronic urticaria"],
    "0304010E0": ["Fexofenadine", "Allergy", "hay fever & chronic urticaria (Telfast)"],
    "0304010D0": ["Loratadine", "Allergy", "hay fever & allergic rhinitis"],
    "0303020G0": ["Montelukast", "Allergy", "asthma with allergic rhinitis (Singulair)"],
    "0304020AB": ["Grass pollen extract", "Allergy", "grass-pollen immunotherapy (Grazax) - the allergy-clinic signal"],
    "0304020AD": ["House dust mite extract", "Allergy", "dust-mite immunotherapy (Acarizax)"],

    # ---- Neurology --------------------------------------------------------
    "0408010A0": ["Levetiracetam", "Neurology", "epilepsy (Keppra)"],
    "0408010H0": ["Lamotrigine", "Neurology", "epilepsy & bipolar"],
    "0409010N0": ["Co-careldopa", "Neurology", "Parkinson's disease (Sinemet)"],
    "0411000D0": ["Donepezil", "Neurology", "Alzheimer's dementia (Aricept)"],
    "0411000G0": ["Memantine", "Neurology", "moderate-severe Alzheimer's dementia"],

    # ---- Fertility / women's health ---------------------------------------
    # Fertility PROPER (IVF) has no primary-care proxy - see NICHES_THIN_PROXY.
    # These two are the gynaecology / heavy-bleeding side of the niche.
    "0211000P0": ["Tranexamic acid", "Fertility / women's health", "heavy menstrual bleeding"],
    "0604012P0": ["Norethisterone", "Fertility / women's health", "heavy / painful periods & cycle control"],
}


# ================================================ NICHES WITH NO NHS PROXY
# T4 for these should render "n/a", NOT a dash. A dash implies "we looked and
# found nothing". n/a means "NHS prescribing cannot see this niche at all".
NICHES_NO_PRESCRIBING = [
    "Aesthetics / skin",          # botox/fillers are private & procedural. The
                                  # botulinum BNF code is NHS spasticity/chronic
                                  # migraine use - tracking it would be a lie.
    "Diagnostics / imaging",      # scans are procedures, not prescriptions.
    "Dental / orthodontics",      # dental prescribing = antibiotics. No demand signal.
    "Tongue-tie / lactation",     # frenulotomy is a procedure. No drug.
    "Longevity / peptides / IV",  # IV drips, peptides & vitamins are private/OTC.
    "MSK / physio",               # see WEAK_PROXIES - analgesics are a bad proxy.
    "Audiology / hearing",        # hearing aids are devices. Betahistine (0406000B0)
                                  # is vertigo/Meniere's, not hearing-loss demand.
    "Eye / optical",              # glasses, lenses & cataract surgery are not drugs.
    "Private GP",                 # no drug is specific to "seeing a GP privately".
]

# Covered, but only just. Read the T4 number as directional at best.
NICHES_THIN_PROXY = {
    "Hair restoration":
        "only topical minoxidil (~600 items/mth). The finasteride-1mg code "
        "1309000W0 is effectively unused on the NHS (1 item/mth), so the "
        "private/OTC hair-loss market is invisible here.",
    "Fertility / women's health":
        "gynaecology drugs only. Clomifene (0605010G0, ~76 items/mth) and "
        "chorionic gonadotrophin (0605010D0, ~4 items/mth) are specialist-issued, "
        "so IVF / fertility demand is NOT visible.",
}

# Verified to EXIST as BNF chemicals, and verified to be USELESS as a signal.
# Listed so nobody re-adds them. Do NOT put these in DRUGS.
DEAD_CODES = {
    "1306010M0": "Isotretinoin (TOPICAL). ** LIVE IN template.py TODAY ** Series "
                 "died Sep-2023: 5 months, 2 items. Roaccutane is ORAL -> 1306020J0.",
    "0105030C0": "Risankizumab. ** LIVE IN template.py TODAY ** 1 month, 1 item. "
                 "It is a Crohn's code (BNF 1.5.3) anyway, not dermatology.",
    "0407042T0": "Erenumab. ** LIVE IN template.py TODAY ** 1 item/mth - CGRP "
                 "injectables are hospital-commissioned, invisible in GP data.",
    "0407042R0": "Fremanezumab. ** LIVE IN template.py TODAY ** 1 item/mth, same reason.",
    "0407042S0": "Galcanezumab. 2 items/mth, same reason.",
    "0405020U0": "Naltrexone/bupropion (Mysimba). ** LIVE IN template.py TODAY ** "
                 "4 items/mth - not funded on the NHS.",
    "0405010T0": "Naltrexone/Bupropion (duplicate code). Returns an EMPTY series.",
    "1309000W0": "Finasteride 1mg (scalp). 1 item/mth - not prescribed on the NHS.",
    "0604011M0": "Estriol (HRT). 1 month, 1 item.",
    "0606020AA": "Romosozumab. 5 months, 1 item - hospital-administered.",
    "0606020V0": "Zoledronic acid. 3 items/mth - hospital-administered.",
    "0606010U0": "Teriparatide. 3 items/mth - hospital-administered.",
    "0304020P0": "Pollen allergy preparations (legacy code). 1 month, 2 items.",
    "0605010G0": "Clomifene. ~76 items/mth - too thin to trend.",
    "0605010D0": "Chorionic gonadotrophin. ~4 items/mth.",
    "0803041L0": "Letrozole. Real series, but it is a BREAST-CANCER code (BNF 8.3.4). "
                 "Using it as a fertility proxy would be wrong.",
}

# Real, high-volume series - but they do NOT measure private-pay MSK demand.
# Analgesic prescribing tracks GP pain policy and the opioid-reduction agenda,
# and has been falling for years for reasons unrelated to whether people are
# paying for physio. Wiring these into MSK would make the niche look "late /
# already served" and would actively mislead the stage score.
# Left here, unused, as an explicit decision - not an oversight.
WEAK_PROXIES = {
    "1001010P0": ["Naproxen", "MSK / physio", "musculoskeletal pain (NSAID)"],
    "0407010F0": ["Co-codamol", "MSK / physio", "moderate pain (codeine/paracetamol)"],
    "0406000B0": ["Betahistine", "Audiology / hearing", "vertigo / Meniere's disease"],
}


# =================================================== ONE REQUEST PER NICHE
# VERIFIED 13 Jul 2026: the spending endpoint accepts COMMA-SEPARATED codes and
# returns a single SERVER-SIDE SUMMED monthly series.
#
#   ?code=0601023AW,0601023AZ  ->  Apr-2026 items = 446,838
#   ?code=0601023AW            ->  Apr-2026 items = 135,692
#   ?code=0601023AZ            ->  Apr-2026 items = 311,146
#                                             135,692 + 311,146 = 446,838  exact
#
# This matters. OpenPrescribing RATE-LIMITS. Firing all 76 codes in parallel
# (what template.py's Promise.all does today, just with 26) starts returning
# HTTP 429 after roughly 60 requests, and a 429 silently shows the niche a dash.
# Query by NICHE, not by DRUG: 16 requests instead of 76, and the sum is done
# server-side - so T4 no longer needs the volume-weighted agg() fudge.
NICHE_CODES = {}
for _code, (_name, _niche, _treats) in DRUGS.items():
    NICHE_CODES.setdefault(_niche, []).append(_code)

# {niche: "code1,code2,..."} - drop straight into the fetch URL.
NICHE_QUERY = {_niche: ",".join(sorted(_codes))
               for _niche, _codes in NICHE_CODES.items()}


# ------------------------------------------------------------------- sanity
def _self_check():
    """Cheap structural guards. No network."""
    errs = []
    for code, row in DRUGS.items():
        if len(code) != 9:
            errs.append("{}: BNF chemical codes are 9 chars, got {}".format(code, len(code)))
        if not isinstance(row, list) or len(row) != 3:
            errs.append("{}: expected [name, niche, treats]".format(code))
        elif not all(isinstance(x, str) and x.strip() for x in row):
            errs.append("{}: empty field".format(code))
    overlap = set(DRUGS) & set(DEAD_CODES)
    if overlap:
        errs.append("dead codes present in DRUGS: {}".format(sorted(overlap)))
    covered = {row[1] for row in DRUGS.values()}
    clash = covered & set(NICHES_NO_PRESCRIBING)
    if clash:
        errs.append("niche marked N/A but has drugs: {}".format(sorted(clash)))
    return errs


if __name__ == "__main__":
    problems = _self_check()

    print("VERIFIED BNF chemical codes : {}".format(len(DRUGS)))
    print("Niches with a T4 signal     : {}".format(len(NICHE_CODES)))
    print("Niches explicitly N/A       : {}".format(len(NICHES_NO_PRESCRIBING)))
    print("Dead codes excluded         : {}".format(len(DEAD_CODES)))
    print("HTTP calls if per-drug      : {}  (429 rate-limit territory)".format(len(DRUGS)))
    print("HTTP calls if per-niche     : {}  <- use NICHE_QUERY".format(len(NICHE_QUERY)))
    print()
    for niche in sorted(NICHE_CODES):
        thin = "  [THIN]" if niche in NICHES_THIN_PROXY else ""
        print("  {:<28} {:>2} drug(s){}".format(niche, len(NICHE_CODES[niche]), thin))
    print()
    for niche in NICHES_NO_PRESCRIBING:
        print("  {:<28} n/a".format(niche))
    print()
    if problems:
        print("SELF-CHECK FAILED:")
        for p in problems:
            print("  - " + p)
        raise SystemExit(1)
    print("SELF-CHECK PASS")
