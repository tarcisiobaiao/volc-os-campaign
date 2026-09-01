"""Contraprovas da observabilidade read-only de Performance Max (P04-T07).

Cada teste aqui nasceu como uma tentativa de REFUTAR a coleta PMax, nao de
confirma-la. As propriedades sob ataque sao sempre as mesmas cinco:

* ausencia nunca vira zero, e zero medido nunca vira ausencia;
* identidade completa, sem colisao entre contas;
* familia independente: uma cair nao derruba as outras;
* recibo vermelho e recibo verde coexistem, e repetir a janela nao duplica;
* nenhuma consulta pode virar mutacao, nem por acidente nem por atalho.

O dublê do Google Ads monta ``GoogleAdsRow`` v25 REAL — nao dicionario — para
que um campo inventado exploda aqui, e nao numa conta de cliente. Nenhum teste
deste arquivo abre socket.
"""

from __future__ import annotations

import ast
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from volc_ads.inteligencia_google import pmax
from volc_ads.inteligencia_google.alvo import AlvoColeta, ErroAlvoDivergente
from volc_ads.inteligencia_google.coletor import ColetorGoogleInteligencia
from volc_ads.inteligencia_google.persistencia import CampanhaAtiva

from test_google_inteligencia_persistente import PersistenciaDuble

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/v12_01_google_inteligencia_coletas.sql"

CONTA = "8017851692"
OUTRA_CONTA = "7016739360"
CAMPANHA_PMAX = "24156373100"

PMAX_PAUSADA = {
    "volc_campaign_id": "c3d5c0de-0000-4000-8000-000000000003",
    "campaign_id": CAMPANHA_PMAX,
    "customer_id": CONTA,
    "nome": "VOLC | PMax | Credito Up",
    "canal": "PERFORMANCE_MAX",
    "estado_externo": "PAUSED",
}
PMAX_OUTRA_CONTA = {
    "volc_campaign_id": "d4e6c0de-0000-4000-8000-000000000004",
    # MESMO campaign_id, conta diferente: o caso que a colisao de identidade
    # produziria se a chave nao carregasse a conta.
    "campaign_id": CAMPANHA_PMAX,
    "customer_id": OUTRA_CONTA,
    "nome": "VOLC | PMax | Outro Cliente",
    "canal": "PERFORMANCE_MAX",
    "estado_externo": "ENABLED",
}
SEARCH_LIGADA = {
    "volc_campaign_id": "b2e4c0de-0000-4000-8000-000000000002",
    "campaign_id": "24156373099",
    "customer_id": CONTA,
    "nome": "VOLC | Search | Credito Up",
    "canal": "SEARCH",
    "estado_externo": "ENABLED",
}
INVENTARIO = (PMAX_PAUSADA, PMAX_OUTRA_CONTA, SEARCH_LIGADA)

GRUPO_A = "2001"
GRUPO_B = "2002"
ASSET_TITULO = "3001"
ASSET_IMAGEM = "3002"


# ---------------------------------------------------------------------------
# dublê do Google Ads: protos v25 reais, zero rede, zero mutacao
# ---------------------------------------------------------------------------


def _row():
    from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

    return GoogleAdsRow()


def linha_campanha_pmax(
    campaign_id=CAMPANHA_PMAX, *, status="PAUSED", nome="VOLC | PMax | Credito Up",
):
    row = _row()
    row.campaign.id = int(campaign_id)
    row.campaign.resource_name = f"customers/{CONTA}/campaigns/{campaign_id}"
    row.campaign.name = nome
    row.campaign.status = status
    row.campaign.advertising_channel_type = "PERFORMANCE_MAX"
    row.campaign.bidding_strategy_type = "MAXIMIZE_CONVERSIONS"
    row.campaign.brand_guidelines_enabled = False
    row.campaign_budget.amount_micros = 50_000_000
    return row


def linha_asset_group(asset_group_id=GRUPO_A, *, forca=None, status="ENABLED"):
    row = _row()
    row.asset_group.id = int(asset_group_id)
    row.asset_group.resource_name = f"customers/{CONTA}/assetGroups/{asset_group_id}"
    row.asset_group.campaign = f"customers/{CONTA}/campaigns/{CAMPANHA_PMAX}"
    row.asset_group.name = f"Grupo {asset_group_id}"
    row.asset_group.status = status
    row.asset_group.primary_status = "ELIGIBLE"
    if forca is not None:
        row.asset_group.ad_strength = forca
    row.asset_group.final_urls.append("https://exemplo.com.br/pmax")
    row.campaign.id = int(CAMPANHA_PMAX)
    return row


def linha_asset_group_asset(
    asset_id=ASSET_TITULO, *, asset_group_id=GRUPO_A, tipo="HEADLINE",
):
    row = _row()
    row.asset_group_asset.resource_name = (
        f"customers/{CONTA}/assetGroupAssets/{asset_group_id}~{asset_id}~{tipo}"
    )
    row.asset_group_asset.asset_group = (
        f"customers/{CONTA}/assetGroups/{asset_group_id}"
    )
    row.asset_group_asset.asset = f"customers/{CONTA}/assets/{asset_id}"
    row.asset_group_asset.field_type = tipo
    row.asset_group_asset.status = "ENABLED"
    row.asset_group_asset.primary_status = "ELIGIBLE"
    row.asset_group_asset.source = "ADVERTISER"
    row.campaign.id = int(CAMPANHA_PMAX)
    return row


def linha_asset(asset_id=ASSET_TITULO, *, tipo="TEXT", texto="Credito com desconto"):
    row = _row()
    row.asset.id = int(asset_id)
    row.asset.resource_name = f"customers/{CONTA}/assets/{asset_id}"
    row.asset.name = f"Asset {asset_id}"
    row.asset.type_ = tipo
    if tipo == "TEXT":
        row.asset.text_asset.text = texto
    return row


