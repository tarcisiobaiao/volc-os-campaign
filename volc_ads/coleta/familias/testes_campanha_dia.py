from __future__ import annotations

import dataclasses
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from google.ads.googleads.v25.enums.types.advertising_channel_type import AdvertisingChannelTypeEnum
from google.ads.googleads.v25.enums.types.campaign_status import CampaignStatusEnum
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta import executor
from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias.campanha_dia import EXTRAS, FAMILIA, METRICAS, TAXAS
from volc_ads.gads import catalogo

RAIZ = Path(__file__).resolve().parents[3]
CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL")

# Valores lidos da Crédito Up em 07/10/2026 (campanha Senac).
COMPLETA = dict(
    impressions=861, clicks=66, interactions=66, cost_micros=59_660_000,
    conversions=30.0, all_conversions=42.0, conversions_value=300.0, all_conversions_value=420.0,
    ctr=0.0766, average_cpc=903939.39, cost_per_conversion=1988666.67,
    search_impression_share=0.0999, search_budget_lost_impression_share=0.092,
    search_rank_lost_impression_share=0.831, search_top_impression_share=0.0999,
    search_absolute_top_impression_share=0.0999, search_click_share=0.05,
    search_exact_match_impression_share=0.148, top_impression_percentage=0.395,
    absolute_top_impression_percentage=0.114, invalid_clicks=3, invalid_click_rate=0.0435,
)


def _row(campaign_id: int = 24278665189, data: str = "2026-10-07", cliente: int = 5478096539,
         **metricas) -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.customer.id = cliente
    r.campaign.id = campaign_id
    r.campaign.name = "VOLC-SENAC"
    r.campaign.status = CampaignStatusEnum.CampaignStatus.ENABLED
    r.campaign.advertising_channel_type = AdvertisingChannelTypeEnum.AdvertisingChannelType.SEARCH
    r.segments.date = data
    for campo, valor in metricas.items():
        setattr(r.metrics, campo, valor)
    return r


# ── o que a função SQL da v12_04 lê, extraído da própria migration ──────────

def _corpo_rpc() -> str:
    sql = (RAIZ / "supabase/migrations/v12_04_gads_fato_canonico_dia.sql").read_text(encoding="utf-8")
    ini = sql.index("CREATE OR REPLACE FUNCTION public.volc_registrar_gads_campanha_dia")
    return sql[ini:sql.index("$$;", ini)]


def _chaves(trecho: str, alvo: str) -> set[str]:
    return set(re.findall(alvo + r"\s*->>?\s*'([a-z_0-9]+)'", trecho))


def chaves_documento_rpc() -> set[str]:
    """Chaves de `documento` que o ramo `contas` lê (as do fechamento ficam de fora)."""
    corpo = _corpo_rpc()
    ini = corpo.index("ELSIF v_tipo = 'fechamento'")
    fim = corpo.index("TIPO_LOTE_INVALIDO")
    return _chaves(corpo[:ini] + corpo[fim:], "documento")


def chaves_fechamento_rpc() -> set[str]:
    """Chaves que o ramo `fechamento` lê; `projetar_compat` só vale no lote."""
    corpo = _corpo_rpc()
    ini = corpo.index("ELSIF v_tipo = 'fechamento'")
    fim = corpo.index("TIPO_LOTE_INVALIDO")
    return (chaves_documento_rpc() - {"projetar_compat"}) | _chaves(corpo[ini:fim], "documento")


def chaves_linha_rpc() -> set[str]:
    corpo = _corpo_rpc()
    chaves = _chaves(corpo, "v_linha") | _chaves(corpo, r"\bx")
    m = re.search(r"WHERE k IN \((.*?)\)", corpo, re.S)
    chaves |= set(re.findall(r"'([a-z_0-9]+)'", m.group(1)))
    return chaves


def teste_extrator_le_a_funcao_de_verdade():
    doc, linha = chaves_documento_rpc(), chaves_linha_rpc()
    assert {"chave_idempotencia", "tipo_lote", "duracao_ms", "projetar_compat", "linhas"} <= doc
    assert "linhas_aceitas" not in doc  # só o fechamento declara contagem
    assert {"customer_id", "segmentos", "metricas_extras", "absolute_top_impression_percentage"} <= linha
    assert len(linha) == 31


# ── validações da RPC e da tabela, em Python ────────────────────────────────

