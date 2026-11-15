// UI-driven re-test: bots with ONE fixed strategy, identical for v1 and v2, run the real dashboard in a browser.
// Outcomes come from what each design renders, not from probabilities we wrote down. Sessions are labeled st=agent
// (bot on the real UI): neither human nor the probability-table simulation. The strategy is still ours, so this tests
// whether the designs differ for this strategy, not how people behave.
//
// What the bot may use (what a person can see): visible text, element sizes and positions, cursor style, colors and
// legend legibility, tooltips, SVG geometry of marks and axis ticks. It never reads data.json, goals.json answers,
// Plotly's internal data, or aria-labels of icons. It may map a point's left-to-right index to the date (the x axis
// shows March 2026, one point per day).
//
// Usage: CHROMIUM=... node demo/test/agent_study.mjs [--n 12] [--seed 1] [--out dir] [--concurrency 4] [--mode both]
import { chromium } from 'playwright-core';
import { spawn } from 'child_process';
import fs from 'fs'; import os from 'os'; import path from 'path'; import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const dash = path.join(here, '..', 'dashboard');
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const N = +arg('n', 12), SEED = +arg('seed', 1), CONC = +arg('concurrency', 4), MODE = arg('mode', 'both');
const OUTDIR = path.resolve(arg('out', fs.mkdtempSync(path.join(os.tmpdir(), 'agent-study-'))));  // absolute: the collector runs in another cwd
const PORT = 9100 + Math.floor(Math.random() * 200);
const evfile = path.join(OUTDIR, 'events.jsonl');
fs.mkdirSync(OUTDIR, { recursive: true });

function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const dateOf = (i) => `2026-03-${String(i + 1).padStart(2, '0')}`;

