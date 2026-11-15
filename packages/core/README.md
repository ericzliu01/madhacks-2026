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

## Chat-assistant study (0.3.0)
```js
const rec = UXTelemetry.init({ ..., promptMeta: (text, at) => ({ overlap: 0.8 }) }); // content-free extras on prompt_submit
rec.setCaptureText(true);                        // consent for prompt text  -> consent {state}
rec.setGoal('G2', { categories: ['filter'], prompt: '...' });               // -> goal_start, turn = 1
rec.setTurn(2);                                  // the page advances the turn after each prompt
rec.goalOutcome({ status: 'correct', answer: '21.75', satisfaction: 4, turn: 2 });  // -> goal_outcome (+ flush)
```
Every event now also carries `goal`, `gcats` (Amar categories, `|`-separated) and `turn`. `prompt_submit` reads goal/turn
at the moment of submit. The demo page emits `chat_open {how}`, `chat_close`, `assistant_response {latency_ms, behavior,
answer_id, correct, intent, answer, mark_x}`, `answer_feedback {feedback: accept|copy|thumbs_up|thumbs_down, answer_id}`
and `selection {chart, series, mark_x, mark_y}` through `rec.emit`. `behavior` and `correct` are testbed ground truth from
the stub assistant, not something the SDK infers.

`paste {ctx, chars}` records where a paste landed and its length, never its content.

Privacy defaults are unchanged: no keystroke content, no editor text, no password fields, no query strings. Prompt text
only with `captureText` (or `setCaptureText(true)`); otherwise a salted hash and length.
