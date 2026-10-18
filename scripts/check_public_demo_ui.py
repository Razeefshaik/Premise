"""Browser smoke for the public banner, real overlays and the public repair-preset story."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from explorer_checks import assert_canvas_in_first_screen, assert_hypothetical_status, assert_story_runs


def main():
    base = os.getenv('PREMISE_BASE_URL', 'http://127.0.0.1:8017').rstrip('/')
    target = Path('.runtime/public-demo-ui')
    target.mkdir(parents=True, exist_ok=True)
    candidates = [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
                  Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]
    executable = next((str(p) for p in candidates if p.exists()), None)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
        errors = []
        for width, height in ((1440, 900), (390, 844)):
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/explore', wait_until='networkidle')
            page.wait_for_function('window.premiseStory && window.premiseExplorer.cy.nodes().length > 5')
            expect(page.locator('.public-demo-banner')).to_contain_text('Public demo on FalkorDB Cloud')
            assert_canvas_in_first_screen(page)
            # Use the real API-backed stage method, preserving animation and label rendering.
            page.evaluate("async () => {const run = await window.premiseWhatIf.stage({'paylane.retry_window_hours':72}, {instant:true}); await run.all();}")
            assert_hypothetical_status(page)
            expect(page.locator('#explorer-verdict')).to_contain_text('4 guarantees broken')
            assert page.locator('#explorer-verdict .metal').count() == 0
            page.screenshot(path=str(target / f'explore-public-{width}.png'), full_page=True)
            assert_story_runs(page)
            page.close()
        browser.close()
        assert not errors, errors
    print('PASS: public desktop/mobile canvas, broken label, visible verdict, preset repair story; no page errors')


if __name__ == '__main__':
    main()
