import {el,showQueries,source,replay} from './source.js';
const explorer=window.premiseExplorer,cy=explorer.cy,root=document.getElementById('explorer-whatif');
const values=new Map();let timer,sequence=0;
const controls=new Map(),factsData=await source.request('/api/graph/facts');
el(root,'h2','What if');el(root,'p','Hypothetical. Nothing is stored or posted.','v3-hypothetical');
if(replay)el(root,'p','Recorded presets and verified repairs. Run locally to try arbitrary values.');
const presets=el(root,'div','','v3-tabs');for(const preset of factsData.presets){const button=el(presets,'button',preset.id);button.dataset.explorerPreset=preset.id;button.onclick=()=>{values.clear();for(const [key,value]of Object.entries(preset.values))values.set(key,value);render();schedule();};}
const verdict=document.getElementById('explorer-verdict');
const advice=el(root,'p'),fixes=el(root,'div');const inputs=el(root,'div');
function render(){inputs.replaceChildren();controls.clear();const visible=new Set(cy.nodes().map(n=>n.id()));for(const fact of factsData.facts){if(!visible.has(fact.id)&&!fact.assumptions.some(a=>visible.has(a))&&!values.has(fact.id))continue;const group=el(inputs,'div','','v3-fact');const label=el(group,'label',fact.id);const id='slider-'+fact.id.replaceAll('.','-');label.htmlFor=id;const numeric=typeof fact.value==='number';if(!numeric){el(group,'p',`Main: ${JSON.stringify(fact.value)}. Use a recorded preset for non-numeric changes.`);continue;}const unit=fact.id.endsWith('_ms')?100:fact.id.includes('_minutes')?5:fact.id.includes('_seconds')?10:1;
 const slider=el(group,'input');slider.type='range';slider.id=id;slider.min=0;slider.max=Math.max(fact.value*4,unit*4,typeof values.get(fact.id)==='number'?values.get(fact.id):0);slider.step=unit;slider.value=values.has(fact.id)?values.get(fact.id):fact.value;
 const number=el(group,'input');number.type='number';number.step='any';number.value=slider.value;number.setAttribute('aria-label','Proposed '+fact.id);const reset=el(group,'button','Reset');reset.dataset.factReset='true';reset.onclick=()=>{values.delete(fact.id);render();schedule();};
 const update=value=>{if(!Number.isFinite(value)||value<0){advice.textContent='Enter a finite non-negative number.';return;}values.set(fact.id,value);slider.value=value;number.value=value;schedule();};slider.oninput=()=>update(Number(slider.value));number.oninput=()=>update(Number(number.value));if(replay){slider.disabled=true;number.disabled=true;reset.disabled=true;}controls.set(fact.id,{slider,number});}}
function schedule(){clearTimeout(timer);sequence++;explorer.clearHypothetical();verdict.textContent='Hypothetical · checking…';fixes.replaceChildren();timer=setTimeout(check,300);}
const delay=()=>new Promise(resolve=>setTimeout(resolve,matchMedia('(prefers-reduced-motion: reduce)').matches?0:250));
async function check(){if(new URL(location.href).searchParams.has('at')){verdict.textContent='Date view · choose Live today to try fact changes';return;}const token=sequence;const url=new URL(location.href);url.searchParams.delete('set');for(const [fact,value]of [...values].sort())url.searchParams.append('set',fact+'='+JSON.stringify(value));history.replaceState(null,'',url);fixes.replaceChildren();if(!values.size){verdict.textContent='Baseline · choose What if to test a change';advice.textContent='';await explorer.load();return;}verdict.textContent='Hypothetical · checking…';
 try{const changes=[...values].sort().map(([fact,value])=>value===null?{fact,delete:true}:{fact,value});const data=await source.request('/api/check',{}, {changes});if(token!==sequence)return;showQueries(data);advice.textContent=data.advice;
 const ids=[...new Set([...data.touched,...data.not_holding.map(g=>g.id),...data.decisions.map(d=>d.id)])];await explorer.addNodes(ids,()=>token===sequence);if(token!==sequence)return;
 explorer.clearHypothetical();for(const a of data.assumptions)explorer.setHealth(a.id,a.state);
 for(const id of data.touched){cy.getElementById(id).addClass('touched');}await delay();
 for(const g of [...data.guarantees].sort((a,b)=>a.chain.length-b.chain.length)){if(token!==sequence)return;explorer.setHealth(g.id,g.status,g.chain);await delay();}
 if(token!==sequence)return;for(const d of data.decisions)cy.getElementById(d.id).addClass('affected');cy.fit(undefined,35);verdict.textContent='Hypothetical · '+(data.verdict==='CLEAR_WITHIN_SCOPE'?'CLEAR':data.verdict);
 for(const fix of data.verified_fixes){const button=el(fixes,'button','Apply verified fix');button.onclick=()=>{for(const [fact,value]of Object.entries(fix.changes))values.set(fact,value);render();schedule();};}document.dispatchEvent(new CustomEvent('premise:check',{detail:data}));
 }catch(error){if(token===sequence){explorer.clearHypothetical();verdict.textContent='Hypothetical · unavailable';advice.textContent=error.message;}}}
for(const raw of new URL(location.href).searchParams.getAll('set')){const index=raw.indexOf('=');if(index>0){try{values.set(raw.slice(0,index),JSON.parse(raw.slice(index+1)));}catch{advice.textContent='Invalid URL fact value.';}}}
function mode(){const dated=new URL(location.href).searchParams.has('at');for(const input of root.querySelectorAll('input,button'))input.disabled=dated||(replay&&(input.tagName==='INPUT'||input.dataset.factReset));if(dated)verdict.textContent='Date view · choose Live today to try fact changes';return dated;}
function refresh(){render();if(!mode()){if(values.size)schedule();else verdict.textContent='Baseline · choose What if to test a change';}}
refresh();document.addEventListener('premise:graph',refresh);
document.addEventListener('premise:graph-loading',()=>{clearTimeout(timer);sequence++;fixes.replaceChildren();verdict.textContent='Loading graph…';});
document.addEventListener('premise:time',()=>{clearTimeout(timer);sequence++;explorer.clearHypothetical();fixes.replaceChildren();mode();});
