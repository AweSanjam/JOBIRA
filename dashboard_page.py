#!/usr/bin/env python3
"""The JOBIRA dashboard page, shared by local_dashboard_server.py (live: polls
/api/jobs, can change statuses) and build_dashboard.py (static snapshot with the
data baked in). payload() is the single JSON shape both use.
"""
import json
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import rank
import tracker

PACIFIC = ZoneInfo("America/Los_Angeles")


def payload(rows=None, live=True):
    rows = tracker.read_rows() if rows is None else rows
    ranked = {r["_idx"]: r for r in rank.rank(rows, statuses=rank.OPEN)}
    jobs = []
    for r in rows:
        rk = ranked.get(r["_idx"])
        files = {}
        for key, col in (("resume", "Resume Path"), ("cover", "Cover Letter Path")):
            path = r[col]
            if tracker.resolve(path):
                files[key] = ("/files?p=" + quote(path)) if live else path
            elif path and not path.lower().endswith((".pdf", ".docx")):
                files["reason"] = path
            elif path:
                files[key + "_missing"] = path
        jobs.append({
            "i": r["_idx"], "date": r["Date Found"], "company": r["Company"], "title": r["Job Title"],
            "location": r["Location"], "work": tracker.work_type(r["Location"]), "bc": tracker.is_bc(r["Location"]),
            "salary": r["Salary"], "licence": r["Requires Class 5 Licence"], "match": r["Match Score"],
            "tier": tracker.match_tier(r["Match Score"]), "ats": tracker.ats_percent(r["Match Score"]),
            "coding": r["Coding Intensity"], "status": r["Status"], "url": r["Job URL"], "files": files,
            "score": rk["_score"] if rk else None, "why": rk["_why"] if rk else [],
            "actionable": r["Status"] in rank.ACTIONABLE,
        })
    return {"generated": datetime.now(PACIFIC).strftime("%Y-%m-%d %H:%M %Z"), "counts": tracker.counts(rows),
            "statuses": tracker.STATUSES, "system_reject": tracker.SYSTEM_REJECT, "live": live, "jobs": jobs}


def render(live=True, data=None):
    """Full HTML. Live pages fetch /api/jobs; static pages embed `data`."""
    boot = "null" if live else json.dumps(data).replace("</", "<\\/")
    return PAGE.replace("__BOOT__", boot).replace("__MODE__", "live" if live else "snapshot")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JOBIRA Dashboard</title>
