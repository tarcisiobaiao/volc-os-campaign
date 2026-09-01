"""A leitura da meta EFETIVA — os três recursos que decidem, e nada menos.

## O defeito que este módulo conserta

Até 01/09/2026 o sistema respondia "qual é a meta desta campanha?" com uma GAQL
sobre `conversion_action`. Ela devolve as ações da conta e o `primary_for_goal`
de cada uma — o que é uma resposta verdadeira para OUTRA pergunta.

A meta efetiva exige três recursos, e a doc oficial é explícita sobre não haver
um quarto que os resuma:

    customer_conversion_goal          as metas da CONTA
    campaign_conversion_goal          as metas da CAMPANHA
    conversion_goal_campaign_config   QUAL DOS DOIS manda

> "Campaigns automatically inherit the effective conversion account's customer
> goals **unless** they have been configured with their own set of campaign
> goals."
> — GoalConfigLevel, developers.google.com/google-ads/api/reference/rpc/v25/
>   GoalConfigLevelEnum.GoalConfigLevel

Ler uma das três e chamar de meta efetiva é exatamente o defeito. Ler as três e
esquecer do nível é o mesmo defeito com mais consultas.

## O que este módulo NÃO faz

Não decide, não persiste e não muta. `assert` nenhum aqui autoriza coisa
alguma: ele lê, traduz para o vocabulário de `plano_mensuracao.py` e carrega o
ESTADO de cada leitura — inclusive `falhou`. Quem decide é `prontidao.avaliar`;
quem grava é `persistencia.py`.

⚠️ **E ele nunca escreve no Google.** Toda consulta aqui é `SELECT`. A doc
oficial fecha a porta do outro lado também:

> "**you can only update those objects. The Google Ads API doesn't support
> creating or removing those objects.**"

## Por que `buscar` é um parâmetro

`contas.py` importa `volc_ads.gads.client.buscar` dentro do corpo de cada
função, e o resultado é que ele não tem UM teste offline: a única forma de
exercitá-lo sem rede seria monkeypatchar o módulo do engine, e nenhum teste da
casa faz isso. Aqui a função de busca entra por parâmetro — como
`adaptador_search.ler_filhas` já faz — e o default continua sendo o `buscar`
real, importado tarde. Custo zero em produção, e a leitura passa a ser
provável sem tocar a conta de ninguém.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from app.trafego import plano_mensuracao as pm

log = logging.getLogger("volc.trafego.metas_efetivas")

Buscar = Callable[..., Iterable[Any]]


# ═══════════════════════════════════════════════════════════════════════════
# AS CONSULTAS
# ═══════════════════════════════════════════════════════════════════════════
#
# Cada campo abaixo foi conferido DUAS vezes em 01/09/2026: contra a página de
# `fields/v25` do recurso (Selectable/Filterable) e contra o descritor real do
# SDK instalado nesta máquina. Um nome inventado aqui não daria erro de
# compilação — daria um `INVALID_FIELD` em produção, na conta do cliente.

#: ⚠️ SEM `WHERE`. `customer_conversion_goal` é de CONTA: o `resource_name` dele
#: tem a forma `customers/{cid}/customerConversionGoals/{category}~{origin}`, ou
#: seja, uma linha por par (categoria, origem). Não há campanha para filtrar.
GAQL_METAS_DA_CONTA = """
    SELECT
      customer_conversion_goal.category,
      customer_conversion_goal.origin,
      customer_conversion_goal.biddable
    FROM customer_conversion_goal
"""

#: ⚠️ O filtro é por RESOURCE NAME, não por `campaign.id`.
#: `conversion_goal_campaign_config.campaign` é `Filterable: True` e do tipo
#: RESOURCE_NAME — o valor tem a forma `customers/{cid}/campaigns/{id}` e vai
#: entre aspas simples na GAQL. Filtrar por `campaign.id` funcionaria por
#: atribuição, e depender disso seria depender de um caminho que a página do
#: recurso não promete.
GAQL_NIVEL_DA_META = """
    SELECT
      conversion_goal_campaign_config.campaign,
      conversion_goal_campaign_config.goal_config_level,
      conversion_goal_campaign_config.custom_conversion_goal
    FROM conversion_goal_campaign_config
    WHERE conversion_goal_campaign_config.campaign = '{recurso_da_campanha}'