def linha_sinal(asset_group_id=GRUPO_A, *, tema="credito consignado"):
    row = _row()
    row.asset_group_signal.resource_name = (
        f"customers/{CONTA}/assetGroupSignals/{asset_group_id}~1"
    )
    row.asset_group_signal.asset_group = (
        f"customers/{CONTA}/assetGroups/{asset_group_id}"
    )
    row.asset_group_signal.search_theme.text = tema
    return row


def linha_desempenho_grupo(
    asset_group_id=GRUPO_A, *, impressoes=0, cliques=0, custo=0,
    conversoes=0.0, valor=0.0, canal=None,
):
    """Métricas escritas EXPLICITAMENTE: zero medido chega como '0', nao sumido."""

    row = _row()
    row.asset_group.id = int(asset_group_id)
    row.asset_group.resource_name = f"customers/{CONTA}/assetGroups/{asset_group_id}"
    row.asset_group.name = f"Grupo {asset_group_id}"
    row.campaign.id = int(CAMPANHA_PMAX)
    row.metrics.impressions = impressoes
    row.metrics.clicks = cliques
    row.metrics.cost_micros = custo
    row.metrics.conversions = conversoes
    row.metrics.conversions_value = valor
    if canal is not None:
        row.segments.ad_network_type = canal
    return row


def linha_recomendacao(campaign_id=CAMPANHA_PMAX, *, forca="POOR"):
    row = _row()
    row.recommendation.resource_name = (
        f"customers/{CONTA}/recommendations/{campaign_id}~IMPROVE"
    )
    row.recommendation.type_ = "IMPROVE_PERFORMANCE_MAX_AD_STRENGTH"
    row.recommendation.campaign = f"customers/{CONTA}/campaigns/{campaign_id}"
    row.recommendation.dismissed = False
    row.recommendation.improve_performance_max_ad_strength_recommendation.asset_group = (
        f"customers/{CONTA}/assetGroups/{GRUPO_A}"
    )
    row.recommendation.improve_performance_max_ad_strength_recommendation.ad_strength = forca
    return row


def classificar_gaql(gaql: str) -> str:
    """Classifica pelo recurso do FROM, nunca por substring frouxa."""

    normal = " ".join(gaql.split())
    recurso = normal.split(" FROM ")[1].split(" ")[0].strip()
    if recurso == "asset_group":
        if "segments.ad_network_type" in normal:
            return "pmax_desempenho_por_canal"
        if "metrics." in normal:
            return "pmax_desempenho"
        return "pmax_asset_groups"
    if recurso == "campaign":
        return "pmax_campanha"
    return {
        "asset_group_asset": "pmax_asset_group_assets",
        "asset": "pmax_assets",
        "asset_group_signal": "pmax_sinais",
        "recommendation": "pmax_recomendacoes",
    }.get(recurso, recurso)


class _Lote:
    def __init__(self, results):
        self.results = results


class _GoogleAdsServiceDuble:
    def __init__(self, respostas, registro):
        self._respostas = respostas
        self._registro = registro

    def search_stream(self, *, customer_id, query):
        if not query.lstrip().upper().startswith("SELECT"):
            raise AssertionError("o coletor enviou algo que nao e SELECT")
        chave = classificar_gaql(query)
        self._registro.setdefault("consultas", []).append((customer_id, chave))
        self._registro.setdefault("gaql", []).append(query)
        resposta = self._respostas.get(chave, [])
        if isinstance(resposta, Exception):
            raise resposta
        return [_Lote(list(resposta))]

    def __getattr__(self, nome):
        # Qualquer superficie fora de `search_stream` — inclusive `mutate` —
        # cai aqui, fica registrada e explode. Silencio nao passa por prova.
        self._registro.setdefault("desconhecidos", []).append(f"GoogleAdsService.{nome}")
        raise AttributeError(nome)


class ClienteGoogleDuble:
    """Lista branca deliberada: a coleta PMax so pode falar com uma superficie."""

    def __init__(self, respostas=None):
        self.respostas = dict(respostas or {})
        self.registro: dict[str, list] = {}

    def get_service(self, nome):
        self.registro.setdefault("servicos", []).append(nome)
        if nome == "GoogleAdsService":
            return _GoogleAdsServiceDuble(self.respostas, self.registro)
        raise AssertionError(f"servico fora da lista branca: {nome}")

    def get_type(self, nome):  # pragma: no cover - a coleta PMax nao monta request
        self.registro.setdefault("tipos", []).append(nome)
        raise AssertionError(f"tipo fora da lista branca: {nome}")

    def __getattr__(self, nome):
        self.registro.setdefault("desconhecidos", []).append(f"cliente.{nome}")
        raise AttributeError(nome)


RESPOSTAS_COMPLETAS = {
    "pmax_campanha": [linha_campanha_pmax()],
    "pmax_asset_groups": [
        linha_asset_group(GRUPO_A, forca="GOOD"),
        linha_asset_group(GRUPO_B),  # sem ad_strength: ausencia de verdade
    ],
    "pmax_asset_group_assets": [
        linha_asset_group_asset(ASSET_TITULO, asset_group_id=GRUPO_A),
        linha_asset_group_asset(
            ASSET_IMAGEM, asset_group_id=GRUPO_A, tipo="MARKETING_IMAGE"
        ),
    ],
    "pmax_assets": [
        linha_asset(ASSET_TITULO),
        linha_asset(ASSET_IMAGEM, tipo="IMAGE"),
    ],
    "pmax_sinais": [linha_sinal(GRUPO_A)],
    # so o grupo A entregou na janela; o B nao tem linha nenhuma
    "pmax_desempenho": [linha_desempenho_grupo(GRUPO_A, impressoes=0, cliques=0)],
    "pmax_desempenho_por_canal": [
        linha_desempenho_grupo(GRUPO_A, impressoes=0, canal="SEARCH")
    ],
    "pmax_recomendacoes": [linha_recomendacao()],
}


