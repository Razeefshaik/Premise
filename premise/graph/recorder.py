"""Request-local graph traces, including overlapping and nested uses of one client."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import re
from threading import RLock
from time import perf_counter
from weakref import WeakKeyDictionary

_active = ContextVar("premise_query_recorders", default=())
_names = ContextVar("premise_query_names", default=())
_lock = RLock()
_installed = WeakKeyDictionary()
_SECRET_KEY = re.compile(r"token|password|passwd|secret|authorization|api.?key|credential", re.I)
_SECRET_VALUE = re.compile(r"(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+|sk-(?:ant-)?[A-Za-z0-9_-]{12,}|Bearer\s+\S+)", re.I)


def _safe(value, key="", depth=0, truncated=None, path=""):
    if _SECRET_KEY.search(key):
        return "[redacted]"
    if depth >= 12:
        if truncated is not None:
            truncated.append(path)
        return "[depth limit]"
    if isinstance(value, dict):
        return {str(k): _safe(v, str(k), depth + 1, truncated, path + "/" + str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if truncated is not None and len(value) > 20:
            truncated.append(path)
        return [_safe(v, depth=depth + 1, truncated=truncated, path=path + "/" + str(n))
                for n, v in enumerate(value[:20])]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[redacted]", value)
    return value


class QueryRecorder:
    """Temporarily wrap read/named/write; methods are restored after the last context.

    Wrappers may be shared by overlapping requests, but ContextVars select only the
    current request's recorder. Named calls are recorded once, at their underlying read.
    Rows are counts, never result bodies. Params are detached, redacted and list-bounded.
    """
    def __init__(self, client):
        self.client, self.entries, self._token = client, [], None

    def __enter__(self):
        if self._token is not None:
            raise RuntimeError("a QueryRecorder instance cannot be re-entered")
        client = self.client
        with _lock:
            state = _installed.get(client)
            if state is None:
                state = {"count": 0, "original": {}, "attributes": {}}
                for method in ("read", "named", "write"):
                    original = getattr(client, method)
                    state["original"][method] = original
                    state["attributes"][method] = client.__dict__.get(method)
                    setattr(client, method, self._wrapper(method, original))
                _installed[client] = state
            state["count"] += 1
        self._token = _active.set((*_active.get(), self))
        return self

    def _wrapper(self, method, original):
        client = self.client
        @wraps(original)
        def wrapped(*args, **kwargs):
            text = args[0] if args else kwargs["name" if method == "named" else "cypher"]
            params = args[1] if len(args) > 1 else kwargs.get("params")
            if method == "named":
                token = _names.set((*_names.get(), (client, text)))
                try:
                    return original(*args, **kwargs)
                finally:
                    _names.reset(token)
            recorders = [r for r in _active.get() if r.client is client]
            if not recorders:
                return original(*args, **kwargs)
            name = next((name for owner, name in reversed(_names.get()) if owner is client), "inline")
            truncated = []
            entry = {"name": name, "cypher": text, "params": _safe(params or {}, truncated=truncated),
                     "truncated_params": truncated,
                     "operation": method, "ms": 0.0, "rows": 0}
            started = perf_counter()
            try:
                result = original(*args, **kwargs)
                entry["rows"] = len(result)
                return result
            except Exception as exc:
                entry["error"] = type(exc).__name__  # no exception messages or credentials
                raise
            finally:
                entry["ms"] = (perf_counter() - started) * 1000
                for recorder in recorders:
                    # Entries are immutable snapshots, independent of caller param changes.
                    recorder.entries.append(dict(entry))
        return wrapped

    def __exit__(self, *exc):
        _active.reset(self._token)
        self._token = None
        with _lock:
            state = _installed[self.client]
            state["count"] -= 1
            if state["count"] == 0:
                for method, value in state["attributes"].items():
                    if value is None:
                        delattr(self.client, method)
                    else:
                        setattr(self.client, method, value)
                del _installed[self.client]
