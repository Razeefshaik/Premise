MATCH (f:Fact)
WHERE f.file = $file AND f.key = $key AND f.retired_rev IS NULL
RETURN f.id AS id, f.file AS file, f.key AS key, f.value AS value, f.value_type AS value_type,
       f.controlled_by AS controlled_by, f.line AS line
ORDER BY id
