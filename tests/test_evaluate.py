"""T1, T2, T3, T6: assumption evaluation and three valued rollup, on small graphs built directly in FalkorDB."""
import pytest

from premise.ingest.load import ensure_indexes
from premise.reasoning.evaluate import evaluate, evaluate_assumptions, rollup

from conftest import NOW, SANDBOX
from helpers import scenario

DAY = 24 * 3600 * 1000


@pytest.fixture
def mini(new_graph):
    """Facts x=10, y=20, s='blue'; one assumption per operator form; manual assumptions with various attestations."""
    c = new_graph()
    c.write("MERGE (s:GraphState {id:'state'}) SET s.ingest_state='ready', s.rev=1")
    ensure_indexes(c)
    c.write("""
    CREATE (x:Entity:Fact {id:'x', value:10}), (y:Entity:Fact {id:'y', value:20}), (s:Entity:Fact {id:'s', value:'blue'}),
      (alive:Entity:Person {id:'alive', status:'active'}), (gone:Entity:Person {id:'gone', status:'departed'})
    WITH x, y, s, alive, gone
    UNWIND [['LT','<'],['LE','<='],['EQ','=='],['GE','>='],['GT','>']] AS o
    CREATE (a:Entity:Assumption {id:'ff_'+o[0], check_kind:'predicate', op:o[1]})-[:LHS]->(x), (a)-[:RHS]->(y)
    CREATE (k:Entity:Assumption {id:'fc_'+o[0], check_kind:'predicate', op:o[1], rhs_const:10})-[:LHS]->(x)
    """)
    c.write("""
    MATCH (s:Fact {id:'s'}), (x:Fact {id:'x'}), (alive:Person {id:'alive'}), (gone:Person {id:'gone'})
    CREATE (:Entity:Assumption {id:'str_eq', check_kind:'predicate', op:'==', rhs_const:'blue'})-[:LHS]->(s),
           (:Entity:Assumption {id:'str_lt', check_kind:'predicate', op:'<', rhs_const:'red'})-[:LHS]->(s),
           (:Entity:Assumption {id:'mixed', check_kind:'predicate', op:'<', rhs_const:'10'})-[:LHS]->(x),
           (:Entity:Assumption {id:'badop', check_kind:'predicate', op:'!=', rhs_const:3})-[:LHS]->(x),
           (:Entity:Assumption {id:'m_none', check_kind:'manual'}),
           (alive)-[:ATTESTED {on:$past, review_by:$future}]->(:Entity:Assumption {id:'m_ok', check_kind:'manual'}),
           (alive)-[:ATTESTED {on:$past, review_by:$past2}]->(:Entity:Assumption {id:'m_expired', check_kind:'manual'}),
           (gone)-[:ATTESTED {on:$past, review_by:$future}]->(:Entity:Assumption {id:'m_gone', check_kind:'manual'}),
           (alive)-[:ATTESTED {on:$future, review_by:$future2}]->(:Entity:Assumption {id:'m_future', check_kind:'manual'})
    """, {"past": NOW - 30 * DAY, "past2": NOW - DAY, "future": NOW + 30 * DAY, "future2": NOW + 60 * DAY})
    return c


def states(c, ids, overlay=None):
    return {k: v.state for k, v in evaluate_assumptions(c, ids, overlay or {}, NOW).items()}


def test_T1_operators_fact_vs_fact_and_const(mini):
    got = states(mini, [f"ff_{o}" for o in ("LT", "LE", "EQ", "GE", "GT")] + [f"fc_{o}" for o in ("LT", "LE", "EQ", "GE", "GT")])
    # x=10, y=20: 10<20, 10<=20 hold; 10==20, 10>=20, 10>20 violated. Against const 10: <= == >= hold.
    assert got == {"ff_LT": "holding", "ff_LE": "holding", "ff_EQ": "violated", "ff_GE": "violated", "ff_GT": "violated",
                   "fc_LT": "violated", "fc_LE": "holding", "fc_EQ": "holding", "fc_GE": "holding", "fc_GT": "violated"}


def test_T1_overlay_changes_the_answer(mini):
    got = states(mini, ["ff_LT", "ff_GT"], {"x": 25})
    assert got == {"ff_LT": "violated", "ff_GT": "holding"}


def test_T2_deleted_fact_is_unevaluable_not_the_old_value(mini):
    # Overlay says x was deleted (None). The old value 10 must not be used.
    assert states(mini, ["fc_LE", "ff_LT"], {"x": None}) == {"fc_LE": "unevaluable", "ff_LT": "unevaluable"}


def test_T2_type_mismatch_and_unknown_operator_are_unevaluable(mini):
    got = states(mini, ["str_eq", "str_lt", "mixed", "badop"])
    assert got == {"str_eq": "holding", "str_lt": "unevaluable", "mixed": "unevaluable", "badop": "unevaluable"}
    assert states(mini, ["fc_LE"], {"x": "10"}) == {"fc_LE": "unevaluable"}


def test_T6_manual_assumption_needs_a_current_attestation_by_an_active_person(mini):
    assert states(mini, ["m_none", "m_ok", "m_expired", "m_gone", "m_future"]) == {
        "m_none": "unverified", "m_ok": "holding", "m_expired": "unverified", "m_gone": "unverified", "m_future": "unverified"}


def test_T6_three_valued_and(mini):
    mini.write("""
    MATCH (v:Assumption {id:'ff_GT'}), (u:Assumption {id:'m_none'}), (h:Assumption {id:'m_ok'}), (h2:Assumption {id:'ff_LT'})
    CREATE (b:Entity:Guarantee {id:'G_BROKEN'})-[:REQUIRES]->(v), (b)-[:REQUIRES]->(u),
           (k:Entity:Guarantee {id:'G_UNKNOWN'})-[:REQUIRES]->(u), (k)-[:REQUIRES]->(h),
           (ok:Entity:Guarantee {id:'G_OK'})-[:REQUIRES]->(h), (ok)-[:REQUIRES]->(h2),
           (top:Entity:Guarantee {id:'G_TOP'})-[:REQUIRES]->(k), (top)-[:REQUIRES]->(ok)
    """)
    a = evaluate_assumptions(mini, ["ff_GT", "m_none", "m_ok", "ff_LT"], {}, NOW)
    got = {g: v["status"] for g, v in rollup(mini, ["G_BROKEN", "G_UNKNOWN", "G_OK", "G_TOP"], a).items()}
    assert got == {"G_BROKEN": "broken", "G_UNKNOWN": "unknown", "G_OK": "holds", "G_TOP": "unknown"}


def test_T3_assessing_a_change_never_writes_to_main_facts(kestrel):
    before = kestrel.read("MATCH (f:Fact) RETURN f.id AS id, f.value AS v ORDER BY id")
    scenario(kestrel, SANDBOX, "S1")
    scenario(kestrel, SANDBOX, "S11")
    after = kestrel.read("MATCH (f:Fact) RETURN f.id AS id, f.value AS v ORDER BY id")
    assert before == after
    main = evaluate(kestrel, {"paylane.retry_window_hours": 24}, NOW)  # same value as main: a no-op overlay
    assert main.assumptions["A_RETRY_WINDOW"].state == "holding"
