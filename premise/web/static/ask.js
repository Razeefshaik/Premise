const form = document.getElementById('ask-form');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('ask-button');
  const box = document.getElementById('answer');
  button.disabled = true;
  box.replaceChildren();
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
    append('h3', result.outcome.replaceAll('_', ' '));
    append('p', result.answer_markdown);
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
    append('p', error.message);
  } finally {
    button.disabled = false;
  }
});
