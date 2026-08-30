"""Provas herméticas da primeira onda executora de Demand Gen.

Nenhum caso carrega credencial ou chama Google Ads. O cliente é um invólucro
sem autenticação usado apenas para produzir protos v25; toda função que faria
rede é substituída por um dublê que registra o payload ou falha o teste.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import struct
from datetime import datetime, timezone
from importlib import import_module

import pytest
from google.ads.googleads.client import GoogleAdsClient

from volc_ads import criativo_ponte
from volc_ads import subir as motor
from volc_ads.campanha import comum, demand_gen, perfil
from volc_ads.campanha.brief import (
    AssetRemotoDemandGen,
    Brief,
    ConfiguracaoDemandGen,
    ControlesDeCanalDemandGen,
    Copy,
    ImagemParaSubir,
    ImagensDemandGen,
    Linhagem,
    Sitelink,
    Snippet,
)
from volc_ads.criativo.contrato import (
    Asset,
    LoteDeAssets,
    Origem,
    Procedencia,
    TipoDeAsset,
    hash_de_conteudo,
)

CID = "8017851692"
MCC = "6016739364"


class _Enums:
    def __getattr__(self, nome: str):
        wrapper = getattr(import_module("google.ads.googleads.v25.enums"), nome)
        for attr in dir(wrapper):
            valor = getattr(wrapper, attr)
            if isinstance(valor, enum.EnumMeta):
                return valor
        raise AttributeError(nome)


def _cliente_sem_rede() -> GoogleAdsClient:
    cliente = GoogleAdsClient.__new__(GoogleAdsClient)
    cliente.version = "v25"
    cliente.use_proto_plus = True
    cliente.enums = _Enums()
    return cliente


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demand_gen, "cliente", lambda _login: _cliente_sem_rede())


def _png(largura: int, altura: int, *, semente: bytes) -> bytes:
    """Cabeçalho suficiente para o medidor stdlib apurar tipo e dimensão."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", largura, altura)
        + b"\x08\x06\x00\x00\x00"
        + semente
    )


def _imagem(nome: str, papel: str, largura: int, altura: int) -> ImagemParaSubir:
    dados = _png(largura, altura, semente=nome.encode())
    conteudo_hash = "sha256:" + hashlib.sha256(dados).hexdigest()
    return ImagemParaSubir(
        nome=nome,
        dados=dados,
        mime="image/png",
        largura=largura,
        altura=altura,
        linhagem=Linhagem(
            nome=nome,
            papel=papel,
            identidade="cri_" + conteudo_hash.removeprefix("sha256:")[:20],
            conteudo_hash=conteudo_hash,
            motor="motor-hermetico",
            versao_do_motor="1",
            insumo=f"gerar {nome}",
            quando="2026-08-29T12:00:00+00:00",
            origem="gerado",
            mime="image/png",
            largura=largura,
            altura=altura,
            bytes_totais=len(dados),
            exigencia_fonte="matriz-api/demand-gen.md",
            exigencia_provisoria=False,
        ),
    )


def _configuracao(**troca) -> ConfiguracaoDemandGen:
    base = {
        "upgraded_targeting": True,
        "controles_de_canal": ControlesDeCanalDemandGen(
            estrategia="ALL_CHANNELS", selected_channels=None
        ),
        "audiencias": (f"customers/{CID}/audiences/7001",),
        "intencoes": (),
        "exclusoes_de_audiencia": (),
    }
    base.update(troca)
    return ConfiguracaoDemandGen(**base)


