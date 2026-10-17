import {source,el,showQueries,replay} from './source.js';
const search=document.getElementById('entity-search'),depth=document.getElementById('graph-depth'),message=document.getElementById('graph-message');
const params=new URL(location.href).searchParams;let focus=params.get('focus')||'',selected='',pathStart='',sequence=0;
depth.value=['1','2','3','4'].includes(params.get('depth'))?params.get('depth'):'1';
const shapes={Decision:'round-rectangle',Guarantee:'ellipse',Assumption:'diamond',Fact:'triangle',Service:'round-rectangle',Person:'hexagon',Team:'barrel'};
const healthClasses='holds holding broken violated unknown unverified unevaluable';
const hypothetical=new Map();let selectedRecord=null,selectionSequence=0;
function caption(node,health=node.health){return (node.label==='Person'?node.title:node.id)+'\n'+(health||node.label);}
function graphNode(node){return {data:{...node,baselineHealth:node.health,caption:caption(node),shape:shapes[node.label]},classes:node.health||''};}
function setHealth(id,health,chain){
 hypothetical.set(id,{health,chain});const node=cy.getElementById(id);
 if(node.length){node.removeClass(healthClasses).addClass(health);node.data({health,caption:caption(node.data(),health)});}
 if(selected===id)renderStatus();
}
function clearHypothetical(){
 hypothetical.clear();for(const node of cy.nodes()){const health=node.data('baselineHealth');node.removeClass(healthClasses+' touched affected');if(health)node.addClass(health);node.data({health,caption:caption(node.data(),health)});}
 renderStatus();
}
function renderStatus(){
 if(!selectedRecord)return;const status=document.getElementById('node-status'),chain=document.getElementById('node-chain');if(!status)return;
 const overlay=hypothetical.get(selected),health=overlay?.health||selectedRecord.health||selectedRecord.node.lifecycle||selectedRecord.node.label;
 status.textContent=health+(overlay?' · Hypothetical':' · Baseline');status.dataset.state=health;
 const steps=overlay?.chain??selectedRecord.chain;chain.textContent=steps.length?'Chain: '+steps.join(' → '):'';
}
const cy=window.cytoscape({container:document.getElementById('explorer-canvas'),elements:[],style:[{selector:'node',style:{label:'data(caption)','font-size':10,color:'#edf0ff','text-wrap':'wrap','text-max-width':120,'text-valign':'bottom','text-margin-y':8,'background-color':'#8697ec',width:34,height:34,shape:'data(shape)'}},{selector:'edge',style:{width:1.4,'line-color':'#4e5776','target-arrow-color':'#647294','target-arrow-shape':'triangle','curve-style':'bezier'}},{selector:'.holds,.holding',style:{'background-color':'#7cf0c8'}},{selector:'.broken,.violated',style:{'background-color':'#ff6b8b'}},{selector:'.unknown,.unverified,.unevaluable',style:{'background-color':'#ffd27a'}},{selector:'.faded',style:{opacity:.25}},{selector:'.path',style:{'line-color':'#c5d1ff',width:4,'border-width':3,'border-color':'#fff'}},{selector:'.touched',style:{'border-width':5,'border-color':'#fff'}},{selector:'.affected',style:{'border-width':4,'border-color':'#ff9ab0'}}]});
if(replay){depth.max='3';if(Number(depth.value)>3)depth.value='3';for(const input of document.querySelectorAll('#graph-kinds input'))input.disabled=true;el(document.querySelector('.v3-network'),'p','Replay includes recorded reasoning/service views at depths 1 to 3. Other paths or views may require a local live run.');}
const picker=document.getElementById('node-picker');picker.onchange=()=>{if(picker.value)select(picker.value);};
const explorer={cy,data:null,source,showQueries,load,select,setHealth,clearHypothetical,async addNodes(ids,isCurrent=()=>true){
 let added=false;
 for(const id of ids){if(!isCurrent())return;if(cy.getElementById(id).length)continue;
  const data=await source.request('/api/graph/neighborhood',viewParams({focus:id,depth:'1',kinds:'reasoning,services'}));
  if(!isCurrent())return;
  for(const n of data.nodes)if(!cy.getElementById(n.id).length){cy.add(graphNode(n));added=true;}
  for(const e of data.edges)if(!cy.edges().some(edge=>edge.source().id()===e.source&&edge.target().id()===e.target&&edge.data('type')===e.type))cy.add({data:{...e,id:'joined-'+e.source+'-'+e.type+'-'+e.target}});
 }
 if(added){cy.layout({name:'breadthfirst',directed:true,roots:cy.nodes('[label="Decision"]'),padding:32,spacingFactor:1.2}).run();for(const n of cy.nodes())if(![...picker.options].some(o=>o.value===n.id()))el(picker,'option',n.data('label')==='Person'?n.data('title'):n.id()+' · '+n.data('title')).value=n.id();}
}};window.premiseExplorer=explorer;
function viewParams(extra={}){const at=new URL(location.href).searchParams.get('at');return at?{...extra,at}:extra;}
function kinds(){return [...document.querySelectorAll('#graph-kinds input:checked')].map(n=>n.value).sort().join(',');}
function urlState(){const url=new URL(location.href);if(focus)url.searchParams.set('focus',focus);else url.searchParams.delete('focus');url.searchParams.set('depth',depth.value);history.replaceState(null,'',url);}
async function load(){
 document.dispatchEvent(new CustomEvent('premise:graph-loading'));
 const token=++sequence;selectionSequence++;selectedRecord=null;clearHypothetical();message.textContent='Loading graph…';message.classList.remove('v3-error');urlState();search.value=focus;document.getElementById('depth-value').value=depth.value;
 try{
  const data=await source.request(focus?'/api/graph/neighborhood':'/api/graph/overview',viewParams(focus?{focus,depth:depth.value,kinds:kinds()}:{}));if(token!==sequence)return;
  explorer.data=data;cy.elements().remove();cy.add([...data.nodes.map(graphNode),...data.edges.map((e,n)=>({data:{...e,id:'edge-'+n}}))]);
  const mixed=data.nodes.some(n=>['Person','Team','Service'].includes(n.label));cy.layout(mixed?{name:'cose',animate:false,randomize:false}:{name:'breadthfirst',directed:true,roots:cy.nodes('[label="Decision"]'),padding:32,spacingFactor:1.2}).run();
  picker.replaceChildren();el(picker,'option','Choose a node').value='';for(const n of data.nodes)el(picker,'option',n.label==='Person'?n.title:n.id+' · '+n.title).value=n.id;
  const options=document.getElementById('entity-options');for(const n of data.nodes)if(![...options.options].some(o=>o.value===n.id)){const option=el(options,'option');option.value=n.id;option.label=n.title;}
  message.textContent=`${data.nodes.length} nodes · ${data.edges.length} edges · revision ${data.graph_rev}${data.truncated?' · View capped at 300 nodes':''}`;showQueries(data);
  if(selected)select(selected,{activate:false});document.dispatchEvent(new CustomEvent('premise:graph',{detail:data}));
 }catch(error){if(token===sequence){message.textContent=error.message;message.classList.add('v3-error');}}
}
function inspectTab(which){for(const name of ['evidence','whatif']){document.getElementById('tab-'+name).setAttribute('aria-selected',String(which===name));document.getElementById(name==='evidence'?'evidence-panel':'explorer-whatif').hidden=which!==name;}}
for(const name of ['evidence','whatif']){const button=document.getElementById('tab-'+name);button.onclick=()=>inspectTab(name);button.onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?'evidence':event.key==='End'?'whatif':name==='evidence'?'whatif':'evidence';inspectTab(next);document.getElementById('tab-'+next).focus();}};}
async function select(id,{activate=true}={}){
 if(activate)inspectTab('evidence');selected=id;selectedRecord=null;const token=++selectionSequence,root=document.getElementById('node-details');root.replaceChildren();
 const node=cy.getElementById(id);document.getElementById('node-heading').textContent=node.data('label')==='Person'?node.data('title'):id;document.getElementById('focus-node').disabled=true;el(root,'p','Loading evidence…');
 try{
  const data=await source.request('/api/graph/node/'+encodeURIComponent(id),viewParams());if(selected!==id||token!==selectionSequence)return;selectedRecord=data;root.replaceChildren();
  document.getElementById('node-heading').textContent=data.node.label==='Person'?data.node.title:id;
  el(root,'p',data.statement);el(root,'p').id='node-status';el(root,'p').id='node-chain';renderStatus();
  el(root,'h3','Evidence');for(const e of data.evidence)el(root,'p',`${e.path}:${e.line}`);
  el(root,'h3','Owners');for(const o of data.owners)el(root,'p',`${o.team_name}: ${o.name||'No active member'} (${o.evidence} sources)`);
  el(root,'h3','Reviewers');el(root,'p',data.reviewers.map(id=>data.names[id]||id).join(', ')||'No reviewer recorded');document.getElementById('focus-node').disabled=false;showQueries(data);
 }catch(error){if(token===selectionSequence){root.replaceChildren();el(root,'p',error.message,'v3-error');}}
}
cy.on('tap','node',async event=>{const id=event.target.id();if(event.originalEvent?.shiftKey){if(!pathStart){pathStart=id;message.textContent='Shift+click a second node.';return;}try{const data=await source.request('/api/graph/path',viewParams({from:pathStart,to:id}));showQueries(data);cy.elements().removeClass('faded path');if(data.path){cy.elements().addClass('faded');for(const node of data.path)cy.getElementById(node).removeClass('faded').addClass('path');for(const e of data.edges)cy.edges().filter(edge=>edge.source().id()===e.source&&edge.target().id()===e.target).removeClass('faded').addClass('path');message.textContent=data.path.join(' → ');}else message.textContent='No allowed path within six hops.';}catch(error){message.textContent=error.message;}pathStart='';}else{pathStart=id;select(id);}});
document.getElementById('focus-form').addEventListener('submit',event=>{event.preventDefault();focus=search.value.trim();load();});document.getElementById('overview-button').onclick=()=>{focus='';load();};document.getElementById('focus-node').onclick=()=>{focus=selected;load();};depth.addEventListener('input',load);document.getElementById('graph-kinds').addEventListener('change',load);document.addEventListener('premise:time',load);await load();await import('./consequences.js');await import('./time.js');
