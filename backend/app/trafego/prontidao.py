"""Os quatro portões do lançamento Search, e o que cada um exige de prova.

## Por que este módulo existe

"Pronto" virou uma palavra sem sujeito. Uma campanha pode estar pronta para
NASCER e completamente despreparada para ser ATIVADA — e até 01/09/2026 nada no
sistema dizia a diferença. O risco não é teórico: uma campanha em Smart Bidding
sem sinal de conversão chegando otimiza para nada e gasta o orçamento inteiro
aprendendo o que ninguém mediu.

Os quatro portões separam perguntas que têm respostas diferentes:

    G0  NASCIMENTO    o recibo, a idempotência e a atomicidade seguram a criação?
    G1  MENSURAÇÃO    existe meta de conversão observada e sinal chegando?
    G2  OBSERVAÇÃO    depois de criada, conseguimos reler e diagnosticar?
    G3  ATIVAÇÃO      despausar é seguro, e o lance tem no que aprender?

⚠️ A regra que este módulo impõe: **G0 não implica G1**. O canário pausado
atravessa G0 sozinho — ele não gasta, não entra em leilão e existe para colher o
veredito de política sobre recurso persistido. Mas nenhuma dessas coisas prova
que a medição funciona, e por isso `smart_bidding_eligible` NUNCA sai `True` por
falta de evidência contrária. Ausência de prova é `INDETERMINADO`, não permissão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Os estados possíveis de cada portão. `INDETERMINADO` é o default deliberado:
# quem não mediu não sabe, e não saber não é o mesmo que estar pronto.
PRONTO = "PRONTO"
NAO_PRONTO = "NAO_PRONTO"
INDETERMINADO = "INDETERMINADO"
NAO_APLICAVEL = "NAO_APLICAVEL"

ESTADOS = (PRONTO, NAO_PRONTO, INDETERMINADO, NAO_APLICAVEL)


@dataclass(frozen=True)
class Prontidao:
    """O que se sabe sobre poder nascer, medir, observar e ativar.

    Frozen porque isto vira resposta HTTP e entra no dossiê: um objeto mutável
    deixaria alguém "melhorar" um veredito depois que ele foi apresentado.
    """

    campaign_birth: str = INDETERMINADO
    conversion_goal_status: str = INDETERMINADO
    measurement_readiness: str = INDETERMINADO
    data_manager_status: str = INDETERMINADO
    observability_status: str = INDETERMINADO
    #: ⚠️ Nunca derivado por otimismo. Ver `avaliar`.
    smart_bidding_eligible: bool = False
    activation_blockers: List[str] = field(default_factory=list)
    notas: Dict[str, Any] = field(default_factory=dict)

    def para_json(self) -> Dict[str, Any]:
        return {
            "campaign_birth": self.campaign_birth,
            "conversion_goal_status": self.conversion_goal_status,
            "measurement_readiness": self.measurement_readiness,
            "data_manager_status": self.data_manager_status,
            "observability_status": self.observability_status,
            "smart_bidding_eligible": self.smart_bidding_eligible,
            "activation_blockers": list(self.activation_blockers),
            "notas": dict(self.notas),
        }


def avaliar(
    *,
    recibo_registrado: bool,
    metas_da_conta: Optional[Dict[str, Any]],
    data_manager_operante: bool = False,
    coleta_pos_criacao_provada: bool = False,
    estrategia_lance: str = "MANUAL_CPC",
) -> Prontidao:
    """O veredito, calculado só do que foi de fato observado.

    ⚠️ `metas_da_conta=None` significa "não conseguimos ler", e NÃO "não há
    meta". Os dois viram estados diferentes de propósito: colapsá-los faria uma
    falha de leitura parecer uma conta sem meta, e uma conta sem meta parecer
    uma falha de leitura. As duas confusões levam a decisões opostas.
    """
    bloqueios: List[str] = []
    notas: Dict[str, Any] = {}

    nascimento = PRONTO if recibo_registrado else NAO_PRONTO
    if not recibo_registrado:
        bloqueios.append(
            "não há recibo registrado: uma campanha sem recibo não é "
            "reconciliável depois")

    # ── G1: meta de conversão ────────────────────────────────────────────────
    if metas_da_conta is None:
        meta_status = INDETERMINADO
        notas["conversion_goal"] = (
            "não foi possível ler as metas da conta; ausência de leitura não é "
            "ausência de meta")
        bloqueios.append("metas de conversão não lidas")
    elif metas_da_conta.get("primaria"):
        meta_status = PRONTO
        notas["conversion_goal"] = (
            "a conta declara ação primária; a campanha Search a HERDA. "
            "Sobrescrever por campanha exigiria CampaignConversionGoal, que é "
            "um ato separado e não faz parte do nascimento")
    else:
        meta_status = NAO_PRONTO
        notas["conversion_goal"] = (
            "a conta não tem ação de conversão primária: uma campanha em lance "
            "automático otimizaria para nada")
        bloqueios.append("conta sem ação de conversão primária")

    # ── G1: sinal chegando ───────────────────────────────────────────────────
    if data_manager_operante:
        dm_status = PRONTO
    else:
        dm_status = NAO_PRONTO
        notas["data_manager"] = (
            "a ingestão de conversão offline pela Data Manager API não está "
            "operante: fila, lote, envio e diagnóstico existem como contrato, "
            "não como execução")
        bloqueios.append("Data Manager não operante")

    # Medir exige meta E sinal. Ter uma sem a outra não é meia medição — é
    # nenhuma, porque o lance aprende do que chega, não do que foi declarado.
    if meta_status == PRONTO and dm_status == PRONTO:
        medicao = PRONTO
    elif meta_status == INDETERMINADO:
        medicao = INDETERMINADO
    else:
        medicao = NAO_PRONTO

    # ── G2: observação pós-criação ───────────────────────────────────────────
    observacao = PRONTO if coleta_pos_criacao_provada else INDETERMINADO
    if not coleta_pos_criacao_provada:
        notas["observabilidade"] = (
            "a releitura pós-criação ainda não foi exercida contra uma campanha "
            "real; o coletor contínuo lê apenas campanhas ENABLED")

    # ── G3: ativação e Smart Bidding ─────────────────────────────────────────
    #
    # ⚠️ AQUI MORA A REGRA QUE ESTE MÓDULO EXISTE PARA IMPOR.
    #
    # `smart_bidding_eligible` só é `True` quando medição está PRONTA. Não há
    # ramo que o ligue por ausência de bloqueio conhecido: um sistema que
    # conclui "elegível" porque não achou problema está afirmando algo sobre o
    # mundo a partir do que ele não olhou.
    elegivel = medicao == PRONTO
    if not elegivel and estrategia_lance != "MANUAL_CPC":
        bloqueios.append(
            f"estratégia {estrategia_lance} exige sinal de conversão provado")
    notas["manual_cpc"] = (
        "Manual CPC pode existir no canário pausado sem Data Manager. Isso não "
        "autoriza ativação nem implica prontidão de ROI")

    return Prontidao(
        campaign_birth=nascimento,
        conversion_goal_status=meta_status,
        measurement_readiness=medicao,
        data_manager_status=dm_status,
        observability_status=observacao,
        smart_bidding_eligible=elegivel,
        activation_blockers=bloqueios,
        notas=notas,
    )
