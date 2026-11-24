#!/usr/bin/env python3
import os
import csv
import time

CYAN = "\033[96m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

DOLPHIN_ART = f'''{CYAN}
         ,
        /|                   _
       / |                  / \\
      /  |                 /   \\
     /   |                /     \\
    /    |              _/       \\
   /     |             /          \\
  /      |            /            \\
 /       |           /              \\
/________|          /         O      \\
\\                  /                  \\
 \\                /                    \\
  \\______________/                      \\
                 \\                      /
                  \\                    /
                   \\                  /
                    \\________________/
{BLUE}
        ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
                   JOBIRA AGENT LAUNCHED
        ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
{RESET}'''

def init_environment():
    print(DOLPHIN_ART)
    print(f"{YELLOW}[+] Initializing JOBIRA agent directories...{RESET}")
    time.sleep(0.5)

    folders = ["cover_letters", "resumes", "track_sheet"]
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f"  {GREEN}[✓]{RESET} Folder initialized: ./{folder}/")

    csv_path = os.path.join("track_sheet", "application_tracker.csv")
    if not os.path.exists(csv_path):
        headers = [
            "Date Found", "Company", "Job Title", "Location", "Salary",
            "Requires Class 5 Licence", "Match Score", "Coding Intensity", "Status",
            "Resume Path", "Cover Letter Path", "Job URL"
        ]
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        print(f"  {GREEN}[✓]{RESET} Created tracker: ./{csv_path}")
    else:
        print(f"  {GREEN}[✓]{RESET} Loaded tracker: ./{csv_path}")

    print(f"\n{GREEN}[JOBIRA READY]{RESET} Active mode: All-in auto-hunt.\n")

if __name__ == "__main__":
    init_environment()

