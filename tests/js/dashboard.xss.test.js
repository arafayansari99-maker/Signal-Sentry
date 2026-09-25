/**
 * Security regression tests for the dashboard feed rendering.
 *
 * Runs the real app/static/dashboard.js in Node with a minimal DOM shim and
 * asserts that API-provided strings (competitor names, summaries, etc.) can
 * never inject markup into the digest feed. Execute with: node --test tests/js/
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// ---------------------------------------------------------------------------
// Minimal DOM shim: just enough of the Element API that dashboard.js uses.
// ---------------------------------------------------------------------------

function escapeText(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    // childNodes holds elements AND text nodes (real DOM semantics); `children`
    // is the element-only view used by selectors and the .children API.
    this.childNodes = [];
    this.attributes = {};
    this.listeners = {};
    this.disabled = false;
    this.value = '';
    this._textContent = '';
    this.className = '';
    this.title = '';
    // data-* attributes stay in `attributes` (dataset is a live view; used by
    // the custom-select widget's click handler).
    this.dataset = new Proxy({}, {
      get: (_t, prop) => this.attributes[`data-${String(prop).replace(/_/g, '-')}`],
      set: (_t, prop, val) => { this.attributes[`data-${String(prop).replace(/_/g, '-')}`] = String(val); return true; },
    });
    this.type = '';
    this.parentElement = null;
    this.style = {};
  }

  get children() {
    return this.childNodes.filter((node) => node.nodeType !== 3);
  }

  set className(value) { this._className = String(value); this.attributes.class = String(value); }
  get className() { return this._className || ''; }

  set textContent(value) {
    // Mirrors the real DOM: assigning textContent replaces children with one
    // text node, so markup in the string can never become elements.
    this._textContent = value == null ? '' : String(value);
    this.childNodes = [];
  }

  get textContent() {
    // Real DOM: textContent concatenates all descendant text.
    if (this.childNodes.length === 0) return this._textContent || '';
    return this.childNodes.map((node) => node.textContent).join('');
  }

  // Mirrors the real DOM: reading innerHTML serializes with escaping; writing
  // it replaces all children (we don't parse HTML, which the feed never needs).
  get innerHTML() {
    if (this.childNodes.length === 0) return escapeText(this._textContent);
    return this.childNodes
      .map((child) => (child.nodeType === 3 ? escapeText(child.textContent) : child.outerHTML))
      .join('');
  }

  set innerHTML(value) {
    this.childNodes = [];
    this._textContent = '';
    this._innerHTMLRaw = String(value);
    // Parse the HTML subset the app's innerHTML writes use: nested
    // <tag attr="value"> elements with plain text between them. Good enough
    // for dashboard.js's select options, mini-cards, and queue job rows; the
    // feed's complex content is built through DOM APIs and never parsed here.
    const stack = [this];
    const tokenPattern = /<(\/?)([a-z]+)([^>]*)>|([^<]+)/gi;
    let token;
    while ((token = tokenPattern.exec(String(value))) !== null) {
      const [full, closing, tagName, attrText, text] = token;
      const top = stack[stack.length - 1];
      if (text !== undefined) {
        if (text.trim()) top.appendChild(new FakeTextNode(text));
        continue;
      }
      if (closing) {
        if (stack.length > 1) stack.pop();
        continue;
      }
      const element = new FakeElement(tagName);
      const attrPattern = /([a-z-]+)="([^"]*)"/gi;
      let attrMatch;
      while ((attrMatch = attrPattern.exec(attrText || '')) !== null) {
        const [, name, attrValue] = attrMatch;
        element.attributes[name] = attrValue;
        if (name === 'class') element._className = attrValue;
      }
      element.parentElement = top;
      top.childNodes.push(element);
      stack.push(element);
    }
  }

  get outerHTML() {
    const attrs = Object.entries(this.attributes)
      .map(([name, val]) => ` ${name}="${escapeText(val)}"`)
      .join('');
    const inner = this.childNodes.length
      ? this.childNodes.map((child) => (child.nodeType === 3 ? escapeText(child.textContent) : child.outerHTML)).join('')
      : escapeText(this._textContent);
    return `<${this.tagName.toLowerCase()}${attrs}>${inner}</${this.tagName.toLowerCase()}>`;
  }

  appendChild(child) {
    child.parentElement = this;
    this.childNodes.push(child);
    return child;
  }

  append(...nodes) { nodes.forEach((n) => this.appendChild(n)); }

  // Mirrors the real DOM: replaces all children with the given nodes.
  replaceChildren(...nodes) {
    this.childNodes = [];
    this._textContent = '';
    nodes.forEach((node) => this.appendChild(node));
  }

  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }

  addEventListener(event, handler) {
    (this.listeners[event] = this.listeners[event] || []).push(handler);
  }

  get classList() {
    const element = this;
    return {
      contains(name) { return element.className.split(/\s+/).includes(name); },
      add(name) {
        const parts = element.className.split(/\s+/).filter(Boolean);
        if (!parts.includes(name)) element.className = [...parts, name].join(' ');
      },
      remove(name) {
        element.className = element.className.split(/\s+/).filter((part) => part && part !== name).join(' ');
      },
      toggle(name, force) {
        const has = this.contains(name);
        const want = force === undefined ? !has : force;
        if (want && !has) this.add(name);
        if (!want && has) this.remove(name);
        return want;
      },
    };
  }

  click() {
    (this.listeners.click || []).forEach((handler) => handler({ preventDefault() {} }));
  }

  focus() { this.focused = true; }

  // Mirrors the real DOM: walks ancestors (inclusive) for the first match.
  closest(selector) {
    let node = this;
    while (node) {
      if (node.nodeType !== 3 && matchesSelector(node, selector)) return node;
      node = node.parentElement;
    }
    return null;
  }

  dispatchEvent(event) {
    (this.listeners[event.type] || []).forEach((handler) => handler(event));
    return true;
  }

  // Canvas 2D context stub — the trend chart draws no-ops in tests.
  getContext(kind) {
    if (kind !== '2d') return null;
    return new Proxy(
      { canvas: this },
      {
        get: (target, prop) => {
          if (prop in target) return target[prop];
          return () => undefined; // every ctx method (clearRect, beginPath, …) is a no-op
        },
        set: () => true, // ctx.lineWidth = … etc.
      },
    );
  }

  remove() {
    if (this.parentElement) {
      const siblings = this.parentElement.childNodes;
      const index = siblings.indexOf(this);
      if (index >= 0) siblings.splice(index, 1);
    }
  }

  // Recursively collect all descendant elements matching a selector subset.
  querySelectorAll(selector) {
    const matches = [];
    const walk = (node) => {
      (node.childNodes || []).forEach((child) => {
        if (child.nodeType !== 3) {
          if (matchesSelector(child, selector)) matches.push(child);
          walk(child);
        }
      });
    };
    walk(this);
    return matches;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

function matchesSimpleSelector(element, selector) {
  // One compound selector: "tag#id.class[attr=value]" pieces.
  const match = selector.match(/^([a-z]*)(?:#([\w-]+))?(?:\.([\w-]+))*(?:\[([a-z-]+)(?:="([^"]*)")?\])?$/i);
  if (!match) return false;
  const [, tag, id, className, attrName, attrValue] = match;
  if (tag && element.tagName !== tag.toUpperCase()) return false;
  if (id && element.attributes.id !== id) return false;
  if (className && !element.className.split(/\s+/).includes(className)) return false;
  if (attrName && element.attributes[attrName] !== attrValue) return false;
  return true;
}

function matchesSelector(element, selector) {
  // Supports compound selectors joined by descendant combinators ("#a .b") and
  // comma groups — the shapes dashboard.js and the tests use. Splitting on
  // whitespace ignores spaces inside [attr="value with spaces"] brackets.
  return selector.split(',').some((part) => {
    const compounds = [];
    let depth = 0;
    let current = '';
    for (const ch of part.trim()) {
      if (ch === '[') depth += 1;
      if (ch === ']') depth -= 1;
      if (/\s/.test(ch) && depth === 0) {
        if (current) compounds.push(current);
        current = '';
      } else {
        current += ch;
      }
    }
    if (current) compounds.push(current);
    if (compounds.length === 0) return false;

    const matchesFrom = (node, index) => {
      // CSS descendant semantics: the LAST compound matches the node itself,
      // earlier compounds must match some ancestor chain (walking upward).
      if (!matchesSimpleSelector(node, compounds[index])) return false;
      if (index === 0) return true;
      let ancestor = node.parentElement;
      while (ancestor) {
        if (matchesFrom(ancestor, index - 1)) return true;
        ancestor = ancestor.parentElement;
      }
      return false;
    };

    return matchesFrom(element, compounds.length - 1);

    return matchesFrom(element, 0);
  });
}

class FakeTextNode {
  constructor(data) {
    this.nodeType = 3;
    this.textContent = String(data);
    this.children = [];
  }
}

class FakeDocument extends FakeElement {
  constructor() {
    super('#document');
    this.elements = new Map();
    this.body = new FakeElement('body');
    this.appendChild(this.body); // so document-level traversal reaches the body tree
    this.register = (id, element) => { this.elements.set(id, element); return element; };
  }

  getElementById(id) {
    if (!this.elements.has(id)) this.register(id, new FakeElement('div'));
    return this.elements.get(id);
  }

  createElement(tag) { return new FakeElement(tag); }

  createTextNode(data) { return new FakeTextNode(data); }

  // Route dispatched events into this element's own listeners (the shim's
  // document-level keydown handler is registered through addEventListener).
  dispatchEvent(event) {
    (this.listeners[event.type] || []).forEach((handler) => handler(event));
    return true;
  }
}

// ---------------------------------------------------------------------------
// Load and execute the real dashboard.js inside a sandbox with the shim.
// ---------------------------------------------------------------------------

function loadDashboard({
  digestPayload = { digest_items: [] },
  competitorsPayload = [],
  metricsPayload = { total_competitors: 0, recent_change_items_7d: 0, coverage_percent: 0, change_items_by_category: { pricing: 0, product: 0, hiring: 0 }, trend: [] },
  workerPayload = { running: false, jobs: [] },
  queuePayload = { jobs: [], queued: 0, started: 0, failed: 0 },
  evidencePayloads = {},
  fetchErrorUrls = [],
  routeOverrides = {},
} = {}) {
  const document = new FakeDocument();

  // Pre-build the static dashboard skeleton the real template renders, so
  // getElementById returns a connected tree (like the real DOM) rather than
  // disconnected islands. Every element dashboard.js touches by id.
  const skeleton = {};
  const skeletonIds = [
    'digest-feed', 'evidence-overlay', 'evidence-title', 'evidence-meta',
    'evidence-body', 'evidence-close', 'competitor-form', 'tracked-url-form',
    'competitor-select', 'competitor-cards', 'run-cycle-btn', 'worker-status',
    'queue-queued', 'queue-started', 'queue-failed', 'queue-monitor',
    'metric-competitors', 'metric-alerts', 'metric-coverage',
    'metric-pricing', 'metric-product', 'metric-hiring',
    'toast-root', // showToast() no-ops without this container
  ];
  for (const id of skeletonIds) {
    // #competitor-select must be an <input type=hidden> to match the widget
    // markup (loadCompetitors queries 'input[type="hidden"]' inside it).
    const tag = id === 'run-cycle-btn' || id === 'evidence-close' ? 'button'
      : id === 'competitor-select' ? 'input' : 'div';
    const el = document.createElement(tag);
    el.attributes.id = id;
    if (id === 'competitor-select') {
      el.attributes.type = 'hidden';
      el.attributes.name = 'competitor_id';
    }
    skeleton[id] = el;
    document.register(id, el);
  }

  // Mirror the real template's nesting: evidence-* ids live inside the
  // overlay panel; #competitor-select is the hidden input inside the
  // custom-select widget (trigger + listbox menu), as in dashboard.html.
  const overlayEl = skeleton['evidence-overlay'];
  const panelEl = document.createElement('div');
  panelEl.className = 'evidence-panel';
  panelEl.append(skeleton['evidence-title'], skeleton['evidence-meta'], skeleton['evidence-body'], skeleton['evidence-close']);
  overlayEl.appendChild(panelEl);
  document.body.appendChild(overlayEl);

  for (const id of skeletonIds.filter((id) => !id.startsWith('evidence-'))) {
    document.body.appendChild(skeleton[id]);
  }

  const selectWidget = document.createElement('div');
  selectWidget.className = 'custom-select';
  selectWidget.attributes['data-name'] = 'competitor_id';
  const trigger = document.createElement('button');
  trigger.className = 'custom-select-trigger';
  trigger.setAttribute('aria-expanded', 'false');
  const selectLabel = document.createElement('span');
  selectLabel.className = 'custom-select-label';
  selectLabel.textContent = 'Select competitor';
  trigger.appendChild(selectLabel);
  const menu = document.createElement('ul');
  menu.className = 'custom-select-menu';
  menu.setAttribute('role', 'listbox');
  menu.setAttribute('aria-label', 'Competitor select');
  const placeholderOption = document.createElement('li');
  placeholderOption.className = 'custom-select-option is-selected';
  placeholderOption.setAttribute('data-value', '');
  placeholderOption.textContent = 'Select competitor';
  menu.appendChild(placeholderOption);
  selectWidget.append(trigger, menu, skeleton['competitor-select']);
  document.body.appendChild(selectWidget);

  // The trend chart is a canvas.
  const canvas = document.createElement('canvas');
  canvas.attributes.id = 'trend-chart';
  canvas.width = 400;
  canvas.height = 170;
  skeleton['trend-chart'] = canvas;
  document.body.appendChild(canvas);

  const fetchedUrls = [];

  const defaultRoutes = {
    '/digests/weekly': digestPayload,
    '/competitors': competitorsPayload,
    '/metrics/overview': metricsPayload,
    '/workers/status': workerPayload,
    '/workers/queue-status': queuePayload,
  };

  const fetchImpl = async (url, options) => {
    fetchedUrls.push({ url, options });
    if (typeof url === 'string' && url.startsWith('/change-items/') && url.endsWith('/evidence')) {
      const itemId = Number(url.match(/\/change-items\/(\d+)\/evidence/)?.[1]);
      if (fetchErrorUrls.includes(itemId)) {
        return { ok: false, status: 404, json: async () => ({ detail: 'Change item not found' }) };
      }
      const payload = evidencePayloads[itemId] ?? {
        change_item_id: itemId,
        status: 'shown',
        category: 'pricing',
        magnitude: 'major',
        summary: 'Price changed',
        why_it_matters: 'It matters',
        confidence: 0.9,
        competitor: { id: 1, name: 'Acme', domain: 'acme.demo' },
        tracked_url: { id: 1, url: 'https://acme.demo/pricing', page_type: 'pricing' },
        diff: { id: 1, material_change: true, stage1_score: 1.0, changed_tokens: ['$49/month', '$39/month'] },
        before: {
          snapshot_id: 10,
          fetched_at: '2026-09-18T09:00:00',
          text_content: 'Team $49/month',
          screenshot_url: null,
        },
        after: {
          snapshot_id: 11,
          fetched_at: '2026-09-24T09:00:00',
          text_content: 'Team $39/month',
          screenshot_url: null,
        },
      };
      return { ok: true, json: async () => payload };
    }
    if (routeOverrides[url] !== undefined) {
      const override = routeOverrides[url];
      if (override.error) {
        return { ok: false, status: override.status || 500, json: async () => ({ detail: override.detail || 'Server error' }) };
      }
      return { ok: true, json: async () => (typeof override === 'function' ? override(fetchedUrls) : override) };
    }
    if (defaultRoutes[url] !== undefined) {
      return { ok: true, json: async () => defaultRoutes[url] };
    }
    // Unmapped route (e.g. feedback/run-cycle POSTs with no override): empty ok.
    return { ok: true, json: async () => ({}) };
  };

  const localStorageShim = {
    store: {},
    getItem(key) { return this.store[key] ?? null; },
    setItem(key, value) { this.store[key] = String(value); },
  };

  const sandbox = {
    document,
    fetch: fetchImpl,
    localStorage: localStorageShim,
    setInterval: () => 0,
    clearInterval: () => {},
    setTimeout: () => 0,
    window: { addEventListener: () => {} },
    KeyboardEvent: class KeyboardEvent { constructor(type, init) { this.type = type; this.key = init?.key; } },
    MouseEvent: class MouseEvent { constructor(type, init) { this.type = type; this.target = init?.target; } },
    console,
  };
  sandbox.globalThis = sandbox;
  // Expose the fetch routing table so tests can re-route endpoints mid-test
  // (same object the fetchImpl closure reads).
  sandbox.routeOverrides = routeOverrides;

  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'app', 'static', 'dashboard.js'),
    'utf8',
  );
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: 'dashboard.js' });

  return {
    document,
    fetchedUrls,
    // Drain every async loader the module kicks off on boot.
    settle: () => vm.runInContext(
      'Promise.all([loadCompetitors(), loadDigest(), loadWorkerStatus(), loadQueueStatus(), loadMetrics()]).then(() => undefined)',
      sandbox,
    ),
    run: (expression) => vm.runInContext(expression, sandbox),
    sandbox,
  };
}

const PAYLOAD = {
  digest_id: 7,
  digest_items: [
    {
      rank: 1,
      change_item_id: 11,
      competitor_name: '<img src=x onerror=window.__pwned=1>',
      url: 'https://evil.example.com',
      category: 'pricing',
      summary: '<script>window.__pwned=2</script>Cut pricing to $39',
      confidence: 0.93,
    },
    {
      rank: 2,
      change_item_id: 12,
      competitor_name: 'Innocent Co',
      url: 'https://ok.example.com',
      category: 'product">"',
      summary: '"><svg onload=window.__pwned=3>',
      confidence: 0.5,
    },
  ],
};

test('digest feed renders competitor names and summaries as text, not markup', async () => {
  const app = loadDashboard({ digestPayload: PAYLOAD });
  await app.settle();

  const container = app.document.getElementById('digest-feed');
  const rows = container.querySelectorAll('.alert-item');
  assert.equal(rows.length, 2, 'renders one row per digest item');

  const firstRow = rows[0];
  const title = firstRow.querySelector('.alert-title');
  const text = firstRow.querySelector('.alert-text');

  // The malicious strings must survive verbatim as text...
  assert.equal(title.textContent, '<img src=x onerror=window.__pwned=1>');
  assert.ok(text.textContent.includes('<script>window.__pwned=2</script>'));
  assert.ok(text.textContent.includes('Cut pricing to $39'));

  // ...and must not have produced any element children inside title/text nodes.
  assert.equal(title.children.length, 0, 'no elements inside title');
  assert.equal(text.children.length, 0, 'no elements inside summary');

  // No img/svg/script elements anywhere in the feed.
  const dangerous = container.querySelectorAll('img,svg,script,iframe');
  assert.equal(dangerous.length, 0, `found dangerous elements: ${dangerous.map((el) => el.tagName).join(', ')}`);
});

test('evidence panel highlights changed tokens inline without allowing injection', async () => {
  const app = loadDashboard({ digestPayload: { digest_items: [] } });
  const sandbox = app.sandbox;

  const container = sandbox.document.createElement('div');
  const maliciousText = '<img src=x> Team $49/month · <script>alert(1)</script> plan';
  const tokens = ['$49/month', '<script>alert(1)</script>', '<img src=x>'];

  sandbox.paintEvidenceText(container, maliciousText, tokens, 'removed');

  // Tokens and hostile text are highlighted as mark/text nodes, never parsed.
  const marks = container.querySelectorAll('mark');
  const markTexts = marks.map((m) => m.textContent);
  assert.ok(markTexts.includes('<img src=x>'), 'hostile token highlighted as inert text inside mark');
  assert.ok(markTexts.includes('$49/month'), 'legit token highlighted');
  assert.ok(markTexts.includes('<script>alert(1)</script>'), 'script token highlighted as inert text');

  // Every mark contains only a text node — nothing parsed.
  for (const mark of marks) {
    assert.equal(mark.children.length, 0, 'mark has no element children');
  }

  // No element anywhere in the container parses the hostile strings.
  const dangerous = container.querySelectorAll('img,svg,script,iframe');
  assert.equal(dangerous.length, 0, 'no dangerous elements created');

  // Full text content preserved (order intact).
  const full = container.textContent;
  assert.ok(full.includes('$49/month'));
  assert.ok(full.includes('<img src=x>'));
  assert.ok(full.includes('Team '));
});

test('paintEvidenceText with no tokens falls back to plain text', () => {
  const app = loadDashboard({ digestPayload: { digest_items: [] } });
  const sandbox = app.sandbox;
  const container = sandbox.document.createElement('div');
  sandbox.paintEvidenceText(container, 'Plain $19 text', [], 'added');
  assert.equal(container.children.length, 0);
  assert.equal(container.textContent, 'Plain $19 text');
});

test('malicious category strings cannot break out of class or tag attributes', async () => {
  const app = loadDashboard({ digestPayload: PAYLOAD });
  await app.settle();

  const container = app.document.getElementById('digest-feed');
  const rows = container.querySelectorAll('.alert-item');

  // Category is interpolated into className; a hostile value stays inert data.
  const secondRow = rows[1];
  assert.ok(secondRow.className.startsWith('alert-item'));
  assert.equal(secondRow.querySelectorAll('svg').length, 0, 'no svg injected via category');
  assert.equal(secondRow.querySelector('.alert-tag').textContent, 'product">"');
});

test('feedback buttons are wired to the correct change item ids', async () => {
  const app = loadDashboard({ digestPayload: PAYLOAD });
  await app.settle();

  const container = app.document.getElementById('digest-feed');
  const rows = container.querySelectorAll('.alert-item');
  assert.equal(rows[0].querySelectorAll('.feedback-btn').length, 2);

  rows[0].querySelector('.feedback-btn[aria-label="Mark not relevant"]').click();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const post = app.fetchedUrls.find((call) => String(call.url).includes('/feedback'));
  assert.ok(post, 'feedback POST issued');
  assert.equal(post.url, '/change-items/11/feedback');
  assert.equal(post.options.method, 'POST');
  assert.deepEqual(JSON.parse(post.options.body), { label: 'not_relevant' });
});

test('escapeHtml escapes angle brackets and quotes', async () => {
  const app = loadDashboard({ digestPayload: { digest_items: [] } });
  const escaped = app.sandbox.escapeHtml('<img src=x onerror="alert(1)">');
  assert.ok(!escaped.includes('<img'), 'angle bracket escaped');
  assert.ok(escaped.includes('&lt;img'), 'uses HTML entity');
  assert.ok(!escaped.includes('onerror="'), 'raw double quote escaped');
});

// ---------------------------------------------------------------------------
// Evidence modal end-to-end: open, paint, close, and error paths.
// ---------------------------------------------------------------------------

const EVIDENCE_ID = 42;

test('evidence modal opens, paints both sides, and closes via Escape/backdrop', async () => {
  const app = loadDashboard({
    digestPayload: { digest_items: [{ change_item_id: EVIDENCE_ID, competitor_name: 'Acme', category: 'pricing', summary: 'Price changed' }] },
  });
  await app.settle();

  // Open by clicking the row's Evidence button, as a user would.
  const button = app.document.getElementById('digest-feed').querySelector('.evidence-btn');
  assert.ok(button, 'evidence button rendered in digest row');
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const overlay = app.document.getElementById('evidence-overlay');
  const state = () => app.run(
    `JSON.stringify({ open: document.getElementById('evidence-overlay').classList.contains('open'), hidden: document.getElementById('evidence-overlay').hidden, bodyOverflow: document.body.style.overflow })`
  );
  let parsed = JSON.parse(state());
  assert.equal(parsed.open, true, 'overlay opens');
  assert.equal(parsed.hidden, false, 'overlay un-hidden');
  assert.equal(parsed.bodyOverflow, 'hidden', 'background scroll locked');

  const title = app.run(`document.getElementById('evidence-title').textContent`);
  assert.equal(title, 'Acme — https://acme.demo/pricing');

  const colTitles = JSON.parse(app.run(
    `JSON.stringify([...document.querySelectorAll('#evidence-overlay .evidence-col-title')].map((n) => n.textContent))`
  ));
  assert.deepEqual(colTitles, ['Before', 'After']);

  const texts = JSON.parse(app.run(
    `JSON.stringify([...document.querySelectorAll('#evidence-overlay .evidence-text')].map((n) => n.textContent))`
  ));
  assert.ok(texts[0].includes('$49/month'), 'before text painted');
  assert.ok(texts[1].includes('$39/month'), 'after text painted');

  const marks = JSON.parse(app.run(
    `JSON.stringify([...document.querySelectorAll('#evidence-overlay mark.evidence-mark')].map((m) => m.textContent))`
  ));
  // Before text only contains $49/month; after only $39/month — one highlight each.
  assert.deepEqual(marks, ['$49/month', '$39/month'], 'tokens highlighted in their respective columns');

  assert.ok(app.fetchedUrls.some((call) => call.url === `/change-items/${EVIDENCE_ID}/evidence`), 'evidence endpoint fetched');

  // Close via Escape key.
  app.run(
    `document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`
  );
  parsed = JSON.parse(state());
  assert.equal(parsed.open, false, 'Escape closes overlay');
  assert.equal(parsed.hidden, true, 'overlay hidden after Escape');
  assert.equal(parsed.bodyOverflow, '', 'scroll unlocked after Escape');

  // Reopen and close via backdrop click (event.target === overlay itself).
  button.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(JSON.parse(state()).open, true, 'overlay reopens');
  app.run(
    `(() => { const overlay = document.getElementById('evidence-overlay'); overlay.dispatchEvent({ type: 'click', target: overlay, currentTarget: overlay, bubbles: true }); })()`
  );
  parsed = JSON.parse(state());
  assert.equal(parsed.open, false, 'backdrop click closes overlay');
});

test('evidence modal shows error message when the endpoint fails', async () => {
  const app = loadDashboard({
    digestPayload: { digest_items: [{ change_item_id: EVIDENCE_ID, competitor_name: 'Acme', category: 'pricing', summary: 'Price changed' }] },
    fetchErrorUrls: [EVIDENCE_ID],
  });
  await app.settle();

  app.document.getElementById('digest-feed').querySelector('.evidence-btn').click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const bodyText = app.run(`document.getElementById('evidence-body').textContent`);
  assert.ok(bodyText.includes('Change item not found'), 'server detail surfaced in panel');

  const overlay = app.run(
    `document.getElementById('evidence-overlay').classList.contains('open')`
  );
  assert.equal(overlay, true, 'panel stays open so the user can see the error');

  // No evidence columns were painted on the error path.
  const columns = app.run(`document.querySelectorAll('#evidence-overlay .evidence-col').length`);
  assert.equal(columns, 0, 'no partial content painted');
});

test('full dashboard load pipeline wires seeded API payloads into every panel', async () => {
  const SEEDED_COMPETITORS = [
    { id: 1, name: 'Nimbus Analytics', domain: 'nimbus-analytics.demo', status: 'active' },
    { id: 2, name: 'Vector Metrics', domain: 'vector-metrics.demo', status: 'active' },
    { id: 3, name: 'Harbor Cloud', domain: 'harbor-cloud.demo', status: 'active' },
    { id: 4, name: 'Quiet Loop', domain: 'quiet-loop.demo', status: 'paused' },
  ];
  const SEEDED_DIGEST = {
    digest_id: 9,
    digest_items: [
      { rank: 1, change_item_id: 21, competitor_name: 'Nimbus Analytics', category: 'pricing', summary: 'Team plan cut to $39', confidence: 0.92 },
      { rank: 2, change_item_id: 22, competitor_name: 'Vector Metrics', category: 'hiring', summary: 'Doubled engineering openings', confidence: 0.68 },
    ],
  };
  const SEEDED_METRICS = {
    total_competitors: 4,
    total_tracked_urls: 7,
    active_tracked_urls: 7,
    coverage_percent: 100,
    recent_change_items_7d: 4,
    change_items_by_category: { pricing: 2, product: 1, hiring: 1 },
    trend: [
      { date: '2026-09-14', material_changes: 0 },
      { date: '2026-09-15', material_changes: 0 },
      { date: '2026-09-16', material_changes: 3 },
    ],
  };

  const app = loadDashboard({
    digestPayload: SEEDED_DIGEST,
    competitorsPayload: SEEDED_COMPETITORS,
    metricsPayload: SEEDED_METRICS,
    workerPayload: { running: true, jobs: [{ id: 'monitoring_cycle', name: 'Run monitoring cycle', next_run_time: '2026-09-26T09:00:00' }] },
    queuePayload: { queued: 2, started: 1, failed: 0, jobs: [{ id: 'job_77', status: 'queued', description: 'monitoring cycle' }] },
  });
  await app.settle();

  const q = (selector) => JSON.parse(app.run(
    `JSON.stringify([...document.querySelectorAll('${selector}')].map((n) => n.textContent))`
  ));
  const text = (id) => app.run(`document.getElementById('${id}').textContent`);

  // --- Metrics cards -------------------------------------------------------
  assert.equal(text('metric-competitors'), '4');
  assert.equal(text('metric-alerts'), '4');
  assert.equal(text('metric-coverage'), '100%');
  assert.equal(text('metric-pricing'), '2');
  assert.equal(text('metric-product'), '1');
  assert.equal(text('metric-hiring'), '1');

  // --- Competitor select + tracked accounts --------------------------------
  // The picker is the custom-select widget: one <li data-value> option per
  // competitor plus the placeholder, and the hidden input stores the choice.
  assert.equal(
    app.run("document.querySelectorAll('.custom-select[data-name=\"competitor_id\"] .custom-select-option').length"),
    SEEDED_COMPETITORS.length + 1,
    'picker has one option per competitor plus the placeholder',
  );
  const miniTitles = q('#competitor-cards .mini-title');
  assert.deepEqual(miniTitles, SEEDED_COMPETITORS.map((c) => c.name), 'all competitors listed (no slice loss at 4)');
  assert.ok(q('#competitor-cards .status-pill').includes('paused'), 'paused status rendered');

  // --- Digest feed rows + feedback/evidence wiring --------------------------
  const alertTitles = q('#digest-feed .alert-title');
  assert.deepEqual(alertTitles, SEEDED_DIGEST.digest_items.map((i) => i.competitor_name));
  assert.equal(app.run("document.querySelectorAll('#digest-feed .feedback-btn').length"), 4);
  assert.equal(app.run("document.querySelectorAll('#digest-feed .evidence-btn').length"), 2);

  // --- Worker + queue panels -----------------------------------------------
  assert.equal(text('worker-status'), 'Live scheduler');
  assert.equal(text('queue-queued'), '2');
  assert.equal(text('queue-started'), '1');
  assert.equal(text('queue-failed'), '0');
  const jobTitles = q('#queue-monitor .alert-title');
  assert.deepEqual(jobTitles, ['job_77']);

  // --- Boot fetched all five endpoints ------------------------------------
  for (const route of ['/competitors', '/digests/weekly', '/workers/status', '/workers/queue-status', '/metrics/overview']) {
    assert.ok(app.fetchedUrls.some((call) => call.url === route), `boot fetched ${route}`);
  }

  // --- Run cycle: button state, toast, and post-cycle refreshes ------------
  app.run(
    `routeOverrides['/workers/run-cycle'] = {
      processed_competitors: 3,
      material_changes: 1,
      diff_ids: [91],
      alerts_sent: 0,
      last_alert: '[DEVELOPMENT] SignalSentry alert\\nCompetitor: Nimbus',
      failed_fetches: [{ tracked_url_id: 5, url: 'https://down.demo/pricing', reason: 'page unreachable' }],
    }`
  );
  app.run("document.getElementById('run-cycle-btn').click()");
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const cycleToast = app.run(
    `(() => { const t = document.querySelector('.toast'); return t ? JSON.stringify({ title: t.querySelector('.toast-title').textContent, stats: [...t.querySelectorAll('.toast-stat')].map(s => s.textContent), body: t.querySelector('.toast-body').textContent }) : null; })()`
  );
  const toast = JSON.parse(cycleToast);
  assert.equal(toast.title, 'Monitoring cycle complete');
  assert.ok(toast.stats.includes('processed: 3'));
  assert.ok(toast.stats.includes('material: 1'));
  assert.ok(toast.stats.includes('fetches skipped: 1'), 'skipped-fetch chip present');
  assert.ok(toast.body.includes('Nimbus'), 'last_alert surfaced in toast body');
  assert.equal(app.run("document.getElementById('run-cycle-btn').textContent"), 'Run cycle', 'button restored after cycle');

  // Post-cycle refreshes hit digest/queue/metrics again.
  const urlsAfterCycle = app.fetchedUrls.map((call) => call.url);
  for (const route of ['/digests/weekly', '/workers/queue-status', '/metrics/overview']) {
    assert.ok(urlsAfterCycle.filter((u) => u === route).length >= 2, `${route} refetched after cycle`);
  }
});

test('dashboard boot survives an API outage with graceful empty states', async () => {
  const app = loadDashboard({
    competitorsPayload: [],
    digestPayload: { digest_items: [] },
    workerPayload: { running: false, jobs: [] },
    queuePayload: { queued: 0, started: 0, failed: 0, jobs: [] },
  });
  await app.settle();

  assert.equal(app.run("document.getElementById('metric-competitors').textContent"), '0');
  assert.equal(app.run("document.getElementById('metric-coverage').textContent"), '0%');
  assert.equal(app.run("document.getElementById('worker-status').textContent"), 'Idle');
  assert.ok(
    app.run("document.getElementById('digest-feed').textContent").includes('No material changes detected this cycle.'),
    'digest feed shows its empty state',
  );
  assert.equal(app.run("document.querySelectorAll('#digest-feed .feedback-btn').length"), 0, 'no feedback buttons without items');
});

test('evidence modal paints baseline note when before snapshot is missing', async () => {
  const app = loadDashboard({
    digestPayload: { digest_items: [{ change_item_id: EVIDENCE_ID, competitor_name: 'Acme', category: 'product', summary: 'Baseline' }] },
    evidencePayloads: {
      [EVIDENCE_ID]: {
        change_item_id: EVIDENCE_ID,
        status: 'pending',
        category: 'product',
        magnitude: 'minor',
        summary: 'Baseline',
        why_it_matters: 'n/a',
        confidence: 0.0,
        competitor: { id: 1, name: 'Acme', domain: 'acme.demo' },
        tracked_url: { id: 1, url: 'https://acme.demo/pricing', page_type: 'pricing' },
        diff: { id: 1, material_change: false, stage1_score: 0.0, changed_tokens: [] },
        before: null,
        after: { snapshot_id: 11, fetched_at: '2026-09-24T09:00:00', text_content: 'First look', screenshot_url: null },
      },
    },
  });
  await app.settle();

  app.document.getElementById('digest-feed').querySelector('.evidence-btn').click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const bodyText = app.run(`document.getElementById('evidence-body').textContent`);
  assert.ok(bodyText.includes('No before-snapshot exists'), 'baseline note shown');

  const colTitles = JSON.parse(app.run(
    `JSON.stringify([...document.querySelectorAll('#evidence-overlay .evidence-col-title')].map((n) => n.textContent))`
  ));
  assert.deepEqual(colTitles, ['After'], 'only the After column renders');

  const marks = app.run(`document.querySelectorAll('#evidence-overlay mark.evidence-mark').length`);
  assert.equal(marks, 0, 'no highlights without tokens');
});

test('dashboard.js never assigns to HTML-injection sinks (regression guard)', () => {
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'app', 'static', 'dashboard.js'),
    'utf8',
  );
  // Strip the one sanctioned innerHTML *read* inside escapeHtml, then demand
  // zero sinks anywhere else: all dynamic content must go through DOM APIs.
  const withoutEscapeHtml = source.replace(/function escapeHtml[\s\S]*?\n}/, '');
  assert.doesNotMatch(withoutEscapeHtml, /\.innerHTML\s*=/, 'no innerHTML assignments');
  assert.doesNotMatch(withoutEscapeHtml, /\.outerHTML\s*=/, 'no outerHTML assignments');
  assert.doesNotMatch(withoutEscapeHtml, /insertAdjacentHTML/, 'no insertAdjacentHTML');
  assert.doesNotMatch(withoutEscapeHtml, /document\.write/, 'no document.write');
});
