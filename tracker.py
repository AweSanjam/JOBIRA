#!/usr/bin/env python3
"""Shared helpers for track_sheet/application_tracker.csv.

The CSV is the single source of truth; every view (xlsx, dashboards, ranking,
status) reads it through here so they agree on tiers, work type and counts.
Standard library only.
"""
import csv
import os
import re
import tempfile
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.environ.get("JOBIRA_TRACKER_CSV") or os.path.join(BASE, "track_sheet", "application_tracker.csv")

FIELDNAMES = ["Date Found", "Company", "Job Title", "Location", "Salary",
              "Requires Class 5 Licence", "Match Score", "Coding Intensity", "Status",
              "Resume Path", "Cover Letter Path", "Job URL"]

# Pipeline statuses (CLAUDE.md step 5 / apply mode) and email-response statuses
# (CLAUDE.md "Email response tracking").
PIPELINE_STATUSES = ["Queued for Auto-Apply", "Queued for Review", "Applied", "Apply Failed",
                     "Rejected / Not Pursued"]
RESPONSE_STATUSES = ["Interview Scheduled", "Next Steps - Assessment", "Offer Received",
                     "Rejected by Employer"]
STATUSES = PIPELINE_STATUSES + RESPONSE_STATUSES

# JOBIRA's own eligibility filter (step 3a) logs non-matches so they're never
# re-scraped, but they aren't applications: they stay out of every total.
SYSTEM_REJECT = "Rejected / Not Pursued"


def read_rows(path=CSV_PATH):
    """All rows as dicts, each with its 0-based position in the file as '_idx'."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["_idx"] = i
        for k in FIELDNAMES:
            r.setdefault(k, "")
            if r[k] is None:
                r[k] = ""
    return rows


def write_rows(rows, path=CSV_PATH):
    """Rewrite the whole CSV atomically (temp file + rename), keeping column order."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".csv.tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDNAMES})
    os.replace(tmp, path)


def match_tier(text):
    """strong / reasonable / stretch / reject / unscored, read from the START of
    the Match Score field (a later 'not a strong match' must not count as strong)."""
    t = (text or "").strip().lower()
    for tier, words in (("strong", ("strong",)), ("reasonable", ("reasonable", "good", "moderate")),
                        ("stretch", ("stretch", "weak", "partial")), ("reject", ("reject", "no match", "not a match"))):
        if any(t.startswith(w) for w in words):
            return tier
    return "unscored"


def ats_percent(text):
    """An ATS percentage recorded in the Match Score field, e.g. 'Strong Match (ATS 97%)'."""
    m = re.search(r"(\d{2,3})\s*%", text or "")
    return int(m.group(1)) if m and int(m.group(1)) <= 100 else None


def is_bc(location):
    t = (location or "").strip()
    return bool(re.search(r"(,|\b)\s*(bc|british columbia)\b", t, re.I)) or t.upper().endswith("BC")


def work_type(location):
    t = (location or "").lower()
    if "remote" in t or "work from home" in t or "wfh" in t:
        return "Remote"
    if "hybrid" in t:
        return "Hybrid"
    return "In-person"


def annual_salary(text):
    """Best-effort yearly figure from a free-text salary, or None.
    Hourly rates are annualised at 2080 h; ranges use their midpoint."""
    t = (text or "").lower().replace(",", "")
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", t)]
    if not nums:
        return None
    k = "k" in t and max(nums) < 1000
    vals = [n * 1000 if k else n for n in nums[:2]]
    v = sum(vals) / len(vals)
    if "hour" in t or "/hr" in t or "hr" in t.split() or v < 200:
        v *= 2080
    return v if 15000 <= v <= 400000 else None


def parse_date(text):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime((text or "").strip()[:10], fmt).date()
        except ValueError:
            pass
    return None


def counts(rows):
    """Headline numbers. 'total' leaves out JOBIRA's own not-a-match rejects."""
    by_status = {}
    for r in rows:
        by_status[r["Status"]] = by_status.get(r["Status"], 0) + 1
    tracked = [r for r in rows if r["Status"] != SYSTEM_REJECT]
    responses = sum(by_status.get(s, 0) for s in ("Interview Scheduled", "Next Steps - Assessment", "Offer Received"))
    applied_ever = sum(by_status.get(s, 0) for s in ("Applied",) + tuple(RESPONSE_STATUSES))
    return {
        "total": len(tracked),
        "filtered_out": by_status.get(SYSTEM_REJECT, 0),
        "by_status": by_status,
        "queued": by_status.get("Queued for Auto-Apply", 0) + by_status.get("Queued for Review", 0),
        "applied": applied_ever,
        "responses": responses,
        "response_rate": round(100 * responses / applied_ever, 1) if applied_ever else 0.0,
        "today": date.today().isoformat(),
    }


def resolve(rel):
    """Absolute path of a tracker file path (e.g. './resumes/X_res.pdf'), or None if it's
    not a real file inside resumes/ or cover_letters/ (reject rows hold a reason there)."""
    if not rel or not rel.lower().endswith((".pdf", ".docx")):
        return None
    p = os.path.normpath(os.path.join(BASE, rel))
    allowed = [os.path.join(BASE, "resumes") + os.sep, os.path.join(BASE, "cover_letters") + os.sep]
    if not any(p.startswith(a) for a in allowed):
        return None
    return p if os.path.isfile(p) else None