<style>
:root {
  --bg: #0b0f14; --panel: #121821; --panel2: #18202b; --line: #243042; --text: #e6edf5; --muted: #8b98a9;
  --accent: #38bdf8; --success: #4ade80; --success-bg: rgba(74,222,128,.13); --warn: #fbbf24; --warn-bg: rgba(251,191,36,.13);
  --danger: #f87171; --danger-bg: rgba(248,113,113,.13); --info: #60a5fa; --info-bg: rgba(96,165,250,.13);
  --violet: #c084fc; --violet-bg: rgba(192,132,252,.14); --orange: #fb923c; --orange-bg: rgba(251,146,60,.14);
}
@media (prefers-color-scheme: light) {
  :root { --bg: #f5f7fb; --panel: #ffffff; --panel2: #f0f3f8; --line: #dde3ec; --text: #16202c; --muted: #5d6b7c;
    --success-bg: #e3f8ea; --warn-bg: #fff4d6; --danger-bg: #fde6e6; --info-bg: #e3efff; --violet-bg: #f1e6fe; --orange-bg: #ffeddc;
    --success: #15803d; --warn: #a16207; --danger: #b91c1c; --info: #1d4ed8; --violet: #7e22ce; --orange: #c2410c; --accent: #0369a1; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--accent); text-decoration: none; } a:hover { text-decoration: underline; }
.wrap { max-width: 1400px; margin: 0 auto; padding: 20px 16px 60px; }
header { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
.wordmark { font-weight: 800; font-size: 22px; letter-spacing: .08em; }
.tagline { color: var(--muted); }
.live { margin-left: auto; color: var(--muted); display: flex; align-items: center; gap: 8px; font-size: 13px; }
.livedot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); display: inline-block; box-shadow: 0 0 0 0 rgba(74,222,128,.6); animation: pulse 2s infinite; }
.livedot.off { background: var(--muted); animation: none; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(74,222,128,.55);} 70% { box-shadow: 0 0 0 6px rgba(74,222,128,0);} 100% { box-shadow: 0 0 0 0 rgba(74,222,128,0);} }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 14px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
.card .n { font-size: 26px; font-weight: 700; } .card .l { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
.card .sub { color: var(--muted); font-size: 12px; }
.bar { display: flex; height: 12px; border-radius: 6px; overflow: hidden; background: var(--panel2); margin: 6px 0 4px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 12px; margin-bottom: 16px; }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }
.grid { display: grid; grid-template-columns: 340px 1fr; gap: 14px; align-items: start; }
@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
.panel h2 { margin: 0 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.next { list-style: none; margin: 0; padding: 0; }
.next li { padding: 9px 0; border-top: 1px solid var(--line); display: grid; grid-template-columns: 36px 1fr; gap: 8px; }
.next li:first-child { border-top: 0; }
.score { font-weight: 700; font-size: 15px; text-align: center; border-radius: 8px; padding: 3px 0; background: var(--info-bg); color: var(--info); height: fit-content; }
.why { color: var(--muted); font-size: 12px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
input, select { background: var(--panel2); color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px; font: inherit; }
input[type=search] { flex: 1; min-width: 200px; }
label.chk { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 13px; }
.tablewrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding: 8px; border-bottom: 1px solid var(--line); cursor: pointer; white-space: nowrap; }
td { padding: 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
tr.filtered td { opacity: .55; }
.co { font-weight: 600; } .ti { color: var(--muted); }
.pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; white-space: nowrap; }
.t-strong { background: var(--success-bg); color: var(--success); } .t-reasonable { background: var(--warn-bg); color: var(--warn); }
.t-stretch, .t-reject { background: var(--danger-bg); color: var(--danger); } .t-unscored { background: var(--panel2); color: var(--muted); }
.c-low { background: var(--info-bg); color: var(--info); } .c-medium { background: var(--warn-bg); color: var(--warn); } .c-high { background: var(--danger-bg); color: var(--danger); }
.w-remote { background: var(--info-bg); color: var(--info); } .w-hybrid { background: var(--violet-bg); color: var(--violet); }
.bc { background: var(--orange-bg); color: var(--orange); }
.s-queued-for-auto-apply { background: var(--info-bg); color: var(--info); } .s-queued-for-review { background: var(--warn-bg); color: var(--warn); }
.s-applied { background: var(--success-bg); color: var(--success); } .s-apply-failed { background: var(--orange-bg); color: var(--orange); }
.s-rejected-not-pursued, .s-rejected-by-employer { background: var(--danger-bg); color: var(--danger); }
.s-interview-scheduled, .s-offer-received { background: var(--success-bg); color: var(--success); font-weight: 700; }
.s-next-steps-assessment { background: var(--violet-bg); color: var(--violet); }
select.status { padding: 3px 6px; font-size: 12px; }
.reason { color: var(--muted); font-size: 12px; max-width: 280px; }
.muted { color: var(--muted); } .empty { color: var(--muted); padding: 30px; text-align: center; }
.toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: var(--panel2); border: 1px solid var(--line); padding: 8px 14px; border-radius: 10px; display: none; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="wordmark">JOBIRA</span>
    <span class="tagline">application pipeline &middot; <span id="mode">__MODE__</span></span>
    <span class="live"><span class="livedot" id="dot"></span><span id="updated">loading…</span></span>
  </header>

  <div class="cards" id="cards"></div>
  <div class="bar" id="bar"></div>
  <div class="legend" id="legend"></div>

  <div class="grid">
    <div class="panel">
      <h2>Apply next</h2>
      <ol class="next" id="next"></ol>
    </div>
    <div class="panel">
      <div class="filters">
        <input type="search" id="q" placeholder="Search company, title, location…">
        <select id="fStatus"><option value="">All statuses</option></select>
        <select id="fTier"><option value="">All matches</option><option>strong</option><option>reasonable</option><option>stretch</option><option>unscored</option></select>
        <select id="fWork"><option value="">Any work type</option><option>Remote</option><option>Hybrid</option><option>In-person</option></select>
        <select id="sort"><option value="rank">Sort: priority</option><option value="date">Sort: newest</option><option value="company">Sort: company</option></select>
        <label class="chk"><input type="checkbox" id="fBC"> BC only</label>
        <label class="chk"><input type="checkbox" id="fFiltered"> Show filtered-out</label>
      </div>
      <div class="tablewrap"><table>
        <thead><tr><th>Score</th><th>Found</th><th>Company / role</th><th>Location</th><th>Salary</th><th>Match</th><th>Coding</th><th>Status</th><th>Files</th></tr></thead>
        <tbody id="rows"></tbody>
      </table></div>
      <div class="empty" id="empty" style="display:none">No jobs match these filters.</div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
const BOOT = __BOOT__;
const LIVE = BOOT === null;
let DATA = BOOT, lastOk = Date.now();
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const COLORS = {"Queued for Auto-Apply":"var(--info)","Queued for Review":"var(--warn)","Applied":"var(--success)","Apply Failed":"var(--orange)",
  "Interview Scheduled":"#22c55e","Next Steps - Assessment":"var(--violet)","Offer Received":"#16a34a","Rejected by Employer":"var(--danger)"};

function toast(msg) { const t = $("toast"); t.textContent = msg; t.style.display = "block"; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = "none", 2500); }

