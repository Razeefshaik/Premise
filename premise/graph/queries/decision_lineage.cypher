MATCH (d:Decision {id:$id})-[r:PROVIDES|RELIES_ON]->(g:Guarantee)
OPTIONAL MATCH p=(g)-[:REQUIRES*1..6]->(a:Assumption)
OPTIONAL MATCH (a)-[:LHS|RHS]->(f:Fact)
RETURN d.id AS decision, type(r) AS role, g.id AS guarantee,
       CASE WHEN p IS NULL THEN [] ELSE [n IN nodes(p) | n.id] END AS chain,
       a.id AS assumption, collect(DISTINCT f.id) AS facts
ORDER BY guarantee, assumption
