// Wires the store to the views, owns playback and the URL.
import { ctx, droughtMonthIndex, isHeldOut, levelOf, loadCore, loadMapExtras, loadRest, loadYear, districtName } from './data.js';
import { state, set, subscribe } from './state.js';
import { $, h, calm, choiceGroup, fmtInt, fmtLong, fmtMedium, fmtSigned, isNum, plural } from './util.js';
import { createMap, droughtClass } from './map.js';
import { createTimeline } from './timeline.js';
import { createPanel, siteStatus } from './panel.js';
import { renderHead, renderLegend } from './overlay.js';
import { renderEvidence } from './evidence.js';
import { renderToday, todayLine } from './today.js';

const STEP_MS = 420;
const FLOOD_HOLD_MS = 1600;
let mapView = null;
let timeline = null;
let panel = null;
let timer = null;
const rendered = { evidence: false, today: false };
let storyWaiting = null;
let restReady = false;

const storyById = (id) => ctx.meta.stories?.find((st) => st.id === id);
const currentStory = () => storyById(state.story);

function windowRange() {
  const H = ctx.H;
  if (!H) return [0, 0];
  const st = currentStory();
  if (state.windowMode === 'story' && st && st.year === H.year) {
    const a = H.indexOf(st.start) ?? 0;
    const b = H.indexOf(st.end) ?? H.dates.length - 1;
    if (b > a) return [a, b];
  }
  return [0, H.dates.length - 1];
}

function atEnd() { return state.i >= windowRange()[1]; }

function stop() {
  clearTimeout(timer);
  timer = null;
  set({ playing: false });
}
function tick() {
  const [, b] = windowRange();
  if (state.i >= b) { stop(); return; }
  const next = state.i + 1;
  set({ i: next });
  const onFlood = ctx.H.events.some((e) => e.i === next);
  timer = setTimeout(tick, onFlood ? FLOOD_HOLD_MS : STEP_MS);
}
function play() {
  const [a, b] = windowRange();
  clearTimeout(timer);
  if (state.i >= b || state.i < a) set({ i: a });
  set({ playing: true });
  timer = setTimeout(tick, STEP_MS);
}
const togglePlay = () => (state.playing ? stop() : play());

async function setYear(year) {
  const box = $('.stage');
  box.classList.add('is-loading');
  const H = await loadYear(year).finally(() => box.classList.remove('is-loading'));
  ctx.H = H;
  return H;
}

async function startStory(story, { autoplay }) {
  stop();
  const H = await setYear(story.year).catch(() => null);
  if (!H) return;
  state.userPickedLevel = false;
  const start = H.indexOf(story.start) ?? 0;
  const end = H.indexOf(story.end) ?? H.dates.length - 1;
  // With reduced motion nothing runs on its own: open on the first recorded flood instead.
  const still = H.events.find((e) => e.i >= start && e.i <= end)?.i ?? end;
  const focus = ctx.districts.has(story.focus) ? story.focus : null;
  set({ year: story.year, story: story.id, windowMode: 'story', district: focus, site: null, i: autoplay && !calm() ? start : still });
  redrawTimeline();
  mapView?.fitState(true);
  if (autoplay && !calm()) play();
}

async function pickYear(year) {
  stop();
  const H = await setYear(year).catch(() => null);
  if (!H) {
    $('#year').value = String(state.year); // that year's file is missing: stay on the one that works
    return;
  }
  const peak = (H.statewide ?? []).reduce((best, v, i, all) => (v > all[best] ? i : best), 0);
  set({ year, story: null, windowMode: 'season', i: peak });
  redrawTimeline();
}

function pickDistrict(key, { zoom = true } = {}) {
  set({ district: key, site: null });
  if (key && zoom) mapView?.zoomTo(key);
  if (!key) mapView?.fitState(true);
}

function redrawTimeline() { timeline?.draw(); }

