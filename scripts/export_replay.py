"""Record real API responses from a fresh, isolated ingest for an offline Pages replay.

Run from the checkout: python scripts/export_replay.py
No GitHub/model calls and no existing graph or site directory is deleted.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from premise.config import Settings
from premise.graph.client import GraphClient
from premise.ingest.run import ingest
from premise.scenarios import load_scenarios,scenario_now
from premise.web.app import create_app,templates


def request_key(path,params=None,body=None):
    def js_numbers(value):
        if isinstance(value,float) and value.is_integer():return int(value)
        if isinstance(value,list):return [js_numbers(v) for v in value]
        if isinstance(value,dict):return {k:js_numbers(v) for k,v in value.items()}
        return value
    return json.dumps(js_numbers(['GET' if body is None else 'POST',path,sorted((k,v) for k,v in (params or {}).items() if v is not None and v!=''),body]),separators=(',',':'),ensure_ascii=False)


def export_site(output=None,host='127.0.0.1',port=6379):
    output=Path(output or ROOT/'site').resolve()
    data_dir=output/'data';data_dir.mkdir(parents=True,exist_ok=True)
    graph=GraphClient(host,port,'premise_replay_'+uuid.uuid4().hex)
    now=scenario_now(load_scenarios(ROOT/'scenarios/scenarios.yaml'))
    model_sha=hashlib.sha256(b''.join(p.relative_to(ROOT/'sandbox/kestrel-platform').as_posix().encode()+p.read_bytes() for p in sorted((ROOT/'sandbox/kestrel-platform').rglob('*')) if p.is_file() and '.git' not in p.parts)).hexdigest()
    index={'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'model_sha256':model_sha,
           'evaluation_at_ms':now,'graph':graph.graph_name,'requests':{},'files':{},'people':['p_jun','p_anika','p_ravi']}
    try:
        ingest(graph,ROOT/'sandbox/kestrel-platform',model_sha)
        config=Settings(poll_enabled=False,llm_provider='none',github_token='',anthropic_api_key='')
        with TestClient(create_app(graph,config,graph_api_at_ms=now)) as http:
            def record(path,params=None,body=None):
                key=request_key(path,params,body)
                if key in index['requests']:
                    return json.loads((data_dir/index['requests'][key]).read_text(encoding='utf8'))
                response=http.get(path,params=params) if body is None else http.post(path,json=body)
                if response.status_code!=200:raise RuntimeError(f'Recording failed: {path} {params}: {response.status_code} {response.text[:200]}')
                payload=response.json()
                filename=hashlib.sha256(key.encode()).hexdigest()[:24]+'.json'
                content=json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode('utf8')
                (data_dir/filename).write_bytes(content)
                index['requests'][key]=filename;index['files'][filename]=hashlib.sha256(content).hexdigest()
                return payload
            overview=record('/api/graph/overview')
            index['graph_rev']=overview['graph_rev']
            timeline=record('/api/graph/timeline')
            facts=record('/api/graph/facts')
            entities=graph.read('MATCH (n:Entity) WHERE n.retired_rev IS NULL AND any(l IN labels(n) WHERE l IN $labels) RETURN n.id AS id,labels(n) AS labels ORDER BY id',{'labels':['Decision','Guarantee','Assumption','Person','Team','Service','Fact']})
            for n in entities:
                record('/api/graph/node/'+n['id'])
                for depth in range(1,4):
                    record('/api/graph/neighborhood',{'focus':n['id'],'depth':str(depth),'kinds':'reasoning,services'})
            # Paths between every reasoning node visible in the overview.
            for a in overview['nodes']:
                for b in overview['nodes']:
                    record('/api/graph/path',{'from':a['id'],'to':b['id']})
            dates={timeline['today'],'2026-10-16','2027-03-02'}
            for mark in timeline['marks']:
                day=dt.date.fromisoformat(mark['date'])
                for offset in (0,1):
                    date=(day+dt.timedelta(days=offset)).isoformat()
                    if timeline['start']<=date<=timeline['end']:dates.add(date)
            index['dates']=sorted(dates)
            focus_nodes=entities
            for date in index['dates']:
                record('/api/graph/overview',{'at':date})
                for n in focus_nodes:
                    record('/api/graph/node/'+n['id'],{'at':date})
                    for depth in range(1,4):
                        record('/api/graph/neighborhood',{'focus':n['id'],'depth':str(depth),'kinds':'reasoning,services','at':date})
            def proposal(values):
                changes=[{'fact':fact,'delete':True} if value is None else {'fact':fact,'value':value} for fact,value in sorted(values.items())]
                return record('/api/check',body={'changes':changes})
            for preset in facts['presets']:
                result=proposal(preset['values'])
                for fix in result['verified_fixes']:
                    proposal({**preset['values'],**fix['changes']})
            for person in ('p_jun','p_anika','p_ravi'):
                record('/api/continuity',{'person':person})
            record('/api/benchmark');record('/api/benchmark/questions')
        render_assets(output,index)
        (data_dir/'index.json').write_text(json.dumps(index,indent=2,ensure_ascii=False),encoding='utf8')
        (output/'.nojekyll').write_text('')
        (output/'README.txt').write_text('Recorded replay only. Run python -m http.server --directory site to inspect locally.\n',encoding='utf8')
        print(json.dumps({'output':str(output),'responses':len(index['requests']),'recorded_dates':len(index['dates']),'model_sha256':model_sha}),flush=True)
        return index
    finally:
        graph.delete_graph()


def render_assets(output,index):
    for name in ('explore','benchmark','continuity'):
        request=SimpleNamespace(url=SimpleNamespace(path='/'+name))
        html=templates.env.get_template(name+'.html').render(request=request,url_for=lambda name,path:'./static/'+path)
        html=html.replace('<html lang="en">','<html lang="en" data-source="replay">')
        html=html.replace('<body class="','<body class="')
        banner='<div class="v3-replay">Replay of recorded FalkorDB results. Run locally for live checks. <small>Recorded '+index['recorded_at']+' · fictional Kestrel company · dates and presets are recorded selections.</small></div>'
        html=re.sub(r'(<body[^>]*>)',lambda m:m[1]+banner,html,count=1)
        nav='<nav aria-label="Replay"><a href="./index.html">Explore</a><a href="./benchmark.html">Benchmark</a><a href="./continuity.html">Continuity</a><a href="https://github.com/Razeefshaik/Premise">Source</a></nav>'
        html=re.sub(r'<nav aria-label="Main">.*?</nav>',nav,html,flags=re.S)
        html=html.replace('href="/static/','href="./static/').replace('src="/static/','src="./static/').replace('href="/"','href="./index.html"')
        (output/('index.html' if name=='explore' else name+'.html')).write_text(html,encoding='utf8')
    static=ROOT/'premise/web/static'
    for path in static.rglob('*'):
        if not path.is_file() or 'models' in path.relative_to(static).parts:continue
        target=output/'static'/path.relative_to(static);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');parser.add_argument('--render-only',action='store_true');parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=6379)
    args=parser.parse_args()
    if args.render_only:
        output=Path(args.output or ROOT/'site').resolve()
        render_assets(output,json.loads((output/'data/index.json').read_text(encoding='utf8')))
    else:export_site(args.output,args.host,args.port)
