import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'motor'))


def test_variacao_chega_ao_papel_principal():
    from render import html_texto
    html=html_texto(dict(id='h',runs=[{'text':'Teste'}],fit={'mode':'fixed','size':96},
        style={'color':'#fff','font':{'family':'Inter','variacao':"'opsz' 32, 'wght' 800"}}))
    assert "font-variation-settings:'opsz' 32, 'wght' 800" in html


def test_tratamento_desconhecido_recusa():
    from render import _tratamento_css
    with pytest.raises(SystemExit):
        _tratamento_css({'tipo':'knockuot'}, {})


def test_sangria_nao_apaga_sombra():
    from render import html_texto
    html=html_texto(dict(id='h',runs=[{'text':'Teste'}],fit={'mode':'fixed','size':96},
        style={'color':'#fff','shadow':'1px 0 0 red','font':{'family':'Inter'}},
        efeitos={'sombra':{'raio':8,'dy':2,'cor':'black'},'sangria':{'raio':'0.01em'}}))
    assert 'text-shadow:1px 0 0 red,0 2px 8px black,0 0 0.01em currentColor' in html
    assert html.count('text-shadow:')==1


def test_colunas_v2_medem_todos_os_textos():
    from render import html_layer
    c=dict(id='checklist',type='colunas',verificar=True,colunas=[{'titulo':'01','texto':'Conferir cadastro'}],
        style=dict(font_titulo={'family':'Inter'},font_corpo={'family':'Inter'},
                   cor_titulo='#111111',cor_corpo='#111111',cor_fio='#444444',fill='#ffff00'))
    html=html_layer(c,{'artboard':{'base':{'w':1080,'h':1350}}})
    assert html.count('data-verify')==2
    assert 'background:#ffff00' in html
    c['orientacao']='vertical'
    assert 'flex-direction:column' in html_layer(c,{'artboard':{'base':{'w':1080,'h':1350}}})
