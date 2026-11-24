#!/usr/bin/env python3
"""
PoC ATS Resume Scorer for JOBIRA
Scores resume Markdown files (0-100) and identifies improvement gaps.
Supports tech-mapping to treat equivalent tools as transferable skills.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# Tech equivalence mapping: tools that should be treated as interchangeable ITSM skills
TECH_EQUIVALENCIES = {
    "ITSM_TICKETING": {
        "ServiceDesk Plus", "Jira", "Jira Service Desk", "ServiceNow",
        "Ticketing", "IT Service Management", "Help Desk", "Ticket System"
    },
    "CLOUD_PLATFORMS": {
        "AWS", "Azure", "Google Cloud", "GCP", "Cloud"
    },
    "OS": {
        "Windows", "Linux", "macOS", "Operating System"
    }
}

def read_resume(resume_path):
    """Load resume markdown."""
    with open(resume_path, 'r') as f:
        return f.read()

def extract_sections(resume_text):
    """Extract major sections from resume."""
    sections = {}
    current_section = None
    current_content = []

    for line in resume_text.split('\n'):
        if line.startswith('## '):
            if current_section:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = line[3:].strip()
            current_content = []
        elif current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_content).strip()

    return sections

# RESUME_RULES.md (2026-10-12) uses the headings "Skills" and "Projects";
# older resumes use "Technical Skills" / "Relevant Projects". Accept both.
SECTION_ALIASES = {'Technical Skills': 'Skills', 'Relevant Projects': 'Projects'}

def get_section(sections, name):
    return sections.get(name) or sections.get(SECTION_ALIASES.get(name, ''), '')

def score_completeness(sections):
    """Score presence of key sections (0-20)."""
    expected_sections = {
        'Summary': 5,
        'Technical Skills': 5,
        'Experience': 5,
        'Relevant Projects': 3,
        'Education': 2
    }

    score = 0
    for section, points in expected_sections.items():
        if len(get_section(sections, section).strip()) > 20:
            score += points

    return score, expected_sections, sections

def score_metrics_and_evidence(sections):
    """Score presence of concrete metrics/numbers (0-15)."""
    score = 0
    metrics_found = []

    experience_text = sections.get('Experience', '')

    # Look for numbers (percentages, years, counts, etc.)
    numbers = re.findall(r'(\d+%|\d+\+?\s*(years?|months?|tickets?|endpoints?|systems?|pages?|instances?|results?|time|achievement))',
                        experience_text, re.IGNORECASE)

    if numbers:
        score += min(15, len(numbers) * 3)  # Cap at 15 points
        metrics_found = [m[0] for m in numbers[:5]]

    return score, metrics_found

def score_skills_presence(sections):
    """Score keyword density from job posting against resume (0-20)."""
    skills_section = get_section(sections, 'Technical Skills')
    experience_section = sections.get('Experience', '')

    resume_text = (skills_section + ' ' + experience_section).lower()

    # Common IT ops keywords (expanded to include support/hardware roles)
    keywords = {
        'Windows': 2, 'Linux': 2, 'Active Directory': 3, 'Network': 2,
        'Troubleshooting': 2, 'Support': 1, 'Cloud': 2, 'Azure': 2, 'AWS': 2,
        'PowerShell': 2, 'Python': 2, 'Bash': 1, 'Security': 2,
        'Monitoring': 2, 'Automation': 2, 'Infrastructure': 2, 'Systems': 1,
        'Hardware': 2, 'Printer': 2, 'Connectivity': 1, 'Wi-Fi': 1, 'IT Service': 2,
        'Help Desk': 2, 'Ticket': 1, 'SLA': 2, 'Incident': 1, 'Router': 1
    }

    score = 0
    found_keywords = {}

    for keyword, points in keywords.items():
        if keyword.lower() in resume_text:
            score += points
            found_keywords[keyword] = True

    return min(20, score), found_keywords

def score_project_relevance(sections):
    """Score presence and relevance of projects (0-15)."""
    projects_section = get_section(sections, 'Relevant Projects')

    if not projects_section or len(projects_section) < 50:
        return 0, 0

    # Count project bullets
    project_lines = [l.strip() for l in projects_section.split('\n')
                    if l.strip().startswith('**')]

    score = min(15, len(project_lines) * 5)
    return score, len(project_lines)

def score_format_and_clarity(sections):
    """Score formatting, clarity, readability (0-10)."""
    score = 10
    issues = []

    # Check for excessive length
    for section, content in sections.items():
        if len(content) > 1000:
            score -= 1
            issues.append(f"{section} is quite long")

    # Check for typos (simple heuristic)
    all_text = ' '.join(sections.values()).lower()
    typo_patterns = [
        (r'\b(teh|thier|recieve|occured|reccomend)\b', "Possible typo"),
    ]

    for pattern, msg in typo_patterns:
        if re.search(pattern, all_text):
            score -= 1
            issues.append(msg)

    return max(0, score), issues

def calculate_ats_score(resume_path):
    """Calculate overall ATS score (0-100)."""
    resume_text = read_resume(resume_path)
    sections = extract_sections(resume_text)

    scores = {}
    details = {}

    # Completeness (0-20)
    completeness_score, expected, _ = score_completeness(sections)
    scores['Completeness'] = completeness_score
    details['Completeness'] = f"{completeness_score}/20 — sections present"

    # Metrics & Evidence (0-15)
    metrics_score, metrics_found = score_metrics_and_evidence(sections)
    scores['Metrics'] = metrics_score
    details['Metrics'] = f"{metrics_score}/15 — {len(metrics_found)} quantifiable results found"

    # Skills Presence (0-20)
    skills_score, found_kw = score_skills_presence(sections)
    scores['Skills'] = skills_score
    details['Skills'] = f"{skills_score}/20 — {len(found_kw)} key IT ops keywords found"

    # Projects (0-15)
    projects_score, project_count = score_project_relevance(sections)
    scores['Projects'] = projects_score
    details['Projects'] = f"{projects_score}/15 — {project_count} relevant projects"

    # Format (0-10)
    format_score, format_issues = score_format_and_clarity(sections)
    scores['Format'] = format_score
    details['Format'] = f"{format_score}/10 — professional formatting"

    total_score = sum(scores.values())

    return {
        'total': total_score,
        'scores': scores,
        'details': details,
        'sections_found': list(sections.keys()),
        'metrics_sample': metrics_found[:3] if metrics_found else [],
        'keywords_sample': list(found_kw.keys())[:5] if found_kw else [],
    }

def print_ats_report(resume_path, ats_result):
    """Print human-readable ATS score report."""
    print(f"\n{'='*60}")
    print(f"ATS Score Report: {Path(resume_path).name}")
    print(f"{'='*60}\n")

    print(f"Overall ATS Score: {ats_result['total']}/100")
    if ats_result['total'] >= 75:
        print("Status: ✓ ACCEPTABLE (≥75) — Ready for iteration if desired")
    else:
        print(f"Status: ⚠ BELOW THRESHOLD (<75) — Recommend iteration")

    print(f"\nBreakdown:")
    for category, score in ats_result['scores'].items():
        detail = ats_result['details'][category]
        print(f"  {category:15} {score:2}  — {detail}")

    print(f"\nSections Found: {', '.join(ats_result['sections_found']) if ats_result['sections_found'] else 'None'}")

    if ats_result['keywords_sample']:
        print(f"\nKey IT Ops Keywords Detected: {', '.join(ats_result['keywords_sample'])}")

    if ats_result['metrics_sample']:
        print(f"\nQuantifiable Results Sample: {', '.join(ats_result['metrics_sample'])}")

    print(f"\n{'='*60}\n")

    return ats_result['total'] >= 75  # Return True if acceptable

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 ats_scorer.py <resume.md>")
        sys.exit(1)

    resume_path = sys.argv[1]
    if not Path(resume_path).exists():
        print(f"Error: {resume_path} not found")
        sys.exit(1)

    result = calculate_ats_score(resume_path)
    acceptable = print_ats_report(resume_path, result)

    # Exit with code 0 if acceptable, 1 if below threshold
    sys.exit(0 if acceptable else 1)
