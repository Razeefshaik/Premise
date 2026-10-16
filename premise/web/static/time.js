import {source,el,showQueries} from './source.js';
const date=document.getElementById('time-date'),slider=document.getElementById('time-range'),label=document.getElementById('time-label');
const day=86400000;let sequence=0;
try{const data=await source.request('/api/graph/timeline'),start=Date.parse(data.start+'T00:00:00Z');date.min=data.start;date.max=data.end;date.value=new URL(location.href).searchParams.get('at')||data.today;slider.value=Math.round((Date.parse(date.value+'T00:00:00Z')-start)/day);
 const marks=document.getElementById('time-marks');for(const mark of data.marks){const n=Math.round((Date.parse(mark.date+'T00:00:00Z')-start)/day);if(n>=0&&n<=545){const option=el(marks,'option');option.value=n;option.label=mark.assumption+' '+mark.kind+' '+mark.date;}}
 document.getElementById('time-events').textContent=data.marks.filter(m=>m.kind==='review_by').map(m=>m.assumption+' review by '+m.date).join(' · ');
 async function change(){const token=++sequence;if(!date.validity.valid||!date.value){label.textContent='Choose a date within the slider range.';return;}slider.value=Math.round((Date.parse(date.value+'T00:00:00Z')-start)/day);label.textContent=(date.value>data.today?'Forecast · ':date.value<data.today?'Historical evaluation · ':'Today · ')+date.value;const url=new URL(location.href);url.searchParams.set('at',date.value);history.replaceState(null,'',url);
 if(window.premiseExplorer){document.dispatchEvent(new CustomEvent('premise:time'));return;}
 const result=await source.request('/api/graph/overview',{at:date.value});if(token!==sequence)return;showQueries(result);for(const n of result.nodes){if(n.label!=='Guarantee')continue;const card=document.querySelector(`[data-guarantee="${n.id}"]`);if(!card)continue;card.classList.remove('is-holds','is-broken','is-unknown');card.classList.add('is-'+n.health);const badge=card.querySelector('.badge');if(badge){badge.textContent=n.health;badge.className='badge '+n.health;}card.href='/explore?focus='+encodeURIComponent(n.id)+'&at='+date.value;for(const p of card.querySelectorAll('.prereq,.dots,.g-foot'))p.hidden=true;}
 }
 date.onchange=()=>change().catch(e=>label.textContent=e.message);slider.oninput=()=>{date.value=new Date(start+Number(slider.value)*day).toISOString().slice(0,10);date.onchange();};
 document.getElementById('time-live').onclick=()=>{const url=new URL(location.href);url.searchParams.delete('at');history.replaceState(null,'',url);date.value=data.today;slider.value=180;label.textContent='Live today';if(window.premiseExplorer)document.dispatchEvent(new CustomEvent('premise:time'));else location.reload();};
 if(new URL(location.href).searchParams.has('at'))await change();
}catch(error){label.textContent=error.message;}