def _imagens(**troca) -> ImagensDemandGen:
    paisagem, b1 = _asset(
        TipoDeAsset.IMAGEM_MARKETING, 600, 314, semente=b"paisagem"
    )
    logo, b2 = _asset(TipoDeAsset.LOGO_QUADRADO, 144, 144, semente=b"logo")
    entrega = criativo_ponte.imagens_de_demand_gen(
        LoteDeAssets(canal="DEMAND_GEN", assets=(paisagem, logo)),
        {paisagem.identidade: b1, logo.identidade: b2},
    )
    assert entrega.ok, entrega.resumo()
    base = {
        papel: list(getattr(entrega.imagens, papel))
        for papel in ImagensDemandGen.PAPEIS
    }
    base.update(troca)
    return ImagensDemandGen(**base)


def _brief(**troca) -> Brief:
    base = {
        "nicho": "Saque Anual",
        "slug": "saque-anual",
        "url_final": "https://creditoup.com.br/r/saque-anual/",
        "keywords": [],
        "copy": Copy(
            headlines=["Entenda o Saque Anual"],
            descriptions=["Veja regras, prazos e limites em fonte informativa."],
            business_name="Credito Up",
        ),
        "estrategia_lance": "MAXIMIZE_CONVERSIONS",
        "imagens_demand_gen": _imagens(),
        "demand_gen": _configuracao(),
    }
    base.update(troca)
    return Brief(**base)


def _copy(**troca) -> Copy:
    base = {
        "headlines": ["Entenda o Saque Anual"],
        "descriptions": ["Veja regras, prazos e limites em fonte informativa."],
        "business_name": "Credito Up",
    }
    base.update(troca)
    return Copy(**base)


def _por_tipo(ops, tipo: str):
    return [o for o in ops if o._pb.WhichOneof("operation") == tipo]


def _erros(resultado) -> str:
    return "\n".join(f"{a.campo}: {a.motivo}" for a in resultado.erros)


def test_grafo_atomico_ordem_ids_temporarios_e_tres_status_pausados() -> None:
    ops, resultado = demand_gen.construir(CID, _brief(), login_customer_id=MCC)
    assert resultado.ok, _erros(resultado)

    assert [o._pb.WhichOneof("operation") for o in ops] == [
        "campaign_budget_operation",
        "campaign_operation",
        "ad_group_operation",
        "ad_group_criterion_operation",  # geo no grupo: upgraded_targeting=True
        "ad_group_criterion_operation",  # idioma
        "ad_group_criterion_operation",  # Audience positiva
        "asset_operation",
        "asset_operation",
        "ad_group_ad_operation",
    ]

    budget = _por_tipo(ops, "campaign_budget_operation")[
        0
    ].campaign_budget_operation.create
    campanha = _por_tipo(ops, "campaign_operation")[0].campaign_operation.create
    grupo = _por_tipo(ops, "ad_group_operation")[0].ad_group_operation.create
    anuncio = _por_tipo(ops, "ad_group_ad_operation")[0].ad_group_ad_operation.create
    assets = [o.asset_operation.create for o in _por_tipo(ops, "asset_operation")]

    assert budget.resource_name == comum.temp(CID, "campaignBudgets", comum.T_BUDGET)
    assert budget.explicitly_shared is False
    assert campanha.resource_name == comum.temp(CID, "campaigns", comum.T_CAMPANHA)
    assert campanha.advertising_channel_type.name == "DEMAND_GEN"
    assert campanha.status.name == "PAUSED"
    assert campanha.demand_gen_campaign_settings.upgraded_targeting is True
    assert (
        campanha._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"
    )
    campos_maxconv = {
        campo.name for campo, _ in campanha.maximize_conversions._pb.ListFields()
    }
    assert "target_cpa_micros" not in campos_maxconv, "ausência de tCPA virou zero"

    assert grupo.resource_name == comum.temp_adgroup(CID, 0)
    assert grupo.status.name == "PAUSED"
    assert "type" not in {campo.name for campo, _ in grupo._pb.ListFields()}
    assert (
        grupo.demand_gen_ad_group_settings.channel_controls.channel_strategy.name
        == "ALL_CHANNELS"
    )
    assert anuncio.status.name == "PAUSED"
    assert "demand_gen_multi_asset_ad" in {
        campo.name for campo, _ in anuncio.ad._pb.ListFields()
    }

    assert [a.resource_name for a in assets] == [
        comum.temp_imagem(CID, 0),
        comum.temp_imagem(CID, 1),
    ]
    info = anuncio.ad.demand_gen_multi_asset_ad
    assert [x.asset for x in info.marketing_images] == [comum.temp_imagem(CID, 0)]
    assert [x.asset for x in info.logo_images] == [comum.temp_imagem(CID, 1)]
    assert info.business_name == "Credito Up"
    assert list(anuncio.ad.final_urls) == [_brief().url_final]


