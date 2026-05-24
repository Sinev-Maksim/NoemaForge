/*
=== NoemaForge File Header ===
File: noemaforge/templates/ui-dashboard/app.js
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Render the local Admin GUI and call backend JSON APIs.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
*/
/* NoemaForge Dashboard (v0.22.0)

   Dependency-free UI.
   Polls /api/snapshot and renders:
     - runtime state
     - task queue (current + next)
     - projects (team semaphore + wakeq + flow)
     - recent SEL events
     - recent telemetry metadata
*/

function el(id) {
  return document.getElementById(id);
}

function fmtBytes(n) {
  const x = Number(n || 0);
  if (!isFinite(x) || x <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = x;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v = v / 1024;
    i += 1;
  }
  const s = v >= 10 || i === 0 ? v.toFixed(0) : v.toFixed(1);
  return `${s} ${units[i]}`;
}

function fmt(x) {
  if (x === null || x === undefined) return "–";
  if (typeof x === "string" && x.trim() === "") return "–";
  return String(x);
}

function badge(text, cls) {
  return `<span class="badge ${cls}">${text}</span>`;
}

function setStatus(ok, text) {
  el("statusText").textContent = text;
  const dot = el("statusDot");
  if (ok === true) dot.style.background = "var(--good)";
  else if (ok === false) dot.style.background = "var(--bad)";
  else dot.style.background = "var(--warn)";
}

function renderKV(obj) {
  const keys = Object.keys(obj);
  if (keys.length === 0) return "<div class='muted'>no data</div>";
  return keys
    .map((k) => {
      return `<div class='k'>${k}</div><div class='v'>${fmt(obj[k])}</div>`;
    })
    .join("");
}

function renderTaskRow(t) {
  const left = `${fmt(t.priority_class)} / ${fmt(t.domain)}`;
  const right = `${fmt(t.task_id)} — ${fmt(t.title)}`;
  return `<div class='row'><div class='c0'>${left}</div><div class='c1'>${right}</div></div>`;
}

function renderEventRow(e) {
  const left = `${fmt(e.ts)}`;
  const typ = fmt(e.type);
  const sev = fmt(e.severity);
  const decision = fmt(e.decision);
  return `<div class='row'><div class='c0'>${left}</div><div class='c1'>${sev} ${typ} — ${decision}</div></div>`;
}

function renderTelemRow(x) {
  const left = `${fmt(x.ts)}`;
  const kind = fmt(x.kind);
  const model = fmt(x.model);
  const ms = fmt(x.latency_ms);
  return `<div class='row'><div class='c0'>${left}</div><div class='c1'>${kind} — ${model} (${ms} ms)</div></div>`;
}

function renderFlow(flow, activeRole) {
  if (!flow || !flow.nodes || flow.nodes.length === 0) return "<div class='muted'>no flow</div>";
  const nodes = flow.nodes
    .map((n) => {
      const role = fmt(n.role);
      const cls = role === activeRole ? "node active" : "node";
      return `<span class='${cls}'>${role}</span>`;
    })
    .join("");
  return `<div class='flow'>${nodes}</div>`;
}

function renderProject(p) {
  const title = fmt(p.title) || p.project_id;
  const prio = fmt(p.priority);
  const st = fmt(p.status);
  const stream = fmt(p.stream_id);

  let activeRole = "";
  const sem = p.team && p.team.semaphore ? p.team.semaphore : null;
  if (sem && sem.active && sem.active.role_id) activeRole = fmt(sem.active.role_id);

  const wakes = p.team && p.team.wakeq ? p.team.wakeq.pending : 0;
  const backlog = p.backlog && p.backlog.counts ? p.backlog.counts.todo : 0;

  const pills = [
    badge(`prio:${prio}`, "warn"),
    badge(`status:${st}`, st === "active" ? "good" : "warn"),
    badge(`stream:${stream}`, "warn"),
    badge(`wakes:${wakes}`, wakes > 0 ? "warn" : "good"),
    badge(`todo:${backlog}`, backlog > 0 ? "warn" : "good"),
  ].join(" ");

  const nextWake = p.team && p.team.wakeq ? p.team.wakeq.next : null;
  const wakeLine = nextWake
    ? `<div class='mono muted'>next wake: ${fmt(nextWake.to_role)} ← ${fmt(nextWake.from_role)} :: ${fmt(
        nextWake.objective
      )}</div>`
    : "";

  return `
    <div style="margin-bottom: 12px;">
      <div style="display:flex; align-items:center; justify-content: space-between; gap:10px;">
        <div>
          <div style="font-weight:700;">${title}</div>
          <div class="muted mono">${p.project_id}${activeRole ? " • active: " + activeRole : ""}</div>
        </div>
        <div style="text-align:right;">${pills}</div>
      </div>
      ${wakeLine}
      ${renderFlow(p.flow, activeRole)}
    </div>
  `;
}


function renderInboxBuckets(buckets) {
  if (!buckets || buckets.length === 0) return "<div class='muted'>no buckets</div>";
  const top = buckets.slice(0, 8);
  return top
    .map((b) => {
      const name = fmt(b.bucket) || "(root)";
      const files = Number(b.files || 0);
      const bytes = fmtBytes(b.bytes || 0);
      const cls = files > 0 ? "warn" : "good";
      return `${badge(name + ":" + files, cls)} <span class='muted mono'>${bytes}</span>`;
    })
    .join(" ");
}

