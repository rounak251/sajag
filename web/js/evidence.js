// The Evidence page. It renders whatever metrics.json holds and skips what is absent, so no number
// lives here. The sentences only explain what each measure means.
import { ctx } from './data.js';
import { h, s, put, choiceGroup, fmtDec, fmtInt, fmtMedium, fmtPct, isNum, plural } from './util.js';
import { COLOR, barList, dataTable, lineChart, niceMax, responsive, scale, showTip, hideTip, tableTwin, ticks } from './charts.js';

const isSajag = (name) => /sajag/i.test(name ?? '');
const uniq = (list) => [...new Set(list)];

function section(n, title, intro, ...body) {
  return h('section', { class: 'doc-sec' },
    h('div', { class: 'doc-side' },
      h('p', { class: 'doc-n', text: `Section ${n}` }),
      h('h2', { class: 'doc-title', text: title }),
      intro ? h('p', { class: 'doc-intro', text: intro }) : null),
    h('div', { class: 'doc-body' }, body));
}

const of = (n, total) => `${n} of ${total}`;

// The page opens on the test that failed, because that is the most useful thing here.
function hero(m) {
  const v1 = m.version1;
  const v2 = m.version2;
  if (!v1?.blind?.total || !v2?.totals) return null;
  const total = v1.blind.total.district_events;
  const s = v2.totals.sajag;
  const chance = v2.placebo?.sajag;
  return h('div', { class: 'hero-num' },
    h('p', { class: 'doc-n', text: 'Version 1, true blind test' }),
    h('p', { class: 'hero-figure', id: 'hero-figure', text: of(v1.blind.total.sajag_3d, total) }),
    h('p', { class: 'hero-line', text: 'recorded district floods in 2024 to 2026 got a Warning at least 3 days ahead. Cross-validation had promised ' + fmtPct(v1.cv?.caught_3d) + '. The list of floods was committed to git before any prediction existed.' }),
    h('p', { class: 'doc-n hero-next', text: 'Version 2, after the failure, not blind' }),
    h('p', { class: 'hero-figure hero-figure-2', id: 'hero-figure-2', text: of(s.warned_3d, v2.district_events) }),
    h('p', { class: 'hero-line', text: `of the same floods, using rain forecasts as really issued at the time. Chance alone would catch about ${fmtDec(chance?.chance_mean ?? 0, 0)}.` }),
    h('p', { class: 'hero-sub', text: `A 3-day rain rule catches ${v2.totals.rain_matched?.warned_3d} and river level ${v2.totals.river_matched?.warned_3d} when given the same number of alerts, with thresholds set in hindsight.` }));
}

function limits(m) {
  if (!m.limits?.length) return null;
  return h('div', { class: 'limits', id: 'limits' },
    h('p', { class: 'doc-n', text: 'Read this first' }),
    h('h2', { class: 'doc-title', text: 'What this cannot do' }),
    h('ol', { class: 'plain-list' }, m.limits.map((t) => h('li', { text: t }))));
}

