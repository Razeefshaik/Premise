"""Injectable GitHub REST client. No credentials in URLs or error messages."""
from __future__ import annotations

from urllib.parse import quote
import httpx


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repo: str, token: str = "", transport=None):
        parts = repo.split("/")
        if len(parts) != 2 or any(not p or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in p) for p in parts):
            raise ValueError("SANDBOX_REPO must be owner/repository")
        self.repo = repo
        self.http = httpx.Client(base_url="https://api.github.com", timeout=30, transport=transport,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                     **({"Authorization": f"Bearer {token}"} if token else {})})

    def request(self, method, path, **kwargs):
        try:
            r = self.http.request(method, f"/repos/{self.repo}/{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub transport failure ({type(exc).__name__})") from None
        if r.status_code >= 400:
            raise GitHubError(f"GitHub {method} {path.split('?')[0]} returned HTTP {r.status_code}")
        return r

    def json(self, method, path, **kwargs):
        r = self.request(method, path, **kwargs)
        return r.json() if r.content else None

    def pages(self, path, params=None):
        out = []
        for page in range(1, 101):
            r = self.request("GET", path, params={**(params or {}), "per_page": 100, "page": page})
            out.extend(r.json())
            if 'rel="next"' not in r.headers.get("link", ""):
                return out
        raise GitHubError("Pagination limit exceeded; refusing an incomplete result")

    def pull(self, number):
        return self.json("GET", f"pulls/{int(number)}")

    def open_pulls(self, etag=None):
        r = self.request("GET", "pulls", params={"state": "open", "per_page": 100},
                         headers={"If-None-Match": etag} if etag else {})
        if r.status_code == 304:
            return None, etag
        rows = r.json()
        if 'rel="next"' in r.headers.get("link", ""):
            rows = self.pages("pulls", {"state": "open"})
        return rows, r.headers.get("etag")

    def status(self, sha, state, description, target_url=""):
        return self.json("POST", f"statuses/{sha}", json={"state": state, "context": "premise/decisions",
            "description": description[:140], **({"target_url": target_url} if target_url else {})})

    def upsert_comment(self, number, body):
        marker = f"<!-- premise:pr:{int(number)} -->"
        comments = self.pages(f"issues/{int(number)}/comments")
        existing = next((c for c in comments if marker in c.get("body", "") and c.get("user", {}).get("login") == self.actor()), None)
        content = body if marker in body else body + "\n\n" + marker
        if existing:
            return self.json("PATCH", f"issues/comments/{existing['id']}", json={"body": content})
        return self.json("POST", f"issues/{int(number)}/comments", json={"body": content})

    def actor(self):
        if not hasattr(self, "_actor"):
            r = self.http.get("/user")
            if r.status_code != 200:
                raise GitHubError("GitHub authentication failed")
            self._actor = r.json()["login"]
        return self._actor

    def file(self, path, ref):
        return self.json("GET", "contents/" + quote(path, safe="/"), params={"ref": ref})

    def close(self):
        self.http.close()
