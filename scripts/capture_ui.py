"""Capture every page at 1440x900 and 390x844 (first screen and full page) for UI review.

Usage: python scripts/capture_ui.py OUTPUT_DIR [--base http://127.0.0.1:8000]
"""
import argparse
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

SIZES = {'1440': {'width': 1440, 'height': 900}, '390': {'width': 390, 'height': 844}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip('/')
    candidates = [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'), Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]
    executable = next((str(p) for p in candidates if p.exists()), None)
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(**({'executable_path': executable} if executable else {}))
        probe = browser.new_page()
        probe.goto(base + '/', wait_until='load')
        assessment = probe.locator("a[href^='/assessments/']").last.get_attribute('href')
        probe.close()
        pages = [
            ('landing', '/', None),
            ('explore', '/explore', 'window.premiseExplorer?.cy.nodes().length>5'),
            ('explore-blocked', '/explore?focus=G_DEDUPE&depth=2&set=paylane.retry_window_hours=72', "document.querySelector('#explorer-verdict')?.textContent.includes('BLOCKED')"),
            ('explore-forecast', '/explore?at=2027-03-02', 'window.premiseExplorer?.cy.getElementById("G_DEDUPE").data("health")==="unknown"'),
            ('benchmark', '/benchmark', "document.querySelector('#benchmark-chart svg')"),
            ('continuity', '/continuity?person=p_anika', "document.querySelector('#continuity-canvas canvas')"),
            ('whatif', '/what-if?set=paylane.retry_window_hours=72', "document.querySelector('#whatif-graph svg')"),
            ('assessment', assessment, "document.querySelector('.mermaid svg')"),
            ('entity', '/entities/G_DEDUPE', None),
        ]
        for size, viewport in SIZES.items():
            for name, path, ready in pages:
                page = browser.new_page(viewport=viewport)
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                page.goto(base + path, wait_until='networkidle')
                if ready:
                    page.wait_for_function(ready, timeout=60000)
                page.wait_for_timeout(1200)
                page.screenshot(path=str(out / f'{name}-{size}.png'))
                page.screenshot(path=str(out / f'{name}-{size}-full.png'), full_page=True)
                canvas = page.locator('#explorer-canvas').bounding_box() if name.startswith('explore') else None
                report[f'{name}-{size}'] = {'errors': errors, 'overflow': page.evaluate('document.documentElement.scrollWidth>innerWidth'),
                                            'canvas': canvas}
                page.close()
        browser.close()
    (out / 'capture.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: {'errors': len(v['errors']), 'overflow': v['overflow']} for k, v in report.items()}))


if __name__ == '__main__':
    main()
