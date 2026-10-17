// Time machine: forecast guarantee health at a date using the current graph and real attestation dates.
// Used by the Explorer (in-place graph update) and the landing board (guarantee cards).
import {source, el, showQueries, replay} from './source.js';

const $ = id => document.getElementById(id);
const date = $('time-date'), slider = $('time-range'), label = $('time-label'), events = $('time-events');
const track = slider.closest('.tm-track'), marksList = $('tm-marks'), bubble = $('tm-bubble');
const day = 86400000, motion = window.premiseMotion;
let sequence = 0, debounce, data, start;
const nameCache = new Map();

const toIndex = value => Math.round((Date.parse(value + 'T00:00:00Z') - start) / day);
const fromIndex = n => new Date(start + n * day).toISOString().slice(0, 10);
const pretty = value => new Date(value + 'T00:00:00Z').toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const graphLoaded = () => new Promise(resolve => document.addEventListener('premise:graph', resolve, {once: true}));

// The bubble follows the thumb on a spring, so dragging feels physical rather than jumpy.
const spring = {x: 0, v: 0, target: 0, frame: 0};
function thumbX() {
  const width = slider.getBoundingClientRect().width, thumb = 16;
  const ratio = (Number(slider.value) - Number(slider.min)) / Math.max(1, Number(slider.max) - Number(slider.min));
  return thumb / 2 + ratio * (width - thumb);
}
function moveBubble() {
  bubble.textContent = pretty(date.value || data.today);
  spring.target = thumbX() - bubble.offsetWidth / 2;
  if (motion.reduced()) { spring.x = spring.target; bubble.style.transform = `translateX(${spring.x}px)`; return; }
  if (spring.frame) return;
  let last = performance.now();
  const step = now => {
    const dt = Math.min(0.032, (now - last) / 1000); last = now;
    const force = 320 * (spring.target - spring.x) - 30 * spring.v;
    spring.v += force * dt; spring.x += spring.v * dt;
    bubble.style.transform = `translateX(${spring.x}px)`;
    if (Math.abs(spring.target - spring.x) < 0.3 && Math.abs(spring.v) < 0.3) { spring.x = spring.target; bubble.style.transform = `translateX(${spring.x}px)`; spring.frame = 0; return; }
    spring.frame = requestAnimationFrame(step);
  };
  spring.frame = requestAnimationFrame(step);
}

// Names of the people whose attestations expire, from the recorded node details.
async function attesters(assumption) {
  if (!nameCache.has(assumption)) nameCache.set(assumption, source.request('/api/graph/node/' + encodeURIComponent(assumption)).then(d => d.names || {}).catch(() => ({})));
  return nameCache.get(assumption);
}
async function callout(value) {
  const token = sequence;
  events.replaceChildren();
  if (!value || value === data.today) return;
  const lines = [];
  const expired = value > data.today ? data.marks.filter(m => m.kind === 'review_by' && m.date >= data.today && m.date < value) : [];
  for (const mark of expired) {
    const names = await attesters(mark.assumption);
    if (token !== sequence) return;
    const text = `${names[mark.person] || mark.person}'s attestation needed review by ${pretty(mark.date)}`;
    lines.push(`${mark.assumption}: ${text}`);
    const chip = el(events, 'span', '', 'tm-callout');
    chip.append(window.premiseIcon('clock'));
    el(chip, 'code', mark.assumption);
    el(chip, 'span', text);
  }
  if (value > data.today && !expired.length) el(events, 'span', 'No attestation needs review before this date.');
  if (window.premiseExplorer) {
    const summary = (lines.length ? lines.join(' · ') : value > data.today ? 'no attestation needs review before this date' : 'historical evaluation') + ' · forecast on the current graph, not an old revision';
    window.premiseExplorer.setVerdict({state: 'date', word: (value > data.today ? 'Forecast · ' : 'Evaluated · ') + pretty(value), summary});
  }
}

function describe() {
  const value = date.value;
  label.textContent = (value > data.today ? 'Forecast · ' : value < data.today ? 'Historical evaluation · ' : 'Today · ') + value;
  label.classList.toggle('forecast', value > data.today);
  label.closest('.tm')?.classList.toggle('dated', value !== data.today);
}

