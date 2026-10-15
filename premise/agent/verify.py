"""Answer grounding verification; citations are rendered exclusively from server tool rows."""
import json
import re

ID_TOKEN = re.compile(r"\b(?:ADR-\d{3}|[GA]_[A-Z_]+|[pt]_[a-z0-9_]+|[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*|[a-z]+service|webhookingress|refundworker)\b")


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
    known = set(strings(rows))
    known.update(ID_TOKEN.findall(json.dumps(rows)))
    text = answer["answer_markdown"]
    if re.search(r"https?://|\]\(", text):
        return False
    cited = answer.get("cited_ids", [])
    return isinstance(cited,list) and all(isinstance(i,str) and i in known for i in cited) and set(ID_TOKEN.findall(text)) <= known
