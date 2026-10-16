"""Source workers. Phase 1 reads fixture files shaped exactly like each source's API response,
so a live connector only has to fetch the same JSON.

Contract (Singer/Onyx style):
* ``fetch(cursor)`` is a generator that yields envelopes and RETURNS the new cursor last.
  The runner saves the cursor only after every yielded envelope is safely in the stream.
* ``list_keys()`` returns every entity key that currently exists, so the runner can emit
  explicit delete tombstones for items that disappeared.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Protocol

from .envelope import AuthorRef, Envelope


class SourceWorker(Protocol):
    name: str

    def fetch(self, cursor: str | None) -> Generator[Envelope, None, str | None]: ...

    def list_keys(self) -> set[str]: ...


def _slack_time(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def _jira_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(timezone.utc)


class SlackFixtureWorker:
    """Reads a conversations.history style export: {channel, users, messages}."""
    name = "slack"

    def __init__(self, path: str | Path, workspace_url: str = "https://kestrel.slack.example"):
        self.path, self.base = Path(path), workspace_url.rstrip("/")

    def _load(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        users = {u["id"]: u for u in data.get("users", [])}
        return data["channel"], users, data.get("messages", [])

    def _key(self, channel: dict, ts: str) -> str:
        return f"slack:{channel['id']}:{ts}"

    def list_keys(self) -> set[str]:
        channel, _, messages = self._load()
        return {self._key(channel, m["ts"]) for m in messages if m.get("type") == "message"}

    def fetch(self, cursor: str | None) -> Generator[Envelope, None, str | None]:
        channel, users, messages = self._load()
        newest = float(cursor) if cursor else 0.0
        high = newest
        for m in sorted(messages, key=lambda x: float(x["ts"])):
            if m.get("type") != "message":
                continue
            changed = float(m.get("edited", {}).get("ts", m["ts"]))
            if changed <= newest:
                continue
            high = max(high, changed)
            user = users.get(m.get("user"), {})
            thread = m.get("thread_ts")
            yield Envelope(
                entity_key=self._key(channel, m["ts"]), source="slack", kind="message",
                native_id=f"{channel['id']}:{m['ts']}", sequence=int(changed * 1_000_000),
                url=f"{self.base}/archives/{channel['id']}/p{m['ts'].replace('.', '')}",
                author=AuthorRef(source_user_id=m.get("user"), display_name=user.get("real_name"),
                                 email=(user.get("profile") or {}).get("email")),
                time=_slack_time(str(changed)), text=m.get("text", ""),
                thread=self._key(channel, thread) if thread and thread != m["ts"] else None,
                container=f"#{channel.get('name', channel['id'])}",
                visibility="private" if channel.get("is_private") else "public",
            )
        return f"{high:.6f}" if high else cursor


class JiraFixtureWorker:
    """Reads a /rest/api/3/search style response: {issues: [{key, fields}]}. Comments are separate items."""
    name = "jira"

    def __init__(self, path: str | Path, site_url: str = "https://kestrel.atlassian.example"):
        self.path, self.base = Path(path), site_url.rstrip("/")

    def _issues(self):
        return json.loads(self.path.read_text(encoding="utf-8")).get("issues", [])

    def list_keys(self) -> set[str]:
        keys = set()
        for issue in self._issues():
            keys.add(f"jira:{issue['key']}")
            for c in issue["fields"].get("comment", {}).get("comments", []):
                keys.add(f"jira:{issue['key']}#{c['id']}")
        return keys

    def fetch(self, cursor: str | None) -> Generator[Envelope, None, str | None]:
        since = _jira_time(cursor) if cursor else None
        high = since
        for issue in sorted(self._issues(), key=lambda i: i["key"]):
            f = issue["fields"]
            items = [(issue["key"], "ticket", f["reporter"], f["created"], f["updated"], f.get("summary"),
                      f.get("description") or "", None)]
            for c in f.get("comment", {}).get("comments", []):
                items.append((f"{issue['key']}#{c['id']}", "comment", c["author"], c["created"], c["updated"], None,
                              c.get("body") or "", f"jira:{issue['key']}"))
            for native, kind, person, _created, updated, title, body, parent in items:
                when = _jira_time(updated)
                if since and when <= since:
                    continue
                high = max(high, when) if high else when
                yield Envelope(
                    entity_key=f"jira:{native}", source="jira", kind=kind, native_id=native,
                    sequence=int(when.timestamp() * 1000),
                    url=f"{self.base}/browse/{issue['key']}" + (f"?focusedCommentId={native.split('#')[1]}" if parent else ""),
                    author=AuthorRef(source_user_id=person.get("accountId"), display_name=person.get("displayName"),
                                     email=person.get("emailAddress")),
                    time=when, title=title, text=body, thread=parent, container=f"Jira {issue['key'].split('-')[0]}",
                )
        return high.strftime("%Y-%m-%dT%H:%M:%S.000+0000") if high else cursor
