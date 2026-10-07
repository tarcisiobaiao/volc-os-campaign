"""Cenário hermético do REVISOR (etapa B5): o ramo editorial novo de ponta a
ponta ATÉ o WordPress falso.

Reaproveita o funil de `cenario_editorial` (tarifa social de energia) e troca
o redator das internas por um que escreve HTML Gutenberg de verdade: botões com
os hrefs que o prompt oferece, parágrafos com palavras que as listas antigas
reprovavam, um parágrafo legítimo com "utilidade pública" e o aviso canônico.
O widget sai de um JSON de conteúdo válido (arquétipo diagnóstico). O revisor
é roteirizado por página (`revisores={3: fn}`); o padrão aprova.

Tudo falso: LLM, verificador de URL, imagem e WordPress. Sem rede, sem gasto.
Não é coletado pelo pytest (não começa com `test_`).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Callable

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT
from funnelforge.pipeline.pipeline import run_pipeline
from tests.cenario_editorial import (
    LP_JSON,
    congelar_data,
    montar_deps,
    responder_v2,
    settings_do_cenario,
    texto_da_mensagem,
)

MARCA_DO_REVISOR = "REVISOR EDITORIAL CONTEXTUAL"

# As frases que as listas por palavra reprovavam e que são LEGÍTIMAS no contexto.
FRASE_VAGAS = ("Cada distribuidora atende por ordem de pedido e as vagas limitadas do "
               "atendimento presencial mudam conforme a agenda local.")
FRASE_SISTEMA = ("O pedido e feito no sistema oficial da distribuidora, e nao neste guia "
                 "independente.")
FRASE_UTILIDADE = ("Conteúdo de utilidade pública sobre {h}, com orientações claras e "
                   "verificadas para o leitor.")
ROTULO_CADASTRO = "Cadastro no programa: veja o passo a passo"
CTA_LP_PRIMEIRA_PESSOA = "Quero ver quem tem direito"

WIDGET_JSON = json.dumps({
    "arquetipo": "diagnostico",
    "titulo": "O que travou o seu pedido",
    "subtitulo": "Escolha o que aconteceu.",
    "controles": [{"id": "sintoma", "rotulo": "O que aconteceu?", "opcoes": [
        {"valor": "negado", "texto": "A distribuidora negou o pedido"},
        {"valor": "analise", "texto": "O pedido esta em analise"}]}],
    "cenarios": [
        {"quando": {"sintoma": "negado"}, "chip": "cadastro", "tom": "risco",
         "titulo": "O pedido depende do cadastro atualizado",
         "corpo": "Confira se o cadastro social esta em dia."},
        {"quando": {"sintoma": "analise"}, "chip": "em analise", "tom": "atencao",
         "titulo": "A analise segue na distribuidora",
         "corpo": "A distribuidora confere os dados antes de aplicar o desconto."},
    ],
    "rodape": "Fonte: canais oficiais citados no texto.",
}, ensure_ascii=False)

_ROTA_RE = re.compile(r"^- (funnel|external_official|cross_funnel): (.*?) → (\S+)$", re.M)
_HEADLINE_RE = re.compile(r"Tema/headline: (.+)")


def _p(texto: str) -> str:
    return f"<!-- wp:paragraph -->\n<p>{texto}</p>\n<!-- /wp:paragraph -->"


def _h2(texto: str) -> str:
    return f"<!-- wp:heading -->\n<h2>{texto}</h2>\n<!-- /wp:heading -->"


def _botao(rotulo: str, href: str) -> str:
    return ("<!-- wp:buttons -->\n<div class=\"wp-block-buttons\"><!-- wp:button -->\n"
            "<div class=\"wp-block-button\"><a class=\"wp-block-button__link "
            f"wp-element-button\" href=\"{href}\">{rotulo}</a></div>\n"
            "<!-- /wp:button --></div>\n<!-- /wp:buttons -->")


def headline_do_prompt(prompt: str) -> str:
    m = _HEADLINE_RE.search(prompt)
    return m.group(1).strip() if m else "pagina"


def html_da_interna(prompt: str, *, extra: str = "", rotulo: str | None = None) -> str:
    """Um artigo Gutenberg que passa nos contratos OBJETIVOS e traz as frases
    que as listas por palavra reprovavam."""
    h = headline_do_prompt(prompt)
    tag = re.sub(r"[^a-z0-9]", "", h.lower())
    filler = " ".join(f"exclusivo{tag}{i:03d}" for i in range(40))
    partes = [
        _p(FRASE_UTILIDADE.format(h=h)),
        _p(f"Este guia explica {h.lower()} com os passos na ordem certa. {filler}"),
        _p(FRASE_VAGAS),
        _h2("O que conferir primeiro"),
        _p(FRASE_SISTEMA),
    ]
    if extra:
        partes.append(extra)
    partes.append(_h2("Como seguir depois"))
    ordinais = ("primeira", "segunda", "terceira", "quarta", "quinta", "sexta")
    for i, (tipo, ancora, href) in enumerate(_ROTA_RE.findall(prompt)):
        if i == 0 and rotulo:
            texto = rotulo                     # o rótulo sob teste vai no 1º botão
        elif tipo == "funnel":
            texto = f"{ROTULO_CADASTRO}, {ordinais[i]} parte" if i else ROTULO_CADASTRO
        else:
            texto = ancora.replace(">>>", "").strip() or "Ver no canal oficial"
        partes.append(_p(f"O proximo guia aprofunda a {ordinais[i]} parte do seu caso."))
        partes.append(_botao(texto, href))
    partes.append(_h2("Resumo do caminho"))
    partes.append(_p("O caminho depende do cadastro e da distribuidora da sua regiao."))
    partes.append(_p(COMPLIANCE_NOTICE_TEXT))
    return "\n\n".join(partes) + "\n"


def lp_json_legitima() -> str:
    lp = json.loads(LP_JSON)
    lp["cta_texts"] = [CTA_LP_PRIMEIRA_PESSOA, "Ver quem tem direito",
                       "Ver o passo a passo do pedido"]
    return json.dumps(lp, ensure_ascii=False)


def resposta_do_revisor(decisao: str = "aprovado", achados=(), patches=(),
                        afirmacoes=()) -> str:
    return json.dumps({
        "versao": "revisao-v1", "decisao": decisao, "achados": list(achados),
        "patches": list(patches), "afirmacoes_nao_verificadas": list(afirmacoes),
        "preservado": ["ângulo", "benefício", "voz"],
        "notas": {"compliance": 9, "cta_discipline": 8, "useful_delivery": 8,
                  "destination_relevance": 8, "single_destination": 8},
    }, ensure_ascii=False)


_PAGINA_DO_REVISOR_RE = re.compile(r"página nº (\d+)")


def numero_da_pagina_no_revisor(prompt: str) -> int:
    m = _PAGINA_DO_REVISOR_RE.search(prompt)
    return int(m.group(1)) if m else 0


def responder_fluxo(*, revisores: dict[int, Callable[[str], str]] | None = None,
                    internas: dict[str, Callable[[str], str]] | None = None,
                    lp: Callable[[str], str] | None = None) -> Callable:
    """O roteiro do fluxo com revisor. `internas` troca o HTML por headline."""
    revisores = revisores or {}
    internas = internas or {}

    def responder(model: str, messages: list[dict]) -> str:
        prompt = texto_da_mensagem(messages[-1])
        if MARCA_DO_REVISOR in prompt:
            fn = revisores.get(numero_da_pagina_no_revisor(prompt))
            return fn(prompt) if fn else resposta_do_revisor()
        if "Você classifica a FORMA DA PERGUNTA" in prompt:
            slugs = re.findall(r"^slug: (\S+)$", prompt, re.M)
            return json.dumps({"paginas": [
                {"slug": s, "resposta_em_uma_frase": "Um bloqueio a destravar.",
                 "engajamento": "diagnostico"} for s in slugs]})
        if "PÁGINA DE POUSO" in prompt:
            return lp(prompt) if lp else lp_json_legitima()
        if "PÁGINA INTERNA" in prompt or "PÁGINA PRÉ-SELL" in prompt:
            h = headline_do_prompt(prompt)
            fn = internas.get(h)
            return fn(prompt) if fn else html_da_interna(prompt)
        if "peça interativa" in prompt:
            return WIDGET_JSON
        return responder_v2(model, messages)

    return responder


class WordPressFalso:
    """Publicador falso: grava o que o motor entregaria ao WordPress."""

    def __init__(self) -> None:
        self.posts: dict[str, dict] = {}
        self.paginas: dict[str, dict] = {}
        self.yoast: list[dict] = []
        self.status: list[dict] = []
        self.midia: list[str] = []
        self._id = 100

    def _novo_id(self) -> int:
        self._id += 1
        return self._id

    def create_post(self, title, content, slug, status, post_type, featured_media=None):
        pid = self._novo_id()
        self.posts[slug] = {"id": pid, "title": title, "content": content, "status": status,
                            "post_type": post_type, "featured_media": featured_media}
        return {"id": pid, "slug": slug, "link": f"https://site.exemplo.com.br/?p={pid}"}

    def create_elementor_page(self, title, slug, elementor, status, post_type="pages",
                              page_settings=None):
        pid = self._novo_id()
        self.paginas[slug] = {"id": pid, "title": title, "elementor": elementor,
                              "status": status, "post_type": post_type}
        return {"id": pid, "slug": slug, "link": f"https://site.exemplo.com.br/?p={pid}"}

    def upload_media(self, data, filename, mime="image/webp", alt=""):
        self.midia.append(filename)
        return {"id": 900 + len(self.midia),
                "source_url": f"https://site.exemplo.com.br/wp-content/uploads/{filename}",
                "alt_text": alt}

    def set_yoast(self, post_id, post_type, fields, status=None):
        self.yoast.append({"post_id": post_id, "fields": fields, "status": status})
        return {}

    def set_status(self, post_id, post_type, status):
        self.status.append({"post_id": post_id, "status": status})
        return {}


def settings_do_revisor(tmp_path: Path, *, publish_status: str | None = None):
    settings = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    if publish_status is not None:
        settings.run.publish_status = publish_status  # type: ignore[assignment]
    return settings


def rodar_fluxo(tmp_path: Path, monkeypatch, arquitetura: dict, *, responder: Callable,
                publish: bool = True, settings=None, wp: WordPressFalso | None = None,
                timestamp: str = "20260930-120000"):
    congelar_data(monkeypatch)
    settings = settings or settings_do_revisor(tmp_path)
    llm, deps = montar_deps(tmp_path, settings, responder)
    wp = wp or WordPressFalso()
    deps.publisher = wp
    plano = plano_do_funnel_architecture(copy.deepcopy(arquitetura))
    state = run_pipeline(None, deps, only=None, publish=publish, plan=plano,
                         timestamp=timestamp)
    return state, deps, llm, wp


def retomar(state, deps, *, publish: bool = True, only: str | None = None):
    return run_pipeline(None, deps, only=only, publish=publish, resume_state=state)


def chamadas_do_revisor(llm, numero: int) -> list[str]:
    saida = []
    for c in llm.calls:
        prompt = texto_da_mensagem(c["messages"][-1])
        if MARCA_DO_REVISOR in prompt and numero_da_pagina_no_revisor(prompt) == numero:
            saida.append(prompt)
    return saida
