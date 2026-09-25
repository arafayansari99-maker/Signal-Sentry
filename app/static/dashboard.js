const competitorForm = document.getElementById('competitor-form');
const trackedUrlForm = document.getElementById('tracked-url-form');
const competitorSelect = document.getElementById('competitor-select');
const dashboardGrid = document.getElementById('dashboard-grid');
const chartCanvas = document.getElementById('trend-chart');

let trendData = [];

function setupCustomSelect(container) {
  if (!container) return;

  const trigger = container.querySelector('.custom-select-trigger');
  const menu = container.querySelector('.custom-select-menu');
  const hiddenInput = container.querySelector('input[type="hidden"]');
  const label = container.querySelector('.custom-select-label');

  if (!trigger || !menu || !hiddenInput || !label) return;

  const closeMenu = () => {
    container.classList.remove('open');
    trigger.setAttribute('aria-expanded', 'false');
  };

  trigger.addEventListener('click', (event) => {
    event.stopPropagation();
    const isOpen = container.classList.contains('open');
    document.querySelectorAll('.custom-select').forEach((select) => {
      if (select !== container) {
        select.classList.remove('open');
        const btn = select.querySelector('.custom-select-trigger');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }
    });
    container.classList.toggle('open', !isOpen);
    trigger.setAttribute('aria-expanded', String(!isOpen));
  });

  menu.addEventListener('click', (event) => {
    const option = event.target.closest('.custom-select-option');
    if (!option) return;

    const selectedValue = option.dataset.value || '';
    const selectedText = option.textContent.trim();
    hiddenInput.value = selectedValue;
    label.textContent = selectedText;

    menu.querySelectorAll('.custom-select-option').forEach((item) => {
      item.classList.toggle('is-selected', item === option);
    });

    closeMenu();
  });

  document.addEventListener('click', (event) => {
    if (!container.contains(event.target)) {
      closeMenu();
    }
  });
}

function setupCustomSelects() {
  document.querySelectorAll('.custom-select').forEach(setupCustomSelect);
}

