"""Reler na conta o que nasceu — por canal, com objetos próprios e sete estados.

## O que este módulo é, e o que ele não é

Ele é o READ-BACK PÓS-CRIAÇÃO: depois do mutate, o que existe na conta bate com
o que o plano descrevia? É irmão — e não substituto — do PERFIL DE VARREDURA
(`adaptador_*.py`), que alimenta o inventário contínuo. Os dois leem a mesma
conta e respondem perguntas diferentes: a varredura pergunta "o que existe?", o
read-back pergunta "o que existe é o que eu criei?".

⚠️ **Ele nunca reenvia criação.** Não há aqui função que mute, crie ou repita um
mutate — em nenhum desfecho, nem mesmo em `AUSENCIA_PROVADA`. Uma releitura que
dispara criação transforma uma resposta perdida em duas campanhas.

⚠️ **Divergência nunca vira sucesso.** `VereditoDaReleitura.sucesso` é `True`
somente em `CONGRUENTE`, e `bloqueia` é `True` em `DIVERGENTE`.

## Objetos por canal — e por que PMax não pode reusar os de Display

    SEARCH / DISPLAY / DEMAND_GEN   campanha · grupo · anúncio
    PERFORMANCE_MAX                 campanha · asset_group

PMax não tem `AdGroup` nem `Ad`. Perguntar por eles não devolve pouco: devolve
VAZIO, sempre — e vazio lido como ausência foi um defeito real, o mesmo que a
autoridade de URL do canário já corrigiu. Aqui a resposta para "qual o anúncio
de PMax?" é `NAO_SUPORTADO`, que é um estado, e não uma ausência.

## Identidade

PMax usa a identidade do LEDGER — `volc_campaign_id(conta, campaign_id)` — e
carrega o asset group como FATO do veredito (`objeto="asset_group"`,
`id_externo=<asset_group.id>`). Não há segunda derivação de identidade: inventar
um `sha256` novo para o asset group foi exatamente o defeito que
`ledger.volc_campaign_id_de` documenta.

Somente leitura: cada consulta é `SELECT`, e nenhuma delas constrói operação.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from app.trafego.veredito_de_releitura import (
    ASSET_GROUP,
    ANUNCIO,
    CAMPANHA,
    GRUPO,
    EstadoDaReleitura,
    VereditoDaReleitura,
    TETO_DE_LINHAS,
)

log = logging.getLogger("volc.trafego.releitura")

#: Teto de LINHAS por consulta de releitura. Mesmo vocabulário e mesma razão de
#: `canario.TETO_DE_LINHAS_DE_DESTINO`: o iterador do `search` devolve REGISTROS,
#: e o tamanho da página é decidido pelo servidor do Google. Bater no teto vira
#: `LEITURA_PARCIAL` — nunca uma lista parcial devolvida como se fosse completa.
TETO_DE_LINHAS_DA_RELEITURA = 10_000

#: Os objetos que cada canal tem. ⚠️ Declarado, e não deduzido: é isto que
#: permite responder `NAO_SUPORTADO` em vez de `AUSENCIA_PROVADA` para uma
#: entidade que o canal não possui.
OBJETOS_POR_CANAL: Mapping[str, Tuple[str, ...]] = {
    "SEARCH": (CAMPANHA, GRUPO, ANUNCIO),
    "DISPLAY": (CAMPANHA, GRUPO, ANUNCIO),
    "DEMAND_GEN": (CAMPANHA, GRUPO, ANUNCIO),
    "PERFORMANCE_MAX": (CAMPANHA, ASSET_GROUP),
}

GAQL_CAMPANHA = (
    "SELECT campaign.id, campaign.name, campaign.status, "
    "campaign.advertising_channel_type, campaign.bidding_strategy_type "
    "FROM campaign WHERE {onde}")

GAQL_GRUPO = (
    "SELECT campaign.id, ad_group.id, ad_group.status "
    "FROM ad_group WHERE campaign.id = {kid} AND ad_group.status != 'REMOVED'")

GAQL_ANUNCIO = (
    "SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.status, "
    "ad_group_ad.ad.final_urls "
    "FROM ad_group_ad WHERE campaign.id = {kid} "
    "AND ad_group_ad.status != 'REMOVED'")

GAQL_ASSET_GROUP = (
    "SELECT campaign.id, asset_group.id, asset_group.status, "
    "asset_group.final_urls, asset_group.final_mobile_urls "
    "FROM asset_group WHERE campaign.id = {kid} "
    "AND asset_group.status != 'REMOVED'")

#: O estado em que a CAMPANHA nasce. Este é o contrato que não se negocia:
#: `campanha/comum.py` faz `camp.status = PAUSED` para os quatro canais, e é a
#: campanha pausada que garante que nada veicule sem decisão humana.
NASCE_PAUSADO = "PAUSED"

#: O estado em que cada FILHO nasce — por canal, porque os builders divergem.
#:
#: ⚠️ O comentário anterior dizia "TODO objeto criado por esta casa nasce
#: PAUSED. Nenhum canal foge", e isso era FALSO para Search: `comum.op_adgroup`
#: tem `status: str = "ENABLED"` como default e `search.py` chama sem passar
#: status; `search.py` também liga o `AdGroupAd`. A própria docstring de
#: `op_adgroup` diz por quê — "Search nasce assim desde sempre: o grupo ligado
#: dentro de uma campanha PAUSED, que não veicula".
#:
#: A regra de bloqueio foi escrita sobre a premissa errada, e o efeito foi
#: medido: uma campanha Search recém-criada pelos builders desta casa, correta e
#: nunca ativada, saía DIVERGENTE e `/reconciliar` devolvia 409 — em 100% dos
#: lançamentos do único canal com criação autorizada. Achado da revisão
#: adversarial de 06/09/2026, reproduzido.
#:
#: ⚠️ DECLARADO, e não deduzido, pelo mesmo motivo de `OBJETOS_POR_CANAL`: o
#: backend não pode importar `volc_ads/campanha/*` (eles arrastam o SDK do
#: Google). A coerência com os builders é cobrada por ÁRVORE SINTÁTICA em
#: `test_trafego_readback_por_canal.py`, que é o padrão já usado neste repo.
NASCE_COM_STATUS: Mapping[str, Mapping[str, str]] = {
    # comum.op_adgroup default ENABLED · search.py `ada.status = ENABLED`
    "SEARCH": {GRUPO: "ENABLED", ANUNCIO: "ENABLED"},
    # display.py pede `status="PAUSED"` no grupo e no anúncio
    "DISPLAY": {GRUPO: NASCE_PAUSADO, ANUNCIO: NASCE_PAUSADO},
    # demand_gen.py idem, nas duas pernas
    "DEMAND_GEN": {GRUPO: NASCE_PAUSADO, ANUNCIO: NASCE_PAUSADO},
    # pmax.py `ag.status = AssetGroupStatusEnum.PAUSED`
    "PERFORMANCE_MAX": {ASSET_GROUP: NASCE_PAUSADO},
}

#: Quantos filhos o plano exige de uma campanha que ESTÁ criada.
#:
#: ⚠️ Um é o mínimo que veicula: campanha sem grupo, grupo sem anúncio, ou PMax
#: sem asset group não entregam impressão nenhuma. Sem esta declaração, "o plano
#: pedia um grupo e a conta tem zero" era estruturalmente indetectável — não
#: havia campo contra o que divergir —, e uma campanha OCA saía
#: `ausencia_provada` com `bloqueia=False`, que a rota carimbava como
#: reconciliada. Achado da revisão adversarial de 06/09/2026, reproduzido até o
#: ledger.
#:
#: ⚠️ Ele só é cobrado onde a campanha-mãe JÁ FOI RESOLVIDA: a guarda de
#: `reler_na_conta` devolve `NAO_SUPORTADO` antes disso, e "não sei" nunca vira
#: exigência.
MINIMO_DE_FILHOS_DE_CAMPANHA_CRIADA = 1


def canonizar(canal: Any) -> str:
    bruto = str(canal or "").strip().upper()
    return "PERFORMANCE_MAX" if bruto == "PMAX" else bruto


def objetos_de(canal: Any) -> Tuple[str, ...]:
    return OBJETOS_POR_CANAL.get(canonizar(canal), ())


def _linhas(buscar: Callable[[str], Iterable[Any]], consulta: str
            ) -> Tuple[list, Optional[str]]:
    """Materializa a consulta com teto. Devolve `(linhas, teto_atingido)`.

    ⚠️ O teto devolve o que leu MAIS a marca de que não terminou. Devolver só a
    lista faria a leitura truncada ficar indistinguível de uma completa — que é
    a confusão que libera a segunda campanha.
    """
    colhidas: list = []
    for linha in buscar(consulta):
        colhidas.append(linha)
        if len(colhidas) > TETO_DE_LINHAS_DA_RELEITURA:
            return colhidas, TETO_DE_LINHAS
    return colhidas, None


def _nome_do_enum(valor: Any) -> str:
    return str(getattr(valor, "name", valor) or "")


def _veredito_de_campanha(canal: str, linhas: list, teto: Optional[str],
                          esperado: Mapping[str, Any], consulta: str
                          ) -> VereditoDaReleitura:
    base = dict(canal=canal, objeto=CAMPANHA, esperado=dict(esperado),
                consulta=consulta, procedencia="GoogleAdsService.search (GAQL)")
    if teto is not None:
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.LEITURA_PARCIAL,
            quantidade=len(linhas), teto_atingido=teto,
            causa=(f"a leitura passou do teto de {TETO_DE_LINHAS_DA_RELEITURA} "
                   "LINHAS sem terminar. Isto NÃO prova que a campanha não "
                   "existe — a parte não lida da conta pode contê-la."))
    if not linhas:
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.AUSENCIA_PROVADA, quantidade=0)
    if len(linhas) > 1:
        ids = ", ".join(sorted(str(l.campaign.id) for l in linhas))
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.AMBIGUO, quantidade=len(linhas),
            causa=(f"a leitura encontrou {len(linhas)} campanhas para a mesma "
                   f"identidade ({ids}). Duas campanhas com a mesma marca é "
                   "duplicidade consumada: decisão humana, e nunca uma "
                   "repetição automática."))

    c = linhas[0].campaign
    lido = {
        "campaign_id": str(c.id),
        "nome": str(getattr(c, "name", "") or ""),
        "status": _nome_do_enum(getattr(c, "status", "")),
        "canal": _nome_do_enum(getattr(c, "advertising_channel_type", "")),
        "estrategia_lance": _nome_do_enum(
            getattr(c, "bidding_strategy_type", "")),
    }
    divergentes = _comparar(esperado, lido)
    if divergentes:
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.DIVERGENTE, quantidade=1,
            id_externo=lido["campaign_id"], lido=lido,
            campos_divergentes=divergentes)
    return VereditoDaReleitura(
        **base, estado=EstadoDaReleitura.CONGRUENTE, quantidade=1,
        id_externo=lido["campaign_id"], lido=lido)


def _comparar(esperado: Mapping[str, Any], lido: Mapping[str, Any]
              ) -> Tuple[str, ...]:
    """Os campos em que o plano e a conta discordam.

    ⚠️ Compara SÓ o que o esperado declara. Um campo que o plano não descreve
    não pode divergir dele — e listar tudo faria toda releitura ser divergente
    por causa de campos que a conta preenche sozinha.
    """
    fora = []
    for chave, valor in (esperado or {}).items():
        if chave not in lido:
            continue
        if str(lido[chave]) != str(valor):
            fora.append(chave)
    return tuple(sorted(fora))


def _veredito_de_filho(canal: str, objeto: str, linhas: list,
                       teto: Optional[str], consulta: str,
                       esperado: Mapping[str, Any],
                       ident: Callable[[Any], str],
                       estado_de: Callable[[Any], str],
                       minimo: int,
                       ) -> VereditoDaReleitura:
    """O veredito de UM filho. ⚠️ Só é chamado com a campanha-mãe RESOLVIDA.

    `minimo` é OBRIGATÓRIO e não tem default. Com default, um chamador futuro
    que esquecesse de declarar a cardinalidade voltaria em silêncio ao neutro
    que este parâmetro existe para eliminar; sem default, o esquecimento é um
    `TypeError` na primeira chamada.
    """
    base = dict(canal=canal, objeto=objeto, esperado=dict(esperado),
                consulta=consulta, procedencia="GoogleAdsService.search (GAQL)")
    if teto is not None:
        # ⚠️ ANTES DE TUDO: leitura truncada não prova ausência nem divergência.
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.LEITURA_PARCIAL,
            quantidade=len(linhas), teto_atingido=teto,
            causa=(f"a leitura de {objeto} passou do teto de "
                   f"{TETO_DE_LINHAS_DA_RELEITURA} LINHAS sem terminar. Isto "
                   "NÃO prova ausência."))
    if not linhas:
        if minimo <= 0:
            return VereditoDaReleitura(
                **base, estado=EstadoDaReleitura.AUSENCIA_PROVADA,
                quantidade=0)
        # ⚠️ AQUI A CAMPANHA-MÃE EXISTE — `reler_na_conta` já devolveu
        # `NAO_SUPORTADO` em todo caso em que ela não foi resolvida. Campanha
        # criada e sem filho não é "conta limpa": é campanha OCA, que não
        # veicula e não é o que o plano descreve. Isso é DIVERGÊNCIA
        # ESTRUTURAL, e divergência bloqueia.
        #
        # ⚠️ E não autoriza reenvio: o próximo ato de DIVERGENTE manda abrir a
        # campanha e comparar, `reenvio_por_readback` continua `False`, e este
        # módulo não tem caminho de escrita nenhum.
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.DIVERGENTE, quantidade=0,
            lido={"quantidade": 0}, campos_divergentes=("quantidade",),
            causa=(f"a campanha existe na conta e o plano pedia ao menos "
                   f"{minimo} {objeto}; a leitura terminou, foi completa e "
                   f"encontrou zero. Campanha sem {objeto} não veicula — isto "
                   "não é ausência da campanha, é uma criação que ficou pela "
                   "metade."))
    estados = {estado_de(l) for l in linhas}
    # ⚠️ O `esperado` DECIDE, e antes ele era decorativo: a comparação era
    # contra a constante do módulo, então passar `esperado={"status": "ENABLED"}`
    # ainda dava divergente. O default continua sendo `NASCE_PAUSADO`, que é o
    # fail-closed: objeto ou canal que ninguém declarou continua tendo de provar
    # que nasceu pausado.
    alvo = str((esperado or {}).get("status") or NASCE_PAUSADO)
    fora_do_alvo = sorted(e for e in estados if e != alvo)
    lido = {"quantidade": len(linhas), "status": sorted(estados)}
    if fora_do_alvo:
        # ⚠️ NASCER COMO O BUILDER DAQUELE CANAL CRIA É CONTRATO, e um objeto
        # fora disso é DIVERGENTE — não um detalhe de um sucesso.
        return VereditoDaReleitura(
            **base, estado=EstadoDaReleitura.DIVERGENTE,
            quantidade=len(linhas), lido=lido,
            id_externo=ident(linhas[0]),
            campos_divergentes=("status",))
    return VereditoDaReleitura(
        **base, estado=EstadoDaReleitura.CONGRUENTE, quantidade=len(linhas),
        lido=lido, id_externo=ident(linhas[0]))


def reler_na_conta(
    *,
    canal: Any,
    buscar: Callable[[str], Iterable[Any]],
    campaign_id: Optional[str] = None,
    marca: Optional[str] = None,
    esperado: Optional[Mapping[str, Any]] = None,
) -> Tuple[VereditoDaReleitura, ...]:
    """Relê a campanha e seus objetos próprios. **Somente leitura.**

    `buscar(gaql) -> linhas` é injetado: quem chama decide se é o cliente real
    ou um dublê. Este módulo não constrói cliente, não abre trava e não muta.

    ⚠️ Uma FALHA de leitura vira `EstadoDaReleitura.FALHA` no objeto afetado, e
    não uma exceção que apaga os outros vereditos. "Não consegui ler o anúncio"
    e "a campanha não existe" são fatos diferentes, e perder o primeiro por
    causa do segundo é o que faz um recibo fechar como ausência sobre
    ignorância.
    """
    nome = canonizar(canal)
    alvo = dict(esperado or {})
    objetos = objetos_de(nome)
    if not objetos:
        return (VereditoDaReleitura(
            canal=nome or "(canal ausente)", objeto=CAMPANHA,
            estado=EstadoDaReleitura.NAO_SUPORTADO,
            causa=(f"não sei quais objetos {nome or '(canal ausente)'} tem, "
                   "então não sei o que reler nele. Canais conhecidos: "
                   + ", ".join(sorted(OBJETOS_POR_CANAL)) + ".")),)

    kid = str(campaign_id or "").strip()
    marca_limpa = str(marca or "").strip()
    if kid:
        onde = f"campaign.id = {int(kid)}"
    elif marca_limpa:
        onde = f"campaign.name LIKE '{marca_limpa}%'"
    else:
        raise ValueError("reler_na_conta exige `campaign_id` ou `marca`.")

    vereditos: list = []
    consulta = GAQL_CAMPANHA.format(onde=onde)
    try:
        linhas, teto = _linhas(buscar, consulta)
        campanha = _veredito_de_campanha(nome, linhas, teto, alvo, consulta)
    except Exception as exc:  # noqa: BLE001
        campanha = VereditoDaReleitura(
            canal=nome, objeto=CAMPANHA, estado=EstadoDaReleitura.FALHA,
            esperado=alvo, consulta=consulta,
            causa=f"a leitura da campanha falhou ({type(exc).__name__}: "
                  f"{str(exc)[:200]}). Isto NÃO é uma afirmação sobre a conta.")
    vereditos.append(campanha)

    # ⚠️ Sem id de campanha, os filhos não têm por onde ser consultados. Isso é
    # `NAO_SUPORTADO` para ESTA leitura — e não ausência, que afirmaria que os
    # objetos não existem.
    id_da_campanha = campanha.id_externo
    if not id_da_campanha:
        for objeto in objetos[1:]:
            vereditos.append(VereditoDaReleitura(
                canal=nome, objeto=objeto,
                estado=EstadoDaReleitura.NAO_SUPORTADO,
                causa=("a campanha não foi resolvida nesta leitura, então não "
                       f"há id por onde consultar {objeto}. Isto não afirma "
                       "que ele não existe.")))
        return tuple(vereditos)

    for objeto in objetos[1:]:
        # ⚠️ O estado esperado vem do BUILDER daquele canal, e não de uma
        # constante única: Search cria os filhos ENABLED dentro da campanha
        # PAUSED, os outros três criam tudo PAUSED. O default é `NASCE_PAUSADO`,
        # que é o lado fail-closed de um canal ainda não declarado aqui.
        nasce = NASCE_COM_STATUS.get(nome, {}).get(objeto, NASCE_PAUSADO)
        alvo_filho: Mapping[str, Any] = {
            "status": nasce,
            "quantidade_minima": MINIMO_DE_FILHOS_DE_CAMPANHA_CRIADA,
        }
        if objeto == GRUPO:
            consulta = GAQL_GRUPO.format(kid=int(id_da_campanha))
            ident = lambda l: str(l.ad_group.id)  # noqa: E731
            estado = lambda l: _nome_do_enum(l.ad_group.status)  # noqa: E731
        elif objeto == ANUNCIO:
            consulta = GAQL_ANUNCIO.format(kid=int(id_da_campanha))
            ident = lambda l: str(l.ad_group_ad.ad.id)  # noqa: E731
            estado = lambda l: _nome_do_enum(l.ad_group_ad.status)  # noqa: E731
        else:  # ASSET_GROUP
            consulta = GAQL_ASSET_GROUP.format(kid=int(id_da_campanha))
            ident = lambda l: str(l.asset_group.id)  # noqa: E731
            estado = lambda l: _nome_do_enum(l.asset_group.status)  # noqa: E731
        try:
            linhas, teto = _linhas(buscar, consulta)
            vereditos.append(_veredito_de_filho(
                nome, objeto, linhas, teto, consulta, alvo_filho, ident, estado,
                alvo_filho["quantidade_minima"]))
        except Exception as exc:  # noqa: BLE001
            vereditos.append(VereditoDaReleitura(
                canal=nome, objeto=objeto, estado=EstadoDaReleitura.FALHA,
                esperado=dict(alvo_filho), consulta=consulta,
                causa=f"a leitura de {objeto} falhou ({type(exc).__name__}: "
                      f"{str(exc)[:200]}). Isto NÃO prova ausência."))

    return tuple(vereditos)
