"""Item 5 (17/10/2026): contrato dos coletores canônicos, testado sobre o MESMO código implantado no n8n.

Executa os Code nodes novos (docs/.../receipts/item5-20261017/codigo) em Node com $() simulado e confere:
zero medido × ausência de linha × moeda observada/não provada (Google) e quantização decimal half-even,
fail-closed e preservação do bruto (JoinAds). As saídas JoinAds passam pelo adaptador estrito do lab.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
COD = RAIZ / "docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/codigo"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node ausente")

NOMES_D0 = {"campaigns": "Google Ads - Get Campaigns1", "goals": "Google Ads - Get Conversion Goals",
            "budgets": "Google Ads - Get Campaign Budget", "metrics": "Google Ads - Get metrics1",
            "split": "Split Out2", "fields": "Edit Fields2"}


def rodar(tmp_path: Path, codigo: str, nodes: dict):
    c, f = tmp_path / "code.js", tmp_path / "fx.json"
    c.write_text(codigo)
    f.write_text(json.dumps({"nodes": nodes}))
    r = subprocess.run([NODE, str(COD / "executar_code_node.mjs"), str(c), str(f)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def camp(cid, status="ENABLED", moeda="BRL"):
    row = {"campaign": {"id": cid, "name": f"c{cid}", "status": status}}
    if moeda is not None:
        row["customer"] = {"currencyCode": moeda}
    return row


def google(tmp_path, campanhas, metricas):
    codigo = (COD / "google_campaign_day.js").read_text().replace("__NOMES__", json.dumps(NOMES_D0))
    nodes = {"Google Ads - Get Campaigns1": [{"json": {"results": campanhas}}],
             "Google Ads - Get Conversion Goals": [{"json": {"results": []}}],
             "Google Ads - Get Campaign Budget": [{"json": {"results": []}}],
             "Google Ads - Get metrics1": [{"json": {"results": metricas}}],
             "Split Out2": [{"json": {"customerClient": {"id": "1111111111"}}}],
             "Edit Fields2": [{"json": {"Start date": "2026-10-17"}}]}
    return {d["campaign_id"]: d for d in rodar(tmp_path, codigo, nodes)[0]["json"]["data"]}


def test_google_zero_medido_ausencia_e_valor_sao_distinguiveis(tmp_path):
    d = google(tmp_path, [camp("101"), camp("102"), camp("103", status="PAUSED")],
               [{"campaign": {"id": "101"}, "metrics": {"costMicros": "1230000", "impressions": "10", "clicks": "2"}},
                {"campaign": {"id": "102"}, "metrics": {}}])
    assert d["101"]["metric_row_status"] == "present" and d["101"]["metrics"]["cost_micros"] == 1230000
    # linha presente com campos omitidos: zero do proto3 = zero MEDIDO
    assert d["102"]["metric_row_status"] == "present" and d["102"]["metrics"]["cost_micros"] == 0
    # sem linha de métrica: nada fabricado
    assert d["103"]["metric_row_status"] == "metric_row_absent" and d["103"]["metrics"] == {}
    assert d["103"]["raw_source"]["metrics"] == {}
    assert all("cost_micros" not in d["103"]["metrics"] for _ in [0])


def test_google_moeda_so_da_origem(tmp_path):
    d = google(tmp_path, [camp("201", moeda="BRL"), camp("202", moeda=None), camp("203", moeda="brl")], [])
    assert (d["201"]["currency_code"], d["201"]["currency_status"], d["201"]["currency_source"]) == ("BRL", "observed", "gaql:customer.currency_code")
    for cid in ("202", "203"):  # ausente ou fora do formato ISO: nunca BRL por default
        assert d[cid]["currency_code"] is None and d[cid]["currency_status"] == "unproven" and d[cid]["currency_source"] is None
    assert "BRL" not in (COD / "google_campaign_day.js").read_text().replace("'BRL'", "")  # nenhum literal de moeda


def test_google_moeda_vinda_da_linha_de_metrica_quando_a_campanha_nao_traz(tmp_path):
    d = google(tmp_path, [camp("301", moeda=None)], [{"campaign": {"id": "301"}, "customer": {"currencyCode": "BRL"}, "metrics": {"impressions": "1"}}])
    assert d["301"]["currency_code"] == "BRL" and d["301"]["currency_status"] == "observed"


def test_termos_moeda_e_linha_presente(tmp_path):
    linha = {"customer": {"currencyCode": "BRL"}, "campaign": {"id": "1"}, "adGroup": {"id": "2"},
             "searchTermView": {"searchTerm": "termo x", "status": "NONE"}, "segments": {"date": "2026-10-16"}, "metrics": {}}
    sem = dict(linha, customer={}, searchTermView={"searchTerm": "termo y"})
    nodes = {"Split Out2": [{"json": {"customerClient": {"id": "1111111111"}}}],
             "Google Ads | Search terms 7d": [{"json": {"results": [linha, sem]}}],
             "Google Ads | Keywords 7d": [{"json": {"results": []}}]}
    obs = rodar(tmp_path, (COD / "google_termos.js").read_text(), nodes)[0]["json"]["data"][0]["observations"]
    a, b = obs
    assert a["currency_code"] == "BRL" and a["attributes"]["currency_status"] == "observed"
    assert a["attributes"]["metric_row_status"] == "present" and a["metrics"]["cost_micros"] == 0
    assert b["currency_code"] is None and b["attributes"]["currency_status"] == "unproven"


def joinads(tmp_path, linhas_earnings):
    cfg = {"DOMAIN": "exemplo.test", "TIMEZONE": "America/Sao_Paulo", "MODE": "shadow", "CURRENCY": "USD", "COLLECTOR_VERSION": 5}
    nodes = {"Config": [{"json": cfg}], "Monta janelas": [{"json": {"start_date": "2026-10-16", "end_date": "2026-10-16", "domain": "exemplo.test"}}],
             "Schedule": [{"json": {}}], "API earnings": [{"json": {"code": 200, "data": linhas_earnings}}]}
    return rodar(tmp_path, (COD / "joinads_normaliza_coleta.js").read_text(), nodes)[0]["json"]


@pytest.mark.parametrize("bruto,esperado", [
    (12.340000000000002, "12.340000"),      # 15 casas (artefato de float a montante)
    (0.12345650000000001, "0.123457"),      # 17 casas: resto acima da metade arredonda para cima
    (0.1234575, "0.123458"),                 # half-even arredonda para o par de cima
    ("0.1234565", "0.123456"),               # texto exato: empate vai para o par
    ("1,5", "1.500000"), (7, "7.000000"), (1e-07, "0.000000"), ("0", "0.000000"),
])
def test_joinads_quantiza_em_micros_half_even(tmp_path, bruto, esperado):
    out = joinads(tmp_path, [{"date": "2026-10-16", "domain": "exemplo.test", "revenue": bruto, "revenue_client": bruto, "impressions": 5}])
    (o,) = out["observations"]
    assert o["revenue_gross"] == esperado and o["revenue_client"] == esperado
    assert o["attributes"]["revenue_quantization"] == "decimal_half_even_micros"
    assert o["attributes"]["revenue_original"]["revenue_gross"] == (str(bruto) if isinstance(bruto, str) else json.dumps(bruto).replace("1e-07", "1e-7"))
    assert out["rows_rejected"] == 0


@pytest.mark.parametrize("bruto,motivo", [(-1.5, "negativo"), ("NaN", "nao_finito"), ("Infinity", "nao_finito"),
                                          ("abc", "nao_numerico"), (1e30, "overflow"), ("0." + "1" * 50, "precisao_excessiva"),
                                          (True, "tipo_invalido")])
def test_joinads_fail_closed(tmp_path, bruto, motivo):
    out = joinads(tmp_path, [{"date": "2026-10-16", "domain": "exemplo.test", "revenue": bruto, "impressions": 5}])
    assert out["observations"] == [] and out["rows_rejected"] == 1
    assert any(w.get("code") == "row_rejected" and f"revenue_invalid:revenue_gross:{motivo}" in w.get("detail", "") for w in out["warnings"])


def test_joinads_bruto_preservado_moeda_atestada_sem_conversao_e_ausencia(tmp_path):
    linha = {"date": "2026-10-16", "domain": "exemplo.test", "revenue": 12.340000000000002, "impressions": 5}
    out = joinads(tmp_path, [linha, {"date": "2026-10-16", "domain": "exemplo.test", "impressions": 3}])
    (lote,) = [b for b in out["raw_batches"] if b["endpoint"] == "earnings"]
    assert lote["payload"]["data"][0]["revenue"] == 12.340000000000002  # bruto intacto
    a, b = out["observations"]
    assert (a["attributes"]["currency_status"], a["attributes"]["currency_source"], a["attributes"]["currency_original"]) == ("attested", "owner_attestation", "USD")
    conv = a["attributes"]["conversion"]
    assert conv["status"] == "nao_convertido" and conv["revenue_converted"] is None and conv["currency_converted"] == "BRL"
    assert b["revenue_gross"] is None and b["revenue_client"] is None and "revenue_original" not in b["attributes"]
    assert out["run"]["collector_version"] == 5 and out["run"]["receipt"]["contract"] == "item5-20261017"


def test_joinads_quantizado_passa_no_adaptador_estrito_do_lab(tmp_path):
    from volc_dil.fundacao.observacao import adaptar_joinads_v2

    out = joinads(tmp_path, [{"date": "2026-10-16", "domain": "exemplo.test", "revenue": 0.12345650000000001,
                              "revenue_client": 12.340000000000002, "impressions": 5}])
    (o,) = out["observations"]
    linha = dict(o, run_collector="n8n_joinads_v2", run_collector_version="5", run_timezone="America/Sao_Paulo",
                 batch_payload_sha256="a" * 64, batch_request_meta={}, created_at=o["collected_at"])
    obs = adaptar_joinads_v2(json.loads(json.dumps(linha), parse_float=Decimal), moeda_atestada="USD")
    receitas = [x for x in obs if x.metrica.value == "revenue"]
    assert receitas and not any("precisao_acima_de_micros" in (x.motivo or "") for x in receitas)
    assert {x.valor for x in receitas} == {123457, 12340000}


# ------------------------------------------------------------------ error workflow
def classificar(tmp_path, evento):
    c, f = tmp_path / "c.js", tmp_path / "f.json"
    c.write_text((COD / "error_classificar.js").read_text())
    f.write_text(json.dumps({"nodes": {}, "input": [{"json": evento}], "execution_id": "err-1"}))
    return json.loads(subprocess.run([NODE, str(COD / "executar_code_node.mjs"), str(c), str(f)], capture_output=True, text=True, check=True).stdout)[0]["json"]


def decidir(tmp_path, classe, lido):
    c, f = tmp_path / "d.js", tmp_path / "g.json"
    c.write_text((COD / "error_decidir.js").read_text())
    f.write_text(json.dumps({"nodes": {"Classificar e sanitizar": [{"json": classe}]}, "input": [{"json": lido}]}))
    return json.loads(subprocess.run([NODE, str(COD / "executar_code_node.mjs"), str(c), str(f)], capture_output=True, text=True, check=True).stdout)[0]["json"]


def evento(wf="Ps9yLfQkHeaAbyZZ", ultimo="Google Ads - Get metrics1", msg="timeout"):
    return {"execution": {"id": "777", "lastNodeExecuted": ultimo, "mode": "trigger", "error": {"message": msg}}, "workflow": {"id": wf}}


def test_error_sanitiza_e_classifica(tmp_path):
    c = classificar(tmp_path, evento(msg="403 Forbidden https://x.test/a?token=abc developer-token: SEGREDO123 conta 1234567890 eyJhbGciOi.eyJzdWIiOiJ4In0.assinatura a@b.com"))
    assert c["classe_erro"] == "autorizacao" and c["run_key_google"] == "Ps9yLfQkHeaAbyZZ:777" and c["elegivel"]
    for vaz in ("SEGREDO123", "1234567890", "eyJhbGciOi", "a@b.com", "token=abc", "https://"):
        assert vaz not in c["mensagem"]
    assert classificar(tmp_path, evento(wf="outro"))["elegivel"] is False


@pytest.mark.parametrize("lido,acao,estagio,status", [
    ({}, "google_finish", "antes_do_primeiro_lote", "failed"),
    ({"status": "running", "batches_written": 3}, "google_finish", "falha_parcial", "partial"),
    ({"status": "completed", "batches_written": 3}, "nenhuma", "ja_finalizado", None),
    ({"error": {"message": "x"}}, "nenhuma", None, None),
])
def test_error_decide_transicao_idempotente_google(tmp_path, lido, acao, estagio, status):
    d = decidir(tmp_path, classificar(tmp_path, evento()), lido)
    assert (d["acao"], d["estagio"], d["status_final"]) == (acao, estagio, status)
    if acao == "google_finish":
        doc = d["google_documento"]["documento"]
        assert doc["status"] == status and doc["run_key"] == "Ps9yLfQkHeaAbyZZ:777" and "error_workflow" in doc["receipt"]


def test_error_depois_da_gravacao_e_joinads(tmp_path):
    d = decidir(tmp_path, classificar(tmp_path, evento(ultimo="Supabase | Finalizar run")), {"status": "running", "batches_written": 5})
    assert d["estagio"] == "depois_da_gravacao" and d["status_final"] == "partial"
    cj = classificar(tmp_path, evento(wf="jDX397ViVcRQft4A", ultimo="Insere observations"))
    dj = decidir(tmp_path, cj, {"run_key": "rk", "status": "running", "batches_written": 2, "receipt": {"phase": "collecting"}})
    assert dj["acao"] == "joinads_patch" and dj["joinads_patch"]["corpo"]["receipt"]["phase"] == "collecting"
    assert decidir(tmp_path, cj, {})["acao"] == "nenhuma"  # JoinAds sem run: só o registro do n8n


def test_error_teste_nunca_escreve(tmp_path):
    c = classificar(tmp_path, {"teste": evento()})
    d = decidir(tmp_path, c, {})
    assert c["teste"] is True and d["acao"] == "nenhuma" and d["acao_planejada"] == "google_finish" and d["motivo"].startswith("teste_sem_escrita")


# ------------------------------------------------------------------ reaper (shadow)
def test_reaper_shadow_classifica_sem_escrever(tmp_path):
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc)
    iso = lambda m: (agora - timedelta(minutes=m)).isoformat()
    nodes = {"Runs Google em running": [{"json": {"run_id": "r-velho", "collector": "c", "started_at": iso(2000), "google_ads_raw_batch": [{"created_at": iso(1900)}]}},
                                        {"json": {"run_id": "r-ativo", "collector": "c", "started_at": iso(300), "google_ads_raw_batch": [{"created_at": iso(5)}]}}],
             "Runs JoinAds em running": [{"json": {}}]}
    c, f = tmp_path / "r.js", tmp_path / "r.json"
    c.write_text((COD / "reaper_classificar.js").read_text())
    f.write_text(json.dumps({"nodes": nodes}))
    out = json.loads(subprocess.run([NODE, str(COD / "executar_code_node.mjs"), str(c), str(f)], capture_output=True, text=True, check=True).stdout)[0]["json"]
    runs = {r["minutos_sem_atividade"] > 60: r for r in out["runs"]}
    assert out["modo"] == "shadow" and out["n_running"] == 2 and out["n_candidatos"] == 1
    assert runs[True]["acao"].startswith("nenhuma_shadow") and runs[False]["candidato_orfao"] is False
    assert all("r-velho" not in json.dumps(r) for r in out["runs"])  # id pseudonimizado
    assert "fetch(" not in (COD / "reaper_classificar.js").read_text() and "PATCH" not in (COD / "reaper_classificar.js").read_text()
