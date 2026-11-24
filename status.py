#!/usr/bin/env python3
"""Live status dashboard for the JOBIRA auto-run loop.

Usage:
    python3 status.py            # one-shot snapshot
    watch -n 5 python3 status.py # live-refreshing view every 5s
"""
import csv
import os
import re
import subprocess
import time
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE, "auto_run.log")
CSV_PATH = os.path.join(BASE, "track_sheet", "application_tracker.csv")
CYCLE_SECONDS = 5 * 60 * 60

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def find_cycle_start_epoch():
    """Parse the most recent 'Starting JOBIRA auto run: <date>' line from auto_run.log."""
    if not os.path.exists(LOG_PATH):
        return None
    last_ts = None
    pattern = re.compile(r"Starting JOBIRA auto run: (.+)")
    with open(LOG_PATH, "r", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                last_ts = m.group(1).strip()
    if not last_ts:
        return None
    # `date` command's default format, e.g. "Thu Aug 13 17:30:00 PDT 2026"
    try:
        result = subprocess.run(["date", "-d", last_ts, "+%s"], capture_output=True, text=True)
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return None


def loop_is_running():
    result = subprocess.run(["pgrep", "-f", "auto_run.sh"], capture_output=True, text=True)
    return bool(result.stdout.strip())


def read_tracker_rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def bar(pct, width=40):
    filled = int(width * pct / 100)
    return "#" * filled + "-" * (width - filled)


def fmt_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def main():
    now = int(time.time())
    start = find_cycle_start_epoch()
    running = loop_is_running()

    print(f"{BOLD}{CYAN}=== JOBIRA STATUS ==={RESET}")
    print(f"Loop process:   {(GREEN + 'RUNNING' + RESET) if running else (RED + 'NOT RUNNING' + RESET)}")

    if start:
        end = start + CYCLE_SECONDS
        elapsed = max(0, min(now - start, CYCLE_SECONDS))
        pct = elapsed / CYCLE_SECONDS * 100
        remaining = max(0, end - now)
        print(f"Cycle started:  {time.strftime('%a %b %d %H:%M:%S', time.localtime(start))}")
        print(f"Cycle progress: [{bar(pct)}] {pct:5.1f}%")
        print(f"Next cycle in:  {fmt_duration(remaining)}")
    else:
        print(f"Cycle:          {YELLOW}no 'Starting JOBIRA auto run' line in auto_run.log{RESET}")

    rows = read_tracker_rows()
    counts = Counter(r.get("Status", "").strip() for r in rows)
    today = time.strftime("%Y-%m-%d")
    found_today = sum(1 for r in rows if r.get("Date Found", "").strip() == today)

    filtered = counts.get("Rejected / Not Pursued", 0)
    print()
    # JOBIRA's own not-a-match rejects are kept for dedup but aren't applications (2026-09-15).
    print(f"{BOLD}Tracker:{RESET} {len(rows) - filtered} tracked ({found_today} found today); "
          f"{filtered} filtered out as not a match, not counted")
    colours = {"Applied": GREEN, "Queued for Auto-Apply": CYAN, "Queued for Review": YELLOW,
               "Apply Failed": RED, "Rejected / Not Pursued": RED, "Interview Scheduled": GREEN,
               "Offer Received": GREEN, "Next Steps - Assessment": CYAN, "Rejected by Employer": RED}
    for status, n in counts.most_common():
        print(f"  {colours.get(status, '')}{status or '(blank)':<26}{RESET} {n}")

    if rows:
        print()
        print(f"{BOLD}Latest 5 entries:{RESET}")
        for r in rows[-5:]:
            print(f"  {r.get('Date Found', '')}  {r.get('Company', '')[:30]:<30}  "
                  f"{r.get('Job Title', '')[:40]:<40}  {r.get('Status', '')}")


if __name__ == "__main__":
    main()
