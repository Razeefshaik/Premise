// Assumptions whose predicate reads at least one of the given facts.
MATCH (a:Assumption)-[:LHS|RHS]->(f:Fact)
WHERE f.id IN $facts
RETURN DISTINCT a.id AS id
ORDER BY id
