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