function drawTrendChart() {
  if (!chartCanvas) return;
  const ctx = chartCanvas.getContext('2d');
  const { width, height } = chartCanvas;
  ctx.clearRect(0, 0, width, height);

  const padding = 20;
  const series = trendData.length ? trendData : [0, 0];
  const max = Math.max(...series, 1);
  const min = 0;

  ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i += 1) {
    const y = padding + (i * (height - padding * 2)) / 4;
    ctx.beginPath();
    ctx.moveTo(padding + 6, y);
    ctx.lineTo(width - padding, y);
    ctx.stroke();
  }

  ctx.beginPath();
  ctx.moveTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  ctx.beginPath();
  ctx.lineWidth = 3;
  ctx.strokeStyle = '#73e5ff';
  ctx.shadowColor = 'rgba(115, 229, 255, 0.8)';
  ctx.shadowBlur = 18;

  series.forEach((point, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(series.length - 1, 1);
    const y = height - padding - ((point - min) / (max - min)) * (height - padding * 2);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });

  ctx.stroke();
  ctx.shadowBlur = 0;

  series.forEach((point, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(series.length - 1, 1);
    const y = height - padding - ((point - min) / (max - min)) * (height - padding * 2);
    ctx.beginPath();
    ctx.fillStyle = '#73e5ff';
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

async function loadMetrics() {
  try {
    const metrics = await fetchJson('/metrics/overview');

    const setText = (id, value) => {
      const node = document.getElementById(id);
      if (node) node.textContent = value;
    };

    setText('metric-competitors', metrics.total_competitors ?? 0);
    setText('metric-alerts', metrics.recent_change_items_7d ?? 0);
    setText('metric-coverage', `${metrics.coverage_percent ?? 0}%`);
    setText('metric-pricing', metrics.change_items_by_category?.pricing ?? 0);
    setText('metric-product', metrics.change_items_by_category?.product ?? 0);
    setText('metric-hiring', metrics.change_items_by_category?.hiring ?? 0);

    trendData = (metrics.trend || []).map((day) => day.material_changes);
    drawTrendChart();
  } catch (error) {
    console.error(error);
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch (_) { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return response.json();
}

async function loadCompetitors() {
  try {
    const list = await fetchJson('/competitors');
    const competitorContainer = document.querySelector('.custom-select[data-name="competitor_id"]');
    const hiddenInput = competitorContainer ? competitorContainer.querySelector('input[type="hidden"]') : null;
    const menu = competitorContainer ? competitorContainer.querySelector('.custom-select-menu') : null;
    const label = competitorContainer ? competitorContainer.querySelector('.custom-select-label') : null;

    if (menu) {
      menu.replaceChildren(...buildCompetitorOptions(list));
      menu.querySelectorAll('.custom-select-option').forEach((option) => {
        if (option.dataset.value === (hiddenInput?.value || '')) {
          option.classList.add('is-selected');
          if (label) label.textContent = option.textContent.trim();
        }
      });
      if (!hiddenInput?.value) {
        if (label) label.textContent = 'Select competitor';
      }
    }

    const competitorCards = document.getElementById('competitor-cards');
    if (competitorCards) {
      competitorCards.replaceChildren(...list.slice(0, 4).map((item) => {
        const card = document.createElement('div');
        card.className = 'mini-card';
        const info = document.createElement('div');
        const title = document.createElement('div');
        title.className = 'mini-title';
        title.textContent = item.name;
        const sub = document.createElement('div');
        sub.className = 'mini-sub';
        sub.textContent = item.domain;
        const pill = document.createElement('span');
        pill.className = `status-pill ${item.status === 'active' ? 'ok' : 'warn'}`;
        pill.textContent = item.status;
        info.append(title, sub);
        card.append(info, pill);
        return card;
      }));
    }
    return list;
  } catch (error) {
    console.error(error);
    const competitorContainer = document.querySelector('.custom-select[data-name="competitor_id"]');
    const menu = competitorContainer ? competitorContainer.querySelector('.custom-select-menu') : null;
    const label = competitorContainer ? competitorContainer.querySelector('.custom-select-label') : null;
    if (menu) {
      menu.replaceChildren(buildOption('API unavailable', '', 'custom-select-option is-selected'));
      if (label) label.textContent = 'API unavailable';
    }
    return [];
  }
}

function buildOption(text, value, className) {
  const option = document.createElement('li');
  option.className = className;
  option.dataset.value = value;
  option.textContent = text;
  return option;
}

function buildEmptyState(title, text) {
  const row = document.createElement('div');
  row.className = 'alert-item';
  const inner = document.createElement('div');
  const titleNode = document.createElement('div');
  titleNode.className = 'alert-title';
  titleNode.textContent = title;
  const textNode = document.createElement('div');
  textNode.className = 'alert-text';
  textNode.textContent = text;
  inner.append(titleNode, textNode);
  row.appendChild(inner);
  return row;
}

function buildCompetitorOptions(list) {
  return [
    buildOption('Select competitor', '', 'custom-select-option'),
    ...list.map((item) => buildOption(`${item.name} (${item.domain})`, String(item.id), 'custom-select-option')),
  ];
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value == null ? '' : String(value);
  return div.innerHTML;
}

async function sendFeedback(changeItemId, label, feedbackButtons) {
  feedbackButtons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch(`/change-items/${changeItemId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label })
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || 'Feedback failed');
    }

    if (label === 'not_relevant') {
      showToast({
        title: 'Marked as not relevant',
        body: 'This change was dismissed and will not appear in future digests.',
        tone: 'success'
      });
    } else {
      showToast({
        title: 'Thanks for the feedback',
        body: 'Marked relevant — it stays in digest rankings.',
        tone: 'success'
      });
    }

    await Promise.all([loadDigest(), loadMetrics()]);
  } catch (error) {
    console.error(error);
    showToast({
      title: 'Feedback failed',
      body: error.message || 'The server did not respond. Try again.',
      tone: 'error'
    });
    feedbackButtons.forEach((button) => { button.disabled = false; });
  }
}

function normalizeDigestSummary(summary, competitorName) {
  if (!summary) {
    return '';
  }

  let text = String(summary).trim().replace(/\s+/g, ' ');
  if (competitorName) {
    const normalizedName = String(competitorName).trim();
    const pattern = new RegExp(`^${normalizedName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*[-:–—]?\\s*`, 'i');
    text = text.replace(pattern, '');
  }

  return text.trim();
}

async function loadDigest() {
  try {
    const digest = await fetchJson('/digests/weekly');
    const digestContainer = document.getElementById('digest-feed');
    if (!digestContainer) return;

    const items = digest.digest_items || [];
    if (!items.length) {
      digestContainer.replaceChildren(buildEmptyState('No alerts', 'No material changes detected this cycle.'));
      return;
    }

    digestContainer.replaceChildren();
    items.slice(0, 4).forEach((item) => {
      const row = document.createElement('div');
      row.className = `alert-item ${item.category || 'product'}`;

      const main = document.createElement('div');
      main.className = 'alert-main';
      const title = document.createElement('div');
      title.className = 'alert-title';
      title.textContent = item.competitor_name;
      const text = document.createElement('div');
      text.className = 'alert-text';
      const cleanSummary = normalizeDigestSummary(item.summary, item.competitor_name);
      text.textContent = cleanSummary || 'Pricing change detected.';
      main.append(title, text);

      const side = document.createElement('div');
      side.className = 'alert-side';
      const tag = document.createElement('span');
      tag.className = 'alert-tag';
      tag.textContent = item.category || 'product';      const feedbackRow = document.createElement('div');
      feedbackRow.className = 'feedback-row';
      const upButton = document.createElement('button');
      upButton.className = 'feedback-btn';
      upButton.type = 'button';
      upButton.title = 'Relevant';
      upButton.setAttribute('aria-label', 'Mark relevant');
      upButton.textContent = '👍';
      const downButton = document.createElement('button');
      downButton.className = 'feedback-btn';
      downButton.type = 'button';
      downButton.title = 'Not relevant';
      downButton.setAttribute('aria-label', 'Mark not relevant');
      downButton.textContent = '👎';
      const evidenceButton = document.createElement('button');
      evidenceButton.className = 'evidence-btn';
      evidenceButton.type = 'button';
      evidenceButton.textContent = 'Evidence';
      evidenceButton.setAttribute('aria-label', `View evidence for ${item.competitor_name} change`);
      evidenceButton.addEventListener('click', () => openEvidence(item.change_item_id));

      const buttons = [upButton, downButton];
      upButton.addEventListener('click', () => sendFeedback(item.change_item_id, 'relevant', buttons));
      downButton.addEventListener('click', () => sendFeedback(item.change_item_id, 'not_relevant', buttons));

      feedbackRow.append(evidenceButton, upButton, downButton);
      side.append(tag, feedbackRow);
      row.append(main, side);
      digestContainer.appendChild(row);
    });
  } catch (error) {
    // 404 simply means no digest exists yet; show the empty state.
    const digestContainer = document.getElementById('digest-feed');
    if (digestContainer && !digestContainer.childElementCount) {
      digestContainer.replaceChildren(buildEmptyState('No alerts', 'No digest generated yet — run a monitoring cycle first.'));
    }
    console.error(error);
  }
}

function setEvidenceOpen(open) {
  const overlay = document.getElementById('evidence-overlay');
  if (!overlay) return;
  overlay.classList.toggle('open', open);
  overlay.hidden = !open;
  document.body.style.overflow = open ? 'hidden' : '';
  if (open) {
    document.getElementById('evidence-close')?.focus();
  }
}

function paintEvidenceText(container, rawText, tokens, tone) {
  // Build the text node-by-node so changed tokens can be wrapped in <mark>
  // while every string still flows through createTextNode — no HTML injection
  // even when snapshot text or tokens contain markup.
  const text = (rawText || '');
  const usableTokens = (tokens || [])
    .map((token) => String(token).trim())
    .filter((token) => token.length > 0)
    .sort((a, b) => b.length - a.length); // longest-first so "$39/month" wins over "$39"

  if (!usableTokens.length) {
    container.appendChild(document.createTextNode(text || '(no text content stored)'));
    return;
  }

  const pattern = new RegExp(
    `(${usableTokens.map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'gi'
  );
  const pieces = text.split(pattern);

  for (const piece of pieces) {
    if (!piece) continue;
    const isToken = usableTokens.some((token) => token.toLowerCase() === piece.toLowerCase());
    if (isToken) {
      const mark = document.createElement('mark');
      mark.className = `evidence-mark ${tone}`;
      mark.textContent = piece;
      container.appendChild(mark);
    } else {
      container.appendChild(document.createTextNode(piece));
    }
  }

  if (!container.childNodes.length) {
    container.appendChild(document.createTextNode('(no text content stored)'));
  }
}

function paintEvidenceSide(bodyNode, label, snapshot, tokens, tone) {
  const col = document.createElement('div');
  col.className = 'evidence-col';

  const heading = document.createElement('div');
  heading.className = 'evidence-col-heading';
  const title = document.createElement('div');
  title.className = 'evidence-col-title';
  title.textContent = label;
  const timestamp = document.createElement('div');
  timestamp.className = 'evidence-timestamp';
  const fetchedAt = snapshot?.fetched_at ? new Date(snapshot.fetched_at) : null;
  timestamp.textContent = fetchedAt && !Number.isNaN(fetchedAt.getTime())
    ? fetchedAt.toLocaleString()
    : 'time unavailable';
  heading.append(title, timestamp);
  col.appendChild(heading);

  if (snapshot?.screenshot_url) {
    const img = document.createElement('img');
    img.className = 'evidence-screenshot';
    img.src = snapshot.screenshot_url;
    img.alt = `${label} snapshot screenshot`;
    img.loading = 'lazy';
    col.appendChild(img);
  } else {
    const missing = document.createElement('div');
    missing.className = 'evidence-screenshot-missing';
    missing.textContent = 'No screenshot captured for this snapshot.';
    col.appendChild(missing);
  }

  const text = document.createElement('div');
  text.className = 'evidence-text';
  paintEvidenceText(text, snapshot?.text_content, tokens, tone);
  col.appendChild(text);

  bodyNode.appendChild(col);
}

async function openEvidence(changeItemId) {
  const overlay = document.getElementById('evidence-overlay');
  if (!overlay) return;

  const meta = document.getElementById('evidence-meta');
  const body = document.getElementById('evidence-body');
  meta.replaceChildren();
  body.replaceChildren();

  const loading = document.createElement('div');
  loading.className = 'evidence-baseline-note';
  loading.textContent = 'Loading evidence…';
  body.appendChild(loading);
  setEvidenceOpen(true);

  try {
    const evidence = await fetchJson(`/change-items/${changeItemId}/evidence`);
    if (!overlay.classList.contains('open')) return; // closed while loading

    document.getElementById('evidence-title').textContent =
      `${evidence.competitor.name} — ${evidence.tracked_url.url}`;

    const chipData = [
      evidence.category,
      evidence.magnitude,
      `confidence ${Math.round((evidence.confidence ?? 0) * 100)}%`,
      evidence.status
    ];
    chipData.forEach((chip) => {
      const node = document.createElement('span');
      node.className = 'toast-stat';
      node.textContent = chip;
      meta.appendChild(node);
    });

    body.replaceChildren();

    const columns = document.createElement('div');
    columns.className = 'evidence-columns';
    const tokens = evidence.diff?.changed_tokens || [];
    if (evidence.before) {
      paintEvidenceSide(columns, 'Before', evidence.before, tokens, 'removed');
    } else {
      const baselineNote = document.createElement('div');
      baselineNote.className = 'evidence-col evidence-baseline-note';
      baselineNote.textContent = 'No before-snapshot exists — this was the first observation of the page, so there is nothing to diff against.';
      columns.appendChild(baselineNote);
    }
    paintEvidenceSide(columns, 'After', evidence.after, tokens, 'added');
    body.appendChild(columns);

    if (tokens.length) {
      const legend = document.createElement('div');
      legend.className = 'evidence-baseline-note';
      legend.textContent = `${tokens.length} changed token${tokens.length === 1 ? '' : 's'} detected — highlighted above.`;
      body.appendChild(legend);
    }
  } catch (error) {
    console.error(error);
    body.replaceChildren();
    const errorNode = document.createElement('div');
    errorNode.className = 'evidence-error';
    errorNode.textContent = error.message || 'Unable to load evidence for this change.';
    body.appendChild(errorNode);
  }
}

async function loadWorkerStatus() {
  try {
    const status = await fetchJson('/workers/status');
    const workerLabel = document.getElementById('worker-status');
    if (workerLabel) {
      workerLabel.textContent = status.running ? 'Live scheduler' : 'Idle';
      workerLabel.classList.toggle('live', !!status.running);
    }
  } catch (error) {
    console.error(error);
  }
}

async function loadQueueStatus() {
  try {
    const status = await fetchJson('/workers/queue-status');
    const queuedNode = document.getElementById('queue-queued');
    const startedNode = document.getElementById('queue-started');
    const failedNode = document.getElementById('queue-failed');
    const queueMonitor = document.getElementById('queue-monitor');

    if (queuedNode) queuedNode.textContent = String(status.queued || 0);
    if (startedNode) startedNode.textContent = String(status.started || 0);
    if (failedNode) failedNode.textContent = String(status.failed || 0);

    if (queueMonitor) {
      const jobs = status.jobs || [];
      const statusTone = { failed: 'pricing', started: 'product' };
      queueMonitor.replaceChildren(...(jobs.length
        ? jobs.slice(0, 6).map((job) => {
            const row = document.createElement('div');
            row.className = `alert-item ${statusTone[job.status] || 'hiring'}`;
            const inner = document.createElement('div');
            const title = document.createElement('div');
            title.className = 'alert-title';
            title.textContent = job.id;
            const text = document.createElement('div');
            text.className = 'alert-text';
            text.textContent = job.description || 'monitoring cycle';
            inner.append(title, text);
            const tag = document.createElement('span');
            tag.className = 'alert-tag';
            tag.textContent = job.status;
            row.append(inner, tag);
            return row;
          })
        : [buildEmptyState('Queue idle', 'No queued, started, or failed monitoring jobs were found.')]));
    }
  } catch (error) {
    console.error(error);
  }
}

competitorForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(competitorForm);
  const payload = {
    name: formData.get('name'),
    domain: formData.get('domain')
  };

  try {
    const response = await fetch('/competitors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();
    if (!response.ok) {
      showToast({
        title: 'Unable to add competitor',
        body: result.detail || 'The request was rejected. Check the details and try again.',
        tone: 'error'
      });
      return;
    }

    competitorForm.reset();
    await Promise.all([loadCompetitors(), loadMetrics()]);
    showToast({
      title: 'Competitor added',
      body: `${result.name} (${result.domain}) is now being tracked.`,
      tone: 'success'
    });
  } catch (error) {
    console.error(error);
    showToast({
      title: 'Unable to add competitor',
      body: 'The server did not respond. Check that the app is running and try again.',
      tone: 'error'
    });
  }
});

trackedUrlForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const compId = competitorSelect?.value || '';
  if (!compId) {
    showToast({
      title: 'Select a competitor first',
      body: 'Choose a competitor from the dropdown before adding a tracked URL.',
      tone: 'error'
    });
    return;
  }

  const formData = new FormData(trackedUrlForm);
  const payload = {
    url: formData.get('url'),
    page_type: formData.get('page_type') || 'product'
  };

  try {
    const response = await fetch(`/competitors/${compId}/tracked-urls`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();
    if (!response.ok) {
      showToast({
        title: 'Unable to add tracked URL',
        body: result.detail || 'The request was rejected. Check the URL and try again.',
        tone: 'error'
      });
      return;
    }

    trackedUrlForm.reset();
    const pageTypeCustom = document.querySelector('.custom-select[data-name="page_type"]');
    const pageTypeInput = pageTypeCustom?.querySelector('input[type="hidden"]');
    const pageTypeLabel = pageTypeCustom?.querySelector('.custom-select-label');
    if (pageTypeInput) pageTypeInput.value = 'pricing';
    if (pageTypeLabel) pageTypeLabel.textContent = 'Pricing';

    const competitorCustom = document.querySelector('.custom-select[data-name="competitor_id"]');
    const competitorHiddenInput = competitorCustom?.querySelector('input[type="hidden"]');
    const competitorLabel = competitorCustom?.querySelector('.custom-select-label');
    if (competitorHiddenInput) competitorHiddenInput.value = '';
    if (competitorLabel) competitorLabel.textContent = 'Select competitor';

    await loadMetrics();
    showToast({
      title: 'Tracked URL added',
      body: `${result.url} will now be monitored for changes.`,
      tone: 'success'
    });
  } catch (error) {
    console.error(error);
    showToast({
      title: 'Unable to add tracked URL',
      body: 'The server did not respond. Check that the app is running and try again.',
      tone: 'error'
    });
  }
});

const TOAST_DURATION_MS = 7000;

function showToast({ title, body = '', tone = 'success', stats = [] }) {
  const root = document.getElementById('toast-root');
  if (!root) return;

  const toast = document.createElement('div');
  toast.className = `toast ${tone}`;

  const head = document.createElement('div');
  head.className = 'toast-head';
  const titleNode = document.createElement('div');
  titleNode.className = 'toast-title';
  titleNode.textContent = title;
  const closeButton = document.createElement('button');
  closeButton.className = 'toast-close';
  closeButton.type = 'button';
  closeButton.setAttribute('aria-label', 'Dismiss notification');
  closeButton.textContent = '×';
  closeButton.addEventListener('click', () => toast.remove());
  head.append(titleNode, closeButton);

  toast.appendChild(head);

  if (stats.length) {
    const statsRow = document.createElement('div');
    statsRow.className = 'toast-stats';
    stats.forEach((stat) => {
      const chip = document.createElement('span');
      chip.className = 'toast-stat';
      chip.textContent = stat;
      statsRow.appendChild(chip);
    });
    toast.appendChild(statsRow);
  }

  if (body) {
    const bodyNode = document.createElement('div');
    bodyNode.className = 'toast-body';
    bodyNode.textContent = body;
    toast.appendChild(bodyNode);
  }

  root.appendChild(toast);
  setTimeout(() => toast.remove(), TOAST_DURATION_MS);
}

document.getElementById('run-cycle-btn')?.addEventListener('click', async () => {
  const button = document.getElementById('run-cycle-btn');
  if (button) {
    button.disabled = true;
    button.textContent = 'Running…';
  }

  try {
    const response = await fetch('/workers/run-cycle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.detail || 'Run cycle failed');
    }

    const stats = [
      `processed: ${result.processed_competitors ?? 0}`,
      `material: ${result.material_changes ?? 0}`,
      `alerts: ${result.alerts_sent ?? 0}`
    ];
    const failedFetches = result.failed_fetches || [];
    if (failedFetches.length) {
      stats.push(`fetches skipped: ${failedFetches.length}`);
    }
    if (result.last_alert) {
      showToast({
        title: 'Monitoring cycle complete',
        stats,
        body: result.last_alert,
        tone: 'success'
      });
    } else {
      const noChangeBody = failedFetches.length
        ? `${failedFetches.length} page${failedFetches.length === 1 ? '' : 's'} could not be fetched and were skipped: ${failedFetches.map(f => f.url).join(', ')}`
        : 'No material changes detected this cycle.';
      showToast({
        title: 'Monitoring cycle complete',
        stats,
        body: noChangeBody,
        tone: 'success'
      });
    }

    await Promise.all([loadDigest(), loadQueueStatus(), loadMetrics()]);
  } catch (error) {
    console.error(error);
    showToast({
      title: 'Run cycle failed',
      body: error.message || 'The monitoring worker did not respond.',
      tone: 'error'
    });
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Run cycle';
    }
  }
});

document.getElementById('evidence-close')?.addEventListener('click', () => setEvidenceOpen(false));

document.getElementById('evidence-overlay')?.addEventListener('click', (event) => {
  if (event.target === event.currentTarget) setEvidenceOpen(false);
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setEvidenceOpen(false);
});

window.addEventListener('resize', drawTrendChart);

setupCustomSelects();

Promise.all([
  loadCompetitors(),
  loadDigest(),
  loadWorkerStatus(),
  loadQueueStatus(),
  loadMetrics()
]);

setInterval(() => {
  loadWorkerStatus();
  loadQueueStatus();
}, 15000);
