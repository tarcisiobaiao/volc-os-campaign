"""
Briefing de Funil (DOCX) — Pautador Pro / VOLC.

Documento ENXUTO: só o briefing do funil. Este arquivo é UM RENDERIZADOR — ele
desenha em DOCX o que `briefing_model.build_briefing_model` já decidiu (quais
campos, em que ordem, com que rótulo). A outra saída do mesmo modelo é a página
HTML (`briefing_html`), aberta em nova aba pelo operador. Regra: composição só
muda em `briefing_model`; aqui só muda o desenho.

Entrada:
  card   -> EntityCard (nome/país/idioma da entidade)
  funnel -> saída do EntityFunnelOrchestrator.run:
            {funnel_strategy, pages[], writing_jobs[], funnel_hypotheses[]}
Saída: bytes do .docx (marca VOLC, sem cabeçalho/índice).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from . import volc_theme as T
from .briefing_model import (
    BRAND,
    DASH,
    BriefingModel,
    Diretrizes,
    briefing_filename,
    build_briefing_model,
)
from .volc_engine import VolcDocx

__all__ = ["build_funnel_briefing", "briefing_filename"]


def _fmt(v: Optional[str]) -> str:
    """Campo ausente vira travessão — no DOCX o buraco não tem outra marcação."""
    return DASH if v is None or v == "" else str(v)


def _diretrizes(doc: VolcDocx, bloco: Optional[Diretrizes]) -> None:
    """Bullets (formato atual, diretriz para o redator) ou prosa (funil legado)."""
    if bloco is None:
        return
    doc.h3(bloco.titulo)
    if bloco.bullets:
        for bullet in bloco.bullets:
            doc.bullet(bullet)
    elif bloco.prosa:
        doc.para(bloco.prosa)


def render_docx(model: BriefingModel) -> bytes:
    doc = VolcDocx(
        title=model.titulo_documento,
        description=model.descricao,
        brand=BRAND,
        show_header=False,
    )

    # ===== CAPA (limpa, sem classificação/descrições) =====
    doc.cover(
        title1=model.capa_titulo,
        title2=model.entidade,
        subtitle1=model.capa_subtitulo_1,
        subtitle2=model.capa_subtitulo_2,
    )

    # ===== ESTRATÉGIA DO FUNIL =====
    doc.h1(model.nome_funil)
    if model.avatar:
        doc.para_runs([
            {"text": "Avatar: ", "bold": True, "color": T.COLORS["gold"]},
            {"text": model.avatar},
        ])
    if model.tom:
        doc.para_runs([
            {"text": "Tom de voz: ", "bold": True, "color": T.COLORS["gold"]},
            {"text": model.tom},
        ])
    if model.arquitetura:
        doc.para_runs([
            {"text": "Arquitetura: ", "bold": True, "color": T.COLORS["gold"]},
            {"text": model.arquitetura},
        ])

    # ===== PÁGINAS DO FUNIL (o briefing em si) =====
    for pag in model.paginas:
        doc.h2(pag.cabecalho)

        # 'Papel:' não aparece aqui (já está no cabeçalho). Sobra só a URL.
        if pag.slug:
            doc.para_runs([
                {"text": "URL: ", "bold": True, "color": T.COLORS["navySoft"]},
                {"text": f"/{pag.slug}", "color": T.COLORS["slate"]},
            ])

        if pag.objetivo:
            doc.para_runs([
                {"text": "Objetivo da página: ", "bold": True, "color": T.COLORS["gold"]},
                {"text": pag.objetivo},
            ])

        # a introdução vem ANTES da lista de H2 e o fechamento DEPOIS: a ordem é
        # a da página que o redator vai escrever, não a do JSON do arquiteto.
        _diretrizes(doc, pag.introducao)

        if pag.estrutura_h2:
            doc.h3("Estrutura da página (H2)")
            for s in pag.estrutura_h2:
                doc.bullet(s)

        _diretrizes(doc, pag.fechamento)

        if pag.links_internos:
            doc.h3("Links internos")
            for lk in pag.links_internos:
                doc.bullet(lk)

        if pag.ficha:
            doc.h3("Ficha de redação")
            doc.data_table(
                ["Campo", "Valor"],
                [[c.rotulo, _fmt(c.valor)] for c in pag.ficha],
                [2600, 6760],
            )
        doc.spacer("lg")

    if model.aviso_sem_paginas:
        doc.note_box(model.aviso_sem_paginas)

    return doc.to_bytes()


# ---------------------------------------------------------------------------
def build_funnel_briefing(
    card: Dict[str, Any],
    funnel: Dict[str, Any],
    *,
    month: int = 7,
    year: int = 2026,
) -> bytes:
    return render_docx(build_briefing_model(card, funnel, month=month, year=year))
