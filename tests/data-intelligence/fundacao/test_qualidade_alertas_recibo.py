"""Alertas (decisão pura + sink injetado, nada é enviado) e recibo de saúde reprodutível."""
from __future__ import annotations

import ast
import json
from datetime import timedelta
from pathlib import Path

from volc_dil.fundacao.qualidade import Achado, Severidade, decidir_alertas, despachar
from volc_dil.fundacao.qualidade.motor import ConjuntoSaude, avaliar_saude
from volc_dil.fundacao.qualidade.recibo import main, recibo_sintetico, resumo_markdown
from volc_dil.fundacao.qualidade.sintetico import AGORA_PADRAO, gerar_tabelas

PACOTE = Path(__file__).resolve().parents[3] / "experiments" / "data-intelligence-lab" / "src" / "volc_dil" / "fundacao" / "qualidade"


def achado(sev: Severidade, regra="r", chave="k") -> Achado:
    return Achado(regra, sev, "google_ads", "campaign_day", (None, None), {}, "m", chave=chave)


def test_decisao_pura_roteia_por_severidade_e_ignora_info():
    alertas, estado = decidir_alertas(
        [achado(Severidade.CRITICO, chave="a"), achado(Severidade.ALTO, chave="b"), achado(Severidade.AVISO, chave="c"),
         achado(Severidade.INFO, chave="d")], AGORA_PADRAO)
    assert [(a.politica, a.achado.chave) for a in alertas] == [("imediato", "a"), ("horario_comercial", "b"),
                                                               ("digest_diario", "c")]
    assert all(a.canal == "a_decidir" for a in alertas)
    assert len(estado) == 3


def test_silencio_e_dedupe_sem_mutar_entrada():
    a = achado(Severidade.ALTO)
    primeiro, estado = decidir_alertas([a, a], AGORA_PADRAO)
    assert len(primeiro) == 1  # duplicata no mesmo lote
    copia = dict(estado)
    dentro, _ = decidir_alertas([a], AGORA_PADRAO + timedelta(hours=1), ultimo_envio=estado)
    assert dentro == [] and estado == copia  # silêncio de 4 h e estado de entrada intacto
    depois, _ = decidir_alertas([a], AGORA_PADRAO + timedelta(hours=5), ultimo_envio=estado)
    assert len(depois) == 1


def test_despacho_so_pelo_sink_injetado():
    recebidos = []
    alertas, _ = decidir_alertas([achado(Severidade.CRITICO)], AGORA_PADRAO)
    assert despachar(alertas, recebidos.append) == 1 and recebidos[0].achado.regra == "r"


def test_pacote_nao_importa_rede_nem_envio():
    proibidos = {"socket", "urllib", "http", "requests", "httpx", "smtplib", "aiohttp", "slack_sdk", "psycopg", "psycopg2"}
    for py in PACOTE.glob("*.py"):
        arvore = ast.parse(py.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            nomes = []
            if isinstance(no, ast.Import):
                nomes = [a.name.split(".")[0] for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                nomes = [no.module.split(".")[0]]
            assert not set(nomes) & proibidos, (py.name, nomes)


def test_recibo_reprodutivel_e_com_manifesto():
    a = recibo_sintetico("producao_conhecida", 20261016)
    b = recibo_sintetico("producao_conhecida", 20261016)
    assert a["fingerprint"] == b["fingerprint"]
    m = a["manifesto"]
    assert m["seed"] == 20261016 and len(m["entrada_sha256"]) == 64 and len(m["codigo_sha256"]) == 64
    assert m["versoes"]["python"].startswith("3.13") and m["estado"] == "testado com sintético"
    assert recibo_sintetico("producao_conhecida", 7)["manifesto"]["entrada_sha256"] != m["entrada_sha256"]
    regras = a["resumo"]["por_regra"]
    assert regras["run_orfao"] == 3 and regras["zero_sintetizado"] >= 1 and regras["atribuicao_sensor_cobertura_baixa"] == 2
    assert a["resumo"]["por_severidade"]["critico"] == 0
    md = resumo_markdown(a)
    assert "NÃO enviados" in md and "run_orfao" in md


def test_recibo_limpo_nao_tem_nada_acima_de_info():
    r = recibo_sintetico("limpo")
    assert r["resumo"]["pior_severidade"] == "info" and r["alertas_propostos"] == []


def test_recibo_estressado_dispara_todas_as_familias():
    regras = set(recibo_sintetico("estressado")["resumo"]["por_regra"])
    for prefixo in ("frescor_atrasado", "frescor_parado", "frescor_sem_registro", "completude_slots", "run_orfao",
                    "falha_silenciosa", "duplicacao_conflito_no_run", "duplicacao_duplicata_exata_no_run",
                    "duplicacao_reingestao_suspeita", "zero_sintetizado", "reconciliacao_receita_cobertura_baixa",
                    "reconciliacao_receita_excesso", "reconciliacao_custo_divergente", "deriva_distribuicao",
                    "esquema_campo_novo", "substituicao_custom_key_run", "substituicao_moeda",
                    "substituicao_campanha_mudou_de_conta", "atribuicao_sensor_cobertura_baixa"):
        assert any(r.startswith(prefixo) for r in regras), prefixo


def test_cli_entrada_formato_tabelas_e_protocolo(tmp_path):
    tabelas = gerar_tabelas(1, "estressado")
    entrada = tmp_path / "export.json"
    entrada.write_text(json.dumps({"formato": "tabelas", "tabelas": tabelas}), encoding="utf-8")
    assert main(["--entrada", str(entrada), "--agora", "2026-10-16T15:00:00Z", "--saida", str(tmp_path / "o1")]) == 0
    r1 = json.loads((tmp_path / "o1" / "health_receipt.json").read_text(encoding="utf-8"))
    assert r1["manifesto"]["origem"] == "arquivo:export.json" and r1["resumo"]["por_severidade"]["critico"] >= 1
    # protocolo: o conjunto serializado e relido dá os mesmos achados
    conj = ConjuntoSaude.de_tabelas(tabelas, AGORA_PADRAO)
    relido = ConjuntoSaude.de_dict(json.loads(json.dumps(conj.como_dict())), AGORA_PADRAO)
    assert [a.como_dict() for a in avaliar_saude(relido, AGORA_PADRAO)] == \
        [a.como_dict() for a in avaliar_saude(conj, AGORA_PADRAO)]
    assert (tmp_path / "o1" / "health_receipt.md").exists()
