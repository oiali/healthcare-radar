#!/usr/bin/env python3
"""
Shared niche taxonomy + FIXED matcher for the UK Healthcare Niche Radar.

WHY THIS FILE EXISTS
--------------------
The old matcher used a LEADING word boundary only:

    re.search(r"\\b" + re.escape(k), t)

so every keyword behaved as a PREFIX. Correct for stems ("dermatolog" ->
dermatology / dermatologist), catastrophic for short keys:

    "Skinner & Partners"  -> "skin" -> Aesthetics    WRONG
    "Brown Dental"        -> "brow" -> Aesthetics    WRONG
    "Lipscomb Opticians"  -> "lip"  -> Aesthetics    WRONG
    "Molesey Clinic"      -> "mole" -> Dermatology   WRONG
    "Scanlon"             -> "scan" -> Diagnostics   WRONG

THE FIX - two explicit key kinds
--------------------------------
  "dermatolog*"  trailing asterisk  -> STEM  match:  \\bdermatolog
  "skin"         no asterisk        -> WHOLE-WORD match:  \\bskin\\b

Multi-word keys ("laser eye", "women's health") are matched as whole phrases
with word boundaries at both ends.

TIE-BREAKING - longest key wins, then list order
------------------------------------------------
The old rule was "first niche in the list that matches, wins". That breaks on
overlapping keys: "Laser Eye Surgery" would hit Aesthetics ("laser") before it
ever reached Eye / optical ("laser eye").

New rule: among ALL matching keys, the LONGEST key wins (most specific literal
evidence); ties are broken by position in NICHES (so the old ordering intuition
still holds for equally-specific matches). This is what makes
"Skin Cancer Clinic" -> Dermatology while "Skin Clinic" -> Aesthetics.

Public API is unchanged:  niche_of(text) -> str | None
Added:                    niche_match(text) -> (niche, matched_key) | (None, None)

Stdlib only.
"""

import re

