"""As contas do Google Ads — descobertas, não digitadas.

## O defeito que este módulo conserta

O cockpit pedia `customer_id` e `login_customer_id` num campo de texto. São dois
números de dez dígitos, sem separador, que o operador teria de achar noutro
lugar e colar — e um dígito errado produz um erro da API que não diz "você
errou o id", diz `USER_PERMISSION_DENIED`.

Pior: a informação já existia. `projects` tem `google_ads_customer_id` e
`google_ads_manager_id` desde antes deste módulo, e `pautador_funnel_runs`
carrega `project_id`. O funil já sabia em que conta a campanha ia entrar; a
tela é que perguntava.

## O que a API dá, e o que ela cobra por isso

`CustomerService.ListAccessibleCustomers` devolve os customer ids que a
credencial alcança — só os ids, sem nome nem hierarquia, e ele não aceita
filtro. Para saber o que é MCC, o que é conta filha e como se chamam, é preciso
uma query em `customer_client` POR MCC.

Ambos são leitura pura (GAQL só tem SELECT), então a trava de `gads/modo.py`
nem chega a ser exercida — não há o que travar.

## `auto_tagging_enabled` não é detalhe

`marcacao.py` recusa `marcacao_gclid=True` quando o auto-tagging da conta está
ligado: com ele, o Google já anexa o `gclid` e declarar a macro duplica o
parâmetro. Hoje o brief DECLARA esse booleano, ou seja chuta. Aqui ele é lido
da conta — a checagem passa a valer de verdade.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger("volc.trafego.contas")

# Uma linha por conta acessível sob um MCC, incluindo o próprio MCC.
# `customer_client.level` é a distância até o manager: 0 é ele mesmo.
GAQL_CLIENTES = """
    SELECT
      customer_client.client_customer,
      customer_client.id,
      customer_client.descriptive_name,
      customer_client.currency_code,
      customer_client.time_zone,
      customer_client.manager,
      customer_client.test_account,
      customer_client.level,
      customer_client.status,
      customer_client.hidden
    FROM customer_client
    WHERE customer_client.status = 'ENABLED'
"""

# Os campos da conta que MUDAM o payload da campanha. Não é telemetria: cada um
# deles é consumido por alguma decisão do construtor.
GAQL_CONTA = """
    SELECT
      customer.id,
      customer.descriptive_name,
      customer.currency_code,
      customer.time_zone,
      customer.auto_tagging_enabled,
      customer.manager,
      customer.test_account
    FROM customer
    LIMIT 1
