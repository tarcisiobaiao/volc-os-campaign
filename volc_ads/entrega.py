"""Campanha ligada que não gasta — e o que a própria conta diz sobre isso.

## Por que este módulo existe

Medido em 20/08/2026, nas duas campanhas vivas da conta `8017851692`:

    Maquininha (ENABLED há 7 dias) · 1 impressão · 0 cliques · R$ 0,00
    FGTS       (ENABLED há 26 min) · 0 impressão · 0 cliques · R$ 0,00

Nenhuma tela dizia isso. O operador via "ENABLED" no painel, achava que estava
veiculando, e o orçamento ficava parado sem ninguém perceber. Descobrir custou
uma investigação manual de sete consultas GAQL.

## ⚠️ O QUE ELE NÃO FAZ, E É AQUI QUE MORA A DECISÃO

**Não diz qual deveria ser o lance.** A tentação era comparar o lance com o CPC
que o cluster do Pautador traz do DataForSEO — na maquininha isso daria
"R$ 0,12 contra mediana de R$ 10,54", que soa devastador e é exatamente o tipo
de número que não se deve pôr num alerta: é estimativa de TERCEIRO, infla, e no
dia em que estiver errada o alerta vira ruído e o operador para de confiar em
todos os outros.

O que ele mostra são fatos da conta — lance, orçamento, impressões, o texto do
próprio Google — e uma ordem de revisão. Quem decide o número é o operador,
olhando o leilão real.

A única conta feita aqui é `orçamento ÷ lance = teto de cliques/dia`, que é
divisão de dois fatos da conta, sem estimativa de ninguém.

**Não escreve nada.** É `search()`, como `forca.py`. Sem `destravar()`, sem
`FORGE_PERMITIR_ESCRITA`.

**Não guarda estado.** Não há tabela de alertas, nem "lido/não lido". O
diagnóstico é recalculado quando alguém abre a tela, e some sozinho quando a
causa some — um alerta que só existe enquanto é verdade não tem como envelhecer
mentindo.

## O silêncio é uma resposta

Quando não dá para saber há quantas horas a campanha está ligada — o
`change_event` só cobre 14 dias — este módulo **não alerta**. Alerta errado é
pior que alerta nenhum: o primeiro que aparecer sem motivo ensina o operador a
ignorar o sino.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .gads.client import cliente

#: Horas ligada sem gastar até o alerta aparecer.
#:
#: ⚠️ NÃO É NÚMERO MEDIDO — é escolha de operação, e está declarada como tal.
#: 24 h cobre a janela em que o Google ainda revisa e distribui, sem deixar a
#: campanha parada um fim de semana inteiro. Quem quiser outro valor muda aqui
#: sabendo que não está contrariando medição nenhuma.
HORAS_ATE_ALERTAR = 24

#: Sintomas. Pedem olhares OPOSTOS, por isso não são um só.
SEM_IMPRESSAO = "sem_impressao"      # não entrou no leilão de forma relevante
SEM_CLIQUE = "sem_clique"            # entrou o bastante e ninguém clicou

#: Quantas impressões são precisas antes de a culpa poder ser DO ANÚNCIO.
#:
#: ⚠️ PEGO NA PRÓPRIA CONTA, EM 20/08/2026. A primeira versão separava os dois
#: sintomas em `impressoes > 0`, e a maquininha — com UMA impressão em 24 horas
#: — recebia "entrou no leilão e ninguém clicou: revise o texto do anúncio".
#:
#: Uma impressão não diz nada sobre CTR. Mandar reescrever o anúncio por causa
#: dela é conselho errado com cara de diagnóstico, e o operador gastaria uma
#: cascata de copy para consertar algo que não é o problema — o problema é que
#: ela quase não entra no leilão.
#:
#: NÃO É NÚMERO MEDIDO, é escolha de operação, como `HORAS_ATE_ALERTAR`. 100 é
#: onde zero clique começa a ser informação em vez de acaso. Quem mudar precisa
#: saber que não está contrariando medição nenhuma.
IMPRESSOES_PARA_CULPAR_O_ANUNCIO = 100


@dataclass(frozen=True)
class Alteracao:
    """Quem mexeu, no quê, quando e por onde.

    ⚠️ É o campo mais útil deste módulo e não existe em painel nenhum. Em
    20/08/2026 ele resolveu em dez segundos uma contradição que eu levaria
    horas para explicar: o motor subiu a campanha com lance R$ 1,00 às 22:26 e
    o lance estava R$ 0,12 na manhã seguinte. `change_event` mostrou a
    alteração no painel às 22:39, feita por um humano.
    """

    quando: str
    campo: str
    de: str
    para: str
    origem: str          # GOOGLE_ADS_WEB_CLIENT, GOOGLE_ADS_API, ...
    quem: str = ""

    def resumo(self) -> str:
        onde = "no painel" if "WEB" in self.origem else "pela API"
        return f"{self.campo} {self.de} → {self.para}, {onde}, {self.quando}"


@dataclass(frozen=True)
class Diagnostico:
    """O que a conta diz sobre UMA campanha. Fatos, e nada derivado deles."""

    campaign_id: str
    campaign_name: str
    status: str
    #: `None` quando não deu para saber — e aí `alerta` é sempre False.
    horas_ligada: float | None = None
    impressoes: int = 0
    cliques: int = 0
    custo: float = 0.0
    lance: float | None = None
    orcamento: float | None = None
    #: O que o Google diz, no texto dele. Vazio = nenhuma observação.
    razoes: tuple[str, ...] = ()
    aprovacao_do_anuncio: str = ""
    veiculacao: str = ""
    alteracoes: tuple[Alteracao, ...] = field(default_factory=tuple)

    @property
    def gastou(self) -> bool:
        return self.custo > 0

    @property
    def alerta(self) -> bool:
        """Ligada há ≥ `HORAS_ATE_ALERTAR` e não gastou um centavo."""
        if self.status != "ENABLED" or self.gastou:
            return False
        if self.horas_ligada is None:
            return False        # ver "O silêncio é uma resposta", no topo
        return self.horas_ligada >= HORAS_ATE_ALERTAR

    @property
    def sintoma(self) -> str:
        """⚠️ O corte não é `> 0` — ver `IMPRESSOES_PARA_CULPAR_O_ANUNCIO`.

        Uma impressão em 24 horas é "não entra no leilão", não "o texto está
        ruim". Foi assim que a maquininha recebeu o conselho errado.
        """
        return (SEM_CLIQUE if self.impressoes >= IMPRESSOES_PARA_CULPAR_O_ANUNCIO
                else SEM_IMPRESSAO)

    @property
    def teto_de_cliques(self) -> int | None:
        """Orçamento ÷ lance. Divisão de dois fatos, sem estimativa de ninguém.

        É a única conta deste módulo, e existe porque responde sozinha uma
        pergunta que o operador faria: "com esse lance, quantos cliques cabem
        no meu dia?". Um teto de 1 ou 2 é sinal de que orçamento e lance não
        conversam — e aí quem decide o que mudar é ele.
        """
        if not self.lance or not self.orcamento:
            return None
        return int(self.orcamento / self.lance)

    def revisar(self) -> tuple[str, ...]:
        """A ordem de revisão. Didática, e sem apontar valor.

        Primeiro o que o Google diz, porque quando ele diz algo é sempre a
        causa. Depois o lance, porque é o que muda com mais frequência e sem
        aviso. Por último o orçamento, que raramente é a causa de gasto ZERO —
        orçamento pequeno gasta pouco, não gasta nada.
        """
        ordem = ["o que o Google está dizendo"]
        if self.sintoma == SEM_IMPRESSAO:
            ordem += ["o lance do grupo", "o orçamento diário"]
        else:
            ordem += ["o texto do anúncio", "a página de destino"]
        return tuple(ordem)


_CAMPANHA = """
SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status,
       campaign.primary_status, campaign.primary_status_reasons,
       campaign_budget.amount_micros
