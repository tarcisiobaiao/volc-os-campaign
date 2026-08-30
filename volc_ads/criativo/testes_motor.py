"""Testes da porta do motor, do falso e da ponte para o FunnelForge.

Rodar da raiz do projeto:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/criativo -q

**Nenhum teste aqui gera imagem de verdade.** O motor falso roda na máquina e o
gerador do FunnelForge chega dublado — com a MESMA assinatura do port real
(`generate(prompt, size) -> bytes` mais `last_usage` opcional), que é o que
torna o dublê uma prova de tradução de contrato e não uma prova de si mesmo.

O teste que fecha o arquivo percorre o ciclo inteiro — pedido, geração, assets,
catálogo, validação — porque cada peça isolada pode estar certa e o encaixe
errado: foi assim que a copy descobriu que o juiz e o contador mediam coisas
diferentes.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads.criativo import requisitos, validacao  # noqa: E402
from volc_ads.criativo.adaptadores import funnelforge_imagem as ponte  # noqa: E402
from volc_ads.criativo.adaptadores.falso import Defeito, MotorFalso  # noqa: E402
from volc_ads.criativo.catalogo import Catalogo, assets_da_resposta  # noqa: E402
from volc_ads.criativo.contrato import TipoDeAsset  # noqa: E402
from volc_ads.criativo.porta import (  # noqa: E402
    ArquivoGerado,
    GeracaoPendente,
    MotorDeCriativo,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
)

QUANDO = datetime(2026, 8, 26, 12, 0, 0)
DISPLAY = requisitos.exigencia_de("DISPLAY")
PMAX = requisitos.exigencia_de("PERFORMANCE_MAX")


def _pedido(tipo=TipoDeAsset.IMAGEM_MARKETING, quantidade=1,
            insumo="banner do FGTS", exigencia=DISPLAY):
    return PedidoDeGeracao(
        referencia="FGTS 2026",
        tipo=tipo,
        insumo=insumo,
        quantidade=quantidade,
        especificacao=exigencia.de(tipo),
    )


# ── o pedido se recusa a nascer incompleto ──────────────────────────────────


def test_pedido_sem_referencia_ou_sem_insumo_nao_nasce():
    with pytest.raises(ValueError, match="referência"):
        PedidoDeGeracao(referencia="  ", tipo=TipoDeAsset.HEADLINE, insumo="x")
    with pytest.raises(ValueError, match="insumo"):
        PedidoDeGeracao(referencia="FGTS", tipo=TipoDeAsset.HEADLINE, insumo="")


def test_pedido_com_especificacao_de_outro_tipo_e_recusado():
    # Pedir logo com a especificação da imagem de marketing produziria um
    # arquivo do tamanho errado, pago, que só a validação descobriria depois.
    with pytest.raises(ValueError, match="especificação de"):
        PedidoDeGeracao(
            referencia="FGTS", tipo=TipoDeAsset.LOGO_QUADRADO, insumo="logo",
            especificacao=DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING),
        )


def test_arquivo_gerado_tem_bytes_ou_texto_nunca_os_dois():
    with pytest.raises(ValueError, match="nunca os dois"):
        ArquivoGerado(conteudo=b"x", texto="x")
    with pytest.raises(ValueError, match="nunca os dois"):
        ArquivoGerado()


# ── o motor falso cumpre a porta ────────────────────────────────────────────


def test_os_dois_motores_cumprem_o_protocolo():
    assert isinstance(MotorFalso(), MotorDeCriativo)
    assert isinstance(ponte.MotorDeImagemFunnelForge(_GeradorDublê()), MotorDeCriativo)


def test_o_falso_e_deterministico_entre_instancias():
    # É isto que permite provar a deduplicação: dois motores diferentes, mesmo
    # pedido, mesmo conteúdo — e o catálogo tem de reconhecer o reencontro.
    a, b = MotorFalso(), MotorFalso()
    resposta_a = a.receber(a.solicitar_geracao(_pedido()))
    resposta_b = b.receber(b.solicitar_geracao(_pedido()))
    assert resposta_a.arquivos[0].conteudo == resposta_b.arquivos[0].conteudo


def test_a_pendencia_e_respeitada_antes_da_entrega():
    motor = MotorFalso(pendencias=2)
    id_pedido = motor.solicitar_geracao(_pedido())
    for _ in range(2):
        with pytest.raises(GeracaoPendente) as e:
            motor.receber(id_pedido)
        assert e.value.permanente is False
    assert motor.receber(id_pedido).arquivos


def test_id_que_o_motor_nunca_emitiu_levanta_tipado_e_permanente():
    with pytest.raises(PedidoDesconhecido) as e:
        MotorFalso().receber("falso-999")
    assert e.value.permanente is True


def test_motor_fora_do_ar_e_erro_transitorio():
    with pytest.raises(MotorIndisponivel) as e:
        MotorFalso(indisponivel=True).solicitar_geracao(_pedido())
    assert e.value.permanente is False
    # A exceção sabe virar dado, para que o lote sobreviva a ela.
    assert e.value.como_falha(TipoDeAsset.IMAGEM_MARKETING).codigo == "MOTOR.indisponivel"


def test_um_item_recusado_vira_falha_e_os_outros_seguem():
    motor = MotorFalso(defeitos={1: Defeito.RECUSADO})
    resposta = motor.receber(motor.solicitar_geracao(_pedido(quantidade=3)))
    assert len(resposta.arquivos) == 2
    assert len(resposta.falhas) == 1
    assert resposta.falhas[0].permanente is True


@pytest.mark.parametrize(
    "defeito, codigo_esperado",
    [
        (Defeito.PEQUENO_DEMAIS, "D1.dimensao_minima"),
        (Defeito.PROPORCAO_ERRADA, "D3.proporcao"),
        (Defeito.PESADO_DEMAIS, "P1.peso"),
        (Defeito.SEM_MEDIDA, "M1.sem_medida"),
        (Defeito.MIME_ERRADO, "F1.mime"),
    ],
)
def test_o_falso_produz_cada_defeito_que_a_validacao_precisa_ver(defeito, codigo_esperado):
    # Um mock que só sabe acertar prova metade do sistema — e a metade barata.
    # Contra Performance Max, que é o canal cuja tabela oficial declara peso:
    # o Display não tem teto de bytes e o defeito de peso passaria despercebido.
    motor = MotorFalso(defeitos={0: defeito})
    pedido = _pedido(exigencia=PMAX)
    assets, _ = assets_da_resposta(
        motor.receber(motor.solicitar_geracao(pedido)), pedido,
        motor=motor.nome, versao=motor.versao, quando=QUANDO,
    )
    achados = validacao.validar_asset(assets[0], PMAX.de(TipoDeAsset.IMAGEM_MARKETING))
    assert codigo_esperado in {v.codigo for v in achados}


def test_sem_defeito_o_falso_produz_asset_que_passa():
    motor = MotorFalso()
    pedido = _pedido()
    assets, falhas = assets_da_resposta(
        motor.receber(motor.solicitar_geracao(pedido)), pedido,
        motor=motor.nome, versao=motor.versao, quando=QUANDO,
    )
    assert not falhas
    assert validacao.validar_asset(assets[0], DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING)) == ()


def test_texto_longo_sob_encomenda_estoura_o_limite_do_slot():
    motor = MotorFalso(defeitos={0: Defeito.TEXTO_LONGO})
    pedido = _pedido(tipo=TipoDeAsset.HEADLINE, insumo="títulos do FGTS")
    assets, _ = assets_da_resposta(
        motor.receber(motor.solicitar_geracao(pedido)), pedido,
        motor=motor.nome, versao=motor.versao, quando=QUANDO,
    )
    achados = validacao.validar_asset(assets[0], DISPLAY.de(TipoDeAsset.HEADLINE))
    assert [v.codigo for v in achados] == ["X1.caracteres"]


# ── a ponte para o FunnelForge ──────────────────────────────────────────────


class _GeradorDublê:
    """Mesma assinatura do port `ImageGenerator` do FunnelForge, sem rede.

    `model`, `quality` e `last_usage` existem porque o `OpenAIImageGenerator`
    real os expõe, e é deles que a ponte tira nome, versão e custo.
    """

    model = "gpt-image-2"
    quality = "medium"

    def __init__(self, *, erro: Exception | None = None, custo: float | None = 0.04,
                 dados: bytes = b"PNG-falso") -> None:
        self._erro = erro
        self._dados = dados
        self.tamanhos_pedidos: list[str] = []
        self.last_usage = type("Uso", (), {"cost_usd": custo})() if custo is not None else None

    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        self.tamanhos_pedidos.append(size)
        if self._erro is not None:
            raise self._erro
        return self._dados


class _ErroHttp(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.response = type("Resposta", (), {"status_code": status})()


def test_a_ponte_recusa_objeto_que_nao_cumpre_o_port():
    with pytest.raises(TypeError, match="ImageGenerator"):
        ponte.MotorDeImagemFunnelForge(object())


def test_a_ponte_se_identifica_pelo_modelo_do_gerador():
    motor = ponte.MotorDeImagemFunnelForge(_GeradorDublê())
    # Sem nome não há procedência, e sem procedência o asset não entra no catálogo.
    assert motor.nome == "funnelforge:gpt-image-2"
    assert motor.versao == "medium"


def test_a_ponte_escolhe_o_tamanho_mais_proximo_da_proporcao_exigida():
    # O quadrado bate exato; 1.91:1 não existe no motor e cai no mais próximo,
    # que é o que exige o MENOR recorte depois.
    assert ponte.tamanho_para(DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING_QUADRADA)) == "1024x1024"
    assert ponte.tamanho_para(DISPLAY.de(TipoDeAsset.IMAGEM_MARKETING)) == "1536x1024"
    assert ponte.tamanho_para(None) == "1024x1024"


def test_a_ponte_repassa_o_tamanho_escolhido_ao_gerador():
    dublê = _GeradorDublê()
    motor = ponte.MotorDeImagemFunnelForge(dublê)
    motor.solicitar_geracao(_pedido(quantidade=2))
    assert dublê.tamanhos_pedidos == ["1536x1024", "1536x1024"]


def test_a_ponte_le_o_custo_de_last_usage_e_diz_None_quando_nao_ha():
    motor = ponte.MotorDeImagemFunnelForge(_GeradorDublê(custo=0.04))
    assert motor.receber(motor.solicitar_geracao(_pedido())).custo_usd == pytest.approx(0.04)

    # Fingir que a imagem foi de graça é mentira no ledger — por isso None, não 0.0.
    mudo = ponte.MotorDeImagemFunnelForge(_GeradorDublê(custo=None))
    assert mudo.receber(mudo.solicitar_geracao(_pedido())).custo_usd is None


def test_a_ponte_separa_erro_de_politica_de_erro_de_transporte():
    permanente = ponte.MotorDeImagemFunnelForge(_GeradorDublê(erro=_ErroHttp(400)))
    falha = permanente.receber(permanente.solicitar_geracao(_pedido())).falhas[0]
    assert falha.permanente is True and falha.codigo == "MOTOR.http_400"

    # 429 é transporte: retentar o mesmo insumo pode dar certo.
    transitorio = ponte.MotorDeImagemFunnelForge(_GeradorDublê(erro=_ErroHttp(429)))
    assert transitorio.receber(transitorio.solicitar_geracao(_pedido())).falhas[0].permanente is False


def test_erro_sem_status_http_e_tratado_como_transitorio():
    motor = ponte.MotorDeImagemFunnelForge(_GeradorDublê(erro=TimeoutError("estourou")))
    falha = motor.receber(motor.solicitar_geracao(_pedido())).falhas[0]
    assert falha.codigo == "MOTOR.indisponivel" and falha.permanente is False


def test_a_ponte_recusa_pedir_video_a_um_motor_de_imagem():
    motor = ponte.MotorDeImagemFunnelForge(_GeradorDublê())
    with pytest.raises(PedidoRecusado):
        motor.solicitar_geracao(PedidoDeGeracao(
            referencia="FGTS", tipo=TipoDeAsset.VIDEO, insumo="hook"
        ))


def test_bytes_ilegiveis_viram_ausencia_de_medida_e_nao_zero():
    motor = ponte.MotorDeImagemFunnelForge(_GeradorDublê(dados=b"nao sou imagem"))
    arquivo = motor.receber(motor.solicitar_geracao(_pedido())).arquivos[0]
    assert arquivo.largura is None and arquivo.altura is None and arquivo.mime is None


def test_a_ponte_mede_a_imagem_de_verdade_quando_da():
    # O motor real devolve bytes e mais nada; sem medir aqui, todo asset
    # chegaria ao catálogo sem dimensão e seria reprovado por MEDIR_ANTES.
    Image = pytest.importorskip("PIL.Image")
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (1200, 628), (10, 20, 30)).save(buffer, format="PNG")

    motor = ponte.MotorDeImagemFunnelForge(_GeradorDublê(dados=buffer.getvalue()))
    arquivo = motor.receber(motor.solicitar_geracao(_pedido())).arquivos[0]
    assert (arquivo.largura, arquivo.altura, arquivo.mime) == (1200, 628, "image/png")


# ── o ciclo inteiro ─────────────────────────────────────────────────────────


def test_do_pedido_ao_veredito_sem_perder_falha_nem_duplicar_asset():
    motor = MotorFalso(defeitos={2: Defeito.RECUSADO, 3: Defeito.PEQUENO_DEMAIS})
    catalogo = Catalogo()

    for tipo, quantidade in (
        (TipoDeAsset.IMAGEM_MARKETING, 4),
        (TipoDeAsset.IMAGEM_MARKETING_QUADRADA, 1),
        (TipoDeAsset.HEADLINE, 1),
        (TipoDeAsset.HEADLINE_LONGA, 1),
        (TipoDeAsset.DESCRICAO, 1),
        (TipoDeAsset.NOME_DA_EMPRESA, 1),
    ):
        pedido = _pedido(tipo=tipo, quantidade=quantidade, insumo=f"insumo de {tipo.value}")
        assets, falhas = assets_da_resposta(
            motor.receber(motor.solicitar_geracao(pedido)), pedido,
            motor=motor.nome, versao=motor.versao, quando=QUANDO,
        )
        catalogo.absorver(assets, falhas, intencao="FGTS 2026")

    lote = catalogo.lote("FGTS 2026", "DISPLAY")
    resultado = validacao.validar_lote(lote, DISPLAY)

    # A recusa virou dado, não exceção.
    assert len(lote.falhas) == 1
    # 3 paisagens entregues (uma recusada) + 5 dos outros slots.
    assert len(lote.assets) == 8
    # A pequena demais foi separada, e as outras duas paisagens seguiram — o
    # lote continua publicável porque o que sobrou cumpre o canal.
    assert len(resultado.reprovados) == 1
    assert len(resultado.aprovados) == 7
    assert resultado.ok, resultado.resumo()
    assert resultado.erros and not resultado.erros_do_lote

    # Reencomendar o mesmo insumo não cria asset novo: o motor é determinístico
    # e o catálogo reconhece o reencontro pelo conteúdo.
    antes = len(catalogo)
    pedido = _pedido(tipo=TipoDeAsset.IMAGEM_MARKETING, quantidade=4,
                     insumo="insumo de imagem_marketing")
    assets, _ = assets_da_resposta(
        motor.receber(motor.solicitar_geracao(pedido)), pedido,
        motor=motor.nome, versao=motor.versao, quando=QUANDO,
    )
    registros = catalogo.absorver(assets, intencao="FGTS 2026")
    assert len(catalogo) == antes
    assert not any(r.novo for r in registros)
