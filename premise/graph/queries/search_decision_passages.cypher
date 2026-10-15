// Plain text retrieval baseline: fulltext over passages of ADR sources only.
CALL db.idx.fulltext.queryNodes('Passage', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(src:Source {kind: 'adr'})
RETURN DISTINCT src.decision AS decision, max(score) AS score
ORDER BY score DESC
