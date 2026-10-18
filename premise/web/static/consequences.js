// What if: hypothetical fact changes checked by the read-only /api/check, then shown as cause and effect.
// A Run visualises one real API result: heal what recovered (reverse order), pulse the touched
// assumption, send failure up each REQUIRES edge hop by hop, light affected decisions, land the verdict.
// Nothing here invents a state: every final health comes from the response (or the recorded baseline).
import {el, showQueries, source, replay} from './source.js';

const explorer = window.premiseExplorer, cy = explorer.cy, motion = window.premiseMotion;
const root = document.getElementById('explorer-whatif');
const values = new Map(), controls = new Map();
let timer, sequence = 0, current = null, signals = 0;
// What the graph shows right now (survives interrupted runs), so every new run diffs against reality.
const shown = new Map(), shownDecisions = new Set();
const factsData = await source.request('/api/graph/facts');

el(root, 'h2', 'What if');
el(root, 'p', 'Hypothetical. Nothing is stored or posted.', 'v3-hypothetical');
if (document.body.dataset.publicDemo === 'true') el(root, 'p', 'Repair search is disabled here. Try S1_FIXED to check the bundled repair as another hypothetical proposal.');
if (replay) el(root, 'p', 'Recorded presets and verified repairs. Run locally to try arbitrary values.');
const presets = el(root, 'div', '', 'preset-row');
for (const preset of factsData.presets) {
  const button = el(presets, 'button', '', 'chip');
  button.type = 'button';
  button.dataset.explorerPreset = preset.id;
  el(button, 'span', preset.id, 'id');
  button.title = preset.title || preset.id;
  button.onclick = () => { setValues(preset.values); schedule(); };
}
const advice = el(root, 'p'), fixes = el(root, 'div', '', 'fix-row'), inputs = el(root, 'div');

const isCurrent = token => () => token === sequence;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const edgeBetween = (from, to) => cy.edges().filter(e => e.source().id() === from && e.target().id() === to);
const dated = () => new URL(location.href).searchParams.has('at');
function setValues(next) { values.clear(); for (const [key, value] of Object.entries(next)) values.set(key, value); render(); }

function render() {
  inputs.replaceChildren(); controls.clear();
  const visible = new Set(cy.nodes().map(n => n.id()));
  for (const fact of factsData.facts) {
    if (!visible.has(fact.id) && !fact.assumptions.some(a => visible.has(a)) && !values.has(fact.id)) continue;
    const group = el(inputs, 'div', '', 'v3-fact');
    const label = el(group, 'label', fact.id);
    const id = 'slider-' + fact.id.replaceAll('.', '-');
    label.htmlFor = id;
    if (typeof fact.value !== 'number') { el(group, 'p', `Main: ${JSON.stringify(fact.value)}. Use a recorded preset for non-numeric changes.`); continue; }
    const unit = fact.id.endsWith('_ms') ? 100 : fact.id.includes('_minutes') ? 5 : fact.id.includes('_seconds') ? 10 : 1;
    const slider = el(group, 'input');
    slider.type = 'range'; slider.id = id; slider.min = 0; slider.step = unit;
    slider.max = Math.max(fact.value * 4, unit * 4, typeof values.get(fact.id) === 'number' ? values.get(fact.id) : 0);
    slider.value = values.has(fact.id) ? values.get(fact.id) : fact.value;
    const number = el(group, 'input');
    number.type = 'number'; number.step = 'any'; number.value = slider.value; number.setAttribute('aria-label', 'Proposed ' + fact.id);
    const reset = el(group, 'button', 'Reset', 'chip quiet-chip');
    reset.type = 'button'; reset.dataset.factReset = 'true';
    reset.onclick = () => { values.delete(fact.id); render(); schedule(); };
    const update = value => {
      if (!Number.isFinite(value) || value < 0) { advice.textContent = 'Enter a finite non-negative number.'; return; }
      values.set(fact.id, value); slider.value = value; number.value = value; schedule();
    };
    slider.oninput = () => update(Number(slider.value));
    number.oninput = () => update(Number(number.value));
    if (replay) { slider.disabled = true; number.disabled = true; reset.disabled = true; }
    controls.set(fact.id, {slider, number});
  }
}

