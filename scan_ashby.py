"""
scan_ashby.py — Scan Ashby ATS boards for IT jobs at funded NY/NJ startups.

Ashby is a modern ATS popular with Series A-C startups (Ramp, Modal, Notion, Linear, etc.)
The API is public, JSON, no authentication required.

Outputs:
  data/raw_jobs_ashby.json  — list of job dicts (same schema as other sources)

Run standalone:
  python scan_ashby.py [--quick]

Or import and call scan() from run_pipeline.py.
"""

import json
import os
import re
import hashlib
import logging
import time
from datetime import datetime
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
JOBS_OUT = os.path.join(DATA_DIR, "raw_jobs_ashby.json")

TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# ── Bootstrap seed ────────────────────────────────────────────────────────────
# Probed once on first run → results cached in discovered_boards.json["ashby"]
# After that, discovery comes from dice_companies.json + the cache.
_ASHBY_SEED = [
    # Confirmed Ashby boards (fintech / NYC strong)
    "ramp", "modal", "notion", "linear", "arc",
    "brex", "mercury", "column", "lithic", "stripe",
    # AI / ML
    "runway", "cohere", "character", "mistral", "perplexity",
    "together-ai", "together", "groq", "sambanova", "cerebras",
    "hugging-face", "scale-ai", "scale", "weights-biases",
    # Dev tools / infra
    "temporal", "prefect", "dagster", "airflow", "dbt-labs",
    "fivetran", "airbyte", "stitch-data",
    "neon", "supabase", "planetscale", "turso",
    "fly-io", "render", "railway",
    "honeycomb", "lightstep", "chronosphere", "opentelemetry",
    "clickhouse", "materialize", "timescale", "questdb",
    "pulumi", "env0", "spacelift", "atlantis",
    # NYC / NJ startups
    "justworks", "justworks-hr", "ro", "hims-hers", "cityblock",
    "spring-health", "headway", "alma", "cerebral", "brightside",
    "flatiron-health", "tempus", "color",
    "capsule", "truepill",
    "noom", "calibrate", "found",
    # Media / creative
    "teachable", "kajabi", "circle", "beehiiv",
    "substack", "ghost",
    # B2B SaaS
    "ashby", "rippling", "deel", "remote", "remote-com",
    "lattice", "leapsome", "culture-amp",
    "hex", "mode", "observable", "sigma",
    "retool", "airplane", "superblocks",
    "merge-dev", "merge", "apideck",
    "resend", "postmark", "sendgrid",
    "clerk", "stytch", "auth0",
    "posthog", "june", "june-so",
    # Finance / trading
    "two-sigma", "citadel", "jane-street", "hudson-river",
    "iex", "robinhood", "betterment", "wealthfront",
    "alpaca", "alpaca-markets", "polygon-io",
    # E-commerce / marketplace
    "faire", "ankorstore", "wholesale",
    "shipbob", "flexport",
    # Security
    "snyk", "socket-dev", "socket",
    "chainguard", "sigstore",
    "semgrep", "r2c",
    "wiz", "lacework", "orca-security",
    # Other NY-area companies
    "squarespace", "etsy", "foursquare",
    "kickstarter", "meetup",
    "bloomberg-beta", "betaworks",
    "the-new-york-times", "nyt",
    "vox-media", "buzzfeed",
]

BOARDS_PATH = os.path.join(BASE_DIR, "data", "discovered_boards.json")


def _slug_variants(name: str) -> list[str]:
    """Generate likely Ashby slug variants from a company display name."""
    s = name.lower()
    for suffix in [
        " inc.", " inc", " corp.", " corp", " llc", " ltd.", " ltd",
        " co.", " co", " technologies", " technology", " software",
        " solutions", " group", " labs", " systems", " services",
        " health", " financial", ", inc", ", llc",
    ]:
        s = s.replace(suffix, "")
    s = s.strip().strip(",").strip()
    nohyphen   = re.sub(r"[^a-z0-9]+", "",  s)
    hyphenated = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    seen = []
    for v in [hyphenated, nohyphen]:  # Ashby prefers hyphenated
        if v and len(v) >= 2 and v not in seen:
            seen.append(v)
    return seen# ── Filters ───────────────────────────────────────────────────────────────────
