# ext/: Premise v2 extensions

v1 ingest ignores this folder. Premise v2 reads it. Every change here goes through a reviewed pull request.

| File | Purpose |
| --- | --- |
| `relations.yaml` | Relation registry. Kind 1 `reasoning` entries are locked to the code constant; Kind 2 `knowledge` entries can grow |
| `identities.yaml` | Explicit mapping from Slack, Jira and GitHub accounts to people |
| `fact_units.yaml` | Unit of every registered fact, used to convert "3 days" into 72 hours |
| `fact_aliases.yaml` | How people talk about each fact, used to find claims in chat and tickets |
| `partners.yaml` | Registered descriptive partner entities for v2; never added to the v1 decision graph |