// Signals are temporary, non-interactive Cytoscape nodes animated along an edge (transform only).
function signal(from, to, kind, ms) {
  const a = cy.getElementById(from), b = cy.getElementById(to);
  if (!ms || !a.length || !b.length) return Promise.resolve();
  const dot = cy.add({group: 'nodes', data: {id: 'signal-' + (++signals), label: 'signal'}, classes: 'signal ' + kind, position: {...a.position()}, grabbable: false, selectable: false});
  return new Promise(resolve => dot.animate({position: {...b.position()}}, {duration: ms, easing: 'ease-in-out-quad', complete: () => { dot.remove(); resolve(); }}));
}
function stopSignals() { cy.$('.signal').stop(true, false).remove(); }
function flash(ids) {
  const nodes = cy.collection(ids.map(id => cy.getElementById(id)).filter(n => n.length));
  nodes.addClass('flash');
  setTimeout(() => nodes.removeClass('flash'), motion.reduced() ? 600 : motion.ms('state', 240) * 2);
}

// The state each node holds in a result (null result = recorded baseline).
function states(result) {
  const map = new Map();
  if (!result) return map;
  for (const a of result.assumptions) if (a.state !== 'holding') map.set(a.id, {health: a.state, level: 0});
  for (const g of result.guarantees) if (g.status !== 'holds') map.set(g.id, {health: g.status, chain: g.chain, level: Math.max(1, g.chain.length - 1)});
  return map;
}

class Run {
  constructor(result, token, {instant = false} = {}) {
    this.result = result; this.token = token; this.instant = instant || motion.reduced();
    this.hop = this.instant ? 0 : motion.ms('hop', 220);
    this.before = new Map(shown); this.after = states(result);
    this.affectedBefore = new Set(shownDecisions);
  }
  // Health a node should end in: the response's value, or the recorded baseline when there is none.
  target(id) {
    const r = this.result;
    const a = r?.assumptions.find(x => x.id === id), g = r?.guarantees.find(x => x.id === id);
    if (a) return {health: a.state, chain: []};
    if (g) return {health: g.status, chain: g.chain};
    return {health: cy.getElementById(id).data('baselineHealth') || (id.startsWith('A_') ? 'holding' : 'holds'), chain: []};
  }
  apply(id, health, chain = []) {
    explorer.setHealth(id, health, chain);
    const s = this.after.get(id);
    if (s && s.health === health) shown.set(id, s); else shown.delete(id);
  }
  live() { return this.token === sequence; }
  async pause(ms = this.hop) { if (ms) await wait(ms); return this.live(); }

  // Reverse order: decisions first, then the highest guarantee, down to the assumption.
  async heal() {
    const healed = [...this.before].filter(([id, s]) => !this.after.has(id) || this.after.get(id).health !== s.health);
    const affectedAfter = new Set(this.result ? this.result.decisions.map(d => d.id) : []);
    const cleared = [...this.affectedBefore].filter(id => !affectedAfter.has(id));
    if (!healed.length && !cleared.length) return this.live();
    for (const id of cleared) { cy.getElementById(id).removeClass('affected'); shownDecisions.delete(id); }
    if (cleared.length && !(await this.pause())) return false;
    const levels = [...new Set(healed.map(([, s]) => s.level))].sort((a, b) => b - a);
    for (const level of levels) {
      const step = healed.filter(([, s]) => s.level === level);
      await Promise.all(step.map(([id, s]) => s.chain ? signal(id, s.chain[1], 'good', this.hop) : Promise.resolve()));
      if (!this.live()) return false;
      for (const [id, s] of step) {
        const next = this.target(id);
        this.apply(id, next.health, next.chain);
        if (s.chain) edgeBetween(id, s.chain[1]).removeClass('fired warned').addClass('healed');
      }
      flash(step.map(([id]) => id));
    }
    setTimeout(() => cy.edges('.healed').removeClass('healed'), this.instant ? 0 : 900);
    return this.pause();
  }

  // The changed facts' assumptions pulse first.
  async touched() {
    if (!this.result) return this.live();
    const touched = this.result.touched.filter(id => cy.getElementById(id).length);
    cy.nodes('.touched').removeClass('touched');
    await Promise.all((this.result.changed || []).flatMap(change => touched.map(id => signal(change.fact, id, 'warn', this.hop))));
    if (!this.live()) return false;
    for (const id of touched) cy.getElementById(id).addClass('touched');
    for (const a of this.result.assumptions) this.apply(a.id, a.state);
    flash(touched);
    return this.pause(this.instant ? 0 : this.hop * 1.5);
  }

