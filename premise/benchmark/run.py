"""Authored, frozen evaluation: structured reasoning versus two passage retrievers.

No answer-generating model, no network APIs and no writes to the decision graph.
Vector indexes live only in uniquely owned temporary graphs.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import time
import uuid

import yaml

from .embedding import ROOT, Embedder
from ..agent.analyst import answer_question
from ..agent.verify import id_tokens
from ..graph.client import GraphClient
from ..graph.recorder import QueryRecorder
from ..graph.tools import GraphTools
from ..reasoning.preflight import check_proposal
from ..scenarios import load_scenarios, scenario_now


def dataset():
    raw = (ROOT / 'bench/dataset.yaml').read_bytes()
    manifest = json.loads((ROOT / 'bench/manifest.json').read_text())
    if hashlib.sha256(raw).hexdigest() != manifest['sha256']:
        raise ValueError('Frozen benchmark dataset hash differs from manifest')
    data = yaml.safe_load(raw)
    questions = data['questions']
    if len(questions) != 60 or len({q['id'] for q in questions}) != 60:
        raise ValueError('Benchmark needs 60 unique questions')
    for split in ('dev', 'test'):
        for kind in ('change', 'brain'):
            if sum(q['split'] == split and q['kind'] == kind for q in questions) != 15:
                raise ValueError('Expected 15 change and 15 Brain questions per split')
    return data, manifest


def score(predicted, gold):
    predicted, gold = set(predicted), set(gold)
    n = len(predicted & gold)
    precision = n / len(predicted) if predicted else float(not gold)
    recall = n / len(gold) if gold else float(not predicted)
    return {'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.,
            'exact': float(predicted == gold)}


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        for kind in (row['kind'], 'all'):
            groups[(row['split'], kind, row['system'], row['k'])].append(row)
    output = []
    for (split, kind, system, k), values in groups.items():
        times = sorted(v['ms'] for v in values)
        output.append({'split': split, 'kind': kind, 'system': system, 'k': k, 'n': len(values),
                       **{key: statistics.mean(v[key] for v in values) for key in ('precision','recall','f1','exact')},
                       'p50_ms': statistics.median(times), 'p95_ms': times[max(0, int(.95 * len(times) + .999) - 1)]})
    return output


def run(client, *, questions=None, encoder=None, download=False):
    data, manifest = dataset()
    questions = questions or data['questions']
    ids = {r['id'] for r in client.read('MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id')}
    missing = set().union(*(set(q['gold']) for q in questions)) - ids
    if missing:
        raise ValueError('Unknown gold ids: ' + ', '.join(sorted(missing)))
    before = client.read('MATCH (s:GraphState) RETURN properties(s) AS state')
    encoder = encoder or Embedder(download=download)
    passages = client.read("MATCH (p:Passage)-[:PART_OF]->(s:Source {kind:'adr'}) WHERE p.retired_rev IS NULL RETURN p.id AS id,p.text AS text,s.decision AS decision ORDER BY id")
    if not passages:
        raise ValueError('No indexed ADR passages')
    vector = client.sibling('premise_bench_vectors_' + uuid.uuid4().hex)
    now = scenario_now(load_scenarios(ROOT / 'scenarios/scenarios.yaml'))
    rows, setup_queries = [], []
    try:
        with QueryRecorder(vector) as setup:
            vector.write("CREATE VECTOR INDEX FOR (p:BenchPassage) ON (p.embedding) OPTIONS {dimension:384, similarityFunction:'cosine'}")
            for p in passages:
                vector.write('CREATE (:BenchPassage {id:$id,text:$text,decision:$decision,embedding:vecf32($embedding)})',
                             {**p, 'embedding': encoder.encode(p['text'])})
            setup_queries = setup.entries
        for q in questions:
            for system, k in [('graph', None), *[(system, k) for system in ('keyword','vector') for k in (3,5,10)]]:
                started = time.perf_counter()
                target = vector if system == 'vector' else client
                with QueryRecorder(target) as trace:
                    if system == 'graph':
                        if q['kind'] == 'change':
                            result = check_proposal(client, changes=q['changes'], include_fixes=False, at_ms=now)
                            predicted = {d['id'] for d in result['decisions']}
                        else:
                            result = answer_question(GraphTools(client, now), q['question'])
                            predicted = id_tokens(result['answer_markdown'])
                    else:
                        if system == 'keyword':
                            terms = re.findall(r'[a-zA-Z0-9_]+', q['question'])[:40]
                            query = ' | '.join(terms) or 'unmatchable_benchmark_empty'
                            found = client.read("CALL db.idx.fulltext.queryNodes('Passage',$q) YIELD node,score MATCH (node)-[:PART_OF]->(s:Source {kind:'adr'}) WHERE node.retired_rev IS NULL RETURN node.id AS id,node.text AS text,s.decision AS decision,score ORDER BY score DESC,id LIMIT $k", {'q': query,'k': k})
                        else:
                            found = vector.read("CALL db.idx.vector.queryNodes('BenchPassage','embedding',$k,vecf32($embedding)) YIELD node,score RETURN node.id AS id,node.text AS text,node.decision AS decision,score ORDER BY score ASC,id", {'k': k, 'embedding': encoder.encode(q['question'])})
                        predicted = ({p['decision'] for p in found} if q['kind'] == 'change' else
                                     id_tokens('\n'.join(p['decision'] + '\n' + p['text'] for p in found)))
                rows.append({'id':q['id'],'split':q['split'],'kind':q['kind'],'system':system,'k':k,
                             'gold':q['gold'],'predicted':sorted(predicted),**score(predicted,q['gold']),
                             'ms':(time.perf_counter()-started)*1000,'queries':trace.entries})
        if before != client.read('MATCH (s:GraphState) RETURN properties(s) AS state'):
            raise ValueError('Decision graph revision changed during benchmark')
        return {'recorded_at':datetime.now(timezone.utc).isoformat(),'graph_state':before,
                'dataset':manifest,'human_review':data['human_review'],'model':encoder.spec,
                'passage_count':len(passages),'corpus_sha256':hashlib.sha256(json.dumps(passages,sort_keys=True).encode()).hexdigest(),
                'vector_namespace':vector.graph_name,'vector_namespace_deleted':True,
                'latency_note':'Client wall time; model initialization and index build excluded. Exact-text embedding cache may be warm. Not a cold inference benchmark.',
                'setup_queries':setup_queries,'rows':rows,'summary':summarize(rows)}
    finally:
        # This client was created here with a fresh uuid; no externally named graph is deleted.
        vector.delete_graph()


def write_report(result):
    folder = ROOT / 'bench/results'
    folder.mkdir(parents=True,exist_ok=True)
    content = json.dumps(result, indent=2, ensure_ascii=False)
    (folder / (result['recorded_at'][:10]+'.json')).write_text(content,encoding='utf-8')
    (folder / 'latest.json').write_text(content,encoding='utf-8')
    lines = ['# Authored synthetic benchmark', '',
             'Measured results, not a general QA claim. Dataset: [60 frozen questions](../bench/dataset.yaml), 30 dev / 30 test, each half changes and Brain questions. Gold labels were authored before running the systems. Human review is pending Razeef.', '',
             '| Test subset | System | k | Precision | Recall | F1 | Exact | p50 ms | p95 ms |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in result['summary']:
        if r['split'] == 'test':
            lines.append(f"| {r['kind']} | {r['system']} | {r['k'] or '—'} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | {r['exact']:.3f} | {r['p50_ms']:.1f} | {r['p95_ms']:.1f} |")
    lines += ['', '## Interpretation and limits', '',
              '- The company and questions are synthetic and written by us. Test has related parameter and paraphrase variants of dev questions; it is not an independent-company generalization test.',
              '- Graph reasoning knows the authored dependency structure. This measures what that structure buys; it does not establish general intelligence or compare generated natural-language answers.',
              '- Keyword and vector use exactly the same active ADR passages and return top-k passages. Change predictions are their cited decision ids. Brain predictions are recognizable entity ids in the passages plus decision citations; graph predictions are ids in deterministic answer prose. Extra ids reduce precision.',
              '- Macro metrics include exact set match. Both-empty sets score 1; a one-sided empty set scores 0. Dev and test are reported separately in the JSON. All k values (3, 5, 10) are published.',
              '- Vector retrieval uses the pinned all-MiniLM-L6-v2 checkpoint with CPU ONNX inference, mask-aware mean pooling and L2 normalization. No LLM or embedding API is called. [Model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).',
              '- A real FalkorDB cosine index is built in a temporary namespace and deleted. A runtime identity-vector check returned distance 0 for an identical vector and 1 for an orthogonal vector; scores are ordered ascending on this runtime.',
              '- '+result['latency_note'],
              '- ADR-012, ADR-015 and ADR-018 are the authored downstream lexical-gap cases. Their appearance in a result depends on actual retrieval; no special scoring boost is applied.',
              '', 'Recorded: '+result['recorded_at']+'. Full queries, per-question outputs, timings, checkpoint revision and corpus/dataset hashes: [JSON](../bench/results/latest.json).']
    (ROOT / 'docs/BENCHMARK.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
