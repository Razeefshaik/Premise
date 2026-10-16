"""Parse the company repository into graph nodes and edges, with provenance (file and line) on everything.

Deterministic: no LLM is involved anywhere in ingestion.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import yamlpos as yp

MODEL_PATH_PREFIXES = ("adr/", "catalog/", "company/")
MODEL_FILES = ("facts.yaml",)

# Relationship types written by ingestion. Only these are swept between revisions; memory edges never are.
AUTHORED_EDGE_TYPES = (
    "MEMBER_OF", "OWNS", "DEPENDS_ON", "ACCOUNTABLE_FOR", "GOVERNS", "SUPERSEDES", "PROVIDES", "RELIES_ON",
    "REQUIRES", "ABOUT", "LHS", "RHS", "ATTESTED", "STATED_IN", "DEFINED_IN", "PART_OF", "AUTHORED", "MENTIONS",
)


def is_model_path(path: str) -> bool:
    return path.startswith(MODEL_PATH_PREFIXES) or path in MODEL_FILES


def to_ms(value: Any) -> int | None:
    """Dates and datetimes (YAML or ISO strings) to epoch milliseconds, UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        d = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    elif isinstance(value, dt.date):
        d = dt.datetime(value.year, value.month, value.day, tzinfo=dt.timezone.utc)
    else:
        s = str(value).replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s) if "T" in s else dt.datetime.fromisoformat(s + "T00:00:00+00:00")
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def value_type(v: Any) -> str:
    if isinstance(v, bool):
        return "other"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    return "other"


def normalize_value(v: Any) -> Any:
    """Facts are int, float or string in the graph. Anything else is stored as its string form."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None if v is None else str(v)
    return v


@dataclass
class Model:
    nodes: dict[str, dict[str, dict[str, Any]]] = field(default_factory=lambda: defaultdict(dict))
    edges: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    errors: list[str] = field(default_factory=list)
    # structures used by validation
    guarantee_requires: dict[str, list[str]] = field(default_factory=dict)
    guarantee_about: dict[str, list[str]] = field(default_factory=dict)
    decision_relies: dict[str, list[str]] = field(default_factory=dict)
    decision_provides: dict[str, list[str]] = field(default_factory=dict)
    decision_status: dict[str, str] = field(default_factory=dict)
    supersedes: list[tuple[str, str]] = field(default_factory=list)
    references: list[tuple[str, str, str]] = field(default_factory=list)  # (source path, kind, id)

    def node(self, label: str, id_: str, src: str | None = None, **props: Any) -> None:
        if id_ in self.nodes[label]:
            self.errors.append(f"duplicate {label} id {id_} ({src})")
            return
        for other_label, ids in self.nodes.items():
            if other_label != label and id_ in ids:
                self.errors.append(f"id {id_} used by both {other_label} and {label} ({src})")
        self.nodes[label][id_] = props

    def edge(self, type_: str, a: str, b: str, src: str | None = None, line: int | None = None, **props: Any) -> None:
        self.edges[type_].append({"a": a, "b": b, "props": {"src": src, "line": line, **props}})

    def all_ids(self) -> dict[str, str]:
        return {i: label for label, ids in self.nodes.items() for i in ids}


# ---------------------------------------------------------------------------------------------------------------
def _source(m: Model, path: str, kind: str, commit_sha: str, repo_url: str | None, **props: Any) -> str:
    sid = f"src:{path}"
    url = f"{repo_url}/blob/{commit_sha}/{path}" if repo_url and re.fullmatch(r"[0-9a-f]{40}", commit_sha) else None
    m.node("Source", sid, path, path=path, kind=kind, url=url, commit_sha=commit_sha,
           search_text=props.pop("title", path), **props)
    return sid


def _passages(m: Model, sid: str, body_lines: list[str], first_line: int) -> None:
    """Split markdown into blocks separated by blank lines; one Passage per block, with its line span."""
    block: list[str] = []
    start = None
    n = 0

    def flush(end_line: int) -> None:
        nonlocal block, start, n
        if block:
            n += 1
            pid = f"{sid}#p{n}"
            m.node("Passage", pid, sid, text="\n".join(block).strip(), start_line=start, end_line=end_line,
                   search_text="")
            m.edge("PART_OF", pid, sid, sid)
        block, start = [], None

    for i, text in enumerate(body_lines):
        ln = first_line + i
        if text.strip() == "":
            flush(ln - 1)
        else:
            if start is None:
                start = ln
            block.append(text)
    flush(first_line + len(body_lines) - 1)


def _split_front_matter(text: str) -> tuple[str, list[str], int]:
    """Return (front matter text, body lines, first body line number). Front matter starts on line 2."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", lines, 1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]) + "\n", lines[i + 1 :], i + 2
    raise ValueError("unterminated front matter")


