// E2E: a scripted bot works through the chat-assistant goals (mode=goals) on v1 (planted behaviors) and v2 (fixed),
// then asserts the telemetry carries what the pipeline needs and that each planted behavior is visible in it.
// Sessions are labeled st=agent (scripted bot), never human.
// Usage: CHROMIUM=/path/to/chromium node demo/test/e2e_chat.mjs   (needs: npm i playwright-core)
import { chromium } from 'playwright-core';
import { spawn } from 'child_process';
import fs from 'fs'; import os from 'os'; import path from 'path'; import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dash = path.join(here, '..', 'dashboard');
const goals = JSON.parse(fs.readFileSync(path.join(dash, 'static', 'goals.json'), 'utf8'));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'chat-e2e-'));
const out = path.join(tmp, 'events.jsonl');
const PORT = 8900 + Math.floor(Math.random() * 200);
const SCALE = 0.2; // planted delays x0.2: v1 B3 = 1.4 s, v2 B3 = 0.3 s

const server = spawn('python3', [path.join(dash, 'app.py'), '--port', String(PORT), '--out', out, '--latency-scale', String(SCALE)],
  { stdio: 'ignore', cwd: dash });
await new Promise((r) => setTimeout(r, 900));
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM, headless: true });

const logAxis = {};
async function runBot(v, consent) {
  const before = fs.existsSync(out) ? fs.readFileSync(out, 'utf8').split('\n').filter(Boolean).length : 0;
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`http://127.0.0.1:${PORT}/?study=1&chat=1&goals=all&pid=C0${v}&st=agent&v=${v}`);
  await page.waitForSelector('#g-start');
  await page.waitForSelector('#line .scatterlayer .trace');
  logAxis[v] = await page.evaluate(() => [...document.querySelectorAll('#line, #bar')].map((gd) => gd.data.map((t) => t.hoverinfo || 'all').join()).join('/'));
  if (consent) await page.check('#g-consent');
  await page.click('#g-start');
  await page.waitForSelector('#chat:not([hidden])');

  let nBot = 0;
  const ask = async (text) => {
    await page.fill('#chat-input', text);
    await page.press('#chat-input', 'Enter');
    nBot++;
    await page.waitForFunction((n) => document.querySelectorAll('#chat-log .msg.bot:not(.typing)').length >= n, nBot, { timeout: 15000 });
    await page.waitForTimeout(300);
  };
  const accept = async () => { await page.locator('#chat-log .msg.bot:not(.typing)').last().locator('[data-ux-id="chat-accept"]').click(); };
  const submit = async (sat) => {
    await page.click('#g-submit');
    await page.click(`[data-ux-id="gsat-${sat}"]`);
    await page.waitForTimeout(700);
  };

  // G1 (B1): percent difference. Both bots accept the assistant's number.
  await ask('By what percentage did Brooklyn have more trips than Queens?');
  await accept(); await submit(v === 1 ? 5 : 4);
  // G2 (B2): Bronx average fare. v1 ignores the borough, so the bot rephrases.
  await ask('What was the average fare in the Bronx?');
  if (v === 1) await ask('average fare for Bronx trips only');
  await accept(); await submit(4);
  // G3 (B3): extremum, slow in v1 with no indicator.
  await page.fill('#chat-input', 'Which day did Queens have the fewest trips?');
  await page.press('#chat-input', 'Enter');
  nBot++;
  await page.waitForTimeout(150);
  const typingShown = await page.locator('#chat-log .msg.typing').count();
  await page.waitForFunction((n) => document.querySelectorAll('#chat-log .msg.bot:not(.typing)').length >= n, nBot, { timeout: 15000 });
  await accept(); await submit(4);
  // G4 (B5): filter to the Bronx, click the anomalous point, ask why.
  if (v === 1) { await page.click('#menu-more'); await page.selectOption('#borough-menu', 'Bronx'); await page.click('#menu-more'); }
  else await page.selectOption('#borough-inline', 'Bronx');
  await page.waitForTimeout(400);
  const pt = await page.evaluate((d) => {
    const gd = document.getElementById('line'), xa = gd._fullLayout.xaxis, ya = gd._fullLayout.yaxis;
    const tr = gd.data.find((t) => t.name === 'Bronx'), i = tr.x.indexOf(d), r = gd.getBoundingClientRect();
    return { x: r.left + xa._offset + xa.l2p(xa.d2l(d)), y: r.top + ya._offset + ya.l2p(ya.d2l(tr.y[i])) };
  }, goals[3].answer);
  await page.mouse.move(pt.x, pt.y, { steps: 5 });
  await page.waitForTimeout(250);
  await page.mouse.click(pt.x, pt.y);
  await page.waitForSelector('#chat-sel:not([hidden])');
  await ask('Why did this drop?');
  if (v === 1) await ask('why is the Bronx so low on March 24?');
  await accept(); await submit(4);
  // G5 (control): v1 bot gives up, v2 asks and answers.
  if (v === 1) await page.click('#g-giveup');
  else { // paste the goal text itself into the chat (a real paste event, then the text appears in the box)
    const goalText = (await page.textContent('#g-q')) + ' ' + (await page.textContent('#g-fmt'));
    await page.evaluate((t) => {
      const el = document.getElementById('chat-input'), dt = new DataTransfer();
      dt.setData('text/plain', t);
      el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    }, goalText);
    await ask(goalText); await accept(); await submit(5);
  }
  await page.waitForSelector('#g-done:not([hidden])');
  await page.waitForTimeout(2600); // periodic SDK flush
  await page.close();
  await new Promise((r) => setTimeout(r, 300));
  const evs = fs.readFileSync(out, 'utf8').split('\n').filter(Boolean).slice(before).map((l) => JSON.parse(l));
  return { evs, typingShown };
}

