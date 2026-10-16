MATCH (n:Entity {id:$id})
WHERE n.retired_rev IS NULL AND any(label IN labels(n) WHERE label IN $labels)
RETURN n.id AS id, labels(n) AS labels, n.title AS title, n.statement AS statement,
       n.text AS text, n.name AS name, n.tier AS tier, n.status AS status, n.value AS value
