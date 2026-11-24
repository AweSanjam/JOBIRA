#!/usr/bin/env python3
"""JOBIRA Dashboard -- the phone / tablet app (an installable PWA).

A lightweight Material You view of track_sheet/application_tracker.csv for when
you're away from the desktop: ranked "Apply next" list with Apply buttons, every
job, every resume / cover-letter PDF, a refresh button, and "mark applied".

    python3 mobile_dashboard.py            # serves http://127.0.0.1:8430/

It listens on 127.0.0.1 only. Remote access (any network, laptop just has to be
on and online) goes through Tailscale: `tailscale serve` publishes it over HTTPS
to your own devices only -- see mobile/README.md. A passcode (mobile/.passcode,
created on first run) is still required on each new device.

The CSV stays the single source of truth: /api/jobs re-reads it on every
request, and a status change rewrites only that row's Status (then refreshes
the colored xlsx view), same as local_dashboard_server.py.

Standard library only. The same file runs JOBIRA 2's app; only CONFIG differs.
"""
import csv
import hashlib
import re
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo

# ---- per-app settings (the only part that differs between JOBIRA and JOBIRA 2) ----
CONFIG = {
    "name": "JOBIRA Dashboard",
    "short": "JOBIRA",
    "port": 8430,
    # Material 3 tonal palette (dark = pure-black AMOLED surfaces), seed indigo #4355B9
    "light": {"primary": "#4355B9", "on-primary": "#FFFFFF", "primary-container": "#DEE0FF",
              "on-primary-container": "#00105C", "secondary-container": "#E0E1F9",
              "on-secondary-container": "#191B2C", "surface": "#FBF8FF", "surface-c-low": "#F5F2FA",
              "surface-c": "#EFEDF4", "surface-c-high": "#E9E7EF", "on-surface": "#1B1B21",
              "on-surface-var": "#46464F", "outline": "#767680", "outline-var": "#C6C5D0"},
    "dark": {"primary": "#BAC3FF", "on-primary": "#08218A", "primary-container": "#293CA0",
             "on-primary-container": "#DEE0FF", "secondary-container": "#444559",
             "on-secondary-container": "#E0E1F9", "surface": "#000000", "surface-c-low": "#0F0F13",
             "surface-c": "#16161B", "surface-c-high": "#222228", "on-surface": "#E4E1E9",
             "on-surface-var": "#C6C5D0", "outline": "#90909A", "outline-var": "#46464F"},
}
STATUSES = ["Queued for Auto-Apply", "Queued for Review", "Applied", "Apply Failed",
            "Rejected / Not Pursued", "Interview Scheduled", "Next Steps - Assessment",
            "Offer Received", "Rejected by Employer"]
# -------------------------------------------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "track_sheet", "application_tracker.csv")
ASSETS = os.path.join(BASE, "mobile")
PASSCODE_FILE = os.path.join(ASSETS, ".passcode")
FILE_DIRS = ("resumes", "cover_letters")
FIELDNAMES = ["Date Found", "Company", "Job Title", "Location", "Salary",
              "Requires Class 5 Licence", "Match Score", "Coding Intensity", "Status",
              "Resume Path", "Cover Letter Path", "Job URL"]
ACTIONABLE = {"Queued for Auto-Apply", "Queued for Review", "Apply Failed"}
SYSTEM_REJECT = "Rejected / Not Pursued"
PACIFIC = ZoneInfo("America/Los_Angeles")
COOKIE = "jd_" + CONFIG["short"].lower().replace(" ", "")
COOKIE_DAYS = 180
WRITE_LOCK = threading.Lock()
FAILS = []  # timestamps of recent wrong passcodes (simple brute-force brake)

try:  # JOBIRA has a ranking module; JOBIRA 2 falls back to tier + date order
    sys.path.insert(0, BASE)
    import rank as _rank
except Exception:
    _rank = None


# ---------------- data ----------------

def read_rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["_idx"] = i
        for k in FIELDNAMES:
            if r.get(k) is None:
                r[k] = ""
    return rows


def write_rows(rows):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CSV_PATH), suffix=".csv.tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDNAMES})
    os.replace(tmp, CSV_PATH)


def tier(text):
    t = (text or "").strip().lower()
    for name, words in (("strong", ("strong",)), ("reasonable", ("reasonable", "good", "moderate")),
                        ("stretch", ("stretch", "weak", "partial")), ("reject", ("reject",))):
        if t.startswith(words):
            return name
    return "unscored"


def ats_percent(text):
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
    """Best-effort yearly figure (hourly x 2080, ranges -> midpoint), else None."""
    t = (text or "").lower().replace(",", "")
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", t)]
    if not nums:
        return None
    k = "k" in t and max(nums) < 1000
    vals = [n * 1000 if k else n for n in nums[:2]]
    v = sum(vals) / len(vals)
    if "hour" in t or "/hr" in t or "hr" in t.split() or v < 200:
        v *= 2080
    return round(v) if 15000 <= v <= 400000 else None


def safe_file(rel):
    """Absolute path of a PDF inside resumes/ or cover_letters/, else None."""
    if not rel or not rel.lower().endswith((".pdf", ".docx")):
        return None
    p = os.path.realpath(os.path.join(BASE, rel))
    if not any(p.startswith(os.path.join(BASE, d) + os.sep) for d in FILE_DIRS):
        return None
    return p if os.path.isfile(p) else None