function budgetCompare(m) {
  const rows = (m.budget ?? []).filter((r) => r.method);
  if (!rows.length) return null;
  const budgets = uniq(rows.map((r) => r.budget)).sort((a, b) => a - b);
  const leads = uniq(rows.flatMap((r) => Object.keys(r).filter((k) => /^caught_\d+d$/.test(k))))
    .sort((a, b) => parseInt(a.slice(7), 10) - parseInt(b.slice(7), 10));
  const start = budgets.includes(m.headline?.budget) ? m.headline.budget : budgets[0];
  const slot = h('div', { id: 'budget-chart' });
  const show = (budget) => {
    const here = rows.filter((r) => r.budget === budget);
    const first = leads.includes('caught_3d') ? 'caught_3d' : leads[0];
    here.sort((a, b) => (b[first] ?? 0) - (a[first] ?? 0));
    const top = Math.max(...here.flatMap((r) => leads.map((k) => r[k] ?? 0)), 0.01);
    const columns = leads.map((k) => h('div', { class: 'small-mult' },
      h('h3', { class: 'sub-title', text: `At least ${plural(parseInt(k.slice(7), 10), 'day')} ahead` }),
      barList(here.map((r) => ({ label: r.method, value: r[k], text: fmtPct(r[k]), strong: isSajag(r.method) })), { max: top, label: `Share of flood starts caught at least ${k.slice(7)} ahead` })));
    const hasPrecision = here.some((r) => isNum(r.precision));
    put(slot,
      h('div', { class: 'mult-grid' }, columns),
      hasPrecision ? h('p', { class: 'read', text: 'Precision, in the table, is the share of alert days followed by a recorded flood.' }) : null,
      tableTwin('Flood starts caught by each method at this budget', [
        { label: 'Method', key: 'method' },
        ...leads.map((k) => ({ label: `Caught ${k.slice(7)}`, num: true, cell: (r) => fmtPct(r[k]) })),
        hasPrecision ? { label: 'Precision', num: true, cell: (r) => fmtPct(r.precision) } : null,
        here.some((r) => isNum(r.median_lead)) ? { label: 'Median lead, days', num: true, cell: (r) => fmtDec(r.median_lead, 1) } : null,
      ].filter(Boolean), here));
  };
  show(start);
  const picker = budgets.length > 1 ? h('div', { class: 'al-row' },
    h('span', { class: 'ctl-label', text: 'Alert budget' }),
    choiceGroup({ label: 'Alert budget', value: start, onChange: show, options: budgets.map((b) => ({ value: b, label: fmtPct(b) })) })) : null;
  const k = m.headline ?? {};
  const gap = Array.isArray(k.rain_difference_ci) ? k.rain_difference_ci : null;
  return section(3, 'Cross-validation on 2006 to 2023',
    `Every method may alert on the same share of district days. Each year block is scored by a model that never saw it. This test uses no rain forecasts, and it is the kind of test that wrongly favoured version 1.${gap ? ` The lead over the rain rule runs from ${fmtPct(gap[0])} to ${fmtPct(gap[1])} in points, which includes zero, so it could be chance.` : ''}`,
    picker, slot);
}

function riverSkill(m) {
  const heldOut = (m.river_held_out ?? []).length > 0;
  const rows = [...(heldOut ? m.river_held_out : m.river ?? [])].filter((r) => isNum(r.lead)).sort((a, b) => a.lead - b.lead);
  if (!rows.length) return null;
  const leads = rows.map((r) => r.lead);
  const panels = [
    { model: 'ap_new_model', base: 'ap_new_persistence', title: 'Spotting new floods', note: 'Average precision for a river crossing its p99 line while it is still below it. This is the case where a forecast adds something.', domain: 'share' },
    { model: 'nse_model', base: 'nse_persistence', title: 'Matching peak flow', note: 'Nash-Sutcliffe efficiency: 1 is a perfect match, 0 is no better than the average flow.', domain: 'share' },
    { model: 'csi_model', base: 'csi_persistence', title: 'Hits against misses and false alarms', note: 'Critical success index: hits divided by hits, misses and false alarms together.', domain: 'share' },
  ].filter((p) => rows.some((r) => isNum(r[p.model])));
  if (!panels.length) return null;
  const grid = h('div', { class: 'mult-grid' });
  for (const p of panels) {
    const host = h('div');
    const all = rows.flatMap((r) => [r[p.model], r[p.base]]).filter(isNum);
    grid.append(h('div', { class: 'small-mult' },
      h('h3', { class: 'sub-title', text: p.title }),
      host,
      h('p', { class: 'note', text: p.note })));
    requestAnimationFrame(() => lineChart(host, {
      xValues: leads, xLabel: 'Days ahead', yMax: Math.min(1, niceMax(Math.max(...all))), yMin: Math.min(0, ...all), yFormat: (v) => fmtDec(v, 2), yLabel: 'Score',
      series: [
        { name: 'Sajag river model', color: COLOR.blue, points: rows.map((r) => [r.lead, r[p.model]]) },
        { name: 'Persistence', color: COLOR.grey, points: rows.map((r) => [r.lead, r[p.base]]) },
      ],
    }));
  }
  return section(2, 'River forecast: the part that passed',
    `Scored on 2024 to 2026, which it never trained on, and unchanged since the blind run. Persistence assumes the river stays as it is today. The target is GloFAS modelled flow, not gauge readings.`,
    grid,
    tableTwin('River skill by lead time', [
      { label: 'Days ahead', key: 'lead', num: true },
      ...panels.flatMap((p) => [
        { label: `${p.title}, Sajag`, num: true, cell: (r) => fmtDec(r[p.model]) },
        { label: `${p.title}, persistence`, num: true, cell: (r) => fmtDec(r[p.base]) },
      ]),
    ], rows));
}

