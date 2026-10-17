import {source,el,showQueries,replay} from './source.js';
const status=document.getElementById('benchmark-status');
try {
 const data=await source.request('/api/benchmark'),recorded=new Date(data.recorded_at);
 const date=Number.isNaN(recorded.valueOf())?'Date unavailable':new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'UTC'}).format(recorded)+' UTC';
 status.textContent=`Recorded ${date} · ${data.passage_count} ADR passages · dev and test kept separate.`;
 document.getElementById('benchmark-latency').textContent=data.latency_note;
 const rows=data.summary.filter(r=>r.split==='test'),body=document.getElementById('benchmark-rows');
 const overall=rows.filter(r=>r.kind==='all'),graph=overall.find(r=>r.system==='graph'),best=overall.filter(r=>r.system!=='graph').sort((a,b)=>b.f1-a.f1)[0];
 if(!graph||!best)throw new Error('Recorded comparison is incomplete. Run the benchmark locally.');
 document.getElementById('benchmark-graph-score').textContent=graph.f1.toFixed(3);
 document.getElementById('benchmark-best-score').textContent=best.f1.toFixed(3);
 document.getElementById('benchmark-best-system').textContent=`Best retriever · ${best.system} k=${best.k}`;
 for(const r of rows){const tr=el(body,'tr');for(const v of [r.kind,r.system,r.k??'—',...['precision','recall','f1','exact'].map(k=>r[k].toFixed(3)),r.p50_ms.toFixed(1),r.p95_ms.toFixed(1)])el(tr,'td',v);}
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 820 330');svg.setAttribute('class','v3-chart');svg.setAttribute('role','img');svg.setAttribute('aria-label','Test macro F1, graph versus keyword and vector at all k values');
 function item(parent,tag,attrs,text){const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;parent.append(n);return n;}
 for(let i=0;i<=5;i++){const y=270-i*48;item(svg,'line',{x1:45,y1:y,x2:810,y2:y,class:'benchmark-grid'});item(svg,'text',{x:0,y:y+4,class:'benchmark-axis'},(i/5).toFixed(1));}
 const bars=[];
 for(const [i,r]of overall.entries()){
  const x=60+i*106,h=r.f1*240,group=item(svg,'g',{class:`benchmark-bar benchmark-${r.system}`});
  bars.push(item(group,'rect',{x,y:270-h,width:62,height:h}));
  item(group,'text',{x:x+31,y:260-h,'text-anchor':'middle',class:'benchmark-value'},r.f1.toFixed(3));
  item(group,'text',{x:x+31,y:292,'text-anchor':'middle'},r.system);
  item(group,'text',{x:x+31,y:312,'text-anchor':'middle',class:'benchmark-axis'},r.k===null?'reasoning':'k '+r.k);
 }
 const chart=document.getElementById('benchmark-chart');chart.append(svg);showQueries(data);
 // One entrance explains magnitude; reduced motion shows the measured values immediately.
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 if(!reduced.matches&&'IntersectionObserver' in window){
  for(const bar of bars)bar.style.transform='scaleY(0)';
  const observer=new IntersectionObserver(entries=>{if(!entries.some(e=>e.isIntersecting))return;observer.disconnect();
   for(const [i,bar]of bars.entries()){bar.style.removeProperty('transform');if(!reduced.matches)bar.animate([{transform:'scaleY(0)'},{transform:'scaleY(1)'}],{duration:480,delay:i*35,easing:'cubic-bezier(0.22,1,0.36,1)'});}
  },{threshold:.2});observer.observe(chart);
  reduced.addEventListener('change',()=>{if(reduced.matches){observer.disconnect();for(const bar of bars){bar.style.removeProperty('transform');for(const animation of bar.getAnimations())animation.finish();}}});
 }
 if(replay){const questions=await source.request('/api/benchmark/questions');const blob=new Blob([JSON.stringify(questions,null,2)],{type:'application/json'});document.getElementById('benchmark-questions').href=URL.createObjectURL(blob);}
}catch(error){status.textContent=error.message;status.classList.add('v3-error');}