"""

GAQL_METAS_DA_CAMPANHA = """
    SELECT
      campaign_conversion_goal.campaign,
      campaign_conversion_goal.category,
      campaign_conversion_goal.origin,
      campaign_conversion_goal.biddable
    FROM campaign_conversion_goal
    WHERE campaign_conversion_goal.campaign = '{recurso_da_campanha}'
"""

#: A identidade completa de cada ação, com o DONO.
#:
#: ⚠️ `status != 'REMOVED'` e não `= 'ENABLED'`: `HIDDEN` existe no enum e uma
#: ação escondida continua sendo um fato sobre a conta. Filtrá-la aqui faria a
#: leitura afirmar que ela não existe; ela é filtrada na ELEIÇÃO, que é onde a
#: distinção importa.
#:
#: ⚠️ `conversion_action.type` (e não `type_`): `type_` é o nome do atributo no
#: SDK Python, `type` é o nome do campo no proto e na GAQL.
GAQL_ACOES = """
    SELECT
      conversion_action.id,
      conversion_action.name,
      conversion_action.resource_name,
      conversion_action.owner_customer,
      conversion_action.category,
      conversion_action.origin,
      conversion_action.type,
      conversion_action.status,
      conversion_action.primary_for_goal,
      conversion_action.include_in_conversions_metric
    FROM conversion_action
    WHERE conversion_action.status != 'REMOVED'
"""

#: O frescor, pelo campo que a doc oficial nomeia para isso:
#:
#: > "metrics.conversion_last_conversion_date — The date of the most recent
#: > conversion for this conversion action. The date is in the customer's time
#: > zone."
#:
#: ⚠️ Consulta SEPARADA da anterior de propósito, e não um campo a mais nela.
#: Uma consulta com `metrics` tem semântica de relatório; misturá-la com a
#: leitura de identidade faria uma falha de métrica apagar a identidade que já
#: tinha sido lida — que é exatamente a armadilha que o router já tem com
#: `metas = None`.
GAQL_FRESCOR = """
    SELECT
      conversion_action.id,
      metrics.conversion_last_conversion_date
    FROM conversion_action
    WHERE conversion_action.status = 'ENABLED'
"""

#: A marcação da conta: por onde o sinal PODE chegar.
GAQL_MARCACAO = """
    SELECT
      customer.id,
      customer.time_zone,
      customer.auto_tagging_enabled,
      customer.conversion_tracking_setting.conversion_tracking_id,
      customer.conversion_tracking_setting.cross_account_conversion_tracking_id,
      customer.conversion_tracking_setting.accepted_customer_data_terms,
      customer.conversion_tracking_setting.conversion_tracking_status,
      customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled,
      customer.conversion_tracking_setting.google_ads_conversion_customer
    FROM customer
    LIMIT 1
