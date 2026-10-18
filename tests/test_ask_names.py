from premise.agent.analyst import answer_question
from premise.config import Settings
from premise.graph.tools import GraphTools
from conftest import NOW


def test_deterministic_ask_names_reviewers_from_the_graph(kestrel):
    tools = GraphTools(kestrel, NOW)
    rows = tools.call('decision_lineage', {'id': 'ADR-012'})
    assert rows['names']['p_jun'] == 'Jun Park'
    assert rows['names']['p_anika'] == 'Anika Rao'
    answer = answer_question(tools, 'Why ADR-012, and who owns it now?', Settings(public_demo=True))
    assert answer['mode'] == 'deterministic' and answer['outcome'] == 'answered_with_path'
    assert 'Jun Park (p_jun)' in answer['answer_markdown']
    assert 'Anika Rao (p_anika)' in answer['answer_markdown']
    assert 'G_CHARGE_ONCE' in answer['answer_markdown'] and 'G_DEDUPE' in answer['answer_markdown']
    assert answer['sources']
