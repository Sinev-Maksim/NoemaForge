const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class FakeText {
  constructor(text) { this.tagName = '#TEXT'; this.textContent = String(text); this.children = []; }
}

class FakeElement {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.className = '';
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.style = {};
    this._text = '';
    this.classList = {
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...names])].join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter((name) => name && !names.includes(name)).join(' '); },
      contains: (name) => this.className.split(/\s+/).includes(name),
      toggle: (name, force) => {
        const enabled = force === undefined ? !this.classList.contains(name) : Boolean(force);
        if (enabled) this.classList.add(name);
        else this.classList.remove(name);
        return enabled;
      },
    };
  }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this._text = String(value ?? ''); this.children = []; }
  append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
  appendChild(node) { this.children.push(typeof node === 'string' ? new FakeText(node) : node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = []; this.append(...nodes); }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null; }
  contains(target) { return target === this || this.children.some((child) => child.contains?.(target)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    const matches = (node) => {
      if (!(node instanceof FakeElement)) return false;
      if (selector.startsWith('#')) return node.id === selector.slice(1);
      if (selector.startsWith('.')) return node.className.split(/\s+/).includes(selector.slice(1));
      if (selector.startsWith('[data-')) {
        const key = selector.slice(6, -1).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        return Object.hasOwn(node.dataset, key);
      }
      return node.tagName === selector.toUpperCase();
    };
    const found = [];
    const visit = (node) => {
      if (matches(node)) found.push(node);
      (node.children || []).forEach(visit);
    };
    this.children.forEach(visit);
    return found;
  }
}

class FakeDocument {
  constructor(ids = []) {
    this.nodes = Object.fromEntries(ids.map((id) => [id, new FakeElement()]));
    this.listeners = {};
  }
  getElementById(id) { return this.nodes[id] ||= new FakeElement(); }
  createElement(tag) { return new FakeElement(tag); }
  createTextNode(text) { return new FakeText(text); }
  querySelectorAll(selector) { return Object.values(this.nodes).flatMap((node) => node.querySelectorAll(selector)); }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
}

function loadScript(relativePath, ids, extras = {}) {
  const document = new FakeDocument(ids);
  const context = vm.createContext({console, document, navigator: {}, URL, ...extras});
  const source = fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf8');
  vm.runInContext(source, context, {filename: relativePath});
  return {context, document};
}

function loadScriptWithWindow(relativePath, ids, extras = {}) {
  const document = new FakeDocument(ids);
  const windowListeners = {};
  const window = {
    document,
    location: {origin: 'http://localhost'},
    addEventListener: (type, listener) => { (windowListeners[type] ||= []).push(listener); },
  };
  const context = vm.createContext({
    console,
    document,
    window,
    navigator: {},
    URL,
    fetch: async () => ({ok: true, text: async () => '{}'}),
    setInterval: () => 1,
    clearInterval: () => {},
    ...extras,
  });
  const source = fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf8');
  vm.runInContext(source, context, {filename: relativePath});
  return {context, document, window, windowListeners};
}

function executableTags(root) {
  return ['SCRIPT', 'IMG', 'SVG', 'IFRAME'].flatMap((tag) => root.querySelectorAll(tag));
}

