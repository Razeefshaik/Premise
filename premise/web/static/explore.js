// Decision Explorer: a layered, live view of the decision graph. consequences.js (What if), time.js
// (time machine) and story.js (guided story) drive it through window.premiseExplorer.
import {source, el, showQueries, replay} from './source.js';

const motion = window.premiseMotion;
const $ = id => document.getElementById(id);
const search = $('entity-search'), depth = $('graph-depth'), message = $('graph-message'), picker = $('node-picker');
const banner = $('explorer-verdict'), wrap = document.querySelector('.xp-canvas-wrap');
const params = new URL(location.href).searchParams;
let focus = params.get('focus') || '', selected = '', pathStart = '', sequence = 0;
depth.value = ['1', '2', '3', '4'].includes(params.get('depth')) ? params.get('depth') : '1';

const shapes = {Decision: 'round-rectangle', Guarantee: 'ellipse', Assumption: 'diamond', Fact: 'triangle', Service: 'round-rectangle', Person: 'hexagon', Team: 'barrel'};
const healthClasses = 'holds holding broken violated unknown unverified unevaluable';
const hypothetical = new Map();
let selectedRecord = null, selectionSequence = 0;

const caption = (node, health = node.health) => (node.label === 'Person' ? node.title : node.id) + '\n' + (health || node.label);
const graphNode = node => ({data: {...node, baselineHealth: node.health, caption: caption(node), shape: shapes[node.label]}, classes: node.health || ''});
const visibleNodes = () => cy.nodes().not('.signal');
const personName = node => node.label === 'Person' ? node.title : node.id;

// Colours come from tokens.css so the graph, badges and banner share one palette.
// Cytoscape needs rgba(r,g,b,a); tokens use modern rgb(r g b / a).
const token = name => motion.token(name).replace(/^rgb\((\d+)\s+(\d+)\s+(\d+)\s*\/\s*([\d.]+)\)$/, 'rgba($1,$2,$3,$4)');
const C = {holds: token('holds'), unknown: token('unknown'), broken: token('broken'), violated: token('violated'), ice: token('ice'),
  indigo2: token('indigo-2'), decision: token('decision'), edge: token('edge'), ink: token('ink'), ground: token('panel-solid')};
