MATCH (s:Source) WHERE s.id IN $ids
OPTIONAL MATCH (p:Passage)-[:PART_OF]->(s)
RETURN s.id AS id, s.path AS path, s.url AS url, coalesce(min(p.start_line),1) AS line
ORDER BY id