NY_NJ_TERMS = [
    "new york", "ny,", "ny ", "nyc", "manhattan", "brooklyn", "queens",
    "bronx", "hoboken", "jersey city", "newark", "new jersey", ", nj",
    "remote", "us remote", "united states",
]

IT_KEYWORDS = [
    "engineer", "developer", "devops", "sre", "reliability",
    "data scientist", "data engineer", "ml", "machine learning",
    "software", "platform", "infrastructure", "cloud", "backend",
    "frontend", "full-stack", "fullstack", "full stack", "security eng",
    "solutions architect", "architect", "golang", "python", "rust",
    "kubernetes", "k8s", "terraform", "aws", "gcp", "azure",
    "ai engineer", "llm", "generative",
]


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())


def make_job_id(company: str, title: str, ashby_id: str = "") -> str:
    if ashby_id:
        return f"ashby-{ashby_id[:16]}"
    return "ashby-" + hashlib.md5(f"{company}|{title}".encode()).hexdigest()[:12]


def is_it_role(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in IT_KEYWORDS)


def is_ny_nj(location: str) -> bool:
    loc = location.lower()
    return any(term in loc for term in NY_NJ_TERMS)


def fetch_board(slug: str) -> list[dict]:
    """Fetch all jobs from an Ashby board. Returns [] on any error."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            logger.debug(f"  {slug}: HTTP {r.status_code}")
            return []
        data = r.json()
        return data.get("jobs", [])
    except Exception as e:
        logger.debug(f"  {slug}: {e}")
        return []


def parse_job(raw: dict, company: str, job_url_base: str) -> dict | None:
    """Convert an Ashby job dict to our standard schema."""
    title = clean(raw.get("title", ""))
    if not title or not is_it_role(title):
        return None

    # Location — Ashby stores it in various formats
    loc_data = raw.get("location") or raw.get("locationName") or ""
    if isinstance(loc_data, dict):
        loc = clean(loc_data.get("locationStr") or loc_data.get("name") or "")
    else:
        loc = clean(str(loc_data))

    if not loc:
        # Check department location or isRemote
        if raw.get("isRemote"):
            loc = "Remote"

    if not loc:
        loc = "Unknown"

    # Only keep NY/NJ/Remote
    if not is_ny_nj(loc):
        return None

    ashby_id = str(raw.get("id", ""))
    job_url = raw.get("jobUrl") or raw.get("applyUrl") or f"{job_url_base}/{ashby_id}"

    desc_raw = raw.get("descriptionPlain") or raw.get("description") or ""
    desc = clean(re.sub(r"<[^>]+>", " ", desc_raw))[:500]

    posted = raw.get("publishedAt") or raw.get("createdAt") or TODAY
    if len(posted) > 10:
        posted = posted[:10]

    return {
        "source":       "ashby",
        "company":      company,
        "job_id":       make_job_id(company, title, ashby_id),
        "title":        title,
        "location":     loc,
        "description":  desc,
        "posting_date": posted,
        "job_url":      job_url,
    }


def get_company_name(slug: str, raw_jobs: list) -> str:
    """Try to get real company name from job data, fallback to prettified slug."""
    # Ashby sometimes includes company name in job metadata
    for job in raw_jobs[:3]:
        team = job.get("team") or {}
        if isinstance(team, dict) and team.get("name"):
            pass  # team name, not company
        dept = job.get("department") or {}

    # Fallback: prettify the slug
    return slug.replace("-", " ").title()


# ── Main scan ─────────────────────────────────────────────────────────────────
def scan(boards: list[str] | None = None, quick: bool = False) -> list[dict]:
    """
    Discovery-driven Ashby scan.
    - Probes _ASHBY_SEED + dice_companies.json (new slugs only — dead list skips repeats)
    - Scans all confirmed-working boards
    - Updates discovered_boards.json with new findings
    """
    if boards:
        # Direct override — used for testing only
        board_list = boards[:20] if quick else boards
        return _scan_boards(board_list)

    # Load cache
    boards_data: dict = {}
    if os.path.exists(BOARDS_PATH):
        with open(BOARDS_PATH) as f:
            boards_data = json.load(f)

    confirmed_working: set[str] = set(boards_data.get("ashby", []))
    confirmed_dead:    set[str] = set(boards_data.get("ashby_dead", []))

    # Candidates = seed + Dice companies not yet tried
    candidates: list[str] = []
    candidate_names: dict[str, str] = {}  # slug → original name

    for slug in _ASHBY_SEED:
        if slug not in confirmed_working and slug not in confirmed_dead:
            candidates.append(slug)

    dice_path = os.path.join(DATA_DIR, "dice_companies.json")
    if os.path.exists(dice_path):
        with open(dice_path) as f:
            for name in json.load(f):
                for slug in _slug_variants(name):
                    if slug not in confirmed_working and slug not in confirmed_dead and slug not in candidate_names:
                        candidates.append(slug)
                        candidate_names[slug] = name

    if candidates:
        logger.info(f"  [Ashby] Probing {len(candidates)} new candidates…")
        newly_found = 0
        for i, slug in enumerate(candidates):
            raw = fetch_board(slug)
            if raw:
                confirmed_working.add(slug)
                newly_found += 1
            else:
                confirmed_dead.add(slug)
            time.sleep(0.2)
            if (i + 1) % 50 == 0:
                logger.info(f"  [Ashby] Probed {i+1}/{len(candidates)} — {newly_found} new boards")

        boards_data["ashby"]      = sorted(confirmed_working)
        boards_data["ashby_dead"] = sorted(confirmed_dead)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(BOARDS_PATH, "w") as f:
            json.dump(boards_data, f, indent=2)

        if newly_found:
            logger.info(f"  [Ashby] +{newly_found} new boards discovered")
    else:
        logger.info(f"  [Ashby] No new candidates to probe (all cached)")

    board_list = sorted(confirmed_working)
    if quick:
        board_list = board_list[:20]

    return _scan_boards(board_list)


def _scan_boards(board_list: list[str]) -> list[dict]:
    """Fetch and filter jobs from a confirmed list of Ashby slugs."""
    all_jobs: list[dict] = []
    seen_ids: set = set()
    found_boards: int = 0
    total_raw: int = 0

    logger.info(f"Scanning {len(board_list)} Ashby boards…")

    for i, slug in enumerate(board_list):
        raw_jobs = fetch_board(slug)
        if not raw_jobs:
            continue

        found_boards += 1
        total_raw += len(raw_jobs)

        company = get_company_name(slug, raw_jobs)
        job_url_base = f"https://jobs.ashbyhq.com/{slug}"

        board_hits = 0
        for raw in raw_jobs:
            job = parse_job(raw, company, job_url_base)
            if job is None:
                continue
            jid = job["job_id"]
            if jid in seen_ids:
                continue
            seen_ids.add(jid)
            all_jobs.append(job)
            board_hits += 1

        if board_hits:
            logger.info(f"  [{i+1}/{len(board_list)}] {slug}: {board_hits} IT jobs in NY/NJ (of {len(raw_jobs)} total)")

        # Gentle pacing
        time.sleep(0.3)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(JOBS_OUT, "w", encoding="utf-8") as fh:
        json.dump(all_jobs, fh, indent=2)

    logger.info(
        f"\nAshby scan complete: {found_boards} active boards | "
        f"{total_raw} raw jobs | {len(all_jobs)} IT jobs in NY/NJ"
    )
    if len(all_jobs) == 0:
        logger.warning("⚠  ZERO Ashby jobs — board list may need updating or network issue")

    return all_jobs


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scan Ashby ATS boards for IT leads")
    parser.add_argument("--quick", action="store_true", help="Scan first 20 boards only")
    args = parser.parse_args()

    jobs = scan(quick=args.quick)
    print(f"\nDone. {len(jobs)} jobs written to {JOBS_OUT}")

    if jobs:
        print("\nSample (first 10):")
        for j in jobs[:10]:
            print(f"  {j['company']:<25} {j['title'][:45]:<45} {j['location']}")
