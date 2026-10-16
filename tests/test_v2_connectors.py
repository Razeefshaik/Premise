import json

import pytest

from premise_v2.connectors import Connector, ConnectorFailure, GitHubConnector, PagesConnector
from premise_v2.pipeline import fixture_workers
from test_v2_pipeline import FIXTURES, FakeGitHub, pipeline, r, stream_name


def page(path, text="Paylane now retries for 72 hours."):
    path.write_text('---\nauthors: [p_anika]\nupdated: "2026-10-17T00:00:00Z"\nvisibility: public\n---\n' + text, encoding="utf-8")


def github_fixture(path):
    stamp = {"updated_at": "2026-10-17T00:00:00Z", "user": {"login": "anika"}}
    data = {"repository": {"full_name": "owner/repo", "private": False},
            "issues": [{**stamp, "number": 1, "title": "Policy", "body": "Paylane retries for 72 hours."}],
            "pulls": [{**stamp, "number": 2, "title": "bot PR", "body": "<!-- premise:v2:identity:1 -->"}],
            "issue_comments": [{**stamp, "id": 3, "issue_url": "https://api.github.com/repos/owner/repo/issues/1", "body": "Paylane retries for 72 hours."}],
            "review_comments": [{**stamp, "id": 4, "pull_request_url": "https://api.github.com/repos/owner/repo/pulls/2", "body": "bot echo"}],
            "files": [{**stamp, "path": "CODEOWNERS", "content": "config/* @payments\n"},
                      {**stamp, "path": "docs/policy.md", "content": "Paylane retries for 72 hours."}]}
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def test_all_four_connectors_conform_and_skip_premise_echoes(tmp_path):
    page(tmp_path / "policy.md")
    fixture = tmp_path / "github.json"
    github_fixture(fixture)
    connectors = fixture_workers(FIXTURES) + [PagesConnector(tmp_path), GitHubConnector("owner/repo", fixture=fixture)]
    assert {c.name for c in connectors} == {"slack", "jira", "github", "pages"}
    assert all(isinstance(c, Connector) for c in connectors)
    gh = connectors[-1]
    rows = list(gh.load(None))
    assert len(rows) == 4
    assert {e.kind for e in rows} == {"issue", "comment", "file", "page"}
    assert all("bot echo" not in e.text for e in rows)


def test_page_failure_retried_and_deletion_is_scoped(r, new_graph, stream_name, tmp_path):
    page(tmp_path / "good.md")
    bad = tmp_path / "bad.md"
    bad.write_text("bad metadata", encoding="utf-8")
    p = pipeline(r, new_graph, stream_name)
    p.workers = [PagesConnector(tmp_path)]
    first = p.run()
    assert len(first.connector_failures) == 1
    assert len(p.staging.live_keys(p.workers[0].scope)) == 1
    assert p.staging.checkpoint(p.workers[0].scope) is None
    page(bad)
    assert not p.run(load_decision=False).connector_failures
    assert len(p.staging.live_keys(p.workers[0].scope)) == 2
    assert p.staging.c.read("MATCH (f:ConnectorFailure) RETURN f.status AS s") == [{"s": "resolved"}]
    bad.unlink()
    assert p.run(load_decision=False).tombstones == 1
    assert len(p.staging.live_keys(p.workers[0].scope)) == 1


def test_checkpoint_crash_replays_without_duplicate_claims(r, new_graph, stream_name, tmp_path, monkeypatch):
    page(tmp_path / "policy.md")
    p = pipeline(r, new_graph, stream_name)
    p.workers = [PagesConnector(tmp_path)]
    p.staging.setup()
    p.load_decision_graph()
    original = p.stream.produce

    def crash_after_xadd(env):
        original(env)
        raise RuntimeError("crash before checkpoint")

    monkeypatch.setattr(p.stream, "produce", crash_after_xadd)
    with pytest.raises(RuntimeError, match="before checkpoint"):
        p.collect()
    assert p.staging.checkpoint(p.workers[0].scope) is None
    monkeypatch.setattr(p.stream, "produce", original)
    summary = p.run(load_decision=False)
    assert summary.gateway == {"stored": 1, "duplicate": 1}
    assert len(p.staging.active_claims()) == 1
    assert isinstance(p.staging.checkpoint(p.workers[0].scope), dict)


def test_github_ownership_is_not_chat(r, new_graph, stream_name, tmp_path):
    fixture = tmp_path / "github.json"
    github_fixture(fixture)
    p = pipeline(r, new_graph, stream_name)
    p.workers = [GitHubConnector("owner/repo", fixture=fixture)]
    p.run()
    rows = p.staging.c.read("MATCH (o:Ownership) RETURN o.pattern AS p, o.owners AS owners")
    assert rows == [{"p": "config/*", "owners": ["@payments"]}]
    assert p.staging.item("github:owner/repo/file/CODEOWNERS")["cls"] == "ownership"


def test_bad_slack_item_does_not_drop_following_good_item(r, new_graph, stream_name, tmp_path):
    data = json.loads((FIXTURES / "slack/payments.json").read_text())
    data["messages"].insert(0, {"type": "message", "text": "bad item", "ts": "bad"})
    root = tmp_path / "slack"
    root.mkdir()
    (root / "payments.json").write_text(json.dumps(data), encoding="utf-8")
    p = pipeline(r, new_graph, stream_name, fixtures=tmp_path)
    s = p.run()
    assert len(s.connector_failures) == 1
    assert s.produced["slack"] == 10


def test_bad_github_comment_is_data_not_a_generator_failure(tmp_path):
    fixture = tmp_path / "github.json"
    data = github_fixture(fixture)
    data["issue_comments"].insert(0, {"id": 99, "issue_url": "bad-url"})
    data["pulls"].append({"body": "invalid PR without a number"})
    fixture.write_text(json.dumps(data), encoding="utf-8")
    rows = list(GitHubConnector("owner/repo", fixture=fixture).load(None))
    assert sum(isinstance(e, ConnectorFailure) for e in rows) == 2
    assert sum(not isinstance(e, ConnectorFailure) for e in rows) == 4


def test_github_api_connector_only_uses_reads(r, new_graph, stream_name, tmp_path):
    import base64
    fixture = tmp_path / "github.json"
    data = github_fixture(fixture)

    class ReadGitHub(FakeGitHub):
        def json(self, method, path, **kwargs):
            assert method == "GET"
            self.calls.append((method, path))
            if path == "":
                return {**data["repository"], "default_branch": "main"}
            if path == "commits/main":
                return {"sha": "head", "commit": {"tree": {"sha": "tree"}}}
            if path == "git/trees/tree":
                return {"tree": [{"path": f["path"], "type": "blob"} for f in data["files"]]}
            raise AssertionError(path)

        def pages(self, path, params=None):
            self.calls.append(("GET", path))
            if path == "commits":
                return [{"commit": {"committer": {"date": "2026-10-17T00:00:00Z"}}}]
            return data[{"issues/comments": "issue_comments", "pulls/comments": "review_comments"}.get(path, path)]

        def file(self, path, ref):
            assert ref == "head"
            self.calls.append(("GET", f"contents/{path}"))
            value = next(f for f in data["files"] if f["path"] == path)
            return {"sha": "file-sha", "content": base64.b64encode(value["content"].encode()).decode()}

    gh = ReadGitHub()
    p = pipeline(r, new_graph, stream_name)
    p.workers = [GitHubConnector("owner/repo", github=gh)]
    summary = p.run()
    assert not summary.connector_failures and summary.produced["github"] == 4
    assert gh.calls and all(method == "GET" for method, _ in gh.calls)
