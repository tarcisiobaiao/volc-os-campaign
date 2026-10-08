"""Evidência por estado e dossiê como CACHE: pesquisa sob demanda por lacuna,
deduplicação, degradação segura e bloqueio só da página afetada."""
from __future__ import annotations

import threading
import time

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.dossie import DossieDoFunil
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.dossie import CompiladorDeDossie, RespostaDaPesquisa
from funnelforge.pipeline.pipeline import run_pipeline
from tests.cenario_editorial import congelar_data, montar_deps, responder_v1, rodar_cenario
from tests.test_dossie_factual import (
    CITADAS,
    FATOS_COMPLETOS,
    MA,
    PLANALTO,
    RENDA,
    _arq_com_requisito_de_renda,
    _Deps,
    _estado,
    _fato,
    _ler,
    _ligar_pesquisa,
    _n,
    _Pesquisa,
    _registrar_canais,
    _settings_com_dossie,
    _Verificador,
)

_dormir = time.sleep              # o conftest troca `time.sleep` por no-op
SEM_RENDA = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
REGRA = [f for f in FATOS_COMPLETOS if RENDA in f["requisitos"]]


def _dossie(state):
    return DossieDoFunil.model_validate(state.dossie)


# --- pesquisa sob demanda ----------------------------------------------------

def test_pesquisa_sob_demanda_com_citacao_valida_entra_no_dossie(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(SEM_RENDA, REGRA))
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                _settings_com_dossie(tmp_path))
    n = _n(state, "renda")
    dossie = _dossie(state)
    assert dossie.pagina(n).cobertura.estado in ("ready", "degraded")
    assert any(f.status == "verified" and RENDA in f.requisitos for f in dossie.fatos)
    assert [t.pagina for t in dossie.pesquisa] == [0, n]       # global + a da p2
    assert "renda.limite_per_capita" in state.step_status[f"dossie_complemento_p{n}"] \
        .issues[0].message


def test_pesquisa_sem_citacao_nao_entra_no_dossie(tmp_path, monkeypatch):
    congelar_data(monkeypatch)

    class _SemCitacao(_Pesquisa):
        def __call__(self, assunto, spec, faltantes):
            resp = super().__call__(assunto, spec, faltantes)
            if faltantes:
                resp.citacoes = []                # complementação sem citação do provedor
            return resp

    _ligar_pesquisa(monkeypatch, _SemCitacao(SEM_RENDA, REGRA))
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                _settings_com_dossie(tmp_path))
    dossie = _dossie(state)
    renda = [f for f in dossie.fatos if RENDA in f.requisitos]
    assert renda and all(f.status != "verified" for f in renda)
    assert all("não citada pelo grounding" in f.motivo_do_status for f in renda)
    assert dossie.pagina(_n(state, "renda")).cobertura.estado == "review"


def test_duas_buscas_simultaneas_pela_mesma_lacuna_sao_deduplicadas():
    """Duas páginas com o MESMO requisito faltando: uma busca, a outra espera."""
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        j = job["writer_briefing"]["jornada"]
        if j["duvida_id"] == "curso":
            j["requisitos"].append({"id": RENDA, "descricao": "limite de renda", "tipos":
                                    ["numero", "condicao"]})
    state = _estado(arq)
    chamadas, liberar = [], threading.Event()

    def pesquisar(assunto, spec, faltantes):
        chamadas.append(faltantes)
        if faltantes:
            liberar.wait(5)
            fatos = [dict(f, paginas=["renda", "curso"]) for f in REGRA]
        else:
            fatos = SEM_RENDA
        return RespostaDaPesquisa(dados={"fatos": fatos}, citacoes=list(CITADAS),
                                  modelo_pedido="m", modelo_servido="m")

    comp = CompiladorDeDossie(state, _Deps(_Verificador()), pesquisar,
                              registrar_canais=_registrar_canais, ler_documento=_ler)
    comp.compilar(complementos=0)
    paginas = {p.jornada.duvida_id: p for p in state.plan.pages}
    resultados = {}

    def worker(nome):
        resultados[nome] = comp.complementar_pagina(paginas[nome], state.model_copy(deep=True))

    t1 = threading.Thread(target=worker, args=("renda",))
    t2 = threading.Thread(target=worker, args=("curso",))
    t1.start()
    _dormir(0.1)
    t2.start()
    _dormir(0.1)
    liberar.set()
    t1.join(5)
    t2.join(5)
    complementos = [c for c in chamadas if c]
    assert len(complementos) == 1 and comp.deduplicadas == 1
    assert RENDA in resultados["renda"]["resolvidas"] and RENDA in resultados["curso"]["resolvidas"]


