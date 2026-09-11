"""Pixel math tests, with real RGB images and no network/provider."""
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'motor'))


def test_tinta_escura_em_cena_clara_nao_recebe_veu(tmp_path):
    from contraste_local import medir
    p=tmp_path/'cena.png'; Image.new('RGB',(100,100),'#f0eee8').save(p)
    r=medir(p,(100,100),dict(x=10,y=10,w=70,h=70),'center center',['#101C30'],'#FFFFFF',4.5)
    assert r['alpha']==0
    assert r['contraste_p05']>=4.5


def test_mede_so_a_zona_visivel_e_compoe_no_espaco_css(tmp_path):
    from contraste_local import medir
    p=tmp_path/'cena.png'
    im=Image.new('RGB',(100,100),'white'); im.paste('#222222',(0,0,50,100)); im.save(p)
    left=medir(p,(100,100),dict(x=0,y=0,w=40,h=100),'center center',['#F7F7F5'],'#000000',4.5)
    right=medir(p,(100,100),dict(x=60,y=0,w=40,h=100),'center center',['#F7F7F5'],'#000000',4.5)
    assert left['alpha']==0
    assert 0<right['alpha']<1
    assert right['contraste_p05']>=4.5


def test_zona_invalida_falha_sem_aprovar(tmp_path):
    from contraste_local import medir
    p=tmp_path/'cena.png'; Image.new('RGB',(100,100),'white').save(p)
    with pytest.raises(ValueError,match='zona'):
        medir(p,(100,100),dict(x=110,y=0,w=10,h=20),'center center',['#FFFFFF'],'#000000',4.5)


@pytest.mark.parametrize('pos', ['center', 'center center', '50% 50%'])
def test_posicoes_css_equivalentes(tmp_path, pos):
    from contraste_local import medir
    p=tmp_path/'cena.png'; Image.new('RGB',(200,100),'black').save(p)
    assert medir(p,(100,100),dict(x=0,y=0,w=100,h=100),pos,['#FFFFFF'],'#000000',4.5)['alpha']==0


def test_transparencia_nao_e_fundo_preto_por_acidente(tmp_path):
    from contraste_local import medir
    p=tmp_path/'cena.png'; Image.new('RGBA',(100,100),(0,0,0,0)).save(p)
    with pytest.raises(ValueError,match='transparente'):
        medir(p,(100,100),dict(x=0,y=0,w=100,h=100),'center',['#FFFFFF'],'#000000',4.5)
