"""Run the feature merge gates in an isolated graph and local app, without GitHub/model writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import httpx
from premise.graph.client import GraphClient


def main():
    tag=sys.argv[1] if len(sys.argv)>1 else 'features'
    artifact=Path('artifacts')/tag
    artifact.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'POLL_ENABLED':'false','AUTO_FIX_PR':'false','LLM_PROVIDER':'none'}
    name='premise_gate_'+uuid.uuid4().hex[:10]
    port=8002
    report={}
    server=None
    client=GraphClient(host=env.get('FALKORDB_HOST','localhost'),port=int(env.get('FALKORDB_PORT','6379')),graph_name=name)
    def run(label,args):
        before=time.monotonic()
        result=subprocess.run([sys.executable,*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        text=result.stdout.decode('utf-8',errors='replace')
        (artifact/(label+'.log')).write_text(text,encoding='utf-8')
        print(text,flush=True)
        report[label]={'exit_code':result.returncode,'seconds':round(time.monotonic()-before,2)}
        if result.returncode:
            raise RuntimeError(label+' failed')
    try:
        if '--browser-only' not in sys.argv:
            run('tests',['-m','pytest','-q'])
        else:
            report['browser_only']=True
        run('seed',['-m','premise.cli','--graph',name,'demo'])
        run('scenarios',['-m','premise.cli','--graph',name,'scenarios'])
        with (artifact/'server.log').open('wb') as log:
            server=subprocess.Popen([sys.executable,'-m','premise.cli','--graph',name,'serve','--web-port',str(port)],
                                    env=env,stdout=log,stderr=subprocess.STDOUT)
            for _ in range(60):
                try:
                    if httpx.get(f'http://localhost:{port}/healthz',timeout=1).status_code==200: break
                except httpx.HTTPError: pass
                if server.poll() is not None: raise RuntimeError('Local server failed')
                time.sleep(0.2)
            else: raise RuntimeError('Local server did not become ready')
            env['PREMISE_BASE_URL']=f'http://localhost:{port}'
            env['PREMISE_UI_ARTIFACT_DIR']=str(artifact)
            run('browser',['scripts/check_ui.py'])
        report['success']=True
    finally:
        if server is not None:
            server.terminate()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
        client.delete_graph()
        (artifact/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__': main()
