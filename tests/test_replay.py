import hashlib
import importlib.util
import json
from pathlib import Path
from conftest import ROOT,SERVER_HOST

spec=importlib.util.spec_from_file_location('export_replay',ROOT/'scripts/export_replay.py')
exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)


def test_real_export_index_files_and_banner(tmp_path,falkordb_port,new_graph):
    result=exporter.export_site(tmp_path/'site',SERVER_HOST,falkordb_port)
    data=tmp_path/'site/data'
    assert len(result['requests'])>100
    for filename in result['requests'].values():
        payload=(data/filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest()==result['files'][filename]
        assert 'queries' in json.loads(payload)
    assert result['graph'] not in new_graph().graph.client.execute_command('GRAPH.LIST')
    for filename in ('index.html','explore.html','benchmark.html','continuity.html'):
        html=(tmp_path/'site'/filename).read_text(encoding='utf8')
        assert 'Replay of recorded FalkorDB results.' in html and 'data-source="replay"' in html
        assert 'src="/static/' not in html
    # The landing is the front door: no CDN, links into the recorded Explorer, every fire chip recorded.
    landing=(tmp_path/'site/index.html').read_text(encoding='utf8')
    assert 'Premise finds consequences.' in landing and './explore.html?story=1' in landing
    assert 'cdn.jsdelivr' not in landing and 'href="/entities/' not in landing and 'id="ask-form"' not in landing
    assert (tmp_path/'site/static/models/brain.bin').exists() and (tmp_path/'site/static/vendor/three-0.160.0/three.module.min.js').exists()
    plate=json.loads(landing.split('id="plate-data">',1)[1].split('</script>',1)[0])
    for preset in plate['presets']:
        changes=[{'fact':f,'value':v} for f,v in sorted(preset['values'].items())]
        assert exporter.request_key('/api/check',body={'changes':changes}) in result['requests'],preset['id']
    # Match browser JSON.stringify for integral numeric fix values.
    assert exporter.request_key('/api/check',body={'changes':[{'fact':'x','value':72.0}]})==exporter.request_key('/api/check',body={'changes':[{'fact':'x','value':72}]})
