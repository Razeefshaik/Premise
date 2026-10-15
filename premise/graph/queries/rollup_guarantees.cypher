// Q2a. Three valued AND over every prerequisite of each guarantee.
// $violated and $unknown hold assumption ids from E1 (unknown = unevaluable or unverified).
// broken if any reachable assumption is violated, else unknown if any is unknown, else holds.
// The witness is the shortest chain to a violated assumption if one exists, else to an unknown one.
UNWIND $guarantees AS gid
MATCH (g:Guarantee {id: gid})
OPTIONAL MATCH p = (g)-[:REQUIRES*1..6]->(a:Assumption)
WHERE a.id IN $violated OR a.id IN $unknown
WITH g, p, CASE WHEN a IS NULL THEN 2 WHEN a.id IN $violated THEN 0 ELSE 1 END AS rank
ORDER BY rank, length(p)
WITH g, collect(rank) AS ranks, head(collect(p)) AS witness
RETURN g.id AS guarantee, g.statement AS statement,
       CASE WHEN 0 IN ranks THEN 'broken' WHEN 1 IN ranks THEN 'unknown' ELSE 'holds' END AS status,
       CASE WHEN witness IS NULL THEN [] ELSE [n IN nodes(witness) | n.id] END AS chain
ORDER BY guarantee
