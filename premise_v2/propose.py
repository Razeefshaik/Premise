"""Proposal writer: turn a corroborated drift into a pull request on the model repo.

* One proposal per (fact, value). A rerun updates the same proposal instead of opening a duplicate.
* The edit is validated with v1's own parser and validator on a temporary copy of the model repo.
* The body previews what v1 will say about the change (it is the same read only assessment).
* The PR offers two exits: the world changed (merge, with any verified fix) or the evidence is
  wrong (close; Premise remembers the rejection).
Dry run is the default. Live mode needs an explicit flag and a GitHub client.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from premise.agent.render import safe
from premise.graph.client import GraphClient
from premise.ingest import yamlpos as yp
from premise.ingest.parse import parse_repo
from premise.ingest.validate import validate
from premise.reasoning.assess import assess
from premise.reasoning.intake import overlay_from_files

from .reconcile import Drift
from .staging import Staging, now_ms

MARKER = "<!-- premise:v2:drift:{key} -->"


@dataclass
class Proposal:
    key: str
    branch: str
    title: str
    file: str
    new_text: str
    diff: str
    body: str
    preview: dict
    state: str                 # created | updated | unchanged | skipped
    reason: str = ""
    pr_url: str | None = None


def _when(ms: int | None) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ms else "unknown"


def branch_for(key: str, fact: str, value) -> str:
    return f"v2/drift-{fact.replace('.', '-').replace('_', '-')}-{value}-{hashlib.sha256(key.encode()).hexdigest()[:8]}"


def _diff(path: str, old: str, new: str) -> str:
    import difflib
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{path}", f"b/{path}"))


def _validate_edit(model_root: Path, rel: str, new_text: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="premise-v2-") as tmp:
        copy = Path(tmp) / "model"
        shutil.copytree(model_root, copy, ignore=shutil.ignore_patterns(".git"))
        (copy / rel).write_text(new_text, encoding="utf-8")
        errors, _ = validate(parse_repo(copy))
        return errors


def preview(decision: GraphClient, rel: str, new_text: str) -> dict:
    changes, paths, model_change = overlay_from_files(decision, {rel: new_text})
    result = assess(decision, changes, changed_paths=paths, model_change=model_change)
    return {"verdict": result.verdict,
            "not_holding": [{"id": g.id, "status": g.status, "chain": g.chain, "tier": g.tier} for g in result.guarantees if g.status != "holds"],
            "decisions": [{"id": d.id, "reviewers": d.reviewers} for d in result.decisions],
            "verified_fixes": [f.changes for f in result.fixes if f.status == "verified"],
            "graph_rev": result.graph_rev}


def quote_of(e: dict) -> str:
    return safe(e["quote"]) if e.get("visibility") == "public" else "(private source; quote withheld)"


def render_body(d: Drift, prev: dict, names: dict[str, str]) -> str:
    who = lambda p: safe(names.get(p, p))
    out = [f"## Premise v2: `{safe(d.fact)}` may have changed from {safe(d.model_value)} to {safe(d.value)} {safe(d.unit)}", "",
           f"**Evidence strength:** {d.support} ({len(d.origins)} independent origins)"
           + (", **contested**" if d.contested else "") + ".",
           f"**Model value last changed:** {_when(d.model_as_of_ms)}" + (" (unknown; evidence time not compared)" if d.as_of_unknown else ""),
           "", "### Supporting evidence", ""]
    for e in d.supporting:
        out.append(f"- {who(e['person'])}, {safe(e.get('container') or e['source'])}, {_when(e['as_of_ms'])}: \"{quote_of(e)}\" ({safe(e['envelope_key'])})")
    if d.disagreeing:
        out += ["", "### Disagreeing evidence", ""]
        out += [f"- {who(e['person'])}, {safe(e.get('container') or e['source'])}, {_when(e['as_of_ms'])}: \"{quote_of(e)}\" ({e['status']})" for e in d.disagreeing]
    if d.weak:
        out += ["", "### Ignored as weak evidence", ""]
        out += [f"- {who(e['person'])}: \"{quote_of(e)}\" ({e['status']})" for e in d.weak]
    out += ["", "### What Premise v1 says about this change", "",
            f"Verdict preview: **{prev['verdict']}**."]
    out += [f"- `{g['id']}` is {g['status']} via {' -> '.join(g['chain'])}" for g in prev["not_holding"]]
    if prev["verified_fixes"]:
        out += ["", "Verified fix to apply together with this change:"]
        out += ["- " + ", ".join(f"`{safe(k)}` = {safe(v)}" for k, v in sorted(fix.items())) for fix in prev["verified_fixes"][:1]]
    out += ["", "### Two ways to resolve", "",
            "1. **The world changed.** Merge this PR, together with the verified fix if one is listed. Premise's PR check will run on it.",
            "2. **The evidence is wrong.** Close this PR. Premise records the rejection and will not propose this value again unless newer evidence appears.",
            "", "Proposed by Premise v2 from evidence. A human must review. No model decided this change.",
            "", MARKER.format(key=d.key_id)]
    return "\n".join(out)


class ProposalWriter:
    def __init__(self, staging: Staging, decision: GraphClient, model_root: str | Path, out_dir: str | Path | None = None,
                 github=None, base_branch: str = "main", model_prefix: str = ""):
        self.staging, self.decision = staging, decision
        self.root, self.out = Path(model_root), Path(out_dir) if out_dir else None
        self.github, self.base, self.prefix = github, base_branch, model_prefix.strip("/")

    def eligible(self, d: Drift) -> tuple[bool, str]:
        if d.previously_rejected:
            return False, "rejected earlier by a human; waiting for newer evidence"
        if d.support != "corroborated":
            return False, "only one independent origin; kept as a watch item"
        return True, ""

    def write(self, d: Drift) -> Proposal:
        key = d.key_id
        branch = branch_for(key, d.fact, d.value)
        title = f"Premise v2: {d.fact} may have changed to {d.value} {d.unit}"
        ok, why = self.eligible(d)
        old = (self.root / d.file).read_text(encoding="utf-8")
        if not ok:
            return Proposal(key, branch, title, d.file, old, "", "", {}, "skipped", why)
        new = yp.set_value(old, d.key, d.value)
        errors = _validate_edit(self.root, d.file, new)
        if errors:
            return Proposal(key, branch, title, d.file, new, "", "", {}, "skipped", "invalid edit: " + "; ".join(errors[:3]))
        names = {r["id"]: r["name"] for r in self.decision.read("MATCH (p:Person) RETURN p.id AS id, p.name AS name")}
        prev = preview(self.decision, d.file, new)
        body = render_body(d, prev, names)
        digest = hashlib.sha256(body.encode()).hexdigest()
        existing = self.staging.proposal(key)
        state = "created" if not existing else "unchanged" if existing.get("body_hash") == digest else "updated"
        p = Proposal(key, branch, title, d.file, new, _diff(d.file, old, new), body, prev, state,
                     pr_url=(existing or {}).get("pr_url"))
        if self.out:
            self.out.mkdir(parents=True, exist_ok=True)
            (self.out / f"{branch.replace('/', '_')}.md").write_text(f"# {title}\n\n{body}\n\n```diff\n{p.diff}```\n", encoding="utf-8")
        needs_publish = self.github is not None and (
            not existing or not existing.get("pr_url") or existing.get("status") != "open"
            or existing.get("remote_state") != "open" or existing.get("published_hash") != digest)
        published = {}
        if needs_publish:
            pr = self._open_pr(p)
            p.pr_url = pr["html_url"]
            published = {"pr_url": p.pr_url, "pr_number": pr["number"], "published_hash": digest, "remote_state": "open"}
        self.staging.upsert_proposal(key, {"fact": d.fact, "value": d.value, "branch": branch, "status": "open",
                                           "body_hash": digest, "verdict_preview": prev["verdict"], **published})
        return p

    # ---- live mode ---------------------------------------------------------------------------------
    def withdraw(self, key: str, reason: str) -> dict | None:
        existing = self.staging.proposal(key)
        if not existing or existing["status"] not in {"open", "withdrawn"}:
            return None
        props = {"status": "withdrawn", "withdrawn_reason": reason,
                 "withdrawn_ms": existing.get("withdrawn_ms") or now_ms()}
        if existing.get("pr_url") and existing.get("remote_state") != "closed":
            props["remote_state"] = "withdrawal_pending"
        # Record the agent's intent before closing remotely, so a restart cannot mistake
        # its own closure for a human rejection. Pending closures are retried at sync.
        self.staging.upsert_proposal(key, props)
        if props.get("remote_state") == "withdrawal_pending" and self.github is not None:
            number = existing.get("pr_number") or int(existing["pr_url"].rstrip("/").split("/")[-1])
            pr = self.github.pull(number)
            body = pr.get("body") or ""
            if body.startswith("> **Withdrawn by Premise v2:**"):
                body = body.partition("\n\n")[2]
            banner = f"> **Withdrawn by Premise v2:** {safe(reason)}. The evidence listed below is no longer current."
            self.github.json("PATCH", f"pulls/{number}", json={"body": banner + "\n\n" + body, "state": "closed"})
            self.staging.upsert_proposal(key, {"remote_state": "closed"})
        return {"key": key, "state": "withdrawn", "reason": reason, "pr_url": existing.get("pr_url")}

    def _path(self, rel: str) -> str:
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def _open_pr(self, p: Proposal) -> dict:
        gh = self.github
        owner = gh.repo.split("/")[0]
        base_sha = gh.json("GET", f"git/ref/heads/{self.base}")["object"]["sha"]
        base_commit = gh.json("GET", f"git/commits/{base_sha}")
        tree = gh.json("POST", "git/trees", json={"base_tree": base_commit["tree"]["sha"], "tree": [
            {"path": self._path(p.file), "mode": "100644", "type": "blob", "content": p.new_text}]})
        commit = gh.json("POST", "git/commits", json={"message": p.title, "tree": tree["sha"], "parents": [base_sha]})
        r = gh.http.get(f"/repos/{gh.repo}/git/ref/heads/{p.branch}")
        if r.status_code == 404:
            gh.json("POST", "git/refs", json={"ref": f"refs/heads/{p.branch}", "sha": commit["sha"]})
        else:
            gh.json("PATCH", f"git/refs/heads/{p.branch}", json={"sha": commit["sha"], "force": True})
        existing = gh.pages("pulls", {"state": "open", "head": f"{owner}:{p.branch}"})
        if existing:
            pr = gh.json("PATCH", f"pulls/{existing[0]['number']}", json={"body": p.body, "title": p.title})
        else:
            pr = gh.json("POST", "pulls", json={"title": p.title, "head": p.branch, "base": self.base, "body": p.body})
        return pr

    def sync_outcomes(self) -> list[dict]:
        """Closed without merge -> rejection memory. Merged -> recorded. Needs a GitHub client."""
        if self.github is None:
            return []
        out = []
        for p in self.staging.proposals("withdrawn"):
            if p.get("remote_state") == "withdrawal_pending":
                self.withdraw(p["key"], p["withdrawn_reason"])
        for p in self.staging.proposals():
            if not p.get("pr_url"):
                continue
            pr = self.github.pull(int(p["pr_url"].rstrip("/").split("/")[-1]))
            if pr["state"] == "closed":
                status = "merged" if pr.get("merged_at") else "rejected"
                if status == "rejected":
                    self.staging.reject(p["key"], p["fact"], p["value"], "closed without merge")
                self.staging.upsert_proposal(p["key"], {"status": status, "remote_state": "closed"})
                out.append({"key": p["key"], "status": status})
        return out
