const $ = (id) => document.getElementById(id);
let settings = null;

async function load() {
  const res = await chrome.storage.local.get('settings');
  settings = res.settings;
  if (!settings) return;
  $('enabled').checked = settings.enabled;
  $('captureText').checked = settings.captureText;
  $('sessionType').value = settings.sessionType;
  $('taskId').value = settings.taskId || '';
  $('participantId').value = settings.participantId || '';
  render();
}

function render() {
  $('rec').textContent = settings.enabled ? '● REC' : '';
  $('rec').className = settings.enabled ? 'on' : '';
  refreshStats();
}

async function save(patch) {
  settings = { ...settings, ...patch };
  await chrome.storage.local.set({ settings });
  render();
}

async function allEvents() {
  const all = await chrome.storage.local.get(null);
  const keys = Object.keys(all).filter((k) => k.startsWith('ev:')).sort();
  return keys.flatMap((k) => all[k]);
}

async function refreshStats() {
  const evs = await allEvents();
  const mine = evs.filter((e) => e.sid === settings.sessionId).length;
  $('stats').textContent = `${evs.length} events stored (${mine} this session). Session: ${settings.sessionId}`;
}

$('enabled').addEventListener('change', (e) => save({ enabled: e.target.checked }));
$('captureText').addEventListener('change', (e) => save({ captureText: e.target.checked }));
$('sessionType').addEventListener('change', (e) => save({ sessionType: e.target.value }));
$('taskId').addEventListener('change', (e) => save({ taskId: e.target.value.trim() }));
$('participantId').addEventListener('change', (e) => save({ participantId: e.target.value.trim() }));
$('newSession').addEventListener('click', () => save({ sessionId: crypto.randomUUID() }));

$('export').addEventListener('click', async () => {
  const evs = (await allEvents()).sort((a, b) => a.t - b.t);
  const blob = new Blob([evs.map((e) => JSON.stringify(e)).join('\n') + '\n'], { type: 'application/x-ndjson' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `dbx-telemetry-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.jsonl`;
  a.click();
  URL.revokeObjectURL(a.href);
});

$('clear').addEventListener('click', async () => {
  if (!confirm('Delete all locally stored telemetry? This cannot be undone.')) return;
  const all = await chrome.storage.local.get(null);
  await chrome.storage.local.remove(Object.keys(all).filter((k) => k.startsWith('ev:')));
  refreshStats();
});

load();
