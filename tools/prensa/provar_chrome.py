"""Prova comportamental offline: executar com o motor candidato e Chrome fixado.

Não é teste de presença de atributos: o fitter roda, mede os corpos finais e
recusa a zona impossível. A máscara é verificada nos pixels do screenshot.
"""
import argparse
import io
import json
import platform
import sys
from pathlib import Path


def provar(motor):
    sys.path.insert(0, str(motor))
    import render
    from PIL import Image
    from playwright.sync_api import sync_playwright

    font = dict(family='Inter',weight=400,weight_range='100 900',file='fonts/Inter-Variable.ttf')
    def texto(id, texto, min, max, prioridade, **extra):
        return dict(id=id,type='text',runs=[{'text':texto}],
                    style={'color':'#111111','font':dict(family='Inter',weight=400,line_height=1.2,**extra)},
                    fit=dict(mode='auto',min=min,max=max,max_lines=1,shrink_priority=prioridade))
    def spec(altura):
        head=texto('headline','Pé-de-Meia',32,100,0,variacao="'wght' 800")
        body=texto('apoio','Confira o cadastro',24,40,1)
        cta=texto('cta','Saiba mais',32,32,2)
        cta['fit']=dict(mode='fixed',size=32)
        return dict(fonts=[font],artboard={'base':{'w':1000,'h':700}},
                    layers=[dict(id='conteudo',type='frame',pos={'anchor':'top_left','x':40,'y':40},
                                 width=900,zona_h=altura,layout={'gap':12},children=[head,body,cta])])
    receipt={'platform':platform.machine(),'tests':{}}
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True,args=[
            '--disable-gpu','--force-color-profile=srgb','--font-render-hinting=none',
            '--disable-lcd-text','--hide-scrollbars'])
        receipt['chrome']=browser.version
        page=browser.new_page(viewport={'width':1000,'height':700},device_scale_factor=1)
        measured=[]
        for height in [300,180,50]:
            s=spec(height)
            page.set_content(render.monta_html(dict(layers=s['layers'],background='#FFFFFF'),s))
            r=page.evaluate(render.FIT_E_VERIFY_JS,dict(safe=dict(left=0,right=0,top=0,bottom=0),
                fontes=[{'familia':'Inter','peso':400}],clearance=0,exploracao=False))
            measured.append(r)
        normal,fit,impossible=measured
        assert normal['ok'], normal['problemas']
        assert fit['ok'], fit['problemas']
        n,f=normal['evidencia'],fit['evidencia']
        assert f['headline']['font_size_px'] < n['headline']['font_size_px']
        assert f['apoio']['font_size_px'] == n['apoio']['font_size_px']
        assert f['cta']['font_size_px'] == n['cta']['font_size_px'] == 32
        assert not impossible['ok'] and any('zona' in x for x in impossible['problemas'])
        assert f['headline']['peso']==800  # CSS weight continua 400; eixo pintado é 800
        receipt['tests']['fitter_prioridades']={'ok':True,'normal':n,'contido':f,
                                              'impossivel':impossible['problemas']}
        receipt['tests']['peso_variavel']={'ok':True,'declarado':400,'pintado':f['headline']['peso']}
        # Plano opaco/sem texto isola o alpha da máscara. Miolo deve manter o
        # alpha medido; transição deve ser contínua também na borda do miolo.
        scrim=dict(id='selo',type='scrim',box=dict(x=100,y=100,w=100,h=100),
                   fill_local='rgba(0,0,0,0.5)',feather=40,borda='dissolver')
        s=dict(fonts=[],artboard={'base':{'w':300,'h':300}})
        page.set_viewport_size({'width':300,'height':300})
        page.set_content(render.monta_html(dict(background='#FFFFFF',layers=[scrim]),s))
        im=Image.open(io.BytesIO(page.screenshot())).convert('RGB')
        samples={x:im.getpixel((x,150))[0] for x in [59,60,70,80,90,99,100,101,150,199,200,220,240]}
        assert abs(samples[99]-samples[100]) <= 4, samples
        assert abs(samples[100]-samples[150]) <= 1, samples
        assert 126 <= samples[150] <= 129, samples
        assert samples[60] > samples[80] > samples[99] >= samples[100], samples
        assert samples[240] == 255, samples
        receipt['tests']['mascara_pixels']={'ok':True,'amostras_sRGB':samples}
        browser.close()
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--motor',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    receipt=provar(args.motor)
    args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps(receipt,ensure_ascii=False))
