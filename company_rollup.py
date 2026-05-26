"""
company_rollup.py — Groups raw jobs by company, applies hard filters.
Exports: rollup(jobs, config, recent) -> list[dict]
Each returned dict = one company with all their open IT roles.
"""
import json, os, re
from datetime import datetime

STRIP_SUFFIXES = re.compile(
    r"\b(inc\.?|corp\.?|llc\.?|ltd\.?|technologies|software|solutions|group|holdings)\b",
    re.IGNORECASE,
)

def _normalize(name: str) -> str:
    """Lowercase, strip legal suffixes, collapse whitespace."""
    n = STRIP_SUFFIXES.sub("", name.lower())
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"[,.\s]+$", "", n)
    return n

def _posting_age(date_str: str) -> int:
    if not date_str:
        return 999
    try:
        return (datetime.now() - datetime.strptime(date_str[:10], "%Y-%m-%d")).days
    except Exception:
        return 999

def rollup(
    jobs: list[dict],
    config: dict,
    recent: dict,
    max_companies: int = 60,
) -> list[dict]:
    """
    Groups jobs by company. Applies hard filters. Returns company dicts.

    Each company dict:
      company, normalized_name, open_roles (list), role_count,
      sources (list), latest_posting_date, slugs_to_try
    """
    enterprise_blocklist = {_normalize(n) for n in config.get("enterprise_blocklist", [])}
    disqualify_kw = [kw.lower() for kw in config.get("disqualify_keywords", [])]
    no_agency_phrases = [
        "no agencies", "no recruiters", "no staffing",
        "no third party", "direct applicants only", "no vendor",
    ]

    # Group by normalized company name
    grouped: dict[str, dict] = {}
    for job in jobs:
        company = job.get("company", "").strip()
        if not company or company.lower() == "unknown":
            continue

        norm = _normalize(company)
        if not norm:
            continue

        if norm not in grouped:
            grouped[norm] = {
                "company": company,
                "normalized_name": norm,
                "open_roles": [],
                "sources": set(),
                "latest_posting_date": "",
            }

        g = grouped[norm]
        title = job.get("title", "")
        desc  = job.get("description", "").lower()

        # Skip disqualified titles
        if any(kw in title.lower() for kw in disqualify_kw):
            continue

        # Skip no-agency postings
        if any(phrase in desc for phrase in no_agency_phrases):
            continue

        g["open_roles"].append({
            "title": title,
            "location": job.get("location", ""),
            "url": job.get("job_url", ""),
            "posting_date": job.get("posting_date", ""),
            "description": job.get("description", ""),
        })
        g["sources"].add(job.get("source", "unknown"))

        d = job.get("posting_date", "")
        if d and (not g["latest_posting_date"] or d > g["latest_posting_date"]):
            g["latest_posting_date"] = d

    # Hard filters on companies
    results = []
    for norm, g in grouped.items():
        if not g["open_roles"]:
            continue

        # Enterprise blocklist
        if norm in enterprise_blocklist:
            continue

        # Recently contacted
        if norm in recent:
            age = _posting_age(recent[norm])
            if age <= 30:
                continue

        # Build slug candidates for Greenhouse/Lever probing
        slug = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
        g["slugs_to_try"] = [slug, slug.replace("-", "")]
        g["sources"] = sorted(g["sources"])
        g["role_count"] = len(g["open_roles"])
        results.append(g)

    # Sort: most open roles first
    results.sort(key=lambda x: -x["role_count"])
    return results[:max_companies]