"""

#: Os tipos de ação cuja existência é evidência de TAG DO GOOGLE no site — o
#: caminho de GTM. Derivado de `type`, e não de `tag_snippets`: o segundo é uma
#: mensagem repetida cuja seletividade em GAQL não foi provada, e um campo não
#: provado numa consulta derruba a consulta inteira em produção.
TIPOS_DE_TAG: Tuple[str, ...] = ("WEBPAGE", "WEBPAGE_CODELESS")

#: Os tipos cuja existência é evidência de importação GA4 ou Firebase.
PREFIXOS_DE_GA4: Tuple[str, ...] = (
    "GOOGLE_ANALYTICS_4", "FIREBASE_", "UNIVERSAL_ANALYTICS_",
    "THIRD_PARTY_APP_ANALYTICS_",
)


# ═══════════════════════════════════════════════════════════════════════════
# LEITURA DE PROTO — sem colapsar ausência
# ═══════════════════════════════════════════════════════════════════════════


def _enum(valor: Any) -> str:
    """O nome do enum, e nunca o número.

    ⚠️ `str(valor)` de um enum proto devolve o inteiro em algumas versões do
    runtime. Um `2` viajando onde se espera `PURCHASE` casaria com nada na
    semântica e produziria "nenhuma ação corresponde ao objetivo" — um veredito
    errado com cara de leitura correta.
    """
    nome = getattr(valor, "name", None)
    return str(nome if nome is not None else valor or "")


def _tem(mensagem: Any, campo: str) -> bool:
    """O campo veio na resposta? Para os campos com *presence* no proto.

    ⚠️ Isto NÃO é preciosismo. `conversion_action.primary_for_goal` tem presence
    (provado contra o descritor real do SDK v25), e a doc oficial diz, literal:
    "By default, `primary_for_goal` will be true if not set." Lê-lo com
    `bool(...)` devolve `False` para uma ação que o Google trata como PRIMÁRIA —
    o veredito exatamente invertido, no campo que decide o lance.
    """
    try:
        return bool(mensagem._pb.HasField(campo))  # noqa: SLF001
    except Exception:  # noqa: BLE001 — sem presence, a pergunta não cabe
        return True


def _bool_ou_none(mensagem: Any, campo: str) -> Optional[bool]:
    if not _tem(mensagem, campo):
        return None
    return bool(getattr(mensagem, campo))


def _int_ou_none(mensagem: Any, campo: str) -> Optional[str]:
    """Um int64 com *presence*, como texto — ou `None` quando não veio.

    ⚠️ `str(0)` é `"0"`, que é truthy. Sem esta função, `x or None` sobre um
    campo int64 não setado devolvia `"0"` e uma conta SEM conversion tracking
    saía declarando o id `0`.
    """
    if mensagem is None or not _tem(mensagem, campo):
        return None
    valor = getattr(mensagem, campo, None)
    return None if valor is None else str(valor)


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor)


def recurso_da_campanha(customer_id: str, campaign_id: str) -> str:
    """`customers/{cid}/campaigns/{id}` — a forma que o filtro exige."""
    return f"customers/{str(customer_id).strip()}/campaigns/{str(campaign_id).strip()}"


# ═══════════════════════════════════════════════════════════════════════════
# UMA LEITURA, COM ESTADO
# ═══════════════════════════════════════════════════════════════════════════


def _buscar_padrao() -> Buscar:
    """O `buscar` real, importado TARDE.

    `volc_ads` mora fora do pacote do backend e pode não estar no caminho de um
    processo que só serve a API. Importar no topo derrubaria o módulo inteiro
    por causa de uma consulta que talvez nem seja feita.
    """
    from volc_ads.gads.client import buscar  # noqa: PLC0415

    return buscar


def _ler(consulta: str, *, customer_id: str, login_customer_id: str,
         buscar: Optional[Buscar], rotulo: str) -> Tuple[str, List[Any], Optional[str]]:
    """`(estado, linhas, causa)`. Nunca levanta, nunca inventa.

    ⚠️ A distinção que custa caro está aqui: uma exceção vira `falhou` com a
    causa, e uma resposta vazia vira `vazio_confirmado`. Colapsá-las faria uma
    conta sem meta parecer uma rede instável, e uma rede instável parecer uma
    conta sem meta — e as duas pedem coisas opostas de quem lê.
    """
    fn = buscar or _buscar_padrao()
    try:
        linhas = list(fn(str(customer_id), consulta,
                         login_customer_id=str(login_customer_id)))
    except Exception as exc:  # noqa: BLE001 — falha é estado, não exceção aqui
        log.warning("leitura %s da conta %s falhou: %s", rotulo, customer_id,
                    type(exc).__name__)
        return pm.FALHOU, [], (
            f"a leitura de {rotulo} não completou "
            f"({type(exc).__name__}). Falha de leitura não é ausência de dado.")
    if not linhas:
        return pm.VAZIO_CONFIRMADO, [], None
    return pm.COM_DADOS, linhas, None


# ═══════════════════════════════════════════════════════════════════════════
# METAS
# ═══════════════════════════════════════════════════════════════════════════


def ler_metas_da_conta(customer_id: str, *, login_customer_id: str,
                       buscar: Optional[Buscar] = None,
                       ) -> Tuple[str, Tuple[pm.Meta, ...], Optional[str]]:
    """As metas de conta — uma por par (categoria, origem)."""
    estado, linhas, causa = _ler(
        GAQL_METAS_DA_CONTA, customer_id=customer_id,
        login_customer_id=login_customer_id, buscar=buscar,
        rotulo="metas da conta")
    metas = tuple(
        pm.Meta(categoria=_enum(l.customer_conversion_goal.category),
                origem=_enum(l.customer_conversion_goal.origin),
                biddable=bool(l.customer_conversion_goal.biddable))
        for l in linhas
    )
    return estado, metas, causa


def ler_metas_da_campanha(customer_id: str, campaign_id: Optional[str], *,
                          login_customer_id: str,
                          buscar: Optional[Buscar] = None,
                          ) -> Tuple[str, Tuple[pm.Meta, ...], Optional[str]]:
    """As metas da campanha — ou `inelegivel` quando a campanha não existe.

    ⚠️ `campaign_id=None` é o caso do NASCIMENTO, e a resposta correta é
    `inelegivel`, não `vazio_confirmado`. A campanha ainda não existe: perguntar
    quais são as metas dela não é uma pergunta que a API possa responder com
    "nenhuma". Dizer `vazio_confirmado` afirmaria que a campanha existe e não
    tem meta — e essa afirmação é falsa sobre uma campanha que não nasceu.
    """
    if not campaign_id:
        return pm.INELEGIVEL, (), (
            "a campanha ainda não existe, e metas de campanha só existem depois "
            "que ela nasce. Ela herda as metas da conta até alguém decidir o "
            "contrário — e decidir o contrário é um ato separado.")
    estado, linhas, causa = _ler(
        GAQL_METAS_DA_CAMPANHA.format(
            recurso_da_campanha=recurso_da_campanha(customer_id, campaign_id)),
        customer_id=customer_id, login_customer_id=login_customer_id,
        buscar=buscar, rotulo="metas da campanha")
    metas = tuple(
        pm.Meta(categoria=_enum(l.campaign_conversion_goal.category),
                origem=_enum(l.campaign_conversion_goal.origin),
                biddable=bool(l.campaign_conversion_goal.biddable),
                campaign=_texto(l.campaign_conversion_goal.campaign) or None)
        for l in linhas
    )
    return estado, metas, causa


def ler_nivel(customer_id: str, campaign_id: Optional[str], *,
              login_customer_id: str,
              buscar: Optional[Buscar] = None,
              ) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Quem manda nesta campanha: a conta ou ela mesma.

    ⚠️ `UNSPECIFIED` e `UNKNOWN` viajam INTEIROS. A tentação é traduzi-los para
    `CUSTOMER`, porque a herança é o caso comum e a frase da doc ("campaigns
    automatically inherit … unless") quase autoriza. Quase. Ela descreve o
    comportamento do produto, não o valor do campo — e afirmar `CUSTOMER` a
    partir de `UNKNOWN` seria decidir, aqui, uma coisa que ninguém leu.
    """
    if not campaign_id:
        return pm.INELEGIVEL, None, None, (
            "o nível de configuração de meta é um atributo da campanha, e a "
            "campanha ainda não existe.")
    estado, linhas, causa = _ler(
        GAQL_NIVEL_DA_META.format(
            recurso_da_campanha=recurso_da_campanha(customer_id, campaign_id)),
        customer_id=customer_id, login_customer_id=login_customer_id,
        buscar=buscar, rotulo="nível de configuração da meta")
    if estado != pm.COM_DADOS:
        return estado, None, None, causa
    cfg = linhas[0].conversion_goal_campaign_config
    nivel = _enum(cfg.goal_config_level)
    # ⚠️ Um resource name não setado chega como STRING VAZIA no proto, não como
    # `None`. Sem este `or None`, `""` viajaria como "há meta customizada" e
    # travaria toda campanha normal com um bloqueio inventado.
    custom = _texto(getattr(cfg, "custom_conversion_goal", "")).strip() or None
    if nivel not in pm.NIVEIS:
        # Um valor fora do enum conhecido é um contrato que mudou embaixo de
        # nós. `nao_suportado` diz isso; traduzir para desconhecido esconderia.
        return pm.NAO_SUPORTADO, None, custom, (
            f"o nível de configuração veio como {nivel!r}, que não está no enum "
            f"conhecido desta versão da API.")
    return pm.COM_DADOS, nivel, custom, None


