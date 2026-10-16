from dataclasses import replace
from fastapi.testclient import TestClient
from premise.config import Settings
from premise.web.app import create_app


def test_explorer_page_and_pinned_local_library(kestrel):
    with TestClient(create_app(kestrel, replace(Settings(), poll_enabled=False, llm_provider='none'))) as http:
        response = http.get('/explore')
        assert response.status_code == 200 and 'explorer-canvas' in response.text
        assert 'cytoscape-3.30.4.min.js' in response.text
        assert http.get('/static/vendor/cytoscape-3.30.4.min.js').status_code == 200
        assert '/explore' in http.get('/').text
