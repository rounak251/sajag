// The map, drawn from GeoJSON alone with Leaflet's SVG renderer: no tiles, no WebGL. SVG keeps
// the hatch fills crisp at any zoom and lets one <pattern> serve the map and the legend alike.
import { ctx } from './data.js';
import { h, calm, isNum, fmtInt, fmtSigned } from './util.js';
import { showTip, hideTip } from './charts.js';

const L = window.L;
const INK = '#1E1B16';
const PAPER = '#F6F1E7';
const BLUE = '#1C5A87';
const RULE = '#D5CBB8';

export const LAND = '#EAE3D3';
export const LEVEL_FILL = [LAND, 'url(#lv1)', 'url(#lv2)', 'url(#lv3)'];

// "At or below -1 means drought" is the contract's line; the finer steps are the usual SPI classes.
export const DROUGHT_CLASSES = [
  { id: 'extreme', upTo: -2, label: 'Extreme drought', range: '−2 or below', fill: 'url(#dr3)', dark: true },
  { id: 'severe', upTo: -1.5, label: 'Severe drought', range: '−2 to −1.5', fill: 'url(#dr2)', dark: true },
  { id: 'moderate', upTo: -1, label: 'Moderate drought', range: '−1.5 to −1', fill: 'url(#dr1)' },
  { id: 'normal', upTo: 1, label: 'Near normal', range: '−1 to 1', fill: LAND },
  { id: 'wet', upTo: Infinity, label: 'Wetter than normal', range: 'above 1', fill: '#B9CFDB' },
];
export const droughtClass = (v) => DROUGHT_CLASSES.find((c) => v <= c.upTo) ?? DROUGHT_CLASSES[3];

const VILLAGE_STYLE = [
  { radius: 2.6, fillColor: PAPER, color: '#6B6354' },
  { radius: 3.6, fillColor: '#D9932A', color: INK },
  { radius: 4.8, fillColor: '#7C2512', color: PAPER },
];
const MAX_VILLAGE_DOTS = 800;

// Context only, so the viewer can see which way the water comes from.
const NEIGHBOURS = [
  ['Nepal', 27.2, 86.3], ['Uttar Pradesh', 26.72, 83.62], ['Jharkhand', 24.5, 87.45], ['West Bengal', 25.1, 87.9],
];

function linesOf(geometry) {
  if (geometry?.type === 'LineString') return [geometry.coordinates];
  if (geometry?.type === 'MultiLineString') return geometry.coordinates;
  return [];
}

function riverLabels() {
  const best = new Map();
  for (const f of ctx.rivers?.features ?? []) {
    const name = f.properties?.name;
    if (!name) continue;
    for (const line of linesOf(f.geometry)) {
      if (line.length > (best.get(name)?.length ?? 1)) best.set(name, line);
    }
  }
  return [...best].map(([name, line]) => {
    const i = Math.floor(line.length * 0.55);
    const a = line[Math.max(0, i - 2)];
    const b = line[Math.min(line.length - 1, i + 2)];
    let deg = (Math.atan2(-(b[1] - a[1]), (b[0] - a[0]) * 0.9) * 180) / Math.PI;
    if (deg > 90) deg -= 180;
    if (deg < -90) deg += 180;
    return { name, lat: line[i][1], lon: line[i][0], deg: Math.round(deg) };
  });
}

