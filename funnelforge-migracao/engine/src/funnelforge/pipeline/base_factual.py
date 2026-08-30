"""O que o redator vê da pesquisa — podado e municiado.

## O defeito, medido em dois runs reais

Run #3 (17/08, 18:08): a pesquisa devolvia URLs inventadas e o gate matava a
página. Consertado colhendo as citações do `groundingMetadata`.

Run #4 (17/08, 18:27), com aquele conserto: a pesquisa passou — 7 fatos tipados,
5 fontes resolvidas — e o REDATOR reprovou, três vezes, por
`ungrounded_critical_claim`:

    "…continua rendendo, chegando a 100% do CDI nas Caixinhas do Nubank…"
    "…o teto do CNPS é de 1.85% ao mês em 2026…"

Nenhum dos dois números estava entre os fatos verificados. E o modelo não estava
desobedecendo: ele recebia `facts.model_dump_json()` INTEIRO — `resumo`,
`dados_validados` e `passo_a_passo` juntos —, textos cheios de cifras que a
pesquisa escreveu em prosa e ninguém verificou. O prompt mandava usar só
`fatos_verificados`; a entrada oferecia o contrário.

## O conserto: simetria com o gate

Este módulo poda da parte QUALITATIVA exatamente aquilo que
`critical_fact_grounding` reprovaria — usando a MESMA expressão regular do
validador, importada dele, não uma cópia. O redator deixa de enxergar o número
que o gate mataria. A regra ("cifra só com fonte verificada") para de depender
de o modelo obedecer e passa a valer por construção.

E o outro lado: os fatos que SOBREVIVERAM à verificação chegam formatados para
uso — valor, unidade, dispositivo, vigência e o link a citar —, não como JSON
que o modelo precisa interpretar no meio de outros cinco campos.

## O que este módulo NÃO faz

Não julga se o fato é bom, não reescreve prosa e não inventa nada. Ele só decide
o que o redator PODE ver.
"""
from __future__ import annotations

from typing import Any

from funnelforge.domain.models import ResearchFacts
from funnelforge.pipeline.validators.checks import _CRITICAL_CLAIM_RE

# O que aparece no lugar do número podado. É deliberadamente EXPLÍCITO: dizer
# "havia um número aqui e ele não foi verificado" ensina o modelo a não procurar
# a cifra noutro lugar, enquanto apagar em silêncio deixaria uma frase capenga
# que ele tentaria completar de memória — que é a alucinação de novo.
MARCADOR = "[número não verificado — não use]"


def _podar(texto: str) -> str:
    """Neutraliza no texto o que o gate final reprovaria."""
    if not texto:
        return texto
    return _CRITICAL_CLAIM_RE.sub(MARCADOR, texto)


def _fatos_confiaveis(facts: ResearchFacts) -> list[Any]:
    """Só os fatos tipados cuja fonte primária RESOLVEU na visita ao vivo.

    É a mesma definição que `critical_fact_grounding` usa para aceitar uma
    afirmação. Passar ao redator um fato cuja fonte não resolveu seria oferecer
    munição que o gate vai recusar depois.
    """
    resolvidas = set(facts.fontes_resolvidas or [])
    return [f for f in (facts.fatos_verificados or [])
            if str(getattr(f, "fonte_primaria", "")) in resolvidas]


def _bloco_de_fatos(confiaveis: list[Any]) -> str:
    if not confiaveis:
        return (
            "FATOS VERIFICADOS: NENHUM.\n"
            "  Nenhuma fonte numérica resolveu na verificação ao vivo desta página.\n"
            "  Escreva SEM cifra, SEM percentual, SEM prazo e SEM citar norma.\n"
            "  Fato qualitativo de autoridade é permitido e suficiente — um texto\n"
            "  útil sem número é melhor que um número que você não pode provar.\n"
        )
    linhas = [f"FATOS VERIFICADOS — os ÚNICOS números que você pode usar ({len(confiaveis)}):"]
    for i, f in enumerate(confiaveis, 1):
        valor = str(getattr(f, "valor", "")).strip()
        unidade = str(getattr(f, "unidade", "")).strip()
        disp = str(getattr(f, "dispositivo", "")).strip()
        fonte = str(getattr(f, "fonte_primaria", "")).strip()
        desde = getattr(f, "vigente_desde", "")
        conferido = getattr(f, "verificado_em", "")
        linhas += [
            f"  {i}. {valor} {unidade}".rstrip(),
            f"     onde está escrito: {disp}",
            f"     vigente desde {desde} · conferido em {conferido}",
            f"     AO USAR ESTE NÚMERO, inclua este link na MESMA frase: {fonte}",
        ]
    return "\n".join(linhas) + "\n"


def base_para_o_redator(facts: ResearchFacts | None) -> str:
    """A base factual como o redator deve recebê-la.

    Texto formatado, não JSON: o modelo não precisa navegar cinco campos para
    achar o que pode citar, e o que ele não pode citar simplesmente não está
    escrito em lugar nenhum.
    """
    if facts is None:
        return _bloco_de_fatos([])

    confiaveis = _fatos_confiaveis(facts)
    partes = [_bloco_de_fatos(confiaveis)]

    resumo = _podar(facts.resumo or "")
    if resumo.strip():
        partes.append(
            "CONTEXTO QUALITATIVO (sem cifra: os números que havia aqui não\n"
            "passaram na verificação e foram removidos):\n  " + resumo.strip())

    passos = [_podar(str(p)) for p in (facts.passo_a_passo or []) if str(p).strip()]
    if passos:
        partes.append("PASSO A PASSO (também sem cifra não verificada):\n"
                      + "\n".join(f"  - {p}" for p in passos))

    qualitativos = []
    for d in (facts.dados_validados or []):
        fato = _podar(str((d or {}).get("fato", ""))).strip() if isinstance(d, dict) else ""
        if fato:
            qualitativos.append(fato)
    if qualitativos:
        partes.append("OBSERVAÇÕES QUALITATIVAS (NÃO autorizam cifra):\n"
                      + "\n".join(f"  - {q}" for q in qualitativos))

    resolvidas = list(facts.fontes_resolvidas or [])
    if resolvidas:
        partes.append("FONTES CONFIRMADAS (responderam a uma visita real):\n"
                      + "\n".join(f"  - {u}" for u in resolvidas))

    return "\n\n".join(partes)


def tem_numero_publicavel(facts: ResearchFacts | None) -> bool:
    """Esta página pode usar cifra? Serve para o prompt mudar de tom."""
    return bool(facts is not None and _fatos_confiaveis(facts))
