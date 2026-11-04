// Small SVG helpers. Marks follow one spec: 2px lines, 8px dots with a surface ring, hairline
// solid grid, labels in text colours, one y axis per chart, and a table twin for every chart.
import { h, s, isNum } from './util.js';

export const COLOR = {
  blue: '#1C5A87', grey: '#8D8474', ink: '#1E1B16', ink3: '#635C50', rule: '#D5CBB8',
  paper: '#F6F1E7', l1: '#D9932A', l2: '#B85419', l3: '#7C2512',
};

export const scale = (d0, d1, r0, r1) => {
  const span = d1 - d0 || 1;
  return (v) => r0 + ((v - d0) / span) * (r1 - r0);
};

export function niceMax(v) {
  if (!(v > 0)) return 1;
  const mag = 10 ** Math.floor(Math.log10(v));
  const n = v / mag;
  const step = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((c) => c >= n);
  return step * mag;
}

export function ticks(lo, hi, count = 4) {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((c) => c >= raw) ?? raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

// Path through points, lifting the pen over gaps so missing values never draw a false line.
export function linePath(points) {
  let d = '';
  let pen = false;
  for (const [x, y] of points) {
    if (!isNum(x) || !isNum(y)) { pen = false; continue; }
    d += `${pen ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function bandPath(top, bottom) {
  const pts = top.map((p, i) => [p, bottom[i]]).filter(([a, b]) => isNum(a[1]) && isNum(b[1]));
  if (!pts.length) return '';
  const up = pts.map(([a]) => `${a[0].toFixed(1)} ${a[1].toFixed(1)}`).join('L');
  const down = pts.reverse().map(([, b]) => `${b[0].toFixed(1)} ${b[1].toFixed(1)}`).join('L');
  return `M${up}L${down}Z`;
}

// Redraws on width changes only, so a chart never loops on its own height. Below MIN_CHART_WIDTH
// there is nothing useful to draw, and the page keeps the last good picture until it widens.
const MIN_CHART_WIDTH = 120;
export function responsive(host, draw) {
  let last = 0;
  const run = () => {
    const w = Math.round(host.clientWidth);
    if (w >= MIN_CHART_WIDTH && w !== last) {
      last = w;
      draw(w);
    }
  };
  new ResizeObserver(run).observe(host);
  run();
  return () => { last = 0; run(); };
}

const tipEl = () => document.getElementById('tip');
export function showTip(x, y, rows) {
  const tip = tipEl();
  tip.replaceChildren(...rows.map((r) => (typeof r === 'string'
    ? h('div', { class: 'tip-head', text: r })
    : h('div', { class: 'tip-row' },
      r.color ? h('span', { class: 'tip-key', style: { background: r.color } }) : null,
      h('strong', { text: r.value }),
      h('span', { text: r.label })))));
  tip.hidden = false;
  const box = tip.getBoundingClientRect();
  const left = Math.min(window.innerWidth - box.width - 8, Math.max(8, x + 14));
  const top = y + box.height + 22 > window.innerHeight ? y - box.height - 12 : y + 14;
  tip.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
}
export const hideTip = () => { tipEl().hidden = true; };

// The WCAG-clean twin of a chart: same numbers, no pointer needed.
export function tableTwin(caption, columns, rows, { open = false } = {}) {
  return h('details', { class: 'twin', open },
    h('summary', { text: 'Show the numbers as a table' }),
    dataTable(caption, columns, rows));
}

export function dataTable(caption, columns, rows, foot) {
  return h('div', { class: 'table-scroll' },
    h('table', { class: 'data' },
      caption ? h('caption', { class: 'vh', text: caption }) : null,
      h('thead', null, h('tr', null, columns.map((c) => h('th', { scope: 'col', class: c.num ? 'num' : null, text: c.label })))),
      h('tbody', null, rows.map((r) => h('tr', null, columns.map((c) => {
        const v = c.cell ? c.cell(r) : r[c.key];
        return h('td', { class: c.num ? 'num' : null }, v instanceof Node ? v : String(v ?? ''));
      })))),
      foot ? h('tfoot', null, foot) : null));
}

// Legend for two or more series, mirroring the mark: a short line for a line.
export function seriesKey(series) {
  return h('ul', { class: 'key' }, series.map((c) => h('li', null,
    h('span', { class: 'key-line', style: { background: c.color } }),
    h('span', { text: c.name }))));
}

// Line chart with shared crosshair. series: [{name, color, points: [[x, y]], width}]
export function lineChart(host, { series, xValues, xLabel, xFormat = String, yMax, yMin = 0, yFormat = String, yLabel, height = 190 }) {
  host.classList.add('chart');
  const body = h('div');
  host.append(seriesKey(series), body);
  responsive(body, (w) => {
    const m = { t: 20, r: 18, b: 34, l: 40 };
    const x = scale(xValues[0], xValues[xValues.length - 1], m.l, w - m.r);
    const y = scale(yMin, yMax, height - m.b, m.t);
    const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img', 'aria-label': `${yLabel} by ${xLabel}` });
    if (yLabel) svg.append(s('text', { x: 0, y: 11, class: 'ax-title', text: yLabel }));
    for (const t of ticks(yMin, yMax, 4)) {
      svg.append(
        s('line', { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t), class: 'grid' }),
        s('text', { x: m.l - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'ax', text: yFormat(t) }));
    }
    for (const v of xValues) {
      svg.append(s('text', { x: x(v), y: height - m.b + 15, 'text-anchor': 'middle', class: 'ax', text: xFormat(v) }));
    }
    svg.append(s('text', { x: (m.l + w - m.r) / 2, y: height - 3, 'text-anchor': 'middle', class: 'ax', text: xLabel }));
    for (const c of series) {
      const pts = c.points.map(([a, b]) => [x(a), isNum(b) ? y(b) : null]);
      svg.append(s('path', { d: linePath(pts), fill: 'none', stroke: c.color, 'stroke-width': c.width ?? 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      for (const [px, py] of pts) {
        if (isNum(py)) svg.append(s('circle', { cx: px, cy: py, r: 4, fill: c.color, stroke: COLOR.paper, 'stroke-width': 2 }));
      }
    }
    const cross = s('line', { y1: m.t, y2: height - m.b, class: 'cross', visibility: 'hidden' });
    svg.append(cross);
    const pick = (e) => {
      const px = e.clientX - svg.getBoundingClientRect().left;
      const near = xValues.reduce((a, b) => (Math.abs(x(b) - px) < Math.abs(x(a) - px) ? b : a));
      cross.setAttribute('x1', x(near));
      cross.setAttribute('x2', x(near));
      cross.setAttribute('visibility', 'visible');
      showTip(e.clientX, e.clientY, [xFormat(near), ...series.map((c) => {
        const hit = c.points.find(([a]) => a === near);
        return { color: c.color, value: yFormat(hit?.[1]), label: c.name };
      })]);
    };
    svg.addEventListener('pointermove', pick);
    svg.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
    body.replaceChildren(svg);
  });
}

// One bar per row, on one baseline. rows: [{label, value, text, strong}]
export function barList(rows, { max, label }) {
  const top = max ?? Math.max(...rows.map((r) => r.value ?? 0), 1e-9);
  return h('ul', { class: 'bars', 'aria-label': label }, rows.map((r) => h('li', { class: r.strong ? 'is-strong' : null },
    h('span', { class: 'bars-label', text: r.label }),
    h('span', { class: 'bars-track' }, h('span', { class: 'bars-fill', style: { width: `${Math.max(0, Math.min(100, ((r.value ?? 0) / top) * 100))}%` } })),
    h('span', { class: 'bars-value', text: r.text }))));
}
