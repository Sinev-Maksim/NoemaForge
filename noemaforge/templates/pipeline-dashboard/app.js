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
let restoredSelectionMode = {mode:'full_composite', composite_top_n:4};

const DASHBOARD_API_ENDPOINT = '/api/dashboard';
const GUI_STATE_FALLBACK_ENDPOINT = '/api/gui/state';

const personaNames = {
  Admin: 'Admin', Optimizer: 'Optimizer', 'Model Evolution': 'Model Evolution', 'Dev Team': 'Dev Team',
  'Music Team': 'Music Team', 'Video Team': 'Video Team', 'Vision Team': 'Vision Team', Runtime: 'Runtime',
  'Task Manager': 'Task Manager', System: 'System'
};

function t(key, fallback){ return (allMessages[activeLocale] && allMessages[activeLocale][key]) || fallback || key; }
function htmlEscape(v){ return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function setText(id, value){ const node = el(id); if(node) node.textContent = value; }
function setPlaceholder(id, value){ const node = el(id); if(node) node.placeholder = value; }
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
  div.innerHTML = `<small>${htmlEscape(speakerLabel(who))}</small>${htmlEscape(text || '')}`;
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
  el('chat-log').innerHTML = '';
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
function artifactPreviewUrl(a){ const p = artifactPath(a); return a?.preview_url || a?.open_url || (p ? `/api/artifacts/open?path=${encodeURIComponent(p)}` : ''); }
function artifactDownloadUrl(a){ const p = artifactPath(a); return a?.download_url || (p ? `/api/artifacts/download?path=${encodeURIComponent(p)}` : ''); }
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
  if(!list.length){ el('artifacts').innerHTML = `<p class="muted">${htmlEscape(t('artifact.none','No artifacts yet.'))}</p>`; return; }
  const groups = {};
  list.forEach((a, index) => { (groups[artifactGroup(a.type || a.label)] ||= []).push({artifact:a, index}); });
  el('artifacts').innerHTML = Object.entries(groups).map(([g, arr]) => `<h3 class="muted">${htmlEscape(g)}</h3>` + arr.slice(-8).reverse().map(({artifact:a, index}) => {
    const downloadUrl = artifactDownloadUrl(a);
    return `<div class="artifact"><b>${htmlEscape(a.label || a.type || 'artifact')}</b><span>${htmlEscape(a.status || '')} · ${htmlEscape(a.type || '')}</span><code>${htmlEscape(a.path || a.open_command || '')}</code><div class="artifact-actions"><button class="ghost small" data-artifact-open="${index}">${htmlEscape(t('artifact.open','Open'))}</button><a class="ghost small artifact-link" href="${htmlEscape(downloadUrl)}" download>${htmlEscape(t('artifact.download','Download'))}</a><button class="ghost small" data-artifact-copy="${index}">${htmlEscape(t('artifact.copy_path','Copy path'))}</button></div></div>`;
  }).join('')).join('');
  el('artifacts').querySelectorAll('[data-artifact-open]').forEach(btn => btn.addEventListener('click', () => openArtifact(btn.dataset.artifactOpen)));
  el('artifacts').querySelectorAll('[data-artifact-copy]').forEach(btn => btn.addEventListener('click', () => navigator.clipboard?.writeText(artifactPath(latestArtifacts[Number(btn.dataset.artifactCopy)]))));
}
function renderInternal(events){
  const arr = events || [];
  el('internal-chat').innerHTML = arr.length ? arr.slice(-8).map(e => `<div class="internal-event">${htmlEscape(e)}</div>`).join('') : `<p class="muted">${htmlEscape(t('internal.none','No internal handoffs yet.'))}</p>`;
}
function absorbResult(result){
  latestRaw = result || {};
  el('raw-json').textContent = JSON.stringify(result, null, 2);
  const route = result.route || {};
  const personaSwitch = result.persona_switch;
  if(personaSwitch && personaSwitch.switch_line){ addSystemLine(personaSwitch.switch_line); setPersona(personaSwitch.to); }
  if(result.reply) addMessage(personaSwitch?.to || route.label || result.persona || 'Admin', result.reply, result.ok === false ? 'error' : '');
  if(result.clarification_required && Array.isArray(result.questions)) addMessage('Admin', result.questions.join('\n'));
  if(Array.isArray(result.artifacts)) renderArtifacts(result.artifacts);
  if(Array.isArray(result.internal_events)) renderInternal(result.internal_events);
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
  target.innerHTML = list.length ? list.map(card => `<div class="observer-card ${htmlEscape(card.status || 'warn')}"><b>${htmlEscape(card.title || card.id)}</b><span>${htmlEscape(card.state || 'unknown')}</span><small>${htmlEscape(card.smoke_affirmation || 'not_affirmed')}</small></div>`).join('') : '<p class="muted">Runtime observers unavailable.</p>';
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
async function refreshEpoch(showMessage=false){
  try{
    const st = await api('/api/epoch/status');
    const current = st.current_epoch || {}, progress = st.progress || {}, staffing = st.firstboot?.staffing || {}, latest = st.latest_model_selection || {};
    el('epoch-current-model').textContent = shortenPath(current.model_realpath || current.manifest?.model_id || '—');
    el('epoch-staffing').textContent = `${staffing.staffing_state || 'unknown'} · selected=${staffing.selected_model_count ?? '—'}`;
    el('epoch-progress').textContent = `${progress.tested_models ?? 0}/${progress.total_models ?? '—'} tested · failed=${progress.failed_models ?? 0} · left=${progress.remaining_models ?? '—'}`;
    el('epoch-latest-plan').textContent = latest.decision?.mode || latest.plan?.mode || '—';
    el('epoch-status-pill').textContent = st.apply_available ? 'ready' : 'no plan';
    el('epoch-status-pill').className = st.apply_available ? 'pill ok' : 'pill warn';
    if(showMessage) addMessage('Admin', `Epoch status: ${el('epoch-progress').textContent}`);
  }catch(e){ if(showMessage) addMessage('Admin', `Epoch status error: ${String(e)}`, 'error'); }
}
async function refreshTelemetry(){
  try{
    const st = await api('/api/telemetry/status');
    el('hardware-status').textContent = 'ok';
    el('runtime-status').textContent = st.runtime?.main_backend?.stdout || st.runtime?.main_backend?.returncode || 'runtime';
    el('product-status').textContent = st.product?.model_selection?.staffing_state || '—';
    el('hardware-metrics').textContent = JSON.stringify(st.hardware?.memory || {}, null, 2) + '\nGPU: ' + String(st.hardware?.nvidia_smi?.stdout || st.hardware?.nvidia_smi?.stderr || 'n/a').slice(0,220);
    renderRuntimeObserverCards(st.runtime?.observer_cards || []);
    el('runtime-metrics').textContent = JSON.stringify({device_policy:st.runtime?.device_policy, sockets:st.runtime?.sockets, model:st.runtime?.main_manifest?.model_id || st.runtime?.main_manifest?.name || 'main'}, null, 2);
    el('product-metrics').textContent = JSON.stringify({model_selection: st.product?.model_selection || {}, creative_media: st.product?.creative_media || {}, creative_metrics_policy: st.creative_metrics_policy || 'review-required'}, null, 2).slice(0,700);
  }catch(e){ el('hardware-status').textContent = 'error'; }
}
async function refreshTasks(){
  try{
    const st = await api('/api/tasks');
    const tasks = st.tasks || [];
    el('task-summary').textContent = `${st.summary?.pending || 0} pending · ${st.summary?.blocked || 0} blocked`;
    el('tasks').innerHTML = tasks.length ? tasks.slice(-8).reverse().map(x => `<div class="task"><b>${htmlEscape(x.title)}</b><span>${htmlEscape(x.category)} · p=${htmlEscape(x.priority)} · ${htmlEscape(x.status)}</span></div>`).join('') : '<p class="muted">No tasks yet.</p>';
  }catch(e){ el('tasks').innerHTML = `<p class="muted">tasks unavailable</p>`; }
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
  if(!list.length){ container.innerHTML = '<p class="muted">No jobs.</p>'; return; }
  container.innerHTML = list.slice(-6).reverse().map(j => {
    const canCancel = CANCELLABLE_JOB_STATES.has(j.status);
    const btn = canCancel ? `<button class="job-cancel-btn" data-job-id="${htmlEscape(j.job_id)}" title="Cancel job">✕</button>` : '';
    return `<div class="job">${btn}<b>${htmlEscape(j.kind)}</b><span>${htmlEscape(j.status)} · ${htmlEscape(j.job_id)}</span><code>${htmlEscape(j.command || '')}</code></div>`;
  }).join('');
  container.querySelectorAll('.job-cancel-btn').forEach(btn =>
    btn.addEventListener('click', () => cancelJob(btn.dataset.jobId))
  );
}
async function refreshJobs(){
  try{
    const st = await api('/api/jobs');
    renderJobs(st.jobs || []);
  }catch(e){ el('jobs').innerHTML = '<p class="muted">jobs unavailable</p>'; }
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
  try{
    const r = await api(`/api/events?after_index=${lastEventIndex}`);
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
  try{ const data = await api('/api/usecases'); const cases = data.usecases || []; el('usecases').innerHTML = cases.map(c => `<button class="usecase" data-help="${htmlEscape(c.example)}"><b>${htmlEscape(c.title)}</b><span>${htmlEscape(c.summary)}</span></button>`).join(''); document.querySelectorAll('[data-help]').forEach(btn => btn.addEventListener('click', ()=>{ el('admin-message').value = `что значит ${btn.getAttribute('data-help') || ''}`; sendAdmin(); })); }catch(_){ el('usecases').innerHTML = '<p class="muted">Usecase help unavailable.</p>'; }
}
function renderPublicShowcase(){
  const box = el('public-showcase');
  if(!box) return;
  const steps = Array.isArray(publicShowcaseScenario?.steps) ? publicShowcaseScenario.steps : [];
  el('public-showcase-status').textContent = publicShowcaseScenario?.status || '—';
  box.innerHTML = steps.length ? steps.map((step, index) => `<div class="showcase-step"><b>${htmlEscape(step.title || step.id)}</b><span>${htmlEscape(step.surface || '')} · ${htmlEscape(step.endpoint || '')}</span><div class="showcase-step-actions"><button class="ghost small" data-showcase-fill="${index}">Fill</button><button class="ghost small" data-showcase-preview="${index}">Preview</button></div></div>`).join('') : '<p class="muted">No scenario loaded.</p>';
  box.querySelectorAll('[data-showcase-fill]').forEach(btn => btn.addEventListener('click', () => fillShowcaseStep(Number(btn.dataset.showcaseFill))));
  box.querySelectorAll('[data-showcase-preview]').forEach(btn => btn.addEventListener('click', () => previewShowcaseStep(Number(btn.dataset.showcasePreview))));
}
async function loadPublicShowcase(){
  try{
    publicShowcaseScenario = await api('/api/public-showcase/scenario');
    renderPublicShowcase();
  }catch(_){
    el('public-showcase').innerHTML = '<p class="muted">Scenario unavailable.</p>';
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
  el('pipeline-list').innerHTML = filtered.slice(0,90).map(p => `<button class="pipeline-card" data-pipeline="${htmlEscape(p.id)}"><b>${htmlEscape(p.id)}</b><span>${htmlEscape(p.group)} · ${htmlEscape(String(p.description||'').slice(0,110))}</span></button>`).join('');
  document.querySelectorAll('[data-pipeline]').forEach(btn => { btn.addEventListener('click', ()=>startPipeline(btn.dataset.pipeline)); btn.addEventListener('contextmenu', e=>{ e.preventDefault(); showPipelineMenu(e, btn.dataset.pipeline); }); });
}
async function loadPipelines(){
  try{ const data = await api('/api/pipelines/catalog'); pipelineCatalog = data.pipelines || []; const groups = ['All', ...(data.groups || [])]; el('pipeline-groups').innerHTML = groups.map(g => `<button class="ghost small" data-group="${htmlEscape(g)}">${htmlEscape(g)}</button>`).join(''); document.querySelectorAll('[data-group]').forEach(b=>b.addEventListener('click',()=>{ pipelineFilter=b.dataset.group; renderPipelines(); })); renderPipelines(); }catch(e){ el('pipeline-list').innerHTML = '<p class="muted">Pipeline catalog unavailable.</p>'; }
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
  editor.innerHTML = `<div class="pipeline-editor-head"><div class="pipeline-editor-title"><b>${htmlEscape(pipelineEditorState.title)}</b><span>draft only · review required before activation</span></div><button id="pipeline-editor-close" class="ghost small">Close</button></div><div class="pipeline-stage-list">${pipelineEditorState.stages.map((stage, index) => `<div class="editor-stage" draggable="true" data-stage-index="${index}"><span class="stage-grip">drag</span><span>${htmlEscape(stage)}</span><div class="stage-actions"><button class="ghost small" data-stage-up="${index}">Up</button><button class="ghost small" data-stage-down="${index}">Down</button><button class="ghost small" data-stage-remove="${index}">Remove</button></div></div>`).join('')}</div><div class="pipeline-editor-actions"><button id="pipeline-stage-add" class="ghost small">Add stage</button><button id="pipeline-draft-save" class="small">Save draft</button></div>`;
  editor.querySelector('#pipeline-editor-close').onclick = () => editor.classList.add('hidden');
  editor.querySelector('#pipeline-stage-add').onclick = addPipelineStage;
  editor.querySelector('#pipeline-draft-save').onclick = savePipelineEditorDraft;
  editor.querySelectorAll('[data-stage-up]').forEach(btn => btn.onclick = () => movePipelineStage(Number(btn.dataset.stageUp), Number(btn.dataset.stageUp)-1));
  editor.querySelectorAll('[data-stage-down]').forEach(btn => btn.onclick = () => movePipelineStage(Number(btn.dataset.stageDown), Number(btn.dataset.stageDown)+1));
  editor.querySelectorAll('[data-stage-remove]').forEach(btn => btn.onclick = () => removePipelineStage(Number(btn.dataset.stageRemove)));
  editor.querySelectorAll('.editor-stage').forEach(row => {
    row.addEventListener('dragstart', ev => { row.classList.add('dragging'); ev.dataTransfer?.setData('text/plain', row.dataset.stageIndex || '0'); });
    row.addEventListener('dragend', () => row.classList.remove('dragging'));
    row.addEventListener('dragover', ev => ev.preventDefault());
    row.addEventListener('drop', ev => { ev.preventDefault(); movePipelineStage(Number(ev.dataTransfer?.getData('text/plain') || 0), Number(row.dataset.stageIndex || 0)); });
  });
}
async function savePipelineEditorDraft(){
  const result = await api('/api/pipelines/draft', {id:pipelineEditorState.pipeline_id, title:pipelineEditorState.title, description:pipelineEditorState.description, stages:pipelineEditorState.stages, editor_mode:'drag_drop_pipeline_editor', review_required:true});
  absorbResult(result);
}
function showPipelineMenu(e, id){
  const m = el('context-menu');
  m.innerHTML = `<button data-act="diagram">Open visual diagram</button><button data-act="stats">Show stats</button><button data-act="explain">Explain pipeline</button><button data-act="draft">Clone/edit draft</button>`;
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
  try{ const loc = await api('/api/locales'); allMessages = loc.messages || {}; if(Array.isArray(loc.locales)){ el('locale-select').innerHTML = loc.locales.map(x => `<option value=”${htmlEscape(x)}”>${htmlEscape(x)}</option>`).join(''); activeLocale = loc.locales.includes('ru') ? 'ru' : (loc.locales[0] || 'en'); el('locale-select').value = activeLocale; } applyLocaleMessages(); }catch(e){}
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
  try{ const loc = await api('/api/locales'); allMessages = loc.messages || {}; if(Array.isArray(loc.locales)){ el('locale-select').innerHTML = loc.locales.map(x => `<option value="${htmlEscape(x)}">${htmlEscape(x)}</option>`).join(''); activeLocale = loc.locales.includes('ru') ? 'ru' : (loc.locales[0] || 'en'); el('locale-select').value = activeLocale; } applyLocaleMessages(); }catch(e){}
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
