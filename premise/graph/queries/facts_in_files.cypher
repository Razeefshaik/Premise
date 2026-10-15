// Registered facts hosted in the given files, with their main branch values.
MATCH (f:Fact)
WHERE f.file IN $files
RETURN f.id AS id, f.file AS file, f.key AS key, f.value AS value, f.controlled_by AS controlled_by, f.line AS line
ORDER BY id
