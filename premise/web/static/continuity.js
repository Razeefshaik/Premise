import {source,el,showQueries,replay} from './source.js';
const picker=document.getElementById('departure-person'),status=document.getElementById('continuity-status'),choices=document.getElementById('departure-choices');
const graphStatus=document.getElementById('continuity-graph-status'),impact=document.querySelector('.continuity-impact');
let sequence=0,cy;
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const token=name=>getComputedStyle(document.documentElement).getPropertyValue('--'+name).trim();
function count(id,value){const n=document.getElementById(id);n.textContent=String(value);for(const animation of n.getAnimations())animation.cancel();if(!reduced.matches)n.animate([{opacity:.25,transform:'translateY(4px)'},{opacity:1,transform:'translateY(0)'}],{duration:240,easing:'cubic-bezier(0.22,1,0.36,1)'});}
async function load(){
 const request=++sequence,person=picker.value||new URL(location.href).searchParams.get('person')||'p_jun';
 status.classList.remove('v3-error');status.textContent='Checking continuity…';graphStatus.textContent='Loading connections…';impact.setAttribute('aria-busy','true');
 try{
  const data=await source.request('/api/continuity',{person});if(request!==sequence)return;
  if(!picker.options.length)for(const p of data.people.filter(p=>!replay||source.index.people.includes(p.id)))el(picker,'option',p.name+' · '+p.status).value=p.id;
  picker.value=person;choices.replaceChildren();
  for(const p of data.people.filter(p=>p.status==='active'&&(!replay||source.index.people.includes(p.id)))){
   const button=el(choices,'button',p.name,'chip quiet-chip');button.type='button';button.dataset.departure=p.id;button.setAttribute('aria-pressed',String(p.id===person));button.onclick=()=>{picker.value=p.id;load();};
  }
  const url=new URL(location.href);url.searchParams.set('person',person);history.replaceState(null,'',url);
  const fill=(id,rows,none)=>{const root=document.getElementById(id);root.replaceChildren();for(const row of rows.length?rows:[none])el(root,'p',row);};
  fill('continuity-orphans',data.orphaned_decisions,'No new accountability gaps.');
  fill('continuity-promises',[...data.unverified_assumptions.map(a=>a.id+' becomes unverified'),...data.changed_guarantees.map(g=>g.id+': '+g.before+' → '+g.status)],'No guarantee health changes.');
  const names=new Map(data.people.map(p=>[p.id,p.name]));
  fill('continuity-reviewers',data.reviewer_routing.map(d=>d.id+': '+(d.after.map(id=>names.get(id)||id).join(', ')||'No active candidate')),'No current reviewer assignments affected.');
  const score=data.bridge.score===null?'not active':new Intl.NumberFormat('en-GB',{maximumFractionDigits:2}).format(data.bridge.score);
  fill('continuity-bridge',[`Native betweenness: ${score} · rank ${data.bridge.rank??'—'} / ${data.bridge.active_people}`,`Services newly disconnected from every active person: ${data.isolated_services.join(', ')||'none'}`],'');
  count('continuity-orphan-count',data.orphaned_decisions.length);count('continuity-promise-count',data.changed_guarantees.length);count('continuity-reviewer-count',data.reviewer_routing.length);
  const ids=new Set([person,...data.orphaned_decisions,...data.affected_decisions,...data.reviewer_routing.map(d=>d.id),...data.isolated_services]);
  for(const edge of data.projection.edges)if(edge.source===person||edge.target===person){ids.add(edge.source);ids.add(edge.target);}
  if(cy)cy.destroy();
  const nodes=data.projection.nodes.filter(n=>ids.has(n.id));
  cy=window.cytoscape({container:document.getElementById('continuity-canvas'),elements:[
   ...nodes.map(n=>({data:{id:n.id,caption:names.get(n.id)||n.id,shape:n.labels.includes('Person')?'hexagon':'round-rectangle'},classes:[n.labels.includes('Person')?'person':'',n.id===person?'gone':'',data.orphaned_decisions.includes(n.id)?'orphan':''].join(' ')})),
   ...data.projection.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map((e,i)=>({data:{...e,id:'c'+i},classes:e.source===person||e.target===person?'cut':''}))
  ],style:[
   {selector:'node',style:{label:'data(caption)',shape:'data(shape)',color:token('ink'),'background-color':token('indigo-2'),'font-size':12,'text-valign':'bottom','text-margin-y':8,'text-wrap':'wrap','text-max-width':120,width:34,height:34}},
   {selector:'.person',style:{'background-color':token('holds')}},
   {selector:'edge',style:{'line-color':token('ink-3'),width:1.5}},
   {selector:'.gone',style:{'background-color':token('broken'),'border-width':3,'border-color':token('broken'),opacity:.65}},
   {selector:'.orphan',style:{'border-width':3,'border-color':token('unknown')}},
   {selector:'.cut',style:{'line-color':token('broken'),'line-style':'dashed',width:2.5}}
  ],layout:{name:'cose',animate:false,padding:40}});
  window.premiseContinuity={cy,data};
  graphStatus.textContent=nodes.length?`${nodes.length} entities shown · ${cy.edges('.cut').length} links touch ${names.get(person)||person}`:'No affected connections in the current graph.';
  document.getElementById('continuity-projection').textContent=data.projection.note;showQueries(data);status.textContent='Hypothetical departure · '+(names.get(person)||person)+' · revision '+data.graph_rev;
 }catch(error){if(request===sequence){status.textContent=error.message+' Choose a person to retry.';status.classList.add('v3-error');graphStatus.textContent='Connections unavailable.';impact.querySelectorAll('[id]').forEach(n=>n.replaceChildren());for(const id of ['continuity-orphan-count','continuity-promise-count','continuity-reviewer-count'])document.getElementById(id).textContent='—';if(cy){cy.destroy();cy=null;}window.premiseContinuity=null;}}
 finally{if(request===sequence)impact.setAttribute('aria-busy','false');}
}
picker.onchange=load;await load();
