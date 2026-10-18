"""Official MCP stdio server exposing exactly the shared read tools."""
from mcp.server.fastmcp import FastMCP
from .config import settings
from .graph.client import GraphClient
from .graph.tools import GraphTools
from .reasoning.preflight import ChangeItem


def create_server(client=None):
    s = settings()
    tools = GraphTools(client or GraphClient.from_settings(s))
    server = FastMCP("Premise Company Brain")

    @server.tool()
    def check_change(changes: list[ChangeItem], include_fixes: bool = True) -> dict:
        """Hypothetical preflight of proposed facts. Stores nothing; posts nothing."""
        return tools.call('check_change', {'changes': [c.model_dump(exclude_unset=True) for c in changes], 'include_fixes': include_fixes})

    @server.tool()
    def check_files(files: dict[str, str | None], include_fixes: bool = True) -> dict:
        """Hypothetical preflight of full proposed files. Stores nothing; posts nothing."""
        return tools.call('check_files', {'files': files, 'include_fixes': include_fixes})

    @server.tool()
    def resolve(query: str, limit: int = 10) -> list:
        """Resolve a name to graph ids."""
        return tools.call("resolve", {"query":query,"limit":limit})

    @server.tool()
    def decision_lineage(id: str) -> dict:
        """Decision requirements, sources, lifecycle and reviewers."""
        return tools.call("decision_lineage",{"id":id})

    @server.tool()
    def guarantee_health(id: str | None = None) -> dict:
        """Current health of all prerequisites, including attestations."""
        return tools.call("guarantee_health",{"id":id})

    @server.tool()
    def who_knows(id: str) -> list:
        """Service ownership and evidence-ranked active experts."""
        return tools.call("who_knows",{"id":id})

    @server.tool()
    def search_evidence(query: str, limit: int = 10) -> list:
        """Find evidence passages with source citations."""
        return tools.call("search_evidence",{"query":query,"limit":limit})

    @server.tool()
    def orphaned_decisions() -> list:
        """Decisions without active accountable people."""
        return tools.call("orphaned_decisions",{})

    @server.tool()
    def load_bearing_guarantees(limit: int = 10) -> list:
        """PageRank over guarantee requirements."""
        return tools.call("load_bearing_guarantees",{"limit":limit})

    @server.tool()
    def impact_if_broken(id: str) -> dict:
        """Hypothetical graph impact of a broken assumption."""
        return tools.call("impact_if_broken",{"id":id})

    @server.tool()
    def recall(id: str) -> list:
        """Historical assessments for an entity."""
        return tools.call("recall",{"id":id})

    return server


def run():
    create_server().run(transport="stdio")
