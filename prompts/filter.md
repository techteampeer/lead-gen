# Filter Criteria — Discard Rules

Apply these in order. Discard at the FIRST match.

## Hard Discard (automatic)

1. **Stale posting** — Posted more than 30 days ago
2. **Wrong location** — Not in New York, New Jersey, or Remote. Keywords to match: "ny", "nyc", "new york", "manhattan", "brooklyn", "queens", "nj", "new jersey", "newark", "hoboken", "jersey city", "remote"
3. **Wrong role type** — Title contains: help desk, IT support, technical support, network admin, system admin, desktop support, field technician, IT technician, NOC engineer, break/fix
4. **No agencies clause** — Description contains: "no agencies", "no recruiters", "no staffing", "no third party", "direct applicants only", "no vendor"
5. **Generic title** — Title is just "Engineer", "Developer", "Programmer" with zero specialization
6. **Recently contacted** — Company appears in `data/recent_companies.json` with a date within the last 30 days

## Soft Discard (use judgment)

These are NOT automatic — apply common sense:

- Job sounds like an internal backfill (not new headcount) AND company is small (<20 people)
- Description implies they already have a preferred staffing vendor/MSP in place
- Role is clearly a contractor conversion (they want to hire their existing contractor permanently)
- The posting is clearly a duplicate of another posting from the same company (different job ID but identical role)

## Do NOT Discard

Even if something seems off, KEEP the job if:
- It's a senior/staff/principal role (these are high-value placements)
- Company is a known funded company (see `config.json` → `known_funded_companies`)
- Multiple openings at the same company (signals hiring push)
- Description mentions urgency ("ASAP", "immediate", "scaling fast")

## Output

For each job, add a `discard_reason` column:
- Qualified jobs: leave empty (`""`)
- Discarded jobs: `"AUTO_DISCARD: {rule_name} ({detail})"`

Write all rows (both qualified and discarded) to `data/qualified_jobs.csv`.
This preserves auditability — the CEO can see why something was discarded.
