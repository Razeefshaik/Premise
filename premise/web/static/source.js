export function requestKey(method,path,params={},body=null){return JSON.stringify([method,path,Object.entries(params).filter(([,v])=>v!==null&&v!=='').sort(([a],[b])=>a.localeCompare(b)),body]);}
export class LiveSource{async request(path,params={},body=null){const url=new URL(path,location.origin);for(const[k,v]of Object.entries(params))if(v!==null&&v!=='')url.searchParams.set(k,v);const r=await fetch(url,body===null?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(data.error||data.detail||`Request failed (${r.status})`);return data;}}
export class ReplaySource{constructor(base='./data/'){this.base=base;this.index=null;}async request(path,params={},body=null){this.index||=await fetch(this.base+'index.json').then(r=>{if(!r.ok)throw new Error('Replay index unavailable');return r.json();});const file=this.index.requests[requestKey(body===null?'GET':'POST',path,params,body)];if(!file)throw new Error('This view was not recorded. Choose a recorded preset or run locally.');const r=await fetch(this.base+file);if(!r.ok)throw new Error('Recorded data unavailable');return r.json();}}
export const replay=document.documentElement.dataset.source==='replay';
export const source=replay?new ReplaySource():new LiveSource();
export function el(parent,tag,text='',cls=''){const n=document.createElement(tag);n.textContent=text;n.className=cls;parent.append(n);return n;}

// Cypher inspector: every query the page ran (or the replay recorded), highlighted, timed and copyable.
const KEYWORDS = new Set(('MATCH OPTIONAL WHERE RETURN WITH UNWIND ORDER BY ASC DESC LIMIT SKIP AS AND OR XOR NOT IN IS NULL CASE WHEN THEN ELSE END '
  + 'DISTINCT CREATE MERGE SET DELETE DETACH REMOVE CALL YIELD EXISTS TRUE FALSE STARTS ENDS CONTAINS ON UNION ALL ANY NONE SINGLE FOREACH').split(' '));
const CYPHER = /(\/\/[^\n]*)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(\$[A-Za-z_]\w*)|(:\s*[A-Z][A-Z0-9_]+\b)|(:\s*[A-Z][A-Za-z0-9_]*)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][\w.]*)(?=\s*\()|([A-Za-z_]\w*)/g;
function spans(pre, text, pattern, classify) {
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) pre.append(document.createTextNode(text.slice(last, match.index)));
    const cls = classify(match);
    if (cls) { const span = document.createElement('span'); span.className = cls; span.textContent = match[0]; pre.append(span); }
    else pre.append(document.createTextNode(match[0]));
    last = match.index + match[0].length;
  }
  if (last < text.length) pre.append(document.createTextNode(text.slice(last)));
}
export function highlightCypher(pre, text) {
  spans(pre, text, CYPHER, m => m[1] ? 'tk-com' : m[2] ? 'tk-str' : m[3] ? 'tk-param' : m[4] ? 'tk-rel' : m[5] ? 'tk-label' : m[6] ? 'tk-num'
    : m[7] ? 'tk-fn' : m[8] && KEYWORDS.has(m[8].toUpperCase()) ? 'tk-kw' : '');
}
const JSON_TOKENS = /("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
function highlightJson(pre, text) { spans(pre, text, JSON_TOKENS, m => m[1] ? (m[2] ? 'tk-key' : 'tk-str') : m[3] ? 'tk-kw' : m[4] ? 'tk-num' : ''); }

function icon(name) { return window.premiseIcon ? window.premiseIcon(name) : document.createTextNode(''); }
export function showQueries(data) {
  const root = document.getElementById('cypher-queries');
  if (!root) return;
  root.replaceChildren();
  const queries = data.queries || [];
  const slowest = Math.max(0.001, ...queries.map(q => q.ms));
  for (const q of queries) {
    const s = el(root, 'section', '', 'cq');
    const head = el(s, 'div', '', 'cq-head');
    el(head, 'h3', q.name);
    const meta = el(head, 'span', '', 'cq-meta');
    el(meta, 'span', `${q.ms.toFixed(2)} ms`);
    el(meta, 'span', `${q.rows} row${q.rows === 1 ? '' : 's'}`);
    const bar = el(head, 'span', '', 'cq-bar');
    bar.setAttribute('aria-hidden', 'true');
    el(bar, 'span').style.width = `${Math.max(2, q.ms / slowest * 100)}%`;
    const copy = el(head, 'button', '', 'chip quiet-chip copy');
    copy.type = 'button';
    const label = () => copy.replaceChildren(icon('copy'), document.createTextNode('Copy Cypher'));
    label();
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(q.cypher); copy.replaceChildren(icon('check'), document.createTextNode('Copied')); copy.classList.add('copied'); }
      catch { copy.textContent = 'Select the query to copy'; }
      setTimeout(() => { label(); copy.classList.remove('copied'); }, 1600);
    };
    const pre = el(s, 'pre', '', 'cq-code');
    highlightCypher(pre, q.cypher);
    if (q.params && Object.keys(q.params).length) {
      const toggle = el(s, 'button', `Parameters (${Object.keys(q.params).length})`, 'cq-params');
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', 'false');
      const params = el(s, 'pre', '', 'cq-param-code');
      params.hidden = true;
      highlightJson(params, JSON.stringify(q.params, null, 2));
      toggle.onclick = () => { params.hidden = !params.hidden; toggle.setAttribute('aria-expanded', String(!params.hidden)); };
    }
  }
  const count = document.getElementById('cypher-count');
  if (count) count.textContent = `${queries.length} quer${queries.length === 1 ? 'y' : 'ies'} · ${queries.reduce((n, q) => n + q.ms, 0).toFixed(2)} ms · from FalkorDB`;
}
