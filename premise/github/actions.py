"""One executor with graph action records, stale guards and crash reconciliation."""
from __future__ import annotations

import base64
import json
import math
from ..ingest import yamlpos
from ..reasoning.assess import graph_ready
from ..reasoning.repair import Repairer
from ..graph.client import GraphUnavailable
from ..agent.render import provenance, render_comment
from .store import Store, digest, assessment_id

STATUS = {"BLOCKED": "failure", "NEEDS_REVIEW": "failure", "CLEAR_WITHIN_SCOPE": "success", "ERROR": "error"}


class StaleAssessment(RuntimeError):
    pass


class Executor:
    def __init__(self, client, github, public_url="http://localhost:8000", auto_fix=False):
        self.client, self.github = client, github
        self.store = Store(client)
        self.public_url, self.auto_fix = public_url.rstrip("/"), auto_fix

    def fresh(self, result, number):
        pr = self.github.pull(number)
        ready, rev, _ = graph_ready(self.client)
        if not ready:
            raise GraphUnavailable("Graph not ready during action execution")
        if pr["state"] != "open" or pr["head"]["sha"] != result.head_sha or rev != result.graph_rev:
            raise StaleAssessment("PR head or graph revision changed; requeue required")
        return pr

    def _run(self, result, number, kind, key, payload, call):
        aid = assessment_id(result)
        previous = self.store.action(key)
        if previous and previous["status"] == "done" and previous.get("payload_json") == json.dumps(payload):
            return previous.get("external_url", "")
        try:
            self.fresh(result, number)
        except StaleAssessment:
            self.store.begin(key, kind, aid, payload)
            self.store.finish(key, "skipped", error="stale assessment; requeue required")
            raise
        self.store.begin(key, kind, aid, payload)
        try:
            output = call()
            url = output.get("html_url", output.get("target_url", "")) or ""
            self.store.finish(key, url=url)
            return url
        except Exception as exc:
            self.store.finish(key, "failed", error=type(exc).__name__)
            raise

    def execute(self, result, pr):
        try:
            return self._execute(result, pr)
        except GraphUnavailable:
            latest = self.github.pull(pr["number"])
            if latest["state"] == "open" and latest["head"]["sha"] == result.head_sha:
                self.github.status(result.head_sha, "error", "Assessment unavailable: graph failed during execution")
            raise

    def _execute(self, result, pr):
        number = pr["number"]
        if result.verdict == "ERROR":
            # An unavailable graph cannot record an action. Only a current-head error status is allowed.
            latest = self.github.pull(number)
            if latest["head"]["sha"] == result.head_sha and latest["state"] == "open":
                self.github.status(result.head_sha, "error", "Assessment unavailable: graph not ready")
            return {"status": "error"}
        aid = self.store.save(result, pr)
        url = f"{self.public_url}/assessments/{aid}"
        payload = {"number": number, "head_sha": result.head_sha, "state": STATUS[result.verdict],
                   "description": f"{result.verdict}: {result.reasons[0].detail}"[:140], "url": url}
        status_key = f"status:{number}:{result.head_sha}:{result.verdict}"
        self._run(result, number, "status", status_key, payload,
                  lambda: self.github.status(result.head_sha, payload["state"], payload["description"], url))
        ids = [c.fact for c in result.changed_facts] + [a.id for a in result.assumptions]
        ids += [f for a in result.assumptions for f in (a.lhs_fact, a.rhs_fact) if f]
        ids += [g.id for g in result.guarantees] + [d.id for d in result.decisions]
        ids += [x for c in result.not_affected + result.checked_with_problems for x in (c.decision, c.via_guarantee, c.sibling_of)]
        refs = provenance(self.client, ids)
        # Proposed values are evidenced at the PR head; unchanged facts stay linked to main.
        for c in result.changed_facts:
            if not c.deleted:
                refs = [r for r in refs if r["id"] != c.fact]
                refs.append({"id":c.fact,"path":c.file,"line":c.line,
                             "url":f"https://github.com/{self.github.repo}/blob/{result.head_sha}/{c.file}",
                             "commit_sha":result.head_sha})
        people = self.client.read("MATCH (p:Person) RETURN p.id AS id, p.name AS name")
        body = render_comment(result, number, url, refs, {p["id"]:p["name"] for p in people})
        cp = {"number": number, "head_sha": result.head_sha, "body": body, "graph_rev": result.graph_rev}
        comment = self._run(result, number, "comment", f"comment:{number}", cp,
                            lambda: self.github.upsert_comment(number, body))
        fixes = [f for f in result.fixes if f.status == "verified"]
        fix_url = None
        if self.auto_fix and fixes and pr["head"]["repo"]["full_name"].lower() == self.github.repo.lower():
            fix = fixes[0]
            fp = {"number": number, "head_sha": result.head_sha, "changes": fix.changes}
            key = f"fix:{number}:{result.head_sha}:{digest(fix.changes)[:8]}"
            fix_url = self._run(result, number, "fix_pr", key, fp, lambda: self.fix_pr(result, pr, fix.changes))
        return {"assessment": url, "comment": comment, "fix_pr": fix_url}

    def fix_pr(self, result, pr, changes):
        if not changes or len(changes) > 3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in changes.values()):
            raise ValueError("Invalid remedy")
        facts = self.client.named("facts_by_id", {"ids": sorted(changes)})
        if len(facts) != len(changes) or any(f["controlled_by"] != "us" for f in facts):
            raise ValueError("Only registered controllable facts may be edited")
        overlay = {c.fact: None if c.deleted else c.new for c in result.changed_facts}
        if any(f["id"] in overlay and changes[f["id"]] == f["value"] for f in facts):
            raise ValueError("Reverting the PR is not a remedy")
        verified = Repairer(self.client, overlay, result.now_ms, budget=1).test_fix(changes)
        if not verified or not verified.evaluation.all_hold:
            raise ValueError("Remedy no longer verifies")
        number = pr["number"]
        branch = f"premise/fix-{number}-{digest([result.head_sha,changes])[:8]}"
        matches = self.github.pages("pulls", {"state": "all", "head": self.github.repo.split('/')[0]+":"+branch})
        if matches:
            return matches[0]
        self.fresh(result, number)
        files = {}
        for f in facts:
            if f["file"] not in files:
                src = self.github.file(f["file"], result.head_sha)
                files[f["file"]] = base64.b64decode(src["content"]).decode("utf-8")
            files[f["file"]] = yamlpos.set_value(files[f["file"]], f["key"], changes[f["id"]])
        # A single tree/commit makes multi-file remedies atomic and crash retryable.
        commit = self.github.json("GET", f"git/commits/{result.head_sha}")
        tree = self.github.json("POST", "git/trees", json={"base_tree": commit["tree"]["sha"], "tree": [
            {"path": path, "mode": "100644", "type": "blob", "content": text} for path,text in sorted(files.items())]})
        new = self.github.json("POST", "git/commits", json={"message": f"Premise: verified remedy for #{number}",
            "tree": tree["sha"], "parents": [result.head_sha]})
        self.fresh(result, number)
        ref_path = "git/ref/heads/" + branch
        r = self.github.http.get(f"/repos/{self.github.repo}/{ref_path}")
        if r.status_code == 404:
            self.github.json("POST", "git/refs", json={"ref": "refs/heads/"+branch, "sha": new["sha"]})
        elif r.status_code != 200:
            raise RuntimeError("Cannot reconcile fix branch")
        else:
            # On retry, only reuse an identical file tree based on this original PR head.
            existing = self.github.json("GET", "git/commits/"+r.json()["object"]["sha"])
            if existing["tree"]["sha"] != tree["sha"] or [p["sha"] for p in existing["parents"]] != [result.head_sha]:
                raise ValueError("Fix branch has unexpected changes")
        self.fresh(result, number)
        return self.github.json("POST", "pulls", json={"title": f"Premise: verified remedy for #{number}",
            "head": branch, "base": pr["head"]["ref"], "body": "Graph-verified complete remedy.\n\n" +
            "\n".join(f"- `{k}` = `{v}`" for k,v in sorted(changes.items())) +
            f"\n\nParent head: `{result.head_sha}`; graph revision {result.graph_rev}.\n\n<!-- premise:fix:{branch} -->"})

    def reconcile(self):
        rows = self.client.read("MATCH (a:Action {status:'executing'})<-[:TOOK]-(s:Assessment) "
            "RETURN a.id AS id, s.id AS assessment ORDER BY id")
        outcomes = []
        for row in rows:
            result = self.store.get(row["assessment"])
            try:
                pr = self.github.pull(int(result.pr.split(":")[-1]))
                self.execute(result, pr)
                outcomes.append({"id": row["id"], "status": "reconciled"})
            except StaleAssessment:
                self.store.finish(row["id"], "skipped", error="stale assessment; requeue required")
                outcomes.append({"id": row["id"], "status": "skipped"})
        return outcomes