function renderStories() {
  const host = $('#stories');
  const stories = (ctx.meta.stories ?? []).filter((st) => (ctx.meta.years ?? []).includes(st.year));
  if (!stories.length) { host.hidden = true; return; }
  const row = h('div', { class: 'story-row', role: 'group', 'aria-label': 'Guided replays' },
    h('span', { class: 'ctl-label', text: 'Replay a flood' }),
    stories.map((st) => h('button', {
      type: 'button', class: 'story', 'data-story': st.id, 'aria-pressed': 'false',
      onclick: () => startStory(st, { autoplay: true }),
    }, h('span', { text: st.title }), st.held_out ? h('span', { class: 'story-tag', text: 'Not in training' }) : null)));
  host.replaceChildren(row, h('p', { class: 'story-caption', id: 'story-caption' }));
}
function paintStories() {
  const st = currentStory();
  for (const b of document.querySelectorAll('.story')) b.setAttribute('aria-pressed', String(b.dataset.story === state.story));
  const cap = $('#story-caption');
  if (cap) {
    cap.textContent = st?.caption ?? 'Choose a replay above, or drag the timeline to any day.';
  }
}

let leadGroup = null;
let layerGroup = null;
function renderControls() {
  const H = ctx.H;
  const years = [...(ctx.meta.years ?? [])].sort((a, b) => b - a);
  const yearSelect = h('select', { id: 'year', 'aria-label': 'Year', onchange: (e) => pickYear(Number(e.target.value)) },
    years.map((y) => h('option', { value: y, text: isHeldOut(y) ? `${y}, not in training` : String(y) })));
  yearSelect.value = String(state.year);
  leadGroup = choiceGroup({
    label: 'Days ahead', value: state.lead, onChange: (v) => set({ lead: v }), className: 'lead-pick',
    options: (H?.leads ?? []).map((l) => ({ value: l, label: l })),
  });
  layerGroup = choiceGroup({
    label: 'Map layer', value: state.layer, onChange: (v) => set({ layer: v }), className: 'layer-pick',
    options: [{ value: 'flood', label: 'Flood level' }, { value: 'drought', label: 'Drought', id: 'layer-drought' }],
  });
  $('#controls').replaceChildren(
    h('label', { class: 'ctl' }, h('span', { class: 'ctl-label', text: 'Year' }), yearSelect),
    h('div', { class: 'ctl' }, h('span', { class: 'ctl-label', text: 'Risk within' }), leadGroup, h('span', { class: 'ctl-unit', text: 'days' })),
    h('div', { class: 'ctl' }, h('span', { class: 'ctl-label', text: 'Show' }), layerGroup));
}

function paintMap() {
  const H = ctx.H;
  if (!H || !mapView) return;
  const drought = state.layer === 'drought' && ctx.drought;
  if (drought) mapView.paintDrought(ctx.drought, droughtMonthIndex(ctx.drought, H.dates[state.i]));
  else mapView.paintFlood(H, state.i, state.lead);
  mapView.setOutlines(drought ? [] : [...new Set(H.activeEvents(state.i).flatMap((e) => e.keys))]);
  mapView.paintGauges((id) => siteStatus(H, id, state.i));
  renderHead($('#map-head'));
  renderLegend($('#legend'));
}

function tipFor(key) {
  const H = ctx.H;
  const rows = [districtName(key)];
  if (state.layer === 'drought' && ctx.drought) {
    const D = ctx.drought;
    const m = droughtMonthIndex(D, H.dates[state.i]);
    const v = D.spi3?.[m]?.[D.dj.get(key)];
    rows.push({ value: fmtSigned(v), label: `SPI-3, ${isNum(v) ? droughtClass(v).label.toLowerCase() : 'no data'}` });
    if (isNum(D.chance?.[m]?.[D.dj.get(key)])) rows.push({ value: `${D.chance[m][D.dj.get(key)]}%`, label: 'chance of drought next month' });
    return rows;
  }
  rows.push({ value: levelOf(H.levelAt(state.i, key)).en, label: 'flood level' });
  const risk = H.riskAt(state.lead, state.i, key);
  if (H.raisedAt(state.i, key)) rows.push({ value: `${H.rainAt(state.i, key)} mm`, label: 'rain forecast, next 5 days' });
  else if (isNum(risk)) rows.push({ value: `${risk}%`, label: `chance within ${plural(Number(state.lead), 'day')}` });
  for (const e of H.activeEvents(state.i)) if (e.keys.includes(key)) rows.push(`On record: ${e.label}`);
  return rows;
}

