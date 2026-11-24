#!/usr/bin/env python3
"""Local, auto-refreshing JOBIRA tracker dashboard.

Serves a single-page dashboard on http://127.0.0.1:8420/ that polls
/api/jobs every few seconds. /api/jobs re-reads track_sheet/application_tracker.csv
from disk on every request, so the page reflects the live file with no rebuild
step -- the CSV stays the single source of truth.

Routes:
    GET  /             the dashboard page
    GET  /api/jobs     tracker rows + counts + ranking (JSON)
    POST /api/status   {"i": row, "status": new, "was": old} -> rewrites that row's
                       Status only, then refreshes the colored xlsx view
    GET  /files?p=...  a resume / cover letter PDF listed in the tracker

Usage:
    python3 local_dashboard_server.py [port]

Stdlib only (http.server), consistent with the rest of this project's
no-external-services approach. Listens on 127.0.0.1 only.

Rebuilt 2026-09-28: the original (617 lines) was lost with the UserSpace drive;
this keeps its header, port, CSV contract and live-polling design.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import dashboard_page
import tracker

DEFAULT_PORT = 8420
WRITE_LOCK = threading.Lock()


def set_status(idx, status, was):
    """Change one row's Status (CLAUDE.md: status updates touch only that column)."""
    if status not in tracker.STATUSES:
        return 400, {"error": f"unknown status: {status}"}
    with WRITE_LOCK:
        rows = tracker.read_rows()
        if not 0 <= idx < len(rows):
            return 404, {"error": "row not found (the tracker changed; reload)"}
        if was and rows[idx]["Status"] != was:
            return 409, {"error": "row changed since the page loaded; reload"}
        rows[idx]["Status"] = status
        tracker.write_rows(rows)
    try:
        import csv_to_colored_xlsx
        csv_to_colored_xlsx.main()
    except Exception as e:  # the CSV is saved either way; the xlsx is only a view
        print(f"xlsx refresh failed: {e}", file=sys.stderr)
    return 200, {"ok": True}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.send(200, dashboard_page.render(live=True), "text/html; charset=utf-8")
        elif url.path == "/api/jobs":
            self.send(200, json.dumps(dashboard_page.payload(live=True)), "application/json")
        elif url.path == "/files":
            rel = unquote(parse_qs(url.query).get("p", [""])[0])
            path = tracker.resolve(rel)
            if not path:
                self.send(404, "Not found", "text/plain")
                return
            with open(path, "rb") as f:
                self.send(200, f.read(), "application/pdf" if path.lower().endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            self.send(404, "Not found", "text/plain")

    def do_POST(self):
        if urlparse(self.path).path != "/api/status":
            self.send(404, "Not found", "text/plain")
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            code, res = set_status(int(body["i"]), str(body["status"]), str(body.get("was", "")))
        except (ValueError, KeyError) as e:
            code, res = 400, {"error": f"bad request: {e}"}
        self.send(code, json.dumps(res), "application/json")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"JOBIRA dashboard running at http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
