"""Shared live/replay browser regressions for the Explorer's visible state."""
from playwright.sync_api import expect


def assert_canvas_in_first_screen(page):
    """Run before clicking or scrolling: the entire graph must be in view."""
    assert page.evaluate('scrollY') == 0
    box = page.locator('#explorer-canvas').bounding_box()
    viewport = page.viewport_size
    assert box and box['y'] >= 0 and box['y'] + box['height'] <= viewport['height'], (box, viewport)
    assert box['x'] >= 0 and box['x'] + box['width'] <= viewport['width'], (box, viewport)
    banner = page.locator('#explorer-verdict').bounding_box()
    assert banner and banner['y'] + banner['height'] <= box['y'], (banner, box)


def assert_hypothetical_status(page, state='broken', assumption='violated', verdict='BLOCKED'):
    """Check the actual Cytoscape label, not just a red node or API response."""
    expect(page.locator('#explorer-verdict')).to_contain_text(verdict)
    label = page.evaluate("window.premiseExplorer.cy.getElementById('G_DEDUPE').style('label')")
    assert label == 'G_DEDUPE\n' + state, label
    page.locator('#node-picker').select_option('G_DEDUPE')
    expect(page.locator('#node-status')).to_have_attribute('data-state', state)
    expect(page.locator('#node-status')).to_contain_text('Hypothetical')
    expect(page.get_by_role('tab', name='Evidence', exact=True)).to_have_attribute('aria-selected', 'true')
    # Return to the canvas while the Evidence tab is active: the verdict stays visible.
    page.evaluate('scrollTo(0,0)')
    assert_canvas_in_first_screen(page)
    expect(page.locator('#explorer-verdict')).to_be_in_viewport()
    reviewers = page.locator('#node-details').inner_text()
    assert 'Jun Park' in reviewers and 'p_jun' not in reviewers, reviewers
    if assumption:
        label = page.evaluate("window.premiseExplorer.cy.getElementById('A_RETRY_WINDOW').style('label')")
        assert label == 'A_RETRY_WINDOW\n' + assumption, label
        page.locator('#node-picker').select_option('A_RETRY_WINDOW')
        expect(page.locator('#node-status')).to_have_attribute('data-state', assumption)
        page.locator('#node-picker').select_option('G_DEDUPE')
        expect(page.locator('#node-status')).to_have_attribute('data-state', state)


def assert_continuity_names(page):
    expect(page.locator('#continuity-status')).to_contain_text('Hypothetical departure')
    text = page.locator('#continuity-reviewers').inner_text()
    assert 'Jun Park' in text and 'p_jun' not in text and 'p_anika' not in text, text


def assert_verdict_visible(page, text):
    """The verdict banner is in the first screen, above the canvas, with its word fully shown."""
    expect(page.locator('#explorer-verdict')).to_contain_text(text)
    assert page.evaluate('scrollY') == 0
    banner = page.locator('#explorer-verdict').bounding_box()
    viewport = page.viewport_size
    assert banner and banner['y'] >= 0 and banner['y'] + banner['height'] <= viewport['height'], (banner, viewport)
    word = page.locator('#explorer-verdict .v-word')
    assert page.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1', word.element_handle()), 'verdict word is truncated'


def assert_story_runs(page, rate=8):
    """Play the story start to finish on the page's real data source, then exit back to baseline."""
    page.evaluate(f'window.premiseStory.rate = {rate}')
    page.locator('#story-play').click()
    seen = set()
    for _ in range(900):
        seen.add(page.evaluate('window.premiseStory.index'))
        if page.evaluate("document.getElementById('story-caption').textContent.startsWith('That is Premise')"):
            break
        page.wait_for_timeout(100)
    steps = page.evaluate('window.premiseStory.steps')
    assert seen >= set(range(steps)), (sorted(seen), steps)
    assert page.evaluate("window.premiseExplorer.cy.getElementById('G_DEDUPE').data('health')") == 'unknown'
    page.keyboard.press('Escape')
    page.wait_for_function("document.getElementById('story-bar').hidden && document.getElementById('explorer-verdict').dataset.state === 'baseline'")
    assert page.evaluate("window.premiseExplorer.cy.getElementById('G_DEDUPE').data('health')") == 'holds'


def assert_reduced_motion(browser, url, viewport=None):
    """Reduced motion applies the same states instantly: no travelling signals, the story still steps."""
    context = browser.new_context(viewport=viewport or {'width': 1440, 'height': 900}, reduced_motion='reduce')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto(url, wait_until='networkidle')
    page.wait_for_function('window.premiseStory && window.premiseExplorer.cy.nodes().length > 5')
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--dur-hop').trim()") == '0ms'
    page.locator('#story-play').click()
    page.wait_for_function('window.premiseStory.index === 0')
    for index in (1, 2, 3, 4):
        page.keyboard.press('ArrowRight')
        page.wait_for_function(f'window.premiseStory.index === {index}')
    page.locator('#explorer-verdict').filter(has_text='BLOCKED').wait_for()
    assert page.evaluate("window.premiseExplorer.cy.$('.signal').length") == 0
    label = page.evaluate("window.premiseExplorer.cy.getElementById('G_DEDUPE').style('label')")
    assert label == 'G_DEDUPE\nbroken', label
    page.keyboard.press('Escape')
    page.wait_for_function("document.getElementById('explorer-verdict').dataset.state === 'baseline'")
    context.close()
    assert not errors, errors
