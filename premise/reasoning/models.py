"""The AssessmentResult contract shared by the CLI, tests, renderer, and GitHub executor."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["BLOCKED", "NEEDS_REVIEW", "CLEAR_WITHIN_SCOPE", "ERROR"]
AssumptionState = Literal["holding", "violated", "unevaluable", "unverified"]
GuaranteeStatus = Literal["holds", "broken", "unknown"]


class Reason(BaseModel):
    code: str
    ids: list[str] = Field(default_factory=list)
    detail: str = ""
    pre_existing: bool = False


class ChangedFact(BaseModel):
    fact: str
    file: str
    line: int | None = None
    old: Any = None
    new: Any = None
    deleted: bool = False
    controlled_by: str = "us"


class AssumptionResult(BaseModel):
    id: str
    kind: str
    state: AssumptionState
    text: str = ""
    lhs_fact: str | None = None
    lv: Any = None
    op: str | None = None
    rhs_fact: str | None = None
    rv: Any = None
    attestations: list[dict[str, Any]] = Field(default_factory=list)
    touched: bool = False


class GuaranteeResult(BaseModel):
    id: str
    statement: str = ""
    status: GuaranteeStatus
    baseline: GuaranteeStatus | None = None
    chain: list[str] = Field(default_factory=list)
    tier: int | None = None
    promised_by: list[str] = Field(default_factory=list)
    relied_on_by: list[str] = Field(default_factory=list)
    about: list[str] = Field(default_factory=list)
    exposed_callers: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    person: str
    team: str
    evidence: int


class DecisionResult(BaseModel):
    id: str
    roles: list[str]
    via: list[str]
    active_accountable: list[str] = Field(default_factory=list)
    departed: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)


class CheckedDecision(BaseModel):
    """A related decision that was actually evaluated: its guarantee's full prerequisite set was checked."""
    decision: str
    via_guarantee: str
    sibling_of: str
    status: GuaranteeStatus


class Fix(BaseModel):
    changes: dict[str, Any]
    status: Literal["verified", "rejected", "partial"]
    failed: list[str] = Field(default_factory=list)
    origin: Literal["repair", "llm"] = "repair"
    rationale: str = ""


class AssessmentResult(BaseModel):
    pr: str | None = None
    head_sha: str | None = None
    graph_rev: int | None = None
    now_ms: int | None = None
    verdict: Verdict
    reasons: list[Reason] = Field(default_factory=list)
    changed_facts: list[ChangedFact] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    model_change: bool = False
    assumptions: list[AssumptionResult] = Field(default_factory=list)
    guarantees: list[GuaranteeResult] = Field(default_factory=list)
    decisions: list[DecisionResult] = Field(default_factory=list)
    not_affected: list[CheckedDecision] = Field(default_factory=list)
    checked_with_problems: list[CheckedDecision] = Field(default_factory=list)
    fixes: list[Fix] = Field(default_factory=list)
    fix_budget_used: int = 0

    def guarantee(self, gid: str) -> GuaranteeResult | None:
        return next((g for g in self.guarantees if g.id == gid), None)

    def by_status(self, status: str) -> list[str]:
        return sorted(g.id for g in self.guarantees if g.status == status)

    def assumptions_in(self, state: str) -> list[str]:
        return sorted(a.id for a in self.assumptions if a.state == state)