const stateMs = () => motion.ms('state', 240);
const cy = window.cytoscape({
  container: $('explorer-canvas'), elements: [], minZoom: 0.25, maxZoom: 2.5,
  style: [
    {selector: 'node', style: {'font-family': 'Manrope, Segoe UI, sans-serif', 'font-size': 12, 'font-weight': 600, color: C.ink,
      'text-wrap': 'wrap', 'text-max-width': 132, 'text-valign': 'bottom', 'text-margin-y': 7, 'text-outline-color': C.ground, 'text-outline-width': 2.5,
      'min-zoomed-font-size': 6, 'background-color': '#9aa3d8', width: 30, height: 30, 'border-width': 0, 'border-color': C.ice,
      'underlay-color': C.ice, 'underlay-opacity': 0, 'underlay-padding': 6, 'underlay-shape': 'ellipse',
      'transition-property': 'background-color, border-color, border-width, opacity, underlay-opacity, underlay-padding', 'transition-duration': `${stateMs() / 1000}s`, 'transition-timing-function': 'ease-out'}},
    {selector: 'node[caption]', style: {label: 'data(caption)'}},
    {selector: 'node[shape]', style: {shape: 'data(shape)'}},
    {selector: 'node[label="Decision"]', style: {'background-color': C.decision, 'border-width': 1.5, 'border-color': C.indigo2, width: 46, height: 28}},
    {selector: 'node[label="Guarantee"]', style: {width: 34, height: 34}},
    {selector: 'node[label="Assumption"]', style: {width: 32, height: 32}},
    {selector: 'node[label="Fact"]', style: {width: 24, height: 24, 'background-color': C.ice}},
    {selector: 'node[label="Service"]', style: {'background-color': '#262b52', 'border-width': 1, 'border-color': C.indigo2, width: 38, height: 24}},
    {selector: 'node[label="Person"]', style: {'background-color': '#c7b8ff'}},
    {selector: '.holds, .holding', style: {'background-color': C.holds}},
    {selector: '.broken', style: {'background-color': C.broken}},
    {selector: '.violated', style: {'background-color': C.violated}},
    {selector: '.unknown, .unverified, .unevaluable', style: {'background-color': C.unknown}},
    {selector: 'node[label="Decision"].affected', style: {'border-color': C.broken, 'border-width': 3, 'background-color': '#3b1426'}},
    {selector: '.touched', style: {'border-width': 3, 'border-color': '#ffffff'}},
    {selector: '.flash', style: {'underlay-opacity': 0.45, 'underlay-padding': 12}},
    {selector: '.faded', style: {opacity: 0.2}},
    {selector: 'node:selected', style: {'border-width': 3, 'border-color': C.ice}},
    {selector: '.path', style: {'line-color': C.ice, 'target-arrow-color': C.ice, width: 3.5, 'border-width': 3, 'border-color': '#ffffff'}},
    {selector: 'edge', style: {width: 1.3, 'line-color': C.edge, 'target-arrow-color': C.edge, 'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier',
      'transition-property': 'line-color, target-arrow-color, width, opacity', 'transition-duration': `${stateMs() / 1000}s`, 'transition-timing-function': 'ease-out'}},
    {selector: 'edge.fired', style: {'line-color': C.broken, 'target-arrow-color': C.broken, width: 2.6}},
    {selector: 'edge.warned', style: {'line-color': C.unknown, 'target-arrow-color': C.unknown, width: 2.6}},
    {selector: 'edge.healed', style: {'line-color': C.holds, 'target-arrow-color': C.holds, width: 2.6}},
    {selector: 'node.signal', style: {label: '', width: 10, height: 10, 'background-color': '#ffffff', 'underlay-opacity': 0.4, 'underlay-padding': 6, 'underlay-color': '#ffffff', events: 'no', 'z-index': 999, 'transition-duration': '0s'}},
    {selector: 'node.signal.bad', style: {'background-color': C.broken, 'underlay-color': C.broken}},
    {selector: 'node.signal.warn', style: {'background-color': C.unknown, 'underlay-color': C.unknown}},
    {selector: 'node.signal.good', style: {'background-color': C.holds, 'underlay-color': C.holds}},
  ],
});

if (replay) {
  depth.max = '3'; if (Number(depth.value) > 3) depth.value = '3';
  for (const input of document.querySelectorAll('#graph-kinds input')) input.disabled = true;
  el(document.querySelector('.v3-network'), 'p', 'Replay includes recorded reasoning/service views at depths 1 to 3. Other paths or views may require a local live run.');
}

