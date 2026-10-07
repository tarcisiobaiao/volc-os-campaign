"""Cenário hermético do ramo editorial (etapa B4).

Roda o pipeline inteiro pelo caminho do `run-volc` (plano injetado a partir de
um `funnel_architecture`) com tudo falso: LLM roteirizado pelo texto do prompt,
pesquisa pelo runner, verificador de URL que aprova qualquer https, gerador de
imagem que devolve um PNG minúsculo. Sem rede, sem gasto, sem sono.

Serve a dois tipos de teste:

- o OURO do ramo desligado (`editorial_v2=false`): os prompts renderizados e a
  ordem dos passos precisam sair byte a byte iguais aos de antes da reforma;
- os testes do ramo novo (`editorial_v2=true`): propagação de tom/público/tensão
  até o redator, briefing com falha fechada, SEO antes da revisão.

`date.today()` é CONGELADO (os prompts levam a data): ver `congelar_data`.

Este arquivo não é coletado pelo pytest (não começa com `test_`).
"""
from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.adapters.images_pillow import PillowImageProcessor
from funnelforge.config.settings import load_settings
from funnelforge.domain.models import RunState
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM, png_bytes

HOJE = date(2026, 9, 30)


class DataCongelada(date):
    """`date` cujo `today()` é sempre HOJE. Só `today` muda."""

    @classmethod
    def today(cls):  # type: ignore[override]
        return HOJE


def congelar_data(monkeypatch) -> None:
    """Congela a data nos módulos que a escrevem em prompt."""
    from funnelforge.adapters import research_perplexity
    from funnelforge.pipeline import steps

    monkeypatch.setattr(steps, "date", DataCongelada)
    monkeypatch.setattr(research_perplexity, "date", DataCongelada)


# ---------------------------------------------------------------------------
# configuração do cenário (a mesma forma do config.yaml, com os passos que o
# pipeline completo pede)
# ---------------------------------------------------------------------------

_CONFIG = """\
run:
  max_retries: 1
  publish: false
  hero_image: true
  featured_image: true
  widgets_enabled: true
site:
  domain: https://site.exemplo.com.br
  post_type: rec
  lp_post_type: r
  cnpj: "42.724.548/0001-24"
  author: {name: Equipe Exemplo, credential: Redacao de jornalismo de servico.}
  official_preference: []
  cross_funnel_lps: [outro-guia-completo]
routing:
  LP:       {allowed_targets: [funnel], required_targets: [funnel],
             forbidden_targets: [self, bare_rec, external_official, cross_funnel],
             cta_min: 3, cta_max: 3, distinct_targets: true, anchor_congruent: true}
  PRESELL:  {allowed_targets: [funnel], required_targets: [funnel],
             forbidden_targets: [self, bare_rec],
             cta_min: 2, cta_max: 8, distinct_targets: true, anchor_congruent: true}
  SOLUTION: {allowed_targets: [funnel, external_official],
             required_targets: [funnel, external_official],
             forbidden_targets: [self, bare_rec, cross_funnel], cta_min: 1, cta_max: 5,
             distinct_targets: true, anchor_congruent: true}
  SOLUTION_TERMINAL: {allowed_targets: [cross_funnel], required_targets: [cross_funnel],
             forbidden_targets: [self, funnel, external_official, bare_rec],
             cta_min: 1, cta_max: 1, distinct_targets: false, anchor_congruent: true}
ads:
  paragraph_anchors: [1, 3]
  vignette: {enabled: true, max_per_window: 1, window_seconds: 600}
index:
  LP:       {robots: 'noindex,follow'}
  PRESELL:  {robots: 'noindex,follow'}
  SOLUTION: {robots: 'noindex,follow'}
uniqueness:
  jaccard_threshold: 0.35
steps:
  research:   {model: gemini/gemini-3.5-flash, fallbacks: [], temperature: 0.2,
               validators: [has_sources, research_facts_contract]}
  write_p1:   {model: gemini/gemini-3.5-flash, fallbacks: [], temperature: 0.7,
               validators: [lp_json_contract, calm_utility, language_pt]}
  write_page: {model: gemini/gemini-3.5-flash, fallbacks: [], temperature: 0.7,
               validators: [gutenberg_blocks, cta_style, pagespec, calm_utility,
                            compliance, language_pt, same_domain, no_bare_rec,
                            no_self_loop, identity, uniqueness]}
  judge:      {model: gpt-4.1, fallbacks: [], temperature: 0.0, validators: []}
  seo:        {model: gpt-4.1, fallbacks: [], temperature: 0.4, validators: [seo_limits]}
  image:      {model: gpt-4.1, fallbacks: [], temperature: 1.0, validators: []}
  image_review: {model: gpt-4.1, fallbacks: [], temperature: 0.0, validators: []}
  widget:     {model: gemini/gemini-3.5-flash, fallbacks: [], temperature: 0.5, validators: []}
  engajamento: {model: gpt-4.1, fallbacks: [], temperature: 0.1, validators: []}
"""

