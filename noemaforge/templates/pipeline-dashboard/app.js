/*
=== NoemaForge File Header ===
File: templates/pipeline-dashboard/app.js
Zone: gui/shell
Version: 0.32.2
Created: 2026-05-10
Modified: 2026-05-28
Purpose: Stateful Admin GUI frontend: backend-owned chat history, persona portraits,
  telemetry, epoch controls, task/job/pipeline dock, right-click pipeline menu and
  safe plan-first actions. Session restore on load; event polling with dedup.
Inputs: JSON APIs from src/admin_gui_server.py.
Outputs: DOM updates only; privileged actions are requested as audited jobs/plans.
Tests: browser smoke + curl dashboard backend + manual send/refresh/history test.
=== End NoemaForge File Header ===
*/
const el = id => document.getElementById(id);
let allMessages = {};
let activeLocale = 'ru';
let latestRaw = {};
let pendingAction = null;
let pipelineCatalog = [];
let pipelineFilter = 'All';
let jobStream = null;
let pipelineEditorState = {pipeline_id:'', title:'', description:'', stages:[]};
let publicShowcaseScenario = null;
let latestArtifacts = [];
let lastEventIndex = 0;
// server_epoch detects server restarts even when rotation_count stays 0.
// rotation_count detects in-process log rotations.
// Both trigger a lastEventIndex reset to avoid missing or duplicating events.
let lastServerEpoch = null;
let lastRotationCount = 0;
let restoredSelectionMode = {mode:'full_composite', composite_top_n:4};

const DASHBOARD_API_ENDPOINT = '/api/dashboard';
const GUI_STATE_FALLBACK_ENDPOINT = '/api/gui/state';

const personaNames = {
  Admin: 'Admin', Optimizer: 'Optimizer', 'Model Evolution': 'Model Evolution', 'Dev Team': 'Dev Team',
  'Music Team': 'Music Team', 'Video Team': 'Video Team', 'Vision Team': 'Vision Team', Runtime: 'Runtime',
  'Task Manager': 'Task Manager', System: 'System'
};

function t(key, fallback){ return (allMessages[activeLocale] && allMessages[activeLocale][key]) || fallback || key; }
function setText(id, value){ const node = el(id); if(node) node.textContent = value; }
function setPlaceholder(id, value){ const node = el(id); if(node) node.placeholder = value; }
function makeNode(tag, className='', text=''){
  const node = document.createElement(tag);
  if(className) node.className = className;
  node.textContent = String(text ?? '');
  return node;
}
function replaceWithNodes(target, nodes){ target.replaceChildren(...nodes); }
function showMuted(target, text){ replaceWithNodes(target, [makeNode('p', 'muted', text)]); }
function safeLocalUrl(value){
  if(!value) return '';
  try{
    const base = typeof window === 'undefined' ? 'http://localhost' : window.location.origin;
    const url = new URL(String(value), base);
    if(url.origin !== base || !['http:', 'https:'].includes(url.protocol)) return '';
    return `${url.pathname}${url.search}${url.hash}`;
  }catch(_){ return ''; }
}
function speakerLabel(who){
  const text = String(who || '');
  if(text.toLowerCase() === 'user') return t('role.user', 'User');
  if(text.toLowerCase() === 'admin') return t('role.admin', 'Admin');
  return personaNames[text] || text || t('role.admin', 'Admin');
}
function speakerClass(who){ return String(who || '').toLowerCase() === 'user' ? 'User' : 'Admin'; }
function applyLocaleMessages(){
  setText('main-chat-title', t('section.main_chat', 'Main chat'));
  setText('chat-status', t('status.ready', 'ready'));
  setPlaceholder('admin-message', t('chat.placeholder', 'Write to Admin'));
  setText('admin-send', t('chat.send', 'Send'));
  setText('depth-steps-label', t('depth.steps', 'Steps'));
  setText('depth-minutes-label', t('depth.minutes', 'Minutes'));
  setText('depth-until-stop-label', t('depth.until_stop', 'until stop'));
  setText('workflow-stop', t('workflow.stop', 'Stop loop'));
  setText('pipeline-dock-title', t('pipeline.dock', 'Pipeline Dock'));
  setPlaceholder('pipeline-search', t('pipeline.search', 'Search pipeline...'));
  setText('pipeline-new', t('pipeline.new', '+ New pipeline'));
}
async function api(path, body){
  const opts = body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = {};
  try{ data = text ? JSON.parse(text) : {}; }catch(e){ data = {ok:false, error:text}; }
  if(!res.ok) throw new Error(data.error || text || res.statusText);
  return data;
}