// Layered layout: facts, then assumptions, then guarantees by REQUIRES depth, then decisions and
// services, so a failure reads bottom to top. Views with people or teams use a force layout.
function layout({animate = false} = {}) {
  const nodes = visibleNodes();
  if (!nodes.length) return Promise.resolve();
  if (nodes.some(n => ['Person', 'Team'].includes(n.data('label')))) {
    cy.layout({name: 'cose', animate: false, randomize: false, nodeRepulsion: 9000, idealEdgeLength: 90, padding: 40}).run();
    return Promise.resolve();
  }
  const level = new Map(), guarantees = nodes.filter('[label="Guarantee"]');
  for (const n of nodes) {
    const label = n.data('label');
    if (label === 'Fact') level.set(n.id(), 0);
    else if (label === 'Assumption') level.set(n.id(), 1);
    else if (label === 'Guarantee') level.set(n.id(), 2);
  }
  for (let changed = true, guard = 0; changed && guard < 24; guard++) {
    changed = false;
    for (const g of guarantees) {
      let value = 2;
      for (const e of g.outgoers('edge[type="REQUIRES"]')) if (e.target().data('label') === 'Guarantee') value = Math.max(value, level.get(e.target().id()) + 1);
      if (value !== level.get(g.id())) { level.set(g.id(), value); changed = true; }
    }
  }
  const top = Math.max(2, ...guarantees.map(g => level.get(g.id())));
  for (const n of nodes) if (!level.has(n.id())) level.set(n.id(), top + 1);
  const rows = new Map();
  for (const n of nodes) { const l = level.get(n.id()); if (!rows.has(l)) rows.set(l, []); rows.get(l).push(n); }
  const levels = [...rows.keys()].sort((a, b) => a - b), x = new Map();
  const spread = row => row.forEach((n, i) => x.set(n.id(), row.length > 1 ? i / (row.length - 1) : 0.5));
  for (const l of levels) { rows.get(l).sort((a, b) => a.id().localeCompare(b.id())); spread(rows.get(l)); }
  for (let pass = 0; pass < 6; pass++) {
    for (const l of pass % 2 ? levels : [...levels].reverse()) {
      const row = rows.get(l);
      const centre = n => { const xs = n.neighborhood('node').not('.signal').map(m => x.get(m.id())).filter(v => v !== undefined); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : x.get(n.id()); };
      const keys = new Map(row.map(n => [n.id(), centre(n)]));
      row.sort((a, b) => keys.get(a.id()) - keys.get(b.id()) || a.id().localeCompare(b.id()));
      spread(row);
    }
  }
  const box = cy.container().getBoundingClientRect(), aspect = box.width / Math.max(1, box.height);
  const perRow = Math.max(4, Math.min(8, Math.round(Math.sqrt(nodes.length * aspect))));
  // Row spacing follows the canvas shape so the graph fills it instead of shrinking labels.
  const rowCount = [...rows.values()].reduce((n, row) => n + Math.ceil(row.length / perRow), 0);
  const column = 150, widest = Math.min(perRow, Math.max(...[...rows.values()].map(r => r.length))) * column;
  const gap = Math.max(70, Math.min(120, widest / aspect / Math.max(1, rowCount - 1))), sub = Math.max(58, gap * 0.85), positions = new Map();
  let y = 0;
  for (const l of [...levels].reverse()) {
    const row = rows.get(l);
    for (let start = 0, part = 0; start < row.length; start += perRow, part++) {
      const chunk = row.slice(start, start + perRow), offset = part % 2 ? column / 2 : 0;
      chunk.forEach((n, i) => positions.set(n.id(), {x: (i - (chunk.length - 1) / 2) * column + offset, y}));
      if (start + perRow < row.length) y += sub;
    }
    y += gap;
  }
  const duration = animate ? motion.ms('enter', 320) : 0;
  const run = cy.layout({name: 'preset', positions: n => positions.get(n.id()), fit: false, animate: duration > 0, animationDuration: duration, animationEasing: 'ease-in-out-cubic'});
  const done = run.promiseOn('layoutstop').then(() => fit(undefined, {instant: !animate}));
  run.run();
  return done;
}

function setHealth(id, health, chain) {
  hypothetical.set(id, {health, chain});
  const node = cy.getElementById(id);
  if (node.length) { node.removeClass(healthClasses).addClass(health); node.data({health, caption: caption(node.data(), health)}); }
  if (selected === id) renderStatus();
}
function clearHypothetical() {
  hypothetical.clear();
  for (const node of visibleNodes()) {
    const health = node.data('baselineHealth');
    node.removeClass(healthClasses + ' touched affected flash');
    if (health) node.addClass(health);
    node.data({health, caption: caption(node.data(), health)});
  }
  cy.edges().removeClass('fired warned healed');
  renderStatus();
}
function renderStatus() {
  if (!selectedRecord) return;
  const status = $('node-status'), chain = $('node-chain');
  if (!status) return;
  const overlay = hypothetical.get(selected), health = overlay?.health || selectedRecord.health || selectedRecord.node.lifecycle || selectedRecord.node.label;
  status.textContent = health + (overlay ? ' · Hypothetical' : ' · Baseline');
  status.dataset.state = health;
  const steps = overlay?.chain ?? selectedRecord.chain;
  chain.textContent = steps.length ? 'Chain: ' + steps.join(' → ') : '';
}

