# Lead Gen Pipeline Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken, keyword-based pipeline with a single company-centric pipeline: Python scrapes 5 sources → rollup to unique companies → Claude researches each company → intelligent scoring → quality lead list.

**Architecture:** Python handles all mechanical scraping (Playwright for JS-heavy sites, JSON APIs for ATS boards). After scraping, jobs are grouped by company and hard-filtered. Claude then researches each surviving company using web search and scores based on real signals (headcount, funding, TA team presence), writing final output to leads_scored.csv.

**Tech Stack:** Python 3, Playwright (chromium), requests, BeautifulSoup, json, csv — all already installed in .venv

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `scan_dice_browser.py` | CREATE | Playwright scraper for Dice.com — fixes "Unknown" company problem |
| `scan_lever.py` | CREATE | Lever public API scraper |
| `scan_wellfound.py` | CREATE | Wellfound HTTP scraper for funded startup discovery |
| `company_rollup.py` | CREATE | Groups raw jobs by company, applies hard filters, outputs research list |
| `run_pipeline.py` | MODIFY | Wire all scrapers + rollup, remove old scoring, hand off to Claude |
| `prompts/score.md` | MODIFY | Rewrite as Claude research + scoring guide (not keyword rubric) |
| `config.json` | MODIFY | Add `enterprise_blocklist` |
| `CLAUDE.md` | MODIFY | Update `/lead-gen` to reflect new flow |

**Never touch:** `scraper.py`, `filters.py`, `scorer.py` (fallback pipeline — CLAUDE.md rule)

---

## Task 1: scan_dice_browser.py — Playwright Dice Scraper

**Files:**
- Create: `scan_dice_browser.py`

- [ ] **Step 1: Create the file with imports and constants**

```python
"""
scan_dice_browser.py — Playwright-based Dice.com scraper.
Uses a real browser to bypass Dice's bot detection and get actual company names.
Exports: scan(headless=True) -> list[dict]
"""
import hashlib, json, os, re, time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

QUERIES = [
    "software+engineer", "data+engineer", "devops+engineer", "backend+engineer",
    "cloud+engineer", "machine+learning+engineer", "platform+engineer",
    "site+reliability+engineer", "solutions+architect", "senior+engineer",
    "staff+engineer", "AI+engineer", "infrastructure+engineer",
]

BASE_URL = (
    "https://www.dice.com/jobs?q={query}"
    "&location=New+York%2C+NY&radius=30&radiusUnit=mi"
    "&page={page}&pageSize=20&filters.postedDate=THIRTY_DAYS&language=en"
)

def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())

def _make_id(company: str, title: str) -> str:
    return hashlib.md5(f"dice:{company}:{title}".encode()).hexdigest()[:14]
```

- [ ] **Step 2: Add the API interception extractor**

```python
def _extract_from_api_response(payload: dict) -> list[dict]:
    """Parse Dice internal search API JSON response."""
    jobs = []
    data = payload
    # Dice API wraps results under different keys depending on version
    hits = (
        data.get("data", {}).get("jobs", [])
        or data.get("hits", {}).get("hits", [])
        or data.get("results", [])
        or (data if isinstance(data, list) else [])
    )
    for hit in hits:
        src = hit.get("_source", hit)
        company = _clean(src.get("hiringOrganization", {}).get("name", "") or src.get("companyName", "") or src.get("company", ""))
        title   = _clean(src.get("title", "") or src.get("positionTitle", ""))
        location = _clean(src.get("jobLocation", {}).get("displayName", "") or src.get("location", "") or "New York, NY")
        guid    = src.get("id", "") or src.get("guid", "")
        date    = (src.get("postDate", "") or src.get("postedDate", "") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
        url     = f"https://www.dice.com/job-detail/{guid}" if guid else ""
        if company and title and company.lower() != "unknown":
            jobs.append({
                "source": "dice",
                "company": company,
                "job_id": guid or _make_id(company, title),
                "title": title,
                "location": location,
                "description": _clean(src.get("jobDescription", ""))[:1000],
                "posting_date": date,
                "job_url": url,
            })
    return jobs
```

