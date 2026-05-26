"""Probe Lever + additional Greenhouse boards for NY/NJ tech companies."""
import requests, json, time, re, os
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
           'Accept': 'application/json'}
TIMEOUT = 10

# Companies known to be hiring in NY/NJ tech scene - not in our seed list
NY_TECH_COMPANIES = [
    # Fintech
    "plaid", "ramp", "brex", "block", "coinbase", "gemini", "blockchain",
    "betterment", "wealthfront", "sofi", "chime", "current", "monzo",
    "mercury", "column", "lithic", "unit", "moov", "increase", "treasury-prime",
    # AI/ML
    "openai", "anthropic", "cohere", "huggingface", "stability-ai",
    "runway", "midjourney", "jasper-ai", "copy-ai", "writer",
    "grammarly", "deepgram", "assembly-ai", "speechmatics",
    # Dev tools / Infra
    "snyk", "hashicorp", "temporal", "pulumi", "fly-io", "render",
    "supabase", "planetscale", "neon", "cockroach-labs", "timescale",
    "grafana-labs", "honeycomb", "lightstep", "chronosphere",
    "clickhouse", "materialize", "dbt-labs", "fivetran", "airbyte",
    "prefect", "dagster", "modal", "anyscale", "weights-and-biases",
    # NYC startups
    "justworks", "ramp", "flatiron-health", "ro-health", "cityblock-health",
    "oscar-health", "capsule", "spring-health", "talkiatry",
    "noom", "peloton", "etsy", "squarespace", "tumblr",
    "meetup", "kickstarter", "foursquare", "buzzfeed",
    "vice", "vox-media", "the-new-york-times", "bloomberg",
    # Enterprise/B2B
    "dataiku", "alteryx", "thoughtspot", "sisense", "mode-analytics",
    "amplitude", "heap", "fullstory", "contentsquare",
    "sailpoint", "cyberark", "crowdstrike", "sentinelone",
    "zscaler", "cloudflare", "fastly", "akamai",
]

# Also try hyphenated/no-hyphen variants
def slug_variants(name):
    variants = [name]
    if '-' in name:
        variants.append(name.replace('-', ''))
    else:
        # Try adding hyphens at common boundaries
        pass
    return variants

TARGET_LOCS = ['new york', 'ny', 'nyc', 'manhattan', 'brooklyn', 'queens',
               'new jersey', 'nj', 'newark', 'hoboken', 'jersey city', 'remote']
IT_KEYWORDS_LOWER = [
    'engineer', 'developer', 'architect', 'devops', 'sre', 'data sci',
    'machine learning', 'software', 'platform', 'infrastructure', 'cloud',
    'backend', 'frontend', 'full stack', 'fullstack', 'security eng',
]

def is_it_role(title):
    t = title.lower()
    return any(kw in t for kw in IT_KEYWORDS_LOWER)

def is_target_location(loc):
    l = loc.lower()
    return any(t in l for t in TARGET_LOCS)

def strip_html(raw):
    if not raw:
        return ''
    try:
        return re.sub(r'\s+', ' ', BeautifulSoup(raw, 'html.parser').get_text(separator=' ')).strip()
    except:
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', raw)).strip()

# Load existing discovered boards
disc_path = 'data/discovered_boards.json'
if os.path.exists(disc_path):
    with open(disc_path) as f:
        discovered = json.load(f)
else:
    discovered = {"working": [], "dead": [], "lever": [], "ashby": []}

working_gh = set(discovered.get("working", []))
dead_gh = set(discovered.get("dead", []))
lever_working = set(discovered.get("lever", []))
lever_dead = set(discovered.get("lever_dead", []))

all_jobs = []
companies_with_jobs = {}

print(f"Probing {len(NY_TECH_COMPANIES)} companies for Greenhouse + Lever boards...")
print(f"Already known: {len(working_gh)} GH working, {len(dead_gh)} GH dead, {len(lever_working)} Lever")
print()

