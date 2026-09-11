"""Medição e fontes devem corresponder ao que o Chrome recebe, não à skin inteira."""
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'motor'))


def cena(tmp_path):
    p = tmp_path / 'crop.png'
    im = Image.new('RGB', (300, 100), 'white')
    im.paste('black', (0, 0, 100, 100))
    im.save(p)
    image = dict(id='foto', type='image', asset='cena', object_position='right center')
    scrim = dict(id='selo', type='scrim', asset_ref='cena', object_position='left center',
                 box=dict(x=0, y=0, w=80, h=80), style={'gradient':dict(auto_local=True,
                 cores_texto=['#FFFFFF'], cor_veu='#000000', contraste_alvo=4.5)})
    spec = dict(artboard={'base':{'w':100,'h':100}}, assets=[{'id':'cena','file':str(p)}],
                layers=[image,scrim])
    return spec, image, scrim


def test_contraste_usa_recorte_da_imagem_nao_copia_desatualizada_do_selo(tmp_path):
    from resolve import resolver_selo_local
    spec, image, scrim = cena(tmp_path)
    resolver_selo_local(spec, spec['layers'], scrim)
    assert scrim['contraste_local']['alpha'] > .4  # direita branca, NÃO esquerda preta
    assert scrim['contraste_local']['image_layer'] == image['id']
    assert scrim['contraste_local']['object_position'] == 'right center'


@pytest.mark.parametrize('defeito', ['ausente', 'duplicada', 'filtro', 'acima', 'interposta'])
def test_geometria_ambigua_nao_produz_recibo_otimista(tmp_path, defeito):
    from resolve import resolver_selo_local
    spec, image, scrim = cena(tmp_path)
    if defeito == 'ausente': spec['layers'].remove(image)
    if defeito == 'duplicada': spec['layers'].insert(0, dict(image, id='outra'))
    if defeito == 'filtro': image['filtro'] = 'brightness(2)'
    if defeito == 'acima': spec['layers'].reverse()
    if defeito == 'interposta': spec['layers'].insert(1, dict(id='placa',type='rect',fill='white'))
    with pytest.raises(ValueError): resolver_selo_local(spec, spec['layers'], scrim)
    assert 'contraste_local' not in scrim


def test_fontes_podadas_preservam_variaveis_e_italico_dos_runs():
    from resolve import fontes_usadas
    fonts = [dict(family='Archivo',weight=700,weight_range='100 900',file='a.ttf'),
             dict(family='Inter',weight=400,file='i.ttf'),
             dict(family='Serif',weight=400,style='italic',file='s.ttf'),
             dict(family='Serif',weight=400,file='sn.ttf')]
    layers = [dict(type='text',style={'font':{'family':'Archivo','weight':800}},
                   runs=[{'text':'Ênfase','fonte':{'family':'Serif','weight':400,'style':'italic'}}])]
    assert [f['file'] for f in fontes_usadas(layers, fonts)] == ['a.ttf','s.ttf']


def test_fonte_sem_face_declarada_nao_vira_fallback_silencioso():
    from resolve import fontes_usadas
    with pytest.raises(ValueError, match='face'):
        fontes_usadas([{'style':{'font':{'family':'Ausente','weight':400}}}], [])


def test_run_dual_preserva_os_defaults_italicos_do_renderer():
    from resolve import fontes_usadas
    fontes=[dict(family='Serif',weight=500,style='italic',file='i.ttf'),
            dict(family='Serif',weight=400,file='n.ttf')]
    usados=fontes_usadas([{'runs':[{'text':'ênfase','fonte':{'family':'Serif'}}]}],fontes)
    assert [f['file'] for f in usados]==['i.ttf']
