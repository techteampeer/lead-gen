# IT Staffing Lead Gen Pipeline

AI-powered B2B lead generation for IT staffing. Finds companies actively hiring software engineers, data engineers, DevOps, and ML engineers in NY/NJ — your potential staffing clients.

**Live dashboard →** https://techteampeer.github.io/lead-gen/

---

## Quick Start

### Run in the cloud (no setup)
1. Go to [GitHub Actions](https://github.com/techteampeer/lead-gen/actions)
2. Click **"Run Lead Gen Pipeline"** → **"Run workflow"**
3. Watch live logs → dashboard updates automatically

### Run locally on Mac
See **[SETUP.md](SETUP.md)** for the full step-by-step guide.

```bash
git clone https://github.com/techteampeer/lead-gen.git
cd lead-gen
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium
python run_pipeline.py && python rebuild_dashboard.py
python -m http.server 8765   # → open http://localhost:8765/dashboard.html
```

---

## How It Works

```
Dice.com (Playwright)  ─┐
Wellfound              ─┤
Greenhouse API         ─┼─→  run_pipeline.py  →  data/companies_to_research.json
Lever API              ─┤
Ashby API              ─┘
                                    ↓
                          rebuild_dashboard.py
                                    ↓
                             dashboard.html  →  GitHub Pages
```

1. **Scrape** — discovers companies actively hiring IT talent in NY/NJ
2. **Filter** — removes staffing firms, non-IT roles, already-contacted companies
3. **Score** — ranks 0-100 based on job signals + company signals
4. **Dashboard** — self-contained HTML, sortable/filterable by score and urgency

---

## Scoring (0-100)

| Signal | Points |
|--------|--------|
| Senior/Staff title | +15 |
| Niche stack (K8s, ML, Go, Rust…) | +12 |
| 3+ open IT roles at company | +15 |
| Urgency language in posting | +8 |
| Posted 14-60 days ago | +10 |
| Series B+ funded | +15 |
| 50-500 employees | +10 |
| NY/NJ location | +8 |
| No internal TA team | +7 |
| Tech/fintech/biotech industry | +5 |

**Urgency:** HIGH = score ≥ 70 · MEDIUM = 40-69 · LOW = < 40

---

## Target Market

- **Geography:** New York, New Jersey, Remote (US)
- **Roles:** Software Engineers, Data Engineers, DevOps, ML Engineers, Platform Engineers, SREs, Cloud Engineers, AI Engineers, Solutions Architects
- **Sweet spot:** Series B+ · 50-500 employees · no internal TA team · tech/fintech/biotech

---

## Key Files

| File | Purpose |
|------|---------|
| `run_pipeline.py` | Main entry point — runs all scrapers |
| `rebuild_dashboard.py` | Rebuilds dashboard.html from scored data |
| `config.json` | Keywords, company lists, tunable settings |
| `dashboard.html` | Auto-generated sales dashboard |
| `data/recent_companies.json` | 30-day contacted-company memory ⚠️ never delete |
| `.github/workflows/pipeline.yml` | GitHub Actions cloud workflow |

---

## Data Files

| File | Contents |
|------|---------|
| `data/companies_to_research.json` | Unique companies with open roles (pipeline output) |
| `data/leads_scored.csv` | Scored + ranked leads (feeds dashboard) |
| `data/qualified_jobs.csv` | Jobs that passed all filters |
| `data/discovered_boards.json` | Auto-discovered Greenhouse/Lever/Ashby boards |
| `data/recent_companies.json` | Companies contacted in last 30 days |