// ------------------------------------------------------------------ perception helpers (run in the page)
const PERCEIVE = `
window.__agent = {
  visible(el) {
    if (!el || !(el instanceof Element)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) return false;
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0 || n.hidden) return false;
    }
    return true;
  },
  // a select whose VISIBLE label text says Borough
  boroughSelect() {
    for (const lab of document.querySelectorAll('label')) {
      if (!/borough/i.test(lab.textContent || '') || !this.visible(lab)) continue;
      const sel = lab.htmlFor ? document.getElementById(lab.htmlFor) : lab.parentElement.querySelector('select');
      if (sel && this.visible(sel)) return '#' + sel.id;
    }
    return null;
  },
  // things that look clickable: native buttons/links or pointer cursor; not charts, not the study panel or chat
  candidates() {
    const out = [];
    for (const el of document.querySelectorAll('body *')) {
      if (el.closest('aside,#chat,.js-plotly-plot,label,select,option')) continue;
      const looks = el.matches('button,a,[role=button]') || getComputedStyle(el).cursor === 'pointer';
      if (!looks || !this.visible(el)) continue;
      if (el.parentElement && el.parentElement.closest('button,a,[role=button]')) continue;
      if (getComputedStyle(el.parentElement).cursor === 'pointer' && !el.matches('button,a')) continue;
      const r = el.getBoundingClientRect();
      out.push({ key: el.id || el.getAttribute('data-ux-id') || el.tagName, x: r.left + r.width / 2, y: r.top + r.height / 2, area: r.width * r.height });
    }
    return out;
  },
  chatInput() {
    const i = document.querySelector('#chat input[type=text]');
    return i && this.visible(i) && /ask/i.test(i.placeholder || '') ? '#chat-input' : null;
  },
  snapshot() { return [...document.querySelectorAll('select,#chat,#more-panel')].map((e) => this.visible(e) ? 1 : 0).join(''); },
  contrast(fg, bg) {
    const L = (c) => { const m = c.match(/\\d+(\\.\\d+)?/g).slice(0, 3).map((v) => { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
    const a = L(fg) + 0.05, b = L(bg) + 0.05; return Math.max(a, b) / Math.min(a, b);
  },
  // legend entries of a chart: readable only if font >= 10px and contrast >= 3:1 (else the bot cannot use them)
  legend(sel) {
    return [...document.querySelectorAll(sel + ' .legend .traces')].filter((t) => !t.closest('.hoverlayer')).map((t) => {
      const txt = t.querySelector('text'), line = t.querySelector('path.js-line');
      const cs = getComputedStyle(txt);
      return { name: txt.textContent, readable: parseFloat(cs.fontSize) >= 10 && this.contrast(txt.getAttribute('style').match(/fill: ([^;]+)/)[1], 'rgb(255,255,255)') >= 3,
               color: line ? getComputedStyle(line).stroke : null };
    });
  },
  // rendered line paths: stroke color + pixel points in page coordinates (from the SVG path and its transform)
  lines(sel) {
    return [...document.querySelectorAll(sel + ' .scatterlayer .trace path.js-line')].filter((p) => this.visible(p)).map((p) => {
      const m = (p.getAttribute('d') || '').match(/-?\\d+(\\.\\d+)?/g) || [];
      const t = p.getCTM(), svg = p.ownerSVGElement.getBoundingClientRect(), pts = [];
      for (let i = 0; i + 1 < m.length; i += 2) pts.push([svg.left + t.e + +m[i], svg.top + t.f + +m[i + 1]]);
      return { color: getComputedStyle(p).stroke, pts };
    });
  },
  tooltip() { return [...document.querySelectorAll('.hoverlayer text')].map((t) => t.textContent).join(' | '); },
  // bar heights as SEEN: clipped to the plot area (an axis that does not start at 0 cuts the bars off)
  bars() {
    const area = document.querySelector('#bar .draglayer .nsewdrag').getBoundingClientRect();
    return [...document.querySelectorAll('#bar .bars .point')].map((pt) => {
      const r = pt.querySelector('path').getBoundingClientRect(), tx = pt.querySelector('text');
      return { h: Math.min(r.bottom, area.bottom) - Math.max(r.top, area.top), label: tx && this.visible(tx) ? tx.textContent : null };
    });
  },
  // y-axis tick labels with their screen positions (for reading values by eye when there is no tooltip)
  yticks(sel) {
    return [...document.querySelectorAll(sel + ' .ytick text')].filter((t) => this.visible(t)).map((t) => {
      const r = t.getBoundingClientRect(), raw = t.textContent.replace(/[,\s]/g, '');
      const v = /k$/i.test(raw) ? parseFloat(raw) * 1000 : parseFloat(raw);
      return { v, y: r.top + r.height / 2 };
    }).filter((t) => Number.isFinite(t.v));
  },
  xLabels(sel) { return [...document.querySelectorAll(sel + ' .xtick text')].map((t) => t.textContent); },
};`;

const rgb = (s) => (s.match(/\d+/g) || []).slice(0, 3).map(Number);
const dist = (a, b) => Math.hypot(...rgb(a).map((v, i) => v - rgb(b)[i]));
const num = (s) => { const m = String(s).replace(/,/g, '').match(/-?\d+(\.\d+)?/); return m ? +m[0] : NaN; };

// ------------------------------------------------------------------ bot strategy (same for every version)
class Bot {
  constructor(page, r) {
    this.p = page; this.r = r;
    this.clickBudget = 1 + Math.floor(r() * 4);      // 1-4 exploratory clicks before giving up on a hunt
    this.frustration = r() < 0.5;                     // repeats a click that did nothing (2 quick extra clicks)
    this.patienceMs = 3000 + Math.floor(r() * 5000);  // wait for a reply; x3 if a progress indicator is shown
    this.checkChart = r() < 0.3;                      // sometimes cross-checks an assistant number against the chart
  }
  ev(fn, ...a) { return this.p.evaluate(fn, ...a); }
  async click(x, y) { await this.p.mouse.move(x, y, { steps: 4 }); await this.p.mouse.click(x, y); }