- [ ] **Step 3: Add the DOM fallback extractor**

```python
def _extract_from_dom(page) -> list[dict]:
    """Extract job cards from rendered Dice DOM."""
    jobs = []
    try:
        # Wait for at least one job card
        page.wait_for_selector("[data-cy='card-title'], .card-title, .job-title", timeout=8000)
    except PWTimeout:
        return jobs

    cards = page.query_selector_all("div[data-cy='search-result'], div.search-result-card, article.job-card")
    if not cards:
        # Try broader selector
        cards = page.query_selector_all("a[href*='/job-detail/']")

    for card in cards:
        try:
            title_el   = card.query_selector("[data-cy='card-title'], .card-title, h5, h2")
            company_el = card.query_selector("[data-cy='search-result-company-name'], .company-name, [class*='company']")
            loc_el     = card.query_selector("[data-cy='search-result-location'], .location, [class*='location']")
            link_el    = card.query_selector("a[href*='/job-detail/']") or card

            title   = _clean(title_el.inner_text()   if title_el   else "")
            company = _clean(company_el.inner_text() if company_el else "")
            location = _clean(loc_el.inner_text()    if loc_el     else "New York, NY")
            href    = link_el.get_attribute("href") or ""
            guid    = re.search(r"/job-detail/([^/?]+)", href)
            guid    = guid.group(1) if guid else ""
            url     = f"https://www.dice.com{href}" if href.startswith("/") else href

            if title and company and company.lower() != "unknown":
                jobs.append({
                    "source": "dice",
                    "company": company,
                    "job_id": guid or _make_id(company, title),
                    "title": title,
                    "location": location,
                    "description": "",
                    "posting_date": datetime.now().strftime("%Y-%m-%d"),
                    "job_url": url,
                })
        except Exception:
            continue
    return jobs
```

- [ ] **Step 4: Add the main scan() function**

```python
def scan(headless: bool = True, pages_per_query: int = 3) -> list[dict]:
    """
    Scrape Dice.com using a real browser.
    Returns list of job dicts with real company names.
    Also saves raw_jobs_dice.json and dice_companies.json.
    """
    all_jobs: list[dict] = []
    api_hits: list[dict] = []        # collected from network intercept
    companies: set[str]  = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        # Intercept Dice's internal search API responses
        def on_response(resp):
            if (
                resp.status == 200
                and "json" in resp.headers.get("content-type", "")
                and any(x in resp.url for x in ["job-search-api", "/jobs/search", "dice.com/api"])
            ):
                try:
                    api_hits.extend(_extract_from_api_response(resp.json()))
                except Exception:
                    pass

        page.on("response", on_response)

        for qi, query in enumerate(QUERIES):
            for page_num in range(1, pages_per_query + 1):
                url = BASE_URL.format(query=query, page=page_num)
                try:
                    page.goto(url, wait_until="networkidle", timeout=25000)
                    time.sleep(1.0)

                    # Prefer API-intercepted data; fall back to DOM
                    if api_hits:
                        new_jobs = api_hits[:]
                        api_hits.clear()
                    else:
                        new_jobs = _extract_from_dom(page)

                    for job in new_jobs:
                        if job["company"]:
                            companies.add(job["company"])
                    all_jobs.extend(new_jobs)

                except PWTimeout:
                    print(f"  [Dice] Timeout: {query} p{page_num}")
                except Exception as e:
                    print(f"  [Dice] Error: {query} p{page_num}: {e}")

            if (qi + 1) % 4 == 0:
                pct = round((qi + 1) / len(QUERIES) * 100)
                print(f"  [Dice] {pct}% done — {len(companies)} companies, {len(all_jobs)} jobs")

        browser.close()

    # Deduplicate by job_id
    seen, unique = set(), []
    for j in all_jobs:
        if j["job_id"] not in seen:
            seen.add(j["job_id"])
            unique.append(j)

    # Save
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "raw_jobs_dice.json"), "w") as f:
        json.dump(unique, f, indent=2)
    with open(os.path.join(DATA_DIR, "dice_companies.json"), "w") as f:
        json.dump(sorted(companies), f, indent=2)

    print(f"  [Dice] Done: {len(unique)} jobs, {len(companies)} unique companies")
    return unique


if __name__ == "__main__":
    jobs = scan(headless=False)   # headed for manual testing
    print(f"Returned {len(jobs)} jobs")
```