export function createMap(hostId, { onPick, tipFor, gaugeTip }) {
  const host = document.getElementById(hostId);
  const touch = matchMedia('(pointer: coarse)').matches;
  const map = L.map(host, {
    zoomControl: false, attributionControl: false, zoomSnap: 0, zoomDelta: 0.6, minZoom: 5, maxZoom: 13,
    boxZoom: false, fadeAnimation: false, zoomAnimation: !calm(), markerZoomAnimation: !calm(),
    // One finger scrolls the page on phones; two fingers move the map.
    dragging: !touch,
  });
  // A plain wheel scrolls the page. Ctrl or Cmd and wheel, or a trackpad pinch, zooms the map.
  host.addEventListener('wheel', (e) => {
    if (!e.ctrlKey && !e.metaKey) e.stopImmediatePropagation();
  }, { capture: true, passive: true });

  const panes = { base: 350, flood: 420, rivers: 430, select: 440, villages: 450, gauges: 460, labels: 470 };
  for (const [name, z] of Object.entries(panes)) {
    map.createPane(name).style.zIndex = z;
  }
  map.getPane('labels').style.pointerEvents = 'none';
  const svgIn = (pane) => L.svg({ pane, padding: 0.5 });
  const quiet = { interactive: false, bubblingMouseEvents: false };

  // Graticule, and the state edge: a heavy line under the fills leaves only its outer half showing.
  const base = svgIn('base');
  for (let lon = 83; lon <= 89; lon += 1) L.polyline([[23, lon], [29, lon]], { ...quiet, pane: 'base', renderer: base, color: RULE, weight: 0.6 }).addTo(map);
  for (let lat = 24; lat <= 28; lat += 1) L.polyline([[lat, 81], [lat, 91]], { ...quiet, pane: 'base', renderer: base, color: RULE, weight: 0.6 }).addTo(map);
  L.geoJSON(ctx.geo, { ...quiet, pane: 'base', renderer: base, style: { color: INK, weight: 2.6, fill: false, lineJoin: 'round' } }).addTo(map);

  const layers = new Map();
  const districts = L.geoJSON(ctx.geo, {
    renderer: svgIn('overlayPane'),
    style: { color: '#8D8474', weight: 0.6, opacity: 1, fillColor: LAND, fillOpacity: 1, lineJoin: 'round' },
    onEachFeature(f, layer) {
      const { key } = f.properties;
      layers.set(key, layer);
      layer.on('click', () => onPick(key));
      layer.on('mousemove', (e) => showTip(e.originalEvent.clientX, e.originalEvent.clientY, tipFor(key)));
      layer.on('mouseout', hideTip);
    },
  }).addTo(map);
  const bounds = districts.getBounds();

  const overlay = (pane, style) => {
    const out = new Map();
    L.geoJSON(ctx.geo, {
      ...quiet, pane, renderer: svgIn(pane), style: { ...style, fill: false, opacity: 0, lineJoin: 'round' },
      onEachFeature: (f, layer) => out.set(f.properties.key, layer),
    }).addTo(map);
    return out;
  };
  const floodCase = overlay('flood', { color: PAPER, weight: 5 });
  const floodLine = overlay('flood', { color: BLUE, weight: 2.6 });
  const selected = overlay('select', { color: INK, weight: 2.4 });

  if (ctx.rivers) {
    const renderer = svgIn('rivers');
    const width = (f) => (f.properties?.name === 'Ganga' ? 2.6 : 1.7);
    L.geoJSON(ctx.rivers, { ...quiet, pane: 'rivers', renderer, style: (f) => ({ color: PAPER, weight: width(f) + 1.6, opacity: 0.8, lineCap: 'round', lineJoin: 'round' }) }).addTo(map);
    L.geoJSON(ctx.rivers, { ...quiet, pane: 'rivers', renderer, style: (f) => ({ color: BLUE, weight: width(f), lineCap: 'round', lineJoin: 'round' }) }).addTo(map);
  }

  const gauges = new Map();
  const gaugeRenderer = svgIn('gauges');
  for (const site of ctx.sites) {
    if (!isNum(site.lat) || !isNum(site.lon)) continue;
    const dot = L.circleMarker([site.lat, site.lon], {
      pane: 'gauges', renderer: gaugeRenderer, radius: 3.6, color: BLUE, weight: 1.5, fillColor: PAPER, fillOpacity: 1,
    }).addTo(map);
    dot.on('mousemove', (e) => showTip(e.originalEvent.clientX, e.originalEvent.clientY, gaugeTip(site)));
    dot.on('mouseout', hideTip);
    gauges.set(site.id, dot);
  }

  const villageLayer = L.layerGroup().addTo(map);
  const villageRenderer = svgIn('villages');

  // Labels are HTML so they use the real fonts. Collisions are resolved once per view, never per
  // day, so names do not flicker while the timeline plays.
  const labels = new Map();
  const label = (id, lat, lon, className, kids, priority) => {
    const el = h('span', { class: 'lb-in' }, kids);
    const icon = L.divIcon({ className: `lb ${className}`, html: el, iconSize: null });
    const marker = L.marker([lat, lon], { icon, pane: 'labels', interactive: false, keyboard: false }).addTo(map);
    const rec = { id, marker, el, priority, node: () => marker.getElement() };
    labels.set(id, rec);
    return rec;
  };
  for (const [key, d] of ctx.districts) {
    const rec = label(key, d.center.lat, d.center.lon, 'lb-district', [
      h('span', { class: 'lb-name', text: d.name }), h('span', { class: 'lb-val' })], d.area);
    rec.name = rec.el.firstChild;
    rec.value = rec.el.lastChild;
  }
  for (const r of riverLabels()) {
    label(`river:${r.name}`, r.lat, r.lon, 'lb-river', [h('span', { text: r.name, style: { transform: `rotate(${r.deg}deg)` } })], -1);
  }
  for (const [name, lat, lon] of NEIGHBOURS) label(`n:${name}`, lat, lon, 'lb-near', [name], -2);

  function layoutLabels() {
    const placed = [];
    const frame = host.getBoundingClientRect();
    const order = [...labels.values()].sort((a, b) => (b.id === selectedKey) - (a.id === selectedKey) || b.priority - a.priority);
    for (const rec of order) {
      const node = rec.node();
      if (!node) continue;
      node.style.visibility = 'visible';
      const box = rec.el.getBoundingClientRect();
      const clash = placed.some((p) => box.left < p.right + 2 && box.right > p.left - 2 && box.top < p.bottom + 1 && box.bottom > p.top - 1);
      const clipped = rec.id.startsWith('n:') && (box.left < frame.left + 4 || box.right > frame.right - 4);
      if (clash || clipped) node.style.visibility = 'hidden';
      else placed.push(box);
    }
  }
  map.on('zoomend', layoutLabels);

  const lastFill = new Map();
  function paint(key, fill, dark, text) {
    if (lastFill.get(key) !== fill) {
      lastFill.set(key, fill);
      layers.get(key)?.setStyle({ fillColor: fill });
    }
    const rec = labels.get(key);
    if (!rec) return;
    const node = rec.node();
    node?.classList.toggle('on-dark', Boolean(dark));
    if (rec.value.textContent !== text) rec.value.textContent = text;
  }

  function paintFlood(H, i, lead) {
    for (const key of layers.keys()) {
      const level = H.levelAt(i, key);
      const risk = H.riskAt(lead, i, key);
      const label = H.raisedAt(i, key) ? `${H.rainAt(i, key)} mm` : isNum(risk) ? `${risk}%` : '';
      paint(key, LEVEL_FILL[level] ?? LAND, level >= 2, level >= 1 ? label : '');
    }
  }
  function paintDrought(D, m) {
    for (const key of layers.keys()) {
      const v = D.spi3?.[m]?.[D.dj.get(key)];
      const c = isNum(v) ? droughtClass(v) : DROUGHT_CLASSES[3];
      paint(key, c.fill, c.dark, isNum(v) && v <= -1 ? fmtSigned(v) : '');
    }
  }

  let outlined = new Set();
  function setOutlines(keys) {
    const next = new Set(keys);
    for (const key of outlined) {
      if (!next.has(key)) {
        floodCase.get(key)?.setStyle({ opacity: 0 });
        floodLine.get(key)?.setStyle({ opacity: 0 });
      }
    }
    for (const key of next) {
      if (!outlined.has(key)) {
        floodCase.get(key)?.setStyle({ opacity: 1 });
        floodLine.get(key)?.setStyle({ opacity: 1 });
      }
    }
    outlined = next;
    host.dataset.outlined = String(next.size);
  }

  let selectedKey = null;
  function setSelected(key) {
    if (selectedKey) {
      selected.get(selectedKey)?.setStyle({ opacity: 0 });
      labels.get(selectedKey)?.node()?.classList.remove('is-selected');
    }
    selectedKey = key;
    if (key) {
      selected.get(key)?.setStyle({ opacity: 1 });
      labels.get(key)?.node()?.classList.add('is-selected');
    }
    layoutLabels();
  }

  let view = 'state';
  function fitState(animate = false) {
    view = 'state';
    const small = host.clientWidth < 620;
    map.fitBounds(bounds, {
      paddingTopLeft: small ? [10, 10] : [24, 20],
      paddingBottomRight: small ? [10, 10] : [24, 20],
      animate: animate && !calm(),
    });
    host.classList.toggle('is-small', small);
    layoutLabels();
  }
  function zoomTo(key) {
    const layer = layers.get(key);
    if (!layer) return;
    view = key;
    const opts = { padding: [46, 46], maxZoom: 10.5 };
    if (calm()) map.fitBounds(layer.getBounds(), { ...opts, animate: false });
    else map.flyToBounds(layer.getBounds(), { ...opts, duration: 0.7 });
  }

  function resize() {
    map.invalidateSize({ animate: false });
    if (view === 'state') fitState();
    else if (layers.has(view)) map.fitBounds(layers.get(view).getBounds(), { padding: [46, 46], maxZoom: 10.5, animate: false });
    layoutLabels();
  }
  new ResizeObserver(() => resize()).observe(host);

  function paintGauges(status) {
    for (const [id, dot] of gauges) {
      const st = status(id);
      dot.setStyle({
        fillColor: st === 'normal' ? PAPER : BLUE,
        radius: st === 'extreme' ? 5.4 : st === 'high' ? 4.4 : 3.6,
        color: st === 'extreme' ? INK : BLUE,
      });
    }
  }

  // Quiet at state zoom so the dots never compete with the flood picture, full size up close.
  function sizeVillages() {
    const z = map.getZoom();
    const f = Math.max(0.4, Math.min(1, 0.4 + ((z - 7.8) / 1.4) * 0.6));
    const close = z >= 8.2;
    villageLayer.eachLayer((d) => {
      d.setRadius(d.options.baseRadius * f);
      const show = close || d.options.exposureClass >= 2;
      d.setStyle({ opacity: show ? 1 : 0, fillOpacity: show ? 1 : 0 });
    });
  }
  map.on('zoomend', sizeVillages);

  function setVillages(rows) {
    villageLayer.clearLayers();
    host.dataset.villages = String(rows?.length ?? 0);
    if (!rows) return;
    const drawn = [...rows].sort((a, b) => b[3] - a[3]).slice(0, MAX_VILLAGE_DOTS).reverse();
    for (const [name, lat, lon, exposure, cls] of drawn) {
      if (!isNum(lat) || !isNum(lon)) continue;
      const dot = L.circleMarker([lat, lon], {
        ...(VILLAGE_STYLE[cls] ?? VILLAGE_STYLE[0]), baseRadius: (VILLAGE_STYLE[cls] ?? VILLAGE_STYLE[0]).radius, exposureClass: cls, pane: 'villages', renderer: villageRenderer, weight: 0.8, fillOpacity: 1,
      });
      dot.on('mousemove', (e) => showTip(e.originalEvent.clientX, e.originalEvent.clientY, [name, { value: `${fmtInt(exposure)} of 100`, label: 'exposure' }]));
      dot.on('mouseout', hideTip);
      villageLayer.addLayer(dot);
    }
    sizeVillages();
  }

  fitState();
  return { map, paintFlood, paintDrought, paintGauges, setOutlines, setSelected, setVillages, fitState, zoomTo, resize, zoomBy: (d) => map.zoomIn(d, { animate: !calm() }) };
}