def violacoes_documento(doc: dict) -> list[str]:
    e = []
    if not (doc.get("chave_idempotencia") or "").strip() or not (doc.get("execucao_chave") or "").strip():
        e.append("chave")
    if doc["fonte"] not in ("n8n", "python_oneshot", "backfill_manual"):
        e.append("fonte")
    if not re.fullmatch(r"[a-z0-9_]{3,40}", doc["job"]):
        e.append("job")
    if doc["disparo"] not in ("agenda", "manual"):
        e.append("disparo")
    if not re.fullmatch(r"v[0-9]{1,3}", doc["api_versao"]):
        e.append("api_versao")
    if not (doc["contrato_versao"] or "").strip() or not re.fullmatch(r"[0-9a-f]{64}", doc["contrato_sha256"]):
        e.append("contrato")
    if doc["tipo_lote"] != "contas" or not (isinstance(doc["lote_ordinal"], int) and doc["lote_ordinal"] >= 1):
        e.append("lote")
    if doc["origem_janela"] not in ("D0", "D-1", "backfill"):
        e.append("origem")
    if doc["origem_janela"] != "backfill" and doc["janela_inicio"] != doc["janela_fim"]:
        e.append("janela")
    ini, fim = (datetime.fromisoformat(doc[k]) for k in ("iniciada_em", "encerrada_em"))
    if fim < ini or not isinstance(doc["duracao_ms"], int) or doc["duracao_ms"] < 0:
        e.append("tempo")
    datetime.fromisoformat(doc["batimento_em"])
    if doc["resultado"] not in ("ok", "parcial", "falhou"):
        e.append("resultado")
    if (doc["resultado"] == "ok") != (doc["motivo"] is None):
        e.append("motivo_semantico")
    for k in ("contas_tentadas", "contas_aceitas"):
        if not all(re.fullmatch(r"[0-9]{6,12}", c) for c in doc[k]):
            e.append(k)
    if not isinstance(doc["contas_recusadas"], list) or not isinstance(doc["linhas"], list):
        e.append("arrays")
    if not isinstance(doc["projetar_compat"], bool):
        e.append("projetar_compat")
    chaves = [(l["customer_id"], l["campaign_id"], l["metric_date"], json.dumps(l["segmentos"]))
              for l in doc["linhas"]]
    if len(chaves) != len(set(chaves)):
        e.append("LINHAS_DUPLICADAS_NO_LOTE")
    for l in doc["linhas"]:
        e += violacoes_linha(l, doc)
    return e


def violacoes_linha(l: dict, doc: dict) -> list[str]:
    e = []
    if not re.fullmatch(r"[0-9]{6,12}", l["customer_id"] or ""):
        e.append("CUSTOMER_ID_INVALIDO")
    if not re.fullmatch(r"[0-9]{1,20}", l["campaign_id"] or ""):
        e.append("CAMPAIGN_ID_INVALIDO")
    if not re.fullmatch(r"[A-Z]{3}", l["currency_code"] or ""):
        e.append("MOEDA_AUSENTE_OU_INVALIDA")
    if l["metric_date"] is None or not doc["janela_inicio"] <= l["metric_date"] <= doc["janela_fim"]:
        e.append("DATA")
    if l["colhida_em"] is None:
        e.append("COLHIDA_EM_AUSENTE")
    if not isinstance(l["segmentos"], dict) or not isinstance(l["metricas_extras"], dict):
        e.append("SEGMENTOS/EXTRAS")
    for coluna in METRICAS:
        v = l[coluna]
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            e.append(f"METRICA_NAO_NUMERICA:{coluna}")
        elif v < 0 or (coluna in TAXAS and v > 1):
            e.append(f"CHECK:{coluna}")
    return e


# ── testes ──────────────────────────────────────────────────────────────────

