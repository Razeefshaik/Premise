"""Deterministic evidence and PR comment rendering."""
from __future__ import annotations

import re


def safe(text):
    return str(text).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;").replace("@", "＠").replace("\n", " ")


def mermaid(result):
    lines = ["flowchart LR"]
    seen = set()
    def node(value):
        return re.sub(r"[^A-Za-z0-9_]", "_", value)
    for g in result.guarantees:
        for parent, child in zip(g.chain, g.chain[1:]):
            seen.add(f'  {node(child)}["{safe(child)}"] --> {node(parent)}["{safe(parent)}"]')
        for did in g.promised_by:
            seen.add(f'  {node(g.id)} -. promises .-> {node(did)}["{did}"]')
        for did in g.relied_on_by:
            seen.add(f'  {node(g.id)} -. "relies on" .-> {node(did)}["{did}"]')
    lines.extend(sorted(seen))
    return "\n".join(lines) if seen else "flowchart LR\n  clear[\"No affected guarantee is broken\"]"


def provenance(client, ids):
    return client.read("MATCH (e:Entity)-[r:STATED_IN|DEFINED_IN]->(s:Source) WHERE e.id IN $ids "
        "RETURN e.id AS id, s.path AS path, s.url AS url, r.line AS line, s.commit_sha AS commit_sha ORDER BY id",
        {"ids": sorted(set(ids))}) if ids else []


def render_comment(result, number, url, sources=(), names=None):
    names = names or {}
    refs = {s["id"]: s for s in sources}
    def cite(entity):
        s = refs.get(entity)
        return f"[{safe(entity)}]({s['url'].split('#')[0]}#L{s['line']})" if s and (s.get("url") or "").startswith("https://github.com/") else f"`{safe(entity)}`"
    out = [f"## Premise: {result.verdict}", "", "### Reasons", ""]
    out += [f"- `{r.code}`{' (pre-existing)' if r.pre_existing else ''}: {safe(r.detail)}" for r in result.reasons]
    out += ["", "### What changed", "", "| Fact | Before | Proposed |", "| --- | --- | --- |"]
    out += [f"| {cite(c.fact)} | {safe(c.old)} | {safe(c.new) if not c.deleted else 'deleted'} |" for c in result.changed_facts]
    out += ["", "### Assumptions checked", "", "| Assumption | State | Evidence |", "| --- | --- | --- |"]
    for a in result.assumptions:
        evidence = f"{cite(a.lhs_fact)}: {safe(a.lv)} {safe(a.op)} {cite(a.rhs_fact) if a.rhs_fact else safe(a.rv)} ({safe(a.rv)})" if a.kind == "predicate" else safe(a.attestations)
        out.append(f"| {cite(a.id)} | {a.state} | {evidence} |")
    out += ["", "### How far it reaches", "", "```mermaid", mermaid(result), "```", "",
            "| Guarantee | Health | Tier | Promised by | Relied on by | Services / callers |", "| --- | --- | --- | --- | --- | --- |"]
    out += [f"| {cite(g.id)} | {g.status} | {g.tier} | {', '.join(cite(x) for x in g.promised_by)} | {', '.join(cite(x) for x in g.relied_on_by)} | {safe(', '.join(g.about + g.exposed_callers))} |" for g in result.guarantees]
    for heading, checked in [("Checked and not affected", result.not_affected), ("Checked, with a pre-existing problem", result.checked_with_problems)]:
        out += ["", f"### {heading}", ""]
        out += [f"- {cite(c.decision)} relies on {cite(c.via_guarantee)}, also provided by {cite(c.sibling_of)}: **{c.status}**." for c in checked] or ["No related decisions in this category."]
    out += ["", "### Who should review", ""]
    for d in result.decisions:
        reviewers = ', '.join(safe(names.get(x, x)) for x in d.reviewers) or "No active reviewer found"
        counts = ", ".join(f"{safe(names.get(c.person,c.person))}: {c.evidence} recent sources" for c in d.candidates)
        out.append(f"- {cite(d.id)}: {reviewers}. Departed or unavailable: {', '.join(safe(names.get(x,x)) for x in d.departed) or 'none'}. {counts}")
    out += ["", "### Verified fixes and rejected alternatives", ""]
    out += [f"- **{f.status}**: `{safe(f.changes)}`. {safe(f.rationale)} {'Fails: ' + ', '.join(f.failed) if f.failed else ''}" for f in result.fixes] or ["No verified remedy available."]
    out += ["", f"Graph revision {result.graph_rev}; head `{result.head_sha}`. [Assessment]({url}).",
            "", f"<!-- premise:pr:{int(number)} -->"]
    return "\n".join(out)
