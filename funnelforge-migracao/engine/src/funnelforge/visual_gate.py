"""Gate local sem servidor: python -m funnelforge.visual_gate DIRETORIO_DO_RUN."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from funnelforge.adapters.preview import document, elementor_body

CHECKS = r"""() => {
 const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
 const rect=e=>e.getBoundingClientRect();
 const text=document.querySelector('main').innerText;
 const checks={}; const evidence={};
 checks.horizontal_scroll=document.documentElement.scrollWidth<=innerWidth+1;
 checks.raw_markup=!/<!--\s*\/?wp:|\[su_|<\/?(?:div|p|h2)\b/.test(text);
 const headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(visible);
 checks.headings=headings.filter(e=>e.tagName==='H1').length===1 && headings.every((e,i)=>
   !i || +e.tagName[1]<=+headings[i-1].tagName[1]+1);
 evidence.headings=headings.map(e=>[e.tagName,e.innerText]);
 const main=rect(document.querySelector('main'));
 const leaves=[...document.querySelectorAll('main p,main h1,main h2,main h3,main li,main td,main th,main a,main summary')].filter(visible);
 const clipped=leaves.filter(e=>{
   if(e.closest('.wp-block-table'))return false;
   const r=document.createRange();r.selectNodeContents(e);const t=r.getBoundingClientRect();
   for(let p=e;p&&p!==document.body;p=p.parentElement){
     const s=getComputedStyle(p),b=rect(p);
     if(/hidden|clip/.test(s.overflowX)&& (t.left<b.left-2||t.right>b.right+2))return true;
     if(/hidden|clip/.test(s.overflowY)&& (t.top<b.top-2||t.bottom>b.bottom+2))return true;
   }return t.right>innerWidth+2||t.left < -2;
 });
 checks.text_clipping=!clipped.length;evidence.clipped=clipped.map(e=>e.innerText.slice(0,90));
 checks.edge_padding=leaves.every(e=>rect(e).left>=main.left+10 && rect(e).right<=main.right-10);
 const overlaps=[];
 for(const parent of document.querySelectorAll('main,main div')){
   const c=[...parent.children].filter(e=>visible(e)&&!['STYLE','SCRIPT'].includes(e.tagName));
   for(let i=0;i<c.length;i++)for(let j=i+1;j<c.length;j++){
     const a=rect(c[i]),b=rect(c[j]);
     if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2 &&
        Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)overlaps.push([c[i].id,c[j].id]);
   }
 }
 checks.overlap=!overlaps.length;evidence.overlaps=overlaps;
 checks.images=[...document.images].every(e=>e.hasAttribute('alt')&&e.complete&&e.naturalWidth>0&&rect(e).right<=innerWidth+1);
 const targets=[...document.querySelectorAll('.elementor-button,.wp-block-button__link,button,summary,input,select')].filter(visible);
 checks.targets_44=targets.every(e=>rect(e).width>=44&&rect(e).height>=44);
 evidence.small_targets=targets.filter(e=>rect(e).width<44||rect(e).height<44).map(e=>e.innerText);
 checks.tables=[...document.querySelectorAll('table')].every(e=>{
   const wrap=e.closest('.wp-block-table');return wrap && rect(wrap).right<=innerWidth+1 && getComputedStyle(wrap).overflowX==='auto';
 });
 checks.columns=innerWidth>=768||[...document.querySelectorAll('.wp-block-columns')].every(e=>getComputedStyle(e).flexDirection==='column');
 const rgb=s=>{const m=s.match(/[\d.]+/g);return m?m.map(Number):[0,0,0,0]};
 const lum=c=>c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
   .reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
 const badContrast=[];
 for(const e of [...document.querySelectorAll('main *,footer * ,footer')].filter(visible)){
   if(![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))continue;
   const s=getComputedStyle(e);const fg=rgb(s.color);let bg=[255,255,255];
   for(let p=e;p;p=p.parentElement){const c=rgb(getComputedStyle(p).backgroundColor);if(c.length===3||c[3]===1){bg=c;break;}}
   const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
   const large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&+s.fontWeight>=700);
   if(ratio<(large?3:4.5))badContrast.push({text:e.innerText.slice(0,80),ratio:+ratio.toFixed(2),fg:s.color,bg});
 }
 checks.contrast_AA=!badContrast.length;evidence.contrast=badContrast;
 const buttons=[...document.querySelectorAll('.elementor-button,.wp-block-button__link')].filter(visible);
 checks.cta_evident=!buttons.length||buttons.some(e=>{const s=getComputedStyle(e);return s.backgroundColor!==s.color&&parseInt(s.fontWeight)>=600;});
 checks.lp_fold=!document.querySelector('.elementor-button')||
   (headings.some(e=>e.tagName==='H1'&&rect(e).bottom<innerHeight)&&
    buttons.some(e=>rect(e).bottom<innerHeight)&&
    [...document.querySelectorAll('.e-widget p,.e-widget h2')].filter(visible).some(e=>rect(e).bottom<innerHeight));
 checks.text_wall=[...document.querySelectorAll('main p')].filter(visible).every(e=>e.innerText.length<=700);
 evidence.links=[...document.querySelectorAll('main a[href]')].map(e=>({text:e.innerText,href:e.getAttribute('href')}));
 evidence.interactives=document.querySelectorAll('details,button,input,select,canvas,iframe').length;
 return {checks,evidence};
}"""


def previews(run: Path, out: Path) -> tuple[list[dict], dict]:
    plan = json.loads((run / 'funnel_plan.json').read_text())
    config = json.loads((run / 'config_snapshot.json').read_text())
    site = config['site']
    footer = site.get('rodape_institucional', '') if site.get('rodape_institucional_persistente') else ''
    hardening = Path(__file__).resolve().parents[3] / 'referencia/hardening-wordpress/volc-funnel-hardening.css'
    extra_css = hardening.read_text() if hardening.exists() else ''
    docs = []
    for p in plan['pages']:
        n = p['page_number']
        if p['page_type'] == 'LANDING PAGE':
            source = run / 'p1.elementor.json'
            body, css = elementor_body(json.loads(source.read_text()))
        else:
            source = next(run.glob(f'p{n}.*.gutenberg.html'))
            body, css = f'<h1>{p["h1_title"]}</h1>' + source.read_text(), extra_css
        path = out / f'p{n}.preview.html'
        path.write_text(document(p['h1_title'], body, css=css, footer=footer))
        docs.append({'page': p, 'path': path, 'source': source,
                     'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    return docs, config


def audit(run: Path, out: Path | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    from funnelforge.pipeline.validators.checks import run_validators
    out = out or run / 'visual'
    out.mkdir(parents=True, exist_ok=True)
    docs, config = previews(run, out)
    state = json.loads((run / 'state.json').read_text())
    official = {u for urls in state.get('official_links', {}).values() for u in urls}
    official |= {f.get('source_url') for f in (state.get('dossie') or {}).get('fatos', [])}
    host = urlsplit(config['site']['domain']).hostname
    slugs = {d['page']['slug'] for d in docs}
    receipt = {'run': str(run), 'renderer': 'payload render_lp → árvore Elementor com estilos responsivos',
               'limitations': ['Sem PHP/DOM nativo Elementor e sem CSS completo do tema WordPress; '
                                'Gutenberg usa wrapper editorial e hardening versionado.',
                                'Shortcodes su_accordion simulados com details nativos; plugin real não exercitado.',
                                'Contraste calculado para cores sólidas; fontes locais substituem fontes remotas.',
                                'Alvos inline em prosa são exceção; mínimo 44×44 aplicado a botões/controles.',
                                'Sem anúncios/rede: CLS local não prova estabilidade com ads em produção.'],
               'proof_scope': 'preview local em Chromium; não é certificação do tema/plugin em produção',
               'pages': [], 'blocking': []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for d in docs:
                p = d['page'];n = p['page_number']
                for mode, viewport in [('mobile', {'width':390,'height':844}),
                                       ('desktop', {'width':1440,'height':1000})]:
                    context = browser.new_context(viewport=viewport, reduced_motion='reduce')
                    context.route('http://**', lambda route: route.abort())
                    context.route('https://**', lambda route: route.abort())
                    page = context.new_page();errors=[]
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('console', lambda m: errors.append(m.text) if m.type=='error' else None)
                    page.add_init_script("window.localCLS=0;new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)window.localCLS+=e.value})).observe({type:'layout-shift',buffered:true})")
                    page.goto(d['path'].resolve().as_uri(), wait_until='load')
                    page.wait_for_timeout(350)
                    result = page.evaluate(CHECKS)
                    checks = result['checks'];ev = result['evidence']
                    links_ok = all((urlsplit(l['href']).hostname==host and urlsplit(l['href']).path.strip('/').split('/')[-1] in slugs)
                                   or l['href'] in official for l in ev['links'])
                    checks['links_plan_and_verified_sources'] = links_ok
                    targets={r['target'].rstrip('/') for r in p.get('routes',[])}
                    checks['button_destinations_plan']=all(
                        (urlsplit(l['href']).path.strip('/').split('/')[-1] in targets
                         if urlsplit(l['href']).hostname==host else l['href'].rstrip('/') in targets)
                        for l in page.locator('.elementor-button,.wp-block-button__link').evaluate_all(
                            "es=>es.map(e=>({href:e.getAttribute('href')}))"))
                    button_ok = True;focus_ok = True;hover_ok = True
                    for link in page.locator('.elementor-button,.wp-block-button__link').all():
                        if not link.is_visible():continue
                        before=link.evaluate('(e)=>getComputedStyle(e).filter')
                        link.hover();after=link.evaluate('(e)=>getComputedStyle(e).filter')
                        hover_ok &= before!=after
                        link.evaluate("e=>e.addEventListener('click',ev=>{ev.preventDefault();e.dataset.clicked=e.href},{once:true})")
                        link.click()
                        button_ok &= link.evaluate('e=>e.dataset.clicked===e.href')
                    # Keyboard traversal uses actual Tab, not programmatic focus.
                    page.mouse.move(0,0);page.evaluate('document.activeElement.blur()')
                    page.evaluate('window.scrollTo(0,0)')
                    focusables=[e for e in page.locator('a[href],button,summary,input,select').all()
                                if e.is_visible()]
                    for index, element in enumerate(focusables):
                        element.evaluate('(e,i)=>e.dataset.auditFocus=String(i)', index)
                    expected=len(focusables)
                    reached=set()
                    for _ in range(expected+2):
                        page.keyboard.press('Tab')
                        active=page.evaluate("""()=>{const e=document.activeElement,s=getComputedStyle(e);return {
                          tag:e.tagName,key:e.dataset.auditFocus||'',focus:s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0}}""")
                        if active['tag']!='BODY':
                            reached.add(active['key']);focus_ok &= active['focus']
                    checks['keyboard_all_targets'] = len(reached)>=expected
                    checks['focus_visible'] = focus_ok
                    checks['hover_visible'] = hover_ok
                    checks['buttons_clickable'] = button_ok
                    toggle_ok=True
                    for detail in page.locator('details').all():
                        if not detail.is_visible():continue
                        summary=detail.locator('summary');was=detail.evaluate('e=>e.open')
                        summary.focus();page.keyboard.press('Enter')
                        toggle_ok &= detail.evaluate('e=>e.open')!=was
                        page.keyboard.press('Enter');toggle_ok &= detail.evaluate('e=>e.open')==was
                    checks['accordion_keyboard_toggle']=toggle_ok
                    checks['console_js']=not errors;ev['console']=errors
                    if d['source'].suffix=='.html':
                        issues=run_validators(['estrutura_da_redacao'],d['source'].read_text(),{})
                        checks['ad_paragraphs_top_level']=not issues
                        ev['ad_structure']=[i.code for i in issues]
                    else:checks['ad_paragraphs_top_level']=True
                    ev['local_cls']=page.evaluate('window.localCLS');checks['local_cls']=ev['local_cls']<.1
                    page.evaluate('window.scrollTo(0,0)');page.locator('body').click(position={'x':1,'y':1})
                    shot=out/f'p{n}.{mode}.png';page.screenshot(path=str(shot),full_page=True)
                    shots=[str(shot)]
                    if n==1:
                        fold=out/f'p{n}.{mode}.fold.png';page.screenshot(path=str(fold));shots.append(str(fold))
                    if page.locator('details').count():
                        page.locator('details').evaluate_all('es=>es.forEach(e=>e.open=true)')
                        opened=out/f'p{n}.{mode}.open.png';page.screenshot(path=str(opened),full_page=True);shots.append(str(opened))
                    item={'page':n,'viewport':mode,'source_sha256':d['sha256'],**result,
                          'screenshots':{s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in shots}}
                    receipt['pages'].append(item)
                    receipt['blocking'] += [f'p{n}/{mode}: {k}' for k,v in checks.items() if not v]
                    context.close()
        finally:browser.close()
    receipt['passed']=not receipt['blocking']
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args();receipt=audit(args.run,args.out)
    print(json.dumps({'passed':receipt['passed'],'blocking':receipt['blocking'],
                      'receipt':str((args.out or args.run/'visual')/'receipt.json')},ensure_ascii=False))
    raise SystemExit(0 if receipt['passed'] else 1)


if __name__=='__main__':main()