def test_upgraded_targeting_false_move_geo_e_idioma_para_a_campanha() -> None:
    cfg = _configuracao(upgraded_targeting=False, audiencias=())
    ops, resultado = demand_gen.construir(
        CID, _brief(demand_gen=cfg), login_customer_id=MCC
    )
    assert resultado.ok, _erros(resultado)
    tipos = [o._pb.WhichOneof("operation") for o in ops]
    assert tipos[:5] == [
        "campaign_budget_operation",
        "campaign_operation",
        "campaign_criterion_operation",
        "campaign_criterion_operation",
        "ad_group_operation",
    ]
    assert "ad_group_criterion_operation" not in tipos


def test_selected_channels_ocupa_o_ramo_certo_sem_inventar_flags() -> None:
    selecionados = frozenset({"youtube_shorts", "discover"})
    cfg = _configuracao(
        controles_de_canal=ControlesDeCanalDemandGen(
            estrategia="SELECTED_CHANNELS", selected_channels=selecionados
        ),
        audiencias=(),
    )
    ops, resultado = demand_gen.construir(
        CID, _brief(demand_gen=cfg), login_customer_id=MCC
    )
    assert resultado.ok, _erros(resultado)
    grupo = _por_tipo(ops, "ad_group_operation")[0].ad_group_operation.create
    controles = grupo.demand_gen_ad_group_settings.channel_controls
    campos = {campo.name for campo, _ in controles._pb.ListFields()}
    assert "selected_channels" in campos
    assert "channel_strategy" not in campos
    assert "channel_config" not in campos, "campo output-only foi escrito"
    verdadeiros = {
        nome
        for nome in demand_gen.CANAIS_SELECIONAVEIS_DEMAND_GEN
        if getattr(controles.selected_channels, nome)
    }
    assert verdadeiros == selecionados


@pytest.mark.parametrize(
    "troca,campo",
    [
        ({"upgraded_targeting": None}, "upgraded_targeting"),
        ({"controles_de_canal": None}, "controles_de_canal"),
        ({"audiencias": None}, "audiencias"),
        ({"intencoes": None}, "intencoes"),
        ({"exclusoes_de_audiencia": None}, "exclusoes_de_audiencia"),
    ],
)
def test_ausencia_de_escolha_perigosa_falha_antes_de_cliente(
    monkeypatch: pytest.MonkeyPatch, troca: dict, campo: str
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail("dados incompletos chegaram ao cliente Google"),
    )
    ops, resultado = demand_gen.construir(
        CID, _brief(demand_gen=_configuracao(**troca)), login_customer_id=MCC
    )
    assert ops == [] and not resultado.ok
    assert campo in _erros(resultado)


def test_audiencia_intencao_e_exclusao_nao_sao_colapsadas() -> None:
    cfg = _configuracao(
        audiencias=(f"customers/{CID}/audiences/7001",),
        intencoes=("interessados em crédito",),
        exclusoes_de_audiencia=(f"customers/{CID}/audiences/7002",),
    )
    ops, resultado = demand_gen.construir(
        CID, _brief(demand_gen=cfg), login_customer_id=MCC
    )
    assert ops == [] and not resultado.ok
    campos = {a.campo for a in resultado.erros}
    assert "demand_gen.intencoes" in campos
    assert "demand_gen.exclusoes_de_audiencia" in campos
    assert "demand_gen.audiencias" not in campos


