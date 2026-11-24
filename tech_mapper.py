#!/usr/bin/env python3
"""
Tech Mapper for JOBIRA ATS Pipeline
Identifies equivalent/interchangeable technologies and suggests additions
to improve ATS keyword density for related tools.
"""

import sys
from pathlib import Path

# Technology equivalence groups: tools treated as interchangeable skills
TECH_GROUPS = {
    "ITSM_TICKETING": {
        "tools": ["ServiceDesk Plus", "Jira", "Jira Service Desk", "ServiceNow", "ZenDesk", "Freshdesk"],
        "aliases": ["Ticket System", "Ticketing", "IT Service Management", "Help Desk", "ITSM"],
        "reasoning": "All are enterprise ITSM/ticketing platforms with similar core concepts (ticket triage, SLA tracking, escalation)"
    },
    "CLOUD_PLATFORMS": {
        "tools": ["AWS", "Azure", "Google Cloud", "GCP"],
        "aliases": ["Cloud", "Cloud Platform", "Cloud Infrastructure"],
        "reasoning": "All provide similar cloud infrastructure services (compute, storage, networking, databases)"
    },
    "OPERATING_SYSTEMS": {
        "tools": ["Windows", "Linux", "macOS"],
        "aliases": ["Operating System", "OS", "System Administration"],
        "reasoning": "Core OS administration skills transfer across platforms"
    },
    "SCRIPTING_LANGUAGES": {
        "tools": ["Python", "Bash", "PowerShell"],
        "aliases": ["Scripting", "Automation", "System Automation"],
        "reasoning": "All are used for system automation and infrastructure scripting"
    },
    "MONITORING": {
        "tools": ["Datadog", "New Relic", "CloudWatch", "Splunk", "Prometheus"],
        "aliases": ["Monitoring", "Observability", "Log Analysis", "System Monitoring"],
        "reasoning": "All provide infrastructure monitoring and log analysis capabilities"
    },
    "CONTAINERIZATION": {
        "tools": ["Docker", "Kubernetes", "ECS", "EKS"],
        "aliases": ["Container", "Orchestration", "Container Platform"],
        "reasoning": "Container orchestration and deployment platforms"
    }
}

def find_tech_group(tech_name):
    """Find which equivalence group a technology belongs to."""
    tech_lower = tech_name.lower()

    for group_name, group_data in TECH_GROUPS.items():
        # Check tools
        for tool in group_data['tools']:
            if tech_lower in tool.lower() or tool.lower() in tech_lower:
                return group_name, group_data
        # Check aliases
        for alias in group_data['aliases']:
            if tech_lower == alias.lower():
                return group_name, group_data

    return None, None

def suggest_equivalent_techs(found_tech):
    """Suggest equivalent technologies when one is found in a resume."""
    group_name, group_data = find_tech_group(found_tech)

    if not group_name:
        return []

    suggestions = []
    for tool in group_data['tools']:
        if tool.lower() != found_tech.lower():
            suggestions.append({
                'tool': tool,
                'group': group_name,
                'reasoning': group_data['reasoning']
            })

    return suggestions

def extract_technologies(resume_text):
    """Extract mentioned technologies from resume."""
    found_techs = set()

    # Look for known technologies in the text
    all_tools = []
    for group_data in TECH_GROUPS.values():
        all_tools.extend(group_data['tools'])
        all_tools.extend(group_data['aliases'])

    resume_lower = resume_text.lower()

    for tech in all_tools:
        if tech.lower() in resume_lower:
            found_techs.add(tech)

    return found_techs

def print_tech_mapping_report(resume_path):
    """Analyze resume technologies and suggest equivalents."""
    with open(resume_path, 'r') as f:
        resume_text = f.read()

    found_techs = extract_technologies(resume_text)

    print(f"\n{'='*60}")
    print(f"Technology Mapping Report: {Path(resume_path).name}")
    print(f"{'='*60}\n")

    if not found_techs:
        print("No tracked technologies found in resume.\n")
        return

    print(f"Detected Technologies ({len(found_techs)}):")
    for tech in sorted(found_techs):
        print(f"  ✓ {tech}")

    print(f"\n\nEquivalence Suggestions (to boost ATS keyword density):")
    print("-" * 60)

    tech_groups_seen = set()
    for tech in sorted(found_techs):
        suggestions = suggest_equivalent_techs(tech)
        if suggestions and suggestions[0]['group'] not in tech_groups_seen:
            group = suggestions[0]['group']
            tech_groups_seen.add(group)
            group_data = TECH_GROUPS[group]

            print(f"\n[{group}]")
            print(f"  Found: {tech}")
            print(f"  Reasoning: {group_data['reasoning']}")
            print(f"  Can frame as equivalent (treat as transferable skill):")
            for sugg in suggestions[:2]:  # Show top 2 suggestions
                print(f"    - {sugg['tool']}")

    print(f"\n{'='*60}\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 tech_mapper.py <resume.md>")
        sys.exit(1)

    resume_path = sys.argv[1]
    if not Path(resume_path).exists():
        print(f"Error: {resume_path} not found")
        sys.exit(1)

    print_tech_mapping_report(resume_path)
