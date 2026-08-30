"""FRENTE 6 — telemetria honesta e o desacoplamento do Playwright.

Quatro defeitos medidos, quatro travas aqui:

1. a IMAGEM não entrava no ledger (saía por um `httpx.post` cru, fora do
   `run_llm_step`): agora vira o passo `image_gen_pN`, com o custo tirado da
   tabela do litellm;
2. o gate factual buscava o verificador em `deps.screenshot.verify_url`, e
   `deps.screenshot` só existe com `run.official_screenshots` ligado — desligar
   os prints reprovava TODA página com fato numérico;
3. `verify_url` não estava em Protocol nenhum: virou o port `UrlVerifier`;
4. cada URL de plataforma era visitada 2–3x por página (write -> content_gate
   -> publish): o cache por run mata a repetição.
"""
from datetime import date
from pathlib import Path

import httpx

from funnelforge.adapters.image_pricing import (
    FONTE_DESCONHECIDA,
    FONTE_POR_IMAGEM,
    FONTE_TOKENS,
    ImageUsage,
    image_cost_usd,
)
from funnelforge.adapters.url_verifier_http import HttpUrlVerifier
from funnelforge.config.settings import (
    RunConfig,
    Secrets,
    Settings,
    SiteConfig,
    StepConfig,
)
from funnelforge.domain.models import (
    Page,
    ResearchFacts,
    RunState,
    StepResult,
    StepStatus,
    VerifiedFact,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps, _profit_ledger
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM

# ---------------------------------------------------------------------------
# 1. preço da imagem — sem número inventado
# ---------------------------------------------------------------------------


def test_preco_por_tokens_de_uso_do_gpt_image_2():
    """`gpt-image-2` (default do RunConfig) é tarifado por TOKEN e NÃO tem
    entrada de preço por imagem na tabela — o custo tem de sair do `usage` que
    a própria API devolve."""
    cost, source = image_cost_usd(
        model="gpt-image-2", size="1536x1024", quality="medium",
        usage={"input_tokens": 40, "output_tokens": 1568,
               "input_tokens_details": {"text_tokens": 40, "image_tokens": 0}})
    assert source == FONTE_TOKENS
    assert 0.03 < cost < 0.09  # ~US$0,047 = 1568*3e-05 + 40*5e-06


def test_preco_por_imagem_quando_a_tabela_tem_a_chave():
    """gpt-image-1 medium 1536x1024 está na tabela como preço POR IMAGEM
    (`medium/1536-x-1024/gpt-image-1` -> 0.063)."""
    cost, source = image_cost_usd(model="gpt-image-1", size="1536x1024",
                                  quality="medium", usage=None)
    assert source == FONTE_POR_IMAGEM
    assert cost == 0.063


def test_modelo_fora_da_tabela_vira_custo_desconhecido_nunca_chute():
    cost, source = image_cost_usd(model="modelo-que-nao-existe-999", size="1024x1024",
                                  quality="medium", usage=None)
    assert (cost, source) == (0.0, FONTE_DESCONHECIDA)


# ---------------------------------------------------------------------------
# 2. a imagem entra no ledger
# ---------------------------------------------------------------------------


class _PagoImageGen:
    """Gerador que expõe o contrato opcional de telemetria do port."""

    def __init__(self) -> None:
        self.last_usage: ImageUsage | None = None

    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        self.last_usage = ImageUsage(
            cost_usd=0.047, cost_source=FONTE_TOKENS, latency_ms=9100,
            model="gpt-image-2", size=size, quality="medium",
            input_tokens=40, output_tokens=1568)
        return b"bytes"


class _ImageProc:
    def to_webp(self, data: bytes, out_path: Path, quality: int = 80) -> Path:
        out_path.write_bytes(data)
        return out_path


def _settings_img() -> Settings:
    return Settings(
        secrets=Secrets(), run=RunConfig(hero_image=True),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"image": StepConfig(model="gpt-4.1-mini")})


def _lp() -> Page:
    return Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS",
                slug="saque-fgts", emotional_objective="clareza")


