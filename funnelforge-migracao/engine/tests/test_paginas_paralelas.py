"""REDAÇÃO PARALELA SEGURA — casos [12]..[17] da missão e o benchmark
hermético serial × paralelo (dublês que dormem; nada sai para a rede)."""
from __future__ import annotations

import json
import threading
import time

import pytest

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import RunState
from funnelforge.pipeline import paralelo as par
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.budget import Orcamento
from funnelforge.pipeline.pipeline import run_pipeline
from funnelforge.ports.llm import LLMResult
from tests.cenario_editorial import (
    congelar_data,
    montar_deps,
    ordem_do_run,
    prompts_do_run,
    responder_v2,
    settings_do_cenario,
    texto_da_mensagem,
)
from tests.test_dossie_factual import (
    FATOS_COMPLETOS,
    _arq_com_requisito_de_renda,
    _ligar_pesquisa,
    _Pesquisa,
)

ESPERA_S = 0.03
_dormir = time.sleep      # o conftest troca `time.sleep` por no-op; o benchmark precisa dormir


class _Medidor:
    """Responder que dorme e mede quantas chamadas estão em voo ao mesmo tempo."""

    def __init__(self, base=responder_v2, espera=ESPERA_S, falhar_em=None):
        self.base, self.espera, self.falhar_em = base, espera, falhar_em
        self.trava = threading.Lock()
        self.em_voo = self.pico = 0
        self.threads: set[str] = set()

    def __call__(self, model, messages):
        prompt = texto_da_mensagem(messages[-1])
        with self.trava:
            self.em_voo += 1
            self.pico = max(self.pico, self.em_voo)
            self.threads.add(threading.current_thread().name)
        try:
            _dormir(self.espera)
            if self.falhar_em and self.falhar_em in prompt and "PÁGINA" in prompt:
                raise RuntimeError("provedor caiu nesta página")
            return self.base(model, messages)
        finally:
            with self.trava:
                self.em_voo -= 1


def _settings(tmp_path, workers):
    s = settings_do_cenario(tmp_path / f"w{workers}", editorial_v2=True, passos_v2=True)
    s.steps["dossie"] = StepConfig(model="gemini/gemini-3.8-flash", web_search=True,
                                   temperature=0.2)
    s.run.dossie_factual = True
    s.run.imagens_habilitadas = False
    s.run.page_workers = workers
    return s


def _rodar(tmp_path, monkeypatch, workers, *, medidor=None, orcamento=None, publish=False,
           publisher=None):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
    medidor = medidor or _Medidor()
    settings = _settings(tmp_path, workers)
    llm, deps = montar_deps(tmp_path / f"w{workers}", settings, medidor)
    deps.runner.budget = orcamento
    deps.publisher = publisher
    plano = plano_do_funnel_architecture(_arq_com_requisito_de_renda())
    inicio = time.monotonic()
    state = run_pipeline(None, deps, only=None, publish=publish, plan=plano,
                         timestamp="20261007-120000")
    return state, deps, medidor, time.monotonic() - inicio


def _saida(state: RunState, deps) -> dict:
    """O que o run produziu, sem a telemetria do próprio paralelismo."""
    ordem = ordem_do_run(deps.runner.runs_dir, state.run_id, state)
    return {
        "drafts": {n: d.content for n, d in sorted(state.drafts.items())},
        "seo": dict(sorted(state.seo.items())),
        "revisoes": {n: r.get("decisao") for n, r in sorted(state.revisoes.items())},
        "recibos": sorted(state.recibos),
        "step_status": [s for s in ordem["step_status"] if not s.startswith("paginas_paralelas")],
        "chamadas_llm": ordem["chamadas_llm"],
        "prompts": prompts_do_run(deps.runner.runs_dir, state.run_id),
        "dossie": state.dossie_sha256,
        "revisao_global": state.revisao_global.get("paginas_bloqueadas"),
    }


# [12] ------------------------------------------------------------------------

def test_12_page_workers_1_e_o_laco_serial_de_sempre(tmp_path, monkeypatch):
    state, deps, medidor, _ = _rodar(tmp_path, monkeypatch, 1)
    assert "paginas_paralelas" not in state.step_status
    assert not (deps.runner.runs_dir / state.run_id / "paginas").exists()
    assert medidor.threads == {"MainThread"} and medidor.pico == 1


def test_12_paralelo_sem_dossie_e_erro_de_configuracao():
    from funnelforge.config.settings import RunConfig
    with pytest.raises(ValueError, match="page_workers > 1 exige run.dossie_factual"):
        RunConfig(page_workers=3)
    with pytest.raises(ValueError):
        RunConfig(page_workers=4, dossie_factual=True)


# [13] [15] -------------------------------------------------------------------

