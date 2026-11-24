#!/usr/bin/env python3
"""Generate resume/cover-letter PDFs (or log a rejection) and append rows to
track_sheet/application_tracker.csv in one step, then refresh the colored
xlsx view.

This formalizes CLAUDE.md pipeline steps 4-5 as a reusable script instead of
ad hoc shell commands, so both interactive sessions and the headless
auto_run.sh loop can call it consistently. Content generation (resume /
cover-letter wording, eligibility classification) stays the agent's job --
this script only handles the mechanical part: md -> pdf, CSV append (with a
duplicate re-check immediately before each write, for concurrent-cycle
safety), and the xlsx refresh.

Usage:
    python3 generate_and_log.py jobs.json            # score, then render + log
    python3 generate_and_log.py --check jobs.json    # ATS-score only, write nothing

ATS gate (resume pipeline rework, 2026-09-17): every resume_md is scored with
ats_scorer.py before anything is rendered. Below ATS_MIN the job is held back
(nothing written, nothing logged) and tech_mapper.py's suggestions for
equivalent tools already in the resume are printed, so the agent can improve
the Markdown and re-run -- the loop repeats until the resume passes.
Set "ats_override": true on a job to log it anyway.

jobs.json is a list of job objects:
{
  "date_found": "2026-08-13",
  "company": "Alpaca",
  "job_title": "IT Operations Specialist",
  "location": "Toronto, ON (Remote)",
  "salary": "N/A",
  "requires_licence": "Unknown",              # "Yes" / "No" / "Unknown" -- Class 5 driver's licence
  "match_score": "Strong Match",
  "coding_intensity": "Low",                   # "Low" / "Medium" / "High" -- per skill_file section 14
  "status": "Queued for Auto-Apply",       # or "Queued for Review" / "Rejected / Not Pursued"
  "job_url": "https://...",
  "resume_md": "...markdown content...",       # required unless status is Rejected / Not Pursued
  "cover_letter_md": "...markdown content...", # required unless status is Rejected / Not Pursued
  "reject_reason": "..."                        # required only when status is Rejected / Not Pursued
}
"""
import csv
import json
import os
import sys
import tempfile

import ats_scorer
import ats_v2
import cover_v2
import md2pdf
import tech_mapper
import csv_to_colored_xlsx as xlsx_view

ATS_MIN = 75

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "track_sheet", "application_tracker.csv")
FIELDNAMES = ["Date Found", "Company", "Job Title", "Location", "Salary",
              "Requires Class 5 Licence", "Match Score", "Coding Intensity", "Status",
              "Resume Path", "Cover Letter Path", "Job URL"]


def slug(text):
    return "".join(ch for ch in text.title().replace(" ", "") if ch.isalnum())


def name_part(text):
    """CompanyName / JobTitle for filenames: words joined, capitals kept, (...) dropped."""
    import re
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"\(.*?\)", " ", text))
    return "".join(w[0].upper() + w[1:] for w in words)


def existing_pairs():
    """Re-read the CSV fresh -- called right before each write so a concurrent
    JOBIRA cycle (e.g. the headless auto_run.sh loop) can't cause a duplicate row."""
    if not os.path.exists(CSV_PATH):
        return set()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return {(r["Company"].strip(), r["Job Title"].strip()) for r in csv.DictReader(f)}


def append_row(row):
    write_header = not os.path.exists(CSV_PATH)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            w.writeheader()
        w.writerow(row)


def ats_check(job, quiet=False):
    """ATS score of the job's resume Markdown (0-100), printing the report and,
    below ATS_MIN, tech_mapper's equivalent-technology suggestions.

    Resume v2 (2026-10-20): when the job carries the posting text ("jd_text", or a
    "jd_path" file), the gate uses ats_v2.py, which scores the resume against that
    posting. Without posting text it falls back to the posting-blind ats_scorer.py."""
    if not job.get("resume_md"):
        return None
    jd = job.get("jd_text") or (open(job["jd_path"], encoding="utf-8").read() if job.get("jd_path") else "")
    if jd:
        r = ats_v2.score(job["resume_md"], jd, job.get("ats_title") or job["job_title"])
        if not quiet:
            print(f"ATS v2: {r['total']}/100  {job['company']} - {job['job_title']}")
            for k, v in r["scores"].items():
                print(f"  {k:20} {v:5}  {r['details'][k]}")
        if not quiet and job.get("cover_letter_md"):
            c = cover_v2.check(job["cover_letter_md"], jd, job["resume_md"], job["company"], job.get("ats_title") or job["job_title"])
            print(f"Cover v2 check: {c['score']}/100, {c['words']} words" + "".join("\n  - " + p for p in c["problems"]))
        return r["total"]
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(job["resume_md"])
        path = f.name
    try:
        result = ats_scorer.calculate_ats_score(path)
        if not quiet:
            ats_scorer.print_ats_report(f"{job['company']} - {job['job_title']}".replace("/", "-"), result)
            if result["total"] < ATS_MIN:
                tech_mapper.print_tech_mapping_report(path)
        return result["total"]
    finally:
        os.unlink(path)


