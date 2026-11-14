// E2E: scripted bot runs the study on the demo dashboard (v1 = planted flaws, v2 = fixed) through the SDK,
// then asserts the collector received the expected telemetry and that the planted flaws are *visible* in it.
// Usage: CHROMIUM=/path/to/chromium node demo/test/e2e_demo.mjs   (needs: npm i playwright-core)
import { chromium } from 'playwright-core';
import { spawn } from 'child_process';
import fs from 'fs'; import os from 'os'; import path from 'path'; import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dash = path.join(here, '..', 'dashboard');
const scenarios = JSON.parse(fs.readFileSync(path.join(dash, 'static', 'scenarios.json'), 'utf8'));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dash-e2e-'));
const PORT = 8700 + Math.floor(Math.random() * 200);

const server = spawn('python3', ['-I', path.join(dash, 'app.py'), '--port', String(PORT), '--out', path.join(tmp, 'events.jsonl')], { stdio: 'ignore' });
await new Promise((r) => setTimeout(r, 800));

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM, headless: true });

async function runBot(v) {
  const out = path.join(tmp, 'events.jsonl');
  const before = fs.existsSync(out) ? fs.readFileSync(out, 'utf8').split('\n').filter(Boolean).length : 0;
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`http://127.0.0.1:${PORT}/?study=1&pid=P0${v}&st=agent&v=${v}`);
  await page.waitForSelector('#task-q:not(:has-text("Loading"))');
  await page.waitForSelector('#bar .bars .point');
  await page.waitForTimeout(400);

  const finish = async (answer, sat) => {
    await page.fill('#task-answer', String(answer));
    await page.click('#task-submit');
    await page.click(`[data-ux-id="sat-${sat}"]`);
    await page.waitForTimeout(800); // human pace: faster would itself register as rage clicks on the same spot
  };
  const hoverSomething = async (sel) => {
    const b = await page.locator(sel).first().boundingBox();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 8 });
    await page.waitForTimeout(350);
    await page.mouse.move(5, 5, { steps: 4 });
  };

  // T1 retrieve_value: hover a line, answer correctly
  await hoverSomething('#line .scatterlayer .trace path.js-line');
  await finish(scenarios[0].answer, 4);
  // T2 compute_derived_value: reads the (v1: truncated) bar chart and misjudges the gap
  await hoverSomething('#bar .bars .point path');
  await finish(v === 1 ? 45 : scenarios[1].answer, v === 1 ? 2 : 4);
  // T3 find_extremum: toggles a legend entry, answers correctly
  await page.locator('#line .legend .traces').first().click();
  await finish(scenarios[2].answer, 3);
  // T4 filter: v1 -> click the "looks clickable" KPI repeatedly, then find the hidden filter menu
  if (v === 1) {
    for (let i = 0; i < 4; i++) await page.click('[data-ux-id="kpi-avg-fare"]');
    await page.click('#menu-more');
    await page.selectOption('#borough-menu', 'Bronx');
  } else {
    await page.selectOption('#borough-inline', 'Bronx');
  }
  await finish(scenarios[3].answer, 3);
  // T5 determine_range: v1 bot gives up, v2 bot answers
  if (v === 1) await page.click('#task-giveup'); else await finish(scenarios[4].answer, 5);
  await page.waitForSelector('#step-done:not([hidden])');
  await page.waitForTimeout(600);
  await page.close();

  return fs.readFileSync(out, 'utf8').split('\n').filter(Boolean).slice(before).map((l) => JSON.parse(l));
}

const v1 = await runBot(1);
const v2 = await runBot(2);
await browser.close(); server.kill();

const outcomes = (evs) => evs.filter((e) => e.type === 'outcome').map((e) => `${e.task}:${e.status}`);
const raw1 = JSON.stringify(v1);
const checks = [
  ['v1 session_start via SDK consent', v1.filter((e) => e.type === 'session_start').length === 1],
  ['v1 five task_start events w/ Amar category', v1.filter((e) => e.type === 'task_start' && e.tcat).length === 5],
  ['v1 outcomes: correct, incorrect, correct, correct, abandoned', outcomes(v1).join() === 'T1:correct,T2:incorrect,T3:correct,T4:correct,T5:abandoned'],
  ['v1 satisfaction captured on answered tasks', v1.filter((e) => e.type === 'outcome' && e.satisfaction != null).length === 4],
  ['v1 chart_hover events from Plotly adapter', v1.some((e) => e.type === 'chart_hover' && e.chart)],
  ['v1 chart_legend_click captured', v1.some((e) => e.type === 'chart_legend_click')],
  ['v1 FLAW F4: rage_click on non-interactive, pointer-cursor KPI', v1.some((e) => e.type === 'rage_click' && e.uxid === 'kpi-avg-fare' && e.ptr === true && e.interactive === false)],
  ['v1 FLAW F3: hidden-filter menu clicked during T4', v1.some((e) => e.type === 'click' && e.uxid === 'menu-more' && e.task === 'T4')],
  ['v2 outcomes all correct except planned', outcomes(v2).join() === 'T1:correct,T2:correct,T3:correct,T4:correct,T5:correct'],
  ['v2 has no rage clicks', !v2.some((e) => e.type === 'rage_click')],
  ['v2 never opens the hidden menu', !v2.some((e) => e.uxid === 'menu-more')],
  ['events carry session type + app id', v1.every((e) => e.st === 'agent' && e.app === 'taxi-ops-demo-v1')],
  ['no query string in recorded path', !raw1.includes('study=1') && !raw1.includes('pid=P01')]
];
for (const [n, ok] of checks) console.log(ok ? 'PASS' : 'FAIL', n);
const by = (evs) => evs.reduce((a, e) => ((a[e.type] = (a[e.type] || 0) + 1), a), {});
console.log('v1', by(v1)); console.log('v2', by(v2));
fs.writeFileSync(path.join(tmp, 'summary.txt'), 'ok');
process.exit(checks.every(([, ok]) => ok) ? 0 : 1);