function addMessage(who, text, cls=''){
  const div = document.createElement('div');
  div.className = `bubble ${speakerClass(who)}${cls ? ' '+cls : ''}`;
  div.appendChild(makeNode('small', '', speakerLabel(who)));
  div.appendChild(document.createTextNode(String(text || '')));
  el('chat-log').appendChild(div);
  el('chat-log').scrollTop = el('chat-log').scrollHeight;
}
function addSystemLine(text){
  const div = document.createElement('div');
  div.className = 'system-line';
  div.textContent = text;
  el('chat-log').appendChild(div);
  el('chat-log').scrollTop = el('chat-log').scrollHeight;
}
function setPersona(name, portraitUrl){
  el('active-persona').textContent = name || 'Admin';
  const img = el('persona-portrait');
  if(portraitUrl){ img.src = portraitUrl; }
  img.onerror = () => { img.src = '/ui/personas/avatars/fallback/operator-admin-administrator.svg'; };
}
function renderConversation(history){
  el('chat-log').replaceChildren();
  const msgs = history.messages || [];
  if(!msgs.length){ addMessage('Admin', t('startup.ready','Ready. Say “Hello”, ask Dev Team, model optimization, or media plan.')); return; }
  for(const m of msgs){
    if(m.system_event) addSystemLine(m.text);
    else addMessage(m.role === 'user' ? 'User' : (m.persona || m.role || 'Admin'), m.text || '');
  }
}
function artifactGroup(type){
  if(String(type).includes('model_selection') || String(type).includes('epoch')) return 'Model selection / epoch';
  if(String(type).includes('model_evolution')) return 'Model evolution';
  if(String(type).includes('pipeline') || String(type).includes('run_dir')) return 'Pipeline runs';
  if(String(type).includes('runtime')) return 'Runtime';
  if(String(type).includes('task')) return 'Tasks';
  return 'Other';
}
function artifactPath(a){ return String(a?.path || '').trim(); }
function artifactPreviewUrl(a){ const p = artifactPath(a); return safeLocalUrl(a?.preview_url || a?.open_url || (p ? `/api/artifacts/open?path=${encodeURIComponent(p)}` : '')); }
function artifactDownloadUrl(a){ const p = artifactPath(a); return safeLocalUrl(a?.download_url || (p ? `/api/artifacts/download?path=${encodeURIComponent(p)}` : '')); }
async function openArtifact(index){
  const artifact = latestArtifacts[Number(index)];
  const url = artifactPreviewUrl(artifact);
  if(!url) return;
  try{ showModal(artifact?.label || artifact?.type || 'Artifact', await api(url)); }
  catch(e){ showModal('Artifact unavailable', {ok:false, error:String(e), path:artifactPath(artifact)}); }
}
function renderArtifacts(items){
  const list = items || [];
  latestArtifacts = list;
  const target = el('artifacts');
  if(!list.length){ showMuted(target, t('artifact.none','No artifacts yet.')); return; }
  const groups = {};
  list.forEach((a, index) => { (groups[artifactGroup(a.type || a.label)] ||= []).push({artifact:a, index}); });
  const nodes = [];
  Object.entries(groups).forEach(([g, arr]) => {
    nodes.push(makeNode('h3', 'muted', g));
    arr.slice(-8).reverse().forEach(({artifact:a, index}) => {
    const downloadUrl = artifactDownloadUrl(a);
      const card = makeNode('div', 'artifact');
      card.append(makeNode('b', '', a.label || a.type || 'artifact'));
      card.append(makeNode('span', '', `${a.status || ''} · ${a.type || ''}`));
      card.append(makeNode('code', '', a.path || a.open_command || ''));
      const actions = makeNode('div', 'artifact-actions');
      const open = makeNode('button', 'ghost small', t('artifact.open','Open'));
      open.dataset.artifactOpen = String(index);
      open.addEventListener('click', () => openArtifact(index));
      actions.append(open);
      const download = makeNode('a', 'ghost small artifact-link', t('artifact.download','Download'));
      if(downloadUrl){ download.setAttribute('href', downloadUrl); download.setAttribute('download', ''); }
      else download.setAttribute('aria-disabled', 'true');
      actions.append(download);
      const copy = makeNode('button', 'ghost small', t('artifact.copy_path','Copy path'));
      copy.dataset.artifactCopy = String(index);
      copy.addEventListener('click', () => navigator.clipboard?.writeText(artifactPath(latestArtifacts[index])));
      actions.append(copy);
      card.append(actions);
      nodes.push(card);
    });
  });
  replaceWithNodes(target, nodes);
}
function renderInternal(events){
  const arr = events || [];
  const target = el('internal-chat');
  if(!arr.length){ showMuted(target, t('internal.none','No internal handoffs yet.')); return; }
  replaceWithNodes(target, arr.slice(-8).map(e => makeNode('div', 'internal-event', e)));
}
function _artifactChatCard(a){
  const div = document.createElement('div');
  div.className = 'bubble Admin artifact-inline-card';
  const dlUrl = artifactDownloadUrl(a);
  div.innerHTML = '<small>Artifact</small><div class="artifact-card-inline"><b class="ac-label"></b><span class="muted ac-meta"></span><code class="ac-path" style="display:block;margin:4px 0;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></code><div class="artifact-actions"><button class="ghost small" data-inline-open>Open</button>' + (dlUrl ? '<a class="ghost small artifact-link" data-inline-dl download>Download</a>' : '') + '<button class="ghost small" data-inline-copy>Copy path</button></div></div>';
  div.querySelector('.ac-label').textContent = a.label || a.type || 'artifact';
  div.querySelector('.ac-meta').textContent = (a.status ? ` · ${a.status}` : '') + (a.type ? ` · ${a.type}` : '');
  div.querySelector('.ac-path').textContent = artifactPath(a) || a.open_command || '—';
  if (dlUrl) div.querySelector('[data-inline-dl]').href = dlUrl;
  div.querySelector('[data-inline-open]')?.addEventListener('click', async () => {
    const url = artifactPreviewUrl(a);
    if(!url) return;
    try{ showModal(a.label || a.type || 'Artifact', await api(url)); }
    catch(e){ showModal('Artifact unavailable', {ok:false, error:String(e), path:artifactPath(a)}); }
  });
  div.querySelector('[data-inline-copy]')?.addEventListener('click', () => { navigator.clipboard?.writeText(artifactPath(a)); });
  return div;
}
function postArtifactsToChat(artifacts){
  if(!Array.isArray(artifacts) || !artifacts.length) return;
  const chatLog = el('chat-log');
  artifacts.forEach(a => chatLog.appendChild(_artifactChatCard(a)));
  chatLog.scrollTop = chatLog.scrollHeight;
}
function _updatePipelineRunPanel(panel, status){
  const stageStates = Array.isArray(status.stage_states) ? status.stage_states : [];
  const statusLine = panel.querySelector('.pipeline-run-status');
  if(statusLine) statusLine.textContent = `Status: ${status.status || '—'}`;
  stageStates.forEach(({stage, state}) => {
    const li = Array.from(panel.querySelectorAll('.pipeline-run-stage')).find(n => n.dataset.stage === stage);
    if(!li) return;
    li.className = `pipeline-run-stage ${state}`;
    const icon = li.querySelector('.stage-icon');
    if(icon) icon.textContent = state === 'active' ? '▶' : state === 'completed' ? '✓' : '○';
  });
  const errors = (status.events || []).filter(ev => ev.type === 'stage_failed' || ev.type === 'run_failed');
  if(errors.length){
    let errDiv = panel.querySelector('.pipeline-run-errors');
    if(!errDiv){ errDiv = document.createElement('div'); errDiv.className = 'pipeline-run-errors'; panel.insertBefore(errDiv, panel.querySelector('.pipeline-run-refresh')); }
    errDiv.innerHTML = '';
    errors.forEach(ev => { const d = document.createElement('div'); d.className = 'pipeline-run-error-line'; d.textContent = `✗ ${ev.stage || '?'}: ${(ev.data && ev.data.error) || ev.type}`; errDiv.appendChild(d); });
  }
}
function renderPipelineRunPanel(result){
  const runId = result.run_id || (result.raw && result.raw.run_id) || '';
  const pipelineId = ((result.route || {}).pipeline_id) || '';
  const initialStatus = (result.raw && result.raw.status) || result.status || 'ready_for_admin_approval';
  const catalogInfo = pipelineById(pipelineId);
  const stages = Array.isArray(catalogInfo.stages) ? catalogInfo.stages : [];
  const panel = document.createElement('div');
  panel.className = 'bubble System pipeline-run-panel';
  panel.dataset.runId = runId;
  // Header
  const headerDiv = document.createElement('div');
  headerDiv.className = 'pipeline-run-header';
  const titleSpan = document.createElement('span');
  titleSpan.className = 'pipeline-run-title';
  titleSpan.textContent = `Pipeline run: ${pipelineId || 'unknown'}`;
  const runIdCode = document.createElement('code');
  runIdCode.className = 'pipeline-run-id';
  runIdCode.textContent = runId || '—';
  const copyBtn = document.createElement('button');
  copyBtn.className = 'ghost small';
  copyBtn.textContent = 'Copy ID';
  copyBtn.addEventListener('click', () => { navigator.clipboard?.writeText(runId); });
  headerDiv.appendChild(titleSpan);
  headerDiv.appendChild(runIdCode);
  headerDiv.appendChild(copyBtn);
  panel.appendChild(headerDiv);
  // Status
  const statusLine = document.createElement('div');
  statusLine.className = 'pipeline-run-status muted';
  statusLine.textContent = `Status: ${initialStatus}`;
  panel.appendChild(statusLine);
  // Stage list
  const stageList = document.createElement('ol');
  stageList.className = 'pipeline-run-stages';
  stages.forEach((s, i) => {
    const li = document.createElement('li');
    li.dataset.stage = s;
    const state = i === 0 ? 'active' : 'pending';
    li.className = `pipeline-run-stage ${state}`;
    const icon = document.createElement('span');
    icon.className = 'stage-icon';
    icon.textContent = state === 'active' ? '▶' : '○';
    const label = document.createElement('span');
    label.textContent = s;
    li.appendChild(icon);
    li.appendChild(label);
    stageList.appendChild(li);
  });
  panel.appendChild(stageList);
  // Refresh button
  const refreshBtn = document.createElement('button');
  refreshBtn.className = 'ghost small pipeline-run-refresh';
  refreshBtn.textContent = 'Refresh status';
  refreshBtn.addEventListener('click', async () => {
    if(!runId){ statusLine.textContent = 'No run ID — cannot refresh'; return; }
    refreshBtn.disabled = true;
    refreshBtn.textContent = '…';
    try{
      const status = await api(`/api/pipeline/run/${encodeURIComponent(runId)}/status`);
      _updatePipelineRunPanel(panel, status);
    } catch(e){
      statusLine.textContent = `Refresh error: ${e.message || String(e)}`;
    } finally{
      refreshBtn.disabled = false;
      refreshBtn.textContent = 'Refresh status';
    }
  });
  panel.appendChild(refreshBtn);
  const chatLog = el('chat-log');
  chatLog.appendChild(panel);
  chatLog.scrollTop = chatLog.scrollHeight;
}
function absorbResult(result){
  latestRaw = result || {};
  el('raw-json').textContent = JSON.stringify(result, null, 2);
  const route = result.route || {};
  const personaSwitch = result.persona_switch;
  if(personaSwitch && personaSwitch.switch_line){ addSystemLine(personaSwitch.switch_line); setPersona(personaSwitch.to); }
  if(result.reply) addMessage(personaSwitch?.to || route.label || result.persona || 'Admin', result.reply, result.ok === false ? 'error' : '');
  else if(result.ok === false) addMessage('Admin', `Error: ${htmlEscape(result.error || 'unknown error')}`, 'error');
  if(result.clarification_required && Array.isArray(result.questions)) addMessage('Admin', result.questions.join('\n'));
  if(Array.isArray(result.artifacts)){ renderArtifacts(result.artifacts); postArtifactsToChat(result.artifacts); }
  if(Array.isArray(result.internal_events)) renderInternal(result.internal_events);
  if(result.mode === 'pipeline_run' || route.intent === 'pipeline_run') renderPipelineRunPanel(result);
  if(result.type === 'model_selection' || route.intent === 'model_selection') pendingAction = null;
  if(route.intent === 'model_selection' || result.mode === 'model_selection_prompt') pendingAction = {type:'model_selection', scope:'dev team'};
  refreshEpoch(false); refreshJobs(); refreshTasks();
}
function parseModeText(text){
  const lower = String(text || '').trim().toLowerCase();
  let m = lower.match(/^full[_ -]?composite\s*(\d+)?$/);
  if(m) return {mode:'full_composite', composite_top_n:Number(m[1] || 0)};
  if(['fast','normal','full'].includes(lower)) return {mode:lower, composite_top_n:0};
  return null;
}
function selectionModePayload(){
  const uiValue = el('selection-mode')?.value || '';
  const parsed = uiValue ? parseModeText(uiValue) : null;
  const mode = parsed?.mode || restoredSelectionMode.mode || 'full_composite';
  let composite_top_n = Number(parsed?.composite_top_n ?? restoredSelectionMode.composite_top_n ?? 0);
  if(mode === 'full_composite' && composite_top_n <= 0) composite_top_n = 4;
  return {mode, composite_top_n};
}
function budgetPayload(){ return { max_steps:Number(el('depth-steps').value || 0), time_budget_minutes:Number(el('depth-minutes').value || 0), until_stop:Boolean(el('depth-until-stop').checked) }; }
function renderRuntimeObserverCards(cards){
  const list = Array.isArray(cards) ? cards : [];
  const target = el('runtime-observer-cards');
  if(!target) return;
  if(!list.length){ showMuted(target, 'Runtime observers unavailable.'); return; }
  replaceWithNodes(target, list.map(card => {
    const status = ['ok', 'warn', 'error'].includes(card.status) ? card.status : 'warn';
    const node = makeNode('div', `observer-card ${status}`);
    node.append(makeNode('b', '', card.title || card.id));
    node.append(makeNode('span', '', card.state || 'unknown'));
    node.append(makeNode('small', '', card.smoke_affirmation || 'not_affirmed'));
    return node;
  }));
}

