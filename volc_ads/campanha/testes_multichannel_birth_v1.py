"""Contratos da missão Multichannel Birth Engine v1.

Nenhum teste fala com a rede: usa protos v25 reais e dublês locais para provar
que os três canais podem atravessar a mesma autoridade Python, com campanha
PAUSED e sem expansão automática de URL em PMax.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import pathlib
import struct
import sys
import zlib
from datetime import datetime, timezone
from importlib import import_module

import pytest
from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from volc_ads import subir as motor  # noqa: E402
from volc_ads.campanha import perfil, pmax  # noqa: E402
from volc_ads.campanha.brief import (  # noqa: E402
    AcaoDeConversao,
    Brief,
    ConfiguracaoPMax,
    Copy,
    ImagemParaSubir,
    ImagensPMax,
    Linhagem,
    _emitir_recibo_asset_aprovado,
    _emitir_recibo_de_mensuracao,
)

CID = "5478096539"
MCC = "6016739364"


class _Enums:
    def __getattr__(self, nome: str):
        wrapper = getattr(import_module("google.ads.googleads.v25.enums"), nome)
        for attr in dir(wrapper):
            valor = getattr(wrapper, attr)
            if isinstance(valor, enum.EnumMeta):
                return valor
        raise AttributeError(nome)


def _cliente_sem_rede():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    c.enums = _Enums()
    return c


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    monkeypatch.setattr(pmax, "cliente", lambda _login: _cliente_sem_rede())


def _png(largura: int, altura: int, *, semente: bytes) -> bytes:
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return (struct.pack(">I", len(dados)) + corpo
                + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    linha = (semente * 3 * largura)[: 3 * largura]
    cru = b"".join(b"\x00" + linha for _ in range(altura))
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", ihdr)
            + bloco(b"IDAT", zlib.compress(cru)) + bloco(b"IEND", b""))


def _imagem(nome: str, papel: str, largura: int, altura: int) -> ImagemParaSubir:
    dados = _png(largura, altura, semente=nome.encode())
    h = hashlib.sha256(dados).hexdigest()
    linhagem = Linhagem(
        nome=nome,
        papel=papel,
        identidade=h,
        conteudo_hash="sha256:" + h,
        motor="teste", insumo="asset hermético",
        quando=datetime.now(timezone.utc).isoformat(),
        origem="asset hermético",
        mime="image/png", largura=largura, altura=altura,
        bytes_totais=len(dados),
        exigencia_fonte="teste",
        exigencia_provisoria=False,
    )
    recibo = _emitir_recibo_asset_aprovado(
        catalogo_id=h,
        canal=pmax.CANAL,
        nome=nome,
        papel=papel,
        conteudo_hash="sha256:" + h,
        mime="image/png",
        largura=largura,
        altura=altura,
        bytes_totais=len(dados),
        resource_name=None,
        exigencia_fonte="teste",
        exigencia_provisoria=False,
        medidor_id="teste-png",
        reconferidor=lambda b: ("image/png", largura, altura, len(b)),
        linhagem=linhagem,
    )
    return ImagemParaSubir(
        nome=nome,
        dados=dados,
        linhagem=linhagem,
        mime="image/png",
        largura=largura,
        altura=altura,
        recibo_aprovacao=recibo,
    )


def _mensuracao():
    return _emitir_recibo_de_mensuracao(
        customer_id=CID,
        login_customer_id=MCC,
        lido_em=datetime.now(timezone.utc).isoformat(),
        consulta="SELECT conversion_action.resource_name FROM conversion_action",
        coletor="teste hermético",
        acoes=(AcaoDeConversao(
            resource_name=f"customers/{CID}/conversionActions/123",
            nome="Lead",
            tipo="WEBPAGE",
            categoria="SUBMIT_LEAD_FORM",
            status="ENABLED",
            primaria_para_meta=True,
            inclui_em_conversoes=True,
            carrega_valor=True,
            conversoes_ultimos_30d=1.0,
        ),),
    )


def _brief_pmax() -> Brief:
    return Brief(
        nicho="Canario PMax", slug="canario-pmax",
        url_final="https://example.invalid/lp/",
        keywords=[],
        copy=Copy(
            headlines=["Titulo PMax Um", "Titulo PMax Dois", "Titulo PMax Tres"],
            long_headlines=["Titulo Longo PMax Seguro"],
            descriptions=["Descricao curta", "Descricao alternativa segura"],
            business_name="VOLC",
        ),
        budget_diario=10.0,
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        prefixo_nome="CANARIO_PMAX",
        carimbo_nome="20260904",
        imagens_pmax=ImagensPMax(
            marketing=[_imagem("mkt.png", "marketing", 1200, 628)],
            marketing_quadrada=[_imagem("sq.png", "marketing_quadrada", 1200, 1200)],
            marketing_retrato=[_imagem("portrait.png", "marketing_retrato", 960, 1200)],
            logo=[_imagem("logo.png", "logo", 1200, 1200)],
            logo_paisagem=[_imagem("logo-land.png", "logo_paisagem", 1200, 300)],
        ),
        pmax=ConfiguracaoPMax(
            brand_guidelines_enabled=False,
            mensuracao=_mensuracao(),
            sinais=(),
            negativas=(),
            nome_do_asset_group="Canario PMax AG",
        ),
    )


def test_birth_v1_pmax_entra_na_mesma_autoridade_de_prova_e_criacao() -> None:
    assert perfil.PERFORMANCE_MAX.construtor is pmax.construir
    assert perfil.PERFORMANCE_MAX.validador is pmax.validar
    assert perfil.PERFORMANCE_MAX.permite_mutacao_real is True
    assert "PERFORMANCE_MAX" in motor.PROVADORES_POR_CANAL
    assert "PERFORMANCE_MAX" in motor.CONSTRUTORES_POR_CANAL


def test_birth_v1_pmax_planeja_sem_bloqueio_de_executor_e_com_url_exata() -> None:
    plano = pmax.planejar(CID, _brief_pmax(), login_customer_id=MCC)
    assert plano.prontidao.pode_provar is True
    assert plano.prontidao.pode_criar is True
    assert not [b for b in plano.bloqueios if b.codigo == "PMAX_FORA_DO_EXECUTOR"]
    grupo = next(u for u in plano.unidades if u.tipo == "asset_group")
    assert grupo.status == "PAUSED"
    assert grupo.urls_finais == ("https://example.invalid/lp/",)


def test_birth_v1_pmax_payload_desabilita_expansao_de_url_final() -> None:
    ops, r = pmax.construir(CID, _brief_pmax(), login_customer_id=MCC)
    assert r.ok
    campanha = next(o.campaign_operation.create for o in ops
                    if o._pb.WhichOneof("operation") == "campaign_operation")
    automacoes = {
        s.asset_automation_type.name: s.asset_automation_status.name
        for s in campanha.asset_automation_settings
    }
    assert automacoes["FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION"] == "OPTED_OUT"
    assert campanha.status.name == "PAUSED"


def test_birth_v1_subir_nao_recusa_pmax_por_politica_de_canal() -> None:
    # O caminho de escrita continua protegido por selo + trava ambiente; este
    # teste prova só que PMax não morre mais no portão antigo de canal sem mutate.
    motor._recusar_canal_sem_mutacao("PERFORMANCE_MAX")
