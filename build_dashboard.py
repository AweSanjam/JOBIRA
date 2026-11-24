#!/usr/bin/env python3
"""Builds a snapshot HTML dashboard from track_sheet/application_tracker.csv,
written to track_sheet/dashboard.html, ready to publish as an Artifact.

Re-run this any time the tracker changes, then republish the same file path
to redeploy to the same Artifact URL. CSV stays the single source of truth --
this is a generated, disposable view (same relationship csv_to_colored_xlsx.py
has to the CSV).

The page is the same one local_dashboard_server.py serves, with the data baked
in and editing turned off. Resume/cover links point at the relative PDF paths,
so they work when the file is opened from track_sheet/'s parent folder copy.

Rebuilt 2026-09-28 (the original was lost with the UserSpace drive).
"""
import os

import dashboard_page
import tracker

OUT_PATH = os.path.join(tracker.BASE, "track_sheet", "dashboard.html")


def main():
    data = dashboard_page.payload(live=False)
    # Links are relative to the project folder; the page lives one level down.
    for j in data["jobs"]:
        for k in ("resume", "cover"):
            if k in j["files"]:
                j["files"][k] = "../" + j["files"][k].lstrip("./")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(dashboard_page.render(live=False, data=data))
    c = data["counts"]
    print(f"Wrote {os.path.relpath(OUT_PATH, tracker.BASE)}: {c['total']} tracked, "
          f"{c['filtered_out']} filtered out, {c['applied']} applied, {c['responses']} responses")


if __name__ == "__main__":
    main()