function cards(c) {
  const s = c.by_status;
  const items = [
    ["Tracked", c.total, "excludes jobs JOBIRA filtered out"],
    ["Queued", c.queued, `${s["Queued for Auto-Apply"]||0} auto · ${s["Queued for Review"]||0} review`],
    ["Applied", c.applied, `${s["Apply Failed"]||0} failed attempts`],
    ["Responses", c.responses, `${c.response_rate}% of applied`],
    ["Interviews", s["Interview Scheduled"]||0, `${s["Next Steps - Assessment"]||0} assessments`],
    ["Offers", s["Offer Received"]||0, `${s["Rejected by Employer"]||0} employer rejections`],
    ["Filtered out", c.filtered_out, "not a match · not counted"],
  ];
  $("cards").innerHTML = items.map(([l, n, sub]) => `<div class="card"><div class="l">${l}</div><div class="n">${n}</div><div class="sub">${esc(sub)}</div></div>`).join("");
  const counted = Object.entries(s).filter(([k]) => k !== DATA.system_reject);
  const total = counted.reduce((a, [, v]) => a + v, 0) || 1;
  $("bar").innerHTML = counted.map(([k, v]) => `<div title="${esc(k)}: ${v}" style="width:${100*v/total}%;background:${COLORS[k]||"var(--muted)"}"></div>`).join("");
  $("legend").innerHTML = counted.map(([k, v]) => `<span><i style="background:${COLORS[k]||"var(--muted)"}"></i>${esc(k)} ${v}</span>`).join("");
}

function files(j) {
  const f = j.files, out = [];
  if (f.resume) out.push(`<a href="${esc(f.resume)}" target="_blank">Resume</a>`);
  if (f.cover) out.push(`<a href="${esc(f.cover)}" target="_blank">Cover</a>`);
  if (f.resume_missing || f.cover_missing) out.push(`<span class="muted" title="${esc(f.resume_missing||f.cover_missing)}">file missing</span>`);
  if (f.reason) out.push(`<div class="reason">${esc(f.reason)}</div>`);
  return out.join(" · ");
}

function statusCell(j) {
  if (!LIVE) return `<span class="pill s-${slug(j.status)}">${esc(j.status)}</span>`;
  const opts = DATA.statuses.map(s => `<option${s === j.status ? " selected" : ""}>${esc(s)}</option>`).join("");
  return `<select class="status pill s-${slug(j.status)}" data-i="${j.i}" data-was="${esc(j.status)}">${opts}</select>`;
}

