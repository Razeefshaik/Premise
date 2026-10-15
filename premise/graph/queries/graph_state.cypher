OPTIONAL MATCH (s:GraphState {id: 'state'})
RETURN s.rev AS rev, s.ingest_state AS ingest_state, s.main_sha AS main_sha, s.warnings_json AS warnings_json
