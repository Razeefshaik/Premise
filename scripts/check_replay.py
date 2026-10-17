"""Browser checks against a static HTTP server, never the live application API."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
from explorer_checks import assert_canvas_in_first_screen, assert_hypothetical_status, assert_continuity_names, assert_verdict_visible, assert_story_runs, assert_reduced_motion
from showcase_checks import assert_benchmark, assert_continuity_controls, assert_replay_landing


def main():
    base=os.environ.get('PREMISE_REPLAY_URL','http://127.0.0.1:8031').rstrip('/')
    artifact=Path('.runtime/v3-replay');artifact.mkdir(parents=True,exist_ok=True)
    candidates=[Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]
    executable=next((str(p) for p in candidates if p.exists()),None)
    errors=[];network=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(**({'executable_path':executable} if executable else {}))
        page=browser.new_page(viewport={'width':1440,'height':1050})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
        page.on('request',lambda request:network.append(request.url))
        for width in (1440,390):
            page.set_viewport_size({'width':width,'height':900 if width==1440 else 844})
            page.goto(base+'/index.html',wait_until='networkidle')
            assert_replay_landing(page)
            page.screenshot(path=str(artifact/f'landing-{width}.png'),full_page=True)
            page.locator('.showcase-story').click()
            page.wait_for_function('window.premiseStory?.index>=0')
            assert page.url.startswith(base+'/explore.html')
            page.goto(base+'/explore.html',wait_until='networkidle')
            page.wait_for_function('window.premiseExplorer?.cy.nodes().length>5')
            assert page.locator('.v3-replay').is_visible()
            assert_canvas_in_first_screen(page)
            assert_verdict_visible(page, 'Baseline')
            assert_story_runs(page)
            page.locator('#node-picker').select_option('G_DEDUPE')
            page.locator('#node-details').filter(has_text='Each Paylane webhook').wait_for()
            page.get_by_role('tab',name='What if',exact=True).click()
            page.locator('[data-explorer-preset="S1"]').click()
            page.locator('#explorer-verdict').filter(has_text='BLOCKED').wait_for()
            assert_hypothetical_status(page)
            page.screenshot(path=str(artifact/f'explore-blocked-{width}.png'),full_page=True)
            page.get_by_role('tab',name='What if',exact=True).click()
            page.get_by_role('button',name='Apply verified fix').first.click()
            page.locator('#explorer-verdict').filter(has_text='CLEAR').wait_for()
            assert_hypothetical_status(page,state='holds',assumption='holding',verdict='CLEAR')
            page.get_by_role('tab',name='Evidence',exact=True).click()
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(artifact/f'explore-{width}.png'),full_page=True)
            page.goto(base+'/explore.html?at=2027-03-02',wait_until='networkidle')
            page.wait_for_function('window.premiseExplorer?.cy.getElementById("G_DEDUPE").data("health")==="unknown"')
            page.goto(base+'/benchmark.html',wait_until='networkidle')
            page.locator('#benchmark-chart svg').wait_for()
            assert_benchmark(page)
            page.screenshot(path=str(artifact/f'benchmark-{width}.png'),full_page=True)
            page.goto(base+'/continuity.html?person=p_anika',wait_until='networkidle')
            page.locator('#continuity-promises').filter(has_text='A_STABLE_EVENT_ID').wait_for()
            assert_continuity_names(page)
            assert_continuity_controls(page)
            page.screenshot(path=str(artifact/f'continuity-{width}.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert_reduced_motion(browser, base+'/explore.html')
        browser.close()
    assert not errors,errors
    assert all(url.startswith(base) or url.startswith(('blob:','data:')) for url in network),network
    result={'errors':errors,'requests':len(network),'external_requests':0,'desktop':[1440,900],'mobile':[390,844],'hypothetical_labels':['broken','violated','holds'],'canvas_in_first_screen':True,'reviewer_names':True,'verdict_visible':True,'story_mode':True,'reduced_motion':True}
    (artifact/'browser.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':main()
