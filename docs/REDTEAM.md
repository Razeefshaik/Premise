# Red-team regression report

35/35 attacks passed their expected safe outcome in this local run.

Real FalkorDB; GitHub writes use HTTP MockTransport and analyst output uses a FakeAdapter. No remote PRs were created. This finite regression set is not a security certification. Deep/alias YAML and bare-link regressions were reproduced failing before the hardening.

| Id | Category | Expected | Actual | Pass |
| --- | --- | --- | --- | --- |
| RT-01 | prompt\_injection\_yaml | BLOCKED | "BLOCKED" | yes |
| RT-02 | prompt\_injection\_yaml | BLOCKED | "BLOCKED" | yes |
| RT-03 | prompt\_injection\_yaml | BLOCKED | "BLOCKED" | yes |
| RT-04 | prompt\_injection\_yaml | BLOCKED | "BLOCKED" | yes |
| RT-05 | prompt\_injection\_yaml | BLOCKED | "BLOCKED" | yes |
| RT-06 | prompt\_injection\_yaml | BLOCKED | "BLOCKED" | yes |
| RT-07 | prompt\_injection\_pr | failure | "failure" | yes |
| RT-08 | prompt\_injection\_pr | failure | "failure" | yes |
| RT-09 | prompt\_injection\_pr | failure | "failure" | yes |
| RT-10 | link\_injection | no\_active\_link | "\\\\\[click\\\\\]\\\\\(https:\\u200b//evil.example\\\\\)" | yes |
| RT-11 | link\_injection | no\_active\_link | "&lt;https:\\u200b//evil.example&gt;" | yes |
| RT-12 | link\_injection | no\_active\_link | "https:\\u200b//evil.example" | yes |
| RT-13 | link\_injection | no\_active\_link | "w\\u200bww.evil.example" | yes |
| RT-14 | mention\_spam | no\_mention | "\\uff20everyone \\uff20here" | yes |
| RT-15 | mention\_spam | no\_mention | "\\uff20Razeefshaik" | yes |
| RT-16 | path\_traversal | rejected | "rejected" | yes |
| RT-17 | path\_traversal | rejected | "rejected" | yes |
| RT-18 | path\_traversal | rejected | "rejected" | yes |
| RT-19 | path\_traversal | rejected | "rejected" | yes |
| RT-20 | path\_traversal | rejected | "rejected" | yes |
| RT-21 | yaml\_malformed | bounded\_rejection | "NEEDS\_REVIEW" | yes |
| RT-22 | yaml\_huge | bounded\_rejection | "size\_rejected" | yes |
| RT-23 | yaml\_deep | bounded\_rejection | "NEEDS\_REVIEW" | yes |
| RT-24 | yaml\_bomb | bounded\_rejection | "NEEDS\_REVIEW" | yes |
| RT-25 | fake\_attestation | unverified | "unverified" | yes |
| RT-26 | fake\_attestation | unverified | "unverified" | yes |
| RT-27 | analyst\_false\_answer | deterministic | "deterministic" | yes |
| RT-28 | analyst\_false\_answer | deterministic | "deterministic" | yes |
| RT-29 | unknown\_entity | unknown\_or\_not\_in\_graph | "unknown\_entity" | yes |
| RT-30 | unknown\_entity | unknown\_or\_not\_in\_graph | "not\_in\_graph" | yes |
| RT-31 | github\_fork | no\_unsafe\_writes | "no\_fix\_pr" | yes |
| RT-32 | github\_stale | no\_unsafe\_writes | "skipped" | yes |
| RT-33 | github\_outage | no\_unsafe\_writes | "error\_status\_only" | yes |
| RT-34 | mcp\_write | rejected | "rejected" | yes |
| RT-35 | mcp\_write | rejected | "rejected" | yes |
