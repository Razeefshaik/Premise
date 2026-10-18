from unittest.mock import Mock

from premise.config import Settings
from premise.graph.client import GraphClient


def test_cloud_auth_and_verified_tls_propagate_to_secondary_graph(monkeypatch):
    config = Settings(falkordb_username="demo", falkordb_password="test-secret", falkordb_tls=True)
    factory = Mock()
    monkeypatch.setattr("premise.graph.client.FalkorDB", factory)
    client = GraphClient.from_settings(config).sibling("isolated")
    client.graph
    options = factory.call_args.kwargs
    assert options["username"] == "demo" and options["password"] == "test-secret"
    assert options["ssl"] is True and options["ssl_check_hostname"] is True
    assert options["ssl_cert_reqs"] == "required"
    factory.return_value.select_graph.assert_called_once_with("isolated")
    assert "test-secret" not in repr(config) + repr(client)


def test_local_connection_defaults_are_unchanged(monkeypatch):
    factory = Mock()
    monkeypatch.setattr("premise.graph.client.FalkorDB", factory)
    GraphClient().graph
    assert factory.call_args.kwargs == dict(host="localhost", port=6379, socket_timeout=5, socket_connect_timeout=2)


def test_public_mode_overrides_unsafe_settings():
    config = Settings(public_demo=True, poll_enabled=True, auto_fix_pr=True, steward_enabled=True,
                      llm_provider="codex-cli", github_token="test-token", anthropic_api_key="test-key")
    assert not config.poll_enabled and not config.auto_fix_pr and not config.steward_enabled
    assert config.llm_provider == "none" and not config.llm_enabled
