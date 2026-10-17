"""Record 12 seconds of the real Explorer break/verified-repair flow as a GIF.

Requires Playwright, an installed Chromium browser, and Pillow. Start a local Premise
server, then set PREMISE_BASE_URL or pass --base. No graph writes or GitHub calls.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import time

from PIL import Image
from playwright.sync_api import sync_playwright


def main():
    import os
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default=os.getenv('PREMISE_BASE_URL','http://127.0.0.1:8000'))
    parser.add_argument('--output',type=Path,default=Path('docs/media/propagation.gif'))
    args=parser.parse_args()
    candidates=[Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]
    executable=next((str(path) for path in candidates if path.exists()),None)
    frames=[];times=[];seen=set();errors=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(**({'executable_path':executable} if executable else {}))
        page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.base.rstrip('/')+'/explore?focus=G_DEDUPE&depth=2',wait_until='networkidle')
        page.wait_for_function('window.premiseWhatIf && window.premiseStory && window.premiseExplorer.cy.nodes().length>5')
        banner=page.locator('#explorer-verdict').bounding_box()
        canvas=page.locator('#explorer-canvas').bounding_box()
        assert banner and canvas
        box={'x':banner['x'],'y':banner['y'],'width':banner['width'],
             'height':canvas['y']+canvas['height']-banner['y']}
        assert box['y']+box['height']<=900
        started=time.monotonic();broken=False;healed=False
        while time.monotonic()-started<12:
            elapsed=time.monotonic()-started
            if elapsed>=1 and not broken:
                page.evaluate("window.__recording = window.premiseWhatIf.apply({'paylane.retry_window_hours':72}); true")
                broken=True
            if elapsed>=6 and not healed:
                page.wait_for_function("window.premiseWhatIf.current?.verified_fixes.length>0")
                page.evaluate("window.__recording = window.premiseWhatIf.apply({'paylane.retry_window_hours':72,...window.premiseWhatIf.current.verified_fixes[0].changes}); true")
                healed=True
            times.append(time.monotonic()-started)
            seen.add(page.locator('#explorer-verdict').get_attribute('data-state'))
            frame=Image.open(BytesIO(page.screenshot(clip=box))).convert('RGB')
            frame.thumbnail((960,680),Image.Resampling.LANCZOS)
            frames.append(frame)
            page.wait_for_timeout(max(0,int((times[-1]+.125-(time.monotonic()-started))*1000)))
        page.wait_for_function("document.getElementById('explorer-verdict').dataset.state==='clear'")
        browser.close()
    assert not errors,errors
    assert 'blocked' in seen and 'clear' in seen,seen
    durations=[max(10,round((b-a)*100)*10) for a,b in zip(times,[*times[1:],12])]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.output,save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=True)
    with Image.open(args.output) as gif:
        duration=sum(gif.seek(i) or gif.info.get('duration',0) for i in range(gif.n_frames))
        assert 10000<=duration<=15000,duration
        print(json.dumps({'output':str(args.output),'frames':gif.n_frames,'duration_ms':duration,'bytes':args.output.stat().st_size,'states':sorted(seen),'page_errors':errors}))


if __name__=='__main__':main()
