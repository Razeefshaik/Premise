"""Validation rules. Errors stop the revision; warnings are recorded on GraphState and shown to users."""
from __future__ import annotations

from .parse import Model

MAX_REQUIRES_DEPTH = 6


def _longest_chain(gid: str, model: Model, stack: tuple[str, ...], memo: dict[str, int], errors: list[str]) -> int:
    """Longest REQUIRES path (in edges) from a guarantee down to an assumption. Detects cycles."""
    if gid in stack:
        cycle = " -> ".join(stack[stack.index(gid):] + (gid,))
        errors.append(f"REQUIRES cycle: {cycle}")
        return 0
    if gid in memo:
        return memo[gid]
    best = 0
    for req in model.guarantee_requires.get(gid, []):
        if req in model.guarantee_requires:  # a guarantee
            best = max(best, 1 + _longest_chain(req, model, stack + (gid,), memo, errors))
        else:  # an assumption
            best = max(best, 1)
    memo[gid] = best
    return best


def _reaches_assumption(gid: str, model: Model, seen: set[str]) -> bool:
    if gid in seen:
        return False
    seen.add(gid)
    for req in model.guarantee_requires.get(gid, []):
        if req not in model.guarantee_requires:
            return True
        if _reaches_assumption(req, model, seen):
            return True
    return False


def validate(model: Model) -> tuple[list[str], list[str]]:
    errors = list(model.errors)
    warnings: list[str] = []
    ids = model.all_ids()

    # Rule 1: every reference resolves to an entity of the right kind.
    for path, kind, ref in model.references:
        if ids.get(ref) != kind:
            errors.append(f"{path}: unknown {kind} {ref!r}")
    for gid, reqs in model.guarantee_requires.items():
        for req in reqs:
            if ids.get(req) not in ("Guarantee", "Assumption"):
                errors.append(f"{gid}: requires unknown guarantee or assumption {req!r}")

    # Rules 3 and 4: REQUIRES is acyclic and at most 6 edges deep.
    memo: dict[str, int] = {}
    for gid in model.guarantee_requires:
        depth = _longest_chain(gid, model, (), memo, errors)
        if depth > MAX_REQUIRES_DEPTH:
            errors.append(f"{gid}: REQUIRES chain is {depth} edges deep (max {MAX_REQUIRES_DEPTH})")
    errors = list(dict.fromkeys(errors))  # a cycle is reported once per entry point otherwise

    # Rule 6: a provided guarantee that requires guarantee X means the providing decision relies on X.
    for did, provided in model.decision_provides.items():
        for gid in provided:
            for req in model.guarantee_requires.get(gid, []):
                if req in model.guarantee_requires and req not in model.decision_relies.get(did, []):
                    errors.append(f"{did}: provides {gid} which requires {req}, but {did} does not rely_on {req}")

    # Rule 7: supersedes targets are marked superseded.
    for new, old in model.supersedes:
        if model.decision_status.get(old) != "superseded":
            errors.append(f"{new} supersedes {old}, but {old} is not marked superseded")

    # Rule 8: every guarantee is about at least one service. Rule 9: every guarantee reaches an assumption.
    for gid in model.guarantee_requires:
        if not model.guarantee_about.get(gid):
            errors.append(f"{gid}: guarantee has no 'about' service")
        if not _reaches_assumption(gid, model, set()):
            errors.append(f"{gid}: guarantee requires no assumption, so it could never be checked")

    # Warnings: orphan assumptions, guarantees without an accepted provider, orphaned decisions.
    required = {r for reqs in model.guarantee_requires.values() for r in reqs}
    for aid in model.nodes["Assumption"]:
        if aid not in required:
            warnings.append(f"orphan assumption {aid}: no guarantee requires it")
    providers: dict[str, list[str]] = {}
    for did, provided in model.decision_provides.items():
        for gid in provided:
            providers.setdefault(gid, []).append(did)
    for gid in model.guarantee_requires:
        if not any(model.decision_status.get(d) == "accepted" for d in providers.get(gid, [])):
            warnings.append(f"guarantee {gid} has no accepted provider")
    people = model.nodes["Person"]
    accountable: dict[str, list[str]] = {}
    for e in model.edges["ACCOUNTABLE_FOR"]:
        accountable.setdefault(e["b"], []).append(e["a"])
    for did, status in model.decision_status.items():
        if status == "accepted" and not any(people.get(p, {}).get("status") == "active" for p in accountable.get(did, [])):
            warnings.append(f"orphaned decision {did}: nobody accountable is still active")
    return errors, warnings
