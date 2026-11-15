# Demo "customer" dashboard (planted-flaw testbed)

A small Taxi Ops dashboard that plays the role of a company's UI. It embeds the uxtelemetry **SDK**
(`packages/core`) and has a built-in study runner that records each trial's outcome. We control the UI,
so we can plant known UX flaws, check the pipeline finds them, ship the fix (`?v=2`), and re-measure.

```bash
python3 demo/gen_data.py                       # synthetic data + scenarios (deterministic)
python3 demo/dashboard/app.py --port 8765      # serves the dashboard, collects POST /events -> events.jsonl
# open: http://127.0.0.1:8765/?study=1&pid=P01&st=human&v=1     (v=2 for the fixed design)
```
URL params: `study=1` shows the task panel; `pid` participant ID; `st` = `human` | `agent`; `v` = 1 (flawed) | 2 (fixed).
Without `study=1` it just records free exploration. Plotly loads from a CDN, so an internet connection is needed.

## Planted flaws (ground truth for the recovery test)
| ID | Flaw (v1) | Fix (v2) | Expected telemetry signature |
|---|---|---|---|
| F1 | Bar-chart y-axis truncated; Brooklyn vs Queens looks far bigger than the true 8.5% gap | Axis from 0, value labels | T2 (`compute_derived_value`) incorrect answers, long `chart_hover` on bars |
| F2 | Four near-identical line colors, tiny pale legend | Distinct palette, large legend, unified hover | T3 (`find_extremum`) slower; `chart_legend_click` toggling, many `chart_hover`s |
| F3 | Borough filter hidden behind a "..." menu | Inline filter | T4 (`filter`): idle time, scattered clicks before `menu-more`, abandonment |
| F4 | Avg-fare KPI looks clickable (pointer + hover ring) but does nothing | Card is plain | `rage_click` with `ptr=true`, `interactive=false` on `kpi-avg-fare` |

## Scenarios (`static/scenarios.json`)
Five chart-reading tasks tagged with an Amar/Eagan/Stasko category and a known answer: T1 `retrieve_value`,
T2 `compute_derived_value`, T3 `find_extremum`, T4 `filter`, T5 `determine_range`.
Each trial ends in an `outcome` event: `correct` | `incorrect` | `abandoned`, plus a 1-5 satisfaction rating.

## Test
```bash
npm i playwright-core   # not committed as a dependency yet
CHROMIUM="/path/to/chromium" node demo/test/e2e_demo.mjs
```
A scripted bot runs v1 and v2 and asserts that the telemetry is recorded and that F3/F4 are visible in it.
Bot sessions are **simulated** data: they test the pipeline, not real user behavior.
