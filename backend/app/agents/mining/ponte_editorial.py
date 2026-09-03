"""A ponte entre as duas decisões — e a garantia de que ela não as funde.

O Validador (`app.validacao`) responde "vale produzir conteúdo sobre este
tema?". Este módulo NÃO recalcula essa resposta: ele a lê do `resumo` que o
Validador já grava, e a põe lado a lado com a resposta paga, que vem de
`paid_eligibility`.

## Por que uma ponte, e não um número só

Uma nota única obrigaria as duas decisões a competir pela mesma escala, e a
consequência prática seria uma delas comprar a outra: tema com boa economia de
leilão subiria como pauta, e pauta boa arrastaria termos para o leilão. São os
dois vazamentos que esta sprint fechou, um de cada lado.

`app.validacao.__init__` já declara a fronteira do lado editorial: `spread` é o
eixo que "ninguém, hoje" mede, porque "CPC é comprável". Enfiar economia de Ads
no índice editorial seria comprar o eixo que o motor recusa a estimar. Por isso
`OpportunityEditorialDecision` carrega apenas o que o Validador mediu, e o
teste `test_F2` falha se qualquer campo de economia paga aparecer aqui.

## O que a ponte NÃO afirma

`apto_para_midia_paga` diz que existe pelo menos um termo elegível e nenhum
bloqueador do conjunto. Não diz que a conta está apta, que o destino passou,
que a mensuração existe, nem que alguém autorizou gasto — `PORTOES_EXTERNOS`
continuam pendentes e viajam junto na visão, escritos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.mining.paid_eligibility import (
    CampaignKeywordSet,
    impressao_do_conjunto,
)

# Campos de economia paga que NÃO podem viajar dentro do objeto editorial.
# A lista é verificada por teste — não é documentação.
CAMPOS_PROIBIDOS_NO_EDITORIAL = (
    "cpc", "spread", "avg_cpc", "bid", "lance", "orcamento", "budget", "roas",
)


@dataclass
class OpportunityEditorialDecision:
    """A decisão editorial, ADAPTADA do resumo do Validador — nunca recalculada."""

    tema: str
    apto: bool = False
    motivo: Optional[str] = None
    indice: Optional[float] = None
    cobertura: Optional[float] = None
    perfil: Optional[str] = None
    sensores_limpos: Optional[bool] = None
    eixos: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    alertas: List[str] = field(default_factory=list)
    fonte: str = "app.validacao"

    @classmethod
    def do_resumo(cls, resumo: Optional[Dict[str, Any]], *, tema: str) -> "OpportunityEditorialDecision":
        """Lê `card.resumo` como ele é gravado hoje por `validacao.orquestrador`.

        Resumo ausente NÃO vira "inapto por mérito": vira inapto com o motivo
        `sem_validacao_editorial`, que é uma lacuna e se lê como lacuna.
        """
        if not isinstance(resumo, dict):
            return cls(tema=tema, apto=False, motivo="sem_validacao_editorial")
        return cls(
            tema=tema,
            apto=bool(resumo.get("apto")),
            motivo=resumo.get("motivo"),
            indice=resumo.get("indice"),
            cobertura=resumo.get("cobertura"),
            perfil=resumo.get("perfil"),
            sensores_limpos=(resumo.get("sensores") or {}).get("limpos"),
            eixos=dict(resumo.get("eixos") or {}),
            alertas=list(resumo.get("alertas") or []),
        )

    def como_dicionario(self) -> Dict[str, Any]:
        return {
            "tema": self.tema,
            "apto": self.apto,
            "motivo": self.motivo,
            "indice": self.indice,
            "cobertura": self.cobertura,
            "perfil": self.perfil,
            "sensores_limpos": self.sensores_limpos,
            "eixos": self.eixos,
            "alertas": self.alertas,
            "fonte": self.fonte,
            "proveniencia": {
                eixo: dados.get("proveniencia") for eixo, dados in self.eixos.items()
            },
        }


def ponte(
    editorial: OpportunityEditorialDecision, conjunto: CampaignKeywordSet
) -> Dict[str, Any]:
    """As duas respostas, lado a lado, sem que uma decida a outra.

    Tema apto com todas as keywords retidas é um estado VÁLIDO — é o caso comum
    de um tema institucional: vale escrever, não vale leiloar.
    """
    return {
        "tema": editorial.tema,
        "vale_produzir_conteudo": editorial.apto,
        "motivo_editorial": editorial.motivo,
        "apto_para_midia_paga": conjunto.ready_for_campaign_plan,
        "conjunto_selecionado": [d.termo for d in conjunto.selected_keywords],
        "conjunto_em_experimento": [
            d.termo for d in conjunto.excluded_keywords if d.decisao == "EXPERIMENT"
        ],
        "conjunto_retido": [
            d.termo for d in conjunto.excluded_keywords if d.decisao in ("HOLD", "REJECT")
        ],
        # Elegível e fora do conjunto por QUANTIDADE, não por mérito. Sem este
        # balde o termo sumiria da visão: ele não é experimento, não foi retido
        # por risco e não está em revisão — só não coube.
        "conjunto_elegivel_nao_selecionado": [
            d.termo for d in conjunto.excluded_keywords if d.decisao == "INCLUDE"
        ],
        "conjunto_em_revisao_humana": [d.termo for d in conjunto.human_review_keywords],
        "selected_set_sha256": impressao_do_conjunto(conjunto),
        "approved_set_sha256": conjunto.approved_set_sha256,
        "bloqueadores_do_conjunto": list(conjunto.blockers),
        "portoes_externos_pendentes": conjunto.portoes_externos_pendentes,
        "editorial": editorial.como_dicionario(),
        # Escrito, não implícito: aprovar keyword não autoriza campanha.
        "aviso": (
            "Aprovar este conjunto de keywords NÃO autoriza campanha. Conta, "
            "destino pago, mensuração e aprovação de gasto continuam sendo "
            "portões independentes."
        ),
    }


__all__ = [
    "CAMPOS_PROIBIDOS_NO_EDITORIAL",
    "OpportunityEditorialDecision",
    "ponte",
]
