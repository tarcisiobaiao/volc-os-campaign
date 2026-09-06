"""O portão de política e identidade de terceiro sobre a peça de mídia paga.

A peça que motivou esta lane trazia um envelope com marca de banco. Ninguém
mentiu: o gerador produziu o que foi pedido, o operador não reparou, e a peça
foi ao ar afirmando um vínculo que não existia.

O que se prova aqui é que o sistema NÃO DEPENDE de alguém reparar.
"""
from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("CRIATIVO_URL_SECRET", "x" * 40)

from app.criativo import politica as P  # noqa: E402
from app.criativo.politica import inspecao as insp  # noqa: E402
from app.criativo.politica import lexico  # noqa: E402
from app.criativo.politica import recibo as rec  # noqa: E402


ASSET = "csa_" + "a" * 24
BYTES_SHA = "b" * 64
IDENTIDADE = "cofre:identidade:portal-mundo-mais"
PROPRIA = ("Portal Mundo Mais",)


@pytest.fixture(autouse=True)
def _sem_detector_de_pixel():
    """Cada teste começa com o registro de detectores vazio e o devolve limpo."""
    insp.limpar_detectores_de_pixel()
    yield
    insp.limpar_detectores_de_pixel()


class _OcrFalso:
    """Um detector de pixel determinístico, para provar o caminho COM motor."""

    nome = "ocr_hermetico"
    versao = "teste-1"

    def __init__(self, texto: str = "", rotulos: tuple = ()) -> None:
        self._texto = texto
        self._rotulos = rotulos

    def inspecionar(self, bytes_da_peca: bytes, *, mime: str):
        return insp.LeituraDePixel(texto=self._texto, rotulos=self._rotulos)


def _avaliar(**troca):
    base = dict(
        asset_ref=ASSET, content_sha256=BYTES_SHA, bytes_da_peca=b"pixels",
        mime="image/png", copy={"headline": "Guia informativo independente"},
        nome_do_arquivo="peca.png", prompt=None, identity_ref=IDENTIDADE,
        identidade_propria=PROPRIA, procedencia="GENERATED",
    )
    base.update(troca)
    return P.avaliar(**base)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A marca de terceiro bloqueia, e bloqueia sem pedir opinião a ninguém
# ═══════════════════════════════════════════════════════════════════════════


def test_marca_de_banco_na_peca_bloqueia_a_midia_paga():
    """CONTRAPROVA T12: o incidente, reproduzido — e agora barrado.

    O envelope com marca de banco chega pelo OCR da imagem FINAL, não pelo
    prompt. O prompt era limpo; a peça, não.
    """
    insp.registrar_detector_de_pixel(
        _OcrFalso(texto="CAIXA ECONOMICA FEDERAL - correspondencia"))

    recibo_da_peca = _avaliar()

    assert recibo_da_peca.decisao == P.THIRD_PARTY_IDENTITY_UNVERIFIED
    assert recibo_da_peca.libera_midia_paga() is False
    classes = {a.classe for a in recibo_da_peca.achados}
    assert "BANCOS" in classes
    # A origem é o pixel, e o recibo diz isso: o operador precisa saber que a
    # marca está NA IMAGEM, não no texto que ele escreveu.
    assert {a.origem for a in recibo_da_peca.achados} == {"ocr"}


def test_o_portao_recusa_a_compilacao_antes_de_qualquer_rede():
    """CONTRAPROVA T12: a recusa é do lado de quem COMPILA, com próximo ato."""
    insp.registrar_detector_de_pixel(_OcrFalso(texto="Banco do Brasil"))
    copy = {"headline": "Guia informativo independente"}
    bloqueado = _avaliar(copy=copy)

    with pytest.raises(P.PoliticaCriativaRecusou) as erro:
        P.exigir_liberacao(
            bloqueado, asset_ref=ASSET, content_sha256=BYTES_SHA, copy=copy)

    assert erro.value.codigo == f"POLICY_{P.THIRD_PARTY_IDENTITY_UNVERIFIED}"
    mensagem = str(erro.value)
    # O próximo ato, não só a recusa.
    assert "Cofre" in mensagem
    assert "confirmar no formulário não limpa" in mensagem.lower()
    # E QUAL marca, para o operador não ter que caçar.
    assert "BANCOS:banco do brasil" in mensagem


