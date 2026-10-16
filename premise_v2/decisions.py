"""Render validated inactive drafts. v1 ignores draft fields until a human promotes them."""
from __future__ import annotations

import hashlib
import json
import yaml
from premise.agent.render import safe
from .extract.decision import DecisionCandidate, DecisionExtractor
from .propose import _validate_edit, quote_of


def render_draft(candidate, suffix, active=False):
    did = "ADR-DRAFT-" + suffix
    guarantees = [{"id": f"G_DRAFT_{suffix}_{n}", "statement": g.statement_quote, "about": g.about,
                   "requires": [f"A_DRAFT_{suffix}_{r.assumption_index}" for r in candidate.requires if r.guarantee_index == n]}
                  for n, g in enumerate(candidate.guarantees)]
    assumptions = []
    for n, a in enumerate(candidate.assumptions):
        check = a.check
        rendered = "manual" if check == "manual" else {"lhs": check.lhs_fact, "op": check.op,
            **({"rhs": check.rhs_fact} if check.rhs_fact is not None else {"rhs_const": check.value})}
        assumptions.append({"id": f"A_DRAFT_{suffix}_{n}", "text": a.text_quote, "check": rendered})
    fm = {"id": did, "title": candidate.title, "status": "proposed", "authors": [], "approvers": [],
          "governs": candidate.governs, "supersedes": [], "relies_on": [],
          "provides": guarantees if active else [], "assumptions": assumptions if active else []}
    if not active:
        fm["draft"] = {"provides": guarantees, "assumptions": assumptions}
    return ("---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n# " + did + ": " + candidate.title
            + "\n\n## Context\n" + candidate.context_quote + "\n\n## Decision\n" + candidate.decision_quote
            + "\n\n## Human promotion required\nReview the draft fields, assign accountable people, move reviewed "
              "draft.provides and draft.assumptions to the active front matter, remove draft, "
              "set status to accepted, validate, and merge. Changing status alone does not activate this draft.\n")


class DecisionWriter:
    def __init__(self, staging, decision, model_root, writer):
        self.staging, self.decision, self.root, self.writer = staging, decision, model_root, writer

    def run(self):
        extractor, output = DecisionExtractor(self.decision, self.root), []
        for row in self.staging.extractions("E1"):
            candidate = DecisionCandidate.model_validate(row["data"])
            ok, reason = extractor.ground(candidate, row["item_text"])
            if not ok:
                continue
            suffix = hashlib.sha256((row["envelope_key"] + candidate.model_dump_json()).encode()).hexdigest()[:8]
            key, rel = "decision:" + suffix, f"adr/ADR-DRAFT-{suffix}.md"
            evidence = [{**row, "quote": candidate.quote}]
            if row.get("visibility") != "public":
                self.staging.upsert_review(key, "decision", "Private decision draft needs review",
                    {"evidence": evidence, "body": yaml.safe_dump(candidate.model_dump(), sort_keys=False),
                     "origins": [[row["envelope_key"]]], "support": "observed"})
                output.append({"key": key, "kind": "decision", "state": "private_review_only"})
                continue
            # Validate the prospective active fields, including v1 reference and cycle checks.
            # Then validate the inert file actually offered in the PR.
            active = render_draft(candidate, suffix, active=True)
            new = render_draft(candidate, suffix)
            errors = _validate_edit(self.writer.root, rel, active) + _validate_edit(self.writer.root, rel, new)
            if errors:
                output.append({"key": key, "kind": "decision", "state": "skipped", "reason": "; ".join(errors[:3])})
                continue
            body = ("## Proposed decision draft\n\n" + safe(candidate.title)
                    + "\n\n" + quote_of(evidence[0]) + "\n\nThe draft has no active guarantees or assumptions. "
                      "A human must review and promote the draft fields before accepting and merging it.")
            p = self.writer.write_document("decision", key, rel, new, body, "Premise v2: draft " + candidate.title)
            if p.state != "skipped":
                self.staging.upsert_proposal(key, {"support": "observed", "evidence_json": json.dumps(evidence),
                    "origins_json": json.dumps([[row["envelope_key"]]])})
            output.append({"key": key, "kind": "decision", "state": p.state, "pr_url": p.pr_url})
        return output
