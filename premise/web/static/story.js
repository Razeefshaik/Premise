// Story mode: a guided minute on real API results (live or recorded replay). Each step fetches what it
// needs, shows a one-line caption written from that data, then plays the same visual code the UI uses.
import {source} from './source.js';

const explorer = window.premiseExplorer, whatIf = window.premiseWhatIf, time = window.premiseTime;
const $ = id => document.getElementById(id);
const bar = $('story-bar'), caption = $('story-caption'), progress = $('story-progress'), count = $('story-count');
const playButton = $('story-play'), pauseButton = $('story-pause');
const preset = whatIf.presets.find(p => p.id === 'S1');
const FORECAST = '2027-03-02';
const pretty = value => new Date(value).toLocaleDateString('en-GB', {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'});
const list = items => items.length > 1 ? items.slice(0, -1).join(', ') + ' and ' + items.at(-1) : items[0] || '';
let ctx = {};

const steps = [
  {
    caption: () => 'This is Kestrel’s company brain: decisions promise guarantees, and guarantees rest on assumptions about live config.',
    async play({instant}) { explorer.unspotlight(); await time.live(); await whatIf.reset({instant: true}); await explorer.goOverview(); await explorer.fit(undefined, {instant}); },
  },
  {
    caption: () => 'G_DEDUPE promises that every Paylane webhook is applied once. It holds only while Paylane retries inside our dedupe window.',
    async play({instant}) { await explorer.spotlight('G_DEDUPE', {instant}); explorer.select('G_DEDUPE'); },
  },
  {
    async prepare({instant}) { explorer.unspotlight(); ctx.run = await whatIf.stage(preset.values, {instant}); ctx.result = ctx.run?.result; },
    caption: () => { const c = ctx.result?.changed?.[0]; return c ? `Paylane extends its retry window from ${c.old} to ${c.new} hours. ${list(ctx.result.touched)} is now violated.` : 'Paylane extends its retry window to 72 hours.'; },
    async play() { await ctx.run.frame(); await ctx.run.heal(); await ctx.run.touched(); },
  },
  {
    caption: () => { const longest = [...(ctx.result?.not_holding || [])].sort((a, b) => b.chain.length - a.chain.length)[0]; return longest ? `Failure travels up the REQUIRES chain: ${[...longest.chain].reverse().join(' → ')}.` : 'Failure travels up the REQUIRES chain.'; },
    async play() { await ctx.run.propagate(); await ctx.run.decisions(); },
  },
  {
    caption: () => { const r = ctx.result; return `Verdict: ${r.verdict}. ${r.not_holding.length} guarantees break and ${r.decisions.length} decisions are affected, though their text never mentions Paylane.`; },
    async play() { ctx.run.verdict(); },
  },
  {
    caption: () => { const r = ctx.result, people = [...new Set(r.decisions.flatMap(d => d.reviewers))].map(id => r.names?.[id] || id); return `Premise routes review to people still at the company: ${list(people)}.`; },
    async play({instant}) { const ids = ctx.result.decisions.map(d => d.id); explorer.cy.elements().addClass('faded'); for (const id of ids) explorer.cy.getElementById(id).closedNeighborhood().removeClass('faded'); explorer.select(ids.includes('ADR-012') ? 'ADR-012' : ids[0]); await explorer.fit(explorer.cy.collection(ids.map(id => explorer.cy.getElementById(id))).closedNeighborhood(), {instant, padding: 60}); },
  },
  {
    caption: () => { const fix = ctx.result.verified_fixes[0]; return fix ? `It has already verified a complete fix: ${Object.entries(fix.changes).map(([k, v]) => `${k} = ${v}`).join(' and ')}.` : 'No verified fix was returned for this change.'; },
    async play({instant}) { explorer.unspotlight(); await explorer.fit(undefined, {instant}); document.querySelector('#explorer-verdict .metal')?.classList.add('pulse'); },
  },
  {
    async prepare({instant}) { const fix = ctx.result.verified_fixes[0]; ctx.fixRun = await whatIf.stage({...preset.values, ...(fix?.changes || {})}, {instant}); ctx.fixed = ctx.fixRun?.result; },
    caption: () => `Applied as a proposal: the graph heals in reverse order. Verdict: ${ctx.fixed?.verdict === 'CLEAR_WITHIN_SCOPE' ? 'CLEAR' : ctx.fixed?.verdict}.`,
    async play() { await ctx.fixRun.all(); },
  },
  {
    caption: () => `Now move the calendar to ${pretty(FORECAST + 'T00:00:00Z')}. No code changes; only time passes.`,
    async play() { await time.setDate(FORECAST); },
  },
  {
    async prepare() {
      const node = await source.request('/api/graph/node/A_STABLE_EVENT_ID');
      const attestation = node.assumption?.attestations?.[0];
      ctx.attester = attestation ? (node.names?.[attestation.person] || attestation.person) : 'The';
      ctx.reviewBy = attestation?.review_by ? pretty(attestation.review_by) : '';
      ctx.unknown = explorer.cy.nodes('[label="Guarantee"].unknown').map(n => n.id());
    },
    caption: () => `${ctx.attester}’s attestation on A_STABLE_EVENT_ID needed review by ${ctx.reviewBy}. ${ctx.unknown.includes('G_DEDUPE') ? 'G_DEDUPE' : ctx.unknown[0]} and ${Math.max(0, ctx.unknown.length - 1)} more guarantees are now unknown.`,
    async play({instant}) { await explorer.spotlight('G_DEDUPE', {instant}); explorer.select('G_DEDUPE'); },
  },
];

let index = -1, token = 0, paused = false, holdTimer = 0;
const story = {rate: 1, get index() { return index; }, get running() { return !bar.hidden; }, steps: steps.length};
window.premiseStory = story;
for (let i = 0; i < steps.length; i++) progress.append(document.createElement('li'));

const dwell = text => (1600 + 28 * text.length) / story.rate;
function show(text) {
  caption.textContent = text;
  caption.classList.remove('enter'); void caption.offsetWidth; caption.classList.add('enter');
  count.textContent = `${index + 1} / ${steps.length}`;
  [...progress.children].forEach((li, i) => { li.className = i < index ? 'done' : i === index ? 'now' : ''; });
  $('story-prev').disabled = index <= 0;
}
function setPaused(value) {
  paused = value;
  pauseButton.replaceChildren(window.premiseIcon(value ? 'play' : 'pause'));
  pauseButton.setAttribute('aria-label', value ? 'Resume' : 'Pause');
  bar.dataset.paused = String(value);
}
function clearHold() { clearTimeout(holdTimer); holdTimer = 0; }
function scheduleNext() {
  clearHold();
  if (paused) return;
  holdTimer = setTimeout(() => index < steps.length - 1 ? goTo(index + 1) : finish(), dwell(caption.textContent));
}

let completed = -1;  // the last step whose prepare and play both finished
async function run(i, options, mine) {
  const step = steps[i];
  index = i;
  if (step.prepare) await step.prepare(options);
  if (mine !== token) return false;
  const text = step.caption(ctx);
  if (!options.silent) show(text);
  await step.play(options);
  if (mine !== token) return false;
  completed = i;
  return true;
}
async function goTo(i) {
  const mine = ++token;
  clearHold();
  try {
    // Going back restarts from the beginning; skipping ahead (or past an interrupted step) replays the
    // missing steps instantly, so every step starts from the state the previous one produced.
    const from = i <= completed ? 0 : completed + 1;
    if (from === 0 && i > 0) ctx = {};
    for (let j = from; j < i; j++) if (!(await run(j, {instant: true, silent: true}, mine))) return;
    index = i;
    if (!(await run(i, {instant: false}, mine))) return;
    document.dispatchEvent(new CustomEvent('premise:story-step', {detail: {index: i}}));
    scheduleNext();
  } catch (error) {
    if (mine === token) { caption.textContent = 'The story could not continue: ' + error.message; setPaused(true); }
  }
}
function finish() {
  clearHold(); setPaused(true);
  caption.textContent = 'That is Premise: search finds documents; Premise finds consequences. Replay, or explore freely.';
  [...progress.children].forEach(li => { li.className = 'done'; });
  document.dispatchEvent(new CustomEvent('premise:story-done'));
}
function start() {
  ctx = {}; index = -1; completed = -1; setPaused(false);
  bar.hidden = false;
  const stage = document.querySelector('.xp-canvas-wrap').getBoundingClientRect();
  if (stage.top < 0 || stage.bottom > innerHeight + 1) document.getElementById('explorer-verdict').scrollIntoView({block: 'start', behavior: window.premiseMotion.reduced() ? 'auto' : 'smooth'});
  pauseButton.focus({preventScroll: true});
  return goTo(0);
}
async function exit() {
  token++; clearHold(); completed = -1;
  bar.hidden = true; index = -1;
  const url = new URL(location.href); url.searchParams.delete('story'); history.replaceState(null, '', url);
  playButton.focus({preventScroll: true});
  explorer.unspotlight();
  await time.live();
  await whatIf.reset({instant: true});
  await explorer.fit(undefined, {instant: true});
}
story.start = start; story.exit = exit; story.next = () => index < steps.length - 1 ? goTo(index + 1) : finish(); story.prev = () => goTo(Math.max(0, index - 1));
story.togglePause = () => {
  if (index >= steps.length - 1 && paused && !holdTimer && caption.textContent.startsWith('That is Premise')) return start();
  setPaused(!paused); if (!paused) scheduleNext(); else clearHold();
};

playButton.onclick = () => start();
$('story-next').onclick = story.next;
$('story-prev').onclick = story.prev;
$('story-exit').onclick = exit;
pauseButton.onclick = story.togglePause;
document.addEventListener('keydown', event => {
  if (bar.hidden || event.altKey || event.ctrlKey || event.metaKey) return;
  const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName);
  if (event.key === 'Escape') { event.preventDefault(); exit(); }
  else if (typing) return;
  else if (event.key === 'ArrowRight') { event.preventDefault(); story.next(); }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); story.prev(); }
  else if ((event.key === ' ' || event.key === 'k') && event.target.tagName !== 'BUTTON') { event.preventDefault(); story.togglePause(); }
});

if (new URL(location.href).searchParams.get('story') === '1') start();
