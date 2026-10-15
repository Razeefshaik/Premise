"""Test fixtures. Tests run against a real FalkorDB server, never a mock.

If FALKORDB_PORT points at a running server it is used (for example the Docker image); otherwise the FalkorDB module
shipped with the falkordblite wheel is started as a real redis-server process on a free port.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from premise.graph.client import GraphClient
from premise.ingest.parse import to_ms
from premise.ingest.run import ingest
from premise.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = ROOT / "sandbox" / "kestrel-platform"
SCENARIOS = load_scenarios(ROOT / "scenarios" / "scenarios.yaml")
NOW = to_ms(SCENARIOS["now"])


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="session")
def falkordb_port(tmp_path_factory):
    env_port = os.environ.get("FALKORDB_PORT")
    if env_port and _port_open(int(env_port)):
        yield int(env_port)
        return
    if not env_port and _port_open(6379):
        yield 6379
        return
    if os.name == "nt":
        pytest.fail("Start FalkorDB with docker compose up -d falkordb; Windows cannot run the Linux lite module")
    import redislite

    bindir = Path(redislite.__file__).parent / "bin"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    workdir = tmp_path_factory.mktemp("falkordb")
    proc = subprocess.Popen(
        [str(bindir / "redis-server"), "--port", str(port), "--loadmodule", str(bindir / "falkordb.so"),
         "--dir", str(workdir), "--save", ""],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        if _port_open(port):
            break
        time.sleep(0.1)
    yield port
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def new_graph(falkordb_port):
    """An empty, isolated graph that is deleted afterwards (one FalkorDB instance holds many graphs)."""
    clients: list[GraphClient] = []

    def make() -> GraphClient:
        c = GraphClient(port=falkordb_port, graph_name=f"premise_test_{uuid.uuid4().hex[:10]}")
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.delete_graph()


@pytest.fixture(scope="module")
def kestrel(falkordb_port):
    """The sandbox company ingested once per test module, read only."""
    c = GraphClient(port=falkordb_port, graph_name=f"premise_test_{uuid.uuid4().hex[:10]}")
    ingest(c, SANDBOX, "testsha", "https://github.com/example/kestrel-platform")
    yield c
    c.delete_graph()


@pytest.fixture
def repo_copy(tmp_path):
    """A writable copy of the sandbox, for tests that need a different main branch."""
    dst = tmp_path / "kestrel"
    shutil.copytree(SANDBOX, dst)
    return dst