- [ ] **Step 5: Test by running headed (visible browser) to confirm it works**

```powershell
cd D:\Users\ysai\Documents\lead_gen
.\.venv\Scripts\python.exe scan_dice_browser.py
```

Expected: browser window opens, searches Dice, prints companies found.
If company count is 0 — DOM selectors may need updating. Check what Dice renders with `page.content()`.

- [ ] **Step 6: Run headless and verify output files**

```powershell
.\.venv\Scripts\python.exe -c "
from scan_dice_browser import scan
jobs = scan(headless=True, pages_per_query=1)
companies = set(j['company'] for j in jobs)
print('Jobs:', len(jobs))
print('Companies (first 10):', sorted(companies)[:10])
print('Unknown count:', sum(1 for j in jobs if j['company'].lower() == 'unknown'))
"
```

Expected: companies list contains real company names, Unknown count = 0.

---

## Task 2: scan_lever.py — Lever API Scraper

**Files:**
- Create: `scan_lever.py`

- [ ] **Step 1: Create the file**

```python
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
```

- [ ] **Step 2: Add the per-company fetch function**

```python
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
        desc     = (p.get("description") or p.get("descriptionPlain") or "")[:1000]
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
            "description": re.sub(r"<[^>]+>", " ", desc).strip(),
            "posting_date": date,
            "job_url": url_link,
        })
    return jobs
```

- [ ] **Step 3: Add the main scan() function**

```python
def scan(slugs: list[str] | None = None) -> list[dict]:
    """
    Scan Lever boards for given company slugs.
    If slugs is None, loads from data/dice_companies.json + config.json greenhouse_boards.
    Saves raw_jobs_lever.json. Returns list of job dicts.
    """
    if slugs is None:
        # Build slug list from discovered companies + seed list
        config_path = os.path.join(BASE_DIR, "config.json")
        with open(config_path) as f:
            config = json.load(f)
        seed_slugs = config.get("greenhouse_boards", [])   # same companies, try Lever too

        companies_path = os.path.join(DATA_DIR, "dice_companies.json")
        discovered = []
        if os.path.exists(companies_path):
            with open(companies_path) as f:
                discovered = [_slug_from_name(n) for n in json.load(f)]

        slugs = list(dict.fromkeys(seed_slugs + discovered))   # dedup, preserve order

    all_jobs: list[dict] = []
    found_boards: list[str] = []

    print(f"  [Lever] Checking {len(slugs)} slugs…")
    for i, slug in enumerate(slugs):
        company_name = slug.replace("-", " ").title()
        jobs = _fetch_lever_jobs(slug, company_name)
        if jobs:
            all_jobs.extend(jobs)
            found_boards.append(slug)
        time.sleep(0.4)
        if (i + 1) % 20 == 0:
            print(f"  [Lever] {i+1}/{len(slugs)} checked — {len(found_boards)} boards found, {len(all_jobs)} jobs")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "raw_jobs_lever.json"), "w") as f:
        json.dump(all_jobs, f, indent=2)

    print(f"  [Lever] Done: {len(all_jobs)} IT jobs from {len(found_boards)} boards")
    return all_jobs


if __name__ == "__main__":
    jobs = scan()
    print(f"Returned {len(jobs)} jobs")
```

- [ ] **Step 4: Test Lever scraper**

```powershell
.\.venv\Scripts\python.exe scan_lever.py
```

Expected: output shows boards found and job count. Check `data/raw_jobs_lever.json` has real titles and company names.

---

## Task 3: scan_wellfound.py — Wellfound Startup Discovery

