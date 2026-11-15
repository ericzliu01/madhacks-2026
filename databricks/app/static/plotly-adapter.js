/*!
 * uxtelemetry Plotly adapter -- chart-mark level events that DOM listeners cannot see.
 * Load AFTER uxtelemetry.js. Usage:
 *   const detach = UXTelemetry.adapters.plotly(recorder, plotDiv, { chartId: 'trips-by-hour' });
 *
 * Events: chart_hover {dur, series, i, x, y}, chart_click, chart_legend_click, chart_legend_dblclick,
 *         chart_relayout {keys} (zoom / pan / axis change), chart_select {n}, chart_reset.
 * Set { redactValues: true } to omit x/y data values.
 */
(function (root) {
  'use strict';
  const UX = root.UXTelemetry;
  if (!UX) throw new Error('Load uxtelemetry.js before plotly-adapter.js');

  UX.adapters.plotly = function attach(rec, gd, opts) {
    opts = opts || {};
    const chart = opts.chartId || gd.id || 'chart';
    const minHoverMs = opts.minHoverMs || 150;
    let hover = null;

    function point(p) {
      const info = { chart: chart, series: (p.data && p.data.name) || null, i: p.pointNumber };
      if (!opts.redactValues) { info.x = p.x; info.y = p.y; }
      return info;
    }
    function closeHover() {
      if (!hover) return;
      const dur = Math.round(performance.now() - hover.t);
      if (dur >= minHoverMs) rec.emit('chart_hover', Object.assign({ dur: dur }, hover.info));
      hover = null;
    }

    const handlers = {
      plotly_hover: function (ev) {
        const p = ev.points && ev.points[0];
        if (!p) return;
        const key = p.curveNumber + ':' + p.pointNumber;
        if (hover && hover.key === key) return;
        closeHover();
        hover = { key: key, t: performance.now(), info: point(p) };
      },
      plotly_unhover: closeHover,
      plotly_click: function (ev) {
        const p = ev.points && ev.points[0];
        if (p) rec.emit('chart_click', point(p));
      },
      plotly_legendclick: function (ev) {
        const tr = ev.data && ev.data[ev.curveNumber];
        rec.emit('chart_legend_click', { chart: chart, series: (tr && tr.name) || null });
      },
      plotly_legenddoubleclick: function (ev) {
        const tr = ev.data && ev.data[ev.curveNumber];
        rec.emit('chart_legend_dblclick', { chart: chart, series: (tr && tr.name) || null });
      },
      plotly_relayout: function (ev) { rec.emit('chart_relayout', { chart: chart, keys: Object.keys(ev || {}).slice(0, 6) }); },
      plotly_selected: function (ev) { rec.emit('chart_select', { chart: chart, n: ev && ev.points ? ev.points.length : 0 }); },
      plotly_doubleclick: function () { rec.emit('chart_reset', { chart: chart }); }
    };

    // NOTE: handlers must not return false -- Plotly treats that as "cancel the default action".
    Object.keys(handlers).forEach(function (name) {
      const fn = handlers[name];
      gd.on(name, function (ev) { fn(ev); });
    });

    return function detach() {
      closeHover();
      Object.keys(handlers).forEach(function (name) { gd.removeAllListeners(name); });
    };
  };
})(typeof globalThis !== 'undefined' ? globalThis : window);
