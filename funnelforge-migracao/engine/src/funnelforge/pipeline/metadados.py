"""METADADOS E DADOS ESTRUTURADOS por página — determinísticos, sem LLM.

Reaproveita o que o pipeline já tem: o SEO da página (`state.seo`), a decisão
de indexação (`index_decision_for`), a pesquisa (fontes), a publicação (data e
URL) e a jornada (o tipo de entrega). Nenhuma chamada paga serializa JSON-LD.

Schema só entra quando o CONTEÚDO VISÍVEL o comprova:
- WebPage (LP) / Article (internas) e BreadcrumbList — sempre;
- FAQPage — só com perguntas E respostas visíveis (FAQ da LP ou `<details>`);
- HowTo — só com passos reais: lista numerada visível numa página cuja jornada
  declara a entrega `passo_a_passo`;
- ItemList — só com checklist visível numa página que declara `checklist`.

Nada de schema para promessa, dado invisível ou falsa oficialidade: o autor e o
publisher são o site editorial, nunca o órgão. `validar_json_ld` confere
sintaxe, URLs, datas e correspondência com o texto visível; o que não passa é
recusado e registrado, não "consertado".
"""
from __future__ import annotations

import json
import re
from datetime import date
from html import unescape
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from funnelforge.domain.models import Page, PageRole, ResearchFacts, RunState, effective_role

_TAG_RE = re.compile(r"<[^>]+>")
_DETAILS_RE = re.compile(r"<details\b[^>]*>\s*<summary\b[^>]*>(.*?)</summary>(.*?)</details>",
                         re.I | re.S)
_OL_RE = re.compile(r"<ol\b[^>]*>(.*?)</ol>", re.I | re.S)
_UL_RE = re.compile(r"<ul\b[^>]*>(.*?)</ul>", re.I | re.S)
_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)


class MetadadosDaPagina(BaseModel):
    title: str = ""
    meta_description: str = ""
    canonical: str = ""
    canonical_estado: str = "previsto"      # previsto (rascunho) | publicado
    robots: str = ""
    open_graph: dict[str, str] = {}
    twitter_card: dict[str, str] = {}
    breadcrumb: list[dict[str, str]] = []
    autor: str = ""
    editor: str = ""
    publicado_em: str | None = None
    atualizado_em: str = ""
    imagem_social: str | None = None
    assunto: str = ""
    entidade: str = ""
    fontes: list[str] = []
    tipo_de_pagina: str = ""
    json_ld: list[dict[str, Any]] = []
    schemas_recusados: list[dict[str, str]] = []