**Files:**
- Create: `scan_wellfound.py`

- [ ] **Step 1: Create the file**

Wellfound's goal here is **company name discovery only** — we find funded NY/NJ startups, then Greenhouse/Lever check picks up their actual jobs.

```python
"""
scan_wellfound.py — Discover funded NY/NJ startups from Wellfound.
Goal: company names only → feeds Greenhouse + Lever discovery.
Exports: scan() -> list[str]  (company names)
"""
import json, os, re, time
import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_URLS = [
    "https://wellfound.com/role/l/software-engineer/new-york",
    "https://wellfound.com/role/l/data-engineer/new-york",
    "https://wellfound.com/role/l/devops-engineer/new-york",
    "https://wellfound.com/role/l/machine-learning-engineer/new-york",
    "https://wellfound.com/role/l/backend-engineer/new-york",
    "https://wellfound.com/role/l/software-engineer/new-jersey",
]


def _extract_companies(html: str) -> list[str]:
    """Extract company names from Wellfound search results HTML."""
    companies = []
    soup = BeautifulSoup(html, "html.parser")

    # Try structured data first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                for item in data:
                    org = item.get("hiringOrganization", {})
                    if isinstance(org, dict) and org.get("name"):
                        companies.append(org["name"].strip())
            elif isinstance(data, dict):
                org = data.get("hiringOrganization", {})
                if isinstance(org, dict) and org.get("name"):
                    companies.append(org["name"].strip())
        except Exception:
            continue

    # Fallback: look for company name patterns in rendered HTML
    if not companies:
        for tag in soup.find_all(["h2", "h3", "span", "a"], class_=re.compile(r"company|startup|org", re.I)):
            text = tag.get_text(strip=True)
            if text and 2 < len(text) < 60 and not any(c.isdigit() for c in text[:3]):
                companies.append(text)

    return list(dict.fromkeys(companies))   # dedup, preserve order


def scan() -> list[str]:
    """
    Scrape Wellfound for funded startup company names in NY/NJ.
    Appends discovered names to data/discovered_boards.json.
    Returns list of company name strings.
    """
    all_companies: list[str] = []

    for url in SEARCH_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                names = _extract_companies(r.text)
                all_companies.extend(names)
                print(f"  [Wellfound] {url.split('/')[-2:]}: {len(names)} companies")
            else:
                print(f"  [Wellfound] HTTP {r.status_code} for {url}")
        except Exception as e:
            print(f"  [Wellfound] Error {url}: {e}")
        time.sleep(1.5)

    all_companies = list(dict.fromkeys(all_companies))

    # Merge into discovered_boards.json
    boards_path = os.path.join(DATA_DIR, "discovered_boards.json")
    boards = {}
    if os.path.exists(boards_path):
        with open(boards_path) as f:
            boards = json.load(f)
    existing = set(boards.get("wellfound_companies", []))
    existing.update(all_companies)
    boards["wellfound_companies"] = sorted(existing)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(boards_path, "w") as f:
        json.dump(boards, f, indent=2)

    print(f"  [Wellfound] Done: {len(all_companies)} unique companies discovered")
    return all_companies


if __name__ == "__main__":
    companies = scan()
    print("Sample:", companies[:10])
```

- [ ] **Step 2: Test Wellfound scraper**

```powershell
.\.venv\Scripts\python.exe scan_wellfound.py
```

Expected: prints company names. If 0 companies — Wellfound may require JavaScript. That's acceptable; Dice + Greenhouse + Lever will still provide strong coverage.

---

## Task 4: company_rollup.py — Group Jobs Into Companies

**Files:**
- Create: `company_rollup.py`

- [ ] **Step 1: Create the file with normalizer and enterprise blocklist loader**

