import mermaid from '/static/graph.js';

const inputs = new Map([...document.querySelectorAll('.fact-input')].map(el => [el.dataset.fact, el]));
const data = JSON.parse(document.getElementById('whatif-data').textContent);
const verdict = document.getElementById('check-verdict');
const panel = document.getElementById('check-result');
let timer, sequence = 0, controller;

function append(parent, tag, text) {const el = document.createElement(tag); el.textContent = text; parent.append(el); return el;}
function setVerdict(value, text = value) {
  verdict.className = `badge ${String(value).toLowerCase()}`;
  const glyph = window.premiseGlyph?.(value);
  verdict.replaceChildren(...(glyph ? [window.premiseIcon(glyph)] : []), document.createTextNode(text));
}
function fill(values, reset = false) {
  if (reset) for (const input of inputs.values()) input.value = '';
  for (const [id, value] of Object.entries(values)) if (inputs.has(id)) inputs.get(id).value = JSON.stringify(value);
  schedule();
}
function schedule() {clearTimeout(timer); sequence++; if (controller) controller.abort(); timer = setTimeout(check, 400);}
for (const input of inputs.values()) input.addEventListener('input', schedule);
for (const button of document.querySelectorAll('[data-preset]')) button.addEventListener('click', () => {
  for (const other of document.querySelectorAll('[data-preset]')) other.setAttribute('aria-pressed', String(other === button));
  fill(data.presets.find(p => p.id === button.dataset.preset).values, true);
});
document.getElementById('reset-proposal').addEventListener('click', () => {
  for (const other of document.querySelectorAll('[data-preset]')) other.setAttribute('aria-pressed', 'false');
  fill({}, true);
});

async function check() {
  const token = sequence;
  const changes = [];
  for (const [fact, input] of inputs) {
    const raw = input.value.trim();
    if (!raw) continue;
    let value; try {value = JSON.parse(raw);} catch {value = raw;}
    changes.push(value === null ? {fact, delete: true} : {fact, value});
  }
  const url = new URL(location.href); url.searchParams.delete('set');
  for (const change of changes) url.searchParams.append('set', `${change.fact}=${JSON.stringify(change.delete ? null : change.value)}`);
  history.replaceState(null, '', url);
  const containers = ['check-reasons', 'whatif-graph', 'whatif-guarantees', 'whatif-decisions', 'whatif-fixes'];
  if (!changes.length) {
    for (const id of containers) document.getElementById(id).replaceChildren();
    setVerdict('', 'Choose a change'); document.getElementById('check-advice').textContent = ''; panel.classList.remove('updating'); return;
  }
  setVerdict('checking', 'Checking'); panel.classList.add('updating');
  controller = new AbortController();
  try {
    const response = await fetch('/api/check', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({changes}), signal: controller.signal});
    const result = await response.json();
    if (token !== sequence) return;
    if (!response.ok) throw new Error(response.status === 422 ? 'This proposal is invalid or contains an untracked fact.' : 'The graph is unavailable.');
    for (const id of containers) document.getElementById(id).replaceChildren();
    setVerdict(result.verdict);
    document.getElementById('check-advice').textContent = result.advice;
    for (const reason of result.reasons) append(document.getElementById('check-reasons'), 'li', reason.detail);
    if (result.not_holding.length) {
      const wrap = append(document.getElementById('whatif-guarantees'), 'div', ''); wrap.className = 'table-wrap';
      const table = append(wrap, 'table', ''); const head = append(append(table, 'thead', ''), 'tr', '');
      for (const title of ['Guarantee', 'Health', 'Main', 'Tier']) append(head, 'th', title).scope = 'col';
      const body = append(table, 'tbody', '');
      for (const guarantee of result.not_holding) {
        const row = append(body, 'tr', ''); const cell = append(row, 'td', '');
        const link = append(cell, 'a', ''); link.className = 'id'; link.href = `/entities/${encodeURIComponent(guarantee.id)}`;
        append(link, 'code', guarantee.id);
        append(cell, 'span', `via ${guarantee.chain.slice(1).join(' → ')}`).className = 'chain-line';
        const labelled = label => { const td = append(row, 'td', ''); td.dataset.label = label; return td; };
        labelled('Health').append(window.premiseBadge(guarantee.status));
        labelled('Main').append(window.premiseBadge(guarantee.baseline));
        labelled('Tier').append(document.createTextNode(guarantee.tier));
      }
    }
    for (const decision of result.decisions) {
      const line = append(document.getElementById('whatif-decisions'), 'p', '');
      append(line, 'code', decision.id).className = 'id';
      line.append(document.createTextNode(`: ${decision.reviewers.map(id => result.names[id] || id).join(', ') || 'No active reviewer'}`));
    }
    for (const fix of result.verified_fixes) {
      const card = append(document.getElementById('whatif-fixes'), 'article', ''); card.className = 'fix verified';
      append(card, 'pre', JSON.stringify(fix.changes, null, 2));
      const button = append(card, 'button', ''); button.type = 'button';
      button.append(window.premiseIcon('wrench'), document.createTextNode('Apply fix'));
      button.addEventListener('click', () => fill(fix.changes));
    }
    panel.classList.remove('updating');
    // The impact panel is narrow: draw consequences top-down so every node stays in view.
    const drawing = await mermaid.render(`whatif-${token}`, result.mermaid.replace(/^flowchart LR/, 'flowchart TD'));
    if (token === sequence) document.getElementById('whatif-graph').innerHTML = drawing.svg;
  } catch (error) {
    if (error.name === 'AbortError' || token !== sequence) return;
    panel.classList.remove('updating');
    setVerdict('error', 'ERROR');
    document.getElementById('check-advice').textContent = error.message;
  }
}
for (const raw of new URL(location.href).searchParams.getAll('set')) {
  const index = raw.indexOf('=');
  if (index > 0 && inputs.has(raw.slice(0, index))) inputs.get(raw.slice(0, index)).value = raw.slice(index + 1);
}
schedule();
