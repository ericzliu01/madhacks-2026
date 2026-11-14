# Databricks UX Telemetry (Chrome extension, MV3)

Opt-in, local-first recorder of interaction telemetry on Databricks pages, for HCI research.
Nothing is recorded until the user ticks the consent box in the popup. Data stays in
`chrome.storage.local` until exported as JSONL.

## Install (unpacked)
1. `chrome://extensions` → enable Developer mode → **Load unpacked** → select this folder.
2. Open (or reload) a Databricks tab. Content scripts only attach on page load.
3. Click the extension icon, set participant ID / session type / task ID, tick consent. Badge shows `REC`.
4. **Export JSONL** from the popup when done.

Matched hosts: `*.cloud.databricks.com`, `*.azuredatabricks.net`, `*.gcp.databricks.com`.

## Event schema
Every event carries: `t` (epoch ms), `sid` (session), `st` (`human`|`agent`), `task`, `pid`, `page`
(notebook, dashboard, genie, sql_editor, catalog, jobs, compute, other), `path` (pathname only),
`type`, `tab`, `frame`, plus type-specific fields:

| type | fields |
|---|---|
| `session_start` / `session_end` / `page_load` | `w`,`h`,`dpr` |
| `mouse_move` | `x`,`y`,`v` (px/s), sampled at ≥100 ms and ≥8 px |
| `hover_region` | `region`,`dur` (ms, ≥300) |
| `click` / `dblclick` / `contextmenu` | `x`,`y`,`btn`,`tag`,`role`,`testid`,`label`,`region`,`dom`,`action` |
| `rage_click` | as click + `n` |
| `scroll` | `region`,`pos`,`ratio`,`h` |
| `key` | `combo` (Enter, Escape, Tab, modifier shortcuts only), `ctx` |
| `typing` | `ctx` (prompt/editor/input/page), `chars`, `del`, `dur`: counts only, never content |
| `prompt_submit` | `how` (enter/click), `chars`, `words`, `hash` (salted), `text` (only if opted in) |
| `idle_start` / `idle_end` | `dur` |
| `visibility`, `window_focus`, `window_blur`, `viewport`, `navigate` | state / `from`,`to` |

`action` is a coarse label inferred from button text: send, run, accept, reject, stop, regenerate, copy, feedback.

## Privacy defaults
- No keystroke content, no notebook/cell/editor/output text, no password fields, no query strings.
- Button/tab labels (≤40 chars) are recorded as UI labels. A button whose text is user data could leak a short snippet.
- Prompt text is off by default; the hash uses a per-install salt.
- Pathnames can contain workspace object IDs. Review exports before sharing.

## Known limitations / next steps
- Heuristics for AI chat inputs (`PROMPT_HINT`) and page kinds are guesses. Tune against the real Databricks DOM.
- `all_frames` is false, so embedded dashboard iframes are not captured yet.
- Not yet captured: AI response render time, suggestion accept/reject beyond click labels, cell run duration.
- Sink is local export only; upload to a Databricks Volume / Delta table is the next step.
- Verified with the e2e fixture only; not yet run against a real Databricks workspace.

## Testing
`test/e2e.mjs` loads the extension in Chromium against `test/fixture.html` (a stand-in for the Databricks DOM)
and asserts events and privacy guarantees (no password/query-string/prompt-text leaks).
```bash
npm i playwright-core   # not committed as a dependency yet
CHROMIUM="/path/to/chromium" node test/e2e.mjs
```
This validates capture logic only; it does not exercise the real Databricks UI.
