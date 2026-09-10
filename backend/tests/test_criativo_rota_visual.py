"""Um lote precisa cobrir território visual, e não só território de prosa.

O caso que originou este arquivo: quatro peças 1080x1350 sobre o Pé-de-Meia,
com ângulos, hipóteses e mecanismos de interrupção genuinamente diferentes — e a
mesma paleta azul-marinho, a mesma tarja de texto no topo e o mesmo adolescente
de perfil com celular nas quatro. `_distancia` aprovava, porque compara cinco
campos de estratégia e nenhum campo visual, e o recibo carimbava
META_CREATIVE_BATCH_DIVERSITY_VALID por cima do lote clonado.
"""
import pytest

from app.criativo.agente.contrato import SaidaDoAgente
from app.criativo.agente.validacao import SaidaCriativaInvalida, validar_saida
from test_criativo_agente_meta import pedido, saida


DIRECAO_BASE = {
    "blueprint_version": "volc.art-direction/2",
    "composicao": "Ponto focal à direita, headline no espaço aéreo à esquerda.",
    "tipografia": "Sans grotesca pesada, caixa alta e baixa, duas linhas.",
    "paleta_e_contraste": "Dominante azul-elétrico, apoio amarelo, tinta branca.",
    "cena": "Estudante em pátio de escola pública, luz de fim de tarde.",
    "tratamento": "Luz natural direcional, textura de tecido e pele preservada.",
}


def _lote(*eixos, **campos):
    """Monta um lote de N peças variando só o que o teste quer variar."""
    raw = saida(len(eixos))
    for indice, (rota, registro, presenca) in enumerate(eixos):
        raw["pecas"][indice]["direcao_de_arte"] = {
            **DIRECAO_BASE, "rota_de_texto": rota,
            "registro": registro, "presenca_humana": presenca,
        }
        raw["pecas"][indice].update(campos.get(indice, {}))
    return SaidaDoAgente.model_validate(raw)


def _pedido(n):
    return pedido(n)


def test_o_lote_reclamado_nao_passa_mais():
    """As quatro peças de 09/09/2026: eixos visuais idênticos, estratégia distinta."""
    clonado = _lote(
        ("campo_cromatico", "editorial", "close"),
        ("campo_cromatico", "editorial", "close"),
        ("campo_cromatico", "editorial", "close"),
        ("campo_cromatico", "editorial", "close"),
    )
    with pytest.raises(SaidaCriativaInvalida) as erro:
        validar_saida(_pedido(4), clonado)
    texto = str(erro.value)
    assert "mesma rota visual" in texto
    assert "campo_cromatico" in texto


def test_um_lote_com_eixos_ortogonais_passa():
    """Eixos ortogonais E densidade variada: as duas coisas que o portão exige.

    A densidade é CONTADA (headline + complemento + cta + selo + ressalva + cada
    item de checklist), então variar de verdade significa mudar quantos
    elementos a peça carrega — não trocar o rótulo.
    """
    lote = _lote(
        ("campo_cromatico", "editorial", "close"),
        ("integrado_na_cena", "foto_crua", "maos"),
        ("tipografia_protagonista", "grafico", "ausente"),
        ("rodape_limpo", "natureza_morta", "ausente"),
    )
    # A primeira ganha checklist e vira densa (6 blocos = 'alta'); as outras
    # continuam em 3 blocos ('minima'). É a variação que o portão exige.
    lote.pecas[0].direcao_de_arte.checklist = [
        "Veja quem pode consultar", "Entenda os critérios", "Confira o calendário",
    ]
    validar_saida(_pedido(4), lote)


def test_lote_com_densidade_constante_e_recusado():
    """Quatro peças com a mesma contagem de blocos não testam densidade."""
    lote = _lote(
        ("campo_cromatico", "editorial", "close"),
        ("integrado_na_cena", "foto_crua", "maos"),
        ("tipografia_protagonista", "grafico", "ausente"),
        ("rodape_limpo", "natureza_morta", "ausente"),
    )
    with pytest.raises(SaidaCriativaInvalida, match="densidade"):
        validar_saida(_pedido(4), lote)


def test_tarja_nao_pode_ser_a_arquitetura_de_quase_todo_o_lote():
    with pytest.raises(SaidaCriativaInvalida, match="campo_cromatico"):
        validar_saida(_pedido(4), _lote(
            ("campo_cromatico", "editorial", "close"),
            ("campo_cromatico", "foto_crua", "maos"),
            ("campo_cromatico", "documento", "ausente"),
            ("rodape_limpo", "natureza_morta", "ausente"),
        ))


def test_lote_inteiro_de_gente_testa_uma_coisa_so():
    with pytest.raises(SaidaCriativaInvalida, match="presenca_humana='ausente'"):
        validar_saida(_pedido(3), _lote(
            ("campo_cromatico", "editorial", "close"),
            ("integrado_na_cena", "foto_crua", "maos"),
            ("rodape_limpo", "documento", "ambiental"),
        ))


def test_lote_precisa_cobrir_registros_diferentes():
    with pytest.raises(SaidaCriativaInvalida, match="registro"):
        validar_saida(_pedido(3), _lote(
            ("campo_cromatico", "editorial", "close"),
            ("integrado_na_cena", "editorial", "maos"),
            ("rodape_limpo", "editorial", "ausente"),
        ))


def test_blueprint_v2_sem_eixos_e_recusado_antes_de_gastar():
    raw = saida(2)
    for peca in raw["pecas"]:
        peca["direcao_de_arte"] = dict(DIRECAO_BASE)
    with pytest.raises(SaidaCriativaInvalida, match="sem os eixos visuais"):
        validar_saida(_pedido(2), SaidaDoAgente.model_validate(raw))


def test_lote_pequeno_nao_recebe_exigencia_impossivel():
    """Duas peças não têm espaço para três registros; o portão não pode inventar isso."""
    validar_saida(_pedido(2), _lote(
        ("campo_cromatico", "editorial", "close"),
        ("integrado_na_cena", "foto_crua", "ausente"),
    ))


def test_blueprint_historico_sem_eixos_continua_valido():
    """Replay de aprovação antiga não é aprovação nova: v1 não conhece estes campos."""
    raw = saida(2)
    for peca in raw["pecas"]:
        peca.pop("direcao_de_arte", None)
    validar_saida(_pedido(2), SaidaDoAgente.model_validate(raw))
