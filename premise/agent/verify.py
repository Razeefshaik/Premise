"""Answer grounding verification; citations are rendered exclusively from server tool rows."""
import json
import re

ID_TOKEN = re.compile(r"\b(?:ADR-\d{3}|[GA]_[A-Z_]+|[pt]_[a-z0-9_]+|(?:[a-z][a-z0-9_]*\.)+[a-z][a-z0-9_]*|[a-z]+service|webhookingress|refundworker)\b")
STATUS_TOKEN = re.compile(r"\b(holds|holding|broken|unknown|violated|unverified|unevaluable)\b", re.I)


def id_tokens(text):
    return set(ID_TOKEN.findall(text)) - {"e.g", "i.e"}


def status_rows(value, out, key=None):
    if isinstance(value, dict):
        entity = value.get("id", key)
        status = value.get("status", value.get("state"))
        if isinstance(entity, str) and entity.startswith(("G_", "A_")) and isinstance(status, str):
            out.setdefault(entity, set()).add(status)
        for name, child in value.items():
            status_rows(child, out, name)
    elif isinstance(value, list):
        for child in value:
            status_rows(child, out)


def statuses_match(text, evidence):
    """Conservative checks for explicit health words, not a verifier of arbitrary prose.

    Ambiguous multi-status clauses and negated health claims fall back to exact graph prose.
    """
    states = {}
    status_rows(evidence, states)
    text = text.replace("e.g.", "for example").replace("i.e.", "that is")
    for clause in re.split(r"(?<=[.!?;])\s+|\n", text):
        claims = {s.lower() for s in STATUS_TOKEN.findall(clause)}
        if not claims:
            continue
        ids = {i for i in id_tokens(clause) if i.startswith(("G_", "A_"))}
        if len(claims) == 1 and ids:
            state = next(iter(claims))
            prefix = "G_" if state in {"holds", "broken", "unknown"} else "A_"
            other_ids = {i for i in ids if not i.startswith(prefix)}
            if other_ids:
                # 'G_RATES_FRESH depends on unverified assumption A_RATES_SOURCE'
                # is a claim about the assumption, not an unverified guarantee.
                noun = r"\bguarantees?\b" if prefix == "G_" else r"\b(?:assumptions?|attestations?|prerequisites?)\b"
                if not re.search(noun, clause, re.I):
                    return False
                plain = clause.replace("*", "").replace("`", "")
                for entity in other_ids:
                    if re.search(rf"\b{re.escape(entity)}\b\s*(?:(?:is|are|was|remains|currently)\s+)*{state}\b", plain, re.I):
                        return False
                ids -= other_ids
        if not ids:
            # General statements such as 'Every guarantee holds' need all returned rows.
            prefix = "G_" if re.search(r"\bguarantees?\b", clause, re.I) else "A_" if re.search(r"\bassumptions?\b", clause, re.I) else None
            ids = {i for i in states if prefix and i.startswith(prefix)}
        if not ids or len(claims) != 1 or re.search(r"\b(?:not|never|no)\b|n't\b", clause, re.I):
            return False
        if any(states.get(i) != claims for i in ids):
            return False
    return True


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def verify_answer(answer, rows):
    if not isinstance(answer, dict) or not isinstance(answer.get("answer_markdown"),str):
        return False
    if answer.get("outcome") not in {"answered_with_path","answered_from_memory","not_in_graph","unknown_entity"}:
        return False
    # Caller-supplied arguments are not evidence. Unknown lookups cannot establish an entity.
    evidence=[]
    for row in rows:
        value=row.get("rows") if isinstance(row,dict) and "tool" in row and "rows" in row else row
        if isinstance(value,dict) and value.get("outcome")=="unknown_entity" and answer["outcome"]!="unknown_entity":
            continue
        evidence.append(value)
    known = set(strings(evidence))
    known.update(id_tokens(json.dumps(evidence)))
    text = answer["answer_markdown"]
    if re.search(r"https?://|\]\(", text):
        return False
    cited = answer.get("cited_ids", [])
    return (isinstance(cited,list) and all(isinstance(i,str) and i in known for i in cited)
            and id_tokens(text) <= known and statuses_match(text, evidence))
