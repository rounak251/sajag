// What sits on the map: the date block, the "what it said before" card and the legend.
import { ctx, beforeMatrix, droughtMonthIndex, isHeldOut, levelOf, districtName } from './data.js';
import { state } from './state.js';
import { h, s, put, bilingual, fmtLong, fmtMedium, fmtMonthYear, isNum, plural } from './util.js';
import { showTip, hideTip } from './charts.js';
import { DROUGHT_CLASSES, LEVEL_FILL, droughtClass } from './map.js';

export const swatch = (fill, size = 14) => s('svg', { class: 'swatch', width: size, height: size, 'aria-hidden': 'true' },
  s('rect', { width: size, height: size, fill, stroke: '#6B6354', 'stroke-width': 1 }));

export function levelChip(id) {
  return h('span', { class: 'chip' }, swatch(LEVEL_FILL[id] ?? LEVEL_FILL[0]), bilingual(levelOf(id)));
}

// One row per lead, one square per flooded district: the level it stood at that many days before.
function beforeCard(H, event) {
  const m = beforeMatrix(H, event);
  const last = m.rows[m.rows.length - 1];
  const weight = new Map(event.keys.map((k) => [k, m.rows.reduce((t, r) => t + (r.cells.find((c) => c.key === k)?.level ?? 0), 0)]));
  const order = [...event.keys].sort((a, b) => weight.get(b) - weight.get(a));
  const size = Math.max(4, Math.min(11, Math.floor(140 / order.length) - 2));
  const rows = m.rows.map((row) => {
    const flagged = row.cells.filter((c) => c.level >= 1).length;
    const cells = new Map(row.cells.map((c) => [c.key, c]));
    const art = s('svg', { width: order.length * (size + 2), height: size, role: 'img', 'aria-label': `${flagged} of ${m.total} districts at Watch or above` },
      order.map((key, n) => {
        const c = cells.get(key);
        return s('rect', {
          x: n * (size + 2), y: 0, width: size, height: size, fill: LEVEL_FILL[c.level] ?? LEVEL_FILL[0], stroke: '#6B6354', 'stroke-width': 0.6,
          onpointermove: (e) => showTip(e.clientX, e.clientY, [districtName(key), { value: levelOf(c.level).en, label: `${row.days} ${row.days === 1 ? 'day' : 'days'} before` }]),
          onpointerleave: hideTip,
        });
      }));
    return h('tr', null,
      h('th', { scope: 'row', text: `${row.days} ${row.days === 1 ? 'day' : 'days'}` }),
      h('td', null, art),
      h('td', { class: 'num', text: `${flagged} of ${m.total}` }));
  });
  return h('div', { class: 'ev', id: 'event-card' },
    h('p', { class: 'ev-kicker', text: 'Flood on record' }),
    h('p', { class: 'ev-title', text: event.label }),
    h('p', { class: 'ev-sub' },
      `First ${event.source === 'press' ? 'reported' : 'recorded'} ${fmtMedium(event.start)}. ${plural(event.keys.length, 'district')} outlined in blue. `,
      event.url ? h('a', { href: event.url, target: '_blank', rel: 'noopener', text: 'Source' }) : null),
    last ? h('table', { class: 'ev-grid' },
      h('caption', { text: 'At Watch or above before first report' }),
      h('tbody', null, rows)) : null);
}

export function renderHead(host) {
  const H = ctx.H;
  if (!H) return;
  const iso = H.dates[state.i];
  const total = H.districts.length;
  const heldOut = isHeldOut(H.year, H);
  const tags = h('p', { class: 'mh-tags' },
    h('span', { class: 'tag', text: 'Replay of past data' }),
    heldOut ? h('span', { class: 'tag tag-blind', id: 'heldout-tag', text: `Not in training data. Tuned after seeing ${H.year}, see Evidence` }) : null);

  if (state.layer === 'drought' && ctx.drought) {
    const D = ctx.drought;
    const m = droughtMonthIndex(D, iso);
    const row = D.spi3?.[m] ?? [];
    const dry = row.filter((v) => isNum(v) && v <= -1).length;
    put(host, tags,
      h('p', { class: 'mh-date', id: 'map-date', text: fmtMonthYear(D.months[m]) }),
      h('p', { class: 'mh-sum', text: `${dry} of ${row.length} districts in drought, with SPI-3 at or below −1.` }));
    return;
  }

  const counts = H.counts(state.i);
  const warn = counts.slice(2).reduce((a, b) => a + b, 0);
  const watch = counts.slice(1).reduce((a, b) => a + b, 0);
  const active = H.activeEvents(state.i);
  put(host, tags,
    h('p', { class: 'mh-date', id: 'map-date', text: fmtLong(iso) }),
    h('p', { class: 'mh-sum', text: warn
      ? `${warn} of ${total} districts at Warning or above. ${watch} at Watch or above.`
      : watch ? `${watch} of ${total} districts at Watch. None at Warning.` : `All ${total} districts Normal.` }),
    active.length ? beforeCard(H, active[active.length - 1]) : null);
}

export function renderLegend(host) {
  const H = ctx.H;
  if (!H) return;
  const row = (mark, label, value) => h('li', null, mark, h('span', { class: 'lg-label' }, label),
    value === undefined ? null : h('span', { class: 'lg-n', text: String(value) }));
  if (state.layer === 'drought' && ctx.drought) {
    const D = ctx.drought;
    const m = droughtMonthIndex(D, H.dates[state.i]);
    const counts = new Map();
    for (const v of D.spi3?.[m] ?? []) if (isNum(v)) counts.set(droughtClass(v).id, (counts.get(droughtClass(v).id) ?? 0) + 1);
    put(host, h('p', { class: 'lg-title', text: 'SPI-3, three-month rainfall' }),
      h('ul', { class: 'lg' }, DROUGHT_CLASSES.map((c) => row(swatch(c.fill), `${c.label} (${c.range})`, counts.get(c.id) ?? 0))));
    return;
  }
  const counts = H.counts(state.i);
  put(host,
    h('p', { class: 'lg-title', text: 'Flood level' }),
    h('ul', { class: 'lg' }, [...ctx.levels].reverse().map((l) => row(swatch(LEVEL_FILL[l.id] ?? LEVEL_FILL[0]), bilingual(l), counts[l.id] ?? 0))),
    h('ul', { class: 'lg lg-marks' },
      row(h('span', { class: 'mk mk-flood' }), 'Flood on record'),
      ctx.rivers ? row(h('span', { class: 'mk mk-river' }), 'River') : null,
      ctx.sites.length ? row(h('span', { class: 'mk mk-gauge' }), 'Gauge') : null,
      ctx.sites.length ? row(h('span', { class: 'mk mk-gauge is-high' }), 'Gauge above p95') : null,
      state.district && h('li', { class: 'lg-villages' }, h('span', { class: 'mk mk-village' }), h('span', { class: 'lg-label', text: 'Village, larger and darker is more exposed' }))),
    h('p', { class: 'lg-note' }, 'Figures on the map: chance of flood within ', h('strong', { text: `${state.lead} ${state.lead === '1' ? 'day' : 'days'}` }), ctx.H?.rain_forecast_used ? ', or forecast rain in mm where the forecast set the level.' : '.'));
}
