# Radar 14 Jul 2026: no baseline yet

Week to 14 Jul 2026. Data last refreshed 2026-07-14 18:30 UTC. Baseline: none.

## What crossed a line

No baseline at least 6 days old (history holds 2 days). Nothing can be called a change yet.

## Early-stage watchlist (early tiers lit, clinics not)

Demand and founders present, capacity not yet built. This is the window in which the operators are still cheap. It is a standing list, not a weekly event.

- Dental / orthodontics: new company incorporations lit (search n/a, companies +229.4%); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- MSK / physio: new company incorporations lit (search n/a, companies +218.4%); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Sexual health / ED: search interest lit (search +55.2%, companies n/a); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Men's health / TRT: search interest lit (search +53.6%, companies n/a); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Menopause / HRT: search interest lit (search +23.7%, companies n/a); no clinic-registration reading at all - CQC returned no rows for it. That is either capacity not yet built or capacity the regulator cannot see, and the radar cannot tell you which.
- Diagnostics / imaging: search interest lit (search +17.6%, companies +156.2%); clinic registrations at -21.0%, below the line.

## Ignore these

Signals that look like something and are not:

- "primary care" in new company incorporations shows +375.8%, but that is 3 -> 13. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.
- "step" in new company incorporations shows +339.2%, but that is 3 -> 12. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.
- "advisory" in new company incorporations shows +273.3%, but that is 5 -> 17. On counts this small the noise alone is about +/-45%. Ignore the percentage; the absolute number is the only thing being said.
- "people" in new company incorporations shows +266.0%, but that is 3 -> 10. On counts this small the noise alone is about +/-58%. Ignore the percentage; the absolute number is the only thing being said.
- "adam" in new company incorporations shows +229.4%, but that is 4 -> 12. On counts this small the noise alone is about +/-50%. Ignore the percentage; the absolute number is the only thing being said.

## Confidence

- Verified: the counts. Search index, Companies House incorporations and CQC registrations are read from the sources as-is.
- Inferred: the niche labels. Every row is mapped to a niche by keyword match on a company or clinic name. Names lie, and short keys collide with surnames. Treat any single-niche number as indicative.
- Assumed: that a +10% weighted 12-month growth means anything. It is a line drawn by hand, not a fitted threshold.
- Tier 4 (NHS prescribing) now runs on the server, from NHSBSA's own data with 12 years of history, so it IS in this digest. It used to be fetched in your browser and was invisible here.
- Job ads have been removed entirely: Adzuna's terms forbid using their data in aggregation, including vacancy counts, which was exactly our use.
- Windows differ by tier and are not comparable: Google Trends GB, 4-week mean vs the same 4 weeks 12 months ago; Companies House, last 3 months vs the same 3 months a year ago; CQC monthly file, last 12 months vs the 12 before.
- CQC publishes monthly. A tier-3 move is a step when the new file lands, not a weekly trend.
- The volume floor is applied using this week's volumes. history.json stores the growth per niche but not the volume behind it, so a niche that was thin at the baseline and is not thin now passes the gate.

---
Dashboard: https://oiali.github.io/healthcare-radar/