def ler_meta_efetiva(customer_id: str, *, login_customer_id: str,
                     campaign_id: Optional[str] = None,
                     buscar: Optional[Buscar] = None) -> pm.MetaEfetiva:
    """As TRÊS leituras, cada uma com o seu estado — e nenhuma apagando a outra.

    ⚠️ Três chamadas independentes de propósito. O router hoje colapsa timeout e
    exceção num único `metas = None`, e o efeito é que uma falha na consulta
    nova apagaria a leitura antiga que tinha funcionado. Aqui cada leitura
    carrega o próprio estado, e o veredito é montado do que sobreviveu.
    """
    estado_conta, metas_conta, causa_conta = ler_metas_da_conta(
        customer_id, login_customer_id=login_customer_id, buscar=buscar)
    estado_nivel, nivel, custom, causa_nivel = ler_nivel(
        customer_id, campaign_id, login_customer_id=login_customer_id,
        buscar=buscar)
    estado_camp, metas_camp, causa_camp = ler_metas_da_campanha(
        customer_id, campaign_id, login_customer_id=login_customer_id,
        buscar=buscar)

    # ⚠️ A herança documentada é aplicada AQUI, e dita em voz alta — nunca
    # escondida dentro de um default. Antes do nascimento, `goal_config_level`
    # é inelegível porque a campanha não existe; e a doc afirma que uma campanha
    # nova HERDA as metas da conta enquanto ninguém configurar as dela:
    #
    #   "Campaigns automatically inherit the effective conversion account's
    #    customer goals unless they have been configured with their own set of
    #    campaign goals."
    #
    # Aplicar isso ANTES do nascimento é legítimo e é o ponto inteiro desta
    # tarefa: o plano precisa dizer, antes de a campanha existir, para o que ela
    # vai otimizar. Aplicá-lo DEPOIS do nascimento seria outra coisa — seria
    # ignorar o campo que existe e responde.
    causas: List[str] = [c for c in (causa_conta, causa_nivel, causa_camp) if c]
    herdado = False
    if campaign_id is None and estado_nivel == pm.INELEGIVEL:
        nivel = pm.NIVEL_CUSTOMER
        # ⚠️ O ESTADO CONTINUA `inelegivel`, e é o campo `nivel_herdado` que
        # carrega a inferência. Sintetizar `com_dados` aqui — como a primeira
        # versão fazia — afirmaria que o recurso foi consultado. Ninguém o
        # consultou: a campanha não existe. E o estado sintetizado ia parar numa
        # coluna consultável do banco, onde ficaria indistinguível de um nível
        # de fato lido.
        herdado = True
        causas.insert(0, (
            "a campanha ainda não nasceu: o nível que manda é o da CONTA, por "
            "herança declarada na documentação oficial. No dia em que a "
            "campanha existir, este campo passa a ser lido do recurso e deixa "
            "de ser inferido."))

    return pm.MetaEfetiva(
        nivel=nivel,
        nivel_estado=estado_nivel,
        metas_da_conta=metas_conta,
        metas_da_conta_estado=estado_conta,
        metas_da_campanha=metas_camp,
        metas_da_campanha_estado=estado_camp,
        campaign_id=(str(campaign_id) if campaign_id else None),
        custom_conversion_goal=custom,
        nivel_herdado=herdado,
        causa=(" · ".join(causas) if causas else None),
    )


