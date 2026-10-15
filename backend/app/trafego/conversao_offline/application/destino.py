"""O destino da importação offline, que pode não ser a ação que o lance persegue.

`plano_mensuracao.eleger_acao_canonica` responde "o que o lance desta campanha
persegue", e por isso só elege ação PRIMÁRIA. A importação offline responde
outra pergunta: "onde cai o valor medido". O ADR do ciclo econômico separa as
duas etapas: primeiro o envio para uma ação SECONDARY (observação, sem efeito
no lance), depois, com aceite próprio, torná-la primária.

Esta função deriva do plano LIDO um plano cujo alvo e destino são a ação de
importação escolhida pelo operador, por id numérico e entre as ações lidas da
conta. Não cria ação, não muda meta e não muda nada no Google: só endereça o
envelope. O plano original continua dizendo a verdade sobre o lance.
"""
from __future__ import annotations

import dataclasses

from app.trafego import data_manager as dm
from app.trafego import plano_mensuracao as pm

TIPO_IMPORTACAO_DE_CLIQUES = "UPLOAD_CLICKS"


class AcaoOfflineInvalida(dm.FronteiraRecusou):
    """A ação indicada não existe na leitura, não está habilitada ou não é de importação."""


def plano_para_acao_offline(plano: pm.PlanoDeMensuracao, acao_id: str, *,
                            permitir_acao_primaria: bool = False) -> pm.PlanoDeMensuracao:
    """⚠️ Ação PRIMÁRIA só com `permitir_acao_primaria=True`, que é um aceite à parte.

    Mandar para uma ação primária move o lance; mandar para uma Secondary não.
    O ADR separa as duas etapas, e a aprovação de cada envelope declara qual é
    (`AprovacaoDeEnvio.destino_primario`). `primaria=None` vale primária: é o
    default documentado do Google (`primaria_efetiva`).
    """
    alvo = str(acao_id or "").strip()
    if not alvo.isdigit():
        raise AcaoOfflineInvalida("a ação de importação é indicada pelo id NUMÉRICO, nunca pelo nome")
    achadas = [a for a in plano.acoes if a.id == alvo]
    if not achadas:
        raise AcaoOfflineInvalida(
            f"a ação #{alvo} não está entre as ações lidas da conta {plano.customer_id}")
    acao = achadas[0]
    if str(acao.status or "").upper() != "ENABLED":
        raise AcaoOfflineInvalida(f"a ação #{alvo} está {acao.status}, não ENABLED")
    if acao.tipo != TIPO_IMPORTACAO_DE_CLIQUES:
        raise AcaoOfflineInvalida(
            f"a ação #{alvo} é {acao.tipo}; o valor medido vai para uma ação "
            f"{TIPO_IMPORTACAO_DE_CLIQUES} própria, e não para a tag do site (a tag "
            "e o upload na mesma ação contariam a mesma sessão duas vezes)")
    if acao.primaria_efetiva and not permitir_acao_primaria:
        raise AcaoOfflineInvalida(
            f"a ação #{alvo} é PRIMÁRIA (ou não declarou, o que o Google trata como primária): "
            "o envio moveria o lance. A primeira etapa é Secondary; tornar primária é um "
            "aceite separado (permitir_acao_primaria=True)")
    destino = pm.resolver_destino(acao)
    if not destino.resolvido:
        raise AcaoOfflineInvalida(destino.causa or "destino não resolvido")
    return dataclasses.replace(plano, acao_alvo=acao, acao_alvo_causa=None, destino=destino)