function impact(m) {
  const rows = (m.impact ?? []).filter((r) => isNum(r.pr_auc));
  const leads = uniq(rows.map((r) => r.lead)).sort((a, b) => a - b);
  if (leads.length < 2) return null;
  const models = uniq(rows.map((r) => r.model)).sort((a, b) => isSajag(b) - isSajag(a));
  const host = h('div');
  const greys = ['#8D8474', '#A99F8E', '#6F675A', '#BDB3A2'];
  let g = 0;
  const series = models.map((name) => ({
    name, color: isSajag(name) ? COLOR.blue : greys[g++ % greys.length], width: isSajag(name) ? 2 : 1.25,
    points: leads.map((l) => [l, rows.find((r) => r.model === name && r.lead === l)?.pr_auc ?? null]),
  }));
  requestAnimationFrame(() => lineChart(host, {
    series, xValues: leads, xLabel: 'Days ahead', yMax: niceMax(Math.max(...rows.map((r) => r.pr_auc))), yFormat: (v) => fmtDec(v, 2), yLabel: 'PR-AUC', height: 230,
  }));
  return section(4, 'District flood risk by lead time',
    'PR-AUC measures how well risk ranks the days that flooded above those that did not. A rare event gives low absolute values, so compare the lines, not the height.',
    host,
    tableTwin('PR-AUC by method and lead', [{ label: 'Days ahead', key: 'lead', num: true }, { label: 'Method', key: 'model' }, { label: 'PR-AUC', num: true, cell: (r) => fmtDec(r.pr_auc, 3) }], rows));
}

function reliability(m) {
  const rows = (m.reliability ?? []).filter((r) => isNum(r.predicted) && isNum(r.observed));
  if (!rows.length) return null;
  const host = h('div', { class: 'chart square', id: 'reliability' });
  const top = niceMax(Math.max(...rows.flatMap((r) => [r.predicted, r.observed])) * 1.05);
  responsive(host, (w0) => {
    const w = Math.min(w0, 460);
    const height = Math.round(w * 0.82);
    const mg = { t: 20, r: 16, b: 38, l: 44 };
    const x = scale(0, top, mg.l, w - mg.r);
    const y = scale(0, top, height - mg.b, mg.t);
    const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img', 'aria-label': 'Predicted chance against observed rate' });
    svg.append(s('text', { x: 0, y: 11, class: 'ax-title', text: 'Share that really flooded' }));
    for (const t of ticks(0, top, 4)) {
      svg.append(
        s('line', { x1: mg.l, x2: w - mg.r, y1: y(t), y2: y(t), class: 'grid' }),
        s('text', { x: mg.l - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'ax', text: fmtPct(t) }),
        s('text', { x: x(t), y: height - mg.b + 15, 'text-anchor': 'middle', class: 'ax', text: fmtPct(t) }));
    }
    svg.append(
      s('text', { x: (mg.l + w - mg.r) / 2, y: height - 4, 'text-anchor': 'middle', class: 'ax', text: 'Chance the model gave' }),
      s('line', { x1: x(0), y1: y(0), x2: x(top), y2: y(top), stroke: COLOR.ink3, 'stroke-width': 1 }),
      s('text', { x: x(top) - 4, y: y(top) + 14, 'text-anchor': 'end', class: 'ax', text: 'Perfect' }));
    for (const r of rows) {
      const dot = s('g', {
        tabindex: 0, role: 'img', 'aria-label': `Predicted ${fmtPct(r.predicted)}, observed ${fmtPct(r.observed)}`,
        onpointermove: (e) => showTip(e.clientX, e.clientY, [`Predicted ${fmtPct(r.predicted, 1)}`, { color: COLOR.blue, value: fmtPct(r.observed, 1), label: 'really flooded' }, ...(isNum(r.n) ? [{ value: fmtInt(r.n), label: 'district days' }] : [])]),
        onpointerleave: hideTip,
      },
      s('circle', { cx: x(r.predicted), cy: y(r.observed), r: 12, fill: 'transparent' }),
      s('circle', { cx: x(r.predicted), cy: y(r.observed), r: 4.5, fill: COLOR.blue, stroke: COLOR.paper, 'stroke-width': 2 }));
      svg.append(dot);
    }
    put(host, svg);
  });
  return section(5, 'Does the stated chance hold up?',
    'Each dot groups days the model scored alike. Dots on the line mean its stated chance can be taken at face value. Dots under the line mean it was too high.',
    host,
    tableTwin('Predicted against observed', [
      { label: 'Predicted', num: true, cell: (r) => fmtPct(r.predicted, 1) },
      { label: 'Observed', num: true, cell: (r) => fmtPct(r.observed, 1) },
      { label: 'District days', num: true, cell: (r) => fmtInt(r.n) },
    ], rows));
}

