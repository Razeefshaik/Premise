"""Attestation challenges are review artifacts, never attestation mutations."""
from __future__ import annotations

import hashlib

from premise.agent.render import safe

from .extract.attestation import AssumptionEvidence, AttestationExtractor
from .identity import IdentityDirectory
from .propose import quote_of
from .reconcile import _origins
from .staging import now_ms


class ChallengeWriter:
    def __init__(self, staging, decision, model_root, out_dir=None, github=None):
        self.staging, self.decision, self.model_root = staging, decision, model_root
        self.out, self.github = out_dir, github

    def run(self, at_ms=None):
        at = at_ms if at_ms is not None else now_ms()
        extractor = AttestationExtractor(self.decision)
        rows = self.staging.extractions("E3")
        rows = [r for r in rows if extractor.ground(AssumptionEvidence.model_validate(r["data"]), r["item_text"])[0]]
        rows = IdentityDirectory(self.staging, self.decision, self.model_root).resolve_claims(rows)
        assumptions = {r["id"]: r for r in self.decision.named("evaluate_assumptions",
                       {"ids": list(extractor.manual), "overlay": [], "now": at})} if extractor.manual else {}
        refs = {i["key"].split(":", 1)[1].split("#")[0]: i["key"].split("#")[0]
                for i in self.staging.items() if i.get("source") == "jira"}
        findings, current = [], set()
        for aid, assumption in sorted(assumptions.items()):
            if assumption["holds"] is not True:
                continue
            valid_atts = [a for a in assumption["atts"] if a["status"] == "active" and a["on"] <= at
                          and (a["review_by"] is None or a["review_by"] >= at)]
            evidence = [r for r in rows if r["data"]["assumption_id"] == aid
                        and r["as_of_ms"] > max(a["on"] for a in valid_atts)]
            support = [r for r in evidence if r["data"]["stance"] == "contradicts"]
            origins = _origins(support, refs)
            if len(origins) < 2:
                continue
            key = f"challenge:{aid}"
            rejected = self.staging.rejection(key)
            if rejected and max(r["as_of_ms"] for r in support) <= rejected["at_ms"]:
                continue
            related = self.decision.read("MATCH (g:Guarantee)-[:REQUIRES*1..]->(:Assumption {id:$aid}) "
                "OPTIONAL MATCH (d:Decision)-[:PROVIDES|RELIES_ON]->(g) "
                "RETURN collect(DISTINCT g.id) AS guarantees, collect(DISTINCT d.id) AS decisions", {"aid": aid})[0]
            reviewers = set()
            for did in related["decisions"]:
                route = self.decision.named("route_decision", {"decision_id": did, "since": at - 180 * 86400000})
                if route:
                    reviewers.update(route[0]["active_accountable"] or [r["person"] for r in route[0]["candidates"][:3]])
            names = {r["id"]: r["name"] for r in self.decision.read("MATCH (p:Person) RETURN p.id AS id, p.name AS name")}
            title = f"Premise v2: review attestation for {aid}"
            body = f"## Attestation challenge: {safe(aid)}\n\n{safe(assumption['text'])}\n\n"
            body += "Contradicting evidence has two or more independent origins. The current attestation remains unchanged.\n\n"
            body += "Attesters: " + ", ".join(safe(names.get(a["person"], a["person"])) for a in valid_atts) + ".\n\n"
            body += "Suggested reviewers: " + ", ".join(safe(names.get(p, p)) for p in sorted(reviewers)) + ".\n\n"
            body += "\n".join(f"- {quote_of(r)} ({safe(r['envelope_key'])})" for r in evidence)
            marker = f"<!-- premise:v2:challenge:{aid} -->"
            body += "\n\nOnly a human edit to the ADR can renew or change its attestation.\n\n" + marker
            result = {"key": key, "kind": "challenge", "assumption": aid, "support": "corroborated", "origins": origins,
                      "evidence": evidence, "reviewers": sorted(reviewers), "attesters": valid_atts,
                      "body": body, "guarantees": related["guarantees"], "contested": any(r["data"]["stance"] == "supports" for r in evidence)}
            if self.out:
                self.out.mkdir(parents=True, exist_ok=True)
                (self.out / f"challenge-{hashlib.sha256(key.encode()).hexdigest()[:12]}.md").write_text(body, encoding="utf-8")
            if self.github is not None:
                actor = self.github.actor()
                issues = self.github.pages("issues", {"state": "all", "creator": actor})
                existing = next((i for i in issues if marker in (i.get("body") or "")
                                 and i.get("user", {}).get("login") == actor and "pull_request" not in i), None)
                if existing and existing["state"] == "closed":
                    self.staging.reject(key, aid, "challenge", "closed by a human")
                    continue
                if not existing:
                    existing = self.github.json("POST", "issues", json={"title": title, "body": body})
                elif existing.get("body") != body:
                    existing = self.github.json("PATCH", f"issues/{existing['number']}", json={"body": body})
                result["issue_url"] = existing["html_url"]
            self.staging.upsert_review(key, "challenge", title, result)
            findings.append(result)
            current.add(key)
        for old in self.staging.review_items("challenge"):
            if old["key"] not in current:
                self.staging.upsert_review(old["key"], "challenge", old["title"], old["data"], status="withdrawn")
        return findings
