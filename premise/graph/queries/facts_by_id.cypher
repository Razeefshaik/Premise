MATCH (f:Fact)
WHERE f.id IN $ids
RETURN f.id AS id, f.file AS file, f.key AS key, f.value AS value, f.value_type AS value_type,
       f.controlled_by AS controlled_by, f.line AS line
ORDER BY id