  // hunt for something (a visible borough select, or the chat input) by clicking clickable-looking things,
  // biggest first (salience), within the click budget. Returns true if found.
  async hunt(found) {
    if (await found()) return true;
    const cands = (await this.ev(() => window.__agent.candidates())).sort((a, b) => b.area - a.area);
    for (const c of cands.slice(0, this.clickBudget)) {
      const before = await this.ev(() => window.__agent.snapshot());
      await this.click(c.x, c.y);
      await sleep(350);
      if (await found()) return true;
      if (this.frustration && (await this.ev(() => window.__agent.snapshot())) === before) {
        await this.p.mouse.click(c.x, c.y); await sleep(120); await this.p.mouse.click(c.x, c.y); await sleep(300);
        if (await found()) return true;
      }
    }
    return false;
  }
  async filterTo(borough) {
    const sel = () => this.ev(() => window.__agent.boroughSelect());
    if (!(await this.hunt(sel))) return false;
    await this.p.selectOption(await sel(), borough);
    await sleep(400);
    if (await this.ev(() => !document.getElementById('more-panel').hidden)) await this.p.click('#menu-more').catch(() => {});
    return true;
  }
  // identify a line: with a legible legend and a clearly distinct color, take the color match; otherwise hover the
  // candidates (closest color first, or random if the legend cannot be read) until the tooltip names the series
  async findLine(name) {
    const legend = await this.ev(() => window.__agent.legend('#line'));
    const lines = await this.ev(() => window.__agent.lines('#line'));
    if (lines.length === 1) return lines[0];
    const entry = legend.find((l) => l.name === name);
    const order = lines.map((_, i) => i);
    if (entry && entry.readable) {
      order.sort((a, b) => dist(lines[a].color, entry.color) - dist(lines[b].color, entry.color));
      const gap = dist(lines[order[1]].color, entry.color) - dist(lines[order[0]].color, entry.color);
      if (gap > 30) return lines[order[0]];
    } else order.sort(() => this.r() - 0.5);
    for (const i of order) {
      for (const k of [15, 5, 25]) {  // a few points along the line: lines can overlap at any one of them
        const [x, y] = lines[i].pts[Math.min(k, lines[i].pts.length - 1)];
        await this.p.mouse.move(x, y, { steps: 3 }); await sleep(220);
        const tip = await this.ev(() => window.__agent.tooltip());
        const named = legend.map((l) => l.name).filter((nm) => tip.includes(nm));
        if (named.length === 1) { if (named[0] === name) return lines[i]; break; }  // names another series: next line
      }
    }
    return lines[order[0]];  // could not confirm: best guess
  }
  // hover a point and read its value from the tooltip. Unified tooltips list "Name : value" for every series;
  // single-series tooltips read "Name | (date, value)" and may show a neighbouring line when lines overlap, so the
  // bot nudges the pointer up and down until the tooltip names the series it wants.
  async valueAt(line, idx, name, day) {
    const [x, y] = day === undefined ? line.pts[idx] : this.pointForDay(line, day);
    let sawTip = false;
    for (const [dx, dy] of [[0, 0], [0, -3], [0, 3], [3, 0], [-3, 0], [0, -6], [0, 6], [3, -3], [3, 3], [0, -9], [0, 9]]) {
      await this.p.mouse.move(x + dx, y + dy, { steps: 2 }); await sleep(220);
      const tip = await this.ev(() => window.__agent.tooltip());
      const uni = tip.match(new RegExp(name + '\\s*:\\s*([\\d,.]+)'));
      if (uni) return +uni[1].replace(/,/g, '');
      if (tip.startsWith(name)) { const m = tip.match(/,\s*([\d,.]+)\)\s*$/); if (m) return +m[1].replace(/,/g, ''); }
      if (tip) sawTip = true;
      else if (dx === 3 && dy === -3 && !sawTip) break;  // several nudges and never a tooltip: there are none
    }
    return sawTip ? NaN : this.readByEye(y);  // no tooltips on this chart: read the value by eye
  }
  // no tooltip: estimate the value from the point's height against the y-axis tick labels (+-1 px)
  async readByEye(y) {
    const ticks = await this.ev(() => window.__agent.yticks('#line'));
    if (ticks.length < 2) return NaN;
    const a = ticks[0], b = ticks[ticks.length - 1], yy = y + (this.r() - 0.5) * 2;
    return Math.round(a.v + (yy - a.y) * (b.v - a.v) / (b.y - a.y));
  }
  // Plotly simplifies line paths (drops collinear points), so the n-th path point is NOT the n-th day. Dates come from
  // x position between the first and last points (always kept: March 1 and March 30), like reading the x axis.
  dayOfX(line, x) { const x0 = line.pts[0][0], x1 = line.pts[line.pts.length - 1][0]; return Math.round((x - x0) / (x1 - x0) * 29); }
  dateAt(line, i) { return dateOf(this.dayOfX(line, line.pts[i][0])); }
  pointForDay(line, d) {  // the point on the drawn line at day d (interpolated between the surrounding path points)
    const x0 = line.pts[0][0], x1 = line.pts[line.pts.length - 1][0], x = x0 + (x1 - x0) * d / 29;
    for (let k = 1; k < line.pts.length; k++) {
      const [ax, ay] = line.pts[k - 1], [bx, by] = line.pts[k];
      if (x <= bx + 0.5) return [x, ay + (by - ay) * (bx === ax ? 0 : (x - ax) / (bx - ax))];
    }
    return line.pts[line.pts.length - 1];
  }
  minIndex(line) { let b = 0; line.pts.forEach(([, y], i) => { if (y > line.pts[b][1]) b = i; }); return b; }
  maxIndex(line) { let b = 0; line.pts.forEach(([, y], i) => { if (y < line.pts[b][1]) b = i; }); return b; }
  async pctFromBars() {  // Brooklyn (2nd bar) vs Queens (3rd): labels if visible, else bar heights (+-1px noise)
    const bars = await this.ev(() => window.__agent.bars());
    if (bars[1].label && bars[2].label) return +((num(bars[1].label) / num(bars[2].label) - 1) * 100).toFixed(1);
    const n = () => (this.r() - 0.5) * 2;
    return +(((bars[1].h + n()) / (bars[2].h + n()) - 1) * 100).toFixed(1);
  }
  kpiFare() { return this.ev(() => document.getElementById('kpi-fare').textContent); }

  // ---------------------------------------------------------------- chat
  async ask(text) {
    // first let any late replies to earlier questions arrive (a person sees them come in), so they are not mistaken
    // for the answer to this question; up to 15 s
    const counts = () => this.ev(() => [document.querySelectorAll('#chat-log .msg.user').length,
                                        document.querySelectorAll('#chat-log .msg.bot:not(.typing)').length]);
    for (let w = 0; w < 60; w++) { const [u, b] = await counts(); if (b >= u) break; await sleep(250); }
    const nBefore = await this.ev(() => document.querySelectorAll('#chat-log .msg.bot:not(.typing)').length);
    await this.p.fill('#chat-input', text); await this.p.press('#chat-input', 'Enter');
    let t0 = Date.now(), resent = false;
    while (true) {
      await sleep(250);
      const n = await this.ev(() => document.querySelectorAll('#chat-log .msg.bot:not(.typing)').length);
      if (n > nBefore) return this.ev(() => { const m = [...document.querySelectorAll('#chat-log .msg.bot:not(.typing)')].pop(); return m.firstChild.textContent; });
      const indicator = await this.ev(() => !!document.querySelector('#chat-log .msg.typing'));
      const limit = this.patienceMs * (indicator ? 3 : 1);
      if (Date.now() - t0 > limit) {
        if (resent) return null;  // gave up waiting
        resent = true; t0 = Date.now();  // re-send once, then wait a full patience period again
        await this.p.fill('#chat-input', text); await this.p.press('#chat-input', 'Enter');
      }
    }
  }
  async acceptLast() { await this.p.locator('#chat-log .msg.bot:not(.typing)').last().locator('[data-ux-id="chat-accept"]').click().catch(() => {}); }
}

