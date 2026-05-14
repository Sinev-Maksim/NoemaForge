/*
=== NoemaForge File Header ===
File: templates/pipeline-dashboard/app.js
Zone: gui/shell
Version: 0.31.13.alpha
Created: 2026-05-10
Modified: 2026-05-14
Purpose: Stateful Admin GUI frontend: backend-owned chat history, persona portraits,
  telemetry, epoch controls, task/job/pipeline dock, right-click pipeline menu and
  safe plan-first actions.
Inputs: JSON APIs from src/admin_gui_server.py.
Outputs: DOM updates only; privileged actions are requested as audited jobs/plans.
Tests: browser smoke + curl /api/gui/state + manual send/refresh/history test.
=== End NoemaForge File Header ===
*/
const el = id => document.getElementById(id);
let allMessages = {};
let activeLocale = 'ru';
let latestRaw = {};
let pendingAction = null;
let pipelineCatalog = [];
let pipelineFilter = 'All';

const personaNames = {
  Admin: 'Admin', Optimizer: 'Optimizer', 'Model Evolution': 'Model Evolution', 'Dev Team': 'Dev Team',
  'Music Team': 'Music Team', 'Video Team': 'Video Team', 'Vision Team': 'Vision Team', Runtime: 'Runtime',
  'Task Manager': 'Task Manager', System: 'System'
};

