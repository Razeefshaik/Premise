// Algorithm as a tool: guarantees required by many others score highest.
CALL algo.pageRank('Guarantee', 'REQUIRES') YIELD node, score
RETURN node.id AS guarantee, score
ORDER BY score DESC
LIMIT $limit
