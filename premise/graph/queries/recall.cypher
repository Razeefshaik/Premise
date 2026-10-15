MATCH (a:Assessment)-[:FOUND|FLAGGED]->(e:Entity {id:$id})
MATCH (a)-[:OF]->(p:ChangeProposal)
RETURN DISTINCT a.id AS id, a.verdict AS verdict, a.graph_rev AS graph_rev,
       a.head_sha AS head_sha, p.pr_number AS pr, a.created_at AS created_at
ORDER BY created_at DESC LIMIT $limit
