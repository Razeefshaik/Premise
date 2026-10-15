// Q2b. For guarantees that are broken or unknown: accepted decisions that promise or rely on them,
// the services they are about, criticality tiers, and callers exposed through DEPENDS_ON (up to 3 hops).
UNWIND $guarantees AS gid
MATCH (g:Guarantee {id: gid})
OPTIONAL MATCH (pd:Decision {status: 'accepted'})-[:PROVIDES]->(g)
OPTIONAL MATCH (rd:Decision {status: 'accepted'})-[:RELIES_ON]->(g)
OPTIONAL MATCH (g)-[:ABOUT]->(s:Service)
OPTIONAL MATCH (pd)-[:GOVERNS]->(ps:Service)
OPTIONAL MATCH (rd)-[:GOVERNS]->(rs:Service)
OPTIONAL MATCH (caller:Service)-[:DEPENDS_ON*1..3]->(s)
RETURN g.id AS guarantee,
       collect(DISTINCT pd.id) AS promised_by,
       collect(DISTINCT rd.id) AS relied_on_by,
       collect(DISTINCT s.id) AS about,
       [t IN collect(DISTINCT s.tier) + collect(DISTINCT ps.tier) + collect(DISTINCT rs.tier) WHERE t IS NOT NULL] AS tiers,
       collect(DISTINCT caller.id) AS exposed_callers
ORDER BY guarantee
