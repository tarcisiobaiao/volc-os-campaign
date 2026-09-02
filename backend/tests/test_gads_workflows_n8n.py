"""Contraprovas dos workflows n8n de ingestão Google Ads campanha-dia.

Estes testes NÃO reimplementam o que os gates já provam — eles fazem os gates
rodarem dentro da suíte, e depois cobrem, em Python puro, as invariantes do
artefato que um gate isolado poderia deixar de fora: o par gerador↔JSON, o
contrato entre o documento que o fluxo monta e o que a migration v12_04 espera,
e a ausência de segundo caminho de agenda.

Nada aqui abre socket, chama Google Ads, fala com o Supabase oficial ou toca no
n8n. `docker` só é usado pelos scripts de ciclo, que vivem fora desta suíte.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
D0 = RAIZ / "n8n" / "volc_gads_campanha_dia_d0.json"
D1 = RAIZ / "n8n" / "volc_gads_campanha_dia_d1.json"
MIGRATION = RAIZ / "supabase" / "migrations" / "v12_04_gads_fato_canonico_dia.sql"


def _rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=RAIZ, capture_output=True, text=True)


def _wf(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _code(wf: dict, nome: str) -> str:
    for no in wf["nodes"]:
        if no["name"] == nome:
            return no["parameters"]["jsCode"]
    raise AssertionError(f"nó {nome} não existe no workflow")


def _sem_comentarios(js: str) -> str:
    """Só o CÓDIGO. Os comentários citam o defeito antigo textualmente, e uma
    varredura ingênua acusaria a própria explicação como reincidência."""
    return "\n".join(l for l in js.splitlines() if not l.lstrip().startswith("//"))


# ── os gates, rodando de verdade ────────────────────────────────────────────

def test_o_json_em_disco_e_o_que_o_gerador_produz():
    """JSON editado à mão diverge do gerador e some no próximo build."""
    p = _rodar(sys.executable, "n8n/gerar_flows_gads_ledger_v12.py", "--check")
    assert p.returncode == 0, p.stdout + p.stderr


def test_validacao_no_a_no_dos_dois_workflows():
    p = _rodar(sys.executable, "scripts/validar_workflows_n8n_gads.py")
    assert p.returncode == 0, p.stdout[-4000:] + p.stderr[-2000:]
    assert "falharam 0" in p.stdout


def test_gate_de_agenda_unica():
    p = _rodar(sys.executable, "scripts/gate_agenda_unica_gads.py")
    assert p.returncode == 0, p.stdout[-4000:] + p.stderr[-2000:]


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node ausente — a simulação offline do Code node exige o runtime")
def test_simulacao_offline_dos_code_nodes():
    """Executa o JavaScript EXATO do workflow, com relógio injetado e zero rede."""
    p = _rodar("node", "scripts/simular_gads_ledger_v12.mjs")
    assert p.returncode == 0, p.stdout[-6000:] + p.stderr[-2000:]
    assert "falharam 0" in p.stdout


# ── o artefato, em Python puro ──────────────────────────────────────────────

def test_os_dois_workflows_nascem_inativos():
    for caminho in (D0, D1):
        assert _wf(caminho)["active"] is False, caminho.name


def test_nenhum_destino_fora_da_autoridade_oficial():
    for caminho in (D0, D1):
        bruto = caminho.read_text(encoding="utf-8")
        assert ".supabase.co" not in bruto
        hosts = set(re.findall(r"https?://([A-Za-z0-9._-]+)", bruto))
        assert hosts <= {"database.agenciavolc.com.br", "googleads.googleapis.com"}, hosts


def test_nenhuma_mutacao_google_alcancavel():
    for caminho in (D0, D1):
        bruto = caminho.read_text(encoding="utf-8")
        assert ":mutate" not in bruto
        assert "mutateOperations" not in bruto
        # A consulta é montada em JS; ela precisa começar por SELECT.
        js = _code(_wf(caminho), "Pagina: preparar pedido")
        assert "const gaql = `SELECT " in js


def test_a_ausencia_nunca_vira_zero_no_normalizador():
    """O defeito que esta entrega corrige, fixado como contraprova.

    O Code legado fazia `parseFloat(item.metrics?.conversionsValue || 0)`. Se
    alguém reintroduzir esse padrão, este teste morre.
    """
    js = _sem_comentarios(_code(_wf(D1), "Pagina: normalizar"))
    assert "|| 0)" not in js
    assert "parseFloat(" not in js
    assert "if (v === null || v === undefined || v === '') return null;" in js


def test_o_normalizador_nao_recalcula_custo_por_conversao():
    """Recalcular custo/conversões inventa número quando conversões é zero."""
    js = _sem_comentarios(_code(_wf(D1), "Pagina: normalizar"))
    assert "custo_por_conversao_micros: num(m.costPerConversion)" in js
    assert "/ $json.conversions" not in js
    assert "spend / " not in js


def test_o_documento_do_fluxo_usa_os_nomes_que_a_rpc_espera():
    """A costura onde dois artefatos discordam calados.

    Todo campo de métrica que o normalizador emite precisa ser um campo que a
    validação da RPC reconhece; e todo campo que a RPC valida precisa ser
    emitido. Um `cost_micros` no fluxo contra um `custo_micros` no banco passaria
    em qualquer teste isolado dos dois lados.
    """
    js = _code(_wf(D1), "Pagina: normalizar")
    sql = MIGRATION.read_text(encoding="utf-8")

    bloco = sql.split("k IN (", 1)[1].split(")", 1)[0]
    esperados = set(re.findall(r"'([a-z_]+)'", bloco))
    assert len(esperados) >= 20

    emitidos = set(re.findall(r"^\s{4}([a-z_]+): (?:num|inteiro)\(", js, re.M))
    assert esperados == emitidos, {
        "só na RPC": sorted(esperados - emitidos),
        "só no fluxo": sorted(emitidos - esperados),
    }


def test_o_fechamento_soma_a_entrada_do_laco_e_nao_um_no_de_dentro():
    """`$('No dentro do laço').all()` devolveria só a última rodada."""
    js = _sem_comentarios(_code(_wf(D1), "Fechar execucao"))
    assert "$input.all()" in js
    assert not re.search(r"\$\(\s*'[^']+'\s*\)\s*\.all\(", js)


def test_o_contexto_da_iteracao_vem_do_merge_e_nao_de_indice_de_rodada():
    """Regressão nomeada: `$()` dentro do laço resolve pelo índice da rodada.

    Uma conta que falha desalinha os índices e a iteração seguinte passa a ler o
    contexto de OUTRA conta, em silêncio. Foi o simulador que derrubou isso.
    """
    wf = _wf(D1)
    for nome in ("Pagina: normalizar", "Classificar erro do Google"):
        assert "$('Pagina: preparar pedido')" not in _sem_comentarios(_code(wf, nome)), nome

    merges = {n["name"]: n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.merge"}
    assert set(merges) == {"Juntar contexto e resposta", "Juntar contexto e erro"}
    for no in merges.values():
        assert no["parameters"]["combineBy"] == "combineByPosition"


def test_split_in_batches_liga_done_e_lote_nas_saidas_certas():
    wf = _wf(D1)
    saidas = wf["connections"]["Lote de contas"]["main"]
    assert [c["node"] for c in saidas[0]] == ["Fechar execucao"]       # main[0] = done
    assert [c["node"] for c in saidas[1]] == ["Pagina: preparar pedido"]  # main[1] = lote


def test_o_limit_1_protege_o_fechamento_de_rodar_por_item():
    wf = _wf(D1)
    limite = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.limit")
    assert limite["parameters"]["maxItems"] == 1
    assert wf["connections"]["Fechar execucao"]["main"][0][0]["node"] == limite["name"]


def test_a_agenda_e_a_janela_de_cada_papel():
    d0, d1 = _wf(D0), _wf(D1)

    def cron(wf: dict) -> str:
        no = next(n for n in wf["nodes"]
                  if n["type"] == "n8n-nodes-base.scheduleTrigger")
        return no["parameters"]["rule"]["interval"][0]["expression"]

    def cfg(wf: dict) -> dict:
        no = next(n for n in wf["nodes"] if n["name"] == "Config")
        return {a["name"]: a["value"] for a in no["parameters"]["assignments"]["assignments"]}

    assert cron(d0) == "0 6,12,18,23 * * *"
    assert cron(d1) == "0 6 * * *"
    assert cfg(d0)["JANELA_MODO"] == "D0" and cfg(d0)["PASSOS"] == "06,12,18,23"
    assert cfg(d1)["JANELA_MODO"] == "D-1" and cfg(d1)["PASSOS"] == "06"
    for wf in (d0, d1):
        assert wf["settings"]["timezone"] == "America/Sao_Paulo"


def test_os_dois_papeis_compartilham_o_mesmo_codigo():
    """D0 e D-1 divergindo é como o legado ganhou `Code` e `Code15`."""
    d0, d1 = _wf(D0), _wf(D1)
    js0 = {n["name"]: n["parameters"].get("jsCode")
           for n in d0["nodes"] if n["type"] == "n8n-nodes-base.code"}
    js1 = {n["name"]: n["parameters"].get("jsCode")
           for n in d1["nodes"] if n["type"] == "n8n-nodes-base.code"}
    assert js0 == js1
    assert d0["connections"] == d1["connections"]


def test_a_projecao_legada_nao_encosta_em_receita_nem_orientacao():
    """A projeção mantém as telas; ela não vira autoridade nem reescreve receita."""
    sql = MIGRATION.read_text(encoding="utf-8")
    corpo = sql.split("CREATE OR REPLACE FUNCTION public.volc_gads_projetar_daily_compat", 1)[1]
    corpo = corpo.split("$$;", 1)[0]
    atualizacao = corpo.split("UPDATE public.daily_campaign_metrics", 1)[1].split("WHERE", 1)[0]
    proibidas = [
        "revenue", "revenue_converted", "revenue_converted_revshare", "roas", "rps",
        "ecpm", "commission_operator", "gam_", "fill_rate", "match_rate", "page_views",
        "pmr", "viewability", "viewable_impressions", "unfilled_impressions",
        "orientacao_", "otimizacao_",
    ]
    for coluna in proibidas:
        assert coluna not in atualizacao, coluna
    # E nunca cria linha nova na legada: criar exigiria decidir receita sem dado.
    assert "INSERT INTO public.daily_campaign_metrics" not in sql


def test_a_migration_nao_toca_a_serie_reservada_a_outra_lane():
    """v13_01 é da lane M-W2-02 e v12_03 é do PMax; nenhuma pode ser criada aqui."""
    versionados = subprocess.run(["git", "ls-files", "supabase/migrations"],
                                 cwd=RAIZ, capture_output=True, text=True,
                                 check=True).stdout.split()
    assert not [v for v in versionados if "v13_" in v]
    assert not [v for v in versionados if "v12_03" in v]
    # E a guarda de colisão está escrita na própria migration.
    assert "v13_01" in MIGRATION.read_text(encoding="utf-8")