# ============================================================ NICHE TAXONOMY
# Key syntax:  "foo*" = stem/prefix match      "foo" = whole-word match
# Order still matters, but only as a TIE-BREAK between equally-long keys.
NICHES = [
    ("Weight loss / GLP-1", [
        "weight loss", "weight-loss", "weight management", "weight",
        "semaglutide*", "tirzepatide*", "liraglutide*",
        "ozempic", "wegovy", "mounjaro", "saxenda",
        "obesity", "obese", "slimming", "orlistat", "bariatric*",
        "glp", "glp-1", "glp1",
    ]),
    ("ADHD", [
        "adhd", "attention deficit", "lisdexamfetamine", "methylphenidate",
        "atomoxetine", "guanfacine", "elvanse", "neurodiver*",
    ]),
    ("Menopause / HRT", [
        "menopaus*", "perimenopaus*", "hrt", "hormone replacement",
        "tibolone", "estradiol*", "oestradiol*", "oestrogen*", "estrogen*",
    ]),
    ("Men's health / TRT", [
        "testosterone", "trt", "hypogonad*", "androlog*",
        "mens health", "men's health", "male health",
    ]),
    ("Hair restoration", [
        "hair transplant", "hair restoration", "hair loss", "hair clinic",
        "hairline", "hair", "finasteride", "minoxidil", "alopecia",
    ]),
    ("Tongue-tie / lactation", [
        "tongue tie", "tongue-tie", "tongue", "lactation",
        "breastfeed*", "frenulotom*", "frenotom*",
    ]),
    ("Aesthetics / skin", [
        "aesthetic*", "botox*", "botulinum", "dermal filler", "filler", "fillers",
        "cosmetic*", "skin", "laser", "lip", "lips", "facial", "beauty",
        "rejuven*", "eyebrow*", "brow", "brows", "lash", "lashes", "eyelash*",
        "peel", "peels", "microneedl*", "injectable*",
        "anti-wrinkle", "wrinkle", "medispa", "medi-spa",
    ]),
    ("Dermatology / acne", [
        "dermatolog*", "dermatit*", "acne", "isotretinoin", "eczema",
        "psoria*", "rosacea", "mole", "moles", "mole check",
        "skin cancer", "hidradenitis",
    ]),
    ("MSK / physio", [
        "physio*", "chiropract*", "chiropod*", "osteopath*", "musculoskeletal",
        "msk", "sports injury", "podiatr*", "orthopaed*", "orthoped*",
        "spine", "spinal", "joint", "joints", "rehab*",
    ]),
    ("Mental health / psychiatry", [
        "psychiatr*", "psycholog*", "psychotherap*", "mental", "counsel*",
        "ketamine", "depress*", "anxiet*", "autis*", "camhs",
    ]),
    ("Sexual health / ED", [
        "erectile dysfunction", "erectile", "sildenafil", "tadalafil", "viagra",
        "sexual health", "libido", "premature ejaculation",
    ]),
    ("Diagnostics / imaging", [
        "diagnostic*", "imaging", "ultrasound", "radiolog*", "endoscop*",
        "screening", "phlebotom*", "blood test", "blood tests", "pathology",
        "scan", "scans", "mri", "ct scan", "x-ray", "xray", "labs",
    ]),
    ("Fertility / women's health", [
        "fertil*", "ivf", "gynaecolog*", "gynecolog*", "obstetric*",
        "endometrios*", "polycystic", "pcos", "midwif*", "antenatal",
        "women's health", "womens health", "women",
    ]),
    ("Sleep", [
        "sleep", "insomnia", "melatonin", "apnoea", "apnea", "snoring",
    ]),
    ("Dental / orthodontics", [
        "dental", "dentist*", "orthodont*", "endodont*", "periodont*",
        "oral surgery", "smile", "invisalign", "hygienist",
    ]),
    ("Longevity / peptides / IV", [
        "longevity", "peptide", "peptides", "iv drip", "drip", "infusion",
        "vitamin", "vitamins", "wellness", "biohack*", "cryo*", "hyperbaric",
    ]),
    ("Migraine", [
        "migraine*", "erenumab", "fremanezumab", "galcanezumab",
        "rimegepant", "atogepant", "sumatriptan",
        "cluster headache", "headache*",
    ]),
    ("Bladder / continence", [
        "overactive bladder", "bladder", "continence", "incontinence",
        "mirabegron", "solifenacin", "urolog*", "prostate", "prostatic", "bph",
    ]),
    ("Osteoporosis / bone", [
        "osteoporos*", "osteopen*", "denosumab", "alendronic",
        "bone density", "dexa",
    ]),
    ("Diabetes", [
        "diabet*", "dapagliflozin", "empagliflozin", "insulin",
        "metformin", "gliclazide",
    ]),
    ("Allergy", [
        "allerg*", "immunotherap*", "rhinitis", "hay fever", "hayfever",
        "anaphyla*", "intolerance",
    ]),
    ("Neurology", [
        "neurolog*", "neurodegener*", "epilep*", "parkinson*",
        "dementia", "alzheim*", "multiple sclerosis",
    ]),
    ("Audiology / hearing", [
        "audiolog*", "hearing aid", "hearing", "tinnitus",
        "earwax", "ear wax", "microsuction",
    ]),
    ("Eye / optical", [
        "optometr*", "optician*", "optical", "ophthalm*", "cataract*",
        "macular", "glaucoma", "lasik", "contact lens",
        "laser eye", "eye clinic", "eye care", "eyecare", "vision", "eye", "eyes",
    ]),
    ("Private GP", [
        "private gp", "gp service*", "gp practice", "general practice",
        "private doctor", "family doctor", "doctor", "gp",
    ]),
]


# ================================================================== MATCHER
def _compile(key):
    """'foo*' -> stem match (\\bfoo).   'foo' -> whole-word match (\\bfoo\\b)."""
    k = key.lower()
    if k.endswith("*"):
        return re.compile(r"\b" + re.escape(k[:-1]))
    return re.compile(r"\b" + re.escape(k) + r"\b")


def _weight(key):
    """Specificity = length of the literal, ignoring the '*' marker."""
    return len(key[:-1] if key.endswith("*") else key)


