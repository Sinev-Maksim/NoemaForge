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
let activeStageHandoff = null;
let pipelineCatalog = [];
let pipelineFilter = 'All';
let jobStream = null;
let activeWorkPollTimer = null;
let activeRunIds = new Set();
let pipelineEditorState = {pipeline_id:'', title:'', description:'', stages:[]};
let publicShowcaseScenario = null;
let latestArtifacts = [];
let postedArtifactKeys = new Set();
let postedStageHandoffKeys = new Set();
let lastEventIndex = 0;
// server_epoch detects server restarts even when rotation_count stays 0.
// rotation_count detects in-process log rotations.
// Both trigger a lastEventIndex reset to avoid missing or duplicating events.
let lastServerEpoch = null;
let lastRotationCount = 0;
let restoredSelectionMode = {mode:'full_composite', composite_top_n:4};

const _REPEAT_WINDOW_MS = 60_000;
const _launchHistory = new Map();
let _confirmPipelineId = '';

const DASHBOARD_API_ENDPOINT = '/api/dashboard';
const GUI_STATE_FALLBACK_ENDPOINT = '/api/gui/state';
const CANONICAL_MAIN_BACKEND_SOCKET = '/run/noemaforge/llm/backends/main.sock';

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
function _addPendingBubble(){
  const div = document.createElement('div');
  div.className = 'bubble Admin pending-indicator';
  div.innerHTML = '<small>Admin</small><span class="pending-dots">…</span>';
  const chatLog = el('chat-log');
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  return div;
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
const _PERSONA_ROLE_TO_NAME = {
  'operator.admin/administrator':'Admin',
  'system.guard/sr':'Optimizer',
  'system.guard/ssr':'Model Evolution',
  'dev.work/dev':'Dev Team',
  'writing.story/writer':'Music Team',
  'video.generator':'Video Team',
  'vision.segmenter':'Vision Team',
};
async function _loadPersonaSelect(){
  try{
    const cat = await api('/api/persona/catalog');
    const sel = el('persona-select');
    if(!sel) return;
    const items = (cat.personas || []).filter(p => _PERSONA_ROLE_TO_NAME[p.role_key]);
    sel.innerHTML = '';
    items.forEach(p => {
      const name = _PERSONA_ROLE_TO_NAME[p.role_key];
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = p.codename ? `${p.codename} (${name})` : name;
      sel.appendChild(opt);
    });
    _updatePersonaSelect(el('active-persona')?.textContent || 'Admin');
    sel.onchange = () => switchPersona(sel.value);
  }catch(e){}
}
function _updatePersonaSelect(name){
  const sel = el('persona-select');
  if(!sel) return;
  for(const opt of sel.options){ opt.selected = opt.value === name; }
}
async function switchPersona(name){
  try{
    const r = await api('/api/persona/switch', {name});
    if(r.ok){
      setPersona(r.active_persona, r.portrait_url);
      _updatePersonaSelect(r.active_persona);
      if(r.switch_line) addSystemLine(r.switch_line);
      if(r.active_persona && r.active_persona !== 'Admin') _addReturnToAdminLine();
    }
  }catch(e){}
}
function _addReturnToAdminLine(){
  const div = document.createElement('div');
  div.className = 'system-line';
  const btn = document.createElement('button');
  btn.className = 'ghost small';
  btn.style.cssText = 'display:inline-block;margin-left:4px';
  btn.textContent = '← Return to Admin';
  btn.onclick = () => switchPersona('Admin');
  div.appendChild(btn);
  el('chat-log').appendChild(div);
  el('chat-log').scrollTop = el('chat-log').scrollHeight;
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
  artifacts.forEach(a => {
    const key = [artifactPath(a), a.label || '', a.type || ''].join('|');
    if(postedArtifactKeys.has(key)) return;
    postedArtifactKeys.add(key);
    chatLog.appendChild(_artifactChatCard(a));
  });
  chatLog.scrollTop = chatLog.scrollHeight;
}
function _stageHandoffKey(handoff){
  if(!handoff) return '';
  return [handoff.run_id || '', handoff.current_stage || '', handoff.handoff_version || 'stage_handoff_v2'].join('|');
}
function postStageHandoffToChat(handoff){
  const key = _stageHandoffKey(handoff);
  if(!key || postedStageHandoffKeys.has(key)) return;
  postedStageHandoffKeys.add(key);
  const persona = handoff.persona || 'Pipeline';
  const questions = Array.isArray(handoff.questions) ? handoff.questions : [];
  addMessage(persona, [handoff.message || 'Stage handoff required.', ...questions].join('\n'));
}
function _setActiveStageHandoff(handoff){
  if(!handoff || !handoff.run_id){
    activeStageHandoff = null;
    return;
  }
  const replyState = handoff.operator_reply_state || {};
  activeStageHandoff = {
    run_id: String(handoff.run_id || ''),
    pipeline_id: String(handoff.pipeline_id || ''),
    current_stage: String(handoff.current_stage || ''),
    persona: String(handoff.persona || 'Pipeline'),
    handoff_version: String(handoff.handoff_version || ''),
    state: String(replyState.state || 'waiting_for_operator_reply'),
  };
}
function _clearActiveStageHandoff(runId, stage){
  if(!activeStageHandoff) return;
  if(runId && String(activeStageHandoff.run_id) !== String(runId)) return;
  if(stage && String(activeStageHandoff.current_stage) !== String(stage)) return;
  activeStageHandoff = null;
}
function _panelForRun(runId){
  if(!runId) return null;
  return Array.from(document.querySelectorAll('.pipeline-run-panel')).find(panel => String(panel.dataset.runId || '') === String(runId)) || null;
}
async function _sendActiveStageHandoffReply(text){
  const handoff = activeStageHandoff ? {...activeStageHandoff} : null;
  if(!handoff || !handoff.run_id) return null;
  const reply = await api(`/api/pipeline/run/${encodeURIComponent(handoff.run_id)}/reply`, {
    stage: handoff.current_stage,
    message: text,
    action: 'reply',
    source: 'chat_input',
    allow_degraded: true,
  });
  const status = await api(`/api/pipeline/run/${encodeURIComponent(handoff.run_id)}/status`);
  const panel = _panelForRun(handoff.run_id);
  if(panel) _updatePipelineRunPanel(panel, status);
  _clearActiveStageHandoff(handoff.run_id, handoff.current_stage);
  return {
    ...reply,
    mode: 'pipeline_stage_handoff_response',
    reply: reply.ok === false
      ? `Pipeline handoff reply rejected: ${reply.error || 'unknown error'}`
      : `Operator reply recorded for pipeline ${handoff.pipeline_id || status.pipeline_id || handoff.run_id}, stage ${handoff.current_stage || status.current_stage || 'stage'}.`,
    route: {id:'pipeline_handoff_reply', intent:'pipeline_handoff_reply', pipeline_id:handoff.pipeline_id || status.pipeline_id, run_id:handoff.run_id},
    status_after_reply: status,
    stage_handoff: status.stage_handoff || null,
    operator_reply_state: status.operator_reply_state || reply.operator_reply_state,
    handoff_reply_mode: status.handoff_reply_mode,
    handoff_reply_limitation: status.handoff_reply_limitation,
    handoff_next_action: status.handoff_next_action,
  };
}
async function _replyStageHandoff(panel, handoff, input, messageNode){
  const runId = String(handoff?.run_id || panel.dataset.runId || '');
  const text = String(input.value || '').trim();
  if(!runId){ messageNode.textContent = 'Missing run_id; cannot reply.'; return; }
  if(!text){ messageNode.textContent = 'Reply is empty.'; return; }
  messageNode.textContent = 'Saving operator reply...';
  try{
    await api(`/api/pipeline/run/${encodeURIComponent(runId)}/reply`, {stage:handoff.current_stage, message:text, action:'reply'});
    input.value = '';
    messageNode.textContent = 'Reply saved.';
    const status = await api(`/api/pipeline/run/${encodeURIComponent(runId)}/status`);
    _updatePipelineRunPanel(panel, status);
    _clearActiveStageHandoff(runId, handoff.current_stage);
  }catch(e){
    messageNode.textContent = `Reply error: ${e.message || String(e)}`;
  }
}
async function _advanceStageHandoff(panel, handoff, mode, button, messageNode){
  const runId = String(handoff?.run_id || panel.dataset.runId || '');
  if(!runId){ messageNode.textContent = 'Missing run_id; cannot advance.'; return; }
  button.disabled = true;
  const skip = mode === 'skip';
  messageNode.textContent = skip ? 'Skipping stage after explicit operator click...' : 'Continuing stage after explicit operator click...';
  try{
    const result = await api('/api/pipeline/advance', {run_id:runId, next:false, skip:skip, allow_degraded:true, note:skip ? `operator skipped ${handoff.current_stage || 'stage'} from stage handoff` : `operator continued ${handoff.current_stage || 'stage'} from stage handoff`});
    const blocker = result.actionable_blocker || {};
    messageNode.textContent = result.ok === false ? `Advance rejected: ${blocker.message || result.error || result.reason || 'unknown error'}` : (skip ? 'Stage skipped explicitly.' : 'Stage continue recorded.');
    const status = await api(`/api/pipeline/run/${encodeURIComponent(runId)}/status`);
    _updatePipelineRunPanel(panel, status);
  }catch(e){
    messageNode.textContent = `Advance error: ${e.message || String(e)}`;
  }finally{
    button.disabled = false;
  }
}
async function _refreshStageHandoff(panel, button, messageNode){
  const runId = String(panel.dataset.runId || '');
  if(!runId){ messageNode.textContent = 'Missing run_id; cannot refresh.'; return; }
  button.disabled = true;
  try{
    const status = await api(`/api/pipeline/run/${encodeURIComponent(runId)}/status`);
    _updatePipelineRunPanel(panel, status);
    messageNode.textContent = 'Status refreshed.';
  }catch(e){
    messageNode.textContent = `Refresh error: ${e.message || String(e)}`;
  }finally{
    button.disabled = false;
  }
}
function _renderStageHandoff(panel, handoff){
  let box = panel.querySelector('.stage-handoff-panel');
  if(!handoff){
    if(box) box.remove();
    return;
  }
  postStageHandoffToChat(handoff);
  if(!box){
    box = document.createElement('div');
    box.className = 'stage-handoff-panel';
    const title = makeNode('b', 'stage-handoff-title');
    const msg = makeNode('p', 'muted stage-handoff-message');
    const qs = makeNode('ul', 'stage-handoff-questions');
    const input = document.createElement('textarea');
    input.className = 'stage-handoff-reply';
    input.rows = 3;
    input.placeholder = 'Operator reply or decision';
    const actions = makeNode('div', 'stage-handoff-actions');
    const reply = makeNode('button', 'small', 'Reply / Provide decision');
    const cont = makeNode('button', 'ghost small', 'Continue after reply');
    const skip = makeNode('button', 'ghost small', 'Skip stage explicitly');
    const refresh = makeNode('button', 'ghost small', 'Refresh status');
    const status = makeNode('div', 'stage-handoff-status muted');
    const meta = makeNode('div', 'stage-handoff-meta muted');
    reply.addEventListener('click', () => _replyStageHandoff(panel, box._handoff, input, status));
    cont.addEventListener('click', () => _advanceStageHandoff(panel, box._handoff, 'continue', cont, status));
    skip.addEventListener('click', () => _advanceStageHandoff(panel, box._handoff, 'skip', skip, status));
    refresh.addEventListener('click', () => _refreshStageHandoff(panel, refresh, status));
    actions.append(reply, cont, skip, refresh);
    box.append(title, msg, qs, meta, input, actions, status);
    const refreshBtn = panel.querySelector('.pipeline-run-refresh');
    panel.insertBefore(box, refreshBtn || null);
  }
  box._handoff = handoff;
  const replyState = handoff.operator_reply_state || {};
  if(replyState.state === 'operator_reply_recorded') _clearActiveStageHandoff(handoff.run_id, handoff.current_stage);
  else _setActiveStageHandoff(handoff);
  box.querySelector('.stage-handoff-title').textContent = `${handoff.persona || 'Pipeline'} · ${handoff.current_stage || 'stage'}`;
  box.querySelector('.stage-handoff-message').textContent = handoff.message || 'Stage handoff required.';
  const quality = handoff.output_quality || {};
  const actions = Array.isArray(handoff.next_actions || handoff.suggested_actions) ? (handoff.next_actions || handoff.suggested_actions).join(' · ') : '—';
  box.querySelector('.stage-handoff-meta').textContent = `Output: ${quality.quality || (quality.exists ? 'placeholder' : 'missing')} · Reply: ${replyState.state || 'waiting_for_operator_reply'} · Next: ${actions}`;
  const qs = box.querySelector('.stage-handoff-questions');
  qs.replaceChildren(...(Array.isArray(handoff.questions) ? handoff.questions : []).map(q => makeNode('li', '', q)));
}
const _DEGRADED_APPROVAL_STATUSES = new Set(['ready_for_admin_approval','waiting_for_admin','needs_admin_approval','approval_required']);
function _isDegradedApprovalStatus(status){ return _DEGRADED_APPROVAL_STATUSES.has(String(status || '').toLowerCase()); }
function _asList(value){
  if(Array.isArray(value)) return value.filter(v => v != null && String(v).trim() !== '').map(v => String(v));
  if(value == null || value === '') return [];
  return [String(value)];
}
function _summaryLine(label, value){
  const line = document.createElement('div');
  line.className = 'degraded-summary-line';
  const k = makeNode('span', 'degraded-summary-key', label);
  const v = makeNode('span', 'degraded-summary-value', Array.isArray(value) ? (value.length ? value.join(', ') : '—') : (value == null || value === '' ? '—' : String(value)));
  line.append(k, v);
  return line;
}
function _renderDegradedSummary(target, data){
  const degraded = data?.degraded_readonly || {};
  const staffing = data?.staffing || {};
  const warnings = _asList(staffing.warnings);
  const checks = _asList(data?.checks).slice(0, 4);
  const nextActions = _asList(data?.next_actions).slice(0, 4);
  const rows = [
    _summaryLine('degraded_readonly', `${degraded.active ? 'active' : 'inactive'} · ${degraded.state || 'unknown'} · ${degraded.mode || 'normal'}`),
    _summaryLine('summary path', degraded.path || '—'),
    _summaryLine('staffing_state', staffing.staffing_state || 'unknown'),
    _summaryLine('warnings', warnings.slice(0, 4)),
    _summaryLine('degraded_roles', _asList(staffing.degraded_roles).slice(0, 8)),
    _summaryLine('unstaffed_roles', _asList(staffing.unstaffed_roles).slice(0, 8)),
    _summaryLine('thresholds', Object.keys(staffing.thresholds || {}).length ? Object.entries(staffing.thresholds).map(([k,v]) => `${k}=${v}`).slice(0, 6) : []),
    _summaryLine('selected_model_ids', _asList(staffing.selected_model_ids).slice(0, 8)),
  ];
  if(checks.length) rows.push(_summaryLine('health checks', checks));
  if(nextActions.length) rows.push(_summaryLine('next_actions', nextActions));
  replaceWithNodes(target, rows);
}
async function _continuePipelineDegraded(panel, button, messageNode){
  const runId = String(panel.dataset.runId || '');
  if(!runId){ messageNode.textContent = 'Missing run_id; cannot continue.'; return; }
  button.disabled = true;
  messageNode.textContent = 'Submitting explicit degraded approval...';
  try{
    const result = await api('/api/pipeline/advance', {run_id:runId, next:true, allow_degraded:true, note:'explicit operator approval from dashboard degraded panel'});
    messageNode.textContent = result.ok === false ? `Advance rejected: ${result.error || result.reason || 'unknown error'}` : 'Pipeline continued in degraded mode.';
    addMessage('Admin', messageNode.textContent);
    const status = await api(`/api/pipeline/run/${encodeURIComponent(runId)}/status`);
    _updatePipelineRunPanel(panel, status);
    await refreshActiveWork();
  }catch(e){
    messageNode.textContent = `Degraded continue error: ${e.message || String(e)}`;
  }finally{
    button.disabled = false;
  }
}
async function _workTowardNormalMode(messageNode){
  messageNode.textContent = 'Creating normal-mode recovery plan...';
  try{
    const {mode, composite_top_n} = selectionModePayload();
    const result = await api('/api/model-selection/continue', {mode, composite_top_n, recovery:'normal-mode recovery'});
    absorbResult(result);
    const transition = result.transition_payload || {};
    if(result.action_state === 'plan_only' || transition.state === 'plan_only'){
      const label = transition.next_action_label || result.next_action_label || 'Run approved normal-mode selection';
      messageNode.textContent = `Normal-mode recovery is plan-only; no corrective process is running. Next action: ${label}. Use the exact operator command from the job card.`;
    }else{
      messageNode.textContent = result.reply || 'Normal-mode recovery state updated.';
    }
    addMessage('Admin', messageNode.textContent);
    await refreshJobs();
  }catch(e){
    messageNode.textContent = `Normal-mode recovery error: ${e.message || String(e)}`;
  }
}
async function _ensureDegradedApprovalPanel(panel, status){
  let approval = panel.querySelector('.degraded-approval-panel');
  if(!_isDegradedApprovalStatus(status.status)){
    if(approval) approval.remove();
    return;
  }
  if(approval) return;
  approval = document.createElement('div');
  approval.className = 'degraded-approval-panel';
  approval.dataset.loaded = 'false';
  const title = makeNode('b', '', 'Degraded/Admin approval required');
  const explain = makeNode('p', 'muted', 'This run is waiting at an admin approval boundary. The host is degraded-readonly, so continuing is a deliberate operator decision.');
  const summary = makeNode('div', 'degraded-summary');
  summary.append(makeNode('p', 'muted', 'Loading degraded details...'));
  const msg = makeNode('div', 'degraded-panel-message muted');
  const actions = makeNode('div', 'degraded-panel-actions');
  const cont = makeNode('button', 'small', 'Continue in degraded mode');
  cont.addEventListener('click', () => _continuePipelineDegraded(panel, cont, msg));
  const normal = makeNode('button', 'ghost small', 'Work toward normal mode');
  normal.title = 'normal-mode recovery action';
  normal.addEventListener('click', () => _workTowardNormalMode(msg));
  const details = makeNode('button', 'ghost small', 'Show degraded details');
  details.addEventListener('click', () => showModal('Degraded details', approval._degradedDetails || {status:'not loaded'}));
  actions.append(cont, normal, details);
  approval.append(title, explain, summary, actions, msg);
  const refresh = panel.querySelector('.pipeline-run-refresh');
  panel.insertBefore(approval, refresh || null);
  try{
    const data = await api('/api/runtime/degraded');
    approval._degradedDetails = data;
    _renderDegradedSummary(summary, data);
    approval.dataset.loaded = 'true';
  }catch(e){
    msg.textContent = `Degraded details unavailable: ${e.message || String(e)}`;
  }
}
function _updatePipelineRunPanel(panel, status){
  const stageStates = Array.isArray(status.stage_states) ? status.stage_states : [];
  const statusLine = panel.querySelector('.pipeline-run-status');
  if(statusLine) statusLine.textContent = `Status: ${status.status || '—'}`;
  const currentLine = panel.querySelector('.pipeline-run-current');
  if(currentLine) currentLine.textContent = `Current stage: ${status.current_stage || '—'}`;
  let metaLine = panel.querySelector('.pipeline-run-contract');
  if(!metaLine){
    metaLine = document.createElement('div');
    metaLine.className = 'pipeline-run-contract muted';
    const stageListAnchor = panel.querySelector('.pipeline-run-stages');
    panel.insertBefore(metaLine, stageListAnchor || panel.querySelector('.pipeline-run-refresh'));
  }
  const progress = status.stage_progress || {};
  const replyState = status.operator_reply_state || {};
  const quality = status.stage_output_quality || {};
  const blocker = status.actionable_blocker || {};
  const nextActions = Array.isArray(status.next_actions) && status.next_actions.length ? status.next_actions.join(' · ') : '—';
  const handoffMode = status.handoff_reply_mode && status.handoff_reply_mode !== 'none' ? ` · Mode: ${status.handoff_reply_mode}` : '';
  const handoffNext = status.handoff_next_action ? ` · Handoff next: ${status.handoff_next_action}` : '';
  metaLine.textContent = `Stage state: ${progress.state || status.status || '—'} · Output: ${quality.quality || 'missing'} · Reply: ${replyState.state || 'waiting_for_operator_reply'}${handoffMode}${handoffNext} · Next: ${nextActions}`;
  let blockerLine = panel.querySelector('.pipeline-run-blocker');
  if(blocker && blocker.message){
    if(!blockerLine){
      blockerLine = document.createElement('div');
      blockerLine.className = 'pipeline-run-blocker';
      panel.insertBefore(blockerLine, panel.querySelector('.pipeline-run-refresh'));
    }
    blockerLine.textContent = `Blocker: ${blocker.message}`;
  }else if(blockerLine){
    blockerLine.remove();
  }
  let limitationLine = panel.querySelector('.pipeline-run-handoff-limitation');
  if(status.handoff_reply_limitation){
    if(!limitationLine){
      limitationLine = document.createElement('div');
      limitationLine.className = 'pipeline-run-handoff-limitation muted';
      panel.insertBefore(limitationLine, panel.querySelector('.pipeline-run-refresh'));
    }
    limitationLine.textContent = status.handoff_reply_limitation;
  }else if(limitationLine){
    limitationLine.remove();
  }
  if(['completed','done','failed','cancelled'].includes(String(status.status || '').toLowerCase())){
    activeRunIds.delete(String(panel.dataset.runId || ''));
  }
  const stageList = panel.querySelector('.pipeline-run-stages');
  if(stageList && stageStates.length){
    const known = new Set(Array.from(stageList.querySelectorAll('.pipeline-run-stage')).map(n => n.dataset.stage));
    stageStates.forEach(({stage}) => {
      if(!known.has(stage)){
        const li = document.createElement('li');
        li.dataset.stage = stage;
        li.className = 'pipeline-run-stage pending';
        const icon = document.createElement('span');
        icon.className = 'stage-icon';
        icon.textContent = '○';
        const label = document.createElement('span');
        label.textContent = stage;
        li.appendChild(icon);
        li.appendChild(label);
        stageList.appendChild(li);
      }
    });
  }
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
  _renderStageHandoff(panel, status.stage_handoff || null);
  if(!status.stage_handoff && status.clarification_required && Array.isArray(status.questions) && status.questions.length){
    addMessage('Admin', status.questions.join('\n'));
  }
  if(Array.isArray(status.artifacts) && status.artifacts.length){
    renderArtifacts(status.artifacts);
    postArtifactsToChat(status.artifacts);
  }
  _ensureDegradedApprovalPanel(panel, status);
}
function renderPipelineRunPanel(result){
  const stdout = result.raw && result.raw.stdout ? result.raw.stdout : {};
  const directStdout = result.stdout && typeof result.stdout === 'object' ? result.stdout : {};
  const runId = result.run_id || (result.raw && result.raw.run_id) || stdout.run_id || directStdout.run_id || '';
  const pipelineId = ((result.route || {}).pipeline_id) || result.pipeline_id || (result.raw && result.raw.pipeline_id) || stdout.pipeline_id || directStdout.pipeline_id || '';
  const initialStatus = (result.raw && result.raw.status) || stdout.status || directStdout.status || result.status || 'ready_for_admin_approval';
  const currentStage = result.current_stage || stdout.current_stage || directStdout.current_stage || '';
  if(runId && !['completed','done','failed','cancelled'].includes(String(initialStatus).toLowerCase())) activeRunIds.add(String(runId));
  const catalogInfo = pipelineById(pipelineId);
  const stages = Array.isArray(result.stages) && result.stages.length ? result.stages : (Array.isArray(catalogInfo.stages) ? catalogInfo.stages : []);
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
  const currentLine = document.createElement('div');
  currentLine.className = 'pipeline-run-current muted';
  currentLine.textContent = `Current stage: ${currentStage || (stages[0] || '—')}`;
  panel.appendChild(currentLine);
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
  _renderStageHandoff(panel, result.stage_handoff || stdout.stage_handoff || directStdout.stage_handoff || null);
  _ensureDegradedApprovalPanel(panel, {status:initialStatus});
  if(runId) refreshActivePipelineRuns();
}
function absorbResult(result){
  latestRaw = result || {};
  el('raw-json').textContent = JSON.stringify(result, null, 2);
  const route = result.route || {};
  const personaSwitch = result.persona_switch;
  if(personaSwitch && personaSwitch.switch_line){ addSystemLine(personaSwitch.switch_line); setPersona(personaSwitch.to); _updatePersonaSelect(personaSwitch.to); if(personaSwitch.to && personaSwitch.to !== 'Admin') _addReturnToAdminLine(); }
  if(result.reply) addMessage(personaSwitch?.to || route.label || result.persona || 'Admin', result.reply, result.ok === false ? 'error' : '');
  else if(result.ok === false) addMessage('Admin', `Error: ${htmlEscape(result.error || 'unknown error')}`, 'error');
  if(result.stage_handoff) postStageHandoffToChat(result.stage_handoff);
  else if(result.clarification_required && Array.isArray(result.questions)) addMessage('Admin', result.questions.join('\n'));
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
function _updateDepthNotice(){
  const steps = Number(el('depth-steps')?.value || 0);
  const mins  = Number(el('depth-minutes')?.value || 0);
  const stop  = Boolean(el('depth-until-stop')?.checked);
  const notice = el('depth-notice');
  const send   = el('admin-send');
  if(!notice) return;
  const parts = [];
  if(steps > 0)  parts.push(`${steps} step${steps !== 1 ? 's' : ''}`);
  if(mins > 0)   parts.push(`${mins} min`);
  if(stop)       parts.push('until stopped');
  if(parts.length){
    notice.textContent = `⚡ Next message: runs ${parts.join(' · ')}`;
    notice.classList.remove('hidden');
    if(send) send.textContent = `Send (${parts.join('·')})`;
  } else {
    notice.classList.add('hidden');
    if(send) send.textContent = t('chat.send','Send');
  }
}
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
  const pendingBubble = _addPendingBubble();
  el('admin-send').disabled = true; el('chat-status').textContent = t('status.running','running');
  try{
    const modePick = pendingAction?.type === 'model_selection' ? parseModeText(text) : null;
    let result;
    if(activeStageHandoff?.run_id){
      result = await _sendActiveStageHandoffReply(text);
    }else if(modePick){
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
    pendingBubble.remove();
    absorbResult(result);
  }catch(e){ pendingBubble.remove(); addMessage('Admin', `Error: ${String(e)}`, 'error'); }
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
function _meminfoBytes(value){
  const match = String(value || '').trim().match(/^(\d+)/);
  return match ? Number(match[1]) * 1024 : null;
}
function _firstValue(...values){
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return null;
}
function _memoryBucket(memory, name){
  const bucket = memory[name] || {};
  if (name === 'ram') {
    const total = _firstValue(bucket.total, memory.total, _meminfoBytes(memory.MemTotal));
    const available = _firstValue(bucket.available, memory.available, _meminfoBytes(memory.MemAvailable));
    const used = _firstValue(bucket.used, memory.used, total != null && available != null ? total - available : null);
    const percent = _firstValue(bucket.percent, memory.percent, total ? used / total * 100 : null);
    return {total, used, percent};
  }
  const total = _firstValue(bucket.total, memory.swap_total, _meminfoBytes(memory.SwapTotal));
  const free = _firstValue(bucket.free, memory.swap_free, _meminfoBytes(memory.SwapFree));
  const used = _firstValue(bucket.used, memory.swap_used, total != null && free != null ? total - free : null);
  const percent = _firstValue(bucket.percent, memory.swap_percent, total ? used / total * 100 : null);
  return {total, used, percent};
}
function _parseGpuCsv(text){
  return String(text || '').trim().split('\n').map((line) => {
    const parts = line.split(',').map((part) => part.trim());
    if (parts.length < 6) return null;
    return {
      name: parts[0],
      temperature_c: parts[1],
      power_w: parts[2],
      memory_used_mib: parts[3],
      memory_total_mib: parts[4],
      utilization_percent: parts[5],
    };
  }).filter(Boolean);
}
function _fmtGpuRows(hw){
  const gpus = Array.isArray(hw.gpus) && hw.gpus.length ? hw.gpus : _parseGpuCsv(hw.nvidia_smi?.stdout);
  if (!gpus.length) {
    const reason = hw.nvidia_smi?.stderr || (hw.nvidia_smi?.available === false ? 'nvidia-smi unavailable' : '');
    return [`GPU:   ${reason ? `not available (${reason})` : 'not available'}`];
  }
  const rows = [];
  gpus.forEach((gpu, idx) => {
    const label = gpus.length > 1 ? `GPU ${idx + 1}` : 'GPU';
    rows.push(`${label}:   ${_na(gpu.name)}`);
    rows.push(`  Temp: ${_na(gpu.temperature_c)} C · Power: ${_na(gpu.power_w)} W · Util: ${_na(gpu.utilization_percent)}%`);
    rows.push(`  VRAM: ${_na(gpu.memory_used_mib)} / ${_na(gpu.memory_total_mib)} MiB`);
  });
  return rows;
}
function _fmtHardware(hw){
  if (!hw) return '—';
  const m = hw.memory || {};
  const ram = _memoryBucket(m, 'ram');
  const swap = _memoryBucket(m, 'swap');
  const lines = [
    `RAM:   ${_gib(ram.used)} / ${_gib(ram.total)} (${_pct(ram.percent)} used)`,
    `Swap:  ${_gib(swap.used)} / ${_gib(swap.total)} (${_pct(swap.percent)} used)`,
  ];
  return lines.concat(_fmtGpuRows(hw)).join('\n');
}
function _metricRow(label, value){ return `${label.padEnd(22)} ${value != null && value !== '' ? String(value) : '—'}`; }
function _metricCellRow(label, cell, formatter){
  const c = cell && typeof cell === 'object' && Object.prototype.hasOwnProperty.call(cell, 'value')
    ? cell
    : {value: cell, source: 'legacy telemetry field'};
  const value = c.value;
  const present = !(value == null || value === '' || (Array.isArray(value) && value.length === 0));
  if (!present) {
    const reason = c.reason || 'not present in source artifact';
    const source = c.source ? ` (${c.source})` : '';
    return _metricRow(label, `missing: ${reason}${source}`);
  }
  let rendered = formatter ? formatter(value) : value;
  if (Array.isArray(rendered)) rendered = rendered.length ? rendered.join(', ') : 'none';
  const source = c.source ? ` [${c.source}]` : '';
  return _metricRow(label, `${rendered}${source}`);
}
function _na(value){
  const text = value == null ? '' : String(value).trim();
  return text || 'not available';
}
function _fmtSoftware(health){
  const h = health || {};
  const gitReason = _na(h.git_metadata_reason || 'package/release install metadata only; git metadata not reported');
  return [
    _metricRow('Version:', _na(h.version)),
    _metricRow('Root:', _na(h.root)),
    _metricRow('State:', _na(h.state)),
    _metricRow('Git branch:', _na(h.git_branch)),
    _metricRow('Git head:', _na(h.git_head)),
    _metricRow('Git metadata:', gitReason),
    _metricRow('CLI path:', _na(h.cli_path)),
    _metricRow('Install path:', _na(h.install_path)),
  ].join('\n');
}
function _fmtRuntimeState(runtime){
  const rt = runtime || {};
  const policy = rt.device_policy || {};
  const persistent = policy.persistent_default || {};
  const sessionOverride = policy.session_override || {};
  const effective = policy.effective_policy || {};
  const sockets = rt.sockets || {};
  const services = rt.service_states || {};
  const socketStates = rt.socket_states || {};
  const active = rt.active_model || {};
  const startup = rt.startup_profile || {};
  const transition = startup.transition || {};
  const serviceRows = Object.entries(services).map(([name, item]) => {
    const unit = item?.unit || name;
    const state = item?.state || 'unknown';
    return `  ${unit}: ${state}`;
  });
  const socketRows = Object.entries(socketStates).map(([name, item]) => {
    const path = item?.path || name;
    const state = item?.state || (item?.present ? 'present' : 'missing');
    return `  ${path}: ${state}`;
  });
  const fallbackSocketRows = Object.keys(sockets).map(path => `  ${path}: ${sockets[path] ? 'present' : 'missing'}`);
  if (!socketRows.length && !fallbackSocketRows.some(row => row.includes(CANONICAL_MAIN_BACKEND_SOCKET))) {
    fallbackSocketRows.unshift(`  ${CANONICAL_MAIN_BACKEND_SOCKET}: not reported`);
  }
  const freshness = rt.state_freshness || {};
  return [
    'State freshness',
    _metricRow('  State:', freshness.state || 'unknown'),
    _metricRow('  Observed at:', freshness.observed_at || rt.observed_at || '—'),
    '',
    'Services',
    serviceRows.length ? serviceRows.join('\n') : '  not available',
    '',
    'Device policy',
    _metricRow('  Safe default:', policy.safe_default?.policy || 'cpu'),
    _metricRow('  Persistent default:', persistent.policy ? `${persistent.policy}${persistent.configured ? '' : ' (not configured)'}` : 'not configured'),
    _metricRow('  Session override:', sessionOverride.policy ? `${sessionOverride.policy} (session only)` : 'none'),
    _metricRow('  Effective:', effective.policy || policy.policy || policy.mode || '—'),
    _metricRow('  Pending apply:', policy.pending_apply),
    _metricRow('  Applies on:', effective.applies_on || policy.applies_on),
    _metricRow('  Updated at:', effective.updated_at || policy.updated_at),
    _metricRow('  Note:', policy.note),
    _metricRow('  GPU policy:', effective.gpu_policy || policy.gpu_policy),
    _metricRow('  Max active workers:', effective.max_active_heavy_workers || policy.max_active_heavy_workers || policy.max_active_llms),
    '',
    'Sockets',
    socketRows.length ? socketRows.join('\n') : (fallbackSocketRows.length ? fallbackSocketRows.join('\n') : '  not available'),
    '',
    'Active model',
    _metricRow('  State:', active.state || (rt.model_selection_required ? 'missing' : '—')),
    _metricRow('  Model:', active.model_id || active.name || '—'),
    _metricRow('  Manifest exists:', active.manifest_exists),
    _metricRow('  Manifest path:', active.manifest_path),
    _metricRow('  Model realpath:', active.model_realpath),
    _metricRow('  Selection required:', active.selection_required ?? rt.model_selection_required),
    _metricRow('  Message:', active.message || '—'),
    '',
    'Startup profile',
    _metricRow('  Safe minimal:', startup.safe_minimal_profile || 'minimal'),
    _metricRow('  Default:', startup.default_profile),
    _metricRow('  Session:', startup.session_profile),
    _metricRow('  Last usable:', startup.last_known_usable_profile),
    _metricRow('  Active:', startup.active_profile),
    _metricRow('  Reason:', startup.active_reason || transition.reason),
    _metricRow('  Transition:', transition.state),
    _metricRow('  Test endpoint:', startup.api?.test_endpoint || '/api/startup/profile'),
  ].join('\n');
}
function _fmtProductMetrics(prod){
  if (!prod) return '—';
  const ms = prod.model_selection || {};
  const cm = prod.creative_media || {};
  const metrics = ms.metrics || {};
  const state = metrics.staffing_state || ms.staffing_state;
  const degradedNote = ms.staffing_state === 'degraded_selected'
    ? [
        'degraded_selected',
        ms.status_explanation || 'Mandatory core roles are staffed, but selected role quality is below target thresholds.',
        `Next action: ${ms.next_action || 'Review degraded roles and continue only with explicit degraded approval or rerun model selection.'}`,
        '',
      ]
    : (ms.status_explanation ? ['Model selection', ms.status_explanation, ms.next_action ? `Next action: ${ms.next_action}` : '', ''] : []);
  const rows = [
    ...degradedNote.filter(Boolean),
    _metricCellRow('Selected model:', metrics.current_main_model || ms.current_main_model || ms.main_model),
    _metricCellRow('Selection status:', state),
    _metricCellRow('Selected count:', metrics.selected_model_count || ms.selected_model_count),
    _metricCellRow('Role coverage:', metrics.role_coverage),
    _metricCellRow('Target-met roles:', metrics.target_met_roles),
    _metricCellRow('Degraded roles:', metrics.degraded_roles),
    _metricCellRow('Unstaffed roles:', metrics.unstaffed_roles),
    _metricCellRow('Missing mandatory:', metrics.missing_mandatory_core_roles || ms.missing_mandatory_core_roles),
    _metricCellRow('Warnings:', metrics.warnings),
    _metricCellRow('Score:', metrics.selection_score || ms.selection_score),
    _metricCellRow('Pass rate:', metrics.pass_rate || ms.pass_rate, v => _pct(Number(v) * 100)),
    _metricCellRow('JSON parse rate:', metrics.json_parse_rate || ms.json_parse_rate, v => _pct(Number(v) * 100)),
    _metricCellRow('Quality score:', metrics.quality_score || ms.quality_score),
    _metricCellRow('Avg latency (s):', metrics.avg_latency_s || ms.avg_latency_s),
    _metricCellRow('Failed tasks:', metrics.failed_tasks || ms.failed_tasks),
    _metricCellRow('Selection mode:', metrics.selection_mode),
    _metricCellRow('Top-N composite:', metrics.selected_composite_top_n || ms.selected_composite_top_n),
    cm.status ? _metricRow('Creative media:', cm.status) : null,
  ].filter(Boolean);
  return rows.join('\n');
}
async function refreshTelemetry(){
  try{
    const [st, health] = await Promise.all([api('/api/telemetry/status'), api('/api/health')]);
    const apiVersion = health.version || st.version || '';
    const mismatch = st.version && health.version && st.version !== health.version;
    el('version-line').textContent = mismatch ? `NoemaForge / version mismatch: API ${health.version} telemetry ${st.version}` : `NoemaForge / ${apiVersion || 'not available'}`;
    el('hardware-status').textContent = 'ok';
    el('runtime-status').textContent = st.runtime?.main_backend?.stdout || st.runtime?.main_backend?.returncode || 'runtime';
    const productState = st.product?.model_selection?.staffing_state || '—';
    el('product-status').textContent = productState;
    el('product-status').title = st.product?.model_selection?.status_explanation || '';
    el('hardware-metrics').textContent = _fmtHardware(st.hardware);
    renderRuntimeObserverCards(st.runtime?.observer_cards || []);
    el('software-metrics').textContent = _fmtSoftware(health);
    el('runtime-metrics').textContent = _fmtRuntimeState(st.runtime);
    const effectiveDevicePolicy = st.runtime?.device_policy?.effective_policy?.policy || st.runtime?.device_policy?.policy;
    if (effectiveDevicePolicy && el('device-policy')) el('device-policy').value = effectiveDevicePolicy;
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
  const activeJobs = list.filter(j=>CANCELLABLE_JOB_STATES.has(j.status));
  el('job-summary').textContent = `${activeJobs.length} active`;
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
    const actionStateValue = j.action_state_label || j.action_state;
    const actionState = actionStateValue ? ` · ${actionStateValue}` : '';
    job.append(makeNode('span', '', `${j.status}${actionState} · ${j.job_id}`));
    if(j.next_action_label) job.append(makeNode('span', '', `Next: ${j.next_action_label}`));
    job.append(makeNode('code', '', j.command || ''));
    if(j.next_action_command) job.append(makeNode('code', '', j.next_action_command));
    return job;
  }));
}
async function refreshJobs(){
  try{
    const st = await api('/api/jobs');
    renderJobs(st.jobs || []);
  }catch(e){ showMuted(el('jobs'), 'jobs unavailable'); }
}
async function refreshActivePipelineRuns(){
  const ids = Array.from(activeRunIds).filter(Boolean);
  await Promise.allSettled(ids.map(async runId => {
    const status = await api(`/api/pipeline/run/${encodeURIComponent(runId)}/status`);
    document.querySelectorAll('.pipeline-run-panel').forEach(panel => {
      if(String(panel.dataset.runId || '') === String(runId)) _updatePipelineRunPanel(panel, status);
    });
  }));
}
async function refreshActiveWork(){
  await Promise.allSettled([refreshJobs(), refreshTelemetry(), refreshEpoch(false), refreshActivePipelineRuns()]);
}
function startActiveWorkPolling(){
  if(activeWorkPollTimer) return;
  activeWorkPollTimer = setInterval(async () => {
    const activeJobs = Number(String(el('job-summary')?.textContent || '').match(/^\d+/)?.[0] || 0);
    if(activeJobs > 0 || activeRunIds.size > 0) await refreshActiveWork();
  }, 3000);
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
async function showPersonaRules(){
  try{
    const st = await api('/api/persona/rules');
    showPersonaRulesModal(st);
  }catch(e){ addMessage('Admin', `Persona rules error: ${String(e)}`, 'error'); }
}
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
async function setDevicePolicy(){ try{ const r = await api('/api/runtime/device-policy', {policy:el('device-policy').value, scope:'session'}); absorbResult(r); }catch(e){ addMessage('Admin', `Device policy error: ${String(e)}`, 'error'); } }
async function resetDevicePolicy(){ try{ const r = await api('/api/runtime/device-policy', {reset_to_safe_default:true, scope:'session'}); absorbResult(r); el('device-policy').value = 'cpu'; }catch(e){ addMessage('Admin', `Device policy reset error: ${String(e)}`, 'error'); } }
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
async function runPipelineDirect(id, request){
  if(!id) return;
  try{
    _launchHistory.set(id, Date.now());
    const result = await api('/api/pipeline/run', {pipeline:id, request:request || `Запусти ${id} по стандартному сценарию`, allow_degraded:true});
    result.mode ||= 'pipeline_run';
    result.route ||= {id:'pipeline', intent:'pipeline_run', pipeline_id:id};
    result.pipeline_id ||= id;
    absorbResult(result);
    await refreshActiveWork();
  }catch(e){ addMessage('Admin', `Pipeline start error: ${String(e)}`, 'error'); }
}
function startPipeline(id){
  const info = pipelineById(id);
  const missingRequired = Array.isArray(info.required_parameters) ? info.required_parameters.filter(p => !p.default && !p.value) : [];
  if(!missingRequired.length){
    runPipelineDirect(id, `Запусти ${id} по стандартному сценарию`);
    return;
  }
  const codename = info.persona_codename || 'Атлас';
  const isRepeat = _launchHistory.has(id) && (Date.now() - _launchHistory.get(id)) < _REPEAT_WINDOW_MS;
  _confirmPipelineId = id;
  const safeId = info.id || id || 'pipeline';
  el('pipeline-confirm-title').textContent = `Pipeline: ${safeId}`;
  el('pipeline-confirm-desc').textContent = info.description || '';
  el('pipeline-confirm-persona').textContent = `→ Persona: ${codename}`;
  el('pipeline-confirm-repeat').classList.toggle('hidden', !isRepeat);
  el('pipeline-confirm-continue').classList.toggle('hidden', !isRepeat);
  el('pipeline-confirm-req').value = `Запусти ${safeId} по стандартному сценарию\n\nMissing: ${missingRequired.join(', ')}`;

  el('pipeline-confirm').classList.remove('hidden');
  el('pipeline-confirm-req').focus();
  el('pipeline-confirm-req').select();
}
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
  m.querySelectorAll('button').forEach(b => b.onclick = async () => { m.classList.add('hidden'); const act=b.dataset.act; if(act==='diagram'){ const _dd=await api(`/api/pipelines/${encodeURIComponent(id)}/diagram`); showPipelineDiagram(id,_dd); } else if(act==='stats') showModal('Pipeline stats', await api(`/api/pipelines/${encodeURIComponent(id)}/stats`)); else if(act==='explain'){ el('admin-message').value = `что значит пайплайн ${id}`; sendAdmin(); } else openPipelineEditor(id); });
}
function showPipelineDiagram(id, data){
  const stages=Array.isArray(data&&data.stages)?data.stages:[];
  const mermaidSrc=(data&&data.mermaid)||'';
  const BOX_W=140,BOX_H=44,GAP=40,MARGIN=20;
  const n=Math.max(stages.length,1);
  const svgW=MARGIN*2+n*BOX_W+(n-1)*GAP;
  const svgH=80,cy=40;
  const NS='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(NS,'svg');
  svg.setAttribute('viewBox',`0 0 ${svgW} ${svgH}`);
  svg.setAttribute('width',String(svgW));
  svg.setAttribute('height',String(svgH));
  svg.style.cssText='max-width:100%;display:block';
  const defs=document.createElementNS(NS,'defs');
  const mk=document.createElementNS(NS,'marker');
  mk.setAttribute('id','d6arr');mk.setAttribute('markerWidth','8');mk.setAttribute('markerHeight','8');
  mk.setAttribute('refX','6');mk.setAttribute('refY','3');mk.setAttribute('orient','auto');
  const ap=document.createElementNS(NS,'path');
  ap.setAttribute('d','M0,0 L0,6 L8,3 z');ap.setAttribute('fill','#8ec5ff');
  mk.appendChild(ap);defs.appendChild(mk);svg.appendChild(defs);
  stages.forEach((s,i)=>{
    const x=MARGIN+i*(BOX_W+GAP),y=cy-BOX_H/2;
    const r=document.createElementNS(NS,'rect');
    r.setAttribute('x',String(x));r.setAttribute('y',String(y));
    r.setAttribute('width',String(BOX_W));r.setAttribute('height',String(BOX_H));
    r.setAttribute('rx','10');r.setAttribute('fill','#0b1118');
    r.setAttribute('stroke','#2b70c9');r.setAttribute('stroke-width','1.5');
    svg.appendChild(r);
    const t=document.createElementNS(NS,'text');
    t.setAttribute('x',String(x+BOX_W/2));t.setAttribute('y',String(cy+5));
    t.setAttribute('text-anchor','middle');t.setAttribute('fill','#e8f2ff');
    t.setAttribute('font-size','12');t.setAttribute('font-family','Inter,system-ui,sans-serif');
    t.textContent=s;svg.appendChild(t);
    if(i<stages.length-1){
      const ln=document.createElementNS(NS,'line');
      ln.setAttribute('x1',String(x+BOX_W));ln.setAttribute('y1',String(cy));
      ln.setAttribute('x2',String(x+BOX_W+GAP-8));ln.setAttribute('y2',String(cy));
      ln.setAttribute('stroke','#8ec5ff');ln.setAttribute('stroke-width','1.5');
      ln.setAttribute('marker-end','url(#d6arr)');svg.appendChild(ln);
    }
  });
  const wrap=document.createElement('div');
  wrap.appendChild(svg);
  if(mermaidSrc){
    const det=document.createElement('details');
    det.style.marginTop='12px';
    const sum=document.createElement('summary');
    sum.textContent='Mermaid source (debug)';
    sum.style.cssText='cursor:pointer;color:var(--muted);font-size:12px';
    const pre=document.createElement('pre');
    pre.textContent=mermaidSrc;pre.style.cssText='font-size:11px;margin-top:8px';
    det.appendChild(sum);det.appendChild(pre);wrap.appendChild(det);
  }
  el('modal-title').textContent=`Pipeline diagram — ${id}`;
  const body=el('modal-body');body.textContent='';body.appendChild(wrap);
  el('modal').classList.remove('hidden');
}
function _jsonPre(obj){
  const pre = makeNode('pre', '', typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2));
  return pre;
}
function showModal(title, obj){
  el('modal-title').textContent = title;
  replaceWithNodes(el('modal-body'), [_jsonPre(obj)]);
  el('modal').classList.remove('hidden');
}
function _personaRulesVisualText(visual){
  const parts = [];
  if(visual.status) parts.push(`Status: ${visual.status}`);
  if(visual.value != null) parts.push(`Value: ${visual.value}${visual.max != null ? ` / ${visual.max}` : ''}${visual.unit ? ` ${visual.unit}` : ''}`);
  if(Array.isArray(visual.rows)) parts.push(`${visual.rows.length} rows`);
  if(Array.isArray(visual.points)) parts.push(`${visual.points.length} points`);
  if(Array.isArray(visual.events)) parts.push(`${visual.events.length} events`);
  return parts.join('\n') || (visual.source || 'persona_rules');
}
function showPersonaRulesModal(payload){
  const rendered = payload.rendered_rules || {};
  const sections = Array.isArray(rendered.sections) ? rendered.sections : [];
  const visuals = Array.isArray(payload.visuals) ? payload.visuals : (Array.isArray(rendered.visuals) ? rendered.visuals : []);
  const root = makeNode('div', 'persona-rules-view');
  if(sections.length){
    sections.forEach(section => {
      const card = makeNode('section', 'persona-rule-section');
      card.append(makeNode('h3', '', section.title || 'Persona rules'));
      const lines = Array.isArray(section.lines) ? section.lines : [];
      const list = makeNode('ul');
      lines.forEach(line => list.append(makeNode('li', '', String(line || '').replace(/^- /, ''))));
      card.append(list);
      root.append(card);
    });
  }else{
    root.append(_jsonPre(rendered.text || 'No readable persona rules are available.'));
  }
  if(visuals.length){
    const grid = makeNode('div', 'persona-visual-grid');
    visuals.forEach(visual => {
      const card = makeNode('div', 'persona-visual');
      card.dataset.renderHint = String(visual.type || '');
      card.append(makeNode('b', '', `${visual.type || 'Visual'} · ${visual.title || 'Persona rules'}`));
      card.append(makeNode('span', 'muted', _personaRulesVisualText(visual)));
      grid.append(card);
    });
    root.append(grid);
  }
  const audit = makeNode('details', 'audit-card');
  audit.append(makeNode('summary', '', 'Raw JSON audit'));
  audit.append(_jsonPre(payload.rules || payload));
  root.append(audit);
  el('modal-title').textContent = 'Persona rules';
  replaceWithNodes(el('modal-body'), [root]);
  el('modal').classList.remove('hidden');
}
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
  await Promise.allSettled([refreshEpoch(false), refreshTelemetry(), refreshTasks(), refreshJobs(), refreshInactivity(), refreshPersona(), _loadPersonaSelect(), loadUsecases(), loadPublicShowcase(), loadPipelines()]);
  _updateDepthNotice();
  connectJobProgressStream();
  startActiveWorkPolling();
  // Poll events every 10 s alongside other refresh tasks; deduplication by lastEventIndex.
  setInterval(()=>{ refreshTelemetry(); refreshJobs(); refreshInactivity(); refreshEpoch(false); pollEvents(); }, 10000);
}
if (typeof window !== 'undefined' && window.document === document) {
  el('admin-send').addEventListener('click', sendAdmin);

  el('admin-message').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendAdmin();
    }
  });

  el('locale-select').addEventListener('change', e => {
    activeLocale = e.target.value;
    applyLocaleMessages();
    renderArtifacts(latestArtifacts);
    _updateDepthNotice();
  });

  el('gui-shutdown').addEventListener('click', async () => {
    try {
      await api('/api/shutdown', { reason: 'operator' });
      addMessage('Admin', 'GUI shutdown requested.');
    } catch (e) {}
  });

  el('epoch-refresh').addEventListener('click', () => refreshEpoch(true));
  el('epoch-apply').addEventListener('click', applyEpoch);
  el('selection-continue').addEventListener('click', continueSelection);
  el('vault-reinventory').addEventListener('click', reinventoryVault);
  el('persona-rules')?.addEventListener('click', showPersonaRules);
  el('workflow-stop').addEventListener('click', stopWorkflow);
  el('depth-steps').addEventListener('input', _updateDepthNotice);
  el('depth-minutes').addEventListener('input', _updateDepthNotice);
  el('depth-until-stop').addEventListener('change', _updateDepthNotice);
  el('device-policy').addEventListener('change', setDevicePolicy);
  el('device-policy-reset').addEventListener('click', resetDevicePolicy);
  el('tasks-refresh').addEventListener('click', refreshTasks);
  el('task-add').addEventListener('click', addTaskDialog);
  el('public-showcase-load').addEventListener('click', loadPublicShowcase);
  el('pipeline-search').addEventListener('input', renderPipelines);

  el('pipeline-new').addEventListener('click', () => {
    const title = prompt('New pipeline draft title:', 'new_pipeline');
    if (!title) return;

    pipelineEditorState = {
      pipeline_id: title,
      title,
      description: '',
      stages: ['intake', 'plan', 'review'],
    };

    renderPipelineEditor();
  });

  el('modal-close').addEventListener('click', () => {
    el('modal').classList.add('hidden');
  });

  function _closePipelineConfirm() {
    el('pipeline-confirm').classList.add('hidden');
  }

  el('pipeline-confirm-close').addEventListener('click', _closePipelineConfirm);
  el('pipeline-confirm-cancel').addEventListener('click', _closePipelineConfirm);

  el('pipeline-confirm-ok').addEventListener('click', () => {
    const req = el('pipeline-confirm-req').value.trim();
    const id = typeof _confirmPipelineId !== 'undefined'
      ? _confirmPipelineId
      : null;

    _closePipelineConfirm();

    if (!req || !id) return;
    runPipelineDirect(id, req);
  });

  const pipelineConfirmContinue = el('pipeline-confirm-continue');
  if (pipelineConfirmContinue) {
    pipelineConfirmContinue.addEventListener('click', () => {
      // UAT/source guard: admin-message Продолжи
      const id = typeof _confirmPipelineId !== 'undefined'
        ? _confirmPipelineId
        : null;

      _closePipelineConfirm();

      if (!id) return;

      runPipelineDirect(id, `Продолжи ${id} по текущему сценарию`);
    });
  }

  document.addEventListener('keydown', e => {
    if (
      e.key === 'Escape' &&
      !el('pipeline-confirm').classList.contains('hidden')
    ) {
      _closePipelineConfirm();
    }
  });

  document.addEventListener('click', e => {
    if (!el('context-menu').contains(e.target)) {
      el('context-menu').classList.add('hidden');
    }
  });

  startup();
}

/* Draft pipeline editor | drag&drop pipeline editor planned */
