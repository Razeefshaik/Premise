"""Behavioral checks for the remaining showcase pages, shared by live and replay QA."""
from playwright.sync_api import expect
import re


def assert_benchmark(page):
    expect(page.locator('#benchmark-graph-score')).to_have_text('0.789')
    expect(page.locator('#benchmark-best-score')).to_have_text('0.297')
    expect(page.locator('#benchmark-best-system')).to_contain_text('vector k=3')
    assert page.locator('#benchmark-rows tr').count()==21
    assert page.locator('.benchmark-bar').count()==7
    assert page.locator('.benchmark-value').count()==7
    assert 'Human review is pending' in page.locator('.benchmark-limits').inner_text()
    assert 'UTC' in page.locator('#benchmark-status').inner_text()
    assert not page.locator('.benchmark-details').evaluate('(el)=>el.open')
    page.locator('.benchmark-details summary').click()
    expect(page.locator('#benchmark-rows')).to_be_visible()
    page.locator('.benchmark-details summary').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def assert_continuity_controls(page):
    expect(page.locator('#continuity-status')).to_contain_text('Anika Rao')
    expect(page.get_by_role('button',name='Anika Rao',exact=True)).to_have_attribute('aria-pressed','true')
    page.wait_for_function('window.premiseContinuity?.data.person==="p_anika"')
    data=page.evaluate('window.premiseContinuity.data')
    expect(page.locator('#continuity-promise-count')).to_have_text(str(len(data['changed_guarantees'])))
    assert page.evaluate('window.premiseContinuity.cy.edges(".cut").length')>0
    assert page.evaluate('window.premiseContinuity.cy.nodes(".gone").data("caption")')=='Anika Rao'
    bridge=page.locator('#continuity-bridge').inner_text()
    assert not __import__('re').search(r'\d+\.\d{3}',bridge),bridge
    page.get_by_role('button',name='Jun Park',exact=True).click()
    expect(page.locator('#continuity-status')).to_contain_text('Jun Park')
    expect(page.get_by_role('button',name='Jun Park',exact=True)).to_have_attribute('aria-pressed','true')
    # The original select remains a functional alternative, including for keyboard users.
    page.locator('#departure-person').select_option('p_anika')
    expect(page.locator('#continuity-status')).to_contain_text('Anika Rao')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def assert_landing(page):
    expect(page.get_by_role('heading',level=1)).to_have_text(re.compile(r'Search finds documents\.\s*Premise finds consequences\.'))
    cta=page.get_by_role('link',name='Play the story',exact=True)
    expect(cta).to_have_attribute('href','/explore?story=1')
    if page.viewport_size['width']>1100:
        expect(cta).to_be_in_viewport()
    else:
        expect(cta).to_be_visible()
    assert page.locator('.showcase-stats>div').count()==3
    assert page.locator('.showcase-hero [data-fire]').count()==0
    assert page.locator('.network [data-fire]').count()==4
    assert page.locator('.network #fire-result').count()==1
    expect(page.get_by_role('heading',name='What still holds?',exact=True)).to_be_visible()


def assert_replay_landing(page):
    """The recorded landing: brain drawn from local files, fire chips answered from recorded checks."""
    expect(page.locator('.v3-replay')).to_be_visible()
    expect(page.locator('#hero-title')).to_contain_text('Premise finds consequences.')
    page.locator('#brain canvas').wait_for()
    story=page.locator('.showcase-story')
    assert story.get_attribute('href')=='./explore.html?story=1'
    expect(page.locator('#health-title')).to_contain_text('Recorded from FalkorDB')
    assert page.locator('.showcase-stats>div').count()==3
    chips=page.locator('[data-fire]')
    assert chips.count()==4
    for i in range(chips.count()):
        chips.nth(i).click()
        page.locator('#fire-result .verdict-line').wait_for()
        assert 'could not' not in page.locator('#fire-result').inner_text()
        chips.nth(i).click()
    assert all(a.startswith('./explore.html') for a in page.locator('.g-card').evaluate_all('els=>els.map(e=>e.getAttribute("href"))'))
    assert page.locator('#ask-form').count()==0
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
