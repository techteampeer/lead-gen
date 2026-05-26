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
