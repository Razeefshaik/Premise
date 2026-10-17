# Three-minute demonstration

For the new Explorer, consequences, forecast, continuity and benchmark, use the separate
[V3 walkthrough](DEMO_V3.md). Its public replay remains a deployment handoff.

Use `docs/PUBLISH.md` to publish and run the sandbox rehearsal first. This is a script, not
evidence that a live GitHub rehearsal or video recording has already happened.

The first live GitHub rehearsal has since succeeded (see `VALIDATION.md`), but no video
has been recorded. The demonstrated repair used deterministic graph-verified search.
Do not say that Claude proposed it unless a real provider run has been completed.
Without an Anthropic key, show deterministic mode and MCP graph tools honestly.
If `PUBLIC_BASE_URL` is localhost, explicitly say the assessment page runs locally;
GitHub's Details link will only open it on the machine running Premise.

The Codex provider, now merged into `main`, passed a real API and fix-controller rehearsal.
Follow [LOCAL_CODEX.md](LOCAL_CODEX.md) to launch the host app on port 8001.
Main can demonstrate Codex answers and a graph-verified Codex repair; it does not
establish a live Anthropic call, an external MCP-client rehearsal, or a Codex-authored remote
fix PR. Keep those claims separate when recording.

| Time | Show | Say / do |
| --- | --- | --- |
| 0:00–0:15 | ADR-007 source | Decisions promise guarantees; guarantees need assumptions. Show G_DEDUPE and the current attestation. |
| 0:15–0:30 | S1 sandbox PR | Record the partner's 72-hour retry policy. The partner fact is external and cannot be reverted by the agent. |
| 0:30–1:10 | Real status and comment | 72 exceeds our 24-hour TTL. Follow G_DEDUPE → G_CHARGE_ONCE → G_REFUND_MATCH → G_LEDGER_CONSISTENT. ADR-012/015/018 are affected despite not mentioning retries. ADR-016 is evaluated and still holds. Jun ranks first for ADR-012 with six recent sources. |
| 1:10–1:45 | Rejected candidate and stacked fix | TTL 72 alone breaks the Redis limit. TTL 72 plus Redis max 72 verifies every prerequisite. Merge the fix into the original PR branch, then show the original check turn green. |
| 1:45–2:00 | S2 PR | Email retries 8 remain within the provider budget 10. Clear within tracked scope. |
| 2:00–2:20 | Assessment UI | Show graph witnesses, exact source lines, checked-not-affected decisions, and the fulltext lexical gap. |
| 2:20–2:50 | MCP client / Brain | Ask the questions below. Show expired currency attestation and live ownership evidence. |
| 2:50–3:00 | Product / repositories | Premise checks each change against the guarantees your decisions depend on. Show the public source and tracks. |

Additional main-branch demonstrations:

- Preflight: an agent calls `check_files` before editing Kestrel configuration; the unsafe
  72-hour change is BLOCKED and the complete repair plus reviewers is returned. The
  installed MCP protocol is tested, but Claude Code automatic tool selection still needs
  a machine with Claude Code installed.
- What if: open `/what-if?set=paylane.retry_window_hours=72`, show the red graph, then
  Apply fix and show CLEAR. This is a hypothetical check and saves/posts nothing.
- Optional steward: show the dry-run plan for the expired rates attestation and orphaned
  ADR-012. Show a real GitHub issue only after deliberately executing the reviewed plan;
  mocked issue tests are not evidence of a live issue.

Three questions:

1. Which guarantees are load bearing, and which rest on unverified assumptions?
2. Why does ADR-012 skip idempotency, and who owns that decision now?
3. Who knows paymentservice, and what evidence supports that?

For an offline walkthrough:

```powershell
docker compose up -d
docker compose exec app premise demo
```

Open `http://localhost:8000`. Rows with PR numbers 9001–9004 explicitly say **Local demo**.
They are deterministic scenario evaluations saved in real FalkorDB, not real GitHub PRs.
`premise reset --demo` replaces local demo history only; it never changes remote branches,
comments, or PRs. Historic live assessments remain separate.

The demo clock for scenarios is 2026-10-16T00:00Z; normal health and live PR assessments use
the current UTC time. Attestations can expire, so re-attest authored data deliberately for
a later demonstration instead of bypassing the evaluator.

## MCP setup

The official SDK stdio server has eleven read tools, including the read-only preflight checks.
Configure your MCP client with the absolute virtual-environment Python executable and `cwd`
set to this repository. On Windows, use the equivalent `.venv/Scripts/python.exe` path.

```json
{
  "mcpServers": {
    "premise": {
      "command": "/absolute/path/to/Premise/.venv/bin/python",
      "args": ["-m", "premise.cli", "mcp"],
      "cwd": "/absolute/path/to/Premise",
      "env": {"FALKORDB_HOST": "localhost", "FALKORDB_PORT": "6379", "GRAPH_NAME": "premise_kestrel"}
    }
  }
}
```

Clients without `cwd` support can invoke the installed absolute `premise.exe` with the same
graph environment. Start FalkorDB and ingest before connecting. No LLM key is required
for MCP: the client's own model selects the tools. No action or arbitrary Cypher tool exists.
