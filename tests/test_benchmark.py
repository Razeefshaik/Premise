import hashlib
import json
from pathlib import Path
from fastapi.testclient import TestClient
from premise.benchmark.run import ROOT,dataset,run,score
from premise.config import Settings
from premise.web.app import create_app


class RecordedEmbeddings:
    def __init__(self):
        self.data=json.loads((ROOT/'bench/recorded_embeddings.json').read_text())
        self.spec=self.data['spec']

    def encode(self,text):
        return self.data['vectors'][hashlib.sha256(text.encode()).hexdigest()]


def test_frozen_dataset_ids_and_split(kestrel):
    data,manifest=dataset()
    ids={r['id'] for r in kestrel.read('MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id')}
    assert len(data['questions'])==60 and manifest['questions']==60
    assert set().union(*(set(q['gold']) for q in data['questions'])) <= ids


def test_three_questions_real_vector_index_cleanup_and_determinism(kestrel):
    questions=[q for q in dataset()[0]['questions'] if q['split']=='dev'][:2]+[q for q in dataset()[0]['questions'] if q['kind']=='brain' and q['split']=='dev'][:1]
    def counts():
        # Two linear counts avoid a Cartesian product under the server's 1s timeout.
        return (kestrel.read('MATCH (n) RETURN count(n) AS n'),
                kestrel.read('MATCH ()-[r]->() RETURN count(r) AS n'))
    before=counts()
    result=run(kestrel,questions=questions,encoder=RecordedEmbeddings())
    again=run(kestrel,questions=questions,encoder=RecordedEmbeddings())
    assert len(result['rows'])==21 and len(result['summary'])==21
    assert result['vector_namespace'].startswith('premise_bench_vectors_')
    assert result['vector_namespace'] not in kestrel.graph.client.execute_command('GRAPH.LIST')
    assert before==counts()
    for a,b in zip(result['rows'],again['rows']):
        if a['system'] in {'graph','keyword'}:
            assert a['predicted']==b['predicted']
        assert all(0<=a[k]<=1 for k in ('precision','recall','f1','exact'))
        assert a['ms']>=0 and a['queries']
    assert score([],[])['exact']==1 and score(['extra'],[])['f1']==0


def test_benchmark_page_and_recorded_trace(kestrel):
    with TestClient(create_app(kestrel,Settings(poll_enabled=False,llm_provider='none'))) as http:
        assert http.get('/benchmark').status_code==200
        assert len(http.get('/api/benchmark/questions').json()['questions'])==60
        result=http.get('/api/benchmark').json()
        assert result['recorded'] and result['queries'] and len(result['rows'])==420
