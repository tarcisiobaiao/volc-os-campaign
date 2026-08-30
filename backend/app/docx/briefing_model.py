"""
Briefing de Funil — o MODELO da composição (uma vez só, sem renderizar nada).

Por que este arquivo existe: o briefing tem DUAS saídas — o `.docx` que vai
anexado na task do ClickUp e a página HTML que o operador abre em nova aba. Se
cada saída decidisse por conta própria quais campos entram, em que ordem e sob
que rótulo, seriam duas verdades sobre o mesmo documento — e elas divergiriam
na primeira mudança de rótulo. Aqui a decisão é tomada uma vez; `funnel_briefing`
(DOCX) e `briefing_html` (HTML) só DESENHAM o que este módulo já decidiu.

Ausente é buraco, nunca zero: o modelo carrega `None` quando o campo não veio do
`page_factory`/arquiteto, e quem decide como mostrar o buraco é o renderizador
(o DOCX escreve "—"; o HTML marca com a classe `ausente`). Nada aqui inventa
valor de exemplo nem substitui ausência por default.

Entrada:
  card   -> EntityCard (nome/país/idioma da entidade)
  funnel -> saída do EntityFunnelOrchestrator.run:
            {funnel_strategy, pages[], writing_jobs[], funnel_hypotheses[]}
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.entities.funnel_roles import role_for_position

_MONTHS_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL", 5: "MAIO", 6: "JUNHO",
    7: "JULHO", 8: "AGOSTO", 9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
}

BRAND = "VOLC"

# O travessão do documento. Só o CABEÇALHO da página o usa embutido (um título
# ausente não pode virar um H2 vazio); os demais campos viajam como `None` e
# cada renderizador decide como mostrar o buraco.
DASH = "—"


def _slug(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    norm = re.sub(r"[^A-Za-z0-9]+", "_", norm).strip("_")
    return norm or "Entidade"


def briefing_filename(card: Dict[str, Any], year: int) -> str:
    e = card.get("entity") or {}
    ent = _slug(e.get("canonical_name") or "Entidade")
    country = _slug(e.get("country") or card.get("country_code") or "")
    return f"Briefing_Funil_{ent}_{country}_{year}_{BRAND}.docx"


def _wjobs_by_page(writing_jobs: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for j in writing_jobs or []:
        wb = j.get("writer_briefing") or {}
        try:
            pn = int(wb.get("page_num"))
        except (TypeError, ValueError):
            continue
        out[pn] = {**wb, "page_type": j.get("page_type")}
    return out


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Diretrizes:
    """`intro_section` / `closing_section` da página.

    O arquiteto hoje devolve ARRAY de bullets em pt-BR (diretriz para o redator);
    funis gerados antes dessa mudança ainda trazem string de prosa. Os dois casos
    convivem no mesmo tipo — `prosa` preenchida é o legado, e o renderizador
    escolhe entre lista e parágrafo sem precisar reinspecionar o dado bruto.
    """

    titulo: str
    bullets: List[str] = field(default_factory=list)
    prosa: Optional[str] = None


@dataclass(frozen=True)
class FichaCampo:
    """Linha da ficha de redação. `valor=None` é ausência REAL do campo."""

    rotulo: str
    valor: Optional[str]


@dataclass(frozen=True)
class PaginaBriefing:
    posicao: int
    titulo: Optional[str]
    papel: Optional[str]
    # o cabeçalho LIDERA com o papel (Landing Page / Pre-sell / Solução N) — o
    # título vem em seguida, mais congruente com a etiqueta.
    cabecalho: str
    slug: Optional[str]
    objetivo: Optional[str]
    introducao: Optional[Diretrizes]
    estrutura_h2: List[str]
    fechamento: Optional[Diretrizes]
    links_internos: List[str]
    # vazia quando a página não tem nem keywords nem CTA: ficha sem nada dentro
    # seria uma tabela de travessões, não um dado.
    ficha: List[FichaCampo]


@dataclass(frozen=True)
class BriefingModel:
    # identidade do documento
    titulo_documento: str
    descricao: str
    nome_arquivo_docx: str
    # capa
    capa_titulo: str
    entidade: str
    capa_subtitulo_1: str
    capa_subtitulo_2: str
    pais: str
    periodo: str
    # estratégia
    nome_funil: str
    avatar: Optional[str]
    tom: Optional[str]
    arquitetura: Optional[str]
    # corpo
    paginas: List[PaginaBriefing]
    # preenchido SÓ quando não há páginas — o documento precisa dizer o que houve
    aviso_sem_paginas: Optional[str]


def _diretrizes(valor: Any, titulo: str) -> Optional[Diretrizes]:
    if not valor:
        return None
    if isinstance(valor, list):
        bullets = [str(b) for b in valor if b]
        return Diretrizes(titulo=titulo, bullets=bullets) if bullets else None
    return Diretrizes(titulo=titulo, prosa=str(valor))


def build_briefing_model(
    card: Dict[str, Any],
    funnel: Dict[str, Any],
    *,
    month: int = 7,
    year: int = 2026,
) -> BriefingModel:
    """Decide o briefing inteiro: quais campos, em que ordem, com que rótulo."""
    e = card.get("entity") or {}
    name = e.get("canonical_name") or "Entidade"
    full = e.get("full_name") or name
    country = e.get("country") or card.get("country_code") or ""

    strategy = funnel.get("funnel_strategy") or {}
    pages = sorted(funnel.get("pages") or [], key=lambda p: p.get("position") or 0)
    jobs_by_page = _wjobs_by_page(funnel.get("writing_jobs") or [])
    hyps = funnel.get("funnel_hypotheses") or []
    funnel_name = (hyps[-1].get("title") if hyps else None) or f"Funil de {name}"
    periodo = f"{_MONTHS_PT.get(month, '').title()} {year}".strip()

    paginas: List[PaginaBriefing] = []
    for p in pages:
        pos = p.get("position") or 0
        titulo = str(p.get("page_title")) if p.get("page_title") else None
        papel = p.get("role_label") or role_for_position(pos)[1]
        wb = jobs_by_page.get(pos, {})
        slug = (wb.get("current_url") or "").strip() or None
        objetivo = p.get("emotional_goal") or wb.get("objective") or None
        kws = wb.get("keywords")
        cta = wb.get("cta_text")
        ficha: List[FichaCampo] = []
        if kws or cta:
            ficha = [
                FichaCampo("Keywords-alvo", str(kws) if kws else None),
                FichaCampo("CTA", str(cta) if cta else None),
                FichaCampo("Link do CTA", str(wb.get("cta_link")) if wb.get("cta_link") else None),
                FichaCampo("Slug", f"/{slug}" if slug else None),
            ]
        paginas.append(
            PaginaBriefing(
                posicao=pos,
                titulo=titulo,
                papel=papel,
                cabecalho=f"{papel} · {titulo or DASH}" if papel else (titulo or DASH),
                slug=slug,
                objetivo=str(objetivo) if objetivo else None,
                introducao=_diretrizes(p.get("intro_section"), "Introdução (diretrizes)"),
                estrutura_h2=[str(s) for s in (p.get("subtitles") or [])],
                fechamento=_diretrizes(p.get("closing_section"), "Fechamento (diretrizes)"),
                links_internos=[str(l) for l in (p.get("internal_links") or [])],
                ficha=ficha,
            )
        )

    return BriefingModel(
        titulo_documento=f"Briefing de Funil — {name} {year}",
        descricao=f"Briefing do funil da entidade {name} ({country})",
        nome_arquivo_docx=briefing_filename(card, year),
        capa_titulo="Briefing de Funil",
        entidade=name,
        capa_subtitulo_1=full if full != name else (e.get("entity_category") or ""),
        capa_subtitulo_2=f"{country}  |  {periodo}",
        pais=str(country or ""),
        periodo=periodo,
        nome_funil=funnel_name,
        avatar=str(strategy.get("avatar_summary")) if strategy.get("avatar_summary") else None,
        tom=str(strategy.get("tone_voice")) if strategy.get("tone_voice") else None,
        arquitetura=(
            f"{len(paginas)} páginas em jornada de captação → utilidade → conversão."
            if paginas else None
        ),
        paginas=paginas,
        aviso_sem_paginas=(
            None if paginas
            else "O arquiteto não retornou páginas. Rode o gerador de funil novamente."
        ),
    )


# O briefing NÃO expõe `insights` nem `task_description`, de propósito:
#   · `insights` é direcionamento para o agente de funil (user prompt) — texto
#     de bastidor, escrito para a máquina, não para o redator;
#   · `task_description` é o corpo da task no ClickUp, e já aparece lá.
# Antes, o `insights` saía num box "Registrado pelo admin" no fim do DOCX: o
# prompt vazava para dentro do material entregue. A regra vale para as DUAS
# saídas — por isso mora aqui, no modelo, e não num dos renderizadores.