function gaugeTip(site) {
  const H = ctx.H;
  const k = H.sk.get(site.id);
  const rows = [`${site.river} at ${site.site}`];
  rows.push({ value: `${fmtInt(H.q?.[state.i]?.[k])} m³/s`, label: `flow on ${fmtMedium(H.dates[state.i])}` });
  if (isNum(site.p95)) rows.push({ value: fmtInt(site.p95), label: 'p95, high' });
  if (isNum(site.p99)) rows.push({ value: fmtInt(site.p99), label: 'p99, extreme' });
  return rows;
}

function zoomControl() {
  if (!currentStory()) return null;
  return choiceGroup({
    label: 'Timeline range', value: state.windowMode, className: 'tl-range',
    onChange: (v) => { set({ windowMode: v }); redrawTimeline(); panel.update({ all: true }); },
    options: [{ value: 'story', label: 'Story' }, { value: 'season', label: 'Season' }],
  });
}

function mapTools() {
  $('#map-tools').replaceChildren(
    h('button', { type: 'button', class: 'tool', 'aria-label': 'Zoom in', onclick: () => mapView.zoomBy(0.6), text: '+' }),
    h('button', { type: 'button', class: 'tool', 'aria-label': 'Zoom out', onclick: () => mapView.zoomBy(-0.6), text: '−' }),
    h('button', { type: 'button', class: 'tool tool-wide', id: 'reset-view', onclick: () => mapView.fitState(true), text: 'All Bihar' }));
}

function writeURL() {
  if (state.route !== 'map' || state.playing || !ctx.H) return;
  const p = new URLSearchParams({ year: state.year, date: ctx.H.dates[state.i], lead: state.lead });
  if (state.district) p.set('district', state.district);
  if (state.layer !== 'flood') p.set('layer', state.layer);
  if (state.panelTab !== 'district') p.set('tab', state.panelTab);
  if (state.story) p.set('story', state.story);
  history.replaceState(null, '', `#/map?${p}`);
}

