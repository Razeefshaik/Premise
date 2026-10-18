"""Render terminates TLS before forwarding HTTP to Uvicorn.

Asset URLs must not depend on the internal request scheme or trusted proxy headers.
"""
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from premise.config import Settings
from premise.web.app import create_app


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.urls.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') in {'stylesheet', 'preload', 'icon'}:
            self.urls.append(attrs['href'])


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('path', ['/explore', '/benchmark', '/continuity'])
def test_assets_use_page_origin_behind_https_proxy(path, public, kestrel):
    http = TestClient(create_app(kestrel, Settings(public_demo=public, poll_enabled=False)),
                      base_url='http://internal-render-service')
    response = http.get(path, headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'premise.example'})
    assert response.status_code == 200, response.text
    assets = Assets()
    assets.feed(response.text)
    assert len(assets.urls) >= 7
    assert all(url.startswith('/static/') for url in assets.urls), assets.urls
    assert not any(url.startswith('http:') for url in assets.urls)
