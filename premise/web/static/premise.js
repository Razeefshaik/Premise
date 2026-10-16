// Shared page behaviour: section entrances, counters, card spotlights, and the icon/badge helpers.
(() => {
  const still = navigator.webdriver || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const targets = [...document.querySelectorAll('.reveal')];
  const showAll = () => targets.forEach(el => el.classList.add('in'));

  // Cards light up where the pointer is
  document.addEventListener('pointermove', event => {
    const card = event.target.closest?.('.card');
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty('--x', `${event.clientX - r.left}px`);
    card.style.setProperty('--y', `${event.clientY - r.top}px`);
  }, {passive: true});

  // Automation, reduced motion and old browsers get the settled page at once.
  if (still || !('IntersectionObserver' in window)) {
    document.documentElement.classList.remove('js');
    showAll();
    return;
  }

  // Numbers count up once, from zero to the graph's value
  document.querySelectorAll('[data-count]').forEach(el => {
    const end = Number(el.dataset.count);
    if (!Number.isFinite(end) || end === 0) return;
    const start = performance.now(), duration = 900 + end * 25;
    const step = now => {
      const t = Math.min(1, (now - start) / duration);
      el.textContent = String(Math.round(end * (1 - Math.pow(1 - t, 3))));
      if (t < 1) requestAnimationFrame(step);
    };
    el.textContent = '0';
    requestAnimationFrame(step);
  });

  // Siblings arriving together stagger: heading, text, then the cards row by row
  const groups = new Map();
  for (const el of targets) {
    const parent = el.parentElement;
    const index = groups.get(parent) || 0;
    groups.set(parent, index + 1);
    el.style.setProperty('--d', `${Math.min(index, 8) * 60}ms`);
  }
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('in');
      observer.unobserve(entry.target);
    }
  }, {rootMargin: '0px 0px -6% 0px', threshold: 0.06});
  targets.forEach(el => observer.observe(el));
})();

window.premiseIcon = name => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'i');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `/static/icons.svg#${name}`);
  svg.append(use);
  return svg;
};

window.premiseGlyph = value => {
  const v = String(value || '').toLowerCase();
  if (['holds', 'holding', 'verified', 'clear_within_scope'].includes(v)) return 'check';
  if (['broken', 'violated', 'blocked', 'rejected', 'error'].includes(v)) return 'octagon-x';
  if (['unknown', 'unverified', 'unevaluable', 'needs_review', 'partial', 'checking'].includes(v)) return 'circle-help';
  return null;
};

window.premiseBadge = (value, text = value) => {
  const span = document.createElement('span');
  span.className = `badge ${String(value).toLowerCase()}`;
  const glyph = window.premiseGlyph(value);
  if (glyph) span.append(window.premiseIcon(glyph));
  span.append(document.createTextNode(text));
  return span;
};
