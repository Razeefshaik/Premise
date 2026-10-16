MATCH (d:Decision)-[:PROVIDES|RELIES_ON]->(g:Guarantee)
WHERE g.id IN $ids AND d.retired_rev IS NULL
RETURN DISTINCT d.id AS id ORDER BY id
