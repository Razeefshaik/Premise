MATCH (f:Fact)
WHERE f.retired_rev IS NULL
RETURN f.id AS id, f.file AS file, f.line AS line, f.key AS key, f.value AS value,
       f.value_type AS value_type, f.controlled_by AS controlled_by, f.owner AS owner
ORDER BY id