# --- degradação e bloqueio local ---------------------------------------------

def test_conflito_material_bloqueia_so_a_pagina_afetada(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    divergente = _fato("Renda per capita de até 1,5 salário mínimo", MA, ["renda"], [RENDA],
                       tipo="condicao", valor="1,5", unidade="salários mínimos")
    _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS + [divergente],
                                           citacoes=CITADAS + [MA]))
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                _settings_com_dossie(tmp_path))
    n = _n(state, "renda")
    assert state.step_status[f"dossie_p{n}"].status.value == "FAILED"
    assert n not in state.drafts
    outras = [p.page_number for p in state.plan.pages if p.page_number != n]
    assert all(m in state.drafts for m in outras)                 # o resto do funil segue
    assert all(state.step_status[f"dossie_p{m}"].status.value == "OK" for m in outras)


def test_regressao_senac_valor_indisponivel_degrada_so_o_detalhe(tmp_path, monkeypatch):
    """Regra comprovada, salário mínimo indisponível (fonte recusa o UA): a
    renda é escrita sem o valor em reais, a ferramenta do valor sai, e p1, p3,
    p4 e p5 são escritas."""
    congelar_data(monkeypatch)
    sm = [f for f in FATOS_COMPLETOS if "salario_minimo.vigente" in f["requisitos"]]
    sem_sm_nem_literal = [f for f in FATOS_COMPLETOS if f not in sm
                          and "renda.valor_vigente" not in f["requisitos"]]

    class _WAF(_Verificador):
        def bloqueada(self, url):
            return url == sm[0]["fonte"]

    _ligar_pesquisa(monkeypatch, _Pesquisa(sem_sm_nem_literal + sm, []))
    settings = _settings_com_dossie(tmp_path)
    from funnelforge.pipeline import dossie as pd
    original = pd.verificar_ao_vivo
    monkeypatch.setattr(pd, "verificar_ao_vivo", lambda fatos, v, hoje: original(
        fatos, _WAF(vivas=[u for u in CITADAS if u != sm[0]["fonte"]]), hoje))
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(), settings)
    n = _n(state, "renda")
    cob = _dossie(state).pagina(n).cobertura
    estados = {r.requisito_id: r.estado for r in cob.requisitos}
    assert estados[RENDA] == "verified" and estados["salario_minimo.vigente"] == "unavailable"
    assert cob.estado == "degraded" and not cob.requer_revisao
    assert any(d["tipo"] == "ativo" for d in cob.desativados)
    assert all(p.page_number in state.drafts for p in state.plan.pages)
    assert state.step_status[f"widget_p{n}"].status.value == "SKIPPED" if \
        f"widget_p{n}" in state.step_status else True


def test_nenhuma_pagina_em_revisao_por_evidencia_e_publicada(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(SEM_RENDA, []))
    publicadas = []
    monkeypatch.setattr(st, "step_publish", lambda state, page, deps: publicadas.append(
        page.page_number))
    settings = _settings_com_dossie(tmp_path)
    llm, deps = montar_deps(tmp_path, settings, responder_v1)
    deps.publisher = object()
    state = run_pipeline(None, deps, only=None, publish=True,
                         plan=plano_do_funnel_architecture(_arq_com_requisito_de_renda()),
                         timestamp="20261007-120000")
    n = _n(state, "renda")
    assert _dossie(state).pagina(n).cobertura.estado == "review" and n in state.drafts
    assert n not in publicadas
    assert state.step_status[f"evidencia_p{n}"].issues[0].code == "revisao_humana_por_evidencia"


# --- paralelismo -----------------------------------------------------------------

