"""Camada 2 — a tese de oportunidade.

O Validador (Camada 1) MEDE: oito eixos com proveniência. `paid_eligibility`
(Camada 3) decide keyword paga. Entre as duas faltava a pergunta que o operador
de fato faz ao arrastar o card:

    vale aprofundar este tema em um funil, e por quê?

Este módulo responde isso — e o faz **sem recalcular nada**. Ele lê o `resumo`
que `validacao.orquestrador._resumir` já gravou, exatamente como
`ponte_editorial.OpportunityEditorialDecision.do_resumo` faz, e monta uma tese
sobre ele.

## Por que não é um score

Uma nota composta obrigaria construtos diferentes a competir na mesma escala, e
o registro de refutações (`motor_pautas/DECISOES.md`) já mostra o preço disso:
a regressão ajustada em `lucro` aprendeu `spend` (AUC 0,971), não qualidade de
tema. A tese aqui é um **vocabulário fechado de decisão** mais três conjuntos
disjuntos — fatos, hipóteses e desconhecidos — porque o que o operador precisa
não é ordenar melhor, é saber **de que tipo** é cada coisa que ele está lendo.

O índice de 10 eixos continua existindo e continua sendo do `espaco.py`. Esta
camada não o recalcula, não o corrige e não o substitui: ela o cita.

## O que NÃO entra aqui, por construção

- Nenhum campo de economia paga. `CAMPOS_PROIBIDOS_NO_EDITORIAL` é verificado
  por teste, não por documentação.
- Nenhuma nota vinda do LLM. O LLM conta; a aritmética é do Python, e ela já
  aconteceu na Camada 1.
- Nenhum prior — nem do benchmark Webgo, nem da tabela de tensões — pode mover
  a decisão. Priors aparecem em `hipoteses`, com procedência, e só.
- Nenhum efeito externo: sem HTTP, sem Supabase, sem Google Ads, sem publicação.

## A dívida do prior de tensão

`resumo["tensao"]["intensidade_prior"]` chega aqui e é **descartado**. Ele veio
do desfecho `lucro`, que `spend` prevê com AUC 0,971 — a mesma régua contaminada
que aposentou a regressão. A tensão em si (o rótulo) é observação do LLM sobre
um vocabulário fechado e essa entra; o número que a acompanha, não.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.agents.mining.paid_eligibility import (
    POS_LANCAMENTO,
    PRE_LANCAMENTO,
    VazamentoDeDesfecho,
)
from app.agents.mining.ponte_editorial import CAMPOS_PROIBIDOS_NO_EDITORIAL

VERSAO_DO_CONTRATO = "oportunidade/1"

# ── vocabulário de decisão ───────────────────────────────────────────────────
#
# Cinco estados, e cada um significa uma AÇÃO diferente do operador. Não são
# faixas de uma escala: `INADEQUADO` e `INSUFICIENTE` empatam em prioridade e
# divergem completamente em o que fazer a seguir — um está medido e não serve,
# o outro não está medido o bastante para dizer.

APROFUNDAR = "aprofundar"        # medido, ramifica, sustenta funil
EXPERIMENTAR = "experimentar"    # promissor com buraco barato de fechar
INSUFICIENTE = "insuficiente"    # medido, mas a evidência não sustenta a aposta
INADEQUADO = "inadequado"        # medido e NÃO serve ao formato de funil
RETIDO = "retido"                # cobertura abaixo do mínimo — não priorizar
SEM_VALIDACAO = "sem_validacao"  # card antigo/nunca medido — lacuna, não mérito

DECISOES = (APROFUNDAR, EXPERIMENTAR, INSUFICIENTE, INADEQUADO, RETIDO,
            SEM_VALIDACAO)

# `ordenar()` do espaço usa 0,5 e a razão é a mesma aqui: abaixo disso a média
# geométrica fala de meia dúzia de eixos e chama isso de retrato do tema.
COBERTURA_MINIMA_PARA_COMPARAR = 0.5

# ── os observáveis que esta camada aceita ────────────────────────────────────
#
# Lista fechada, e ela é uma DECISÃO. Nada visual entra: o benchmark Webgo
# provou que elemento recorrente de página é template — 14 de 18 domínios
# servem vencedora, perdedora e controle com o mesmo gerador, e as medianas
# estruturais empatam nos três grupos (cta 6/6/6, form 1/1/1).
OBSERVAVEIS_ACEITOS: Tuple[str, ...] = (
    "ramos_de_acao",
    "condicoes_pessoais",
    "decisao_apos_resposta",
    "oficial_fecha_sozinho",
    "engajamento",
    "ignorancia",
    "opacidade",
    "volume",
    "reposicao",
    "vacuo",
    "densidade",
    "formato_consumo",
    "share_dado_unico",
    "tensao",
)

# ── priors do benchmark ──────────────────────────────────────────────────────
#
# `pode_decidir` é False em TODOS, e o teste garante. Um prior aqui existe para
# o operador saber o que já se observou noutro lugar — nunca para mover a
# decisão deste tema. A regra vem do contrato da sprint anterior: nenhum prior,
# de qualquer confiança, bloqueia ou autoriza.
PRIORS_WEBGO: Tuple[Dict[str, Any], ...] = (
    {
        "id": "webgo/ramificacao-cosmetica",
        "afirmacao": (
            "Rótulo de escolha não é ramo. No corpus, a mediana é 3 rótulos por "
            "página contra 1 destino real, e 66 de 82 páginas apontam 3+ rótulos "
            "para um único URL."
        ),
        "confianca": "media",
        "tem_controle": "parcial",
        "pode_decidir": False,
        "uso": "contraprova para `ramos_de_acao`: ramo declarado precisa levar a ação diferente",
    },
    {
        "id": "webgo/estrutura-nao-discrimina",
        "afirmacao": (
            "Estrutura de página não separa vencedora de controle: medianas de "
            "palavras 894/927/902, CTAs 6/6/6, formulários 1/1/1, e 14 de 18 "
            "domínios servem mais de um grupo de desempenho."
        ),
        "confianca": "alta",
        "tem_controle": "sim",
        "pode_decidir": False,
        "uso": "afirma uma AUSÊNCIA — nenhum observável visual merece peso",
    },
    {
        "id": "webgo/densidade-de-anuncio",
        "afirmacao": (
            "Densidade de anúncio acima da dobra é o único gradiente monotônico "
            "com controle (14,8% vencedoras · 38,9% controles · 68,4% perdedoras), "
            "mas é propriedade de monetização paga, medida no DOM do estado ATUAL "
            "contra desfecho de 90-180 dias, com n efetivo de ~18 domínios."
        ),
        "confianca": "baixa",
        "tem_controle": "sim",
        "pode_decidir": False,
        "uso": "hipótese para o lado pago; fora da decisão editorial (contraprova #16)",
    },
    {
        "id": "webgo/passo-2-inobservavel",
        "afirmacao": (
            "O segundo passo do funil é inobservável no corpus: nenhum destino "
            "dos blocos de escolha foi capturado."
        ),
        "confianca": "alta",
        "tem_controle": "nao",
        "pode_decidir": False,
        "uso": "proíbe citar Webgo para sustentar 'sustenta sequência de páginas'",
    },
)


# ── a tese ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TeseDeOportunidade:
    """A resposta a 'vale aprofundar?', com a procedência de cada parte.

    `fatos`, `hipoteses` e `desconhecidos` são DISJUNTOS por construção. É a
    propriedade que a interface precisa para não pintar hipótese de fato.
    """

    tema: str
    decisao: str
    porque: str
    versao_do_contrato: str = VERSAO_DO_CONTRATO

    formato_de_funil: Optional[str] = None
    observaveis_do_formato: Tuple[str, ...] = ()

    fatos: Tuple[str, ...] = ()
    hipoteses: Tuple[str, ...] = ()
    desconhecidos: Tuple[str, ...] = ()
    contradicoes: Tuple[str, ...] = ()

    proximo_experimento: Optional[str] = None

    indice_citado: Optional[float] = None
    cobertura: Optional[float] = None
    perfil_citado: Optional[str] = None
    comparavel: bool = False
    motivo_incomparavel: Optional[str] = None

    def como_dicionario(self) -> Dict[str, Any]:
        return {
            "tema": self.tema,
            "decisao": self.decisao,
            "porque": self.porque,
            "versao_do_contrato": self.versao_do_contrato,
            "formato_de_funil": self.formato_de_funil,
            "observaveis_do_formato": list(self.observaveis_do_formato),
            "fatos": list(self.fatos),
            "hipoteses": list(self.hipoteses),
            "desconhecidos": list(self.desconhecidos),
            "contradicoes": list(self.contradicoes),
            "proximo_experimento": self.proximo_experimento,
            "indice_citado": self.indice_citado,
            "cobertura": self.cobertura,
            "perfil_citado": self.perfil_citado,
            "comparavel": self.comparavel,
            "motivo_incomparavel": self.motivo_incomparavel,
        }


# ── formato de funil ─────────────────────────────────────────────────────────
#
# O roteador é aritmético sobre contagens que o LLM fez na Camada 1, e cada
# saída CITA os números que a produziram (contraprova #23). `oficial_fecha_
# sozinho` é o VETO — sem ele o roteador recomendaria construir a ferramenta que
# o balcão oficial já entrega em um clique.

FERRAMENTA = "ferramenta_de_elegibilidade"
COMPARADOR = "comparador_de_caminhos"
GUIA = "guia_sequencial"
RESPOSTA_UNICA = "resposta_unica"


def _numeros_das_perguntas(ficha: Dict[str, Any]) -> List[Dict[str, Any]]:
    """As perguntas com as contagens saneadas. Pergunta malformada é DESCARTADA,
    não zerada — zerar inventaria uma observação que ninguém fez."""
    saidas: List[Dict[str, Any]] = []
    for q in (ficha.get("perguntas") or []):
        if not isinstance(q, dict):
            continue
        ramos, cond = q.get("ramos"), q.get("condicoes")
        if not isinstance(ramos, int) or not isinstance(cond, int):
            continue
        saidas.append({
            "ramos": ramos,
            "condicoes": cond,
            "decide_depois": bool(q.get("decide_depois")),
            "fecha_sozinho": bool(q.get("oficial_fecha_sozinho")),
            "engajamento": q.get("engajamento"),
        })
    return saidas


def _rotear_formato(perguntas: List[Dict[str, Any]]) -> Tuple[Optional[str], Tuple[str, ...]]:
    if not perguntas:
        return None, ()

    n = len(perguntas)
    fecham = sum(1 for q in perguntas if q["fecha_sozinho"])
    max_cond = max(q["condicoes"] for q in perguntas)
    max_ramos = max(q["ramos"] for q in perguntas)
    decidem = sum(1 for q in perguntas if q["decide_depois"])

    # ⚠️ O VETO. Se o canal oficial fecha TODAS as perguntas, não há página a
    # construir: o widget não acrescenta nada ao balcão.
    if fecham == n:
        return None, (
            f"oficial_fecha_sozinho em {fecham} de {n} perguntas",
            f"max ramos_de_acao {max_ramos}",
        )

    citacoes = (
        f"max condicoes_pessoais {max_cond}",
        f"max ramos_de_acao {max_ramos}",
        f"decisao_apos_resposta em {decidem} de {n} perguntas",
    )

    if max_cond >= 2 and max_ramos >= 2:
        return FERRAMENTA, citacoes
    if max_ramos >= 2 and decidem >= 1:
        return COMPARADOR, citacoes
    if n >= 3 and max_cond >= 1:
        return GUIA, citacoes
    return RESPOSTA_UNICA, citacoes


# ── vazamento de desfecho ────────────────────────────────────────────────────


def _guardar_vazamento(evidencias: Sequence[Dict[str, Any]],
                       campanha_ref: Optional[str]) -> None:
    """Evidência pós-desfecho da MESMA campanha não entra numa decisão
    pré-lançamento. De outra campanha entra como prior, marcada.

    A guarda depende de `campanha_ref` ser preenchido — é contrato de honestidade
    do chamador, não prova, e o mesmo limite já está declarado no lado pago.
    """
    for ev in evidencias or ():
        if not isinstance(ev, dict):
            continue
        if str(ev.get("momento")) != POS_LANCAMENTO:
            continue
        if campanha_ref and ev.get("campanha_ref") == campanha_ref:
            raise VazamentoDeDesfecho(
                "evidência pós-lançamento da própria campanha "
                f"{campanha_ref!r} oferecida a uma decisão {PRE_LANCAMENTO}"
            )


# ── a montagem ───────────────────────────────────────────────────────────────


_ROTULO_EIXO = {
    "volume": "demanda medida",
    "reposicao": "renovação do público",
    "vacuo": "espaço editorial",
    "densidade": "setores que falariam com essa audiência",
    "formato_consumo": "como o tema é consumido",
    "ignorancia": "o que o leitor não sabe ao chegar",
    "engajamento": "a resposta esgota ou sustenta",
    "opacidade": "quão clara é a regra oficial",
}


def tese_do_resumo(
    resumo: Optional[Dict[str, Any]],
    *,
    tema: str,
    evidencias_externas: Optional[Sequence[Dict[str, Any]]] = None,
    campanha_ref: Optional[str] = None,
    aplicar_priors: bool = False,
) -> TeseDeOportunidade:
    """Monta a tese a partir do resumo JÁ GRAVADO. Nunca recalcula a medição.

    `resumo` ausente ou malformado NÃO vira "inapto por mérito": vira
    `SEM_VALIDACAO`, que se lê como lacuna — a mesma regra que
    `OpportunityEditorialDecision.do_resumo` já aplica do lado pago.
    """
    _guardar_vazamento(evidencias_externas or (), campanha_ref)

    if not isinstance(resumo, dict) or not resumo.get("eixos"):
        return TeseDeOportunidade(
            tema=tema,
            decisao=SEM_VALIDACAO,
            porque="Este card não passou pela coluna de validação, ou passou numa "
                   "versão anterior do motor. Não é um veredito sobre o tema.",
            comparavel=False,
            motivo_incomparavel="sem medição registrada",
        )

    eixos: Dict[str, Any] = dict(resumo.get("eixos") or {})
    ficha: Dict[str, Any] = dict(resumo.get("ficha") or {})
    perguntas = _numeros_das_perguntas(ficha)

    fatos: List[str] = []
    desconhecidos: List[str] = []
    hipoteses: List[str] = []
    contradicoes: List[str] = []

    # ── eixos: medido vira fato, julgado vira fato marcado, ausente vira buraco
    for nome in sorted(eixos):
        if nome not in OBSERVAVEIS_ACEITOS:
            continue
        dado = eixos.get(nome) or {}
        proveniencia = dado.get("proveniencia")
        nivel = dado.get("nivel")
        rotulo = _ROTULO_EIXO.get(nome, nome)
        if proveniencia == "ausente" or nivel is None:
            motivo = dado.get("motivo_ausencia") or "não medido"
            desconhecidos.append(f"{nome} ({rotulo}): não medido — {motivo}")
        elif proveniencia == "julgado":
            fatos.append(f"{nome} ({rotulo}): {nivel} — contado pelo modelo, derivado em Python")
        else:
            fatos.append(f"{nome} ({rotulo}): {nivel} — medido por sensor")

    # ── as contagens da ficha: fatos, com número
    if perguntas:
        n = len(perguntas)
        max_cond = max(q["condicoes"] for q in perguntas)
        max_ramos = max(q["ramos"] for q in perguntas)
        fecham = sum(1 for q in perguntas if q["fecha_sozinho"])
        fatos.append(f"perguntas lidas: {n}")
        fatos.append(f"max condicoes_pessoais {max_cond}, max ramos_de_acao {max_ramos}")
        fatos.append(f"oficial_fecha_sozinho em {fecham} de {n} perguntas")
    else:
        desconhecidos.append("perguntas do PAA: nenhuma ficha legível foi gravada")

    # ── a tensão: o RÓTULO entra; o número que o acompanha, não
    tensao = resumo.get("tensao") or {}
    if isinstance(tensao, dict) and tensao.get("tensao"):
        share = tensao.get("share_com_tensao")
        fatos.append(
            f"tensao dominante: {tensao['tensao']}"
            + (f" em {share} das perguntas" if share is not None else "")
        )

    # ── estabilidade entre passadas
    comparacao = ficha.get("comparacao") or {}
    if comparacao.get("estavel") is False:
        hipoteses.append(
            "as passadas do modelo divergiram entre si — o nível deste tema não "
            f"é estável (shares {comparacao.get('shares')})"
        )

    # ── priors: entram como hipótese, com procedência, e nunca decidem
    if aplicar_priors:
        for p in PRIORS_WEBGO:
            hipoteses.append(
                f"[prior {p['id']} · confiança {p['confianca']} · "
                f"controle {p['tem_controle']}] {p['afirmacao']}"
            )

    for ev in (evidencias_externas or ()):
        if isinstance(ev, dict) and ev.get("afirmacao"):
            hipoteses.append(
                f"[evidência externa · {ev.get('momento', 'desconhecido')}] {ev['afirmacao']}"
            )

    # ── contradições: reportadas, nunca resolvidas em silêncio
    portoes = list(resumo.get("portoes_disparados") or [])
    if resumo.get("apto") and portoes:
        contradicoes.append(
            f"o resumo diz apto=true mas há portão disparado: {', '.join(portoes)}"
        )
    if resumo.get("indice") is not None and portoes and resumo.get("indice") > 0:
        contradicoes.append(
            f"portão disparado ({', '.join(portoes)}) com índice {resumo['indice']} acima de zero"
        )

    formato, citacoes = _rotear_formato(perguntas)

    # ── a decisão ────────────────────────────────────────────────────────────
    cobertura = resumo.get("cobertura")
    decisao, porque = _decidir(
        resumo=resumo, perguntas=perguntas, formato=formato,
        cobertura=cobertura, portoes=portoes, desconhecidos=desconhecidos,
    )

    comparavel = decisao not in (RETIDO, SEM_VALIDACAO)
    motivo_incomparavel = None
    if not comparavel:
        motivo_incomparavel = (
            f"cobertura {cobertura} abaixo do mínimo {COBERTURA_MINIMA_PARA_COMPARAR}"
            if decisao == RETIDO else "sem medição registrada"
        )

    experimento = _experimento(desconhecidos, decisao)

    # Disjunção: um mesmo enunciado nunca aparece em dois conjuntos.
    fatos_t = tuple(dict.fromkeys(fatos))
    hip_t = tuple(x for x in dict.fromkeys(hipoteses) if x not in fatos_t)
    desc_t = tuple(x for x in dict.fromkeys(desconhecidos)
                   if x not in fatos_t and x not in hip_t)

    return TeseDeOportunidade(
        tema=tema,
        decisao=decisao,
        porque=porque,
        formato_de_funil=formato,
        observaveis_do_formato=citacoes,
        fatos=fatos_t,
        hipoteses=hip_t,
        desconhecidos=desc_t,
        contradicoes=tuple(dict.fromkeys(contradicoes)),
        proximo_experimento=experimento,
        indice_citado=resumo.get("indice"),
        cobertura=cobertura,
        perfil_citado=resumo.get("perfil"),
        comparavel=comparavel,
        motivo_incomparavel=motivo_incomparavel,
    )


def _decidir(*, resumo: Dict[str, Any], perguntas: List[Dict[str, Any]],
             formato: Optional[str], cobertura: Optional[float],
             portoes: List[str], desconhecidos: List[str]) -> Tuple[str, str]:
    """A regra, em ordem. Cada ramo diz o que o operador faz a seguir."""

    # 1 · cobertura primeiro: sem base não se prioriza, nem para cima nem para baixo
    if cobertura is not None and cobertura < COBERTURA_MINIMA_PARA_COMPARAR:
        return RETIDO, (
            f"Cobertura de {cobertura:.0%} — abaixo de "
            f"{COBERTURA_MINIMA_PARA_COMPARAR:.0%}, a média fala de meia dúzia de "
            "eixos e chama isso de retrato do tema. Medir antes de comparar."
        )

    # 2 · o veto do formato: o balcão oficial já resolve
    if formato is None and perguntas:
        return INADEQUADO, (
            "O canal oficial fecha todas as perguntas sozinho. Uma página aqui "
            "repete o balcão sem acrescentar nada — não há funil a construir."
        )

    # 3 · portão do motor de medição, citado e não recalculado
    if portoes:
        return INADEQUADO, (
            f"Portão disparado na medição: {', '.join(portoes)}. "
            "O motor de eixos já decidiu que este tema não sustenta funil."
        )

    if not perguntas:
        return INSUFICIENTE, (
            "Nenhuma ficha legível foi gravada. Há eixos medidos, mas nada sobre "
            "a forma das perguntas — e é ela que diz se existe funil."
        )

    max_cond = max(q["condicoes"] for q in perguntas)
    max_ramos = max(q["ramos"] for q in perguntas)

    # 4 · ramificação real é o que separa funil de artigo
    if formato in (FERRAMENTA, COMPARADOR):
        base = (
            f"Ramifica de verdade: até {max_ramos} caminhos que levam a ações "
            f"diferentes e até {max_cond} condições pessoais que mudam a resposta. "
            "É isso que uma página só não resolve."
        )
        if desconhecidos:
            return EXPERIMENTAR, base + (
                f" Faltam {len(desconhecidos)} observáveis — feche o barato primeiro."
            )
        return APROFUNDAR, base

    if formato == GUIA:
        return EXPERIMENTAR, (
            f"Sequência plausível ({len(perguntas)} perguntas, até {max_cond} "
            "condições), mas sem ramificação que exija ferramenta. Vale um teste "
            "barato antes de montar funil."
        )

    return INSUFICIENTE, (
        f"Até {max_ramos} caminho(s) e {max_cond} condição(ões): a resposta cabe "
        "numa página. Não é um tema ruim — é um tema que não pede funil."
    )


def _experimento(desconhecidos: List[str], decisao: str) -> Optional[str]:
    """O menor experimento que reduz a incerteza. Só existe se houver buraco."""
    if not desconhecidos or decisao == SEM_VALIDACAO:
        return None
    primeiro = desconhecidos[0].split(" (")[0]
    return (
        f"Medir {primeiro}: é o observável ausente mais barato de fechar e o que "
        "mais muda a leitura deste card."
    )


# ── comparação ───────────────────────────────────────────────────────────────


def comparar(teses: Sequence[TeseDeOportunidade]
             ) -> Tuple[List[TeseDeOportunidade], List[TeseDeOportunidade]]:
    """Separa o que pode ser comparado do que não pode, e ordena só o primeiro.

    Devolver DUAS listas em vez de uma ordenada é deliberado: o card sem
    cobertura não some da tela — ele aparece dizendo por que não entra no
    ranking. Sumir seria a ordenação silenciosa que a contraprova #20 proíbe.
    """
    ordem = {APROFUNDAR: 0, EXPERIMENTAR: 1, INSUFICIENTE: 2, INADEQUADO: 3}
    aptos = [t for t in teses if t.comparavel]
    fora = [t for t in teses if not t.comparavel]
    aptos.sort(key=lambda t: (
        ordem.get(t.decisao, 9),
        -(t.indice_citado if t.indice_citado is not None else -1.0),
        -(t.cobertura if t.cobertura is not None else 0.0),
        t.tema,
    ))
    return aptos, fora


__all__ = [
    "VERSAO_DO_CONTRATO",
    "APROFUNDAR", "EXPERIMENTAR", "INSUFICIENTE", "INADEQUADO", "RETIDO",
    "SEM_VALIDACAO", "DECISOES",
    "COBERTURA_MINIMA_PARA_COMPARAR",
    "OBSERVAVEIS_ACEITOS", "PRIORS_WEBGO",
    "FERRAMENTA", "COMPARADOR", "GUIA", "RESPOSTA_UNICA",
    "TeseDeOportunidade", "tese_do_resumo", "comparar",
    "CAMPOS_PROIBIDOS_NO_EDITORIAL",
]