async function apply() {
  const token = ++sequence;
  if (!date.validity.valid || !date.value) { label.textContent = 'Choose a date within the slider range.'; return; }
  slider.value = toIndex(date.value);
  describe(); moveBubble();
  const url = new URL(location.href); url.searchParams.set('at', date.value); history.replaceState(null, '', url);
  if (window.premiseExplorer) { document.dispatchEvent(new CustomEvent('premise:time')); callout(date.value); return; }
  callout(date.value);
  const result = await source.request('/api/graph/overview', {at: date.value});
  if (token !== sequence) return;
  showQueries(result);
  for (const n of result.nodes) {
    if (n.label !== 'Guarantee') continue;
    const card = document.querySelector(`[data-guarantee="${n.id}"]`);
    if (!card) continue;
    card.classList.remove('is-holds', 'is-broken', 'is-unknown');
    card.classList.add('is-' + n.health);
    const badge = card.querySelector('.badge');
    if (badge) badge.replaceWith(window.premiseBadge(n.health));
    card.href = '/explore?focus=' + encodeURIComponent(n.id) + '&at=' + date.value;
    for (const p of card.querySelectorAll('.prereq,.dots,.g-foot')) p.hidden = true;
  }
}

function live() {
  sequence++;
  const url = new URL(location.href); url.searchParams.delete('at'); history.replaceState(null, '', url);
  date.value = data.today; slider.value = toIndex(data.today);
  label.textContent = replay ? 'Recorded baseline' : 'Live today'; label.classList.remove('forecast'); label.closest('.tm')?.classList.remove('dated');
  events.replaceChildren(); moveBubble();
  if (window.premiseExplorer) document.dispatchEvent(new CustomEvent('premise:time'));
  else location.reload();
}

try {
  data = await source.request('/api/graph/timeline');
  start = Date.parse(data.start + 'T00:00:00Z');
  date.min = data.start; date.max = data.end;
  slider.max = toIndex(data.end);
  date.value = new URL(location.href).searchParams.get('at') || data.today;
  slider.value = toIndex(date.value);
  const marks = $('time-marks');
  for (const mark of data.marks) {
    const n = toIndex(mark.date);
    if (n < 0 || n > Number(slider.max)) continue;
    const option = el(marks, 'option'); option.value = n; option.label = `${mark.assumption} ${mark.kind} ${mark.date}`;
    if (mark.kind === 'review_by') { const tick = el(marksList, 'li'); tick.style.left = `${n / Number(slider.max) * 100}%`; tick.title = `${mark.assumption} review by ${mark.date}`; }
  }
  const today = el(marksList, 'li', '', 'today'); today.style.left = `${toIndex(data.today) / Number(slider.max) * 100}%`;
  if (replay) {
    date.readOnly = true;
    $('time-live').textContent = 'Recorded baseline';
    el(document.querySelector('[aria-label="Time machine"]'), 'p', 'Replay slider snaps to recorded dates. Run locally for any date.', 'tm-note');
  }
  date.onchange = () => apply().catch(error => { label.textContent = error.message; });
  slider.oninput = () => {
    let instant = start + Number(slider.value) * day;
    if (replay) instant = source.index.dates.map(d => Date.parse(d + 'T00:00:00Z')).reduce((best, d) => Math.abs(d - instant) < Math.abs(best - instant) ? d : best);
    date.value = new Date(instant).toISOString().slice(0, 10);
    describe(); moveBubble();
    clearTimeout(debounce);
    debounce = setTimeout(() => date.onchange(), 160);
  };
  slider.onchange = () => { clearTimeout(debounce); date.onchange(); };
  slider.addEventListener('pointerdown', () => track.classList.add('dragging'));
  addEventListener('pointerup', () => track.classList.remove('dragging'));
  slider.addEventListener('focus', () => track.classList.add('dragging'));
  slider.addEventListener('blur', () => track.classList.remove('dragging'));
  $('time-live').onclick = live;
  if (new URL(location.href).searchParams.has('at')) await apply();
  else { describe(); moveBubble(); }
} catch (error) { label.textContent = error.message; }

// Story mode hooks: each resolves once the graph shows the new date.
window.premiseTime = {
  async setDate(value) { date.value = value; const loaded = graphLoaded(); await apply(); if (window.premiseExplorer) await loaded; },
  async live() { if (!new URL(location.href).searchParams.has('at')) return; const loaded = graphLoaded(); live(); if (window.premiseExplorer) await loaded; },
  get today() { return data?.today; },
};