# ---------------------------------------------------------------------------------------------------------------
def parse_company(m: Model, root: Path, sha: str, repo: str | None) -> None:
    path = "company/teams.yaml"
    text = (root / path).read_text()
    sid = _source(m, path, "company", sha, repo)
    doc = yp.compose(text)
    for item in yp.items(yp.mapping_get(doc, "teams")[1]):
        t = yp.safe_load(yaml.serialize(item))
        m.node("Team", t["id"], path, name=t["name"], search_text=f"{t['id']} {t['name']}")
        m.edge("STATED_IN", t["id"], sid, path, yp.line(item))

    path = "company/people.yaml"
    text = (root / path).read_text()
    sid = _source(m, path, "company", sha, repo)
    doc = yp.compose(text)
    for item in yp.items(yp.mapping_get(doc, "people")[1]):
        p = yp.safe_load(yaml.serialize(item))
        m.node("Person", p["id"], path, name=p["name"], status=p["status"], left_at=to_ms(p.get("left_at")),
               search_text=f"{p['id']} {p['name']}")
        m.edge("STATED_IN", p["id"], sid, path, yp.line(item))
        for ms in p.get("memberships", []):
            m.edge("MEMBER_OF", p["id"], ms["team"], path, yp.line(item),
                   since=to_ms(ms.get("since")), until=to_ms(ms.get("until")))
            m.references.append((path, "Team", ms["team"]))


def parse_catalog(m: Model, root: Path, sha: str, repo: str | None) -> None:
    path = "catalog/services.yaml"
    text = (root / path).read_text()
    sid = _source(m, path, "catalog", sha, repo)
    doc = yp.compose(text)
    for item in yp.items(yp.mapping_get(doc, "services")[1]):
        s = yp.safe_load(yaml.serialize(item))
        aliases = s.get("aliases", []) or []
        m.node("Service", s["id"], path, name=s["name"], tier=int(s["tier"]), aliases=aliases,
               fictional=bool(s.get("fictional", False)),
               search_text=" ".join([s["id"], s["name"], *aliases]))
        ln = yp.line(item)
        m.edge("STATED_IN", s["id"], sid, path, ln)
        m.edge("OWNS", s["owner"], s["id"], path, ln)
        m.references.append((path, "Team", s["owner"]))
        for dep in s.get("depends_on", []) or []:
            m.edge("DEPENDS_ON", s["id"], dep["to"], path, ln, kind=dep.get("kind", "sync"))
            m.references.append((path, "Service", dep["to"]))


def parse_facts(m: Model, root: Path, sha: str, repo: str | None) -> None:
    path = "facts.yaml"
    reg = yp.safe_load((root / path).read_text())["facts"]
    sources: dict[str, str] = {}
    for fid, spec in reg.items():
        fpath = spec["file"]
        if fpath not in sources:
            sources[fpath] = _source(m, fpath, "config", sha, repo)
        file_text = (root / fpath).read_text() if (root / fpath).exists() else None
        if file_text is None:
            m.errors.append(f"fact {fid}: file {fpath} does not exist")
            continue
        _, vnode = yp.find(yp.compose(file_text), spec["key"])
        if vnode is None:
            m.errors.append(f"fact {fid}: key {spec['key']} not found in {fpath}")
            continue
        raw = yp.scalar_value(vnode)
        ln = yp.line(vnode)
        m.node("Fact", fid, path, file=fpath, key=spec["key"], value=normalize_value(raw), value_type=value_type(raw),
               controlled_by=spec.get("controlled_by", "us"), owner=spec.get("owner"), line=ln,
               search_text=f"{fid} {spec['key']} {fpath}")
        m.edge("DEFINED_IN", fid, sources[fpath], fpath, ln)


