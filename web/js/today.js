// Today: what the system says now, from live.json and the latest month of drought.json.
import { ctx, districtName, levelOf } from './data.js';
import { h, s, put, bilingual, fmtInt, fmtLong, fmtMonthYear, fmtPct, fmtShort, fmtSigned, isNum, plural } from './util.js';
import { COLOR, bandPath, dataTable, hideTip, linePath, niceMax, responsive, scale, showTip, tableTwin, ticks } from './charts.js';
import { DROUGHT_CLASSES, LEVEL_FILL, LAND, droughtClass } from './map.js';
import { levelChip, swatch } from './overlay.js';

const STATUS = {
  extreme: { rank: 0, label: 'Extreme, above p99' },
  high: { rank: 1, label: 'High, above p95' },
  normal: { rank: 2, label: 'Normal' },
};

// A static map for a printed feel: no pan or zoom needed for one month of 38 districts.
function miniMap(host, fillFor, tipFor) {
  const geo = ctx.geo;
  const pts = [];
  const rings = (g) => (g.type === 'Polygon' ? g.coordinates : g.coordinates.flat());
  for (const f of geo.features) for (const r of rings(f.geometry)) pts.push(...r);
  const lons = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  const k = Math.cos(((y0 + y1) / 2) * (Math.PI / 180));
  responsive(host, (w) => {
    const height = Math.round((w * (y1 - y0)) / ((x1 - x0) * k));
    const x = scale(x0, x1, 2, w - 2);
    const y = scale(y0, y1, height - 2, 2);
    const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img', 'aria-label': 'Map of Bihar by district' });
    for (const f of geo.features) {
      const key = f.properties?.key;
      const d = rings(f.geometry).map((r) => `M${r.map((p) => `${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join('L')}Z`).join('');
      svg.append(s('path', {
        d, fill: fillFor(key), stroke: '#8D8474', 'stroke-width': 0.6, 'data-key': key,
        onpointermove: (e) => showTip(e.clientX, e.clientY, tipFor(key)),
        onpointerleave: hideTip,
      }));
    }
    put(host, svg);
  });
}

function fanChart(host, site, row) {
  const f = row.forecast;
  const days = f?.dates ?? [];
  const lift = (arr) => (arr ?? []).map(Number);
  // Scale to the forecast so the fan can be read. The p95 line joins only when it is close enough
  // to share the scale; otherwise the card says it is off the chart.
  const reach = Math.max(...lift(f?.max), ...lift(f?.q), row.q ?? 0, 1);
  const showP95 = isNum(site?.p95) && site.p95 <= reach * 1.6;
  const top = niceMax(Math.max(reach, showP95 ? site.p95 : 0) * 1.05);
  responsive(host, (w) => {
    const height = 118;
    const m = { t: 8, r: 6, b: 18, l: 38 };
    const x = scale(0, Math.max(1, days.length - 1), m.l, w - m.r);
    const y = scale(0, top, height - m.b, m.t);
    const at = (arr) => (arr ?? []).map((v, i) => [x(i), isNum(v) ? y(v) : null]);
    const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img', 'aria-label': `Forecast flow at ${site?.site ?? row.id}` });
    for (const t of ticks(0, top, 2)) {
      svg.append(
        s('line', { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t), class: 'grid' }),
        s('text', { x: m.l - 5, y: y(t) + 3.5, 'text-anchor': 'end', class: 'ax', text: t >= 10000 ? `${t / 1000}k` : fmtInt(t) }));
    }
    if (f?.min && f?.max) svg.append(s('path', { d: bandPath(at(f.max), at(f.min)), fill: COLOR.blue, opacity: 0.12 }));
    if (f?.p25 && f?.p75) svg.append(s('path', { d: bandPath(at(f.p75), at(f.p25)), fill: COLOR.blue, opacity: 0.28 }));
    if (f?.q) svg.append(s('path', { d: linePath(at(f.q)), fill: 'none', stroke: COLOR.blue, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    if (showP95) {
      svg.append(
        s('line', { x1: m.l, x2: w - m.r, y1: y(site.p95), y2: y(site.p95), stroke: COLOR.l1, 'stroke-width': 1.25 }),
        s('text', { x: w - m.r, y: y(site.p95) + 11, 'text-anchor': 'end', class: 'ax', text: 'p95' }));
    }
    if (days.length) {
      svg.append(
        s('text', { x: m.l, y: height - 4, class: 'ax', text: fmtShort(days[0]) }),
        s('text', { x: w - m.r, y: height - 4, 'text-anchor': 'end', class: 'ax', text: fmtShort(days[days.length - 1]) }));
    }
    svg.addEventListener('pointermove', (e) => {
      const i = Math.max(0, Math.min(days.length - 1, Math.round(((e.clientX - svg.getBoundingClientRect().left - m.l) / (w - m.l - m.r)) * (days.length - 1))));
      if (!days.length) return;
      showTip(e.clientX, e.clientY, [fmtShort(days[i]),
        { color: COLOR.blue, value: `${fmtInt(f.q?.[i])} m³/s`, label: 'middle forecast' },
        { value: `${fmtInt(f.p25?.[i])} to ${fmtInt(f.p75?.[i])}`, label: 'middle half' },
        { value: `${fmtInt(f.min?.[i])} to ${fmtInt(f.max?.[i])}`, label: 'full range' }]);
    });
    svg.addEventListener('pointerleave', hideTip);
    put(host, svg);
  });
}

function statusBlock(L) {
  const active = Boolean(L.season_active);
  return h('section', { class: `status ${active ? 'is-active' : 'is-resting'}`, id: 'season-status' },
    h('p', { class: 'doc-n', text: `Issued ${L.issued ? fmtLong(L.issued) : 'date not given'}` }),
    h('h2', { class: 'status-head', text: active ? 'The monsoon flood model is running.' : 'The monsoon flood model is resting.' }),
    L.note ? h('p', { class: 'status-note', text: L.note }) : null,
    active ? null : h('p', { class: 'read', text: 'Out of season there is no flood forecast from Sajag. River flow and drought below stay current.' }));
}

function floodBlock(L) {
  const entries = Object.entries(L.districts ?? {});
  if (!L.season_active || !entries.length) return null;
  const top = entries.map(([key, d]) => ({ key, level: d.level ?? 0, risk: d.risk ?? {}, reasons: d.reasons ?? [] }))
    .sort((a, b) => b.level - a.level || (b.risk['3'] ?? 0) - (a.risk['3'] ?? 0));
  const mapHost = h('div', { class: 'mini-map' });
  const levels = new Map(top.map((r) => [r.key, r]));
  miniMap(mapHost, (k) => LEVEL_FILL[levels.get(k)?.level ?? 0] ?? LAND, (k) => [districtName(k), { value: levelOf(levels.get(k)?.level ?? 0).en, label: 'flood level' }]);
  return h('section', { class: 'doc-sec' },
    h('div', { class: 'doc-side' },
      h('h2', { class: 'doc-title', text: 'Flood level today' }),
      h('ul', { class: 'lg' }, [...ctx.levels].reverse().map((l) => h('li', null, swatch(LEVEL_FILL[l.id] ?? LAND), h('span', { class: 'lg-label' }, bilingual(l)), h('span', { class: 'lg-n', text: String(top.filter((r) => r.level === l.id).length) }))))),
    h('div', { class: 'doc-body split' },
      mapHost,
      dataTable('Highest risk districts today', [
        { label: 'District', cell: (r) => districtName(r.key) },
        { label: 'Level', cell: (r) => levelChip(r.level) },
        { label: 'Within 3 days', num: true, cell: (r) => (isNum(r.risk['3']) ? `${r.risk['3']}%` : 'n/a') },
      ], top.slice(0, 8))));
}

function riverBlock(L) {
  const rows = [...(L.sites ?? [])].sort((a, b) => (STATUS[a.status]?.rank ?? 3) - (STATUS[b.status]?.rank ?? 3) || (b.pct ?? 0) - (a.pct ?? 0));
  if (!rows.length) return null;
  const counts = Object.keys(STATUS).map((k) => [k, rows.filter((r) => r.status === k).length]).filter(([, n]) => n > 0);
  const grid = h('div', { class: 'fan-grid', id: 'fan-grid' });
  for (const row of rows) {
    const site = ctx.siteById.get(row.id);
    const chart = h('div', { class: 'chart' });
    grid.append(h('article', { class: `fan is-${row.status}` },
      h('h3', { class: 'fan-title' }, site ? `${site.river} at ${site.site}` : row.id),
      h('p', { class: 'fan-read' },
        h('strong', { text: `${fmtInt(row.q)} m³/s` }),
        ` ${STATUS[row.status]?.label ?? row.status}`),
      chart,
      h('p', { class: 'note', text: [
        isNum(row.pct) ? `Higher than ${Math.round(row.pct)}% of reference days.` : '',
        isNum(site?.p95) && site.p95 > Math.max(...(row.forecast?.max ?? []).map(Number), row.q ?? 0, 1) * 1.6 ? `p95 is ${fmtInt(site.p95)}, off this chart.` : '',
      ].filter(Boolean).join(' ') })));
    fanChart(chart, site, row);
  }
  return h('section', { class: 'doc-sec doc-wide' },
    h('div', { class: 'doc-side' },
      h('h2', { class: 'doc-title', text: 'Rivers now' }),
      h('p', { class: 'doc-intro', text: `${counts.map(([k, n]) => `${n} ${k}`).join(', ')}. GloFAS forecast: the line is the middle forecast, the dark band the middle half of forecasts, the pale band the full range.` })),
    h('div', { class: 'doc-body' }, grid,
      tableTwin('River status today', [
        { label: 'River', cell: (r) => ctx.siteById.get(r.id)?.river ?? '' },
        { label: 'Site', cell: (r) => ctx.siteById.get(r.id)?.site ?? r.id },
        { label: 'Flow, m³/s', num: true, cell: (r) => fmtInt(r.q) },
        { label: 'Status', cell: (r) => STATUS[r.status]?.label ?? r.status },
      ], rows)));
}

function droughtBlock() {
  const D = ctx.drought;
  if (!D?.months?.length) return null;
  const m = D.months.length - 1;
  const row = D.spi3?.[m] ?? [];
  const value = new Map((D.districts ?? []).map((k, j) => [k, row[j]]));
  const chance = new Map((D.districts ?? []).map((k, j) => [k, D.chance?.[m]?.[j]]));
  const dry = [...value].filter(([, v]) => isNum(v) && v <= -1).sort((a, b) => a[1] - b[1]);
  const mapHost = h('div', { class: 'mini-map', id: 'today-drought-map' });
  miniMap(mapHost, (k) => (isNum(value.get(k)) ? droughtClass(value.get(k)).fill : LAND),
    (k) => [districtName(k), { value: fmtSigned(value.get(k)), label: 'SPI-3' }, ...(isNum(chance.get(k)) ? [{ value: `${chance.get(k)}%`, label: 'chance of drought next month' }] : [])]);
  const declared = [...(D.declared ?? [])].sort((a, b) => b.year - a.year);
  return h('section', { class: 'doc-sec' },
    h('div', { class: 'doc-side' },
      h('h2', { class: 'doc-title', text: 'Drought now' }),
      h('p', { class: 'doc-intro', text: `${fmtMonthYear(D.months[m])}. ${dry.length} of ${row.length} districts in drought, with SPI-3 at or below −1. SPI-3 compares three months of rain with what is normal for those months.` }),
      h('ul', { class: 'lg' }, DROUGHT_CLASSES.map((c) => h('li', null, swatch(c.fill), h('span', { class: 'lg-label', text: `${c.label} (${c.range})` }))))),
    h('div', { class: 'doc-body split' },
      mapHost,
      h('div', null,
        h('h3', { class: 'sub-title', text: dry.length ? 'Driest districts' : 'No district is in drought' }),
        dry.length ? dataTable('Driest districts', [
          { label: 'District', cell: (r) => districtName(r[0]) },
          { label: 'SPI-3', num: true, cell: (r) => fmtSigned(r[1]) },
          { label: 'Chance next month', num: true, cell: (r) => (isNum(chance.get(r[0])) ? `${chance.get(r[0])}%` : 'n/a') },
        ], dry.slice(0, 8)) : null,
        isNum(D.state_share?.[m]) ? h('p', { class: 'note', text: `${fmtPct(D.state_share[m])} of districts are in drought this month.` }) : null,
        declared.length ? h('h3', { class: 'sub-title', text: 'Droughts the state declared' }) : null,
        declared.length ? h('ul', { class: 'plain-mini' }, declared.map((d) => h('li', null,
          h('strong', { text: String(d.year) }), ` ${d.scope ?? ''} `,
          d.url ? h('a', { href: d.url, target: '_blank', rel: 'noopener', text: 'Source' }) : null))) : null)));
}

export function renderToday(host) {
  const L = ctx.live;
  put(host,
    h('div', { class: 'doc-head' },
      h('h1', { class: 'doc-h1', text: 'Today' }),
      h('p', { class: 'doc-lede', text: 'What the system says now, not a replay.' })),
    L ? statusBlock(L) : h('p', { class: 'read', text: 'The current forecast file is not available.' }),
    L ? floodBlock(L) : null,
    // Out of season the drought map is the live question, so it comes before the rivers.
    L?.season_active ? riverBlock(L) : droughtBlock(),
    L?.season_active ? droughtBlock() : (L ? riverBlock(L) : null));
}

export function todayLine() {
  const L = ctx.live;
  if (!L) return null;
  const parts = [L.season_active ? 'Flood model running' : 'Flood model resting'];
  const rows = L.sites ?? [];
  if (rows.length) {
    const high = rows.filter((r) => r.status !== 'normal').length;
    parts.push(high ? `${plural(high, 'gauge')} high` : `All ${rows.length} gauges normal`);
  }
  const D = ctx.drought;
  if (D?.spi3?.length) {
    const row = D.spi3[D.spi3.length - 1];
    parts.push(`${row.filter((v) => isNum(v) && v <= -1).length} of ${row.length} districts in drought`);
  }
  return parts.join('. ');
}
