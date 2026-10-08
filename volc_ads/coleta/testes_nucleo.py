"""Núcleo do coletor: contexto, executor e porta de escrita — sem Google e sem banco."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from volc_ads.coleta import executor
from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.persistencia import RPC, ErroPersistenciaColeta


def _ctx(**over):
    base = dict(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
                data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7), fuso="America/Sao_Paulo",
                moeda="BRL", colhida_em=datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc))
    return Contexto(**{**base, **over})


class _Fam:
    nome = "url"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx):
        return f"SELECT campaign.id, metrics.clicks FROM campaign WHERE {ctx.janela_gaql}"

    def normalizar(self, row, ctx):
        return None if row == "descarta" else {"campaign_id": "1", "linha": row}


def teste_d0_e_d1_sao_de_um_dia():
    with pytest.raises(ValueError, match="um dia"):
        _ctx(data_fim=date(2026, 10, 8))
    assert _ctx(origem_janela="backfill", data_fim=date(2026, 10, 8)).data_fim == date(2026, 10, 8)


def teste_executor_conta_descartes_e_monta_documento_do_ledger():
    docs = []
    r = executor.coletar(_Fam(), _ctx(), buscar=lambda cid, q: ["a", "descarta", "b"],
                         registrar=lambda rpc, d: docs.append((rpc, d)) or {"aceitas": len(d["linhas"])})
    assert (r.lidas, r.descartadas, r.aceitas) == (3, 1, 2)
    rpc, d = docs[0]
    assert rpc == "volc_registrar_gads_fatos"
    assert d["familia"] == "url" and d["job"] == "gads_url" and d["lote_ordinal"] == 1
    assert d["janela_inicio"] == d["janela_fim"] == "2026-10-07"
    assert d["chave_idempotencia"].endswith(":lote1")
    assert len(d["contrato_sha256"]) == 64


def teste_sem_linhas_ainda_registra_um_lote_vazio():
    docs = []
    executor.coletar(_Fam(), _ctx(), buscar=lambda c, q: [],
                     registrar=lambda rpc, d: docs.append(d) or {})
    assert len(docs) == 1 and docs[0]["linhas"] == []


def teste_lotes_grandes_sao_fatiados_com_ordinal_e_chave_proprios(monkeypatch):
    monkeypatch.setattr(executor, "LOTE_MAXIMO", 2)
    docs = []
    executor.coletar(_Fam(), _ctx(), buscar=lambda c, q: ["a", "b", "c"],
                     registrar=lambda rpc, d: docs.append(d) or {})
    assert [d["lote_ordinal"] for d in docs] == [1, 2]
    assert len({d["chave_idempotencia"] for d in docs}) == 2
    assert len({d["execucao_chave"] for d in docs}) == 1


def teste_gaql_invalida_nao_sai_da_maquina():
    class Ruim(_Fam):
        def gaql(self, ctx):
            return "SELECT asset_group_asset.primary_status_details.status FROM asset_group_asset"

    chamou = []
    with pytest.raises(ValueError, match="não selecionáveis"):
        executor.coletar(Ruim(), _ctx(), buscar=lambda c, q: chamou.append(q) or [],
                         registrar=lambda r, d: {})
    assert chamou == []


def teste_porta_de_escrita_recusa_outra_autoridade_e_outra_rpc():
    with pytest.raises(ErroPersistenciaColeta, match="autoridade"):
        RPC(url="https://txvvzpstquqmbhljudfn.supabase.co", service_key="x")
    rpc = RPC(url="https://database.agenciavolc.com.br", service_key="x")
    with pytest.raises(ErroPersistenciaColeta, match="fora da lista"):
        rpc("trafego_ledger_despachar", {})


def teste_executor_consolida_antes_de_fatiar_quando_a_familia_sabe():
    """Views por grupo/anúncio repetem a identidade do fato. Sem consolidar, a
    segunda linha empata em precedência e vira 'preterida': perda silenciosa."""
    class Somadora(_Fam):
        def normalizar(self, row, ctx):
            return {"campaign_id": "1", "placement": "x.com", "cliques": row}

        def consolidar(self, linhas):
            return [{"campaign_id": "1", "placement": "x.com", "cliques": sum(l["cliques"] for l in linhas)}]

    docs = []
    r = executor.coletar(Somadora(), _ctx(), buscar=lambda c, q: [2, 3],
                         registrar=lambda rpc, d: docs.append(d) or {})
    assert r.lidas == 2
    assert docs[0]["linhas"] == [{"campaign_id": "1", "placement": "x.com", "cliques": 5}]


def teste_recibo_le_as_chaves_das_duas_rpcs():
    from volc_ads.coleta.executor import Recibo

    r = Recibo("x", lotes=[{"aceitas": 2, "rejeitadas": 1}, {"linhas_aceitas": 3, "linhas_preteridas": 1}])
    assert (r.aceitas, r.preteridas, r.rejeitadas) == (5, 1, 1)


def teste_fechamento_e_truncamento():
    class ComFecho(_Fam):
        limite = 2

        def fechamento(self, ctx, *, execucao_chave, lotes, iniciada):
            return {"tipo_lote": "fechamento", "lotes": len(lotes)}

    docs = []
    r = executor.coletar(ComFecho(), _ctx(), buscar=lambda c, q: ["a", "b"],
                         registrar=lambda rpc, d: docs.append(d) or {"ok": True})
    assert docs[-1] == {"tipo_lote": "fechamento", "lotes": 1}
    assert r.fechamento == {"ok": True} and r.truncado is True
