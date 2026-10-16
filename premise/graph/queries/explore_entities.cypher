MATCH (n:Entity)
WHERE n.retired_rev IS NULL AND any(label IN labels(n) WHERE label IN $labels)
  AND ($ids IS NULL OR n.id IN $ids)
WITH n, coalesce(head([r IN $ranks WHERE r.id=n.id | r.score]), 0.0) AS pagerank
RETURN n.id AS id, labels(n) AS labels, n.title AS title, n.statement AS statement,
       n.text AS text, n.name AS name, n.tier AS tier, n.status AS status, n.value AS value, pagerank
ORDER BY pagerank DESC, id
LIMIT $limit
