#!/usr/bin/env python3
"""
filters.py  –  Lead Gen Pipeline  |  Phase 2

Reads data/raw_jobs.csv, applies 6 auto-discard filters and a 30-day
company dedup check, then writes data/qualified_jobs.csv (all rows,
with a discard_reason column filled in for discarded jobs).

Also updates data/recent_companies.json with today's seen companies.

Output: data/qualified_jobs.csv
        data/recent_companies.json
Log:    logs/filters.log
"""

import csv
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

RAW_JOBS_CSV       = os.path.join(DATA_DIR, "raw_jobs.csv")
QUALIFIED_JOBS_CSV = os.path.join(DATA_DIR, "qualified_jobs.csv")
RECENT_COMPANIES   = os.path.join(DATA_DIR, "recent_companies.json")
CONFIG_PATH        = os.path.join(BASE_DIR, "config.json")

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "filters.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
try:
    with open(CONFIG_PATH, encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except Exception as e:
    logger.error(f"Cannot load config.json: {e}")
    CONFIG = {}

TARGET_LOCATIONS: List[str]    = [loc.lower() for loc in CONFIG.get("target_locations", [])]
DISQUALIFY_KW:    List[str]    = [kw.lower()  for kw  in CONFIG.get("disqualify_keywords", [])]

# Phrases that mean "no agencies" in a job description
NO_AGENCY_PHRASES = [
    "no agencies", "no recruiters", "no staffing", "no third party",
    "no third-party", "agency submissions", "direct applicants only",
    "no agency calls", "no vendor",
]

# Patterns that match overly generic job titles (full-string match)
GENERIC_TITLE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^engineer$",
        r"^software engineer$",
        r"^developer$",
        r"^programmer$",
        r"^it engineer$",
        r"^engineer i+$",      # Engineer I, II, III
        r"^engineer \d+$",
    ]
]

# ── Column schema ─────────────────────────────────────────────────────────────
INPUT_COLS  = ["source", "company", "job_id", "title", "location", "description", "posting_date", "job_url"]
OUTPUT_COLS = INPUT_COLS + ["discard_reason"]


# ── Recent-companies persistence ──────────────────────────────────────────────

