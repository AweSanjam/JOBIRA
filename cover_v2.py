#!/usr/bin/env python3
"""
Cover letter v2 for JOBIRA (built 2026-10-20): builder + checker.

Research and rules: reference/cover_v2/COVER_RULES.md. Facts come only from ./skill_file;
style follows RESUME_RULES.md rules 1 and 3 (no em/en dashes, no banned words).

Shape (skill_file 18 length kept: 120 to 160 words in the body, 2 short paragraphs + a 1-line close):
  P1  HOOK      the posting's need in its own words + the strongest matching proof (X-Y-Z) + the role name
  P2  BRIDGE    reframes the path (IT support -> Canadian customer-facing tech roles -> ICT diploma + AI
                projects) as preparation for THIS job, answers the likely concern head-on, and gives one
                proof point the resume summary does not already lead with + one specific company fact
  CLOSE         a specific ask tied to a posting duty (not "I'd welcome the opportunity")

  python3 cover_v2.py check <cover.md> <posting.txt> [--resume resume.md] [--company X] [--title Y]
"""
import re
import sys

import ats_v2

NAME_BLOCK = ("# Your Name\n\nyour.phone | your.email@example.com | "
              "linkedin.com/in/your-profile\n\n{date}\n\n")
BANNED = ["spearheaded", "leveraged", "dynamic", "results-driven", "passionate", "synergy", "seamless", "robust",
          "cutting-edge", "utilize", "proven track record", "detail-oriented", "orchestrated", "championed"]
FILLER = ["i am excited", "i'm excited", "i believe i would be", "great fit", "perfect fit", "to whom it may concern",
          "i am writing to", "i'm writing to", "i'm applying for", "i am applying for", "dream job",
          "i would be a valuable", "hit the ground running", "team player"]
GENERIC_CLOSE = ["i'd welcome the opportunity to discuss further", "i look forward to hearing from you",
                 "thank you for your consideration"]


def build(company, title, hook, bridge, ask, date, salutation=None):
    """Assemble the letter. hook/bridge/ask are written per job from skill_file facts."""
    s = NAME_BLOCK.format(date=date)
    s += f"Hiring Team, {company}\n\n**Re: {title}**\n\n{salutation or 'Dear ' + company + ' Hiring Team'},\n\n"
    hook = re.sub(r"\bis hiring a (?=[AEIOUaeiou]|IT\b|HR\b|SQL\b)", "is hiring an ", hook)  # 2026-11-08: "a IT" fix
    s += hook.strip() + "\n\n" + bridge.strip() + "\n\n" + ask.strip() + "\n\nSincerely,\n\nYour Name\n"
    return s


def body_of(md):
    m = re.search(r"Dear[^\n]*,\n\n(.*?)\n\nSincerely", md, re.S)
    return m.group(1).strip() if m else md


def sentences(t):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if x.strip()]


def check(md, jd, resume_md="", company="", title=""):
    """Score 0-100 with a list of problems. Each failed rule costs its points."""
    body = body_of(md)
    paras = [p for p in body.split("\n\n") if p.strip()]
    low = body.lower()
    words = len(body.split())
    out, pts = [], 0

    def rule(ok, p, msg):
        nonlocal pts
        if ok:
            pts += p
        else:
            out.append(msg)

    rule(120 <= words <= 160, 15, f"body is {words} words (target 120 to 160)")
    rule(len(paras) <= 3, 5, f"{len(paras)} paragraphs (2 + close)")
    bad = [b for b in BANNED if b in low] + (["dash"] if ("—" in body or "–" in body) else [])
    rule(not bad, 10, f"style: {bad}")
    fil = [f for f in FILLER if f in low]
    rule(not fil, 10, f"filler phrases: {fil}")
    rule(not company or company.lower().split()[0] in low, 5, "company not named in the body")
    tw = [w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 3 and w not in {"junior", "associate"}]
    rule(not tw or all(w in low for w in tw[:2]), 5, "role title not named in the body")
    terms = ats_v2.posting_terms(jd)
    hit = [t for t in terms if ats_v2.present(t, body)]
    rule(len(hit) >= 4, 10, f"only {len(hit)} posting keywords in the letter (want 4+)")
    first = sentences(paras[0])[0] if paras else ""
    rule(bool(re.search(r"\d", paras[0])) if paras else False, 10, "opening paragraph has no concrete number or proof")
    rule(not re.match(r"(i'm|i am) (applying|writing|interested)", first.lower()), 5, "opens with a bare 'I'm applying/writing'")
    i_starts = sum(1 for s in sentences(body) if re.match(r"(i|i'm|i've|i'd)\b", s.lower()))
    rule(i_starts <= 3, 5, f"{i_starts} sentences start with I (max 3)")
    close = paras[-1].lower() if paras else ""
    rule(not any(g in close for g in GENERIC_CLOSE) and len(close.split()) <= 30, 10,
         "close is generic; make a specific ask tied to a posting duty")
    rule(any(ats_v2.present(t, close) for t in terms) or company.lower().split()[0] in close if company else True, 5,
         "close does not name a posting duty or the company")
    if resume_md:
        rb = [b for b in ats_v2.bullets(resume_md)]
        rs = [set(re.findall(r"[a-z]{4,}", b.lower())) for b in rb]
        copied = 0
        for s in sentences(body):
            ss = set(re.findall(r"[a-z]{4,}", s.lower()))
            if ss and any(len(ss & r) / len(ss | r) > 0.5 for r in rs if r):
                copied += 1
        rule(copied == 0, 5, f"{copied} sentence(s) copied from resume bullets")
    else:
        pts += 5
    return {"score": pts, "words": words, "keywords": hit, "problems": out}


def main():
    a = sys.argv[1:]
    if len(a) < 3 or a[0] != "check":
        print(__doc__)
        sys.exit(1)
    opts = {}
    for k in ("--resume", "--company", "--title"):
        if k in a:
            i = a.index(k)
            opts[k] = a[i + 1]
            del a[i:i + 2]
    md, jd = open(a[1]).read(), open(a[2]).read()
    r = check(md, jd, open(opts["--resume"]).read() if "--resume" in opts else "",
              opts.get("--company", ""), opts.get("--title", ""))
    print(f"Cover v2 check: {r['score']}/100, {r['words']} words, keywords: {', '.join(r['keywords'])}")
    for p in r["problems"]:
        print("  -", p)


if __name__ == "__main__":
    main()