// default link (no chat=1): the assistant is switched off for now
const plain = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await plain.goto(`http://127.0.0.1:${PORT}/?study=1&pid=C09&st=agent&v=1`);
await plain.waitForSelector('#g-start');
const noChat = await plain.evaluate(() => ['#chat', '#chat-launch', '#g-consent'].every((q) => {
  const el = document.querySelector(q); return !el || el.offsetParent === null; }));
await plain.close();
// default link: 3 goals per session
const three = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await three.goto(`http://127.0.0.1:${PORT}/?study=1&pid=C08&st=agent&v=2`);
await three.waitForSelector('#g-start'); await three.click('#g-start');
await three.waitForSelector('#g-work:not([hidden])');
const goalCounter = await three.textContent('#g-n'), introCount = await three.textContent('#g-count');
await three.close();
const r1 = await runBot(1, true);
const r2 = await runBot(2, false);
await browser.close(); server.kill();
const [v1, v2] = [r1.evs, r2.evs];

const of = (evs, type) => evs.filter((e) => e.type === type);
const resp = (evs, beh) => of(evs, 'assistant_response').filter((e) => e.behavior === beh);
const outcomes = (evs) => of(evs, 'goal_outcome').map((e) => `${e.goal}:${e.status}`).join();
const lat = (evs, beh) => Math.max(...resp(evs, beh).map((e) => e.latency_ms));
const g4sel = (evs) => { const s = of(evs, 'selection'), p = of(evs, 'prompt_submit').find((e) => e.goal === 'G4'); return s.length && p && s[0].t < p.t; };
const checks = [
  ['revision 2: assistant opens automatically in both versions (B4 retired)', of(v1, 'chat_open')[0]?.how === 'auto' && of(v2, 'chat_open')[0]?.how === 'auto'],
  ['F5: no tooltips on either chart in v1 (hoverinfo none), tooltips in v2', logAxis[1].split(/[\/,]/).every((h) => h === 'none') && !logAxis[2].includes('none')],
  ['F5: hovering is still recorded in v1 without tooltips', of(v1, 'chart_hover').length > 0 || of(v1, 'selection').length > 0],
  ['five goal_start events with Amar categories', of(v1, 'goal_start').length === 5 && of(v1, 'goal_start').every((e) => e.gcats)],
  ['one prompt_submit per question, each with goal + turn', of(v1, 'prompt_submit').length === 6 && of(v1, 'prompt_submit').every((e) => e.goal && e.turn >= 1)],
  ['prompt_submit and assistant_response pair up by (goal, turn)', of(v1, 'prompt_submit').every((p) => of(v1, 'assistant_response').some((a) => a.goal === p.goal && a.turn === p.turn))],
  ['consent on (v1): prompt text recorded; consent event', of(v1, 'prompt_submit').every((e) => e.text && e.hash) && of(v1, 'consent')[0]?.state === 'prompt_text'],
  ['consent off (v2): no prompt text, hash + length only', of(v2, 'prompt_submit').every((e) => e.text === undefined && e.hash && e.chars > 0)],
  ['B1: v1 confident wrong percent, v2 correct', resp(v1, 'B1')[0]?.correct === false && resp(v2, 'B1')[0]?.correct === true],
  ['B1 over-trust: v1 submits the wrong assistant answer, rated 5', of(v1, 'goal_outcome').find((e) => e.goal === 'G1' && e.status === 'incorrect' && e.turn === 1 && e.satisfaction === 5)],
  ['B2: v1 ignores the borough first, then parses the rephrase', resp(v1, 'B2').map((e) => e.correct).join() === 'false,true' && resp(v2, 'B2').map((e) => e.correct).join() === 'true'],
  ['B2: rephrase overlaps the first prompt (>= 0.6)', of(v1, 'prompt_submit').find((e) => e.goal === 'G2' && e.turn === 2)?.overlap >= 0.6],
  ['B3: v1 slower than v2, indicator only in v2', lat(v1, 'B3') > lat(v2, 'B3') + 500 && r1.typingShown === 0 && r2.typingShown === 1],
  ['B5: selection recorded before the G4 prompt', g4sel(v1) && g4sel(v2)],
  ['B5: v1 ignores the selection (wrong), v2 uses it', resp(v1, 'B5')[0]?.correct === false && resp(v1, 'B5')[0]?.mark_x === goals[3].answer && resp(v2, 'B5')[0]?.correct === true],
  ['accept feedback logged with answer_id', of(v1, 'answer_feedback').some((e) => e.feedback === 'accept' && e.answer_id)],
  ['v1 outcomes', outcomes(v1) === 'G1:incorrect,G2:correct,G3:correct,G4:correct,G5:abandoned'],
  ['v2 outcomes all correct', outcomes(v2) === 'G1:correct,G2:correct,G3:correct,G4:correct,G5:correct'],
  ['paste: event has where + length only, no content', of(v2, 'paste').length === 1 && of(v2, 'paste')[0].ctx === 'prompt' && of(v2, 'paste')[0].chars > 50 && !('text' in of(v2, 'paste')[0])],
  ['paste: pasted goal flagged on its prompt (pasted + goal_sim >= 0.8)', (() => { const p = of(v2, 'prompt_submit').find((e) => e.goal === 'G5'); return p && p.pasted === true && p.goal_sim >= 0.8; })()],
  ['paste: typed prompts are not flagged and stay below 0.8', of(v1, 'prompt_submit').every((e) => e.pasted === false && e.goal_sim < 0.8)],
  ['pasted G5 goal still answered correctly by the stub', of(v2, 'goal_outcome').find((e) => e.goal === 'G5')?.status === 'correct'],
  ['default link: no assistant, no button, no prompt-text consent box', noChat],
  ['default link: 3 goals per session (counter and intro say 3)', goalCounter.trim() === '1 / 3' && introCount === '3'],
  ['every event is st=agent, app id set', [...v1, ...v2].every((e) => e.st === 'agent' && /^taxi-ops-demo-r2-v[12]$/.test(e.app))],
  ['no query string in recorded path', !JSON.stringify(v1).includes('study=1') && !JSON.stringify(v1).includes('pid=C01')],
];
for (const [n, ok] of checks) console.log(ok ? 'PASS' : 'FAIL', n);
if (!checks.every(([, ok]) => ok)) {
  const brief = (evs) => evs.filter((e) => /prompt_submit|assistant_response|goal_outcome|chat_open|selection/.test(e.type))
    .map((e) => [e.type, e.goal, e.turn, e.behavior, e.correct, e.latency_ms, e.status, e.overlap].join(' '));
  console.log(brief(v1).join('\n')); console.log('---'); console.log(brief(v2).join('\n'));
}
process.exit(checks.every(([, ok]) => ok) ? 0 : 1);
