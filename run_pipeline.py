"""
run_pipeline.py — Lead gen pipeline orchestrator.

Stages:
  1. Scrape  — Dice (Playwright), Greenhouse, Lever, Ashby, Wellfound
  2. Rollup  — group by company, apply hard filters
  3. Handoff — write companies_to_research.json, print scoring instructions for Claude

Run: python run_pipeline.py [--skip-browser] [--skip-wellfound]
"""
import csv, json, os, sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

with open(os.path.join(BASE_DIR, "config.json")) as f:
    CONFIG = json.load(f)

SKIP_BROWSER   = "--skip-browser"   in sys.argv
SKIP_WELLFOUND = "--skip-wellfound" in sys.argv

# ── 1. SCRAPE ──────────────────────────────────────────────────────────────────

all_raw: list[dict] = []

# Dice
dice_jobs: list[dict] = []
if not SKIP_BROWSER:
    try:
        from scan_dice_browser import scan as dice_scan
        print("\n[1/5] Dice.com (Playwright)…")
        dice_jobs = dice_scan(headless=True)
    except Exception as e:
        print(f"  Dice browser scan failed ({e}) — trying cached data")
dice_path = os.path.join(DATA_DIR, "raw_jobs_dice.json")
if not dice_jobs and os.path.exists(dice_path):
    with open(dice_path) as f:
        dice_jobs = json.load(f)
    print(f"  Loaded {len(dice_jobs)} cached Dice jobs")
all_raw.extend(dice_jobs)

# Wellfound (discovery only — adds company names, no job rows)
if not SKIP_WELLFOUND:
    try:
        from scan_wellfound import scan as wf_scan
        print("\n[2/5] Wellfound…")
        wf_scan()
    except Exception as e:
        print(f"  Wellfound scan failed ({e})")

# Greenhouse
print("\n[3/5] Greenhouse…")
gh_jobs: list[dict] = []
try:
    from scan_greenhouse import scan as gh_scan
    gh_jobs = gh_scan()
except Exception as e:
    print(f"  Greenhouse scan failed ({e}) — trying cached data")
    gh_path = os.path.join(DATA_DIR, "raw_jobs_greenhouse.json")
    if os.path.exists(gh_path):
        with open(gh_path) as f:
            gh_jobs = json.load(f)
        print(f"  Loaded {len(gh_jobs)} cached Greenhouse jobs")
all_raw.extend(gh_jobs)

# Lever
print("\n[4/5] Lever…")
try:
    from scan_lever import scan as lever_scan
    lever_jobs = lever_scan()
    all_raw.extend(lever_jobs)
except Exception as e:
    print(f"  Lever scan failed ({e})")
    lever_path = os.path.join(DATA_DIR, "raw_jobs_lever.json")
    if os.path.exists(lever_path):
        with open(lever_path) as f:
            lj = json.load(f)
        all_raw.extend(lj)
        print(f"  Loaded {len(lj)} cached Lever jobs")

# Ashby
print("\n[5/5] Ashby…")
try:
    from scan_ashby import scan as ashby_scan
    ashby_jobs = ashby_scan()
    all_raw.extend(ashby_jobs)
except Exception as e:
    ashby_path = os.path.join(DATA_DIR, "raw_jobs_ashby.json")
    if os.path.exists(ashby_path):
        with open(ashby_path) as f:
            aj = json.load(f)
        all_raw.extend(aj)
        print(f"  Loaded {len(aj)} cached Ashby jobs")

print(f"\nTotal raw jobs: {len(all_raw)}")

# Write raw_jobs.csv
RAW_COLS = ["source", "company", "job_id", "title", "location", "description", "posting_date", "job_url"]
with open(os.path.join(DATA_DIR, "raw_jobs.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=RAW_COLS, extrasaction="ignore")
    w.writeheader(); w.writerows(all_raw)

# ── 2. ROLLUP ─────────────────────────────────────────────────────────────────

from company_rollup import rollup

recent: dict = {}
recent_path = os.path.join(DATA_DIR, "recent_companies.json")
if os.path.exists(recent_path):
    with open(recent_path) as f:
        recent = json.load(f)

print("\nRolling up to unique companies…")
companies = rollup(all_raw, CONFIG, recent, max_companies=50)
print(f"  {len(companies)} unique companies after hard filters")

# ── 3. WRITE RESEARCH LIST + HANDOFF ─────────────────────────────────────────

research_path = os.path.join(DATA_DIR, "companies_to_research.json")
with open(research_path, "w") as f:
    json.dump(companies, f, indent=2, default=list)

print(f"\nWritten: data/companies_to_research.json ({len(companies)} companies)")
print("\n" + "="*60)
print("SCRAPING COMPLETE — READY FOR CLAUDE SCORING")
print("="*60)
print(f"\n{len(companies)} companies need research + scoring.")
print("Claude: read prompts/score.md, then research and score")
print("each company in data/companies_to_research.json.")
print("Write results to data/leads_scored.csv.")
print("Then run: python rebuild_dashboard.py")
