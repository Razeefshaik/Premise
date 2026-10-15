"""Explicit sandbox-only live rehearsal, to run AFTER the user pushes both repos."""
from __future__ import annotations
import argparse
import json
from premise.config import settings
from premise.github.api import GitHub
from premise.github.gitrepo import GitRepo
from premise.github.poller import Pipeline
from premise.graph.client import GraphClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',required=True,help='Create sandbox PRs and post real statuses/comments')
    parser.add_argument('--protect-main',action='store_true')
    args=parser.parse_args()
    s=settings()
    if s.sandbox_repo.lower()!='razeefshaik/kestrel-platform':
        raise SystemExit('This rehearsal is restricted to the designated fictional sandbox.')
    github=GitHub(s.sandbox_repo,s.github_token)
    pipeline=Pipeline(GraphClient(s.falkordb_host,s.falkordb_port,s.graph_name),github,
        GitRepo(s.sandbox_clone_dir,f'https://github.com/{s.sandbox_repo}.git'),s)
    pipeline.sync_main()
    results=[]
    for branch,title in [('scenario/s1-retry-72','Record Paylane new 72 hour retry policy'),('scenario/s2-email-decoy','Raise email retries within provider budget')]:
        prs=github.pages('pulls',{'state':'open','head':s.sandbox_repo.split('/')[0]+':'+branch})
        pr=prs[0] if prs else github.json('POST','pulls',json={'head':branch,'base':'main','title':title,
            'body':'Fictional-company demonstration for Premise. No production systems or real people are affected.'})
        result=pipeline.assess_pr(pr['number'],execute=True)
        results.append({'url':pr['html_url'],'verdict':result.verdict,'head_sha':result.head_sha})
    if args.protect_main:
        try:
            github.json('PUT','branches/main/protection',json={'required_status_checks':{'strict':True,'contexts':['premise/decisions']},
                'enforce_admins':False,'required_pull_request_reviews':None,'restrictions':None})
            results.append({'branch_protection':'required premise/decisions configured'})
        except Exception as exc:
            results.append({'branch_protection':'not configured','error':str(exc)})
    print(json.dumps(results,indent=2))
    print('Fix PRs, if enabled, are stacked on the failing PR branch. Merge them manually; rerun premise poll-once to verify green.')


if __name__=='__main__':
    main()