def _limpo(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", html or ""))).strip()


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def texto_visivel(conteudo: str, formato: str) -> str:
    if formato == "lp_json":
        try:
            obj = json.loads(conteudo)
        except (TypeError, ValueError):
            return _limpo(conteudo)
        partes: list[str] = []

        def andar(v: Any) -> None:
            if isinstance(v, str):
                partes.append(v)
            elif isinstance(v, dict):
                for x in v.values():
                    andar(x)
            elif isinstance(v, list):
                for x in v:
                    andar(x)
        andar(obj)
        return _limpo(" ".join(partes))
    return _limpo(conteudo)


def _perguntas_visiveis(conteudo: str, formato: str) -> list[tuple[str, str]]:
    pares: list[tuple[str, str]] = []
    if formato == "lp_json":
        try:
            faq = json.loads(conteudo).get("faq") or []
        except (TypeError, ValueError, AttributeError):
            faq = []
        for item in faq if isinstance(faq, list) else []:
            if isinstance(item, dict):
                pares.append((_limpo(str(item.get("q") or "")), _limpo(str(item.get("a") or ""))))
    else:
        for q, a in _DETAILS_RE.findall(conteudo):
            pares.append((_limpo(q), _limpo(a)))
    return [(q, a) for q, a in pares if q and a]


def _itens(regex: re.Pattern, conteudo: str) -> list[str]:
    m = regex.search(conteudo or "")
    if not m:
        return []
    return [t for t in (_limpo(x) for x in _LI_RE.findall(m.group(1))) if t]


def url_da_pagina(page: Page, settings: Any) -> str:
    site = settings.site
    tipo = site.lp_post_type if effective_role(page) is PageRole.LP else site.post_type
    return f"{site.domain.rstrip('/')}/{tipo}/{page.slug.strip('/')}/"


def metadados_da_pagina(state: RunState, page: Page, settings: Any, *,
                        hoje: date, robots: str) -> MetadadosDaPagina:
    n = page.page_number
    draft = state.drafts.get(n)
    conteudo, formato = (draft.content, draft.format) if draft else ("", "")
    seo = state.seo.get(n) or {}
    publicado = state.published.get(n) or {}
    facts = state.facts.get(n, ResearchFacts(sparse=True))
    papel = effective_role(page)
    url = url_da_pagina(page, settings)
    no_ar = str(publicado.get("status_wp") or "") == "publish" and publicado.get("url_wp")
    canonical = str(publicado.get("url_wp")) if no_ar else url
    titulo = str(seo.get("seotitle") or page.h1_title)
    descricao = str(seo.get("metadescription") or "")
    autor = settings.site.author_name
    imagem = state.images.get(n) if str(state.images.get(n) or "").startswith("https://") else None
    fontes = list(dict.fromkeys([*(state.official_links.get(n) or []),
                                 *(facts.fontes_resolvidas or [])]))
    assunto = (page.jornada.pergunta_principal if page.jornada
               else (page.target_keywords[0] if page.target_keywords else page.h1_title))
    entidade = (state.plan.jornada.intencao_principal
                if state.plan and state.plan.jornada else "")
    meta = MetadadosDaPagina(
        title=titulo, meta_description=descricao, canonical=canonical,
        canonical_estado="publicado" if no_ar else "previsto", robots=robots,
        open_graph={"og:type": "article" if papel is not PageRole.LP else "website",
                    "og:title": titulo, "og:description": descricao, "og:url": canonical,
                    **({"og:image": imagem} if imagem else {})},
        twitter_card={"twitter:card": "summary_large_image" if imagem else "summary",
                      "twitter:title": titulo, "twitter:description": descricao},
        breadcrumb=[{"nome": "Início", "url": settings.site.domain.rstrip("/") + "/"},
                    {"nome": page.h1_title, "url": canonical}],
        autor=autor, editor=autor,
        publicado_em=hoje.isoformat() if no_ar else None,
        atualizado_em=hoje.isoformat(), imagem_social=imagem, assunto=assunto,
        entidade=entidade, fontes=fontes, tipo_de_pagina=papel.value,
    )
    meta.json_ld, meta.schemas_recusados = _json_ld(page, meta, conteudo, formato, settings)
    return meta


def _json_ld(page: Page, meta: MetadadosDaPagina, conteudo: str, formato: str,
             settings: Any) -> tuple[list[dict], list[dict]]:
    org = {"@type": "Organization", "name": meta.autor,
           "url": settings.site.domain.rstrip("/") + "/"}
    principal: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "WebPage" if effective_role(page) is PageRole.LP else "Article",
        "headline" if effective_role(page) is not PageRole.LP else "name": page.h1_title[:110],
        "url": meta.canonical, "inLanguage": "pt-BR",
        "dateModified": meta.atualizado_em,
        **({"datePublished": meta.publicado_em} if meta.publicado_em else {}),
        **({"description": meta.meta_description} if meta.meta_description else {}),
        **({"author": org, "publisher": org} if effective_role(page) is not PageRole.LP else {}),
        **({"about": meta.assunto} if meta.assunto else {}),
        **({"citation": meta.fontes} if meta.fontes else {}),
    }
    blocos: list[dict] = [principal, {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": b["nome"], "item": b["url"]}
                            for i, b in enumerate(meta.breadcrumb, start=1)]}]
    perguntas = _perguntas_visiveis(conteudo, formato)
    if perguntas:
        blocos.append({"@context": "https://schema.org", "@type": "FAQPage",
                       "mainEntity": [{"@type": "Question", "name": q,
                                       "acceptedAnswer": {"@type": "Answer", "text": a}}
                                      for q, a in perguntas]})
    entregas = set(page.jornada.valor.entregas) if page.jornada and page.jornada.valor else set()
    passos = _itens(_OL_RE, conteudo) if formato != "lp_json" else []
    if "passo_a_passo" in entregas and len(passos) >= 2:
        blocos.append({"@context": "https://schema.org", "@type": "HowTo", "name": page.h1_title,
                       "step": [{"@type": "HowToStep", "position": i, "text": t}
                                for i, t in enumerate(passos, start=1)]})
    itens = _itens(_UL_RE, conteudo) if formato != "lp_json" else []
    if "checklist" in entregas and len(itens) >= 2:
        blocos.append({"@context": "https://schema.org", "@type": "ItemList", "name": page.h1_title,
                       "itemListElement": [{"@type": "ListItem", "position": i, "name": t}
                                           for i, t in enumerate(itens, start=1)]})
    visivel = texto_visivel(conteudo, formato)
    aceitos, recusados = [], []
    for bloco in blocos:
        motivos = validar_json_ld(bloco, visivel, settings)
        if motivos:
            recusados.append({"tipo": str(bloco.get("@type")), "motivo": "; ".join(motivos)})
        else:
            aceitos.append(bloco)
    return aceitos, recusados


_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validar_json_ld(bloco: dict, visivel: str, settings: Any) -> list[str]:
    """O que impede este bloco de ir ao ar. Lista vazia = válido."""
    motivos: list[str] = []
    try:
        json.loads(json.dumps(bloco, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        return [f"sintaxe: {exc}"]
    if bloco.get("@context") != "https://schema.org" or not bloco.get("@type"):
        motivos.append("sem @context/@type")
    host = urlparse(settings.site.domain).netloc.lower()
    for chave in ("url",):
        v = bloco.get(chave)
        if v and (not str(v).startswith("https://") or urlparse(str(v)).netloc.lower() != host):
            motivos.append(f"{chave} fora do domínio do site: {v}")
    for chave in ("dateModified", "datePublished"):
        v = bloco.get(chave)
        if v is not None and not _DATA_RE.match(str(v)):
            motivos.append(f"{chave} não é data ISO: {v}")
    alvo = _norm(visivel)
    tipo = bloco.get("@type")
    if tipo == "FAQPage":
        for q in bloco.get("mainEntity") or []:
            pergunta = q.get("name", "")
            resposta = (q.get("acceptedAnswer") or {}).get("text", "")
            if _norm(pergunta) not in alvo or _norm(resposta) not in alvo:
                motivos.append(f"pergunta/resposta não visível: {pergunta[:60]}")
    if tipo == "HowTo":
        for passo in bloco.get("step") or []:
            if _norm(passo.get("text", "")) not in alvo:
                motivos.append(f"passo não visível: {passo.get('text', '')[:60]}")
    if tipo == "ItemList":
        for item in bloco.get("itemListElement") or []:
            if _norm(item.get("name", "")) not in alvo:
                motivos.append(f"item não visível: {item.get('name', '')[:60]}")
    if tipo in ("Article", "WebPage"):
        for org in (bloco.get("author"), bloco.get("publisher")):
            if isinstance(org, dict) and org.get("@type") in ("GovernmentOrganization",):
                motivos.append("autor/publisher como órgão público: falsa oficialidade")
    return motivos