function ablation(m) {
  const rows = (m.ablation ?? []).filter((r) => isNum(r.pr_auc));
  if (!rows.length) return null;
  const sorted = [...rows].sort((a, b) => b.pr_auc - a.pr_auc);
  const withCaught = sorted.some((r) => isNum(r.caught_3d));
  return section(6, 'What each input is worth',
    'The model was retrained with one thing changed at a time, on 2006 to 2023. With about 22 events, small gaps here are noise. The calendar version scores best on this test and failed on unseen years, which is why cross-validation alone was not enough.',
    barList(sorted.map((r) => ({ label: r.variant, value: r.pr_auc, text: fmtDec(r.pr_auc, 3), strong: /full/i.test(r.variant) })), { label: 'PR-AUC by model variant' }),
    tableTwin('Model variants', [
      { label: 'Variant', key: 'variant' },
      { label: 'PR-AUC', num: true, cell: (r) => fmtDec(r.pr_auc, 3) },
      withCaught ? { label: 'Caught 3 days ahead', num: true, cell: (r) => fmtPct(r.caught_3d) } : null,
    ].filter(Boolean), sorted));
}

function floodTable(title, rows, extra, id) {
  const cols = [
    { label: 'Flood', key: 'event' },
    { label: 'First report', cell: (r) => (r.first_report ? fmtMedium(r.first_report) : 'n/a') },
    { label: 'Districts', key: 'districts', num: true },
    { label: 'Warned 3 days ahead', key: 'warned_3d', num: true },
    ...extra,
    { label: 'Median lead, days', num: true, cell: (r) => (isNum(r.median_lead) ? fmtDec(r.median_lead, 1).replace(/\.0$/, '') : 'n/a') },
  ];
  return h('div', { id }, dataTable(title, cols, rows));
}

