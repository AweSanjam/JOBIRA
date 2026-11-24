#!/usr/bin/env python3
"""
Skills-section engine for JOBIRA resumes (v2.1, 2026-10-20).

Builds the resume's Skills section from a posting instead of writing it by hand:
  * only skills in SKILL_DB, and every entry there is backed by ./skill_file (the "src" field)
  * standard category labels that ATS skill parsers and recruiters recognise
    (Technical Support, Operating Systems, Networking, Tools and Software, ...)
  * short, taxonomy-style item names (1 to 4 words), comma separated, so ATS skill
    extraction can normalise them; the posting's own wording is used where it is an alias
  * categories ordered by how much the posting asks for them; items inside by posting hits
  * honest qualifiers kept: (coursework), (projects), (self-study) per skill_file proficiency
  * 12 to 18 items in at most 4 lines + an optional Self-Directed Practice line
Research: reference/resume_v2/SKILLS_RESEARCH.md

  python3 skills_v2.py <posting.txt> [--family support|security|dev]   print the section + gaps
"""
import re
import sys

import ats_v2

# name, category, aliases (posting wording, lower case), qualifier, core-for families, skill_file source
SKILL_DB = [
 # Technical Support
 ("Technical Support", "Technical Support", ["technical support", "tech support", "first level support", "first-level"], "", "support security", "13 Surjit, 7"),
 ("Help Desk", "Technical Support", ["help desk", "helpdesk", "service desk"], "", "support security", "7 preferred_terms"),
 ("Troubleshooting", "Technical Support", ["troubleshoot", "diagnos", "problem solving"], "", "support security dev", "3 technical_operations"),
 ("Remote Support", "Technical Support", ["remote support", "remotely", "remote services"], "", "support", "13 confirmed: onsite & remote support"),
 ("Deskside Support", "Technical Support", ["deskside", "in-person support", "in-person assistance", "in-person requests", "on-site support", "onsite support"], "", "", "13 confirmed: onsite support"),
 ("Escalation", "Technical Support", ["escalat"], "", "support", "19.3 basic IT"),
 ("Incident Management", "Technical Support", ["incident"], "", "", "7 incident troubleshooting"),
 ("Root Cause Analysis", "Technical Support", ["root cause"], "", "", "3 technical_operations"),
 ("User Training", "Technical Support", ["training", "train users", "educat"], "", "support", "7 user onboarding/training"),
 ("User Onboarding", "Technical Support", ["onboard"], "", "", "7 user onboarding/training"),
 ("Documentation", "Technical Support", ["document"], "", "support", "3 technical documentation"),
 ("Knowledge Base Articles", "Technical Support", ["knowledge base", "knowledge article", "faq", "help center"], "", "", "10 KB bot; how-to guides"),
 ("Hardware Troubleshooting", "Technical Support", ["hardware"], "", "", "3 technical_operations"),
 ("Software Troubleshooting", "Technical Support", ["software issue", "software problem", "software troubleshooting", "software navigation"], "", "", "3 technical_operations"),
 ("Application Support", "Technical Support", ["application support", "business application", "standard applications"], "", "", "7 capabilities"),
 ("Android Device Testing (projects)", "Technical Support", ["mobile device", "android", "phones and peripherals"], "", "", "10 TeenyTune, Clocky tested on real devices"),
 ("Mobile App Testing (projects)", "Technical Support", ["manual test", "test case", "test plan", "quality assurance", "qa test", "software test", "app test", "testing"], "", "", "1 adjacent titles; 10 TeenyTune, Clocky, HeadSpace, BudPop tested on phone, tablet, watch over adb"),
 ("Bluetooth Devices (projects)", "Technical Support", ["bluetooth", "wireless audio", "earbuds", "headphones", "wearable"], "", "", "10 HeadSpace (RFCOMM), BudPop (connect events, battery)"),
 ("Android Debug Bridge (adb)", "Tools and Software", ["adb", "android debug bridge"], "", "", "10 all Android projects"),
 ("Printers and Peripherals", "Technical Support", ["printer", "peripheral"], "", "", "19.3 PC/printer help"),
 ("Device Setup", "Technical Support", ["device setup", "laptop", "workstation", "device", "deploy", "imaging", "set up computers"], "", "", "19.3 PC and account setup"),
 ("Software Installation and Configuration", "Technical Support", ["software installation", "install", "configur"], "", "", "13 Surjit; 19.3 setup"),
 # Customer Service (the one non-technical group the examples keep)
 ("Customer Service", "Customer Service", ["customer service", "customer-first", "customer experience", "customer satisfaction"], "", "support", "13 HP, IKEA, Kognitive"),
 ("Phone and Email Support", "Customer Service", ["phone", "email"], "", "", "13 confirmed: via phone and email"),
 ("Product Demonstrations", "Customer Service", ["product demo", "demonstration", "demos", "lead demo"], "", "", "13 HP"),
 ("English, Hindi, Punjabi", "Customer Service", ["multilingual", "bilingual", "language skills", "punjabi", "hindi"], "", "", "19.2"),
 # Operating Systems
 ("Windows", "Operating Systems", ["windows"], "", "support security", "6 Windows"),
 ("macOS", "Operating Systems", ["macos", "mac os", "mac computers", "mac and windows", "mac laptops", "windows and mac"], "(coursework)", "", "6 macOS foundational"),
 ("Linux", "Operating Systems", ["linux"], "", "security dev", "6 Linux"),
 # Tools and Software
 ("Ticketing Systems (ServiceDesk Plus)", "Tools and Software", ["ticket", "help desk software", "itsm", "servicenow", "jira", "zendesk", "crm", "case management", "support cases"], "", "support", "13 confirmed"),
 ("Microsoft 365", "Tools and Software", ["microsoft 365", "office 365", "ms office 365", "msoffice 365", "m365", "o365", "microsoft office", "ms office", "office applications", "office suite"], "", "support", "17 M365 1 yr"),
 ("Active Directory", "Tools and Software", ["active directory"], "", "", "17 M365 and AD 1 yr"),
 ("User Accounts and Access", "Tools and Software", ["user account", "end-user account", "access procedures", "account setup", "permission"], "", "", "19.3 account setup"),
 ("Excel", "Tools and Software", ["excel"], "", "", "3 data"),
 ("SQL", "Tools and Software", ["sql", "database"], "", "dev", "3 data"),
 ("Power BI", "Tools and Software", ["power bi", "dashboard", "reporting"], "", "", "10 monitoring dashboard"),
 # Networking
 ("TCP/IP", "Networking", ["tcp/ip"], "", "", "6 Networking"),
 ("LAN", "Networking", ["lan", "local area network"], "", "", "10 15-system LAN"),
 ("Routers", "Networking", ["router"], "", "", "10 2 routers"),
 ("Network Troubleshooting", "Networking", ["network", "connectivity"], "", "support", "6 Networking"),
 ("DNS", "Networking", ["dns"], "(coursework)", "", "11 Bits and Bytes of Computer Networking"),
 ("Firewall Basics", "Networking", ["firewall"], "", "", "10 Network Config project"),
 ("FTP", "Networking", ["ftp", "file transfer", "uploading/downloading files", "file sharing"], "", "", "10 Network Config project"),
 # Security
 ("Access Control and Permissions", "Security", ["access control", "rbac", "identity and access", "iam", "permissions"], "", "security", "3 security; 6 Linux permissions"),
 ("Networking Fundamentals", "Security", ["networking"], "", "", "6 Networking; Bits and Bytes"),
 ("Log Review and Alerts", "Security", ["security logs", "logs and alerts", "log review", "log analy", "alerts", "siem", "monitoring"], "", "security", "10 log analyzer, monitoring dashboard"),
 ("Encryption", "Security", ["encrypt", "data protection", "safe handling of company data", "data security"], "", "", "3 security"),
 ("Security Fundamentals", "Security", ["security"], "", "security", "11 Google IT Security"),
 # Cloud, Scripting and AI
 ("Python", "Scripting and Cloud", ["python", "scripting"], "", "security dev", "8, 17 Python 2 yrs"),
 ("PowerShell", "Scripting and Cloud", ["powershell"], "", "", "3 automation"),
 ("Bash", "Scripting and Cloud", ["bash", "shell"], "", "", "3 automation"),
 ("Microsoft Azure", "Scripting and Cloud", ["azure"], "", "", "5, 10 Azure gallery"),
 ("AWS", "Scripting and Cloud", ["aws", "amazon web services"], "", "", "5"),
 ("REST APIs", "Scripting and Cloud", ["api"], "", "dev", "10 RentAVilla, OpenAI API"),
 ("SaaS Web Apps", "Scripting and Cloud", ["saas", "web app", "cloud-based software", "web browsers"], "(projects)", "", "10 resume builder, RentAVilla"),
 ("OpenAI API", "AI Tools", ["openai", "gpt", "llm", "generative ai", "ai mindset", "ai api", "ai models", "prompt engineering"], "", "", "10 several projects"),
 ("Prompt Engineering", "AI Tools", ["prompt engineering", "prompting", "system prompt"], "(projects)", "", "10 JOBIRA prompt/rule design"),
 ("Machine Learning", "AI Tools", ["machine learning", "ai/ml", "ml concepts", " ml "], "(coursework)", "", "9, 10 bike regression; Douglas ML coursework"),
 ("Claude Code", "AI Tools", ["claude", "ai coding", "ai agent", "agentic"], "", "", "10 JOBIRA"),
 ("AI-Assisted Troubleshooting", "AI Tools", ["ai-powered", "ai-assisted", "leverage ai", "leveraging ai", "ai mindset", "using ai", "ai to support"], "", "", "10 monitoring auto-responder"),
 # Development (skill_file 3 development; projects in 10). Family "dev" pulls these in.
 ("Python", "Languages and Frameworks", ["python"], "", "dev", "8, 17"),
 ("JavaScript", "Languages and Frameworks", ["javascript"], "", "dev", "3 development"),
 ("TypeScript", "Languages and Frameworks", ["typescript"], "", "dev", "10 RentAVilla"),
 ("React", "Languages and Frameworks", ["react"], "", "dev", "10 RentAVilla, resume builder"),
 ("Next.js", "Languages and Frameworks", ["next.js", "nextjs"], "", "", "10 resume builder"),
 ("Node.js", "Languages and Frameworks", ["node.js", "node", "backend", "back end"], "", "dev", "10 RentAVilla, resume builder"),
 ("Express", "Languages and Frameworks", ["express"], "", "", "10 RentAVilla"),
 ("Flask", "Languages and Frameworks", ["flask"], "", "", "10 Cloud Web App"),
 ("HTML and CSS", "Languages and Frameworks", ["html", "css", "front end", "frontend", "user experiences"], "", "", "3 development"),
 ("Kotlin", "Languages and Frameworks", ["kotlin", "android"], "(projects)", "", "10 TeenyTune, Clocky, BudPop, HeadSpace, Transi-Time"),
 ("Jetpack Compose", "Languages and Frameworks", ["jetpack compose", "compose"], "(projects)", "", "10 TeenyTune, Clocky, HeadSpace"),
 ("Wear OS", "Languages and Frameworks", ["wear os", "smartwatch", "wearable"], "(projects)", "", "10 TeenyTune, Clocky, Transi-Time, HeadSpace"),
 ("Unit Testing (Robolectric)", "Languages and Frameworks", ["unit test", "automated test", "robolectric", "test automation"], "(projects)", "", "10 BudPop, HeadSpace frame-render tests"),
 ("PostgreSQL", "Databases and Cloud", ["postgres"], "", "dev", "10 RentAVilla"),
 ("MongoDB", "Databases and Cloud", ["mongodb", "nosql"], "", "", "10 resume builder"),
 ("AWS", "Databases and Cloud", ["aws", "amazon web services"], "", "", "5"),
 ("Git and GitHub", "Databases and Cloud", ["git", "github", "code review", "version control"], "", "dev", "10 RentAVilla, TeenyTune"),
 ("Agile and Scrum", "Databases and Cloud", ["scrum", "sprint", "agile methodolog", "agile development", "release planning"], "", "", "10 RentAVilla"),
 # Self-directed (skill_file 6A): separate line, never mixed in
 ("ELK Stack (Elastic)", "Self-Directed Practice", ["elastic", "elk", "kibana"], "", "", "6A"),
 ("Docker", "Self-Directed Practice", ["docker", "container"], "", "", "6A"),
 ("Terraform", "Self-Directed Practice", ["terraform", "infrastructure as code"], "", "", "6A"),
 ("Kubernetes", "Self-Directed Practice", ["kubernetes", "k8s"], "", "", "6A"),
]

