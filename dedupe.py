#!/usr/bin/env python3
"""Check scraped candidates against the tracker before any materials are made
(CLAUDE.md pipeline step 3).

Reads "Company | Job Title" lines on stdin and prints one verdict per line:
    DUP   this company + title is already tracked (any status) -- skip it
    NEW*  new role at a company already in the tracker -- worth a closer look
    NEW   company not seen before

Matching ignores case, spacing and punctuation, so "Acme Inc." / "ACME, Inc"
and "IT Support Analyst II" / "IT Support Analyst - II" count as the same.

    printf 'BGIS | Service Desk Analyst\n' | python3 dedupe.py
"""
import re
import sys

import tracker


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def main():
    rows = tracker.read_rows()
    seen = {(norm(r["Company"]), norm(r["Job Title"])) for r in rows}
    seen_co = {norm(r["Company"]) for r in rows}
    for line in sys.stdin:
        line = line.strip()
        if not line or "|" not in line:
            continue
        co, title = [x.strip() for x in line.split("|", 1)]
        if (norm(co), norm(title)) in seen:
            tag = "DUP "
        elif norm(co) in seen_co:
            tag = "NEW*"
        else:
            tag = "NEW "
        print(f"{tag} {co} | {title}")


if __name__ == "__main__":
    main()
