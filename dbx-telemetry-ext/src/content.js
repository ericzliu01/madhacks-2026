// Thin extension wrapper around the shared core (src/uxtelemetry.js, synced from packages/core).
// Supplies: the sink (-> service worker), settings (chrome.storage), and Databricks-specific heuristics.
// The Databricks DOM is not a stable API; tune the heuristics below against the real UI.

(() => {
  'use strict';
  if (window.__dbxTelemetryLoaded) return;
  window.__dbxTelemetryLoaded = true;

  function classifyPage(p) {
    if (/\/editor\/notebooks|\/notebooks?\//.test(p)) return 'notebook';
    if (/dashboard/.test(p)) return 'dashboard';
    if (/genie/.test(p)) return 'genie';
    if (/\/sql\/(editor|queries)/.test(p)) return 'sql_editor';
    if (/explore\/data|\/catalog/.test(p)) return 'catalog';
    if (/\/jobs|\/pipelines/.test(p)) return 'jobs';
    if (/\/compute|\/clusters/.test(p)) return 'compute';
    return 'other';
  }

  const rec = UXTelemetry.create({
    sink(batch) {
      try {
        chrome.runtime.sendMessage({ kind: 'events', batch }, () => void chrome.runtime.lastError);
      } catch (_) {
        /* extension was reloaded; drop */
      }
    },
    heuristics: {
      classifyPage,
      promptHint: /assistant|genie|ask|chat|message|prompt/i
    }
  });
  rec.start();

  chrome.storage.local.get('settings', ({ settings }) => rec.update(settings || null, { initial: true }));
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.settings) rec.update(changes.settings.newValue || null);
  });
})();