def file_url(rel):
    p = safe_file(rel)
    return "/f/" + quote(os.path.relpath(p, BASE)) if p else None


def jobs_payload():
    rows = read_rows()
    scores = {}
    if _rank:
        try:
            for r in _rank.rank([dict(x) for x in rows], statuses=_rank.OPEN):
                scores[r["_idx"]] = (r["_score"], r["_why"])
        except Exception:
            scores = {}
    order = {"strong": 0, "reasonable": 1, "unscored": 2, "stretch": 3, "reject": 4}
    jobs, counts = [], {}
    for r in rows:
        counts[r["Status"]] = counts.get(r["Status"], 0) + 1
        sc = scores.get(r["_idx"])
        reason = ""
        for col in ("Resume Path", "Cover Letter Path"):
            v = r[col]
            if v and not v.lower().endswith((".pdf", ".docx")):
                reason = v
        jobs.append({
            "i": r["_idx"], "date": r["Date Found"], "company": r["Company"], "title": r["Job Title"],
            "location": r["Location"], "work": work_type(r["Location"]), "bc": is_bc(r["Location"]),
            "salary": r["Salary"], "pay": annual_salary(r["Salary"]), "licence": r["Requires Class 5 Licence"],
            "ats": ats_percent(r["Match Score"]), "match": r["Match Score"],
            "tier": tier(r["Match Score"]), "coding": r["Coding Intensity"], "status": r["Status"],
            "url": r["Job URL"] if r["Job URL"].startswith(("http://", "https://")) else "",
            "resume": file_url(r["Resume Path"]), "cover": file_url(r["Cover Letter Path"]),
            "reason": reason, "score": sc[0] if sc else None, "why": sc[1] if sc else [],
            "sort": (-(sc[0] if sc else 0), order[tier(r["Match Score"])], -_ord(r["Date Found"])),
        })
    jobs.sort(key=lambda j: j.pop("sort"))
    tracked = sum(v for k, v in counts.items() if k != SYSTEM_REJECT)
    return {"app": CONFIG["name"], "generated": datetime.now(PACIFIC).strftime("%a %b %d, %I:%M %p"),
            "statuses": STATUSES, "counts": counts, "tracked": tracked,
            "queued": sum(counts.get(s, 0) for s in ACTIONABLE), "jobs": jobs}


def _ord(d):
    try:
        return datetime.strptime((d or "")[:10], "%Y-%m-%d").toordinal()
    except ValueError:
        return 0


def files_payload():
    used = {}
    for r in read_rows():
        for col in ("Resume Path", "Cover Letter Path"):
            p = safe_file(r[col])
            if p:
                used.setdefault(p, []).append(f"{r['Company']} — {r['Job Title']}")
    out = []
    for d in FILE_DIRS:
        folder = os.path.join(BASE, d)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if name.lower().endswith((".pdf", ".docx")) and os.path.isfile(p):
                st = os.stat(p)
                out.append({"name": name, "kind": "resume" if d == "resumes" else "cover",
                            "url": "/f/" + quote(f"{d}/{name}"), "kb": round(st.st_size / 1024),
                            "mtime": st.st_mtime, "jobs": used.get(os.path.realpath(p), [])})
    out.sort(key=lambda f: -f["mtime"])
    return {"files": out}


def set_status(i, status, was):
    if status not in STATUSES:
        return 400, {"error": "unknown status"}
    with WRITE_LOCK:
        rows = read_rows()
        if not 0 <= i < len(rows):
            return 404, {"error": "That job moved -- refresh and try again."}
        if was and rows[i]["Status"] != was:
            return 409, {"error": "Status changed elsewhere -- refresh and try again."}
        rows[i]["Status"] = status
        write_rows(rows)
    try:
        import csv_to_colored_xlsx
        csv_to_colored_xlsx.main()
    except Exception as e:  # the CSV is saved either way; the xlsx is only a view
        print(f"xlsx refresh failed: {e}", file=sys.stderr)
    return 200, {"ok": True}


# ---------------- auth ----------------

