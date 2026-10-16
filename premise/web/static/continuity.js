import {source,el,showQueries,replay} from './source.js';
const picker=document.getElementById('departure-person'),status=document.getElementById('continuity-status');let sequence=0,cy;
async function load(){const token=++sequence,person=picker.value||new URL(location.href).searchParams.get('person')||'p_jun';status.textContent='Checking continuity…';try{const data=await source.request('/api/continuity',{person});if(token!==sequence)return;
 if(!picker.options.length)for(const p of data.people.filter(p=>!replay||source.index.people.includes(p.id)))el(picker,'option',p.name+' · '+p.status).value=p.id;picker.value=person;const url=new URL(location.href);url.searchParams.set('person',person);history.replaceState(null,'',url);
 const fill=(id,rows,none)=>{const root=document.getElementById(id);root.replaceChildren();for(const row of rows.length?rows:[none])el(root,'p',row);};
 fill('continuity-orphans',data.orphaned_decisions,'No new accountability gaps.');
 fill('continuity-promises',[...data.unverified_assumptions.map(a=>a.id+' becomes unverified'),...data.changed_guarantees.map(g=>g.id+': '+g.before+' → '+g.status)],'No guarantee health changes.');
 fill('continuity-reviewers',data.reviewer_routing.map(d=>d.id+': '+(d.after.join(', ')||'No active candidate')),'No current reviewer assignments affected.');
 fill('continuity-bridge',[`Native betweenness: ${data.bridge.score??'not active'} · rank ${data.bridge.rank??'—'} / ${data.bridge.active_people}`,`Services newly disconnected from every active person: ${data.isolated_services.join(', ')||'none'}`],'');
 const ids=new Set([person,...data.orphaned_decisions,...data.reviewer_routing.map(d=>d.id),...data.isolated_services]);for(const e of data.projection.edges)if(e.source===person||e.target===person){ids.add(e.source);ids.add(e.target);}
 if(cy)cy.destroy();cy=window.cytoscape({container:document.getElementById('continuity-canvas'),elements:[...data.projection.nodes.filter(n=>ids.has(n.id)).map(n=>({data:{id:n.id},classes:n.id===person?'gone':''})),...data.projection.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map((e,i)=>({data:{...e,id:'c'+i}}))],style:[{selector:'node',style:{label:'data(id)',color:'#edf0ff','background-color':'#a9b7ff','font-size':11}},{selector:'edge',style:{'line-color':'#626c8c'}},{selector:'.gone',style:{'background-color':'#ff6b8b',opacity:.6}}],layout:{name:'cose',animate:false}});
 document.getElementById('continuity-projection').textContent=data.projection.note;showQueries(data);status.textContent='Hypothetical departure · revision '+data.graph_rev;
}catch(error){status.textContent=error.message;status.classList.add('v3-error');}}
picker.onchange=load;await load();
