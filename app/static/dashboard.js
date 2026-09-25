const currentTheme = localStorage.getItem('signalsentry-theme') || 'dark';
const root = document.documentElement;

const applyTheme = (theme) => {
  root.dataset.theme = theme;
  localStorage.setItem('signalsentry-theme', theme);
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.textContent = theme === 'dark' ? '☀ Light' : '☾ Dark';
  }
};

applyTheme(currentTheme);

const competitorForm = document.getElementById('competitor-form');
const trackedUrlForm = document.getElementById('tracked-url-form');
const competitorSelect = document.getElementById('competitor-select');
const dashboardGrid = document.getElementById('dashboard-grid');
const chartCanvas = document.getElementById('trend-chart');

const trendData = [28, 40, 30, 55, 62, 58, 72, 82, 69, 96, 90, 100];

function drawTrendChart() {
  if (!chartCanvas) return;
  const ctx = chartCanvas.getContext('2d');
  const { width, height } = chartCanvas;
  ctx.clearRect(0, 0, width, height);

  const padding = 20;
  const max = 100;
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

  trendData.forEach((point, index) => {
    const x = padding + (index * (width - padding * 2)) / (trendData.length - 1);
    const y = height - padding - ((point - min) / (max - min)) * (height - padding * 2);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });

  ctx.stroke();
  ctx.shadowBlur = 0;

  trendData.forEach((point, index) => {
    const x = padding + (index * (width - padding * 2)) / (trendData.length - 1);
    const y = height - padding - ((point - min) / (max - min)) * (height - padding * 2);
    ctx.beginPath();
    ctx.fillStyle = '#73e5ff';
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

drawTrendChart();

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('Request failed');
  return response.json();
}

async function loadCompetitors() {
  try {
    const list = await fetchJson('/competitors');
    competitorSelect.innerHTML = '<option value="">Select competitor</option>' + list.map(item => `<option value="${item.id}">${item.name} (${item.domain})</option>`).join('');
    const competitorCards = document.getElementById('competitor-cards');
    if (competitorCards) {
      competitorCards.innerHTML = list.slice(0, 4).map(item => `
        <div class="mini-card">
          <div>
            <div class="mini-title">${item.name}</div>
            <div class="mini-sub">${item.domain}</div>
          </div>
          <span class="status-pill ${item.status === 'active' ? 'ok' : 'warn'}">${item.status}</span>
        </div>
      `).join('');
    }
    return list;
  } catch (error) {
    console.error(error);
    competitorSelect.innerHTML = '<option value="">API unavailable</option>';
    return [];
  }
}

async function loadDigest() {
  try {
    const digest = await fetchJson('/digests/weekly');
    const digestContainer = document.getElementById('digest-feed');
    if (digestContainer) {
      const items = digest.digest_items || [];
      digestContainer.innerHTML = items.slice(0, 4).map(item => `
        <div class="alert-item ${item.category || 'product'}">
          <div>
            <div class="alert-title">${item.competitor_name}</div>
            <div class="alert-text">${item.summary}</div>
          </div>
          <span class="alert-tag">${item.category || 'product'}</span>
        </div>
      `).join('') || '<div class="alert-item"><div><div class="alert-title">No alerts</div><div class="alert-text">No material changes detected this cycle.</div></div></div>';
    }
  } catch (error) {
    console.error(error);
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
      queueMonitor.innerHTML = jobs.length
        ? jobs.slice(0, 6).map(job => `
            <div class="alert-item ${job.status === 'failed' ? 'pricing' : job.status === 'started' ? 'product' : 'hiring'}">
              <div>
                <div class="alert-title">${job.id}</div>
                <div class="alert-text">${job.description || 'monitoring cycle'}</div>
              </div>
              <span class="alert-tag">${job.status}</span>
            </div>
          `).join('')
        : '<div class="alert-item"><div><div class="alert-title">Queue idle</div><div class="alert-text">No queued, started, or failed monitoring jobs were found.</div></div></div>';
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

  const response = await fetch('/competitors', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const result = await response.json();
  if (!response.ok) {
    alert(result.detail || 'Unable to add competitor');
    return;
  }

  competitorForm.reset();
  await loadCompetitors();
  alert(`Competitor added: ${result.name}`);
});

trackedUrlForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const compId = competitorSelect.value;
  if (!compId) {
    alert('Select a competitor first');
    return;
  }

  const formData = new FormData(trackedUrlForm);
  const payload = {
    url: formData.get('url'),
    page_type: formData.get('page_type') || 'product'
  };

  const response = await fetch(`/competitors/${compId}/tracked-urls`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const result = await response.json();
  if (!response.ok) {
    alert(result.detail || 'Unable to add tracked URL');
    return;
  }

  trackedUrlForm.reset();
  alert(`Tracked URL added: ${result.url}`);
});

document.getElementById('theme-toggle')?.addEventListener('click', () => {
  const nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(nextTheme);
});

window.addEventListener('resize', drawTrendChart);

Promise.all([
  loadCompetitors(),
  loadDigest(),
  loadWorkerStatus(),
  loadQueueStatus()
]);

setInterval(() => {
  loadWorkerStatus();
  loadQueueStatus();
}, 15000);