def test_13_e_15_paralelo_respeita_o_teto_e_produz_o_mesmo_funil(tmp_path, monkeypatch):
    serial, deps_s, _, _ = _rodar(tmp_path, monkeypatch, 1)
    paralelo, deps_p, medidor, _ = _rodar(tmp_path, monkeypatch, 3)
    assert 1 < medidor.pico <= 3, medidor.pico
    assert len([t for t in medidor.threads if t.startswith("pagina")]) <= 3
    tele = paralelo.step_status["paginas_paralelas"]
    assert tele.status.value == "OK" and "workers=3" in tele.issues[0].message
    a, b = _saida(serial, deps_s), _saida(paralelo, deps_p)
    for chave in a:
        assert a[chave] == b[chave], chave            # mesmos textos, ordem, prompts


# [14] ------------------------------------------------------------------------

def test_14_worker_nao_grava_estado_nem_log_global(tmp_path, monkeypatch):
    escritas: list[tuple[str, str]] = []
    from funnelforge.pipeline.runner import Runner
    original_ck, original_log = Runner.checkpoint, Runner.log

    def ck(self, run_id, js):
        if type(self) is Runner:
            escritas.append(("state", threading.current_thread().name))
        return original_ck(self, run_id, js)

    def lg(self, run_id, entry):
        if type(self) is Runner:
            escritas.append(("log", threading.current_thread().name))
        return original_log(self, run_id, entry)

    monkeypatch.setattr(Runner, "checkpoint", ck)
    monkeypatch.setattr(Runner, "log", lg)
    state, deps, _, _ = _rodar(tmp_path, monkeypatch, 3)
    assert escritas and {t for _, t in escritas} == {"MainThread"}
    raiz = deps.runner.runs_dir / state.run_id / "paginas"
    for pasta in raiz.iterdir():
        n = int(pasta.name[1:])
        passos = [json.loads(l)["step"] for l in (pasta / "log.jsonl").read_text().splitlines()]
        assert passos and all(par.chave_da_pagina(p, n) for p in passos), (pasta.name, passos)
        assert all(par.chave_da_pagina(p.stem, n) for p in (pasta / "prompts").glob("*.txt"))


def test_14_delta_fora_da_pagina_e_violacao_e_nao_e_aplicado():
    from funnelforge.domain.models import PageDraft, StepResult, StepStatus
    from tests.test_dossie_factual import _estado
    antes = _estado()
    depois = antes.model_copy(deep=True)
    page = depois.plan.pages[1]
    depois.drafts[2] = PageDraft(page_number=2, page_type="x", format="gutenberg", content="a")
    depois.drafts[3] = PageDraft(page_number=3, page_type="x", format="gutenberg", content="b")
    depois.step_status["write_p2"] = StepResult(step="write_p2", status=StepStatus.OK)
    depois.step_status["revisao_global"] = StepResult(step="revisao_global", status=StepStatus.OK)
    delta = par.extrair_delta(antes, depois, page, sinal=None, publicar=False, duracao_s=0)
    assert delta.violacoes == ["drafts[3]", "step_status[revisao_global]"]
    assert set(delta.campos["drafts"]) == {2} and set(delta.passos) == {"write_p2"}


def test_15_unicidade_entre_paginas_do_lote_tem_o_veredito_do_serial(tmp_path, monkeypatch):
    """Limiar zero: todo par é "parecido". Desde 10/10/2026 a similaridade
    lexical é observação para o revisor, não condenação: serial e paralelo
    chegam ao mesmo veredito, nenhuma página cai por isso e todas seguem."""
    vereditos = {}
    for workers in (1, 3):
        settings = _settings(tmp_path / "u", workers)
        settings.uniqueness.jaccard_threshold = 0.0
        settings.uniqueness.hub_distinction_threshold = 0.0
        congelar_data(monkeypatch)
        _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
        _, deps = montar_deps(tmp_path / "u" / f"w{workers}", settings, _Medidor(espera=0))
        state = run_pipeline(None, deps, only=None, publish=False,
                             plan=plano_do_funnel_architecture(_arq_com_requisito_de_renda()),
                             timestamp="20261007-120000")
        falhou = {k for k, r in state.step_status.items() if r.status.value == "FAILED"}
        vereditos[workers] = {
            "condenadas": sorted(p.page_number for p in state.plan.pages if {
                f"write_p{p.page_number}", f"page_{p.page_number}"} & falhou),
            "seo": sorted(k for k in state.step_status if k.startswith("seo_p")),
            "revisor": sorted(state.revisoes),
            "drafts_ok": sorted(n for n in state.drafts if f"write_p{n}" not in falhou
                                and f"page_{n}" not in falhou),
            "observadas": sorted(n for n in state.drafts if any(
                i.code == "similaridade_lexical"
                for i in state.step_status[f"write_p{n}"].issues)),
        }
    assert vereditos[1] == vereditos[3]
    assert vereditos[3]["condenadas"] == []
    assert vereditos[3]["drafts_ok"] == [1, 2, 3, 4, 5]
    assert vereditos[3]["observadas"] == [2, 3, 4, 5]     # cada uma contra as anteriores
    assert vereditos[3]["seo"] == [f"seo_p{n}" for n in (1, 2, 3, 4, 5)]


# [16] ------------------------------------------------------------------------