#: O vocabulario que a migration v12_03 traria. Usado apenas para PROVAR que o
#: bloqueio de hoje mora no CHECK do banco, e nao no codigo desta coleta.
VOCABULARIO_AMPLIADO = frozenset(
    set(pmax.TIPOS_SINAL_ACEITOS_PELO_LEDGER)
    | set(pmax.TIPO_SINAL_POR_FAMILIA.values())
)


def _alvo(linha=PMAX_PAUSADA):
    return AlvoColeta(
        customer_id=linha["customer_id"],
        volc_campaign_id=linha["volc_campaign_id"],
        campaign_id=linha["campaign_id"],
    )


def coletor(respostas=None, inventario=INVENTARIO, **opcoes):
    persistencia = PersistenciaDuble(inventario)
    google = ClienteGoogleDuble(
        RESPOSTAS_COMPLETAS if respostas is None else respostas
    )
    motor = ColetorGoogleInteligencia(
        persistencia=persistencia, cliente_google=google, **opcoes
    )
    return motor, persistencia, google


def por_familia(resultado):
    return {c["familia"]: c for c in resultado["coletas"]}


def estados(resultado):
    return {c["familia"]: c["estado"] for c in resultado["coletas"]}


# ---------------------------------------------------------------------------
# A. campanha PAUSED PMax continua coletavel
# ---------------------------------------------------------------------------


def test_a_campanha_pmax_pausada_continua_coletavel():
    motor, _, google = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())

    assert resultado["estado_externo"] == "PAUSED"
    assert resultado["canal"] == pmax.CANAL_PMAX
    assert set(estados(resultado)) == set(pmax.FAMILIAS_PMAX)
    assert estados(resultado)[pmax.FAMILIA_ASSET_GROUPS] == "com_dados"
    # Nenhuma consulta filtrou por campanha habilitada: e isso que alcanca a
    # pausada. Se alguem acrescentar `campaign.status = 'ENABLED'`, cai aqui.
    for gaql in google.registro["gaql"]:
        assert "campaign.status = 'ENABLED'" not in gaql
        assert "campaign.status IN" not in gaql


def test_a_estados_externos_distintos_nao_se_achatam():
    """PAUSED, ENABLED e REMOVED chegam ao recibo como coisas diferentes."""

    vistos = set()
    for status in ("PAUSED", "ENABLED", "REMOVED"):
        respostas = dict(
            RESPOSTAS_COMPLETAS,
            pmax_campanha=[linha_campanha_pmax(status=status)],
        )
        motor, persistencia, _ = coletor(respostas)
        resultado = motor.executar_alvo_pmax(_alvo())
        familia = por_familia(resultado)[pmax.FAMILIA_CAMPANHA]
        vistos.add(familia["payload"]["status_observado"])
    assert vistos == {"PAUSED", "ENABLED", "REMOVED"}


def test_a_campanha_ausente_na_resposta_nao_e_campanha_removida():
    motor, _, _ = coletor(dict(RESPOSTAS_COMPLETAS, pmax_campanha=[]))
    resultado = motor.executar_alvo_pmax(_alvo())

    campanha = por_familia(resultado)[pmax.FAMILIA_CAMPANHA]
    assert campanha["estado"] == "vazio_confirmado"
    assert campanha["payload"]["status_observado"] is None


# ---------------------------------------------------------------------------
# B. campanha Search nao entra na coleta PMax
# ---------------------------------------------------------------------------


def test_b_campanha_search_nao_entra_na_coleta_pmax():
    motor, persistencia, google = coletor()
    with pytest.raises(pmax.ErroCanalNaoPMax, match="SEARCH"):
        motor.executar_alvo_pmax(_alvo(SEARCH_LIGADA))

    assert persistencia.documentos == []
    assert google.registro.get("consultas", []) == []


# ---------------------------------------------------------------------------
# N. campanha sem PMax recusa ANTES da coleta especifica
# ---------------------------------------------------------------------------


def test_n_recusa_acontece_antes_de_qualquer_consulta():
    motor, persistencia, google = coletor()
    with pytest.raises(pmax.ErroCanalNaoPMax):
        motor.executar_alvo_pmax(_alvo(SEARCH_LIGADA))

    assert google.registro.get("servicos") == ["GoogleAdsService"]  # so o construtor
    assert "gaql" not in google.registro
    assert persistencia.enviados == []


@pytest.mark.parametrize("canal_cego", ("UNKNOWN", "UNSPECIFIED"))
def test_n_canal_sem_informacao_nao_vira_pmax(canal_cego):
    cego = dict(PMAX_PAUSADA, canal=canal_cego)
    motor, persistencia, google = coletor(inventario=(cego,))
    with pytest.raises(ErroAlvoDivergente, match=canal_cego):
        motor.executar_alvo_pmax(_alvo(cego))

    assert persistencia.documentos == []
    assert google.registro.get("consultas", []) == []


# ---------------------------------------------------------------------------
# C. duas contas com o mesmo campaign_id nao colidem
# ---------------------------------------------------------------------------


def test_c_mesma_campanha_em_contas_diferentes_nao_colide():
    motor_a, persistencia_a, _ = coletor()
    motor_b, persistencia_b, _ = coletor()
    resultado_a = motor_a.executar_alvo_pmax(_alvo(PMAX_PAUSADA))
    resultado_b = motor_b.executar_alvo_pmax(_alvo(PMAX_OUTRA_CONTA))

    assert resultado_a["campaign_id"] == resultado_b["campaign_id"]
    assert resultado_a["customer_id"] != resultado_b["customer_id"]

    chaves_a = {d["chave_idempotencia"] for d in persistencia_a.enviados}
    chaves_b = {d["chave_idempotencia"] for d in persistencia_b.enviados}
    assert chaves_a and chaves_b
    assert not (chaves_a & chaves_b)
    for documento in persistencia_a.enviados:
        assert documento["customer_id"] == CONTA
    for documento in persistencia_b.enviados:
        assert documento["customer_id"] == OUTRA_CONTA