# ═══════════════════════════════════════════════════════════════════════════
# AÇÕES DE CONVERSÃO
# ═══════════════════════════════════════════════════════════════════════════


def ler_acoes(customer_id: str, *, login_customer_id: str,
              buscar: Optional[Buscar] = None,
              ) -> Tuple[str, Tuple[pm.AcaoDeConversao, ...], Optional[str]]:
    """As ações da conta, com DONO — a leitura que resolve o destino offline.

    ⚠️ `owner_customer` pode vir vazio, e a doc diz por quê: "the resource name
    of the conversion action owner customer, **or null if this is a
    system-defined conversion action**". `None` aqui é um fato sobre a ação, e
    não uma falha da leitura — e é ele que faz `resolver_destino` recusar com
    causa em vez de mandar o evento para a conta errada.
    """
    estado, linhas, causa = _ler(
        GAQL_ACOES, customer_id=customer_id,
        login_customer_id=login_customer_id, buscar=buscar,
        rotulo="ações de conversão")
    acoes: List[pm.AcaoDeConversao] = []
    for l in linhas:
        a = l.conversion_action
        identificador = _texto(getattr(a, "id", "")).strip()
        if not identificador.isdigit():
            # Uma ação sem id numérico não é endereçável pelo Data Manager e
            # não pode virar destino. Deixá-la de fora com log é melhor que
            # explodir a leitura inteira — e melhor que fabricar um id.
            log.warning("ação de conversão sem id numérico na conta %s",
                        customer_id)
            continue
        acoes.append(pm.AcaoDeConversao(
            id=identificador,
            resource_name=_texto(a.resource_name),
            owner_customer_id=pm.customer_id_do_recurso(
                _texto(getattr(a, "owner_customer", "")) or None),
            nome=_texto(getattr(a, "name", "")),
            categoria=_enum(a.category),
            origem=_enum(a.origin),
            tipo=_enum(getattr(a, "type_", getattr(a, "type", ""))),
            status=_enum(a.status),
            primaria=_bool_ou_none(a, "primary_for_goal"),
            incluida_em_metricas=_bool_ou_none(
                a, "include_in_conversions_metric"),
        ))
    return estado, tuple(acoes), causa


