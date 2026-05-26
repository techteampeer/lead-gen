# Scan Mode — Discovery-Driven Lead Finding

## Philosophy

We do NOT rely on a hardcoded list of companies. Our approach:
1. **Discover** — Use job aggregators (Dice, Wellfound, LinkedIn, Google) as search engines to find ANY company hiring IT talent in NY/NJ right now
2. **Expand** — For every interesting company found, check their full careers page (Greenhouse, Lever, Ashby, Workable, or company website) to find ALL their open IT roles
3. **Accumulate** — Every new company discovered gets added to `data/discovered_boards.json` so future runs start with a bigger net

The `config.json` → `greenhouse_boards` list is just a seed. The real source of leads is whatever companies are actively hiring TODAY.

## Step 1: Discovery (Cast the Wide Net)

### Dice.com — Primary discovery engine

Search for IT roles in the NY/NJ metro area. Use broad queries:

```
https://www.dice.com/jobs?q={query}&location=New+York%2C+NY&radius=30&radiusUnit=mi&page={page}&pageSize=20&filters.postedDate=THIRTY_DAYS&language=en
```

Queries (rotate through all of these):
- software+engineer, data+engineer, devops+engineer, backend+engineer
- cloud+engineer, machine+learning+engineer, platform+engineer
- site+reliability+engineer, solutions+architect, senior+engineer
- staff+engineer, principal+engineer, golang+engineer, rust+engineer
- kubernetes+engineer, infrastructure+engineer, AI+engineer

Browse 3 pages per query. **The goal is not the jobs themselves — it's the COMPANY NAMES.** Collect every unique company that's hiring IT in NY/NJ.

### Wellfound (AngelList) — Startup discovery

Browse startup jobs in the NY area. Focus on:
- Tech / SaaS / Fintech / Biotech startups
- Engineering roles
- Companies with recent funding

### Google Jobs / LinkedIn (if needed for volume)

If Dice + Wellfound aren't yielding enough unique companies, search:
- `site:greenhouse.io "new york" "software engineer"`
- `site:lever.co "new york" "engineer"`
- `site:jobs.ashbyhq.com "new york" "engineer"`

## Step 2: Expand (Go Deep on Each Company)

For every unique company name discovered, try to find their full job board:

### Greenhouse (JSON API, no auth)
```
GET https://api.greenhouse.io/v1/boards/{slug}/jobs
```
Slug generation: lowercase → remove Inc/Corp/LLC/Technologies/Software → replace spaces with hyphens, or remove spaces entirely. Try both.

### Lever
```
GET https://api.lever.co/v0/postings/{slug}?mode=json
```

### Ashby
```
Check: https://jobs.ashbyhq.com/{slug}
```

### Company website
If none of the above work, check `{company}.com/careers` or `{company}.com/jobs`

**When a board is found:** Grab ALL their IT/engineering roles (not just the one you found on Dice). A company with 5 open engineering roles is more valuable than one with 1.

**Cache results:** Update `data/discovered_boards.json`:
```json
{
  "working": ["slug1", "slug2"],
  "dead": ["slug3"],
  "lever": ["slug4"],
  "ashby": ["slug5"]
}
```

## Step 3: Extract

From each company's job board, extract every IT/engineering role located in NY/NJ/Remote:
- Job title
- Location
- Description (first 1000 chars, plain text)
- Posting date
- Job URL
- Company name

**Domain filter at extraction time:** Only grab roles that are clearly software/data/devops/cloud/ML/platform/infrastructure. Skip: marketing, sales, HR, finance, legal, design (unless it's a UX engineer).

**Geography filter at extraction time:** Only grab roles in NY, NJ, or Remote (US). Skip: SF, Austin, London, etc.

## Output

Write to `data/raw_jobs.csv`:
```
source, company, job_id, title, location, description, posting_date, job_url
```

- `source`: greenhouse | dice | wellfound | lever | ashby | custom
- `job_id`: from API, or hash of company+title+url
- `description`: first 1000 chars, plain text
- `posting_date`: YYYY-MM-DD

Deduplicate: same company + same title = keep only the first occurrence.

## Rate Limiting

- Greenhouse API: 0.5s between requests
- Lever API: 0.5s between requests
- Dice/Wellfound (browser): 1s between page loads
- Board discovery probes: 0.4s between attempts

## Success Criteria

A good run discovers:
- 30+ unique companies actively hiring IT in NY/NJ
- 150-400 raw job listings total
- At least 5 NEW companies not previously in discovered_boards.json

If volume is low, tell the CEO and suggest broadening (e.g., "Should I also look at CT and PA?" or "Should I include mid-level roles too?")
