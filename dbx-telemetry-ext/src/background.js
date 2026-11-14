// Service worker: owns defaults, badge, and persistence of event batches.
// Events are stored as chunks under keys "ev:<ms>:<rand>" in chrome.storage.local.

const DEFAULTS = () => ({
  enabled: false,          // consent gate: nothing is recorded until the user turns this on
  captureText: false,      // if true, raw prompt text is stored (otherwise only length + salted hash)
  sessionType: 'human',    // 'human' | 'agent'  (tag Claude-in-Chrome runs as 'agent')
  taskId: '',
  participantId: '',       // pseudonymous ID only
  sessionId: crypto.randomUUID(),
  salt: crypto.randomUUID()
});

function applyBadge(settings) {
  const on = !!(settings && settings.enabled);
  chrome.action.setBadgeText({ text: on ? 'REC' : '' });
  chrome.action.setBadgeBackgroundColor({ color: '#c0392b' });
}

async function ensureSettings() {
  const { settings } = await chrome.storage.local.get('settings');
  if (!settings) {
    const s = DEFAULTS();
    await chrome.storage.local.set({ settings: s });
    return s;
  }
  return settings;
}

chrome.runtime.onInstalled.addListener(async () => applyBadge(await ensureSettings()));
chrome.runtime.onStartup.addListener(async () => applyBadge(await ensureSettings()));

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.settings) applyBadge(changes.settings.newValue);
});

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.kind === 'events' && Array.isArray(msg.batch) && msg.batch.length) {
    const tab = sender.tab ? sender.tab.id : null;
    const frame = typeof sender.frameId === 'number' ? sender.frameId : null;
    const batch = msg.batch.map((e) => ({ ...e, tab, frame }));
    const key = `ev:${String(Date.now()).padStart(13, '0')}:${Math.random().toString(36).slice(2, 8)}`;
    chrome.storage.local.set({ [key]: batch });
  }
  // no async response
  return false;
});