# Os passos do ramo novo. Entram só quando o teste pede (`passos_v2=True`), para
# que o ouro do ramo desligado continue vendo exatamente a configuração antiga.
_CONFIG_PASSOS_V2 = """\
  briefing:   {model: gpt-4.1, fallbacks: [], temperature: 0.2, validators: [briefing_contract]}
  revisor:    {model: gpt-4.1, fallbacks: [], temperature: 0.0, validators: []}
"""


def settings_do_cenario(tmp_path: Path, *, editorial_v2: bool = False,
                        passos_v2: bool = False):
    pasta = tmp_path / "cfg"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ".env").write_text("", encoding="utf-8")
    texto = _CONFIG + (_CONFIG_PASSOS_V2 if passos_v2 else "")
    if editorial_v2:
        texto = texto.replace("run:\n", "run:\n  editorial_v2: true\n", 1)
    (pasta / "config.yaml").write_text(texto, encoding="utf-8")
    return load_settings(pasta / ".env", pasta / "config.yaml")


# ---------------------------------------------------------------------------
# o funil (um `funnel_architecture` como o backend grava)
# ---------------------------------------------------------------------------

_PAGINAS = (
    # (pos, slug, headline, objetivo, estrutura, keywords, cta_text)
    (1, "tarifa-social-energia", "Tarifa social de energia: quem tem direito e como pedir",
     "Leitor paga conta de luz alta e quer saber se a familia pode ter desconto",
     ["Quem pode ter o desconto", "Como o desconto aparece na conta",
      "Onde pedir", "O que conferir antes de pedir"],
     "tarifa social, desconto conta de luz", "Ver se a familia tem direito"),
    (2, "por-onde-comecar-tarifa-social-pr", "Por onde comecar na tarifa social",
     "Leitor quer saber qual caminho serve para o caso dele",
     ["Qual e a sua situacao", "Qual guia resolve a sua duvida"],
     "tarifa social como pedir", "Ver o caminho do seu caso"),
    (3, "quem-tem-direito-tarifa-social-p1", "Quem tem direito a tarifa social",
     "Leitor quer confirmar se a familia se encaixa nas regras",
     ["Quem tem direito", "Documentos que costumam ser pedidos", "Casos que ficam de fora"],
     "quem tem direito tarifa social", "Ver quem tem direito"),
    (4, "como-pedir-tarifa-social-p2", "Como pedir a tarifa social na distribuidora",
     "Leitor quer o passo a passo para pedir o desconto",
     ["Antes de pedir", "Passo a passo do pedido", "Depois do pedido"],
     "como pedir tarifa social", "Ver o passo a passo do pedido"),
    (5, "conferir-desconto-conta-de-luz-p3", "Como conferir o desconto na conta de luz",
     "Leitor quer saber se o desconto ja aparece na conta",
     ["Onde o desconto aparece", "O que fazer se nao aparecer", "Quando procurar a distribuidora"],
     "conferir desconto conta de luz", "Ver como conferir o desconto"),
)

TOM_DO_ARQUITETO = "Direto e acolhedor, com exemplos da conta de luz e sem jargao tecnico"
AVATAR_DO_ARQUITETO = ("Familia de baixa renda que paga conta de luz alta e nao sabe se ja "
                       "recebe o desconto")

