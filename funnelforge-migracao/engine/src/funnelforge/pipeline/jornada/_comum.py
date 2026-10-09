"""O que as quatro réguas da jornada compartilham: termos, grafo do plano,
classificação da saída oficial e o ESTADO DO LEITOR por caminho."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from funnelforge.domain.models import FunnelPlan, Page, PageRole, effective_role

_STOP = frozenset({
    "como", "seu", "sua", "seus", "suas", "para", "pelo", "pela", "fazer", "quem",
    "pode", "sobre", "qual", "quais", "onde", "minha", "meu", "meus", "minhas",
    "esta", "este", "isso", "isto", "mais", "voce", "voces", "cada", "entre",
    "depois", "antes", "aqui", "ver", "veja", "achar", "escolher", "clique",
    "ainda", "tambem", "quando", "porque", "pois", "ate", "sem", "com", "nos",
    "das", "dos", "que", "uma", "uns", "umas", "num", "numa",
})

#: Teto de caminhos enumerados por página. Um funil tem ~5 páginas; o teto só
#: existe para que um plano patológico não trave o motor.
_MAX_CAMINHOS = 2000


def sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(ch for ch in normal if not unicodedata.combining(ch)).lower()


def _palavras_unicode(texto: str) -> list[str]:
    """Palavras em qualquer escrita, sem voltar ao bug ASCII do tailandês.

    NFKD continua tornando o português tolerante a acentos; letras e números
    de outros alfabetos permanecem. Marcas combinantes são ignoradas somente
    para comparação, nunca para conteúdo ou `duvida_id`.
    """
    normal = unicodedata.normalize("NFKD", texto or "").casefold()
    partes = []
    for ch in normal:
        if unicodedata.combining(ch):
            continue
        partes.append(ch if unicodedata.category(ch)[:1] in {"L", "N"} else " ")
    limpo = "".join(partes)
    return limpo.split()


def tokens(texto: str) -> set[str]:
    return {t for t in _palavras_unicode(texto) if len(t) >= 4 and t not in _STOP}


def norm(texto: str) -> str:
    return " ".join(_palavras_unicode(texto))


def tem_jornada(plan: FunnelPlan | None) -> bool:
    return bool(plan and (plan.jornada is not None
                          or any(p.jornada is not None for p in plan.pages)))


def por_slug(plan: FunnelPlan) -> dict[str, Page]:
    return {p.slug: p for p in plan.pages}


def por_duvida(plan: FunnelPlan) -> dict[str, Page]:
    return {p.jornada.duvida_id: p for p in plan.pages if p.jornada is not None}


def links(page: Page) -> list:
    return list(page.editorial.links) if page.editorial is not None else []


def cta_do_link(link, alvo: Page) -> str:
    """O texto do botão DESTA origem para `alvo`: o `cta` do link quando o
    arquiteto o declarou; senão, o rótulo de entrada do destino (como antes)."""
    proprio = (getattr(link, "cta", "") or "").strip()
    if proprio:
        return proprio
    return alvo.editorial.cta_label if alvo.editorial is not None else ""


def rotulo(page: Page) -> str:
    return page.jornada.duvida_id if page.jornada else page.slug


def justificado(origem: Page, destino: Page) -> str:
    if origem.jornada is None or destino.jornada is None:
        return ""
    return (origem.jornada.retornos_justificados.get(destino.jornada.duvida_id) or "").strip()


def adjacencia(plan: FunnelPlan) -> dict[str, list[str]]:
    slugs = por_slug(plan)
    return {p.slug: [l.target for l in links(p) if l.target in slugs] for p in plan.pages}


# ---------------------------------------------------------------------------
# saída oficial
# ---------------------------------------------------------------------------

def classificar_saida_oficial(page: Page) -> str:
    """`boa` | `prematura` | `nao_aplicavel`, por regra declarada:

    - sem saída esperada -> não se aplica;
    - justificativa explícita do arquiteto -> boa (e fica registrada);
    - na LP -> prematura: o leitor ainda não se qualificou;
    - com condição terminal declarada (a tarefa da página está resolvida) -> boa;
    - qualquer outro caso -> prematura.
    """
    j = page.jornada
    if j is None or not j.saida_oficial.esperada:
        return "nao_aplicavel"
    if j.saida_oficial.justificativa.strip():
        return "boa"
    if effective_role(page) is PageRole.LP:
        return "prematura"
    if j.condicao_terminal.strip():
        return "boa"
    return "prematura"


def conclusiva(page: Page) -> bool:
    j = page.jornada
    return bool(j and (j.condicao_terminal.strip() or classificar_saida_oficial(page) == "boa"))


# ---------------------------------------------------------------------------
# ciclos
# ---------------------------------------------------------------------------

def ciclos(adj: dict[str, list[str]]) -> list[list[str]]:
    """Ciclos elementares, cada um uma vez (começando no menor nó)."""
    achados: list[list[str]] = []
    for inicio in sorted(adj):
        pilha: list[tuple[str, list[str]]] = [(inicio, [inicio])]
        while pilha:
            no, caminho = pilha.pop()
            for prox in adj.get(no, []):
                if prox == inicio and len(caminho) > 1:
                    achados.append(list(caminho))
                elif prox not in caminho and prox > inicio:
                    pilha.append((prox, [*caminho, prox]))
    return achados


def descreve_ciclo(ciclo: list[str], slugs: dict[str, Page]) -> str:
    nomes = [rotulo(slugs[s]) for s in ciclo]
    return " → ".join([*nomes, nomes[0]])


def ciclo_justificado(ciclo: list[str], slugs: dict[str, Page]) -> str:
    for a, b in zip(ciclo, [*ciclo[1:], ciclo[0]]):
        motivo = justificado(slugs[a], slugs[b])
        if motivo:
            return motivo
    return ""


# ---------------------------------------------------------------------------
# entradas e estado do leitor POR CAMINHO
# ---------------------------------------------------------------------------

def entradas(plan: FunnelPlan) -> dict[str, list[str]]:
    """slug -> rótulos de entrada. A LP é entrada; toda página com
    `coortes_de_entrada` é entrada direta; toda coorte do funil também."""
    saida: dict[str, list[str]] = {}
    for p in plan.pages:
        if effective_role(p) is PageRole.LP:
            saida.setdefault(p.slug, []).append("lp")
        if p.jornada is not None:
            for canal in p.jornada.coortes_de_entrada:
                saida.setdefault(p.slug, []).append(f"{canal}:{p.jornada.duvida_id}")
    if plan.jornada is not None:
        duvidas = por_duvida(plan)
        for c in plan.jornada.coortes:
            if c.entrada in duvidas:
                saida.setdefault(duvidas[c.entrada].slug, []).append(f"{c.canal}:{c.entrada}")
    return {s: list(dict.fromkeys(r)) for s, r in saida.items()}


@dataclass
class EstadoDoLeitor:
    """O que o leitor já resolveu ao chegar a uma página.

    `certamente`: resolvido em TODO caminho de qualquer entrada até aqui (uma
    página que é ela mesma entrada tem `certamente` vazio — quem chega direto
    não resolveu nada). `possivelmente`: resolvido em ALGUM caminho, mais o que
    o arquiteto declarou em `ja_resolvido` para o caminho planejado.
    `por_entrada`: o certo para quem vem de cada entrada (coorte ou LP)."""
    certamente: set[str] = field(default_factory=set)
    possivelmente: set[str] = field(default_factory=set)
    por_entrada: dict[str, set[str]] = field(default_factory=dict)


def _caminhos(adj: dict[str, list[str]], origem: str, alvo: str) -> list[list[str]]:
    achados: list[list[str]] = []
    pilha: list[list[str]] = [[origem]]
    while pilha and len(achados) < _MAX_CAMINHOS:
        caminho = pilha.pop()
        no = caminho[-1]
        if no == alvo:
            achados.append(caminho)
            continue
        for prox in adj.get(no, []):
            if prox not in caminho:
                pilha.append([*caminho, prox])
    return achados


def estado_do_leitor(plan: FunnelPlan, page: Page) -> EstadoDoLeitor:
    if page.jornada is None:
        return EstadoDoLeitor()
    adj, slugs = adjacencia(plan), por_slug(plan)
    duvidas = set(por_duvida(plan))

    def resolvidas(caminho: list[str]) -> set[str]:
        return {slugs[s].jornada.duvida_id for s in caminho[:-1]
                if slugs[s].jornada is not None}

    estado = EstadoDoLeitor()
    todos: list[set[str]] = []
    for origem, rotulos in entradas(plan).items():
        conjuntos = [resolvidas(c) for c in _caminhos(adj, origem, page.slug)]
        if not conjuntos:
            continue
        todos.extend(conjuntos)
        certo = set.intersection(*conjuntos)
        for r in rotulos:
            estado.por_entrada[r] = certo
    estado.certamente = set.intersection(*todos) if todos else set()
    estado.possivelmente = (set().union(*todos) if todos else set()) | {
        d for d in page.jornada.ja_resolvido if d in duvidas}
    estado.possivelmente.discard(page.jornada.duvida_id)
    return estado
