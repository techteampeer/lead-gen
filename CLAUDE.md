# Lead Gen Pipeline — Claude Code Instructions

## What This Project Does

AI-powered B2B lead generation for IT staffing. Finds companies actively hiring IT talent (software engineers, data engineers, DevOps, etc.) in NY/NJ — these are potential clients for our staffing agency.

## Who Uses This

The CEO. One person. Interactive use only — no overnight automation needed.

## How To Operate

When asked to find leads, follow this pipeline:

1. **Scrape** — Run `python run_pipeline.py` (handles Dice/Greenhouse/Lever/Ashby/Wellfound).
   - Add `--skip-browser` if Playwright is unavailable
   - Add `--skip-wellfound` to skip Wellfound discovery
   - This writes `data/companies_to_research.json` — a list of unique companies with their open roles
2. **Research** — For each company in `companies_to_research.json`, do web searches:
   - Headcount (LinkedIn)
   - Funding stage (Crunchbase / news)
   - Internal TA team presence (LinkedIn)
   Read `prompts/score.md` for the exact research steps and scoring rubric.
3. **Score** — Assign 0-100 score and urgency using the rubric in `prompts/score.md`
4. **Output** — Write `data/leads_scored.csv` (one row per role, sorted by score)
5. **Dashboard** — Run `python rebuild_dashboard.py`

Minimum viable run = at least 20 researched companies or flag as LOW YIELD.

## Slash Commands

- `/lead-gen` — Full pipeline: scan → filter → score → dashboard
- `/lead-gen scan` — Scan only, save raw results to `data/raw_jobs.csv`
- `/lead-gen score` — Re-score existing qualified_jobs.csv with current rubric
- `/lead-gen add-source <url>` — Add a new company/job board to scan
- `/lead-gen status` — Show stats from last run

## Data Files

| File | Purpose |
|------|---------|
| `data/raw_jobs.csv` | All scraped jobs (unfiltered) |
| `data/qualified_jobs.csv` | Jobs that passed filters |
| `data/leads_scored.csv` | Scored + ranked leads (feeds dashboard) |
| `data/recent_companies.json` | 30-day contacted company memory |
| `data/discovered_boards.json` | Auto-discovered Greenhouse boards |
| `config.json` | Keyword lists, company lists, tunable settings |

## Output Format

`data/leads_scored.csv` must have these columns (the dashboard depends on them):
```
source, company, job_id, title, location, description, posting_date, job_url,
discard_reason, score, urgency, job_signals_score, company_signals_score,
score_breakdown, linkedin_url, company_size, funding_stage
```

## Rules

- NEVER delete or overwrite `data/recent_companies.json` — it tracks contacted companies
- NEVER modify the existing Python files (scraper.py, filters.py, scorer.py) — they are the fallback pipeline
- Always write dates as YYYY-MM-DD
- If a source returns 0 results, warn the user (it probably changed its layout)
- Minimum viable run = at least 30 qualified leads or flag as LOW YIELD
- Deduplicate by company+title combo before scoring
- Keep `dashboard.html` compatible — same embedded JSON structure

## Job Sources (Discovery-Driven)

We do NOT depend on a hardcoded list. The pipeline DISCOVERS companies actively hiring:

1. **Dice.com** — Use as a search engine to find companies hiring IT in NY/NJ. The companies matter more than the individual listings.
2. **Wellfound** — Discover funded startups hiring engineers in the area.
3. **Greenhouse API** (JSON, no auth) — Once a company is identified, check if they have a board. Scrape ALL their IT roles.
4. **Lever API** (JSON, no auth) — Same as Greenhouse, alternative ATS.
5. **Ashby** — Same pattern, newer ATS used by startups.
6. **Any URL the CEO pastes** — Extract jobs from whatever page is given.

The `config.json` → `greenhouse_boards` list is just a seed for the first run. After that, `data/discovered_boards.json` grows automatically.

## Target Market

- **Geography:** New York, New Jersey, Remote (US) — this is the ONLY hard filter
- **Domain:** Software Engineers, Data Engineers, DevOps, ML Engineers, Platform Engineers, SREs, Cloud Engineers, Solutions Architects, Infrastructure Engineers, AI Engineers — this is the ONLY other hard filter
- **Sweet spot companies (score higher, don't exclude others):** Series B+ funded, 50-500 employees, no internal TA team, tech/fintech/biotech
- **Do NOT limit to a preset company list.** Any company hiring IT in NY/NJ is a potential client.

## Fallback

If Claude Code is unavailable or the CEO needs overnight automation, the original Python pipeline still works:
```
python scraper.py && python filters.py && python scorer.py
```
