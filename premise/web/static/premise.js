// Shared page behaviour: section entrances and the icon helper used by the page scripts.
(() => {
  const targets = [...document.querySelectorAll('.reveal, .reveal-plate')];
  const showAll = () => targets.forEach(el => el.classList.add('in'));
  // Automation and full-page captures never scroll, so they get the finished page at once.
  if (navigator.webdriver || !('IntersectionObserver' in window) || matchMedia('(prefers-reduced-motion: reduce)').matches) {
    // Settle the page outright: no hidden states, no transitions in flight, every picture loaded.
    document.documentElement.classList.remove('js');
    if (navigator.webdriver) document.querySelectorAll('img[loading="lazy"]').forEach(img => { img.loading = 'eager'; });
    showAll();
    return;
  }
  // Stagger siblings that arrive together: heading, then text, then the table or plate.
  const groups = new Map();
  for (const el of targets) {
    const parent = el.closest('section, .pair, .board, .lower-grid, ul, ol') || document.body;
    const index = groups.get(parent) || 0;
    groups.set(parent, index + 1);
    el.style.setProperty('--d', `${Math.min(index, 6) * 70}ms`);
  }
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('in');
      observer.unobserve(entry.target);
    }
  }, {rootMargin: '0px 0px -8% 0px', threshold: 0.08});
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