def test_c_identidade_interna_e_externa_viajam_juntas_em_toda_familia():
    motor, persistencia, _ = coletor(tipos_sinal_do_ledger=VOCABULARIO_AMPLIADO)
    motor.executar_alvo_pmax(_alvo())

    assert len(persistencia.enviados) == len(pmax.FAMILIAS_PMAX)
    for documento in persistencia.enviados:
        assert documento["campaign_id"] == CAMPANHA_PMAX
        assert documento["volc_campaign_id"] == PMAX_PAUSADA["volc_campaign_id"]
        assert documento["customer_id"] == CONTA


# ---------------------------------------------------------------------------
# D. zero metrica nao vira ausencia   ·   E. ausencia de linha nao vira zero
# ---------------------------------------------------------------------------


def test_d_zero_medido_atravessa_como_zero():
    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())

    metricas = {
        (m["recurso_externo"], m["nome"]): m
        for m in por_familia(resultado)[pmax.FAMILIA_DESEMPENHO]["metricas"]
    }
    for nome in ("impressions", "clicks", "cost_micros", "conversions"):
        medida = metricas[(GRUPO_A, nome)]
        assert medida["estado_valor"] == "medido", nome
        assert medida["valor_numerico"] is not None, nome
        assert float(medida["valor_numerico"]) == 0.0, nome


def test_e_ausencia_de_linha_nao_vira_zero():
    """O grupo B existe na estrutura e nao tem linha na janela."""

    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    desempenho = por_familia(resultado)[pmax.FAMILIA_DESEMPENHO]

    metricas = {
        (m["recurso_externo"], m["nome"]): m for m in desempenho["metricas"]
    }
    for nome in ("impressions", "clicks", "cost_micros", "conversions"):
        ausente = metricas[(GRUPO_B, nome)]
        assert ausente["estado_valor"] == "ausente", nome
        assert ausente["valor_numerico"] is None, nome
    assert GRUPO_B in desempenho["payload"]["grupos_sem_linha"]
    assert GRUPO_A not in desempenho["payload"]["grupos_sem_linha"]


def test_e_sem_estrutura_lida_nao_se_inventa_grupo_ausente():
    """Se a familia de asset groups caiu, nao ha lista de grupos conhecidos.

    Emitir `ausente` para grupos que ninguem enumerou seria afirmar a existencia
    de algo que nao foi lido.
    """

    respostas = dict(
        RESPOSTAS_COMPLETAS,
        pmax_asset_groups=ConnectionError("estrutura caiu"),
    )
    motor, _, _ = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    desempenho = por_familia(resultado)[pmax.FAMILIA_DESEMPENHO]

    assert desempenho["payload"]["grupos_conhecidos"] is None
    assert desempenho["payload"]["grupos_sem_linha"] is None
    recursos = {m["recurso_externo"] for m in desempenho["metricas"]}
    assert recursos == {GRUPO_A}


def test_d_janela_declarada_viaja_no_recibo():
    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    desempenho = por_familia(resultado)[pmax.FAMILIA_DESEMPENHO]

    assert desempenho["janela_inicio"] and desempenho["janela_fim"]
    assert desempenho["janela_inicio"] <= desempenho["janela_fim"]
    assert resultado["janela"] == [
        desempenho["janela_inicio"], desempenho["janela_fim"]
    ]


# ---------------------------------------------------------------------------
# F. consulta verde sem recomendacoes nao vira falha
# ---------------------------------------------------------------------------


def test_f_zero_recomendacoes_e_vazio_confirmado_nao_falha():
    motor, _, _ = coletor(dict(RESPOSTAS_COMPLETAS, pmax_recomendacoes=[]))
    resultado = motor.executar_alvo_pmax(_alvo())
    recomendacoes = por_familia(resultado)[pmax.FAMILIA_RECOMENDACOES]

    assert recomendacoes["estado"] == "vazio_confirmado"
    assert recomendacoes["quantidade"] == 0
    assert recomendacoes["erro_codigo"] is None


def test_f_recomendacao_de_outra_campanha_nao_conta_como_desta():
    outra = linha_recomendacao(campaign_id="99999999999")
    motor, _, _ = coletor(dict(RESPOSTAS_COMPLETAS, pmax_recomendacoes=[outra]))
    resultado = motor.executar_alvo_pmax(_alvo())
    recomendacoes = por_familia(resultado)[pmax.FAMILIA_RECOMENDACOES]

    assert recomendacoes["estado"] == "vazio_confirmado"
    assert recomendacoes["payload"]["linhas_na_conta"] == 1
    assert recomendacoes["payload"]["filtro_por_campanha"] == "local"


def test_f_campanha_pmax_ausente_torna_recomendacao_inelegivel():
    respostas = dict(RESPOSTAS_COMPLETAS, pmax_campanha=[], pmax_recomendacoes=[])
    motor, _, _ = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    recomendacoes = por_familia(resultado)[pmax.FAMILIA_RECOMENDACOES]

    assert recomendacoes["estado"] == "inelegivel"
    assert recomendacoes["quantidade"] is None


def test_f_recomendacao_e_segunda_opiniao_nunca_ordem():
    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    recomendacoes = por_familia(resultado)[pmax.FAMILIA_RECOMENDACOES]

    assert recomendacoes["estado"] == "com_dados"
    assert recomendacoes["payload"]["aplicada"] is False
    assert recomendacoes["payload"]["natureza"] == "segunda_opiniao"