def test_aprovacao_humana_nao_limpa_o_estado():
    """SUP-INV-02: só um recibo NOVO limpa. Não existe botão de confirmar.

    A prova é estrutural: não há caminho na API pública do portão que receba
    uma confirmação humana e mude a decisão de um recibo.
    """
    insp.registrar_detector_de_pixel(_OcrFalso(texto="INSS"))
    bloqueado = _avaliar()
    assert bloqueado.decisao == P.THIRD_PARTY_IDENTITY_UNVERIFIED

    # Editar o campo à mão quebra a assinatura — que é exatamente o ponto.
    forjado = dataclasses.replace(bloqueado, decisao=P.CLEAR)
    with pytest.raises(P.PoliticaCriativaRecusou) as erro:
        P.exigir_liberacao(
            forjado, asset_ref=ASSET, content_sha256=BYTES_SHA,
            copy={"headline": "Guia informativo independente"})
    assert erro.value.codigo == "POLICY_RECEIPT_SIGNATURE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════
# 2. O recibo forjado é recusado
# ═══════════════════════════════════════════════════════════════════════════


def test_recibo_com_assinatura_forjada_e_recusado():
    """CONTRAPROVA T12: o navegador não pode cunhar a própria autorização."""
    limpo = _avaliar(exigir_pixel=False)
    assert limpo.decisao == P.CLEAR

    forjado = dataclasses.replace(limpo, assinatura_hmac="0" * 64)
    with pytest.raises(P.PoliticaCriativaRecusou) as erro:
        P.exigir_liberacao(
            forjado, asset_ref=ASSET, content_sha256=BYTES_SHA,
            copy={"headline": "Guia informativo independente"})
    assert erro.value.codigo == "POLICY_RECEIPT_SIGNATURE_INVALID"


def test_trocar_os_bytes_invalida_o_recibo():
    """Uma peça nova precisa de um recibo novo: a autorização é DAQUELES bytes."""
    limpo = _avaliar(exigir_pixel=False)
    with pytest.raises(P.PoliticaCriativaRecusou) as erro:
        P.exigir_liberacao(
            limpo, asset_ref=ASSET, content_sha256="c" * 64,
            copy={"headline": "Guia informativo independente"})
    assert erro.value.codigo == "POLICY_RECEIPT_CONTENT_DIVERGED"


def test_trocar_a_copy_invalida_o_recibo():
    """A mesma imagem com outro texto pode afirmar outra coisa."""
    limpo = _avaliar(exigir_pixel=False)
    with pytest.raises(P.PoliticaCriativaRecusou) as erro:
        P.exigir_liberacao(
            limpo, asset_ref=ASSET, content_sha256=BYTES_SHA,
            copy={"headline": "Outro texto completamente diferente"})
    assert erro.value.codigo == "POLICY_RECEIPT_COPY_DIVERGED"


def test_recibo_expirado_e_recusado():
    ontem = datetime.now(timezone.utc) - timedelta(days=2)
    velho = _avaliar(exigir_pixel=False, agora=ontem)
    with pytest.raises(P.PoliticaCriativaRecusou) as erro:
        P.exigir_liberacao(
            velho, asset_ref=ASSET, content_sha256=BYTES_SHA,
            copy={"headline": "Guia informativo independente"})
    assert erro.value.codigo == "POLICY_RECEIPT_EXPIRED"


# ═══════════════════════════════════════════════════════════════════════════
# 3. A identidade própria nunca é terceiro
# ═══════════════════════════════════════════════════════════════════════════


def test_o_proprio_nome_do_anunciante_nunca_e_terceiro():
    """CONTRAPROVA T12: um portão que acusa o anunciante de si mesmo é desligado."""
    insp.registrar_detector_de_pixel(_OcrFalso(texto="Portal Mundo Mais Oficial"))
    recibo_da_peca = _avaliar(
        identidade_propria=("Portal Mundo Mais Oficial", "Portal Mundo Mais"),
        copy={"headline": "Portal Mundo Mais — guia independente"},
    )
    assert recibo_da_peca.decisao == P.CLEAR
    assert recibo_da_peca.achados == ()