def test_keywords_long_headline_video_e_tcpa_nao_migram_por_analogia() -> None:
    ops, resultado = demand_gen.construir(
        CID,
        _brief(
            keywords=["keyword não é intenção"],
            copy=Copy(
                headlines=["Entenda o Saque Anual"],
                descriptions=["Veja as regras."],
                long_headlines=["Este texto pertence a outro tipo de anúncio"],
                business_name="Credito Up",
            ),
            videos=[f"customers/{CID}/assets/9001"],
            tcpa=5.0,
        ),
        login_customer_id=MCC,
    )
    assert ops == [] and not resultado.ok
    campos = {a.campo for a in resultado.erros}
    assert {"keywords", "copy.long_headlines", "videos", "tcpa"} <= campos


@pytest.mark.parametrize(
    ("copy", "campo"),
    [
        (_copy(sitelinks=[Sitelink("Saiba mais")]), "copy.sitelinks"),
        (_copy(callouts=["Sem taxa escondida"]), "copy.callouts"),
        (
            _copy(snippet=Snippet("Serviços", ["Consulta", "Simulação"])),
            "copy.snippet",
        ),
    ],
)
def test_extensao_nao_operada_e_recusada_antes_do_cliente(
    monkeypatch: pytest.MonkeyPatch, copy: Copy, campo: str
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail(f"{campo} descartado chegou ao cliente"),
    )
    ops, resultado = demand_gen.construir(
        CID, _brief(copy=copy), login_customer_id=MCC
    )
    assert ops == [] and not resultado.ok
    assert campo in {achado.campo for achado in resultado.erros}


def test_sdk_v25_real_instancia_e_serializa_folhas_e_operacoes() -> None:
    suporte = demand_gen.sondar_proto_v25()
    assert suporte.disponivel, suporte.motivo
    assert {
        "campaign_budget_operation",
        "campaign_operation",
        "campaign_criterion_operation",
        "ad_group_operation",
        "ad_group_criterion_operation",
        "asset_operation",
        "ad_group_ad_operation",
        "DemandGenMultiAssetAdInfo",
        "AdImageAsset",
        "AdTextAsset",
    } <= set(suporte.objetos_serializados)

    ops, resultado = demand_gen.construir(CID, _brief(), login_customer_id=MCC)
    assert resultado.ok, _erros(resultado)
    serializados = [
        op._pb.SerializeToString(deterministic=True)
        for op in ops
    ]
    assert len(serializados) == len(ops)
    assert all(serializados)


def test_sdk_v25_ausente_rebaixa_capacidade_sem_cliente_ou_validate_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "sondar_proto_v25",
        lambda: demand_gen.SuporteProtoV25(False, "namespace removido"),
    )
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail("SDK incompatível chegou ao cliente"),
    )
    monkeypatch.setattr(
        demand_gen,
        "validar_mutacoes",
        lambda *_a, **_k: pytest.fail("SDK incompatível chegou ao validate_only"),
    )

    resultado, falha, quantidade = demand_gen.validar(
        CID, _brief(), login_customer_id=MCC
    )
    assert not resultado.ok and falha is None and quantidade == 0
    assert "sdk.google_ads.v25" in _erros(resultado)
    assert "namespace removido" in _erros(resultado)


def test_limites_e_resource_names_falham_fechado_sem_chamada() -> None:
    aprovada = _imagens()
    muitas = [aprovada.marketing[0]] * 21
    imagens = ImagensDemandGen(
        marketing=muitas,
        logo_quadrado=aprovada.logo_quadrado,
    )
    ops, resultado = demand_gen.construir(
        CID, _brief(imagens_demand_gen=imagens), login_customer_id=MCC
    )
    assert ops == [] and "teto combinado" in _erros(resultado)

    conta_errada = _imagens_remotas(
        marketing_rn="customers/1234567890/assets/1"
    )
    ops2, resultado2 = demand_gen.construir(
        CID, _brief(imagens_demand_gen=conta_errada), login_customer_id=MCC
    )
    assert ops2 == [] and "não da conta" in _erros(resultado2)