function draw() {
  if (!DATA) return;
  cards(DATA.counts);
  const st = $("fStatus");
  if (st.options.length === 1) DATA.statuses.forEach(s => st.add(new Option(s, s)));
  const q = $("q").value.trim().toLowerCase(), fs = st.value, ft = $("fTier").value, fw = $("fWork").value;
  const bcOnly = $("fBC").checked, showFiltered = $("fFiltered").checked || fs === DATA.system_reject;
  let jobs = DATA.jobs.filter(j =>
    (showFiltered || j.status !== DATA.system_reject) && (!fs || j.status === fs) && (!ft || j.tier === ft) &&
    (!fw || j.work === fw) && (!bcOnly || j.bc) &&
    (!q || `${j.company} ${j.title} ${j.location} ${j.salary}`.toLowerCase().includes(q)));
  const by = $("sort").value;
  jobs.sort(by === "date" ? (a, b) => (b.date || "").localeCompare(a.date || "") || b.i - a.i
          : by === "company" ? (a, b) => a.company.localeCompare(b.company)
          : (a, b) => (b.score ?? -1) - (a.score ?? -1) || (b.date || "").localeCompare(a.date || ""));
  $("rows").innerHTML = jobs.map(j => `<tr class="${j.status === DATA.system_reject ? "filtered" : ""}">
    <td>${j.score === null ? '<span class="muted">—</span>' : `<span class="score" title="${esc(j.why.join(", "))}">${j.score}</span>`}</td>
    <td class="muted" style="white-space:nowrap">${esc(j.date)}</td>
    <td><div class="co">${esc(j.company)}</div><div class="ti">${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a>` : esc(j.title)}</div></td>
    <td>${esc(j.location)}<div>${j.bc ? '<span class="pill bc">BC</span> ' : ""}${j.work !== "In-person" ? `<span class="pill w-${slug(j.work)}">${j.work}</span>` : ""}</div></td>
    <td class="muted">${esc(j.salary)}</td>
    <td><span class="pill t-${j.tier}" title="${esc(j.match)}">${esc(j.tier)}${j.ats ? " · " + j.ats + "%" : ""}</span></td>
    <td>${j.coding ? `<span class="pill c-${slug(j.coding)}">${esc(j.coding)}</span>` : ""}${j.licence === "Yes" ? '<div class="muted">Class 5</div>' : ""}</td>
    <td>${statusCell(j)}</td>
    <td>${files(j)}</td></tr>`).join("");
  $("empty").style.display = jobs.length ? "none" : "block";
  const next = DATA.jobs.filter(j => j.actionable && j.score !== null).sort((a, b) => b.score - a.score).slice(0, 10);
  $("next").innerHTML = next.length ? next.map(j => `<li><div class="score">${j.score}</div><div>
      <div class="co">${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.company)}</a>` : esc(j.company)}</div>
      <div>${esc(j.title)}</div><div class="why">${esc(j.status)} · ${esc(j.why.join(", "))}</div></div></li>`).join("")
    : '<li class="muted" style="display:block">Nothing queued.</li>';
}

function stamp() {
  if (!DATA) return;
  if (!LIVE) { $("updated").textContent = "snapshot " + DATA.generated; $("dot").classList.add("off"); return; }
  const age = Math.round((Date.now() - lastOk) / 1000);
  $("updated").textContent = age > 15 ? `offline — last update ${age}s ago` : `live · ${DATA.generated}`;
  $("dot").classList.toggle("off", age > 15);
}

async function poll() {
  try {
    const r = await fetch("/api/jobs", {cache: "no-store"});
    if (!r.ok) throw new Error(r.status);
    DATA = await r.json(); lastOk = Date.now();
    if (!document.activeElement || document.activeElement.tagName !== "SELECT") draw();
  } catch (e) { /* keep the last good data; the stamp shows it's stale */ }
  stamp();
}

document.addEventListener("change", async e => {
  const el = e.target;
  if (!el.classList.contains("status")) { draw(); return; }
  const r = await fetch("/api/status", {method: "POST", headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({i: +el.dataset.i, status: el.value, was: el.dataset.was})});
  const res = await r.json().catch(() => ({}));
  toast(r.ok ? `Status → ${el.value}` : (res.error || "Couldn't save"));
  el.blur(); poll();
});
["q"].forEach(id => $(id).addEventListener("input", draw));

if (LIVE) { poll(); setInterval(poll, 5000); } else { draw(); stamp(); }
setInterval(stamp, 1000);
</script>
</body>
</html>
"""
