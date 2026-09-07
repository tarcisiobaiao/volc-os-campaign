"""Contraprovas do contrato de leitura escopada Meta (T07 / F06 / F07 / F10).

Antes desta rodada, `listar` aplicava o filtro de conta apenas a campanhas,
criativos e insights: pedir os CONJUNTOS da conta A devolvia tambem os da conta
B, porque o parametro era simplesmente descartado. `detalhe` nao recebia conta
nenhuma — um id era a propria autorizacao. E `limit: 500` sem cursor se
apresentava como inventario completo.

O duble de Supabase abaixo fala PostgREST de verdade (eq/in/gt/order/limit),
entao o escopo e a paginacao sao exercitados como o backend os emite, sem rede
e sem banco.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.trafego.meta import dominio as dom
from app.trafego.meta.read_model import RepositorioMetaReadModelSupabase

CONTA_A = "100000000001"
CONTA_B = "200000000002"
REF_A = dom.referencia_opaca_conta(CONTA_A)
REF_B = dom.referencia_opaca_conta(CONTA_B)
ATIVO_A = f"meta_account_{REF_A}"
ATIVO_B = f"meta_account_{REF_B}"


class SupabaseFalso:
    """PostgREST o bastante para provar escopo e paginacao."""

    def __init__(self, tabelas: dict[str, list[dict[str, Any]]], *,
                 ausentes: set[str] | None = None) -> None:
        self.enabled = True
        self.tabelas = tabelas
        self.ausentes = ausentes or set()
        self.consultas: list[tuple[str, dict[str, Any]]] = []

    async def select(self, tabela: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.consultas.append((tabela, dict(params)))
        if tabela in self.ausentes or tabela not in self.tabelas:
            pedido = httpx.Request("GET", f"https://exemplo.invalido/{tabela}")
            raise httpx.HTTPStatusError(
                "not found", request=pedido,
                response=httpx.Response(404, request=pedido))
        linhas = [dict(r) for r in self.tabelas[tabela]]
        for chave, bruto in params.items():
            if chave in {"select", "order", "limit", "offset"}:
                continue
            valor = str(bruto)
            if valor.startswith("eq."):
                alvo = valor[3:]
                linhas = [r for r in linhas if str(r.get(chave)) == alvo]
            elif valor.startswith("in.("):
                permitidos = set(valor[4:-1].split(","))
                linhas = [r for r in linhas if str(r.get(chave)) in permitidos]
            elif valor.startswith("gt."):
                alvo = valor[3:]
                linhas = [r for r in linhas if str(r.get(chave)) > alvo]
            else:  # pragma: no cover - o backend so emite os tres acima
                raise AssertionError(f"operador PostgREST nao suportado: {valor}")
        ordem = params.get("order")
        if ordem:
            coluna, _, direcao = str(ordem).partition(".")
            linhas.sort(key=lambda r: str(r.get(coluna) or ""),
                        reverse=direcao == "desc")
        limite = params.get("limit")
        if limite is not None:
            linhas = linhas[: int(limite)]
        return linhas


def _contas() -> list[dict[str, Any]]:
    return [
        {"cofre_ativo_id": ATIVO_A, "account_external_id": CONTA_A,
         "nome_observado": "Conta A", "moeda": "BRL",
         "timezone_name": "America/Sao_Paulo", "account_status": "1",
         "readiness_state": "READY_FOR_READ", "observado_em": "2026-09-06T10:00:00Z",
         "ultima_leitura_ok_em": "2026-09-06T10:00:00Z"},
        {"cofre_ativo_id": ATIVO_B, "account_external_id": CONTA_B,
         "nome_observado": "Conta B", "moeda": "USD",
         "timezone_name": "UTC", "account_status": "1",
         "readiness_state": "READY_FOR_READ", "observado_em": "2026-09-06T10:00:00Z",
         "ultima_leitura_ok_em": "2026-09-06T10:00:00Z"},
    ]


def _base() -> dict[str, list[dict[str, Any]]]:
    """Duas contas com filhos homonimos e o MESMO observado_em em tudo."""
    obs = "2026-09-06T10:00:00Z"
    camp = [
        {"meta_campaign_id": "c-a-1", "ad_account_ativo_id": ATIVO_A,
         "external_id": "11", "nome": "Descoberta", "status": "PAUSED",
         "observado_em": obs},
        {"meta_campaign_id": "c-a-2", "ad_account_ativo_id": ATIVO_A,
         "external_id": "12", "nome": "Retorno", "status": "PAUSED",
         "observado_em": obs},
        {"meta_campaign_id": "c-b-1", "ad_account_ativo_id": ATIVO_B,
         "external_id": "21", "nome": "Descoberta", "status": "ACTIVE",
         "observado_em": obs},
    ]
    conj = [
        {"meta_adset_id": "s-a-1", "meta_campaign_id": "c-a-1",
         "external_id": "31", "nome": "Amplo", "observado_em": obs},
        {"meta_adset_id": "s-b-1", "meta_campaign_id": "c-b-1",
         "external_id": "41", "nome": "Amplo", "observado_em": obs},
    ]
    anun = [
        {"meta_ad_id": "d-a-1", "meta_adset_id": "s-a-1",
         "external_id": "51", "nome": "Peca A", "observado_em": obs},
        {"meta_ad_id": "d-b-1", "meta_adset_id": "s-b-1",
         "external_id": "61", "nome": "Peca B", "observado_em": obs},
    ]
    return {
        "trafego_meta_ad_account": _contas(),
        "trafego_meta_campaign": camp,
        "trafego_meta_adset": conj,
        "trafego_meta_ad": anun,
        "trafego_meta_creative": [],
        "vw_trafego_meta_insight_latest": [
            {"meta_insight_daily_id": "i-a-1", "ad_account_ativo_id": ATIVO_A,
             "nivel": "campaign", "spend": "10.00", "observado_em": obs},
            {"meta_insight_daily_id": "i-b-1", "ad_account_ativo_id": ATIVO_B,
             "nivel": "campaign", "spend": "99.00", "observado_em": obs},
        ],
        "trafego_meta_sync_run": [],
    }


def repo(tabelas=None, ausentes=None) -> tuple[RepositorioMetaReadModelSupabase, SupabaseFalso]:
    supa = SupabaseFalso(tabelas if tabelas is not None else _base(), ausentes=ausentes)
    return RepositorioMetaReadModelSupabase(supa), supa


# ---------------------------------------------------------------------------
# F07 — o filtro de conta chega a conjuntos, anuncios e mensuracao
# ---------------------------------------------------------------------------

def test_conjuntos_da_conta_a_nao_trazem_os_da_conta_b():
    r, _ = repo()
    saida = asyncio.run(r.listar("conjuntos", REF_A))
    assert [i["meta_adset_id"] for i in saida["items"]] == ["s-a-1"]


def test_anuncios_respeitam_o_escopo_por_dois_niveis_de_pai():
    r, _ = repo()
    saida = asyncio.run(r.listar("anuncios", REF_A))
    assert [i["meta_ad_id"] for i in saida["items"]] == ["d-a-1"]
    saida_b = asyncio.run(r.listar("anuncios", REF_B))
    assert [i["meta_ad_id"] for i in saida_b["items"]] == ["d-b-1"]


def test_campanhas_homonimas_nao_vazam_entre_contas():
    r, _ = repo()
    a = asyncio.run(r.listar("campanhas", REF_A))
    b = asyncio.run(r.listar("campanhas", REF_B))
    assert {i["nome"] for i in a["items"]} == {"Descoberta", "Retorno"}
    assert {i["meta_campaign_id"] for i in b["items"]} == {"c-b-1"}
    assert not {i["meta_campaign_id"] for i in a["items"]} & \
        {i["meta_campaign_id"] for i in b["items"]}


def test_entidade_que_exige_conta_recusa_pedido_sem_escopo():
    r, _ = repo()
    saida = asyncio.run(r.listar("conjuntos"))
    assert saida["estado"] == "ESCOPO_OBRIGATORIO"
    assert saida["items"] == []


def test_handle_de_conta_desconhecido_vira_escopo_vazio_e_nao_conta_inteira():
    r, _ = repo()
    saida = asyncio.run(r.listar("campanhas", "metaacct_inexistente0000000000"))
    assert saida["estado"] == "ESCOPO_DESCONHECIDO"
    assert saida["items"] == []


# ---------------------------------------------------------------------------
# F07 — detalhe exige escopo; um id nao e autorizacao
# ---------------------------------------------------------------------------

def test_detalhe_de_objeto_de_outra_conta_e_recusado():
    r, _ = repo()
    saida = asyncio.run(r.detalhe("campanhas", "c-b-1", REF_A))
    assert saida["item"] is None
    assert saida["estado"] == "NAO_ENCONTRADO_NO_ESCOPO"


def test_detalhe_sem_conta_e_recusado():
    r, _ = repo()
    saida = asyncio.run(r.detalhe("campanhas", "c-a-1"))
    assert saida["estado"] == "ESCOPO_OBRIGATORIO"
    assert saida["item"] is None


def test_detalhe_dentro_do_escopo_resolve():
    r, _ = repo()
    saida = asyncio.run(r.detalhe("campanhas", "c-a-1", REF_A))
    assert saida["item"]["meta_campaign_id"] == "c-a-1"


# ---------------------------------------------------------------------------
# F10 — uma identidade publica que liga nascimento e persistencia
# ---------------------------------------------------------------------------

def test_entity_ref_do_recibo_resolve_o_detalhe_persistido():
    # O executor entrega ao operador exatamente esta referencia no nascimento.
    do_recibo = dom.referencia_opaca_objeto(CONTA_A, "campaign", "11")
    r, _ = repo()
    saida = asyncio.run(r.detalhe("campanhas", do_recibo, REF_A))
    assert saida["item"]["meta_campaign_id"] == "c-a-1"
    assert saida["item"]["entity_ref"] == do_recibo


def test_id_bruto_da_meta_nunca_sai_na_resposta():
    r, _ = repo()
    saida = asyncio.run(r.listar("campanhas", REF_A))
    for item in saida["items"]:
        assert "external_id" not in item
        assert item["id_mascarado"].startswith("••••")
        assert item["entity_ref"].startswith("metaobj_")


# ---------------------------------------------------------------------------
# F07 — paginacao com ordem total, cursor opaco e completude honesta
# ---------------------------------------------------------------------------

def test_paginacao_percorre_tudo_mesmo_com_observado_em_identico():
    obs = "2026-09-06T10:00:00Z"
    tabelas = _base()
    tabelas["trafego_meta_campaign"] = [
        {"meta_campaign_id": f"c-a-{i:03d}", "ad_account_ativo_id": ATIVO_A,
         "external_id": str(1000 + i), "nome": f"C{i}", "observado_em": obs}
        for i in range(250)
    ]
    r, _ = repo(tabelas)
    vistos: list[str] = []
    cursor = None
    paginas = 0
    while True:
        saida = asyncio.run(r.listar("campanhas", REF_A, cursor=cursor, tamanho=100))
        vistos += [i["meta_campaign_id"] for i in saida["items"]]
        paginas += 1
        if not saida["has_more"]:
            assert saida["completo"] is True
            break
        cursor = saida["proximo_cursor"]
        assert cursor
    assert paginas == 3
    assert len(vistos) == 250, "a varredura nao pode perder linhas"
    assert len(set(vistos)) == 250, "nem repetir linhas"


def test_pagina_com_has_more_nunca_se_declara_completa():
    tabelas = _base()
    tabelas["trafego_meta_campaign"] = [
        {"meta_campaign_id": f"c-a-{i:03d}", "ad_account_ativo_id": ATIVO_A,
         "external_id": str(1000 + i), "observado_em": "2026-09-06T10:00:00Z"}
        for i in range(10)
    ]
    r, _ = repo(tabelas)
    saida = asyncio.run(r.listar("campanhas", REF_A, tamanho=3))
    assert saida["has_more"] is True
    assert saida["completo"] is False
    assert len(saida["items"]) == 3


def test_cursor_invalido_e_recusado_com_tipo():
    r, _ = repo()
    with pytest.raises(dom.ContratoMetaInvalido):
        asyncio.run(r.listar("campanhas", REF_A, cursor="nao-e-cursor!!"))


# ---------------------------------------------------------------------------
# F06 — ausencia de schema/conexao e estado distinto de vazio
# ---------------------------------------------------------------------------

def test_schema_ausente_e_estado_distinto_de_inventario_vazio():
    r, _ = repo(ausentes={"trafego_meta_campaign"})
    saida = asyncio.run(r.listar("campanhas", REF_A))
    assert saida["estado"] == "SCHEMA_NAO_APLICADO"
    assert saida["has_snapshot"] is False

    tabelas = _base()
    tabelas["trafego_meta_campaign"] = []
    r2, _ = repo(tabelas)
    vazio = asyncio.run(r2.listar("campanhas", REF_A))
    assert vazio["estado"] == "SEM_SNAPSHOT"
    assert vazio["estado"] != saida["estado"]


def test_supabase_desligado_e_estado_proprio():
    r, supa = repo()
    supa.enabled = False
    saida = asyncio.run(r.listar("campanhas", REF_A))
    assert saida["estado"] == "SEM_CONEXAO"


def test_recibo_preserva_o_estado_do_read_model():
    r, _ = repo(ausentes={"trafego_meta_sync_run"})
    saida = asyncio.run(r.ultimo_recibo())
    assert saida["estado"] == "SCHEMA_NAO_APLICADO"
    assert saida["recibo"] is None


# ---------------------------------------------------------------------------
# Insights: a leitura usa a projecao `latest`, nunca a tabela crua
# ---------------------------------------------------------------------------

def test_insights_leem_a_projecao_latest_e_nao_a_tabela_crua():
    r, supa = repo()
    saida = asyncio.run(r.listar("insights", REF_A))
    tabelas_consultadas = {t for t, _ in supa.consultas}
    assert "vw_trafego_meta_insight_latest" in tabelas_consultadas
    assert "trafego_meta_insight_daily" not in tabelas_consultadas
    assert [i["meta_insight_daily_id"] for i in saida["items"]] == ["i-a-1"]


def test_moeda_fuso_e_frescor_acompanham_a_pagina():
    r, _ = repo()
    saida = asyncio.run(r.listar("campanhas", REF_A))
    assert saida["moeda"] == "BRL"
    assert saida["fuso"] == "America/Sao_Paulo"
    assert saida["frescor"] == "2026-09-06T10:00:00Z"


# ---------------------------------------------------------------------------
# Recibo por conta, id bruto que nao vaza, snapshot e idempotencia
# ---------------------------------------------------------------------------

def test_ultimo_recibo_nao_devolve_o_da_outra_conta():
    tabelas = _base()
    tabelas["trafego_meta_sync_run"] = [
        {"run_id": "run-a", "ad_account_ativo_id": ATIVO_A, "resultado": "ok",
         "concluido_em": "2026-09-06T09:00:00Z", "paginas_lidas": 4,
         "contagens": {}, "snapshot_hash": "meta_snapshot_a",
         "escrita_executada": True, "erro_codigo": None, "erro_mensagem": None},
        {"run_id": "run-b", "ad_account_ativo_id": ATIVO_B, "resultado": "ok",
         "concluido_em": "2026-09-06T23:00:00Z", "paginas_lidas": 4,
         "contagens": {}, "snapshot_hash": "meta_snapshot_b",
         "escrita_executada": True, "erro_codigo": None, "erro_mensagem": None},
    ]
    r, _ = repo(tabelas)
    # Sem escopo, o mais recente e o da conta B.
    assert asyncio.run(r.ultimo_recibo())["recibo"]["run_id"] == "run-b"
    # Com escopo, cada conta le o seu.
    assert asyncio.run(r.ultimo_recibo(REF_A))["recibo"]["run_id"] == "run-a"
    assert asyncio.run(r.ultimo_recibo(REF_B))["recibo"]["run_id"] == "run-b"


def test_object_story_id_nao_atravessa_a_fronteira_do_navegador():
    # `<page_id>_<post_id>` e identificador bruto da Meta e nao termina em
    # `external_id`, entao a regra de sufixo sozinha nao o alcancava.
    tabelas = _base()
    tabelas["trafego_meta_creative"] = [{
        "meta_creative_id": "cr-a-1", "ad_account_ativo_id": ATIVO_A,
        "external_id": "71", "nome": "Peca",
        "object_story_id": "123456789_987654321",
        "observado_em": "2026-09-06T10:00:00Z",
    }]
    r, _ = repo(tabelas)
    saida = asyncio.run(r.listar("criativos", REF_A))
    item = saida["items"][0]
    assert "object_story_id" not in item
    assert "123456789_987654321" not in str(item)
    assert item["entity_ref"].startswith("metaobj_")