# ---------------------------------------------------------------------------
# G. falha da API nao vira lista vazia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "consulta,familia",
    [
        ("pmax_campanha", pmax.FAMILIA_CAMPANHA),
        ("pmax_asset_groups", pmax.FAMILIA_ASSET_GROUPS),
        ("pmax_asset_group_assets", pmax.FAMILIA_ASSET_GROUP_ASSETS),
        ("pmax_sinais", pmax.FAMILIA_SINAIS),
        ("pmax_recomendacoes", pmax.FAMILIA_RECOMENDACOES),
    ],
)
def test_g_falha_da_api_nunca_vira_lista_vazia(consulta, familia):
    respostas = dict(RESPOSTAS_COMPLETAS)
    respostas[consulta] = ConnectionError("conexao recusada pelo transporte")
    motor, _, _ = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    caiu = por_familia(resultado)[familia]

    assert caiu["estado"] == "falhou"
    assert caiu["quantidade"] is None
    assert caiu["erro_codigo"] == "ConnectionError"


def test_g_assets_sem_prerequisito_falha_em_vez_de_fingir_vazio():
    respostas = dict(
        RESPOSTAS_COMPLETAS,
        pmax_asset_group_assets=ConnectionError("vinculos caiu"),
    )
    motor, _, google = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    assets = por_familia(resultado)[pmax.FAMILIA_ASSETS]

    assert assets["estado"] == "falhou"
    assert assets["quantidade"] is None
    assert assets["erro_codigo"] == pmax.CODIGO_PREREQUISITO
    # E nao foi buscar TODOS os assets da conta como consolo.
    assert "pmax_assets" not in [c for _, c in google.registro["consultas"]]


def test_g_sem_vinculo_lido_a_familia_de_assets_e_vazio_observado():
    motor, _, google = coletor(
        dict(RESPOSTAS_COMPLETAS, pmax_asset_group_assets=[])
    )
    resultado = motor.executar_alvo_pmax(_alvo())
    assets = por_familia(resultado)[pmax.FAMILIA_ASSETS]

    assert assets["estado"] == "vazio_confirmado"
    assert assets["quantidade"] == 0
    assert "pmax_assets" not in [c for _, c in google.registro["consultas"]]


# ---------------------------------------------------------------------------
# H. campo nao suportado nao derruba familias independentes
# ---------------------------------------------------------------------------


def test_h_performance_label_ausente_na_v25_e_nomeado_nao_inventado():
    motor, _, google = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    vinculos = por_familia(resultado)[pmax.FAMILIA_ASSET_GROUP_ASSETS]

    assert vinculos["estado"] == "com_dados"
    assert (
        "asset_group_asset.performance_label"
        in vinculos["payload"]["campos_nao_suportados"]
    )
    # Nenhuma metrica inventada com esse nome, em familia nenhuma.
    for coleta in resultado["coletas"]:
        assert not [
            m for m in coleta["metricas"] if m["nome"] == "performance_label"
        ]
    # E a consulta nao pede o campo que a v25 nao tem.
    for gaql in google.registro["gaql"]:
        assert "performance_label" not in gaql


def test_h_campo_nao_suportado_e_fato_do_sdk_instalado():
    from google.ads.googleads.v25.resources.types import asset_group_asset

    campos = set(asset_group_asset.AssetGroupAsset.meta.fields)
    for caminho in pmax.CAMPOS_NAO_SUPORTADOS_V25:
        recurso, campo = caminho.split(".", 1)
        assert recurso == "asset_group_asset"
        assert campo not in campos, f"{caminho} existe na v25: a lista mente"


def test_h_uma_familia_caida_nao_derruba_as_independentes():
    respostas = dict(RESPOSTAS_COMPLETAS)
    respostas["pmax_sinais"] = ConnectionError("sinais caiu")
    motor, _, _ = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    estado = estados(resultado)

    assert estado[pmax.FAMILIA_SINAIS] == "falhou"
    assert estado[pmax.FAMILIA_ASSET_GROUPS] == "com_dados"
    assert estado[pmax.FAMILIA_ASSET_GROUP_ASSETS] == "com_dados"
    assert estado[pmax.FAMILIA_DESEMPENHO] == "com_dados"
    assert estado[pmax.FAMILIA_RECOMENDACOES] == "com_dados"


def test_h_segmentacao_por_canal_caida_deixa_desempenho_parcial():
    respostas = dict(
        RESPOSTAS_COMPLETAS,
        pmax_desempenho_por_canal=ConnectionError("segmento recusado"),
    )
    motor, _, _ = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    desempenho = por_familia(resultado)[pmax.FAMILIA_DESEMPENHO]

    assert desempenho["estado"] == "parcial"
    assert desempenho["erro_codigo"] is None  # parcial nao e falha
    assert desempenho["payload"]["segmentacao_por_canal"]["estado"] == "falhou"
    # A metrica agregada sobreviveu ao segmento que caiu.
    assert any(m["estado_valor"] == "medido" for m in desempenho["metricas"])


def test_h_ad_strength_ausente_nao_recebe_valor():
    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    grupos = por_familia(resultado)[pmax.FAMILIA_ASSET_GROUPS]
    metricas = {
        (m["recurso_externo"], m["nome"]): m for m in grupos["metricas"]
    }

    medida = metricas[(GRUPO_A, "ad_strength")]
    assert medida["estado_valor"] == "medido"
    assert medida["valor_texto"] == "GOOD"

    ausente = metricas[(GRUPO_B, "ad_strength")]
    assert ausente["estado_valor"] == "ausente"
    assert ausente["valor_texto"] is None
    assert ausente["valor_numerico"] is None


