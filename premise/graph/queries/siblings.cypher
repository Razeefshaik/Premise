// Guarantees provided by the same accepted decisions as the affected ones, but not affected themselves,
// together with the accepted decisions that rely on them. These are evaluated, not assumed healthy.
MATCH (pd:Decision {status: 'accepted'})-[:PROVIDES]->(g:Guarantee)
WHERE g.id IN $affected
MATCH (pd)-[:PROVIDES]->(sib:Guarantee)
WHERE NOT sib.id IN $affected
MATCH (rd:Decision {status: 'accepted'})-[:RELIES_ON]->(sib)
RETURN DISTINCT sib.id AS guarantee, rd.id AS decision, pd.id AS provider
ORDER BY decision, guarantee
