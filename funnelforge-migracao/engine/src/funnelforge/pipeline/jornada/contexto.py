"""O CONTEXTO da jornada de uma página: o que redator, juiz, briefing e revisor
recebem, e a política da saída oficial que o roteador obedece."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from funnelforge.domain.models import FunnelPlan, Page, PageRole, effective_role
from funnelforge.pipeline.jornada._comum import (
    classificar_saida_oficial,
    estado_do_leitor,
    justificado,
    links,
    por_duvida,
    por_slug,
)
from funnelforge.pipeline.jornada.esqueleto import ativo_completo


def alvo_da_proxima_duvida(plan: FunnelPlan, page: Page) -> str | None:
    """O slug do destino que resolve a próxima dúvida (o CTA principal)."""
    if page.jornada is None or not page.jornada.proxima_duvida:
        return None
    slugs = por_slug(plan)
    for link in links(page):
        alvo = slugs.get(link.target)
        if alvo is not None and alvo.jornada is not None and (
                alvo.jornada.duvida_id == page.jornada.proxima_duvida):
            return alvo.slug
    return None


def ativos_validos(page: Page) -> list:
    """Os ativos interativos com especificação completa. Os incompletos não
    são gerados (o revisor de esqueleto já avisou)."""
    if page.jornada is None:
        return []
    return [a for a in page.jornada.ativos if not ativo_completo(a)]


@dataclass(frozen=True)
class PoliticaDaSaidaOficial:
    """Quem manda na rota `external_official` quando a página tem jornada."""
    exige: bool            # a rota oficial é obrigatória (fail-closed sem fonte)
    classe: str            # boa | prematura | nao_aplicavel
    primeiro: bool         # boa vem antes dos CTAs internos; prematura, depois


def politica_da_saida_oficial(page: Page) -> PoliticaDaSaidaOficial | None:
    """None = página sem jornada (o roteador segue a regra de papel/posição).

    Com jornada: só há rota oficial quando a saída é ESPERADA e a página não é
    a LP (o template da LP não renderiza link oficial). `nao_aplicavel` nunca é
    obrigada; `boa` e `prematura` exigem fonte comprovada — sem ela, a página
    falha fechada como sempre (`target_missing`)."""
    if page.jornada is None:
        return None
    classe = classificar_saida_oficial(page)
    exige = classe != "nao_aplicavel" and effective_role(page) is not PageRole.LP
    return PoliticaDaSaidaOficial(exige=exige, classe=classe, primeiro=classe == "boa")


def contexto_de_jornada(plan: FunnelPlan | None, page: Page,
                        dossie: dict | None = None) -> dict[str, Any]:
    """O contrato da jornada desta página, pronto para o prompt. `{}` quando a
    página não tem jornada — e aí os templates não mudam um byte."""
    if plan is None or page.jornada is None:
        return {}
    j = page.jornada
    slugs, duvidas = por_slug(plan), por_duvida(plan)
    principal = alvo_da_proxima_duvida(plan, page)
    estado = estado_do_leitor(plan, page)

    def pergunta(d: str) -> str:
        return duvidas[d].jornada.pergunta_principal if d in duvidas else d

    destinos = []
    for link in links(page):
        alvo = slugs.get(link.target)
        if alvo is None or alvo.jornada is None:
            continue
        duvida = alvo.jornada.duvida_id
        destinos.append({
            "slug": alvo.slug,
            "cta": alvo.editorial.cta_label if alvo.editorial else "",
            "resolve": alvo.jornada.pergunta_principal,
            "motivo": link.reason,
            "principal": alvo.slug == principal,
            # `contextual`: resolvida só em parte dos caminhos — CTA secundário
            # e condicional ("se você ainda não fez a conta...").
            "contextual": duvida in estado.possivelmente and duvida not in estado.certamente,
            "retorno_justificado": justificado(page, alvo),
        })
    destinos.sort(key=lambda d: not d["principal"])
    valor = j.valor.model_dump() if j.valor else {}
    projecao = _projecao(dossie, page.page_number)
    desativados = {(d.get("tipo"), d.get("nome")) for d in projecao.get("desativados", [])}
    return {
        "papel": effective_role(page).value,
        "duvida_id": j.duvida_id,
        "pergunta": j.pergunta_principal,
        "trabalho": j.trabalho_do_leitor,
        "resposta_imediata": j.resposta_imediata,
        "coortes": list(j.coortes_de_entrada),
        "resolvido_em_todo_caminho": [pergunta(d) for d in sorted(estado.certamente)],
        "talvez_resolvido": [pergunta(d) for d in sorted(estado.possivelmente - estado.certamente)],
        "proxima_duvida": pergunta(j.proxima_duvida) if j.proxima_duvida else "",
        "destinos": destinos,
        "condicao_terminal": j.condicao_terminal,
        "entrada_direta": j.entrada_direta,
        "saida_oficial": {"classificacao": classificar_saida_oficial(page),
                          "condicao": j.saida_oficial.condicao,
                          "justificativa": j.saida_oficial.justificativa},
        "monetizacao": j.monetizacao.model_dump(),
        "valor": valor,
        # Bloco ou ferramenta que dependia de dado sem evidência sai do pedido
        # (degradação segura): o resto da página segue.
        "plano_visual": [b.model_dump() for b in j.plano_visual
                         if ("bloco", b.secao) not in desativados],
        "ativos": [a.model_dump() for a in ativos_validos(page)
                   if ("ativo", a.pergunta) not in desativados],
        # O PageDossier (vazio sem dossiê): a mesma projeção para briefing,
        # redator, juiz e revisor.
        "dossie": projecao,
    }


def _projecao(dossie: dict | None, numero: int) -> dict:
    if not dossie:
        return {}
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    return projecao_para_o_prompt(dossie, numero)