def parse_adrs(m: Model, root: Path, sha: str, repo: str | None) -> None:
    for file in sorted((root / "adr").glob("*.md")):
        path = f"adr/{file.name}"
        text = file.read_text()
        fm_text, body, body_first = _split_front_matter(text)
        doc = yp.compose(fm_text)
        fm = yp.safe_load(fm_text) or {}
        off = 1  # front matter text starts on file line 2
        did = fm["id"]
        sid = _source(m, path, "adr", sha, repo, title=f"{did} {fm.get('title', '')}", decision=did,
                      ts=to_ms(fm.get("decided")))
        status = fm.get("status", "proposed")
        m.decision_status[did] = status
        m.node("Decision", did, path, title=fm.get("title", ""), status=status, decided_at=to_ms(fm.get("decided")),
               search_text=f"{did} {fm.get('title', '')}")
        m.edge("STATED_IN", did, sid, path, yp.line(yp.mapping_get(doc, "id")[0], off))

        for role, key in (("author", "authors"), ("approver", "approvers")):
            kn, _ = yp.mapping_get(doc, key)
            for pid in fm.get(key, []) or []:
                m.edge("ACCOUNTABLE_FOR", pid, did, path, yp.line(kn, off), role=role)
                m.references.append((path, "Person", pid))
                if role == "author":
                    m.edge("AUTHORED", pid, sid, path, yp.line(kn, off))
        kn, _ = yp.mapping_get(doc, "governs")
        for svc in fm.get("governs", []) or []:
            m.edge("GOVERNS", did, svc, path, yp.line(kn, off))
            m.references.append((path, "Service", svc))
        kn, _ = yp.mapping_get(doc, "supersedes")
        for old in fm.get("supersedes", []) or []:
            m.edge("SUPERSEDES", did, old, path, yp.line(kn, off))
            m.supersedes.append((did, old))
        kn, _ = yp.mapping_get(doc, "relies_on")
        m.decision_relies[did] = list(fm.get("relies_on", []) or [])
        for gid in m.decision_relies[did]:
            m.edge("RELIES_ON", did, gid, path, yp.line(kn, off))
            m.references.append((path, "Guarantee", gid))

        m.decision_provides[did] = []
        for item in yp.items(yp.mapping_get(doc, "provides")[1]):
            g = yp.safe_load(yaml.serialize(item))
            gid = g["id"]
            m.decision_provides[did].append(gid)
            ln = yp.line(item, off)
            m.node("Guarantee", gid, path, statement=g.get("statement", ""), search_text=f"{gid} {g.get('statement', '')}")
            m.edge("PROVIDES", did, gid, path, ln)
            m.edge("STATED_IN", gid, sid, path, ln)
            m.guarantee_about[gid] = list(g.get("about", []) or [])
            akn, _ = yp.mapping_get(item, "about")
            for svc in m.guarantee_about[gid]:
                m.edge("ABOUT", gid, svc, path, yp.line(akn, off))
                m.references.append((path, "Service", svc))
            m.guarantee_requires[gid] = list(g.get("requires", []) or [])
            rkn, _ = yp.mapping_get(item, "requires")
            for req in m.guarantee_requires[gid]:
                m.edge("REQUIRES", gid, req, path, yp.line(rkn, off))

        for item in yp.items(yp.mapping_get(doc, "assumptions")[1]):
            a = yp.safe_load(yaml.serialize(item))
            aid = a["id"]
            ln = yp.line(item, off)
            check = a.get("check")
            if check == "manual" or check is None:
                m.node("Assumption", aid, path, text=a.get("text", ""), check_kind="manual", op=None, rhs_const=None,
                       search_text=f"{aid} {a.get('text', '')}")
                att = a.get("attestation")
                if att and not (att.get("by") and att.get("date")):
                    m.errors.append(f"{aid}: attestation needs 'by' and 'date' (note: 'on' is a YAML boolean)")
                    att = None
                if att:
                    m.edge("ATTESTED", att["by"], aid, path, yp.line(yp.mapping_get(item, "attestation")[0], off),
                           on=to_ms(att.get("date")), review_by=to_ms(att.get("review_by")),
                           evidence=att.get("evidence"))
                    m.references.append((path, "Person", att["by"]))
            else:
                if check.get("op") not in ("<", "<=", "==", ">=", ">"):
                    m.errors.append(f"{aid}: unsupported operator {check.get('op')!r}")
                if ("rhs" in check) == ("rhs_const" in check):
                    m.errors.append(f"{aid}: exactly one of rhs or rhs_const is required")
                m.node("Assumption", aid, path, text=a.get("text", ""), check_kind="predicate", op=check.get("op"),
                       rhs_const=normalize_value(check.get("rhs_const")), search_text=f"{aid} {a.get('text', '')}")
                ckn, _ = yp.mapping_get(item, "check")
                m.edge("LHS", aid, check["lhs"], path, yp.line(ckn, off))
                m.references.append((path, "Fact", check["lhs"]))
                if "rhs" in check:
                    m.edge("RHS", aid, check["rhs"], path, yp.line(ckn, off))
                    m.references.append((path, "Fact", check["rhs"]))
            m.edge("STATED_IN", aid, sid, path, ln)

        _passages(m, sid, body, body_first)


