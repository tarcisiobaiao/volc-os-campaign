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
from urllib.parse import urlparse

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
    # `citavel: false` (pesquisa tipada, 30/09) = a fonte é contraditória ou
    # instável sobre o fato. Mesma régua do `critical_fact_grounding`: o que o
    # portão não aceita, o redator não vê.
    return [f for f in (facts.fatos_verificados or [])
            if str(getattr(f, "fonte_primaria", "")) in resolvidas
            and getattr(f, "citavel", None) is not False]


def _dados_confiaveis(facts: ResearchFacts) -> list[dict]:
    """Dados tipados, citáveis e comprovados pela mesma visita ao vivo.

    Condições e processos são representados como ``dados_validados``. Escondê-los
    do redator enquanto o gate final os aceita cria uma contradição: a prova está
    congelada, mas a página recebe ``FATOS VERIFICADOS: NENHUM``.
    """
    resolvidas = set(facts.fontes_resolvidas or [])
    saida: list[dict] = []
    for dado in facts.dados_validados or []:
        if not isinstance(dado, dict) or not str(dado.get("tipo") or "").strip():
            continue
        fonte = str(dado.get("fonte") or dado.get("source_url") or "").strip()
        fato = str(dado.get("fato") or dado.get("afirmacao") or "").strip()
        if fonte in resolvidas and fato and dado.get("citavel") is not False:
            saida.append({**dado, "fonte": fonte, "fato": fato})
    return saida


def _nao_citaveis(facts: ResearchFacts) -> int:
    """Quantos fatos a pesquisa marcou como NÃO citáveis (e foram retirados)."""
    verificados = sum(1 for f in (facts.fatos_verificados or [])
                      if getattr(f, "citavel", None) is False)
    qualitativos = sum(1 for d in (facts.dados_validados or [])
                       if isinstance(d, dict) and d.get("citavel") is False)
    return verificados + qualitativos


def nome_da_fonte(url: str) -> str:
    """O NOME pelo qual a fonte é citada em prosa: o host, sem `www.`.

    Num destino pago é ele que o redator recebe no lugar da URL. Um host não é
    clicável e não vira `<a href>` em tema nenhum — a URL nua vira, e é por isso
    que ela não pode nem aparecer no que o modelo lê.
    """
    host = (urlparse(str(url or "")).netloc or str(url or "")).lower()
    return host[4:] if host.startswith("www.") else host


# SOLUÇÃO no ramo editorial novo: o link oficial continua permitido onde serve
# à tarefa, mas UMA vez por fonte. "Inclua este link na MESMA frase" produziu a
# p6 da tarifa social (09/10) com o mesmo link da ANEEL nove vezes, um
# "conforme a ANEEL" depois de quase toda frase. O texto antigo segue no V1.
def _citacao_link_unico(fonte: str) -> str:
    return (f"fonte: {fonte}. Vira link no máximo UMA vez por fonte, no ponto em que "
            "o leitor age ou confere; nas outras menções basta o nome da instituição.")


def _bloco_de_fatos(confiaveis: list[Any], destino_pago: bool = False,
                    *, ha_dados_tipados: bool = False, link_unico: bool = False) -> str:
    if not confiaveis:
        if ha_dados_tipados:
            return ""
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
            # ⚠️ AQUI NASCEU O ACHADO MAIS FORTE DO INCIDENTE.
            #
            # A instrução era "inclua este link na MESMA frase: <url>", e o
            # resultado está preservado: sete links `caixa.gov.br` no corpo de
            # `/r/fgts-saque-aniversario/`, quatro deles com âncora que é só um
            # valor. Num destino pago a fonte pertence ao DOSSIÊ e é citada em
            # PROSA; em página editorial ela continua virando link, e é o PAPEL
            # que decide qual das duas instruções o redator recebe.
            (f"     AO USAR ESTE NÚMERO, cite a fonte em PROSA, com âncora "
             f"descritiva (\"segundo o site da {nome_da_fonte(fonte)}\"). "
             f"NÃO escreva a URL e NÃO crie link."
             if destino_pago
             else f"     AO USAR ESTE NÚMERO, {_citacao_link_unico(fonte)}"
             if link_unico
             else f"     AO USAR ESTE NÚMERO, inclua este link na MESMA frase: {fonte}"),
        ]
    return "\n".join(linhas) + "\n"