// The verdict banner sits above the canvas whatever inspector tab is open; it is the ARIA live region.
const glyphs = {blocked: 'octagon-x', needs_review: 'circle-help', clear: 'check', date: 'clock', baseline: 'network'};
function setVerdict({state = 'baseline', word = '', summary = '', tag = '', actions = []} = {}) {
  const landed = ['blocked', 'needs_review', 'clear'].includes(state) && banner.dataset.state !== state;
  banner.dataset.state = state;
  banner.replaceChildren();
  if (glyphs[state]) { const icon = window.premiseIcon(glyphs[state]); icon.classList.add('v-icon'); banner.append(icon); }
  if (word) el(banner, 'span', word, 'v-word');
  if (summary) el(banner, 'span', summary, 'v-summary');
  if (tag) el(banner, 'span', tag, 'v-tag');
  for (const action of actions) banner.append(action);
  if (landed && !motion.reduced()) { banner.classList.remove('landed'); void banner.offsetWidth; banner.classList.add('landed'); }
}
const baselineVerdict = () => setVerdict({state: 'baseline', word: 'Baseline', summary: '· choose What if, or play the story, to test a change'});

// Camera moves for the story: focus a node's neighbourhood or return to the whole graph.
function spotlight(id, {instant = false} = {}) {
  const node = cy.getElementById(id);
  if (!node.length) return Promise.resolve();
  const near = node.closedNeighborhood().union(node.closedNeighborhood().neighborhood('node')).not('.signal');
  cy.elements().not('.signal').addClass('faded');
  near.removeClass('faded');
  near.edgesWith(near).removeClass('faded');
  return fit(near, {instant, padding: 70});
}
function unspotlight() { cy.elements().removeClass('faded path'); }
function fit(eles = visibleNodes(), {instant = false, padding = 46} = {}) {
  const nodes = eles.nodes ? eles.nodes().not('.signal') : eles;
  if (!nodes.length) return Promise.resolve();
  const bar = $('story-bar'), reserve = bar && !bar.hidden ? bar.offsetHeight + 16 : 0;
  const legend = document.querySelector('.xp-legend'), top = legend ? legend.offsetHeight + 12 : 0;
  const width = cy.width(), height = Math.max(120, cy.height() - reserve - top), box = nodes.boundingBox({includeLabels: true});
  const zoom = Math.min(1.5, Math.max(cy.minZoom(), Math.min((width - 2 * padding) / Math.max(1, box.w), (height - 2 * padding) / Math.max(1, box.h))));
  const pan = {x: width / 2 - zoom * (box.x1 + box.w / 2), y: top + height / 2 - zoom * (box.y1 + box.h / 2)};
  const duration = instant ? 0 : motion.ms('enter', 320) * 2;
  if (!duration) { cy.viewport({zoom, pan}); return Promise.resolve(); }
  return new Promise(resolve => cy.animate({zoom, pan}, {duration, easing: 'ease-in-out-cubic', complete: resolve}));
}

const explorer = {cy, data: null, source, showQueries, load, select, setHealth, clearHypothetical, setVerdict, baselineVerdict, layout, spotlight, unspotlight, fit,
  isBaseline: () => !hypothetical.size,
  async addNodes(ids, isCurrent = () => true) {
    let added = false;
    for (const id of ids) {
      if (!isCurrent()) return;
      if (cy.getElementById(id).length) continue;
      const data = await source.request('/api/graph/neighborhood', viewParams({focus: id, depth: '1', kinds: 'reasoning,services'}));
      if (!isCurrent()) return;
      for (const n of data.nodes) if (!cy.getElementById(n.id).length) { cy.add(graphNode(n)); added = true; }
      for (const e of data.edges) if (!cy.edges().some(edge => edge.source().id() === e.source && edge.target().id() === e.target && edge.data('type') === e.type)) cy.add({data: {...e, id: 'joined-' + e.source + '-' + e.type + '-' + e.target}});
    }
    if (added) { fillPicker(); await layout({animate: true}); await fit(undefined, {instant: true}); }
  },
};
window.premiseExplorer = explorer;