FROM campaign WHERE campaign.id IN ({ids})
"""

# ⚠️ Sem lista de ids, a fonte é a CONTA e não a nossa tabela. Ver a docstring
# de `verificar`: `campaigns` tem dois donos, `customer_id` vazio e linhas
# faltando. `ENABLED` porque só campanha ligada pode gastar.
_CAMPANHA_LIGADAS = """
SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status,
       campaign.primary_status, campaign.primary_status_reasons,
       campaign_budget.amount_micros
FROM campaign WHERE campaign.status = 'ENABLED'
"""

_GRUPO = """
SELECT campaign.id, ad_group.cpc_bid_micros
FROM ad_group WHERE campaign.id IN ({ids}) AND ad_group.status != 'REMOVED'
"""

_ANUNCIO = """
SELECT campaign.id, ad_group_ad.policy_summary.approval_status
FROM ad_group_ad WHERE campaign.id IN ({ids}) AND ad_group_ad.status != 'REMOVED'
"""

# ⚠️ MÉTRICA PRECISA DE JANELA, e a janela precisa ser MAIOR que o gatilho.
# Sem `segments.date` a API devolve o período padrão da conta; com uma janela
# menor que `HORAS_ATE_ALERTAR` daria para alertar uma campanha que gastou
# ontem e não hoje — o alerta diria "nunca gastou" sobre algo que gastou.
_METRICAS = """
SELECT campaign.id, metrics.impressions, metrics.clicks, metrics.cost_micros
FROM campaign WHERE campaign.id IN ({ids}) AND segments.date DURING LAST_30_DAYS
"""

_MUDANCAS = """
SELECT change_event.change_date_time, change_event.change_resource_type,
       change_event.client_type, change_event.user_email,
       change_event.changed_fields, change_event.old_resource,
       change_event.new_resource, change_event.campaign
