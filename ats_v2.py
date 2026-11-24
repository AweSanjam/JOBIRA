#!/usr/bin/env python3
"""
ATS v2 scorer for JOBIRA (built 2026-10-20).

ats_scorer.py (v1) scores a resume on its own: it never reads the job posting
and tops out at 80, so every tailored resume lands at 78-79. v2 scores the
resume AGAINST a posting, the way match-rate tools (Jobscan-style) and ATS
keyword filters do, and adds the recruiter-side checks from
reference/resume_v2/BEST_PRACTICES.md (Google X-Y-Z bullets, summary,
skills section, parse safety).

Usage:
  python3 ats_v2.py <resume.md> <posting.txt> [--title "Exact Job Title"] [--json]

Categories (100):
  Keyword match      35  hard skills / tools / role terms in the posting found in the resume
  Job title match    10  the posting's exact title in the headline or summary
  Keywords in context 10 matched keywords that also appear in Experience/Projects bullets
  Measurable results 10  share of bullets carrying a number (X-Y-Z "measured by Y")
  Bullet quality     10  action-verb start, X-Y-Z shape (what + how + result), length, no repeats
  Summary             8  3 sentences max, names the target title and top posting skills
  Skills section      7  hard skills only, grouped, sized, relevant to the posting
  Parse & format     10  standard headings, contact line, one-page length, dates
"""
import json
import re
import sys
from pathlib import Path