function viewParams(extra = {}) { const at = new URL(location.href).searchParams.get('at'); return at ? {...extra, at} : extra; }
function kinds() { return [...document.querySelectorAll('#graph-kinds input:checked')].map(n => n.value).sort().join(','); }
function urlState() { const url = new URL(location.href); if (focus) url.searchParams.set('focus', focus); else url.searchParams.delete('focus'); url.searchParams.set('depth', depth.value); history.replaceState(null, '', url); }
function fillPicker() {
  const current = picker.value;
  picker.replaceChildren();
  el(picker, 'option', 'Choose a node').value = '';
  for (const n of visibleNodes().map(n => n.data()).sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id))) el(picker, 'option', n.label === 'Person' ? n.title : n.id + ' · ' + n.title).value = n.id;
  if (current) picker.value = current;
}
const sameView = data => {
  const ids = visibleNodes().map(n => n.id());
  return ids.length === data.nodes.length && data.nodes.every(n => cy.getElementById(n.id).length) && cy.edges().length === data.edges.length;
};

async function load() {
  document.dispatchEvent(new CustomEvent('premise:graph-loading'));
  const token = ++sequence;
  selectionSequence++; selectedRecord = null;
  message.textContent = 'Loading graph…'; message.classList.remove('v3-error'); urlState(); search.value = focus; $('depth-value').value = depth.value;
  wrap.classList.add('loading');
  try {
    const data = await source.request(focus ? '/api/graph/neighborhood' : '/api/graph/overview', viewParams(focus ? {focus, depth: depth.value, kinds: kinds()} : {}));
    if (token !== sequence) return;
    explorer.data = data;
    cy.$('.signal').remove();
    if (sameView(data)) {
      // Same nodes (a new date or a reset): change state in place so health fades instead of jumping.
      hypothetical.clear();
      for (const n of data.nodes) {
        const node = cy.getElementById(n.id);
        node.removeClass(healthClasses + ' touched affected flash').addClass(n.health || '');
        node.data({...n, baselineHealth: n.health, caption: caption(n)});
      }
      cy.edges().removeClass('fired warned healed');
    } else {
      cy.elements().remove();
      cy.add([...data.nodes.map(graphNode), ...data.edges.map((e, n) => ({data: {...e, id: 'edge-' + n}}))]);
      layout();
    }
    fillPicker();
    const options = $('entity-options');
    for (const n of data.nodes) if (![...options.options].some(o => o.value === n.id)) { const option = el(options, 'option'); option.value = n.id; option.label = n.title; }
    message.textContent = `${data.nodes.length} nodes · ${data.edges.length} edges · revision ${data.graph_rev}${data.truncated ? ' · View capped at 300 nodes' : ''}`;
    showQueries(data);
    if (selected) select(selected, {activate: false});
    document.dispatchEvent(new CustomEvent('premise:graph', {detail: data}));
  } catch (error) {
    if (token === sequence) { message.textContent = error.message; message.classList.add('v3-error'); }
  } finally {
    if (token === sequence) wrap.classList.remove('loading');
  }
}

function inspectTab(which) {
  for (const name of ['evidence', 'whatif']) {
    $('tab-' + name).setAttribute('aria-selected', String(which === name));
    $(name === 'evidence' ? 'evidence-panel' : 'explorer-whatif').hidden = which !== name;
  }
}
for (const name of ['evidence', 'whatif']) {
  const button = $('tab-' + name);
  button.onclick = () => inspectTab(name);
  button.onkeydown = event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 'evidence' : event.key === 'End' ? 'whatif' : name === 'evidence' ? 'whatif' : 'evidence';
    inspectTab(next); $('tab-' + next).focus();
  };
}
explorer.inspectTab = inspectTab;