# ═══════════════════════════════════════════════════════════════════════════
# FRESCOR
# ═══════════════════════════════════════════════════════════════════════════


def ler_frescor(customer_id: str, acao: Optional[pm.AcaoDeConversao], *,
                login_customer_id: str,
                hoje: Optional[str] = None,
                buscar: Optional[Buscar] = None) -> pm.Frescor:
    """Quando esta ação recebeu a última conversão.

    O campo é o que a doc oficial nomeia para exatamente isto:

    > "metrics.conversion_last_conversion_date — The date of the most recent
    > conversion for this conversion action. The date is in the customer's
    > time zone."

    ⚠️ `hoje` entra por parâmetro. Sem ele, esta função dependeria do relógio da
    máquina para calcular `dias_desde_a_ultima`, e um teste que fixasse a data
    da conversão passaria hoje e falharia amanhã. Quando `hoje` não vem, a
    distância NÃO é calculada — e `None` é dito em voz alta em vez de virar um
    número que envelhece sozinho.
    """
    if acao is None:
        return pm.Frescor(
            estado=pm.INELEGIVEL,
            causa=("nenhuma ação de conversão foi eleita para esta campanha; "
                   "frescor sem sujeito não decide nada."))
    estado, linhas, causa = _ler(
        GAQL_FRESCOR, customer_id=customer_id,
        login_customer_id=login_customer_id, buscar=buscar,
        rotulo="data da última conversão")
    if estado == pm.VAZIO_CONFIRMADO:
        # ⚠️ ZERO LINHA NO RELATÓRIO NÃO É ZERO CONVERSÃO, e confundir os dois
        # era um defeito meu que a revisão adversarial reproduziu.
        #
        # `_ler` devolve `vazio_confirmado` quando a consulta volta sem linha —
        # o que, para a maioria das leituras, é a conclusão "não há nenhum".
        # Para o FRESCOR não é: o relatório não ter trazido linha nenhuma não
        # diz nada sobre esta ação ter recebido conversão. O zero MEDIDO desta
        # leitura mora noutro lugar: a linha vem e o campo de data vem vazio
        # (mais abaixo). Repassar `vazio_confirmado` daqui produzia um
        # `Frescor(vazio_confirmado, conversoes=None)` que o schema recusa e que
        # a tela afirmava como "nunca recebeu conversão" — uma afirmação sobre a
        # conta a partir de um relatório que voltou vazio.
        #
        # ⚠️ E há um motivo concreto para isso acontecer: `GAQL_ACOES` filtra
        # `status != 'REMOVED'` e `GAQL_FRESCOR` filtra `status = 'ENABLED'`.
        # As duas consultas NÃO veem o mesmo conjunto, e uma ação `HIDDEN`
        # eleita cai exatamente aqui.
        return pm.Frescor(
            estado=pm.INELEGIVEL,
            conversion_action_id=acao.id,
            causa=("a leitura de frescor não devolveu linha nenhuma. Isso é "
                   "diferente de esta ação ter recebido zero conversões: o "
                   "relatório não trouxe ação alguma, e daqui as duas são "
                   "indistinguíveis."))
    if estado != pm.COM_DADOS:
        return pm.Frescor(
            estado=estado,
            conversion_action_id=acao.id,
            causa=(causa or
                   "a leitura de frescor não completou para esta conta."))

    data: Optional[str] = None
    for l in linhas:
        if _texto(getattr(l.conversion_action, "id", "")).strip() != acao.id:
            continue
        data = _texto(getattr(l.metrics, "conversion_last_conversion_date", "")).strip()
        break

    if data is None:
        # A consulta trouxe linhas e nenhuma é desta ação. Isso é `inelegivel`:
        # a ação existe no cadastro e não apareceu no relatório — não é zero
        # medido, porque ninguém mediu ESTA ação.
        return pm.Frescor(
            estado=pm.INELEGIVEL,
            conversion_action_id=acao.id,
            causa=("a ação eleita não apareceu na leitura de frescor. Ela pode "
                   "estar fora do relatório por não estar habilitada — e não "
                   "aparecer é diferente de ter recebido zero conversões."))
    if not data:
        # ⚠️ ESTE é o zero medido: a linha veio, o campo veio vazio. A API diz
        # "nunca houve conversão para esta ação", e essa é uma conclusão.
        return pm.Frescor(
            estado=pm.VAZIO_CONFIRMADO,
            conversion_action_id=acao.id,
            conversoes_na_janela=0.0,
            causa=None)

    dias = _dias_ate(data, hoje)
    return pm.Frescor(
        estado=pm.COM_DADOS,
        ultima_conversao_em=data,
        dias_desde_a_ultima=dias,
        # ⚠️ `1.0` NÃO é uma contagem: é a marca de que houve ao menos uma
        # conversão, que é tudo o que `conversion_last_conversion_date` prova.
        # Contar quantas exigiria `metrics.all_conversions` com janela, que é
        # outra consulta — e inventar aqui um número que ninguém somou seria
        # dar precisão a uma leitura que não a tem.
        conversoes_na_janela=1.0,
        conversion_action_id=acao.id,
        causa=None,
    )


