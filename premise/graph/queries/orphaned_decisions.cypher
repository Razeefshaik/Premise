MATCH (d:Decision {status:'accepted'})-[:GOVERNS]->(s:Service)
OPTIONAL MATCH (p:Person)-[:ACCOUNTABLE_FOR]->(d)
WITH d, collect(DISTINCT s.id) AS services, min(s.tier) AS tier, collect(DISTINCT p) AS people
WHERE none(p IN people WHERE p.status='active')
RETURN d.id AS decision, d.title AS title, services, tier, [p IN people | p.id] AS departed
ORDER BY tier, decision
