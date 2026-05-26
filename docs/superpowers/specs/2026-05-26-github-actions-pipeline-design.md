# GitHub Actions Pipeline + GitHub Pages Dashboard — Design Spec

**Date:** 2026-05-26  
**Status:** Approved  
**Repo:** https://github.com/techteampeer/lead-gen (public)

---

## Goal

Host the complete IT staffing lead gen pipeline on GitHub — free, zero infrastructure to manage. The CEO clicks a button in the GitHub Actions UI, watches live progress logs, and the dashboard auto-updates at a public URL when done.

---

## Architecture

```
GitHub repo: techteampeer/lead-gen (public)
│
├── .github/workflows/pipeline.yml   ← "Run workflow" button in Actions tab
├── dashboard.html                    ← rebuilt each run, served by Pages
├── index.html                        ← redirects to dashboard.html
├── requirements.txt                  ← playwright, beautifulsoup4, requests
└── data/                             ← committed back after every run
    ├── recent_companies.json         ← contacted-company memory (must persist)
    ├── discovered_boards.json        ← auto-discovered ATS boards
    ├── leads_scored.csv              ← latest scored leads
    └── qualified_jobs.csv            ← qualified jobs from last run
```

---

## Components

### 1. GitHub Actions Workflow (`.github/workflows/pipeline.yml`)

**Trigger:** `workflow_dispatch` — manual "Run workflow" button in the Actions tab. No scheduled runs (CEO controls when it runs).

**Runner:** `ubuntu-latest` (free, includes 14 GB disk, 7 GB RAM — sufficient for Playwright/Chromium).

**Steps:**
1. `actions/checkout@v4` — full clone with history (needed for data file persistence)
2. `actions/setup-python@v5` with Python 3.11
3. `pip install -r requirements.txt`
4. `playwright install chromium --with-deps` — installs Chromium + system deps
5. `python run_pipeline.py` — scrape all sources (Dice/Greenhouse/Lever/Ashby/Wellfound)
6. `python rebuild_dashboard.py` — score + build dashboard.html
7. Git commit & push — commits `data/` and `dashboard.html` back to `main`
8. GitHub Pages auto-redeploys on push (no separate deploy step needed)

**Permissions required:**
- `contents: write` — to commit results back to the repo

**Error handling:**
- Each scraper already has try/except fallback to cached data
- If `run_pipeline.py` exits non-zero, the workflow fails visibly in the UI
- The commit step uses `git diff --staged --quiet || git commit` — skips commit if nothing changed (idempotent)

**Optional input:**
- `skip_browser` (boolean, default: false) — passes `--skip-browser` to `run_pipeline.py` for faster runs when Playwright is not needed

### 2. `requirements.txt` (new file)

```
playwright
beautifulsoup4
requests
```

All other imports (`csv`, `json`, `os`, `re`, `logging`, `datetime`, etc.) are Python standard library — no install needed.

### 3. `index.html` (new file)

Single-line meta-refresh redirect from `techteampeer.github.io/lead-gen/` to `dashboard.html`. Lets the CEO bookmark the root URL.

```html
<!DOCTYPE html>
<meta http-equiv="refresh" content="0; url=dashboard.html">
```

### 4. `.gitignore` updates

Remove these two lines (so pipeline results are committed back):
```
data/qualified_jobs.csv
data/leads_scored.csv
```

Keep ignoring:
- `data/raw_jobs.csv` — intermediate file, not needed
- `data/raw_jobs_*.json` — intermediate files (already ignored by pattern or not listed — verify)
- `.env` — secrets, never commit

### 5. GitHub Pages setup (manual one-time step)

In repo Settings → Pages:
- **Source:** Deploy from branch
- **Branch:** `main`
- **Folder:** `/` (root)

Dashboard URL: `https://techteampeer.github.io/lead-gen/dashboard.html`  
Root URL: `https://techteampeer.github.io/lead-gen/` (redirects via index.html)

---

## Data Persistence Strategy

GitHub Actions runners are ephemeral — disk is wiped after each run. Persistence works by committing data files back to the repo at the end of each run.

| File | Committed? | Why |
|------|-----------|-----|
| `data/recent_companies.json` | ✅ Yes | Critical — tracks contacted companies (30-day memory) |
| `data/discovered_boards.json` | ✅ Yes | Grows over time — ATS board discovery |
| `data/leads_scored.csv` | ✅ Yes | Latest results — feeds dashboard |
| `data/qualified_jobs.csv` | ✅ Yes | Useful for re-scoring runs |
| `data/companies_to_research.json` | ✅ Yes | Already tracked |
| `data/dice_companies.json` | ✅ Yes | Cached Dice results |
| `data/raw_jobs_*.json` | ✅ Yes | Cached source data (already in repo) |
| `data/raw_jobs.csv` | ❌ No | Intermediate, stays gitignored |
| `.env` | ❌ No | Secrets, never commit |

---

## User Flow (post-deploy)

1. Visit `https://github.com/techteampeer/lead-gen/actions`
2. Click **"Run Lead Gen Pipeline"** workflow → **"Run workflow"** button
3. Watch live logs: Dice scraping → Greenhouse → Lever → Ashby → Scoring → Dashboard
4. When complete: visit `https://techteampeer.github.io/lead-gen/` for fresh leads

---

## What We're NOT Doing

- No scheduled/automatic runs (CEO controls timing per CLAUDE.md)
- No database (Git is the persistence layer)
- No authentication on dashboard (public URL — data is public job postings)
- No custom domain (github.io subdomain is fine)
- No Docker (GitHub's Ubuntu runner has everything we need)

---

## Files Changed Summary

| File | Action |
|------|--------|
| `.github/workflows/pipeline.yml` | Create |
| `requirements.txt` | Create |
| `index.html` | Create |
| `.gitignore` | Update (remove 2 lines) |

---

## Free Tier Limits

| Resource | Limit | Expected Usage |
|----------|-------|----------------|
| Actions minutes | Unlimited (public repo) | ~15 min/run |
| GitHub Pages bandwidth | 100 GB/month | ~negligible (1 user) |
| Repo storage | 5 GB soft limit | Well under |
