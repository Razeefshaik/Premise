from __future__ import annotations

from pathlib import Path

from premise.ingest import yamlpos as yp
from premise.reasoning.models import AssessmentResult
from premise.scenarios import run_scenario

from conftest import NOW, SCENARIOS


def scenario(client, root: Path, name: str) -> AssessmentResult:
    return run_scenario(client, Path(root), SCENARIOS["scenarios"][name], NOW, SCENARIOS.get("since_days", 180))


def adhoc(client, root: Path, patches: list[dict]) -> AssessmentResult:
    return run_scenario(client, Path(root), {"title": "adhoc", "patches": patches}, NOW, 180)


def set_main(root: Path, file: str, key: str, value) -> None:
    p = Path(root) / file
    p.write_text(yp.set_value(p.read_text(), key, value))


def replace_in(root: Path, file: str, old: str, new: str) -> None:
    p = Path(root) / file
    text = p.read_text()
    assert old in text, f"{old!r} not in {file}"
    p.write_text(text.replace(old, new, 1))
