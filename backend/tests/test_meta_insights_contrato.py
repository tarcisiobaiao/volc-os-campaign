"""Contraprovas do contrato de Insights Meta (T05 / F08 / F09).

Cada teste aqui nasceu vermelho contra o comportamento anterior: LPV somava
ViewContent, action ausente virava zero, o pedido nao carregava incremento nem
janela, o "hoje" vinha do host e um `campaign_id` ausente virava o id da conta.
Todos exercitam a fronteira HTTP por `MockTransport` — nenhum toca a rede.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.credenciais import SegredoEfemero

TOKEN = "token-de-teste-que-nunca-vai-para-a-url"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _pedido(**kwargs) -> dom.PedidoDeInsights:
    base = dict(
        conta_externa="123456789012",
        nivel="campaign",
        periodo_inicio=date(2026, 9, 1),
        periodo_fim=date(2026, 9, 2),
        fuso_da_conta="America/Sao_Paulo",
    )
    base.update(kwargs)
    return dom.PedidoDeInsights(**base)


def _transporte(linhas: list[dict], capturadas: list[httpx.Request] | None = None):
    def responder(req: httpx.Request) -> httpx.Response:
        if capturadas is not None:
            capturadas.append(req)
        return httpx.Response(200, json={"data": linhas})
    return httpx.MockTransport(responder)


async def _ler(linhas: list[dict], pedido=None, capturadas=None):
    async with httpx.AsyncClient(transport=_transporte(linhas, capturadas)) as cliente:
        return await AdaptadorMetaSomenteLeitura(cliente).ler_insights(
            pedido or _pedido(), SegredoEfemero(TOKEN))


# ---------------------------------------------------------------------------
# F09 — LPV nao e ViewContent, e ausencia nao e zero
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_lpv_ignora_view_content_e_nao_soma_os_dois():
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "actions": [
            {"action_type": "landing_page_view", "value": "4"},
            {"action_type": "offsite_conversion.fb_pixel_view_content", "value": "7"},
        ],
    }])
    fato = resultado.insights[0]
    assert fato.landing_page_views == 4, "ViewContent nao pode entrar no LPV"
    # ViewContent continua existindo como action propria, so nao vira LPV.
    tipos = {a.action_type for a in fato.actions}
    assert dom.ACTION_TYPE_VIEW_CONTENT in tipos


@pytest.mark.anyio
async def test_lpv_presente_sem_valor_medido_fica_nulo():
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "actions": [{"action_type": "landing_page_view", "value": None}],
    }])
    assert resultado.insights[0].landing_page_views is None


@pytest.mark.anyio
async def test_lpv_zero_medido_continua_zero():
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "actions": [{"action_type": "landing_page_view", "value": "0"}],
    }])
    assert resultado.insights[0].landing_page_views == 0


@pytest.mark.anyio
async def test_lpv_ausente_e_nulo_nao_zero():
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "actions": [{"action_type": "link_click", "value": "9"}],
    }])
    assert resultado.insights[0].landing_page_views is None


# ---------------------------------------------------------------------------
# F08 — o pedido e tipado, viaja no fio e volta carimbado com honestidade
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_request_serializado_carrega_incremento_diario_instante_e_janelas():
    capturadas: list[httpx.Request] = []
    pedido = _pedido(janelas_de_atribuicao=("7d_click", "1d_view"),
                     action_report_time="conversion")
    await _ler([], pedido=pedido, capturadas=capturadas)
    params = parse_qs(capturadas[0].url.query.decode())
    assert params["time_increment"] == ["1"]
    assert params["action_report_time"] == ["conversion"]
    assert json.loads(params["action_attribution_windows"][0]) == ["7d_click", "1d_view"]
    assert json.loads(params["time_range"][0]) == {
        "since": "2026-09-01", "until": "2026-09-02"}
    assert "action_values" in params["fields"][0]
    # O segredo nunca vai na URL.
    assert TOKEN not in str(capturadas[0].url)
    assert capturadas[0].headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.anyio
async def test_janela_nao_solicitada_nunca_e_carimbada():
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "spend": "10",
    }])
    fato = resultado.insights[0]
    assert fato.janela_atribuicao == dom.JANELA_PADRAO_DA_CONTA
    assert fato.janelas_solicitadas == ()


def test_tipo_recusa_carimbo_de_janela_que_nao_foi_pedida():
    with pytest.raises(dom.ContratoMetaInvalido, match="janela_atribuicao"):
        dom.InsightMeta(
            provider="META_ADS", conta_externa="123", nivel="campaign",
            objeto_externo="555", periodo_inicio=date(2026, 9, 1),
            periodo_fim=date(2026, 9, 1), janela_atribuicao="7d_click",
            breakdown="none", observado_em=datetime.now(timezone.utc))


@pytest.mark.anyio
async def test_actions_com_janelas_distintas_nao_sao_achatadas():
    pedido = _pedido(janelas_de_atribuicao=("1d_click", "7d_click"))
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "actions": [{"action_type": "lead", "1d_click": "3", "7d_click": "5"}],
    }], pedido=pedido)
    acoes = resultado.insights[0].actions
    por_janela = {a.attribution_window: a.value for a in acoes}
    assert por_janela == {"1d_click": Decimal("3"), "7d_click": Decimal("5")}
    assert len(acoes) == 2, "cada janela e uma linha; somar as duas inventa evento"


@pytest.mark.anyio
async def test_action_values_ficam_separados_de_actions():
    resultado = await _ler([{
        "campaign_id": "555", "date_start": "2026-09-01", "date_stop": "2026-09-01",
        "actions": [{"action_type": "purchase", "value": "2"}],
        "action_values": [{"action_type": "purchase", "value": "199.90"}],
    }])
    fato = resultado.insights[0]
    assert [a.medida for a in fato.actions] == ["count"]
    assert [a.medida for a in fato.action_values] == ["value"]
    assert fato.actions[0].value == Decimal("2")
    assert fato.action_values[0].value == Decimal("199.90")


# ---------------------------------------------------------------------------
# F08 — nivel pedido e nivel respondido precisam coincidir
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_falta_campaign_id_no_nivel_campaign_nao_vira_id_da_conta():
    with pytest.raises(ErroDeLeituraMeta) as erro:
        await _ler([{
            "account_id": "123456789012",
            "date_start": "2026-09-01", "date_stop": "2026-09-01", "spend": "42",
        }])
    assert erro.value.codigo == "META_INSIGHT_LEVEL_MISMATCH"


@pytest.mark.anyio
async def test_nivel_account_usa_account_id_normalmente():
    resultado = await _ler([{
        "account_id": "123456789012",
        "date_start": "2026-09-01", "date_stop": "2026-09-01", "spend": "42",
    }], pedido=_pedido(nivel="account"))
    assert resultado.insights[0].objeto_externo == "123456789012"


# ---------------------------------------------------------------------------
# Fuso da conta, allowlist, teto de periodo e completude
# ---------------------------------------------------------------------------

def test_hoje_e_o_da_conta_e_nao_o_do_host():
    # 02:30Z de 05/09 ainda e 04/09 em Sao Paulo.
    agora = datetime(2026, 9, 5, 2, 30, tzinfo=timezone.utc)
    assert dom.hoje_na_conta("America/Sao_Paulo", agora=agora) == date(2026, 9, 4)
    assert dom.hoje_na_conta("UTC", agora=agora) == date(2026, 9, 5)


def test_periodo_sem_fuso_da_conta_e_recusado():
    with pytest.raises(dom.ContratoMetaInvalido, match="fuso"):
        dom.hoje_na_conta(None)


def test_combinacao_fora_da_allowlist_e_recusada_antes_da_chamada():
    with pytest.raises(dom.CombinacaoDeInsightRecusada):
        _pedido(breakdown="hourly_stats_aggregated_by_advertiser_time_zone")
    with pytest.raises(dom.CombinacaoDeInsightRecusada):
        _pedido(nivel="account", breakdown="region")
    with pytest.raises(dom.CombinacaoDeInsightRecusada):
        _pedido(janelas_de_atribuicao=("30d_click",))


def test_periodo_grande_demais_falha_com_mensagem_util():
    with pytest.raises(dom.ContratoMetaInvalido, match="excede o teto local"):
        _pedido(periodo_inicio=date(2020, 1, 1), periodo_fim=date(2026, 9, 7))


@pytest.mark.anyio
async def test_pagina_truncada_marca_janela_incompleta_em_vez_de_mentir():
    def responder(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": [{"campaign_id": "555", "date_start": "2026-09-01",
                      "date_stop": "2026-09-01", "spend": "1"}],
            "paging": {"next": "https://graph.facebook.com/proxima",
                       "cursors": {"after": f"cursor-{req.url.params.get('after', '0')}x"}},
        })
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        adaptador = AdaptadorMetaSomenteLeitura(cliente, max_paginas_por_edge=3)
        resultado = await adaptador.ler_insights(_pedido(), SegredoEfemero(TOKEN))
    assert resultado.completo is False
    assert resultado.motivo_incompleto == "META_PAGINATION_LIMIT"
    assert resultado.paginas_lidas == 3
    assert len(resultado.insights) == 3, "as linhas ja lidas sao preservadas"


def test_metricas_nao_aditivas_estao_declaradas():
    assert "reach" in dom.METRICAS_NAO_ADITIVAS
    assert "frequency" in dom.METRICAS_NAO_ADITIVAS
    assert "spend" in dom.METRICAS_ADITIVAS
    assert not set(dom.METRICAS_NAO_ADITIVAS) & set(dom.METRICAS_ADITIVAS)