CAT_ORDER_DEFAULT = ["Languages and Frameworks", "Databases and Cloud", "Technical Support", "Customer Service", "Operating Systems", "Tools and Software",
                     "Networking", "Security", "Scripting and Cloud", "AI Tools"]


# when the posting writes a skill differently (exact-term rule), show the posting's form (exact-term rule)
ALIAS_SHOW = {"Microsoft 365": [("msoffice 365", "Microsoft 365 (MS Office 365)"), ("office 365", "Microsoft 365 (Office 365)"), ("microsoft office", "Microsoft Office (Microsoft 365)"), ("office applications", "Microsoft Office (Microsoft 365)"), ("office suite", "Microsoft Office Suite (Microsoft 365)")],
              "Device Setup": [("laptop", "Laptop and PC Setup")],
              "Help Desk": [("helpdesk", "Helpdesk"), ("service desk", "Service Desk")],
              "Customer Service": [("customer experience", "Customer Experience")],
              "Ticketing Systems (ServiceDesk Plus)": [("case management", "Case Management (ServiceDesk Plus)")]}


def show(x, jd_norm):
    for alias, text in ALIAS_SHOW.get(x["name"], []):
        if ats_v2.rx(alias).search(jd_norm):
            return f"{text} {x['qual']}".strip()
    return f"{x['name']} {x['qual']}".strip()


