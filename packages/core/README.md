# uxtelemetry core (SDK)

UI-agnostic interaction recorder. `uxtelemetry.js` is the single source; `scripts/sync-core.sh` copies it to the
extension and the demo dashboard (`--check` fails if a copy is stale).

```html
<script src="uxtelemetry.js"></script>
<script src="plotly-adapter.js"></script>   <!-- optional: chart-mark events -->
<script>
  const rec = UXTelemetry.init({
    endpoint: '/events',          // or sink: batch => ...
    appId: 'my-dashboard',
    consent: true,                // REQUIRED: without it nothing is recorded
    sessionType: 'human',         // 'human' | 'agent'
    participantId: 'P01',
    captureText: false            // true stores raw AI prompt text (default: length + salted hash only)
  });
  rec.setTask('T3', { category: 'find_extremum', prompt: '...' });   // -> task_start
  rec.outcome({ status: 'correct', satisfaction: 4 });                // -> outcome (+ flush)
  UXTelemetry.adapters.plotly(rec, document.getElementById('chart'), { chartId: 'sales' });
</script>
```

## Opt-in markup (stable semantics, preferred over DOM guessing)
`data-ux-id` (element id, reported as `uxid`), `data-ux-region` (named region for hover/scroll),
`data-ux-action` (semantic click action), `data-ux-prompt` (marks an AI prompt input).

## Events added beyond the extension's original set
`task_start`, `outcome {status, satisfaction, answer, dur}`, `custom {name}`, `chart_hover`, `chart_click`,
`chart_legend_click`, `chart_legend_dblclick`, `chart_relayout`, `chart_select`, `chart_reset`.
Click events now also carry `uxid`, `interactive`, and `ptr` (pointer cursor), which together flag
"looks clickable but isn't" elements. Every event carries `app` and `tcat` (task category).

Privacy defaults are unchanged: no keystroke content, no editor text, no password fields, no query strings.
