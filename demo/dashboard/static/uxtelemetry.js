/*!
 * uxtelemetry core -- UI-agnostic interaction recorder for HCI research.
 *
 * One source of truth, used two ways:
 *   - SDK:       <script src="uxtelemetry.js"></script>  then  UXTelemetry.init({...})
 *   - Extension: loaded as a content script before a thin wrapper that supplies sink + settings.
 *
 * Privacy defaults: no keystroke content, no editor text, no password fields, no query strings,
 * prompt text only if settings.captureText is true. Nothing is recorded unless settings.enabled.
 *
 * Opt-in markup for stable, app-owned semantics (preferred over DOM guessing):
 *   data-ux-id="filter-date"       stable element id (reported as `uxid`)
 *   data-ux-region="kpi-row"       named region for hover dwell / scroll
 *   data-ux-action="send"          semantic action for clicks (send, run, accept, ...)
 *   data-ux-prompt                 marks an AI prompt input
 *
 * Study structure: a task (setTask/outcome) is one scripted question; a goal (setGoal/goalOutcome) is an open-ended
 * need worked on with an assistant over several turns (setTurn). Both are stamped on every event while active.
 */
(function (root) {
  'use strict';

  const BASE_CFG = {
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

  const DEFAULT_ACTION_RULES = [
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
    'button,a,[role=button],[role=tab],[role=menuitem],[role=option],[role=switch],input,select,textarea,[data-testid],[aria-label],[data-ux-id]';
  const NATIVE_INTERACTIVE_SEL = 'button,a,[role=button],[role=tab],[role=menuitem],[role=option],[role=switch],input,select,textarea,summary,[data-ux-action]';
  const EDITOR_SEL = '.monaco-editor,.cm-editor,[contenteditable="true"]';
  const SENSITIVE_SEL = `${EDITOR_SEL},textarea,input`;
  const REGION_SEL =
    '[data-ux-region],[data-testid],[role=region],[role=main],[role=navigation],[role=dialog],[role=tabpanel],[role=complementary],[aria-label]';

  function create(options) {
    options = options || {};
    const CFG = Object.assign({}, BASE_CFG, options.cfg);
    const sink = options.sink || function () {};
    const H = options.heuristics || {};
    const PROMPT_HINT = H.promptHint || /assistant|genie|ask|chat|message|prompt/i;
    const ACTION_RULES = H.actionRules || DEFAULT_ACTION_RULES;
    const classifyPage = H.classifyPage || function () { return 'other'; };
    // Optional page hook: extra, content-free fields for prompt_submit (e.g. token overlap with the previous prompt).
    // Called synchronously at submit with (text, {goal, turn}); must not return the text itself.
    const promptMeta = options.promptMeta || null;

    let S = options.settings || null; // {enabled, sessionId, sessionType, taskId, taskCategory, goalId, goalCats, turnId, participantId, appId, captureText, salt}
    let started = false;
    let pageKind = classifyPage(location.pathname);
    let lastRoute = location.pathname + location.hash;
    let taskStartWall = null;
    let goalStartWall = null;
    const buf = [];
    const disposers = [];

    function on(target, type, fn, opts) {
      target.addEventListener(type, fn, opts);
      disposers.push(function () { target.removeEventListener(type, fn, opts); });
    }
    function every(fn, ms) {
      const id = setInterval(fn, ms);
      disposers.push(function () { clearInterval(id); });
    }

    // ------------------------------------------------------------ emit / flush
    function emitAt(t, type, data) {
      if (!S || !S.enabled) return;
      buf.push(
        Object.assign(
          {
            t: t,
            sid: S.sessionId,
            st: S.sessionType,
            app: S.appId || null,
            task: S.taskId || null,
            tcat: S.taskCategory || null,
            pid: S.participantId || null,
            goal: S.goalId || null,
            gcats: S.goalCats || null,
            turn: S.turnId == null ? null : S.turnId,
            page: pageKind,
            path: location.pathname, // never the query string
            type: type
          },
          data // may override `page` (typing bursts keep the page they started on)
        )
      );
      if (buf.length >= CFG.flushMaxEvents) flush();
    }
    function emit(type, data) { emitAt(Date.now(), type, data || {}); }

    function flush(final) {
      closeHover(performance.now());
      if (final !== false) flushTyping(); // periodic flushes must not split an in-progress typing burst
      if (!buf.length) return;
      const batch = buf.splice(0);
      try { sink(batch); } catch (_) { /* sink failure must never break the host page */ }
    }

    // ------------------------------------------------------------ element description
    function describe(el) {
      if (!(el instanceof Element)) return {};
      const hit = el.closest(INTERACTIVE_SEL) || el;
      if (hit.matches('input[type=password]')) return { tag: 'input', redacted: true };
      const sensitive = hit.matches(SENSITIVE_SEL) || !!hit.closest(SENSITIVE_SEL);
      const uxEl = el.closest('[data-ux-id]');

      const testid = hit.getAttribute('data-testid') || hit.getAttribute('data-test-id') || hit.getAttribute('data-cy') || null;
      let label = hit.getAttribute('aria-label') || hit.getAttribute('title') || '';
      if (!label && !sensitive && hit.matches('button,[role=button],[role=tab],[role=menuitem]')) {
        const t = (hit.innerText || '').trim();
        if (t.length <= CFG.labelMaxLen && t.indexOf('\n') < 0) label = t;
      }
      label = label.replace(/\s+/g, ' ').slice(0, CFG.labelMaxLen);

      let ptr = false;
      try { ptr = getComputedStyle(el).cursor === 'pointer'; } catch (_) { /* ignore */ }

      return {
        tag: hit.tagName.toLowerCase(),
        role: hit.getAttribute('role') || null,
        uxid: uxEl ? uxEl.getAttribute('data-ux-id') : null,
        testid: testid,
        label: label || null,
        region: regionKey(hit),
        dom: domPath(hit),
        action: (uxEl && uxEl.getAttribute('data-ux-action')) || hit.getAttribute('data-ux-action') || classifyAction(label || testid || ''),
        interactive: hit.matches(NATIVE_INTERACTIVE_SEL),
        ptr: ptr // pointer cursor on a non-interactive element = "looks clickable" signal
      };
    }

    function classifyAction(s) {
      if (!s) return null;
      for (let i = 0; i < ACTION_RULES.length; i++) if (ACTION_RULES[i][1].test(s)) return ACTION_RULES[i][0];
      return null;
    }

    function regionKey(el) {
      if (!(el instanceof Element)) return null;
      const r = el.closest(REGION_SEL);
      if (!r) return null;
      const id = r.getAttribute('data-ux-region') || r.getAttribute('data-testid') || r.getAttribute('aria-label') || '';
      return ((r.getAttribute('role') || r.tagName.toLowerCase()) + ':' + id).slice(0, 80);
    }

    function domPath(el) {
      const toks = [];
      for (let n = el, i = 0; n && n.nodeType === 1 && i < 6; n = n.parentElement, i++) {
        const tok = n.getAttribute('data-ux-id') || n.getAttribute('data-testid') || n.getAttribute('role') || n.tagName.toLowerCase();
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

    // ------------------------------------------------------------ idle
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

    // ------------------------------------------------------------ hover dwell
    let hover = { key: null, since: 0 };
    function closeHover(now) {
      if (hover.key && now - hover.since >= CFG.hoverMinMs) {
        emit('hover_region', { region: hover.key, dur: Math.round(now - hover.since) });
      }
      hover = { key: null, since: now };
    }

    // ------------------------------------------------------------ scroll
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

    // ------------------------------------------------------------ typing (counts only)
    let typing = null;
    function flushTyping() {
      if (!typing) return;
      emitAt(typing.wall, 'typing', {
        ctx: typing.ctx,
        chars: typing.chars,
        del: typing.del,
        dur: Math.round(typing.last - typing.start),
        page: typing.page
      });
      typing = null;
    }

    // ------------------------------------------------------------ AI prompt submission
    function findPromptBox(el) {
      if (!(el instanceof Element)) return null;
      const box = el.closest('textarea,[contenteditable="true"],[role=textbox],input[type=text],input:not([type])');
      if (!box || box.closest('.monaco-editor,.cm-editor')) return null;
      if (box.closest('[data-ux-prompt]')) return box;
      const near = box.closest('[data-testid]');
      const hints = [
        box.getAttribute('aria-label'),
        box.getAttribute('placeholder'),
        box.getAttribute('data-testid'),
        near && near.getAttribute('data-testid')
      ].filter(Boolean).join(' ');
      return PROMPT_HINT.test(hints) ? box : null;
    }

    function findPromptBoxNear(el) {
      let n = el;
      for (let i = 0; i < 6 && n; i++, n = n.parentElement) {
        const cands = n.querySelectorAll('textarea,[contenteditable="true"],[role=textbox],input[type=text]');
        for (let j = 0; j < cands.length; j++) if (findPromptBox(cands[j])) return cands[j];
      }
      return null;
    }

    async function saltedHash(text) {
      try {
        const data = new TextEncoder().encode(((S && S.salt) || '') + ':' + text);
        const digest = await crypto.subtle.digest('SHA-256', data);
        return Array.prototype.slice.call(new Uint8Array(digest), 0, 8).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
      } catch (_) {
        return null;
      }
    }

    function submitPrompt(box, how) {
      const text = String('value' in box ? box.value : box.innerText || '').trim(); // read before the UI clears it
      if (!text) return;
      const t = Date.now();
      const settings = S;
      // goal/turn are read now: the page may advance the turn before the hash resolves
      const at = { goal: (settings && settings.goalId) || null, turn: settings && settings.turnId != null ? settings.turnId : null };
      let extra = {};
      if (promptMeta) { try { extra = promptMeta(text, at) || {}; } catch (_) { extra = {}; } }
      delete extra.text;
      saltedHash(text).then(function (hash) {
        emitAt(t, 'prompt_submit', Object.assign({}, extra, {
          goal: at.goal,
          turn: at.turn,
          how: how,
          chars: text.length,
          words: text.split(/\s+/).length,
          hash: hash,
          text: settings && settings.captureText ? text : undefined
        }));
      });
    }

    // ------------------------------------------------------------ listeners
    function attach() {
      every(function () { flush(false); }, CFG.flushMs);

      every(function () {
        if (!idle && performance.now() - lastActivity > CFG.idleMs) {
          idle = true;
          emit('idle_start', {});
        }
      }, 1000);

      every(function () {
        if (typing && performance.now() - typing.last > CFG.typingGapMs) flushTyping();
      }, 500);

      // Databricks-style SPAs: poll the route instead of patching history from an isolated world.
      every(function () {
        const route = location.pathname + location.hash;
        if (route === lastRoute) return;
        const from = lastRoute;
        lastRoute = route;
        pageKind = classifyPage(location.pathname);
        emit('navigate', { from: from, to: route });
      }, 500);

      // mouse move + hover dwell
      let lastMove = { t: 0, x: 0, y: 0 };
      on(window, 'mousemove', function (e) {
        noteActivity();
        const now = performance.now();
        const key = regionKey(e.target);
        if (key !== hover.key) {
          closeHover(now);
          hover = { key: key, since: now };
        }
        if (now - lastMove.t < CFG.mouseSampleMs) return;
        const dist = Math.hypot(e.clientX - lastMove.x, e.clientY - lastMove.y);
        if (dist < CFG.mouseMinDistPx) return;
        const dt = now - lastMove.t || 1;
        lastMove = { t: now, x: e.clientX, y: e.clientY };
        emit('mouse_move', { x: e.clientX, y: e.clientY, v: Math.round((dist / dt) * 1000) });
      }, { capture: true, passive: true });
      on(document, 'mouseleave', function () { closeHover(performance.now()); });

      // scroll
      on(window, 'scroll', function (e) {
        noteActivity();
        const t = e.target;
        pendingScroll = t === document || t === window ? document.documentElement : t;
        if (!(pendingScroll instanceof Element)) return;
        if (scrollTimer) return;
        const wait = Math.max(0, CFG.scrollSampleMs - (performance.now() - lastScrollEmit));
        scrollTimer = setTimeout(emitScroll, wait);
      }, { capture: true, passive: true });

      // clicks + rage clicks
      let recentClicks = [];
      function onPointer(e) {
        noteActivity();
        const d = describe(e.target);
        emit(e.type, Object.assign({ x: e.clientX, y: e.clientY, btn: e.button }, d));
        if (e.type !== 'click') return;
        const now = performance.now();
        recentClicks = recentClicks.filter(function (c) { return now - c.t < CFG.rageWindowMs; });
        recentClicks.push({ t: now, x: e.clientX, y: e.clientY });
        const near = recentClicks.filter(function (c) { return Math.hypot(c.x - e.clientX, c.y - e.clientY) <= CFG.rageRadiusPx; });
        if (near.length >= CFG.rageClicks) {
          emit('rage_click', Object.assign({ x: e.clientX, y: e.clientY, n: near.length }, d));
          recentClicks = [];
        }
        if (d.action === 'send') {
          const box = findPromptBoxNear(e.target);
          if (box) submitPrompt(box, 'click');
        }
      }
      ['click', 'dblclick', 'contextmenu'].forEach(function (type) {
        on(window, type, onPointer, { capture: true, passive: true });
      });

      // keyboard (never key content)
      on(window, 'keydown', function (e) {
        if (e.target instanceof Element && e.target.matches('input[type=password]')) return;
        noteActivity();
        if (e.key === 'Meta' || e.key === 'Control' || e.key === 'Alt' || e.key === 'Shift') return;
        const ctx = ctxOf(e.target);
        const mod = e.metaKey || e.ctrlKey || e.altKey;
        const special = mod || e.key === 'Enter' || e.key === 'Escape' || e.key === 'Tab';
        if (special) {
          const combo = [e.metaKey && 'meta', e.ctrlKey && 'ctrl', e.altKey && 'alt', e.shiftKey && 'shift', e.key.length === 1 ? e.key.toLowerCase() : e.key]
            .filter(Boolean).join('+');
          emit('key', { combo: combo, ctx: ctx });
        } else if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete') {
          const now = performance.now();
          if (typing && (typing.ctx !== ctx || now - typing.last > CFG.typingGapMs)) flushTyping();
          if (!typing) typing = { ctx: ctx, start: now, last: now, chars: 0, del: 0, wall: Date.now(), page: pageKind };
          typing.last = now;
          if (e.key.length === 1) typing.chars++; else typing.del++;
        }
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          const box = findPromptBox(e.target);
          if (box) submitPrompt(box, 'enter');
        }
      }, true);

      // paste: where and how long, never the content (the text is read only to measure its length)
      on(window, 'paste', function (e) {
        if (e.target instanceof Element && e.target.matches('input[type=password]')) return;
        noteActivity();
        let n = null;
        try { n = ((e.clipboardData && e.clipboardData.getData('text')) || '').length; } catch (_) { n = null; }
        emit('paste', { ctx: ctxOf(e.target), chars: n });
      }, true);

      // visibility, focus, viewport
      on(document, 'visibilitychange', function () {
        emit('visibility', { state: document.visibilityState });
        if (document.visibilityState === 'hidden') flush();
      });
      on(window, 'focus', function () { emit('window_focus', {}); });
      on(window, 'blur', function () { emit('window_blur', {}); });
      on(window, 'pagehide', function () { flush(); });
      let resizeT = null;
      on(window, 'resize', function () {
        clearTimeout(resizeT);
        resizeT = setTimeout(function () { emit('viewport', { w: innerWidth, h: innerHeight, dpr: devicePixelRatio }); }, 300);
      });
    }

    // ------------------------------------------------------------ public API
    function vp() { return { w: innerWidth, h: innerHeight, dpr: devicePixelRatio }; }

    function update(next, opts) {
      const old = S;
      next = next || null;
      if (old && old.enabled && (!next || !next.enabled || next.sessionId !== old.sessionId)) {
        emit('session_end', {});
        flush();
      }
      S = next;
      if (next && next.enabled) {
        if (opts && opts.initial && !old) emit('page_load', vp());
        else if (!old || !old.enabled || old.sessionId !== next.sessionId) emit('session_start', vp());
      }
    }

    function setTask(taskId, meta) {
      meta = meta || {};
      S = Object.assign({}, S, { taskId: taskId, taskCategory: meta.category || null });
      taskStartWall = Date.now();
      emit('task_start', { prompt: meta.prompt === undefined ? undefined : String(meta.prompt).slice(0, 200) });
    }

    // Outcome of a task trial: status 'correct' | 'incorrect' | 'abandoned' | 'unknown';
    // satisfaction: optional 1-5 self-report; answer: optional user-supplied answer.
    function outcome(o) {
      o = o || {};
      emit('outcome', {
        status: o.status || 'unknown',
        satisfaction: o.satisfaction === undefined ? null : o.satisfaction,
        answer: o.answer === undefined ? undefined : String(o.answer).slice(0, 200),
        dur: taskStartWall ? Date.now() - taskStartWall : null
      });
      flush();
    }

    // Goal = open-ended need worked on with an assistant. meta: {categories: [...Amar tasks], prompt}. Turn ids restart at 1.
    function setGoal(goalId, meta) {
      meta = meta || {};
      S = Object.assign({}, S, { goalId: goalId || null, goalCats: (meta.categories || []).join('|') || null, turnId: goalId ? 1 : null });
      goalStartWall = goalId ? Date.now() : null;
      if (goalId) emit('goal_start', { prompt: meta.prompt === undefined ? undefined : String(meta.prompt).slice(0, 200) });
    }
    function setTurn(n) { S = Object.assign({}, S, { turnId: n == null ? null : n }); }

    // Outcome of a goal: status 'correct' | 'incorrect' | 'abandoned'; satisfaction 1-5; answer: the final answer;
    // turn: the assistant turn whose answer the participant submitted (null if they typed their own).
    function goalOutcome(o) {
      o = o || {};
      emit('goal_outcome', {
        status: o.status || 'unknown',
        satisfaction: o.satisfaction === undefined ? null : o.satisfaction,
        answer: o.answer === undefined ? undefined : String(o.answer).slice(0, 200),
        turn: o.turn === undefined ? null : o.turn,
        answer_id: o.answerId === undefined ? undefined : o.answerId,
        dur: goalStartWall ? Date.now() - goalStartWall : null
      });
      flush();
    }

    // Consent for prompt text can be given (or withdrawn) during the session; recorded as a 'consent' event.
    function setCaptureText(on) {
      S = Object.assign({}, S, { captureText: on === true });
      emit('consent', { state: on === true ? 'prompt_text' : 'no_prompt_text' });
    }

    function setPage(name) { pageKind = name; }
    function mark(name, data) { emit('custom', Object.assign({ name: name }, data)); }

    function start() {
      if (started) return api;
      started = true;
      attach();
      return api;
    }
    function stop() {
      if (!started) return;
      flush();
      while (disposers.length) disposers.pop()();
      started = false;
    }

    const api = {
      start: start, stop: stop, update: update, flush: flush,
      emit: emit, mark: mark, setTask: setTask, outcome: outcome, setPage: setPage,
      setGoal: setGoal, setTurn: setTurn, goalOutcome: goalOutcome, setCaptureText: setCaptureText,
      settings: function () { return S; }
    };
    return api;
  }

  // ---------------------------------------------------------------- SDK facade
  function uuid() {
    if (root.crypto && root.crypto.randomUUID) return root.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  /**
   * UXTelemetry.init({ endpoint, appId, consent: true, sessionType, participantId, taskId, captureText, salt, heuristics, cfg })
   * `consent: true` is required; without it nothing is recorded.
   */
  function init(opts) {
    opts = opts || {};
    const settings = {
      enabled: opts.consent === true,
      sessionId: opts.sessionId || uuid(),
      sessionType: opts.sessionType || 'human',
      appId: opts.appId || null,
      taskId: opts.taskId || '',
      taskCategory: opts.taskCategory || null,
      participantId: opts.participantId || '',
      captureText: opts.captureText === true,
      salt: opts.salt || opts.appId || ''
    };
    const sink = opts.sink || (opts.endpoint ? httpSink(opts.endpoint) : function () {});
    const rec = create({ sink: sink, settings: null, heuristics: opts.heuristics, cfg: opts.cfg, promptMeta: opts.promptMeta });
    rec.start();
    rec.update(settings); // emits session_start when enabled
    return rec;
  }

  function httpSink(endpoint) {
    return function (batch) {
      const body = JSON.stringify(batch);
      if (typeof fetch === 'function') {
        fetch(endpoint, { method: 'POST', headers: { 'content-type': 'application/json' }, body: body, keepalive: true }).catch(function () {});
      } else if (navigator.sendBeacon) {
        navigator.sendBeacon(endpoint, body);
      }
    };
  }

  root.UXTelemetry = { create: create, init: init, adapters: {}, version: '0.3.0' };
})(typeof globalThis !== 'undefined' ? globalThis : window);
