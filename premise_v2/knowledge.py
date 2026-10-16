"""Propose descriptive knowledge; load only reviewed model rows into a separate graph."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml
from premise.agent.render import safe

from .entities import EntityCatalog
from .extract import INSTRUCTION
from .extract.knowledge import KnowledgeExtractor, RelationCandidate
from .identity import IdentityDirectory
from .propose import quote_of
from .registry import Ext, REASONING_RELATIONS, check_relations, knowledge_relations
from .reconcile import _origins


def instant(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def validate_rows(doc, registry, catalog):
    errors = check_relations(registry)
    approved = {r["name"]: r for r in knowledge_relations(registry)}
    rows = doc.get("relations") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise ValueError("knowledge file needs a relations list")
    seen = defaultdict(list)
    for n, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {n}: must be a mapping")
            continue
        relation = approved.get(row.get("type"))
        if row.get("type") in REASONING_RELATIONS or not relation or not re.fullmatch(r"[A-Z][A-Z0-9_]*", row.get("type", "")):
            errors.append(f"row {n}: unapproved knowledge relation")
            continue
        for key, side in (("from", "domain"), ("to", "range")):
            entity = catalog.entities.get(row.get(key)) if isinstance(row.get(key), str) else None
            if not entity or entity["label"] not in relation[side]:
                errors.append(f"row {n}: {side} mismatch")
        try:
            start = instant(row["valid_from"])
            end = instant(row["valid_to"]) if row.get("valid_to") else None
            if end is not None and end <= start:
                raise ValueError("interval must have positive duration")
            pair = row["type"], row["from"], row["to"]
            if any((end is None or old_start < end) and (old_end is None or start < old_end) for old_start, old_end in seen[pair]):
                raise ValueError("overlapping intervals")
            seen[pair].append((start, end))
        except (ValueError, TypeError, KeyError):
            errors.append(f"row {n}: invalid temporal interval")
        if type(row.get("registry_version")) is not int or row["registry_version"] != registry.get("registry_version"):
            errors.append(f"row {n}: registry version mismatch")
        if not isinstance(row.get("evidence"), list) or not row["evidence"] or not all(isinstance(k, str) and k for k in row["evidence"]):
            errors.append(f"row {n}: evidence keys are required")
    if errors:
        raise ValueError("; ".join(errors))
    return rows


def require_merged_model(root):
    """CLI guard: the knowledge file must be committed on the local main history."""
    root = Path(root)
    commands = [
        ["ls-files", "--error-unmatch", "knowledge/relations.yaml"],
        ["diff", "--exit-code", "HEAD", "--", "knowledge/relations.yaml"],
        ["merge-base", "--is-ancestor", "HEAD", "refs/heads/main"],
    ]
    for command in commands:
        try:
            p = subprocess.run(["git", "-C", str(root), *command], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("cannot verify merged model history") from None
        if p.returncode:
            raise ValueError("load-knowledge requires a clean, committed knowledge file on local main history")
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=20).stdout.strip()


def load_knowledge(knowledge, decision, model_root, protected=()):
    if knowledge.graph_name == decision.graph_name or knowledge.graph_name in set(protected) | {"premise_kestrel", "premise_codex_demo"}:
        raise ValueError("knowledge graph must be separate from protected decision graphs")
    root = Path(model_root)
    ext = Ext.load(root)
    catalog = EntityCatalog(decision, root)
    doc = yaml.safe_load((root / "knowledge/relations.yaml").read_text(encoding="utf-8"))
    rows = validate_rows(doc, ext.relations, catalog)
    # Every row is validated before the first write. No reasoning edge name can reach Cypher.
    knowledge.write("MATCH (n) DETACH DELETE n")
    for row in rows:
        a, b = catalog.entities[row["from"]], catalog.entities[row["to"]]
        knowledge.write(f"MERGE (a:{a['label']} {{id:$a}}) SET a.name=$an MERGE (b:{b['label']} {{id:$b}}) SET b.name=$bn "
                        f"CREATE (a)-[:{row['type']} {{valid_from:$start, valid_to:$end, evidence:$ev, registry_version:$version}}]->(b)",
                        {"a": row["from"], "an": a["name"], "b": row["to"], "bn": b["name"],
                         "start": int(instant(row["valid_from"]).timestamp() * 1000),
                         "end": int(instant(row["valid_to"]).timestamp() * 1000) if row.get("valid_to") else None,
                         "ev": row["evidence"], "version": row["registry_version"]})
    digest = hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()
    knowledge.write("CREATE (:KnowledgeState {id:'state', revision:$rev, registry_version:$version, status:'ready'})",
                    {"rev": digest, "version": ext.relations["registry_version"]})
    return {"rows": len(rows), "revision": digest, "registry_version": ext.relations["registry_version"]}


class KnowledgeWriter:
    def __init__(self, staging, decision, model_root, writer):
        self.staging, self.decision, self.root, self.writer = staging, decision, Path(model_root), writer

    def run(self):
        extractor = KnowledgeExtractor(self.decision, self.root)
        items = self.staging.items()
        candidates = self.staging.extractions("K2") + self.staging.extractions("K2_LLM")
        candidates = [c for c in candidates if extractor.ground(RelationCandidate.model_validate(c["data"]), c["item_text"])[0]]
        accepted_quotes = {(c["envelope_key"], c["quote"]) for c in candidates}
        self.staging.c.write("MATCH (u:UnmatchedMention) SET u.active=false")
        for item in items:
            if INSTRUCTION.search(item["body"]):
                continue
            for m in extractor.unmatched(item):
                if (item["key"], m["quote"]) in accepted_quotes:
                    continue
                key = hashlib.sha256(repr([item["key"], item["sequence"], m]).encode()).hexdigest()
                self.staging.c.write("MERGE (u:UnmatchedMention {id:$id}) SET u.phrase=$phrase, u.domain_label=$d, "
                                     "u.range_label=$r, u.quote=$quote, u.item=$item, u.visibility=$vis, u.active=true",
                                     {"id": key, "phrase": m["phrase"], "d": m["domain_label"], "r": m["range_label"],
                                      "quote": m["quote"], "item": item["key"], "vis": item.get("visibility")})
        candidates = IdentityDirectory(self.staging, self.decision, self.root).resolve_claims(candidates)
        grouped = defaultdict(list)
        for c in candidates:
            data = c["data"]
            grouped[(data["relation"], data["from_id"], data["to_id"], data["action"])].append(c)
        ext = Ext.load(self.root)
        path = self.root / "knowledge/relations.yaml"
        output = []
        for (type_, from_, to_, action), evidence in sorted(grouped.items()):
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"relations": []}
            rows = doc["relations"]
            first = min(evidence, key=lambda c: c["as_of_ms"])
            data = first["data"]
            when = data.get("valid_from") or datetime.fromtimestamp(first["as_of_ms"] / 1000, timezone.utc).isoformat()
            end_when = data.get("valid_to") or when
            keys = sorted({c["envelope_key"] for c in evidence})
            active = [r for r in rows if r["type"] == type_ and r["to"] == to_ and not r.get("valid_to")]
            same = next((r for r in active if r["from"] == from_), None)
            if action == "end":
                if same is None:
                    continue
                same["valid_to"] = end_when
            elif same:
                old_keys = set(same["evidence"])
                if set(keys) <= old_keys:
                    continue
                same["evidence"] = sorted(old_keys | set(keys))
            else:
                if type_ == "ON_CALL_FOR":
                    for row in active:
                        row["valid_to"] = when
                rows.append({"type": type_, "from": from_, "to": to_, "valid_from": when,
                             "valid_to": data.get("valid_to"), "evidence": keys,
                             "registry_version": ext.relations["registry_version"]})
            key = "knowledge:" + hashlib.sha256(repr([type_, from_, to_, action, when]).encode()).hexdigest()[:12]
            try:
                validate_rows(doc, ext.relations, extractor.catalog)
            except ValueError as exc:
                self.staging.upsert_review(key, "knowledge", "Knowledge proposal needs review", {"reason": str(exc)})
                continue
            body = f"## Descriptive relation: {type_}\n\n`{from_}` -> `{to_}` ({action}). Human review required.\n\n"
            body += "\n".join(f"- {quote_of(c)} ({safe(c['envelope_key'])})" for c in evidence)
            p = self.writer.write_document("knowledge", key, "knowledge/relations.yaml", yaml.safe_dump(doc, sort_keys=False), body,
                                           f"Premise v2: review {type_} for {to_}")
            origins = _origins(evidence, {})
            if p.state != "skipped":
                self.staging.upsert_proposal(key, {"evidence_json": json.dumps(evidence), "origins_json": json.dumps(origins),
                                                   "support": "corroborated" if len(origins) >= 2 else "observed"})
            output.append({"key": key, "kind": "knowledge", "state": p.state, "pr_url": p.pr_url})
        return output