function renderInboxRecent(items) {
  if (!items || items.length === 0) return "<div class='muted'>empty</div>";
  return items
    .slice(0, 10)
    .map((x) => {
      const left = `${fmt(x.mtime)}`;
      const p = fmt(x.path);
      const sz = fmtBytes(x.size || 0);
      return `<div class='row'><div class='c0'>${left}</div><div class='c1'>${p} <span class='muted mono'>(${sz})</span></div></div>`;
    })
    .join("");
}

function renderInboxBlock(title, obj) {
  if (!obj || obj.available !== true) {
    return `<div style="margin-bottom: 14px;"><div style="font-weight:700;">${title}</div><div class='muted mono'>not available</div></div>`;
  }
  const files = Number(obj.total_files || 0);
  const bytes = fmtBytes(obj.total_bytes || 0);
  const pills = [
    badge(`files:${files}`, files > 0 ? "warn" : "good"),
    badge(`size:${bytes}`, files > 0 ? "warn" : "good"),
  ].join(" ");

  const base = obj.base_dir ? `<div class='muted mono'>${fmt(obj.base_dir)}</div>` : "";
  const buckets = renderInboxBuckets(obj.by_bucket || []);
  const recent = renderInboxRecent(obj.recent || []);

  return `
    <div style="margin-bottom: 16px;">
      <div style="display:flex; align-items:center; justify-content: space-between; gap:10px;">
        <div>
          <div style="font-weight:700;">${title}</div>
          ${base}
        </div>
        <div style="text-align:right;">${pills}</div>
      </div>
      <div style="margin-top:8px;">${buckets}</div>
      <div style="margin-top:10px;" class="table">${recent}</div>
    </div>
  `;
}


async function tick() {
  try {
    const r = await fetch("/api/snapshot", { cache: "no-store" });
    const ok = r.ok;
    const snap = await r.json();
    if (!ok) {
      setStatus(false, "snapshot error");
      return;
    }

    setStatus(true, "online");
    el("ts").textContent = fmt(snap.generated_at);

    const rt = snap.runtime_state || {};
    const nowObj = {
      state: fmt(rt.state),
      last_activity: fmt(rt.last_activity_ts),
      last_domain: fmt(rt.last_activity_domain),
      idle_armed: fmt(rt.idle_armed_ts),
      idle_triggered: fmt(rt.idle_triggered_ts),
      auto_cycle: fmt(rt.auto_cycle_active),
      auto_steps: fmt(rt.auto_cycle_steps),
      note: fmt(rt.note),
      last_error: fmt(rt.last_error),
    };
    el("nowKv").innerHTML = renderKV(nowObj);

    const tq = snap.taskqueue || {};
    const sum = tq.summary || {};
    el("tqSummary").innerHTML = `db: <span class='mono'>${fmt(tq.db_path)}</span> • TODO:${fmt(
      sum.TODO
    )} IN_PROGRESS:${fmt(sum.IN_PROGRESS)} DONE:${fmt(sum.DONE)} DEAD:${fmt(sum.DEADLETTER)}`;

    const cur = tq.current;
    el("tqCurrent").textContent = cur ? `${fmt(cur.task_id)} — ${fmt(cur.title)} (${fmt(cur.domain)})` : "–";

    const next = tq.next || [];
    el("tqNext").innerHTML = next.length
      ? next.slice(0, 14).map(renderTaskRow).join("")
      : "<div class='muted'>empty</div>";

    const pr = snap.projects || {};
    const items = pr.items || [];
    el("projectsList").innerHTML = items.length
      ? items.map(renderProject).join("")
      : "<div class='muted'>no projects</div>";

    const ev = snap.events || {};
    const evs = ev.recent || [];
    el("eventsTable").innerHTML = evs.length
      ? evs.slice(-30).map(renderEventRow).join("")
      : "<div class='muted'>no events</div>";

    const tl = snap.telemetry || {};
    const calls = tl.recent_llm_calls || [];
    el("telemetryTable").innerHTML = calls.length
      ? calls.slice(-20).map(renderTelemRow).join("")
      : "<div class='muted'>no calls</div>";

    const ib = snap.inboxes || {};
    const lib = ib.library || null;
    const vault = ib.vault || null;
    const ws = ib.workspace || null;

    const totalFiles = (lib && lib.total_files ? Number(lib.total_files) : 0) + (vault && vault.total_files ? Number(vault.total_files) : 0) + (ws && ws.total_files ? Number(ws.total_files) : 0);
    el("inboxSummary").innerHTML = `total files: <span class='mono'>${totalFiles}</span> • <span class='muted'>Library/Vault/Workspace inboxes</span>`;

    el("inboxBlocks").innerHTML =
      renderInboxBlock("Library inbox", lib) +
      renderInboxBlock("Vault inbox", vault) +
      renderInboxBlock("Workspace inbox", ws);
  } catch (e) {
    setStatus(false, "offline");
  }
}

setStatus(null, "starting…");
tick();
setInterval(tick, 2000);