# Os contratos editoriais de cada página (ramo contextual): quem liga para quem
# e por quê. O terminal (p3) liga de volta para a p1 -- navegação voluntária.
_EDITORIAL = {
    1: ("A minha familia pode ter desconto na conta de luz?",
        "Explica quem tem direito, onde pedir e como conferir o desconto",
        "Ver se a familia tem direito",
        [("por-onde-comecar-tarifa-social-pr", "Leitor ainda nao sabe qual e o proprio caso"),
         ("quem-tem-direito-tarifa-social-p1", "Leitor quer conferir as regras direto")]),
    2: ("Qual guia resolve o meu caso?",
        "Ajuda o leitor a escolher entre conferir o direito, pedir ou conferir a conta",
        "Ver o caminho do seu caso",
        [("quem-tem-direito-tarifa-social-p1", "Quem ainda nao sabe se tem direito"),
         ("como-pedir-tarifa-social-p2", "Quem ja sabe que tem direito"),
         ("conferir-desconto-conta-de-luz-p3", "Quem ja pediu e quer conferir")]),
    3: ("Quem tem direito a tarifa social?",
        "Lista as condicoes que a regra exige e os casos que ficam de fora",
        "Ver quem tem direito",
        [("como-pedir-tarifa-social-p2", "Depois de confirmar o direito, o pedido")]),
    4: ("Como faco o pedido na distribuidora?",
        "Mostra o passo a passo do pedido e o que levar",
        "Ver o passo a passo do pedido",
        [("conferir-desconto-conta-de-luz-p3", "Depois do pedido, conferir a conta")]),
    5: ("Como sei se o desconto ja esta na conta?",
        "Mostra onde o desconto aparece na conta e o que fazer se faltar",
        "Ver como conferir o desconto",
        [("quem-tem-direito-tarifa-social-p1", "Se o desconto nao apareceu, rever as regras")]),
}


def arquitetura_base(*, editorial: bool = False) -> dict[str, Any]:
    """Um `funnel_architecture` fiel ao que o VOLC grava."""
    paginas, jobs = [], []
    for pos, slug, h1, objetivo, estrutura, kws, cta in _PAGINAS:
        proximo = _PAGINAS[pos][1] if pos < len(_PAGINAS) else None
        canonica = {
            "position": pos, "page_title": h1, "emotional_goal": objetivo,
            "subtitles": list(estrutura), "internal_links": [],
            "avatar": AVATAR_DO_ARQUITETO, "intro_section": "", "closing_section": "",
        }
        wb = {
            "avatar_context": AVATAR_DO_ARQUITETO, "tone": TOM_DO_ARQUITETO,
            "page_num": pos, "total_pages": len(_PAGINAS), "headline": h1,
            "objective": objetivo, "current_url": slug, "cta_text": cta,
            "cta_link": f"/{proximo}" if proximo else "/inicio",
            "skeleton": "\n".join(f"- {s}" for s in estrutura), "keywords": kws,
            "intro_section": "", "closing_section": "",
        }
        if editorial:
            pergunta, entrega, rotulo, links = _EDITORIAL[pos]
            wb["editorial"] = {
                "reader_question": pergunta, "useful_delivery": entrega,
                "cta_label": rotulo,
                "links": [{"target": t, "reason": r} for t, r in links],
            }
        paginas.append(canonica)
        jobs.append({"job_id": f"write_p{pos}", "page_type": "x", "writer_briefing": wb})
    return {
        "funnel_strategy": {"avatar_summary": AVATAR_DO_ARQUITETO,
                            "tone_voice": TOM_DO_ARQUITETO, "total_pages": len(_PAGINAS)},
        "pages": paginas,
        "writing_jobs": jobs,
    }


# ---------------------------------------------------------------------------
# respostas roteirizadas (o LLM falso)
# ---------------------------------------------------------------------------

FONTE_OFICIAL = "https://servicos.exemplo.gov.br/tarifa-social/consulta"
FONTE_CADASTRO = "https://servicos.exemplo.gov.br/cadastro-unico/consulta"

RESEARCH_JSON = json.dumps({
    "resumo": ("A tarifa social da desconto na conta de luz para familias inscritas no "
               "cadastro social; o pedido e feito na distribuidora."),
    "dados_validados": [
        {"fato": "O desconto e aplicado pela distribuidora de energia da regiao.",
         "fonte": FONTE_OFICIAL},
        {"fato": "A inscricao no cadastro social e condicao para o desconto.",
         "fonte": FONTE_CADASTRO},
    ],
    "fatos_verificados": [
        {"valor": "65%", "unidade": "de desconto na faixa de consumo mais baixa",
         "fonte_primaria": FONTE_OFICIAL, "dispositivo": "Lei de exemplo, art. 1",
         "vigente_desde": "2010-01-20", "verificado_em": "2026-09-29"},
    ],
    "passo_a_passo": ["Conferir a inscricao no cadastro social",
                      "Pedir o desconto na distribuidora"],
    "fontes": [FONTE_OFICIAL, FONTE_CADASTRO],
}, ensure_ascii=False)