def load_recent_companies() -> Dict[str, str]:
    """Load {company_lower: 'YYYY-MM-DD'} from disk."""
    if not os.path.exists(RECENT_COMPANIES):
        return {}
    try:
        with open(RECENT_COMPANIES, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load recent_companies.json: {e}")
        return {}


def save_recent_companies(recent: Dict[str, str]) -> None:
    """Prune entries older than 30 days and persist to disk."""
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in recent.items() if v >= cutoff}
    try:
        with open(RECENT_COMPANIES, "w", encoding="utf-8") as f:
            json.dump(pruned, f, indent=2)
        logger.info(f"Saved recent_companies.json ({len(pruned)} entries after pruning)")
    except IOError as e:
        logger.warning(f"Could not save recent_companies.json: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def posting_age_days(posting_date: str) -> int:
    if not posting_date:
        return 999
    try:
        posted = datetime.strptime(posting_date[:10], "%Y-%m-%d")
        return (datetime.now() - posted).days
    except ValueError:
        return 999


# ── Filter logic ──────────────────────────────────────────────────────────────

def check_filters(
    job: Dict[str, str],
    recent: Dict[str, str],
) -> Tuple[bool, str]:
    """
    Apply all 6 filters in priority order.
    Returns (qualified: bool, discard_reason: str).
    discard_reason is '' when qualified, 'AUTO_DISCARD: ...' when not.
    """
    title_l       = job.get("title", "").lower()
    location_l    = job.get("location", "").lower()
    description_l = job.get("description", "").lower()
    company_l     = job.get("company", "").lower().strip()
    posting_date  = job.get("posting_date", "")

    # ── Filter 1: Posting age > 90 days ──────────────────────────────────────
    age = posting_age_days(posting_date)
    if age > 90:
        return False, f"AUTO_DISCARD: posting_age_over_90_days ({age} days)"

    # ── Filter 2: Location not in target ─────────────────────────────────────
    if location_l:
        if not any(target in location_l for target in TARGET_LOCATIONS):
            return False, f"AUTO_DISCARD: location_not_target ({job.get('location', '')!r})"

    # ── Filter 3: Disqualifying title keyword ────────────────────────────────
    for kw in DISQUALIFY_KW:
        if kw in title_l:
            return False, f"AUTO_DISCARD: title_keyword ({kw!r})"

    # ── Filter 4: "No agencies / recruiters / staffing" in description ───────
    for phrase in NO_AGENCY_PHRASES:
        if phrase in description_l:
            return False, "AUTO_DISCARD: no_agencies_clause"

    # ── Filter 5: Generic title (no specialisation) ──────────────────────────
    title_stripped = title_l.strip()
    for pattern in GENERIC_TITLE_PATTERNS:
        if pattern.match(title_stripped):
            return False, f"AUTO_DISCARD: generic_title ({job.get('title', '')!r})"

    # ── Filter 6: Company contacted within last 30 days ──────────────────────
    if not CONFIG.get("disable_recent_check", False):
        if company_l and company_l in recent:
            last_seen = recent[company_l]
            days_since = posting_age_days(last_seen)
            if days_since <= 30:
                return False, f"AUTO_DISCARD: recently_contacted ({last_seen})"

    return True, ""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 60)
    logger.info("Lead Gen Filters — Starting")
    logger.info("=" * 60)

    if not os.path.exists(RAW_JOBS_CSV):
        logger.error(f"Input not found: {RAW_JOBS_CSV}  (run scraper.py first)")
        return

    # Load raw jobs
    try:
        with open(RAW_JOBS_CSV, encoding="utf-8") as f:
            raw_jobs: List[Dict[str, str]] = list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Failed to read {RAW_JOBS_CSV}: {e}")
        return

    logger.info(f"Loaded {len(raw_jobs)} raw jobs")

    # Load companies contacted in PREVIOUS runs only
    recent_prev = load_recent_companies()
    logger.info(f"Loaded {len(recent_prev)} recent companies (30-day memory)")

    # Apply filters
    output_rows:        List[Dict[str, str]] = []
    qualified:          List[Dict[str, str]] = []
    discard_tallies:    Dict[str, int]       = {}
    seen_this_run:      set                  = set()   # one job per company per run

    for job in raw_jobs:
        ok, reason = check_filters(job, recent_prev)

        # Within-run dedup: keep only the first qualifying job per company
        if ok:
            company_l = job.get("company", "").lower().strip()
            if company_l and company_l in seen_this_run:
                ok = False
                reason = f"AUTO_DISCARD: duplicate_company_this_run ({job.get('company','')})"
            elif company_l:
                seen_this_run.add(company_l)

        row = {col: job.get(col, "") for col in INPUT_COLS}
        row["discard_reason"] = reason
        output_rows.append(row)

        if ok:
            qualified.append(job)
        else:
            # Bucket by filter type (the word after "AUTO_DISCARD: ")
            key = reason.split(":")[1].strip().split("(")[0].strip() if ":" in reason else "unknown"
            discard_tallies[key] = discard_tallies.get(key, 0) + 1

    # Update 30-day memory with all companies seen in this run
    today = datetime.now().strftime("%Y-%m-%d")
    recent_updated = dict(recent_prev)
    for company_l in seen_this_run:
        recent_updated[company_l] = today

    # Write qualified_jobs.csv (all rows, discard_reason column filled)
    with open(QUALIFIED_JOBS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(output_rows)

    save_recent_companies(recent_updated)

    # ── Console + log summary ─────────────────────────────────────────────────
    discarded = len(raw_jobs) - len(qualified)
    sep = "─" * 60
    logger.info(sep)
    logger.info(f"SUMMARY: {len(raw_jobs)} raw → {len(qualified)} qualified → {discarded} discarded")
    for reason, cnt in sorted(discard_tallies.items(), key=lambda x: -x[1]):
        logger.info(f"  ├── {reason}: {cnt}")
    logger.info(f"Output: {QUALIFIED_JOBS_CSV}")
    logger.info("=" * 60)

    print(f"\n{'='*55}")
    print(f"  Filters complete")
    print(f"  {len(raw_jobs):>4} raw jobs")
    print(f"  {len(qualified):>4} qualified  ✓")
    print(f"  {discarded:>4} discarded  ✗")
    for reason, cnt in sorted(discard_tallies.items(), key=lambda x: -x[1]):
        print(f"        └ {reason}: {cnt}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