def _asset(
    tipo: TipoDeAsset,
    largura: int,
    altura: int,
    *,
    semente: bytes,
    id_externo: str | None = None,
    mime: str = "image/png",
    largura_declarada: int | None = None,
    altura_declarada: int | None = None,
) -> tuple[Asset, bytes]:
    dados = _png(largura, altura, semente=semente)
    return (
        Asset(
            tipo=tipo,
            procedencia=Procedencia(
                motor="motor-hermetico",
                versao_do_motor="1",
                insumo="brief aprovado",
                quando=datetime(2026, 8, 29, tzinfo=timezone.utc),
            ),
            conteudo_hash=hash_de_conteudo(dados),
            origem=Origem.GERADO,
            bytes_totais=len(dados),
            mime=mime,
            largura=largura if largura_declarada is None else largura_declarada,
            altura=altura if altura_declarada is None else altura_declarada,
            id_externo=id_externo,
            rotulo=tipo.value,
        ),
        dados,
    )


def _imagens_remotas(
    *,
    marketing_rn: str = f"customers/{CID}/assets/9101",
    logo_rn: str = f"customers/{CID}/assets/9102",
) -> ImagensDemandGen:
    paisagem, b1 = _asset(
        TipoDeAsset.IMAGEM_MARKETING,
        600,
        314,
        semente=b"paisagem-remota",
        id_externo=marketing_rn,
    )
    logo, b2 = _asset(
        TipoDeAsset.LOGO_QUADRADO,
        144,
        144,
        semente=b"logo-remoto",
        id_externo=logo_rn,
    )
    entrega = criativo_ponte.imagens_de_demand_gen(
        LoteDeAssets(canal="DEMAND_GEN", assets=(paisagem, logo)),
        {paisagem.identidade: b1, logo.identidade: b2},
    )
    assert entrega.ok, entrega.resumo()
    return entrega.imagens


def test_ponte_do_estudio_aprova_papeis_e_recusa_retrato_sem_imagem_base() -> None:
    paisagem, b1 = _asset(TipoDeAsset.IMAGEM_MARKETING, 600, 314, semente=b"paisagem")
    retrato, b2 = _asset(
        TipoDeAsset.IMAGEM_MARKETING_RETRATO, 480, 600, semente=b"retrato"
    )
    logo, b3 = _asset(TipoDeAsset.LOGO_QUADRADO, 144, 144, semente=b"logo")
    conteudos = {
        a.identidade: b for a, b in ((paisagem, b1), (retrato, b2), (logo, b3))
    }

    entrega = criativo_ponte.imagens_de_demand_gen(
        LoteDeAssets(canal="DEMAND_GEN", assets=(paisagem, retrato, logo)),
        conteudos,
    )
    assert entrega.ok
    assert len(entrega.imagens.marketing) == 1
    assert len(entrega.imagens.marketing_retrato) == 1
    assert len(entrega.imagens.logo_quadrado) == 1
    assert all(linhagem.confirmada for linhagem in entrega.linhagem)

    somente_retrato = criativo_ponte.imagens_de_demand_gen(
        LoteDeAssets(canal="DEMAND_GEN", assets=(retrato, logo)),
        {retrato.identidade: b2, logo.identidade: b3},
    )
    assert not somente_retrato.ok
    assert "imagem base" in somente_retrato.resumo()