// ------------------------------------------------------------------ task mode (T1-T5)
async function runTasks(bot, v) {
  const p = bot.p;
  const finish = async (answer, sat) => {
    await p.fill('#task-answer', String(answer)); await p.click('#task-submit');
    await p.click(`[data-ux-id="sat-${sat}"]`); await sleep(500);
  };
  const giveUp = async () => { await p.click('#task-giveup'); await sleep(400); };
  // T1 Brooklyn on 2026-03-15: find the line, read the tooltip at day 15
  { const line = await bot.findLine('Brooklyn'); await finish(await bot.valueAt(line, null, 'Brooklyn', 14), 4); }
  // T2 percent Brooklyn over Queens from the bar chart
  await finish(await bot.pctFromBars(), 4);
  // T3 Queens' lowest day: lowest point of the Queens line
  { const line = await bot.findLine('Queens'); await finish(bot.dateAt(line, bot.minIndex(line)), 4); }
  // T4 filter to Bronx, read the Avg fare KPI
  if (await bot.filterTo('Bronx')) await finish(await bot.kpiFare(), 4); else await giveUp();
  // T5 Manhattan range: hover its highest and lowest points
  { const line = await bot.findLine('Manhattan');
    const hi = await bot.valueAt(line, bot.maxIndex(line), 'Manhattan'), lo = await bot.valueAt(line, bot.minIndex(line), 'Manhattan');
    if (Number.isFinite(hi - lo)) await finish(hi - lo, 4); else await giveUp(); }
  await p.waitForSelector('#step-done:not([hidden])', { timeout: 5000 }).catch(() => {});
}

