MATCH (n:Entity {id:$id})-[:ABOUT|GOVERNS]->(s:Service)
WHERE s.retired_rev IS NULL
RETURN DISTINCT s.id AS id ORDER BY id
