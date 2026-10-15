// E1. Evaluate assumptions under an overlay of proposed fact values.
// Predicate assumptions: compare operands; a fact present in the overlay uses the overlay value even when it is null
// (a deleted key), so missing data can never fall back to the old value.
// Manual assumptions: hold only with a current attestation by an active person; otherwise holds is null (unverified).
UNWIND $ids AS aid
MATCH (a:Assumption {id: aid})
OPTIONAL MATCH (a)-[:LHS]->(l:Fact)
OPTIONAL MATCH (a)-[:RHS]->(r:Fact)
OPTIONAL MATCH (p:Person)-[at:ATTESTED]->(a)
WITH a, l, r,
     [x IN collect({person: p.id, status: p.status, on: at.on, review_by: at.review_by}) WHERE x.person IS NOT NULL] AS atts
WITH a, l, r, atts,
     CASE WHEN l IS NULL THEN null
          WHEN any(o IN $overlay WHERE o.fact = l.id) THEN head([o IN $overlay WHERE o.fact = l.id | o.to])
          ELSE l.value END AS lv,
     CASE WHEN r IS NULL THEN a.rhs_const
          WHEN any(o IN $overlay WHERE o.fact = r.id) THEN head([o IN $overlay WHERE o.fact = r.id | o.to])
          ELSE r.value END AS rv
WITH a, l, r, atts, lv, rv,
     ((typeOf(lv) IN ['Integer', 'Float'] AND typeOf(rv) IN ['Integer', 'Float'])
      OR (typeOf(lv) = 'String' AND typeOf(rv) = 'String' AND a.op = '==')) AS comparable,
     any(x IN atts WHERE x.status = 'active' AND x.on <= $now
                     AND (x.review_by IS NULL OR x.review_by >= $now)) AS attested
RETURN a.id AS id, a.check_kind AS kind, a.text AS text,
       l.id AS lhs_fact, lv, a.op AS op, r.id AS rhs_fact, rv, atts,
       CASE WHEN a.check_kind = 'manual' THEN (CASE WHEN attested THEN true ELSE null END)
            WHEN NOT comparable THEN null
            WHEN a.op = '<=' THEN lv <= rv
            WHEN a.op = '<'  THEN lv <  rv
            WHEN a.op = '>=' THEN lv >= rv
            WHEN a.op = '>'  THEN lv >  rv
            WHEN a.op = '==' THEN lv =  rv
            ELSE null END AS holds
ORDER BY id