// ------------------------------------------------------------------ goal mode (G1-G5)
async function runGoals(bot, v) {
  const p = bot.p;
  let chat = !!(await bot.ev(() => window.__agent.chatInput()));
  const submit = async (answer, sat) => { await p.fill('#g-answer', String(answer)); await p.click('#g-submit'); await p.click(`[data-ux-id="gsat-${sat}"]`); await sleep(500); };
  const giveUp = async () => { await p.click('#g-giveup'); await sleep(400); };
  const findChat = async () => { if (!chat) chat = await bot.hunt(() => bot.ev(() => window.__agent.chatInput())); return chat; };
  const reset = async () => { await p.keyboard.press('Escape'); };

  // G1 percent Brooklyn over Queens
  if (await findChat()) {
    const reply = await bot.ask('By what percentage did Brooklyn have more trips than Queens?');
    if (!reply) await giveUp();
    else {
      const shown = (reply.match(/\d[\d,]*/g) || []).map((s) => +s.replace(/,/g, '')).filter((n) => n > 1000);
      let ans = num(reply.match(/(\d+\.\d)%/)?.[1] ?? NaN);
      if (shown.length >= 2) ans = +((shown[0] / shown[1] - 1) * 100).toFixed(1);  // working shown: check the arithmetic
      else if (bot.checkChart) { const c = await bot.pctFromBars(); if (Math.abs(c - ans) > 2) ans = c; }
      await bot.acceptLast(); await submit(ans, 4);
    }
  } else await submit(await bot.pctFromBars(), 4);

  // G2 Bronx average fare
  if (await findChat()) {
    let reply = await bot.ask('What was the average fare in the Bronx?');
    if (reply && !/bronx/i.test(reply)) reply = await bot.ask('average fare for Bronx trips only');  // ignored the borough
    if (reply && /bronx/i.test(reply)) { await bot.acceptLast(); await submit(num(reply.match(/\$(\d+\.\d+)/)?.[1]), 4); }
    else await giveUp();
  } else if (await bot.filterTo('Bronx')) await submit(await bot.kpiFare(), 4); else await giveUp();

  // G3 Queens' quietest day
  if (await findChat()) {
    const reply = await bot.ask('Which day did Queens have the fewest trips?');
    const d = reply && reply.match(/2026-\d\d-\d\d/);
    if (d) { await bot.acceptLast(); await submit(d[0], 4); } else await giveUp();
  } else { const line = await bot.findLine('Queens'); await submit(bot.dateAt(line, bot.minIndex(line)), 3); }

  // G4 the odd Bronx day: isolate the Bronx, click its lowest point, ask why
  let line, filtered = await bot.filterTo('Bronx');
  line = filtered ? (await bot.ev(() => window.__agent.lines('#line')))[0] : await bot.findLine('Bronx');
  const i = bot.minIndex(line), [x, y] = line.pts[i];
  await p.mouse.move(x, y, { steps: 3 }); await sleep(200); await p.mouse.click(x, y); await sleep(300);
  const day = bot.dateAt(line, i);
  if (chat) {
    let reply = await bot.ask('Why did this drop?');
    if (reply && !reply.includes(day)) reply = await bot.ask(`why is the Bronx so low on ${day}?`);  // ignored my selection
    if (reply && reply.includes(day)) { await bot.acceptLast(); await submit(day, 4); } else await submit(day, 3);
  } else await submit(day, 3);

  // G5 Manhattan range
  if (await findChat()) {
    const reply = await bot.ask("How much did Manhattan's daily trips vary, highest minus lowest?");
    const n = reply && reply.match(/range of ([\d,]+)/);
    if (n) { await bot.acceptLast(); await submit(n[1].replace(/,/g, ''), 4); } else await giveUp();
  } else {
    const l = await bot.findLine('Manhattan');
    const hi = await bot.valueAt(l, bot.maxIndex(l), 'Manhattan'), lo = await bot.valueAt(l, bot.minIndex(l), 'Manhattan');
    if (Number.isFinite(hi - lo)) await submit(hi - lo, 4); else await giveUp();
  }
  await p.waitForSelector('#g-done:not([hidden])', { timeout: 5000 }).catch(() => {});
}

