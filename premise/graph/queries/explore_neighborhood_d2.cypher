MATCH p=(focus:Entity {id:$focus})-[:REQUIRES|PROVIDES|RELIES_ON|ABOUT|GOVERNS|ACCOUNTABLE_FOR|OWNS|MEMBER_OF|LHS|RHS|ATTESTED|DEPENDS_ON*0..2]-(n:Entity)
WHERE all(v IN nodes(p) WHERE v.retired_rev IS NULL AND any(label IN labels(v) WHERE label IN $allowed_labels))
  AND any(label IN labels(n) WHERE label IN $labels)
WITH n, min(length(p)) AS distance
WITH n, distance, coalesce(head([r IN $ranks WHERE r.id=n.id | r.score]), 0.0) AS pagerank
RETURN n.id AS id, labels(n) AS labels, n.title AS title, n.statement AS statement,
       n.text AS text, n.name AS name, n.tier AS tier, n.status AS status, n.value AS value, distance, pagerank
ORDER BY distance, pagerank DESC, id
LIMIT $limit
