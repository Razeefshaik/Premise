from __future__ import annotations

from pathlib import Path

import yaml

from ..envelope import AuthorRef, Envelope
from .base import ConnectorFailure, timestamp


class PagesConnector:
    name = "pages"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.scope = "pages:" + self.root.as_posix()

    def native(self, path):
        return f"{self.root.name}:{path.relative_to(self.root).as_posix()}"

    def list_keys(self):
        if not self.root.is_dir():
            raise OSError("page export directory is unavailable")
        return {f"pages:{self.native(p)}" for p in self.root.rglob("*.md") if not p.is_symlink()}

    def load(self, checkpoint=None):
        versions = dict((checkpoint or {}).get("versions", {}))
        try:
            paths = sorted(p for p in self.root.rglob("*.md") if not p.is_symlink())
            if not self.root.is_dir():
                raise OSError("missing export directory")
        except OSError:
            yield ConnectorFailure(scope=self.scope, error="cannot list page export")
            return checkpoint or {}
        current = {}
        for path in paths:
            native = self.native(path)
            try:
                raw = path.read_text(encoding="utf-8")
                if not raw.startswith("---\n"):
                    raise ValueError("missing front matter")
                header, separator, body = raw[4:].partition("\n---\n")
                if not separator:
                    raise ValueError("unterminated front matter")
                meta = yaml.safe_load(header)
                when = timestamp(meta["updated"])
                visibility = meta.get("visibility", "private")
                authors = meta.get("authors") or []
                if not isinstance(authors, list) or not all(isinstance(a, str) for a in authors):
                    raise ValueError("authors must be names or account ids")
                env = Envelope(source="pages", kind="page", scope=self.scope, entity_key=f"pages:{native}",
                               native_id=native, sequence=int(when.timestamp() * 1_000_000), time=when,
                               title=meta.get("title", path.stem), text=body, visibility=visibility,
                               author=AuthorRef(source_user_id=authors[0] if authors else None), container=self.root.name)
                current[native] = f"{env.sequence}:{env.content_hash}"
                if versions.get(native) != current[native]:
                    yield env
            except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
                yield ConnectorFailure(scope=self.scope, native_id=native, error=f"invalid page ({type(exc).__name__})")
        return {"versions": current}
