#!/usr/bin/env python3
"""
scraper.py  â€“  Lead Gen Pipeline  |  Phase 1

Scrapes IT job postings from:
  1. Dice.com    (HTML / embedded JSON)      — organic NY/NJ keyword search, 10 queries × 3 pages
  2. Otta        (GraphQL API, no auth)      — organic startup/tech roles, NY filter
  3. Greenhouse  (public JSON API, no auth)  — seed list + auto-discovered from Dice/Otta

  Discovery engine: company names from Dice/Otta are tested as Greenhouse slugs and cached
  in data/discovered_boards.json — the list grows automatically each nightly run.

Output: data/raw_jobs.csv
Log:    logs/scraper.log
"""

import csv
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

# â”€â”€ Paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

RAW_JOBS_CSV          = os.path.join(DATA_DIR, "raw_jobs.csv")
CONFIG_PATH           = os.path.join(BASE_DIR, "config.json")
DISCOVERED_BOARDS_PATH = os.path.join(DATA_DIR, "discovered_boards.json")

# â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "scraper.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    with open(CONFIG_PATH, encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except Exception as e:
    logger.error(f"Cannot load config.json: {e}")
    CONFIG = {}

TIMEOUT:  int   = CONFIG.get("request_timeout", 10)
DELAY:    float = CONFIG.get("scraper_delay_seconds", 1)
MAX_DESC: int   = CONFIG.get("max_description_chars", 1000)
MAX_PER_BOARD: int = CONFIG.get("max_jobs_per_board", 25)

CSV_COLUMNS = [
    "source", "company", "job_id", "title",
    "location", "description", "posting_date", "job_url",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}
JSON_HEADERS = {**HEADERS, "Accept": "application/json, text/plain, */*"}


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    try:
        soup = BeautifulSoup(raw, "html.parser")
        return clean_text(soup.get_text(separator=" "))
    except Exception:
        return clean_text(re.sub(r"<[^>]+>", " ", raw))