```python
"""
company_rollup.py — Groups raw jobs by company, applies hard filters.
Exports: rollup(jobs, config, recent) -> list[dict]
Each returned dict = one company with all their open IT roles.
"""
import json, os, re
from datetime import datetime

STRIP_SUFFIXES = re.compile(
    r"\b(inc\.?|corp\.?|llc\.?|ltd\.?|technologies|software|solutions|group|holdings)\b",
    re.IGNORECASE,
)

def _normalize(name: str) -> str:
    """Lowercase, strip legal suffixes, collapse whitespace."""
    n = STRIP_SUFFIXES.sub("", name.lower())
    return re.sub(r"\s+", " ", n).strip().strip(",").strip()

def _posting_age(date_str: str) -> int:
    if not date_str:
        return 999
    try:
        return (datetime.now() - datetime.strptime(date_str[:10], "%Y-%m-%d")).days
    except Exception:
        return 999
```

- [ ] **Step 2: Add the rollup() function**

```python
def rollup(
    jobs: list[dict],
    config: dict,
    recent: dict,
    max_companies: int = 60,
) -> list[dict]:
    """
    Groups jobs by company. Applies hard filters. Returns company dicts.

    Each company dict:
      company, normalized_name, open_roles (list), role_count,
      sources (set→list), latest_posting_date, slugs_to_try
    """
    enterprise_blocklist = {_normalize(n) for n in config.get("enterprise_blocklist", [])}
    disqualify_kw = [kw.lower() for kw in config.get("disqualify_keywords", [])]
    no_agency_phrases = [
        "no agencies", "no recruiters", "no staffing",
        "no third party", "direct applicants only", "no vendor",
    ]

    # Group by normalized company name
    grouped: dict[str, dict] = {}
    for job in jobs:
        company = job.get("company", "").strip()
        if not company or company.lower() == "unknown":
            continue

        norm = _normalize(company)
        if not norm:
            continue

        if norm not in grouped:
            grouped[norm] = {
                "company": company,            # display name (first seen)
                "normalized_name": norm,
                "open_roles": [],
                "sources": set(),
                "latest_posting_date": "",
            }

        g = grouped[norm]
        title = job.get("title", "")
        desc  = job.get("description", "").lower()

        # Skip disqualified titles
        if any(kw in title.lower() for kw in disqualify_kw):
            continue

        # Skip no-agency postings
        if any(phrase in desc for phrase in no_agency_phrases):
            continue

        g["open_roles"].append({
            "title": title,
            "location": job.get("location", ""),
            "url": job.get("job_url", ""),
            "posting_date": job.get("posting_date", ""),
            "description": job.get("description", ""),
        })
        g["sources"].add(job.get("source", "unknown"))

        d = job.get("posting_date", "")
        if d and (not g["latest_posting_date"] or d > g["latest_posting_date"]):
            g["latest_posting_date"] = d

    # Hard filters on companies
    results = []
    for norm, g in grouped.items():
        if not g["open_roles"]:
            continue

        # Enterprise blocklist
        if norm in enterprise_blocklist:
            continue

        # Recently contacted
        if norm in recent:
            age = _posting_age(recent[norm])
            if age <= 30:
                continue

        # Build slug candidates for Greenhouse/Lever probing
        slug = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
        g["slugs_to_try"] = [slug, slug.replace("-", "")]
        g["sources"] = sorted(g["sources"])
        g["role_count"] = len(g["open_roles"])
        results.append(g)

    # Sort: most open roles first
    results.sort(key=lambda x: -x["role_count"])
    return results[:max_companies]
```

- [ ] **Step 3: Write tests**

