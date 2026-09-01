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
#: Leu alguma coisa verdadeira, e não o bastante para afirmar prontidão. É o
#: estado que impede "consultei um recurso próximo" de virar "está pronto".
PARCIAL = "PARCIAL"
NAO_PRONTO = "NAO_PRONTO"
INDETERMINADO = "INDETERMINADO"
NAO_APLICAVEL = "NAO_APLICAVEL"

ESTADOS = (PRONTO, PARCIAL, NAO_PRONTO, INDETERMINADO, NAO_APLICAVEL)


@dataclass(frozen=True)
class Prontidao:
    """O que se sabe sobre poder nascer, medir, observar e ativar.

    Frozen porque isto vira resposta HTTP e entra no dossiê: um objeto mutável
    deixaria alguém "melhorar" um veredito depois que ele foi apresentado.
    """

    #: ⚠️ O PLANO está pronto para criar — a campanha ainda NÃO nasceu.
    #:
    #: Estes dois campos foram um só, e o nome era `campaign_birth`. Ele saía
    #: PRONTO no `/provar`, que não cria nada: o relatório chegou a dizer
    #: "CAMPAIGN_BIRTH_READY ✅" sem existir campanha, recibo ou id externo.
    #: "Nascer" é um fato sobre o mundo, não sobre o plano.
    creation_plan_ready: str = INDETERMINADO
    #: Só vira PRONTO depois de mutate + recibo fechado + releitura na conta.
    campaign_birth: str = INDETERMINADO
    conversion_goal_status: str = INDETERMINADO
    #: ⚠️ SEPARADO do Data Manager de propósito. Data Manager é UMA fonte de
    #: sinal, não a única: tag do Google, importação GA4 e upload offline são
    #: caminhos legítimos. Exigir Data Manager para uma conta que converte por
    #: tag declararia despreparo onde não há.
    conversion_signal_status: str = INDETERMINADO
    #: As fontes de sinal efetivamente OBSERVADAS. Lista vazia = nenhuma foi
    #: comprovada, e isso é diferente de "não existe nenhuma".
    signal_sources: List[str] = field(default_factory=list)
    measurement_readiness: str = INDETERMINADO
    data_manager_status: str = INDETERMINADO
    observability_status: str = INDETERMINADO
    #: ⚠️ Nunca derivado por otimismo. Ver `avaliar`.
    smart_bidding_eligible: bool = False
    activation_blockers: List[str] = field(default_factory=list)
    notas: Dict[str, Any] = field(default_factory=dict)

    def para_json(self) -> Dict[str, Any]:
        return {
            "creation_plan_ready": self.creation_plan_ready,
            "campaign_birth": self.campaign_birth,
            "conversion_goal_status": self.conversion_goal_status,
            "conversion_signal_status": self.conversion_signal_status,
            "signal_sources": list(self.signal_sources),
            "measurement_readiness": self.measurement_readiness,
            "data_manager_status": self.data_manager_status,
            "observability_status": self.observability_status,
            "smart_bidding_eligible": self.smart_bidding_eligible,
            "activation_blockers": list(self.activation_blockers),
            "notas": dict(self.notas),
        }


