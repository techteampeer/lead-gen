#!/usr/bin/env python3
"""
scorer.py  –  Lead Gen Pipeline  |  Phase 3

Reads data/qualified_jobs.csv, scores each qualified lead 0-100,
assigns urgency (HIGH / MEDIUM / LOW), enriches with company info,
then writes:
  - data/leads_scored.csv   (all qualified leads, ranked by score)
  - dashboard.html          (self-contained HTML with embedded data)

Log: logs/scorer.log

Scoring rubric (0-100):
  Job signals   (0-60):  SeniorRole +15 | NicheStack +12 | Age14-60d +10
                          3+OpenRoles +15 | UrgencyLang +8
  Company signals (0-40): Funded B+ +15 | Size50-500 +10 | NY/NJ +8
                           NoInternalTA +7 | TechIndustry +5
"""

import csv
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
DATA_DIR           = os.path.join(BASE_DIR, "data")
LOGS_DIR           = os.path.join(BASE_DIR, "logs")
QUALIFIED_JOBS_CSV = os.path.join(DATA_DIR, "qualified_jobs.csv")
LEADS_SCORED_CSV   = os.path.join(DATA_DIR, "leads_scored.csv")
DASHBOARD_HTML     = os.path.join(BASE_DIR, "dashboard.html")
CONFIG_PATH        = os.path.join(BASE_DIR, "config.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "scorer.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
try:
    with open(CONFIG_PATH, encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except Exception as e:
    logger.error(f"Cannot load config.json: {e}")
    CONFIG = {}

NICHE_STACK:    List[str] = [kw.lower() for kw in CONFIG.get("niche_stack_keywords", [])]
URGENCY_KW:     List[str] = [kw.lower() for kw in CONFIG.get("urgency_keywords", [])]
FUNDED_KW:      List[str] = [kw.lower() for kw in CONFIG.get("funded_stage_keywords", [])]
TARGET_LOC:     List[str] = [loc.lower() for loc in CONFIG.get("target_locations", [])]
KNOWN_FUNDED:   List[str] = [c.lower()   for c   in CONFIG.get("known_funded_companies", [])]

NY_NJ_TERMS = ["new york", " ny ", "nyc", "manhattan", "brooklyn", "queens", "bronx",
               "new jersey", " nj ", "newark", "hoboken", "jersey city"]

# ── Output columns ────────────────────────────────────────────────────────────
INPUT_COLS = [
    "source", "company", "job_id", "title", "location",
    "description", "posting_date", "job_url", "discard_reason",
]
OUTPUT_COLS = INPUT_COLS + [
    "score", "urgency", "job_signals_score", "company_signals_score",
    "score_breakdown", "linkedin_url", "company_size", "funding_stage",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def posting_age_days(posting_date: str) -> int:
    if not posting_date:
        return 999
    try:
        return (datetime.now() - datetime.strptime(posting_date[:10], "%Y-%m-%d")).days
    except ValueError:
        return 999


def company_slug(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug.strip("-")


# ── Job signals scoring (0-60) ────────────────────────────────────────────────

def score_job_signals(
    job: Dict[str, str],
    open_role_count: int,
) -> Tuple[int, List[str]]:
    title = job.get("title", "").lower()
    desc  = job.get("description", "").lower()
    text  = f"{title} {desc}"
    score = 0
    parts: List[str] = []

    # +15 — Senior / Staff / Principal title
    SENIOR_TERMS = ["senior", "staff", "principal", "lead ", "architect", "distinguished", "vp of eng"]
    if any(t in title for t in SENIOR_TERMS):
        score += 15
        matched = next(t.strip() for t in SENIOR_TERMS if t in title)
        parts.append(f"SeniorRole(+15)")

    # +12 — Niche / specialised stack in title or description
    niche_hits = [kw for kw in NICHE_STACK if kw in text]
    if niche_hits:
        score += 12
        label = niche_hits[0].replace(" ", "_").title()
        parts.append(f"NicheStack_{label}(+12)")

    # +10 — Posted 14-60 days ago  |  +5 — posted 0-13 days (very fresh)
    age = posting_age_days(job.get("posting_date", ""))
    if 14 <= age <= 60:
        score += 10
        parts.append(f"{age}DaysOld(+10)")
    elif 0 <= age < 14:
        score += 5
        parts.append(f"{age}DaysOld_Fresh(+5)")

    # +15 — Company has 3+ open IT roles simultaneously
    if open_role_count >= 3:
        score += 15
        parts.append(f"{open_role_count}OpenRoles(+15)")
    elif open_role_count == 2:
        score += 8
        parts.append(f"2OpenRoles(+8)")

    # +8 — Urgency language in title or description
    urgency_hits = [kw for kw in URGENCY_KW if kw in text]
    if urgency_hits:
        score += 8
        parts.append(f"UrgencyLang(+8)")

    return min(score, 60), parts


# ── Company signals scoring (0-40) ────────────────────────────────────────────

def score_company_signals(
    job: Dict[str, str],
) -> Tuple[int, List[str], str, str]:
    """Returns (score, breakdown_parts, company_size_label, funding_stage_label)."""
    company_l = job.get("company", "").lower()
    location_l = job.get("location", "").lower()
    desc_l     = job.get("description", "").lower()
    score = 0
    parts: List[str] = []
    company_size  = "Unknown"
    funding_stage = "Unknown"

    # +15 — Series B+ / public / known funded company
    funded_hits = [kw for kw in FUNDED_KW if kw in desc_l or kw in company_l]
    if funded_hits:
        score += 15
        funding_stage = funded_hits[0].replace("series ", "Series ").title()
        parts.append(f"Funded_{funding_stage.replace(' ', '')}(+15)")
    elif any(k in company_l for k in KNOWN_FUNDED):
        score += 15
        funding_stage = "Series B+ (inferred)"
        parts.append(f"KnownFundedCo(+15)")

    # +10 — Estimated 50-500 employees
    # Proxy: startup / scale-up language, or infer from known companies
    size_50_500_terms = ["startup", "scale-up", "scaleup", "series a", "series b", "series c",
                         "growing team", "small team", "fast-growing team"]
    enterprise_terms  = ["fortune 500", "enterprise", "global company", "multinational",
                         "10,000 employees", "50,000", "100,000"]
    if any(t in desc_l for t in size_50_500_terms):
        score += 10
        company_size = "50-500 (estimated)"
        parts.append(f"EstSize_50-500(+10)")
    elif any(k in company_l for k in KNOWN_FUNDED) and not any(t in desc_l for t in enterprise_terms):
        score += 10
        company_size = "50-500 (inferred)"
        parts.append(f"InferredSize_50-500(+10)")

    # +8 — NY / NJ HQ or major office
    loc_check = f"{location_l} {desc_l[:200]}"
    if any(t in loc_check for t in NY_NJ_TERMS):
        score += 8
        parts.append(f"NY_NJ_Location(+8)")
    elif "remote" in location_l:
        score += 3
        parts.append(f"Remote_Partial(+3)")

    # +7 — No visible internal recruiter / TA team signal
    # Proxy: absence of "talent acquisition", "internal recruiter", "in-house recruiter"
    ta_team_terms = ["talent acquisition", "in-house recruiter", "internal recruiter",
                     "our talent team", "our recruiting team", "our hr team"]
    if not any(t in desc_l for t in ta_team_terms):
        score += 7
        parts.append(f"NoVisibleTA(+7)")

    # +5 — Tech / fintech / biotech / healthtech industry
    industry_terms = ["fintech", "biotech", "healthtech", "health tech", "medtech",
                      " saas ", "developer tools", "cloud platform", "data platform",
                      "ai platform", "machine learning platform", "infrastructure"]
    if any(t in desc_l or t in company_l for t in industry_terms):
        score += 5
        parts.append(f"TechIndustry(+5)")

    return min(score, 40), parts, company_size, funding_stage


# ── Urgency assignment ────────────────────────────────────────────────────────

def assign_urgency(
    job: Dict[str, str],
    job_score: int,
    company_score: int,
    open_role_count: int,
) -> str:
    age   = posting_age_days(job.get("posting_date", ""))
    text  = f"{job.get('title','').lower()} {job.get('description','').lower()}"
    total = job_score + company_score

    has_urgency = any(kw in text for kw in URGENCY_KW)
    has_niche   = any(kw in text for kw in NICHE_STACK)
    has_funding = any(kw in text for kw in FUNDED_KW)

    # HIGH: very fresh AND strong signals
    if age <= 21 and (has_urgency or open_role_count >= 3 or has_funding or total >= 60):
        return "HIGH"
    # MEDIUM: within 60 days with at least one urgency signal
    if age <= 60 and (has_urgency or has_niche or total >= 40):
        return "MEDIUM"
    return "LOW"


# ── Score all leads ───────────────────────────────────────────────────────────

def score_all(jobs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    qualified = [j for j in jobs if not j.get("discard_reason", "")]

    # Pre-compute open role counts per company (qualified only)
    company_role_counts: Dict[str, int] = {}
    for j in qualified:
        key = j.get("company", "").lower().strip()
        company_role_counts[key] = company_role_counts.get(key, 0) + 1

    results: List[Dict[str, str]] = []

    for job in qualified:
        company_key   = job.get("company", "").lower().strip()
        open_roles    = company_role_counts.get(company_key, 1)

        j_score, j_parts = score_job_signals(job, open_roles)
        c_score, c_parts, c_size, c_funding = score_company_signals(job)

        total   = min(j_score + c_score, 100)
        urgency = assign_urgency(job, j_score, c_score, open_roles)

        slug    = company_slug(job.get("company", ""))
        breakdown = " ".join(j_parts + c_parts) or "NoSignals(0)"

        row = {col: job.get(col, "") for col in INPUT_COLS}
        row.update({
            "score":                str(total),
            "urgency":              urgency,
            "job_signals_score":    str(j_score),
            "company_signals_score":str(c_score),
            "score_breakdown":      breakdown,
            "linkedin_url":         f"https://www.linkedin.com/company/{slug}/jobs",
            "company_size":         c_size,
            "funding_stage":        c_funding,
        })
        results.append(row)

    URGENCY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results.sort(key=lambda x: (-int(x["score"]), URGENCY_ORDER.get(x["urgency"], 2)))
    return results


# ── Dashboard HTML generation ─────────────────────────────────────────────────

DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>IT Staffing Leads — %RUN_DATE%</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #f1f5f9; color: #0f172a; font-size: 14px; }
    a { color: inherit; text-decoration: none; }

    /* ── Header ── */
    .header { background: #1e293b; color: #f8fafc; padding: 16px 24px;
              display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
    .header h1 { font-size: 18px; font-weight: 700; letter-spacing: -.3px; }
    .header .run-date { font-size: 12px; color: #94a3b8; }
    .stats-bar { display: flex; gap: 16px; flex-wrap: wrap; }
    .stat { display: flex; flex-direction: column; align-items: center; }
    .stat-num  { font-size: 22px; font-weight: 800; line-height: 1; }
    .stat-label { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: .5px; }
    .stat-high   .stat-num { color: #f87171; }
    .stat-medium .stat-num { color: #fb923c; }
    .stat-low    .stat-num { color: #60a5fa; }
    .stat-total  .stat-num { color: #34d399; }

    /* ── Controls bar ── */
    .controls { background: #fff; border-bottom: 1px solid #e2e8f0;
                padding: 12px 24px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .control-group { display: flex; flex-direction: column; gap: 2px; }
    .control-group label { font-size: 11px; font-weight: 600; color: #64748b;
                           text-transform: uppercase; letter-spacing: .4px; }
    input[type=range] { width: 140px; accent-color: #6366f1; cursor: pointer; }
    select, input[type=text] { border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 10px;
                                font-size: 13px; background: #f8fafc; outline: none; }
    select:focus, input[type=text]:focus { border-color: #6366f1; box-shadow: 0 0 0 2px #e0e7ff; }
    .btn-toggle { background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;
                  padding: 6px 12px; font-size: 12px; cursor: pointer; color: #475569;
                  transition: background .15s; white-space: nowrap; }
    .btn-toggle:hover { background: #e2e8f0; }
    .btn-toggle.active { background: #6366f1; color: #fff; border-color: #6366f1; }
    .score-val { font-size: 13px; font-weight: 700; color: #6366f1; min-width: 28px; }

    /* ── Table wrapper ── */
    .table-wrap { overflow-x: auto; padding: 16px 24px; }
    table { width: 100%; border-collapse: collapse; background: #fff;
            border-radius: 10px; overflow: hidden;
            box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    thead { background: #1e293b; color: #f8fafc; }
    th { padding: 11px 12px; text-align: left; font-size: 12px; font-weight: 600;
         letter-spacing: .4px; text-transform: uppercase; white-space: nowrap;
         cursor: pointer; user-select: none; }
    th:hover { background: #334155; }
    th .sort-arrow { margin-left: 4px; opacity: .5; }
    th.sorted .sort-arrow { opacity: 1; }
    td { padding: 10px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
    tr:last-child td { border-bottom: none; }

    /* ── Company rows ── */
    tr.company-row { cursor: pointer; }
    tr.company-row:hover td { background: #f8fafc; }
    tr.row-green  td:first-child { border-left: 4px solid #22c55e; }
    tr.row-yellow td:first-child { border-left: 4px solid #eab308; }
    tr.row-gray   td:first-child { border-left: 4px solid #94a3b8; }
    tr.contacted td { opacity: .45; text-decoration: line-through; }

    /* ── Role sub-rows ── */
    tr.role-row td { background: #f8fafc; padding: 7px 12px 7px 32px;
                     border-bottom: 1px solid #f1f5f9; font-size: 13px; }
    tr.role-row:last-child td { border-bottom: none; }
    tr.role-row td:first-child { border-left: 4px solid transparent; padding-left: 32px; }
    tr.role-row.hidden { display: none; }
    .role-title-link { color: #3b82f6; text-decoration: none; }
    .role-title-link:hover { text-decoration: underline; }

    /* ── Score badge ── */
    .score-badge { display: inline-block; padding: 3px 8px; border-radius: 20px;
                   font-weight: 800; font-size: 13px; min-width: 38px; text-align: center;
                   cursor: help; }
    .score-green  { background: #dcfce7; color: #15803d; }
    .score-yellow { background: #fef9c3; color: #854d0e; }
    .score-gray   { background: #f1f5f9; color: #475569; }

    /* ── Urgency badge ── */
    .urg { display: inline-block; padding: 2px 8px; border-radius: 12px;
           font-size: 11px; font-weight: 700; letter-spacing: .3px; white-space: nowrap; }
    .urg-HIGH   { background: #fee2e2; color: #dc2626; }
    .urg-MEDIUM { background: #fff7ed; color: #ea580c; }
    .urg-LOW    { background: #eff6ff; color: #2563eb; }

    /* ── Role count badge ── */
    .role-count { display: inline-block; padding: 1px 7px; border-radius: 10px;
                  font-size: 11px; font-weight: 700; background: #e0e7ff; color: #4338ca;
                  white-space: nowrap; margin-left: 6px; }

    /* ── Expand arrow ── */
    .expand-arrow { display: inline-block; margin-right: 8px; font-size: 10px;
                    color: #94a3b8; transition: transform .2s; }
    .expand-arrow.open { transform: rotate(90deg); }

    /* ── Source badge ── */
    .src { display: inline-block; padding: 1px 6px; border-radius: 8px;
           font-size: 10px; font-weight: 600; background: #f1f5f9; color: #64748b; }

    /* ── Action buttons ── */
    .actions { display: flex; gap: 5px; flex-wrap: nowrap; }
    .btn { border: none; border-radius: 6px; padding: 5px 9px; font-size: 12px;
           font-weight: 600; cursor: pointer; transition: opacity .15s, transform .1s;
           white-space: nowrap; }
    .btn:hover { opacity: .85; transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-li   { background: #0077b5; color: #fff; }
    .btn-cb   { background: #0288d1; color: #fff; }
    .btn-copy { background: #6366f1; color: #fff; }
    .btn-done { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
    .btn-done.contacted-btn { background: #dcfce7; color: #15803d; border-color: #86efac; }
    .btn-job  { background: #f1f5f9; color: #3b82f6; border: 1px solid #bfdbfe;
                font-size: 11px; padding: 3px 7px; }

    /* ── Toast ── */
    #toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(80px);
             background: #1e293b; color: #f8fafc; padding: 10px 20px; border-radius: 8px;
             font-size: 13px; font-weight: 500; opacity: 0; transition: all .3s;
             pointer-events: none; z-index: 9999; white-space: nowrap; }
    #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

    /* ── Empty state ── */
    .empty { text-align: center; padding: 60px 24px; color: #94a3b8; }
    .empty h3 { font-size: 18px; margin-bottom: 8px; }

    /* ── Responsive ── */
    @media (max-width: 768px) {
      .header { flex-direction: column; align-items: flex-start; }
      .controls { flex-direction: column; align-items: flex-start; }
      .table-wrap { padding: 8px; }
      td.hide-mobile, th.hide-mobile { display: none; }
    }
  </style>
</head>
<body>

<div class="header">
  <div>
    <h1>IT Staffing Lead Dashboard</h1>
    <div class="run-date">Generated %RUN_DATE%</div>
  </div>
  <div class="stats-bar">
    <div class="stat stat-total">  <span class="stat-num" id="cnt-total">0</span><span class="stat-label">Companies</span></div>
    <div class="stat stat-high">   <span class="stat-num" id="cnt-high">0</span> <span class="stat-label">High</span></div>
    <div class="stat stat-medium"> <span class="stat-num" id="cnt-med">0</span>  <span class="stat-label">Medium</span></div>
    <div class="stat stat-low">    <span class="stat-num" id="cnt-low">0</span>  <span class="stat-label">Low</span></div>
  </div>
</div>

<div class="controls">
  <div class="control-group">
    <label>Min Score</label>
    <div style="display:flex;align-items:center;gap:8px">
      <input type="range" id="score-slider" min="0" max="100" value="0" step="5"
             oninput="onScoreSlider(this.value)" />
      <span class="score-val" id="score-val-lbl">0+</span>
    </div>
  </div>
  <div class="control-group">
    <label>Urgency</label>
    <select id="urgency-filter" onchange="onUrgencyFilter(this.value)">
      <option value="ALL">All urgencies</option>
      <option value="HIGH">HIGH only</option>
      <option value="MEDIUM">MEDIUM only</option>
      <option value="LOW">LOW only</option>
    </select>
  </div>
  <div class="control-group">
    <label>Search</label>
    <input type="text" id="search-box" placeholder="Company or role…"
           oninput="onSearch(this.value)" style="width:200px" />
  </div>
  <div class="control-group">
    <label>Contacted</label>
    <button class="btn-toggle" id="toggle-contacted" onclick="toggleContacted()">
      Hide contacted
    </button>
  </div>
  <div class="control-group" style="margin-left:auto">
    <label>&nbsp;</label>
    <button class="btn-toggle" onclick="clearContacted()" title="Remove all contacted marks">
      Clear marks
    </button>
  </div>
</div>

<div class="table-wrap">
  <table id="leads-table">
    <thead>
      <tr>
        <th onclick="sortBy('score')"    class="sorted" id="th-score">   Score <span class="sort-arrow">▼</span></th>
        <th onclick="sortBy('urgency')"  id="th-urgency">  Urgency <span class="sort-arrow">↕</span></th>
        <th onclick="sortBy('company')"  id="th-company">  Company <span class="sort-arrow">↕</span></th>
        <th>Open Roles</th>
        <th onclick="sortBy('location')" id="th-location" class="hide-mobile"> Location <span class="sort-arrow">↕</span></th>
        <th class="hide-mobile">Source</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty" id="empty-state" style="display:none">
    <h3>No leads match your filters</h3>
    <p>Try lowering the score threshold or changing urgency filter.</p>
  </div>
</div>

<div id="toast"></div>

<script>
// ── Embedded data ─────────────────────────────────────────────────────────────
const ALL_LEADS = %LEADS_JSON%;
const RUN_DATE  = "%RUN_DATE%";

// ── State ─────────────────────────────────────────────────────────────────────
let sortCol       = "score";
let sortDir       = -1;
let minScore      = 0;
let filterUrg     = "ALL";
let searchText    = "";
let hideContacted = false;
const expandedSet = new Set();

// ── Contacted (tracked by company key) ───────────────────────────────────────
function getContacted() {
  try { return new Set(JSON.parse(localStorage.getItem("contacted_cos") || "[]")); }
  catch { return new Set(); }
}
function saveContacted(s) {
  localStorage.setItem("contacted_cos", JSON.stringify([...s]));
}

// ── Group ALL_LEADS by company ────────────────────────────────────────────────
const URGENCY_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2 };

function buildGroups(leads) {
  const map = new Map();
  leads.forEach(l => {
    const key = l.company.toLowerCase().trim();
    if (!map.has(key)) map.set(key, { key, company: l.company, roles: [] });
    map.get(key).roles.push(l);
  });
  return Array.from(map.values()).map(g => {
    const scores   = g.roles.map(r => parseInt(r.score) || 0);
    const best     = g.roles[scores.indexOf(Math.max(...scores))];
    const urgOrd   = g.roles.map(r => URGENCY_ORDER[r.urgency] ?? 3);
    return {
      key:        g.key,
      company:    g.company,
      roles:      g.roles,
      score:      Math.max(...scores),
      urgency:    g.roles[urgOrd.indexOf(Math.min(...urgOrd))].urgency,
      location:   best.location,
      source:     best.source,
      linkedin_url: best.linkedin_url,
      score_breakdown: best.score_breakdown,
    };
  });
}

// ── Filter + sort groups ──────────────────────────────────────────────────────
function getGroups() {
  const contacted = getContacted();
  const s = searchText.toLowerCase();

  // filter individual leads first so role count reflects active filters
  const leads = ALL_LEADS.filter(l => {
    if (parseInt(l.score) < minScore) return false;
    if (filterUrg !== "ALL" && l.urgency !== filterUrg) return false;
    if (s) return l.company.toLowerCase().includes(s) || l.title.toLowerCase().includes(s);
    return true;
  });

  let groups = buildGroups(leads);

  if (hideContacted) groups = groups.filter(g => !contacted.has(g.key));

  groups.sort((a, b) => {
    let av, bv;
    if (sortCol === "score")    { av = a.score;   bv = b.score; }
    else if (sortCol === "urgency")  { av = URGENCY_ORDER[a.urgency] ?? 3; bv = URGENCY_ORDER[b.urgency] ?? 3; }
    else if (sortCol === "company")  { av = a.company.toLowerCase(); bv = b.company.toLowerCase(); }
    else if (sortCol === "location") { av = (a.location||"").toLowerCase(); bv = (b.location||"").toLowerCase(); }
    else { av = ""; bv = ""; }
    if (av < bv) return sortDir;
    if (av > bv) return -sortDir;
    return 0;
  });

  return groups;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s || "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
function escAttr(s) { return esc(s); }

function ageDays(d) {
  if (!d) return 999;
  try { return Math.floor((Date.now() - new Date(d)) / 86400000); }
  catch { return 999; }
}
function ageLabel(d) {
  const n = ageDays(d);
  return n < 999 ? `${n}d ago` : d || "–";
}
function crunchbaseUrl(co) {
  return "https://www.crunchbase.com/organization/" +
    encodeURIComponent(co.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,""));
}

// ── Render ────────────────────────────────────────────────────────────────────
function render() {
  const contacted = getContacted();
  const groups    = getGroups();
  const tbody     = document.getElementById("tbody");
  const emptyEl   = document.getElementById("empty-state");

  document.getElementById("cnt-total").textContent = groups.length;
  document.getElementById("cnt-high").textContent  = groups.filter(g => g.urgency === "HIGH").length;
  document.getElementById("cnt-med").textContent   = groups.filter(g => g.urgency === "MEDIUM").length;
  document.getElementById("cnt-low").textContent   = groups.filter(g => g.urgency === "LOW").length;

  if (!groups.length) {
    tbody.innerHTML = "";
    emptyEl.style.display = "block";
    return;
  }
  emptyEl.style.display = "none";

  const rows = [];
  groups.forEach(g => {
    const score      = g.score;
    const isCo       = contacted.has(g.key);
    const isExpanded = expandedSet.has(g.key);
    const rowCls     = score >= 80 ? "row-green" : score >= 70 ? "row-yellow" : "row-gray";
    const scBadge    = score >= 80 ? "score-green" : score >= 70 ? "score-yellow" : "score-gray";
    const cbUrl      = crunchbaseUrl(g.company);
    const safeKey    = escAttr(g.key);
    const safeComp   = escAttr(g.company);
    const safeLI     = escAttr(g.linkedin_url || "");
    const safeCB     = escAttr(cbUrl);
    const breakdown  = esc(g.score_breakdown || "");
    // pick the top role title for the pitch
    const topTitle   = escAttr(g.roles[0]?.title || "");

    // unique sources across all roles
    const sources = [...new Set(g.roles.map(r => r.source))].join(", ");

    rows.push(`<tr class="company-row ${rowCls}${isCo ? " contacted" : ""}"
        onclick="toggleExpand('${safeKey}')">
      <td>
        <span class="expand-arrow${isExpanded ? " open" : ""}">▶</span><span
          class="score-badge ${scBadge}" title="${breakdown}">${score}</span>
      </td>
      <td><span class="urg urg-${esc(g.urgency)}">${esc(g.urgency)}</span></td>
      <td style="font-weight:700;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
          title="${safeComp}">${esc(g.company)}</td>
      <td>
        <span class="role-count">${g.roles.length} role${g.roles.length > 1 ? "s" : ""}</span>
      </td>
      <td class="hide-mobile" style="color:#64748b;white-space:nowrap">${esc(g.location || "–")}</td>
      <td class="hide-mobile"><span class="src">${esc(sources)}</span></td>
      <td onclick="event.stopPropagation()">
        <div class="actions">
          <button class="btn btn-li"   onclick="openUrl('${safeLI}')"           title="LinkedIn Jobs">LI</button>
          <button class="btn btn-cb"   onclick="openUrl('${safeCB}')"           title="Crunchbase">CB</button>
          <button class="btn btn-copy" onclick="copyPitch('${safeComp}','${topTitle}')" title="Copy outreach pitch">📋</button>
          <button class="btn btn-done${isCo ? " contacted-btn" : ""}"
                  onclick="toggleContact('${safeKey}')"
                  title="${isCo ? "Unmark contacted" : "Mark as contacted"}">
            ${isCo ? "✓" : "○"}
          </button>
        </div>
      </td>
    </tr>`);

    // role sub-rows
    g.roles.forEach(r => {
      const age  = ageLabel(r.posting_date);
      const link = r.job_url
        ? `<a class="role-title-link" href="${escAttr(r.job_url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`
        : esc(r.title);
      rows.push(`<tr class="role-row${isExpanded ? "" : " hidden"}" data-group="${safeKey}">
        <td colspan="2"></td>
        <td colspan="2">${link}</td>
        <td class="hide-mobile" style="color:#64748b">${esc(r.location || "–")}</td>
        <td class="hide-mobile" style="color:#94a3b8">${age}</td>
        <td></td>
      </tr>`);
    });
  });

  tbody.innerHTML = rows.join("");
}

// ── Expand / collapse ─────────────────────────────────────────────────────────
function toggleExpand(key) {
  if (expandedSet.has(key)) expandedSet.delete(key);
  else expandedSet.add(key);
  // toggle DOM directly — faster than full re-render
  document.querySelectorAll(`tr.role-row[data-group="${CSS.escape(key)}"]`).forEach(tr => {
    tr.classList.toggle("hidden");
  });
  const arrow = document.querySelector(`tr.company-row[onclick*="'${key}'"] .expand-arrow`);
  if (arrow) arrow.classList.toggle("open", expandedSet.has(key));
}

// ── Contact toggle ────────────────────────────────────────────────────────────
function toggleContact(key) {
  const s = getContacted();
  if (s.has(key)) { s.delete(key); showToast("Unmarked as contacted"); }
  else            { s.add(key);    showToast("Marked as contacted ✓"); }
  saveContacted(s);
  render();
}

function clearContacted() {
  if (!confirm("Clear all contacted marks?")) return;
  saveContacted(new Set());
  render();
  showToast("All marks cleared");
}

// ── Open URL ──────────────────────────────────────────────────────────────────
function openUrl(url) {
  if (url) window.open(url, "_blank", "noopener");
}

// ── Copy pitch ────────────────────────────────────────────────────────────────
function copyPitch(company, title) {
  const pitch =
`Hi [Name],

I noticed ${company} is hiring for a ${title} — congrats on the growth!

I run an IT staffing practice focused exclusively on senior/staff-level engineers for Series B+ tech companies in NY/NJ. We typically place candidates with niche stacks (Kubernetes, Rust, Go, ML infrastructure) within 7-10 business days.

A few differentiators:
• Pre-vetted talent pool — we only submit candidates we'd hire ourselves
• No-risk trial period — 90-day guarantee on every placement
• NY/NJ network — strong pipeline of local engineers open to the right opportunity

Would you be open to a 15-min call this week to see if there's a fit?

Best,
[Your Name]
[Company] | IT Staffing Specialists
[Phone] | [Email]`;

  navigator.clipboard.writeText(pitch)
    .then(() => showToast("Outreach pitch copied!"))
    .catch(() => {
      const ta = document.createElement("textarea");
      ta.value = pitch; ta.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(ta); ta.select(); document.execCommand("copy");
      document.body.removeChild(ta); showToast("Pitch copied!");
    });
}

// ── Controls ──────────────────────────────────────────────────────────────────
function sortBy(col) {
  if (sortCol === col) sortDir = -sortDir;
  else { sortCol = col; sortDir = (col === "score" || col === "urgency") ? -1 : 1; }
  document.querySelectorAll("thead th").forEach(th => {
    const active = th.id === "th-" + col;
    th.classList.toggle("sorted", active);
    const arr = th.querySelector(".sort-arrow");
    if (arr) arr.textContent = active ? (sortDir === -1 ? "▼" : "▲") : "↕";
  });
  render();
}
function onScoreSlider(v) {
  minScore = parseInt(v);
  document.getElementById("score-val-lbl").textContent = v + "+";
  render();
}
function onUrgencyFilter(v) { filterUrg = v; render(); }
function onSearch(v)        { searchText = v.trim(); render(); }
function toggleContacted() {
  hideContacted = !hideContacted;
  const btn = document.getElementById("toggle-contacted");
  btn.classList.toggle("active", hideContacted);
  btn.textContent = hideContacted ? "Show contacted" : "Hide contacted";
  render();
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let _tt = null;
function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.classList.add("show");
  if (_tt) clearTimeout(_tt);
  _tt = setTimeout(() => el.classList.remove("show"), 2500);
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  if (!ALL_LEADS || !ALL_LEADS.length) {
    document.getElementById("empty-state").style.display = "block";
    document.getElementById("empty-state").querySelector("h3").textContent =
      "No data — run scorer.py to generate leads";
    return;
  }
  render();
});
</script>
</body>
</html>
"""


def generate_dashboard(scored_jobs: List[Dict[str, str]]) -> None:
    top = scored_jobs[:150]
    leads_json = json.dumps(top, ensure_ascii=True, separators=(",", ":"))
    run_date   = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    html = (
        DASHBOARD_TEMPLATE
        .replace("%LEADS_JSON%", leads_json)
        .replace("%RUN_DATE%", run_date)
    )

    with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Dashboard written: {DASHBOARD_HTML}  ({len(top)} leads embedded)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 60)
    logger.info("Lead Gen Scorer — Starting")
    logger.info("=" * 60)

    if not os.path.exists(QUALIFIED_JOBS_CSV):
        logger.error(f"Input not found: {QUALIFIED_JOBS_CSV}  (run filters.py first)")
        return

    try:
        with open(QUALIFIED_JOBS_CSV, encoding="utf-8") as f:
            jobs: List[Dict[str, str]] = list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Failed to read {QUALIFIED_JOBS_CSV}: {e}")
        return

    qualified_count = sum(1 for j in jobs if not j.get("discard_reason", ""))
    logger.info(f"Loaded {len(jobs)} rows ({qualified_count} qualified for scoring)")

    scored = score_all(jobs)
    logger.info(f"Scored {len(scored)} leads")

    # Write leads_scored.csv
    with open(LEADS_SCORED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(scored)

    # Generate dashboard
    generate_dashboard(scored)

    # ── Score distribution summary ─────────────────────────────────────────────
    if scored:
        scores  = [int(r["score"]) for r in scored]
        high_ct = sum(1 for r in scored if r["urgency"] == "HIGH")
        med_ct  = sum(1 for r in scored if r["urgency"] == "MEDIUM")
        low_ct  = sum(1 for r in scored if r["urgency"] == "LOW")
        gte70   = sum(1 for s in scores if s >= 70)
        gte80   = sum(1 for s in scores if s >= 80)

        logger.info("─" * 60)
        logger.info(f"Score distribution:")
        logger.info(f"  80-100 (green):  {gte80}")
        logger.info(f"  70-79  (yellow): {gte70 - gte80}")
        logger.info(f"  0-69   (gray):   {len(scores) - gte70}")
        logger.info(f"Urgency: HIGH={high_ct}  MEDIUM={med_ct}  LOW={low_ct}")
        logger.info(f"Top 5 leads:")
        for r in scored[:5]:
            logger.info(f"  [{r['score']:>3}] {r['company'][:30]:<30} — {r['title'][:40]}")

    logger.info(f"Output: {LEADS_SCORED_CSV}")
    logger.info(f"Dashboard: {DASHBOARD_HTML}")
    logger.info("=" * 60)

    print(f"\n{'='*55}")
    print(f"  Scorer complete  →  {len(scored)} leads ranked")
    if scored:
        print(f"  Score 80+: {sum(1 for s in [int(r['score']) for r in scored] if s >= 80)}")
        print(f"  Score 70+: {sum(1 for s in [int(r['score']) for r in scored] if s >= 70)}")
        print(f"  HIGH urgency: {sum(1 for r in scored if r['urgency'] == 'HIGH')}")
        print(f"\n  Open dashboard.html in your browser")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