def test_sigla_so_casa_em_maiuscula():
    """`inss` dentro de uma palavra qualquer não é uma afirmação de vínculo."""
    assert lexico.procurar("um episodio de inss qualquer", origem="copy") == ()
    assert len(lexico.procurar("consulte o INSS hoje", origem="copy")) == 1


def test_termo_nunca_casa_dentro_de_outra_palavra():
    """Sem fronteira de palavra, 'tim' casaria em 'estimativa'."""
    assert lexico.procurar("uma estimativa conservadora", origem="copy") == ()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Autorização do Cofre — e só ela — libera um achado
# ═══════════════════════════════════════════════════════════════════════════


def test_autorizacao_do_cofre_cobre_o_termo_que_lista():
    insp.registrar_detector_de_pixel(_OcrFalso(texto="Banco do Brasil"))
    autorizacao = P.AutorizacaoDeTerceiro(
        autorizacao_ref="cofre:autorizacao:bb-2026",
        classes=("BANCOS",), termos=("banco do brasil",),
        expira_em=datetime.now(timezone.utc) + timedelta(days=30),
    )
    recibo_da_peca = _avaliar(autorizacoes=[autorizacao])

    assert recibo_da_peca.decisao == P.THIRD_PARTY_IDENTITY_AUTHORIZED
    assert recibo_da_peca.libera_midia_paga() is True
    assert all(a.coberto_por_autorizacao for a in recibo_da_peca.achados)
    assert recibo_da_peca.autorizacoes_consultadas == ("cofre:autorizacao:bb-2026",)


def test_autorizacao_nao_cobre_marca_que_nao_lista():
    """A autorização cobre SOMENTE os termos que ela lista. Um achado descoberto
    mantém o estado inteiro em UNVERIFIED — não existe liberação parcial."""
    insp.registrar_detector_de_pixel(
        _OcrFalso(texto="Banco do Brasil e Caixa Economica Federal"))
    autorizacao = P.AutorizacaoDeTerceiro(
        autorizacao_ref="cofre:autorizacao:bb-2026",
        classes=("BANCOS",), termos=("banco do brasil",),
        expira_em=datetime.now(timezone.utc) + timedelta(days=30),
    )
    recibo_da_peca = _avaliar(autorizacoes=[autorizacao])
    assert recibo_da_peca.decisao == P.THIRD_PARTY_IDENTITY_UNVERIFIED


def test_autorizacao_expirada_nao_cobre_nada():
    insp.registrar_detector_de_pixel(_OcrFalso(texto="Banco do Brasil"))
    vencida = P.AutorizacaoDeTerceiro(
        autorizacao_ref="cofre:autorizacao:bb-2025",
        classes=("BANCOS",), termos=("banco do brasil",),
        expira_em=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert _avaliar(autorizacoes=[vencida]).decisao == (
        P.THIRD_PARTY_IDENTITY_UNVERIFIED)


# ═══════════════════════════════════════════════════════════════════════════
# 5. ⚠️ Não conseguir olhar NÃO é a peça estar limpa
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_detector_de_pixel_o_portao_fica_indisponivel_e_bloqueia():
    """A regra mais importante do módulo, e a que produziu o incidente.

    Sem OCR, uma peça com o envelope do banco passa por todos os detectores de
    texto — a copy é limpa, o nome do arquivo é limpo — e sairia CLEAR. Declarar
    o detector ausente como ERROR é o que impede "não consegui olhar" de virar
    "olhei e não tem nada".
    """
    recibo_da_peca = _avaliar()  # nenhum detector registrado
    assert recibo_da_peca.decisao == P.GATE_UNAVAILABLE
    assert recibo_da_peca.libera_midia_paga() is False
    assert "PIXEL_DETECTOR_NOT_REGISTERED" in recibo_da_peca.motivos
    ausente = [d for d in recibo_da_peca.detectores if d.nome == "inspecao_de_pixel"]
    assert ausente and ausente[0].resultado == "ERROR"


def test_detector_que_explode_tambem_deixa_o_portao_indisponivel():
    class _Explode:
        nome, versao = "ocr_quebrado", "teste-1"

        def inspecionar(self, *_a, **_k):
            raise RuntimeError("motor fora do ar")

    insp.registrar_detector_de_pixel(_Explode())
    recibo_da_peca = _avaliar()
    assert recibo_da_peca.decisao == P.GATE_UNAVAILABLE
    assert "PIXEL_DETECTOR_FAILED" in recibo_da_peca.motivos


# ═══════════════════════════════════════════════════════════════════════════
# 6. Direitos e procedência
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("procedencia", "motivo"),
    [
        ("HUMAN_UPLOAD", "RIGHTS_UNKNOWN"),
        ("OBSERVED_EXTERNAL", "NOT_INSPECTABLE"),
        ("STOCK", "STOCK_LICENSE_MISSING"),
    ],
)
def test_procedencia_sem_licenca_bloqueia(procedencia, motivo):
    insp.registrar_detector_de_pixel(_OcrFalso())
    recibo_da_peca = _avaliar(procedencia=procedencia)
    assert recibo_da_peca.decisao == P.BLOCKED_BY_POLICY
    assert motivo in recibo_da_peca.motivos