# canonical term -> variants (lower case). A posting term counts as matched when ANY
# variant is in the resume; "exact" also records whether the posting's own wording is there.
LEXICON = {
    # platforms / OS
    "Windows": ["windows", "windows 10", "windows 11"],
    "Windows Server": ["windows server"],
    "macOS": ["macos", "mac os", "mac computers", "mac and windows", "mac "],
    "Linux": ["linux"],
    "Active Directory": ["active directory", " ad "],
    "Microsoft 365": ["microsoft 365", "office 365", "ms office 365", "msoffice 365", "m365", "o365"],
    "Microsoft Office": ["microsoft office", "ms office", "office applications", "office apps", "office suite", "word, excel"],
    "SharePoint": ["sharepoint", "share point"],
    "Excel": ["excel"],
    "Google Workspace": ["google workspace", "g suite", "gsuite"],
    "Azure": ["azure"],
    "AWS": ["aws", "amazon web services"],
    "VMware": ["vmware"],
    "Virtualization": ["virtualization", "virtualized", "virtual machine", "virtualbox", " vms"],
    "SQL": ["sql"],
    "SQL Server": ["sql server"],
    "IIS": ["iis"],
    "APIs": ["api", "apis", "rest api"],
    "Python": ["python"],
    "PowerShell": ["powershell"],
    "Bash": ["bash"],
    "Scripting": ["scripting", "scripts", "script"],
    "Ansible": ["ansible"],
    "Elastic": ["elastic", "elasticsearch", "elk"],
    "Zendesk": ["zendesk"],
    "ServiceNow": ["servicenow"],
    "Jira": ["jira"],
    "ServiceDesk Plus": ["servicedesk plus"],
    "SaaS": ["saas", "software as a service", "cloud-based software", "web app", "web apps"],
    "CRM": ["crm", "salesforce"],
    # development (added 2026-10-20)
    "React": ["react"], "Redux": ["redux"], "TypeScript": ["typescript"], "JavaScript": ["javascript"],
    "Node.js": ["node.js", "nodejs"], "Next.js": ["next.js", "nextjs"], "Express": ["express.js", "expressjs", "express"],
    "PostgreSQL": ["postgresql", "postgres"], "MongoDB": ["mongodb"], "NoSQL": ["nosql"], "GraphQL": ["graphql"],
    "Git": ["git", "github"], "Flask": ["flask"], "HTML/CSS": ["html", "css"], "Docker": ["docker"],
    "Kubernetes": ["kubernetes"], "CI/CD": ["ci/cd", "continuous integration"], "Unit testing": ["unit test", "testing"],
    "Machine learning": ["machine learning", "ai/ml", " ml "], "Full stack": ["full stack", "full-stack"],
    "Front end": ["front end", "frontend", "front-end"], "Back end": ["back end", "backend", "back-end"],
    "Agile": ["agile", "scrum", "sprint"], "Code review": ["code review"], "Kotlin": ["kotlin"],
    "Prompt engineering": ["prompt engineering", "prompting", "system prompt"],
    # networking
    "TCP/IP": ["tcp/ip"],
    "DNS": ["dns"],
    "DHCP": ["dhcp"],
    "VLAN": ["vlan"],
    "LAN": ["lan", "local area network"],
    "Wi-Fi": ["wi-fi", "wifi", "wireless"],
    "Networking": ["networking", "network connectivity", "network troubleshooting", "network issues", "networks"],
    "Connectivity": ["connectivity"],
    "VPN": ["vpn"],
    "Firewall": ["firewall"],
    "Routers": ["router"],
    # hardware / endpoints
    "Hardware": ["hardware"],
    "Laptops": ["laptop"],
    "Desktops": ["desktop", "pcs", " pc "],
    "Printers": ["printer"],
    "Mobile devices": ["mobile device", "phones", "android"],
    "Peripherals": ["peripheral"],
    "Desk phones": ["desk phone", "voip"],
    "Device setup": ["device setup", "set up", "setup", "imaging", "deploy"],
    "Endpoint management": ["endpoint", "device management", "mdm", "intune"],
    "Patch management": ["patch", "software updates", "windows updates"],
    "Asset management": ["asset", "inventory"],
    # support practice
    "Technical support": ["technical support", "tech support"],
    "IT support": ["it support"],
    "Help desk": ["help desk", "helpdesk", "service desk"],
    "Deskside support": ["deskside", "in-person support", "in person", "onsite", "on-site"],
    "Remote support": ["remote support", "remotely"],
    "Customer service": ["customer service", "customer-facing", "customer facing", "customer support"],
    "Customer success": ["customer success"],
    "Troubleshooting": ["troubleshoot", "troubleshot"],
    "Diagnose": ["diagnos"],
    "Software troubleshooting": ["software issue", "software problem", "software troubleshooting"],
    "Ticketing system": ["ticketing", "tickets", "ticket system", "help desk software"],
    "Escalation": ["escalat"],
    "SLA": ["sla"],
    "Incident management": ["incident"],
    "Root cause analysis": ["root cause"],
    "Documentation": ["document", "documentation"],
    "Knowledge base": ["knowledge base", "knowledge article", "kb article", "help center", "faq"],
    "User accounts": ["user account", "end-user account", "accounts and access", "account setup"],
    "Access management": ["access management", "permissions", "identity and access", "iam", "access procedures"],
    "Onboarding": ["onboard"],
    "Offboarding": ["offboard"],
    "User training": ["training", "train users", "showed employees", "taught"],
    "Phone and email support": ["phone", "email"],
    "Chat support": ["chat"],
    "Self-service": ["self-service", "self service", "help themselves", "solve common problems themselves"],
    "Security": ["security"],
    "Vulnerability": ["vulnerabilit"],
    "Logs": ["logs", "log analy", "log file"],
    "Alerts": ["alert"],
    "Monitoring": ["monitoring", "monitor"],
    "Automation": ["automat"],
    "AI tools": ["ai-powered", "ai tools", "openai", "gpt", "claude", "ai-assisted", " ai "],
    "Data handling": ["safe handling of company data", "data protection", "data security"],
    "Backups": ["backup"],
    "Database": ["database"],
    "SCADA": ["scada"],
    "Software configuration": ["software configuration", "configur"],
    "Software upgrades": ["upgrade"],
    "Installation": ["install"],
    "Business applications": ["business application", "standard applications", "applications"],
    "Information systems": ["information systems", "information and communication technolog", "computer applications"],
    "Process improvement": ["process improvement", "improve it services", "improve"],
    "Conflict resolution": ["conflict resolution", "de-escalat", "deescalat"],
    "Multilingual": ["multilingual", "bilingual", "punjabi", "hindi"],
    "Bachelor's degree": ["bachelor"],
    "Diploma": ["diploma"],
}

# terms that only add noise when they come from generic posting boilerplate
WEAK = {"Phone and email support", "Business applications", "Process improvement", "Device setup",
        "Installation", "Software configuration", "Documentation", "Information systems"}

SOFT_WORDS = {"communication", "teamwork", "team player", "leadership", "problem-solving", "problem solving",
              "empathy", "time management", "hard-working", "motivated", "detail-oriented", "multitasking"}

ACTION_VERBS = set("""
achieved added administered advised analyzed answered applied assembled assisted automated built
captured checked cleaned coached collaborated compiled completed configured connected created cut
debugged delivered demonstrated deployed designed developed diagnosed directed documented drafted
educated enabled escalated evaluated explained facilitated fixed followed gathered guided handled
helped identified implemented imaged improved installed integrated kept launched led logged maintained
managed mapped migrated monitored onboarded operated optimized organized prepared presented processed
programmed provided published ran rebuilt recovered reduced repaired replaced reported resolved responded
restored reviewed rotated scheduled scripted served set shipped showed simplified sold solved standardized
supported taught tested tracked trained triaged troubleshot tuned updated upgraded verified walked wrote
serve handle explain follow keep greet answer process listened asked greeted served
""".split())

