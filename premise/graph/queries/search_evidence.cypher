CALL db.idx.fulltext.queryNodes('Passage', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(s:Source)
WHERE node.retired_rev IS NULL
OPTIONAL MATCH (node)-[:MENTIONS]->(e:Entity)
RETURN node.id AS id, node.text AS text, node.start_line AS line, s.path AS path,
       s.url AS url, collect(DISTINCT e.id) AS mentions, score
ORDER BY score DESC, id LIMIT $limit