def passcode():
    os.makedirs(ASSETS, exist_ok=True)
    if not os.path.exists(PASSCODE_FILE):
        code = "-".join(secrets.token_hex(2) for _ in range(3))  # e.g. 3fa1-09bc-e2d4
        fd = os.open(PASSCODE_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(code + "\n")
    with open(PASSCODE_FILE) as f:
        return f.read().strip()


def session_value():
    # Tied to the passcode: deleting mobile/.passcode signs every device out.
    return hmac.new(passcode().encode(), b"jobira-mobile-session", hashlib.sha256).hexdigest()


# ---------------- http ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = "JOBIRA"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype, headers=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def authed(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and hmac.compare_digest(v, session_value()):
                return True
        return False

    def do_GET(self):
        url = urlparse(self.path)
        p = url.path
        if p == "/manifest.webmanifest":
            return self.send(200, manifest(), "application/manifest+json")
        if p == "/sw.js":
            return self.send(200, SW, "text/javascript", {"Service-Worker-Allowed": "/"})
        if p.startswith("/icon-") and p.endswith(".png"):
            f = os.path.join(ASSETS, os.path.basename(p))
            if os.path.isfile(f):
                with open(f, "rb") as fh:
                    return self.send(200, fh.read(), "image/png")
            return self.send(404, "not found", "text/plain")
        if p == "/healthz":
            return self.send(200, "ok", "text/plain")
        if p == "/login":
            return self.send(200, page(LOGIN), "text/html; charset=utf-8")
        if not self.authed():
            if p.startswith("/api/") or p.startswith("/f/"):
                return self.send(401, json.dumps({"error": "sign in"}), "application/json")
            return self.send(303, "", "text/plain", {"Location": "/login"})
        if p in ("/", "/index.html"):
            return self.send(200, page(APP), "text/html; charset=utf-8")
        if p == "/api/jobs":
            return self.send(200, json.dumps(jobs_payload()), "application/json")
        if p == "/api/files":
            return self.send(200, json.dumps(files_payload()), "application/json")
        if p.startswith("/f/"):
            rel = unquote(p[3:])
            f = safe_file(rel)
            if not f:
                return self.send(404, "not found", "text/plain")
            dl = "attachment" if parse_qs(url.query).get("dl") else "inline"
            with open(f, "rb") as fh:
                return self.send(200, fh.read(), "application/pdf" if f.lower().endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                 {"Content-Disposition": f'{dl}; filename="{os.path.basename(f)}"'})
        self.send(404, "not found", "text/plain")

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 10000)) or b"{}")
        except ValueError:
            return self.send(400, json.dumps({"error": "bad request"}), "application/json")
        if p == "/login":
            now = time.time()
            FAILS[:] = [t for t in FAILS if now - t < 600]
            if len(FAILS) >= 10:
                return self.send(429, json.dumps({"error": "Too many tries. Wait 10 minutes."}), "application/json")
            if hmac.compare_digest(str(body.get("code", "")).strip().lower(), passcode()):
                cookie = (f"{COOKIE}={session_value()}; Path=/; Max-Age={COOKIE_DAYS * 86400}; "
                          "HttpOnly; Secure; SameSite=Strict")
                return self.send(200, json.dumps({"ok": True}), "application/json", {"Set-Cookie": cookie})
            FAILS.append(now)
            time.sleep(1)
            return self.send(403, json.dumps({"error": "Wrong passcode."}), "application/json")
        if not self.authed():
            return self.send(401, json.dumps({"error": "sign in"}), "application/json")
        if p == "/api/status" and self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                code, res = set_status(int(body["i"]), str(body["status"]), str(body.get("was", "")))
            except (KeyError, ValueError):
                code, res = 400, {"error": "bad request"}
            return self.send(code, json.dumps(res), "application/json")
        self.send(404, json.dumps({"error": "not found"}), "application/json")


def manifest():
    c = CONFIG
    return json.dumps({
        "name": c["name"], "short_name": c["short"], "id": "/", "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": c["light"]["surface"],
        "theme_color": c["light"]["primary"],
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    })


def page(tpl):
    def tokens(t):
        return "".join(f"--{k}:{v};" for k, v in t.items())
    return (tpl.replace("__HEAD__", HEAD).replace("__LIGHT__", tokens(CONFIG["light"])).replace("__DARK__", tokens(CONFIG["dark"]))
            .replace("__NAME__", CONFIG["name"]).replace("__THEME__", CONFIG["light"]["primary"])
            .replace("__THEME_DARK__", CONFIG["dark"]["surface"]))


# Network-first for the API (so a refresh is always live), with the last good
# response kept so the app still opens with recent data when the laptop is off.
SW = r"""
const C = 'jd-v1';
self.addEventListener('install', e => { self.skipWaiting(); e.waitUntil(caches.open(C).then(c => c.addAll(['/', '/manifest.webmanifest', '/icon-192.png']))); });
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/f/') || u.pathname === '/login') return;
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && (u.pathname === '/' || u.pathname.startsWith('/api/'))) { const k = r.clone(); caches.open(C).then(c => c.put(e.request, k)); }
    return r;
  }).catch(() => caches.match(e.request).then(m => m || new Response(JSON.stringify({offline: true}), {status: 503, headers: {'Content-Type': 'application/json'}}))));
});
"""

