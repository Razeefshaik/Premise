"""Read-only GitHub evidence. Fixtures mirror REST objects; no remote mutation methods are used."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from ..envelope import AuthorRef, Envelope
from .base import ConnectorFailure, timestamp


def is_premise(body):
    return isinstance(body, str) and "<!-- premise:" in body


class GitHubConnector:
    name = "github"

    def __init__(self, repo: str, github=None, fixture: str | Path | None = None):
        self.repo, self.github, self.fixture = repo, github, Path(fixture) if fixture else None
        self.scope = f"github:{repo}"
        self._keys = None

    def _snapshot(self):
        if self.fixture:
            return json.loads(self.fixture.read_text(encoding="utf-8"))
        gh = self.github
        if gh is None:
            raise ValueError("a fixture or GitHub client is required")
        repository = gh.json("GET", "")
        pulls = gh.pages("pulls", {"state": "all"})
        head = gh.json("GET", f"commits/{repository['default_branch']}")
        tree = gh.json("GET", f"git/trees/{head['commit']['tree']['sha']}", params={"recursive": "1"})
        if tree.get("truncated"):
            raise ValueError("incomplete repository tree")
        files = []
        for entry in tree["tree"]:
            path = entry["path"]
            if entry["type"] != "blob" or not (path in {"CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"}
                    or path.startswith("docs/") and path.endswith(".md")):
                continue
            try:
                obj = gh.file(path, head["sha"])
                commits = gh.pages("commits", {"path": path, "sha": head["sha"], "per_page": 1})
                files.append({"path": path, "content": base64.b64decode(obj["content"]).decode("utf-8"),
                              "updated_at": commits[0]["commit"]["committer"]["date"], "sha": obj["sha"]})
            except Exception as exc:
                files.append({"path": path, "error": type(exc).__name__})
        return {"repository": repository, "issues": gh.pages("issues", {"state": "all"}), "pulls": pulls,
                "issue_comments": gh.pages("issues/comments"), "review_comments": gh.pages("pulls/comments"),
                "files": files, "head_sha": head["sha"]}

    def load(self, checkpoint=None):
        self._keys = None
        try:
            data = self._snapshot()
            visibility = "private" if data["repository"].get("private", True) else "public"
        except Exception as exc:
            yield ConnectorFailure(scope=self.scope, error=f"cannot read GitHub snapshot ({type(exc).__name__})")
            return checkpoint or {}
        excluded = {p["number"] for p in data.get("pulls", []) if isinstance(p, dict)
                    and isinstance(p.get("number"), int) and is_premise(p.get("body"))}
        rows = []
        for kind, collection in [("issue", "issues"), ("pull_request", "pulls")]:
            for obj in data.get(collection, []):
                if not isinstance(obj, dict) or not isinstance(obj.get("number"), int):
                    yield ConnectorFailure(scope=self.scope, error="invalid issue or PR number")
                    continue
                if obj.get("number") in excluded or kind == "issue" and "pull_request" in obj:
                    continue
                rows.append((f"{kind}/{obj.get('number')}", kind, obj, None))
        for collection in ("issue_comments", "review_comments"):
            for obj in data.get(collection, []):
                try:
                    parent_url = obj.get("pull_request_url") or obj.get("issue_url", "")
                    number = int(parent_url.rstrip("/").split("/")[-1])
                    native = f"comment/{obj['id']}"
                except (KeyError, TypeError, ValueError, AttributeError):
                    yield ConnectorFailure(scope=self.scope, error="invalid GitHub comment identity")
                    continue
                if number in excluded:
                    continue
                parent_kind = "pull_request" if collection == "review_comments" or any(
                    isinstance(p, dict) and p.get("number") == number for p in data.get("pulls", [])) else "issue"
                rows.append((native, "comment", obj, f"github:{self.repo}/{parent_kind}/{number}"))
        for obj in data.get("files", []):
            path = obj.get("path") if isinstance(obj, dict) else None
            if not isinstance(path, str):
                yield ConnectorFailure(scope=self.scope, error="invalid GitHub file path")
                continue
            if path in {"CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"} or path.startswith("docs/") and path.endswith(".md"):
                rows.append((f"file/{path}", "file" if path.endswith("CODEOWNERS") else "page", obj, None))
        versions, old = {}, (checkpoint or {}).get("versions", {})
        self._keys = {f"github:{self.repo}/{native}" for native, *_ in rows}
        for native, kind, obj, parent in rows:
            try:
                if obj.get("error"):
                    raise ValueError("file could not be read")
                when = timestamp(obj.get("updated_at") or obj["created_at"])
                user = obj.get("user") or {}
                native = f"{self.repo}/{native}"
                env = Envelope(source="github", kind=kind, scope=self.scope, native_id=native,
                               entity_key=f"github:{native}", sequence=int(when.timestamp() * 1_000_000), time=when,
                               title=obj.get("title") or obj.get("path"), text=obj.get("body") or obj.get("content") or "",
                               thread=parent, url=obj.get("html_url"), container=self.repo, visibility=visibility,
                               author=AuthorRef(source_user_id=user.get("login"), display_name=user.get("name")))
                versions[native] = f"{env.sequence}:{env.content_hash}"
                if old.get(native) != versions[native]:
                    yield env
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                yield ConnectorFailure(scope=self.scope, native_id=native, error=f"invalid GitHub item ({type(exc).__name__})")
        return {"versions": versions, "head_sha": data.get("head_sha")}

    def list_keys(self):
        if self._keys is None:
            raise ValueError("a complete snapshot must be loaded before listing keys")
        return set(self._keys)
