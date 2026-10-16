"""Publish actual pytest outcomes, including failures; no hand-authored pass totals."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import yaml
from .agent.render import safe

ROOT=Path(__file__).resolve().parents[1]


def report(host='127.0.0.1',port=6379):
    folder=ROOT/'.runtime/redteam';folder.mkdir(parents=True,exist_ok=True)
    xml=folder/'results.xml'
    if xml.exists():xml.unlink()
    result=subprocess.run([sys.executable,'-m','pytest','tests/test_redteam.py','-q',
                           '-o','junit_family=legacy','--junitxml',str(xml)],cwd=ROOT,
                          env={**os.environ,'FALKORDB_HOST':host,'FALKORDB_PORT':str(port)},
                          capture_output=True,text=True,timeout=180)
    (folder/'pytest.txt').write_text(result.stdout+result.stderr,encoding='utf8')
    if not xml.exists():raise RuntimeError('Red-team runner produced no results; inspect .runtime/redteam/pytest.txt')
    outcomes={}
    for case in ET.parse(xml).iter('testcase'):
        key=case.attrib['name'].partition('[')[2].removesuffix(']')
        failure=case.find('failure')
        error=case.find('error')
        skipped=case.find('skipped')
        props={p.attrib['name']:p.attrib['value'] for p in case.findall('./properties/property')}
        outcomes[key]={'pass':failure is None and error is None and skipped is None,
                       'actual':props.get('actual') or ((failure if failure is not None else error).attrib.get('message','failed')[:180] if failure is not None or error is not None else 'not executed')}
    attacks=yaml.safe_load((ROOT/'redteam/attacks.yaml').read_text())
    passed=sum(outcomes.get(a['id'],{}).get('pass',False) for a in attacks)
    lines=['# Red-team regression report','',f'{passed}/{len(attacks)} attacks passed their expected safe outcome in this local run.', '',
           'Real FalkorDB; GitHub writes use HTTP MockTransport and analyst output uses a FakeAdapter. No remote PRs were created. This finite regression set is not a security certification. Deep/alias YAML and bare-link regressions were reproduced failing before the hardening.', '',
           '| Id | Category | Expected | Actual | Pass |','| --- | --- | --- | --- | --- |']
    for a in attacks:
        row=outcomes.get(a['id'],{'actual':'not run','pass':False})
        lines.append('| '+ ' | '.join(safe(v) for v in [a['id'],a['category'],a['expect'],row['actual'],'yes' if row['pass'] else 'NO'])+' |')
    (ROOT/'docs/REDTEAM.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    return {'passed':passed,'total':len(attacks),'exit_code':result.returncode}
