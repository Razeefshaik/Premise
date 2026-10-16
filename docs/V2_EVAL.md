# Phase 2 synthetic evaluation

80 synthetic snippets; frozen 40/40 split. **Razeef's hand review is pending.**
These small, author-labeled samples do not establish production accuracy.
Model metrics replay actual local Codex outputs; seconds are recorded inference time, not replay time.
Requested CLI default does not identify the resolved backend model.

E1 claim matching ignores a title's terminal full stop/case and absent optional nulls; governs, guarantees, assumption checks and requirement indexes must match. Literal title punctuation remains part of annotated-field accuracy.

Corpus SHA256: `26e6e37e9a1bb3ab78267ac07e8ebcc3aeb0ff355024e6eb00057709064bc7a5`

| Split | Extractor | Precision | Recall | Exact quotes | Field accuracy | Schema validity | Calls | Recorded seconds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| tune | E3 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 | 11 | 99.450 |
| tune | K2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 3 | 25.054 |
| tune | E1 | 1.000 | 1.000 | 1.000 | 0.857 | 1.000 | 3 | 30.484 |
| tune | E2 | 1.000 | 1.000 | 1.000 | 1.000 | n/a | 0 | 0.000 |
| holdout | E3 | 1.000 | 1.000 | 1.000 | 0.750 | 1.000 | 6 | 48.240 |
| holdout | K2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 3 | 23.096 |
| holdout | E1 | 1.000 | 1.000 | 1.000 | 0.857 | 1.000 | 3 | 26.878 |
| holdout | E2 | 1.000 | 1.000 | 1.000 | 1.000 | n/a | 0 | 0.000 |

tune: injected grounded candidates = 0; identity cases 4/4.
Grounding rejections: {"E3": {"source_instruction": 2}, "K2": {"unapproved_relation": 1, "source_instruction": 1}, "E1": {}, "E2": {}}

holdout: injected grounded candidates = 0; identity cases 4/4.
Grounding rejections: {"E3": {}, "K2": {"unapproved_relation": 1, "source_instruction": 1}, "E1": {}, "E2": {}}

Floor failures: none

Full mismatch details: run `python -m premise_v2.cli eval --gold` (JSON output).
