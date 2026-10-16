"""Fetch immutable revisions and read only files in the PR's merge-base diff."""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
import re
import subprocess


@dataclass
class PRFiles:
    head: dict[str, str | None]
    base: dict[str, str | None]


class GitRepo:
    def __init__(self, root: str | Path, url: str):
        self.root = Path(root).resolve()
        self.url = url

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, timeout=120)
        if p.returncode:
            raise RuntimeError(f"git {args[0]} failed (exit {p.returncode})")
        return p.stdout.decode("utf-8", errors="strict")

    def ensure(self):
        if not (self.root / ".git").exists():
            self.root.parent.mkdir(parents=True, exist_ok=True)
            p = subprocess.run(["git", "clone", "--no-checkout", self.url, str(self.root)], capture_output=True, timeout=120)
            if p.returncode:
                raise RuntimeError("Cannot clone sandbox repository")

    def main(self, branch="main"):
        self.ensure()
        self.git("fetch", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        sha = self.git("rev-parse", f"refs/remotes/origin/{branch}").strip()
        self.git("checkout", "--detach", sha)
        return sha

    def pr_files(self, number: int, expected_sha: str, main_sha: str):
        if not re.fullmatch(r"[0-9a-f]{40}", expected_sha) or not re.fullmatch(r"[0-9a-f]{40}", main_sha):
            raise ValueError("Expected immutable Git object ids")
        self.git("fetch", "origin", f"+refs/pull/{int(number)}/head:refs/premise/pr/{int(number)}")
        actual = self.git("rev-parse", f"refs/premise/pr/{int(number)}").strip()
        if actual != expected_sha:
            raise RuntimeError("PR head changed during intake; retry required")
        base = self.git("merge-base", main_sha, actual).strip()
        paths = self.git("diff", "--name-only", "-z", base, actual).split("\0")
        changed, original = {}, {}
        for path in filter(None, paths):
            exists = subprocess.run(["git", "-C", str(self.root), "cat-file", "-e", f"{actual}:{path}"], capture_output=True)
            changed[path] = None if exists.returncode else self.git("show", f"{actual}:{path}")
            exists = subprocess.run(["git", "-C", str(self.root), "cat-file", "-e", f"{base}:{path}"], capture_output=True)
            original[path] = None if exists.returncode else self.git("show", f"{base}:{path}")
        return PRFiles(head=changed, base=original)
