CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node, score
WHERE node.retired_rev IS NULL
RETURN node.id AS id, labels(node) AS labels, node.search_text AS text, score
ORDER BY score DESC, id LIMIT $limit