# (niche_name, list_order, specificity, compiled_regex, original_key)
_PATTERNS = []
for _order, (_name, _keys) in enumerate(NICHES):
    for _key in _keys:
        _PATTERNS.append((_name, _order, _weight(_key), _compile(_key), _key))


def niche_match(text):
    """Return (niche, matched_key). Longest matching key wins; ties -> list order."""
    t = (text or "").lower()
    if not t.strip():
        return (None, None)
    best_name = best_key = None
    best_score = None
    for name, order, weight, rx, key in _PATTERNS:
        if rx.search(t):
            score = (weight, -order)
            if best_score is None or score > best_score:
                best_score, best_name, best_key = score, name, key
    return (best_name, best_key)


def niche_of(text):
    """Drop-in replacement for the old niche_of(). Same signature, correct results."""
    return niche_match(text)[0]


# ==================================================================== TESTS
# 75 real-world UK clinic / company names.
# Block A: adversarial - substrings that USED to trigger a false niche.
# Block B: true positives - the short keys must still fire as whole words.
TESTS = [
    # ---- A. ADVERSARIAL: must NOT be mis-classified -----------------------
    ("Skinner & Partners",            None),                        # "skin"
    ("Molesey Clinic Ltd",            None),                        # "mole"
    ("Scanlon Medical Ltd",           None),                        # "scan"
    ("Smiley Recruitment Ltd",        None),                        # "smile"
    ("Peele & Sons Ltd",              None),                        # "peel"
    ("Laserton Holdings Ltd",         None),                        # "laser"
    ("Hairston Ltd",                  None),                        # "hair"
    ("Browning Estates Ltd",          None),                        # "brow"
    ("Skintech Manufacturing Ltd",    None),                        # "skin"
    ("Lipton Foods Ltd",              None),                        # "lip"
    ("Moleculab Ltd",                 None),                        # "mole"
    ("Eyeworth Consulting Ltd",       None),                        # "eye"
    ("Peelman Ltd",                   None),                        # "peel"
    ("Fillery & Co",                  None),                        # "filler"
    ("Scanning Solutions Ltd",        None),                        # "scan"
    ("Weightman Legal Ltd",           None),                        # "weight"
    ("Boteler Ltd",                   None),                        # "botox"
    ("Dermot O'Leary Ltd",            None),                        # "dermatolog"
    ("Jointon Ltd",                   None),                        # "joint"
    ("Spinelli Ltd",                  None),                        # "spine"
    ("Mentha Ltd",                    None),                        # "mental"
    ("Sleeper Trains Ltd",            None),                        # "sleep"
    ("Doctorow Ltd",                  None),                        # "doctor"
    ("GPS Tracking Ltd",              None),                        # "gp"
    ("Vitaminas Ltd",                 None),                        # "vitamin"
    ("Hearingham Ltd",                None),                        # "hearing"
    ("Trentino Ltd",                  None),
    ("Insulind Ltd",                  None),                        # "insulin"
    ("Lashford Motors Ltd",           None),                        # "lash"
    ("Brownlow Holdings Ltd",         None),                        # "brow"

    # ---- A2. ADVERSARIAL but genuinely healthcare: right niche, not the
    #          one the substring bug would have given -----------------------
    ("Brown Dental Practice",         "Dental / orthodontics"),     # not Aesthetics
    ("Lipscomb Opticians Ltd",        "Eye / optical"),             # not Aesthetics
    ("Cosmeticare Ltd",               "Aesthetics / skin"),         # stem still fires
    ("Laser Eye Surgery London",      "Eye / optical"),             # not Aesthetics
    ("Skin Cancer Screening Centre",  "Dermatology / acne"),        # not Aesthetics/Diagnostics

    # ---- B. TRUE POSITIVES: whole-word short keys must still fire ---------
    ("The Skin Clinic",               "Aesthetics / skin"),
    ("The Brow Bar London",           "Aesthetics / skin"),
    ("Chemical Peel Studio",          "Aesthetics / skin"),
    ("Lip Filler Lounge",             "Aesthetics / skin"),
    ("Mole Check Clinic",             "Dermatology / acne"),
    ("Advanced Hair Studio",          "Hair restoration"),
    ("Dermal Filler Clinic",          "Aesthetics / skin"),
    ("The Eyebrow Studio",            "Aesthetics / skin"),
    ("Microneedling by Sarah",        "Aesthetics / skin"),
    ("Elite Botox & Aesthetics",      "Aesthetics / skin"),
    ("Harley Street Dermatology",     "Dermatology / acne"),
    ("Isotretinoin Clinic",           "Dermatology / acne"),
    ("SpaMedica Cataract Clinic",     "Eye / optical"),
    ("The Menopause Clinic",          "Menopause / HRT"),
    ("HRT Direct Ltd",                "Menopause / HRT"),
    ("Optimale Testosterone Clinic",  "Men's health / TRT"),
    ("ADHD 360",                      "ADHD"),
    ("Private ADHD Assessment Ltd",   "ADHD"),
    ("Mounjaro Weight Loss Clinic",   "Weight loss / GLP-1"),
    ("Medical Slimming Clinic",       "Weight loss / GLP-1"),
    ("Tongue Tie Clinic Bristol",     "Tongue-tie / lactation"),
    ("The Lactation Consultant Ltd",  "Tongue-tie / lactation"),
    ("Bristol Physiotherapy Clinic",  "MSK / physio"),
    ("The Chiropractic Centre",       "MSK / physio"),
    ("Priory Psychiatry Ltd",         "Mental health / psychiatry"),
    ("Anxiety UK Counselling",        "Mental health / psychiatry"),
    ("Numan Erectile Dysfunction",    "Sexual health / ED"),
    ("The Sleep Clinic",              "Sleep"),
    ("London Migraine Centre",        "Migraine"),
    ("Bladder & Bowel Clinic",        "Bladder / continence"),
    ("The Osteoporosis Clinic",       "Osteoporosis / bone"),
    ("Diabetes Care Direct",          "Diabetes"),
    ("The Allergy Clinic London",     "Allergy"),
    ("National Neurology Centre",     "Neurology"),
    ("Specsavers Audiology",          "Audiology / hearing"),
    ("Private Ultrasound Scan Ltd",   "Diagnostics / imaging"),
    ("The Fertility Partnership",     "Fertility / women's health"),
    ("Women's Health Clinic",         "Fertility / women's health"),
    ("The Private GP Practice",       "Private GP"),
    ("Invisalign Smile Studio",       "Dental / orthodontics"),
    ("IV Drip Lounge",                "Longevity / peptides / IV"),
    ("Peptide Therapy Clinic",        "Longevity / peptides / IV"),
]


