"""Headless desktop/mobile QA of a running local demo. Install playwright separately."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright
from explorer_checks import assert_canvas_in_first_screen, assert_hypothetical_status, assert_continuity_names, assert_verdict_visible, assert_story_runs, assert_reduced_motion
from showcase_checks import assert_landing, assert_benchmark, assert_continuity_controls


def main():
    print('Starting headless UI check',flush=True)
    artifact=Path(os.getenv('PREMISE_UI_ARTIFACT_DIR','artifacts')); artifact.mkdir(parents=True,exist_ok=True)
    base=os.getenv('PREMISE_BASE_URL','http://localhost:8000').rstrip('/')
    candidates=[Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]
    executable=next((str(p) for p in candidates if p.exists()),None)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
        print('Browser started',flush=True)
        errors=[]
        console_errors=[]
        page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)
        page.goto(base+'/',wait_until='networkidle')
        print('Brain loaded',flush=True)
        page.get_by_role('heading',name='What still holds?').wait_for()
        assert_landing(page)
        assert page.locator('.g-card').count()>=9
        page.screenshot(path=str(artifact/'brain-desktop.png'),full_page=True)
        page.get_by_label('Your question').fill('Why ADR-012, and who owns it now?')
        page.get_by_role('button',name='Find graph evidence').click()
        page.locator('#answer h3').wait_for(timeout=60000)
        assert 'ADR-012' in page.locator('#answer').inner_text()
        assert 'p_jun' in page.locator('#answer').inner_text()
        print('Question answered with reviewer evidence',flush=True)
        page.get_by_role('link',name='#9001 Local demo S1:',exact=False).first.click()
        page.get_by_role('heading',name='Consequences, connected.').wait_for()
        page.wait_for_timeout(1500)
        graph=page.locator('.mermaid svg').count()>0
        page.screenshot(path=str(artifact/'assessment-desktop.png'),full_page=True)
        assert 'ADR-016' in page.locator('main').inner_text()
        reviewers=page.locator('[aria-labelledby="review-title"]').inner_text()
        assert 'Jun Park' in reviewers and 'p_jun' not in reviewers and 'p_anika' not in reviewers
        assert '(p_anika)' not in page.locator('[aria-labelledby="evidence-title"]').inner_text()
        page.set_viewport_size({'width':390,'height':844})
        assert page.locator('.page-head h1').evaluate('(el)=>el.scrollWidth<=el.clientWidth'), 'Assessment title is clipped'
        page.screenshot(path=str(artifact/'assessment-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.goto(base+'/',wait_until='networkidle')
        assert_landing(page)
        page.set_viewport_size({'width':768,'height':1024})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Tablet landing overflows'
        assert page.locator('.hero-copy').bounding_box()['y']+page.locator('.hero-copy').bounding_box()['height']<=page.locator('#brain').bounding_box()['y'], 'Tablet brain overlaps copy'
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(artifact/'brain-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.set_viewport_size({'width':1440,'height':1050})
        page.goto(base+'/what-if?set=paylane.retry_window_hours=72',wait_until='networkidle')
        page.locator('#check-verdict').filter(has_text='BLOCKED').wait_for()
        page.locator('#whatif-graph svg').wait_for()
        assert page.locator('#whatif-guarantees tbody tr').count()==4
        assert 'Jun Park' in page.locator('#whatif-decisions').inner_text()
        page.screenshot(path=str(artifact/'whatif-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(artifact/'whatif-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), page.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,children:[...document.body.children].map(e=>({tag:e.tagName,id:e.id,cls:String(e.className),right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})),overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth && !e.closest('.table-wrap')).map(e=>({tag:e.tagName,id:e.id,cls:String(e.className),right:e.getBoundingClientRect().right})).slice(0,20)})")
        page.get_by_role('button',name='Apply fix',exact=True).first.click()
        page.locator('#check-verdict').filter(has_text='CLEAR_WITHIN_SCOPE').wait_for()
        assert 'redis.max_ttl_hours' in page.url
        page.reload(wait_until='networkidle')
        page.locator('#check-verdict').filter(has_text='CLEAR_WITHIN_SCOPE').wait_for()
        for preset,expected in [('S6','NEEDS_REVIEW'),('S12','NEEDS_REVIEW')]:
            page.locator(f'[data-preset="{preset}"]').click()
            page.locator('#check-verdict').filter(has_text=expected).wait_for()
        for size in [{'width':1440,'height':900},{'width':390,'height':844}]:
            page.set_viewport_size(size)
            page.goto(base+'/explore?focus=G_DEDUPE&depth=2',wait_until='networkidle')
            page.wait_for_function('window.premiseExplorer?.cy.nodes().length >= 5')
            assert_canvas_in_first_screen(page)
            assert_verdict_visible(page, 'Baseline')
            page.locator('#graph-message').filter(has_text='nodes').wait_for()
            position=page.evaluate("window.premiseExplorer.cy.getElementById('G_DEDUPE').renderedPosition()")
            box=page.locator('#explorer-canvas').bounding_box()
            page.mouse.click(box['x']+position['x'],box['y']+position['y'])
            page.locator('#node-details').filter(has_text='Each Paylane webhook').wait_for(timeout=8000)
            page.locator('#cypher-drawer summary').click()
            assert page.locator('#cypher-queries section').count()>0
            page.locator('#cypher-drawer summary').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(artifact/f"explorer-{size['width']}.png"),full_page=True)
            if size['width']==1440:
                page.locator('#explorer-canvas').screenshot(path=str(artifact/'explorer-green.png'))
            page.get_by_role('tab',name='What if',exact=True).click()
            page.locator('[data-explorer-preset="S1"]').click()
            page.locator('#explorer-verdict').filter(has_text='BLOCKED').wait_for()
            page.evaluate('window.scrollTo(0,0)')
            assert_verdict_visible(page, 'BLOCKED')
            assert page.evaluate('window.premiseExplorer.cy.nodes(".broken").length')==4
            assert_hypothetical_status(page)
            page.screenshot(path=str(artifact/f"explorer-blocked-{size['width']}.png"),full_page=True)
            if size['width']==1440:
                page.locator('#explorer-canvas').screenshot(path=str(artifact/'explorer-red.png'))
            page.get_by_role('tab',name='What if',exact=True).click()
            page.get_by_role('button',name='Apply verified fix').first.click()
            page.locator('#explorer-verdict').filter(has_text='CLEAR').wait_for()
            assert page.evaluate('window.premiseExplorer.cy.nodes(".broken").length')==0
            assert_hypothetical_status(page,state='holds',assumption='holding',verdict='CLEAR')
            if size['width']==1440:
                page.locator('#explorer-canvas').screenshot(path=str(artifact/'explorer-fixed.png'))
        # Regression requested explicitly: a direct numeric proposal must label G_DEDUPE broken.
        page.goto(base+'/explore?focus=G_DEDUPE&depth=2&set=paylane.retry_window_hours=72',wait_until='networkidle')
        assert_hypothetical_status(page)
        page.get_by_role('tab',name='What if',exact=True).click()
        page.get_by_label('Proposed paylane.retry_window_hours',exact=True).fill('12')
        assert_hypothetical_status(page,state='holds',assumption='holding',verdict='CLEAR')
        page.get_by_role('tab',name='What if',exact=True).click()
        page.locator('.v3-fact').filter(has=page.locator('#slider-paylane-retry_window_hours')).get_by_role('button',name='Reset',exact=True).click()
        page.locator('#explorer-verdict').filter(has_text='Baseline').wait_for()
        page.locator('#node-picker').select_option('G_DEDUPE')
        page.locator('#node-status').filter(has_text='holds · Baseline').wait_for()
        for preset,target,state in [('S6','G_ADS_FRESH','broken'),('S12','G_RATES_FRESH','unknown')]:
            page.get_by_role('tab',name='What if',exact=True).click()
            page.locator(f'[data-explorer-preset="{preset}"]').click()
            page.locator('#explorer-verdict').filter(has_text='NEEDS_REVIEW').wait_for()
            page.locator('#node-picker').select_option(target)
            page.locator(f'#node-status[data-state="{state}"]').wait_for()
            assert page.evaluate('(id)=>window.premiseExplorer.cy.getElementById(id).style("label")',target)==target+'\n'+state
        page.goto(base+'/explore?focus=G_DEDUPE&depth=2&set=webhook.dedupe_ttl_hours=null',wait_until='networkidle')
        assert_hypothetical_status(page,state='unknown',assumption='unevaluable',verdict='NEEDS_REVIEW')
        page.goto(base+'/benchmark',wait_until='networkidle')
        page.locator('#benchmark-chart svg').wait_for()
        assert page.locator('#benchmark-rows tr').count()==21
        assert_benchmark(page)
        page.screenshot(path=str(artifact/'benchmark-mobile.png'),full_page=True)
        page.goto(base+'/continuity?person=p_anika',wait_until='networkidle')
        page.locator('#continuity-promises').filter(has_text='A_STABLE_EVENT_ID').wait_for()
        page.locator('#continuity-canvas canvas').first.wait_for()
        assert_continuity_names(page)
        assert_continuity_controls(page)
        page.screenshot(path=str(artifact/'continuity-mobile.png'),full_page=True)
        page.goto(base+'/entities/ADR-012',wait_until='networkidle')
        assert 'Jun Park' in page.locator('.entity-head').inner_text()
        assert 'p_jun' not in page.locator('.entity-head').inner_text()
        assert 'p_anika' not in page.locator('[aria-labelledby="reviewer-title"]').inner_text()
        page.goto(base+'/explore?at=2027-03-02',wait_until='networkidle')
        page.wait_for_function('window.premiseExplorer?.cy.getElementById("G_DEDUPE").data("health")==="unknown"')
        if page.locator('#xp-more-toggle').is_visible():
            page.locator('#xp-more-toggle').click()
        page.locator('#time-label').filter(has_text='Forecast').wait_for()
        page.locator('#explorer-verdict').filter(has_text='Anika Rao').wait_for()
        page.locator('#time-live').click()
        page.wait_for_function('window.premiseExplorer?.cy.getElementById("G_DEDUPE").data("health")==="holds"')
        for size in [{'width':1440,'height':900},{'width':390,'height':844}]:
            page.set_viewport_size(size)
            page.goto(base+'/explore',wait_until='networkidle')
            page.wait_for_function('window.premiseStory && window.premiseExplorer?.cy.nodes().length >= 5')
            assert_story_runs(page)
        page.set_viewport_size({'width':1440,'height':1050})
        assert_reduced_motion(browser, base+'/explore')
        assert_reduced_motion(browser, base+'/explore', {'width':390,'height':844})
        print('Story mode and reduced motion passed',flush=True)
        page.goto(base+'/',wait_until='networkidle')
        page.locator('#time-date').fill('2027-03-02')
        page.locator('#time-date').dispatch_event('change')
        page.locator('[data-guarantee="G_DEDUPE"] .badge').filter(has_text='unknown').wait_for()
        page.locator('#time-live').click()
        page.locator('[data-guarantee="G_DEDUPE"] .badge').filter(has_text='holds').wait_for()
        browser.close()
        report={'page_errors':errors,'console_errors':console_errors,'mermaid_svg_rendered':graph,'desktop':[1440,1050],'explorer_desktop':[1440,900],'mobile':[390,844], 'hypothetical_labels':['broken','violated','unknown','holds'],'canvas_in_first_screen':True,'reviewer_names':True,'verdict_visible':True,'story_mode':True,'reduced_motion':True}
        (artifact/'ui-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        assert not errors
        assert not console_errors


if __name__=='__main__':
    main()
