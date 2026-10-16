import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.esm.min.mjs';
mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral'});
const inputs = new Map([...document.querySelectorAll('.fact-input')].map(el => [el.dataset.fact,el]));
const data = JSON.parse(document.getElementById('whatif-data').textContent);
const verdict = document.getElementById('check-verdict');
let timer, sequence=0, controller;
function append(parent,tag,text) {const el=document.createElement(tag); el.textContent=text; parent.append(el); return el;}
function fill(values,reset=false) {
  if(reset) for(const input of inputs.values()) input.value='';
  for(const [id,value] of Object.entries(values)) if(inputs.has(id)) inputs.get(id).value=JSON.stringify(value);
  schedule();
}
function schedule() {clearTimeout(timer); sequence++; if(controller) controller.abort(); timer=setTimeout(check,400);}
for(const input of inputs.values()) input.addEventListener('input',schedule);
for(const button of document.querySelectorAll('[data-preset]')) button.addEventListener('click',()=>fill(data.presets.find(p=>p.id===button.dataset.preset).values,true));
document.getElementById('reset-proposal').addEventListener('click',()=>fill({},true));
async function check() {
  const token=sequence;
  const changes=[];
  for(const [fact,input] of inputs) {
    const raw=input.value.trim();
    if(!raw) continue;
    let value; try {value=JSON.parse(raw);} catch {value=raw;}
    changes.push(value===null?{fact,delete:true}:{fact,value});
  }
  const url=new URL(location.href); url.searchParams.delete('set');
  for(const change of changes) url.searchParams.append('set',`${change.fact}=${JSON.stringify(change.delete?null:change.value)}`);
  history.replaceState(null,'',url);
  const containers=['check-reasons','whatif-graph','whatif-guarantees','whatif-decisions','whatif-fixes'];
  for(const id of containers) document.getElementById(id).replaceChildren();
  if(!changes.length) {verdict.textContent='Choose a change'; verdict.className='badge'; document.getElementById('check-advice').textContent=''; return;}
  verdict.textContent='Checking'; verdict.className='badge unknown';
  controller=new AbortController();
  try {
    const response=await fetch('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({changes}),signal:controller.signal});
    const result=await response.json();
    if(token!==sequence) return;
    if(!response.ok) throw new Error(response.status===422?'This proposal is invalid or contains an untracked fact.':'The graph is unavailable.');
    verdict.textContent=result.verdict; verdict.className=`badge ${result.verdict.toLowerCase()}`;
    document.getElementById('check-advice').textContent=result.advice;
    for(const reason of result.reasons) append(document.getElementById('check-reasons'),'li',reason.detail);
    if(result.not_holding.length) {
      const wrap=append(document.getElementById('whatif-guarantees'),'div',''); wrap.className='table-wrap';
      const table=append(wrap,'table',''); const head=append(append(table,'thead',''),'tr','');
      for(const title of ['Guarantee','Health','Main','Tier','Chain']) append(head,'th',title);
      const body=append(table,'tbody','');
      for(const guarantee of result.not_holding) {
        const row=append(body,'tr',''); const cell=append(row,'td','');
        const link=append(cell,'a',guarantee.id); link.href=`/entities/${encodeURIComponent(guarantee.id)}`;
        for(const text of [guarantee.status,guarantee.baseline,guarantee.tier,guarantee.chain.join(' → ')]) append(row,'td',text);
      }
    }
    for(const decision of result.decisions) append(document.getElementById('whatif-decisions'),'p',`${decision.id}: ${decision.reviewers.map(id=>result.names[id]||id).join(', ')||'No active reviewer'}`);
    for(const fix of result.verified_fixes) {
      const card=append(document.getElementById('whatif-fixes'),'article',''); card.className='fix verified';
      append(card,'pre',JSON.stringify(fix.changes,null,2));
      const button=append(card,'button','Apply fix'); button.type='button'; button.addEventListener('click',()=>fill(fix.changes));
    }
    const drawing=await mermaid.render(`whatif-${token}`,result.mermaid);
    if(token===sequence) document.getElementById('whatif-graph').innerHTML=drawing.svg;
  } catch(error) {
    if(error.name==='AbortError'||token!==sequence) return;
    verdict.textContent='ERROR'; verdict.className='badge error';
    document.getElementById('check-advice').textContent=error.message;
  }
}
for(const raw of new URL(location.href).searchParams.getAll('set')) {
  const index=raw.indexOf('=');
  if(index>0 && inputs.has(raw.slice(0,index))) inputs.get(raw.slice(0,index)).value=raw.slice(index+1);
}
schedule();