HEAD = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="__THEME__" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="__THEME_DARK__" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon-192.png">
<link rel="apple-touch-icon" href="/icon-192.png">
<title>__NAME__</title>
<style>
:root { __LIGHT__ color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { __DARK__ } }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
html, body { margin: 0; background: var(--surface); color: var(--on-surface); }
body { font: 15px/1.45 Roboto, "Google Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }
button, input, select { font: inherit; color: inherit; }
a { color: var(--primary); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 40px; padding: 0 18px;
  border-radius: 20px; border: 0; font-weight: 500; font-size: 14px; letter-spacing: .01em; cursor: pointer; text-decoration: none; white-space: nowrap; }
.btn.filled { background: var(--primary); color: var(--on-primary); }
.btn.tonal { background: var(--secondary-container); color: var(--on-secondary-container); }
.btn.text { background: transparent; color: var(--primary); padding: 0 12px; }
.btn:disabled { opacity: .38; cursor: default; }
.btn svg { width: 18px; height: 18px; fill: currentColor; }
</style>"""

LOGIN = r"""<!doctype html><html lang="en"><head>__HEAD__
<style>
main { min-height: 100dvh; display: grid; place-items: center; padding: 24px 16px; }
.card { width: 100%; max-width: 360px; background: var(--surface-c); border-radius: 28px; padding: 28px 24px; }
h1 { font-size: 24px; font-weight: 400; margin: 0 0 6px; }
p { margin: 0 0 20px; color: var(--on-surface-var); font-size: 14px; }
input { width: 100%; height: 56px; border-radius: 4px; border: 1px solid var(--outline); background: transparent;
  padding: 0 16px; font-size: 18px; letter-spacing: .08em; margin-bottom: 16px; }
input:focus { outline: 2px solid var(--primary); border-color: transparent; }
.err { color: #BA1A1A; min-height: 20px; font-size: 13px; margin: -8px 0 12px; }
@media (prefers-color-scheme: dark) { .err { color: #FFB4AB; } }
.btn { width: 100%; }
</style></head><body><main><form class="card" id="f">
<h1>__NAME__</h1><p>Enter the passcode shown on your laptop (once per device).</p>
<input id="c" autocomplete="one-time-code" autocapitalize="off" spellcheck="false" placeholder="xxxx-xxxx-xxxx" required>
<div class="err" id="e"></div><button class="btn filled">Sign in</button></form></main>
<script>
document.getElementById('f').onsubmit = async ev => {
  ev.preventDefault();
  const r = await fetch('/login', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code: document.getElementById('c').value})}).catch(() => null);
  if (r && r.ok) location.replace('/');
  else document.getElementById('e').textContent = r ? (await r.json()).error : 'Can\'t reach your laptop.';
};
</script></body></html>"""

APP = r"""<!doctype html><html lang="en"><head>__HEAD__
<style>
header { position: sticky; top: 0; z-index: 5; background: var(--surface); display: flex; align-items: center;
  gap: 4px; padding: calc(8px + env(safe-area-inset-top)) 8px 8px 16px; }
header h1 { font-size: 22px; font-weight: 400; margin: 0; flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.icon-btn { width: 48px; height: 48px; border-radius: 24px; border: 0; background: transparent; display: grid; place-items: center; cursor: pointer; color: var(--on-surface-var); }
.icon-btn svg { width: 24px; height: 24px; fill: currentColor; }
.icon-btn.busy svg { opacity: .4; }
main { padding: 0 16px calc(96px + env(safe-area-inset-bottom)); max-width: 760px; margin: 0 auto; }
.sub { color: var(--on-surface-var); font-size: 13px; margin: 0 0 12px; }
.sub.off { color: #BA1A1A; } @media (prefers-color-scheme: dark) { .sub.off { color: #FFB4AB; } }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
.stat { background: var(--primary-container); color: var(--on-primary-container); border-radius: 16px; padding: 12px; }
.stat b { display: block; font-size: 24px; font-weight: 500; line-height: 1.1; }
.stat span { font-size: 12px; }
.search { width: 100%; height: 48px; border-radius: 24px; border: 0; background: var(--surface-c-high);
  padding: 0 20px; margin-bottom: 10px; font-size: 15px; }
.search:focus { outline: 2px solid var(--primary); }
.chips { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 12px; scrollbar-width: none; }
.chip { flex: none; height: 32px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--outline-var);
  background: transparent; font-size: 13px; font-weight: 500; color: var(--on-surface-var); cursor: pointer; }
.chip.on { background: var(--secondary-container); color: var(--on-secondary-container); border-color: transparent; }
.card { background: var(--surface-c-low); border-radius: 16px; padding: 16px; margin-bottom: 10px; }
.bar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.bar .search { margin: 0; flex: 1; }
.fbtn { flex: none; height: 48px; padding: 0 16px 0 12px; border-radius: 24px; border: 0; background: var(--surface-c-high); display: inline-flex; align-items: center; gap: 6px; font-weight: 500; font-size: 14px; cursor: pointer; }
.fbtn svg { width: 20px; height: 20px; fill: currentColor; }
.fbtn.on { background: var(--secondary-container); color: var(--on-secondary-container); }
.fbtn .n { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--primary); color: var(--on-primary); font-size: 12px; display: inline-grid; place-items: center; }
.panel { background: var(--surface-c); border-radius: 20px; padding: 16px; margin-bottom: 12px; display: grid; gap: 14px; }
@media (min-width: 900px) { .panel { grid-template-columns: 1fr 1fr; } .panel .wide { grid-column: 1 / -1; } }
.grp label.h { display: block; font-size: 12px; font-weight: 500; color: var(--on-surface-var); margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em; }
.grp .chips { flex-wrap: wrap; padding: 0; overflow: visible; }
.grp select { width: 100%; height: 40px; border-radius: 8px; border: 1px solid var(--outline-var); background: transparent; padding: 0 10px; font-size: 14px; }
.grp select option { background: var(--surface-c); color: var(--on-surface); }
.chip.on.t::before { content: "\2713  "; }
.pfoot { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.count { color: var(--on-surface-var); font-size: 13px; margin: -4px 0 10px; }
.tag.w-remote { background: #D3E3FD; color: #041E49; } .tag.w-hybrid { background: #E8DEF8; color: #1D192B; }
.tag.c-high { background: #FFDAD6; color: #410002; } .tag.c-medium { background: #FFE08B; color: #241A00; }
@media (prefers-color-scheme: dark) { .tag.w-remote { background: #0B3B7A; color: #D3E3FD; } .tag.w-hybrid { background: #4A4458; color: #E8DEF8; }
  .tag.c-high { background: #93000A; color: #FFDAD6; } .tag.c-medium { background: #574500; color: #FFE08B; } }
.card h2 { font-size: 16px; font-weight: 500; margin: 0; }
.co { color: var(--on-surface-var); font-size: 14px; margin: 2px 0 8px; }
.meta { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.tag { font-size: 12px; padding: 3px 8px; border-radius: 6px; background: var(--surface-c-high); color: var(--on-surface-var); }
.tag.strong { background: #C4EED0; color: #072711; } .tag.reasonable { background: #FFE08B; color: #241A00; }
.tag.stretch, .tag.reject { background: #FFDAD6; color: #410002; }
@media (prefers-color-scheme: dark) { .tag.strong { background: #1F5130; color: #C4EED0; } .tag.reasonable { background: #574500; color: #FFE08B; }
  .tag.stretch, .tag.reject { background: #93000A; color: #FFDAD6; } }
.note { font-size: 13px; color: var(--on-surface-var); margin: 0 0 10px; overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.status { flex: 1 1 140px; margin-left: auto; height: 32px; border-radius: 8px; border: 1px solid var(--outline-var); background: transparent; padding: 0 8px; font-size: 12px; max-width: 46%; }
.file { display: flex; align-items: center; gap: 12px; padding: 12px 4px; border-bottom: 1px solid var(--outline-var); }
.file .fi { width: 40px; height: 40px; border-radius: 20px; background: var(--secondary-container); color: var(--on-secondary-container); display: grid; place-items: center; flex: none; }
.file .fi svg { width: 20px; height: 20px; fill: currentColor; }
.file .fn { flex: 1; min-width: 0; color: inherit; text-decoration: none; }
.file .fn b { display: block; font-weight: 500; font-size: 14px; overflow-wrap: anywhere; }
.file .fn span { font-size: 12px; color: var(--on-surface-var); }
.empty { text-align: center; color: var(--on-surface-var); padding: 48px 16px; }
.more { display: block; margin: 8px auto 0; }
nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 5; background: var(--surface-c); display: flex;
  padding: 12px 0 calc(16px + env(safe-area-inset-bottom)); }
nav button { flex: 1; border: 0; background: transparent; display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 12px; font-weight: 500; color: var(--on-surface-var); cursor: pointer; }
nav .pill { width: 64px; height: 32px; border-radius: 16px; display: grid; place-items: center; }
nav svg { width: 24px; height: 24px; fill: currentColor; }
nav button.on { color: var(--on-surface); } nav button.on .pill { background: var(--secondary-container); color: var(--on-secondary-container); }
.snack { position: fixed; left: 16px; right: 16px; bottom: calc(96px + env(safe-area-inset-bottom)); z-index: 6; max-width: 560px; margin: 0 auto;
  background: var(--on-surface); color: var(--surface); padding: 14px 16px; border-radius: 4px; font-size: 14px; display: none; }
@media (min-width: 900px) { main { max-width: 1100px; } #list { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; } }
</style></head><body>
<header><h1>__NAME__</h1>
<button class="icon-btn" id="refresh" aria-label="Refresh" title="Refresh"><svg viewBox="0 0 24 24"><path d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.74 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg></button>
</header>
<main>
<p class="sub" id="sub">Loading…</p>
<section id="view"></section>
</main>
<nav id="nav">
<button data-v="next" class="on"><span class="pill"><svg viewBox="0 0 24 24"><path d="M12 2 4 6v6c0 5 3.4 9.7 8 10.9 4.6-1.2 8-5.9 8-10.9V6l-8-4zm-1.1 14.6-3.7-3.7 1.4-1.4 2.3 2.3 5-5 1.4 1.4-6.4 6.4z"/></svg></span>Apply next</button>
<button data-v="all"><span class="pill"><svg viewBox="0 0 24 24"><path d="M20 6h-4V4c0-1.1-.9-2-2-2h-4c-1.1 0-2 .9-2 2v2H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-6 0h-4V4h4v2z"/></svg></span>All jobs</button>
<button data-v="files"><span class="pill"><svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg></span>Files</button>
</nav>
<div class="snack" id="snack"></div>
<script>
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const ICON = {
  open: '<svg viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>',
  doc: '<svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
  dl: '<svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>',
};
const ACTION = new Set(['Queued for Auto-Apply', 'Queued for Review', 'Apply Failed']);
let data = null, files = null, view = localStorage.getItem('jd-view') || 'next', filter = localStorage.getItem('jd-filter') || 'Open', q = '', shown = 40;
const FDEF = () => ({sort: 'priority', status: '', tiers: [], work: [], coding: [], days: 0, date: '', bc: false, salary: false, pay: 0, noLicence: false, resume: false});
let fs = Object.assign(FDEF(), (() => { try { return JSON.parse(localStorage.getItem('jd-fs') || '{}'); } catch (_) { return {}; } })());
let panelOpen = false, HAS_CODING = false;
const saveFs = () => { try { localStorage.setItem('jd-fs', JSON.stringify(fs)); } catch (_) {} };
const TUNE = '<svg viewBox="0 0 24 24"><path d="M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z"/></svg>';
const TIERS = ['strong', 'reasonable', 'unscored', 'stretch', 'reject'];
const daysAgo = d => { const t = Date.parse((d || '').slice(0, 10) + 'T00:00:00'); return isNaN(t) ? 1e9 : Math.floor((Date.now() - t) / 864e5); };
const codingOf = j => /^(low|medium|high)$/i.test(j.coding || '') ? j.coding[0].toUpperCase() + j.coding.slice(1).toLowerCase() : 'Unknown';
function activeCount() {
  return (fs.status ? 1 : 0) + (fs.tiers.length ? 1 : 0) + (fs.work.length ? 1 : 0) + (fs.coding.length ? 1 : 0) + (fs.days ? 1 : 0) + (fs.date ? 1 : 0)
    + (fs.bc ? 1 : 0) + (fs.salary ? 1 : 0) + (fs.pay ? 1 : 0) + (fs.noLicence ? 1 : 0) + (fs.resume ? 1 : 0) + (fs.sort !== 'priority' ? 1 : 0);
}
function applyFilters(jobs) {
  const t = q.toLowerCase();
  jobs = jobs.filter(j =>
    (!t || `${j.company} ${j.title} ${j.location} ${j.salary} ${j.match}`.toLowerCase().includes(t)) &&
    (!fs.status || j.status === fs.status) &&
    (!fs.tiers.length || fs.tiers.includes(j.tier)) &&
    (!fs.work.length || fs.work.includes(j.work)) &&
    (!fs.coding.length || fs.coding.includes(codingOf(j))) &&
    (!fs.days || daysAgo(j.date) < fs.days) && (!fs.date || (j.date || '').startsWith(fs.date)) &&
    (!fs.bc || j.bc) && (!fs.salary || j.pay) && (!fs.pay || (j.pay && j.pay >= fs.pay)) &&
    (!fs.noLicence || j.licence !== 'Yes') && (!fs.resume || j.resume));
  const S = {
    newest: (a, b) => (b.date || '').localeCompare(a.date || '') || b.i - a.i,
    oldest: (a, b) => (a.date || '').localeCompare(b.date || '') || a.i - b.i,
    pay: (a, b) => (b.pay || 0) - (a.pay || 0),
    company: (a, b) => a.company.localeCompare(b.company),
    match: (a, b) => TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier) || (b.ats || 0) - (a.ats || 0),
  };
  return S[fs.sort] ? [...jobs].sort(S[fs.sort]) : jobs;
}
function chipGroup(key, values, labels) {
  return values.map((v, i) => `<button class="chip t${fs[key].includes(v) ? ' on' : ''}" data-m="${key}" data-val="${esc(v)}">${esc((labels || values)[i])}</button>`).join('');
}
function panel() {
  const dates = [...new Set(data.jobs.map(j => (j.date || '').slice(0, 10)).filter(Boolean))].sort().reverse();
  const sel = (key, opts) => `<select data-s="${key}">${opts.map(([v, l]) => `<option value="${esc(v)}"${String(fs[key]) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  return `<div class="panel">
    <div class="grp"><label class="h">Sort by</label>${sel('sort', [['priority', 'Priority (best first)'], ['newest', 'Newest found'], ['oldest', 'Oldest found'], ['pay', 'Pay (highest first)'], ['match', 'Match strength'], ['company', 'Company A–Z']])}</div>
    <div class="grp"><label class="h">Status</label>${sel('status', [['', 'Any status'], ...data.statuses.map(s => [s, s])])}</div>
    <div class="grp"><label class="h">Match</label><div class="chips">${chipGroup('tiers', ['strong', 'reasonable', 'stretch', 'unscored'], ['Strong', 'Reasonable', 'Stretch', 'Unscored'])}</div></div>
    <div class="grp"><label class="h">Work type</label><div class="chips">${chipGroup('work', ['Remote', 'Hybrid', 'In-person'])}</div></div>
    ${HAS_CODING ? `<div class="grp"><label class="h">Coding</label><div class="chips">${chipGroup('coding', ['Low', 'Medium', 'High', 'Unknown'])}</div></div>` : ''}
    <div class="grp"><label class="h">Found</label>${sel('days', [[0, 'Any time'], [1, 'Today'], [3, 'Last 3 days'], [7, 'Last 7 days'], [14, 'Last 2 weeks'], [30, 'Last 30 days']])}</div>
    <div class="grp"><label class="h">On date</label>${sel('date', [['', 'Any date'], ...dates.map(d => [d, d])])}</div>
    <div class="grp"><label class="h">Minimum pay</label>${sel('pay', [[0, 'Any pay'], [35000, '$35k+ (about $17/h)'], [40000, '$40k+ (about $19/h)'], [45000, '$45k+ (about $22/h)'], [55000, '$55k+ (about $26/h)'], [70000, '$70k+ (about $34/h)']])}</div>
    <div class="grp wide"><label class="h">Only show</label><div class="chips">
      <button class="chip t${fs.bc ? ' on' : ''}" data-tg="bc">In BC</button>
      <button class="chip t${fs.salary ? ' on' : ''}" data-tg="salary">Pay listed</button>
      <button class="chip t${fs.noLicence ? ' on' : ''}" data-tg="noLicence">No licence needed</button>
      <button class="chip t${fs.resume ? ' on' : ''}" data-tg="resume">Resume ready</button></div></div>
    <div class="pfoot wide"><button class="btn text" id="fclear">Clear all</button><button class="btn filled" id="fdone">Done</button></div>
  </div>`;
}

function snack(msg) { const s = $('#snack'); s.textContent = msg; s.style.display = 'block'; clearTimeout(snack.t); snack.t = setTimeout(() => s.style.display = 'none', 3500); }

async function get(url) {
  const r = await fetch(url, {cache: 'no-store'});
  if (r.status === 401) { location.replace('/login'); throw new Error('auth'); }
  const j = await r.json();
  if (j.offline) throw new Error('offline');
  return j;
}

async function load(manual) {
  const b = $('#refresh'); b.classList.add('busy'); b.disabled = true;
  try {
    data = await get('/api/jobs');
    if (view === 'files' || files) files = await get('/api/files');
    $('#sub').className = 'sub';
    $('#sub').textContent = `${data.tracked} tracked · ${data.queued} to apply · updated ${data.generated}`;
    if (manual) snack('Up to date');
  } catch (e) {
    if (e.message === 'auth') return;
    $('#sub').className = 'sub off';
    $('#sub').textContent = data ? `Laptop offline — showing ${data.generated}` : 'Can\'t reach your laptop. Is it on and online?';
  } finally { b.classList.remove('busy'); b.disabled = false; render(); }
}

function card(j) {
  const cod = (j.coding || '').toLowerCase();
  const tags = [j.tier !== 'unscored' ? `<span class="tag ${j.tier}">${esc(j.tier)}${j.ats ? ' · ' + j.ats + '%' : ''}</span>` : '',
    j.location ? `<span class="tag">${esc(j.location)}</span>` : '',
    j.work !== 'In-person' ? `<span class="tag w-${j.work.toLowerCase()}">${j.work}</span>` : '',
    j.salary && j.salary !== 'N/A' ? `<span class="tag">${esc(j.salary)}</span>` : '',
    HAS_CODING && /^(low|medium|high)$/.test(cod) ? `<span class="tag c-${cod}">${esc(j.coding)} coding</span>` : '',
    j.licence === 'Yes' ? '<span class="tag">Class 5 licence</span>' : '',
    j.score != null ? `<span class="tag">priority ${j.score}</span>` : '', j.date ? `<span class="tag">${esc(j.date)}</span>` : ''].join('');
  const note = j.reason || j.match;
  const opts = data.statuses.map(s => `<option${s === j.status ? ' selected' : ''}>${esc(s)}</option>`).join('');
  return `<article class="card"><h2>${esc(j.title)}</h2><div class="co">${esc(j.company)}</div><div class="meta">${tags}</div>
    ${note ? `<p class="note">${esc(note.length > 220 ? note.slice(0, 220) + '…' : note)}</p>` : ''}
    <div class="actions">
      ${j.url ? `<a class="btn filled" href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${ICON.open}Apply</a>` : ''}
      ${j.resume ? `<a class="btn tonal" href="${esc(j.resume)}" target="_blank">${ICON.doc}Resume</a>` : ''}
      ${j.cover ? `<a class="btn tonal" href="${esc(j.cover)}" target="_blank">Cover</a>` : ''}
      <select class="status" data-i="${j.i}" data-was="${esc(j.status)}" aria-label="Status">${opts}</select>
    </div></article>`;
}

function render() {
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.v === view));
  const v = $('#view');
  if (!data) { v.innerHTML = ''; return; }
  if (view === 'files') return renderFiles(v);
  const c = data.counts;
  let html = `<div class="stats"><div class="stat"><b>${data.queued}</b><span>To apply</span></div>
    <div class="stat"><b>${c['Applied'] || 0}</b><span>Applied</span></div>
    <div class="stat"><b>${(c['Interview Scheduled'] || 0) + (c['Next Steps - Assessment'] || 0) + (c['Offer Received'] || 0)}</b><span>Responses</span></div></div>`;
  HAS_CODING = data.jobs.some(j => /^(medium|high)$/i.test(j.coding || ''));
  const n = activeCount();
  html += `<div class="bar"><input class="search" id="q" type="search" placeholder="Search company, title, location, pay" value="${esc(q)}">
    <button class="fbtn${n || panelOpen ? ' on' : ''}" id="fbtn">${TUNE}Filters${n ? ` <span class="n">${n}</span>` : ''}</button></div>`;
  if (panelOpen) html += panel();
  let jobs = data.jobs;
  if (view === 'next') {
    jobs = jobs.filter(j => ACTION.has(j.status));
  } else {
    const F = {Open: j => j.status !== 'Rejected / Not Pursued' && j.status !== 'Rejected by Employer', 'To apply': j => ACTION.has(j.status),
      Applied: j => j.status === 'Applied', Responses: j => /Interview|Next Steps|Offer/.test(j.status), 'Filtered out': j => j.status === 'Rejected / Not Pursued', All: () => true};
    if (!F[filter]) filter = 'Open';
    html += `<div class="chips">${Object.keys(F).map(k => `<button class="chip${k === filter ? ' on' : ''}" data-f="${k}">${k}</button>`).join('')}</div>`;
    jobs = jobs.filter(F[filter]);
    if (filter !== 'To apply') jobs = [...jobs].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || (b.date || '').localeCompare(a.date || ''));
  }
  jobs = applyFilters(jobs);
  html += `<p class="count">${jobs.length} job${jobs.length === 1 ? '' : 's'}${n ? ` · ${n} filter${n === 1 ? '' : 's'} on` : ''}</p>`;
  html += jobs.length ? `<div id="list">${jobs.slice(0, shown).map(card).join('')}</div>` : `<div class="empty">${view === 'next' && !activeCount() && !q ? 'Nothing waiting to apply. Nice.' : 'No jobs match these filters.'}</div>`;
  if (jobs.length > shown) html += `<button class="btn text more" id="more">Show more (${jobs.length - shown})</button>`;
  const keep = document.activeElement && document.activeElement.id === 'q';
  v.innerHTML = html;
  if (keep) { const i = $('#q'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
}

function renderFiles(v) {
  if (!files) { v.innerHTML = '<div class="empty">Loading files…</div>'; return; }
  const t = q.toLowerCase();
  const list = files.files.filter(f => !t || (f.name + ' ' + f.jobs.join(' ')).toLowerCase().includes(t));
  v.innerHTML = `<input class="search" id="q" type="search" placeholder="Search files or jobs" value="${esc(q)}">` +
    (list.length ? list.slice(0, shown).map(f => `<div class="file"><div class="fi">${ICON.doc}</div>
      <a class="fn" href="${esc(f.url)}" target="_blank"><b>${esc(f.name)}</b><span>${f.kind === 'resume' ? 'Resume' : 'Cover letter'} · ${f.kb} KB${f.jobs.length ? ' · ' + esc(f.jobs.slice(0, 2).join(', ')) + (f.jobs.length > 2 ? ` +${f.jobs.length - 2}` : '') : ''}</span></a>
      <a class="icon-btn" href="${esc(f.url)}?dl=1" aria-label="Download" title="Download">${ICON.dl}</a></div>`).join('')
      : '<div class="empty">No files.</div>') +
    (list.length > shown ? `<button class="btn text more" id="more">Show more (${list.length - shown})</button>` : '');
  const i = $('#q'); if (document.activeElement === document.body && q) { i.focus(); }
}

document.addEventListener('input', e => { if (e.target.id === 'q') { q = e.target.value; shown = 40; render(); const i = $('#q'); i.focus(); i.setSelectionRange(q.length, q.length); } });
document.addEventListener('click', async e => {
  const nb = e.target.closest('nav button');
  if (nb) { view = nb.dataset.v; localStorage.setItem('jd-view', view); q = ''; shown = 40; panelOpen = false; window.scrollTo(0, 0);
    if (view === 'files' && !files) { render(); try { files = await get('/api/files'); } catch (_) {} } render(); return; }
  if (e.target.closest('#fbtn')) { panelOpen = !panelOpen; render(); return; }
  if (e.target.closest('#fdone')) { panelOpen = false; render(); return; }
  if (e.target.closest('#fclear')) { fs = FDEF(); q = ''; saveFs(); shown = 40; render(); return; }
  const mc = e.target.closest('[data-m]');
  if (mc) { const k = mc.dataset.m, v = mc.dataset.val; fs[k] = fs[k].includes(v) ? fs[k].filter(x => x !== v) : [...fs[k], v]; saveFs(); shown = 40; render(); return; }
  const tg = e.target.closest('[data-tg]'); if (tg) { fs[tg.dataset.tg] = !fs[tg.dataset.tg]; saveFs(); shown = 40; render(); return; }
  const ch = e.target.closest('.chip[data-f]'); if (ch) { filter = ch.dataset.f; localStorage.setItem('jd-filter', filter); shown = 40; render(); return; }
  if (e.target.id === 'more') { shown += 40; render(); return; }
  if (e.target.closest('#refresh')) load(true);
});
document.addEventListener('change', async e => {
  const fsel = e.target.closest('[data-s]');
  if (fsel) { const k = fsel.dataset.s; fs[k] = (k === 'days' || k === 'pay') ? +fsel.value : fsel.value; saveFs(); shown = 40; render(); return; }
  const s = e.target.closest('.status'); if (!s) return;
  const was = s.dataset.was, status = s.value;
  if (!confirm(`Change status to “${status}”?`)) { s.value = was; return; }
  s.disabled = true;
  const r = await fetch('/api/status', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({i: +s.dataset.i, status, was})}).catch(() => null);
  if (r && r.ok) { snack(`Marked ${status}`); load(); }
  else { s.value = was; s.disabled = false; snack(r ? (await r.json()).error || 'Could not save' : 'Laptop offline — not saved'); }
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
load();
</script></body></html>"""


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else CONFIG["port"]
    code = passcode()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"{CONFIG['name']} (mobile) on http://127.0.0.1:{port}/  passcode: {code}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