// ------------------------------------------------------------------ driver
const server = spawn('python3', [path.join(dash, 'app.py'), '--port', String(PORT), '--out', evfile, '--latency-scale', '1'], { stdio: 'ignore', cwd: dash });
await sleep(900);
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM, headless: true });
const jobs = [];
for (const mode of MODE === 'both' ? ['tasks', 'goals'] : [MODE]) for (const v of [1, 2]) for (let i = 0; i < N; i++) jobs.push({ mode, v, i });
let done = 0; const failures = [];
async function worker() {
  while (jobs.length) {
    const j = jobs.shift();
    const r = rng(SEED * 1000003 + j.i * 7919 + (j.mode === 'goals' ? 104729 : 0));  // same bot for v1 and v2
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.addInitScript(PERCEIVE);
    const pid = `A${j.mode[0]}${j.i.toString().padStart(3, '0')}`;
    try {
      await page.goto(`http://127.0.0.1:${PORT}/?study=1&mode=${j.mode}&pid=${pid}&st=agent&v=${j.v}`);
      await page.waitForSelector('#line .scatterlayer .trace path.js-line');
      await sleep(500);
      const bot = new Bot(page, r);
      if (j.mode === 'tasks') { await page.waitForSelector('#task-q:not(:has-text("Loading"))'); await runTasks(bot, j.v); }
      else {
        if (r() < 0.5) await page.check('#g-consent');
        await page.click('#g-start'); await sleep(300); await runGoals(bot, j.v);
      }
      await sleep(2600);  // periodic SDK flush
    } catch (e) { failures.push(`${j.mode} v${j.v} #${j.i}: ${String(e.message).split('\n')[0]}`); }
    await ctx.close();
    console.log(`done ${++done}: ${j.mode} v${j.v} #${j.i}`);
  }
}
await Promise.all(Array.from({ length: CONC }, worker));
if (!fs.existsSync(evfile)) { console.error(`no events were written to ${evfile}: check the collector`); process.exit(1); }
await browser.close(); server.kill();
// one file per session for upload to the Volume
const bySid = {};
for (const l of fs.readFileSync(evfile, 'utf8').split('\n').filter(Boolean)) { const e = JSON.parse(l); (bySid[e.sid] ||= []).push(l); }
for (const [sid, lines] of Object.entries(bySid)) fs.writeFileSync(path.join(OUTDIR, `agent-${sid}.jsonl`), lines.join('\n') + '\n');
console.log(`sessions: ${Object.keys(bySid).length}, failures: ${failures.length}${failures.length ? '\n' + failures.join('\n') : ''}\nout: ${OUTDIR}`);
