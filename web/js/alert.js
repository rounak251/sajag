// Alert preview: what a person would receive, filled in for the selected district.
import { ctx, nearestSites, levelOf } from './data.js';
import { state, set } from './state.js';
import { h, choiceGroup, plural } from './util.js';

// Translation of river names only. The contract's sites.json gives them in English.
const RIVER_HI = {
  Ganga: 'गंगा', Kosi: 'कोसी', Gandak: 'गंडक', 'Burhi Gandak': 'बूढ़ी गंडक', Bagmati: 'बागमती',
  Kamla: 'कमला', Mahananda: 'महानंदा', Ghaghara: 'घाघरा', Sone: 'सोन', Punpun: 'पुनपुन',
};
const GSM7 = /^[@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&'()*+,\-./0-9:;<=>?¡A-ZÄÖÑÜ§¿a-zäöñüà]*$/;

const usesDevanagari = (lang) => lang !== 'en';

function fillTemplate(text, key, lang) {
  const d = ctx.districts.get(key);
  const river = nearestSites(key, 1)[0]?.river ?? '';
  const name = usesDevanagari(lang) ? (d?.name_hi ?? d?.name) : d?.name;
  const riverName = usesDevanagari(lang) ? (RIVER_HI[river] ?? river) : river;
  return (text ?? '').replaceAll('{district}', name ?? '').replaceAll('{river}', riverName).replaceAll('{days}', state.lead);
}

// A Unicode SMS holds 70 UCS-2 characters, a plain one 160. Long messages split into smaller parts.
function smsLimit(text) {
  const plain = GSM7.test(text);
  const single = plain ? 160 : 70;
  const part = plain ? 153 : 67;
  const parts = text.length <= single ? 1 : Math.ceil(text.length / part);
  return { single, parts, plain };
}

function worstCase(level, lang) {
  const template = ctx.alerts?.templates?.[lang]?.[level]?.sms;
  if (!template) return null;
  let worst = null;
  for (const key of ctx.districts.keys()) {
    const n = fillTemplate(template, key, lang).length;
    if (!worst || n > worst.n) worst = { n, key };
  }
  return worst;
}

export function createAlert(host) {
  const heading = h('h3', { class: 'sec-title', id: 'alert-title' });
  const levelSlot = h('div', { class: 'al-row' });
  const langSlot = h('div', { class: 'al-row' });
  const screen = h('p', { class: 'phone-text', id: 'sms-text' });
  const counter = h('p', { class: 'al-count', id: 'sms-count', 'aria-live': 'polite' });
  const meter = h('span', { class: 'meter-fill' });
  const worst = h('p', { class: 'note', id: 'sms-worst' });
  const audio = h('audio', { controls: true, preload: 'none', id: 'alert-audio' });
  const audioNote = h('p', { class: 'note', id: 'audio-note', hidden: true });
  const script = h('p', { class: 'al-script', id: 'voice-text' });
  const empty = h('p', { class: 'note' });
  const body = h('div', { class: 'al-body' },
    h('figure', { class: 'phone', 'aria-label': 'The SMS as it would appear on a basic phone' },
      h('div', { class: 'phone-screen' },
        h('div', { class: 'phone-bar' }, h('span', { text: 'SAJAG' }), h('span', { id: 'phone-part' })),
        screen,
        h('div', { class: 'phone-bar phone-soft' }, h('span', { text: 'Options' }), h('span', { text: 'Back' })))),
    h('div', { class: 'al-side' },
      counter,
      h('span', { class: 'meter' }, meter),
      worst)),
  voice = h('div', { class: 'al-voice' },
    h('h4', { class: 'sub-title', text: 'Voice call message' }),
    audio, audioNote, script);
  host.append(heading, levelSlot, langSlot, body, voice, empty);

  let fallbackTried = false;
  audio.addEventListener('error', () => {
    const path = audio.dataset.path;
    if (!path) return;
    if (!fallbackTried) {
      fallbackTried = true;
      audio.src = path; // the contract does not say whether audio/ sits under data/ or beside it
      return;
    }
    audio.hidden = true;
    audioNote.hidden = false;
    audioNote.textContent = 'This recording could not be played. The script is below.';
  });

  let built = false;
  function build() {
    const A = ctx.alerts;
    const languages = A?.languages ?? [];
    if (!languages.length) return;
    if (!state.alertLang) state.alertLang = languages[0].id;
    if (!state.alertLevel) state.alertLevel = '1';
    const levels = ctx.levels.filter((l) => l.id >= 1 && languages.some((g) => A.templates?.[g.id]?.[l.id]));
    levelSlot.replaceChildren(
      h('span', { class: 'ctl-label', text: 'Level' }),
      (levelSlot.group = choiceGroup({
        label: 'Alert level', value: state.alertLevel, onChange: (v) => { state.userPickedLevel = true; set({ alertLevel: v }); },
        options: levels.map((l) => ({ value: String(l.id), label: l.en })),
      })));
    langSlot.replaceChildren(
      h('span', { class: 'ctl-label', text: 'Language' }),
      choiceGroup({
        label: 'Language', value: state.alertLang, role: 'tab', className: 'al-tabs', onChange: (v) => set({ alertLang: v }),
        options: languages.map((g) => ({ value: g.id, label: g.name, lang: g.id === 'en' ? 'en' : g.id, id: `lang-${g.id}` })),
      }));
    built = true;
  }

  function update() {
    const A = ctx.alerts;
    const key = state.district;
    const ready = Boolean(A && key);
    for (const part of [levelSlot, langSlot, body, voice]) part.hidden = !ready;
    empty.hidden = ready;
    if (!A) { heading.textContent = 'Alert preview'; empty.textContent = 'The alert templates are not available.'; return; }
    if (!key) { heading.textContent = 'Alert preview'; empty.textContent = 'Choose a district to see the alert it would receive.'; return; }
    if (!built) build();
    if (!built) return;

    const H = ctx.H;
    const now = H ? H.levelAt(state.i, key) : 0;
    if (!state.userPickedLevel && now >= 1 && state.alertLevel !== String(now)) {
      state.alertLevel = String(now);
      levelSlot.group?.setValue(state.alertLevel);
    }
    const lang = state.alertLang;
    const level = state.alertLevel;
    const t = A.templates?.[lang]?.[level];
    heading.textContent = `Alert preview for ${ctx.districts.get(key)?.name ?? key}`;
    const text = fillTemplate(t?.sms, key, lang);
    screen.textContent = text || 'No template for this language and level.';
    screen.lang = lang;
    const { single, parts, plain } = smsLimit(text);
    const over = text.length > single;
    counter.replaceChildren(
      h('strong', { class: 'al-n', text: String(text.length) }),
      ` of ${single} characters. `,
      over ? h('span', { class: 'al-over', text: `Needs ${parts} messages.` }) : 'Fits one SMS.');
    meter.style.width = `${Math.min(100, (text.length / single) * 100)}%`;
    meter.classList.toggle('is-over', over);
    document.getElementById('phone-part').textContent = `1/${parts}`;
    const w = worstCase(level, lang);
    const worstName = w ? (usesDevanagari(lang) ? ctx.districts.get(w.key)?.name_hi : null) ?? ctx.districts.get(w.key)?.name : '';
    worst.replaceChildren(
      plain ? `Plain Latin text gets ${single} characters. Devanagari gets 70, because each character takes two bytes.` : 'Devanagari is limited to 70 characters, because each character takes two bytes.',
      w ? ` Longest of all ${plural(ctx.districts.size, 'district')}: ${worstName}, ${w.n} characters.` : '');

    const path = A.audio?.[lang]?.[level];
    if (path) {
      if (audio.dataset.path !== path) {
        audio.dataset.path = path;
        fallbackTried = false;
        audio.src = `data/${path}`;
      }
      audio.hidden = false;
      audioNote.hidden = true;
    } else {
      delete audio.dataset.path;
      audio.removeAttribute('src');
      audio.hidden = true;
      audioNote.hidden = false;
      audioNote.textContent = 'No recording for this language and level. The script is below.';
    }
    script.textContent = fillTemplate(t?.voice, key, lang);
    script.lang = lang;
    if (now === 0) {
      worst.append(h('span', { class: 'al-none', text: ` On this date ${ctx.districts.get(key)?.name} is ${levelOf(0).en}, so no alert would go out.` }));
    }
  }
  return { update };
}