for i, slug_base in enumerate(NY_TECH_COMPANIES):
    if (i + 1) % 20 == 0:
        print(f"  Progress: {i+1}/{len(NY_TECH_COMPANIES)} | Found: {len(all_jobs)} jobs from {len(companies_with_jobs)} companies")

    for slug in slug_variants(slug_base):
        # --- TRY GREENHOUSE ---
        if slug not in working_gh and slug not in dead_gh:
            try:
                url = f"https://api.greenhouse.io/v1/boards/{slug}/jobs"
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if r.status_code == 200:
                    jobs = r.json().get("jobs", [])
                    if jobs:
                        working_gh.add(slug)
                        # Filter for NY/NJ IT roles
                        count = 0
                        for job in jobs[:30]:
                            title = job.get("title", "")
                            loc_obj = job.get("location", {})
                            location = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)
                            if is_it_role(title) and is_target_location(location):
                                job_id = str(job.get("id", ""))
                                # Get description
                                desc = ""
                                try:
                                    dr = requests.get(f"https://api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}",
                                                     headers=HEADERS, timeout=TIMEOUT)
                                    if dr.status_code == 200:
                                        desc = strip_html(dr.json().get("content", ""))[:1000]
                                    time.sleep(0.25)
                                except:
                                    pass
                                all_jobs.append({
                                    "source": "greenhouse",
                                    "company": slug.replace('-', ' ').title(),
                                    "job_id": job_id,
                                    "title": title.strip(),
                                    "location": location.strip(),
                                    "description": desc,
                                    "posting_date": job.get("updated_at", "")[:10] if job.get("updated_at") else "",
                                    "job_url": job.get("absolute_url", ""),
                                })
                                count += 1
                                if count >= 25:
                                    break
                        if count > 0:
                            companies_with_jobs[slug] = count
                            print(f"  [GH] {slug}: {count} IT roles in NY/NJ")
                    else:
                        dead_gh.add(slug)
                else:
                    dead_gh.add(slug)
            except:
                dead_gh.add(slug)
            time.sleep(0.4)

        # --- TRY LEVER ---
        if slug not in lever_working and slug not in lever_dead:
            try:
                url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if r.status_code == 200:
                    postings = r.json()
                    if isinstance(postings, list) and postings:
                        lever_working.add(slug)
                        count = 0
                        for posting in postings[:30]:
                            title = posting.get("text", "")
                            categories = posting.get("categories", {})
                            location = categories.get("location", "") or categories.get("allLocations", [""])[0] if categories.get("allLocations") else ""
                            if is_it_role(title) and is_target_location(str(location)):
                                desc_plain = ""
                                desc_html = posting.get("descriptionPlain", "") or ""
                                desc_plain = desc_html[:1000]
                                all_jobs.append({
                                    "source": "lever",
                                    "company": slug.replace('-', ' ').title(),
                                    "job_id": posting.get("id", ""),
                                    "title": title.strip(),
                                    "location": str(location).strip(),
                                    "description": desc_plain,
                                    "posting_date": "",  # Lever doesn't always expose dates
                                    "job_url": posting.get("hostedUrl", "") or posting.get("applyUrl", ""),
                                })
                                count += 1
                                if count >= 25:
                                    break
                        if count > 0:
                            companies_with_jobs[slug] = companies_with_jobs.get(slug, 0) + count
                            print(f"  [LV] {slug}: {count} IT roles in NY/NJ")
                    else:
                        lever_dead.add(slug)
                else:
                    lever_dead.add(slug)
            except:
                lever_dead.add(slug)
            time.sleep(0.4)

# Save discovered boards
discovered["working"] = sorted(working_gh)
discovered["dead"] = sorted(dead_gh)
discovered["lever"] = sorted(lever_working)
discovered["lever_dead"] = sorted(lever_dead)
with open(disc_path, 'w') as f:
    json.dump(discovered, f, indent=2)

# Save new jobs
with open('data/raw_jobs_expanded.json', 'w') as f:
    json.dump(all_jobs, f, indent=2)

print(f"\n{'='*50}")
print(f"DISCOVERY COMPLETE")
print(f"{'='*50}")
print(f"New jobs found: {len(all_jobs)}")
print(f"Companies with NY/NJ IT roles: {len(companies_with_jobs)}")
print(f"Greenhouse boards discovered: {len(working_gh)} working, {len(dead_gh)} dead")
print(f"Lever boards discovered: {len(lever_working)} working")
print(f"\nCompanies found:")
for co, cnt in sorted(companies_with_jobs.items(), key=lambda x: -x[1]):
    print(f"  {co:25} {cnt} roles")
