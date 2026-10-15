MATCH (t:Team)-[:OWNS]->(s:Service {id:$id})
OPTIONAL MATCH (p:Person)-[m:MEMBER_OF]->(t)
WHERE p.status='active' AND m.until IS NULL
OPTIONAL MATCH (p)-[:AUTHORED]->(src:Source)<-[:PART_OF]-(:Passage)-[:MENTIONS]->(s)
WHERE src.ts >= $since
RETURN s.id AS service, t.id AS team, t.name AS team_name, p.id AS person, p.name AS name,
       count(DISTINCT src) AS evidence, collect(DISTINCT src.id) AS sources
ORDER BY evidence DESC, person
