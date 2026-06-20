/*
=== NoemaForge File Header ===
File: noemaforge/templates/ui-dashboard/app.js
Zone: release/package
Version: 0.32.1
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

function makeNode(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = String(text ?? "");
  return node;
}

function muted(text) {
  return makeNode("div", "muted", text);
}

function replaceWith(target, nodes) {
  target.replaceChildren(...(Array.isArray(nodes) ? nodes : [nodes]));
}

function badge(text, cls) {
  return makeNode("span", `badge ${cls}`, text);
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
  if (keys.length === 0) return [muted("no data")];
  return keys.flatMap((k) => [makeNode("div", "k", k), makeNode("div", "v", fmt(obj[k]))]);
}

function renderTaskRow(t) {
  const left = `${fmt(t.priority_class)} / ${fmt(t.domain)}`;
  const right = `${fmt(t.task_id)} — ${fmt(t.title)}`;
  const row = makeNode("div", "row");
  row.append(makeNode("div", "c0", left), makeNode("div", "c1", right));
  return row;
}

function renderEventRow(e) {
  const left = `${fmt(e.ts)}`;
  const typ = fmt(e.type);
  const sev = fmt(e.severity);
  const decision = fmt(e.decision);
  const row = makeNode("div", "row");
  row.append(makeNode("div", "c0", left), makeNode("div", "c1", `${sev} ${typ} — ${decision}`));
  return row;
}

function renderTelemRow(x) {
  const left = `${fmt(x.ts)}`;
  const kind = fmt(x.kind);
  const model = fmt(x.model);
  const ms = fmt(x.latency_ms);
  const row = makeNode("div", "row");
  row.append(makeNode("div", "c0", left), makeNode("div", "c1", `${kind} — ${model} (${ms} ms)`));
  return row;
}

function renderFlow(flow, activeRole) {
  if (!flow || !flow.nodes || flow.nodes.length === 0) return muted("no flow");
  const target = makeNode("div", "flow");
  flow.nodes.forEach((n) => {
    const role = fmt(n.role);
    target.append(makeNode("span", role === activeRole ? "node active" : "node", role));
  });
  return target;
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

  const pills = makeNode("div");
  pills.style.textAlign = "right";
  [
    badge(`prio:${prio}`, "warn"), badge(`status:${st}`, st === "active" ? "good" : "warn"),
    badge(`stream:${stream}`, "warn"), badge(`wakes:${wakes}`, wakes > 0 ? "warn" : "good"),
    badge(`todo:${backlog}`, backlog > 0 ? "warn" : "good"),
  ].forEach((item) => { pills.append(item, document.createTextNode(" ")); });
  const nextWake = p.team && p.team.wakeq ? p.team.wakeq.next : null;
  const block = makeNode("div");
  block.style.marginBottom = "12px";
  const head = makeNode("div");
  Object.assign(head.style, {display:"flex", alignItems:"center", justifyContent:"space-between", gap:"10px"});
  const labels = makeNode("div");
  const titleNode = makeNode("div", "", title);
  titleNode.style.fontWeight = "700";
  labels.append(titleNode, makeNode("div", "muted mono", `${p.project_id}${activeRole ? " • active: " + activeRole : ""}`));
  head.append(labels, pills);
  block.append(head);
  if (nextWake) block.append(makeNode("div", "mono muted", `next wake: ${fmt(nextWake.to_role)} ← ${fmt(nextWake.from_role)} :: ${fmt(nextWake.objective)}`));
  block.append(renderFlow(p.flow, activeRole));
  return block;
}


function renderInboxBuckets(buckets) {
  if (!buckets || buckets.length === 0) return muted("no buckets");
  const top = buckets.slice(0, 8);
  const target = makeNode("div");
  top.forEach((b) => {
    const name = fmt(b.bucket) || "(root)";
    const files = Number(b.files || 0);
    target.append(badge(name + ":" + files, files > 0 ? "warn" : "good"));
    target.append(document.createTextNode(" "), makeNode("span", "muted mono", fmtBytes(b.bytes || 0)), document.createTextNode(" "));
  });
  return target;
}

function renderInboxRecent(items) {
  if (!items || items.length === 0) return muted("empty");
  const target = makeNode("div", "table");
  items.slice(0, 10).forEach((x) => {
      const left = `${fmt(x.mtime)}`;
      const p = fmt(x.path);
      const sz = fmtBytes(x.size || 0);
      const row = makeNode("div", "row");
      const detail = makeNode("div", "c1", `${p} `);
      detail.append(makeNode("span", "muted mono", `(${sz})`));
      row.append(makeNode("div", "c0", left), detail);
      target.append(row);
    });
  return target;
}

function renderInboxBlock(title, obj) {
  if (!obj || obj.available !== true) {
    const missing = makeNode("div");
    missing.style.marginBottom = "14px";
    const heading = makeNode("div", "", title);
    heading.style.fontWeight = "700";
    missing.append(heading, makeNode("div", "muted mono", "not available"));
    return missing;
  }
  const files = Number(obj.total_files || 0);
  const bytes = fmtBytes(obj.total_bytes || 0);
  const block = makeNode("div");
  block.style.marginBottom = "16px";
  const head = makeNode("div");
  Object.assign(head.style, {display:"flex", alignItems:"center", justifyContent:"space-between", gap:"10px"});
  const labels = makeNode("div");
  const heading = makeNode("div", "", title);
  heading.style.fontWeight = "700";
  labels.append(heading);
  if (obj.base_dir) labels.append(makeNode("div", "muted mono", fmt(obj.base_dir)));
  const pills = makeNode("div");
  pills.style.textAlign = "right";
  pills.append(badge(`files:${files}`, files > 0 ? "warn" : "good"), document.createTextNode(" "), badge(`size:${bytes}`, files > 0 ? "warn" : "good"));
  head.append(labels, pills);
  const buckets = renderInboxBuckets(obj.by_bucket || []);
  buckets.style.marginTop = "8px";
  const recent = renderInboxRecent(obj.recent || []);
  recent.style.marginTop = "10px";
  block.append(head, buckets, recent);
  return block;
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
    replaceWith(el("nowKv"), renderKV(nowObj));

    const tq = snap.taskqueue || {};
    const sum = tq.summary || {};
    const tqSummary = el("tqSummary");
    tqSummary.replaceChildren(document.createTextNode("db: "), makeNode("span", "mono", fmt(tq.db_path)), document.createTextNode(
      ` • TODO:${fmt(sum.TODO)} IN_PROGRESS:${fmt(sum.IN_PROGRESS)} DONE:${fmt(sum.DONE)} DEAD:${fmt(sum.DEADLETTER)}`
    ));

    const cur = tq.current;
    el("tqCurrent").textContent = cur ? `${fmt(cur.task_id)} — ${fmt(cur.title)} (${fmt(cur.domain)})` : "–";

    const next = tq.next || [];
    replaceWith(el("tqNext"), next.length ? next.slice(0, 14).map(renderTaskRow) : muted("empty"));

    const pr = snap.projects || {};
    const items = pr.items || [];
    replaceWith(el("projectsList"), items.length ? items.map(renderProject) : muted("no projects"));

    const ev = snap.events || {};
    const evs = ev.recent || [];
    replaceWith(el("eventsTable"), evs.length ? evs.slice(-30).map(renderEventRow) : muted("no events"));

    const tl = snap.telemetry || {};
    const calls = tl.recent_llm_calls || [];
    replaceWith(el("telemetryTable"), calls.length ? calls.slice(-20).map(renderTelemRow) : muted("no calls"));

    const ib = snap.inboxes || {};
    const lib = ib.library || null;
    const vault = ib.vault || null;
    const ws = ib.workspace || null;

    const totalFiles = (lib && lib.total_files ? Number(lib.total_files) : 0) + (vault && vault.total_files ? Number(vault.total_files) : 0) + (ws && ws.total_files ? Number(ws.total_files) : 0);
    el("inboxSummary").replaceChildren(
      document.createTextNode("total files: "), makeNode("span", "mono", totalFiles),
      document.createTextNode(" • "), makeNode("span", "muted", "Library/Vault/Workspace inboxes")
    );

    replaceWith(el("inboxBlocks"), [
      renderInboxBlock("Library inbox", lib),
      renderInboxBlock("Vault inbox", vault),
      renderInboxBlock("Workspace inbox", ws),
    ]);
  } catch (e) {
    setStatus(false, "offline");
  }
}

if (typeof window !== "undefined" && window.document === document) {
  setStatus(null, "starting…");
  tick();
  setInterval(tick, 2000);
}
