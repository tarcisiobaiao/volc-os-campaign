"""Direction is data: preserve copy, protect supporting text, respect the scene."""
import hashlib
from pathlib import Path

import pytest
from test_criativo_prensa_tradutor import _spec, FAMILIA
from app.criativo.bancada.adaptadores import prensa_tradutor as T


def post(registro='documento', claro=False):
    spec = _spec()
    spec.direcao_de_arte['registro'] = registro
    if claro:
        spec.plano_de_composicao['nome'] = 'faixa_inferior_clara'
    return T.traduzir(spec, artboard=(1080,1350), ancora='Pé-de-Meia',
                      asset={'id':'cena','file':'out/cena.png','w':1080,'h':1350},
                      botao=True, versao_direcao='2')


def test_registros_tem_vozes_distintas_com_fontes_empacotadas():
    skin = T.skin_da_familia(FAMILIA, versao_direcao="2")
    regs = skin['type']['registros']
    assert regs['cartaz_beneficio']['display']['family'] == 'Barlow Condensed'
    assert regs['documento']['body']['family'] == 'Source Serif 4'
    assert regs['documento']['label']['family'] == 'IBM Plex Mono'
    assert len({r['display']['family'] for r in regs.values()}) >= 2
    root = Path(__file__).resolve().parents[2] / 'services/prensa/motor'
    for f in skin['fonts']:
        assert hashlib.sha256((root/f['file']).read_bytes()).hexdigest() == f['sha256']


def test_direcao_preserva_copy_e_ancora_sem_quebrar_palavra_composta():
    p = post()
    assert T.textos_de(p) == _spec().texto_exato
    assert [r['text'] for r in T.runs_da_headline(p) if r.get('accent')] == ['Pé-de-Meia']
    assert next(r for r in T.runs_da_headline(p) if r.get('accent'))['nowrap'] is True


def test_claro_escolhe_tinta_escura_e_selo_local_claro():
    p = post(claro=True)
    head = T.camadas_de_texto(p)[0]
    assert head['style']['color'] == '$color.ink.dark'
    selo = next(c for c in T.camadas_de(p) if c['id']=='selo')
    assert selo['style']['gradient']['auto_local'] is True
    assert selo['style']['gradient']['cor_veu'] == '#FFFFFF'
    assert 'box' in selo
    assert not any(c['type']=='vinheta' for c in T.camadas_de(p))


def test_apoio_tem_piso_legivel_e_prioridade_acima_do_display():
    p = post()
    texts={c['id']:c for c in T.camadas_de_texto(p)}
    assert texts['complemento']['fit']['min'] >= 32
    assert texts['complemento']['fit']['shrink_priority'] > texts['headline']['fit']['shrink_priority']
    assert texts['cta']['fit']['size'] >= 30
    assert 'halacao' not in texts['headline'].get('efeitos',{})


def test_legado_e_versao_desconhecida():
    old=T.traduzir(_spec(),artboard=(1080,1350),versao_direcao='1')
    assert T.camadas_de_texto(old)[0]['style']['font']=='$type.display'
    with pytest.raises(ValueError,match='direção'):
        T.traduzir(_spec(),artboard=(1080,1350),versao_direcao='999')


def test_tinta_do_botao_mede_a_cor_de_fundo():
    for familia in (FAMILIA,['branco','azul royal'],['preto','vermelho']):
        skin=T.skin_da_familia(familia, versao_direcao="2")
        assert T.contraste(skin['color']['ink']['on_accent'],skin['color']['accent']['text'])>=4.5


def test_cartaz_tem_coluna_propria_nao_o_mesmo_esqueleto():
    frame=lambda p: next(c for c in T.camadas_de(p) if c['id']=='conteudo')
    assert frame(post('cartaz_beneficio'))['max_width'] < frame(post('documento'))['max_width']


def test_skin_sem_versao_declarada_continua_sendo_a_v1():
    """⚠️ Ativação deliberada vale para as DUAS portas, ou não vale para nenhuma.

    `traduzir()` faz certo: sem versão declarada ele devolve v1. Mas
    `skin_da_familia()` nasceu com `versao_direcao="2"` como padrão, então a
    chamada natural — a que todo script existente faz — passou a devolver a skin
    nova de oito famílias.

    O efeito é pior que trocar as duas: quem chama o par sem argumento recebe
    SKIN v2 com LAYOUT v1, uma combinação que nenhum dos dois conjuntos de teste
    exercita. E um lote aprovado, regerado, volta com outros bytes sem ninguém
    ter pedido — que é exatamente o que a ativação deliberada existe para impedir.
    """
    from app.criativo.bancada.adaptadores import prensa_tradutor as T

    familia = ["azul royal", "amarelo ouro", "verde bandeira", "branco"]
    padrao = T.skin_da_familia(familia)
    v1 = T.skin_da_familia(familia, versao_direcao="1")

    assert padrao == v1
    assert {f["family"] for f in padrao["fonts"]} == {"Inter"}


def test_versao_desconhecida_diz_qual_valor_recusou():
    """Erro que não nomeia o valor recusado obriga quem depura a adivinhar."""
    from app.criativo.bancada.adaptadores import prensa_tradutor as T

    import pytest as _pytest
    with _pytest.raises(ValueError, match="7"):
        T.skin_da_familia(["azul royal", "branco"], versao_direcao="7")


def test_banner_tem_piso_de_cta_distinto_e_selo_nao_duplica_recorte():
    p=T.traduzir(_spec(),artboard=(1200,628),versao_direcao='2',
                 asset={'id':'cena','file':'out/cena.png','w':1200,'h':628})
    d=p['direcao_resolvida']
    assert d['cta_px'] > d['apoio_min_px']
    selo=next(c for c in T.camadas_de(p) if c['id']=='selo')
    assert 'object_position' not in selo
    assert selo['borda']=='dissolver'
