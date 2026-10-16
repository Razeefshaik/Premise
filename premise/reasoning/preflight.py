"""Read-only preflight proposals; never persist assessments or invoke a model."""
from __future__ import annotations

import math
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..graph.client import GraphUnavailable
from ..ingest.parse import normalize_value
from .assess import assess, graph_ready
from .intake import overlay_from_files
from .models import ChangedFact, Reason


def repo_path(path):
    if not path or len(path) > 240 or '\\' in path or ':' in path or '\0' in path or any(p in {'', '.', '..'} for p in path.split('/')):
        raise ValueError('Use a POSIX repository-relative path without traversal')
    return path


class ChangeItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    fact: str | None = Field(default=None, min_length=1, max_length=160)
    file: str | None = None
    key: str | None = Field(default=None, min_length=1, max_length=160)
    value: str | int | float | bool | None = None
    delete: bool | None = None

    @model_validator(mode='after')
    def validate_item(self):
        if not ((self.fact is not None and self.file is None and self.key is None) or
                (self.fact is None and self.file is not None and self.key is not None)):
            raise ValueError('Choose a fact id or a file and key')
        if self.file is not None:
            repo_path(self.file)
        if ('value' in self.model_fields_set) == ('delete' in self.model_fields_set):
            raise ValueError('Choose exactly one of value or delete=true')
        if 'value' in self.model_fields_set and (self.value is None or isinstance(self.value, float) and not math.isfinite(self.value)):
            raise ValueError('Value must be a finite JSON scalar; use delete=true for deletion')
        if 'delete' in self.model_fields_set and self.delete is not True:
            raise ValueError('Deletion requires delete=true')
        return self


class ChangeArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    changes: list[ChangeItem] = Field(min_length=1, max_length=20)
    include_fixes: bool = True


class FileArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    files: dict[str, str | None] = Field(min_length=1, max_length=10)
    include_fixes: bool = True

    @field_validator('files')
    @classmethod
    def validate_files(cls, files):
        for path, text in files.items():
            repo_path(path)
            if text is not None and len(text.encode('utf-8')) > 200_000:
                raise ValueError('Each file is limited to 200 KB')
        return files


ADVICE = {
    'BLOCKED': 'Do not apply this change alone. Apply a verified fix together with it, or ask the listed reviewers.',
    'NEEDS_REVIEW': 'Ask the listed reviewers and resolve missing or unverified evidence before applying this change.',
    'CLEAR_WITHIN_SCOPE': 'Every affected guarantee holds within the tracked scope. Untracked behavior is not assessed.',
    'ERROR': 'Assessment unavailable. Do not treat this result as permission to apply the change.',
}


def check_proposal(client, *, changes=None, files=None, include_fixes=True, at_ms=None, since_days=180):
    ready, _, why = graph_ready(client)
    if not ready:
        raise GraphUnavailable(why)
    issues, merged, paths, model_change = [], {}, [], False
    if files is not None:
        args = FileArgs(files=files, include_fixes=include_fixes)
        found, paths, model_change = overlay_from_files(client, args.files, issues=issues)
        active = {row['id'] for row in client.read(
            'MATCH (f:Fact) WHERE f.id IN $ids AND f.retired_rev IS NULL RETURN f.id AS id',
            {'ids':[c.fact for c in found]})}
        for c in found:
            if c.fact in active:
                merged[c.fact] = c
            else:
                issues.append(Reason(code='R_UNTRACKED',detail=f'{c.fact} is not a tracked fact; Premise has no evidence about its impact'))
    if changes is not None:
        args = ChangeArgs(changes=changes, include_fixes=include_fixes)
        # facts_by_id also serves historical assessments. Only current registry facts
        # may establish the scope of a new hypothetical proposal.
        active = {row['id'] for row in client.read(
            'MATCH (f:Fact) WHERE f.id IN $ids AND f.retired_rev IS NULL RETURN f.id AS id',
            {'ids': [item.fact for item in args.changes if item.fact]})}
        seen = set()
        for item in args.changes:
            rows = client.named('facts_by_id', {'ids': [item.fact]}) if item.fact in active else []
            if not item.fact:
                rows = client.named(
                'facts_by_file_key', {'file': item.file, 'key': item.key})
            if not rows:
                label = item.fact or f'{item.file}:{item.key}'
                issues.append(Reason(code='R_UNTRACKED', detail=f'{label} is not a tracked fact; Premise has no evidence about its impact'))
                continue
            f = rows[0]
            if f['id'] in seen:
                raise ValueError('A fact may be specified only once')
            seen.add(f['id'])
            new = None if item.delete else normalize_value(item.value)
            paths.append(f['file'])
            if item.delete or new != f['value'] or type(new) is not type(f['value']):
                merged[f['id']] = ChangedFact(fact=f['id'], file=f['file'], line=f['line'], old=f['value'],
                    new=new, deleted=bool(item.delete), controlled_by=f['controlled_by'])
            else:
                merged.pop(f['id'], None)
    result = assess(client, list(merged.values()), changed_paths=sorted(set(paths)), model_change=model_change,
                    at_ms=at_ms, since_days=since_days, run_repair=include_fixes)
    if issues and result.verdict != 'ERROR':
        result.reasons = issues + [r for r in result.reasons if r.code not in {'R_ALL_HOLD', 'R_NO_TRACKED_FACTS'}]
        if result.verdict != 'BLOCKED':
            result.verdict = 'NEEDS_REVIEW'
        result.fixes = []
    return compact(result)


def compact(result):
    return {'hypothetical': True, 'stored': False, 'graph_rev': result.graph_rev, 'verdict': result.verdict,
        'reasons': [r.model_dump(include={'code', 'detail'}) for r in result.reasons],
        'changed': [c.model_dump(include={'fact', 'old', 'new', 'controlled_by'}) for c in result.changed_facts],
        'not_holding': [g.model_dump(include={'id', 'status', 'baseline', 'tier', 'chain', 'promised_by'})
                        for g in result.guarantees if g.status != 'holds'],
        'decisions': [d.model_dump(include={'id', 'reviewers', 'departed'}) for d in result.decisions],
        'verified_fixes': [{'changes': f.changes} for f in result.fixes if f.status == 'verified'],
        'advice': ADVICE[result.verdict]}