function blindTest(m) {
  const v1 = m.version1?.blind;
  const v2 = m.version2;
  if (!v1?.events?.length) return null;
  const rate = (v1.alert_rate ?? []).map((r) => `${fmtPct(r.sajag, 1)} in ${r.year}`).join(', ');
  const rows = v2?.totals ? [
    { name: 'Sajag, version 2', key: 'sajag' },
    { name: 'Observed-data model alone', key: 'model_only' },
    { name: 'Rain-forecast rule alone', key: 'forecast_only' },
    { name: '3-day rain, same alert rate', key: 'rain_matched' },
    { name: 'River level, same alert rate', key: 'river_matched' },
  ].filter((r) => v2.totals[r.key]).map((r) => ({
    name: r.name, warned: v2.totals[r.key].warned_3d, rate: v2.totals[r.key].alert_rate,
    chance: v2.placebo?.[r.key]?.chance_mean, top: v2.placebo?.[r.key]?.chance_p95,
  })) : [];
  return section(1, 'The test we failed',
    'The floods were listed from press reports and committed to git before the model ran on these years. It ran once.',
    h('h3', { class: 'sub-title', text: 'Version 1, blind' }),
    h('p', { class: 'read', text: `The Warning level fired on ${rate || 'very few days'}, against a designed 5%. Nearly every miss came from a model that had learned the calendar, or had barely seen the Ganga.` }),
    floodTable('Version 1 on the blind test', v1.events, [
      { label: 'Watch, 3 days', key: 'watch_3d', num: true },
      { label: '3-day rain rule', key: 'rain_3d', num: true },
      { label: 'River level rule', key: 'river_3d', num: true },
    ], 'blind-table'),
    v2?.events?.length ? h('h3', { class: 'sub-title', text: 'Version 2, not blind' }) : null,
    v2?.events?.length ? h('p', { class: 'read', text: 'Three changes: no calendar input, the 2016 Ganga flood restored to training, and a rule that raises the alert when extreme rain is forecast. The forecasts are the ones really issued at the time, so nothing from the future leaks in. But these changes were made after seeing the failure above, so this is not a clean test.' }) : null,
    v2?.events?.length ? floodTable('Version 2 on the same floods', v2.events, [
      { label: '3-day rain, same alerts', key: 'rain_3d', num: true },
      { label: 'River level, same alerts', key: 'river_3d', num: true },
    ], 'v2-table') : null,
    v2?.spatial?.length ? h('h3', { class: 'sub-title', text: 'Right place, or everywhere?' }) : null,
    v2?.spatial?.length ? h('p', { class: 'read', text: 'Districts named in reports against all others, in the same 7 to 3 days before the first report. Press lists are incomplete, so some other districts may really have flooded, but a warning that covers everywhere helps nobody.' }) : null,
    v2?.spatial?.length ? dataTable('Named districts against the rest', [
      { label: 'Flood', key: 'event' },
      { label: 'Named districts warned', num: true, cell: (r) => of(r.named_warned, r.named) },
      { label: 'Other districts warned', num: true, cell: (r) => of(r.other_warned, r.other) },
    ], v2.spatial) : null,
    rows.length ? h('h3', { class: 'sub-title', text: 'Could this be luck?' }) : null,
    rows.length ? h('p', { class: 'read', text: 'Alerts come in clumps, so a rule can catch floods by accident. Each flood was moved to random days of the same monsoon 2,000 times and scored again. The last two columns show what that gave. A rule that beats the 95th percentile is unlikely to be luck, though the test is generous to version 2, which was built after seeing these floods.' }) : null,
    rows.length ? dataTable('Floods warned against chance', [
      { label: 'Rule', key: 'name' },
      { label: `Warned, of ${v2.district_events}`, key: 'warned', num: true },
      { label: 'Alert rate', num: true, cell: (r) => fmtPct(r.rate, 1) },
      { label: 'By chance, average', num: true, cell: (r) => (isNum(r.chance) ? fmtDec(r.chance, 1) : 'n/a') },
      { label: 'By chance, 95th percentile', num: true, cell: (r) => (isNum(r.top) ? fmtDec(r.top, 0) : 'n/a') },
    ], rows) : null);
}

