# UK Healthcare Niche Radar

A self-updating dashboard that ranks UK healthcare niches by how fast they're
rising, across three live sources:

- **Prescribing** — NHS items dispensed in England (OpenPrescribing, no key)
- **New incorporations** — new companies by health SIC code (Companies House, free key)
- **Job ads** — clinician job-ad volume (Adzuna, free key; trend builds over time)

Each source is ranked by 1 / 3 / 12-month growth with an "accelerating" flag.
A daily job on GitHub's servers refreshes it and publishes to a web link.

---

## Deploy (~5 minutes)

**1. Create the repo**
- Go to github.com → sign up (free) if you don't have an account.
- Click **New repository** → name it `healthcare-radar` → **Private** is fine → **Create**.

**2. Add these files**
- On the repo page: **Add file → Upload files**.
- Drag in `pull_and_build.py`, the `README.md`, and the `.github` folder
  (keep the folder structure: `.github/workflows/refresh.yml`).
- **Commit changes**.

**3. Add your API keys as Secrets**
- Repo → **Settings → Secrets and variables → Actions → New repository secret**.
- Add:
  - `CH_API_KEY` = your Companies House key
  - `ADZUNA_APP_ID` = your Adzuna app id
  - `ADZUNA_APP_KEY` = your Adzuna app key
- Prescribing needs no key, so it works even before you add these.

**4. Turn on Pages**
- Repo → **Settings → Pages** → under **Build and deployment**, set **Source = GitHub Actions**.

**5. Run it**
- Repo → **Actions** tab → **refresh-radar** → **Run workflow**.
- When it finishes (green tick), your live dashboard URL appears in
  **Settings → Pages** (looks like `https://<you>.github.io/healthcare-radar/`).
- After this it refreshes automatically every day at 06:00 UTC.

---

## Notes

- Built to run on GitHub Actions (Python 3.11, standard library only — no installs).
- A source with no key is skipped and its tab shows an "add key" note.
- Job-ad momentum needs a few daily runs to accrue history before percentages appear.
- The BNF prescribing scan and health SIC list are broad starters; any code that
  returns no data is skipped safely. Edit `SECTIONS` / `SIC` / `TERMS` in
  `pull_and_build.py` to widen or narrow coverage.
- First run is the real test — the **Actions** log prints how many rows each
  source returned and surfaces any code that needs adjusting.