def _dias_ate(data: str, hoje: Optional[str]) -> Optional[int]:
    """A distância em dias — ou `None` quando não há de onde contar."""
    if not hoje:
        return None
    from datetime import date  # noqa: PLC0415

    try:
        a = date.fromisoformat(str(data).strip())
        b = date.fromisoformat(str(hoje).strip())
    except ValueError:
        return None
    return (b - a).days


# ═══════════════════════════════════════════════════════════════════════════
# MARCAÇÃO
# ═══════════════════════════════════════════════════════════════════════════


def ler_marcacao(customer_id: str, *, login_customer_id: str,
                 acoes: Sequence[pm.AcaoDeConversao] = (),
                 acoes_estado: str = pm.NAO_COLETADO,
                 buscar: Optional[Buscar] = None) -> pm.InventarioDeMarcacao:
    """Por onde o sinal PODE chegar nesta conta.

    ⚠️ `google_ads_conversion_customer` é o campo que diz QUEM é o dono do
    tracking. Numa hierarquia com conversion tracking centralizado no manager,
    a conta que roda a campanha e a que possui as ações são diferentes — e é
    essa diferença que faz um evento offline chegar em lugar nenhum quando
    alguém usa a conta errada como operating account.
    """
    estado, linhas, causa = _ler(
        GAQL_MARCACAO, customer_id=customer_id,
        login_customer_id=login_customer_id, buscar=buscar,
        rotulo="marcação da conta")
    if estado != pm.COM_DADOS:
        return pm.InventarioDeMarcacao(
            estado=estado,
            causa=(causa or "a consulta de marcação não devolveu a conta."))
    c = linhas[0].customer
    cts = getattr(c, "conversion_tracking_setting", None)

    # ⚠️ As duas listas abaixo só são preenchidas quando a leitura de AÇÕES
    # concluiu. Derivá-las de uma lista que ninguém leu produziria `()` — e um
    # `()` aqui seria lido como "esta conta não tem tag e não tem GA4", que é
    # uma afirmação sobre o mundo a partir do que não se olhou.
    com_tag: Tuple[str, ...] = ()
    de_ga4: Tuple[str, ...] = ()
    if acoes_estado not in pm.ESTADOS_SEM_CONCLUSAO:
        com_tag = tuple(a.id for a in acoes
                        if a.tipo in TIPOS_DE_TAG
                        and str(a.status).upper() == "ENABLED")
        de_ga4 = tuple(a.id for a in acoes
                       if any(a.tipo.startswith(p) for p in PREFIXOS_DE_GA4)
                       and str(a.status).upper() == "ENABLED")

    return pm.InventarioDeMarcacao(
        estado=pm.COM_DADOS,
        auto_tagging=_bool_ou_none(c, "auto_tagging_enabled"),
        fuso=(_texto(getattr(c, "time_zone", "")) or None),
        # ⚠️ `conversion_tracking_id` e `cross_account_conversion_tracking_id`
        # são INT64 COM PRESENCE (provado contra o descritor v25). `_texto(0)`
        # devolve a string "0", que é truthy — então o campo NÃO SETADO virava
        # `"0"` em vez de `None`, e uma conta sem tracking chegava à tela e ao
        # banco declarando um id que não existe. `_int_ou_none` respeita a
        # presença, como `_bool_ou_none` já fazia para os booleanos.
        conversion_tracking_id=_int_ou_none(cts, "conversion_tracking_id"),
        conversion_tracking_owner_id=pm.customer_id_do_recurso(
            _texto(getattr(cts, "google_ads_conversion_customer", "")) or None),
        cross_account_conversion_tracking_id=_int_ou_none(
            cts, "cross_account_conversion_tracking_id"),
        conversion_tracking_status=(
            _enum(getattr(cts, "conversion_tracking_status", "")) or None),
        aceitou_termos_de_dados=(
            _bool_ou_none(cts, "accepted_customer_data_terms")
            if cts is not None else None),
        enhanced_conversions_for_leads=(
            _bool_ou_none(cts, "enhanced_conversions_for_leads_enabled")
            if cts is not None else None),
        acoes_de_ga4=de_ga4,
        acoes_com_tag=com_tag,
        causa=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# O PLANO INTEIRO, DE UMA LEITURA SÓ
# ═══════════════════════════════════════════════════════════════════════════


def hoje_na_conta(fuso: Optional[str]) -> Optional[str]:
    """A data de HOJE no fuso da CONTA — nunca no do servidor.

    ⚠️ `metrics.conversion_last_conversion_date` é, literalmente, "the date of
    the most recent conversion for this conversion action. The date is **in the
    customer's time zone**". Subtraí-la da data local do servidor compara dois
    fusos como se fossem um: num container em UTC, toda conversão de hoje entre
    21h e meia-noite de Brasília vira "há 1 dia", e o ramo "última conversão
    hoje" fica inalcançável por três horas por dia.

    `None` quando o fuso não foi lido ou não é conhecido — e `None` não vira o
    relógio do servidor: sem saber de quando contar, `Frescor.comprovado` é
    `False`, que é o lado seguro.
    """
    if not fuso:
        return None
    from datetime import datetime  # noqa: PLC0415
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415

    try:
        return datetime.now(ZoneInfo(str(fuso))).date().isoformat()
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("fuso %r da conta não é conhecido nesta máquina", fuso)
        return None


def ler_plano(customer_id: str, *, login_customer_id: str,
              campaign_id: Optional[str] = None,
              chave_intencao: Optional[str] = None,
              hoje: Optional[str] = None,
              buscar: Optional[Buscar] = None) -> pm.PlanoDeMensuracao:
    """O plano canônico, montado do que CINCO leituras independentes trouxeram.

    ⚠️ Nenhuma leitura aborta a próxima. Cada uma carrega o próprio estado, e o
    plano que sai descreve exatamente o que se sabe — inclusive quando o que se
    sabe é pouco. É o oposto do `try/except → metas = None` que o router faz
    hoje, em que uma falha apaga tudo o que já tinha funcionado.
    """
    meta = ler_meta_efetiva(customer_id, login_customer_id=login_customer_id,
                            campaign_id=campaign_id, buscar=buscar)
    estado_acoes, acoes, _ = ler_acoes(
        customer_id, login_customer_id=login_customer_id, buscar=buscar)

    plano = pm.montar(
        customer_id=customer_id,
        login_customer_id=login_customer_id,
        meta_efetiva=meta,
        acoes=acoes,
        acoes_estado=estado_acoes,
        campaign_id=campaign_id,
        chave_intencao=chave_intencao,
    )
    marcacao = ler_marcacao(customer_id, login_customer_id=login_customer_id,
                            acoes=acoes, acoes_estado=estado_acoes,
                            buscar=buscar)
    # ⚠️ A MARCAÇÃO VEM ANTES DO FRESCOR, e a ordem é a correção de um defeito.
    # É ela que traz `customer.time_zone`, e é no fuso da CONTA que a data da
    # última conversão foi escrita. `hoje` explícito de quem chama ainda vence —
    # é o que torna os testes determinísticos —, mas o default deixou de ser o
    # relógio do servidor.
    frescor = ler_frescor(customer_id, plano.acao_alvo,
                          login_customer_id=login_customer_id,
                          hoje=hoje or hoje_na_conta(marcacao.fuso),
                          buscar=buscar)
    # Remontado com as duas leituras que dependiam da eleição. A eleição não
    # muda: ela é função das metas e das ações, e nenhuma das duas foi relida.
    return pm.montar(
        customer_id=customer_id,
        login_customer_id=login_customer_id,
        meta_efetiva=meta,
        acoes=acoes,
        acoes_estado=estado_acoes,
        frescor=frescor,
        marcacao=marcacao,
        campaign_id=campaign_id,
        chave_intencao=chave_intencao,
    )
