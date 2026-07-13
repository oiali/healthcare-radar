# Radar 13 Jul 2026: no baseline yet

Week to 13 Jul 2026. Data last refreshed 2026-07-13 19:49 UTC. Baseline: none.

## What crossed a line

No baseline at least 6 days old (history holds 1 day). Nothing can be called a change yet.

## Early-stage watchlist (early tiers lit, clinics not)

Demand and founders present, capacity not yet built. This is the window in which the operators are still cheap. It is a standing list, not a weekly event.

- Dental / orthodontics: new company incorporations lit (search n/a, companies +200.0%); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- MSK / physio: new company incorporations lit (search n/a, companies +125.9%); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Bladder / continence: new company incorporations lit (search n/a, companies +100.0%); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Sexual health / ED: search interest lit (search +55.8%, companies n/a); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Men's health / TRT: search interest lit (search +44.0%, companies n/a); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Menopause / HRT: search interest lit (search +15.1%, companies n/a); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Aesthetics / skin: new company incorporations lit (search +6.7%, companies +158.9%); clinic registrations at -11.6%, below the line.

## Ignore these

Signals that look like something and are not:

- "wild" in new company incorporations shows +333.3%, but that is 3 -> 13. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.
- "oral" in new company incorporations shows +300.0%, but that is 7 -> 28. On counts this small the noise alone is about +/-38%. Ignore the percentage; the absolute number is the only thing being said.
- "primary care" in new company incorporations shows +266.7%, but that is 3 -> 11. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.
- "change" in new company incorporations shows +200.0%, but that is 3 -> 9. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.
- "occupational" in new company incorporations shows +200.0%, but that is 3 -> 9. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.

## Confidence

- Verified: the counts. Search index, Companies House incorporations and CQC registrations are read from the sources as-is.
- Inferred: the niche labels. Every row is mapped to a niche by keyword match on a company or clinic name. Names lie, and short keys collide with surnames. Treat any single-niche number as indicative.
- Assumed: that a +10% weighted 12-month growth means anything. It is a line drawn by hand, not a fitted threshold, and it has never been backtested against a niche that actually turned out to be investable.
- Not covered: Tier 4, NHS prescribing. It is fetched in your browser (OpenPrescribing blocks datacentre IPs) so it is not in the daily data file and cannot be in this digest. "Nothing crossed" does not include prescribing - open the dashboard for that.
- Also not covered: job ads. They are on the dashboard but not in the week-on-week history, so tier 3 here means CQC registrations only.
- Windows differ by tier and are not comparable: Google Trends GB, 4-week mean vs the same 4 weeks 12 months ago; Companies House, last 3 months vs the same 3 months a year ago; CQC monthly file, last 12 months vs the 12 before.
- CQC publishes monthly. A tier-3 move is a step when the new file lands, not a weekly trend.
- The volume floor is applied using this week's volumes. history.json stores the growth per niche but not the volume behind it, so a niche that was thin at the baseline and is not thin now passes the gate.

---
Dashboard: https://oiali.github.io/healthcare-radar/
