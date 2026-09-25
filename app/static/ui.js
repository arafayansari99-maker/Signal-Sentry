const competitorList = document.getElementById('competitor-list');
const digestList = document.getElementById('digest-list');
const statCompetitors = document.getElementById('stat-competitors');
const statAlerts = document.getElementById('stat-alerts');
const statDigest = document.getElementById('stat-digest');
const statScheduler = document.getElementById('stat-scheduler');

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderCompetitors(items) {
  if (!items.length) {
    competitorList.innerHTML = '<div class="competitor-item"><div class="competitor-main"><div class="competitor-name">No competitors tracked yet</div><div class="subtext">Add a competitor to begin monitoring.</div></div></div>';
    return;
  }

  competitorList.innerHTML = items
    .slice(0, 4)
    .map((item) => `
      <div class="competitor-item">
        <div class="competitor-main">
          <div class="competitor-name">${item.name}</div>
          <div class="subtext">${item.domain}</div>
        </div>
        <span class="badge product">${item.status}</span>
      </div>
    `)
    .join('');
}

function renderDigest(items) {
  if (!items.length) {
    digestList.innerHTML = '<div class="digest-item"><div class="digest-main"><div class="digest-title">No changes detected</div><div class="digest-meta">The next cycle will surface competitor movements here.</div></div></div>';
    return;
  }

  digestList.innerHTML = items
    .slice(0, 4)
    .map((item) => `
      <div class="digest-item">
        <div class="digest-main">
          <div class="digest-title">${item.competitor_name}</div>
          <div class="digest-meta">${item.summary}</div>
        </div>
        <span class="badge ${item.category || 'product'}">${item.category || 'update'}</span>
      </div>
    `)
    .join('');
}

async function loadDashboard() {
  try {
    const [competitors, digest, scheduler] = await Promise.all([
      fetchJson('/competitors'),
      fetchJson('/digests/weekly'),
      fetchJson('/workers/status')
    ]);

    statCompetitors.textContent = competitors.length;
    statDigest.textContent = digest.digest_items?.length ?? 0;
    statAlerts.textContent = Number((digest.digest_items || []).length > 0);
    statScheduler.textContent = scheduler.running ? 'Live' : 'Idle';

    renderCompetitors(competitors);
    renderDigest(digest.digest_items || []);
  } catch (error) {
    competitorList.innerHTML = '<div class="competitor-item"><div class="competitor-main"><div class="competitor-name">API unavailable</div><div class="subtext">Run the app and refresh the page.</div></div></div>';
    digestList.innerHTML = '<div class="digest-item"><div class="digest-main"><div class="digest-title">No data</div><div class="digest-meta">The monitoring worker is not responding.</div></div></div>';
    statCompetitors.textContent = '0';
    statDigest.textContent = '0';
    statAlerts.textContent = '0';
    statScheduler.textContent = 'Offline';
    console.error(error);
  }
}

loadDashboard();
