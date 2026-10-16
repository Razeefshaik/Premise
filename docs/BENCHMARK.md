# Authored synthetic benchmark

Measured results, not a general QA claim. Dataset: [60 frozen questions](../bench/dataset.yaml), 30 dev / 30 test, each half changes and Brain questions. Gold labels were authored before running the systems. Human review is pending Razeef.

| Test subset | System | k | Precision | Recall | F1 | Exact | p50 ms | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| change | graph | — | 1.000 | 1.000 | 1.000 | 1.000 | 43.7 | 52.1 |
| all | graph | — | 0.731 | 0.967 | 0.789 | 0.600 | 27.2 | 49.7 |
| change | keyword | 3 | 0.278 | 0.317 | 0.257 | 0.000 | 2.7 | 3.0 |
| all | keyword | 3 | 0.221 | 0.403 | 0.247 | 0.000 | 2.6 | 3.1 |
| change | keyword | 5 | 0.254 | 0.383 | 0.266 | 0.000 | 2.6 | 3.1 |
| all | keyword | 5 | 0.179 | 0.436 | 0.216 | 0.000 | 2.6 | 3.1 |
| change | keyword | 10 | 0.182 | 0.450 | 0.238 | 0.000 | 2.8 | 3.0 |
| all | keyword | 10 | 0.126 | 0.469 | 0.178 | 0.000 | 2.7 | 3.0 |
| change | vector | 3 | 0.500 | 0.467 | 0.457 | 0.200 | 12.8 | 33.4 |
| all | vector | 3 | 0.296 | 0.383 | 0.297 | 0.100 | 11.5 | 15.7 |
| change | vector | 5 | 0.300 | 0.467 | 0.343 | 0.000 | 15.7 | 24.2 |
| all | vector | 5 | 0.188 | 0.400 | 0.232 | 0.000 | 15.0 | 17.4 |
| change | vector | 10 | 0.241 | 0.583 | 0.312 | 0.000 | 4.2 | 5.1 |
| all | vector | 10 | 0.150 | 0.486 | 0.206 | 0.000 | 4.2 | 5.1 |
| brain | graph | — | 0.461 | 0.933 | 0.578 | 0.200 | 20.2 | 23.8 |
| brain | keyword | 3 | 0.163 | 0.489 | 0.237 | 0.000 | 2.5 | 3.2 |
| brain | keyword | 5 | 0.104 | 0.489 | 0.165 | 0.000 | 2.6 | 3.4 |
| brain | keyword | 10 | 0.070 | 0.489 | 0.118 | 0.000 | 2.7 | 3.2 |
| brain | vector | 3 | 0.091 | 0.300 | 0.138 | 0.000 | 8.9 | 12.7 |
| brain | vector | 5 | 0.076 | 0.333 | 0.120 | 0.000 | 14.8 | 17.2 |
| brain | vector | 10 | 0.058 | 0.389 | 0.099 | 0.000 | 4.2 | 5.4 |

## Interpretation and limits

- The company and questions are synthetic and written by us. Test has related parameter and paraphrase variants of dev questions; it is not an independent-company generalization test.
- Graph reasoning knows the authored dependency structure. This measures what that structure buys; it does not establish general intelligence or compare generated natural-language answers.
- Keyword and vector use exactly the same active ADR passages and return top-k passages. Change predictions are their cited decision ids. Brain predictions are recognizable entity ids in the passages plus decision citations; graph predictions are ids in deterministic answer prose. Extra ids reduce precision.
- Macro metrics include exact set match. Both-empty sets score 1; a one-sided empty set scores 0. Dev and test are reported separately in the JSON. All k values (3, 5, 10) are published.
- Vector retrieval uses the pinned all-MiniLM-L6-v2 checkpoint with CPU ONNX inference, mask-aware mean pooling and L2 normalization. No LLM or embedding API is called. [Model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
- A real FalkorDB cosine index is built in a temporary namespace and deleted. A runtime identity-vector check returned distance 0 for an identical vector and 1 for an orthogonal vector; scores are ordered ascending on this runtime.
- Client wall time; model initialization and index build excluded. Exact-text embedding cache may be warm. Not a cold inference benchmark.
- ADR-012, ADR-015 and ADR-018 are the authored downstream lexical-gap cases. Their appearance in a result depends on actual retrieval; no special scoring boost is applied.

Recorded: 2026-10-16T22:37:17.664997+00:00. Full queries, per-question outputs, timings, checkpoint revision and corpus/dataset hashes: [JSON](../bench/results/latest.json).