def _hits(alias_list, jd_norm):
    return sum(len(ats_v2.rx(a).findall(jd_norm)) for a in alias_list)


def select(jd, family="support", min_items=12, max_items=20, max_lines=4, extra=None, drop=None):
    """Return (lines, chosen, gaps). extra/drop: skill names to force in or out."""
    j = ats_v2.norm(jd)
    scored, seen = [], set()
    for name, cat, aliases, qual, core, src in SKILL_DB:
        dev_group = cat in ("Languages and Frameworks", "Databases and Cloud")
        if (family == "dev") != dev_group and name in ("Python", "AWS"):
            continue  # one Python/AWS entry per resume: dev groups for dev roles, scripting group otherwise
        if name in seen:
            continue
        h = _hits(aliases + [name.lower()], j)
        if (drop and name in drop):
            continue
        if h or (extra and name in extra) or (family in core.split()):
            scored.append(dict(name=name, cat=cat, hits=h, qual=qual, core=family in core.split(), src=src))
            seen.add(name)
    # posting-matched first, then core fill
    if family == "dev":  # developer resumes keep support/customer items only when the posting stresses them
        scored = [x for x in scored if x["cat"] != "Customer Service" and (x["cat"] != "Technical Support" or x["hits"] >= 3)]
    # named tools and platforms outrank generic process words at equal posting hits
    for x in scored:
        x["prio"] = x["hits"] + (1.5 if x["cat"] not in ("Technical Support", "Customer Service") else 0)
    matched = sorted([s for s in scored if s["hits"]], key=lambda s: -s["prio"])
    filler = [s for s in scored if not s["hits"]]
    chosen = []
    main = [s for s in matched if s["cat"] != "Self-Directed Practice"]
    selfd = [s for s in matched if s["cat"] == "Self-Directed Practice"]
    for s in main:
        if len(chosen) < max_items:
            chosen.append(s)
    for x in filler:  # extras the job asks for are always added (they still need a SKILL_DB entry)
        if extra and x["name"] in extra and x not in chosen:
            chosen.append(x)
    # keep at most 2 of the troubleshooting family (generic first), then fill to min_items with core skills
    fam = [x for x in chosen if "Troubleshooting" in x["name"] and x["cat"] == "Technical Support"]
    for x in sorted(fam, key=lambda x: (x["name"] != "Troubleshooting", -x["hits"]))[2:]:
        chosen.remove(x)
    for s in filler:
        if s in chosen:
            continue
        if len(chosen) < min_items and s["cat"] != "Self-Directed Practice" and not (
                "Troubleshooting" in s["name"] and s["name"] != "Troubleshooting" and
                sum("Troubleshooting" in x["name"] for x in chosen) >= 2):
            chosen.append(s)
    cats = {}
    for s_ in chosen:
        cats.setdefault(s_["cat"], []).append(s_)
    merge_into = {"Databases and Cloud": "Languages and Frameworks", "Operating Systems": "Tools and Software", "Tools and Software": "Technical Support",
                  "Networking": "Technical Support", "Security": "Networking", "AI Tools": "Scripting and Cloud",
                  "Scripting and Cloud": "Tools and Software", "Customer Service": "Technical Support"}

    merged = {}

    def weight(c):
        return sum(x["hits"] for x in cats[c])

    # merge single-item lines and lines beyond max_lines into their nearest kept category
    while len(cats) > 1 and (len(cats) > max_lines or any(len(v) == 1 for v in cats.values())):
        small = min(cats, key=lambda c: (len(cats[c]) > 1, weight(c)))
        tgt = merge_into.get(small)
        while tgt and tgt not in cats:
            tgt = merge_into.get(tgt)
        if not tgt or tgt == small:
            pref = [c for c in ("Tools and Software", "Scripting and Cloud", "Languages and Frameworks", "Operating Systems") if c in cats and c != small]
            tgt = pref[0] if pref else max((c for c in cats if c != small), key=weight)
        cats[tgt] += cats.pop(small)
        merged.setdefault(tgt, {tgt}).update(merged.pop(small, {small}))
    # at most 7 items per line: drop the lowest-hit extras
    for c in cats:
        cats[c].sort(key=lambda x: -x["prio"])
        for x in cats[c][8:]:
            chosen.remove(x)
        cats[c] = cats[c][:8]
    keep = sorted(cats, key=lambda c: (-weight(c), CAT_ORDER_DEFAULT.index(c) if c in CAT_ORDER_DEFAULT else 99))
    lines = []
    NAMES = {frozenset({"Networking", "Security"}): "Networking and Security",
             frozenset({"Tools and Software", "Operating Systems"}): "Systems and Tools",
             frozenset({"Scripting and Cloud", "AI Tools"}): "Scripting, Cloud and AI",
             frozenset({"Tools and Software", "Scripting and Cloud"}): "Tools, Scripting and Cloud",
             frozenset({"Tools and Software", "Scripting and Cloud", "AI Tools"}): "Tools, Scripting and AI",
             frozenset({"Technical Support", "Customer Service"}): "Technical and Customer Support",
             frozenset({"Operating Systems", "Tools and Software", "Scripting and Cloud"}): "Systems, Tools and Scripting"}

    def lab(c):
        m = frozenset(merged.get(c, {c}))
        return NAMES.get(m, c)
    label = {c: lab(c) for c in cats}
    for c in keep:
        lines.append(f"{label.get(c, c)}: " + ", ".join(show(x, j) for x in cats[c]))
    if selfd:
        lines.append("Self-Directed Practice: " + ", ".join(s["name"] for s in selfd))
    # gaps: posting terms (ats_v2 lexicon) that no SKILL_DB entry covers
    known = " ".join(a for _, _, al, _, _, _ in SKILL_DB for a in al).lower()
    gaps = [t for t in ats_v2.posting_terms(jd)
            if not any(ats_v2.rx(v).search(" " + known + " ") for v in ats_v2.LEXICON[t])]
    return lines, chosen, gaps


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    fam = a[a.index("--family") + 1] if "--family" in a else "support"
    lines, chosen, gaps = select(open(a[0]).read(), fam)
    print("## Skills\n")
    print("\n\n".join(lines))
    print(f"\n{len(chosen)} items. Not on file (gaps): {', '.join(gaps) or 'none'}")


if __name__ == "__main__":
    main()
