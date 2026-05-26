import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from company_rollup import rollup, _normalize

CONFIG = {
    "enterprise_blocklist": ["JPMorgan", "IBM", "Deloitte"],
    "disqualify_keywords": ["help desk", "it support"],
}

def _job(company, title, desc="", source="dice", date="2026-05-01"):
    return {"company": company, "title": title, "description": desc,
            "source": source, "job_url": "", "location": "New York, NY",
            "posting_date": date, "job_id": "x"}

def test_normalize_strips_suffixes():
    assert _normalize("Stripe, Inc.") == "stripe"
    assert _normalize("DataBricks LLC") == "databricks"

def test_groups_by_company():
    jobs = [_job("Stripe", "Backend Engineer"), _job("Stripe", "Data Engineer")]
    result = rollup(jobs, CONFIG, {})
    assert len(result) == 1
    assert result[0]["role_count"] == 2

def test_drops_unknown_company():
    jobs = [_job("Unknown", "Software Engineer")]
    assert rollup(jobs, CONFIG, {}) == []

def test_drops_enterprise():
    jobs = [_job("JPMorgan", "Software Engineer")]
    assert rollup(jobs, CONFIG, {}) == []

def test_drops_disqualified_title():
    jobs = [_job("Startup Co", "Help Desk Engineer")]
    assert rollup(jobs, CONFIG, {}) == []

def test_drops_no_agency():
    jobs = [_job("Good Co", "Software Engineer", desc="no agencies please")]
    assert rollup(jobs, CONFIG, {}) == []

def test_recently_contacted_excluded():
    jobs = [_job("Stripe", "Software Engineer")]
    recent = {"stripe": "2026-05-15"}   # 6 days ago — within 30
    assert rollup(jobs, CONFIG, recent) == []

def test_sorts_by_role_count():
    jobs = [
        _job("SmallCo", "Engineer"),
        _job("BigHirer", "Backend"), _job("BigHirer", "Frontend"), _job("BigHirer", "Data"),
    ]
    result = rollup(jobs, CONFIG, {})
    assert result[0]["company"] == "BigHirer"
