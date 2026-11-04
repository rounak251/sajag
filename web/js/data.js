// Reads the files described in docs/DATA_CONTRACT.md. Paths are relative so the page works from
// any subpath. Only meta.json, districts.geojson and one hindcast year are required: everything
// else resolves to null and the view that needs it says so.
import { dayNumber, isNum } from './util.js';

const cache = new Map();
const LEVEL_FALLBACK = [
  { id: 0, en: 'Normal' }, { id: 1, en: 'Watch' }, { id: 2, en: 'Warning' }, { id: 3, en: 'Severe' },
];
export const ctx = {
  meta: null, geo: null, rivers: null, sites: [], siteById: new Map(), drought: null, live: null,
  alerts: null, metrics: null, districts: new Map(), levels: LEVEL_FALLBACK,
};

export function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path);
}
export const optional = (path) => getJSON(path).catch(() => null);

export const levelOf = (id) => ctx.levels.find((l) => l.id === id) ?? LEVEL_FALLBACK[id] ?? LEVEL_FALLBACK[0];
// Held out: these floods were never training data, but version 2 was designed after seeing version 1
// fail on them, so they are not a blind test. The Evidence page explains the difference.
export const isHeldOut = (year, H) => Boolean(H?.held_out) || (ctx.meta?.held_out_years ?? []).includes(year);
export const districtName = (key) => ctx.districts.get(key)?.name ?? key.replace(/_/g, ' ');

// How long a recorded flood stays outlined after its last day, so it can be read while playing.
export const OUTLINE_HOLD_DAYS = 6;

function buildEvents(raw, indexOf) {
  const groups = new Map();
  for (const r of raw.records ?? []) {
    if (!r?.start) continue;
    const label = r.label || 'Recorded flood';
    const id = `${label}|${r.start}`;
    if (!groups.has(id)) {
      groups.set(id, { id, label, start: r.start, end: r.end || r.start, rows: [], source: r.source, url: r.url });
    }
    const g = groups.get(id);
    g.rows.push(r);
    if ((r.end || r.start) > g.end) g.end = r.end || r.start;
    if (!g.url && r.url) g.url = r.url;
  }
  const events = [...groups.values()].map((g) => ({
    ...g,
    i: indexOf(g.start),
    iEnd: indexOf(g.end),
    keys: [...new Set(g.rows.map((r) => r.district).filter((k) => ctx.districts.has(k)))],
  }));
  return events.filter((e) => e.i !== null).sort((a, b) => a.i - b.i);
}

export async function loadYear(year) {
  const raw = await getJSON(`data/hindcast/${year}.json`);
  if (raw._ready) return raw;
  const first = dayNumber(raw.dates[0]);
  const last = raw.dates.length - 1;
  const indexOf = (iso) => {
    const i = dayNumber(iso) - first;
    if (i > last + 30 || i < -30) return null;
    return Math.max(0, Math.min(last, i));
  };
  raw.indexOf = indexOf;
  raw.dj = new Map(raw.districts.map((k, j) => [k, j]));
  raw.sk = new Map((raw.sites ?? []).map((id, k) => [id, k]));
  raw.leads = Object.keys(raw.risk ?? {}).sort((a, b) => a - b);
  raw.events = buildEvents(raw, indexOf);
  raw.levelAt = (i, key) => {
    const v = raw.level?.[i]?.[raw.dj.get(key)];
    return isNum(v) ? v : 0;
  };
  raw.riskAt = (lead, i, key) => {
    const v = raw.risk?.[lead]?.[i]?.[raw.dj.get(key)];
    return isNum(v) ? v : null;
  };
  // True when the rain forecast, not the observed-data model, set this level.
  raw.raisedAt = (i, key) => Boolean(raw.raised?.[i]?.[raw.dj.get(key)]);
  raw.rainAt = (i, key) => raw.rain_mm?.[i]?.[raw.dj.get(key)] ?? null;
  raw.reasonsAt = (i, key) => raw.reasons?.[`${i}:${raw.dj.get(key)}`] ?? [];
  raw.counts = (i) => {
    const out = ctx.levels.map(() => 0);
    for (const v of raw.level?.[i] ?? []) if (out[v] !== undefined) out[v] += 1;
    return out;
  };
  raw.activeEvents = (i) => raw.events.filter((e) => e.i <= i && i <= e.iEnd + OUTLINE_HOLD_DAYS);
  raw._ready = true;
  return raw;
}