FROM change_event
WHERE change_event.change_date_time DURING LAST_14_DAYS
  AND change_event.campaign IN ({recursos})
ORDER BY change_event.change_date_time DESC
LIMIT 200
"""

#: Só estes interessam. `changed_fields` traz de tudo — nome, sufixo de URL,
#: rede — e uma lista de vinte alterações irrelevantes enterra a que importa.
CAMPOS_QUE_IMPORTAM = ("cpc_bid_micros", "amount_micros", "status")


def verificar(customer_id: str, campaign_ids: list[str] | None = None, *,
              login_customer_id: str, servico: Any = None,
              agora: datetime | None = None) -> tuple[Diagnostico, ...]:
    """Diagnostica as campanhas de UMA conta. Leitura pura.

    Várias de uma vez, e não uma por chamada, porque a tela mostra a conta
    inteira: cinco consultas para N campanhas em vez de cinco por campanha.

    ## ⚠️ `campaign_ids=None` PERGUNTA À CONTA, e é o caminho normal

    A primeira versão desta rota lia os ids da nossa tabela `campaigns`. Medido
    em 20/08/2026, e ela não serve como fonte:

      · `customer_id` VAZIO nas quatro linhas — sem conta, não há o que consultar;
      · as campanhas subidas na véspera NÃO estavam lá;
      · `status_source` dizia `auto`, ou seja, outro produtor (o fluxo n8n)
        escreve na mesma tabela e sobrescreve o que o `/subir` grava.

    Uma tabela com dois donos é cache, não verdade. O alerta que dependesse
    dela ficaria em silêncio exatamente quando mais importa — e silêncio de
    alerta quebrado é indistinguível de "está tudo bem".

    A conta do Google sabe quais campanhas existem e em que estado. Perguntar a
    ela custa uma consulta e nunca fica desatualizado.

    `servico` e `agora` existem para o teste injetar dublê e relógio — a
    consulta é a parte que não dá para provar sem rede, e a DECISÃO em cima
    dela é a que importa.
    """
    svc = servico or cliente(login_customer_id).get_service("GoogleAdsService")
    cid = str(customer_id)
    ids = [str(c) for c in (campaign_ids or []) if str(c or "").strip()]

    def buscar(gaql: str, **fmt: Any) -> list[Any]:
        try:
            return list(svc.search(customer_id=cid, query=gaql.format(**fmt)))
        except Exception:  # noqa: BLE001 — uma consulta a menos degrada, não derruba
            return []

    base: dict[str, dict[str, Any]] = {}
    # Sem lista, pergunta à conta quais estão LIGADAS: só elas podem gastar, e
    # só elas interessam a um alerta de "ligada e não gasta".
    primeira = (_CAMPANHA.format(ids=",".join(ids)) if ids
                else _CAMPANHA_LIGADAS)
    for row in buscar(primeira):
        c = row.campaign
        base[str(c.id)] = {
            "nome": str(c.name),
            "status": _nome(c.status),
            "veiculacao": _nome(getattr(c, "serving_status", None)),
            "razoes": tuple(_nome(r) for r in (c.primary_status_reasons or ())),
            "orcamento": _reais(getattr(row.campaign_budget, "amount_micros", 0)),
        }

    # As demais consultas usam os ids QUE VIERAM, não os que foram pedidos: sem
    # campanha na conta não há o que perguntar, e `IN ()` é erro de sintaxe.
    if not base:
        return ()
    lista = ",".join(base)

    for row in buscar(_GRUPO, ids=lista):
        d = base.get(str(row.campaign.id))
        if d is not None and d.get("lance") is None:
            d["lance"] = _reais(row.ad_group.cpc_bid_micros)

    for row in buscar(_ANUNCIO, ids=lista):
        d = base.get(str(row.campaign.id))
        if d is not None and not d.get("aprovacao"):
            d["aprovacao"] = _nome(row.ad_group_ad.policy_summary.approval_status)

    # ⚠️ Métrica vem SEGMENTADA POR DIA: a mesma campanha aparece N vezes e os
    # valores são do dia, não do período. Ler a última linha daria o último dia
    # e chamaria de "nunca gastou" uma campanha que gastou na segunda-feira.
    for row in buscar(_METRICAS, ids=lista):
        d = base.get(str(row.campaign.id))
        if d is None:
            continue
        d["impressoes"] = d.get("impressoes", 0) + int(row.metrics.impressions or 0)
        d["cliques"] = d.get("cliques", 0) + int(row.metrics.clicks or 0)
        d["custo"] = d.get("custo", 0.0) + _reais(row.metrics.cost_micros)

    recursos = ",".join(f"'customers/{cid}/campaigns/{i}'" for i in base)
    for row in buscar(_MUDANCAS, recursos=recursos):
        alvo = str(row.change_event.campaign).rsplit("/", 1)[-1]
        d = base.get(alvo)
        if d is None:
            continue
        d.setdefault("alteracoes", []).extend(_ler_mudanca(row.change_event))
        if _ligou(row.change_event):
            d["ligada_em"] = str(row.change_event.change_date_time)

    quando = agora or datetime.now(timezone.utc)
    saida = []
    for cid_camp, d in base.items():
        saida.append(Diagnostico(
            campaign_id=cid_camp,
            campaign_name=d.get("nome", ""),
            status=d.get("status", ""),
            horas_ligada=_horas(d.get("ligada_em"), quando),
            impressoes=d.get("impressoes", 0),
            cliques=d.get("cliques", 0),
            custo=d.get("custo", 0.0),
            lance=d.get("lance"),
            orcamento=d.get("orcamento"),
            razoes=d.get("razoes", ()),
            aprovacao_do_anuncio=d.get("aprovacao", ""),
            veiculacao=d.get("veiculacao", ""),
            alteracoes=tuple(d.get("alteracoes", []))[:5],
        ))
    return tuple(saida)


def _ler_mudanca(ev: Any) -> list[Alteracao]:
    """Uma `Alteracao` por campo que importa. Ignora o resto em silêncio."""
    caminhos = list(getattr(getattr(ev, "changed_fields", None), "paths", ()) or ())
    fora: list[Alteracao] = []
    for caminho in caminhos:
        campo = caminho.rsplit(".", 1)[-1]
        if campo not in CAMPOS_QUE_IMPORTAM:
            continue
        de, para = _valores(ev, caminho, _recurso(ev))
        if de is None and para is None:
            continue
        fora.append(Alteracao(
            quando=str(ev.change_date_time)[:16],
            campo=_rotulo(campo),
            de=de or "?", para=para or "?",
            origem=_nome(getattr(ev, "client_type", None)),
            quem=str(getattr(ev, "user_email", "") or ""),
        ))
    return fora


_ROTULOS = {"cpc_bid_micros": "lance", "amount_micros": "orçamento",
            "status": "status"}


def _rotulo(campo: str) -> str:
    return _ROTULOS.get(campo, campo)


def _recurso(ev: Any) -> str:
    """`AD_GROUP` → `ad_group`: onde o valor mora dentro de `old/new_resource`.

    ⚠️ `changed_fields.paths` é RELATIVO ao recurso. Numa alteração de grupo o
    caminho é `cpc_bid_micros`, mas o valor está em
    `old_resource.ad_group.cpc_bid_micros`. Ler direto do `old_resource`
    devolve `None`, e a alteração — que é o dado mais útil deste módulo —
    desaparece em silêncio.
    """
    return _nome(getattr(ev, "change_resource_type", None)).lower()


def _valores(ev: Any, caminho: str, recurso: str = "") -> tuple[str | None, str | None]:
    """O antes e o depois, já em reais quando o campo é dinheiro."""
    def ler(raiz: Any) -> str | None:
        alvo = getattr(raiz, recurso, None) if recurso else raiz
        if alvo is None:
            alvo = raiz             # dublês e recursos sem invólucro
        for parte in caminho.split("."):
            alvo = getattr(alvo, parte, None)
            if alvo is None:
                return None
        if caminho.endswith("micros"):
            return f"R$ {_reais(alvo):.2f}"
        return _nome(alvo) or str(alvo)

    return ler(getattr(ev, "old_resource", None)), ler(getattr(ev, "new_resource", None))


def _ligou(ev: Any) -> bool:
    """Esta alteração é a que ligou a campanha?

    ⚠️ Só serve `CAMPAIGN` — o `status` de grupo e de anúncio também aparece em
    `changed_fields`, e contar um deles daria "ligada há 3 h" para uma campanha
    que roda há semanas.
    """
    if _nome(getattr(ev, "change_resource_type", None)) != "CAMPAIGN":
        return False
    caminhos = list(getattr(getattr(ev, "changed_fields", None), "paths", ()) or ())
    if "status" not in caminhos:
        return False
    novo = getattr(getattr(ev, "new_resource", None), "campaign", None)
    return _nome(getattr(novo, "status", None)) == "ENABLED"


def _horas(quando: str | None, agora: datetime) -> float | None:
    if not quando:
        return None
    try:
        t = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        # `change_event` devolve no fuso da CONTA, sem offset. Tratar como UTC
        # erra por horas, mas erra sempre para MENOS (Brasil é UTC-3), então o
        # alerta atrasa em vez de disparar cedo. Atrasar é o lado seguro.
        t = t.replace(tzinfo=timezone.utc)
    return max(0.0, (agora - t).total_seconds() / 3600.0)


def _reais(micros: Any) -> float:
    try:
        return int(micros or 0) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


def _nome(v: Any) -> str:
    return getattr(v, "name", None) or (str(v) if v is not None else "")


def alertar(diagnosticos: tuple[Diagnostico, ...]) -> tuple[Diagnostico, ...]:
    """Só os que precisam de olho. É o que o sino conta."""
    return tuple(d for d in diagnosticos if d.alerta)
