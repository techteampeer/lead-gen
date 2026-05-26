"""Rebuild dashboard.html from the company-grouped leads_scored.csv"""
import csv, json, os, sys

# Trick: temporarily put company data into qualified_jobs.csv so scorer.py builds dashboard from it
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Read company-grouped leads
leads = list(csv.DictReader(open(os.path.join(BASE_DIR, 'data', 'leads_scored.csv'), encoding='utf-8')))
print(f"Building dashboard from {len(leads)} company leads")

# Write as qualified_jobs.csv (what scorer.py reads)
# Actually let's just directly rebuild the dashboard ourselves using the existing template

# Read existing dashboard to get the HTML template
with open(os.path.join(BASE_DIR, 'dashboard.html'), encoding='utf-8') as f:
    html = f.read()

# Find where the JSON data is embedded and replace it
# The dashboard embeds data as: const LEADS_DATA = [...];
import re

# Build the JSON data array
json_leads = []
for lead in leads:
    json_leads.append({
        "source": lead.get("source", ""),
        "company": lead.get("company", ""),
        "title": lead.get("title", ""),
        "location": lead.get("location", ""),
        "score": int(lead.get("score", 0)),
        "urgency": lead.get("urgency", "LOW"),
        "job_signals_score": int(lead.get("job_signals_score", 0)),
        "company_signals_score": int(lead.get("company_signals_score", 0)),
        "score_breakdown": lead.get("score_breakdown", ""),
        "linkedin_url": lead.get("linkedin_url", ""),
        "company_size": lead.get("company_size", ""),
        "funding_stage": lead.get("funding_stage", ""),
        "posting_date": lead.get("posting_date", ""),
        "job_url": lead.get("job_url", ""),
    })

# Replace the data in dashboard
json_str = json.dumps(json_leads, indent=2)
pattern = r'const LEADS_DATA\s*=\s*\[.*?\];'

# Use string find/replace instead of re.sub to avoid escape issues
marker_start = 'const ALL_LEADS = ['
start_idx = html.find(marker_start)
varname = 'ALL_LEADS'

if start_idx < 0:
    # Find any large JSON array
    for candidate in ['const data = [', 'var data = [', 'let data = [']:
        start_idx = html.find(candidate)
        if start_idx >= 0:
            varname = 'data'
            break

if start_idx >= 0:
    # Find the closing ];
    bracket_depth = 0
    search_start = html.index('[', start_idx)
    end_idx = search_start
    for i in range(search_start, len(html)):
        if html[i] == '[':
            bracket_depth += 1
        elif html[i] == ']':
            bracket_depth -= 1
            if bracket_depth == 0:
                end_idx = i + 1
                break
    # Include the trailing semicolon
    if end_idx < len(html) and html[end_idx] == ';':
        end_idx += 1

    new_html = html[:start_idx] + f'const {varname} = {json_str};' + html[end_idx:]
    print(f"Found data variable: {varname}")
else:
    print("ERROR: Could not find data variable in dashboard.html")
    new_html = html

with open(os.path.join(BASE_DIR, 'dashboard.html'), 'w', encoding='utf-8') as f:
    f.write(new_html)

print(f"Dashboard rebuilt with {len(json_leads)} company leads")
print(f"  Score 80+: {sum(1 for l in json_leads if l['score'] >= 80)}")
print(f"  Score 70+: {sum(1 for l in json_leads if l['score'] >= 70)}")
print(f"  HIGH urgency: {sum(1 for l in json_leads if l['urgency'] == 'HIGH')}")
