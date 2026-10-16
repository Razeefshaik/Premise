# Leader review follow-up

Review input: `Premise_Code_Review.md` and `test_zz_review_probes.py`, reviewed locally
on October 16, 2026 against commit `8e1cab2`. All five original probes passed before
changes, reproducing the reported behaviour. Their assertions are now regressions in
`tests/test_review_regressions.py`.

| Finding | Resolution |
| --- | --- |
| C1: token in workspace ZIP | Clean source packaging documented and archive inspected. The exposed token must still be revoked/replaced by its owner; no rotation is claimed. The original ZIP in Downloads was not deleted. |
| H1: stale branch overlays unedited main values | Git intake returns head and merge-base file texts. Only facts changed relative to merge base enter the overlay; their old values still come from current main. Real Git and graph-backed regressions cover this. |
| H2: malformed YAML/status loop | Per-file `R_UNPARSEABLE` reasons include source location and require review. Other files remain assessable; incomplete intake offers no fixes. Completed heads are recorded. ERROR heads have graph-backed retry metadata, with 60-second exponential backoff capped at 15 minutes. A main-sync outage uses process-local backoff because the graph may be unavailable. |
| M1: unverified live model API | No Anthropic key is configured, so a real fix-agent/API-ask call remains untested. Demo instructions explicitly identify deterministic repair and prohibit claiming a live Claude repair without evidence. The provider adapter was not speculatively changed. |
| M2: grounding limits | An accepted model answer requires its own successful tool call. Contradictory explicit health words are rejected conservatively, abbreviations are allowed, and the UI states that other prose claims remain unverified. This is not semantic verification of arbitrary language. |
| M3: hidden programming errors | Unexpected readiness, reasoning, pipeline and polling failures log tracebacks. Internal errors have a separate reason and retain exception type in error status descriptions. Outages retain ERROR behaviour. |
| L1: Markdown injection | Escape Markdown delimiters, backslashes, code ticks and mentions in PR-controlled strings. Server-authored provenance links remain available. |
| L2: missing safety tests | Added specific controller/executor revert tests and mention escaping, plus a URL-ban regression that cannot pass accidentally through the ID regex. |
| L3: demo polish | Lexical terms derive from changed fact IDs; attestation evidence shows names and UTC dates. Docs disclose localhost Details links and exact-request-only model cache replay, including `now_ms`. |
| L4: submission hygiene | Use a tracked-source Git archive. Both Track 1 and Track 3 are named, matching the official rules and superseding D11's one-track contingency. All new commits stay local for the user to push. |

The review's P3 "harmless" example said that every guarantee holds, but the fixture
includes an unknown currency guarantee. The abbreviation regression therefore uses
the accurate sentence "G_DEDUPE holds, e.g. under current facts." A separate test rejects
the unsupported universal health claim.

No token revocation, remote push, branch-protection update, new GitHub rehearsal write,
video recording or hackathon submission was performed during this follow-up.

See [VALIDATION.md](VALIDATION.md) for executed checks and [PUBLISH.md](PUBLISH.md) for
token replacement, safe packaging and manual publication. Multiple-track eligibility was
checked against the [official rules](https://www.wemakedevs.org/hackathons/falkordb/rules).