def _old_niche_of(text, niches):
    """The buggy prefix-only matcher, kept so the test output can show the delta."""
    t = (text or "").lower()
    for name, keys in niches:
        for k in keys:
            k = k[:-1] if k.endswith("*") else k
            if re.search(r"\b" + re.escape(k), t):
                return name
    return None


def main():
    fails = []
    for name, expect in TESTS:
        got = niche_of(name)
        if got != expect:
            fails.append((name, expect, got))

    width = max(len(n) for n, _ in TESTS)
    for name, expect in TESTS:
        got = niche_of(name)
        ok = "PASS" if got == expect else "FAIL"
        print("{}  {:<{w}}  ->  {}".format(
            ok, name, got if got else "-", w=width))

    print("\n" + "=" * 72)
    print("{} / {} passed".format(len(TESTS) - len(fails), len(TESTS)))
    if fails:
        print("\nFAILURES:")
        for name, expect, got in fails:
            print("  {!r}: expected {!r}, got {!r}".format(name, expect, got))
    print("=" * 72)

    # Show what the OLD matcher did to the adversarial block - the regression proof.
    print("\nRegression proof - old prefix-only matcher on the adversarial names:")
    bad = 0
    for name, expect in TESTS[:35]:
        old = _old_niche_of(name, NICHES)
        new = niche_of(name)
        if old != new:
            bad += 1
            print("  {:<30} old={:<28} new={}".format(
                name, str(old), str(new)))
    print("  -> old matcher mis-classified {} of the first 35 names.".format(bad))

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
