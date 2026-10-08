from __future__ import annotations

import json
import os
import sys
import pytest

from funnelforge.adapters.preview import document, elementor_body
from funnelforge.visual_gate import CHECKS, main


def test_preview_preserva_arvore_estilo_e_breakpoint_do_payload():
    body,css=elementor_body([{'id':'hero','elType':'container',
        'settings':{'background_color':'#123456','hide_mobile':'hidden-mobile'},
        'elements':[{'id':'cta','widgetType':'button','settings':{
            'text':'Ver o saldo','link':{'url':'https://portal.test/rec/saldo'},
            'background_color':'#ffffff','button_text_color':'#111111'}}]}])
    assert body.index('el-hero')<body.index('el-cta')
    assert 'https://portal.test/rec/saldo' in body and 'color:#111111' in body
    assert '@media(max-width:767px){#el-hero{display:none}}' in css
    assert 'background-color:#123456' in css
    assert 'name="viewport"' in document('teste',body,css=css)


def test_cli_retorna_nao_zero_em_defeito_bloqueante(monkeypatch,tmp_path):
    monkeypatch.setattr('funnelforge.visual_gate.audit',lambda *a:{'passed':False,'blocking':['overflow']})
    monkeypatch.setattr(sys,'argv',['visual_gate',str(tmp_path)])
    with pytest.raises(SystemExit) as e:main()
    assert e.value.code==1


@pytest.mark.skipif(os.environ.get('FF_VISUAL_BROWSER')!='1',reason='execute FF_VISUAL_BROWSER=1 com Chromium permitido')
@pytest.mark.parametrize('defect,check',[
    ('<div style="width:2000px">Texto vazando</div>','horizontal_scroll'),
    ('<p style="color:#eee">Texto de baixo contraste</p>','contrast_AA'),
    ('<h4>Salto de heading</h4>','headings'),
    ('<p>&lt;!-- wp:paragraph --&gt;</p>','raw_markup'),
    ('<button style="padding:0;width:10px;height:10px">x</button>','targets_44'),
    ('<div style="overflow:hidden;width:50px"><p style="white-space:nowrap">Texto comprido cortado</p></div>','text_clipping'),
])
def test_browser_detecta_defeitos_reais(defect,check):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':390,'height':844})
            page.set_content(document('Teste','<h1>Pergunta útil</h1>'+defect))
            assert page.evaluate(CHECKS)['checks'][check] is False
        finally:browser.close()


@pytest.mark.skipif(os.environ.get('FF_VISUAL_BROWSER')!='1',reason='execute FF_VISUAL_BROWSER=1 com Chromium permitido')
def test_browser_gate_salva_recibo_prints_e_audita_interacao(tmp_path):
    from funnelforge.visual_gate import audit
    p={'page_number':2,'page_type':'SOLUTION','slug':'resposta','h1_title':'Uma resposta útil','routes':[]}
    (tmp_path/'funnel_plan.json').write_text(json.dumps({'pages':[p]}))
    (tmp_path/'config_snapshot.json').write_text(json.dumps({'site':{'domain':'https://portal.test'}}))
    (tmp_path/'state.json').write_text('{}')
    source=tmp_path/'p2.resposta.gutenberg.html'
    source.write_text('<!-- wp:paragraph --><p>Resposta curta e útil.</p><!-- /wp:paragraph -->'
                      '<!-- wp:paragraph --><p><a href="https://portal.test/rec/resposta">Mesmo link</a> '
                      'e <a href="https://portal.test/rec/resposta">Mesmo link</a>.</p><!-- /wp:paragraph -->'
                      '<!-- wp:html --><details><summary>Dúvida complementar</summary><p>Resposta.</p></details><!-- /wp:html -->')
    receipt=audit(tmp_path)
    assert receipt['passed'],receipt['blocking']
    assert (tmp_path/'visual/receipt.json').exists()
    assert len(list((tmp_path/'visual').glob('*.png')))==4
    source.write_text(source.read_text()+'<script>throw new Error("ativo quebrado")</script>')
    receipt=audit(tmp_path,tmp_path/'visual-defeito')
    assert not receipt['passed']
    assert 'p2/mobile: console_js' in receipt['blocking']
