"""
scan_lever.py — Scrape Lever ATS public API for IT jobs in NY/NJ.
Lever API: GET https://api.lever.co/v0/postings/{slug}?mode=json
Exports: scan(slugs: list[str]) -> list[dict]
"""
import hashlib, json, os, re, time
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; lead-gen-bot/1.0)"}

TARGET_LOCS = ["new york", "ny", "nyc", "new jersey", "nj", "remote", "manhattan", "brooklyn"]

IT_TEAMS = [
    "engineering", "software", "data", "infrastructure", "platform",
    "devops", "sre", "machine learning", "ml", "security", "backend",
    "frontend", "full stack", "cloud", "ai",
]

DISQUALIFY = [
    "help desk", "it support", "technical support", "desktop support",
    "field technician", "noc engineer", "network admin", "system admin",
]

def _is_it_role(title: str, team: str) -> bool:
    t = (title + " " + team).lower()
    if any(d in t for d in DISQUALIFY):
        return False
    return any(kw in t for kw in IT_TEAMS) or "engineer" in t or "developer" in t

def _is_target_location(location: str) -> bool:
    loc = location.lower()
    return not loc or any(t in loc for t in TARGET_LOCS)

def _slug_from_name(name: str) -> str:
    s = name.lower()
    for suffix in [" inc", " corp", " llc", " ltd", " technologies", " software", " solutions"]:
        s = s.replace(suffix, "")
    return re.sub(r"[^a-z0-9]+", "-", s.strip()).strip("-")

def _fetch_lever_jobs(slug: str, company_name: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        postings = r.json()
        if not isinstance(postings, list):
            return []
    except Exception:
        return []

    jobs = []
    for p in postings:
        title    = (p.get("text") or "").strip()
        team     = (p.get("categories", {}).get("team") or "")
        location = (p.get("categories", {}).get("location") or "")
        job_id   = p.get("id") or hashlib.md5(f"lever:{slug}:{title}".encode()).hexdigest()[:14]
        url_link = p.get("hostedUrl") or f"https://jobs.lever.co/{slug}/{job_id}"
        desc_raw = p.get("description") or p.get("descriptionPlain") or ""
        desc     = re.sub(r"<[^>]+>", " ", desc_raw).strip()[:1000]
        created  = p.get("createdAt")
        if created:
            date = datetime.fromtimestamp(created / 1000).strftime("%Y-%m-%d")
        else:
            date = datetime.now().strftime("%Y-%m-%d")

        if not _is_it_role(title, team):
            continue
        if not _is_target_location(location):
            continue

        jobs.append({
            "source": "lever",
            "company": company_name,
            "job_id": job_id,
            "title": title,
            "location": location or "Remote",
            "description": desc,
            "posting_date": date,
            "job_url": url_link,
        })
    return jobs

def scan(slugs: list[str] | None = None) -> list[dict]:
    """
    Scan Lever boards for given company slugs.
    If slugs is None, discovers from dice_companies.json + confirmed lever boards.
    Saves raw_jobs_lever.json. Returns list of job dicts.
    """
    slug_to_name: dict[str, str] = {}

    if slugs is None:
        # Boards confirmed working from previous discovery runs
        boards_path = os.path.join(DATA_DIR, "discovered_boards.json")
        if os.path.exists(boards_path):
            with open(boards_path) as f:
                boards_data = json.load(f)
            for s in boards_data.get("lever", []):
                slug_to_name[s] = s.replace("-", " ").title()

        # Discover from Dice companies
        companies_path = os.path.join(DATA_DIR, "dice_companies.json")
        if os.path.exists(companies_path):
            with open(companies_path) as f:
                for name in json.load(f):
                    slug = _slug_from_name(name)
                    if slug and slug not in slug_to_name:
                        slug_to_name[slug] = name   # preserve original casing

        slugs = list(slug_to_name.keys())
    else:
        # If slugs provided directly, fall back to title-casing
        slug_to_name = {s: s.replace("-", " ").title() for s in slugs}

    all_jobs: list[dict] = []
    found_boards: list[str] = []

    print(f"  [Lever] Checking {len(slugs)} slugs…")
    for i, slug in enumerate(slugs):
        company_name = slug_to_name.get(slug, slug.replace("-", " ").title())
        jobs = _fetch_lever_jobs(slug, company_name)
        if jobs:
            all_jobs.extend(jobs)
            found_boards.append(slug)
        time.sleep(0.4)
        if (i + 1) % 20 == 0 or i == len(slugs) - 1:
            print(f"  [Lever] {i+1}/{len(slugs)} checked — {len(found_boards)} boards found, {len(all_jobs)} jobs")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "raw_jobs_lever.json"), "w") as f:
        json.dump(all_jobs, f, indent=2)

    print(f"  [Lever] Done: {len(all_jobs)} IT jobs from {len(found_boards)} boards")
    return all_jobs


if __name__ == "__main__":
    jobs = scan()
    print(f"Returned {len(jobs)} jobs")
