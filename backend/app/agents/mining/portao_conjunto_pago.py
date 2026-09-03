"""O portão entre o conjunto APROVADO e o nascimento da campanha.

## O buraco que este módulo fecha

`paid_eligibility` decidia bem e não decidia nada, porque
`para_criterios_de_campanha()` não tinha chamador de produção. O caminho real
— `/provar` e, atrás dele, `/subir` — continuava tirando as keywords positivas
do cockpit, que as tira de `production_ads_queue`: a fila BRUTA da mineração.

Ou seja: o motor de elegibilidade existia ao lado do nascimento da campanha, e
não no caminho dele. Um conjunto de 3 selecionadas convivia com um pedido de 8
termos, e nada no sistema notava a diferença.

## A regra, em uma frase

Critério positivo de campanha nasce EXCLUSIVAMENTE de
`para_criterios_de_campanha(conjunto, exigir_aprovacao=True)`. Não há segunda
porta, e as portas que existiam foram fechadas antes de qualquer rede.

## Falha fechada, e antes da rede

Todas as recusas abaixo acontecem ANTES de qualquer chamada ao Google —
inclusive `validate_only`, que é leitura mas ainda é rede e ainda é conta
real:

    CONJUNTO_PAGO_AUSENTE                       não há conjunto no cluster
    CONJUNTO_PAGO_NAO_APROVADO                  ninguém conferiu a impressão
    CONJUNTO_PAGO_HASH_DIVERGENTE               mudou depois de aprovado
    CONJUNTO_PAGO_BLOQUEADO                     bloqueador nomeado em aberto
    CONJUNTO_PAGO_VAZIO                         aprovado, porém sem termo
    N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED   cluster produzido fora do motor

Nenhuma delas inventa valor para seguir adiante. Teto econômico não declarado
e congruência termo→anúncio→página não avaliada continuam bloqueadores
NOMEADOS: o portão diz qual falta, não escolhe um número plausível.

## Por que o n8n falha fechado em vez de ser corrigido

O fluxo n8n versionado ainda carrega o defeito de origem
(`dedupedKws.forEach -> allKeywordsForCampaign`, CPC/volume ausente virando
zero). Corrigi-lo exigiria uma de duas coisas, e as duas são piores que a
recusa:

  · editar à mão um JSON GERADO — `n8n/pautador_kw_mining_webhook.json` sai de
    `backend/scripts/build_n8n_kw_webhook_flow.py`, que copia os nós "ouro"
    VERBATIM de um export externo do n8n que não vive neste repositório. A
    autoridade do JS está fora, e uma edição manual seria sobrescrita na
    próxima geração;
  · reimplementar a elegibilidade em JavaScript — que é manter DOIS algoritmos
    independentes decidindo a mesma coisa, exatamente o que produziu esta
    divergência.

Então a autoridade operacional é declarada, uma só: **o motor Python**. Um
cluster que não carrega o contrato aprovado não vira campanha, e o erro diz o
nome disso em vez de deixar a fila bruta passar por conjunto aprovado.

Isto NÃO desliga a mineração por n8n. O que ele fecha é a EXPORTAÇÃO/CRIAÇÃO
paga a partir de um cluster que não passou pelo contrato.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.agents.mining.paid_eligibility import (
    CampaignKeywordSet,
    conferir_congelamento,
    conjunto_de_dicionario,
    para_criterios_de_campanha,
)

# Os códigos são o vocabulário compartilhado entre o portão, a rota e o teste.
# Mudar um nome aqui quebra o teste de propósito: uma recusa que muda de nome
# em silêncio é uma recusa que ninguém consegue monitorar.
CONJUNTO_AUSENTE = "CONJUNTO_PAGO_AUSENTE"
NAO_APROVADO = "CONJUNTO_PAGO_NAO_APROVADO"
HASH_DIVERGENTE = "CONJUNTO_PAGO_HASH_DIVERGENTE"
BLOQUEADO = "CONJUNTO_PAGO_BLOQUEADO"
VAZIO = "CONJUNTO_PAGO_VAZIO"
N8N_SEM_CONTRATO = "N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED"
# As três recusas que fecham a MUTAÇÃO PÓS-APROVAÇÃO pelo corpo HTTP.
POSITIVA_DO_CORPO = "CRITERIO_POSITIVO_DO_CORPO_RECUSADO"
KEYWORDS_FORA = "KEYWORDS_FORA_APOS_APROVACAO_RECUSADA"
POSITIVAS_DIVERGENTES = "CONJUNTO_POSITIVO_DIVERGENTE"

#: A única autoridade operacional de elegibilidade paga.
AUTORIDADE = "python:app.agents.mining.paid_eligibility"


class PortaoDoConjuntoPago(RuntimeError):
    """Recusa do portão. `codigo` é estável; `detalhe` é para o humano."""

    def __init__(self, codigo: str, detalhe: str, *, bloqueadores: Optional[List[str]] = None):
        super().__init__(f"{codigo}: {detalhe}")
        self.codigo = codigo
        self.detalhe = detalhe
        self.bloqueadores = list(bloqueadores or [])


def _itens_de_fabrica(cluster: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(cluster, dict):
        return []
    saida = cluster.get("factory_output")
    return [x for x in (saida or []) if isinstance(x, dict)]


def parece_produzido_fora_do_motor(cluster: Optional[Dict[str, Any]]) -> bool:
    """O cluster tem fila de campanha mas NÃO tem o contrato.

    É a assinatura de um cluster escrito pelo fluxo n8n: `factory_output` ou
    `production_ads_queue` presentes, `conjunto_pago` ausente em todos os
    funis. Não se detecta pelo campo `engine`, que o produtor externo não é
    obrigado a preencher — detecta-se pela FALTA do contrato, que é o que
    importa.
    """
    if not isinstance(cluster, dict):
        return False
    tem_producao = bool(cluster.get("production_ads_queue")) or bool(_itens_de_fabrica(cluster))
    if not tem_producao:
        return False
    for item in _itens_de_fabrica(cluster):
        if (item.get("keywords_campanha") or {}).get("conjunto_pago"):
            return False
    return True


def conjunto_do_cluster(cluster: Optional[Dict[str, Any]]) -> CampaignKeywordSet:
    """O conjunto pago gravado no cluster, reidratado e CONFERIDO.

    A impressão é recalculada das decisões, nunca lida do registro: é o que
    faz a conferência valer alguma coisa quando o JSON persistido foi editado
    depois da aprovação.
    """
    if parece_produzido_fora_do_motor(cluster):
        raise PortaoDoConjuntoPago(
            N8N_SEM_CONTRATO,
            "este cluster foi produzido fora do motor Python de elegibilidade paga "
            "e não carrega `conjunto_pago`. A autoridade operacional é "
            f"{AUTORIDADE}; minere de novo por ela antes de preparar campanha.",
        )

    bruto = None
    for item in _itens_de_fabrica(cluster):
        bruto = (item.get("keywords_campanha") or {}).get("conjunto_pago")
        if bruto:
            break
    if not bruto:
        raise PortaoDoConjuntoPago(
            CONJUNTO_AUSENTE,
            "nenhum `conjunto_pago` no cluster — não há conjunto aprovado para "
            "virar critério de campanha.",
        )

    try:
        conjunto = conjunto_de_dicionario(bruto)
    except ValueError as exc:
        raise PortaoDoConjuntoPago(CONJUNTO_AUSENTE, str(exc)) from exc

    if not conjunto.approved_set_sha256:
        raise PortaoDoConjuntoPago(
            NAO_APROVADO,
            "o conjunto existe mas ninguém conferiu a impressão dele. Aprovação "
            "é o que separa uma lista minerada de um conjunto de campanha.",
        )
    if conjunto.selected_set_sha256 != conjunto.approved_set_sha256:
        raise PortaoDoConjuntoPago(
            HASH_DIVERGENTE,
            f"impressão recomputada {conjunto.selected_set_sha256[:12]}… difere da "
            f"aprovada {conjunto.approved_set_sha256[:12]}… — o conjunto mudou "
            "depois de aprovado e o selo não vale mais.",
        )
    if conjunto.blockers:
        raise PortaoDoConjuntoPago(
            BLOQUEADO,
            "o conjunto tem bloqueador em aberto: " + ", ".join(conjunto.blockers),
            bloqueadores=conjunto.blockers,
        )
    if not conjunto.selected_keywords:
        raise PortaoDoConjuntoPago(
            VAZIO, "o conjunto aprovado não tem keyword selecionada nenhuma."
        )
    # A guarda de mutação-pós-aprovação do próprio contrato, de novo e de graça.
    conferir_congelamento(conjunto)
    return conjunto


def criterios_do_cluster(
    cluster: Optional[Dict[str, Any]],
) -> Tuple[CampaignKeywordSet, List[Any]]:
    """O conjunto conferido e os `Criterio` que ele autoriza.

    Devolve os dois porque a rota precisa dos critérios para montar e do
    conjunto para responder QUAL impressão autorizou aquele pedido.
    """
    conjunto = conjunto_do_cluster(cluster)
    return conjunto, para_criterios_de_campanha(conjunto, exigir_aprovacao=True)


def keywords_por_grupo(conjunto: CampaignKeywordSet) -> Dict[str, Tuple[str, ...]]:
    """A seleção, agrupada por sub-intenção, na forma que a `Escolha` espera.

    Sem isto o construtor do brief voltaria a montar o grupo INTEIRO a partir
    do cockpit — que é a fila bruta. É a mesma classe de defeito que a própria
    rota já documenta ter corrigido uma vez ("duas keywords escolhidas viraram
    oito no plano que o validate_only aprovou"), e que voltaria por outro
    caminho se a seleção não descesse daqui.
    """
    fora: Dict[str, List[str]] = {}
    for d in conjunto.selected_keywords:
        fora.setdefault(d.subintencao or "", []).append(d.termo)
    return {grupo: tuple(termos) for grupo, termos in fora.items()}


# ── a mutação pós-aprovação pelo corpo HTTP ────────────────────────────────
#
# ⚠️ O PORTÃO ESTAVA ABERTO PELO LADO DE DENTRO.
#
# Ligar o conjunto aprovado à rota não bastava: as duas rotas montavam
#
#     criterios = tuple(criterios_do_conjunto) + tuple(_criterios_do_corpo(...))
#
# e `_criterios_do_corpo` devolve `body.criterios`, que aceita `negativa=False`.
# Reproduzido contra o funil BPC/LOAS:
#
#     conjunto aprovado    'bpc loas quem tem direito'  PHRASE
#     corpo injeta         'bpc loas quem tem direito'  EXACT
#     positive_count            4   (o conjunto aprovado tinha 3)
#     duplicate_count_for_term  2   match types ['PHRASE', 'EXACT']
#
# O corpo produzia uma QUARTA positiva e mudava a semântica de match type
# DEPOIS de `approved_set_sha256` ter sido emitido. A garantia publicada — "as
# positivas nascem exclusivamente do conjunto aprovado" — era falsa.
#
# A segunda variante da mesma falha: `keywords_fora` continuava descendo para a
# `Escolha` e RETIRAVA selecionada aprovada. Medido: 3 aprovadas viravam 2.
#
# Aprovar precisa significar aprovar. Depois da impressão emitida, o corpo só
# pode ACRESCENTAR NEGATIVA — e nem isso em silêncio.


def _identidade_positiva(c: Any) -> Tuple[str, str, str, str]:
    """O que torna duas positivas A MESMA operação de campanha.

    Texto normalizado pela régua do lado Ads (`Criterio.chave`), match type,
    grupo e origem. Os quatro entram porque mudar qualquer um deles muda o que
    vai ao leilão — foi trocando só o match type que o corpo escapou.
    """
    return (c.chave, c.match_type, c.grupo or "", c.origem)


def somente_negativas_do_corpo(criterios_do_corpo: Sequence[Any]) -> List[Any]:
    """Deixa passar negativa declarada; recusa positiva, fechado.

    Negativa continua sendo caminho legítimo do operador, com todas as regras
    de evidência, procedência e overblocking que `Criterio` já impõe — este
    módulo não cria negativa nenhuma e não afrouxa nenhuma daquelas regras.
    O que ele fecha é a porta pela qual uma POSITIVA entrava por fora do
    conjunto que alguém assinou.
    """
    positivas = [c for c in criterios_do_corpo if not c.negativa]
    if positivas:
        amostra = ", ".join(
            f"{c.texto!r} ({c.match_type})" for c in positivas[:5]
        )
        raise PortaoDoConjuntoPago(
            POSITIVA_DO_CORPO,
            f"{len(positivas)} critério(s) POSITIVO(s) vieram no corpo do pedido, e "
            "existe conjunto aprovado. Depois da impressão emitida, positiva só "
            f"nasce do conjunto: {amostra}"
            f"{'…' if len(positivas) > 5 else ''}. Para mudar o conjunto, mude a "
            "seleção e aprove de novo — a impressão nova é o que autoriza. "
            "O corpo continua podendo declarar NEGATIVAS.",
        )
    return list(criterios_do_corpo)


def recusar_keywords_fora(
    keywords_fora: Sequence[str], conjunto: CampaignKeywordSet
) -> List[str]:
    """`keywords_fora` não retira selecionada depois da aprovação.

    Recusa QUALQUER lista não vazia, e não só a que acerta um termo aprovado.
    Ignorar as que não acertam seria silenciar o campo — e o campo estar lá,
    aceito e sem efeito, é como o operador acredita ter excluído algo que
    continua no pedido. Quando ela acerta termos aprovados, o erro os nomeia.
    """
    fora = [str(k) for k in (keywords_fora or []) if str(k).strip()]
    if not fora:
        return []
    from volc_ads.campanha.criterio import chave as _chave

    aprovadas = {_chave(d.termo) for d in conjunto.selected_keywords}
    atingidas = sorted({k for k in fora if _chave(k) in aprovadas})
    detalhe = (
        f"`keywords_fora` traz {len(fora)} termo(s) e existe conjunto aprovado. "
        "A exclusão é decidida na SELEÇÃO, antes da impressão — depois dela, "
        "retirar keyword mudaria o conjunto sem mudar o selo."
    )
    if atingidas:
        detalhe += f" Atinge keyword(s) aprovada(s): {', '.join(repr(k) for k in atingidas)}."
    else:
        detalhe += (
            " Nenhum dos termos está no conjunto aprovado, então o campo não "
            "teria efeito — e aceitar sem efeito é pior que recusar."
        )
    raise PortaoDoConjuntoPago(KEYWORDS_FORA, detalhe)


def conferir_positivas_do_brief(
    brief: Any,
    aprovados: Sequence[Any],
    *,
    grupo_colapsado: bool = False,
) -> None:
    """As positivas do Brief FINAL são exatamente as aprovadas.

    Não subconjunto, não superconjunto, não a mesma lista com outro match
    type: o mesmo MULTICONJUNTO de (texto normalizado, match type, grupo,
    origem). É a pós-condição que torna a garantia verificável no artefato que
    de fato vai ao Google, e não só na entrada que a rota montou.

    `Counter` e não `set` de propósito — sem ele, uma duplicata exata passaria,
    e cardinalidade é justamente o que o defeito alterava.
    """
    from collections import Counter

    positivas = [c for c in getattr(brief, "criterios", []) if not c.negativa]

    # ⚠️ O GRUPO NEM SEMPRE É DIMENSÃO DO BRIEF, E EXIGIR QUE SEJA É EXIGIR
    # PROVA SOBRE O QUE O ARTEFATO NÃO CARREGA.
    #
    # Com `conjunto_unico=True` — a doutrina da casa, "um conjunto, sempre" —
    # `montar_brief` colapsa todas as keywords num ad group só e as positivas
    # saem SEM rótulo de grupo. Medido: aprovada em `INTENCAO`, no brief como
    # `''`. Isso é o colapso documentado fazendo o trabalho dele, não mutação.
    #
    # Então a igualdade é conferida na dimensão que o brief de fato expressa,
    # mas SOMENTE quando o chamador declara explicitamente que escolheu essa
    # topologia. Inferir o colapso apenas porque todos os grupos sumiram faria
    # uma remoção acidental de todos os rótulos parecer legítima.
    grupos_no_brief = {(c.grupo or "") for c in positivas}
    if grupo_colapsado and grupos_no_brief != {""}:
        raise PortaoDoConjuntoPago(
            POSITIVAS_DIVERGENTES,
            "o brief declarou conjunto único, mas preservou grupo em ao menos "
            "uma positiva; a topologia final não corresponde à aprovada.",
        )

    def _ident(c: Any) -> Tuple[str, ...]:
        cheia = _identidade_positiva(c)
        return (cheia[0], cheia[1], cheia[3]) if grupo_colapsado else cheia

    esperado = Counter(_ident(c) for c in aprovados)
    obtido = Counter(_ident(c) for c in positivas)
    if esperado == obtido:
        return
    sobrando = sorted(str(k) for k in (obtido - esperado).elements())
    faltando = sorted(str(k) for k in (esperado - obtido).elements())
    raise PortaoDoConjuntoPago(
        POSITIVAS_DIVERGENTES,
        "as positivas do brief final não são exatamente as aprovadas — "
        f"aprovadas={sum(esperado.values())}, no brief={sum(obtido.values())}. "
        + (f"Sobrando: {sobrando[:5]}. " if sobrando else "")
        + (f"Faltando: {faltando[:5]}." if faltando else ""),
    )


__all__ = [
    "AUTORIDADE",
    "CONJUNTO_AUSENTE", "NAO_APROVADO", "HASH_DIVERGENTE", "BLOQUEADO", "VAZIO",
    "N8N_SEM_CONTRATO",
    "PortaoDoConjuntoPago",
    "parece_produzido_fora_do_motor",
    "conjunto_do_cluster", "criterios_do_cluster", "keywords_por_grupo",
    "POSITIVA_DO_CORPO", "KEYWORDS_FORA", "POSITIVAS_DIVERGENTES",
    "somente_negativas_do_corpo", "recusar_keywords_fora",
    "conferir_positivas_do_brief",
]