def test_linhagem_autoatestada_e_resource_name_solto_nao_sao_recibo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail("asset sem recibo chegou ao cliente"),
    )
    aprovadas = _imagens()

    autoatestada = ImagensDemandGen(
        marketing=[_imagem("manual", "marketing", 600, 314)],
        logo_quadrado=aprovadas.logo_quadrado,
    )
    ops, resultado = demand_gen.construir(
        CID, _brief(imagens_demand_gen=autoatestada), login_customer_id=MCC
    )
    assert ops == [] and "Linhagem preenchida" in _erros(resultado)

    aprovada = aprovadas.marketing[0]
    linhagem_trocada = dataclasses.replace(
        aprovada.linhagem, identidade="cri_autoatestado"
    )
    lote_trocado = ImagensDemandGen(
        marketing=[dataclasses.replace(aprovada, linhagem=linhagem_trocada)],
        logo_quadrado=aprovadas.logo_quadrado,
    )
    ops_trocadas, resultado_trocado = demand_gen.construir(
        CID, _brief(imagens_demand_gen=lote_trocado), login_customer_id=MCC
    )
    assert ops_trocadas == []
    assert "identidade de catálogo" in _erros(resultado_trocado)

    remoto_solto = ImagensDemandGen(
        marketing=[f"customers/{CID}/assets/9101"],
        logo_quadrado=aprovadas.logo_quadrado,
    )
    ops2, resultado2 = demand_gen.construir(
        CID, _brief(imagens_demand_gen=remoto_solto), login_customer_id=MCC
    )
    assert ops2 == []
    assert "recibo tipado" in _erros(resultado2)
    assert "bytes para reconferência" in _erros(resultado2)


def test_asset_remoto_aprovado_e_reconferido_so_e_referenciado() -> None:
    imagens = _imagens_remotas()
    assert all(
        isinstance(item, AssetRemotoDemandGen) and item.recibo.integro
        for item in imagens.todas
    )

    ops, resultado = demand_gen.construir(
        CID, _brief(imagens_demand_gen=imagens), login_customer_id=MCC
    )
    assert resultado.ok, _erros(resultado)
    assert _por_tipo(ops, "asset_operation") == []
    anuncio = _por_tipo(ops, "ad_group_ad_operation")[0]
    info = anuncio.ad_group_ad_operation.create.ad.demand_gen_multi_asset_ad
    assert [item.asset for item in info.marketing_images] == [
        f"customers/{CID}/assets/9101"
    ]
    assert [item.asset for item in info.logo_images] == [
        f"customers/{CID}/assets/9102"
    ]


def test_asset_remoto_adulterado_morre_por_hash_e_papel_antes_do_cliente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail("asset adulterado chegou ao cliente"),
    )
    imagens = _imagens_remotas()
    marketing = imagens.marketing[0]
    adulterado = dataclasses.replace(marketing, dados=marketing.dados + b"troca")
    lote = ImagensDemandGen(
        marketing=[adulterado],
        logo_quadrado=[marketing],
    )

    ops, resultado = demand_gen.construir(
        CID, _brief(imagens_demand_gen=lote), login_customer_id=MCC
    )
    assert ops == [] and not resultado.ok
    texto = _erros(resultado)
    assert "bytes/hash divergentes" in texto
    assert "recibo aprovou papel 'marketing', não 'logo_quadrado'" in texto


@pytest.mark.parametrize(
    ("mime", "largura_declarada", "altura_declarada", "esperado"),
    [
        ("image/jpeg", None, None, "mime divergente"),
        ("image/png", 1200, 628, "dimensões divergentes"),
    ],
)
def test_mime_e_dimensoes_de_catalogo_sao_rechecados_nos_bytes(
    monkeypatch: pytest.MonkeyPatch,
    mime: str,
    largura_declarada: int | None,
    altura_declarada: int | None,
    esperado: str,
) -> None:
    paisagem, b1 = _asset(
        TipoDeAsset.IMAGEM_MARKETING,
        600,
        314,
        semente=b"metadado-falso",
        mime=mime,
        largura_declarada=largura_declarada,
        altura_declarada=altura_declarada,
    )
    logo, b2 = _asset(TipoDeAsset.LOGO_QUADRADO, 144, 144, semente=b"logo-ok")
    entrega = criativo_ponte.imagens_de_demand_gen(
        LoteDeAssets(canal="DEMAND_GEN", assets=(paisagem, logo)),
        {paisagem.identidade: b1, logo.identidade: b2},
    )
    assert entrega.ok, entrega.resumo()
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail("metadado falso chegou ao cliente"),
    )

    ops, resultado = demand_gen.construir(
        CID, _brief(imagens_demand_gen=entrega.imagens), login_customer_id=MCC
    )
    assert ops == [] and esperado in _erros(resultado)


