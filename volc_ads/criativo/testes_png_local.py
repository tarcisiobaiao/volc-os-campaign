"""Testes do motor local de PNG — o arquivo é real, e é isso que se prova aqui.

Rodar da raiz do projeto:
    backend/.venv/bin/python -m pytest volc_ads/criativo -q

A pergunta que estes testes respondem não é "o motor devolveu bytes?" — o motor
falso já devolvia. É "os bytes que ele devolveu são um PNG que o MEDIDOR
AUTORITATIVO da casa consegue ler?". A diferença entre as duas é a diferença
entre um asset que sobe e um asset que a API recusa depois de a geração já ter
sido paga.

E há uma segunda pergunta, que custa mais: "este arquivo pode ser apresentado
como produção?". A resposta é não, e ela precisa estar no DADO — não numa
convenção de quem opera.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads.criativo import requisitos  # noqa: E402
from volc_ads.criativo.adaptadores import medir_imagem, png_local  # noqa: E402
from volc_ads.criativo.adaptadores.falso import MotorFalso  # noqa: E402
from volc_ads.criativo.contrato import (  # noqa: E402
    NaturezaDaProcedencia,
    TipoDeAsset,
)
from volc_ads.criativo.porta import (  # noqa: E402
    MotorDeCriativo,
    MotorIndisponivel,
    PedidoDeGeracao,
    PedidoDesconhecido,
    PedidoRecusado,
)

INSUMO = "banner do FGTS de setembro"


def _pedido(tipo=TipoDeAsset.IMAGEM_MARKETING, *, canal="DISPLAY", **extra):
    spec = requisitos.exigencia_binaria_de(canal).de(tipo)
    campos = {
        "referencia": f"prova/{tipo.value}",
        "tipo": tipo,
        "insumo": INSUMO,
        "especificacao": spec,
    }
    campos.update(extra)
    return PedidoDeGeracao(**campos)


def _gerar(motor, pedido):
    return motor.receber(motor.solicitar_geracao(pedido))


# ── a porta ─────────────────────────────────────────────────────────────────


def test_o_motor_local_cumpre_a_porta_de_criativo():
    assert isinstance(png_local.MotorLocalDePNG(), MotorDeCriativo)


def test_o_motor_declara_natureza_local_e_ela_nao_e_publicavel():
    motor = png_local.MotorLocalDePNG()
    assert motor.natureza is NaturezaDaProcedencia.LOCAL
    assert motor.natureza.publicavel is False


# ── o arquivo é real ────────────────────────────────────────────────────────


def test_os_bytes_sao_um_png_que_o_medidor_autoritativo_le():
    resposta = _gerar(png_local.MotorLocalDePNG(), _pedido())
    arquivo = resposta.arquivos[0]

    medida = medir_imagem.medir(arquivo.conteudo)
    assert medida.mime == "image/png"
    assert medida.largura is not None and medida.altura is not None
    # O que o motor DECLAROU tem de ser o que o medidor LEU. Declarar sem medir
    # é a mentira que o `ArquivoGerado` permite e que este motor não comete.
    assert (arquivo.mime, arquivo.largura, arquivo.altura) == (
        medida.mime, medida.largura, medida.altura
    )


def test_o_motor_falso_nao_serve_para_este_caminho_e_e_por_isso_que_este_existe():
    """A regressão que motivou o motor local, presa num teste.

    `MotorFalso` declara `mime="image/png"` sobre 128 bytes de digest. Enquanto
    ninguém mede, ele é um ótimo motor de teste; no instante em que o caminho vai
    até a ponte — onde os bytes SÃO conferidos — ele passa a ser um asset que
    parece produção e não é. Se um dia o falso passar a produzir PNG de verdade,
    este teste falha e a decisão volta à mesa em vez de virar redundância muda.
    """
    resposta = _gerar(MotorFalso(), _pedido())
    arquivo = resposta.arquivos[0]

    assert arquivo.mime == "image/png"          # o que ele DIZ
    medida = medir_imagem.medir(arquivo.conteudo)
    assert medida.mime is None                  # o que os bytes SÃO
    assert medida.largura is None and medida.altura is None


# ── determinismo ────────────────────────────────────────────────────────────


def test_dois_motores_diferentes_produzem_o_mesmo_arquivo_para_o_mesmo_pedido():
    pedido = _pedido()
    a = _gerar(png_local.MotorLocalDePNG(), pedido).arquivos[0].conteudo
    b = _gerar(png_local.MotorLocalDePNG(), pedido).arquivos[0].conteudo
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_o_id_do_pedido_sai_do_conteudo_e_nao_de_um_contador():
    """Dois pedidos iguais convergem; um pedido diferente não.

    Um contador faria o replay de um lote criar uma segunda procedência para o
    mesmo arquivo — e a pergunta "de que pedido veio este banner?" passaria a ter
    duas respostas verdadeiras, que é o mesmo que não ter nenhuma.
    """
    motor = png_local.MotorLocalDePNG()
    igual = motor.solicitar_geracao(_pedido())
    de_novo = motor.solicitar_geracao(_pedido())
    outro = motor.solicitar_geracao(_pedido(insumo="outro briefing"))

    assert igual == de_novo
    assert outro != igual


def test_insumos_diferentes_produzem_arquivos_diferentes():
    a = _gerar(png_local.MotorLocalDePNG(), _pedido()).arquivos[0].conteudo
    b = _gerar(
        png_local.MotorLocalDePNG(), _pedido(insumo="outro briefing")
    ).arquivos[0].conteudo
    assert a != b


# ── a geometria sai da régua ────────────────────────────────────────────────


@pytest.mark.parametrize("canal", ["DISPLAY", "DEMAND_GEN"])
def test_cada_papel_sai_com_a_geometria_que_a_regua_daquele_canal_pede(canal):
    exigencia = requisitos.exigencia_binaria_de(canal)
    motor = png_local.MotorLocalDePNG()

    for spec in exigencia.especificacoes:
        if spec.tipo is TipoDeAsset.VIDEO:
            continue  # este motor não produz vídeo, e recusa dizendo isso
        arquivo = _gerar(motor, _pedido(spec.tipo, canal=canal)).arquivos[0]

        if spec.largura_minima:
            assert arquivo.largura >= spec.largura_minima, spec.tipo
        if spec.altura_minima:
            assert arquivo.altura >= spec.altura_minima, spec.tipo
        if spec.proporcao_alvo:
            esperada = spec.proporcao_alvo[0] / spec.proporcao_alvo[1]
            atual = arquivo.largura / arquivo.altura
            assert abs(atual - esperada) / esperada <= spec.tolerancia_proporcao, spec.tipo
        if spec.bytes_maximos:
            # O logo do Demand Gen tem teto de 150 KB. Um desenho ruidoso
            # estouraria e o motor reprovaria a si mesmo — por isso ele é chapado.
            assert len(arquivo.conteudo) <= spec.bytes_maximos, spec.tipo
        if spec.mimes_aceitos:
            assert arquivo.mime in spec.mimes_aceitos, spec.tipo


# ── falha tem causa, e a causa é tipada ─────────────────────────────────────


def test_video_e_recusado_com_erro_permanente_e_nao_com_arquivo_vazio():
    motor = png_local.MotorLocalDePNG()
    with pytest.raises(PedidoRecusado) as capturado:
        motor.solicitar_geracao(
            PedidoDeGeracao(referencia="r", tipo=TipoDeAsset.VIDEO, insumo=INSUMO)
        )
    # Permanente é o campo que importa: retentar o mesmo vídeo num motor de
    # imagem erra igual todas as vezes.
    assert capturado.value.permanente is True
    assert capturado.value.codigo == "MOTOR.recusado"


def test_motor_fora_do_ar_levanta_erro_transitorio_e_nao_devolve_lote_vazio():
    motor = png_local.MotorLocalDePNG(indisponivel=True)
    with pytest.raises(MotorIndisponivel) as capturado:
        motor.solicitar_geracao(_pedido())
    assert capturado.value.permanente is False


def test_receber_um_id_que_este_motor_nunca_emitiu_e_erro_e_nao_resposta_vazia():
    with pytest.raises(PedidoDesconhecido):
        png_local.MotorLocalDePNG().receber("png-local-inventado")


def test_dimensao_absurda_vira_falha_no_lote_e_nao_estouro_de_memoria():
    """O teto existe para que um erro de digitação recuse em vez de matar o processo."""
    with pytest.raises(ValueError):
        png_local.desenhar(png_local._LADO_MAXIMO + 1, 10, b"\x00" * 32)


# ── custo ───────────────────────────────────────────────────────────────────


def test_custo_ausente_e_None_e_nunca_zero():
    """`0.0` é uma afirmação de custo apurado. O motor local não custa dinheiro,
    e ainda assim não pode afirmar que a imagem saiu de graça: um COGS que soma
    esses zeros fecha bonito e está errado."""
    resposta = _gerar(png_local.MotorLocalDePNG(), _pedido())
    assert resposta.custo_usd is None
    assert resposta.arquivos[0].custo_usd is None


# ── procedência do próprio motor ────────────────────────────────────────────


def test_as_versoes_declaram_o_zlib_porque_ele_muda_os_bytes():
    versoes = png_local.MotorLocalDePNG().versoes()
    assert versoes["adaptador"] == png_local.VERSAO_DO_ADAPTADOR
    assert versoes["algoritmo"] == png_local.VERSAO_DO_ALGORITMO
    # Sem esta linha, duas máquinas com zlib diferente produziriam hashes
    # diferentes para o mesmo pedido e a divergência viraria mistério.
    assert versoes["zlib"]