function parseHash() {
  const [path, query] = location.hash.replace(/^#\/?/, '').split('?');
  return { route: ['map', 'evidence', 'today'].includes(path) ? path : 'map', params: new URLSearchParams(query ?? '') };
}

function showRoute() {
  const { route } = state;
  for (const name of ['map', 'evidence', 'today']) $(`#screen-${name}`).hidden = name !== route;
  for (const a of document.querySelectorAll('.tabs-main a')) {
    if (a.dataset.route === route) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  document.title = { map: 'Sajag: flood and drought early warning for Bihar', evidence: 'Evidence | Sajag', today: 'Today | Sajag' }[route];
  document.documentElement.dataset.route = route;
  window.scrollTo(0, 0);
  if (route !== 'map') stop();
  else {
    mapView?.resize();
    if (storyWaiting) {
      const story = storyWaiting;
      storyWaiting = null;
      startStory(story, { autoplay: true });
    }
  }
  renderDocs();
}

function renderDocs() {
  if (!restReady) return;
  if (state.route === 'evidence' && !rendered.evidence) {
    rendered.evidence = true;
    renderEvidence($('#screen-evidence'));
  }
  if (state.route === 'today' && !rendered.today) {
    rendered.today = true;
    renderToday($('#screen-today'));
  }
}

subscribe((c) => {
  if (c.route) showRoute();
  if (!ctx.H || !mapView) return;
  if (c.year || c.i || c.lead || c.layer || c.district) paintMap();
  if (c.year) {
    if ($('#year')) $('#year').value = String(state.year);
  }
  if (c.story || c.windowMode) paintStories();
  if (c.i) timeline.move();
  if (c.district) mapView.setSelected(state.district);
  if (c.playing || c.i) timeline.setPlaying(state.playing, atEnd());
  if (c.year || c.i || c.lead || c.layer || c.district || c.site || c.panelTab || c.alertLang || c.alertLevel) panel.update(c);
  if (!state.playing && (c.playing || c.i || c.lead || c.layer || c.district || c.panelTab || c.year)) writeURL();
});

const measureTop = () => document.documentElement.style.setProperty('--mast-h', `${$('#top').offsetHeight}px`);
new ResizeObserver(measureTop).observe($('#top'));

async function boot() {
  await loadCore();
  const { route, params } = parseHash();
  const meta = ctx.meta;
  if (meta.mock) {
    const banner = $('#mock-banner');
    banner.hidden = false;
    banner.textContent = 'Mock data for building and testing. Every model number on this page is invented.';
  }

  const stories = (meta.stories ?? []).filter((st) => (meta.years ?? []).includes(st.year));
  const askedYear = Number(params.get('year'));
  const deepLink = params.has('date') || params.has('year');
  const first = stories[0];
  const year = (meta.years ?? []).includes(askedYear) ? askedYear : first?.year ?? Math.max(...(meta.years ?? []));

  await Promise.all([loadMapExtras(), setYear(year)]);

  const H = ctx.H;
  if (H.leads.length && !H.leads.includes(state.lead)) state.lead = H.leads[0];
  if (params.has('lead') && H.leads.includes(params.get('lead'))) state.lead = params.get('lead');
  state.year = year;
  state.route = route;

  mapView = createMap('map', { onPick: (key) => pickDistrict(key), tipFor, gaugeTip });
  mapTools();
  renderControls();
  renderStories();
  timeline = createTimeline($('#timeline'), {
    getH: () => ctx.H, getWindow: windowRange, getIndex: () => state.i, zoomControl,
    onSeek: (i, jump) => { if (state.playing || jump) stop(); set({ i }); },
    onTogglePlay: togglePlay,
  });
  panel = createPanel($('#panel'), { onPick: (key) => pickDistrict(key) });
  panel.bind({ range: windowRange, villagesLoaded: (rows) => { mapView.setVillages(rows); renderLegend($('#legend')); } });

  showRoute();

  const asked = storyById(params.get('story'));
  if (asked && asked.year === year) state.story = asked.id;
  if (deepLink) {
    const i = params.has('date') ? H.indexOf(params.get('date')) ?? 0 : (H.statewide ?? []).reduce((best, v, n, all) => (v > all[best] ? n : best), 0);
    if (state.story) state.windowMode = 'story';
    state.layer = params.get('layer') === 'drought' ? 'drought' : 'flood';
    state.panelTab = params.get('tab') === 'alert' ? 'alert' : 'district';
    state.i = i;
    state.district = ctx.districts.has(params.get('district')) ? params.get('district') : null;
    layerGroup.setValue(state.layer);
    leadGroup.setValue(state.lead);
    paintStories();
    paintMap();
    mapView.setSelected(state.district);
    redrawTimeline();
    panel.update({ all: true });
    timeline.setPlaying(false, atEnd());
    if (state.district) mapView.zoomTo(state.district);
  } else if (first && route === 'map') {
    panel.update({ all: true });
    await startStory(first, { autoplay: true });
  } else {
    if (first) {
      state.story = first.id;
      state.windowMode = 'story';
      state.i = H.indexOf(first.start) ?? 0;
      storyWaiting = first;
    }
    paintStories();
    paintMap();
    redrawTimeline();
    panel.update({ all: true });
    timeline.setPlaying(false, atEnd());
  }

  document.documentElement.dataset.ready = 'map';

  await loadRest();
  restReady = true;
  const line = todayLine();
  const strip = $('#today-strip');
  if (line) {
    strip.hidden = false;
    strip.replaceChildren(h('span', { class: 'strip-label', text: `Today, ${fmtLong(ctx.live?.issued ?? meta.issued)}` }), h('span', { text: line }));
  }
  if (!ctx.drought) {
    const b = $('#layer-drought');
    if (b) { b.disabled = true; b.title = 'Drought data is not available'; }
  }
  renderDocs();
  paintMap();
  panel.update({ all: true });
  document.documentElement.dataset.ready = 'all';
}

window.addEventListener('hashchange', () => {
  const { route } = parseHash();
  set({ route });
});

document.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' || state.route !== 'map') return;
  if (e.target.closest?.('button, a, input, select, textarea, audio, summary')) return;
  e.preventDefault();
  togglePlay();
});

$('.skip').addEventListener('click', (e) => {
  e.preventDefault();
  $('#main').focus();
});

boot().catch((err) => {
  console.warn(err);
  $('#main').replaceChildren(h('div', { class: 'fatal' },
    h('h1', { text: 'The data could not be loaded.' }),
    h('p', { text: 'The page needs its data files, and it has to be opened through a web server, not as a local file.' })));
  document.documentElement.dataset.ready = 'failed';
});

window.__sajag = { state, ctx };
