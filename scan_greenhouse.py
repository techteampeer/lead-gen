"""
scan_greenhouse.py — Scrape Greenhouse ATS public API for IT jobs in NY/NJ.

Discovery flow:
  1. Load confirmed-working boards from discovered_boards.json (instant scan)
  2. Probe companies from dice_companies.json against Greenhouse API (new discovery)
  3. Cache results: new working boards → discovered_boards.json["working"]
                    dead probes     → discovered_boards.json["dead"] (skipped next run)

API: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Exports: scan() -> list[dict]
"""
import hashlib, json, os, re, time
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; lead-gen-bot/1.0)"}

TARGET_LOCS = [
    "new york", "ny", "nyc", "new jersey", "nj", "remote",
    "manhattan", "brooklyn", "queens", "hoboken", "jersey city",
    "united states", "usa", "anywhere",
]

IT_KEYWORDS = [
    "engineering", "software", "data", "infrastructure", "platform",
    "devops", "sre", "machine learning", "ml", "security", "backend",
    "frontend", "full stack", "fullstack", "cloud", "ai", "mlops",
]

DISQUALIFY = [
    "help desk", "it support", "technical support", "desktop support",
    "field technician", "noc engineer", "network admin", "system admin",
]

# Slugs whose title-casing is wrong — override display name here
SLUG_NAMES = {
    "thenewyorktimes": "The New York Times",
    "coreweave": "CoreWeave",
    "doubleverify": "DoubleVerify",
    "fanduel": "FanDuel",
    "grafanalabs": "Grafana Labs",
    "voxmedia": "Vox Media",
    "cockroachlabs": "Cockroach Labs",
    "flatironhealth": "Flatiron Health",
    "assemblyai": "AssemblyAI",
    "stabilityai": "Stability AI",
    "speechmatics": "Speechmatics",
    "treasuryprime": "Treasury Prime",
    "dvtrading": "DV Trading",
}


def _is_it_role(title: str, dept: str = "") -> bool:
    t = (title + " " + dept).lower()
    if any(d in t for d in DISQUALIFY):
        return False
    return any(kw in t for kw in IT_KEYWORDS) or "engineer" in t or "developer" in t


def _is_target_location(location: str) -> bool:
    loc = location.lower()
    return not loc or any(t in loc for t in TARGET_LOCS)


def _slug_to_name(slug: str, original: str = "") -> str:
    if original:
        return original
    return SLUG_NAMES.get(slug, slug.replace("-", " ").title())


def _slug_variants(name: str) -> list[str]:
    """Generate likely Greenhouse slug variants from a company display name."""
    s = name.lower()
    for suffix in [
        " inc.", " inc", " corp.", " corp", " llc", " ltd.", " ltd",
        " co.", " co", " technologies", " technology", " software",
        " solutions", " group", " labs", " systems", " services",
        " health", " financial", ", inc", ", llc",
    ]:
        s = s.replace(suffix, "")
    s = s.strip().strip(",").strip()
    nohyphen  = re.sub(r"[^a-z0-9]+", "",  s)
    hyphenated = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    seen = []
    for v in [nohyphen, hyphenated]:
        if v and len(v) >= 2 and v not in seen:
            seen.append(v)
    return seen