def avaliar(
    *,
    plano_valido: bool = False,
    recibo_registrado: bool,
    metas_da_conta: Optional[Dict[str, Any]],
    fontes_de_sinal_observadas: Optional[List[str]] = None,
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

    # ⚠️ DUAS PERGUNTAS DIFERENTES, e confundi-las produziu um relatório que
    # dizia "pronto para nascer ✅" sem existir campanha nenhuma.
    plano_pronto = PRONTO if plano_valido else INDETERMINADO
    nascimento = PRONTO if recibo_registrado else NAO_PRONTO
    if not recibo_registrado:
        notas["campaign_birth"] = (
            "a campanha ainda NÃO nasceu. Este campo só vira PRONTO depois de "
            "mutate + recibo fechado + releitura do id externo na conta")

    # ── G1: meta de conversão ────────────────────────────────────────────────
    if metas_da_conta is None:
        meta_status = INDETERMINADO
        notas["conversion_goal"] = (
            "não foi possível ler as metas da conta; ausência de leitura não é "
            "ausência de meta")
        bloqueios.append("metas de conversão não lidas")
    elif metas_da_conta.get("primaria"):
        # ⚠️ PARCIAL, E NÃO PRONTO — e a diferença é o que foi de fato lido.
        #
        # O que existe hoje é uma GAQL sobre `conversion_action`, que devolve as
        # ações e o `primary_for_goal` de cada uma. Isso NÃO é a meta efetiva da
        # campanha. A doc oficial (evidence/GOOGLE-ADS-DOCS-2026-09-01.md) é
        # explícita: o efetivo exige `customer_conversion_goal`,
        # `campaign_conversion_goal` e sobretudo
        # `conversion_goal_campaign_config.goal_config_level`, que diz se quem
        # manda é a conta ou a campanha. Nenhuma dessas três é consultada.
        #
        # Medido na Portal Mundo Mais em 01/09/2026: NOVE ações ENABLED, OITO
        # com `primary_for_goal=true`. Dizer "a ação primária" no singular
        # apagaria sete delas. `PARCIAL` diz o que se sabe sem inventar o resto.
        primarias = [a for a in (metas_da_conta.get("acoes") or ())
                     if a.get("primaria")]
        meta_status = PARCIAL
        notas["conversion_goal"] = (
            f"leitura PARCIAL: {len(primarias) or 1} ação(ões) com "
            "primary_for_goal=true em `conversion_action`. Isso não é a meta "
            "EFETIVA: ela exige customer_conversion_goal, campaign_conversion_goal "
            "e conversion_goal_campaign_config.goal_config_level, que ainda não "
            "são consultados. A campanha herda as metas da conta, e sobrescrever "
            "exigiria CampaignConversionGoal — ato separado, e a API só ATUALIZA "
            "goals, nunca cria nem remove")
        notas["conversion_actions_primarias"] = [
            {"id": a.get("id"), "nome": a.get("nome"),
             "categoria": a.get("categoria")} for a in primarias]
        bloqueios.append(
            "meta de conversão efetiva não lida (faltam customer_conversion_goal "
            "e conversion_goal_campaign_config)")
    else:
        meta_status = NAO_PRONTO
        notas["conversion_goal"] = (
            "a conta não tem ação de conversão primária: uma campanha em lance "
            "automático otimizaria para nada")
        bloqueios.append("conta sem ação de conversão primária")

    # ── G1: sinal chegando ───────────────────────────────────────────────────
    #
    # ⚠️ SINAL ≠ DATA MANAGER. A primeira versão tratava os dois como a mesma
    # coisa e exigia Data Manager operante para declarar medição. Isso está
    # errado em conta que converte por tag do Google ou importação GA4: ela tem
    # sinal chegando e seria declarada despreparada por não usar uma via que
    # não precisa. Data Manager é UMA fonte, e a que ainda não existe aqui.
    fontes = list(fontes_de_sinal_observadas or ())
    if fontes:
        sinal = PRONTO
        notas["conversion_signal"] = (
            "fontes de sinal observadas: " + ", ".join(fontes))
    else:
        sinal = NAO_PRONTO
        notas["conversion_signal"] = (
            "nenhuma fonte de sinal foi COMPROVADA nesta leitura (tag do "
            "Google, importação GA4, upload offline ou Data Manager). Lista "
            "vazia significa 'não comprovado', e não 'não existe'")
        bloqueios.append("nenhuma fonte de sinal de conversão comprovada")

    if data_manager_operante:
        dm_status = PRONTO
    else:
        dm_status = NAO_PRONTO
        notas["data_manager"] = (
            "a ingestão de conversão offline pela Data Manager API não está "
            "operante: fila, lote, envio e diagnóstico existem como contrato, "
            "não como execução. Isso NÃO bloqueia por si só uma conta cuja "
            "conversão venha de tag ou GA4")

    # Medir exige meta efetiva E ao menos um caminho de sinal comprovado. Ter
    # uma sem a outra não é meia medição — é nenhuma, porque o lance aprende do
    # que chega, não do que foi declarado.
    if meta_status == PRONTO and sinal == PRONTO:
        medicao = PRONTO
    elif meta_status == INDETERMINADO or sinal == INDETERMINADO:
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
    # ⚠️ G2 GOVERNA G3 JUNTO COM G1.
    #
    # A primeira versão fazia `smart_bidding_eligible` depender só de medição.
    # A alegação "não liga por ausência de bloqueio" continuava verdadeira, mas
    # os quatro portões não governavam juntos: dava para ter elegibilidade com
    # `observability_status=INDETERMINADO` e `activation_blockers` VAZIO — ou
    # seja, autorizado a otimizar sem conseguir observar o que acontece depois.
    elegivel = medicao == PRONTO and observacao == PRONTO
    if observacao != PRONTO:
        bloqueios.append(
            "observabilidade pós-criação não provada: sem releitura, um "
            "desvio de entrega ou de política não seria notado")
    if not elegivel and estrategia_lance != "MANUAL_CPC":
        bloqueios.append(
            f"estratégia {estrategia_lance} exige sinal de conversão provado")
    notas["manual_cpc"] = (
        "Manual CPC pode existir no canário pausado sem Data Manager. Isso não "
        "autoriza ativação nem implica prontidão de ROI")

    return Prontidao(
        creation_plan_ready=plano_pronto,
        campaign_birth=nascimento,
        conversion_goal_status=meta_status,
        conversion_signal_status=sinal,
        signal_sources=fontes,
        measurement_readiness=medicao,
        data_manager_status=dm_status,
        observability_status=observacao,
        smart_bidding_eligible=elegivel,
        activation_blockers=bloqueios,
        notas=notas,
    )