def test_resource_names_e_duplicatas_exigem_forma_canonica(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "cliente",
        lambda _login: pytest.fail("identidade não canônica chegou ao cliente"),
    )
    cfg = _configuracao(
        audiencias=(
            f"customers/{CID}/audiences/7001",
            f"customers/{CID}/audiences/7001",
        )
    )
    aprovadas = _imagens()
    duplicadas = ImagensDemandGen(
        marketing=[aprovadas.marketing[0], aprovadas.marketing[0]],
        logo_quadrado=aprovadas.logo_quadrado,
    )
    ops, resultado = demand_gen.construir(
        CID,
        _brief(demand_gen=cfg, imagens_demand_gen=duplicadas),
        login_customer_id=MCC,
    )
    assert ops == []
    texto = _erros(resultado)
    assert "Audience duplicada depois da canonização" in texto
    assert "asset duplicado na forma canônica" in texto

    nao_canonicas = _imagens_remotas(
        marketing_rn=f"customers/0{CID}/assets/09101"
    )
    ops2, resultado2 = demand_gen.construir(
        CID, _brief(imagens_demand_gen=nao_canonicas), login_customer_id=MCC
    )
    assert ops2 == [] and "forma canônica" in _erros(resultado2)


def test_validar_faz_uma_unica_prova_do_lote_inteiro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas = []

    def _validate_only(cid, ops, *, login_customer_id):
        chamadas.append((cid, tuple(ops), login_customer_id))

    monkeypatch.setattr(demand_gen, "validar_mutacoes", _validate_only)
    resultado, falha, quantidade = demand_gen.validar(
        CID, _brief(), login_customer_id=MCC
    )
    assert resultado.ok and falha is None
    assert quantidade == 9
    assert len(chamadas) == 1
    assert chamadas[0][0] == CID and chamadas[0][2] == MCC
    assert len(chamadas[0][1]) == quantidade


def test_validar_localmente_recusado_faz_zero_chamadas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        demand_gen,
        "validar_mutacoes",
        lambda *_a, **_k: pytest.fail("validate_only recebeu payload inelegível"),
    )
    resultado, falha, quantidade = demand_gen.validar(
        CID,
        _brief(demand_gen=_configuracao(upgraded_targeting=None)),
        login_customer_id=MCC,
    )
    assert not resultado.ok and falha is None and quantidade == 0


def test_perfil_prova_demand_gen_mas_registry_real_e_executor_recusam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert perfil.DEMAND_GEN.sabe_provar is True
    assert perfil.DEMAND_GEN.sabe_criar is False
    assert "DEMAND_GEN" in motor.PROVADORES_POR_CANAL
    assert "DEMAND_GEN" not in motor.CONSTRUTORES_POR_CANAL
    assert motor.resolver_provador(" demand_gen ")[0] == "DEMAND_GEN"

    monkeypatch.setattr(motor, "validar_mutacoes", lambda *_a, **_k: None)
    preparo = motor.preparar(
        CID,
        _brief(),
        login_customer_id=MCC,
        canal="DEMAND_GEN",
    )
    assert preparo.provado, preparo.porque_nao()
    assert preparo.selo.canal == "DEMAND_GEN"
    assert preparo.selo.login_customer_id == MCC
    assert len(preparo.selo.tipos_operacoes) == len(preparo.operacoes)
    assert len(preparo.selo.hashes_operacoes) == len(preparo.operacoes)
    monkeypatch.setattr(
        motor,
        "mutar",
        lambda *_a, **_k: pytest.fail("Demand Gen alcançou mutação real"),
    )
    monkeypatch.setattr(
        motor,
        "_recusar_trava_ambiente",
        lambda: pytest.fail("Demand Gen chegou até a trava de escrita"),
    )
    with pytest.raises(motor.CanalSemMutacaoReal, match="nada foi enviado"):
        motor.subir(preparo, motivo="prova hermética de recusa real")