def process(job):
    key = (job["company"].strip(), job["job_title"].strip())
    if key in existing_pairs():
        return "skipped (duplicate already in tracker)"

    if job["status"] == "Rejected / Not Pursued":
        # Per CLAUDE.md step 3a: rejects ARE logged, with a one-line reason
        # in place of the resume/cover-letter paths -- this keeps the dedup
        # check working for future cycles and preserves the audit trail.
        reason = job.get("reject_reason", "")
        append_row({
            "Date Found": job["date_found"],
            "Company": job["company"],
            "Job Title": job["job_title"],
            "Location": job.get("location", ""),
            "Salary": job.get("salary", "N/A"),
            "Requires Class 5 Licence": job.get("requires_licence", "Unknown"),
            "Match Score": job.get("match_score", "Reject"),
            "Coding Intensity": job.get("coding_intensity", "Unknown"),
            "Status": job["status"],
            "Resume Path": reason,
            "Cover Letter Path": reason,
            "Job URL": job.get("job_url", ""),
        })
        return f"rejected, logged ({reason})"

    base = f'{name_part(job["company"])[:40]}_{name_part(job["job_title"])[:50]}'
    # Filenames since 2026-10-10 (CLAUDE.md step 4): [Company]_[Role]_res.pdf / _cover.pdf.
    resume_rel = os.path.join("resumes", f"{base}_res.pdf")
    cover_rel = os.path.join("cover_letters", f"{base}_cover.docx")  # since 2026-10-12: [Company]_[JobTitle]_cover.docx
    # md2pdf overwrites blindly; never replace materials that already exist
    # (a same-named file may belong to a job that was already applied to).
    taken = [p for p in (resume_rel, cover_rel) if os.path.exists(os.path.join(BASE, p))]
    if taken:
        return f"held: {', '.join(taken)} already exists -- pick a distinct role name"

    score = ats_check(job)
    if score is not None and score < ATS_MIN and not job.get("ats_override"):
        return f"held: ATS {score}/100 < {ATS_MIN} -- improve resume_md and re-run (see suggestions above)"
    with tempfile.TemporaryDirectory() as td:
        r_md = os.path.join(td, "resume.md")
        c_md = os.path.join(td, "cover.md")
        with open(r_md, "w", encoding="utf-8") as f:
            f.write(job["resume_md"])
        with open(c_md, "w", encoding="utf-8") as f:
            f.write(job["cover_letter_md"])
        md2pdf.convert(r_md, os.path.join(BASE, resume_rel), css=md2pdf.RESUME_CSS)
        md2pdf.convert_docx(c_md, os.path.join(BASE, cover_rel))
    resume_path = "./" + resume_rel
    cover_path = "./" + cover_rel

    append_row({
        "Date Found": job["date_found"],
        "Company": job["company"],
        "Job Title": job["job_title"],
        "Location": job["location"],
        "Salary": job.get("salary", "N/A"),
        "Requires Class 5 Licence": job.get("requires_licence", "Unknown"),
        "Match Score": job.get("match_score", ""),
        "Coding Intensity": job.get("coding_intensity", "Unknown"),
        "Status": job["status"],
        "Resume Path": resume_path,
        "Cover Letter Path": cover_path,
        "Job URL": job.get("job_url", ""),
    })
    return "logged"


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    args = [a for a in args if a != "--check"]
    if len(args) != 1:
        print("Usage: generate_and_log.py [--check] jobs.json", file=sys.stderr)
        sys.exit(1)

    with open(args[0], encoding="utf-8") as f:
        jobs = json.load(f)

    if check_only:
        for job in jobs:
            score = ats_check(job)
            verdict = "no resume" if score is None else ("pass" if score >= ATS_MIN else "below threshold")
            print(f'{job["company"]} — {job["job_title"]}: ATS {score} ({verdict})')
        return

    for job in jobs:
        result = process(job)
        print(f'{job["company"]} — {job["job_title"]}: {result}')

    xlsx_view.main()


if __name__ == "__main__":
    main()