"""


def _texto(v: Any) -> str:
    return "" if v is None else str(v)


def descobrir(mcc: str) -> Dict[str, Any]:
    """Lista as contas sob um MCC. Somente leitura.

    ⚠️ Contas `hidden` e `test_account` viajam com a marca, não são filtradas
    aqui. Esconder a conta de teste tiraria do operador justamente a que ele
    deveria usar para o primeiro disparo; esconder a `hidden` faria uma conta
    sumir da lista sem explicação e ninguém saberia por quê.
    """
    from volc_ads.gads.client import buscar

    linhas = list(buscar(str(mcc), GAQL_CLIENTES, login_customer_id=str(mcc)))
    contas: List[Dict[str, Any]] = []
    for l in linhas:
        c = l.customer_client
        contas.append({
            "customer_id": str(c.id),
            "nome": _texto(c.descriptive_name) or f"conta {c.id}",
            "moeda": _texto(c.currency_code),
            "fuso": _texto(c.time_zone),
            # `manager=True` é MCC: não recebe campanha, só administra.
            "manager": bool(c.manager),
            "teste": bool(c.test_account),
            "oculta": bool(c.hidden),
            # 0 = o próprio MCC consultado; 1 = filha direta; 2+ = neta.
            "nivel": int(c.level),
        })
    contas.sort(key=lambda x: (x["manager"], x["nome"].lower()))
    return {
        "mcc": str(mcc),
        "contas": contas,
        "anunciaveis": [c for c in contas if not c["manager"]],
    }


def detalhe(customer_id: str, *, login_customer_id: str) -> Dict[str, Any]:
    """Os campos da conta que mudam o payload. Somente leitura.

    `auto_tagging_enabled` é o que decide se `marcacao_gclid` pode ser `True` —
    hoje o brief declara esse booleano em vez de lê-lo.
    """
    from volc_ads.gads.client import buscar

    linhas = list(buscar(str(customer_id), GAQL_CONTA,
                         login_customer_id=str(login_customer_id)))
    if not linhas:
        return {}
    c = linhas[0].customer
    return {
        "customer_id": str(c.id),
        "nome": _texto(c.descriptive_name),
        "moeda": _texto(c.currency_code),
        "fuso": _texto(c.time_zone),
        # ⚠️ Consumido por `marcacao.validar()`: com auto-tagging LIGADO, o
        # Google já anexa o gclid e declarar a macro duplica o parâmetro.
        "auto_tagging": bool(c.auto_tagging_enabled),
        "manager": bool(c.manager),
        "teste": bool(c.test_account),
    }


def acessiveis() -> List[str]:
    """Os customer ids que a credencial alcança — só os ids, sem nome.

    `ListAccessibleCustomers` não aceita filtro nem devolve hierarquia: é a
    porta de entrada, não o mapa. O mapa é `descobrir()`, por MCC.

    ⚠️ Ele devolve `customers/1234567890`, não o número. Passar o resource name
    onde a API espera o id produz erro de id inválido — que diz o que está
    errado, mas não que a causa foi o prefixo.
    """
    from google.ads.googleads.client import GoogleAdsClient

    from volc_ads.gads.client import VERSAO_API

    # Sem `login_customer_id`: esta chamada é sobre a CREDENCIAL, não sobre um
    # manager. Fixar um MCC aqui esconderia todo o resto que ela alcança.
    c = GoogleAdsClient.load_from_storage(version=VERSAO_API)
    resp = c.get_service("CustomerService").list_accessible_customers()
    return [rn.rsplit("/", 1)[-1] for rn in resp.resource_names]


# A meta que a campanha VAI usar. Não é telemetria: é o que o
# `maximize_conversions` de `campanha/comum.py` otimiza.
GAQL_METAS = """
    SELECT
      conversion_action.id,
      conversion_action.name,
      conversion_action.category,
      conversion_action.type,
      conversion_action.primary_for_goal,
      conversion_action.status
    FROM conversion_action
    WHERE conversion_action.status = 'ENABLED'
"""


def meta_de_conversao(customer_id: str, *, login_customer_id: str) -> Dict[str, Any]:
    """Para que a campanha vai otimizar. Somente leitura.

    ## Por que isto precisa estar na tela

    `campanha/comum.py` cria toda campanha Search em `maximize_conversions`. O
    que ela persegue NÃO é escolhido pelo cockpit — é a ação primária da CONTA.
    Medido em 18/08/2026 na Crédito Up: `adViewInterstitial`, categoria
    PURCHASE, que é o evento de receita da arbitragem. O desenho está certo.

    ⚠️ O QUE ESTÁ ERRADO É O CAMPO `conversao` DO BRIEF.

    Ele existe em `campanha/brief.py`, viaja da rota `/provar` e **ninguém o
    lê**: zero referências em `search.py`, `comum.py` e `subir.py`. Escolher
    outra meta por campanha é impossível hoje, e o campo promete que dá. Até
    isso ser ligado (ou removido), a tela mostra a meta REAL — a da conta — em
    vez de deixar o operador achar que escolheu alguma coisa.

    Conta sem ação primária devolve `primaria: None`, e aí a campanha nasce
    otimizando para nada: é o pior desfecho possível e ele precisa ser visível
    ANTES do lançamento, não depois do orçamento gasto.
    """
    from volc_ads.gads.client import buscar

    acoes: List[Dict[str, Any]] = []
    for l in buscar(str(customer_id), GAQL_METAS,
                    login_customer_id=str(login_customer_id)):
        a = l.conversion_action
        acoes.append({
            "id": str(a.id),
            "nome": _texto(a.name),
            "categoria": a.category.name,
            "tipo": a.type_.name,
            "primaria": bool(a.primary_for_goal),
        })

    primaria = next((a for a in acoes if a["primaria"]), None)
    return {
        "acoes": acoes,
        "primaria": primaria,
        "por_que": (
            "A campanha nasce em `maximize_conversions` e persegue a ação "
            "PRIMÁRIA da conta. O cockpit não escolhe meta — o campo que "
            "prometia isso não é lido por ninguém."
        ) if primaria else (
            "⚠️ Esta conta não tem ação de conversão primária. Uma campanha em "
            "`maximize_conversions` sem meta otimiza para nada e gasta o "
            "orçamento sem sinal."
        ),
    }
