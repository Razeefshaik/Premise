# Local Codex CLI provider

This branch adds an optional provider for the locally authenticated Codex CLI. It does not
require an Anthropic key. The existing Anthropic provider remains the default; `LLM_MODEL`
still applies only to Anthropic. Set `LLM_PROVIDER=none` to force deterministic mode.

The design follows the native-process pattern in ForgeFlow, with a narrower responsibility:
Codex returns structured proposals and Premise executes the allowed tools. The official
[non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) describes
saved CLI authentication, JSONL events and schema-constrained final output.

## Run on Windows

Keep FalkorDB in Docker and run this branch's Python app on Windows so it can invoke the
existing Windows CLI and login. No login files are copied into a container or source tree.
The existing Docker app can keep serving port 8000.

From the Premise workspace:

```powershell
git switch feat/local-codex-cli
docker compose up -d falkordb
codex login status
.\scripts\run_local_codex.ps1
```

Open **http://localhost:8001**. The launcher prepares a separate `premise_codex_demo` graph
with labelled local scenarios, selects `LLM_PROVIDER=codex-cli`, and disables GitHub polling
and automatic fix PRs for that process. `.env` is not edited. Stop with Ctrl+C.

For another port/graph:

```powershell
.\scripts\run_local_codex.ps1 -Port 8002 -Graph premise_codex_demo_2
```

The launcher overrides the current PowerShell process's environment. Open another terminal
for the original setup, or remove those overrides there before starting another provider.

## Provider settings

| Variable | Meaning |
| --- | --- |
| `LLM_PROVIDER` | `anthropic` (default), `codex-cli`, or `none` |
| `CODEX_BINARY` | Optional native executable path; Windows `.ps1`/`.cmd` wrappers are not launched through a shell |
| `CODEX_MODEL` | Optional explicit Codex model; empty uses the CLI default |
| `CODEX_TIMEOUT_SECONDS` | Total inference budget per answer/fix loop, default 180, allowed 1 to 600 |

The adapter ignores user CLI config/rules for this invocation but uses the saved CLI login.
User model overrides in that config are therefore not loaded: use `CODEX_MODEL` explicitly
when a particular model is required. Account usage limits still apply.

## Boundaries

- Each run uses a disposable directory, read-only sandbox, ephemeral sessions, disabled
  native shell/MCP/apps/plugins/browser tools, and no web search. It receives no repository
  checkout. The child environment omits GitHub tokens and provider API keys.
- The model requests one permitted tool through a schema-constrained JSON envelope.
  Premise dispatches it and supplies actual graph rows for the next step. Maximum six
  Analyst tool calls or eight repair tool calls, as before.
- Answer IDs and explicit health claims pass the existing verifier; other prose claims
  are not semantically verified. The UI identifies the actual accepted provider, and
  exposes a safe error class when a provider failure triggers deterministic fallback.
- Numeric fixes must still be controllable, non-reverting, at most three facts and tested
  in the current session. Only complete graph-verified fixes can reach the GitHub executor.
- The process has a wall-clock deadline and bounded output. Timeouts/cancellation terminate
  the owned process tree. A failed login, missing CLI, invalid response or exhausted budget
  preserves deterministic graph answers and repairs.
- Exact model steps may be replayed from FalkorDB's LLMCache. Tool reads still execute on
  replay; changed rows or timestamps change the next request key. No inference cache files
  are persisted on disk. Temporary transport/schema files are removed after the run.

This is an explicit branch-specific provider change from the implementation spec's
Anthropic-only choice. The graph schema, deterministic verdict policy, repair verifier,
human merge control and existing Anthropic request rules remain in place.

## Explicit live rehearsal

```powershell
.\.venv\Scripts\python.exe scripts/codex_rehearsal.py --execute
```

This consumes your signed-in Codex allowance. It asks the three demo questions through
the FastAPI `/api/ask` route and tests an S1 repair against real FalkorDB. It uses and
deletes an isolated graph, makes no GitHub writes, and saves evidence in ignored
`artifacts/codex-rehearsal.json`. A deterministic fallback does not count as a passing
live model test. The normal test suite never starts Codex or requires a model login.

To exercise real GitHub polling with this provider later, first stop the Docker app's
poller, replace any previously exposed token and deliberately run the launcher with
`-PollGitHub`. That option enables real statuses/comments and verified fix PRs using
`.env`; it does not merge anything. It is not part of the isolated provider rehearsal.
