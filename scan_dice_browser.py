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


def _extract_from_api_response(payload: dict) -> list[dict]:
    """Parse Dice internal search API JSON response."""
    jobs = []
    data = payload
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


def _extract_from_dom(page) -> list[dict]:
    """Extract job cards from rendered Dice DOM using current data-testid selectors."""
    jobs = []
    try:
        page.wait_for_selector("[data-testid='job-card']", timeout=8000)
    except PWTimeout:
        return jobs

    cards = page.query_selector_all("[data-testid='job-card']")

    for card in cards:
        try:
            # Title link
            title_el = card.query_selector("[data-testid='job-search-job-detail-link']")
            title    = _clean(title_el.inner_text() if title_el else "")

            # GUID from the invisible full-card link
            link_el  = card.query_selector("[data-testid='job-search-job-card-link']")
            href     = (link_el.get_attribute("href") if link_el else "") or ""
            if not href and title_el:
                href = title_el.get_attribute("href") or ""
            guid     = re.search(r"/job-detail/([^/?]+)", href)
            guid     = guid.group(1) if guid else ""
            url      = href if href.startswith("http") else f"https://www.dice.com{href}"

            # Company: first anchor/element that isn't the title or save button
            company  = ""
            for el in card.query_selector_all("a, [class*='company'], [class*='employer']"):
                text = _clean(el.inner_text())
                if text and text != title and len(text) < 80 and text.lower() not in ("apply now", "save job", ""):
                    company = text
                    break

            # Location: look for location text
            loc_el   = card.query_selector("[data-testid='job-search-job-location'], [class*='location'], [class*='Location']")
            location = _clean(loc_el.inner_text() if loc_el else "New York, NY")
            if not location or location == title:
                location = "New York, NY"

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


def scan(headless: bool = True, pages_per_query: int = 3) -> list[dict]:
    """
    Scrape Dice.com using a real browser.
    Returns list of job dicts with real company names.
    Also saves raw_jobs_dice.json and dice_companies.json.
    """
    all_jobs: list[dict] = []
    api_hits: list[dict] = []
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

        try:
            for qi, query in enumerate(QUERIES):
                for page_num in range(1, pages_per_query + 1):
                    url = BASE_URL.format(query=query, page=page_num)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(1.0)

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
                        api_hits.clear()
                        print(f"  [Dice] Timeout: {query} p{page_num}")
                    except Exception as e:
                        print(f"  [Dice] Error: {query} p{page_num}: {e}")

                if (qi + 1) % 4 == 0 or qi == len(QUERIES) - 1:
                    pct = round((qi + 1) / len(QUERIES) * 100)
                    print(f"  [Dice] {pct}% done — {len(companies)} companies, {len(all_jobs)} jobs")
        finally:
            browser.close()

    seen, unique = set(), []
    for j in all_jobs:
        if j["job_id"] not in seen:
            seen.add(j["job_id"])
            unique.append(j)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "raw_jobs_dice.json"), "w") as f:
        json.dump(unique, f, indent=2)
    with open(os.path.join(DATA_DIR, "dice_companies.json"), "w") as f:
        json.dump(sorted(companies), f, indent=2)

    print(f"  [Dice] Done: {len(unique)} jobs, {len(companies)} unique companies")
    return unique


if __name__ == "__main__":
    jobs = scan(headless=False)
    print(f"Returned {len(jobs)} jobs")
