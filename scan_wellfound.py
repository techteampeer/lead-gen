"""
scan_wellfound.py — Discover funded NY/NJ startups from Wellfound using Playwright.
Goal: company names only → feeds Greenhouse + Lever discovery.
Exports: scan() -> list[str]  (company names)
"""
import json, os, re, time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SEARCH_URLS = [
    "https://wellfound.com/role/l/software-engineer/new-york",
    "https://wellfound.com/role/l/data-engineer/new-york",
    "https://wellfound.com/role/l/devops-engineer/new-york",
    "https://wellfound.com/role/l/machine-learning-engineer/new-york",
    "https://wellfound.com/role/l/backend-engineer/new-york",
    "https://wellfound.com/role/l/software-engineer/new-jersey",
]


def _extract_companies(page) -> list[str]:
    """Extract company names from a rendered Wellfound page."""
    companies = []

    # Try structured JSON-LD data
    for script in page.query_selector_all("script[type='application/ld+json']"):
        try:
            data = json.loads(script.inner_text() or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                org = item.get("hiringOrganization", {})
                if isinstance(org, dict) and org.get("name"):
                    companies.append(org["name"].strip())
        except Exception:
            continue

    # Fallback: rendered company name elements
    if not companies:
        for sel in ["[class*='company'] h2", "[class*='startup-link']", "[data-test='startup-name']",
                    "h2[class*='name']", "a[href*='/company/'] span"]:
            els = page.query_selector_all(sel)
            for el in els:
                text = (el.inner_text() or "").strip()
                if text and 2 < len(text) < 80:
                    companies.append(text)
            if companies:
                break

    return list(dict.fromkeys(companies))


def scan() -> list[str]:
    """
    Scrape Wellfound for funded startup company names in NY/NJ.
    Uses Playwright to bypass 403 blocking.
    Appends discovered names to data/discovered_boards.json.
    Returns list of company name strings.
    Note: Wellfound now requires login for full listings.
    If login wall detected, returns empty list with a clear warning.
    """
    all_companies: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = ctx.new_page()

        for url in SEARCH_URLS:
            try:
                page.goto(url, wait_until="load", timeout=30000)
                time.sleep(4)  # Wait for JS hydration
                html = page.content()
                if len(html) < 5000:
                    print(f"  [Wellfound] Requires login (page only {len(html)} bytes) — skipping")
                    break
                names = _extract_companies(page)
                all_companies.extend(names)
                label = "/".join(url.split("/")[-2:])
                print(f"  [Wellfound] {label}: {len(names)} companies")
            except PWTimeout:
                print(f"  [Wellfound] Timeout: {url}")
            except Exception as e:
                print(f"  [Wellfound] Error {url}: {e}")
            time.sleep(1.5)

        browser.close()

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
