#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"

while true; do
    echo "=================================================="
    echo "Starting JOBIRA auto run: $(date)"
    echo "=================================================="
    python3 runner.py
    claude --dangerously-skip-permissions -p "Scan job sources across MULTIPLE job boards this cycle -- do not rely on a single source. Use the Indeed, Dice, and ZipRecruiter search tools (all callable without a browser), plus Job Bank (jobbank.gc.ca, fetch the public search and posting pages per skill_file 19.5) and the BC Tech Association job board (wearebctech.com/jobs); LinkedIn coverage happens separately in live interactive sessions since it needs claude-in-chrome. Cover a spread of the target titles in skill_file's Primary career direction table, not just the ones from the last cycle. For each new candidate job: classify per skill_file, create a tailored resume in ./resumes/ and cover letter in ./cover_letters/ per skill_file's Resume Generation Rule and Cover Letter Standards (section 16/20 -- dense one-skill-per-bullet ATS keyword coverage, concise cover letters), and update ./track_sheet/application_tracker.csv (re-checking the file immediately before each write for concurrent-cycle safety). Do NOT attempt browser automation or auto-apply in this headless cycle — queue only (Queued for Auto-Apply / Queued for Review / Rejected). Applying happens later in a live interactive session."
    echo "Run complete. Waiting 5 hours..."
    sleep 18000
done

