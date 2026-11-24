#!/usr/bin/env python3
"""JOBIRA ranking: which tracked jobs to act on first.

Each job gets a 0-100 priority from what the tracker already records:

    match tier        strong 45 / reasonable 30 / unscored 18 / stretch 10
    ATS %             up to +10 when the Match Score records one (90%+ = full)
    coding intensity  Low +15 / Medium +8 / Unknown +6 / High 0
    location          BC +8, Remote +10 or Hybrid +5 (on top)
    salary            up to +10, scaled from $40k to $100k a year
    freshness         -1 per 3 days since found, down to -8
    licence           Class 5 required -6, unconfirmed field role -2

Jobs JOBIRA filtered out itself ("Rejected / Not Pursued") and closed jobs
(rejected by the employer) aren't ranked. The dashboards use rank(); on the
command line:

    python3 rank.py              # top 25 jobs to act on (queued / failed)
    python3 rank.py --all 50     # top 50 of everything still open
    python3 rank.py --json       # machine-readable
"""
import json
import sys
from datetime import date

import tracker

ACTIONABLE = {"Queued for Auto-Apply", "Queued for Review", "Apply Failed"}
OPEN = ACTIONABLE | {"Applied", "Interview Scheduled", "Next Steps - Assessment", "Offer Received"}

TIER_POINTS = {"strong": 45, "reasonable": 30, "unscored": 18, "stretch": 10, "reject": 0}
CODING_POINTS = {"low": 15, "medium": 8, "high": 0}


def score(row, today=None):
    """(priority 0-100, list of 'reason +n' strings)."""
    today = today or date.today()
    why = []

    def add(points, reason):
        if points:
            why.append(f"{reason} {points:+d}")
        return points

    s = add(TIER_POINTS[tracker.match_tier(row["Match Score"])], tracker.match_tier(row["Match Score"]))
    ats = tracker.ats_percent(row["Match Score"])
    if ats is not None:
        s += add(max(0, min(10, round((ats - 70) / 2))), f"ATS {ats}%")
    s += add(CODING_POINTS.get(row["Coding Intensity"].strip().lower(), 6), f"coding {row['Coding Intensity'] or 'Unknown'}")
    if tracker.is_bc(row["Location"]):
        s += add(8, "BC")
    wt = tracker.work_type(row["Location"])
    s += add({"Remote": 10, "Hybrid": 5}.get(wt, 0), wt)
    pay = tracker.annual_salary(row["Salary"])
    if pay:
        s += add(max(0, min(10, round((pay - 40000) / 6000))), f"${pay / 1000:.0f}k")
    found = tracker.parse_date(row["Date Found"])
    if found:
        s += add(-min(8, max(0, (today - found).days // 3)), "age")
    lic = row["Requires Class 5 Licence"].strip().lower()
    if lic == "yes":
        s += add(-6, "Class 5 required")
    elif lic.startswith("unknown - verify"):
        s += add(-2, "licence unconfirmed")
    return max(0, min(100, s)), why


def rank(rows=None, statuses=ACTIONABLE):
    """Rows (with '_score', '_why', '_rank') for the given statuses, best first."""
    rows = tracker.read_rows() if rows is None else rows
    today = date.today()
    picked = []
    for r in rows:
        if r["Status"] in statuses:
            r["_score"], r["_why"] = score(r, today)
            picked.append(r)
    # Ties: auto-apply before review (quicker to act on), then newest first.
    picked.sort(key=lambda r: (-r["_score"], r["Status"] != "Queued for Auto-Apply",
                               -((tracker.parse_date(r["Date Found"]) or date.min).toordinal())))
    for i, r in enumerate(picked, 1):
        r["_rank"] = i
    return picked


def main():
    args = sys.argv[1:]
    statuses = OPEN if "--all" in args else ACTIONABLE
    nums = [a for a in args if a.isdigit()]
    limit = int(nums[0]) if nums else 25
    ranked = rank(statuses=statuses)
    if "--json" in args:
        print(json.dumps([{k: v for k, v in r.items() if not k.startswith("_") or k in ("_score", "_why", "_rank")}
                          for r in ranked[:limit]], indent=2))
        return
    if not ranked:
        print("Nothing to rank yet: no queued jobs in the tracker.")
        return
    print(f"{'#':>3}  {'Score':>5}  {'Status':<22} Company — Job Title")
    for r in ranked[:limit]:
        print(f"{r['_rank']:>3}  {r['_score']:>5}  {r['Status']:<22} {r['Company']} — {r['Job Title']}")
        print(f"{'':>13}{', '.join(r['_why'])}")
    print(f"\n{len(ranked)} ranked ({'all open' if statuses is OPEN else 'queued / failed'}).")


if __name__ == "__main__":
    main()