```python
# tests/test_rollup.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from company_rollup import rollup, _normalize

CONFIG = {
    "enterprise_blocklist": ["JPMorgan", "IBM", "Deloitte"],
    "disqualify_keywords": ["help desk", "it support"],
}

def _job(company, title, desc="", source="dice", date="2026-05-01"):
    return {"company": company, "title": title, "description": desc,
            "source": source, "job_url": "", "location": "New York, NY",
            "posting_date": date, "job_id": "x"}

def test_normalize_strips_suffixes():
    assert _normalize("Stripe, Inc.") == "stripe"
    assert _normalize("DataBricks LLC") == "databricks"

def test_groups_by_company():
    jobs = [_job("Stripe", "Backend Engineer"), _job("Stripe", "Data Engineer")]
    result = rollup(jobs, CONFIG, {})
    assert len(result) == 1
    assert result[0]["role_count"] == 2

def test_drops_unknown_company():
    jobs = [_job("Unknown", "Software Engineer")]
    assert rollup(jobs, CONFIG, {}) == []

def test_drops_enterprise():
    jobs = [_job("JPMorgan", "Software Engineer")]
    assert rollup(jobs, CONFIG, {}) == []

def test_drops_disqualified_title():
    jobs = [_job("Startup Co", "Help Desk Engineer")]
    assert rollup(jobs, CONFIG, {}) == []

def test_drops_no_agency():
    jobs = [_job("Good Co", "Software Engineer", desc="no agencies please")]
    assert rollup(jobs, CONFIG, {}) == []

def test_recently_contacted_excluded():
    jobs = [_job("Stripe", "Software Engineer")]
    recent = {"stripe": "2026-05-15"}   # 6 days ago — within 30
    assert rollup(jobs, CONFIG, recent) == []

def test_sorts_by_role_count():
    jobs = [
        _job("SmallCo", "Engineer"),
        _job("BigHirer", "Backend"), _job("BigHirer", "Frontend"), _job("BigHirer", "Data"),
    ]
    result = rollup(jobs, CONFIG, {})
    assert result[0]["company"] == "BigHirer"
```

- [ ] **Step 4: Run tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rollup.py -v
```

Expected: all 8 tests PASS.

---

## Task 5: Update config.json — Enterprise Blocklist

**Files:**
- Modify: `config.json`

- [ ] **Step 1: Add enterprise_blocklist array**

In `config.json`, add after `"known_funded_companies"`:

```json
"enterprise_blocklist": [
  "JPMorgan", "JP Morgan", "Morgan Stanley", "Goldman Sachs", "Citibank", "Citi",
  "Bank of America", "Wells Fargo", "Barclays", "Deutsche Bank", "HSBC",
  "IBM", "Accenture", "Deloitte", "PwC", "KPMG", "EY", "McKinsey",
  "Cognizant", "Infosys", "TCS", "Tata Consultancy", "Wipro", "HCL",
  "Amazon", "Microsoft", "Google", "Apple", "Meta", "Netflix",
  "Oracle", "SAP", "Salesforce", "ServiceNow",
  "Lockheed Martin", "Raytheon", "General Dynamics", "Booz Allen"
]
```

---

## Task 6: Update run_pipeline.py — Wire Everything + Company Rollup

**Files:**
- Modify: `run_pipeline.py`

- [ ] **Step 1: Replace run_pipeline.py with the new orchestration version**

The new run_pipeline.py does: scan → rollup → write companies_to_research.json → print handoff message to Claude.

```python
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
        wf_scan()   # side-effect: updates discovered_boards.json
    except Exception as e:
        print(f"  Wellfound scan failed ({e})")

# Greenhouse
gh_path = os.path.join(DATA_DIR, "raw_jobs_greenhouse.json")
if os.path.exists(gh_path):
    with open(gh_path) as f:
        gh_jobs = json.load(f)
    print(f"\n[3/5] Greenhouse: loaded {len(gh_jobs)} cached jobs")
    all_raw.extend(gh_jobs)
else:
    print("\n[3/5] Greenhouse: no cache — run discover_boards.py first")

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
```

- [ ] **Step 2: Verify the pipeline runs end-to-end**

```powershell
.\.venv\Scripts\python.exe run_pipeline.py --skip-browser --skip-wellfound
```

Expected: loads cached data, prints company count, writes `companies_to_research.json`. No crash.

---

## Task 7: Rewrite prompts/score.md — Claude Research + Scoring Guide

**Files:**
- Modify: `prompts/score.md`

- [ ] **Step 1: Replace prompts/score.md with the new research-driven prompt**

```markdown
# Lead Research + Scoring — Claude Instructions

You have a list of companies in `data/companies_to_research.json`.
Each company is actively hiring IT talent in NY/NJ.
Your job: research each company, score it 0-100, write results to `data/leads_scored.csv`.

