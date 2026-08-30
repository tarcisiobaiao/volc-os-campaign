"""FRENTE 3 — retentativa inteligente e fim do dinheiro jogado fora.

Cinco defeitos medidos, cinco travas aqui:

1. tudo era retentado igual — 401 e "faltou uma ponte antes do CTA" gastavam o
   mesmo número de chamadas (`retry_policy`);
2. a ORDEM pagava pesquisa + até 3 redações + juiz para descobrir uma
   reprovação que já estava decidida nas rotas (`preflight`);
3. a PESQUISA não tinha retentativa nenhuma: um 429 matava a página com o
   extract já pago (`run.research_max_attempts`);
4. não existia teto: um laço em fuga gastava até acabar (`budget`);
5. o ledger mentia para menos — a imagem não entrava e a tentativa que morria
   levava o custo junto no traceback.
"""
from __future__ import annotations

from pathlib import Path

from funnelforge.config.settings import (
    BudgetConfig, RunConfig, Secrets, Settings, SiteConfig, StepConfig,
)
from funnelforge.domain.models import (
    FunnelPlan, Issue, Page, PageRole, ResearchFacts, Route, RunState, StepStatus,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.budget import Orcamento, OrcamentoEstourado
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.preflight import preflight_issues
from funnelforge.pipeline.retry_policy import classificar_excecao, classificar_issues
from funnelforge.pipeline.runner import LLMStepError, Runner
from funnelforge.ports.llm import LLMResult
from tests.fakes import FakeLLM


class _LLMQueDorme:
    """LLM que sempre levanta o MESMO erro, contando as chamadas."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.chamadas = 0

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        self.chamadas += 1
        raise self._exc


class _LLMPago:
    """Devolve texto reprovado, cobrando US$ 0,10 por chamada."""

    def __init__(self, texto: str) -> None:
        self._texto = texto
        self.chamadas = 0

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        self.chamadas += 1
        return LLMResult(text=self._texto, model_used=model, prompt_tokens=10,
                         completion_tokens=5, cost_usd=0.10, latency_ms=100)


_CFG = StepConfig(model="m", fallbacks=[], temperature=0.0, validators=["language_pt"])


# ---------------------------------------------------------------------------
# 1. classificação
# ---------------------------------------------------------------------------


def test_erro_terminal_do_provedor_nao_e_retentado() -> None:
    assert classificar_excecao(RuntimeError("AuthenticationError: bad key")).retentar is False
    assert classificar_excecao(RuntimeError("ContextWindowExceededError")).retentar is False
    assert classificar_excecao(AssertionError("prompt não roteirizado")).retentar is False


def test_erro_transitorio_do_provedor_e_retentado() -> None:
    v = classificar_excecao(RuntimeError("OpenAIException: InternalServerError"))
    assert v.retentar is True and v.classe == "transitorio"
    assert classificar_excecao(RuntimeError("RateLimitError 429")).retentar is True


def test_reprovacao_de_rota_e_terminal_mas_defeito_de_texto_e_recuperavel() -> None:
    # `cta_too_few` vem do pagespec, que valida `page.routes` -- reescrever
    # devolve exatamente a mesma reprovação.
    assert classificar_issues([Issue(code="cta_too_few", message="x")], {}).retentar is False
    assert classificar_issues([Issue(code="language_pt", message="x")], {}).retentar is True
    # official_links_few só é terminal quando NÃO existe link oficial nenhum.
    sem = classificar_issues([Issue(code="official_links_few", message="x")],
                             {"official_links": []})
    com = classificar_issues([Issue(code="official_links_few", message="x")],
                             {"official_links": ["https://gov.br/x"]})
    assert sem.retentar is False and com.retentar is True


# ---------------------------------------------------------------------------
# 2. runner
# ---------------------------------------------------------------------------


def test_runner_nao_gasta_segunda_chamada_em_erro_terminal(tmp_path: Path) -> None:
    llm = _LLMQueDorme(RuntimeError("AuthenticationError: Incorrect API key"))
    r = Runner(llm=llm, max_retries=2, runs_dir=tmp_path, sleep=lambda _s: None)
    try:
        r.run_llm_step("w", _CFG, [{"role": "user", "content": "go"}], ctx={},
                       run_id="r-1")
    except LLMStepError as exc:
        assert exc.classe == "terminal"
    assert llm.chamadas == 1, "401 foi retentado — dinheiro e tempo por nada"


def test_runner_retenta_erro_transitorio_com_espera_crescente(tmp_path: Path) -> None:
    llm = _LLMQueDorme(RuntimeError("OpenAIException: InternalServerError"))
    esperas: list[float] = []
    r = Runner(llm=llm, max_retries=2, runs_dir=tmp_path, backoff_s=2.0,
               sleep=esperas.append)
    try:
        r.run_llm_step("w", _CFG, [{"role": "user", "content": "go"}], ctx={},
                       run_id="r-1")
    except LLMStepError as exc:
        assert exc.classe == "transitorio"
    assert llm.chamadas == 3
    assert esperas == [2.0, 4.0]


def test_runner_sela_o_passo_quando_a_reprovacao_nao_depende_do_texto(tmp_path) -> None:
    """Uma rota inválida reprova igual nas três tentativas: uma chamada só."""
    llm = _LLMPago("<!-- wp:paragraph --><p>ok</p><!-- /wp:paragraph -->")
    cfg = StepConfig(model="m", validators=["pagespec"])
    ctx = {"pagespec": {"role": "SOLUTION", "allowed_targets": ["funnel"],
                        "required_targets": ["funnel"], "forbidden_targets": [],
                        "cta_min": 3, "cta_max": 5},
           "parsed": {"routes": []}, "slug": "a-p1", "h1_by_slug": {}}
    r = Runner(llm=llm, max_retries=2, runs_dir=tmp_path, sleep=lambda _s: None)
    _, res = r.run_llm_step("write_p3", cfg, [{"role": "user", "content": "go"}],
                            ctx=ctx, run_id="r-1")
    assert res.status is StepStatus.FAILED
    assert llm.chamadas == 1, "reescreveu contra uma reprovação de rota"
    assert res.cost_usd == 0.10


def test_llm_step_error_carrega_o_que_ja_foi_pago(tmp_path: Path) -> None:
    """Duas tentativas pagas e a terceira morre: o ledger não pode perder as duas."""
    class _PagaDepoisMorre:
        def __init__(self) -> None:
            self.n = 0

        def complete(self, model, fallbacks, messages, temperature,
                     response_schema=None, web_search=False):
            self.n += 1
            if self.n <= 2:
                return LLMResult(text="Ingreso", model_used=model, prompt_tokens=10,
                                 completion_tokens=5, cost_usd=0.10, latency_ms=100)
            raise RuntimeError("AuthenticationError: chave revogada no meio do run")

    llm = _PagaDepoisMorre()
    r = Runner(llm=llm, max_retries=5, runs_dir=tmp_path, sleep=lambda _s: None)
    try:
        r.run_llm_step("w", _CFG, [{"role": "user", "content": "go"}], ctx={},
                       run_id="r-1")
        raise AssertionError("deveria ter levantado")
    except LLMStepError as exc:
        assert abs(exc.step_result.cost_usd - 0.20) < 1e-9
        assert exc.step_result.prompt_tokens == 20


# ---------------------------------------------------------------------------
# 3. pré-voo
# ---------------------------------------------------------------------------


def _settings_com_official() -> Settings:
    from funnelforge.config.settings import RoutingSpecConfig

    return Settings(
        secrets=Secrets(), run=RunConfig(),
        site=SiteConfig(domain="https://creditoup.com.br",
                        allowed_external=["https://www.gov.br"]),
        steps={"write_page": StepConfig(model="m",
                                        validators=["official_link_density"]),
               "research": StepConfig(model="m")},
        routing={"SOLUTION": RoutingSpecConfig(
            allowed_targets=["funnel", "external_official"],
            required_targets=["funnel"], forbidden_targets=[], cta_min=1, cta_max=5)},
    )


def test_preflight_barra_solucao_sem_nenhum_link_oficial() -> None:
    ctx = {"role": PageRole.SOLUTION, "is_terminal": False, "official_links": []}
    issues = preflight_issues(["official_link_density"], ctx)
    assert [i.code for i in issues] == ["official_links_none"]


def test_preflight_nao_inventa_exigencia_fora_da_lista_do_passo() -> None:
    """A LP tem `validators: []` -> nenhum pré-voo, exatamente como antes."""
    ctx = {"role": PageRole.SOLUTION, "is_terminal": False, "official_links": []}
    assert preflight_issues([], ctx) == []


def test_step_write_nao_chama_o_redator_quando_a_pesquisa_nao_deu_link_oficial(
        tmp_path: Path) -> None:
    settings = _settings_com_official()
    llm = FakeLLM(responses=[])
    runner = Runner(llm=llm, max_retries=2, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=None, settings=settings, runner=runner)
    page = Page(page_number=3, page_type="SOLUTION", h1_title="Como sacar",
                slug="a-p1", ordinal=1, role=PageRole.SOLUTION,
                routes=[Route(placement="body", kind="funnel", target="a-p2",
                              anchor="Como sacar")])
    # Uma segunda solução para que `page` NÃO seja a terminal (a terminal é
    # isenta da densidade de link oficial).
    seguinte = Page(page_number=4, page_type="SOLUTION", h1_title="Prazos",
                    slug="a-p2", ordinal=2, role=PageRole.SOLUTION)
    state = RunState(run_id="a-20260815-101010")
    state.plan = FunnelPlan(total_pages=2, pages=[page, seguinte])
    # pesquisa OK no gate, mas SEM nenhuma fonte oficial elegível.
    #
    # Não basta dar uma fonte "não-oficial": com a chave AUSENTE em
    # `official_links`, o fallback offline recalcula por proveniência pura e
    # aceitaria o próprio blog como canal — o pré-voo passaria e o teste mediria
    # outra coisa. A chave PRESENTE e vazia é como se diz, no contrato novo,
    # "a pesquisa rodou e não elegeu canal nenhum".
    state.facts[3] = ResearchFacts(fontes=["https://blog.qualquer.com/x"])
    state.official_links[3] = []

    st.step_write(state, page, deps)

    assert state.step_status["write_p3"].status is StepStatus.FAILED
    assert [i.code for i in state.step_status["write_p3"].issues] == ["official_links_none"]
    assert llm.calls == [], "pagou o redator por uma reprovação já decidida"


# ---------------------------------------------------------------------------
# 4. pesquisa com retentativa
# ---------------------------------------------------------------------------


class _PesquisaInstavel:
    """Falha nas duas primeiras chamadas, acerta na terceira."""

    def __init__(self) -> None:
        self.n = 0
        self.last_cost_usd = 0.0

    def research(self, topic: str, structure: str) -> ResearchFacts:
        self.n += 1
        self.last_cost_usd = 0.01
        if self.n < 3:
            return ResearchFacts(sparse=True)
        return ResearchFacts(resumo="r", fontes=["https://www.gov.br/fgts"])


def _settings_pesquisa(tentativas: int) -> Settings:
    return Settings(
        secrets=Secrets(),
        run=RunConfig(research_max_attempts=tentativas, research_backoff_s=1.0),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"research": StepConfig(model="m")},
    )


def test_pesquisa_instavel_e_retentada_e_a_conta_soma_as_tentativas(tmp_path) -> None:
    settings = _settings_pesquisa(3)
    esperas: list[float] = []
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0,
                    runs_dir=tmp_path / "runs", sleep=esperas.append)
    provider = _PesquisaInstavel()
    deps = Deps(llm=runner.llm, research=provider, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="a-20260815-101010")
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS", slug="a")

    st.step_research(state, page, deps)

    res = state.step_status["research_p1"]
    assert res.status is StepStatus.OK
    assert provider.n == 3 and res.attempts == 3
    assert esperas == [1.0, 2.0]
    # as duas tentativas que falharam TAMBÉM custaram e aparecem no ledger
    assert abs(res.cost_usd - 0.03) < 1e-9


def test_pesquisa_desiste_na_hora_quando_falta_o_verificador(tmp_path) -> None:
    """`fact_source_verifier_missing` é fiação: nenhuma busca nova liga o Chromium."""
    from datetime import date

    from funnelforge.domain.models import VerifiedFact

    class _ComFatoCritico:
        def __init__(self) -> None:
            self.n = 0

        def research(self, topic: str, structure: str) -> ResearchFacts:
            self.n += 1
            fonte = "https://www.gov.br/fgts"
            return ResearchFacts(
                fontes=[fonte],
                fatos_verificados=[VerifiedFact(
                    valor="10%", unidade="percentual", fonte_primaria=fonte,
                    dispositivo="não se aplica", vigente_desde=date.today(),
                    verificado_em=date.today())])

    settings = _settings_pesquisa(3)
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0,
                    runs_dir=tmp_path / "runs", sleep=lambda _s: None)
    provider = _ComFatoCritico()
    deps = Deps(llm=runner.llm, research=provider, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="a-20260815-101010")
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS", slug="a")

    st.step_research(state, page, deps)

    assert state.step_status["research_p1"].status is StepStatus.FAILED
    assert provider.n == 1, "retentou uma falha de fiação"


# ---------------------------------------------------------------------------
# 5. teto de custo + ledger
# ---------------------------------------------------------------------------


def test_orcamento_bloqueia_antes_da_chamada_e_nao_depois(tmp_path: Path) -> None:
    orc = Orcamento(teto_run_usd=0.05, teto_pagina_usd=1.0)
    llm = _LLMPago("Consulte seu saldo em 2026")
    r = Runner(llm=llm, max_retries=0, runs_dir=tmp_path, budget=orc)
    r.run_llm_step("w1", _CFG, [{"role": "user", "content": "go"}], ctx={}, run_id="r")
    assert llm.chamadas == 1 and orc.gasto_run_usd == 0.10
    try:
        r.run_llm_step("w2", _CFG, [{"role": "user", "content": "go"}], ctx={}, run_id="r")
        raise AssertionError("deveria ter abortado")
    except OrcamentoEstourado as exc:
        assert "Teto de custo do run" in str(exc)
    assert llm.chamadas == 1, "gastou depois de estourar o teto"


def test_imagem_entra_no_ledger_com_o_preco_declarado(tmp_path: Path) -> None:
    class _Gen:
        def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
            return b"img"

    class _Proc:
        def to_webp(self, data: bytes, out_path: Path, quality: int = 80) -> Path:
            out_path.write_bytes(data)
            return out_path

    settings = Settings(
        secrets=Secrets(), run=RunConfig(hero_image=True, image_quality="medium"),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"image": StepConfig(model="m")},
        budget=BudgetConfig(image_price_usd={"medium": 0.06}),
    )
    orc = Orcamento(teto_run_usd=10.0, teto_pagina_usd=10.0)
    runner = Runner(llm=FakeLLM(responses=["a photo prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs", budget=orc)
    deps = Deps(llm=runner.llm, research=None, image_gen=_Gen(), image_proc=_Proc(),
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="a-20260815-101010")
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS", slug="a")

    st.step_image(state, page, deps)

    # O custo da imagem entra como PASSO PRÓPRIO `image_gen_p1`, não somado no
    # `image_p1` (que é só a chamada de texto que escreve o prompt, centavos).
    # Foi a conciliação entre esta frente e a da telemetria: separar as duas
    # linhas é o que faz a despesa que PESA aparecer no relatório em vez de se
    # esconder atrás da que não pesa. E o valor é o MEDIDO pela tabela do
    # litellm; o preço declarado no config serve só para o teto decidir, antes
    # de gerar, se pode gastar.
    assert state.step_status["image_p1"].cost_usd == 0.0
    assert "image_gen_p1" in state.step_status
    assert abs(orc.gasto_run_usd - 0.06) < 1e-9


# ---------------------------------------------------------------------------
# 6. grafo quebrado não paga nada
# ---------------------------------------------------------------------------


def test_grafo_quebrado_aborta_o_funil_antes_de_qualquer_chamada_paga(
        tmp_path: Path, config_files: Path) -> None:
    """`funnel_graph` FAILED bloqueia build/publish de TODAS as páginas -- então
    pagar pesquisa/redação/juiz/seo delas é gastar por zero URL publicada."""
    from funnelforge.config.settings import load_settings

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    llm = FakeLLM(responses=[])
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=None, settings=settings, runner=runner)
    state = RunState(run_id="a-20260815-101010")
    state.plan = FunnelPlan(total_pages=2, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="LP", slug="a"),
        Page(page_number=2, page_type="SOLUTION", h1_title="S", slug="a-p1", ordinal=1),
    ])
    state.step_status["funnel_graph"] = st.StepResult(
        step="funnel_graph", status=StepStatus.FAILED,
        issues=[Issue(code="terminal_no_exit", message="sem saída cross-funnel")])

    out = run_pipeline(None, deps, publish=False, resume_state=state)

    assert llm.calls == [], "pagou um funil que nunca seria publicado"
    assert out.step_status["blocked_p1"].status is StepStatus.FAILED
    assert out.step_status["blocked_p2"].status is StepStatus.FAILED
    assert (tmp_path / "runs" / out.run_id / "report.md").exists()