LP_JSON = json.dumps({
    "hero_title": "Tarifa social de energia",
    "hero_subtitle": "O que a regra exige, onde pedir e como conferir o desconto na conta",
    "article_title": "Tarifa social de energia: quem tem direito e onde pedir",
    "intro": "<p>A conta de luz pesa no orcamento. Esta pagina mostra quem tem direito ao "
             "<strong>desconto</strong> e onde pedir.</p>",
    "sections": [
        {"title": "Quem pode ter o desconto", "body": "<p>A regra olha a inscricao no cadastro social.</p>"},
        {"title": "Como o desconto aparece", "body": "<p>O desconto aparece na propria conta de luz.</p>"},
        {"title": "Onde pedir", "body": "<p>O pedido e feito na distribuidora da regiao.</p>"},
        {"title": "O que conferir antes", "body": "<p>Tenha a conta e o cadastro atualizados.</p>"},
    ],
    "faq": [
        {"q": "Preciso pagar para pedir?", "a": "Nao. O pedido e gratuito na distribuidora."},
        {"q": "Onde pedir?", "a": "Na distribuidora de energia da sua regiao."},
    ],
    "transition": "<p>O proximo guia mostra qual caminho serve para o seu caso.</p>",
    "cta_texts": ["Ver o caminho do seu caso", "Ver quem tem direito",
                  "Ver o passo a passo do pedido"],
}, ensure_ascii=False)

JUDGE_JSON = json.dumps({
    "approved": True, "blocking": False,
    "scores": {k: 8 for k in ("useful_delivery", "destination_relevance", "cta_discipline",
                              "proof_and_authority", "compliance", "tone_e_e_a_t",
                              "faq_resolution", "single_destination", "authorship_signal")},
    "feedback": [],
})

SEO_JSON = json.dumps({
    "seotitle": "Tarifa social de energia: quem tem direito",
    "metadescription": "Veja quem tem direito ao desconto na conta de luz e onde pedir.",
    "keywordfocus": "tarifa social de energia",
    "slug": "tarifa-social-energia",
}, ensure_ascii=False)

IMAGE_PROMPT = "An unbranded editorial photo of an electricity bill on a kitchen table."

REVIEW_JSON = json.dumps({
    "third_party_branding": False, "official_document_or_interface": False,
    "personal_data_or_qr": False, "implied_approval_or_outcome": False,
    "anatomy_or_physics_error": False, "topic_mismatch": False, "uncertain": False,
    "evidence": "Kitchen table with an unbranded bill.",
    "anatomy_evidence": "No people in the frame.",
    "topic_evidence": "Electricity bill matches the headline.",
})

_HEADLINE_RE = re.compile(r"Tema/headline: (.+)")
_SLUG_RE = re.compile(r"^slug: (\S+)$", re.M)


def texto_da_mensagem(mensagem: dict) -> str:
    """O texto de uma mensagem, inclusive a multimodal (lista de partes)."""
    conteudo = mensagem.get("content")
    if isinstance(conteudo, list):
        return "\n".join(p.get("text", "") for p in conteudo
                         if isinstance(p, dict) and p.get("type") == "text")
    return str(conteudo or "")


def html_interno(prompt: str) -> str:
    """HTML Gutenberg distinto por página (passa no guarda de unicidade)."""
    m = _HEADLINE_RE.search(prompt)
    headline = m.group(1).strip() if m else "pagina"
    tag = re.sub(r"[^a-z0-9]", "", headline.lower())
    filler = " ".join(f"exclusivo{tag}{i:03d}" for i in range(60))
    return (
        "<!-- wp:paragraph -->\n"
        f"<p>Conteúdo de utilidade pública sobre {headline}, com orientações claras "
        f"e verificadas para o leitor. {filler}</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "<!-- wp:list -->\n"
        f'<ul class="wp-block-list"><li>Primeiro passo sobre {headline.lower()}.</li>'
        f"<li>Segundo passo sobre {headline.lower()}.</li></ul>\n"
        "<!-- /wp:list -->\n"
    )


def _engajamento(prompt: str) -> str:
    return json.dumps({"paginas": [
        {"slug": s, "resposta_em_uma_frase": "Uma ordem de acoes.", "engajamento": "sequencial"}
        for s in _SLUG_RE.findall(prompt)]})