# ---------------------------------------------------------------------------
# I. retry verde nao apaga recibo vermelho   ·   J. repetir a janela e idempotente
# ---------------------------------------------------------------------------


def test_i_falha_e_retry_verde_preservam_os_dois_recibos():
    """A familia que HOJE chega ao ledger e a que prova isso no banco real."""

    persistencia = PersistenciaDuble(INVENTARIO)

    vermelho = ClienteGoogleDuble(
        dict(RESPOSTAS_COMPLETAS, pmax_recomendacoes=ConnectionError("caiu"))
    )
    ColetorGoogleInteligencia(
        persistencia=persistencia, cliente_google=vermelho,
    ).executar_alvo_pmax(_alvo())

    verde = ClienteGoogleDuble(RESPOSTAS_COMPLETAS)
    ColetorGoogleInteligencia(
        persistencia=persistencia, cliente_google=verde,
    ).executar_alvo_pmax(_alvo())

    recibos = [
        d for d in persistencia.documentos
        if d["payload"].get("familia") == pmax.FAMILIA_RECOMENDACOES
    ]
    assert {d["estado"] for d in recibos} == {"falhou", "com_dados"}
    assert len({d["chave_idempotencia"] for d in recibos}) == 2
    vermelho_gravado = [d for d in recibos if d["estado"] == "falhou"][0]
    assert vermelho_gravado["erro_codigo"] == "ConnectionError"


def test_j_repetir_o_mesmo_alvo_e_janela_nao_duplica_fatos():
    persistencia = PersistenciaDuble(INVENTARIO)
    for _ in range(2):
        ColetorGoogleInteligencia(
            persistencia=persistencia,
            cliente_google=ClienteGoogleDuble(RESPOSTAS_COMPLETAS),
        ).executar_alvo_pmax(_alvo())

    chaves = [d["chave_idempotencia"] for d in persistencia.enviados]
    assert len(chaves) == 2 * len(
        [f for f in pmax.FAMILIAS_PMAX if pmax.recusa_de_persistencia(f) is None]
    )
    assert len(set(chaves)) == len(chaves) // 2
    assert len(persistencia.documentos) == len(set(chaves))


def test_j_familias_pmax_nao_colidem_entre_si_na_chave():
    motor, persistencia, _ = coletor()
    motor.executar_alvo_pmax(_alvo())

    chaves = [d["chave_idempotencia"] for d in persistencia.enviados]
    assert len(set(chaves)) == len(chaves)


def test_j_familia_entra_na_chave_sem_mexer_nas_chaves_antigas():
    """A chave das familias herdadas nao pode mudar por causa desta missao.

    Se mudasse, uma repeticao no mesmo bucket deixaria de deduplicar contra o
    que ja esta gravado e o banco ganharia um fato duplicado silencioso.
    """

    from volc_ads.inteligencia_google.modelo import DocumentoColeta, EstadoColeta

    base = dict(
        tipo_sinal="EXPERIMENTOS", estado=EstadoColeta.VAZIO_CONFIRMADO,
        customer_id=CONTA, login_customer_id="6016739364",
        competencia=date(2026, 8, 29),
        coletada_em=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        bucket="daily:2026-08-29", quantidade=0,
    )
    sem_familia = DocumentoColeta(**base).serializar()["chave_idempotencia"]
    # Valor congelado, calculado com o coletor v3 ANTES desta missao existir.
    assert sem_familia == (
        "d46b0c8d98505fd1d1284fa0cbbf780ed732ffe26ec4e35b6b7c9a2ca5e7f52d"
    )
    com_familia = DocumentoColeta(
        **base, familia="PMAX_SINAIS",
    ).serializar()["chave_idempotencia"]
    assert com_familia != sem_familia


# ---------------------------------------------------------------------------
# K. nenhuma query dispara mutate
# ---------------------------------------------------------------------------


def test_k_toda_consulta_pmax_e_select_read_only():
    from volc_ads.observabilidade_pmax import assert_read_only_gaql

    motor, _, google = coletor()
    motor.executar_alvo_pmax(_alvo())

    assert google.registro["gaql"]
    for gaql in google.registro["gaql"]:
        assert gaql.lstrip().upper().startswith("SELECT")
        assert_read_only_gaql(gaql)


def test_k_coleta_pmax_so_fala_com_googleadsservice():
    motor, _, google = coletor()
    motor.executar_alvo_pmax(_alvo())

    assert set(google.registro["servicos"]) == {"GoogleAdsService"}
    assert "tipos" not in google.registro
    assert "desconhecidos" not in google.registro


def test_k_modulo_pmax_nao_contem_mutacao_google():
    proibidos = (
        ".mutate_", "mutate_operation", "apply_recommendation",
        "dismiss_recommendation", "forge_permitir_escrita=1", "validate_only",
    )
    fonte = (ROOT / "volc_ads/inteligencia_google/pmax.py").read_text().lower()
    assert not [token for token in proibidos if token in fonte]


def test_k_pmax_nao_importa_agenda_nem_superficie_de_escrita():
    """Verificado na ARVORE: comentario nenhum produz import ou laco."""

    MODULOS = {
        "threading", "sched", "schedule", "apscheduler", "croniter", "crontab",
        "signal", "asyncio", "time", "multiprocessing", "subprocess",
    }
    CHAMADAS = {"sleep", "every", "enter", "enterabs", "alarm", "set_wakeup_fd"}

    arvore = ast.parse((ROOT / "volc_ads/inteligencia_google/pmax.py").read_text())
    importados, chamadas, lacos = set(), set(), 0
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
        elif isinstance(no, ast.Call):
            nome = getattr(no.func, "attr", None) or getattr(no.func, "id", None)
            if nome in CHAMADAS:
                chamadas.add(nome)
        elif isinstance(no, ast.While):
            if not (isinstance(no.test, ast.Constant) and no.test.value is False):
                lacos += 1

    assert not (importados & MODULOS)
    assert not chamadas
    assert lacos == 0


