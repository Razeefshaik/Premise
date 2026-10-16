"""Opt-in deterministic knowledge maintenance; domain nodes are never mutated."""
from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import quote

from ..agent.render import provenance, safe
from ..graph.client import GraphUnavailable
from ..graph.tools import GraphTools
from ..reasoning.assess import DAY_MS, _route, graph_ready
from .store import Store, digest

MARKER = re.compile(r'<!-- premise:steward:(EXPIRED_ATTESTATION|ORPHANED_DECISION):([A-Za-z0-9_-]+) -->')


def marker(kind, entity):
    return f'<!-- premise:steward:{kind}:{entity} -->'


def date(ms):
    return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).strftime('%Y-%m-%d') if ms is not None else 'not recorded'


class Steward:
    def __init__(self, client, github, at_ms=None, since_days=180):
        self.client,self.github = client,github
        self.tools=GraphTools(client,at_ms,since_days)
        self.store=Store(client)

    def findings(self):
        health=self.tools.call('guarantee_health',{})
        states={g['id']:g for g in health['guarantees']}
        problems=[]
        for a in health['assumptions']:
            if a['kind']=='manual' and a['state']=='unverified':
                pairs=self.client.named('guarantee_assumption_pairs',{'assumptions':[a['id']],'guarantees':None})
                problems.append({'kind':'EXPIRED_ATTESTATION','entity':a['id'],
                    'guarantee_ids':sorted({p['guarantee'] for p in pairs}), 'attestations':a['attestations']})
        for d in self.tools.call('orphaned_decisions',{}):
            paths=self.client.named('decision_lineage',{'id':d['decision']})
            problems.append({'kind':'ORPHANED_DECISION','entity':d['decision'],
                             'guarantee_ids':sorted({p['guarantee'] for p in paths})})
        people={p['id']:p['name'] for p in self.client.read('MATCH (p:Person) RETURN p.id AS id, p.name AS name')}
        for f in problems:
            impacts=self.client.named('guarantee_impact',{'guarantees':f['guarantee_ids']}) if f['guarantee_ids'] else []
            f['guarantees']=[{'id':g['guarantee'],'tier':min(g['tiers']) if g['tiers'] else None,
                             'status':states[g['guarantee']]['status']} for g in impacts]
            decisions={d for g in impacts for d in g['promised_by']+g['relied_on_by']}
            if f['kind']=='ORPHANED_DECISION': decisions.add(f['entity'])
            f['decisions']=sorted(decisions)
            reviewers={}
            for did in f['decisions']:
                active,_,candidates=_route(self.client,did,self.tools.now-self.tools.since_days*DAY_MS)
                for c in candidates:
                    if c.person not in reviewers or c.evidence > reviewers[c.person]['evidence']:
                        reviewers[c.person]={'id':c.person,'name':people.get(c.person,c.person),'evidence':c.evidence}
                for person in active:
                    reviewers.setdefault(person,{'id':person,'name':people.get(person,person),'evidence':0})
            f['reviewers']=sorted(reviewers.values(),key=lambda p:(-p['evidence'],p['id']))
            f['sources']=provenance(self.client,[f['entity'],*f['decisions'],*f['guarantee_ids']])
            for a in f.get('attestations',[]): a['name']=people.get(a['person'],a['person'])
        return sorted(problems,key=lambda f:(f['kind'],f['entity']))

    def body(self, finding, rev):
        f=finding
        out=[f"## Knowledge needing review: {safe(f['entity'])}",'']
        if f['kind']=='EXPIRED_ATTESTATION':
            out+=['No current attestation by an active person establishes this manual assumption.']
            for a in f.get('attestations',[]):
                out.append(f"- {safe(a['name'])}: attested {date(a.get('on'))}; review by {date(a.get('review_by'))}; person status {safe(a['status'])}.")
            action='Renew or record the attestation with an active person, date and review_by in the authored source below.'
        else:
            out+=['No active accountable author or approver is recorded in the current graph. The date this gap began is not recorded.']
            action='Add an active accountable author or approver in the decision front matter below.'
        out+=['','### Exposed guarantees']
        out += [f"- {safe(g['id'])}: tier {g['tier'] if g['tier'] is not None else 'unknown'}; health {safe(g['status'])}." for g in f['guarantees']]
        out+=['','### Exposed decisions',', '.join(safe(d) for d in f['decisions']) or 'None recorded.',
              '','### Suggested reviewers']
        out += [f"- {safe(p['name'])} ({safe(p['id'])}): {p['evidence']} recent authored sources." for p in f['reviewers']]
        out+=['','### What to update',action]
        # Put the exact entity's authored file first, then supporting provenance.
        for source in sorted(f['sources'],key=lambda s:(s['id']!=f['entity'],s['path'],s['line'] or 0)):
            label=safe(f"{source['id']}: {source['path']}:{source['line']}")
            url=source.get('url') or ''
            out.append(f"- [{label}]({quote(url.split('#')[0],safe='/:') }#L{source['line']})" if url.startswith('https://github.com/') else f'- {label} (local source).')
        out+=['',f'Graph revision {rev}.','Generated by Premise from graph data; no model was used.',
              '',marker(f['kind'],f['entity'])]
        return '\n'.join(out)

    def fresh(self, rev):
        ready,current,_=graph_ready(self.client)
        if not ready or current!=rev:
            raise GraphUnavailable('Graph changed or became unavailable; rerun the steward')

    def reconcile(self, issues, actor):
        for task in self.store.pending_tasks():
            payload=json.loads(task['payload'])
            if payload.get('repo')!=self.github.repo: continue
            issue=next((i for i in issues if marker(payload['kind'],payload['entity']) in (i.get('body') or '')),None)
            if not issue: continue
            op=payload['operation']
            done=(op=='create' or op=='update' and issue['body']==payload['body'] or op=='close' and issue['state']=='closed')
            if op=='comment':
                comments=self.github.pages(f"issues/{issue['number']}/comments")
                done=any(c.get('body')==payload['body'] and c.get('user',{}).get('login')==actor for c in comments)
            if done: self.store.finish_task(task['id'],url=issue.get('html_url',''))

    def run(self, execute=False, max_writes=10):
        self.tools.guard()
        rev=self.client.named('graph_state')[0]['rev']
        findings=self.findings()
        self.fresh(rev)
        actor=self.github.actor()
        issues=[i for i in self.github.pages('issues',{'state':'all','creator':actor})
                if 'pull_request' not in i and i.get('user',{}).get('login')==actor]
        if execute: self.reconcile(issues,actor)
        managed={}
        for issue in sorted(issues,key=lambda i:i['number'],reverse=True):
            match=MARKER.search(issue.get('body') or '')
            if match: managed[match.groups()]=issue
        plans=[]
        active=set()
        for f in findings:
            key=(f['kind'],f['entity']); active.add(key)
            issue=managed.get(key); body=self.body(f,rev)
            op='create' if not issue else 'suppressed_by_human' if issue['state']=='closed' else 'unchanged' if issue['body']==body else 'update'
            title=f"Premise: {safe(f['entity'])} needs an owner" if f['kind']=='ORPHANED_DECISION' else f"Premise: attestation for {safe(f['entity'])} expired"
            plans.append({'kind':f['kind'],'entity':f['entity'],'operation':op,'body':body,'title':title,
                          'issue':issue,'finding':f})
        for key,issue in managed.items():
            if key not in active and issue['state']=='open':
                plans.append({'kind':key[0],'entity':key[1],'operation':'close','issue':issue})
        count=0
        for plan in plans:
            op=plan['operation']
            if op in {'unchanged','suppressed_by_human'}: continue
            needed=2 if op=='close' else 1
            if execute and count+needed > min(10,max_writes):
                plan['status']='deferred_write_cap'; continue
            if not execute: continue
            number=plan['issue']['number'] if plan['issue'] else None
            def write(operation, method, path, content):
                nonlocal count
                self.fresh(rev)
                payload={'repo':self.github.repo,'kind':plan['kind'],'entity':plan['entity'],
                         'graph_rev':rev,'operation':operation,'body':content.get('body',''),
                         'issue_url':(plan['issue'] or {}).get('html_url','')}
                key='steward:'+digest([payload,content])
                self.store.begin_task(key,plan['kind'],payload)
                try:
                    count+=1
                    response=self.github.json(method,path,json=content)
                    self.store.finish_task(key,url=(response or {}).get('html_url',payload['issue_url']))
                    return response
                except Exception as exc:
                    self.store.finish_task(key,'failed',error=type(exc).__name__)
                    raise
            if op=='create':
                response=write('create','POST','issues',{'title':plan['title'],'body':plan['body']})
                plan['issue_url']=response['html_url']
            elif op=='update':
                write('update','PATCH',f'issues/{number}',{'body':plan['body']})
            else:
                body=f'Resolved at graph revision {rev}'
                comments=self.github.pages(f'issues/{number}/comments')
                if not any(c.get('body')==body and c.get('user',{}).get('login')==actor for c in comments):
                    write('comment','POST',f'issues/{number}/comments',{'body':body})
                write('close','PATCH',f'issues/{number}',{'state':'closed'})
            plan['status']='applied'
        return {'graph_rev':rev,'execute':execute,'writes':count,'plan':plans}