STD_HEADINGS = ["summary", "skills", "experience", "education"]


def norm(s):
    return " " + re.sub(r"\s+", " ", s.lower()) + " "


def sections(md):
    out, cur = {"_top": []}, "_top"
    for line in md.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip().lower()
            out[cur] = []
        else:
            out.setdefault(cur, []).append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def find_sec(secs, *names):
    for k, v in secs.items():
        if any(n in k for n in names):
            return v
    return ""


def bullets(text):
    return [l.strip()[2:].strip() for l in text.splitlines() if l.strip().startswith(("- ", "* "))]


_RX = {}


def rx(v):
    """Variant must start at a word boundary; short variants (<=5 chars) must also end at one
    (an optional plural s allowed), so 'excel' does not match 'excellent' and 'lan' not 'plan'."""
    if v not in _RX:
        core = re.escape(v.strip())
        end = r"s?(?![a-z0-9])" if len(v.strip()) <= 5 or v.strip() in {"excel", "chat", "patch"} else ""
        _RX[v] = re.compile(r"(?<![a-z0-9])" + core + end)
    return _RX[v]


def posting_terms(jd):
    """Canonical terms in the posting with a weight (frequency, capped, x0.5 for weak terms)."""
    j = norm(jd)
    terms = {}
    for canon, variants in LEXICON.items():
        hits = sum(len(rx(v).findall(j)) for v in variants)
        if hits:
            w = min(3, hits)
            terms[canon] = w * (0.5 if canon in WEAK else 1.0)
    return terms


def present(canon, text):
    t = norm(text)
    return any(rx(v).search(t) for v in LEXICON[canon])