@pytest.mark.parametrize(
    ("adulterar", "esperado"),
    [
        (
            lambda preparo: dataclasses.replace(preparo, canal="SEARCH"),
            "rótulo do preparo foi trocado",
        ),
        (
            lambda preparo: dataclasses.replace(
                preparo, login_customer_id="9999999999"
            ),
            "troca o escopo de autorização",
        ),
        (
            lambda preparo: dataclasses.replace(
                preparo,
                selo=dataclasses.replace(
                    preparo.selo,
                    tipos_operacoes=(
                        "campaign_operation.create",
                        *preparo.selo.tipos_operacoes[1:],
                    ),
                ),
            ),
            "tipo/verbo das operações divergiu",
        ),
        (
            lambda preparo: dataclasses.replace(
                preparo,
                selo=dataclasses.replace(
                    preparo.selo,
                    hashes_operacoes=(
                        "0" * 64,
                        *preparo.selo.hashes_operacoes[1:],
                    ),
                ),
            ),
            "hash individual das operações divergiu",
        ),
    ],
)
def test_relabel_mcc_tipo_e_hash_divergentes_morrem_antes_da_trava_e_mutacao(
    monkeypatch: pytest.MonkeyPatch,
    adulterar,
    esperado: str,
) -> None:
    monkeypatch.setattr(motor, "validar_mutacoes", lambda *_a, **_k: None)
    preparo = motor.preparar(
        CID, _brief(), login_customer_id=MCC, canal="DEMAND_GEN"
    )
    assert preparo.provado, preparo.porque_nao()
    monkeypatch.setattr(
        motor,
        "_recusar_trava_ambiente",
        lambda: pytest.fail("divergência chegou à trava"),
    )
    monkeypatch.setattr(
        motor,
        "mutar",
        lambda *_a, **_k: pytest.fail("divergência chegou ao cliente/mutate"),
    )

    with pytest.raises(motor.PayloadNaoValidado, match=esperado):
        motor.subir(
            adulterar(preparo),
            motivo="contraprova hermética de autoridade do selo",
        )


def test_canal_declarado_pelo_builder_nao_supera_o_canal_da_operacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = perfil.DEMAND_GEN

    def _builder_relabelado(*args, **kwargs):
        ops, resultado = real.construtor(*args, **kwargs)
        campanha = _por_tipo(ops, "campaign_operation")[0]
        campanha.campaign_operation.create.advertising_channel_type = (
            _cliente_sem_rede().enums.AdvertisingChannelTypeEnum.SEARCH
        )
        return ops, resultado

    falso = dataclasses.replace(real, construtor=_builder_relabelado)
    monkeypatch.setitem(perfil.PERFIS, "DEMAND_GEN", falso)
    monkeypatch.setattr(
        motor,
        "validar_mutacoes",
        lambda *_a, **_k: pytest.fail(
            "divergência entre perfil e operação chegou ao validate_only"
        ),
    )

    preparo = motor.preparar(
        CID, _brief(), login_customer_id=MCC, canal="DEMAND_GEN"
    )
    assert not preparo.provado
    assert "perfil declarou 'DEMAND_GEN', operações declaram 'SEARCH'" in (
        preparo.recusa_local
    )