def test_licenca_declarada_desbloqueia_a_procedencia():
    insp.registrar_detector_de_pixel(_OcrFalso())
    recibo_da_peca = _avaliar(procedencia="STOCK", licenca_ref="cofre:licenca:1")
    assert recibo_da_peca.decisao == P.CLEAR


def test_peca_que_nao_e_de_producao_nunca_vai_a_midia_paga():
    insp.registrar_detector_de_pixel(_OcrFalso())
    recibo_da_peca = _avaliar(natureza="rascunho")
    assert recibo_da_peca.decisao == P.BLOCKED_BY_POLICY
    assert "NATURE_NOT_PRODUCTION" in recibo_da_peca.motivos


# ═══════════════════════════════════════════════════════════════════════════
# 7. O recibo não vaza o que não deve
# ═══════════════════════════════════════════════════════════════════════════


def test_a_projecao_publica_nao_carrega_prompt_nem_texto_integral_do_ocr():
    """Só os termos que casaram. O texto inteiro é conteúdo, não evidência."""
    segredo_no_ocr = "CAIXA ECONOMICA FEDERAL e um segredo qualquer aqui"
    insp.registrar_detector_de_pixel(_OcrFalso(texto=segredo_no_ocr))
    recibo_da_peca = _avaliar(prompt="um prompt que nao pode vazar")

    import json

    texto = json.dumps(recibo_da_peca.publico(), ensure_ascii=False)
    assert "um prompt que nao pode vazar" not in texto
    assert "um segredo qualquer aqui" not in texto
    # O termo que casou ENTRA — é ele que o operador precisa ver.
    assert "caixa economica federal" in texto


