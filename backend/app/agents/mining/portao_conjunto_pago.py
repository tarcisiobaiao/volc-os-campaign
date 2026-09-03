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

from typing import Any, Dict, List, Optional, Tuple

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


__all__ = [
    "AUTORIDADE",
    "CONJUNTO_AUSENTE", "NAO_APROVADO", "HASH_DIVERGENTE", "BLOQUEADO", "VAZIO",
    "N8N_SEM_CONTRATO",
    "PortaoDoConjuntoPago",
    "parece_produzido_fora_do_motor",
    "conjunto_do_cluster", "criterios_do_cluster", "keywords_por_grupo",
]
