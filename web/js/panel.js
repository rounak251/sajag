// Everything beside the map: statewide ranking, or one district in depth, and the alert preview.
import { ctx, districtName, droughtMonthIndex, getJSON, levelOf, nearestSites } from './data.js';
import { state, set } from './state.js';
import { h, s, put, bilingual, choiceGroup, fmtInt, fmtMedium, fmtMonthYear, fmtShort, fmtSigned, isNum, plural } from './util.js';
import { COLOR, linePath, niceMax, responsive, scale, showTip, hideTip, ticks } from './charts.js';
import { createAlert } from './alert.js';
import { levelChip, swatch } from './overlay.js';
import { droughtClass, LEVEL_FILL } from './map.js';

const VILLAGE_CLASS = ['Low', 'Medium', 'High'];
const VILLAGE_STEP = 8;

export function siteStatus(H, id, i) {
  const k = H.sk.get(id);
  const site = ctx.siteById.get(id);
  const q = H.q?.[i]?.[k];
  if (!site || !isNum(q)) return 'normal';
  if (isNum(site.p99) && q >= site.p99) return 'extreme';
  if (isNum(site.p95) && q >= site.p95) return 'high';
  return 'normal';
}

function flowChart(host, H, site, windowRange, i) {
  const k = H.sk.get(site.id);
  const [a, b0] = windowRange;
  const b = Math.min(H.dates.length - 1, Math.max(b0, Math.min(i + 7, H.dates.length - 1)));
  const qAt = (n) => H.q?.[n]?.[k];
  const peak = H.peak7?.[i]?.[k];
  const values = [];
  for (let n = a; n <= b; n += 1) if (isNum(qAt(n))) values.push(qAt(n));
  const top = niceMax(Math.max(...values, site.p99 ?? 0, site.p95 ?? 0, isNum(peak) ? peak : 0, 1) * 1.04);
  const height = 214;
  const draw = (w) => {
    const m = { t: 26, r: 10, b: 24, l: 46 };
    const x = scale(a, b, m.l, w - m.r);
    const y = scale(0, top, height - m.b, m.t);
    const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img', 'aria-label': `River flow at ${site.site} on the ${site.river}, in cubic metres per second` });
    svg.append(s('text', { x: 0, y: 11, class: 'ax-title', text: 'Flow, m³/s' }));
    for (const t of ticks(0, top, 4)) {
      svg.append(
        s('line', { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t), class: 'grid' }),
        s('text', { x: m.l - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'ax', text: t >= 10000 ? `${t / 1000}k` : fmtInt(t) }));
    }
    const line = (level, color, text) => {
      if (!isNum(level)) return;
      svg.append(
        s('line', { x1: m.l, x2: w - m.r, y1: y(level), y2: y(level), stroke: color, 'stroke-width': 1.25 }),
        s('text', { x: m.l + 4, y: y(level) - 4, class: 'ax ax-strong', text }));
    };
    line(site.p95, COLOR.l1, `p95 high, ${fmtInt(site.p95)}`);
    line(site.p99, COLOR.l3, `p99 extreme, ${fmtInt(site.p99)}`);
    const past = [];
    const future = [];
    for (let n = a; n <= b; n += 1) {
      const pt = [x(n), isNum(qAt(n)) ? y(qAt(n)) : null];
      if (n <= i) past.push(pt);
      if (n >= i) future.push(pt);
    }
    svg.append(
      s('path', { d: linePath(future), fill: 'none', stroke: COLOR.blue, 'stroke-width': 1.25, opacity: 0.35 }),
      s('path', { d: linePath(past), fill: 'none', stroke: COLOR.blue, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    if (isNum(qAt(i))) svg.append(s('circle', { cx: x(i), cy: y(qAt(i)), r: 4, fill: COLOR.blue, stroke: COLOR.paper, 'stroke-width': 2 }));
    svg.append(s('line', { x1: x(i), x2: x(i), y1: m.t - 8, y2: height - m.b, stroke: COLOR.ink, 'stroke-width': 1 }));
    if (isNum(peak)) {
      const end = Math.min(H.dates.length - 1, i + 7);
      const flip = x(end) > w * 0.62;
      svg.append(
        s('line', { x1: x(i), x2: x(end), y1: y(peak), y2: y(peak), stroke: COLOR.ink, 'stroke-width': 2, 'stroke-linecap': 'round' }),
        s('circle', { cx: x(end), cy: y(peak), r: 4, fill: COLOR.ink, stroke: COLOR.paper, 'stroke-width': 2 }),
        s('text', {
          x: flip ? x(i) - 5 : x(end) + 7, y: y(peak) + (flip ? -5 : 3.5), 'text-anchor': flip ? 'end' : 'start', class: 'ax ax-strong',
          text: `7-day peak ${fmtInt(peak)}`,
        }));
    }
    const dayStep = Math.max(1, Math.round((b - a) / Math.max(2, Math.floor(w / 90))));
    for (let n = a; n <= b; n += dayStep) {
      svg.append(s('text', { x: x(n), y: height - 7, 'text-anchor': n === a ? 'start' : 'middle', class: 'ax', text: fmtShort(H.dates[n]) }));
    }
    svg.addEventListener('pointermove', (e) => {
      const px = e.clientX - svg.getBoundingClientRect().left;
      const n = Math.max(a, Math.min(b, Math.round(a + ((px - m.l) / (w - m.l - m.r)) * (b - a))));
      showTip(e.clientX, e.clientY, [fmtMedium(H.dates[n]), { color: COLOR.blue, value: `${fmtInt(qAt(n))} m³/s`, label: 'flow' }]);
    });
    svg.addEventListener('pointerleave', hideTip);
    put(host, svg);
  };
  host.redraw = draw;
  if (host.clientWidth) draw(host.clientWidth);
}

function droughtBlock(key) {
  const D = ctx.drought;
  if (state.layer !== 'drought' || !D || !ctx.H) return null;
  const j = D.dj.get(key);
  const m = droughtMonthIndex(D, ctx.H.dates[state.i]);
  const v = D.spi3?.[m]?.[j];
  if (!isNum(v)) return null;
  const c = droughtClass(v);
  const chance = D.chance?.[m]?.[j];
  return h('section', { class: 'sec' },
    h('h3', { class: 'sec-title', text: `Rainfall, ${fmtMonthYear(D.months[m])}` }),
    h('p', { class: 'chip' }, swatch(c.fill), h('span', { text: c.label })),
    h('p', { class: 'read', text: `SPI-3 is ${fmtSigned(v)}. Zero is a normal three months of rain, and −1 or below counts as drought.` }),
    isNum(chance) ? h('p', { class: 'read', text: `Chance of drought next month: ${chance}%.` }) : null);
}

export function createPanel(host, { onPick }) {
  const select = h('select', { id: 'district-select', 'aria-label': 'Choose a district', onchange: (e) => onPick(e.target.value || null) },
    h('option', { value: '', text: 'All of Bihar' }),
    [...ctx.districts.values()].sort((a, b) => a.name.localeCompare(b.name)).map((d) => h('option', { value: d.key, text: d.name })));
  const tabs = choiceGroup({
    label: 'Panel', role: 'tab', value: 'district', className: 'panel-tabs',
    onChange: (v) => set({ panelTab: v }),
    options: [
      { value: 'district', label: 'District', id: 'tab-district', controls: 'panel-district' },
      { value: 'alert', label: 'Alert preview', id: 'tab-alert', controls: 'panel-alert' },
    ],
  });
  const title = h('div', { class: 'p-title' });
  const main = h('div', { id: 'panel-district', role: 'tabpanel', 'aria-labelledby': 'tab-district' });
  const alertHost = h('div', { id: 'panel-alert', role: 'tabpanel', 'aria-labelledby': 'tab-alert', hidden: true });
  const overview = h('div', { id: 'p-overview' });
  const now = h('div', { id: 'p-now' });
  const riverSec = h('section', { class: 'sec', id: 'p-river' });
  const villageSec = h('section', { class: 'sec', id: 'p-villages' });
  main.append(overview, now, riverSec, villageSec);
  host.append(h('div', { class: 'p-pick' }, select), title, tabs, main, alertHost);

  const alert = createAlert(alertHost);

  const riverTitle = h('h3', { class: 'sec-title', text: 'Nearby river flow' });
  const siteSlot = h('div', { class: 'site-pick' });
  const chart = h('div', { class: 'chart', id: 'flow-chart' });
  const riverRead = h('p', { class: 'read' });
  riverSec.append(riverTitle, siteSlot, chart, riverRead);
  responsive(chart, (w) => chart.redraw?.(w));

  let villages = null;
  let villagesFor = null;
  let shown = VILLAGE_STEP;
  const villageList = h('div');
  villageSec.append(h('h3', { class: 'sec-title', text: 'Most exposed villages' }), villageList);

  function renderOverview() {
    const H = ctx.H;
    if (!H) return;
    if (state.layer === 'drought' && ctx.drought) {
      const D = ctx.drought;
      const m = droughtMonthIndex(D, H.dates[state.i]);
      const dry = H.districts.map((key) => ({ key, spi: D.spi3?.[m]?.[D.dj.get(key)] }))
        .filter((r) => isNum(r.spi)).sort((a, b) => a.spi - b.spi);
      put(overview, h('section', { class: 'sec' },
        h('h3', { class: 'sec-title', text: 'All districts, driest first' }),
        h('p', { class: 'read', text: `SPI-3 for ${fmtMonthYear(D.months[m])}. At or below \u22121 means drought.` }),
        h('ol', { class: 'rank', id: 'rank' }, dry.map((r) => h('li', null,
          h('button', { type: 'button', onclick: () => onPick(r.key) },
            swatch(droughtClass(r.spi).fill, 12),
            h('span', { class: 'rank-name', text: districtName(r.key) }),
            h('span', { class: 'rank-level', text: r.spi <= -1 ? 'Drought' : '' }),
            h('span', { class: 'rank-risk', text: fmtSigned(r.spi) })))))));
      return;
    }
    const rows = H.districts.map((key) => ({ key, level: H.levelAt(state.i, key), risk: H.riskAt(state.lead, state.i, key) }))
      .sort((a, b) => b.level - a.level || (b.risk ?? -1) - (a.risk ?? -1));
    put(overview,
      h('section', { class: 'sec' },
        h('h3', { class: 'sec-title', text: `All districts, highest risk first` }),
        h('p', { class: 'read', text: `Chance of flood within ${plural(Number(state.lead), 'day')}, on ${fmtMedium(H.dates[state.i])}.` }),
        h('ol', { class: 'rank', id: 'rank' }, rows.map((r) => h('li', null,
          h('button', { type: 'button', onclick: () => onPick(r.key) },
            swatch(LEVEL_FILL[r.level] ?? LEVEL_FILL[0], 12),
            h('span', { class: 'rank-name', text: districtName(r.key) }),
            h('span', { class: 'rank-level', text: levelOf(r.level).en }),
            h('span', { class: 'rank-risk', text: isNum(r.risk) ? `${r.risk}%` : 'n/a' })))))));
  }

  function renderNow() {
    const H = ctx.H;
    const key = state.district;
    if (!H || !key) return;
    const i = state.i;
    const level = H.levelAt(i, key);
    const codes = H.reasonsAt(i, key);
    const risk = H.leads.map((lead) => ({ lead, value: H.riskAt(lead, i, key) }));
    const chosen = risk.find((r) => r.lead === state.lead);
    const onRecord = H.activeEvents(i).filter((e) => e.keys.includes(key));
    put(now,
      droughtBlock(key),
      h('section', { class: 'sec' },
        h('h3', { class: 'sec-title', text: `Flood level on ${fmtMedium(H.dates[i])}` }),
        h('p', { class: 'p-level', id: 'p-level' }, levelChip(level)),
        H.raisedAt(i, key) ? h('p', { class: 'read', id: 'raised-note', text: `The rain forecast set this level: ${H.rainAt(i, key)} mm forecast over the next 5 days here or upstream. The chances below use only rain and rivers observed so far, so they stay low until the rain falls.` }) : null,
        onRecord.length ? h('p', { class: 'on-record' }, h('span', { class: 'mk mk-flood' }), `On record: ${onRecord[onRecord.length - 1].label}`) : null),
      h('section', { class: 'sec' },
        h('h3', { class: 'sec-title', text: H.raisedAt(i, key) ? 'From observed data only, chance of flood within' : 'Chance of flood within' }),
        h('ul', { class: 'risk', id: 'risk-bars' }, risk.map((r) => h('li', { class: r.lead === state.lead ? 'is-on' : null },
          h('span', { class: 'risk-label', text: plural(Number(r.lead), 'day') }),
          h('span', { class: 'risk-track' }, h('span', { class: 'risk-fill', style: { width: `${r.value ?? 0}%` } })),
          h('span', { class: 'risk-n', text: isNum(r.value) ? `${r.value}%` : 'n/a' })))),
        isNum(chosen?.value) ? h('p', { class: 'read', text: `${chosen.value}% means about ${chosen.value} in 100 days like this one are followed by a flood within ${plural(Number(chosen.lead), 'day')}.` }) : null),
      h('section', { class: 'sec' },
        h('h3', { class: 'sec-title', text: 'Why' }),
        codes.length
          ? h('ul', { class: 'why', id: 'why' }, codes.map((c) => h('li', null, bilingual(ctx.meta.reasons?.[c], c.replace(/_/g, ' ')))))
          : h('p', { class: 'read', id: 'why', text: 'Nothing stands out on this date.' })));
  }

  function renderRiver() {
    const H = ctx.H;
    const key = state.district;
    if (!H || !key) return;
    const near = nearestSites(key, 3).filter((x) => H.sk.has(x.id));
    riverSec.hidden = near.length === 0;
    if (!near.length) return;
    const site = near.find((x) => x.id === state.site) ?? near[0];
    if (siteSlot.dataset.for !== key) {
      siteSlot.dataset.for = key;
      put(siteSlot, choiceGroup({
        label: 'Gauge', value: site.id, onChange: (v) => set({ site: v }),
        options: near.map((x) => ({ value: x.id, label: `${x.river} at ${x.site}` })),
      }));
    }
    const range = getRange();
    flowChart(chart, H, site, range, state.i);
    const q = H.q?.[state.i]?.[H.sk.get(site.id)];
    const peak = H.peak7?.[state.i]?.[H.sk.get(site.id)];
    const st = siteStatus(H, site.id, state.i);
    riverRead.textContent = `${site.river} at ${site.site}, ${Math.round(site.km)} km from the district centre. `
      + (isNum(q) ? `Flow is ${fmtInt(q)} m³/s, ${st === 'extreme' ? 'above the p99 line' : st === 'high' ? 'above the p95 line' : 'below the p95 line'}. ` : '')
      + (isNum(peak) ? `Forecast peak in the next 7 days: ${fmtInt(peak)} m³/s.` : '');
  }

  async function renderVillages() {
    const key = state.district;
    if (!key) return;
    if (villagesFor !== key) {
      villagesFor = key;
      shown = VILLAGE_STEP;
      villages = null;
      put(villageList, h('p', { class: 'read', text: 'Loading villages.' }));
      const data = await getJSON(`data/villages/${key}.json`).catch(() => null);
      if (villagesFor !== key) return;
      villages = data?.villages ?? [];
      onVillages(villages);
    }
    if (!villages) return;
    if (!villages.length) {
      put(villageList, h('p', { class: 'read', text: 'No village file for this district.' }));
      return;
    }
    const top = [...villages].sort((a, b) => b[3] - a[3]);
    const more = top.length - shown;
    put(villageList,
      h('ol', { class: 'vill', id: 'village-list' }, top.slice(0, shown).map(([name, , , exposure, cls]) => h('li', null,
        h('span', { class: 'vill-name', text: name }),
        h('span', { class: 'vill-track' }, h('span', { class: `vill-fill c${cls}`, style: { width: `${exposure}%` } })),
        h('span', { class: 'vill-n', text: String(exposure) }),
        h('span', { class: 'vill-class', text: VILLAGE_CLASS[cls] ?? '' })))),
      h('p', { class: 'note', text: `Exposure runs from 0 to 100. ${plural(top.length, 'village')} in this file.` }),
      more > 0 ? h('button', { type: 'button', class: 'btn', onclick: () => { shown += VILLAGE_STEP * 2; renderVillages(); }, text: `Show ${Math.min(more, VILLAGE_STEP * 2)} more` }) : null);
  }

  let getRange = () => [0, 0];
  let onVillages = () => {};

  function renderTitle() {
    const key = state.district;
    const d = ctx.districts.get(key);
    put(title, key && d
      ? h('h2', { class: 'p-name', id: 'district-name' }, d.name, d.name_hi ? h('span', { class: 'p-name-hi', lang: 'hi', text: d.name_hi }) : null)
      : h('h2', { class: 'p-name', id: 'district-name', text: 'Bihar' }, h('span', { class: 'p-name-hi', lang: 'hi', text: 'बिहार' })));
  }

  function update(c = {}) {
    const key = state.district;
    if (c.district || c.all) {
      select.value = key ?? '';
      renderTitle();
      riverSec.hidden = !key;
      villageSec.hidden = !key;
      if (!key) { villagesFor = null; villages = null; onVillages(null); }
    }
    const tab = state.panelTab;
    if (c.panelTab || c.all) {
      tabs.setValue(tab);
      main.hidden = tab !== 'district';
      alertHost.hidden = tab !== 'alert';
    }
    overview.hidden = Boolean(key);
    now.hidden = !key;
    if (tab === 'district') {
      if (key) {
        renderNow();
        renderRiver();
      } else renderOverview();
    } else {
      alert.update();
    }
    if (key && (c.district || c.all || c.panelTab)) renderVillages();
  }

  return {
    update,
    bind({ range, villagesLoaded }) { getRange = range; onVillages = villagesLoaded; },
  };
}
