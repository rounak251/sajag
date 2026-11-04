// DOM builders and formatters. All text goes in through text nodes, never innerHTML: names and
// notes arrive from data files.
const SVG_NS = 'http://www.w3.org/2000/svg';

function fill(el, props, kids) {
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid);
  }
  return el;
}
export const h = (tag, props, ...kids) => fill(document.createElement(tag), props, kids);
export const s = (tag, props, ...kids) => fill(document.createElementNS(SVG_NS, tag), props, kids);
export const $ = (sel, root = document) => root.querySelector(sel);
// replaceChildren, except that absent optional blocks are skipped rather than printed as "null".
export const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
export const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

const toDate = (iso) => new Date(`${iso}T00:00:00Z`);
const dateFmt = (opts) => new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', ...opts });
const LONG = dateFmt({ day: 'numeric', month: 'long', year: 'numeric' });
const SHORT = dateFmt({ day: 'numeric', month: 'short' });
const MEDIUM = dateFmt({ day: 'numeric', month: 'short', year: 'numeric' });
const MONTH = dateFmt({ month: 'short' });
const MONTH_YEAR = dateFmt({ month: 'long', year: 'numeric' });
export const fmtLong = (iso) => LONG.format(toDate(iso));
export const fmtShort = (iso) => SHORT.format(toDate(iso));
export const fmtMedium = (iso) => MEDIUM.format(toDate(iso));
export const fmtMonthName = (iso) => MONTH.format(toDate(iso));
export const fmtMonthYear = (ym) => MONTH_YEAR.format(toDate(`${ym}-01`));
export const dayOfMonth = (iso) => Number(iso.slice(8, 10));
export const dayNumber = (iso) => Math.round(toDate(iso).getTime() / 864e5);

const NUM = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
export const fmtInt = (v) => (isNum(v) ? NUM.format(v) : 'n/a');
export const fmtPct = (share, digits = 0) => (isNum(share) ? `${(share * 100).toFixed(digits)}%` : 'n/a');
export const fmtDec = (v, digits = 2) => (isNum(v) ? v.toFixed(digits) : 'n/a');
export const fmtSigned = (v, digits = 1) => (isNum(v) ? v.toFixed(digits).replace('-', '−') : 'n/a');
export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

// English with Hindi beside it, the pairing used for every level and reason.
export function bilingual(pair, fallback = '') {
  if (!pair) return h('span', { text: fallback });
  return h('span', { class: 'bi' },
    h('span', { text: pair.en ?? fallback }),
    pair.hi ? h('span', { class: 'bi-hi', lang: 'hi', text: pair.hi }) : null);
}

// A set of mutually exclusive buttons: role=tab with arrow keys, or radio-like when role='radio'.
export function choiceGroup({ label, options, value, onChange, role = 'radio', className = '' }) {
  const group = h('div', { class: `choice ${className}`, role: role === 'tab' ? 'tablist' : 'radiogroup', 'aria-label': label });
  const buttons = new Map();
  let current = value;
  const paint = () => {
    for (const [v, b] of buttons) {
      const on = v === current;
      b.setAttribute(role === 'tab' ? 'aria-selected' : 'aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    }
  };
  const choose = (v, focus) => {
    current = v;
    paint();
    if (focus) buttons.get(v)?.focus();
    onChange(v);
  };
  for (const o of options) {
    const b = h('button', {
      type: 'button', role, lang: o.lang, id: o.id, 'aria-controls': o.controls,
      onclick: () => choose(o.value), text: o.label,
    });
    buttons.set(o.value, b);
    group.append(b);
  }
  group.addEventListener('keydown', (e) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const keys = [...buttons.keys()];
    choose(keys[(keys.indexOf(current) + step + keys.length) % keys.length], true);
  });
  paint();
  group.setValue = (v) => { if (buttons.has(v)) { current = v; paint(); } };
  return group;
}