def test_paginas_independentes_sao_escritas_enquanto_outra_pesquisa(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    linha_do_tempo: list[tuple[str, float]] = []
    trava = threading.Lock()

    def pesquisar(assunto, spec, faltantes):
        if faltantes:
            with trava:
                linha_do_tempo.append(("pesquisa_inicio", time.monotonic()))
            _dormir(0.4)
            with trava:
                linha_do_tempo.append(("pesquisa_fim", time.monotonic()))
            fatos = REGRA
        else:
            fatos = SEM_RENDA
        return RespostaDaPesquisa(dados={"fatos": fatos}, citacoes=list(CITADAS),
                                  modelo_pedido="gemini/gemini-3.8-flash",
                                  modelo_servido="gemini-3.8-flash")

    _ligar_pesquisa(monkeypatch, pesquisar)

    def responder(model, messages):
        with trava:
            linha_do_tempo.append(("chamada", time.monotonic()))
        return responder_v1(model, messages)

    settings = _settings_com_dossie(tmp_path)
    settings.run.page_workers = 3
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(), settings,
                                responder=responder)
    inicio = next(t for e, t in linha_do_tempo if e == "pesquisa_inicio")
    fim = next(t for e, t in linha_do_tempo if e == "pesquisa_fim")
    durante = [t for e, t in linha_do_tempo if e == "chamada" and inicio < t < fim]
    assert durante, "nenhuma página escreveu enquanto a p2 pesquisava"
    assert all(p.page_number in state.drafts for p in state.plan.pages)
    assert _dossie(state).pagina(_n(state, "renda")).cobertura.estado in ("ready", "degraded")


def test_canal_oficial_verificado_em_outra_pagina_fortalece_a_evidencia_da_lp():
    """A LP não tem saída oficial; a fonte do mesmo publicador que a jornada
    verificou como canal de outra página é oficial para ela também."""
    from funnelforge.domain.dossie import FatoDoDossie
    from funnelforge.pipeline.dossie import cobertura_da_pagina
    state = _estado()
    lp = next(p for p in state.plan.pages if p.jornada.duvida_id == "senac_gratuito")
    estado = next(p for p in state.plan.pages if p.jornada.duvida_id == "estado")
    fato = FatoDoDossie(fact_id="f_" + "b" * 12, afirmacao="O PSG atende famílias de baixa renda",
                        tipo="condicao", source_url="https://www.exemplo-oficial.gov/psg",
                        status="verified", paginas=["senac_gratuito"],
                        requisitos=["psg.quem_atende"])
    assert cobertura_da_pagina(state, lp, [fato]).requisitos[0].estado == "unsupported"
    state.official_links[estado.page_number] = ["https://www.exemplo-oficial.gov/canal"]
    assert cobertura_da_pagina(state, lp, [fato]).requisitos[0].estado == "verified"


def test_resposta_principal_de_paginas_diferentes_nao_e_deduplicada():
    """Card real #65: sem requisitos declarados, toda página tem o requisito
    derivado `resposta_principal` — que é a pergunta DELA. A p5 esperou a busca
    da p4 e ficou sem pesquisa."""
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        job["writer_briefing"]["jornada"]["requisitos"] = []
    state = _estado(arq)
    pedidos = []

    def pesquisar(assunto, spec, faltantes):
        pedidos.append([f["duvida_id"] for f in faltantes or []])
        return RespostaDaPesquisa(dados={"fatos": []}, citacoes=[], modelo_pedido="m",
                                  modelo_servido="m")

    comp = CompiladorDeDossie(state, _Deps(_Verificador()), pesquisar,
                              registrar_canais=_registrar_canais, ler_documento=_ler)
    comp.compilar(complementos=0)
    for p in state.plan.pages[:2]:
        comp.complementar_pagina(p, state.model_copy(deep=True))
    duvidas = [p.jornada.duvida_id for p in state.plan.pages[:2]]
    # cada página pesquisa a PRÓPRIA pergunta; ninguém espera a busca alheia
    assert [set(p) for p in pedidos[1:]] == [{duvidas[0]}, {duvidas[1]}]
    assert comp.deduplicadas == 0


def test_pre_voo_respeita_a_saida_oficial_desativada_pelo_dossie():
    from funnelforge.domain.models import PageRole
    from funnelforge.pipeline.preflight import _preflight_official_links
    ctx = {"role": PageRole.SOLUTION, "is_terminal": False, "official_links": []}
    assert [i.code for i in _preflight_official_links(ctx)] == ["official_links_none"]
    assert _preflight_official_links(dict(ctx, saida_oficial_exigida=False)) == []