def parse_texts(m: Model, root: Path, sha: str, repo: str | None) -> None:
    for file in sorted((root / "docs").rglob("*.md")):
        path = file.relative_to(root).as_posix()
        fm_text, body, first = _split_front_matter(file.read_text())
        fm = yp.safe_load(fm_text) if fm_text else {}
        sid = _source(m, path, "doc", sha, repo, title=path, ts=to_ms((fm or {}).get("updated")))
        for pid in (fm or {}).get("authors", []) or []:
            m.edge("AUTHORED", pid, sid, path, 2)
            m.references.append((path, "Person", pid))
        _passages(m, sid, body, first)

    tpath = "tickets/tickets.jsonl"
    if (root / tpath).exists():
        for ln, raw in enumerate((root / tpath).read_text().splitlines(), start=1):
            if not raw.strip():
                continue
            t = json.loads(raw)
            sid = f"src:ticket:{t['id']}"
            url = f"{repo}/blob/{sha}/{tpath}" if repo and re.fullmatch(r"[0-9a-f]{40}", sha) else None
            m.node("Source", sid, tpath, path=tpath, kind="ticket", url=url, commit_sha=sha, ts=to_ms(t["created_at"]),
                   search_text=f"{t['id']} {t['title']}", line=ln)
            m.edge("AUTHORED", t["author"], sid, tpath, ln)
            m.references.append((tpath, "Person", t["author"]))
            texts = [f"{t['title']}. {t['body']}"] + [c["body"] for c in t.get("comments", [])]
            for i, txt in enumerate(texts, start=1):
                pid = f"{sid}#p{i}"
                m.node("Passage", pid, tpath, text=txt, start_line=ln, end_line=ln, search_text="")
                m.edge("PART_OF", pid, sid, tpath, ln)

    cpath = "chat/chat.jsonl"
    if (root / cpath).exists():
        for ln, raw in enumerate((root / cpath).read_text().splitlines(), start=1):
            if not raw.strip():
                continue
            c = json.loads(raw)
            sid = f"src:chat:{c['id']}"
            url = f"{repo}/blob/{sha}/{cpath}" if repo and re.fullmatch(r"[0-9a-f]{40}", sha) else None
            m.node("Source", sid, cpath, path=cpath, kind="chat", url=url, commit_sha=sha, ts=to_ms(c["ts"]),
                   search_text=f"chat {c['channel']} {c['id']}", line=ln)
            m.edge("AUTHORED", c["author"], sid, cpath, ln)
            m.references.append((cpath, "Person", c["author"]))
            pid = f"{sid}#p1"
            m.node("Passage", pid, cpath, text=c["text"], start_line=ln, end_line=ln, search_text="")
            m.edge("PART_OF", pid, sid, cpath, ln)


def resolve_mentions(m: Model) -> None:
    """Deterministic MENTIONS: word bounded, case insensitive matches of ids, names and aliases."""
    patterns: list[tuple[re.Pattern, str]] = []
    for sid_, props in m.nodes["Service"].items():
        for term in {sid_, props["name"], *props.get("aliases", [])}:
            patterns.append((re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE), sid_))
    for label in ("Decision", "Guarantee", "Assumption"):
        for id_ in m.nodes[label]:
            patterns.append((re.compile(rf"\b{re.escape(id_)}\b"), id_))
    for pid, props in m.nodes["Passage"].items():
        found = {target for pat, target in patterns if pat.search(props["text"])}
        for target in sorted(found):
            m.edge("MENTIONS", pid, target, None, props.get("start_line"), method="alias")


def parse_repo(root: Path, commit_sha: str = "local", repo_url: str | None = None) -> Model:
    m = Model()
    parse_company(m, root, commit_sha, repo_url)
    parse_catalog(m, root, commit_sha, repo_url)
    parse_facts(m, root, commit_sha, repo_url)
    parse_adrs(m, root, commit_sha, repo_url)
    parse_texts(m, root, commit_sha, repo_url)
    resolve_mentions(m)
    return m
