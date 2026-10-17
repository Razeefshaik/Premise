"""Static guarantees for the showcase UI: one token source, accessible state colours, Explorer markup.

Browser behaviour (propagation labels, story mode, reduced motion, names) is exercised by
scripts/check_ui.py and scripts/check_replay.py through scripts/explorer_checks.py.
"""
from dataclasses import replace
import gzip
import re

from fastapi.testclient import TestClient

from conftest import NOW, ROOT
from premise.config import Settings
from premise.web.app import create_app

STATIC = ROOT / 'premise/web/static'


def tokens():
    text = re.sub(r'/\*.*?\*/', '', (STATIC / 'tokens.css').read_text(encoding='utf8'), flags=re.S)
    root = text[text.index(':root {'):text.index('}')]
    return dict(re.findall(r'--([\w-]+):\s*([^;]+);', root))


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_tokens_are_the_single_shared_source():
    for app in ('premise/web/static', 'premise_v2/web/static'):
        sheet = (ROOT / app / 'style.css').read_text(encoding='utf8')
        assert "@import url('tokens.css');" in sheet
        assert ':root {' not in sheet, 'tokens belong in tokens.css'
    assert (ROOT / 'premise/web/static/tokens.css').read_bytes() == (ROOT / 'premise_v2/web/static/tokens.css').read_bytes()
    values = tokens()
    for name in ('space-4', 'r-card', 'text-base', 'shadow-1', 'dur-hop', 'ease-out', 'ease-in'):
        assert name in values, name
    assert values['dur-hop'] == '220ms'
    reduced = (STATIC / 'tokens.css').read_text(encoding='utf8').split('prefers-reduced-motion: reduce')[1]
    assert '--dur-hop: 0ms' in reduced


def test_text_and_state_colours_meet_wcag_aa_on_every_surface():
    values = tokens()
    surfaces = [values['bg'], values['frame'], values['panel-solid'], values['panel-raised']]
    for name in ('ink', 'ink-2', 'ink-3', 'holds', 'unknown', 'broken', 'violated', 'indigo-2', 'ice'):
        for surface in surfaces:
            assert contrast(values[name], surface) >= 4.5, (name, surface, round(contrast(values[name], surface), 2))


def test_explorer_puts_the_verdict_above_the_canvas_with_story_controls(kestrel):
    app = create_app(kestrel, replace(Settings(), poll_enabled=False, llm_provider='none'), graph_api_at_ms=NOW)
    with TestClient(app) as http:
        page = http.get('/explore').text
    verdict, canvas, inspector = page.index('id="explorer-verdict"'), page.index('id="explorer-canvas"'), page.index('id="tab-whatif"')
    assert verdict < canvas < inspector
    assert re.search(r'id="explorer-verdict"[^>]*role="status"[^>]*aria-live="polite"', page)
    for control, label in (('story-prev', 'Previous step'), ('story-pause', 'Pause'), ('story-next', 'Next step'), ('story-exit', 'Exit story')):
        assert re.search(rf'id="{control}"[^>]*aria-label="{label}"', page), control
    assert 'Play the story' in page and 'id="story-caption"' in page
    assert 'tokens.css' not in page or 'style.css' in page


def test_hypothetical_banner_text_and_js_budget():
    assert 'Hypothetical. Nothing is stored or posted.' in (STATIC / 'consequences.js').read_text(encoding='utf8')
    added = ['explore.js', 'consequences.js', 'story.js', 'time.js', 'source.js', 'premise.js']
    size = sum(len(gzip.compress((STATIC / name).read_bytes())) for name in added)
    assert size < 150 * 1024, size