def responder_v1(model: str, messages: list[dict]) -> str:
    """Resposta roteirizada pelo TEXTO do prompt (independe da ordem)."""
    prompt = texto_da_mensagem(messages[-1])
    if "Pesquise e retorne SOMENTE um objeto JSON" in prompt:
        return RESEARCH_JSON
    if "Você classifica a FORMA DA PERGUNTA" in prompt:
        return _engajamento(prompt)
    if "PÁGINA DE POUSO" in prompt:
        return LP_JSON
    if "PÁGINA INTERNA" in prompt or "PÁGINA PRÉ-SELL" in prompt:
        return html_interno(prompt)
    if "JUIZ DE QUALIDADE" in prompt:
        return JUDGE_JSON
    if "YOAST SEO" in prompt:
        return SEO_JSON
    if "VISUAL STRATEGIST" in prompt or "Write one English image prompt" in prompt:
        return IMAGE_PROMPT
    if "Inspect the actual image" in prompt:
        return REVIEW_JSON
    if "peça interativa" in prompt:
        return "NONE"
    raise AssertionError(f"prompt sem roteiro no cenário: {prompt[:300]!r}")


# ---------------------------------------------------------------------------
# o ramo novo (editorial_v2): briefing e SEO v2
# ---------------------------------------------------------------------------

_DESTINO_RE = re.compile(r"^- tipo=(\S+) destino=(\S+)", re.M)


def briefing_valido(prompt: str) -> str:
    """Um briefing-v1 que passa no contrato para QUALQUER página do cenário:
    procedência só no plano do arquiteto e no primeiro destino que o prompt
    oferece (lido do próprio prompt), sem benefício (não há fato citado)."""
    passos = []
    m = _DESTINO_RE.search(prompt)
    if m:
        tipo, destino = m.group(1), m.group(2)
        passos.append({
            "tipo": tipo, "destino": destino, "rotulo": "Ver o que muda no seu caso",
            "intencao_do_leitor": {"texto": "Avancar para o proprio caso",
                                   "base": "briefing_do_arquiteto", "ref": ["arquiteto:objetivo"]},
            "o_que_encontra": {"texto": "O que o destino declara entregar",
                               "base": "briefing_do_arquiteto", "ref": [f"destino:{destino}"]},
            "motivo": "a proxima duvida do leitor",
        })
    arq = {"base": "briefing_do_arquiteto", "ref": ["arquiteto:objetivo"]}
    return json.dumps({
        "intencao": {
            "pergunta_do_leitor": {"texto": "A familia pode ter o desconto?", **arq},
            "intencao_real_da_busca": {"texto": "Resolver o proprio caso", "base": "hipotese",
                                       "evidencia": ["arquiteto:objetivo"]},
        },
        "leitor": {
            "conhecimento_previo": {"texto": "Sabe que existe desconto", **arq},
            "desejo_ou_problema": {"texto": "Pagar menos na conta", **arq},
            "objecoes": [{
                "objecao": {"texto": "Acha que o pedido e caro", "base": "hipotese",
                            "evidencia": ["arquiteto:avatar_summary"]},
                "resposta": {"texto": "A pagina mostra onde pedir", **arq},
            }],
        },
        "promessa_da_pagina": {"texto": "Mostrar o caminho do caso do leitor",
                               "cumprida_em": "primeira secao",
                               "base": "briefing_do_arquiteto", "ref": ["arquiteto:estrutura"]},
        "entrega_concreta": {"formato": "passo_a_passo",
                             "itens": [{"texto": "As etapas do plano", "base": "briefing_do_arquiteto",
                                        "ref": ["arquiteto:estrutura"]}]},
        "beneficios": [],
        "proximos_passos": passos,
        "limites": [{"texto": "O site informa; quem executa e a instituicao", "base": "identidade"}],
        "hipoteses": [{"id": "h1", "sobre": "leitor", "texto": "Teme pagar intermediario",
                       "como_confirmar": "termos com pagar"}],
        "tom": {"registro": "servico", "intensidade": "direta",
                "justificativa": "o arquiteto pediu voz direta", "base": "briefing_do_arquiteto",
                "ref": ["arquiteto:tone_voice"]},
    }, ensure_ascii=False)