# ---------------------------------------------------------------------------
# ledger: reuso do v12 ate onde ele alcanca, e lacuna nomeada onde nao alcanca
# ---------------------------------------------------------------------------


def test_vocabulario_do_ledger_e_o_da_migration_aplicada():
    """A lista local NAO pode divergir do CHECK que esta no banco.

    Se alguem ampliar o CHECK sem atualizar aqui (ou o contrario), a coleta
    tentaria gravar um `tipo_sinal` que o Postgres recusa — ou recusaria em
    memoria algo que o banco ja aceita.
    """

    sql = MIGRATION.read_text()
    bloco = sql.split("CHECK (tipo_sinal IN (")[1].split("))")[0]
    do_banco = frozenset(re.findall(r"'([A-Z_]+)'", bloco))
    assert do_banco == pmax.TIPOS_SINAL_ACEITOS_PELO_LEDGER


def test_familia_sem_lugar_no_ledger_para_a_persistencia_e_nomeia_a_lacuna():
    motor, persistencia, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())

    recusadas = [c for c in resultado["coletas"] if not c["persistido"]]
    assert recusadas, "nenhuma familia recusada: o vocabulario mudou?"
    for coleta in recusadas:
        recusa = coleta["recusa_de_persistencia"]
        assert recusa["tipo_sinal"] == coleta["tipo_sinal"]
        assert recusa["migration_necessaria"]
        assert coleta["coleta_id"] is None
    assert resultado["lacunas"]

    # O que foi recusado NAO chegou ao banco, e o que foi aceito chegou.
    tipos_gravados = {d["tipo_sinal"] for d in persistencia.enviados}
    assert tipos_gravados <= pmax.TIPOS_SINAL_ACEITOS_PELO_LEDGER


def test_familia_com_lugar_no_ledger_e_persistida_de_verdade():
    motor, persistencia, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    recomendacoes = por_familia(resultado)[pmax.FAMILIA_RECOMENDACOES]

    assert recomendacoes["persistido"] is True
    assert recomendacoes["coleta_id"]
    assert recomendacoes["tipo_sinal"] == "RECOMENDACOES_ARMAZENADAS"
    gravado = [
        d for d in persistencia.documentos
        if d["payload"].get("familia") == pmax.FAMILIA_RECOMENDACOES
    ]
    assert len(gravado) == 1
    assert gravado[0]["campaign_id"] == CAMPANHA_PMAX


def test_ampliar_o_vocabulario_basta_para_persistir_tudo():
    """Prova de que o bloqueio e o CHECK do banco, e nao o codigo.

    Com o vocabulario ampliado — o que a migration v12_03 faria — as MESMAS
    familias atravessam sem uma linha de codigo diferente.
    """

    motor, persistencia, _ = coletor(tipos_sinal_do_ledger=VOCABULARIO_AMPLIADO)
    resultado = motor.executar_alvo_pmax(_alvo())

    assert all(c["persistido"] for c in resultado["coletas"])
    assert resultado["lacunas"] == []
    assert len(persistencia.documentos) == len(pmax.FAMILIAS_PMAX)


def test_recibo_carrega_o_contrato_minimo_da_fotografia():
    motor, persistencia, _ = coletor(tipos_sinal_do_ledger=VOCABULARIO_AMPLIADO)
    motor.executar_alvo_pmax(_alvo())

    for documento in persistencia.documentos:
        assert documento["customer_id"] and documento["login_customer_id"]
        assert documento["campaign_id"] and documento["volc_campaign_id"]
        assert documento["payload"]["familia"] in pmax.FAMILIAS_PMAX
        assert documento["coletor_versao"] > 0 and documento["api_versao"]
        assert documento["coletada_em"] and documento["bucket"]
        assert documento["chave_idempotencia"]
        assert documento["payload"]["somente_leitura"] is True
        assert documento["payload"]["fonte"] == pmax.FONTE_GOOGLE_ADS


# ---------------------------------------------------------------------------
# L. o bloqueador nao fica verde so por impressions > 0
# ---------------------------------------------------------------------------


def _fotografia(resultado, *, agora=None):
    return pmax.avaliar_prontidao_pmax(
        resultado, agora=agora or datetime.now(timezone.utc)
    )


def test_l_impressions_positivas_nao_provam_prontidao():
    respostas = dict(
        RESPOSTAS_COMPLETAS,
        pmax_asset_groups=ConnectionError("estrutura caiu"),
        pmax_asset_group_assets=ConnectionError("vinculos caiu"),
        pmax_desempenho=[linha_desempenho_grupo(GRUPO_A, impressoes=4210)],
    )
    motor, _, _ = coletor(respostas)
    resultado = motor.executar_alvo_pmax(_alvo())
    prontidao = _fotografia(resultado)

    assert prontidao.provada is False
    assert pmax.FAMILIA_ASSET_GROUPS in prontidao.faltando


def test_l_familia_lida_mas_nao_persistida_nao_prova_prontidao():
    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    prontidao = _fotografia(resultado)

    assert all(
        c["estado"] in ("com_dados", "vazio_confirmado")
        for c in resultado["coletas"]
    )
    assert prontidao.provada is False
    assert any("nao persistida" in motivo for motivo in prontidao.motivos)


def test_l_fotografia_completa_e_recente_prova_prontidao():
    motor, _, _ = coletor(tipos_sinal_do_ledger=VOCABULARIO_AMPLIADO)
    resultado = motor.executar_alvo_pmax(_alvo())

    assert _fotografia(resultado).provada is True