  // Failure travels up REQUIRES edges one hop at a time, in the chain order the engine returned.
  async propagate() {
    if (!this.result) return this.live();
    const fresh = [...this.after].filter(([id, s]) => s.level > 0 && (!this.before.has(id) || this.before.get(id).health !== s.health));
    const levels = [...new Set(fresh.map(([, s]) => s.level))].sort((a, b) => a - b);
    for (const level of levels) {
      const step = fresh.filter(([, s]) => s.level === level);
      await Promise.all(step.map(([id, s]) => signal(s.chain[1], id, s.health === 'broken' ? 'bad' : 'warn', this.hop)));
      if (!this.live()) return false;
      for (const [id, s] of step) {
        this.apply(id, s.health, s.chain);
        edgeBetween(id, s.chain[1]).addClass(s.health === 'broken' ? 'fired' : 'warned');
      }
      flash(step.map(([id]) => id));
    }
    for (const g of this.result.guarantees) if (!this.after.has(g.id)) this.apply(g.id, g.status, g.chain);
    return this.live();
  }

  // Decisions that promise or rely on a failing guarantee light up together.
  async decisions() {
    if (!this.result) return this.live();
    const failing = new Set(this.result.not_holding.map(g => g.id));
    const routes = [];
    for (const d of this.result.decisions) for (const e of cy.getElementById(d.id).outgoers('edge')) if (failing.has(e.target().id())) routes.push([e.target().id(), d.id]);
    await Promise.all(routes.map(([g, d]) => signal(g, d, 'bad', this.hop)));
    if (!this.live()) return false;
    for (const d of this.result.decisions) { cy.getElementById(d.id).addClass('affected'); shownDecisions.add(d.id); }
    flash(this.result.decisions.map(d => d.id));
    return this.live();
  }

  verdict() {
    if (!this.live()) return false;
    current = this.result;
    if (!this.result) { explorer.clearHypothetical(); shown.clear(); shownDecisions.clear(); explorer.baselineVerdict(); fixes.replaceChildren(); advice.textContent = ''; announceDone(); return true; }
    const r = this.result, word = r.verdict === 'CLEAR_WITHIN_SCOPE' ? 'CLEAR' : r.verdict;
    const broken = r.not_holding.filter(g => g.status === 'broken').length, unknown = r.not_holding.length - broken;
    const people = [...new Set(r.decisions.flatMap(d => d.reviewers))].map(id => r.names?.[id] || id);
    const parts = [];
    if (broken) parts.push(`${broken} guarantee${broken === 1 ? '' : 's'} broken`);
    if (unknown) parts.push(`${unknown} unknown`);
    if (r.decisions.length) parts.push(`${r.decisions.length} decision${r.decisions.length === 1 ? '' : 's'} affected`);
    if (people.length) parts.push('review: ' + people.join(', '));
    if (!parts.length) parts.push('every affected guarantee holds');
    const actions = r.verified_fixes.map(fix => fixButton(fix, 'metal'));
    explorer.setVerdict({state: word.toLowerCase(), word, summary: 'Hypothetical · ' + parts.join(' · '), actions});
    advice.textContent = r.advice;
    fixes.replaceChildren(...r.verified_fixes.map(fix => fixButton(fix, 'button')));
    announceDone();
    return true;
  }

  // Before showing cause and effect, glide the camera to the part of the graph that changes.
  async frame() {
    const ids = new Set([...this.before.keys(), ...this.affectedBefore]);
    if (this.result) { for (const id of this.result.touched) ids.add(id); for (const g of this.result.not_holding) ids.add(g.id); for (const d of this.result.decisions) ids.add(d.id); }
    const visible = cy.nodes().not('.signal');
    const nodes = visible.length <= 24 ? visible : cy.collection([...ids].map(id => cy.getElementById(id)).filter(n => n.length));
    await explorer.fit(nodes.length ? nodes : undefined, {instant: this.instant, padding: 56});
    return this.live();
  }

  async all() {
    return (await this.frame()) && (await this.heal()) && (await this.touched()) && (await this.propagate()) && (await this.decisions()) && this.verdict();
  }
}