function drought(m) {
  const d = m.drought;
  if (!d) return null;
  // The contract says `share`; sajag/drought.py calls the same column `aug_share`.
  const rows = [...(d.rows ?? [])].filter((r) => isNum(r.year)).map((r) => ({ ...r, share: r.share ?? r.aug_share })).sort((a, b) => a.year - b.year);
  const host = h('div', { class: 'chart', id: 'drought-years' });
  const top = niceMax(Math.max(...rows.map((r) => r.share ?? 0), 0.1));
  if (rows.length) {
    responsive(host, (w) => {
      const height = 190;
      const mg = { t: 20, r: 4, b: 26, l: 38 };
      const slot = (w - mg.l - mg.r) / rows.length;
      const bar = Math.max(1, Math.min(24, slot - 2));
      const y = scale(0, top, height - mg.b, mg.t);
      const svg = s('svg', { width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img', 'aria-label': 'Share of districts in drought by year' });
      svg.append(s('text', { x: 0, y: 11, class: 'ax-title', text: 'Share of districts in drought' }));
      for (const t of ticks(0, top, 3)) {
        svg.append(
          s('line', { x1: mg.l, x2: w - mg.r, y1: y(t), y2: y(t), class: 'grid' }),
          s('text', { x: mg.l - 6, y: y(t) + 3.5, 'text-anchor': 'end', class: 'ax', text: fmtPct(t) }));
      }
      const every = slot < 30 ? Math.ceil(30 / slot) : 1;
      rows.forEach((r, n) => {
        const cx = mg.l + slot * n + slot / 2;
        const v = r.share ?? 0;
        svg.append(s('g', {
          onpointermove: (e) => showTip(e.clientX, e.clientY, [String(r.year), { value: fmtPct(v), label: 'of districts in drought' }, r.declared ? 'Drought declared' : 'Not declared']),
          onpointerleave: hideTip,
        },
        s('rect', { x: cx - slot / 2, y: mg.t, width: slot, height: height - mg.b - mg.t, fill: 'transparent' }),
        s('rect', { x: cx - bar / 2, y: y(v), width: bar, height: Math.max(0, y(0) - y(v)), fill: r.declared ? COLOR.ink : '#BDB3A2' })));
        if (n % every === 0) svg.append(s('text', { x: cx, y: height - 8, 'text-anchor': 'middle', class: 'ax', text: String(r.year) }));
      });
      put(host, svg);
    });
  }
  const scopes = new Map((ctx.drought?.declared ?? []).map((x) => [x.year, x.scope]));
  return section(7, 'Drought',
    'Each bar is how much of Bihar was dry by the rainfall index. Black bars are years the state declared drought.',
    isNum(d.auc_august) ? h('p', { class: 'read read-lg' }, h('strong', { text: fmtDec(d.auc_august, 2) }), ' AUC at the end of August, and ', h('strong', { text: fmtDec(d.auc_july_forecast, 2) }), ' from the forecast at the end of July. Pick one declared year and one other: this is how often the declared year scored drier. 0.5 is a coin toss and 1 is perfect.') : null,
    d.note ? h('p', { class: 'read', text: d.note }) : null,
    d.forecast ? h('p', { class: 'read', text: `Month to month the forecast only just beats assuming nothing changes: AUC ${fmtDec(d.forecast.auc_model, 3)} against ${fmtDec(d.forecast.auc_persistence, 3)}.` }) : null,
    rows.length ? h('ul', { class: 'key' },
      h('li', null, h('span', { class: 'key-box', style: { background: COLOR.ink } }), h('span', { text: 'Drought declared' })),
      h('li', null, h('span', { class: 'key-box', style: { background: '#BDB3A2' } }), h('span', { text: 'Not declared' }))) : null,
    rows.length ? host : null,
    rows.length ? tableTwin('Drought by year', [
      { label: 'Year', key: 'year', num: true },
      { label: 'Share of districts', num: true, cell: (r) => fmtPct(r.share) },
      { label: 'Declared', cell: (r) => (r.declared ? (scopes.get(r.year) ?? 'Yes') : 'No') },
    ], rows) : null);
}

function exposure(m) {
  const e = m.exposure;
  if (!e) return null;
  const rows = [
    isNum(e.high_flooded) ? { label: 'High exposure villages', value: e.high_flooded, text: fmtPct(e.high_flooded), strong: true } : null,
    isNum(e.medium_flooded) ? { label: 'Medium exposure villages', value: e.medium_flooded, text: fmtPct(e.medium_flooded) } : null,
    isNum(e.low_flooded) ? { label: 'Low exposure villages', value: e.low_flooded, text: fmtPct(e.low_flooded) } : null,
  ].filter(Boolean);
  return section(8, 'Village exposure',
    'The score uses a satellite water record ending in 2021 and land height, so it knows nothing of 2024. It is tested here on a Sentinel-1 flood map of the Kosi plain from 9 October 2024.',
    isNum(e.ratio) ? h('p', { class: 'read read-lg' }, 'Flood water was mapped within 500 m of high exposure villages ', h('strong', { text: `${fmtDec(e.ratio, 1).replace(/\.0$/, '')} times` }), ' as often as low exposure ones',
      isNum(e.villages) ? `, across ${fmtInt(e.villages)} villages. One flood, one date, one area.` : '.') : null,
    rows.length ? barList(rows, { max: 1, label: 'Share of villages with flood water mapped within 500 m' }) : null);
}

function dataStory(m) {
  if (!m.data_story?.length) return null;
  return section(9, 'The data, and what was wrong with it',
    'The problems found in the data, and what was done about each.',
    h('ol', { class: 'plain-list', id: 'data-story' }, m.data_story.map((t) => h('li', { text: t }))));
}

export function renderEvidence(host) {
  const m = ctx.metrics;
  if (!m) {
    put(host, h('div', { class: 'doc-head' }, h('h1', { class: 'doc-h1', text: 'Evidence' }), h('p', { class: 'read', text: 'The results file is not available.' })));
    return;
  }
  const lead = [hero(m), limits(m)].filter(Boolean);
  put(host,
    h('div', { class: 'doc-head' },
      h('h1', { class: 'doc-h1', text: 'Evidence' }),
      h('p', { class: 'doc-lede', text: 'Where the system failed, what changed, and how far to trust it.' })),
    lead.length ? h('div', { class: 'doc-lead' }, lead) : null,
    ...[blindTest, riverSkill, budgetCompare, impact, reliability, ablation, drought, exposure, dataStory].map((f) => f(m)).filter(Boolean));
}
