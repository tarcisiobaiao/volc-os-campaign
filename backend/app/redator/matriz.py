"""A matriz páginas × etapas — a tradução do `state.json` para a tela.

## Por que isto existe

Durante os ~45 min e ~US$ 2 que o motor leva para escrever um funil, a linha do
run guardava quatro escalares. O operador não via em qual das 11 etapas o motor
estava, nem que `research_p1` fica até 236 s sem escrever nada, nem que ~80% do
dinheiro já saiu quando a redação da última página fecha — que é justamente a
informação que decide se vale cancelar.

Aqui o `step_status` do motor vira uma grade: uma linha por página, uma coluna
por etapa, uma célula por `StepResult`.

## As duas armadilhas do parse

**A convenção quebra em `page_N`.** Quase toda chave é `<etapa>_p<N>`
(`write_p3`, `image_gen_p2`), mas o pipeline também grava `page_5` — sem o `p`.
Um `split('_p')` ingênuo transforma a exceção da página 5 num passo chamado
`age`. Por isso o parse é regex ancorada, com o caso especial declarado.

**Ausência de chave é ambígua por construção.** Um `widget_p1` que não existe
pode ser: não se aplica (LP não tem widget), a flag está desligada, ainda não
chegou, ou a página morreu antes. A tela não tem como desambiguar sozinha — e
pintar tudo de "pendente" mentiria. Por isso a máscara `aplicaveis` é calculada
AQUI, no servidor, onde os papéis e as flags do run são conhecidos.

## O fluxo editorial v2 tem outra grade

Com `run.editorial_v2` (config do motor ou perfil do funil), cada página ganha
`briefing` antes da redação e `revisor` no lugar do juiz — e o SEO roda ANTES do
revisor, para o título que vira H1 também ser revisado (contrato entre trilhas,
30/09/2026). Um run é v2 quando a flag diz, ou quando um passo v2 já está no
estado. Run antigo continua com as mesmas 11 colunas de sempre.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

# As 11 etapas, na ordem exata do laço de `pipeline.py`. `paga` diz se aquela
# etapa gasta dinheiro — a célula de uma etapa não paga NUNCA exibe "US$ 0,00",
# que sugeriria medição onde não há.
COLUNAS: List[Dict[str, Any]] = [
    {"chave": "research",     "rotulo": "pesquisa",  "paga": True},
    {"chave": "write",        "rotulo": "redação",   "paga": True},
    {"chave": "judge",        "rotulo": "juiz",      "paga": True},
    {"chave": "seo",          "rotulo": "seo",       "paga": True},
    {"chave": "image",        "rotulo": "prompt img", "paga": True},
    {"chave": "image_gen",    "rotulo": "imagem",    "paga": True},
    {"chave": "screenshot",   "rotulo": "print",     "paga": False},
    {"chave": "build",        "rotulo": "build",     "paga": False},
    {"chave": "widget",       "rotulo": "widget",    "paga": True},
    {"chave": "content_gate", "rotulo": "portão",    "paga": False},
    {"chave": "publish",      "rotulo": "publicar",  "paga": False},
]

# A grade do fluxo editorial v2. O `revisor` substitui o `judge` e vem DEPOIS do
# `seo` (o título SEO é o H1 visível das interiores e passa pela revisão).
_POR_CHAVE = {c["chave"]: c for c in COLUNAS}
COLUNAS_EDITORIAL_V2: List[Dict[str, Any]] = [
    _POR_CHAVE["research"],
    {"chave": "briefing",     "rotulo": "briefing",  "paga": True},
    _POR_CHAVE["write"],
    _POR_CHAVE["seo"],
    {"chave": "revisor",      "rotulo": "revisor",   "paga": True},
    *(_POR_CHAVE[c] for c in ("image", "image_gen", "screenshot", "build",
                              "widget", "content_gate", "publish")),
]
ETAPAS_EDITORIAL_V2 = ("briefing", "revisor")

# Toda etapa que é coluna em ALGUMA grade vira célula da página — nunca faixa
# do run. Sem isto, `briefing_p3` cairia na faixa como se fosse passo do run.
CHAVES_DE_COLUNA = {c["chave"] for c in COLUNAS} | {c["chave"] for c in COLUNAS_EDITORIAL_V2}

# Sinônimos de etapa, normalizados antes de tudo. `revisao_pN` é aceito enquanto
# a trilha do motor não fixa o nome do passo (o combinado é `revisor_pN`, como
# `judge_pN`); a célula sai sempre sob a chave da coluna, que é a que a tela lê.
ALIASES_DE_ETAPA = {"revisao": "revisor"}

# Passos que valem para o RUN, não para uma página. Vão numa faixa acima da
# grade — pô-los como coluna criaria 5 colunas vazias em toda linha.
FAIXA_DO_RUN = ("extract", "engajamento", "expand_presell_hubs",
                "funnel_graph", "contract_advisory")

_SUFIXO = re.compile(r"^(?P<etapa>.+)_p(?P<n>\d+)$")
_EXCECAO_PAGE = re.compile(r"^page_(?P<n>\d+)$")


def parse_chave(chave: str) -> tuple[str, Optional[int]]:
    """`write_p3` -> ('write', 3) · `funnel_graph` -> ('funnel_graph', None).

    ⚠️ `page_5` -> ('page', 5), e NÃO ('', 5) nem ('age', 5): o pipeline grava
    essa chave sem o `p` do meio, quebrando a própria convenção. Um
    `split('_p')` a converteria num passo fantasma.
    """
    m = _EXCECAO_PAGE.match(chave)
    if m:
        return "page", int(m.group("n"))
    m = _SUFIXO.match(chave)
    if m:
        return m.group("etapa"), int(m.group("n"))
    return chave, None


def colunas_do_run(editorial_v2: bool = False) -> List[Dict[str, Any]]:
    """A grade deste run: a de sempre, ou a do fluxo editorial v2."""
    return COLUNAS_EDITORIAL_V2 if editorial_v2 else COLUNAS


def _normalizar_passos(passos: Dict[str, Any]) -> Dict[str, Any]:
    """`revisao_p3` -> `revisor_p3`. Se as duas existirem, a canônica vence."""
    saida: Dict[str, Any] = {}
    sinonimos: Dict[str, Any] = {}
    for chave, r in passos.items():
        etapa, n = parse_chave(chave)
        if n is not None and etapa in ALIASES_DE_ETAPA:
            sinonimos[f"{ALIASES_DE_ETAPA[etapa]}_p{n}"] = r
        else:
            saida[chave] = r
    for chave, r in sinonimos.items():
        saida.setdefault(chave, r)
    return saida


def eh_editorial_v2(passos: Dict[str, Any], flags: Optional[Dict[str, Any]] = None) -> bool:
    """O run é do fluxo editorial v2? A flag diz; um passo v2 no estado prova."""
    if (flags or {}).get("editorial_v2") is True:
        return True
    for chave in passos:
        etapa, n = parse_chave(chave)
        if n is not None and etapa in ETAPAS_EDITORIAL_V2:
            return True
    return False


def aplicaveis_da_pagina(
    papel: str, *, engajamento: str = "", featured_image: bool = True,
    tem_screenshot: bool = False, widgets_ligados: bool = False,
    publica: bool = True, gera_imagem: bool = True,
    tem_editorial: bool = False, editorial_v2: bool = False,
) -> List[str]:
    """Quais colunas da grade deste run fazem sentido NESTA página.

    Sem esta máscara a tela não distingue "vazio verdadeiro" de "ainda não
    chegou". No run de referência são 9 ausências estruturais de 63 posições —
    todas legítimas, nenhuma falha.
    """
    p = (papel or "").upper()
    ok = ["research", "write", "seo", "build", "content_gate"]

    if editorial_v2:
        # Toda página tem briefing e é revisada — a LP inclusive, com ou sem
        # `editorial` (contrato entre trilhas, decisão 5). O revisor substitui
        # o juiz.
        ok += ["briefing", "revisor"]
    elif p != "LP" or tem_editorial:
        # A LP só é julgada quando traz `editorial` (`steps.py`:
        # `if page.editorial: _judge_page`). Sem ele, ela dá `return` antes do
        # juiz: é JSON de slots, não prosa Gutenberg.
        ok.append("judge")

    quer_imagem = (p == "LP") or featured_image
    if quer_imagem:
        ok.append("image")
        if gera_imagem:
            ok.append("image_gen")

    # Print e widget só existem em página de SOLUÇÃO.
    if tem_screenshot and p == "SOLUTION":
        ok.append("screenshot")
    if widgets_ligados and p == "SOLUTION" and engajamento != "dado_unico":
        ok.append("widget")

    if publica:
        ok.append("publish")

    ordem = {c["chave"]: i for i, c in enumerate(colunas_do_run(editorial_v2))}
    return sorted(set(ok), key=lambda c: ordem[c])


def _papel(pagina: Dict[str, Any]) -> str:
    """O PAPEL, nunca o `page_type`.

    `page_type` diz "HUB" onde o papel é PRESELL — usá-lo faria a máscara errar
    em toda página de hub. Sem `role` no plano, deriva do sufixo do slug, que é
    a mesma convenção que o motor usa (`derive_role`).
    """
    papel = (pagina.get("role") or "").upper()
    if papel:
        return papel
    slug = pagina.get("slug") or ""
    if re.search(r"-pr\d*$", slug):
        return "PRESELL"
    if re.search(r"-p\d+$", slug):
        return "SOLUTION"
    return "LP"


def _onde_morreu(passos: Dict[str, Any], n: Any,
                 colunas: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    """A coluna em que a página parou — a PRIMEIRA que falhou, na ordem real.

    Ordem do pipeline e não ordem de dicionário: em `research_p4` FAILED, tudo
    que vem depois nem chegou a ser tentado, mas o `write_p4` também aparece
    FAILED (com `research_dependency_failed`). A primeira na ordem das colunas é
    a causa; as outras são consequência.
    """
    if f"blocked_p{n}" not in passos:
        return None
    for c in (colunas or COLUNAS):
        r = passos.get(f"{c['chave']}_p{n}") or {}
        if r.get("status") in ("FAILED", "BLOCKED"):
            return c["chave"]
    return None


def montar(estado: Dict[str, Any], *, flags: Optional[Dict[str, Any]] = None
           ) -> Dict[str, Any]:
    """O payload que a tela consome. Não inventa nada que o motor não gravou."""
    flags = flags or {}
    passos: Dict[str, Any] = _normalizar_passos(estado.get("step_status") or {})
    plano = estado.get("plan") or {}
    paginas_plano = plano.get("pages") or []
    screenshots = estado.get("screenshots") or {}
    publicadas = estado.get("published") or {}
    editorial_v2 = eh_editorial_v2(passos, flags)
    colunas = colunas_do_run(editorial_v2)
    ordem = [c["chave"] for c in colunas]

    linhas: List[Dict[str, Any]] = []
    for pg in paginas_plano:
        n = pg.get("page_number")
        papel = _papel(pg)
        regra = aplicaveis_da_pagina(
            papel,
            engajamento=pg.get("engajamento") or "",
            featured_image=bool(flags.get("featured_image", True)),
            tem_screenshot=bool(flags.get("official_screenshots", False)),
            widgets_ligados=bool(flags.get("widgets_enabled", False)),
            publica=bool(flags.get("publish", True)),
            tem_editorial=bool(pg.get("editorial")),
            editorial_v2=editorial_v2,
        )
        # A máscara explica AUSÊNCIA; ela nunca esconde uma célula que existe.
        # Passo gravado é passo que rodou — e pode ter custado.
        visiveis = set(regra) | {c for c in ordem if f"{c}_p{n}" in passos}
        linhas.append({
            "page_number": n,
            "papel": papel,
            "slug": pg.get("slug") or "",
            "h1": pg.get("h1_title") or "",
            "engajamento": pg.get("engajamento") or "",
            "aplicaveis": [c for c in ordem if c in visiveis],
            # `screenshot OK` não significa "tem print": o motor grava o OK fora
            # do `if shots`. A célula mostra a CONTAGEM, não só o status.
            "prints": len((screenshots.get(str(n)) or screenshots.get(n) or [])),
            "publicada": publicadas.get(str(n)) or publicadas.get(n),
            # `blocked_pN` existe -> a página foi barrada.
            "bloqueada": f"blocked_p{n}" in passos,
            # ONDE ela morreu. Sem isto a tela não consegue distinguir as duas
            # ausências que sobram numa linha bloqueada: as células à ESQUERDA
            # da falha que não se aplicam (vazio legítimo) e as à DIREITA, que
            # se aplicavam e nunca vão rodar — "cancelada", não "pendente".
            #
            # Medido no run #6: a página 4 morreu em `research` e deixou 9
            # posições órfãs; a 3 morreu em `content_gate` e deixou só o
            # `publish`. Pintar as duas caudas de "pendente" mostraria um funil
            # eternamente a meio caminho.
            "bloqueada_em": _onde_morreu(passos, n, colunas),
        })

    celulas: Dict[str, Any] = {}
    faixa: Dict[str, Any] = {}
    for chave, r in passos.items():
        etapa, n = parse_chave(chave)
        alvo = celulas if (n is not None and etapa in CHAVES_DE_COLUNA) else faixa
        alvo[chave] = {
            "status": (r or {}).get("status"),
            "tentativas": (r or {}).get("attempts"),
            "modelo": (r or {}).get("model_used") or "",
            "custo_usd": float((r or {}).get("cost_usd") or 0.0),
            "latencia_ms": (r or {}).get("latency_ms") or 0,
            "issues": [{"code": i.get("code"), "message": i.get("message")}
                       for i in ((r or {}).get("issues") or [])],
        }

    custos = [c["custo_usd"] for c in celulas.values() if c["custo_usd"] > 0]
    return {
        "colunas": colunas,
        "paginas": linhas,
        "celulas": celulas,
        "faixa": faixa,
        "custo_total": round(sum(c["custo_usd"] for c in celulas.values())
                             + sum(c["custo_usd"] for c in faixa.values()), 6),
        # A altura de cada célula é proporcional ao custo dela sobre este teto.
        # É o que faz a mesma grade que responde "onde estou" responder também
        # "para onde foi o dinheiro".
        "custo_maior_celula": max(custos) if custos else 0.0,
        # ⚠️ Quando o total pode estar ABAIXO da fatura do provedor.
        #
        # Retentativa NÃO subestima: `runner.py:125` faz `cost_usd += res.cost_usd`
        # a cada tentativa que RETORNOU, então uma célula RETRIED já traz a soma
        # das três (medido: `write_p5`, 3 tentativas, US$ 0,2189).
        #
        # O ponto cego é o outro caminho: `runner.py:110` — a chamada LEVANTOU
        # antes de existir `res`. O provedor pode ter faturado e o motor nunca
        # viu o custo. A assinatura desse caminho é uma célula FAILED SEM issue
        # registrada: reprovação de validação sempre carrega `issues`; exceção
        # carrega um veredito que não chega aqui.
        #
        # A tela AVISA e não compensa sozinha: inventar um número para o que não
        # foi medido seria trocar um total honestamente incompleto por um total
        # falso.
        "subestimado": any(c.get("status") == "FAILED" and not c["issues"]
                           for c in celulas.values()),
    }


def flags_do_motor(raiz: Any) -> Dict[str, Any]:
    """As três flags que decidem quais colunas existem, lidas do `config.yaml`.

    Não dá para inferi-las do `state.json`: o motor não grava a configuração
    efetiva no estado, e inferir "widgets ligados" da PRESENÇA de `widget_p1`
    seria circular — é exatamente a ausência que precisamos explicar.

    ⚠️ Acoplamento declarado: os padrões aqui têm de ser os mesmos de
    `config/settings.py` (`featured_image`, `official_screenshots` e
    `widgets_enabled` nascem `False`). Chave ausente no YAML significa o padrão
    do pydantic, não "ligado".
    """
    from pathlib import Path

    import yaml

    padroes = {"featured_image": False, "official_screenshots": False,
               "widgets_enabled": False}
    try:
        bruto = yaml.safe_load(
            (Path(raiz) / "config.yaml").read_text(encoding="utf-8")) or {}
        secao = (bruto.get("run") or {})
        return {k: bool(secao.get(k, v)) for k, v in padroes.items()}
    except Exception:  # noqa: BLE001 — sem config, a tela ainda tem de abrir
        return padroes


def impressao(passos: Dict[str, Any]) -> str:
    """Impressão digital dos passos, para 304 no polling e para o worker não
    gravar linha idêntica a cada 3 segundos (seriam ~900 escritas por run)."""
    bruto = json.dumps(passos, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()[:16]