def test_geracao_de_imagem_vira_passo_no_ledger(tmp_path: Path) -> None:
    settings = _settings_img()
    runner = Runner(llm=FakeLLM(responses=["a photo prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=_PagoImageGen(),
                image_proc=_ImageProc(), publisher=None, loader=None,
                settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260815-101010")

    st.step_image(state, _lp(), deps)

    gen = state.step_status["image_gen_p1"]
    assert gen.cost_usd == 0.047
    assert gen.latency_ms == 9100
    assert gen.completion_tokens == 1568
    assert "gpt-image-2" in gen.model_used
    led = _profit_ledger(state)
    assert led["cost_usd"] >= 0.047
    assert led["per_kind"]["image_gen"]["cost_usd"] == 0.047


def test_gerador_sem_telemetria_avisa_em_vez_de_lancar_zero_silencioso(
    tmp_path: Path,
) -> None:
    class _Mudo:
        def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
            return b"bytes"

    settings = _settings_img()
    runner = Runner(llm=FakeLLM(responses=["p"]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=_Mudo(), image_proc=_ImageProc(),
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="r-20260815-101010")

    st.step_image(state, _lp(), deps)

    assert any(i.code == "image_cost_unknown"
               for i in state.step_status["image_gen_p1"].issues)


def test_falha_na_imagem_nao_apaga_o_custo_ja_pago(tmp_path: Path) -> None:
    """O SKIPPED antes SOBRESCREVIA o StepResult da chamada de texto — apagando
    do relatório um custo que a fatura ia cobrar mesmo assim."""
    class _Explode:
        def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
            raise RuntimeError("image provider 500")

    settings = _settings_img()
    runner = Runner(llm=FakeLLM(responses=["p"]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=_Explode(), image_proc=_ImageProc(),
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="r-20260815-101010")
    st.step_image(state, _lp(), deps)
    # injeta o custo do passo de texto e repete: o SKIPPED tem de preservá-lo
    state.step_status["image_p1"] = StepResult(
        step="image_p1", status=StepStatus.OK, cost_usd=0.004, prompt_tokens=120,
        model_used="gpt-4.1-mini")
    st.step_image(state, _lp(), deps)

    res = state.step_status["image_p1"]
    assert res.status is StepStatus.SKIPPED
    assert res.cost_usd == 0.004 and res.prompt_tokens == 120


# ---------------------------------------------------------------------------
# 3. o verificador de URL: HTTP, sem browser, com cache por run
# ---------------------------------------------------------------------------


def _verifier(handler) -> HttpUrlVerifier:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return HttpUrlVerifier(client=client)


def test_verificador_aceita_pagina_viva_e_usa_cache():
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text="<html><title>Jeitto</title>ok</html>")

    verifier = _verifier(handler)
    assert verifier.verify_url("https://jeitto.com.br") is True
    assert verifier.verify_url("https://jeitto.com.br") is True
    assert verifier.verify_url("https://jeitto.com.br") is True
    assert hits["n"] == 1                     # uma visita só; o resto é cache
    assert verifier.stats.cache_hits == 2


def test_verificador_recusa_404_e_200_com_texto_de_erro():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sumiu":
            return httpx.Response(404, text="nope")
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text="<html><title>Página não encontrada</title></html>")

    verifier = _verifier(handler)
    assert verifier.verify_url("https://x.com.br/sumiu") is False
    assert verifier.verify_url("https://x.com.br/falso200") is False
    assert verifier.stats.refused == 2


def test_verificador_trata_antibot_como_inconclusivo_e_ainda_reprova():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="blocked")

    verifier = _verifier(handler)
    assert verifier.verify_url("https://protegido.com.br") is False
    assert verifier.stats.inconclusive == 1
    assert "403" in verifier.stats.reasons["https://protegido.com.br"]


def test_verificador_exige_https_sem_sair_para_a_rede():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("não deveria haver requisição")

    verifier = _verifier(handler)
    assert verifier.verify_url("http://inseguro.com.br") is False
    assert verifier.stats.checked == 0


def test_falha_de_rede_e_fail_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    verifier = _verifier(handler)
    assert verifier.verify_url("https://lento.com.br") is False
    assert verifier.stats.inconclusive == 1


# ---------------------------------------------------------------------------
# 4. o gate factual não depende mais da flag de screenshot
# ---------------------------------------------------------------------------


class _StrictResearch:
    def research(self, topic: str, structure: str) -> ResearchFacts:
        source = "https://www.gov.br/fgts"
        return ResearchFacts(
            fontes=[source],
            fatos_verificados=[VerifiedFact(
                valor="10%", unidade="percentual", fonte_primaria=source,
                dispositivo="não se aplica", vigente_desde=date.today(),
                verificado_em=date.today())])


class _SempreVivo:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def verify_url(self, url: str) -> bool:
        self.urls.append(url)
        return True


def _settings_research() -> Settings:
    return Settings(
        secrets=Secrets(), run=RunConfig(official_screenshots=False),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"research": StepConfig(model="perplexity/sonar")})


def _page_research() -> Page:
    return Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS",
                slug="saque-fgts", main_content_structure=["H2: Como funciona"])


