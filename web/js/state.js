// One small store. Views subscribe and redraw only what a change touches.
export const state = {
  route: 'map',
  year: null,
  i: 0,
  lead: '3',
  layer: 'flood',
  district: null,
  story: null,
  windowMode: 'season',
  playing: false,
  panelTab: 'district',
  site: null,
  alertLang: null,
  alertLevel: null,
};

const listeners = new Set();
export const subscribe = (fn) => listeners.add(fn);

export function set(patch) {
  const changed = {};
  for (const [k, v] of Object.entries(patch)) {
    if (state[k] !== v) {
      state[k] = v;
      changed[k] = true;
    }
  }
  if (Object.keys(changed).length) for (const fn of listeners) fn(changed);
}
