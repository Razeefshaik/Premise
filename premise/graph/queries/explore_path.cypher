// 4.18.3 rejects undirected shortestPath(), even in WITH/RETURN.
// Keep the requested undirected semantics with a bounded minimum-hop query.
MATCH p=(a:Entity {id:$from})-[:REQUIRES|PROVIDES|RELIES_ON|ABOUT*0..6]-(b:Entity {id:$to})
WHERE all(n IN nodes(p) WHERE n.retired_rev IS NULL AND any(label IN labels(n) WHERE label IN $labels))
WITH p, [n IN nodes(p) | n.id] AS ids
ORDER BY length(p), ids
LIMIT 1
RETURN ids,
       [r IN relationships(p) | {source:startNode(r).id, target:endNode(r).id, type:type(r)}] AS edges,
       true AS allowed
