"""Headless desktop/mobile QA of a running local demo. Install playwright separately."""
from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright


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
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(artifact/'assessment-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.goto(base+'/',wait_until='networkidle')
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
        for size in [{'width':1440,'height':1050},{'width':390,'height':844}]:
            page.set_viewport_size(size)
            page.goto(base+'/explore?focus=G_DEDUPE&depth=2',wait_until='networkidle')
            page.wait_for_function('window.premiseExplorer?.cy.nodes().length >= 5')
            page.locator('#explorer-canvas').scroll_into_view_if_needed()
            page.evaluate('window.premiseExplorer.cy.resize(); window.premiseExplorer.cy.fit(undefined,35)')
            position=page.evaluate("window.premiseExplorer.cy.getElementById('G_DEDUPE').renderedPosition()")
            box=page.locator('#explorer-canvas').bounding_box()
            page.mouse.click(box['x']+position['x'],box['y']+position['y'])
            page.locator('#node-details').filter(has_text='Each Paylane webhook').wait_for(timeout=8000)
            page.locator('#cypher-drawer summary').click()
            assert page.locator('#cypher-queries section').count()>0
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(artifact/f"explorer-{size['width']}.png"),full_page=True)
            page.locator('[data-explorer-preset="S1"]').click()
            page.locator('#explorer-verdict').filter(has_text='BLOCKED').wait_for()
            assert page.evaluate('window.premiseExplorer.cy.nodes(".broken").length')==4
            page.get_by_role('button',name='Apply verified fix').first.click()
            page.locator('#explorer-verdict').filter(has_text='CLEAR').wait_for()
            assert page.evaluate('window.premiseExplorer.cy.nodes(".broken").length')==0
        page.goto(base+'/benchmark',wait_until='networkidle')
        page.locator('#benchmark-chart svg').wait_for()
        assert page.locator('#benchmark-rows tr').count()==21
        page.screenshot(path=str(artifact/'benchmark-mobile.png'),full_page=True)
        browser.close()
        report={'page_errors':errors,'console_errors':console_errors,'mermaid_svg_rendered':graph,'desktop':[1440,1050],'mobile':[390,844]}
        (artifact/'ui-check.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        assert not errors
        assert not console_errors


if __name__=='__main__':
    main()
