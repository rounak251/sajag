#!/usr/bin/env node
// End-to-end check of the Sajag dashboard in a real headless browser.
//
//   python3 -m http.server 8765 --directory web &
//   node web/dev/smoke.js http://localhost:8765/ [--shots dir] [--degrade]
//
// Fails on any console error, page error, failed request or empty map. Works on mock or real data:
// it reads what to expect from the data files, never from constants. --degrade also replays the
// page with optional files and fields removed, to prove that it does not crash.
const path = require('path');
const fs = require('fs');

const PLAYWRIGHT = '/Users/rounakchoudhary/Desktop/datascience/snack-skyline/node_modules/playwright-core';
const CHROME = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const { chromium } = require(PLAYWRIGHT);

const argv = process.argv.slice(2);
const base = (argv.find((a) => /^https?:/.test(a)) || 'http://localhost:8765/').replace(/\/?$/, '/');
const shotsAt = argv.indexOf('--shots');
const shots = shotsAt >= 0 ? argv[shotsAt + 1] : path.join(__dirname, 'shots');
const degrade = argv.includes('--degrade');
fs.mkdirSync(shots, { recursive: true });

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok) });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
};

function watch(page, problems, { allow = () => false } = {}) {
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text();
    if (allow(text, m.location()?.url)) return;
    const at = m.location();
    problems.push(`console: ${text} at ${(at?.url ?? '').replace(base, '')}:${at?.lineNumber ?? '?'}`);
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('requestfailed', (r) => {
    if (r.failure()?.errorText === 'net::ERR_ABORTED') return; // media element swapping its src
    if (allow(r.url(), r.url())) return;
    problems.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`);
  });
  page.on('response', (r) => {
    if (r.status() >= 400 && !allow(r.url(), r.url())) problems.push(`http ${r.status()}: ${r.url()}`);
  });
}

const ready = (page, level = 'all') => page.waitForFunction((want) => {
  const r = document.documentElement.dataset.ready;
  // 'map' is passed through on the way to 'all', and can be missed between polls.
  return r === want || r === 'all' || r === 'failed';
}, level, { timeout: 20000 });

// Text colour against the nearest solid background, for everything readable outside the map.
const contrastScan = () => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const v = m[1].split(/[ ,/]+/).map(Number);
    return { r: v[0], g: v[1], b: v[2], a: v[3] ?? 1 };
  };
  const lum = ({ r, g, b }) => {
    const f = (x) => { const s = x / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const bgOf = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a >= 0.99) return c;
    }
    return { r: 255, g: 255, b: 255 };
  };
  const bad = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let checked = 0;
  while (walker.nextNode()) {
    const text = walker.currentNode.textContent.trim();
    const el = walker.currentNode.parentElement;
    if (!text || !el || el.closest('#map, script, style, noscript, .vh, .skip, svg, #tip, option')) continue;
    const box = el.getBoundingClientRect();
    if (!box.width || !box.height) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    const fg = parse(st.color);
    if (!fg) continue;
    const a = lum(fg);
    const b = lum(bgOf(el));
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const px = parseFloat(st.fontSize);
    const large = px >= 24 || (px >= 18.66 && Number(st.fontWeight) >= 700);
    checked += 1;
    if (ratio < (large ? 3 : 4.5)) bad.push(`${ratio.toFixed(2)} "${text.slice(0, 30)}"`);
  }
  return { checked, bad: bad.slice(0, 6) };
};

const copyScan = () => {
  const text = document.body.innerText;
  const words = text.match(/revolutionary|cutting-edge|seamless|leverage|empower/gi) ?? [];
  return { dash: (text.match(/—/g) ?? []).length, words, nullish: /\b(undefined|NaN|\[object)\b/.test(text) || /(^|\n)null(\n|$)/.test(text) };
};

async function main() {
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'],
  });

  // ---- Desktop run
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const problems = [];
  watch(page, problems);
  const external = [];
  page.on('request', (r) => { if (!r.url().startsWith(base) && !/^(data|blob):/.test(r.url())) external.push(r.url()); });
  const t0 = Date.now();
  await page.goto(base, { waitUntil: 'load' });
  await ready(page, 'map');
  const firstPaint = Date.now() - t0;
  const meta = await page.evaluate(() => fetch('data/meta.json').then((r) => r.json()));
  const stories = (meta.stories ?? []).filter((s) => (meta.years ?? []).includes(s.year));

  const mapStats = () => page.evaluate(() => {
    const fills = [...document.querySelectorAll('#map .leaflet-overlay-pane path')].map((p) => p.getAttribute('fill'));
    return {
      polygons: fills.length,
      coloured: fills.filter((f) => f && f !== 'none').length,
      distinct: new Set(fills).size,
      gauges: document.querySelectorAll('#map .leaflet-gauges-pane path').length,
      rivers: document.querySelectorAll('#map .leaflet-rivers-pane path').length,
      labels: [...document.querySelectorAll('.lb-district')].filter((n) => n.style.visibility !== 'hidden').length,
      outlined: Number(document.getElementById('map').dataset.outlined ?? 0),
      box: document.getElementById('map').getBoundingClientRect().height,
    };
  });

  const m0 = await mapStats();
  const districts = await page.evaluate(() => window.__sajag.ctx.districts.size);
  check('load: map drawn', m0.polygons === districts && m0.coloured === districts && m0.box > 200, `${m0.polygons} polygons, ${m0.gauges} gauges, ${m0.rivers / 2} river lines, ${m0.labels} labels, first paint ${firstPaint} ms`);
  check('load: no external requests', external.length === 0, external[0] ?? 'all same origin');

  const s0 = await page.evaluate(() => ({ i: window.__sajag.state.i, playing: window.__sajag.state.playing, story: window.__sajag.state.story, d: window.__sajag.state.district }));
  check('load: first story starts by itself', stories.length === 0 || (s0.story === stories[0].id && s0.playing), `story ${s0.story}, focus ${s0.d}`);
  await page.waitForTimeout(2500);
  const s1 = await page.evaluate(() => window.__sajag.state.i);
  check('play: timeline advances within 5 seconds', s1 > s0.i, `day index ${s0.i} to ${s1}`);
  const blindTag = await page.locator('#heldout-tag').count();
  const firstBlind = (meta.held_out_years ?? []).includes(stories[0]?.year);
  check('held out label shown', firstBlind ? blindTag === 1 : blindTag === 0, firstBlind ? await page.locator('#heldout-tag').innerText() : 'not a blind year');
  await page.screenshot({ path: path.join(shots, 'desktop-play.png') });

  await page.click('#play');
  const paused = await page.evaluate(() => window.__sajag.state.playing);
  const i1 = await page.evaluate(() => window.__sajag.state.i);
  await page.waitForTimeout(900);
  const i2 = await page.evaluate(() => window.__sajag.state.i);
  check('pause: timeline stops', !paused && i1 === i2);

  // Recorded flood: jump to its marker and expect the outline and the "before" card.
  const marks = await page.locator('.tl-mark').count();
  if (marks) {
    await page.locator('.tl-mark').first().click();
    await page.waitForTimeout(250);
    const m1 = await mapStats();
    const card = await page.locator('#event-card').count();
    check('flood record: outlines and before card', m1.outlined > 0 && card === 1, `${m1.outlined} districts outlined, ${marks} markers`);
    await page.screenshot({ path: path.join(shots, 'desktop-flood.png') });
  } else check('flood record: no records in this window', true);

  // Keyboard on the scrubber.
  await page.focus('#scrub');
  const k0 = await page.evaluate(() => window.__sajag.state.i);
  await page.keyboard.press('ArrowRight');
  const k1 = await page.evaluate(() => window.__sajag.state.i);
  check('keyboard: arrow key moves the date', k1 === k0 + 1, await page.getAttribute('#scrub', 'aria-valuetext'));

  // End of the replay offers Replay, and pressing it starts again from the first day.
  await page.keyboard.press('End');
  const endLabel = await page.locator('#play').innerText();
  const a0 = await page.getAttribute('#scrub', 'min');
  await page.click('#play');
  const restarted = await page.evaluate(() => window.__sajag.state.i);
  check('replay: restarts from the first day', endLabel === 'Replay' && restarted === Number(a0), `button said "${endLabel}", back to day ${restarted}`);
  await page.click('#play');
  await page.locator('.tl-mark').first().click().catch(() => {});

  // Lead selector changes what is shown.
  const lead = await page.evaluate(() => window.__sajag.ctx.H.leads.at(-1));
  await page.locator('.lead-pick button', { hasText: lead }).click();
  const on = await page.locator('#risk-bars li.is-on .risk-label').innerText().catch(() => '');
  check('lead selector', on.startsWith(lead), `risk row "${on}" highlighted`);

  // Story switch.
  if (stories.length > 1) {
    await page.locator(`.story[data-story="${stories[1].id}"]`).click();
    await page.waitForFunction((y) => window.__sajag.state.year === y, stories[1].year);
    const st = await page.evaluate(() => ({ story: window.__sajag.state.story, year: window.__sajag.state.year, date: window.__sajag.ctx.H.dates[window.__sajag.state.i] }));
    check('story switch', st.story === stories[1].id && st.date >= stories[1].start && st.date <= stories[1].end, `${st.story} at ${st.date}`);
    await page.click('#play').catch(() => {});
  } else check('story switch: only one story in this data', true);
  await page.evaluate(() => { document.querySelector('#play').textContent === 'Pause' && document.querySelector('#play').click(); });

  // Year selector.
  const years = meta.years ?? [];
  if (years.length > 1) {
    const other = years.find((y) => y !== (stories[1]?.year ?? stories[0]?.year)) ?? years[0];
    await page.selectOption('#year', String(other));
    await page.waitForFunction((y) => window.__sajag.state.year === y, other);
    const m2 = await mapStats();
    check('year selector', m2.polygons === districts, `now showing ${other}`);
  }

  // District click on the real map, at the centre of a label point.
  const target = await page.evaluate(() => {
    const d = [...window.__sajag.ctx.districts.values()].sort((a, b) => b.area - a.area)[0];
    return { key: d.key, name: d.name };
  });
  const point = await page.evaluate((k) => {
    const node = [...document.querySelectorAll('#map .leaflet-overlay-pane path')].find(Boolean);
    const box = document.getElementById('map').getBoundingClientRect();
    const d = window.__sajag.ctx.districts.get(k);
    const lb = [...document.querySelectorAll('.lb-district')].find((n) => n.textContent.startsWith(d.name));
    const r = (lb.querySelector('.lb-in') ?? lb).getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 + 14, ok: Boolean(node), box };
  }, target.key);
  await page.mouse.click(point.x, point.y);
  await page.waitForFunction(() => window.__sajag.state.district !== null, null, { timeout: 4000 });
  const picked = await page.evaluate(() => window.__sajag.state.district);
  await page.waitForFunction(() => Number(document.getElementById('map').dataset.villages) >= 0, null, { timeout: 5000 });
  await page.waitForTimeout(1000);
  const panel = await page.evaluate(() => ({
    name: document.getElementById('district-name').textContent,
    bars: document.querySelectorAll('#risk-bars li').length,
    flow: document.querySelectorAll('#flow-chart svg path').length,
    villages: document.querySelectorAll('#village-list li').length,
    dots: document.querySelectorAll('#map .leaflet-villages-pane path').length,
  }));
  check('district click: panel', panel.bars >= 1 && panel.flow > 0, `${picked}: ${panel.bars} risk bars, flow chart drawn`);
  check('district click: villages lazy-load', panel.villages > 0 && panel.dots > 0, `${panel.villages} listed, ${panel.dots} dots on map`);
  await page.screenshot({ path: path.join(shots, 'desktop-district.png') });

  // Alert preview.
  await page.click('#tab-alert');
  const langs = await page.evaluate(() => (window.__sajag.ctx.alerts?.languages ?? []).map((l) => l.id));
  const counts = [];
  for (const lang of langs) {
    await page.click(`#lang-${lang}`);
    const n = await page.evaluate(() => ({
      text: document.getElementById('sms-text').textContent,
      count: Number(document.querySelector('#sms-count .al-n').textContent),
    }));
    counts.push(`${lang} ${n.count}`);
    if (n.count !== n.text.length || !n.text) problems.push(`sms count wrong for ${lang}`);
    if (/\{(district|river|days)\}/.test(n.text)) problems.push(`placeholder left in sms for ${lang}`);
  }
  check('alert: language tabs and live count', langs.length > 0 && counts.length === langs.length, counts.join(', '));
  const audio = await page.evaluate(async () => {
    const a = document.getElementById('alert-audio');
    if (!a) return { present: false };
    const out = { present: true, hidden: a.hidden, src: a.getAttribute('src'), can: a.canPlayType('audio/mp4; codecs="mp4a.40.2"') };
    if (out.src) out.status = (await fetch(out.src, { method: 'HEAD' })).status;
    return out;
  });
  check('alert: audio element present', audio.present && (audio.hidden || audio.status === 200), JSON.stringify(audio));
  if (audio.src) {
    const played = await page.evaluate(async () => {
      const a = document.getElementById('alert-audio');
      await a.play();
      await new Promise((r) => { setTimeout(r, 700); });
      a.pause();
      return { at: a.currentTime, length: a.duration };
    }).catch((e) => ({ error: String(e) }));
    check('alert: audio really plays', played.at > 0, JSON.stringify(played));
  }
  await page.screenshot({ path: path.join(shots, 'desktop-alert.png') });
  await page.click('#tab-district');

  // Drought layer.
  await page.click('#layer-drought');
  await page.waitForTimeout(250);
  const fills = await page.evaluate(() => [...document.querySelectorAll('#map .leaflet-overlay-pane path')].filter((p) => /dr\d|#B9CFDB/.test(p.getAttribute('fill') ?? '')).length);
  const legendTitle = await page.locator('#legend .lg-title').innerText();
  check('drought layer', /SPI/.test(legendTitle), `${fills} districts on a dry or wet class, legend "${legendTitle}"`);
  await page.click('#reset-view');
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(shots, 'desktop-drought.png') });
  await page.locator('.layer-pick button').first().click();
  const contrastMap = await page.evaluate(contrastScan);
  const copyMap = await page.evaluate(copyScan);
  await page.click('#tab-alert');
  const copyAlert = await page.evaluate(copyScan);
  await page.click('#tab-district');
  check('contrast AA: map screen', contrastMap.bad.length === 0, `${contrastMap.checked} text runs ${contrastMap.bad.join('; ')}`);

  // Evidence.
  await page.locator('.tabs-main a[data-route="evidence"]').click();
  await page.waitForSelector('#screen-evidence .doc-h1');
  await page.waitForTimeout(400);
  const ev = await page.evaluate(() => ({
    hero: document.getElementById('hero-figure')?.textContent,
    sections: document.querySelectorAll('#screen-evidence .doc-sec').length,
    charts: document.querySelectorAll('#screen-evidence svg').length,
    limits: document.querySelectorAll('#limits li').length,
    story: document.querySelectorAll('#data-story li').length,
    blind: document.querySelectorAll('#blind-table tbody tr').length,
  }));
  check('evidence page', ev.sections >= 1 && ev.charts >= 1, JSON.stringify(ev));
  await page.screenshot({ path: path.join(shots, 'desktop-evidence.png'), fullPage: true });
  const contrastEv = await page.evaluate(contrastScan);
  check('contrast AA: evidence', contrastEv.bad.length === 0, `${contrastEv.checked} text runs ${contrastEv.bad.join('; ')}`);
  const copyEv = await page.evaluate(copyScan);

  // Today.
  await page.locator('.tabs-main a[data-route="today"]').click();
  await page.waitForSelector('#season-status');
  await page.waitForTimeout(400);
  const td = await page.evaluate(() => ({
    status: document.querySelector('#season-status .status-head')?.textContent,
    fans: document.querySelectorAll('#fan-grid .fan').length,
    fanPaths: document.querySelectorAll('#fan-grid svg path').length,
    drought: document.querySelectorAll('#today-drought-map path').length,
  }));
  check('today page', Boolean(td.status) && td.fans >= 0, JSON.stringify(td));
  await page.screenshot({ path: path.join(shots, 'desktop-today.png'), fullPage: true });
  const contrastTd = await page.evaluate(contrastScan);
  check('contrast AA: today', contrastTd.bad.length === 0, `${contrastTd.checked} text runs ${contrastTd.bad.join('; ')}`);
  const copyTd = await page.evaluate(copyScan);
  const scans = { map: copyMap, alert: copyAlert, evidence: copyEv, today: copyTd };
  const clean = Object.values(scans).every((c) => c.dash === 0 && !c.words.length && !c.nullish);
  check('copy: no em dash, marketing words or broken values', clean, clean ? 'map, alert, evidence, today' : JSON.stringify(scans));

  // Footer note.
  const foot = await page.locator('.foot').innerText();
  check('footer: not an official warning', /not an official warning/i.test(foot) && /IMD/.test(foot) && /CWC/.test(foot) && /BSDMA/.test(foot));

  check('no console errors or failed requests on desktop', problems.length === 0, problems.slice(0, 5).join(' | '));
  await page.close();

  // ---- Phone run
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
  const phoneProblems = [];
  watch(phone, phoneProblems);
  await phone.goto(base, { waitUntil: 'load' });
  await ready(phone);
  await phone.waitForTimeout(1500);
  const lay = await phone.evaluate(() => {
    const map = document.getElementById('map').getBoundingClientRect();
    const panel = document.getElementById('panel').getBoundingClientRect();
    return { overflow: document.documentElement.scrollWidth - window.innerWidth, stacked: panel.top >= map.bottom, mapW: map.width, mapH: map.height };
  });
  check('390px: no sideways scroll, panel under map', lay.overflow <= 0 && lay.stacked && lay.mapW > 300, JSON.stringify(lay));
  const mp = await phone.evaluate(() => document.querySelectorAll('#map .leaflet-overlay-pane path').length);
  check('390px: map drawn', mp === districts, `${mp} polygons`);
  await phone.evaluate(() => { const b = document.getElementById('play'); if (b.textContent === 'Pause') b.click(); });
  await phone.screenshot({ path: path.join(shots, 'phone-map.png'), fullPage: true });
  await phone.tap('#tab-alert');
  await phone.waitForTimeout(250);
  await phone.locator('#panel').scrollIntoViewIfNeeded();
  await phone.screenshot({ path: path.join(shots, 'phone-alert.png'), fullPage: true });
  for (const route of ['evidence', 'today']) {
    await phone.evaluate((r) => { location.hash = `#/${r}`; }, route);
    await phone.waitForTimeout(600);
    const over = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(`390px: ${route} fits`, over <= 0, `overflow ${over}px`);
    await phone.screenshot({ path: path.join(shots, `phone-${route}.png`), fullPage: true });
  }
  check('no console errors or failed requests on phone', phoneProblems.length === 0, phoneProblems.slice(0, 5).join(' | '));
  await phone.close();

  // ---- Reduced motion: nothing moves on its own.
  const calmCtx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const calm = await calmCtx.newPage();
  const calmProblems = [];
  watch(calm, calmProblems);
  await calm.goto(base, { waitUntil: 'load' });
  await ready(calm);
  const c0 = await calm.evaluate(() => ({ playing: window.__sajag.state.playing, i: window.__sajag.state.i }));
  await calm.waitForTimeout(1300);
  const c1 = await calm.evaluate(() => window.__sajag.state.i);
  check('reduced motion: no autoplay', !c0.playing && c0.i === c1, `held at day ${c1}`);
  check('no console errors with reduced motion', calmProblems.length === 0, calmProblems.slice(0, 3).join(' | '));
  await calmCtx.close();

  // ---- Arriving on another tab: the map is built hidden, and must still be right when opened.
  const late = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const lateProblems = [];
  watch(late, lateProblems);
  await late.goto(`${base}#/evidence`, { waitUntil: 'load' });
  await ready(late);
  await late.locator('.tabs-main a[data-route="map"]').click();
  await late.waitForTimeout(1300);
  const lateState = await late.evaluate(() => {
    const box = document.querySelector('#map .leaflet-overlay-pane path')?.getBoundingClientRect();
    return { playing: window.__sajag.state.playing, story: window.__sajag.state.story, drawnWidth: box?.width ?? 0 };
  });
  check('deep link to Evidence, then map: drawn and playing', lateState.drawnWidth > 0 && (stories.length === 0 || lateState.playing) && lateProblems.length === 0, JSON.stringify(lateState));
  await late.close();

  // ---- Subpath: GitHub Pages serves this under /sajag/.
  const sub = await browser.newPage({ viewport: { width: 1280, height: 760 } });
  const subProblems = [];
  watch(sub, subProblems);
  await sub.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/sajag/')) return route.abort();
    return route.continue({ url: base + url.pathname.replace(/^\/sajag\//, '') });
  });
  const origin = new URL(base).origin;
  await sub.goto(`${origin}/sajag/`, { waitUntil: 'load' }).catch((e) => subProblems.push(String(e)));
  await ready(sub).catch(() => subProblems.push('never ready'));
  const subPaths = await sub.evaluate(() => document.querySelectorAll('#map .leaflet-overlay-pane path').length);
  check('subpath /sajag/: works with relative URLs only', subPaths === districts && subProblems.length === 0, subProblems[0] ?? `${subPaths} polygons at 1280x760`);
  await sub.screenshot({ path: path.join(shots, 'small-laptop.png') });
  await sub.close();

  // ---- Degraded data: each case removes something optional. The page must keep working.
  if (degrade) {
    const cases = {
      'no optional files': { drop: /data\/(rivers\.geojson|sites\.json|drought\.json|live\.json|alerts\.json|metrics\.json)$/ },
      'no villages': { drop: /data\/villages\// },
      'in season live.json': {
        edit: {
          'live.json': (j) => {
            j.season_active = true;
            j.note = '';
            const keys = Object.keys(j.districts);
            keys.slice(0, 9).forEach((k, n) => { j.districts[k] = { risk: { 1: 40, 3: 55, 5: 60, 7: 70 }, level: 1 + (n % 3), reasons: ['river_now'] }; });
            j.sites.slice(0, 2).forEach((s, n) => { s.status = n ? 'high' : 'extreme'; });
            return j;
          },
        },
      },
      'sparse fields': {
        edit: {
          'metrics.json': (j) => ({ headline: { caught_3d: j.headline?.caught_3d }, limits: j.limits }),
          'meta.json': (j) => { delete j.reasons; delete j.levels; j.stories = []; return j; },
          'districts.geojson': (j) => { j.features.forEach((f) => delete f.properties.name_hi); return j; },
          'alerts.json': (j) => { j.audio = {}; return j; },
        },
      },
      'heavy data': {
        edit: {
          'hindcast/': (j) => {
            const extra = [];
            for (let n = 0; n < 150; n += 1) {
              extra.push({ start: j.dates[n], end: j.dates[Math.min(j.dates.length - 1, n + 4)], district: j.districts[n % j.districts.length], label: `Inventory event ${Math.floor(n / 3)}`, source: 'inventory', url: '' });
            }
            j.records = [...j.records, ...extra];
            return j;
          },
          'villages/': (j) => {
            const rows = [];
            for (let n = 0; n < 9; n += 1) rows.push(...j.villages);
            j.villages = rows;
            return j;
          },
          'meta.json': (j) => { j.years = [...new Set([...j.years, ...Array.from({ length: 18 }, (_, n) => 2006 + n)])].sort(); return j; },
        },
      },
      'null values in a year': {
        edit: {
          'hindcast/': (j) => {
            j.q = j.q.map((row, i) => (i % 7 ? row : row.map(() => null)));
            j.peak7 = j.peak7.map(() => j.sites.map(() => null));
            j.records = [...j.records, { start: '1999-01-01', end: '1999-01-01', district: 'nowhere', label: '' }];
            return j;
          },
        },
      },
    };
    for (const [name, spec] of Object.entries(cases)) {
      const p = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      const errs = [];
      p.on('pageerror', (e) => errs.push(e.message));
      await p.route('**/data/**', async (route) => {
        const url = route.request().url();
        if (spec.drop?.test(url)) return route.fulfill({ status: 404, body: '' });
        const hit = Object.entries(spec.edit ?? {}).find(([k]) => url.includes(k));
        if (!hit) return route.continue();
        const res = await route.fetch();
        return route.fulfill({ response: res, json: hit[1](await res.json()) });
      });
      await p.goto(base, { waitUntil: 'load' });
      await ready(p);
      await p.waitForTimeout(500);
      const state = await p.evaluate(() => document.documentElement.dataset.ready);
      const paths = await p.evaluate(() => document.querySelectorAll('#map .leaflet-overlay-pane path').length);
      await p.evaluate(() => { const b = document.getElementById('play'); if (b?.textContent === 'Pause') b.click(); });
      await p.selectOption('#district-select', { index: 3 }).catch((e) => errs.push(String(e)));
      await p.waitForTimeout(300);
      await p.click('#tab-alert').catch((e) => errs.push(String(e)));
      await p.waitForTimeout(150);
      await p.evaluate(() => { location.hash = '#/evidence'; });
      await p.waitForTimeout(300);
      const evidenceText = await p.locator('#screen-evidence').innerText();
      await p.evaluate(() => { location.hash = '#/today'; });
      await p.waitForTimeout(300);
      const todayText = await p.locator('#screen-today').innerText();
      if (name.startsWith('in season')) await p.screenshot({ path: path.join(shots, 'desktop-today-season.png'), fullPage: true });
      const scan = await p.evaluate(copyScan);
      check(`degrade: ${name}`, state === 'all' && paths === districts && errs.length === 0 && !scan.nullish && evidenceText.length > 5 && todayText.length > 5, errs[0] ?? `${paths} polygons`);
      await p.close();
    }
  }

  await browser.close();
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length} of ${results.length} checks passed.`);
  if (failed.length) {
    console.log(`Failed: ${failed.map((f) => f.name).join('; ')}`);
    process.exit(1);
  }
}

main().catch((e) => { console.error('SMOKE CRASHED', e); process.exit(2); });