test('pipeline dashboard renders API text literally and rejects active artifact URLs', () => {
  const {context, document} = loadScript('templates/pipeline-dashboard/app.js', ['chat-log', 'artifacts', 'job-summary', 'jobs']);
  context.payload = '<img src=x onerror=alert(1)>';
  vm.runInContext("addMessage(payload, payload)", context);
  const chat = document.getElementById('chat-log');
  assert.match(chat.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(executableTags(chat).length, 0);

  context.artifacts = [{
    label: context.payload,
    status: 'ready<script>alert(1)</script>',
    path: context.payload,
    download_url: 'javascript:alert(1)',
  }];
  vm.runInContext('renderArtifacts(artifacts)', context);
  const artifacts = document.getElementById('artifacts');
  assert.match(artifacts.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(executableTags(artifacts).length, 0);
  const link = artifacts.querySelector('a');
  assert.equal(link.getAttribute('href'), null);
  assert.equal(link.getAttribute('aria-disabled'), 'true');
  const actionButtons = artifacts.querySelectorAll('button');
  assert.ok(actionButtons.length > 0, 'expected artifact action buttons to render');
  assert.equal(actionButtons.every((button) => button.listeners.click?.length === 1), true);

  context.artifacts = [{label: 'safe', path: 'report.json', download_url: '/api/artifacts/download?path=report.json'}];
  vm.runInContext('renderArtifacts(artifacts)', context);
  const safeLink = artifacts.querySelector('a');
  assert.equal(safeLink.getAttribute('href'), '/api/artifacts/download?path=report.json');
  assert.equal(safeLink.getAttribute('download'), '');

  context.jobs = [{job_id: context.payload, kind: context.payload, status: 'running', command: context.payload}];
  vm.runInContext('renderJobs(jobs)', context);
  const jobs = document.getElementById('jobs');
  assert.equal(executableTags(jobs).length, 0);
  assert.match(jobs.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(jobs.querySelector('button').listeners.click.length, 1);
});

test('legacy UI dashboard renders snapshot fields as text nodes', async () => {
  const payload = '<svg onload=alert(1)>';
  const ids = ['statusText', 'statusDot', 'ts', 'nowKv', 'tqSummary', 'tqCurrent', 'tqNext', 'projectsList', 'eventsTable', 'telemetryTable', 'inboxSummary', 'inboxBlocks'];
  const snapshot = {
    generated_at: payload,
    runtime_state: {state: payload, note: payload},
    taskqueue: {db_path: payload, summary: {TODO: 1}, current: {task_id: payload, title: payload, domain: payload}, next: [{priority_class: payload, domain: payload, task_id: payload, title: payload}]},
    projects: {items: [{project_id: payload, title: payload, priority: payload, status: 'active', stream_id: payload, flow: {nodes: [{role: payload}]}, team: {wakeq: {pending: 0}}, backlog: {counts: {todo: 1}}}]},
    events: {recent: [{ts: payload, type: payload, severity: payload, decision: payload}]},
    telemetry: {recent_llm_calls: [{ts: payload, kind: payload, model: payload, latency_ms: payload}]},
    inboxes: {library: {available: true, total_files: 1, base_dir: payload, by_bucket: [{bucket: payload, files: 1}], recent: [{mtime: payload, path: payload, size: 1}]}, vault: null, workspace: null},
  };
  const {context, document} = loadScript('templates/ui-dashboard/app.js', ids, {
    fetch: async () => ({ok: true, json: async () => snapshot}),
  });
  await vm.runInContext('tick()', context);
  for (const id of ids) {
    const node = document.getElementById(id);
    assert.equal(executableTags(node).length, 0, `${id} created an executable element`);
  }
  assert.match(document.getElementById('projectsList').textContent, /<svg onload=alert\(1\)>/);
  assert.match(document.getElementById('eventsTable').textContent, /<svg onload=alert\(1\)>/);
  assert.match(document.getElementById('inboxBlocks').textContent, /<svg onload=alert\(1\)>/);
});

test('pipeline dashboard refresh cadence follows visibility and focus state', () => {
  const intervals = [];
  const cleared = [];
  const {context, document} = loadScript('templates/pipeline-dashboard/app.js', ['inactivity-status', 'inactivity'], {
    setInterval: (fn, ms) => {
      const id = intervals.length + 1;
      intervals.push({id, fn, ms});
      return id;
    },
    clearInterval: (id) => cleared.push(id),
  });

  document.hidden = false;
  document.visibilityState = 'visible';
  assert.equal(vm.runInContext('inactivityRefreshCadenceMs()', context), 1000);
  assert.equal(vm.runInContext('dashboardRefreshCadenceMs()', context), 10000);

  vm.runInContext('startInactivityRefreshTimer(); startDashboardRefreshTimer();', context);
  assert.deepEqual(intervals.map((item) => item.ms), [1000, 10000]);

  document.hidden = true;
  document.visibilityState = 'hidden';
  assert.equal(vm.runInContext('inactivityRefreshCadenceMs()', context), 30000);
  assert.equal(vm.runInContext('dashboardRefreshCadenceMs()', context), 30000);
  vm.runInContext('updateDashboardRefreshCadence();', context);
  assert.deepEqual(cleared, [1, 2]);
  assert.deepEqual(intervals.map((item) => item.ms), [1000, 10000, 30000, 30000]);

  document.hidden = false;
  document.visibilityState = 'visible';
  vm.runInContext('dashboardWindowFocused = false', context);
  assert.equal(vm.runInContext('dashboardIsBackgrounded()', context), true);
  assert.equal(vm.runInContext('inactivityRefreshCadenceMs()', context), 30000);
});

test('pipeline dashboard visibilitychange restores focused cadence when visible', () => {
  const intervals = [];
  const {context, document} = loadScriptWithWindow('templates/pipeline-dashboard/app.js', ['inactivity-status', 'inactivity'], {
    setInterval: (fn, ms) => {
      const id = intervals.length + 1;
      intervals.push({id, fn, ms});
      return id;
    },
  });

  assert.equal(document.listeners.visibilitychange.length, 1);
  document.hidden = false;
  document.visibilityState = 'visible';
  vm.runInContext('dashboardWindowFocused = false', context);
  assert.equal(vm.runInContext('dashboardIsBackgrounded()', context), true);

  document.listeners.visibilitychange[0]();

  assert.equal(vm.runInContext('dashboardIsBackgrounded()', context), false);
  assert.equal(vm.runInContext('inactivityRefreshCadenceMs()', context), 1000);
  assert.equal(vm.runInContext('dashboardRefreshCadenceMs()', context), 10000);
  assert.ok(intervals.some((item) => item.ms === 1000));
  assert.ok(intervals.some((item) => item.ms === 10000));
});
