MATCH (a:Entity)-[r:REQUIRES|PROVIDES|RELIES_ON|ABOUT|GOVERNS|ACCOUNTABLE_FOR|OWNS|MEMBER_OF|LHS|RHS|ATTESTED|DEPENDS_ON]->(b:Entity)
WHERE a.id IN $ids AND b.id IN $ids AND a.retired_rev IS NULL AND b.retired_rev IS NULL
RETURN DISTINCT a.id AS source, b.id AS target, type(r) AS type
ORDER BY source, target, type
