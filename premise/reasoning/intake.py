"""Turn changed files into an overlay of proposed fact values. The registry of facts comes from the graph."""
from __future__ import annotations

from ..graph.client import GraphClient
from ..ingest import yamlpos as yp
from ..ingest.parse import is_model_path, normalize_value
from .models import ChangedFact


def overlay_from_files(client: GraphClient, changed: dict[str, str | None]) -> tuple[list[ChangedFact], list[str], bool]:
    """changed maps repo relative path to new text (None if the file was deleted).

    Returns (changed facts, changed paths, model_change). A fact whose key disappears is a deletion and evaluates
    as null, never as its old value.
    """
    paths = sorted(changed)
    model_change = any(is_model_path(p) for p in paths)
    facts = client.named("facts_in_files", {"files": paths}) if paths else []
    out: list[ChangedFact] = []
    for f in facts:
        text = changed[f["file"]]
        new, deleted, line = None, True, None
        if text is not None:
            _, vnode = yp.find(yp.compose(text), f["key"])
            if vnode is not None:
                new, deleted, line = normalize_value(yp.scalar_value(vnode)), False, yp.line(vnode)
        if deleted or new != f["value"] or type(new) is not type(f["value"]):
            out.append(ChangedFact(fact=f["id"], file=f["file"], line=line if line else f["line"], old=f["value"],
                                   new=new, deleted=deleted, controlled_by=f["controlled_by"]))
    return out, paths, model_change
