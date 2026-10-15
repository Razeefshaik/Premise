# Morning publishing handoff

The user asked to keep commits local and will push manually. No remote push, sandbox PR,
status, comment, branch protection change, or fix PR was executed during this build.
Read-only GitHub authentication confirmed the `Razeefshaik` account and access to both repos.

## 1. Push the product

From the Premise workspace:

```powershell
git status
git log --oneline -8
git remote -v
git push -u origin main
```

The remote is `https://github.com/Razeefshaik/Premise.git`. If GitHub already has an initial
README commit, fetch and inspect it, then merge it with `--allow-unrelated-histories` if
needed. Preserve that work; do not force push. `.env` is ignored and must remain local.

## 2. Push the fictional company

Prepare the independent local sandbox repo (the script refuses an existing destination):

```powershell
.\.venv\Scripts\python.exe scripts/prepare_sandbox.py
git -C .runtime/kestrel-publish log --oneline --all --decorate
git -C .runtime/kestrel-publish push -u origin main
git -C .runtime/kestrel-publish push origin --all
```

The sandbox remote is `https://github.com/Razeefshaik/kestrel-platform.git`.
The eight scenario branches have committed changes and their exact SHAs are saved beside
the managed checkout in `.runtime/kestrel-publish-expected.json`.
If the preparation script has already been run, skip its first command and use that checkout.

## 3. Rehearse real GitHub actions

In `.env`, retain `GITHUB_TOKEN` and set:

```dotenv
SANDBOX_REPO=Razeefshaik/kestrel-platform
POLL_ENABLED=true
AUTO_FIX_PR=true
PUBLIC_BASE_URL=http://localhost:8000
```

The local URL works on your machine. It is not a public deployment; use a reachable URL
before asking judges to open the commit status link. The REST API and PR comments still
work independently of public hosting.

Token permissions on the sandbox: Contents, Pull requests, Issues, Commit statuses read/write;
Metadata read. Administration write is additionally needed to configure branch protection.

```powershell
docker compose up --build -d
.\.venv\Scripts\python.exe scripts/github_rehearsal.py --execute --protect-main
```

The explicit rehearsal creates/reuses S1 and S2 sandbox PRs, evaluates them against real
FalkorDB, posts real statuses and one updatable comment, and opens a stacked verified fix
when enabled. It prints actual URLs. S1 must fail; S2 must pass. Open S1's fix PR,
confirm its base is the S1 branch, and merge it manually. The original S1 PR must then turn
green after the next poll. The script does not merge anything or submit the hackathon entry.

If branch protection is denied by GitHub, the script reports the failure. In repository
Settings, require the `premise/decisions` status on `main` after its first run. Account rules
may restrict this. No successful configuration is assumed.

## Before submitting

- Check both repos are public and the code is pushed.
- Run the full suite and all scenarios; compare with `docs/VALIDATION.md`.
- Record the real red-to-green demonstration, at most three minutes; follow `docs/DEMO.md`.
- Verify the video plays while logged out. No recorded video is included in this repository.
- Configure the MCP server in your client and try the three demo questions.
- Confirm track eligibility with the organizers; the spec chooses Track 1 if only one is allowed.
- Submit the entry yourself. The agent has not registered a team or submitted anything.