async function sendAdmin(){
  const input = el('admin-message');
  const text = input.value.trim();
  if(!text) return;
  input.value = '';
  addMessage('User', text);
  el('admin-send').disabled = true; el('chat-status').textContent = t('status.running','running');
  try{
    const modePick = pendingAction?.type === 'model_selection' ? parseModeText(text) : null;
    let result;
    if(modePick){
      result = await api('/api/model-selection/plan', {request:`GUI pending model selection: ${text}`, mode:modePick.mode, composite_top_n:modePick.composite_top_n, scope:pendingAction.scope || 'dev team'});
      result.type = 'model_selection';
      // Persist the selected mode to session so it survives page refresh.
      api('/api/session/mode', {mode:modePick.mode, composite_top_n:modePick.composite_top_n}).catch(()=>{});
      // Explicit confirmation so the user can see which mode was accepted.
      const _modeLabel = modePick.mode === 'full_composite'
        ? `full_composite${modePick.composite_top_n > 0 ? ` (top ${modePick.composite_top_n})` : ''}`
        : modePick.mode;
      addMessage('Admin', `Mode selected: ${_modeLabel}`);
    }else{
      result = await api('/api/admin/message', {message:text, execute:el('admin-execute').checked, prepare_media:el('admin-prepare-media').checked, allow_degraded:true, locale:el('locale-select').value, ...budgetPayload()});
    }
    absorbResult(result);
  }catch(e){ addMessage('Admin', `Error: ${String(e)}`, 'error'); }
  finally{ el('admin-send').disabled = false; el('chat-status').textContent = t('status.ready','ready'); }
}
function shortenPath(path){ if(!path) return '—'; const parts = String(path).split('/'); return parts.slice(-2).join('/'); }
const _STAFFING_LABELS = {
  selected: 'Model selected',
  degraded_selected: 'Model selected (degraded)',
  no_further_improvement_found: 'Selection complete',
  selecting: 'Selection in progress',
  initialized: 'Initialised',
  not_started: 'Not started yet',
};
function _humanStaffingState(s){ if(!s) return 'unknown'; return _STAFFING_LABELS[s] || String(s).replaceAll('_',' '); }
async function refreshEpoch(showMessage=false){
  try{
    const st = await api('/api/epoch/status');
    const current = st.current_epoch || {}, progress = st.progress || {}, staffing = st.firstboot?.staffing || {}, latest = st.latest_model_selection || {};
    const fullModel = current.model_realpath || current.manifest?.model_id || '—';
    const staffState = staffing.staffing_state || 'unknown';
    const staffSelected = staffing.selected_model_count ?? '—';
    const tested = progress.tested_models ?? 0, total = progress.total_models ?? '—', failed = progress.failed_models ?? 0, left = progress.remaining_models ?? '—';
    const planMode = latest.decision?.mode || latest.plan?.mode || '—';
    const planTs = latest.created_at ? new Date(latest.created_at).toLocaleDateString() : '';
    el('epoch-current-model').textContent = shortenPath(fullModel);
    el('epoch-current-model').title = `Full path: ${fullModel}`;
    el('epoch-staffing').textContent = `${_humanStaffingState(staffState)} · ${staffSelected} selected`;
    el('epoch-staffing').title = `staffing_state: ${staffState}\nModels chosen for this epoch: ${staffSelected}`;
    el('epoch-progress').textContent = `${tested}/${total} tested`;
    el('epoch-progress').title = `Tested: ${tested} of ${total}\nFailed: ${failed}\nRemaining: ${left}`;
    el('epoch-latest-plan').textContent = planMode + (planTs ? ` (${planTs})` : '');
    el('epoch-latest-plan').title = planMode === '—' ? 'No selection plan yet' : `Mode: ${planMode}\nCreated: ${latest.created_at || 'unknown'}\nApply available: ${st.apply_available ? 'yes — click Switch to activate' : 'no'}`;
    el('epoch-status-pill').textContent = st.apply_available ? 'ready' : 'no plan';
    el('epoch-status-pill').className = st.apply_available ? 'pill ok' : 'pill warn';
    el('epoch-status-pill').title = st.apply_available ? 'A new model selection is ready to apply.' : 'No pending model selection plan.';
    if(showMessage) addMessage('Admin', `Epoch: ${_humanStaffingState(staffState)} · tested ${tested}/${total}${failed ? ` (${failed} failed)` : ''}`);
  }catch(e){ if(showMessage) addMessage('Admin', `Epoch status error: ${String(e)}`, 'error'); }
}
function _gib(bytes){ return bytes != null ? (bytes / 1073741824).toFixed(1) + ' GiB' : '—'; }
function _pct(v){ return v != null ? String(Math.round(v)) + '%' : '—'; }
function _fmtHardware(hw){
  if (!hw) return '—';
  const m = hw.memory || {};
  const lines = [
    `RAM:   ${_gib(m.used)} / ${_gib(m.total)} (${_pct(m.percent)} used)`,
    `Swap:  ${_gib(m.swap_used)} / ${_gib(m.swap_total)} (${_pct(m.swap_percent)} used)`,
  ];
  const gpu = String(hw.nvidia_smi?.stdout || hw.nvidia_smi?.stderr || '').trim().split('\n')[0];
  if (gpu) lines.push(`GPU:   ${gpu.slice(0, 140)}`);
  return lines.join('\n');
}
function _metricRow(label, value){ return `${label.padEnd(22)} ${value != null && value !== '' ? String(value) : '—'}`; }
function _fmtProductMetrics(prod){
  if (!prod) return '—';
  const ms = prod.model_selection || {};
  const cm = prod.creative_media || {};
  const rows = [
    _metricRow('Selected model:', ms.current_main_model || ms.main_model || '—'),
    _metricRow('Selection status:', ms.staffing_state || '—'),
    _metricRow('Score:', ms.selection_score != null ? ms.selection_score : '—'),
    _metricRow('Pass rate:', ms.pass_rate != null ? _pct(ms.pass_rate * 100) : '—'),
    _metricRow('JSON parse rate:', ms.json_parse_rate != null ? _pct(ms.json_parse_rate * 100) : '—'),
    _metricRow('Quality score:', ms.quality_score != null ? ms.quality_score : '—'),
    _metricRow('Avg latency (s):', ms.avg_latency_s != null ? ms.avg_latency_s : '—'),
    _metricRow('Failed tasks:', ms.failed_tasks != null ? ms.failed_tasks : '—'),
    _metricRow('Top-N composite:', ms.selected_composite_top_n != null ? ms.selected_composite_top_n : '—'),
    cm.status ? _metricRow('Creative media:', cm.status) : null,
  ].filter(Boolean);
  return rows.join('\n');
}
async function refreshTelemetry(){
  try{
    const st = await api('/api/telemetry/status');
    el('hardware-status').textContent = 'ok';
    el('runtime-status').textContent = st.runtime?.main_backend?.stdout || st.runtime?.main_backend?.returncode || 'runtime';
    el('product-status').textContent = st.product?.model_selection?.staffing_state || '—';
    el('hardware-metrics').textContent = _fmtHardware(st.hardware);
    renderRuntimeObserverCards(st.runtime?.observer_cards || []);
    el('runtime-metrics').textContent = JSON.stringify({device_policy:st.runtime?.device_policy, sockets:st.runtime?.sockets, model:st.runtime?.main_manifest?.model_id || st.runtime?.main_manifest?.name || 'main'}, null, 2);
    el('product-metrics').textContent = _fmtProductMetrics(st.product);
  }catch(e){ el('hardware-status').textContent = 'error'; }
}
async function refreshTasks(){
  try{
    const st = await api('/api/tasks');
    const tasks = st.tasks || [];
    el('task-summary').textContent = `${st.summary?.pending || 0} pending · ${st.summary?.blocked || 0} blocked`;
    const target = el('tasks');
    if(!tasks.length){ showMuted(target, 'No tasks yet.'); return; }
    replaceWithNodes(target, tasks.slice(-8).reverse().map(x => {
      const task = makeNode('div', 'task');
      task.append(makeNode('b', '', x.title));
      task.append(makeNode('span', '', `${x.category} · p=${x.priority} · ${x.status}`));
      return task;
    }));
  }catch(e){ showMuted(el('tasks'), 'tasks unavailable'); }
}
const CANCELLABLE_JOB_STATES = new Set(['queued','starting','running','needs_privilege']);
async function cancelJob(jobId){
  try{
    await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {});
    await refreshJobs();
  }catch(e){ addMessage('Admin', `Cancel error: ${String(e)}`, 'error'); }
}
function renderJobs(jobs){
  const list = jobs || [];
  el('job-summary').textContent = `${list.filter(j=>CANCELLABLE_JOB_STATES.has(j.status)).length} active`;
  const container = el('jobs');
  if(!list.length){ showMuted(container, 'No jobs.'); return; }
  replaceWithNodes(container, list.slice(-6).reverse().map(j => {
    const canCancel = CANCELLABLE_JOB_STATES.has(j.status);
    const job = makeNode('div', 'job');
    if(canCancel){
      const btn = makeNode('button', 'job-cancel-btn', '✕');
      btn.dataset.jobId = String(j.job_id || '');
      btn.title = 'Cancel job';
      btn.addEventListener('click', () => cancelJob(j.job_id));
      job.append(btn);
    }
    job.append(makeNode('b', '', j.kind));
    job.append(makeNode('span', '', `${j.status} · ${j.job_id}`));
    job.append(makeNode('code', '', j.command || ''));
    return job;
  }));
}
async function refreshJobs(){
  try{
    const st = await api('/api/jobs');
    renderJobs(st.jobs || []);
  }catch(e){ showMuted(el('jobs'), 'jobs unavailable'); }
}
function connectJobProgressStream(){
  if(jobStream || typeof EventSource === 'undefined') return;
  try{
    jobStream = new EventSource('/api/jobs/stream');
    jobStream.addEventListener('jobs_snapshot', ev => {
      try{ const data = JSON.parse(ev.data || '{}'); renderJobs(data.jobs || []); }
      catch(_){}
    });
    jobStream.addEventListener('job_progress', ev => {
      try{
        const data = JSON.parse(ev.data || '{}');
        if(data.job) refreshJobs();
      }catch(_){}
    });
    jobStream.onerror = () => { try{ jobStream.close(); }catch(_){} jobStream = null; };
  }catch(_){ jobStream = null; }
}
async function refreshInactivity(){ try{ const st = await api('/api/inactivity/status'); el('inactivity-status').textContent = st.idle_human || '—'; el('inactivity').textContent = `policy=${st.policy?.mode || 'manual'} · next=${st.policy?.next_idle_action || 'none'} · status=${st.status}`; }catch(e){} }
async function refreshPersona(){ try{ const st = await api('/api/persona/current'); setPersona(st.active_persona || 'Admin', st.portrait_url); }catch(e){} }
async function pollEvents(){
  // Poll /api/events with deduplication by index — only fetch rows after lastEventIndex.
  // Reset lastEventIndex=0 when server restarts (server_epoch changes) or when the
  // log file is rotated in-process (rotation_count changes).
  try{
    const r = await api(`/api/events?after_index=${lastEventIndex}`);
    // Only adopt a non-empty server_epoch; empty string ("") from error paths is ignored.
    if(lastServerEpoch === null && r.server_epoch) lastServerEpoch = r.server_epoch;
    if(r.server_epoch && r.server_epoch !== lastServerEpoch){
      // Server restarted — reset cursor and adopt new epoch.
      // Return immediately: current r.events was fetched with a stale after_index;
      // processing it would advance lastEventIndex past events 0..N that we must
      // still fetch. The next poll will start clean from after_index=0.
      lastEventIndex = 0;
      lastServerEpoch = r.server_epoch;
      lastRotationCount = r.rotation_count || 0;
      return;
    } else if(typeof r.rotation_count === 'number' && r.rotation_count !== lastRotationCount){
      // In-process rotation — log was truncated. Same reasoning: return early.
      lastEventIndex = 0;
      lastRotationCount = r.rotation_count;
      return;
    }
    const events = r.events || [];
    if(!events.length) return;
    const target = el('internal-chat');
    for(const ev of events){
      // Advance cursor so next poll skips already-seen rows.
      if(typeof ev.index === 'number' && ev.index >= lastEventIndex) lastEventIndex = ev.index + 1;
      if(!target) continue;
      const div = document.createElement('div');
      div.className = 'internal-event';
      const dataStr = ev.data && Object.keys(ev.data).length ? ' ' + JSON.stringify(ev.data) : '';
      div.textContent = `[${ev.type}] ${ev.actor || 'system'}${dataStr}`;
      target.appendChild(div);
    }
    if(target) target.scrollTop = target.scrollHeight;
  }catch(_){}
}
async function applyEpoch(){ try{ absorbResult(await api('/api/epoch/apply', {locale: el('locale-select').value})); }catch(e){ addMessage('Admin', `Epoch apply error: ${String(e)}`, 'error'); } }
async function continueSelection(){
  try{
    const {mode, composite_top_n} = selectionModePayload();
    const r = await api('/api/model-selection/continue', {mode, composite_top_n});
    absorbResult(r); refreshJobs();
    api('/api/session/mode', {mode: r.mode || mode, composite_top_n: Number(r.composite_top_n ?? composite_top_n)}).catch(()=>{});
  }catch(e){ addMessage('Admin', `Continue selection error: ${String(e)}`, 'error'); }
}
async function reinventoryVault(){ try{ const r = await api('/api/vault/reinventory', {}); absorbResult(r); refreshJobs(); }catch(e){ addMessage('Admin', `Vault inventory error: ${String(e)}`, 'error'); } }
async function stopWorkflow(){ try{ absorbResult(await api('/api/workflow/stop', {reason:'operator_clicked_stop'})); }catch(e){ addMessage('Admin', `Stop error: ${String(e)}`, 'error'); } }
async function setDevicePolicy(){ try{ const r = await api('/api/runtime/device-policy', {policy:el('device-policy').value}); absorbResult(r); }catch(e){ addMessage('Admin', `Device policy error: ${String(e)}`, 'error'); } }
async function loadUsecases(){
  try{
    const data = await api('/api/usecases');
    const cases = data.usecases || [];
    replaceWithNodes(el('usecases'), cases.map(c => {
      const btn = makeNode('button', 'usecase');
      btn.append(makeNode('b', '', c.title));
      btn.append(makeNode('span', '', c.summary));
      btn.addEventListener('click', ()=>{ el('admin-message').value = `что значит ${c.example || ''}`; sendAdmin(); });
      return btn;
    }));
  }catch(_){ showMuted(el('usecases'), 'Usecase help unavailable.'); }
}
function renderPublicShowcase(){
  const box = el('public-showcase');
  if(!box) return;
  const steps = Array.isArray(publicShowcaseScenario?.steps) ? publicShowcaseScenario.steps : [];
  el('public-showcase-status').textContent = publicShowcaseScenario?.status || '—';
  if(!steps.length){ showMuted(box, 'No scenario loaded.'); return; }
  replaceWithNodes(box, steps.map((step, index) => {
    const row = makeNode('div', 'showcase-step');
    row.append(makeNode('b', '', step.title || step.id));
    row.append(makeNode('span', '', `${step.surface || ''} · ${step.endpoint || ''}`));
    const actions = makeNode('div', 'showcase-step-actions');
    const fill = makeNode('button', 'ghost small', 'Fill');
    fill.addEventListener('click', () => fillShowcaseStep(index));
    const preview = makeNode('button', 'ghost small', 'Preview');
    preview.addEventListener('click', () => previewShowcaseStep(index));
    actions.append(fill, preview);
    row.append(actions);
    return row;
  }));
}
async function loadPublicShowcase(){
  try{
    publicShowcaseScenario = await api('/api/public-showcase/scenario');
    renderPublicShowcase();
  }catch(_){
    showMuted(el('public-showcase'), 'Scenario unavailable.');
  }
}
function fillShowcaseStep(index){
  const step = publicShowcaseScenario?.steps?.[index];
  if(!step) return;
  el('admin-message').value = step.request || '';
  addSystemLine(`Public scenario step staged: ${step.id || index}`);
}
function previewShowcaseStep(index){
  const step = publicShowcaseScenario?.steps?.[index];
  if(step) showModal(step.title || 'Public scenario step', step);
}
function renderPipelines(){
  const q = (el('pipeline-search').value || '').toLowerCase();
  const filtered = pipelineCatalog.filter(p => (pipelineFilter === 'All' || p.group === pipelineFilter) && (p.id.toLowerCase().includes(q) || String(p.description||'').toLowerCase().includes(q)));
  replaceWithNodes(el('pipeline-list'), filtered.slice(0,90).map(p => {
    const btn = makeNode('button', 'pipeline-card');
    btn.append(makeNode('b', '', p.id));
    btn.append(makeNode('span', '', `${p.group} · ${String(p.description||'').slice(0,110)}`));
    btn.addEventListener('click', ()=>startPipeline(p.id));
    btn.addEventListener('contextmenu', e=>{ e.preventDefault(); showPipelineMenu(e, p.id); });
    return btn;
  }));
}
async function loadPipelines(){
  try{
    const data = await api('/api/pipelines/catalog');
    pipelineCatalog = data.pipelines || [];
    const groups = ['All', ...(data.groups || [])];
    replaceWithNodes(el('pipeline-groups'), groups.map(g => {
      const btn = makeNode('button', 'ghost small', g);
      btn.addEventListener('click',()=>{ pipelineFilter=g; renderPipelines(); });
      return btn;
    }));
    renderPipelines();
  }catch(e){ showMuted(el('pipeline-list'), 'Pipeline catalog unavailable.'); }
}
async function startPipeline(id){ const req = prompt(`Request for pipeline ${id}:`, `Запусти ${id} по стандартному сценарию`); if(req===null) return; absorbResult(await api('/api/pipeline/run', {pipeline:id, request:req, allow_degraded:true})); }
function pipelineById(id){ return pipelineCatalog.find(p => p.id === id) || {id:id || 'new_pipeline', description:'', stages:['intake','plan','review']}; }
function movePipelineStage(from, to){
  const stages = pipelineEditorState.stages;
  if(from < 0 || to < 0 || from >= stages.length || to >= stages.length || from === to) return;
  const [item] = stages.splice(from, 1);
  stages.splice(to, 0, item);
  renderPipelineEditor();
}
function removePipelineStage(index){
  if(pipelineEditorState.stages.length <= 1) return;
  pipelineEditorState.stages.splice(index, 1);
  renderPipelineEditor();
}
function addPipelineStage(){
  const stage = prompt('Stage id:', 'review');
  if(!stage) return;
  const clean = stage.trim().replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '').slice(0,80);
  if(clean && !pipelineEditorState.stages.includes(clean)) pipelineEditorState.stages.push(clean);
  renderPipelineEditor();
}
function openPipelineEditor(id=''){
  const p = pipelineById(id);
  pipelineEditorState = {pipeline_id:p.id || 'new_pipeline', title:p.id || 'New pipeline', description:p.description || '', stages:Array.isArray(p.stages) && p.stages.length ? [...p.stages] : ['intake','plan','review']};
  renderPipelineEditor();
}
function renderPipelineEditor(){
  const editor = el('pipeline-editor');
  editor.classList.remove('hidden');
  const head = makeNode('div', 'pipeline-editor-head');
  const title = makeNode('div', 'pipeline-editor-title');
  title.append(makeNode('b', '', pipelineEditorState.title));
  title.append(makeNode('span', '', 'draft only · review required before activation'));
  const close = makeNode('button', 'ghost small', 'Close');
  close.id = 'pipeline-editor-close';
  close.onclick = () => editor.classList.add('hidden');
  head.append(title, close);
  const stageList = makeNode('div', 'pipeline-stage-list');
  pipelineEditorState.stages.forEach((stage, index) => {
    const row = makeNode('div', 'editor-stage');
    row.draggable = true;
    row.dataset.stageIndex = String(index);
    row.append(makeNode('span', 'stage-grip', 'drag'));
    row.append(makeNode('span', '', stage));
    const actions = makeNode('div', 'stage-actions');
    const up = makeNode('button', 'ghost small', 'Up');
    up.onclick = () => movePipelineStage(index, index-1);
    const down = makeNode('button', 'ghost small', 'Down');
    down.onclick = () => movePipelineStage(index, index+1);
    const remove = makeNode('button', 'ghost small', 'Remove');
    remove.onclick = () => removePipelineStage(index);
    actions.append(up, down, remove);
    row.append(actions);
    row.addEventListener('dragstart', ev => { row.classList.add('dragging'); ev.dataTransfer?.setData('text/plain', row.dataset.stageIndex || '0'); });
    row.addEventListener('dragend', () => row.classList.remove('dragging'));
    row.addEventListener('dragover', ev => ev.preventDefault());
    row.addEventListener('drop', ev => { ev.preventDefault(); movePipelineStage(Number(ev.dataTransfer?.getData('text/plain') || 0), Number(row.dataset.stageIndex || 0)); });
    stageList.append(row);
  });
  const editorActions = makeNode('div', 'pipeline-editor-actions');
  const add = makeNode('button', 'ghost small', 'Add stage');
  add.id = 'pipeline-stage-add';
  add.onclick = addPipelineStage;
  const save = makeNode('button', 'small', 'Save draft');
  save.id = 'pipeline-draft-save';
  save.onclick = savePipelineEditorDraft;
  editorActions.append(add, save);
  replaceWithNodes(editor, [head, stageList, editorActions]);
}
async function savePipelineEditorDraft(){
  const result = await api('/api/pipelines/draft', {id:pipelineEditorState.pipeline_id, title:pipelineEditorState.title, description:pipelineEditorState.description, stages:pipelineEditorState.stages, editor_mode:'drag_drop_pipeline_editor', review_required:true});
  absorbResult(result);
}
function showPipelineMenu(e, id){
  const m = el('context-menu');
  const actions = [['diagram','Open visual diagram'],['stats','Show stats'],['explain','Explain pipeline'],['draft','Clone/edit draft']];
  replaceWithNodes(m, actions.map(([act, label]) => {
    const button = makeNode('button', '', label);
    button.dataset.act = act;
    return button;
  }));
  m.style.left = `${e.clientX}px`; m.style.top = `${e.clientY}px`; m.classList.remove('hidden');
  m.querySelectorAll('button').forEach(b => b.onclick = async () => { m.classList.add('hidden'); const act=b.dataset.act; if(act==='diagram') showModal('Pipeline diagram', await api(`/api/pipelines/${encodeURIComponent(id)}/diagram`)); else if(act==='stats') showModal('Pipeline stats', await api(`/api/pipelines/${encodeURIComponent(id)}/stats`)); else if(act==='explain'){ el('admin-message').value = `что значит пайплайн ${id}`; sendAdmin(); } else openPipelineEditor(id); });
}
function showModal(title, obj){ el('modal-title').textContent = title; el('modal-body').textContent = typeof obj === 'string' ? obj : JSON.stringify(obj,null,2); el('modal').classList.remove('hidden'); }
async function addTaskDialog(){ const title = prompt('Task title:'); if(!title) return; const cat = prompt('Category:', 'gui') || 'general'; const priority = Number(prompt('Priority 1-100:', '50') || 50); const r = await api('/api/tasks/create', {title, category:cat, priority}); absorbResult(r); refreshTasks(); }
async function loadDashboardBackendState(){
  try{ return await api(DASHBOARD_API_ENDPOINT); }
  catch(_){ return await api(GUI_STATE_FALLBACK_ENDPOINT); }
}
async function startup(){
  try{ const loc = await api('/api/locales'); allMessages = loc.messages || {}; if(Array.isArray(loc.locales)){ replaceWithNodes(el('locale-select'), loc.locales.map(x => { const option=makeNode('option','',x); option.value=String(x); return option; })); activeLocale = loc.locales.includes('ru') ? 'ru' : (loc.locales[0] || 'en'); el('locale-select').value = activeLocale; } applyLocaleMessages(); }catch(e){}
  // Try session-based restore first (persists across page refresh); fall back to dashboard state.
  let restoredFromSession = false;
  try{
    const sess = await api('/api/session/current');
    const msgs = (sess.session || {}).messages || [];
    if(msgs.length > 0){ renderConversation(sess.session); restoredFromSession = true; }
  }catch(_){}
  if(!restoredFromSession){
    try{ const st = await loadDashboardBackendState(); renderConversation(st.conversation || {}); renderArtifacts(st.conversation?.artifacts || []); if(st.persona?.portrait_url) setPersona(st.persona.active_persona || st.persona.persona?.role_key || 'Admin', st.persona.portrait_url); }catch(e){ addMessage('Admin', t('startup.ready','Ready. Say “Hello”, ask Dev Team, model optimization, or media plan.')); }
  }
  try{ const loc = await api('/api/locales'); allMessages = loc.messages || {}; if(Array.isArray(loc.locales)){ replaceWithNodes(el('locale-select'), loc.locales.map(x => { const option=makeNode('option','',x); option.value=String(x); return option; })); activeLocale = loc.locales.includes('ru') ? 'ru' : (loc.locales[0] || 'en'); el('locale-select').value = activeLocale; } applyLocaleMessages(); }catch(e){}
  // Restore selected mode from the session store; conversation state is rendered below.
  try{
    const sess = await api('/api/session/current');
    const selected_mode = sess?.session?.selected_mode;
    const selected_composite_top_n = Number(sess?.session?.selected_composite_top_n || 0);
    if(selected_mode){
      restoredSelectionMode = {mode:selected_mode, composite_top_n:selected_composite_top_n};
      if(el('selection-mode')){ el('selection-mode').value = selected_composite_top_n ? `${selected_mode} ${selected_composite_top_n}` : selected_mode; }
    }
  }catch(_){}
  try{ const st = await loadDashboardBackendState(); renderConversation(st.conversation || {}); renderArtifacts(st.conversation?.artifacts || []); if(st.persona?.portrait_url) setPersona(st.persona.active_persona || st.persona.persona?.role_key || 'Admin', st.persona.portrait_url); }catch(e){ addMessage('Admin', t('startup.ready','Ready. Say “Hello”, ask Dev Team, model optimization, or media plan.')); }
  await Promise.allSettled([refreshEpoch(false), refreshTelemetry(), refreshTasks(), refreshJobs(), refreshInactivity(), refreshPersona(), loadUsecases(), loadPublicShowcase(), loadPipelines()]);
  connectJobProgressStream();
  // Poll events every 10 s alongside other refresh tasks; deduplication by lastEventIndex.
  setInterval(()=>{ refreshTelemetry(); refreshJobs(); refreshInactivity(); refreshEpoch(false); pollEvents(); }, 10000);
}
if(typeof window !== 'undefined' && window.document === document){
  el('admin-send').addEventListener('click', sendAdmin);
  el('admin-message').addEventListener('keydown', e => { if(e.key === 'Enter' && (e.ctrlKey || e.metaKey)){ e.preventDefault(); sendAdmin(); } });
  el('locale-select').addEventListener('change', e => { activeLocale = e.target.value; applyLocaleMessages(); renderArtifacts(latestArtifacts); });
  el('gui-shutdown').addEventListener('click', async()=>{ try{ await api('/api/shutdown', {reason:'operator'}); addMessage('Admin','GUI shutdown requested.'); }catch(e){} });
  el('epoch-refresh').addEventListener('click', ()=>refreshEpoch(true));
  el('epoch-apply').addEventListener('click', applyEpoch);
  el('selection-continue').addEventListener('click', continueSelection);
  el('vault-reinventory').addEventListener('click', reinventoryVault);
  el('workflow-stop').addEventListener('click', stopWorkflow);
  el('device-policy').addEventListener('change', setDevicePolicy);
  el('tasks-refresh').addEventListener('click', refreshTasks);
  el('task-add').addEventListener('click', addTaskDialog);
  el('public-showcase-load').addEventListener('click', loadPublicShowcase);
  el('pipeline-search').addEventListener('input', renderPipelines);
  el('pipeline-new').addEventListener('click', ()=>{ const title = prompt('New pipeline draft title:', 'new_pipeline'); if(!title) return; pipelineEditorState = {pipeline_id:title, title, description:'', stages:['intake','plan','review']}; renderPipelineEditor(); });
  el('modal-close').addEventListener('click', ()=>el('modal').classList.add('hidden'));
  document.addEventListener('click', e=>{ if(!el('context-menu').contains(e.target)) el('context-menu').classList.add('hidden'); });
  startup();
}
