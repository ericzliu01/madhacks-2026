// Content script: captures interaction telemetry on Databricks pages.
// Privacy defaults: no keystroke content, no editor/cell/output text, no query strings.
// The Databricks DOM is not a stable API -- heuristics are collected in CFG / *_HINT below.

(() => {
  'use strict';
  if (window.__dbxTelemetryLoaded) return;
  window.__dbxTelemetryLoaded = true;

  const CFG = {
    mouseSampleMs: 100,
    mouseMinDistPx: 8,
    scrollSampleMs: 200,
    flushMs: 2000,
    flushMaxEvents: 100,
    idleMs: 30000,
    rageClicks: 3,
    rageWindowMs: 700,
    rageRadiusPx: 30,
    hoverMinMs: 300,
    typingGapMs: 1500,
    labelMaxLen: 40
  };

  // Heuristics for AI chat inputs (Assistant / Genie). Tune against the real DOM.
  const PROMPT_HINT = /assistant|genie|ask|chat|message|prompt/i;
  const ACTION_RULES = [
    ['send', /^(send|submit|ask|generate)\b/i],
    ['run', /\b(run|execute)\b/i],
    ['accept', /\b(accept|insert|apply|replace)\b/i],
    ['reject', /\b(reject|discard|dismiss)\b/i],
    ['stop', /\b(stop|cancel|interrupt)\b/i],
    ['regenerate', /\b(regenerate|retry|try again)\b/i],
    ['copy', /\bcopy\b/i],
    ['feedback', /\b(thumbs|helpful|feedback)\b/i]
  ];

  const INTERACTIVE_SEL =
    'button,a,[role=button],[role=tab],[role=menuitem],[role=option],[role=switch],input,select,textarea,[data-testid],[aria-label]';
  const EDITOR_SEL = '.monaco-editor,.cm-editor,[contenteditable="true"]';
  const SENSITIVE_SEL = `${EDITOR_SEL},textarea,input`;
  const REGION_SEL =
    '[data-testid],[role=region],[role=main],[role=navigation],[role=dialog],[role=tabpanel],[role=complementary],[aria-label]';

  // ---------------------------------------------------------------- state
  let S = null; // settings from chrome.storage.local
  const buf = [];
  let pageKind = classifyPage(location.pathname);
  let lastRoute = location.pathname + location.hash;

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

  // ---------------------------------------------------------------- emit / flush
  function emitAt(t, type, data) {
    if (!S || !S.enabled) return;
    buf.push({
      t,
      sid: S.sessionId,
      st: S.sessionType,
      task: S.taskId || null,
      pid: S.participantId || null,
      page: pageKind,
      path: location.pathname, // never the query string
      type,
      ...data // may override `page` (typing bursts keep the page they started on)
    });
    if (buf.length >= CFG.flushMaxEvents) flush();
  }
  const emit = (type, data) => emitAt(Date.now(), type, data || {});

  function flush(final = true) {
    closeHover(performance.now());
    if (final) flushTyping(); // periodic flushes must not split an in-progress typing burst
    if (!buf.length) return;
    const batch = buf.splice(0);
    try {
      chrome.runtime.sendMessage({ kind: 'events', batch }, () => void chrome.runtime.lastError);
    } catch (_) {
      /* extension was reloaded; drop */
    }
  }
  setInterval(() => flush(false), CFG.flushMs);

  // ---------------------------------------------------------------- element description
  function describe(el) {
    if (!(el instanceof Element)) return {};
    const hit = el.closest(INTERACTIVE_SEL) || el;
    const sensitive = hit.matches(SENSITIVE_SEL) || !!hit.closest(SENSITIVE_SEL);
    if (hit.matches('input[type=password]')) return { tag: 'input', redacted: true };

    const testid = hit.getAttribute('data-testid') || hit.getAttribute('data-test-id') || hit.getAttribute('data-cy') || null;
    let label = hit.getAttribute('aria-label') || hit.getAttribute('title') || '';
    if (!label && !sensitive && hit.matches('button,[role=button],[role=tab],[role=menuitem]')) {
      const t = (hit.innerText || '').trim();
      if (t.length <= CFG.labelMaxLen && !t.includes('\n')) label = t;
    }
    label = label.replace(/\s+/g, ' ').slice(0, CFG.labelMaxLen);

    return {
      tag: hit.tagName.toLowerCase(),
      role: hit.getAttribute('role') || null,
      testid,
      label: label || null,
      region: regionKey(hit),
      dom: domPath(hit),
      action: classifyAction(label || testid || '')
    };
  }

  function classifyAction(s) {
    if (!s) return null;
    for (const [name, re] of ACTION_RULES) if (re.test(s)) return name;
    return null;
  }

  function regionKey(el) {
    if (!(el instanceof Element)) return null;
    const r = el.closest(REGION_SEL);
    if (!r) return null;
    const id = r.getAttribute('data-testid') || r.getAttribute('aria-label') || '';
    return `${r.getAttribute('role') || r.tagName.toLowerCase()}:${id}`.slice(0, 80);
  }

  function domPath(el) {
    const toks = [];
    for (let n = el, i = 0; n && n.nodeType === 1 && i < 6; n = n.parentElement, i++) {
      const tok = n.getAttribute('data-testid') || n.getAttribute('role') || n.tagName.toLowerCase();
      if (toks[0] !== tok) toks.unshift(tok);
    }
    return toks.slice(-5).join('>').slice(0, 120);
  }

  function ctxOf(el) {
    if (!(el instanceof Element)) return 'page';
    if (findPromptBox(el)) return 'prompt';
    if (el.closest(EDITOR_SEL)) return 'editor';
    if (el.closest('input,textarea,select')) return 'input';
    return 'page';
  }

  // ---------------------------------------------------------------- idle tracking
  let lastActivity = performance.now();
  let idle = false;
  function noteActivity() {
    const now = performance.now();
    if (idle) {
      idle = false;
      emit('idle_end', { dur: Math.round(now - lastActivity) });
    }
    lastActivity = now;
  }
  setInterval(() => {
    if (!idle && performance.now() - lastActivity > CFG.idleMs) {
      idle = true;
      emit('idle_start', {});
    }
  }, 1000);

  // ---------------------------------------------------------------- mouse move + hover dwell
  let lastMove = { t: 0, x: 0, y: 0 };
  let hover = { key: null, since: 0 };

  function closeHover(now) {
    if (hover.key && now - hover.since >= CFG.hoverMinMs) {
      emit('hover_region', { region: hover.key, dur: Math.round(now - hover.since) });
    }
    hover = { key: null, since: now };
  }

  addEventListener(
    'mousemove',
    (e) => {
      noteActivity();
      const now = performance.now();
      const key = regionKey(e.target);
      if (key !== hover.key) {
        closeHover(now);
        hover = { key, since: now };
      }
      if (now - lastMove.t < CFG.mouseSampleMs) return;
      const dist = Math.hypot(e.clientX - lastMove.x, e.clientY - lastMove.y);
      if (dist < CFG.mouseMinDistPx) return;
      const dt = now - lastMove.t || 1;
      lastMove = { t: now, x: e.clientX, y: e.clientY };
      emit('mouse_move', { x: e.clientX, y: e.clientY, v: Math.round((dist / dt) * 1000) });
    },
    { capture: true, passive: true }
  );
  document.addEventListener('mouseleave', () => closeHover(performance.now()));

  // ---------------------------------------------------------------- scroll
  let scrollTimer = null;
  let lastScrollEmit = 0;
  let pendingScroll = null;
  function emitScroll() {
    scrollTimer = null;
    lastScrollEmit = performance.now();
    const el = pendingScroll;
    if (!el) return;
    const max = el.scrollHeight - el.clientHeight;
    emit('scroll', {
      region: regionKey(el),
      pos: Math.round(el.scrollTop),
      ratio: max > 0 ? +(el.scrollTop / max).toFixed(3) : 0,
      h: el.scrollHeight
    });
  }
  addEventListener(
    'scroll',
    (e) => {
      noteActivity();
      const t = e.target;
      pendingScroll = t === document || t === window ? document.documentElement : t;
      if (!(pendingScroll instanceof Element)) return;
      if (scrollTimer) return;
      const wait = Math.max(0, CFG.scrollSampleMs - (performance.now() - lastScrollEmit));
      scrollTimer = setTimeout(emitScroll, wait);
    },
    { capture: true, passive: true }
  );

  // ---------------------------------------------------------------- clicks (+ rage clicks)
  let recentClicks = [];
  function onPointer(e) {
    noteActivity();
    const d = describe(e.target);
    emit(e.type, { x: e.clientX, y: e.clientY, btn: e.button, ...d });

    if (e.type === 'click') {
      const now = performance.now();
      recentClicks = recentClicks.filter((c) => now - c.t < CFG.rageWindowMs);
      recentClicks.push({ t: now, x: e.clientX, y: e.clientY });
      const near = recentClicks.filter((c) => Math.hypot(c.x - e.clientX, c.y - e.clientY) <= CFG.rageRadiusPx);
      if (near.length >= CFG.rageClicks) {
        emit('rage_click', { x: e.clientX, y: e.clientY, n: near.length, ...d });
        recentClicks = [];
      }
      // Send-button click for AI chat
      if (d.action === 'send') {
        const box = findPromptBoxNear(e.target);
        if (box) submitPrompt(box, 'click');
      }
    }
  }
  for (const type of ['click', 'dblclick', 'contextmenu']) {
    addEventListener(type, onPointer, { capture: true, passive: true });
  }

  // ---------------------------------------------------------------- keyboard (no key content)
  let typing = null; // {ctx, start, last, chars, del}
  function flushTyping() {
    if (!typing) return;
    // Stamp with the burst's start time and page, not the (later) flush time.
    emitAt(typing.wall, 'typing', {
      ctx: typing.ctx,
      chars: typing.chars,
      del: typing.del,
      dur: Math.round(typing.last - typing.start),
      page: typing.page
    });
    typing = null;
  }
  setInterval(() => {
    if (typing && performance.now() - typing.last > CFG.typingGapMs) flushTyping();
  }, 500);

  addEventListener(
    'keydown',
    (e) => {
      if (e.target instanceof Element && e.target.matches('input[type=password]')) return;
      noteActivity();
      if (e.key === 'Meta' || e.key === 'Control' || e.key === 'Alt' || e.key === 'Shift') return;
      const ctx = ctxOf(e.target);
      const mod = e.metaKey || e.ctrlKey || e.altKey;
      const special = mod || e.key === 'Enter' || e.key === 'Escape' || e.key === 'Tab';

      if (special) {
        const combo = [e.metaKey && 'meta', e.ctrlKey && 'ctrl', e.altKey && 'alt', e.shiftKey && 'shift', e.key.length === 1 ? e.key.toLowerCase() : e.key]
          .filter(Boolean)
          .join('+');
        emit('key', { combo, ctx });
      } else if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete') {
        const now = performance.now();
        if (typing && (typing.ctx !== ctx || now - typing.last > CFG.typingGapMs)) flushTyping();
        if (!typing) typing = { ctx, start: now, last: now, chars: 0, del: 0, wall: Date.now(), page: pageKind };
        typing.last = now;
        if (e.key.length === 1) typing.chars++;
        else typing.del++;
      }

      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        const box = findPromptBox(e.target);
        if (box) submitPrompt(box, 'enter');
      }
    },
    true
  );

  // ---------------------------------------------------------------- AI prompt submission
  function findPromptBox(el) {
    if (!(el instanceof Element)) return null;
    const box = el.closest('textarea,[contenteditable="true"],[role=textbox],input[type=text],input:not([type])');
    if (!box || box.closest('.monaco-editor,.cm-editor')) return null;
    const hints = [
      box.getAttribute('aria-label'),
      box.getAttribute('placeholder'),
      box.getAttribute('data-testid'),
      box.closest('[data-testid]') && box.closest('[data-testid]').getAttribute('data-testid')
    ]
      .filter(Boolean)
      .join(' ');
    return PROMPT_HINT.test(hints) ? box : null;
  }

  function findPromptBoxNear(el) {
    let n = el;
    for (let i = 0; i < 6 && n; i++, n = n.parentElement) {
      for (const c of n.querySelectorAll('textarea,[contenteditable="true"],[role=textbox],input[type=text]')) {
        if (findPromptBox(c)) return c;
      }
    }
    return null;
  }

  async function saltedHash(text) {
    try {
      const data = new TextEncoder().encode(`${(S && S.salt) || ''}:${text}`);
      const buf = await crypto.subtle.digest('SHA-256', data);
      return [...new Uint8Array(buf)].slice(0, 8).map((b) => b.toString(16).padStart(2, '0')).join('');
    } catch (_) {
      return null;
    }
  }

  function submitPrompt(box, how) {
    const text = ('value' in box ? box.value : box.innerText || '').trim(); // read before the UI clears it
    if (!text) return;
    const t = Date.now();
    const settings = S;
    saltedHash(text).then((hash) => {
      emitAt(t, 'prompt_submit', {
        how,
        chars: text.length,
        words: text.split(/\s+/).length,
        hash,
        text: settings && settings.captureText ? text : undefined
      });
    });
  }

  // ---------------------------------------------------------------- visibility, focus, navigation, viewport
  document.addEventListener('visibilitychange', () => {
    emit('visibility', { state: document.visibilityState });
    if (document.visibilityState === 'hidden') flush();
  });
  addEventListener('focus', () => emit('window_focus', {}));
  addEventListener('blur', () => emit('window_blur', {}));
  addEventListener('pagehide', flush);

  let resizeT = null;
  addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => emit('viewport', { w: innerWidth, h: innerHeight, dpr: devicePixelRatio }), 300);
  });

  // Databricks is a SPA; poll the route instead of patching history from the isolated world.
  setInterval(() => {
    const route = location.pathname + location.hash;
    if (route === lastRoute) return;
    const from = lastRoute;
    lastRoute = route;
    pageKind = classifyPage(location.pathname);
    emit('navigate', { from, to: route });
  }, 500);

  // ---------------------------------------------------------------- settings lifecycle
  function sessionStart() {
    emit('session_start', { w: innerWidth, h: innerHeight, dpr: devicePixelRatio });
  }

  chrome.storage.local.get('settings', ({ settings }) => {
    S = settings || null;
    if (S && S.enabled) emit('page_load', { w: innerWidth, h: innerHeight, dpr: devicePixelRatio });
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local' || !changes.settings) return;
    const old = S;
    const next = changes.settings.newValue || null;
    if (old && old.enabled && (!next || !next.enabled || next.sessionId !== old.sessionId)) {
      emit('session_end', {});
      flush();
    }
    S = next;
    if (next && next.enabled && (!old || !old.enabled || old.sessionId !== next.sessionId)) sessionStart();
  });
})();
