// Q3. Who should review a decision. Active accountable people first; if none are active,
// active current members of the teams owning the governed services, ranked by recent authored evidence.
MATCH (d:Decision {id: $decision_id})
OPTIONAL MATCH (p:Person)-[:ACCOUNTABLE_FOR]->(d)
WITH d, collect(p) AS acc
WITH d,
     [x IN acc WHERE x.status = 'active' | x.id] AS active_accountable,
     [x IN acc WHERE x.status <> 'active' | x.id] AS gone
OPTIONAL MATCH (d)-[:GOVERNS]->(s:Service)<-[:OWNS]-(t:Team)<-[m:MEMBER_OF]-(c:Person)
WHERE c.status = 'active' AND m.until IS NULL
OPTIONAL MATCH (c)-[:AUTHORED]->(src:Source)<-[:PART_OF]-(:Passage)-[:MENTIONS]->(s)
WHERE src.ts >= $since
WITH d, active_accountable, gone, c, t, count(DISTINCT src) AS evidence
ORDER BY evidence DESC, c.id ASC
RETURN active_accountable, gone,
       [x IN collect({person: c.id, team: t.id, evidence: evidence}) WHERE x.person IS NOT NULL] AS candidates