def score(resume_md, jd, title=None):
    secs = sections(resume_md)
    rtext = resume_md
    top = secs.get("_top", "")
    summary = find_sec(secs, "summary")
    skills = find_sec(secs, "skill")
    exp = find_sec(secs, "experience")
    proj = find_sec(secs, "project")
    blts = bullets(exp) + bullets(proj)
    res, det = {}, {}

    # 1. keyword match (35)
    terms = posting_terms(jd)
    matched = {t: w for t, w in terms.items() if present(t, rtext)}
    tot = sum(terms.values()) or 1
    res["Keyword match"] = round(35 * sum(matched.values()) / tot, 1)
    missing = sorted((t for t in terms if t not in matched), key=lambda t: -terms[t])
    det["Keyword match"] = f"{len(matched)}/{len(terms)} posting terms; missing: {', '.join(missing[:12]) or 'none'}"

    # 2. job title (10)
    if not title:
        title = jd.strip().splitlines()[0].split("|")[0].strip()
    tl = norm(title).strip()
    head = norm(top + " " + summary)
    if tl and tl in head:
        res["Job title match"] = 10.0
    else:
        words = [w for w in re.findall(r"[a-z+#]+", tl) if w not in {"and", "the", "of", "i", "ii", "jr", "junior"}]
        hit = sum(1 for w in words if f" {w}" in head)
        res["Job title match"] = round(6 * hit / max(1, len(words)), 1)
    det["Job title match"] = f"target title: {title}"

    # 3. keywords in context (10)
    btext = " ".join(blts)
    ctx = [t for t in matched if present(t, btext)]
    res["Keywords in context"] = round(10 * len(ctx) / max(1, len(matched)), 1)
    det["Keywords in context"] = f"{len(ctx)}/{len(matched)} matched terms also used in bullets"

    # 4. measurable results (10)
    numbered = [b for b in blts if re.search(r"\d", b)]
    share = len(numbered) / max(1, len(blts))
    res["Measurable results"] = round(10 * min(1.0, share / 0.5), 1)
    det["Measurable results"] = f"{len(numbered)}/{len(blts)} bullets carry a number (full marks at 50%)"

    # 5. bullet quality (10)
    if blts:
        verbs = [re.findall(r"[a-z]+", b.lower())[:1] for b in blts]
        verbs = [v[0] if v else "" for v in verbs]
        verb_ok = sum(v in ACTION_VERBS for v in verbs) / len(blts)
        xyz = sum(bool(re.search(r"\b(with|using|through|by|via|in)\b", b, re.I)) and
                  bool(re.search(r"\b(so|so that|to keep|to cut|to help|cutting|reducing|improving|keeping|protecting|giving|letting|saving|which)\b", b, re.I))
                  for b in blts) / len(blts)
        length_ok = sum(10 <= len(b.split()) <= 32 for b in blts) / len(blts)
        repeats = sum(1 for a, b in zip(verbs, verbs[1:]) if a and a == b)
        dup = 0
        sets = [set(re.findall(r"[a-z]{4,}", b.lower())) for b in blts]
        for i in range(len(sets)):
            for k in range(i + 1, len(sets)):
                if sets[i] and sets[k] and len(sets[i] & sets[k]) / len(sets[i] | sets[k]) > 0.45:
                    dup += 1
        q = 3 * verb_ok + 4 * xyz + 3 * length_ok - repeats - 2 * dup
        res["Bullet quality"] = round(max(0, min(10, q)), 1)
        det["Bullet quality"] = (f"verb start {verb_ok:.0%}, X-Y-Z shape {xyz:.0%}, length ok {length_ok:.0%}, "
                                 f"same-verb repeats {repeats}, near-duplicate pairs {dup}")
    else:
        res["Bullet quality"] = 0.0
        det["Bullet quality"] = "no bullets"

    # 6. summary (8)
    s = 0.0
    if summary:
        sent = len(re.findall(r"[.!?](\s|$)", summary)) or 1
        s += 2 if sent <= 3 else 0
        s += 1 if len(summary.split()) <= 75 else 0
        core = [w for w in re.findall(r"[a-z]+", tl) if len(w) > 3 and w not in {"junior", "associate"}]
        s += 2 if any(w in norm(summary) for w in core) else 0
        sk = sum(1 for t in matched if present(t, summary))
        s += min(3, sk)
    res["Summary"] = s
    det["Summary"] = f"{len(summary.split())} words, {sum(1 for t in matched if present(t, summary))} posting terms" if summary else "missing"

    # 7. skills section (7)
    s = 0.0
    if skills:
        lines = [l for l in skills.splitlines() if l.strip()]
        items = [i.strip() for l in lines for i in re.split(r"[|,;]", l.split(":", 1)[-1]) if i.strip()]
        s += 2 if 8 <= len(items) <= 25 else (1 if items else 0)
        s += 1 if 1 <= len(lines) <= 5 else 0
        soft = [i for i in items if any(w in i.lower() for w in SOFT_WORDS)]
        s += 1 if not soft else 0
        rel = sum(1 for i in items if any(present(t, i) for t in terms)) / max(1, len(items))
        s += round(2 * min(1.0, rel / 0.6), 1)
        short = sum(1 for i in items if len(re.sub(r"\(.*?\)", "", i).split()) <= 4) / max(1, len(items))
        s += 1 if short >= 0.85 else 0
        det["Skills section"] = (f"{len(items)} items in {len(lines)} lines, {rel:.0%} tied to posting, "
                                 f"{short:.0%} short taxonomy-style names, soft-skill items {len(soft)}")
    else:
        det["Skills section"] = "missing"
    res["Skills section"] = s

    # 8. parse & format (10)
    s = 0.0
    keys = " ".join(k for k in secs)
    s += sum(1 for h in STD_HEADINGS if h in keys)
    s += 1 if re.search(r"@", top) else 0
    s += 1 if re.search(r"\d{3}.?\d{3}.?\d{4}", top) else 0
    words = len(re.sub(r"[#*|_-]", " ", resume_md).split())
    s += 2 if 350 <= words <= 700 else (1 if words <= 850 else 0)
    jobs = [l for l in exp.splitlines() if l.startswith("**")]
    dated = sum(bool(re.search(r"(19|20)\d\d", l)) for l in jobs)
    s += 2 if jobs and dated == len(jobs) else 0
    res["Parse & format"] = s
    det["Parse & format"] = f"{words} words, {dated}/{len(jobs)} jobs dated"

    total = round(sum(res.values()), 1)
    return {"total": total, "scores": res, "details": det, "matched": sorted(matched), "missing": missing}


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        sys.exit(1)
    title = None
    if "--title" in a:
        i = a.index("--title")
        title = a[i + 1]
        del a[i:i + 2]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    r = score(Path(a[0]).read_text(), Path(a[1]).read_text(), title)
    if as_json:
        print(json.dumps(r, indent=1))
        return
    print(f"ATS v2: {r['total']}/100  ({Path(a[0]).name})")
    for k, v in r["scores"].items():
        print(f"  {k:20} {v:5}  {r['details'][k]}")


if __name__ == "__main__":
    main()
