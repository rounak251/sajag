// Scrubber. A native range input does the seeking, so keyboard, touch and screen readers work for
// free; the SVG beneath it is only the picture.
import { h, s, fmtShort, fmtMedium, fmtMonthName, dayOfMonth, plural } from './util.js';
import { COLOR, linePath, niceMax, scale, showTip, hideTip, ticks } from './charts.js';

const PLOT_H = 74;
const AXIS_H = 20;
const TOP = 22;

export function createTimeline(host, { getH, getWindow, getIndex, onSeek, onTogglePlay, zoomControl }) {
  const play = h('button', { type: 'button', class: 'btn btn-play', id: 'play', onclick: onTogglePlay, text: 'Play' });
  const zoom = h('div', { class: 'tl-zoom' });
  const title = h('p', { class: 'tl-title', text: 'Districts at Warning or above, as a share of all districts' });
  const plot = h('div', { class: 'tl-plot' });
  const art = h('div', { class: 'tl-art' });
  const marks = h('div', { class: 'tl-marks' });
  const range = h('input', { type: 'range', id: 'scrub', min: 0, max: 1, value: 0, step: 1, 'aria-label': 'Date' });
  plot.append(art, range, marks);
  host.append(h('div', { class: 'tl-side' }, play, zoom), h('div', { class: 'tl-main' }, title, plot));

  let x = (v) => v;
  let a = 0;
  let b = 1;
  let cursor = null;
  let pastClip = null;

  range.addEventListener('input', () => onSeek(Number(range.value)));
  range.addEventListener('pointermove', (e) => {
    const H = getH();
    if (!H) return;
    const box = range.getBoundingClientRect();
    const i = Math.round(a + ((e.clientX - box.left) / box.width) * (b - a));
    const iso = H.dates[Math.max(a, Math.min(b, i))];
    const share = H.statewide?.[Math.max(a, Math.min(b, i))];
    showTip(e.clientX, box.top - 4, [fmtMedium(iso), { color: COLOR.l2, value: `${Math.round((share ?? 0) * 100)}%`, label: 'of districts at Warning or above' }]);
  });
  range.addEventListener('pointerleave', hideTip);

  function draw() {
    const H = getH();
    if (!H) return;
    [a, b] = getWindow();
    const w = Math.max(200, Math.round(plot.clientWidth));
    const height = TOP + PLOT_H + AXIS_H;
    const top = niceMax(Math.max(...(H.statewide ?? [0]), 0.05));
    x = scale(a, b, 1, w - 1);
    const y = scale(0, top, TOP + PLOT_H, TOP);
    const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, 'aria-hidden': 'true' });
    for (const t of ticks(0, top, 2)) {
      svg.append(s('line', { x1: 0, x2: w, y1: y(t), y2: y(t), class: 'grid' }));
      if (t > 0) svg.append(s('text', { x: 2, y: y(t) - 3, class: 'ax', text: `${Math.round(t * 100)}%` }));
    }
    const pts = [];
    for (let i = a; i <= b; i += 1) pts.push([x(i), y(H.statewide?.[i] ?? 0)]);
    const area = `${linePath(pts)}L${x(b)} ${y(0)}L${x(a)} ${y(0)}Z`;
    const id = `tl-clip-${a}-${b}`;
    pastClip = s('rect', { x: 0, y: 0, width: 0, height });
    svg.append(
      s('defs', null, s('clipPath', { id }, pastClip)),
      s('path', { d: area, fill: COLOR.l2, opacity: 0.1 }),
      s('path', { d: linePath(pts), fill: 'none', stroke: COLOR.l2, 'stroke-width': 1.25, opacity: 0.5 }),
      s('g', { 'clip-path': `url(#${id})` },
        s('path', { d: area, fill: COLOR.l2, opacity: 0.26 }),
        s('path', { d: linePath(pts), fill: 'none', stroke: COLOR.l2, 'stroke-width': 2, 'stroke-linejoin': 'round' })));

    // Date axis: days inside a story window, months across a season.
    const span = b - a;
    const every = span <= 34 ? 5 : null;
    let lastX = -99;
    for (let i = a; i <= b; i += 1) {
      const iso = H.dates[i];
      const newMonth = dayOfMonth(iso) === 1;
      const show = every ? (newMonth || dayOfMonth(iso) % every === 0) : newMonth;
      if (!show || x(i) - lastX < 40) continue;
      lastX = x(i);
      svg.append(
        s('line', { x1: x(i), x2: x(i), y1: TOP + PLOT_H, y2: TOP + PLOT_H + 4, class: 'axis-tick' }),
        s('text', { x: x(i), y: height - 4, 'text-anchor': i === a ? 'start' : 'middle', class: 'ax', text: every ? fmtShort(iso) : fmtMonthName(iso) }));
    }
    svg.append(s('line', { x1: 0, x2: w, y1: TOP + PLOT_H, y2: TOP + PLOT_H, class: 'axis' }));
    cursor = s('g', { class: 'tl-cursor' },
      s('line', { y1: 8, y2: TOP + PLOT_H, stroke: COLOR.ink, 'stroke-width': 1.5 }),
      s('rect', { x: -5, y: TOP + PLOT_H - 5, width: 10, height: 10, fill: COLOR.ink, stroke: COLOR.paper, 'stroke-width': 2 }));
    svg.append(cursor);
    art.replaceChildren(svg);

    range.min = a;
    range.max = b;
    range.style.height = `${TOP + PLOT_H + AXIS_H}px`;

    // Floods that really happened. Buttons, so they can be reached and jumped to from the keyboard.
    marks.replaceChildren();
    let lastEdge = -Infinity;
    for (const e of H.events) {
      if (e.i < a || e.i > b) continue;
      const left = x(e.i);
      const said = `${fmtMedium(e.start)}: ${e.label}, ${plural(e.keys.length, 'district')} on record`;
      const mark = h('button', {
        type: 'button', class: 'tl-mark', style: { left: `${left}px` }, 'aria-label': `Go to ${said}`,
        onclick: () => onSeek(e.i, true),
        onpointermove: (ev) => showTip(ev.clientX, ev.clientY, [fmtMedium(e.start), e.label, { value: String(e.keys.length), label: 'districts on record' }]),
        onpointerleave: hideTip,
      });
      marks.append(mark);
      if (span <= 40 && w > 420) {
        const text = h('span', { class: 'tl-mark-text', text: e.label });
        mark.append(text);
        const room = w - left;
        const width = e.label.length * 6.4 + 10;
        if (left - width / 2 > lastEdge) {
          if (width > room) mark.classList.add('flip');
          lastEdge = left + width;
        } else {
          text.remove();
        }
      }
    }
    zoom.replaceChildren(zoomControl() ?? '');
    move();
  }

  function move() {
    const H = getH();
    if (!H || !cursor) return;
    const i = getIndex();
    const px = x(Math.max(a, Math.min(b, i)));
    cursor.setAttribute('transform', `translate(${px} 0)`);
    pastClip.setAttribute('width', Math.max(0, px));
    range.value = i;
    const n = H.level?.[i]?.filter((v) => v >= 2).length ?? 0;
    range.setAttribute('aria-valuetext', `${fmtMedium(H.dates[i])}. ${n} of ${H.districts.length} districts at Warning or above.`);
  }

  new ResizeObserver(() => draw()).observe(plot);
  return {
    draw, move,
    setPlaying(playing, atEnd) {
      play.textContent = playing ? 'Pause' : atEnd ? 'Replay' : 'Play';
      play.setAttribute('aria-pressed', String(playing));
    },
  };
}