class _Precificado:
    """LLM que cobra US$ 0,01 por chamada — contabilidade exata."""

    def __init__(self, llm):
        self.llm, self.chamadas, self.trava = llm, 0, threading.Lock()

    def complete(self, *a, **kw):
        res = self.llm.complete(*a, **kw)
        with self.trava:
            self.chamadas += 1
        return LLMResult(text=res.text, model_used=res.model_used, cost_usd=0.01)


def test_16_chamadas_e_custo_batem_exatamente_no_paralelo(tmp_path, monkeypatch):
    resultados = {}
    for workers in (1, 3):
        congelar_data(monkeypatch)
        _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
        settings = _settings(tmp_path, workers)
        llm, deps = montar_deps(tmp_path / f"w{workers}", settings, _Medidor(espera=0.005))
        caro = _Precificado(llm)
        deps.llm = deps.runner.llm = caro
        orc = Orcamento(teto_run_usd=10.0, teto_pagina_usd=5.0)
        deps.runner.budget = orc
        state = run_pipeline(None, deps, only=None, publish=False,
                             plan=plano_do_funnel_architecture(_arq_com_requisito_de_renda()),
                             timestamp="20261007-120000")
        ledger = round(sum(r.cost_usd for k, r in state.step_status.items()
                           if k != "dossie" and k != "paginas_paralelas"), 6)
        fora = round(sum(r.cost_usd for k, r in state.step_status.items()
                         if k not in ("dossie", "paginas_paralelas")
                         and not any(par.chave_da_pagina(k, p.page_number)
                                     for p in state.plan.pages)), 6)
        pesquisas = len(state.dossie["pesquisa"])           # global + sob demanda
        resultados[workers] = (caro.chamadas, round(orc.gasto_run_usd, 6), ledger, fora,
                               dict(sorted(orc.gasto_por_pagina.items())), pesquisas)
    chamadas, gasto, ledger, fora, por_pagina, pesquisas = resultados[3]
    assert resultados[1] == resultados[3]
    assert gasto == pytest.approx(0.01 * chamadas + 0.002 * pesquisas)  # + as pesquisas
    assert ledger == pytest.approx(0.01 * chamadas)                  # nenhuma chamada sem dono
    assert fora == pytest.approx(0.01)                               # engajamento, antes do laço
    assert sum(por_pagina.values()) + fora == pytest.approx(ledger, abs=1e-6)


# [17] ------------------------------------------------------------------------

def test_17_falha_de_uma_pagina_nao_derruba_as_outras(tmp_path, monkeypatch):
    # A URL da própria página não entra no prompt do writer. Antes este teste
    # não injetava a falha: passava por um veto editorial incidental.
    alvo = "Tema/headline: Tipos de curso do Senac e como escolher o seu"
    medidor = _Medidor(falhar_em=alvo)
    serial, deps_s, _, _ = _rodar(tmp_path, monkeypatch, 1, medidor=_Medidor(
        falhar_em=alvo))
    paralelo, deps_p, _, _ = _rodar(tmp_path, monkeypatch, 3, medidor=medidor)
    falhas_s = sorted(k for k, r in serial.step_status.items() if r.status.value == "FAILED")
    falhas_p = sorted(k for k, r in paralelo.step_status.items() if r.status.value == "FAILED")
    assert falhas_s == falhas_p and falhas_p, falhas_p
    assert sorted(serial.drafts) == sorted(paralelo.drafts)
    assert len(paralelo.drafts) >= 3


def test_17_publicacao_so_depois_da_revisao_global_e_na_thread_principal(tmp_path, monkeypatch):
    eventos: list[tuple] = []
    original = st.step_publish

    def gravar(state, page, deps):
        eventos.append((page.page_number, bool(state.revisao_global),
                        threading.current_thread().name))
        return original(state, page, deps)

    monkeypatch.setattr(st, "step_publish", gravar)

    class _Publicador:
        def __getattr__(self, nome):
            raise AssertionError("o teste não deixa nada ir ao WordPress")

    state, _, _, _ = _rodar(tmp_path, monkeypatch, 3, publish=True, publisher=_Publicador())
    assert state.revisao_global, "revisão global não rodou"
    assert all(rg and t == "MainThread" for _, rg, t in eventos), eventos
    assert [n for n, *_ in eventos] == sorted(n for n, *_ in eventos)


# BENCHMARK ---------------------------------------------------------------------

def test_benchmark_hermetico_serial_x_paralelo(tmp_path, monkeypatch, capsys):
    serial, deps_s, med_s, t_s = _rodar(tmp_path, monkeypatch, 1, medidor=_Medidor(espera=0.05))
    paralelo, deps_p, med_p, t_p = _rodar(tmp_path, monkeypatch, 3, medidor=_Medidor(espera=0.05))
    assert _saida(serial, deps_s) == _saida(paralelo, deps_p)
    chamadas = len(_saida(serial, deps_s)["chamadas_llm"])
    with capsys.disabled():
        print(f"\n[benchmark] chamadas={chamadas} espera=0.05s serial={t_s:.2f}s "
              f"paralelo(3)={t_p:.2f}s ganho={t_s / t_p:.2f}x pico={med_p.pico}")
    assert t_p < t_s * 0.75