def test_l_fotografia_velha_deixa_de_provar():
    motor, _, _ = coletor(tipos_sinal_do_ledger=VOCABULARIO_AMPLIADO)
    resultado = motor.executar_alvo_pmax(_alvo())
    futuro = datetime.now(timezone.utc) + timedelta(days=3)

    velha = pmax.avaliar_prontidao_pmax(resultado, agora=futuro)
    assert velha.provada is False
    assert any("frescor" in motivo for motivo in velha.motivos)


def test_l_familia_ausente_da_fotografia_nao_e_familia_verde():
    motor, _, _ = coletor(tipos_sinal_do_ledger=VOCABULARIO_AMPLIADO)
    resultado = motor.executar_alvo_pmax(_alvo())
    resultado["coletas"] = [
        c for c in resultado["coletas"] if c["familia"] != pmax.FAMILIA_SINAIS
    ]

    prontidao = _fotografia(resultado)
    assert prontidao.provada is False
    assert pmax.FAMILIA_SINAIS in prontidao.faltando


# ---------------------------------------------------------------------------
# M. asset group sem performance_label nao recebe valor inventado
#     (o campo nao existe na v25; ver test_h_* acima)
# ---------------------------------------------------------------------------


def test_m_asset_sem_metadado_nao_ganha_qualidade_inferida():
    """Nao baixamos midia e nao julgamos o que nao foi lido."""

    motor, _, google = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    assets = por_familia(resultado)[pmax.FAMILIA_ASSETS]

    assert assets["estado"] == "com_dados"
    for item in assets["itens"]:
        assert "qualidade" not in item["payload"]
        assert "score" not in item["payload"]
        assert "avaliacao" not in item["payload"]

    # E o modulo nao tem como baixar midia: nao ha cliente HTTP nele.
    arvore = ast.parse((ROOT / "volc_ads/inteligencia_google/pmax.py").read_text())
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
    assert not (importados & {"urllib", "http", "requests", "httpx", "socket"})


# ---------------------------------------------------------------------------
# CLI one-shot: identidade completa, saida sanitizada, saida != 0 no erro
# ---------------------------------------------------------------------------


def _cli(*argumentos):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/coletar_google_inteligencia.py"),
         *argumentos],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def test_cli_pmax_exige_a_identidade_completa():
    parcial = _cli("--pmax", "--campaign-id", CAMPANHA_PMAX)
    assert parcial.returncode != 0
    assert "identidade" in (parcial.stderr + parcial.stdout).lower()

    sem_nada = _cli("--pmax")
    assert sem_nada.returncode != 0


def test_cli_pmax_aparece_na_ajuda_e_nao_ganhou_agenda():
    ajuda = _cli("--help")
    assert ajuda.returncode == 0
    assert "--pmax" in ajuda.stdout
    for bandeira in ("--intervalo", "--repetir", "--loop", "--daemon", "--watch"):
        assert bandeira not in ajuda.stdout


def test_cli_nao_imprime_credencial_nem_dado_pessoal():
    cli = (ROOT / "scripts/coletar_google_inteligencia.py").read_text()
    for token in (
        "SUPABASE_SERVICE_ROLE_KEY", "developer_token", "refresh_token",
        "client_secret", "Authorization",
    ):
        assert token not in cli


def _modulo_cli():
    import importlib.util

    caminho = ROOT / "scripts/coletar_google_inteligencia.py"
    spec = importlib.util.spec_from_file_location("volc_cli_coleta", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_cli_canal_incompativel_sai_diferente_de_zero(monkeypatch, capsys):
    """Canal errado vira codigo de saida, nao stacktrace nem sucesso mudo."""

    cli = _modulo_cli()

    def recusar(**_):
        raise pmax.ErroCanalNaoPMax("canal SEARCH nao e PERFORMANCE_MAX")

    monkeypatch.setattr(cli, "executar_coleta_pmax", recusar)
    codigo = cli.main([
        "--pmax", "--customer-id", CONTA,
        "--volc-campaign-id", PMAX_PAUSADA["volc_campaign_id"],
        "--campaign-id", CAMPANHA_PMAX,
    ])
    assert codigo != 0
    assert "PERFORMANCE_MAX" in capsys.readouterr().err


def test_cli_falha_de_api_sai_diferente_de_zero(monkeypatch, capsys):
    cli = _modulo_cli()

    def cair(**_):
        raise ConnectionError("transporte recusou a conexao")

    monkeypatch.setattr(cli, "executar_coleta_pmax", cair)
    codigo = cli.main([
        "--pmax", "--customer-id", CONTA,
        "--volc-campaign-id", PMAX_PAUSADA["volc_campaign_id"],
        "--campaign-id", CAMPANHA_PMAX,
    ])
    assert codigo != 0
    assert capsys.readouterr().err.strip()


def test_cli_imprime_resumo_sanitizado_sem_payload(monkeypatch, capsys):
    """O resumo diz o estado de cada familia, e nao vaza item nem metrica."""

    import json

    motor, _, _ = coletor()
    resultado = motor.executar_alvo_pmax(_alvo())
    cli = _modulo_cli()
    monkeypatch.setattr(cli, "executar_coleta_pmax", lambda **_: resultado)

    assert cli.main([
        "--pmax", "--customer-id", CONTA,
        "--volc-campaign-id", PMAX_PAUSADA["volc_campaign_id"],
        "--campaign-id", CAMPANHA_PMAX,
    ]) == 0
    saida = capsys.readouterr().out
    impresso = json.loads(saida)

    assert {c["familia"] for c in impresso["coletas"]} == set(pmax.FAMILIAS_PMAX)
    for coleta in impresso["coletas"]:
        assert "itens" not in coleta
        assert "metricas" not in coleta
        assert "payload" not in coleta
    # Nenhum texto de anuncio, nome de campanha ou URL final atravessou.
    assert "Credito com desconto" not in saida
    assert "exemplo.com.br" not in saida
    assert PMAX_PAUSADA["nome"] not in saida