def normalize_date(date_str: str) -> str:
    """Return YYYY-MM-DD; fall back to today."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    # Handle ISO 8601 variants
    date_str = str(date_str).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(date_str[: len(fmt) + 5], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str[:10]
    return datetime.now().strftime("%Y-%m-%d")


def make_id(source: str, company: str, title: str, url: str) -> str:
    raw = f"{source}:{company.lower()}:{title.lower()}:{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:14]


# â”€â”€ Source 1: Greenhouse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def scrape_greenhouse(boards: List[str] = None) -> List[Dict[str, str]]:
    """Scrape public Greenhouse boards via their v1 JSON API."""
    if boards is None:
        boards = CONFIG.get("greenhouse_boards", [])
    jobs: List[Dict[str, str]] = []
    logger.info(f"[Greenhouse] Scraping {len(boards)} boards (max {MAX_PER_BOARD} jobs each) â€¦")

    for board in boards:
        try:
            list_url = f"https://api.greenhouse.io/v1/boards/{board}/jobs"
            resp = requests.get(list_url, headers=JSON_HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                logger.warning(f"[Greenhouse] {board}: HTTP {resp.status_code}")
                continue

            board_jobs = resp.json().get("jobs", [])[:MAX_PER_BOARD]
            count = 0

            for job in board_jobs:
                job_id = str(job.get("id", ""))
                loc_obj = job.get("location", {})
                location = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)

                # Fetch description from detail endpoint
                description = ""
                try:
                    detail_url = f"https://api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
                    dr = requests.get(detail_url, headers=JSON_HEADERS, timeout=TIMEOUT)
                    if dr.status_code == 200:
                        description = strip_html(dr.json().get("content", ""))[:MAX_DESC]
                    time.sleep(0.25)
                except Exception as de:
                    logger.warning(f"[Greenhouse] {board}/{job_id} description error: {de}")

                jobs.append({
                    "source": "greenhouse",
                    "company": board.replace("-", " ").title(),
                    "job_id": job_id,
                    "title": clean_text(job.get("title", "")),
                    "location": clean_text(location),
                    "description": description,
                    "posting_date": normalize_date(job.get("updated_at", "")),
                    "job_url": job.get("absolute_url", ""),
                })
                count += 1

            logger.info(f"[Greenhouse] {board}: {count} jobs")

        except requests.exceptions.Timeout:
            logger.warning(f"[Greenhouse] {board}: Timeout")
        except json.JSONDecodeError as e:
            logger.warning(f"[Greenhouse] {board}: JSON error â€“ {e}")
        except Exception as e:
            logger.warning(f"[Greenhouse] {board}: {e}")

        time.sleep(DELAY)

    logger.info(f"[Greenhouse] Total: {len(jobs)} jobs")
    return jobs


# ── Greenhouse Auto-Discovery ─────────────────────────────────────────────────

def _slug_candidates(company: str):
    name = company.lower().strip()
    for suffix in (" inc", " inc.", " corp", " corp.", " llc", " ltd",
                   " co.", " co", " technologies", " tech", " software",
                   " solutions", " systems", " group", " services"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    plain = re.sub(r"[^a-z0-9]", "", name)
    hyph  = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    seen = []
    for c in (plain, hyph):
        if len(c) >= 2 and c not in seen:
            seen.append(c)
    return seen


def discover_greenhouse_boards(companies):
    cache = {"working": [], "dead": []}
    boards_path = os.path.join(BASE_DIR, "data", "discovered_boards.json")
    if os.path.exists(boards_path):
        try:
            with open(boards_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
    working      = set(cache.get("working", []))
    dead         = set(cache.get("dead",    []))
    config_boards = set(CONFIG.get("greenhouse_boards", []))
    max_new      = CONFIG.get("discovery_max_per_run", 60)
    tested = 0
    logger.info(
        f"[Discovery] {len(working)} boards cached | "
        f"testing up to {max_new} new slugs from {len(companies)} companies..."
    )
    for company in companies:
        if tested >= max_new:
            break
        for slug in _slug_candidates(company):
            if slug in working or slug in dead or slug in config_boards:
                continue
            if tested >= max_new:
                break
            url = f"https://api.greenhouse.io/v1/boards/{slug}/jobs"
            try:
                r = requests.get(url, headers=JSON_HEADERS, timeout=5)
                if r.status_code == 200 and r.json().get("jobs"):
                    working.add(slug)
                    logger.info(f"[Discovery] Found new board: {slug} ({company})")
                else:
                    dead.add(slug)
            except Exception:
                dead.add(slug)
            tested += 1
            time.sleep(0.4)
    cache["working"] = sorted(working)
    cache["dead"]    = sorted(dead)
    try:
        with open(boards_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"[Discovery] Could not save cache: {e}")
    logger.info(f"[Discovery] {len(working)} total working | {tested} tested this run")
    return sorted(working)


# ── Source 2: Otta ────────────────────────────────────────────────────────────

def scrape_otta():
    """Scrape Otta via internal GraphQL API -- no auth, organic company discovery."""
    jobs = []
    GQL_URL = "https://api.otta.com/graphql"
    # Otta GraphQL 'jobs' query requires authentication -- skip
    logger.info("[Otta] jobs API requires auth, skipping")
    logger.info("[Otta] Total: 0 jobs")
    return []
def scrape_dice() -> List[Dict[str, str]]:
    """Scrape Dice.com â€“ organic keyword search across NY/NJ, no fixed company list."""
    jobs: List[Dict[str, str]] = []
    queries = [
        "software+engineer",
        "data+engineer",
        "devops+engineer",
        "backend+engineer",
        "cloud+engineer",
        "machine+learning+engineer",
        "platform+engineer",
        "site+reliability+engineer",
        "solutions+architect",
        "senior+engineer",
    ]
    max_pages: int = CONFIG.get("dice_pages", 3)
    logger.info(f"[Dice] Scraping {len(queries)} queries Ã— {max_pages} pages â€¦")

    for query in queries:
        for page_num in range(1, max_pages + 1):
            url = (
                f"https://www.dice.com/jobs?q={query}"
                f"&location=New+York%2C+NY&radius=30&radiusUnit=mi"
                f"&page={page_num}&pageSize=20&filters.postedDate=THIRTY_DAYS&language=en"
            )
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code != 200:
                    logger.warning(f"[Dice] {query} p{page_num}: HTTP {resp.status_code}")
                    break  # no point trying more pages if this one fails

                soup = BeautifulSoup(resp.text, "html.parser")
                count = 0
                # -- RSC payload (Next.js flight): contains companyName --
                _rsc_done = False
                for _rsc_script in soup.find_all("script"):
                    _rsc_text = _rsc_script.string or ""
                    if '\\"jobList\\"' not in _rsc_text and '"jobList"' not in _rsc_text:
                        continue
                    try:
                        # Unescape JS double-escaping used by Next.js RSC
                        _unesc = _rsc_text.replace('\\"', '"').replace('\\\\', '\\')
                        _marker = '"jobList":{"data":'
                        _mi = _unesc.find(_marker)
                        if _mi < 0:
                            continue
                        # Bracket-count to find the closing ] of the data array
                        _arr_start = _unesc.index('[', _mi)
                        _depth = 0
                        _arr_end = _arr_start
                        for _k, _ch in enumerate(_unesc[_arr_start:], _arr_start):
                            if _ch == '[':
                                _depth += 1
                            elif _ch == ']':
                                _depth -= 1
                                if _depth == 0:
                                    _arr_end = _k + 1
                                    break
                        _job_arr = json.loads(_unesc[_arr_start:_arr_end])
                        for _job in _job_arr:
                            if not isinstance(_job, dict):
                                continue
                            _title   = clean_text(_job.get("title") or "")
                            _company = clean_text(_job.get("companyName") or "Unknown")
                            _guid    = _job.get("guid") or _job.get("id") or ""
                            _href    = _job.get("detailsPageUrl") or (
                                f"https://www.dice.com/job-detail/{_guid}" if _guid else ""
                            )
                            _loc_obj = _job.get("jobLocation") or {}
                            _loc_val = clean_text(_loc_obj.get("displayName") or "New York, NY")
                            _posted  = _job.get("postedDate") or _job.get("modifiedDate") or ""
                            _desc    = strip_html(_job.get("summary") or "")[:MAX_DESC]
                            if _title:
                                jobs.append({
                                    "source":       "dice",
                                    "company":      _company,
                                    "job_id":       _guid or make_id("dice", _company, _title, _href),
                                    "title":        _title,
                                    "location":     _loc_val,
                                    "description":  _desc,
                                    "posting_date": normalize_date(_posted),
                                    "job_url":      _href,
                                })
                                count += 1
                        _rsc_done = True
                        break
                    except Exception:
                        continue

                # â”€â”€ Attempt 1: embedded JSON â”€â”€
                for script in soup.find_all("script", type=["application/json", "application/ld+json"]):
                    try:
                        data = json.loads(script.string or "")
                        job_list = (
                            data.get("jobs")
                            or data.get("data")
                            or data.get("results")
                            or (data.get("itemListElement") if isinstance(data, dict) else None)
                            or []
                        )
                        if not isinstance(job_list, list):
                            continue
                        for job in job_list[:20]:
                            if not isinstance(job, dict):
                                continue
                            title   = clean_text(job.get("title") or job.get("jobTitle") or "")
                            company = clean_text(job.get("employerName") or job.get("hiringOrganization", {}).get("name") or "Unknown")
                            loc_val = clean_text(job.get("location") or job.get("jobLocation", {}).get("address", {}).get("addressLocality") or "New York, NY")
                            href    = job.get("jobDetailUrl") or job.get("url") or job.get("applyUrl") or ""
                            if href and not href.startswith("http"):
                                href = f"https://www.dice.com{href}"
                            j_id = str(job.get("id") or job.get("jobId") or make_id("dice", company, title, href))
                            desc = strip_html(job.get("description") or job.get("snippet") or "")[:MAX_DESC]
                            posted = job.get("datePosted") or job.get("postedDate") or job.get("modifiedDate") or ""
                            if title:
                                jobs.append({
                                    "source": "dice",
                                    "company": company,
                                    "job_id": j_id,
                                    "title": title,
                                    "location": loc_val,
                                    "description": desc,
                                    "posting_date": normalize_date(str(posted)),
                                    "job_url": href,
                                })
                                count += 1
                    except (json.JSONDecodeError, TypeError):
                        continue

                # â”€â”€ Attempt 2: HTML card fallback â”€â”€
                if count == 0:
                    cards = (
                        soup.find_all("div", {"data-cy": "card"})
                        or soup.find_all(class_=re.compile(r"job[-_]?(card|tile)", re.I))
                        or soup.find_all("a", href=re.compile(r"/job-detail/", re.I))
                    )
                    for card in cards[:20]:
                        try:
                            if card.name == "a":
                                title   = clean_text(card.get_text())[:80]
                                href    = card.get("href", "")
                                job_url = href if href.startswith("http") else f"https://www.dice.com{href}"
                                if title and len(title) > 3:
                                    jobs.append({
                                        "source": "dice",
                                        "company": "Unknown",
                                        "job_id": make_id("dice", "unknown", title, job_url),
                                        "title": title,
                                        "location": "New York, NY",
                                        "description": "",
                                        "posting_date": datetime.now().strftime("%Y-%m-%d"),
                                        "job_url": job_url,
                                    })
                                    count += 1
                            else:
                                t_el = card.find(["h2", "h3", "h4"]) or card.find(class_=re.compile(r"title|role", re.I))
                                c_el = card.find(class_=re.compile(r"company|employer", re.I))
                                a_el = card.find("a", href=re.compile(r"job", re.I))
                                title   = clean_text(t_el.get_text()) if t_el else ""
                                company = clean_text(c_el.get_text()) if c_el else "Unknown"
                                href    = a_el["href"] if a_el else ""
                                job_url = href if href.startswith("http") else f"https://www.dice.com{href}"
                                if title and len(title) > 3:
                                    jobs.append({
                                        "source": "dice",
                                        "company": company,
                                        "job_id": make_id("dice", company, title, job_url),
                                        "title": title,
                                        "location": "New York, NY",
                                        "description": "",
                                        "posting_date": datetime.now().strftime("%Y-%m-%d"),
                                        "job_url": job_url,
                                    })
                                    count += 1
                        except Exception:
                            continue

                logger.info(f"[Dice] {query} p{page_num}: {count} jobs")
                if count == 0:
                    break  # no results on this page, skip remaining pages for this query

            except requests.exceptions.Timeout:
                logger.warning(f"[Dice] {query} p{page_num}: Timeout")
                break
            except Exception as e:
                logger.warning(f"[Dice] {query} p{page_num}: {e}")
                break

            time.sleep(DELAY)

    logger.info(f"[Dice] Total: {len(jobs)} jobs")
    return jobs


# â”€â”€ Deduplication â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def deduplicate(jobs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen_ids:    set = set()
    seen_combos: set = set()
    unique:      List[Dict[str, str]] = []
    for job in jobs:
        jid   = job.get("job_id", "")
        combo = f"{job.get('company','').lower().strip()}|{job.get('title','').lower().strip()}"
        if jid and jid in seen_ids:
            continue
        if combo in seen_combos:
            continue
        seen_ids.add(jid)
        seen_combos.add(combo)
        unique.append(job)
    return unique


# â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main() -> None:
    start = datetime.now()
    logger.info("=" * 60)
    logger.info("Lead Gen Scraper -- Starting")
    logger.info(f"Run: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    all_jobs = []

    # Phase 1: Dice -- organic NY/NJ keyword search
    logger.info("[Main] Phase 1: Dice")
    try:
        dice_jobs = scrape_dice()
        all_jobs.extend(dice_jobs)
        logger.info(f"[Dice] {len(dice_jobs)} jobs")
    except Exception as e:
        logger.error(f"[Dice] failed: {e}")
        dice_jobs = []

    # Phase 2: Otta -- organic startup/tech discovery
    logger.info("[Main] Phase 2: Otta")
    try:
        otta_jobs = scrape_otta()
        all_jobs.extend(otta_jobs)
        logger.info(f"[Otta] {len(otta_jobs)} jobs")
    except Exception as e:
        logger.error(f"[Otta] failed: {e}")
        otta_jobs = []

    # Phase 3: Auto-discover Greenhouse boards from organic companies
    organic_companies = sorted({
        j["company"] for j in (dice_jobs + otta_jobs)
        if j.get("company") and j["company"].lower() not in ("unknown", "")
    })
    logger.info(f"[Main] Phase 3: Discover Greenhouse boards ({len(organic_companies)} companies)")
    discovered = discover_greenhouse_boards(organic_companies)

    # Phase 4: Greenhouse -- seed list + all discovered boards
    seed_boards = CONFIG.get("greenhouse_boards", [])
    all_boards  = list(dict.fromkeys(seed_boards + discovered))
    logger.info(
        f"[Main] Phase 4: Greenhouse -- {len(all_boards)} boards "
        f"({len(seed_boards)} seed + {len(discovered)} discovered)"
    )
    try:
        gh_jobs = scrape_greenhouse(boards=all_boards)
        all_jobs.extend(gh_jobs)
        logger.info(f"[Greenhouse] {len(gh_jobs)} jobs")
    except Exception as e:
        logger.error(f"[Greenhouse] failed: {e}")

    # Dedup + write
    before   = len(all_jobs)
    all_jobs = deduplicate(all_jobs)
    logger.info(f"Dedup: {before} -> {len(all_jobs)} (removed {before - len(all_jobs)} dupes)")

    with open(RAW_JOBS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_jobs)

    elapsed = (datetime.now() - start).seconds
    logger.info(f"Output: {RAW_JOBS_CSV}  |  {len(all_jobs)} jobs  |  {elapsed}s elapsed")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
