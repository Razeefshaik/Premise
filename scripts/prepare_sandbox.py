"""Prepare a dedicated LOCAL sandbox Git repo and scenario branches. Never pushes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from premise.scenarios import load_scenarios, apply_patches


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',default='.runtime/kestrel-publish')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    dest=Path(args.destination).resolve()
    if dest.exists():
        raise SystemExit('Destination already exists; choose a new empty path. Existing work is preserved.')
    shutil.copytree(root/'sandbox/kestrel-platform',dest)
    def git(*args):
        return subprocess.check_output(['git','-C',str(dest),*args],stderr=subprocess.DEVNULL).decode().strip()
    git('init','-b','main')
    git('config','user.name','Shaik Mohammad Razeef')
    git('config','user.email','149264441+Razeefshaik@users.noreply.github.com')
    git('remote','add','origin','https://github.com/Razeefshaik/kestrel-platform.git')
    git('add','.');git('commit','-m','Seed fictional Kestrel company and guarantee model')
    base=git('rev-parse','HEAD')
    scenarios=load_scenarios(root/'scenarios/scenarios.yaml')['scenarios']
    names={'S1':'s1-retry-72','S2':'s2-email-decoy','S3':'s3-ttl-deleted','S5':'s5-charge-timeout','S6':'s6-ad-cache','S7':'s7-adr-edit','S8':'s8-readme','S10':'s10-cart-ttl'}
    refs={}
    for name,branch in names.items():
        git('checkout','-b','scenario/'+branch,base)
        for path,text in apply_patches(dest,scenarios[name]['patches']).items():
            target=dest/path
            target.write_text(text,encoding='utf-8') if text is not None else target.unlink()
        git('add','.');git('commit','-m',scenarios[name]['title'])
        refs[name]={'branch':'scenario/'+branch,'sha':git('rev-parse','HEAD')}
    git('checkout','main')
    # Manifest belongs in the product workspace, not the synthetic company's graph.
    manifest=dest.parent/(dest.name+'-expected.json')
    manifest.write_text(json.dumps({'main':base,'scenarios':refs},indent=2),encoding='utf-8')
    print(f'Local sandbox prepared: {dest}')
    print(f'Scenario commits: {manifest}')
    print('No remote changes were made. See docs/PUBLISH.md for the manual push steps.')


if __name__=='__main__':
    main()