async function select(id, {activate = true} = {}) {
  if (activate) inspectTab('evidence');
  selected = id; selectedRecord = null;
  const token = ++selectionSequence, root = $('node-details');
  root.replaceChildren();
  const node = cy.getElementById(id);
  if (node.length) { cy.$(':selected').unselect(); node.select(); }
  $('node-heading').textContent = node.length ? personName(node.data()) : id;
  $('focus-node').disabled = true;
  el(root, 'p', 'Loading evidence…');
  try {
    const data = await source.request('/api/graph/node/' + encodeURIComponent(id), viewParams());
    if (selected !== id || token !== selectionSequence) return;
    selectedRecord = data;
    root.replaceChildren();
    $('node-heading').textContent = data.node.label === 'Person' ? data.node.title : id;
    el(root, 'p', data.statement);
    el(root, 'p').id = 'node-status';
    el(root, 'p').id = 'node-chain';
    renderStatus();
    el(root, 'h3', 'Evidence');
    for (const e of data.evidence) el(root, 'p', `${e.path}:${e.line}`, 'evidence-path');
    if (!data.evidence.length) el(root, 'p', 'No source lines recorded.');
    el(root, 'h3', 'Owners');
    for (const o of data.owners) el(root, 'p', `${o.team_name}: ${o.name || 'No active member'} (${o.evidence} sources)`);
    if (!data.owners.length) el(root, 'p', 'No owning team recorded.');
    el(root, 'h3', 'Reviewers');
    el(root, 'p', data.reviewers.map(r => data.names[r] || r).join(', ') || 'No reviewer recorded');
    $('focus-node').disabled = false;
    showQueries(data);
  } catch (error) {
    if (token === selectionSequence) { root.replaceChildren(); el(root, 'p', error.message, 'v3-error'); }
  }
}

picker.onchange = () => { if (picker.value) select(picker.value); };
cy.on('tap', 'node', async event => {
  const id = event.target.id();
  if (event.target.hasClass('signal')) return;
  if (!event.originalEvent?.shiftKey) { pathStart = id; select(id); return; }
  if (!pathStart) { pathStart = id; message.textContent = 'Shift+click a second node.'; return; }
  try {
    const data = await source.request('/api/graph/path', viewParams({from: pathStart, to: id}));
    showQueries(data);
    cy.elements().removeClass('faded path');
    if (data.path) {
      cy.elements().addClass('faded');
      for (const node of data.path) cy.getElementById(node).removeClass('faded').addClass('path');
      for (const e of data.edges) cy.edges().filter(edge => edge.source().id() === e.source && edge.target().id() === e.target).removeClass('faded').addClass('path');
      message.textContent = data.path.join(' → ');
    } else message.textContent = 'No allowed path within six hops.';
  } catch (error) { message.textContent = error.message; }
  pathStart = '';
});
cy.on('tap', event => { if (event.target === cy) unspotlight(); });

$('focus-form').addEventListener('submit', event => { event.preventDefault(); focus = search.value.trim(); load(); });
$('overview-button').onclick = () => { focus = ''; load(); };
$('focus-node').onclick = () => { focus = selected; load(); };
depth.addEventListener('input', load);
$('graph-kinds').addEventListener('change', load);
document.addEventListener('premise:time', load);
explorer.goOverview = () => { focus = ''; return load(); };

// Desktop shows every control in the toolbar; phones fold depth, include and time behind one toggle.
const toolbar = $('xp-toolbar'), moreToggle = $('xp-more-toggle');
moreToggle.onclick = () => { const open = !toolbar.classList.contains('open'); toolbar.classList.toggle('open', open); moreToggle.setAttribute('aria-expanded', String(open)); };

let resizeTimer;
new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { cy.resize(); if (!cy.animated()) fit(undefined, {instant: true}); }, 150); }).observe($('explorer-canvas'));

baselineVerdict();
await load();
await import('./consequences.js');
await import('./time.js');
await import('./story.js');
