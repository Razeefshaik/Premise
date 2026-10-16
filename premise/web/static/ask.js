const form = document.getElementById('ask-form');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('ask-button');
  const box = document.getElementById('answer');
  button.disabled = true;
  box.replaceChildren();
  box.classList.add('thinking');
  function append(tag, text) {
    const el = document.createElement(tag);
    el.textContent = text;
    box.append(el);
    return el;
  }
  try {
    const response = await fetch('/api/ask', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: document.getElementById('question').value})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The graph could not answer this question.');
    box.classList.remove('thinking');
    append('h3', result.outcome.replaceAll('_', ' '));
    // The answer arrives word by word; automation and reduced motion get it whole.
    const answer = append('p', '');
    if (navigator.webdriver || matchMedia('(prefers-reduced-motion: reduce)').matches) answer.textContent = result.answer_markdown;
    else result.answer_markdown.split(/(\s+)/).forEach((word, i) => {
      if (!word.trim()) { answer.append(word); return; }
      const span = document.createElement('span');
      span.className = 'reveal-word';
      span.style.animationDelay = `${Math.min(i, 160) * 9}ms`;
      span.textContent = word;
      answer.append(span);
    });
    append('small', `Answer mode: ${result.mode} · provider: ${result.provider || result.mode}`);
    if (result.provider_error === 'AnswerVerificationFailed') {
      append('p', 'The model summary did not pass verification; showing graph results.');
    } else if (result.provider_error) {
      append('p', `Model provider unavailable (${result.provider_error}); showing graph results.`);
    }
    append('p', result.verification);
    for (const call of result.tool_results) {
      const details = append('details', '');
      const summary = document.createElement('summary');
      const pre = document.createElement('pre');
      summary.textContent = call.tool;
      pre.textContent = JSON.stringify(call.rows, null, 2);
      details.append(summary, pre);
    }
    const list = append('ul', '');
    for (const source of result.sources) {
      const li = document.createElement('li');
      if (!source.url) {
        li.textContent = `${source.path}:${source.line} (local checkout)`;
      } else if (source.url.startsWith('https://github.com/')) {
        const a = document.createElement('a');
        a.href = source.url.split('#')[0] + '#L' + source.line;
        a.textContent = `${source.path}:${source.line}`;
        li.append(a);
      } else continue;
      list.append(li);
    }
  } catch (error) {
    box.classList.remove('thinking');
    append('p', error.message);
  } finally {
    box.classList.remove('thinking');
    button.disabled = false;
  }
});
