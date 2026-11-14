// E2E smoke test: loads the extension in Chromium against a local fixture that mimics Databricks DOM.
// Usage: CHROMIUM=/path/to/chromium node test/e2e.mjs   (needs: npm i playwright-core)
import { chromium } from 'playwright-core';
import http from 'http'; import fs from 'fs'; import os from 'os'; import path from 'path'; import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dbx-ext-'));
const EXT = path.join(tmp, 'ext');
fs.cpSync(path.join(here, '..'), EXT, { recursive: true, filter: (s) => !s.includes('node_modules') });
const m = JSON.parse(fs.readFileSync(path.join(EXT, 'manifest.json'), 'utf8'));
m.content_scripts[0].matches = ['http://localhost/*']; // test-only: match the fixture server
fs.writeFileSync(path.join(EXT, 'manifest.json'), JSON.stringify(m, null, 2));

const srv = http.createServer((q, r) => { r.setHeader('content-type', 'text/html'); r.end(fs.readFileSync(path.join(here, 'fixture.html'))); }).listen(0);
await new Promise((r) => srv.on('listening', r));
const url = `http://localhost:${srv.address().port}/editor/notebooks/123?secret=1`;

const ctx = await chromium.launchPersistentContext(path.join(tmp, 'profile'), {
  executablePath: process.env.CHROMIUM, headless: false,
  args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, '--headless=new']
});
const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
await sw.evaluate(async () => { for (let i = 0; i < 50; i++) { if ((await chrome.storage.local.get('settings')).settings) return; await new Promise((r) => setTimeout(r, 100)); } });
await new Promise((r) => setTimeout(r, 500)); // let onInstalled finish before overriding settings
const page = await ctx.newPage();
await page.goto(url);
await sw.evaluate(() => chrome.storage.local.set({ settings: { enabled: true, captureText: false, sessionType: 'agent', taskId: 'T1', participantId: 'P01', sessionId: 's-1', salt: 'x' } }));
await page.waitForTimeout(500);

await page.mouse.move(50, 50); await page.mouse.move(300, 120, { steps: 10 }); await page.mouse.move(200, 400, { steps: 10 });
await page.waitForTimeout(500);
await page.click('text=Run all');
for (let i = 0; i < 3; i++) await page.mouse.click(400, 400);
await page.mouse.move(100, 100); await page.mouse.wheel(0, 300);
await page.click('#prompt'); await page.keyboard.type('show me the top 10 rows', { delay: 20 }); await page.keyboard.press('Enter');
await page.click('#ed'); await page.keyboard.type('select 1', { delay: 20 }); await page.keyboard.press('Meta+Enter');
await page.click('#pw'); await page.keyboard.type('hunter2');
await page.evaluate(() => history.pushState({}, '', '/sql/dashboardsv3/9'));
await page.waitForTimeout(1200); await page.keyboard.press('Escape'); await page.waitForTimeout(4500);

const evs = await sw.evaluate(async () => { const a = await chrome.storage.local.get(null); return Object.keys(a).filter((k) => k.startsWith('ev:')).sort().flatMap((k) => a[k]); });
await ctx.close(); srv.close();

const by = {}; for (const e of evs) by[e.type] = (by[e.type] || 0) + 1;
const blob = JSON.stringify(evs);
const checks = [
  ['session_start recorded', by.session_start === 1],
  ['mouse_move recorded', by.mouse_move > 0],
  ['click w/ run action', evs.some((e) => e.type === 'click' && e.action === 'run')],
  ['rage_click detected', by.rage_click === 1],
  ['scroll recorded', by.scroll > 0],
  ['prompt_submit w/ hash, no text', evs.some((e) => e.type === 'prompt_submit' && e.hash && e.chars === 23 && !('text' in e))],
  ['single prompt typing burst (23 chars)', evs.filter((e) => e.type === 'typing' && e.ctx === 'prompt').length === 1],
  ['editor typing keeps notebook page', evs.some((e) => e.type === 'typing' && e.ctx === 'editor' && e.page === 'notebook')],
  ['navigate -> dashboard', evs.some((e) => e.type === 'navigate' && e.page === 'dashboard')],
  ['no password leak', !blob.includes('hunter2')],
  ['no query string leak', !blob.includes('secret=1')],
  ['no prompt text leak', !blob.includes('top 10')],
  ['no bare modifier key events', !evs.some((e) => e.type === 'key' && /Meta$|Control$/.test(e.combo))]
];
for (const [n, ok] of checks) console.log(ok ? 'PASS' : 'FAIL', n);
console.log(by);
process.exit(checks.every(([, ok]) => ok) ? 0 : 1);
