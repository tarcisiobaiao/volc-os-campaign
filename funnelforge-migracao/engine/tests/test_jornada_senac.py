"""A JORNADA DO FUNIL como contrato tipado — regressão SENAC.

Fixture: `tests/fixtures/jornada_senac/arquitetura.json` (funil coerente). Cada
teste muta uma cópia para provar UMA falha. Os achados do relatório MiroFish
entram aqui como casos de teste, não como métrica: aquilo é simulação
qualitativa com 0/29 entrevistas transcritas.

Os doze casos obrigatórios da missão de 07/10/2026 estão marcados [C1]..[C12].
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.medicao import ContratoDeMedicao, LeituraDoFunil
from funnelforge.domain.models import PageRole, effective_role
from funnelforge.pipeline.jornada import (
    classificar_saida_oficial,
    contrato_de_medicao,
    revisar_esqueleto,
)
from funnelforge.pipeline.routing import build_funnel_routes, validate_funnel_graph
from tests.cenario_editorial import rodar_cenario, settings_do_cenario

FIXTURE = Path(__file__).parent / "fixtures" / "jornada_senac" / "arquitetura.json"

SLUG = {
    "senac_gratuito": "curso-gratuito-senac",
    "renda": "por-onde-comecar-senac-pr",
    "curso": "tipos-de-curso-senac-p1",
    "estado": "bolsas-de-estudo-senac-p2",
    "inscricao": "portal-do-senac-do-seu-estado-p3",
}


def arquitetura() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _wb(arq: dict, duvida: str) -> dict:
    for job in arq["writing_jobs"]:
        wb = job["writer_briefing"]
        if wb["jornada"]["duvida_id"] == duvida:
            return wb
    raise KeyError(duvida)


def _link(arq: dict, origem: str, destino: str, motivo: str = "volta") -> None:
    _wb(arq, origem)["editorial"]["links"].append(
        {"target": SLUG[destino], "reason": motivo})


def _codigos(issues) -> set[str]:
    return {i.code for i in issues}


def _plano(arq: dict):
    return plano_do_funnel_architecture(copy.deepcopy(arq))


# ---------------------------------------------------------------------------
# o contrato chega tipado do card ao motor
# ---------------------------------------------------------------------------

def test_a_ponte_entrega_a_jornada_tipada_por_pagina_e_por_funil():
    plano = _plano(arquitetura())
    assert plano.jornada is not None
    assert plano.jornada.checkpoint == "estado"
    assert {c.canal for c in plano.jornada.coortes} == {
        "paid_search", "discover", "organic_search", "social"}
    estado = next(p for p in plano.pages if p.slug == SLUG["estado"])
    assert estado.jornada.duvida_id == "estado"
    assert estado.jornada.ja_resolvido == ["renda", "curso"]
    assert estado.jornada.proxima_duvida == "inscricao"
    assert estado.jornada.saida_oficial.classificacao == "boa"


def test_jornada_quebrada_falha_na_ponte_com_o_motivo_antes_de_qualquer_gasto():
    arq = arquitetura()
    _wb(arq, "curso")["jornada"]["entrada_direta"] = "talvez"
    with pytest.raises(ValueError, match="jornada"):
        plano_do_funnel_architecture(arq)


def test_card_sem_jornada_continua_carregando_como_antes():
    arq = arquitetura()
    del arq["funnel_strategy"]["jornada"]
    for job in arq["writing_jobs"]:
        del job["writer_briefing"]["jornada"]
    plano = _plano(arq)
    assert plano.jornada is None
    assert all(p.jornada is None for p in plano.pages)
    assert revisar_esqueleto(plano).bloqueantes == []


def test_funil_coerente_passa_no_revisor_de_esqueleto(settings_minimas):
    plano = _plano(arquitetura())
    revisao = revisar_esqueleto(plano)
    assert revisao.bloqueantes == [], revisao.bloqueantes
    build_funnel_routes(plano, settings_minimas)
    assert validate_funnel_graph(plano, settings_minimas, research_pending=True) == []


# ---------------------------------------------------------------------------
# [C1] CTA de renda repetido depois de a renda já estar resolvida
# ---------------------------------------------------------------------------

def test_c1_cta_de_renda_repetido_depois_de_resolvida_bloqueia():
    arq = arquitetura()
    _link(arq, "estado", "renda", "Refazer a conta da renda")
    revisao = revisar_esqueleto(_plano(arq))
    assert "cta_repetido_apos_resolvido" in _codigos(revisao.bloqueantes)
    msg = next(i.message for i in revisao.bloqueantes
               if i.code == "cta_repetido_apos_resolvido")
    assert "estado" in msg and "renda" in msg


# ---------------------------------------------------------------------------
# [C2] [C3] ciclos sem ganho de informação
# ---------------------------------------------------------------------------

def test_c2_ciclo_renda_curso_sem_informacao_nova_bloqueia():
    arq = arquitetura()
    _wb(arq, "curso")["jornada"]["ja_resolvido"] = []
    _link(arq, "curso", "renda", "Checar a renda")
    revisao = revisar_esqueleto(_plano(arq))
    loops = [i for i in revisao.bloqueantes if i.code == "loop_sem_ganho"]
    assert loops, revisao.bloqueantes
    assert "renda" in loops[0].message and "curso" in loops[0].message


def test_c3_ciclo_estado_inscricao_sem_informacao_nova_bloqueia():
    arq = arquitetura()
    _wb(arq, "inscricao")["jornada"]["ja_resolvido"] = ["renda", "curso"]
    _wb(arq, "inscricao")["jornada"]["proxima_duvida"] = "estado"
    _link(arq, "inscricao", "estado", "Voltar ao estado")
    revisao = revisar_esqueleto(_plano(arq))
    assert "loop_sem_ganho" in _codigos(revisao.bloqueantes)


def test_retorno_justificado_vira_aviso_e_nao_bloqueia():
    arq = arquitetura()
    _wb(arq, "curso")["jornada"]["ja_resolvido"] = []
    _wb(arq, "curso")["jornada"]["retornos_justificados"] = {
        "renda": "Quem entrou direto pelo curso pela busca ainda não fez a conta"}
    _link(arq, "curso", "renda", "Quem entrou direto e não fez a conta da renda")
    revisao = revisar_esqueleto(_plano(arq))
    assert "loop_sem_ganho" not in _codigos(revisao.bloqueantes)
    assert "retorno_justificado" in _codigos(revisao.avisos)


# ---------------------------------------------------------------------------
# [C4] [C5] saída oficial boa x prematura
# ---------------------------------------------------------------------------

def test_c4_saida_oficial_no_estado_com_tarefa_resolvida_e_boa():
    plano = _plano(arquitetura())
    estado = next(p for p in plano.pages if p.slug == SLUG["estado"])
    assert classificar_saida_oficial(estado) == "boa"


def test_c5_saida_oficial_direta_na_lp_antes_da_qualificacao_e_prematura():
    arq = arquitetura()
    _wb(arq, "senac_gratuito")["jornada"]["saida_oficial"] = {
        "esperada": True, "classificacao": "boa"}
    plano = _plano(arq)
    lp = next(p for p in plano.pages if effective_role(p) is PageRole.LP)
    assert classificar_saida_oficial(lp) == "prematura"
    revisao = revisar_esqueleto(plano)
    assert "saida_oficial_prematura" in _codigos(revisao.avisos)


def test_c5_justificativa_explicita_permite_saida_oficial_na_lp():
    arq = arquitetura()
    _wb(arq, "senac_gratuito")["jornada"]["saida_oficial"] = {
        "esperada": True, "classificacao": "boa",
        "justificativa": "Busca de marca pelo portal nacional: o leitor já está pronto"}
    lp = next(p for p in _plano(arq).pages if effective_role(p) is PageRole.LP)
    assert classificar_saida_oficial(lp) == "boa"


def test_saida_oficial_do_curso_antes_do_estado_e_prematura():
    plano = _plano(arquitetura())
    curso = next(p for p in plano.pages if p.slug == SLUG["curso"])
    assert classificar_saida_oficial(curso) == "prematura"


# ---------------------------------------------------------------------------
# [C6] LP que só roteia
# ---------------------------------------------------------------------------

def test_c6_lp_sem_resposta_propria_bloqueia():
    arq = arquitetura()
    _wb(arq, "senac_gratuito")["jornada"]["resposta_imediata"] = ""
    assert "lp_so_roteia" in _codigos(revisar_esqueleto(_plano(arq)).bloqueantes)


def test_c6_lp_cuja_resposta_e_so_o_menu_de_destinos_bloqueia():
    arq = arquitetura()
    _wb(arq, "senac_gratuito")["jornada"]["resposta_imediata"] = (
        "Fazer a conta da renda, ver como achar o meu curso ou achar o Senac do meu estado.")
    assert "lp_so_roteia" in _codigos(revisar_esqueleto(_plano(arq)).bloqueantes)


# ---------------------------------------------------------------------------
# [C7] entrada direta numa /rec que depende de contexto anterior
# ---------------------------------------------------------------------------

def test_c7_rec_que_depende_da_pagina_anterior_bloqueia():
    arq = arquitetura()
    _wb(arq, "curso")["jornada"]["entrada_direta"] = "depende_de_contexto"
    revisao = revisar_esqueleto(_plano(arq))
    assert "entrada_direta_dependente" in _codigos(revisao.bloqueantes)


# ---------------------------------------------------------------------------
# [C8] toda entrada chega a uma conclusão; nenhum beco sem saída
# ---------------------------------------------------------------------------

def test_c8_toda_entrada_do_funil_coerente_tem_caminho_ate_conclusao():
    revisao = revisar_esqueleto(_plano(arquitetura()))
    assert not ({"entrada_sem_conclusao", "beco_sem_saida"}
                & _codigos(revisao.bloqueantes))


def test_c8_pagina_sem_destino_e_sem_conclusao_e_beco_sem_saida():
    arq = arquitetura()
    curso = _wb(arq, "curso")
    curso["editorial"]["links"] = []
    curso["jornada"]["proxima_duvida"] = ""
    revisao = revisar_esqueleto(_plano(arq))
    assert "beco_sem_saida" in _codigos(revisao.bloqueantes)
    assert "entrada_sem_conclusao" in _codigos(revisao.bloqueantes)


# ---------------------------------------------------------------------------
# [C9] busca paga e tráfego frio com a mesma promessa genérica
# ---------------------------------------------------------------------------

def test_c9_paid_search_e_trafego_frio_com_a_mesma_promessa_e_achado():
    arq = arquitetura()
    coortes = arq["funnel_strategy"]["jornada"]["coortes"]
    coortes[1]["promessa"] = coortes[0]["promessa"]
    coortes[1]["profundidade"] = coortes[0]["profundidade"]
    coortes[1]["proximo_passo"] = coortes[0]["proximo_passo"]
    revisao = revisar_esqueleto(_plano(arq))
    assert "promessa_identica_entre_coortes" in _codigos(revisao.avisos)


# ---------------------------------------------------------------------------
# [C10] simulação nunca vira métrica observada
# ---------------------------------------------------------------------------

def test_c10_simulacao_nao_pode_ser_gravada_como_observacao_real():
    with pytest.raises(ValidationError):
        LeituraDoFunil(natureza="observacao_real", sinal="loop_revisita",
                       escopo="aresta:renda->curso", valor=0.31, amostra=1000,
                       fonte="simulacao:mirofish-creditoup-senac-2026-10-01",
                       janela={"inicio": "2026-09-01", "fim": "2026-09-30"})


def test_c10_simulacao_nao_carrega_numero_que_pareca_metrica():
    with pytest.raises(ValidationError):
        LeituraDoFunil(natureza="simulacao", sinal="loop_revisita",
                       escopo="aresta:renda->curso", valor=0.31,
                       fonte="simulacao:mirofish-creditoup-senac-2026-10-01")


def test_c10_contrato_separa_hipotese_simulacao_e_observacao():
    contrato = contrato_de_medicao(_plano(arquitetura()), run_id="r1")
    assert isinstance(contrato, ContratoDeMedicao)
    naturezas = {p.natureza for p in contrato.premissas}
    assert naturezas == {"simulacao", "hipotese"}
    # nada observado: o funil ainda não tem dado real e o contrato não finge
    assert contrato.observadas() == []
    sim = LeituraDoFunil(natureza="simulacao", sinal="loop_revisita",
                         escopo="aresta:renda->curso", faixa="media",
                         fonte="simulacao:mirofish-creditoup-senac-2026-10-01")
    contrato = contrato.model_copy(update={"leituras": [sim]})
    assert contrato.observadas() == []
    despejo = json.loads(contrato.model_dump_json())
    assert despejo["leituras"][0]["natureza"] == "simulacao"


def test_contrato_preve_todos_os_sinais_da_jornada():
    contrato = contrato_de_medicao(_plano(arquitetura()), run_id="r1")
    sinais = {s.sinal for s in contrato.sinais}
    assert sinais >= {
        "chegada_lp", "escolha_de_ramo", "progressao", "resolucao",
        "saida_oficial_boa", "saida_oficial_prematura", "loop_revisita",
        "abandono", "receita_por_sessao", "rpm_valor_de_sessao", "core_web_vitals"}
    assert contrato.saidas_oficiais == {
        "senac_gratuito": "nao_aplicavel", "renda": "nao_aplicavel",
        "curso": "prematura", "estado": "boa", "inscricao": "boa"}
    assert contrato.proposta is not None
    assert contrato.proposta.requer_aprovacao_humana is True
    assert contrato.proposta.publicacao_automatica is False


# ---------------------------------------------------------------------------
# roteamento orientado à próxima dúvida
# ---------------------------------------------------------------------------

def test_cta_principal_e_a_proxima_duvida_e_nao_a_ordem_do_card(settings_minimas):
    plano = _plano(arquitetura())
    build_funnel_routes(plano, settings_minimas)
    lp = next(p for p in plano.pages if effective_role(p) is PageRole.LP)
    assert lp.routes[0].target == SLUG["renda"]
    assert lp.routes[0].placement == "hero"
    assert {r.target for r in lp.routes} == {SLUG["renda"], SLUG["curso"], SLUG["estado"]}


def test_jornada_parcial_bloqueia():
    arq = arquitetura()
    del _wb(arq, "curso")["jornada"]
    assert "jornada_incompleta" in _codigos(revisar_esqueleto(_plano(arq)).bloqueantes)


def test_duas_paginas_com_a_mesma_duvida_bloqueia():
    arq = arquitetura()
    _wb(arq, "inscricao")["jornada"]["duvida_id"] = "estado"
    assert "duvida_duplicada" in _codigos(revisar_esqueleto(_plano(arq)).bloqueantes)


def test_proxima_duvida_sem_destino_que_a_resolva_bloqueia():
    arq = arquitetura()
    _wb(arq, "renda")["jornada"]["proxima_duvida"] = "inscricao"
    assert "proxima_duvida_sem_destino" in _codigos(
        revisar_esqueleto(_plano(arq)).bloqueantes)


# ---------------------------------------------------------------------------
# [C12] falha estrutural conhecida não gasta com redação
# ---------------------------------------------------------------------------

def test_c12_falha_estrutural_antes_da_redacao_nao_faz_chamada_paga(tmp_path):
    arq = arquitetura()
    _link(arq, "estado", "renda", "Refazer a conta da renda")
    settings = settings_do_cenario(tmp_path)
    state, _deps, llm = rodar_cenario(tmp_path, arq, settings)
    assert llm.calls == [], [c["model"] for c in llm.calls]
    grafo = state.step_status["funnel_graph"]
    assert grafo.status.value == "FAILED"
    assert "cta_repetido_apos_resolvido" in _codigos(grafo.issues)
    assert not state.drafts


@pytest.fixture
def settings_minimas(tmp_path):
    return settings_do_cenario(tmp_path)