def _probe_greenhouse(slug: str) -> bool:
    """Return True if this slug has an active Greenhouse board with at least one job."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            return isinstance(data, dict) and bool(data.get("jobs"))
    except Exception:
        pass
    return False


def _fetch_greenhouse_jobs(slug: str, company_name: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        postings = data.get("jobs", []) if isinstance(data, dict) else []
    except Exception:
        return []

    jobs = []
    for p in postings:
        title = (p.get("title") or "").strip()

        loc_obj = p.get("location", {})
        location = loc_obj.get("name", "") if isinstance(loc_obj, dict) else (str(loc_obj) if loc_obj else "")

        dept_list = p.get("departments", [])
        dept = dept_list[0].get("name", "") if dept_list else ""

        job_id   = str(p.get("id", "") or hashlib.md5(f"gh:{slug}:{title}".encode()).hexdigest()[:14])
        url_link = p.get("absolute_url", "") or f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"
        desc_raw = p.get("content", "") or ""
        desc     = re.sub(r"<[^>]+>", " ", desc_raw).strip()[:1000]
        updated  = p.get("updated_at", "") or ""
        date     = updated[:10] if updated else datetime.now().strftime("%Y-%m-%d")

        if not _is_it_role(title, dept):
            continue
        if not _is_target_location(location):
            continue

        jobs.append({
            "source":       "greenhouse",
            "company":      company_name,
            "job_id":       job_id,
            "title":        title,
            "location":     location or "Remote",
            "description":  desc,
            "posting_date": date,
            "job_url":      url_link,
        })
    return jobs


def scan() -> list[dict]:
    """
    Discovery-driven Greenhouse scan.
    - Probes companies from dice_companies.json (new ones only — dead list skips repeats)
    - Scans all confirmed-working boards
    - Updates discovered_boards.json with new findings
    """
    boards_path = os.path.join(DATA_DIR, "discovered_boards.json")
    boards_data: dict = {}
    if os.path.exists(boards_path):
        with open(boards_path) as f:
            boards_data = json.load(f)

    confirmed_working: set[str] = set(boards_data.get("working", []))
    confirmed_dead:    set[str] = set(boards_data.get("dead",    []))

    # ── DISCOVERY: probe Dice companies not yet tried ──────────────────────────
    slug_original: dict[str, str] = {}  # slug → original company name from Dice
    dice_path = os.path.join(DATA_DIR, "dice_companies.json")
    if os.path.exists(dice_path):
        with open(dice_path) as f:
            dice_names: list[str] = json.load(f)
        for name in dice_names:
            for slug in _slug_variants(name):
                if slug not in confirmed_working and slug not in confirmed_dead:
                    if slug not in slug_original:
                        slug_original[slug] = name

    if slug_original:
        print(f"  [Greenhouse] Probing {len(slug_original)} new companies from Dice…")
        newly_found = 0
        for i, (slug, name) in enumerate(slug_original.items()):
            if _probe_greenhouse(slug):
                confirmed_working.add(slug)
                SLUG_NAMES[slug] = name  # remember original name
                newly_found += 1
            else:
                confirmed_dead.add(slug)
            time.sleep(0.2)
            if (i + 1) % 50 == 0:
                print(f"  [Greenhouse] Probed {i+1}/{len(slug_original)} — {newly_found} new boards found")

        boards_data["working"] = sorted(confirmed_working)
        boards_data["dead"]    = sorted(confirmed_dead)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(boards_path, "w") as f:
            json.dump(boards_data, f, indent=2)

        if newly_found:
            print(f"  [Greenhouse] +{newly_found} new boards discovered")
    else:
        print(f"  [Greenhouse] No new companies to probe (all already cached)")

    # ── SCAN: fetch jobs from all confirmed working boards ─────────────────────
    all_jobs: list[dict] = []
    found_boards: list[str] = []

    print(f"  [Greenhouse] Scanning {len(confirmed_working)} confirmed boards…")
    for i, slug in enumerate(sorted(confirmed_working)):
        company_name = _slug_to_name(slug, SLUG_NAMES.get(slug, ""))
        jobs = _fetch_greenhouse_jobs(slug, company_name)
        if jobs:
            all_jobs.extend(jobs)
            found_boards.append(slug)
        time.sleep(0.3)
        if (i + 1) % 15 == 0 or i == len(confirmed_working) - 1:
            print(f"  [Greenhouse] {i+1}/{len(confirmed_working)} scanned — {len(found_boards)} with IT jobs, {len(all_jobs)} total")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "raw_jobs_greenhouse.json"), "w") as f:
        json.dump(all_jobs, f, indent=2)

    print(f"  [Greenhouse] Done: {len(all_jobs)} IT jobs from {len(found_boards)} boards")
    return all_jobs


if __name__ == "__main__":
    jobs = scan()
    print(f"Returned {len(jobs)} jobs")
    for j in jobs[:10]:
        print(f"  {j['company']:30} | {j['title'][:50]}")