---

## For Each Company — Research Steps

Do a web search for each company. You need 4 signals:

**1. Headcount** — search `"{company}" site:linkedin.com employees`
- Sweet spot: 50–500 employees → they have budget but no big internal TA team
- Too small (<20): no budget for agency fees
- Too large (500+): likely has full internal recruiting

**2. Funding stage** — search `"{company}" funding raised OR "series b" OR crunchbase`
- Series B+ or recently raised = they have money to pay fees (15-25% of salary)
- Bootstrapped/unknown = less reliable budget

**3. Internal TA team** — search `"{company}" "talent acquisition" OR "recruiting team" site:linkedin.com`
- If they have 2+ internal recruiters: lower score (they have capacity)
- If no TA team found: higher score (they NEED external help)

**4. Recent news** — search `"{company}" hiring OR "growing team" OR funding 2025 2026`
- Active hiring push = urgent need
- Layoffs or freeze = skip

---

## Scoring Rubric (0–100)

| Signal | Points |
|--------|--------|
| 50–500 employees | +20 |
| Series B+ funded | +20 |
| No visible internal TA team | +15 |
| 3+ open IT roles | +15 |
| NY/NJ location (not just remote) | +10 |
| Niche stack in job descriptions (K8s, Rust, ML, Go) | +10 |
| Urgency signals (ASAP, scaling, rapid growth) | +10 |

**Deductions:**
- Clear internal TA team found: −20
- No funding info + <50 employees: −10
- Only 1 generic role open: −5

---

## Urgency Assignment

- **HIGH** — score ≥ 60 AND posted within 21 days
- **MEDIUM** — score ≥ 40 OR posted within 30 days
- **LOW** — everything else

---

## Output Format

Write `data/leads_scored.csv` with these exact columns:
```
source, company, job_id, title, location, description, posting_date, job_url,
discard_reason, score, urgency, job_signals_score, company_signals_score,
score_breakdown, linkedin_url, company_size, funding_stage
```

One row per **role** (not per company) — use the roles from `open_roles` in the research JSON.
All roles from the same company get the same score, urgency, company_size, funding_stage.

`score_breakdown` example:
`Headcount_200(+20) SeriesB(+20) NoTA(+15) 4OpenRoles(+15) NY(+10) K8s(+10)`

Sort: score descending, then HIGH → MEDIUM → LOW urgency.

After writing the CSV, run: `python rebuild_dashboard.py`
```

---

## Task 8: Update CLAUDE.md — Reflect New Pipeline Flow

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "How To Operate" section in CLAUDE.md**

Replace the current pipeline description:

```markdown
## How To Operate

When asked to find leads, follow this pipeline:

1. **Scrape** — Run `python run_pipeline.py` (handles Dice/Greenhouse/Lever/Ashby/Wellfound).
   - Add `--skip-browser` if Playwright is unavailable
   - This writes `data/companies_to_research.json` — a list of unique companies
2. **Research** — For each company in `companies_to_research.json`, do web searches:
   - Headcount (LinkedIn)
   - Funding stage (Crunchbase / news)
   - Internal TA team presence (LinkedIn)
   Read `prompts/score.md` for the exact research steps and scoring rubric.
3. **Score** — Assign 0-100 score and urgency using the rubric in `prompts/score.md`
4. **Output** — Write `data/leads_scored.csv` (one row per role, sorted by score)
5. **Dashboard** — Run `python rebuild_dashboard.py`

Minimum viable run = at least 20 researched companies or flag as LOW YIELD.
```

---

## Done — Verify Full Pipeline

- [ ] **Run full pipeline end-to-end**

```powershell
.\.venv\Scripts\python.exe run_pipeline.py
```

Then manually score 3 companies using `prompts/score.md` to confirm the research flow works and output CSV matches expected columns.

```powershell
.\.venv\Scripts\python.exe rebuild_dashboard.py
```

Open `dashboard.html` in browser and confirm leads appear with scores and company data.
