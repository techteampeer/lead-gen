# GitHub Actions + Pages Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the lead gen pipeline to GitHub so the CEO can click "Run workflow" in GitHub Actions, watch live progress, and see a fresh dashboard at `techteampeer.github.io/lead-gen`.

**Architecture:** GitHub Actions runs the full Python + Playwright pipeline on Ubuntu, commits results back to `main`, and GitHub Pages serves `dashboard.html` automatically on every push.

**Tech Stack:** GitHub Actions (ubuntu-latest), Python 3.11, Playwright/Chromium, GitHub Pages (static HTML)

---

## Files To Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `.github/workflows/pipeline.yml` | **Create** | The "Run Pipeline" workflow |
| `requirements.txt` | **Create** | Python deps for the runner |
| `index.html` | **Create** | Root URL redirect to dashboard |
| `.gitignore` | **Modify** | Allow data CSVs to be committed |

---

## Task 1: Update .gitignore to allow data outputs

**Files:**
- Modify: `.gitignore`

The pipeline commits `leads_scored.csv` and `qualified_jobs.csv` back to the repo after each run. Remove them from gitignore so Git tracks them.

- [ ] **Step 1: Edit `.gitignore`**

Replace this section:
```
# ── Data outputs (generated, not committed) ───────────────────
data/raw_jobs.csv
data/qualified_jobs.csv
data/leads_scored.csv
```

With:
```
# ── Data outputs ──────────────────────────────────────────────
# raw_jobs.csv is intermediate — never commit
data/raw_jobs.csv
# leads_scored.csv and qualified_jobs.csv ARE committed (pipeline
# writes them back to repo so they persist between GitHub Actions runs)
```

- [ ] **Step 2: Verify the change looks right**

Run:
```powershell
git diff .gitignore
```

Expected output shows `data/qualified_jobs.csv` and `data/leads_scored.csv` removed from the ignore list.

- [ ] **Step 3: Stage data files that were previously gitignored**

```powershell
cd "D:\Users\ysai\Documents\lead_gen"
git add data/leads_scored.csv data/qualified_jobs.csv
git status --short
```

Expected: both files show as `A ` (new tracked files).

- [ ] **Step 4: Commit**

```powershell
git add .gitignore data/leads_scored.csv data/qualified_jobs.csv
git commit -m "chore: track data outputs in git for Actions persistence"
```

---

## Task 2: Create requirements.txt

**Files:**
- Create: `requirements.txt`

GitHub Actions needs this file to install Python dependencies on the Ubuntu runner.

- [ ] **Step 1: Create the file**

Create `requirements.txt` in the project root with exactly this content:
```
playwright
beautifulsoup4
requests
```

No version pins — the pipeline is not version-sensitive and pinning would cause stale dependency issues.

- [ ] **Step 2: Verify locally (optional but good)**

```powershell
pip install -r requirements.txt --dry-run 2>&1 | Select-Object -First 10
```

Expected: lists playwright, beautifulsoup4, requests with no errors.

- [ ] **Step 3: Commit**

```powershell
git add requirements.txt
git commit -m "chore: add requirements.txt for GitHub Actions runner"
```

---

## Task 3: Create index.html redirect

**Files:**
- Create: `index.html`

GitHub Pages will serve `techteampeer.github.io/lead-gen/` — without this, that URL shows a 404. This file instantly redirects to `dashboard.html`.

- [ ] **Step 1: Create `index.html`**

Create `index.html` in the project root:
```html
<!DOCTYPE html>
<meta http-equiv="refresh" content="0; url=dashboard.html">
<title>Redirecting…</title>
<a href="dashboard.html">Click here if not redirected</a>
```

- [ ] **Step 2: Commit**

```powershell
git add index.html
git commit -m "chore: add index.html redirect for GitHub Pages root URL"
```

---

## Task 4: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/pipeline.yml`

This is the core of the deployment — the workflow that runs the pipeline in the cloud.

- [ ] **Step 1: Create the workflows directory**

```powershell
New-Item -ItemType Directory -Force "D:\Users\ysai\Documents\lead_gen\.github\workflows"
```

- [ ] **Step 2: Create `.github/workflows/pipeline.yml`**

Create the file with this exact content:

```yaml
name: Run Lead Gen Pipeline

on:
  workflow_dispatch:
    inputs:
      skip_browser:
        description: 'Skip Playwright/Dice scraping (uses cached Dice data — faster)'
        required: false
        default: false
        type: boolean

permissions:
  contents: write

jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Python dependencies
        run: pip install -r requirements.txt

      - name: Install Playwright browsers
        run: playwright install chromium --with-deps

      - name: "[1/2] Run pipeline (scrape → filter → rollup)"
        run: |
          if [ "${{ inputs.skip_browser }}" = "true" ]; then
            python run_pipeline.py --skip-browser
          else
            python run_pipeline.py
          fi

      - name: "[2/2] Score + rebuild dashboard"
        run: python rebuild_dashboard.py

      - name: Commit results back to repo
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ dashboard.html
          git diff --staged --quiet && echo "Nothing changed — skipping commit" || \
            git commit -m "pipeline: update leads $(date -u '+%Y-%m-%d %H:%M UTC')"
          git push
```

