// "Fire a change": posts a saved scenario to the read-only /api/check, reports the verdict in the HUD,
// lights the affected guarantee cards, and broadcasts the result so the 3D brain and the 2D plate react together.
(() => {
  const source = document.getElementById('plate-data');
  const out = document.getElementById('fire-result');
  if (!source || !out) return;
  const data = JSON.parse(source.textContent);
  const idle = out.innerHTML;
  const buttons = [...document.querySelectorAll('[data-fire]')];
  let active = null;

  const emit = detail => document.dispatchEvent(new CustomEvent('premise:fire', {detail}));
  function summary(check) {
    const broken = check.not_holding.filter(g => g.status === 'broken').length;
    const unknown = check.not_holding.length - broken;
    if (broken) return `${broken} guarantee${broken === 1 ? '' : 's'} stop holding${unknown ? `, ${unknown} become unknown` : ''}.`;
    if (unknown) return `${unknown} guarantee${unknown === 1 ? '' : 's'} can no longer be shown to hold.`;
    return 'Every affected guarantee still holds.';
  }
  function markCards(check) {
    const hit = new Map((check ? check.not_holding : []).map(g => [g.id, g.status]));
    document.querySelectorAll('.g-card[data-guarantee]').forEach(card => {
      card.classList.remove('is-fired-broken', 'is-fired-unknown');
      const status = hit.get(card.dataset.guarantee);
      if (status) card.classList.add(status === 'broken' ? 'is-fired-broken' : 'is-fired-unknown');
    });
  }
  function report(check, changes) {
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
    out.replaceChildren(wrap);
  }
  function reset() {
    active = null;
    buttons.forEach(b => b.setAttribute('aria-pressed', 'false'));
    out.innerHTML = idle;
    markCards(null);
    emit(null);
  }
  async function fire(button) {
    const preset = data.presets.find(p => p.id === button.dataset.fire);
    if (active === preset.id) return reset();
    active = preset.id;
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    const changes = Object.entries(preset.values).map(([fact, value]) => ({fact, value}));
    out.replaceChildren(Object.assign(document.createElement('p'), {textContent: 'Tracing the change through the graph…'}));
    try {
      const response = await fetch('/api/check', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({changes})});
      const check = await response.json();
      if (active !== preset.id) return;
      if (!response.ok) throw new Error('The graph could not check this change.');
      report(check, changes);
      markCards(check);
      emit({check, changes});
    } catch (error) {
      out.replaceChildren(Object.assign(document.createElement('p'), {textContent: error.message}));
    }
  }
  buttons.forEach(button => {
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => fire(button));
  });
})();
