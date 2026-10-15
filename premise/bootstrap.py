"""Compose entry point: ingest local fixtures only if polling is disabled and the graph is empty."""
import uvicorn
from .config import settings
from .graph.client import GraphClient
from .reasoning.assess import graph_ready
from .ingest.run import ingest
from .web.app import create_app


def main():
    s=settings()
    client=GraphClient(s.falkordb_host,s.falkordb_port,s.graph_name)
    if not s.poll_enabled and not graph_ready(client)[0]:
        ingest(client,s.sandbox_dir,"local",f"https://github.com/{s.sandbox_repo}")
    uvicorn.run(create_app(client,s),host="0.0.0.0",port=8000)


if __name__=="__main__":
    main()
