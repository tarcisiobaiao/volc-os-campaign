"""Custo do período pelo fato canônico (W11b): o que a leitura afirma e o que
ela se recusa a afirmar. Hermético: fato e ledger são linhas sintéticas no
formato da v12_04; nada fala com Supabase nem com o Google."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.trafego import custo_canonico as cc

CU, OUTRA = "5478096539", "1112223334"     # Crédito Up e uma conta sintética
SENAC, REMOVIDA = "24278665189", "23000000001"
AGORA = datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)   # 10h em São Paulo
# Para a rota: 02h UTC de 15/10 ainda é 14/10 (23h) em São Paulo. Se a rota
# usasse UTC para "hoje", o período padrão sairia um dia adiantado.
AGORA_ROTA = datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc)
P = cc.Periodo(date(2026, 10, 12), date(2026, 10, 14))


def fato(dia: str, custo: Any, *, conta=CU, campanha=SENAC, status="ENABLED",
         colhida="2026-10-15T09:00:00+00:00", origem="backfill", moeda="BRL", nome="VOLC-SENAC"):
    return {"customer_id": conta, "campaign_id": campanha, "metric_date": dia,
            "campaign_name": nome, "campaign_status": status,
            "advertising_channel_type": "SEARCH", "volc_campaign_id": None,
            "custo_micros": custo, "currency_code": moeda, "colhida_em": colhida,
            "origem_janela": origem}


def fecho(ini: str, fim: str, *, origem="D-1", resultado="ok", contas=(CU,),
          job="gads_campanha_dia", encerrada="2026-10-15T09:30:00+00:00",
          tentadas=None, recusadas=()):
    """Formato n8n por padrão (conta lida vai em `contas_aceitas`)."""
    return {"job": job, "origem_janela": origem, "janela_inicio": ini, "janela_fim": fim,
            "resultado": resultado, "contas_aceitas": list(contas),
            "contas_tentadas": list(contas if tentadas is None else tentadas),
            "contas_recusadas": [{"customer_id": c, "classe": "X"} for c in recusadas],
            "encerrada_em": encerrada}


def fecho_python(ini, fim, *, origem="D-1", conta=CU, com_linha=False, resultado="ok"):
    """O fechamento que `volc_ads/coleta/familias/campanha_dia.py` grava: leitura
    sem linha deixa `contas_aceitas=[]` e a conta só em `contas_tentadas`."""
    return fecho(ini, fim, origem=origem, resultado=resultado,
                 contas=(conta,) if com_linha else (), tentadas=(conta,))


TUDO_FECHADO = [fecho("2026-10-12", "2026-10-14", origem="backfill")]


def montar(linhas, fechos, contas=(CU,), periodo=P):
    return cc.montar_custo(linhas, fechos, contas=list(contas) if contas else None,
                           periodo=periodo, agora=AGORA)


def conta(r, cid=CU):
    return next(c for c in r["contas"] if c["customer_id"] == cid)


# ── domínio ─────────────────────────────────────────────────────────────────

def teste_periodo_padrao_sao_30_dias_fechados_ate_ontem():
    p = cc.periodo_padrao(date(2026, 10, 15))
    assert (p.inicio, p.fim, p.dias) == (date(2026, 9, 15), date(2026, 10, 14), 30)


@pytest.mark.parametrize("ini, fim", [(date(2026, 10, 2), date(2026, 10, 1)),
                                      (date(2026, 1, 1), date(2026, 6, 1))])
def teste_periodo_invertido_ou_longo_demais_e_recusado(ini, fim):
    with pytest.raises(cc.PeriodoInvalido):
        cc.Periodo(ini, fim)


def teste_todos_os_dias_fechados_da_real_e_soma_em_micros_inteiros():
    r = montar([fato("2026-10-12", 10_000_000), fato("2026-10-14", 5_500_000)], TUDO_FECHADO)
    c = conta(r)
    assert r["verdade"] == c["verdade"] == "real" and r["fonte"] == "google_ads_campanha_dia"
    assert c["custo_micros"] == 15_500_000 and type(c["custo_micros"]) is int
    # 13/10 foi lido e não veio linha: zero MEDIDO, não ausência
    assert [d["custo_micros"] for d in c["dias"]] == [10_000_000, 0, 5_500_000]
    assert r["moedas"] == {"BRL": {"contas": [CU], "custo_micros": 15_500_000,
                                   "custo_micros_coberto": 15_500_000}}


def teste_dia_sem_coleta_e_sem_dado_e_o_total_some():
    """A regra que motivou o lote: falta de dia nunca vira zero."""
    r = montar([fato("2026-10-12", 10_000_000)], [fecho("2026-10-12", "2026-10-12")])
    c = conta(r)
    assert c["verdade"] == r["verdade"] == "parcial"
    assert c["custo_micros"] is None and c["custo_micros_coberto"] == 10_000_000
    assert [(d["estado"], d["custo_micros"]) for d in c["dias"]] == [
        ("fechado", 10_000_000), ("sem_coleta", None), ("sem_coleta", None)]
    assert "2 dia(s) sem coleta" in c["motivos"]
    assert r["moedas"]["BRL"]["custo_micros"] is None


def teste_conta_nunca_coletada_e_indisponivel_e_nao_zero():
    r = montar([], [])
    c = conta(r)
    assert r["verdade"] == c["verdade"] == "indisponivel"
    assert c["custo_micros"] is None and c["custo_micros_coberto"] is None and c["moeda"] is None
    assert all(d["custo_micros"] is None for d in c["dias"])
    assert r["moedas"] == {}


def teste_fechamento_falhou_nao_cobre_dia():
    r = montar([], [fecho("2026-10-12", "2026-10-14", origem="backfill", resultado="falhou")])
    assert conta(r)["verdade"] == "indisponivel"


def teste_fechamento_de_outra_familia_nao_cobre_o_campanha_dia():
    r = montar([], [fecho("2026-10-12", "2026-10-14", origem="backfill", job="gads_url")])
    assert conta(r)["verdade"] == "indisponivel"


def teste_fechamento_de_outra_conta_nao_cobre():
    r = montar([], [fecho("2026-10-12", "2026-10-14", origem="backfill", contas=(OUTRA,))])
    assert conta(r)["verdade"] == "indisponivel"


def teste_fluxos_n8n_v12_tambem_cobrem():
    r = montar([], [fecho("2026-10-12", "2026-10-12", job="gads_dia_d1"),
                    fecho("2026-10-13", "2026-10-13", job="gads_dia_d1"),
                    fecho("2026-10-14", "2026-10-14", job="gads_dia_d1")])
    assert conta(r)["verdade"] == "real" and conta(r)["custo_micros"] == 0


def teste_so_d0_e_intradia_e_rebaixa():
    r = montar([fato("2026-10-14", 1_000_000, origem="D0")],
               [fecho("2026-10-12", "2026-10-13", origem="backfill"),
                fecho("2026-10-14", "2026-10-14", origem="D0")])
    c = conta(r)
    assert c["dias"][2] == {"data": "2026-10-14", "estado": "intradia", "custo_micros": 1_000_000}
    assert c["verdade"] == "parcial" and c["custo_micros"] is None
    assert c["custo_micros_coberto"] == 1_000_000


def teste_fechamento_parcial_rebaixa_mas_mostra_o_valor():
    r = montar([fato("2026-10-13", 2_000_000)],
               [fecho("2026-10-12", "2026-10-14", origem="backfill"),
                fecho("2026-10-13", "2026-10-13", resultado="parcial")])
    # o fechado ganha do parcial no mesmo dia
    assert conta(r)["verdade"] == "real"
    r = montar([fato("2026-10-13", 2_000_000)],
               [fecho("2026-10-12", "2026-10-12"), fecho("2026-10-14", "2026-10-14"),
                fecho("2026-10-13", "2026-10-13", resultado="parcial")])
    c = conta(r)
    assert c["dias"][1]["estado"] == "parcial" and c["dias"][1]["custo_micros"] == 2_000_000
    assert c["verdade"] == "parcial"


def teste_linha_sem_fechamento_aparece_rebaixada():
    r = montar([fato("2026-10-13", 2_000_000)],
               [fecho("2026-10-12", "2026-10-12"), fecho("2026-10-14", "2026-10-14")])
    c = conta(r)
    assert c["dias"][1] == {"data": "2026-10-13", "estado": "sem_fechamento", "custo_micros": 2_000_000}
    assert c["verdade"] == "parcial" and c["custo_micros"] is None


def teste_custo_null_no_fato_nao_vira_zero():
    r = montar([fato("2026-10-13", None), fato("2026-10-13", 3_000_000, campanha=REMOVIDA)],
               TUDO_FECHADO)
    c = conta(r)
    assert c["dias"][1]["custo_micros"] is None
    assert c["verdade"] == "parcial" and c["custo_micros"] is None
    senac = next(x for x in c["campanhas"] if x["campaign_id"] == SENAC)
    assert senac["custo_micros"] is None and senac["custo_micros_coberto"] is None


def teste_removida_entra_na_soma_e_e_marcada():
    r = montar([fato("2026-10-12", 10_000_000),
                fato("2026-10-12", 4_000_000_000, campanha=REMOVIDA, status="ENABLED",
                     colhida="2026-10-13T09:00:00+00:00", nome="velha"),
                fato("2026-10-13", 1_000_000, campanha=REMOVIDA, status="REMOVED",
                     colhida="2026-10-15T09:00:00+00:00", nome="velha-removida")],
               TUDO_FECHADO)
    c = conta(r)
    assert c["custo_micros"] == 4_011_000_000 and c["verdade"] == "real"
    rem = next(x for x in c["campanhas"] if x["campaign_id"] == REMOVIDA)
    # status e nome vêm da leitura mais nova
    assert rem["removida"] is True and rem["status"] == "REMOVED" and rem["nome"] == "velha-removida"
    assert rem["custo_micros"] == 4_001_000_000
    assert c["campanhas_removidas_com_gasto"] == 1
    assert any("removida" in m for m in c["motivos"])


def teste_moedas_nunca_se_somam():
    r = montar([fato("2026-10-12", 10_000_000),
                fato("2026-10-12", 7_000_000, conta=OUTRA, moeda="USD")],
               [fecho("2026-10-12", "2026-10-14", origem="backfill", contas=(CU, OUTRA))],
               contas=(CU, OUTRA))
    assert r["moedas"]["BRL"]["custo_micros"] == 10_000_000
    assert r["moedas"]["USD"]["custo_micros"] == 7_000_000
    assert "custo_micros" not in r  # não há total geral: só por moeda


def teste_moeda_divergente_na_mesma_conta_nao_soma():
    r = montar([fato("2026-10-12", 10_000_000), fato("2026-10-13", 1, moeda="USD")], TUDO_FECHADO)
    c = conta(r)
    assert c["moeda"] is None and c["custo_micros"] is None and c["verdade"] == "parcial"
    assert r["verdade"] == "parcial" and r["moedas"] == {}


def teste_duplicata_vale_a_mais_nova_e_e_contada():
    r = montar([fato("2026-10-12", 10_000_000, colhida="2026-10-13T09:00:00+00:00"),
                fato("2026-10-12", 9_000_000, colhida="2026-10-15T09:00:00+00:00")], TUDO_FECHADO)
    assert conta(r)["custo_micros"] == 9_000_000
    assert any("repetida" in d for d in r["detalhe"])


def teste_custo_texto_e_recusado_em_vez_de_virar_numero():
    with pytest.raises(ValueError, match="não inteiro"):
        montar([fato("2026-10-12", "10000000")], TUDO_FECHADO)


def teste_frescor_e_proveniencia():
    r = montar([fato("2026-10-12", 1, colhida="2026-10-15T09:00:00+00:00", origem="backfill"),
                fato("2026-10-14", 1, colhida="2026-10-14T09:00:00+00:00", origem="D-1")],
               TUDO_FECHADO)
    c = conta(r)
    assert c["frescor"] == {"ultima_colhida_em": "2026-10-15T09:00:00+00:00",
                            "ultimo_fechamento_em": "2026-10-15T09:30:00+00:00",
                            "idade_horas": 4.0}
    assert c["campanhas"][0]["origens"] == ["D-1", "backfill"]


def teste_sem_conta_pedida_infere_e_avisa():
    r = montar([fato("2026-10-12", 1)], TUDO_FECHADO, contas=None)
    assert [c["customer_id"] for c in r["contas"]] == [CU]
    assert any("inferidas" in d for d in r["detalhe"])


def teste_linha_fora_do_periodo_e_ignorada():
    r = montar([fato("2026-10-11", 99), fato("2026-10-12", 1)], TUDO_FECHADO)
    assert conta(r)["custo_micros"] == 1


# ── infraestrutura: os filtros que vão ao PostgREST ─────────────────────────

@pytest.mark.asyncio
async def teste_fonte_pede_so_o_periodo_as_contas_e_a_linha_sem_segmento(monkeypatch):
    from app.trafego.custo_canonico_fonte import FonteDeCustoCanonico

    pedidos: List[tuple] = []

    async def _tudo(self, alvo, params, *, chave="volc_campaign_id", pagina=1000):
        pedidos.append((alvo, params, chave))
        return []

    monkeypatch.setattr(FonteDeCustoCanonico, "_tudo", _tudo)
    f = FonteDeCustoCanonico("https://database.agenciavolc.com.br", "x")
    await f.linhas_do_fato([CU, OUTRA], P)
    await f.fechamentos([CU], P)
    (a1, p1, k1), (a2, p2, k2) = pedidos
    assert a1 == "google_ads_campanha_dia" and k1 == "fato_id"
    assert p1["metric_date"] == ["gte.2026-10-12", "lte.2026-10-14"]
    assert p1["customer_id"] == f"in.({CU},{OUTRA})" and p1["segmentos"] == "eq.{}"
    # Conjunto EXATO de filtros: um filtro a mais (ex.: esconder REMOVED) quebra.
    assert set(p1) == {"select", "metric_date", "segmentos", "customer_id"}
    assert "campaign_status" in p1["select"] and "currency_code" in p1["select"]
    assert a2 == "trafego_coleta_execucao" and k2 == "execucao_id"
    assert set(p2) == {"select", "tipo_lote", "job", "janela_inicio", "janela_fim", "or"}
    assert p2["tipo_lote"] == "eq.fechamento"
    assert p2["or"] == "(contas_aceitas.ov.{%s},contas_tentadas.ov.{%s})" % (CU, CU)
    assert "contas_tentadas" in p2["select"] and "contas_recusadas" in p2["select"]
    assert p2["job"] == "in.(gads_campanha_dia,gads_dia_d0,gads_dia_d1)"
    assert (p2["janela_inicio"], p2["janela_fim"]) == ("lte.2026-10-14", "gte.2026-10-12")


# ── a rota ──────────────────────────────────────────────────────────────────

class FonteDuble:
    def __init__(self, linhas=(), fechos=(), falha=None):
        self.linhas, self.fechos, self.falha = list(linhas), list(fechos), falha
        self.pedidos: List[tuple] = []

    async def linhas_do_fato(self, contas, periodo):
        self.pedidos.append(("fato", contas, periodo))
        if self.falha:
            raise self.falha
        return self.linhas

    async def fechamentos(self, contas, periodo):
        self.pedidos.append(("ledger", contas, periodo))
        return self.fechos


@pytest.fixture
def rota(monkeypatch):
    from app.main import app
    from app.routers import trafego_custo

    monkeypatch.setattr(trafego_custo, "_agora", lambda: AGORA_ROTA)

    def usar(fonte):
        trafego_custo.definir_fonte(fonte)
        return TestClient(app)

    yield usar
    trafego_custo.definir_fonte(None)


def teste_rota_entrega_o_contrato_com_periodo_padrao(rota):
    fonte = FonteDuble([fato("2026-10-13", 5)], [fecho("2026-09-14", "2026-10-13", origem="backfill")])
    r = rota(fonte).get("/api/trafego/custo", params={"conta": "547-809-6539"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["periodo"] == {"inicio": "2026-09-14", "fim": "2026-10-13", "dias": 30}
    assert corpo["verdade"] == "real" and corpo["contas"][0]["custo_micros"] == 5
    assert fonte.pedidos[0][1] == [CU]   # hífen do painel aceito e removido


def teste_rota_recusa_parametro_torto_antes_de_ler(rota):
    fonte = FonteDuble()
    c = rota(fonte)
    for params in ({"conta": "abc"}, {"inicio": "2026-10-01"},
                   {"inicio": "2026-10-10", "fim": "2026-10-01"},
                   {"inicio": "2026-10-10", "fim": "2026-10-15"},   # amanhã em São Paulo
                   {"inicio": "2026-01-01", "fim": "2026-10-01"}):
        assert c.get("/api/trafego/custo", params=params).status_code == 400, params
    assert fonte.pedidos == []


def teste_rota_com_fonte_fora_do_ar_e_503_nunca_custo_zero(rota):
    r = rota(FonteDuble(falha=RuntimeError("PostgREST caiu"))).get(
        "/api/trafego/custo", params={"conta": CU})
    assert r.status_code == 503 and "fato canônico" in r.json()["detail"]


def teste_rota_com_dado_fora_do_contrato_e_502(rota):
    fonte = FonteDuble([fato("2026-10-13", "5")], [])
    r = rota(fonte).get("/api/trafego/custo", params={"conta": CU})
    assert r.status_code == 502


def teste_rota_exige_sessao_no_nivel_do_router():
    """Inspeção, como em `test_seguranca_hub`: o portão está declarado na rota."""
    from fastapi.routing import APIRoute

    from app.main import app
    from app.seguranca.identidade import exigir_usuario

    rotas = [r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/trafego/custo"]
    assert len(rotas) == 1 and rotas[0].methods == {"GET"}
    assert exigir_usuario in {d.call for d in rotas[0].dependant.dependencies}


def teste_rota_nao_importa_o_google():
    """Caminho de render do Hub: carregar `volc_ads` ou o SDK seria rede no render."""
    import os
    import subprocess
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    codigo = (
        "import sys\n"
        "class Bloqueio:\n"
        "    def find_spec(self, nome, *a, **k):\n"
        "        if nome.split('.')[0] == 'volc_ads' or nome.startswith('google.ads'):\n"
        "            raise ImportError('BLOQUEADO ' + nome)\n"
        "sys.meta_path.insert(0, Bloqueio())\n"
        "import app.routers.trafego_custo, app.trafego.custo_canonico, app.trafego.custo_canonico_fonte\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=backend, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(backend)})
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr[-800:]


# ── achados da revisão adversarial (C1–C10) ─────────────────────────────────

def teste_c1_rota_le_o_ledger_antes_do_fato(rota):
    fonte = FonteDuble([], [])
    rota(fonte).get("/api/trafego/custo", params={"conta": CU})
    assert [p[0] for p in fonte.pedidos] == ["ledger", "fato"]


def teste_c2_leitura_python_sem_linha_e_zero_medido_nao_sem_coleta():
    r = montar([fato("2026-10-12", 10_000_000)],
               [fecho_python("2026-10-12", "2026-10-12", com_linha=True),
                fecho_python("2026-10-13", "2026-10-13"),
                fecho_python("2026-10-14", "2026-10-14")])
    c = conta(r)
    assert [(d["estado"], d["custo_micros"]) for d in c["dias"]] == [
        ("fechado", 10_000_000), ("fechado", 0), ("fechado", 0)]
    assert c["verdade"] == "real" and c["custo_micros"] == 10_000_000


def teste_c2_conta_recusada_num_ok_nao_conta_como_lida():
    r = montar([], [fecho("2026-10-12", "2026-10-14", origem="backfill", contas=(),
                          tentadas=(CU,), recusadas=(CU,))])
    assert conta(r)["verdade"] == "indisponivel"


def teste_c2_python_falhou_nao_cobre():
    r = montar([], [fecho_python("2026-10-12", "2026-10-14", origem="backfill", resultado="falhou")])
    assert conta(r)["verdade"] == "indisponivel"


def teste_c3_conta_pedida_indisponivel_anula_o_total_da_moeda():
    r = montar([fato("2026-10-12", 10_000_000)], TUDO_FECHADO, contas=(CU, OUTRA))
    assert conta(r, OUTRA)["verdade"] == "indisponivel"
    assert r["moedas"]["BRL"]["custo_micros"] is None
    assert r["moedas"]["BRL"]["custo_micros_coberto"] == 10_000_000
    assert r["verdade"] == "parcial" and any("sem moeda conhecida" in d for d in r["detalhe"])


def teste_c3_conta_lida_inteira_sem_gasto_nao_anula_o_total():
    r = montar([fato("2026-10-12", 10_000_000)],
               [fecho("2026-10-12", "2026-10-14", origem="backfill", contas=(CU, OUTRA))],
               contas=(CU, OUTRA))
    assert conta(r, OUTRA)["custo_micros"] == 0
    assert r["moedas"]["BRL"]["custo_micros"] == 10_000_000 and r["verdade"] == "real"


def teste_c4_inferencia_inclui_conta_so_tentada_e_nao_da_real():
    r = montar([fato("2026-10-12", 1)],
               TUDO_FECHADO + [fecho("2026-10-12", "2026-10-14", origem="backfill",
                                     resultado="falhou", contas=(), tentadas=(OUTRA,))],
               contas=None)
    assert [c["customer_id"] for c in r["contas"]] == [OUTRA, CU]
    assert conta(r, OUTRA)["verdade"] == "indisponivel" and r["verdade"] == "parcial"


def teste_c5_dia_parcial_sem_linha_e_sem_dado_nao_zero():
    r = montar([], [fecho("2026-10-12", "2026-10-14", origem="backfill", resultado="parcial")])
    assert {(d["estado"], d["custo_micros"]) for d in conta(r)["dias"]} == {("parcial", None)}
    assert conta(r)["custo_micros_coberto"] is None


def teste_c7_status_traz_de_quando_e():
    r = montar([fato("2026-10-12", 1, colhida="2026-10-13T09:00:00+00:00")], TUDO_FECHADO)
    assert conta(r)["campanhas"][0]["status_lido_em"] == "2026-10-13T09:00:00+00:00"


def teste_c10_ultimo_fechamento_ignora_falhou():
    r = montar([], TUDO_FECHADO + [fecho("2026-10-12", "2026-10-14", origem="backfill",
                                         resultado="falhou", encerrada="2026-10-15T12:00:00+00:00")])
    assert conta(r)["frescor"]["ultimo_fechamento_em"] == "2026-10-15T09:30:00+00:00"