def _bloco_de_dados(confiaveis: list[dict], destino_pago: bool = False,
                    *, link_unico: bool = False) -> str:
    if not confiaveis:
        return ""
    linhas = [
        "CONDIÇÕES E PROCESSOS VERIFICADOS — use exatamente como escritos;",
        "números presentes nestas frases estão autorizados pela fonte:",
    ]
    for i, dado in enumerate(confiaveis, 1):
        fonte = dado["fonte"]
        linhas.append(f"  {i}. {dado['fato']}")
        if destino_pago:
            linhas.append(
                "     Cite a fonte em prosa, com âncora descritiva "
                f"(\"segundo o site da {nome_da_fonte(fonte)}\"). "
                "NÃO escreva a URL e NÃO crie link."
            )
        elif link_unico:
            linhas.append(f"     Ao usar esta condição ou processo, {_citacao_link_unico(fonte)}")
        else:
            linhas.append(
                "     Ao usar esta condição ou processo, inclua este link na "
                f"MESMA frase: {fonte}"
            )
    return "\n".join(linhas) + "\n"


def base_para_o_redator(facts: ResearchFacts | None, *,
                       destino_pago: bool = False, link_unico: bool = False) -> str:
    """A base factual como o redator deve recebê-la.

    Texto formatado, não JSON: o modelo não precisa navegar cinco campos para
    achar o que pode citar, e o que ele não pode citar simplesmente não está
    escrito em lugar nenhum.

    `destino_pago=True` troca a instrução de citação: nome em prosa em vez de
    URL para linkar, e o dossiê de evidência perde as URLs. O princípio é o
    mesmo do resto do módulo — o que o modelo não pode usar não fica escrito
    em lugar nenhum do que ele lê. Vale para a LP e para a pré-sell.

    `link_unico=True` (página de SOLUÇÃO do ramo novo) mantém a URL, mas pede
    o link uma vez por fonte, onde o leitor age ou confere, em vez de "na
    MESMA frase" de cada número. Sem nenhum dos dois, o texto é o do V1.
    """
    if facts is None:
        return _bloco_de_fatos([], destino_pago)

    confiaveis = _fatos_confiaveis(facts)
    dados_confiaveis = _dados_confiaveis(facts)
    partes = [
        _bloco_de_fatos(confiaveis, destino_pago,
                        ha_dados_tipados=bool(dados_confiaveis), link_unico=link_unico),
        _bloco_de_dados(dados_confiaveis, destino_pago, link_unico=link_unico),
    ]

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
        if isinstance(d, dict) and any(
            str(d.get("fato") or d.get("afirmacao") or "").strip() == c["fato"]
            and str(d.get("fonte") or d.get("source_url") or "").strip() == c["fonte"]
            and str(d.get("tipo") or "") == str(c.get("tipo") or "")
            for c in dados_confiaveis
        ):
            continue
        if isinstance(d, dict) and d.get("citavel") is False:
            continue                     # a pesquisa disse: não citável
        fato = _podar(str((d or {}).get("fato", ""))).strip() if isinstance(d, dict) else ""
        if fato:
            qualitativos.append(fato)
    if qualitativos:
        partes.append("OBSERVAÇÕES QUALITATIVAS (NÃO autorizam cifra):\n"
                      + "\n".join(f"  - {q}" for q in qualitativos))

    retirados = _nao_citaveis(facts)
    if retirados:
        partes.append(f"FATOS RETIRADOS: {retirados} marcado(s) pela pesquisa como não "
                      "citável(is) (fonte contraditória ou instável). Não os use nem os "
                      "reconstrua de memória.")

    resolvidas = list(facts.fontes_resolvidas or [])
    if resolvidas and destino_pago:
        # Só os NOMES. A URL viaja no dossiê de evidência (o recibo do portão),
        # não no que o redator lê: uma URL escrita no prompt reaparece no corpo,
        # e no corpo de um destino pago ela vira o achado
        # `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO`.
        nomes = sorted({nome_da_fonte(u) for u in resolvidas if nome_da_fonte(u)})
        partes.append(
            "FONTES CONFIRMADAS — cite pelo NOME, em prosa (a URL fica no dossiê\n"
            "de evidência, fora da página; nesta página nenhuma vira link):\n"
            + "\n".join(f"  - {n}" for n in nomes))
    elif resolvidas:
        partes.append("FONTES CONFIRMADAS (responderam a uma visita real):\n"
                      + "\n".join(f"  - {u}" for u in resolvidas))

    return "\n\n".join(p for p in partes if p)


def tem_numero_publicavel(facts: ResearchFacts | None) -> bool:
    """Esta página pode usar cifra? Serve para o prompt mudar de tom."""
    if facts is None:
        return False
    return bool(_fatos_confiaveis(facts) or any(
        _CRITICAL_CLAIM_RE.search(d["fato"]) for d in _dados_confiaveis(facts)
    ))
