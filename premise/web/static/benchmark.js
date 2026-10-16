import {source,el,showQueries,replay} from './source.js';
const status=document.getElementById('benchmark-status');
try {
 const data=await source.request('/api/benchmark');
 status.textContent=`Recorded ${data.recorded_at} · ${data.passage_count} ADR passages · dev and test kept separate.`;
 document.getElementById('benchmark-latency').textContent=data.latency_note;
 const rows=data.summary.filter(r=>r.split==='test'),body=document.getElementById('benchmark-rows');
 for(const r of rows){const tr=el(body,'tr');for(const v of [r.kind,r.system,r.k??'—',...['precision','recall','f1','exact'].map(k=>r[k].toFixed(3)),r.p50_ms.toFixed(1),r.p95_ms.toFixed(1)])el(tr,'td',v);}
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 820 330');svg.setAttribute('class','v3-chart');svg.setAttribute('role','img');svg.setAttribute('aria-label','Test macro F1, graph versus keyword and vector at all k values');
 function item(tag,attrs,text){const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;svg.append(n);}
 for(let i=0;i<=5;i++){const y=270-i*48;item('line',{x1:45,y1:y,x2:810,y2:y,stroke:'#34374b'});item('text',{x:0,y:y+4,fill:'#c5cae0','font-size':12},(i/5).toFixed(1));}
 const colors={graph:'#7cf0c8',keyword:'#a9b7ff',vector:'#ffd27a'};
 for(const [i,r]of rows.filter(r=>r.kind==='all').entries()){const x=60+i*106,h=r.f1*240;item('rect',{x,y:270-h,width:62,height:h,fill:colors[r.system]});item('text',{x,y:292,fill:'#edf0ff','font-size':12},r.system);item('text',{x,y:312,fill:'#c5cae0','font-size':12},'k '+(r.k??'—'));}
 document.getElementById('benchmark-chart').append(svg);showQueries(data);
 if(replay){const questions=await source.request('/api/benchmark/questions');const blob=new Blob([JSON.stringify(questions,null,2)],{type:'application/json'});document.getElementById('benchmark-questions').href=URL.createObjectURL(blob);}
}catch(error){status.textContent=error.message;status.classList.add('v3-error');}