// The level each flooded district stood at, on the days before the first report.
export function beforeMatrix(H, event) {
  const offsets = H.leads.map(Number).sort((a, b) => b - a);
  const rows = offsets.filter((d) => event.i - d >= 0).map((d) => ({
    days: d,
    cells: event.keys.map((key) => ({
      key, level: H.levelAt(event.i - d, key), risk: H.riskAt(H.leads[0], event.i - d, key),
    })),
  }));
  return { rows, total: event.keys.length };
}

export function droughtMonthIndex(drought, iso) {
  if (!drought?.months?.length) return null;
  const want = Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7));
  let best = 0;
  let gap = Infinity;
  drought.months.forEach((m, i) => {
    const d = Math.abs(Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - want);
    if (d < gap) { gap = d; best = i; }
  });
  return best;
}

// Districts have no gauge list in the contract, so "nearby" means nearest by great-circle distance.
export function nearestSites(key, count = 3) {
  const c = ctx.districts.get(key)?.center;
  if (!c) return [];
  const rad = Math.PI / 180;
  const km = (s) => {
    const a = Math.sin(((s.lat - c.lat) * rad) / 2) ** 2
      + Math.cos(c.lat * rad) * Math.cos(s.lat * rad) * Math.sin(((s.lon - c.lon) * rad) / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(a));
  };
  return ctx.sites
    .filter((s) => isNum(s.lat) && isNum(s.lon))
    .map((s) => ({ ...s, km: km(s) }))
    .sort((a, b) => a.km - b.km)
    .slice(0, count);
}

// Label point: the most interior of a grid of samples, so names sit inside crescent shapes.
function ringsOf(geometry) {
  if (geometry.type === 'Polygon') return [geometry.coordinates];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates;
  return [];
}
function area(ring) {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    a += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
  }
  return Math.abs(a / 2);
}
function inside(pt, ring) {
  let hit = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}
function edgeDistance(pt, ring) {
  let best = Infinity;
  const stride = Math.max(1, Math.floor(ring.length / 80));
  for (let i = 0; i < ring.length; i += stride) {
    best = Math.min(best, (ring[i][0] - pt[0]) ** 2 + (ring[i][1] - pt[1]) ** 2);
  }
  return best;
}
function labelPoint(geometry) {
  const polys = ringsOf(geometry);
  const main = polys.reduce((a, b) => (area(b[0]) > area(a[0]) ? b : a), polys[0]);
  const ring = main[0];
  const xs = ring.map((c) => c[0]);
  const ys = ring.map((c) => c[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  let best = [(x0 + x1) / 2, (y0 + y1) / 2];
  let score = -1;
  for (let a = 1; a < 14; a += 1) {
    for (let b = 1; b < 14; b += 1) {
      const pt = [x0 + ((x1 - x0) * a) / 14, y0 + ((y1 - y0) * b) / 14];
      if (!inside(pt, ring)) continue;
      const d = edgeDistance(pt, ring);
      if (d > score) { score = d; best = pt; }
    }
  }
  return { lon: best[0], lat: best[1], area: polys.reduce((t, p) => t + area(p[0]), 0) };
}

export async function loadCore() {
  const [meta, geo] = await Promise.all([getJSON('data/meta.json'), getJSON('data/districts.geojson')]);
  ctx.meta = meta;
  ctx.geo = geo;
  if (meta.levels?.length) ctx.levels = meta.levels;
  for (const f of geo.features ?? []) {
    const p = f.properties ?? {};
    if (!p.key) continue;
    const c = labelPoint(f.geometry);
    ctx.districts.set(p.key, { key: p.key, name: p.name ?? p.key, name_hi: p.name_hi, center: { lat: c.lat, lon: c.lon }, area: c.area });
  }
}

export async function loadMapExtras() {
  const [rivers, sites] = await Promise.all([optional('data/rivers.geojson'), optional('data/sites.json')]);
  ctx.rivers = rivers;
  ctx.sites = Array.isArray(sites) ? sites : [];
  ctx.siteById = new Map(ctx.sites.map((s) => [s.id, s]));
}

export async function loadRest() {
  const [drought, live, alerts, metrics] = await Promise.all([
    optional('data/drought.json'), optional('data/live.json'),
    optional('data/alerts.json'), optional('data/metrics.json'),
  ]);
  Object.assign(ctx, { drought, live, alerts, metrics });
  if (drought?.districts) drought.dj = new Map(drought.districts.map((k, j) => [k, j]));
}
