# Local Setup Guide — Mac (VS Code / Cursor)

Get the pipeline running on your Mac in under 10 minutes.

---

## What You Need First

| Tool | Check if installed | Install if missing |
|------|-------------------|-------------------|
| **Git** | `git --version` | Comes with Xcode tools — run `git --version` and follow the prompt |
| **Python 3.11+** | `python3 --version` | [python.org/downloads](https://www.python.org/downloads/) |
| **VS Code or Cursor** | Open the app | [code.visualstudio.com](https://code.visualstudio.com) · [cursor.com](https://cursor.com) |

---

## Step 1 — Clone the Repo

Open Terminal and run:

```bash
git clone https://github.com/techteampeer/lead-gen.git
cd lead-gen
```

Then open the folder in your editor:

```bash
# VS Code
code .

# Cursor
cursor .
```

---

## Step 2 — Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your terminal prompt will show `(.venv)` — that means it's active. ✅

> **Every time you open a new terminal**, run `source .venv/bin/activate` again before running any Python commands.

---

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` downloads the headless browser used to scrape Dice.com (~150 MB, one-time).

---

## Step 4 — Set Up Your `.env` File

The pipeline uses some environment variables. Create a `.env` file in the project root:

```bash
cp .env.example .env   # if the example file exists
# or just create it:
touch .env
```

Open `.env` in your editor and fill in any API keys needed (ask the team if unsure what goes here).

> ℹ️ `.env` is gitignored — it never gets pushed to GitHub.

---

## Step 5 — Run the Pipeline

```bash
python run_pipeline.py
```

This runs all 5 scrapers (Dice, Greenhouse, Lever, Ashby, Wellfound) and writes results to `data/companies_to_research.json`.

**Options:**

| Flag | What it does |
|------|-------------|
| *(none)* | Full run including Playwright/Dice browser scraping |
| `--skip-browser` | Skip Dice (faster, uses cached Dice data) |
| `--skip-wellfound` | Skip Wellfound discovery |

```bash
# Faster run (uses cached Dice data)
python run_pipeline.py --skip-browser

# Skip both browser-based scrapers
python run_pipeline.py --skip-browser --skip-wellfound
```

Expected output:
```
[1/5] Dice.com (Playwright)…   ← takes ~2-3 min
[2/5] Wellfound…
[3/5] Greenhouse boards…
[4/5] Lever boards…
[5/5] Ashby boards…
✓ 47 companies written to data/companies_to_research.json
```

---

## Step 6 — Score + Rebuild Dashboard

```bash
python rebuild_dashboard.py
```

This reads `data/leads_scored.csv` and rebuilds `dashboard.html`.

---

## Step 7 — Launch the Dashboard

```bash
python -m http.server 8765
```

Then open your browser and go to:

```
http://localhost:8765/dashboard.html
```

You should see the **IT Staffing Lead Dashboard** with scored and ranked companies.

> Press `Ctrl+C` in Terminal to stop the server when done.

---

## Full Run (all steps combined)

```bash
# Activate env (if not already active)
source .venv/bin/activate

# Run pipeline → score → launch
python run_pipeline.py && python rebuild_dashboard.py && python -m http.server 8765
```

---

## Running in VS Code / Cursor

### Recommended extensions
- **Python** (ms-python.python) — syntax, linting, venv detection
- **Pylance** — type hints and autocomplete

### Select the virtual environment
1. Open Command Palette → `Cmd+Shift+P`
2. Type **"Python: Select Interpreter"**
3. Choose `.venv` (the one inside the project folder)

### Run from the integrated terminal
`Ctrl+`` ` opens the terminal inside VS Code/Cursor. All the commands above work there exactly the same way.

---

## Project Structure (quick reference)

```
lead-gen/
├── run_pipeline.py        ← main entry point — runs all scrapers
├── rebuild_dashboard.py   ← rebuilds dashboard.html from scored data
├── scorer.py              ← scores companies 0-100
├── filters.py             ← applies hard filters
├── scan_dice_browser.py   ← Playwright scraper for Dice.com
├── scan_greenhouse.py     ← Greenhouse ATS API
├── scan_lever.py          ← Lever ATS API
├── scan_ashby.py          ← Ashby ATS API
├── scan_wellfound.py      ← Wellfound startup discovery
├── config.json            ← keywords, company lists, settings
├── dashboard.html         ← auto-generated — open in browser
├── requirements.txt       ← Python dependencies
├── .env                   ← API keys (never committed)
└── data/
    ├── companies_to_research.json  ← pipeline output
    ├── leads_scored.csv            ← scored + ranked leads
    ├── recent_companies.json       ← 30-day contacted memory ⚠️ don't delete
    └── discovered_boards.json      ← auto-discovered ATS boards
```

---

## Troubleshooting

**`playwright: command not found`**
→ Make sure your venv is active: `source .venv/bin/activate`

**`ModuleNotFoundError: No module named 'playwright'`**
→ Run `pip install -r requirements.txt` inside the activated venv

**`playwright install` hangs or fails**
→ Try `playwright install chromium --with-deps`

**Dice scraper returns 0 results**
→ Dice may have changed its layout. Run with `--skip-browser` and report to the team.

**`data/leads_scored.csv` not found**
→ Run `python run_pipeline.py` first before `rebuild_dashboard.py`

**Dashboard shows old data**
→ Re-run `python rebuild_dashboard.py` after the pipeline finishes

---

## Cloud Alternative (no setup needed)

If you don't want to run locally, the pipeline runs in the cloud:

1. Go to → https://github.com/techteampeer/lead-gen/actions
2. Click **"Run Lead Gen Pipeline"** → **"Run workflow"**
3. Watch live logs — dashboard updates automatically at:
   **https://techteampeer.github.io/lead-gen/**