function fixButton(fix, cls) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = cls;
  button.append(window.premiseIcon('wrench'), document.createTextNode('Apply verified fix'));
  button.title = Object.entries(fix.changes).map(([fact, value]) => `${fact} = ${value}`).join(', ');
  button.onclick = () => { for (const [fact, value] of Object.entries(fix.changes)) values.set(fact, value); render(); schedule(0); };
  return button;
}
function announceDone() { document.dispatchEvent(new CustomEvent('premise:check-presented', {detail: current})); }

function schedule(delay = 300) {
  clearTimeout(timer);
  sequence++;
  stopSignals();
  explorer.setVerdict({state: 'checking', word: 'Hypothetical · checking…'});
  timer = setTimeout(() => check(), delay);
}
const changeList = () => [...values].sort().map(([fact, value]) => value === null ? {fact, delete: true} : {fact, value});
function syncUrl() {
  const url = new URL(location.href);
  url.searchParams.delete('set');
  for (const [fact, value] of [...values].sort()) url.searchParams.append('set', fact + '=' + JSON.stringify(value));
  history.replaceState(null, '', url);
}

// Fetch a result and stage it; callers decide whether to play every phase (UI) or step (story).
async function prepare(options = {}) {
  const token = ++sequence;
  clearTimeout(timer); stopSignals(); syncUrl();
  if (dated()) { explorer.setVerdict({state: 'date', word: 'Date view', summary: '· choose Live today to try fact changes'}); return null; }
  if (!values.size) return new Run(null, token, options);
  explorer.setVerdict({state: 'checking', word: 'Hypothetical · checking…'});
  const data = await source.request('/api/check', {}, {changes: changeList()});
  if (token !== sequence) return null;
  showQueries(data);
  const changed = (data.changed || []).map(c => `${c.fact} ${JSON.stringify(c.old)} → ${c.deleted ? 'deleted' : JSON.stringify(c.new)}`).join(' · ');
  explorer.setVerdict({state: 'checking', word: 'Hypothetical · tracing', summary: changed});
  const ids = [...new Set([...data.touched, ...data.not_holding.map(g => g.id), ...data.decisions.map(d => d.id)])];
  await explorer.addNodes(ids, isCurrent(token));
  if (token !== sequence) return null;
  return new Run(data, token, options);
}

async function check() {
  try {
    const run = await prepare();
    if (run) await run.all();
  } catch (error) {
    explorer.clearHypothetical(); current = null; shown.clear(); shownDecisions.clear();
    explorer.setVerdict({state: 'baseline', word: 'Hypothetical · unavailable', summary: '· ' + error.message});
    advice.textContent = error.message;
  }
}

for (const raw of new URL(location.href).searchParams.getAll('set')) {
  const index = raw.indexOf('=');
  if (index > 0) { try { values.set(raw.slice(0, index), JSON.parse(raw.slice(index + 1))); } catch { advice.textContent = 'Invalid URL fact value.'; } }
}
function mode() {
  const isDated = dated();
  for (const input of root.querySelectorAll('input,button')) input.disabled = isDated || (replay && (input.tagName === 'INPUT' || input.dataset.factReset));
  if (isDated && explorer.cy && document.getElementById('explorer-verdict').dataset.state !== 'date') explorer.setVerdict({state: 'date', word: 'Date view', summary: '· choose Live today to try fact changes'});
  return isDated;
}
function refresh() {
  render();
  if (mode()) return;
  if (values.size && !current) schedule();
  else if (!values.size && !current) explorer.baselineVerdict();
}
refresh();
const forget = () => { current = null; shown.clear(); shownDecisions.clear(); };
document.addEventListener('premise:graph', () => { forget(); refresh(); });
document.addEventListener('premise:graph-loading', () => { clearTimeout(timer); sequence++; stopSignals(); fixes.replaceChildren(); });
document.addEventListener('premise:time', () => { clearTimeout(timer); sequence++; stopSignals(); forget(); explorer.clearHypothetical(); fixes.replaceChildren(); mode(); });

// Story mode drives the same code path one phase at a time.
window.premiseWhatIf = {
  values, presets: factsData.presets,
  get current() { return current; },
  async stage(next, options) { setValues(next); return prepare(options); },
  async apply(next, options) { const run = await this.stage(next, options); if (run) await run.all(); return current; },
  async reset(options) { values.clear(); render(); const run = await prepare(options); if (run) await run.all(); },
};