function t(key, fallback){ return (allMessages[activeLocale] && allMessages[activeLocale][key]) || fallback || key; }
function htmlEscape(v){ return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
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
  div.className = `bubble ${who}${cls ? ' '+cls : ''}`;
  div.innerHTML = `<small>${htmlEscape(who)}</small>${htmlEscape(text || '')}`;
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
function renderArtifacts(items){
  const list = items || [];
  if(!list.length){ el('artifacts').innerHTML = `<p class="muted">${htmlEscape(t('artifact.none','No artifacts yet.'))}</p>`; return; }
  const groups = {};
  for(const a of list){ (groups[artifactGroup(a.type || a.label)] ||= []).push(a); }
  el('artifacts').innerHTML = Object.entries(groups).map(([g, arr]) => `<h3 class="muted">${htmlEscape(g)}</h3>` + arr.slice(-8).reverse().map(a => `
    <div class="artifact"><b>${htmlEscape(a.label || a.type || 'artifact')}</b><span>${htmlEscape(a.status || '')} · ${htmlEscape(a.type || '')}</span><code>${htmlEscape(a.path || a.open_command || '')}</code><button class="ghost small" onclick="navigator.clipboard?.writeText('${htmlEscape(a.path || '')}')">${htmlEscape(t('artifact.copy_path','Copy path'))}</button></div>`).join('')).join('');
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
function budgetPayload(){ return { max_steps:Number(el('depth-steps').value || 0), time_budget_minutes:Number(el('depth-minutes').value || 0), until_stop:Boolean(el('depth-until-stop').checked) }; }

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
    el('runtime-metrics').textContent = JSON.stringify({device_policy:st.runtime?.device_policy, sockets:st.runtime?.sockets, model:st.runtime?.main_manifest?.model_id || st.runtime?.main_manifest?.name || 'main'}, null, 2);
    el('product-metrics').textContent = JSON.stringify(st.product || {}, null, 2).slice(0,500);
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
async function refreshJobs(){
  try{
    const st = await api('/api/jobs');
    const jobs = st.jobs || [];
    el('job-summary').textContent = `${jobs.filter(j=>['queued','running','needs_privilege'].includes(j.status)).length} active`;
    el('jobs').innerHTML = jobs.length ? jobs.slice(-6).reverse().map(j => `<div class="job"><b>${htmlEscape(j.kind)}</b><span>${htmlEscape(j.status)} · ${htmlEscape(j.job_id)}</span><code>${htmlEscape(j.command || '')}</code></div>`).join('') : '<p class="muted">No jobs.</p>';
  }catch(e){ el('jobs').innerHTML = '<p class="muted">jobs unavailable</p>'; }
}
async function refreshInactivity(){ try{ const st = await api('/api/inactivity/status'); el('inactivity-status').textContent = st.idle_human || '—'; el('inactivity').textContent = `policy=${st.policy?.mode || 'manual'} · next=${st.policy?.next_idle_action || 'none'} · status=${st.status}`; }catch(e){} }
async function refreshPersona(){ try{ const st = await api('/api/persona/current'); setPersona(st.active_persona || 'Admin', st.portrait_url); }catch(e){} }
async function applyEpoch(){ try{ absorbResult(await api('/api/epoch/apply', {locale: el('locale-select').value})); }catch(e){ addMessage('Admin', `Epoch apply error: ${String(e)}`, 'error'); } }
async function continueSelection(){ try{ const r = await api('/api/model-selection/continue', {mode:'full_composite', composite_top_n:4}); absorbResult(r); refreshJobs(); }catch(e){ addMessage('Admin', `Continue selection error: ${String(e)}`, 'error'); } }
async function reinventoryVault(){ try{ const r = await api('/api/vault/reinventory', {}); absorbResult(r); refreshJobs(); }catch(e){ addMessage('Admin', `Vault inventory error: ${String(e)}`, 'error'); } }
async function stopWorkflow(){ try{ absorbResult(await api('/api/workflow/stop', {reason:'operator_clicked_stop'})); }catch(e){ addMessage('Admin', `Stop error: ${String(e)}`, 'error'); } }
async function setDevicePolicy(){ try{ const r = await api('/api/runtime/device-policy', {policy:el('device-policy').value}); absorbResult(r); }catch(e){ addMessage('Admin', `Device policy error: ${String(e)}`, 'error'); } }
async function loadUsecases(){
  try{ const data = await api('/api/usecases'); const cases = data.usecases || []; el('usecases').innerHTML = cases.map(c => `<button class="usecase" data-help="${htmlEscape(c.example)}"><b>${htmlEscape(c.title)}</b><span>${htmlEscape(c.summary)}</span></button>`).join(''); document.querySelectorAll('[data-help]').forEach(btn => btn.addEventListener('click', ()=>{ el('admin-message').value = `что значит ${btn.getAttribute('data-help') || ''}`; sendAdmin(); })); }catch(_){ el('usecases').innerHTML = '<p class="muted">Usecase help unavailable.</p>'; }
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
function showPipelineMenu(e, id){
  const m = el('context-menu');
  m.innerHTML = `<button data-act="diagram">Open visual diagram</button><button data-act="stats">Show stats</button><button data-act="explain">Explain pipeline</button><button data-act="draft">Clone/edit draft (TODO)</button>`;
  m.style.left = `${e.clientX}px`; m.style.top = `${e.clientY}px`; m.classList.remove('hidden');
  m.querySelectorAll('button').forEach(b => b.onclick = async () => { m.classList.add('hidden'); const act=b.dataset.act; if(act==='diagram') showModal('Pipeline diagram', await api(`/api/pipelines/${encodeURIComponent(id)}/diagram`)); else if(act==='stats') showModal('Pipeline stats', await api(`/api/pipelines/${encodeURIComponent(id)}/stats`)); else if(act==='explain'){ el('admin-message').value = `что значит пайплайн ${id}`; sendAdmin(); } else showModal('Draft pipeline editor', {todo:'drag&drop pipeline editor planned', pipeline:id}); });
}
function showModal(title, obj){ el('modal-title').textContent = title; el('modal-body').textContent = typeof obj === 'string' ? obj : JSON.stringify(obj,null,2); el('modal').classList.remove('hidden'); }
async function addTaskDialog(){ const title = prompt('Task title:'); if(!title) return; const cat = prompt('Category:', 'gui') || 'general'; const priority = Number(prompt('Priority 1-100:', '50') || 50); const r = await api('/api/tasks/create', {title, category:cat, priority}); absorbResult(r); refreshTasks(); }
async function startup(){
  try{ const loc = await api('/api/locales'); allMessages = loc.messages || {}; if(Array.isArray(loc.locales)){ el('locale-select').innerHTML = loc.locales.map(x => `<option value="${htmlEscape(x)}">${htmlEscape(x)}</option>`).join(''); activeLocale = loc.locales.includes('ru') ? 'ru' : (loc.locales[0] || 'en'); el('locale-select').value = activeLocale; } }catch(e){}
  try{ const st = await api('/api/gui/state'); renderConversation(st.conversation || {}); renderArtifacts(st.conversation?.artifacts || []); if(st.persona?.portrait_url) setPersona(st.persona.active_persona || st.persona.persona?.role_key || 'Admin', st.persona.portrait_url); }catch(e){ addMessage('Admin', t('startup.ready','Ready. Say “Hello”, ask Dev Team, model optimization, or media plan.')); }
  await Promise.allSettled([refreshEpoch(false), refreshTelemetry(), refreshTasks(), refreshJobs(), refreshInactivity(), refreshPersona(), loadUsecases(), loadPipelines()]);
  setInterval(()=>{ refreshTelemetry(); refreshJobs(); refreshInactivity(); refreshEpoch(false); }, 10000);
}
el('admin-send').addEventListener('click', sendAdmin);
el('admin-message').addEventListener('keydown', e => { if(e.key === 'Enter' && (e.ctrlKey || e.metaKey)){ e.preventDefault(); sendAdmin(); } });
el('locale-select').addEventListener('change', e => { activeLocale = e.target.value; });
el('gui-shutdown').addEventListener('click', async()=>{ try{ await api('/api/shutdown', {reason:'operator'}); addMessage('Admin','GUI shutdown requested.'); }catch(e){} });
el('epoch-refresh').addEventListener('click', ()=>refreshEpoch(true));
el('epoch-apply').addEventListener('click', applyEpoch);
el('selection-continue').addEventListener('click', continueSelection);
el('vault-reinventory').addEventListener('click', reinventoryVault);
el('workflow-stop').addEventListener('click', stopWorkflow);
el('device-policy').addEventListener('change', setDevicePolicy);
el('tasks-refresh').addEventListener('click', refreshTasks);
el('task-add').addEventListener('click', addTaskDialog);
el('pipeline-search').addEventListener('input', renderPipelines);
el('pipeline-new').addEventListener('click', async()=>{ const title = prompt('New pipeline draft title:'); if(!title) return; showModal('New pipeline draft', await api('/api/pipelines/draft', {title, stages:['intake','plan','review']})); });
el('modal-close').addEventListener('click', ()=>el('modal').classList.add('hidden'));
document.addEventListener('click', e=>{ if(!el('context-menu').contains(e.target)) el('context-menu').classList.add('hidden'); });
startup();