def test_fato_critico_passa_com_screenshots_desligados(tmp_path: Path) -> None:
    """A regressão que motivou a frente: `official_screenshots=False` (flag
    cosmética) NÃO pode reprovar uma página com fato numérico."""
    settings = _settings_research()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=_StrictResearch(), image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner,
                screenshot=None, url_verifier=_SempreVivo())
    state = RunState(run_id="r-20260815-101010")

    st.step_research(state, _page_research(), deps)

    assert state.step_status["research_p1"].status is StepStatus.OK
    assert state.facts[1].fontes_resolvidas == ["https://www.gov.br/fgts"]


def test_sem_verificador_o_fato_critico_continua_reprovando(tmp_path: Path) -> None:
    settings = _settings_research()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=_StrictResearch(), image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="r-20260815-101010")

    st.step_research(state, _page_research(), deps)

    res = state.step_status["research_p1"]
    assert res.status is StepStatus.FAILED
    assert any(i.code == "fact_source_verifier_missing" for i in res.issues)


# ---------------------------------------------------------------------------
# 5. o resumo de custo que o operador lê
# ---------------------------------------------------------------------------


def test_ledger_separa_custo_por_pagina_por_tipo_e_o_desperdicio():
    state = RunState(run_id="x")
    state.step_status["extract"] = StepResult(step="extract", status=StepStatus.OK,
                                              cost_usd=0.02)
    state.step_status["write_p1"] = StepResult(step="write_p1", status=StepStatus.OK,
                                               cost_usd=0.10, prompt_tokens=100)
    state.step_status["image_gen_p1"] = StepResult(step="image_gen_p1",
                                                   status=StepStatus.OK, cost_usd=0.05)
    state.step_status["publish_p1"] = StepResult(step="publish_p1", status=StepStatus.OK)
    state.step_status["write_p2"] = StepResult(step="write_p2", status=StepStatus.FAILED,
                                               cost_usd=0.08)
    state.step_status["blocked_p2"] = StepResult(step="blocked_p2",
                                                 status=StepStatus.FAILED)

    led = _profit_ledger(state)

    assert led["per_page"][1]["cost_usd"] == 0.15
    assert led["per_page"][1]["published"] is True
    assert led["per_page"][2]["blocked"] is True
    assert led["desperdicio_usd"] == 0.08
    assert led["per_kind"]["image_gen"]["cost_usd"] == 0.05
    assert led["per_kind"]["extract"]["cost_usd"] == 0.02


def test_a_mesma_url_de_plataforma_nao_e_visitada_duas_vezes_por_pagina(
    tmp_path: Path, config_files: Path,
) -> None:
    """Defeito 4: `_write_ctx` roda no `step_write`, DE NOVO no
    `step_content_gate` e mais uma vez no `step_publish`. Com o cache por run,
    a URL sai para a rede UMA vez — não 2–3 vezes por página, a 20s cada."""
    from funnelforge.config.settings import load_settings
    from funnelforge.domain.models import FunnelPlan

    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text="<html><title>Jeitto</title>ok</html>")

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner,
                url_verifier=_verifier(handler))
    page = Page(page_number=3, page_type="SOLUTION", h1_title="Cartão consignado",
                slug="cartao-consignado-p3", ordinal=1)
    # uma irmã com ordinal maior, só para esta página NÃO ser a terminal (a
    # terminal exige um pagespec que só o config.yaml de produção traz)
    irma = Page(page_number=4, page_type="SOLUTION", h1_title="Cartão pré-pago",
                slug="cartao-pre-pago-p4", ordinal=2)
    state = RunState(run_id="r-20260815-101010")
    state.plan = FunnelPlan(pages=[page, irma])
    state.facts[3] = ResearchFacts(fontes=["https://jeitto.com.br"])
    # A pesquisa rodou e NÃO elegeu canal oficial para esta página (chave
    # presente, lista vazia). Sem isto, o fallback offline reivindicaria a
    # jeitto.com.br como canal oficial e ela sairia da lista de plataformas —
    # o teste mediria outra coisa.
    state.official_links[3] = []

    primeiro = st._write_ctx(state, page, deps)
    segundo = st._write_ctx(state, page, deps)   # content_gate
    terceiro = st._write_ctx(state, page, deps)  # publish

    assert primeiro["verified_platforms"] == ["jeitto.com.br"]
    assert segundo["verified_platforms"] == terceiro["verified_platforms"]
    assert hits["n"] == 1