def test_decisao_fora_do_vocabulario_e_recusada_na_construcao():
    with pytest.raises(rec.ReciboInvalido):
        rec.ReciboDePolitica(
            policy_receipt_ref="cpr_" + "a" * 24, asset_ref=ASSET,
            content_sha256_inspecionado=BYTES_SHA, copy_sha256=None,
            identity_ref=IDENTIDADE, lexico_versao="v1",
            decisao="LIBERADO_PORQUE_SIM",
            avaliado_em=datetime.now(timezone.utc),
            expira_em=datetime.now(timezone.utc) + timedelta(hours=1),
            assinatura_hmac="a" * 64,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. A trava do portão incompleto — e o que ela NUNCA afrouxa
# ═══════════════════════════════════════════════════════════════════════════


def test_a_trava_aberta_aceita_a_lacuna_mas_nao_a_esconde(monkeypatch):
    """Com `CRIATIVO_POLICY_GATE_STRICT=0` a decisão sai dos detectores que
    rodaram — e o recibo continua dizendo que a imagem NÃO foi inspecionada."""
    monkeypatch.setenv(P.FLAG_ESTRITO, "0")
    recibo_da_peca = _avaliar()  # sem detector de pixel

    assert recibo_da_peca.decisao == P.CLEAR
    # ⚠️ A lacuna continua no recibo. Ninguém pode ler este CLEAR como "a
    # imagem foi olhada".
    assert "PIXEL_DETECTOR_NOT_REGISTERED" in recibo_da_peca.motivos
    ausente = [d for d in recibo_da_peca.detectores if d.nome == "inspecao_de_pixel"]
    assert ausente and ausente[0].resultado == "ERROR"


def test_a_trava_aberta_nao_afrouxa_um_achado(monkeypatch):
    """A trava governa a AUSÊNCIA de detector, nunca a presença de marca."""
    monkeypatch.setenv(P.FLAG_ESTRITO, "0")
    recibo_da_peca = _avaliar(copy={"headline": "Saque liberado pelo governo"})
    assert recibo_da_peca.decisao == P.THIRD_PARTY_IDENTITY_UNVERIFIED


def test_o_padrao_da_trava_e_fechado(monkeypatch):
    monkeypatch.delenv(P.FLAG_ESTRITO, raising=False)
    assert P.modo_estrito() is True


# ═══════════════════════════════════════════════════════════════════════════
# 9. O adaptador do motor que falta — escrito, e honestamente não registrado
# ═══════════════════════════════════════════════════════════════════════════


def test_o_registro_de_boot_nao_registra_nada_sem_motor():
    """CONTRAPROVA A: sem OCR instalado, ninguém é registrado.

    ⚠️ E o portão continua bloqueando. A tentação seria registrar um detector
    que sempre devolve "não vi nada" — isso transformaria "não consegui olhar"
    em "olhei e está limpo", que é a confusão que deixou a peça com marca de
    banco ir ao ar. Detector mudo some com o ERROR do recibo.
    """
    from app.criativo.politica.detectores import (
        DetectorOcrTesseract,
        registrar_detectores_disponiveis,
    )

    assert DetectorOcrTesseract.se_disponivel() is None
    assert registrar_detectores_disponiveis() == ()
    assert insp.detectores_de_pixel_registrados() == ()
    # E a consequência, medida e não suposta:
    assert _avaliar().decisao == P.GATE_UNAVAILABLE


def test_o_adaptador_respeita_o_protocol_do_portao():
    """O adaptador existe pronto: assinatura conferida contra o seam."""
    import inspect

    from app.criativo.politica.detectores import DetectorOcrTesseract

    d = DetectorOcrTesseract(versao="5.0.0-fixture")
    assert d.nome == "ocr.tesseract"
    assert d.versao == "5.0.0-fixture"
    assinatura = inspect.signature(DetectorOcrTesseract.inspecionar)
    assert list(assinatura.parameters) == ["self", "bytes_da_peca", "mime"]
    # ⚠️ SÍNCRONO: é o Protocol que o portão declara, e o portão roda dentro de
    # uma requisição async.
    assert not inspect.iscoroutinefunction(DetectorOcrTesseract.inspecionar)


def test_falha_do_motor_vira_ERROR_e_nunca_leitura_vazia():
    """CONTRAPROVA: detector que explode não pode virar PASS.

    Uma `LeituraDePixel()` vazia numa falha diria que a peça foi inspecionada e
    está limpa. Levantar é o contrato — o portão marca ERROR e bloqueia.
    """
    from app.criativo.politica.detectores.ocr_tesseract import (
        DetectorOcrTesseract,
        MotorDeOcrIndisponivel,
    )

    d = DetectorOcrTesseract(versao="5.0.0-fixture")
    with pytest.raises(MotorDeOcrIndisponivel):
        d.inspecionar(b"nao-e-imagem", mime="image/png")

    insp.registrar_detector_de_pixel(d)
    recibo_da_peca = _avaliar()
    assert recibo_da_peca.decisao == P.GATE_UNAVAILABLE
    assert "PIXEL_DETECTOR_FAILED" in recibo_da_peca.motivos
    quebrado = [x for x in recibo_da_peca.detectores if x.nome == "ocr.tesseract"]
    assert quebrado and quebrado[0].resultado == "ERROR"