# O revisor contextual (B5) aprova: os testes que precisam de outra decisão
# roteirizam o revisor por página (ver `tests/cenario_revisor.py`).
REVISOR_APROVA = json.dumps({
    "versao": "revisao-v1", "decisao": "aprovado", "achados": [], "patches": [],
    "afirmacoes_nao_verificadas": [], "preservado": ["ângulo", "voz"],
    # notas válidas em TODO critério existencial que o revisor pode exigir
    # (conjunto editorial + single_destination da LP sem contrato editorial)
    "notas": {"compliance": 9, "cta_discipline": 8, "useful_delivery": 8,
              "destination_relevance": 8, "single_destination": 8},
})


def responder_v2(model: str, messages: list[dict]) -> str:
    """O roteiro do ramo novo: briefing, SEO v2 e revisor; o resto como no ramo
    antigo (os redatores v2 mantêm os mesmos marcadores de identidade)."""
    prompt = texto_da_mensagem(messages[-1])
    if "EDITOR DE BRIEFING" in prompt:
        return briefing_valido(prompt)
    if "Você escreve o TÍTULO SEO" in prompt:
        return SEO_JSON
    if "REVISOR EDITORIAL CONTEXTUAL" in prompt:
        return REVISOR_APROVA
    if "PÁGINA INTERNA" in prompt or "PÁGINA PRÉ-SELL" in prompt:
        return html_interno_v2(prompt)
    return responder_v1(model, messages)


def html_interno_v2(prompt: str) -> str:
    """Página interna do ramo novo: a mesma do V1 com a abertura que o gate
    estrutural exige (3 parágrafos no fluxo principal para os slots do Ad
    Inserter). O ouro do V1 continua usando `html_interno`."""
    m = _HEADLINE_RE.search(prompt)
    headline = (m.group(1).strip() if m else "pagina").lower()
    return (
        "<!-- wp:paragraph -->\n"
        f"<p>Quem procura {headline} quer saber por onde começar e o que conferir.</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "<!-- wp:paragraph -->\n"
        f"<p>Este guia reúne o que a fonte oficial diz sobre {headline}.</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        + html_interno(prompt)
    )


class VerificadorQueAprova:
    """`UrlVerifier` falso: toda https responde. Sem rede."""

    def verify_url(self, url: str) -> bool:
        return str(url).startswith("https://")


class GeradorDeImagemFalso:
    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        return png_bytes(32, 32)


def montar_deps(tmp_path: Path, settings, responder: Callable[[str, list[dict]], str]):
    llm = FakeLLM(responses=responder)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries,
                    runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=GeradorDeImagemFalso(),
                image_proc=PillowImageProcessor(), publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner,
                url_verifier=VerificadorQueAprova())
    return llm, deps


def rodar_cenario(tmp_path: Path, arquitetura: dict, settings, *,
                  responder: Callable[[str, list[dict]], str] = responder_v1,
                  timestamp: str = "20260930-120000") -> tuple[RunState, Deps, FakeLLM]:
    llm, deps = montar_deps(tmp_path, settings, responder)
    plano = plano_do_funnel_architecture(copy.deepcopy(arquitetura))
    state = run_pipeline(None, deps, only=None, publish=False, plan=plano,
                         timestamp=timestamp)
    return state, deps, llm


# ---------------------------------------------------------------------------
# captura do que foi pedido ao modelo
# ---------------------------------------------------------------------------

_BASE64_RE = re.compile(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+")


def normalizar_prompt(texto: str) -> str:
    """Tira do snapshot o que não é prompt (bytes da imagem revisada)."""
    return _BASE64_RE.sub("data:image/<bytes>;base64,<omitido>", texto)


def prompts_do_run(runs_dir: Path, run_id: str) -> dict[str, str]:
    """{passo: prompt inicial} — o snapshot que o Runner grava por passo."""
    pasta = runs_dir / run_id / "prompts"
    return {p.stem: normalizar_prompt(p.read_text(encoding="utf-8"))
            for p in sorted(pasta.glob("*.txt"))}


def ordem_do_run(runs_dir: Path, run_id: str, state: RunState) -> dict[str, Any]:
    """A ordem das chamadas pagas (log.jsonl) e o estado final dos passos."""
    chamadas: list[str] = []
    log = runs_dir / run_id / "log.jsonl"
    if log.exists():
        for linha in log.read_text(encoding="utf-8").splitlines():
            entrada = json.loads(linha)
            if "step" in entrada and "attempt" in entrada:
                chamadas.append(f"{entrada['step']}#{entrada['attempt']}")
    return {
        "chamadas_llm": chamadas,
        "step_status": [f"{k}={v.status.value}" for k, v in state.step_status.items()],
    }
