// Fig. 1: the company's decision network drawn as a Cajal plate, from the live graph.
// Facts feed assumptions; assumptions hold up guarantees. Firing a change uses the read-only /api/check.
(() => {
  const stage = document.getElementById('plate');
  const source = document.getElementById('plate-data');
  if (!stage || !source) return;
  const data = JSON.parse(source.textContent);
  const NS = 'http://www.w3.org/2000/svg';
  // Automated captures get the settled plate, as with reduced motion.
  const reduce = navigator.webdriver || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const node = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.append(n);
    return n;
  };
  const hash = text => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
  const wobble = (text, span) => ((hash(text) % 1000) / 1000 - 0.5) * span;

  // Model ------------------------------------------------------------------
  const facts = new Map(data.facts.map(f => [f.id, f]));
  const assumptions = new Map(data.assumptions.map(a => [a.id, a]));
  const guarantees = new Map(data.guarantees.map(g => [g.id, g]));
  for (const a of assumptions.values()) for (const f of [a.lhs_fact, a.rhs_fact]) if (f && !facts.has(f)) facts.set(f, {id: f});
  const factEdges = [], guaranteeEdges = [];
  for (const a of assumptions.values()) for (const f of new Set([a.lhs_fact, a.rhs_fact])) if (f) factEdges.push([f, a.id]);
  for (const g of guarantees.values()) for (const a of g.prerequisites) if (assumptions.has(a)) guaranteeEdges.push([a, g.id]);
  const feeds = id => factEdges.filter(([f]) => f === id).map(([, a]) => a);
  const fedBy = id => factEdges.filter(([, a]) => a === id).map(([f]) => f);
  const holds = id => guaranteeEdges.filter(([a]) => a === id).map(([, g]) => g);

  // Order each stratum by the mean position of its neighbours, so paths cross less.
  const mean = values => values.length ? values.reduce((s, v) => s + v, 0) / values.length : Infinity;
  let gOrder = [...guarantees.keys()];
  let aOrder = [...assumptions.keys()], fOrder = [...facts.keys()];
  for (let pass = 0; pass < 3; pass++) {
    const gi = new Map(gOrder.map((id, i) => [id, i]));
    aOrder.sort((x, y) => mean(holds(x).map(g => gi.get(g))) - mean(holds(y).map(g => gi.get(g))));
    const ai = new Map(aOrder.map((id, i) => [id, i]));
    fOrder.sort((x, y) => mean(feeds(x).map(a => ai.get(a))) - mean(feeds(y).map(a => ai.get(a))));
    gOrder.sort((x, y) => mean(guarantees.get(x).prerequisites.map(a => ai.get(a) ?? 0)) - mean(guarantees.get(y).prerequisites.map(a => ai.get(a) ?? 0)));
  }

  // Drawing ----------------------------------------------------------------
  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.setAttribute('role', 'tooltip');
  let svg, cells = new Map(), edges = [], pos = new Map(), lastResult = null, drawnOnce = false, width = 0;

  function draw() {
    width = stage.clientWidth;
    const height = stage.clientHeight;
    const narrow = width < 600;
    const top = 58, bottom = 26;
    // Geist Mono at 11.5px sets about 6.95px per character; leave room for the longest real label.
    const longest = ids => Math.max(...ids.map(id => id.length)) * 6.95;
    const xF = narrow ? 22 : Math.min(width * 0.36, longest(fOrder) + 30);
    const xG = narrow ? width - 168 : width - Math.min(width * 0.3, longest(gOrder) + 36);
    const xA = narrow ? width * 0.44 : (xF + xG) / 2;
    const column = (order, x) => order.forEach((id, i) => pos.set(id, {x: x + wobble(id, narrow ? 6 : 14), y: top + (i + 0.5) * ((height - top - bottom) / order.length)}));
    pos = new Map();
    column(fOrder, xF); column(aOrder, xA); column(gOrder, xG);

    svg?.remove();
    svg = node('svg', {class: 'neuro', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `Decision network: ${facts.size} facts, ${assumptions.size} assumptions, ${guarantees.size} guarantees.`});
    for (const [label, x, anchor] of [['Facts', narrow ? 14 : xF, narrow ? 'start' : 'end'], ['Assumptions', xA, 'middle'], ['Guarantees', narrow ? width - 14 : xG + 12, narrow ? 'end' : 'start']]) {
      node('text', {class: 'stratum', x, y: 28, 'text-anchor': anchor}, svg).textContent = label;
    }
    const edgeLayer = node('g', {}, svg);
    const cellLayer = node('g', {}, svg);
    edges = [];
    const link = (from, to, kind) => {
      const a = pos.get(from), b = pos.get(to);
      const dx = (b.x - a.x) * (0.42 + wobble(from + to, 0.18));
      const sag = wobble(to + from, 26);
      const path = node('path', {class: 'edge', d: `M${a.x},${a.y} C${a.x + dx},${a.y + sag} ${b.x - dx},${b.y - sag} ${b.x},${b.y}`}, edgeLayer);
      edges.push({from, to, kind, path});
    };
    factEdges.forEach(([f, a]) => link(f, a, 'fa'));
    guaranteeEdges.forEach(([a, g]) => link(a, g, 'ag'));

    cells = new Map();
    const twig = (group, x, y, angle, length, seed) => {
      const ex = x + Math.cos(angle) * length, ey = y + Math.sin(angle) * length;
      const bend = wobble(seed, length * 0.5);
      node('path', {class: 'twig', d: `M${x},${y} Q${(x + ex) / 2 + bend},${(y + ey) / 2 - bend} ${ex},${ey}`}, group);
    };
    for (const id of fOrder) {
      const {x, y} = pos.get(id), fact = facts.get(id);
      const g = node('g', {class: 'cell fact', 'data-id': id}, cellLayer);
      twig(g, x, y, Math.PI + wobble(id, 0.6), 12, id);
      node('circle', {class: 'ring', cx: x, cy: y, r: 6}, g);
      node('circle', {class: 'soma', cx: x, cy: y, r: 3.2, ...(fact.controlled_by === 'external' ? {style: 'fill: var(--ground); stroke: var(--ink); stroke-width: 1.3'} : {})}, g);
      if (!narrow) node('text', {class: 'label', x: x - 14, y: y + 4, 'text-anchor': 'end'}, g).textContent = id;
      cells.set(id, g);
    }
    for (const id of aOrder) {
      const {x, y} = pos.get(id), a = assumptions.get(id);
      const g = node('g', {class: 'cell assumption', 'data-id': id}, cellLayer);
      for (let k = 0; k < 3; k++) twig(g, x, y, -Math.PI / 2 + (k - 1) * 1.1 + wobble(id + k, 0.5), 9 + (hash(id + k) % 6), id + k);
      node('circle', {class: 'ring', cx: x, cy: y, r: 8}, g);
      node('circle', {class: `soma ${a.state}`, cx: x, cy: y, r: 5}, g);
      if (!narrow) node('text', {class: 'label', x, y: y - 13, 'text-anchor': 'middle', style: 'font-size: 10.5px; fill: var(--ink-3)'}, g).textContent = id;
      cells.set(id, g);
    }
    for (const id of gOrder) {
      const {x, y} = pos.get(id), item = guarantees.get(id);
      const g = node('g', {class: 'cell guarantee', 'data-id': id, tabindex: '0', role: 'link', 'aria-label': `${id}, ${item.status}: ${item.statement}`}, cellLayer);
      twig(g, x, y - 8, -Math.PI / 2 + wobble(id, 0.4), 16, id);
      twig(g, x, y - 16, -Math.PI / 2 - 0.7, 7, id + 'l');
      twig(g, x, y - 18, -Math.PI / 2 + 0.7, 7, id + 'r');
      node('circle', {class: 'ring', cx: x, cy: y, r: 10}, g);
      node('path', {class: `soma ${item.status}`, d: `M${x},${y - 8.5} L${x + 7},${y + 5} L${x - 7},${y + 5} Z`}, g);
      node('text', {class: 'label', x: x + 14, y: y + 4}, g).textContent = id;
      cells.set(id, g);
    }
    node('circle', {class: 'pulse', r: 2.6, cx: -10, cy: -10}, svg);
    stage.append(svg);
    stage.append(tip);
    stage.classList.add('drawn');
    bind();
    if (!drawnOnce && !reduce) develop();
    drawnOnce = true;
    if (lastResult) apply(lastResult);
  }

  // The plate develops like a stained slide: paths ink in from the facts upward.
  function develop() {
    edges.forEach((edge, i) => {
      const length = edge.path.getTotalLength();
      edge.path.animate([{strokeDasharray: length, strokeDashoffset: length}, {strokeDasharray: length, strokeDashoffset: 0}],
        {duration: 1100, delay: (edge.kind === 'fa' ? 120 : 620) + (i % 14) * 28, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'backwards'});
    });
    [...cells.values()].forEach((cell, i) => {
      const kind = cell.classList.contains('fact') ? 0 : cell.classList.contains('assumption') ? 1 : 2;
      cell.animate([{opacity: 0}, {opacity: 1}], {duration: 600, delay: 80 + kind * 480 + (i % 12) * 26, easing: 'ease-out', fill: 'backwards'});
    });
  }

  // Tracing ----------------------------------------------------------------
  function connected(id) {
    const set = new Set([id]);
    if (facts.has(id)) feeds(id).forEach(a => { set.add(a); holds(a).forEach(g => set.add(g)); });
    if (assumptions.has(id)) { fedBy(id).forEach(f => set.add(f)); holds(id).forEach(g => set.add(g)); }
    if (guarantees.has(id)) guarantees.get(id).prerequisites.forEach(a => { set.add(a); fedBy(a).forEach(f => set.add(f)); });
    return set;
  }
  function describe(id) {
    if (guarantees.has(id)) { const g = guarantees.get(id); return `${g.statement}. Currently ${g.status}; ${g.prerequisites.length} prerequisites.`; }
    if (assumptions.has(id)) { const a = assumptions.get(id); return `${a.text}. Currently ${a.state}.`; }
    const f = facts.get(id);
    return f.value === undefined ? 'Fact referenced by an assumption.' : `Main value ${JSON.stringify(f.value)}, controlled ${f.controlled_by || 'internally'}.`;
  }
  function trace(id) {
    const set = connected(id);
    svg.classList.add('tracing');
    for (const [key, cell] of cells) cell.classList.toggle('on', set.has(key));
    for (const edge of edges) edge.path.classList.toggle('on', set.has(edge.from) && set.has(edge.to));
    const {x, y} = pos.get(id);
    tip.replaceChildren();
    const strong = document.createElement('strong');
    strong.textContent = id;
    tip.append(strong, document.createTextNode(describe(id)));
    const left = Math.min(Math.max(8, x - 140), width - 288);
    tip.style.left = `${left}px`;
    tip.style.top = `${y + 18}px`;
    if (y > stage.clientHeight * 0.66) tip.style.top = `${y - 18 - 96}px`;
    tip.classList.add('show');
  }
  function untrace() {
    svg.classList.remove('tracing');
    for (const cell of cells.values()) cell.classList.remove('on');
    for (const edge of edges) edge.path.classList.remove('on');
    tip.classList.remove('show');
  }
  function bind() {
    for (const [id, cell] of cells) {
      cell.addEventListener('pointerenter', () => trace(id));
      cell.addEventListener('pointerleave', untrace);
      cell.addEventListener('focus', () => trace(id));
      cell.addEventListener('blur', untrace);
      cell.addEventListener('click', () => { location.href = `/entities/${encodeURIComponent(id)}`; });
      cell.addEventListener('keydown', event => { if (event.key === 'Enter') location.href = `/entities/${encodeURIComponent(id)}`; });
    }
  }

  // Ambient signal: one impulse at a time travels a real fact → assumption → guarantee path.
  let visible = true, busy = false;
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }).observe(stage);
  function impulse() {
    if (reduce || busy || !visible || document.hidden || !svg || svg.classList.contains('tracing') || svg.classList.contains('firing')) return;
    const routes = factEdges.flatMap(([f, a]) => holds(a).map(g => [f, a, g]));
    if (!routes.length) return;
    const [f, a, g] = routes[Math.floor(Math.random() * routes.length)];
    const legs = [edges.find(e => e.from === f && e.to === a), edges.find(e => e.from === a && e.to === g)].filter(Boolean).map(e => e.path);
    const dot = svg.querySelector('.pulse');
    const lengths = legs.map(p => p.getTotalLength());
    const total = lengths.reduce((s, l) => s + l, 0);
    const start = performance.now(), duration = 1700;
    busy = true;
    const step = now => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 2.2);
      let distance = eased * total, leg = 0;
      while (leg < legs.length - 1 && distance > lengths[leg]) { distance -= lengths[leg]; leg++; }
      const point = legs[leg].getPointAtLength(Math.min(distance, lengths[leg]));
      dot.setAttribute('cx', point.x); dot.setAttribute('cy', point.y);
      dot.style.opacity = String(Math.sin(Math.PI * t) * 0.95);
      if (t < 1) requestAnimationFrame(step);
      else { busy = false; cells.get(g)?.querySelector('.ring')?.animate([{opacity: 0.7, transform: 'scale(1)'}, {opacity: 0, transform: 'scale(2.4)'}], {duration: 900, easing: 'cubic-bezier(0.22, 1, 0.36, 1)'}); }
    };
    requestAnimationFrame(step);
  }
  setInterval(impulse, 2600);

  // Firing a change ---------------------------------------------------------
  const result = document.getElementById('fire-result');
  let active = null;
  function clearFire() {
    svg.classList.remove('firing');
    for (const cell of cells.values()) cell.classList.remove('fired', 'touched', 'checked');
    for (const edge of edges) edge.path.classList.remove('fired', 'checked');
    for (const [id, g] of guarantees) cells.get(id).querySelector('.soma').setAttribute('class', `soma ${g.status}`);
  }
  function apply(check) {
    clearFire();
    svg.classList.add('firing');
    const touched = new Set(check.changed.map(c => c.fact));
    const fired = new Set();
    for (const g of check.not_holding) {
      for (const id of [g.id, ...g.chain]) fired.add(id);
      cells.get(g.id)?.querySelector('.soma').setAttribute('class', `soma ${g.status}`);
    }
    const reached = new Set([...touched].flatMap(f => feeds(f)));
    for (const id of touched) cells.get(id)?.classList.add('touched');
    for (const id of reached) cells.get(id)?.classList.add(fired.has(id) ? 'fired' : 'touched');
    for (const id of fired) cells.get(id)?.classList.add('fired');
    for (const edge of edges) {
      const isFired = (edge.kind === 'fa' && touched.has(edge.from) && fired.has(edge.to)) || (edge.kind === 'ag' && fired.has(edge.from) && fired.has(edge.to));
      const isChecked = !isFired && ((edge.kind === 'fa' && touched.has(edge.from)) || (edge.kind === 'ag' && reached.has(edge.from)));
      edge.path.classList.toggle('fired', isFired);
      edge.path.classList.toggle('checked', isChecked);
      if (isChecked && edge.kind === 'ag') cells.get(edge.to)?.classList.add('checked');
    }
  }
  function summary(check) {
    const broken = check.not_holding.filter(g => g.status === 'broken').length;
    const unknown = check.not_holding.length - broken;
    if (broken) return `${broken} guarantee${broken === 1 ? '' : 's'} stop holding${unknown ? `, ${unknown} become unknown` : ''}.`;
    if (unknown) return `${unknown} guarantee${unknown === 1 ? '' : 's'} can no longer be shown to hold.`;
    return 'Every affected guarantee still holds.';
  }
  function report(check, changes) {
    result.replaceChildren();
    const wrap = document.createElement('div');
    wrap.className = 'settle';
    const line = document.createElement('div');
    line.className = 'verdict-line';
    line.append(window.premiseBadge(check.verdict));
    const text = document.createElement('span');
    text.textContent = summary(check);
    line.append(text);
    const advice = document.createElement('p');
    advice.textContent = check.advice;
    const url = new URL('/what-if', location.origin);
    for (const c of changes) url.searchParams.append('set', `${c.fact}=${JSON.stringify(c.value)}`);
    const link = document.createElement('a');
    link.href = url.pathname + url.search;
    link.append(document.createTextNode('Trace it in What if'), window.premiseIcon('arrow-up-right'));
    wrap.append(line, advice, link);
    result.append(wrap);
  }
  async function fire(button) {
    const preset = data.presets.find(p => p.id === button.dataset.fire);
    const buttons = document.querySelectorAll('[data-fire]');
    if (active === preset.id) {
      active = null; lastResult = null;
      buttons.forEach(b => b.setAttribute('aria-pressed', 'false'));
      clearFire(); result.replaceChildren();
      return;
    }
    active = preset.id;
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    const changes = Object.entries(preset.values).map(([fact, value]) => ({fact, value}));
    result.textContent = 'Tracing the change through the graph…';
    try {
      const response = await fetch('/api/check', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({changes})});
      const check = await response.json();
      if (active !== preset.id) return;
      if (!response.ok) throw new Error('The graph could not check this change.');
      lastResult = check;
      apply(check);
      report(check, changes);
    } catch (error) {
      result.textContent = error.message;
    }
  }
  document.querySelectorAll('[data-fire]').forEach(button => {
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => fire(button));
  });

  draw();
  let resizeTimer;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (Math.abs(stage.clientWidth - width) > 2) draw(); }, 160);
  }).observe(stage);
})();
