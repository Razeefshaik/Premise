// Every (guarantee, assumption) pair joined by a REQUIRES chain of 1 to 6 hops.
// Used upward (ancestors of touched assumptions) and downward (closure of checked guarantees).
MATCH (g:Guarantee)-[:REQUIRES*1..6]->(a:Assumption)
WHERE ($assumptions IS NULL OR a.id IN $assumptions)
  AND ($guarantees IS NULL OR g.id IN $guarantees)
RETURN DISTINCT g.id AS guarantee, a.id AS assumption
ORDER BY guarantee, assumption
