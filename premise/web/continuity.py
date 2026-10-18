"""Read-only hypothetical departure; native algorithms on an owned temporary projection."""
import uuid
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from ..graph.client import GraphClient, GraphUnavailable
from ..graph.recorder import QueryRecorder
from ..graph.tools import GraphTools
from ..reasoning.assess import _route
from .graph_api import GraphRoute

DAY_MS=86_400_000


def projection(client, person):
    nodes=client.read("MATCH (n:Entity) WHERE n.retired_rev IS NULL AND ((n:Person AND n.status='active') OR n:Service OR (n:Decision AND n.status='accepted')) RETURN n.id AS id,labels(n) AS labels")
    ids=[n['id'] for n in nodes]
    edges=client.read("MATCH (a:Entity)-[r:ACCOUNTABLE_FOR|GOVERNS]->(b:Entity) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id AS source,b.id AS target,type(r) AS type",{'ids':ids})
    edges+=client.read("MATCH (p:Person)-[m:MEMBER_OF]->(:Team)-[:OWNS]->(s:Service) WHERE p.id IN $ids AND s.id IN $ids AND m.until IS NULL RETURN p.id AS source,s.id AS target,'TEAM_OWNERSHIP' AS type",{'ids':ids})
    graph=client.sibling('premise_proj_'+uuid.uuid4().hex)
    with QueryRecorder(graph) as trace:
        try:
            for label in ('Person','Service','Decision'):
                graph.write(f'UNWIND $nodes AS row CREATE (n:{label} {{id:row.id}})',{'nodes':[n for n in nodes if label in n['labels']]})
            graph.write('UNWIND $edges AS e MATCH (a {id:e.source}),(b {id:e.target}) MERGE (a)-[:LINK]->(b) MERGE (b)-[:LINK]->(a)',{'edges':edges})
            scores=graph.read('CALL algo.betweenness() YIELD node,score RETURN node.id AS id,score ORDER BY score DESC,id')
            before=graph.read('CALL algo.WCC() YIELD node,componentId RETURN node.id AS id,componentId')
            graph.write('MATCH (p:Person {id:$id}) DETACH DELETE p',{'id':person})
            after=graph.read('CALL algo.WCC() YIELD node,componentId RETURN node.id AS id,componentId')
            def isolated(rows, excluded):
                components={r['id']:r['componentId'] for r in rows}
                with_person={components[n['id']] for n in nodes if 'Person' in n['labels'] and n['id'] in components and n['id'] not in excluded}
                return {n['id'] for n in nodes if 'Service' in n['labels'] and components[n['id']] not in with_person}
            people_scores=[r for r in scores if any(n['id']==r['id'] and 'Person' in n['labels'] for n in nodes)]
            chosen=next((r for r in people_scores if r['id']==person),None)
            bridge={'score':chosen['score'] if chosen else None,
                    'rank':1+sum(r['score']>chosen['score'] for r in people_scores) if chosen else None,
                    'active_people':len(people_scores)}
            result={'bridge':bridge,'isolated_services':sorted(isolated(after,{person})-isolated(before,set())),
                    'projection':{'namespace':graph.graph_name,'nodes':nodes,'edges':edges,
                    'note':'Active people, services and accepted decisions. Accountable/governs edges plus current membership in service-owning teams. Links are bidirectional for descriptive bridge/WCC analysis; they do not decide guarantee health.'}}
        finally:
            graph.delete_graph()
    return result,[{**q,'graph':graph.graph_name} for q in trace.entries]


def create_continuity_router(client, at_ms=None, *, startup_cache=None):
    router=APIRouter(route_class=GraphRoute)

    @router.get('/api/continuity')
    def continuity(person:str=Query('p_jun',min_length=1,max_length=160)):
        with QueryRecorder(client) as trace:
            projected=[]
            try:
                tools=GraphTools(client,at_ms);tools.guard()
                state=client.named('graph_state')[0]
                people=client.read('MATCH (p:Person) WHERE p.retired_rev IS NULL RETURN p.id AS id,p.name AS name,p.status AS status ORDER BY name')
                if not any(p['id']==person for p in people):
                    return JSONResponse({'error':'unknown_entity','queries':trace.entries},status_code=404)
                before=tools.call('guarantee_health',{})
                after=GraphTools(client,tools.now,gone=[person]).call('guarantee_health',{})
                old={g['id']:g['status'] for g in before['guarantees']}
                changed=[{**g,'before':old[g['id']]} for g in after['guarantees'] if g['status']!=old[g['id']]]
                affected=[r['id'] for r in client.named('explore_decisions',{'ids':[g['id'] for g in changed]})]
                old_assumptions={a['id']:a['state'] for a in before['assumptions']}
                unverified=[a for a in after['assumptions'] if a['state']=='unverified' and old_assumptions[a['id']]!='unverified']
                decisions=client.read("MATCH (d:Decision {status:'accepted'}) WHERE d.retired_rev IS NULL RETURN d.id AS id ORDER BY id")
                orphaned,routing=[],[]
                since=tools.now-tools.since_days*DAY_MS
                for d in decisions:
                    active,_,candidates=_route(client,d['id'],since)
                    remaining,_,alternatives=_route(client,d['id'],since,gone=[person])
                    if active and not remaining:orphaned.append(d['id'])
                    current=active or [c.person for c in candidates]
                    if person in current:
                        routing.append({'id':d['id'],'before':current,'after':remaining or [c.person for c in alternatives]})
                if startup_cache is None:
                    analysis,projected=projection(client,person)
                else:
                    cached = startup_cache.get(person)
                    if not cached or cached[0] != state:
                        raise GraphUnavailable('continuity snapshot unavailable; restart the demo')
                    _, analysis, projected = cached
                if client.named('graph_state')[0]!=state:raise GraphUnavailable('revision changed; retry')
                return {'graph_rev':state['rev'],'person':person,'people':people,'hypothetical':True,
                        'orphaned_decisions':orphaned,'unverified_assumptions':unverified,
                        'changed_guarantees':changed,'reviewer_routing':routing,**analysis,
                        'affected_decisions':affected,
                        'queries':trace.entries+projected}
            except GraphUnavailable:
                return JSONResponse({'error':'graph_not_ready','queries':trace.entries+projected},status_code=503)
    return router