def teste_familia_registrada_com_nome_e_rpc():
    assert todas()["campanha_dia"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_campanha_dia"


def teste_gaql_so_tem_campo_selecionavel_e_janela():
    gaql = FAMILIA.gaql(CTX)
    assert catalogo.invalidos(gaql) == ()
    assert "FROM campaign" in gaql and CTX.janela_gaql in gaql
    for campo in ("metrics.invalid_clicks", "metrics.invalid_click_rate", "customer.id",
                  "campaign.advertising_channel_type"):
        assert campo in catalogo.campos_do_select(gaql)


def teste_tipos_da_linha_completa():
    l = FAMILIA.normalizar(_row(**COMPLETA), CTX)
    assert l["campaign_id"] == "24278665189" and l["customer_id"] == "5478096539"
    assert (l["campaign_status"], l["advertising_channel_type"]) == ("ENABLED", "SEARCH")
    assert l["currency_code"] == "BRL" and l["segmentos"] == {}
    assert l["volc_campaign_id"] is None
    for coluna, (_, tipo) in METRICAS.items():
        assert type(l[coluna]) is tipo, coluna
    assert l["metricas_extras"] == {"invalid_clicks": 3, "invalid_click_rate": 0.0435}
    assert type(l["metricas_extras"]["invalid_clicks"]) is int
    assert json.loads(json.dumps(l)) == l


def teste_ausente_vira_none_e_zero_medido_continua_zero():
    l = FAMILIA.normalizar(_row(impressions=0, cost_micros=0), CTX)
    assert l["impressoes"] == 0 and l["custo_micros"] == 0
    for coluna in METRICAS:
        if coluna not in ("impressoes", "custo_micros"):
            assert l[coluna] is None, coluna
    assert l["metricas_extras"] == {}


def teste_conta_divergente_estoura():
    with pytest.raises(ValueError, match="IDENTIDADE_DIVERGENTE"):
        FAMILIA.normalizar(_row(cliente=1111111111, **COMPLETA), CTX)


def _documento(linhas):
    agora = datetime.now(timezone.utc)
    return FAMILIA.documento(CTX, linhas, lote=1, execucao_chave="gads_campanha_dia:x:D-1:2026-10-07",
                             iniciada=agora - timedelta(seconds=2))


def teste_documento_tem_exatamente_as_chaves_que_a_rpc_le():
    doc = _documento([FAMILIA.normalizar(_row(**COMPLETA), CTX)])
    assert set(doc) == chaves_documento_rpc()
    assert set(doc["linhas"][0]) == chaves_linha_rpc()


def teste_documento_passaria_nas_validacoes_da_rpc():
    linhas = [FAMILIA.normalizar(_row(**COMPLETA), CTX),
              FAMILIA.normalizar(_row(campaign_id=23518009650, impressions=0), CTX)]
    doc = _documento(linhas)
    assert violacoes_documento(doc) == []
    assert (doc["resultado"], doc["motivo"], len(doc["linhas"])) == ("ok", None, 2)
    assert doc["projetar_compat"] is True


def teste_documento_de_lote_vazio_e_valido():
    doc = _documento([])
    assert violacoes_documento(doc) == [] and doc["linhas"] == []


def teste_taxa_fora_de_0_1_e_duplicata_viram_recusa_local_nomeada():
    boa = FAMILIA.normalizar(_row(**COMPLETA), CTX)
    ruim = FAMILIA.normalizar(_row(campaign_id=1, **{**COMPLETA, "ctr": 7.66}), CTX)
    doc = _documento([boa, ruim, dict(boa)])
    assert len(doc["linhas"]) == 1 and doc["resultado"] == "parcial"
    assert "TAXA_FORA_DE_0_1:ctr" in doc["motivo"] and "LINHA_DUPLICADA_NA_PAGINA" in doc["motivo"]
    assert violacoes_documento(doc) == []


def teste_executor_usa_o_documento_e_a_rpc_da_familia():
    chamadas = []
    recibo_lote = {"linhas_aceitas": 1, "linhas_preteridas": 0, "linhas_rejeitadas": 0,
                   "projecao_estado": "aplicada", "projecao_linhas": 0, "resultado": "ok"}
    rec = executor.coletar(FAMILIA, CTX, buscar=lambda cid, g: [_row(**COMPLETA)],
                           registrar=lambda rpc, doc: chamadas.append((rpc, doc)) or dict(recibo_lote))
    assert rec.lidas == 1 and len(chamadas) == 2 and rec.fechamento is not None
    (rpc, doc), (rpc_f, fech) = chamadas
    assert rpc == rpc_f == "volc_registrar_gads_campanha_dia" and set(doc) == chaves_documento_rpc()
    assert doc["chave_idempotencia"].endswith(":lote1") and violacoes_documento(doc) == []
    assert fech["execucao_chave"] == doc["execucao_chave"]
    assert (fech["tipo_lote"], fech["lote_ordinal"], fech["linhas_aceitas"]) == ("fechamento", 0, 1)


def violacoes_fechamento(f: dict) -> list[str]:
    e = []
    if (f["tipo_lote"], f["lote_ordinal"], f["linhas"]) != ("fechamento", 0, []):
        e.append("tipo_lote")
    if (f["resultado"] == "ok") != (f["motivo"] is None):
        e.append("motivo_semantico")
    if f["resultado"] == "ok" and f["linhas_rejeitadas"] != 0:
        e.append("ok_sem_recusa")
    if f["resultado"] == "falhou" and f["linhas_aceitas"] != 0:
        e.append("falha_sem_linha")
    if f["projecao_estado"] not in ("nao_solicitada", "aplicada", "parcial", "recusada_ambigua",
                                    "indisponivel"):
        e.append("projecao_estado")  # 'falhou' exige código, que o fechamento não manda
    if f["projecao_estado"] not in ("aplicada", "parcial") and f["projecao_linhas"] != 0:
        e.append("projecao_zero")
    if f["projecao_linhas"] > f["linhas_aceitas"]:
        e.append("projecao_cabe")
    for k in ("linhas_aceitas", "linhas_preteridas", "linhas_rejeitadas", "projecao_linhas"):
        if type(f[k]) is not int or f[k] < 0:
            e.append(k)
    return e


def _fechar(lotes):
    return FAMILIA.fechamento(CTX, execucao_chave="gads_campanha_dia:x:D-1:2026-10-07", lotes=lotes,
                              iniciada=datetime.now(timezone.utc) - timedelta(seconds=2))


def teste_fechamento_tem_as_chaves_da_rpc_e_soma_os_lotes():
    lotes = [{"linhas_aceitas": 2, "linhas_preteridas": 1, "linhas_rejeitadas": 0,
              "projecao_estado": "aplicada", "projecao_linhas": 2, "resultado": "ok"},
             {"linhas_aceitas": 1, "linhas_preteridas": 0, "linhas_rejeitadas": 0,
              "projecao_estado": "aplicada", "projecao_linhas": 0, "resultado": "ok", "repetida": True}]
    f = _fechar(lotes)
    assert set(f) == chaves_fechamento_rpc()
    assert (f["linhas_aceitas"], f["linhas_preteridas"], f["linhas_rejeitadas"]) == (3, 1, 0)
    assert (f["projecao_estado"], f["projecao_linhas"], f["resultado"]) == ("aplicada", 2, "ok")
    assert f["chave_idempotencia"].endswith(":fechamento") and violacoes_fechamento(f) == []


def teste_fechamento_com_lote_parcial_ou_falho_nao_mente():
    parcial = _fechar([{"linhas_aceitas": 1, "linhas_rejeitadas": 1, "resultado": "parcial",
                        "projecao_estado": "aplicada", "projecao_linhas": 1},
                       {"linhas_aceitas": 0, "resultado": "ok", "projecao_estado": "falhou",
                        "projecao_linhas": 0}])
    assert (parcial["resultado"], parcial["projecao_estado"]) == ("parcial", "parcial")
    assert parcial["motivo"] and violacoes_fechamento(parcial) == []
    falhou = _fechar([{"linhas_aceitas": 0, "linhas_rejeitadas": 2, "resultado": "falhou",
                       "projecao_estado": "nao_solicitada", "projecao_linhas": 0}])
    assert falhou["resultado"] == "falhou" and falhou["contas_aceitas"] == []
    assert violacoes_fechamento(falhou) == []
    vazio = _fechar([{"linhas_aceitas": 0, "resultado": "ok", "projecao_estado": "nao_solicitada"}])
    assert (vazio["resultado"], vazio["linhas_aceitas"]) == ("ok", 0) and violacoes_fechamento(vazio) == []


def teste_vinculo_volc_vem_do_mapa_do_contexto():
    com = dataclasses.replace(CTX, mapa_volc={"24278665189": "volc-senac-001"})
    assert FAMILIA.normalizar(_row(**COMPLETA), com)["volc_campaign_id"] == "volc-senac-001"
    assert FAMILIA.normalizar(_row(campaign_id=1, **COMPLETA), com)["volc_campaign_id"] is None
    assert FAMILIA.normalizar(_row(**COMPLETA), CTX)["volc_campaign_id"] is None


def teste_extras_sao_as_chaves_da_view():
    sql = (RAIZ / "supabase/migrations/v17_01_gads_fatos_granulares.sql").read_text(encoding="utf-8")
    lidas = set(re.findall(r"metricas_extras\s*->>\s*'([a-z_]+)'", sql))
    assert set(EXTRAS) == lidas