- [ ] **Step 3: Verify the YAML is valid**

```powershell
python -c "import yaml; yaml.safe_load(open('.github/workflows/pipeline.yml'))" 2>&1
```

Expected: no output (no errors). If `yaml` not installed, run `pip install pyyaml` first.

- [ ] **Step 4: Commit**

```powershell
git add .github/workflows/pipeline.yml
git commit -m "ci: add GitHub Actions pipeline workflow"
```

---

## Task 5: Create GitHub repo and push

**Files:** None (Git/GitHub operations)

We need to create the public repo on GitHub and push the local commits.

- [ ] **Step 1: Create a GitHub Personal Access Token (PAT)**

  1. Visit https://github.com/settings/tokens/new
  2. Note name: `lead-gen deploy`
  3. Expiration: `No expiration` (or 1 year)
  4. Scopes: check **`repo`** (full control of private repositories) — this covers public repos too
  5. Click **Generate token**
  6. **Copy the token** (shown once — starts with `ghp_`)

- [ ] **Step 2: Create the GitHub repo via API**

Replace `YOUR_PAT_HERE` with the token you just copied:

```powershell
$pat = "YOUR_PAT_HERE"
$headers = @{
  Authorization = "token $pat"
  Accept = "application/vnd.github+json"
}
$body = @{
  name        = "lead-gen"
  description = "AI-powered IT staffing lead gen pipeline"
  private     = $false
  auto_init   = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://api.github.com/orgs/techteampeer/repos" `
  -Method Post -Headers $headers -Body $body -ContentType "application/json"
```

Expected output: a JSON object with `"full_name": "techteampeer/lead-gen"` and `"html_url": "https://github.com/techteampeer/lead-gen"`.

> **Note:** If techteampeer is a personal account (not an org), replace `/orgs/techteampeer/repos` with `/user/repos` in the URL.

- [ ] **Step 3: Add the GitHub remote**

```powershell
cd "D:\Users\ysai\Documents\lead_gen"
git remote add origin https://github.com/techteampeer/lead-gen.git
git remote -v
```

Expected:
```
origin  https://github.com/techteampeer/lead-gen.git (fetch)
origin  https://github.com/techteampeer/lead-gen.git (push)
```

- [ ] **Step 4: Set the default branch name to `main`**

```powershell
git branch -M main
```

- [ ] **Step 5: Push to GitHub**

```powershell
git push -u origin main
```

When prompted for credentials:
- **Username:** `techteampeer`
- **Password:** paste the PAT (not your GitHub password)

Expected: output ending with `Branch 'main' set up to track remote branch 'main' from 'origin'.`

- [ ] **Step 6: Verify on GitHub**

Visit https://github.com/techteampeer/lead-gen — you should see all 32+ files.

---

## Task 6: Enable GitHub Pages

**Files:** None (GitHub settings)

This is a one-time manual step in the GitHub UI. GitHub Pages will then auto-deploy every time the pipeline pushes `dashboard.html` to `main`.

- [ ] **Step 1: Open Pages settings**

Visit: https://github.com/techteampeer/lead-gen/settings/pages

- [ ] **Step 2: Configure source**

Under **"Build and deployment"**:
- Source: **Deploy from a branch**
- Branch: **main**
- Folder: **/ (root)**

Click **Save**.

- [ ] **Step 3: Wait for first deployment (~2 minutes)**

GitHub will show a banner: *"Your site is live at https://techteampeer.github.io/lead-gen/"*

- [ ] **Step 4: Verify dashboard loads**

Visit: https://techteampeer.github.io/lead-gen/

Expected: redirect to `dashboard.html` → IT Staffing Lead Dashboard loads with existing data.

---

## Task 7: Run the pipeline end-to-end on GitHub

Smoke test the whole thing.

- [ ] **Step 1: Navigate to Actions**

Visit: https://github.com/techteampeer/lead-gen/actions

You should see **"Run Lead Gen Pipeline"** listed.

- [ ] **Step 2: Trigger a run**

Click **"Run Lead Gen Pipeline"** → click **"Run workflow"** button → leave `skip_browser` unchecked → click the green **"Run workflow"** button.

- [ ] **Step 3: Watch live logs**

Click the running job. You should see each step stream in real time:
```
[1/5] Dice.com (Playwright)…
[2/5] Wellfound…
[3/5] Greenhouse boards…
[4/5] Lever boards…
[5/5] Ashby boards…
Building dashboard from N company leads
```

- [ ] **Step 4: Verify commit was pushed**

After the workflow completes (~10-15 min), visit:
https://github.com/techteampeer/lead-gen/commits/main

The latest commit should say: `pipeline: update leads YYYY-MM-DD HH:MM UTC`

- [ ] **Step 5: Verify dashboard updated**

Visit: https://techteampeer.github.io/lead-gen/

The "Generated" timestamp in the dashboard header should match the run time.

---

## Summary: What the CEO Does Each Time

1. Go to https://github.com/techteampeer/lead-gen/actions
2. Click **"Run Lead Gen Pipeline"** → **"Run workflow"**
3. Watch live logs (optional)
4. Visit https://techteampeer.github.io/lead-gen/ for fresh leads
