"""Turn changed files into an overlay of proposed fact values. The registry of facts comes from the graph."""
from __future__ import annotations

import yaml

from ..graph.client import GraphClient
from ..ingest import yamlpos as yp
from ..ingest.parse import is_model_path, normalize_value
from .models import ChangedFact, Reason


def overlay_from_files(client: GraphClient, changed: dict[str, str | None], *,
                       base_files: dict[str, str | None] | None = None,
                       issues: list[Reason] | None = None) -> tuple[list[ChangedFact], list[str], bool]:
    """changed maps repo relative path to new text (None if the file was deleted).

    Compare head to merge base to select PR-owned edits, then overlay those edits on main.
    Without base_files (local scenarios), compare directly to the ingested main facts.
    Malformed YAML is reported per file through issues; callers without an issues sink raise.
    """
    paths = sorted(changed)
    model_change = any(is_model_path(p) for p in paths)
    facts = client.named("facts_in_files", {"files": paths}) if paths else []
    parsed, bases, invalid = {}, {}, set()
    yaml_paths = {f["file"] for f in facts} | {p for p in paths if p.endswith((".yaml", ".yml"))}
    for path in sorted(yaml_paths):
        try:
            parsed[path] = yp.compose(changed[path]) if changed[path] is not None else None
            if base_files is not None:
                bases[path] = yp.compose(base_files[path]) if base_files[path] is not None else None
        except yaml.YAMLError as exc:
            if issues is None:
                raise
            mark = getattr(exc, "problem_mark", None)
            location = f"{path}:{mark.line + 1}:{mark.column + 1}" if mark else path
            issues.append(Reason(code="R_UNPARSEABLE", detail=f"Malformed YAML in {location}; fix this file before assessment can complete"))
            invalid.add(path)
    out: list[ChangedFact] = []
    for f in facts:
        if f["file"] in invalid:
            continue
        new, deleted, line = None, True, None
        try:
            _, vnode = yp.find(parsed[f["file"]], f["key"])
            if vnode is not None:
                new, deleted, line = normalize_value(yp.scalar_value(vnode)), False, yp.line(vnode)
            if base_files is not None:
                _, before = yp.find(bases[f["file"]], f["key"])
                before_value = normalize_value(yp.scalar_value(before)) if before is not None else None
                if deleted == (before is None) and new == before_value and type(new) is type(before_value):
                    continue
        except yaml.YAMLError as exc:
            if issues is None:
                raise
            issues.append(Reason(code="R_UNPARSEABLE", detail=f"Malformed YAML value in {f['file']}:{line or f['line']}"))
            invalid.add(f["file"])
            continue
        if deleted or new != f["value"] or type(new) is not type(f["value"]):
            out.append(ChangedFact(fact=f["id"], file=f["file"], line=line if line else f["line"], old=f["value"],
                                   new=new, deleted=deleted, controlled_by=f["controlled_by"]))
    return [c for c in out if c.file not in invalid], paths, model_change
