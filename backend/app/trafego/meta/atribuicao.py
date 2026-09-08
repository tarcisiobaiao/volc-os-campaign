"""O contrato canônico de atribuição financeira da Meta: CONJUNTO/DIA.

## O defeito que este módulo conserta

Até 07/09/2026 o sistema declarava, em código e em documentação, que

    GAM.utm_campaign_value = Meta campaign_id

e `financeiro.py` filtrava `gam_metrics` por esse igual. A operação real nunca
foi assim. Os anúncios que rodaram carregam

    utm_source={{site_source_name}}
    utm_medium=paid_social
    utm_campaign={{adset.id}}      <-- o CONJUNTO, não a campanha
    utm_term={{adset.id}}
    utm_content={{ad.id}}
    placement={{placement}}

ou seja: a coluna `utm_campaign_value` do GAM guarda um id de CONJUNTO. O join
por `campaign_id` casava zero linhas contra o dado real, e a tela mostrava
receita `—` para sempre — sem errar uma conta, porque não chegava a fazer
nenhuma.

A prova que fechou a questão tem 64 linhas campanha/dia, 62 com receita
atribuída via conjunto e 2 sem UTM de conjunto no GAM (ambas sem entrega):
R$ 1.029,41 de investimento, R$ 1.140,73 de receita, ROAS agregado ~1,108.

## O grão canônico

    account_ref + campaign_id + adset_id + date + metric_scope + metric_version

`metric_scope` existe para tornar IMPOSSÍVEL o erro que este módulo mais teme:
somar uma leitura campaign-level da Meta às leituras adset-level. As duas medem
a MESMA despesa por caminhos diferentes. Somá-las dobra o gasto. Por isso o
escopo entra na identidade da linha e `agregar_campanha_dia` recusa, com nome
próprio, qualquer coleção que misture escopos.

## A regra de soma

    receita da campanha  = SUM(receita dos conjuntos filhos)
    investimento da camp = SUM(investimento dos conjuntos filhos no mesmo grão)

A leitura campaign-level continua útil — para RECONCILIAR. Ela nunca é parcela.

Receita não desce de grão: nada copia a receita do conjunto para cada anúncio ou
criativo. Se um dia existir receita por `ad_id`, ela nasce em grão próprio
(`ESCOPO_ANUNCIO`) e não pode duplicar a que já foi atribuída por conjunto.

## Semântica de ausência (a parte que mais erra em silêncio)

- dado não medido / associação desconhecida ....... `None`
- entrega medida com receita comprovadamente zero .. `Decimal(0)`
- nenhuma URL/UTM disponível ....................... estado explícito
  (`SEM_UTM_ADSET_NO_GAM`), receita `None` — nunca zero inventado
- leitura parcial .................................. `completo=False`; um total
  parcial nunca é apresentado como total completo

Moeda e fuso fazem parte do contrato: linhas de moedas ou fusos diferentes não
somam. Nenhum caminho aqui resolve nada por NOME de campanha ou de conjunto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date as Data
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

#: Versão do contrato de atribuição que produziu a linha.
#:
#: Viaja no grão para que uma mudança futura na forma da atribuição seja
#: DETECTÁVEL em vez de silenciosa: linhas de versões diferentes não se somam.
VERSAO_DA_ATRIBUICAO = "meta-atribuicao-adset-v1"

#: Escopo da medida. Entra na identidade da linha DE PROPÓSITO.
ESCOPO_CONJUNTO = "adset"
ESCOPO_CAMPANHA = "campaign"
ESCOPO_ANUNCIO = "ad"
ESCOPOS_CONHECIDOS = frozenset({ESCOPO_CONJUNTO, ESCOPO_CAMPANHA, ESCOPO_ANUNCIO})

#: Como a receita chegou até esta linha.
METODO_UTM_CAMPAIGN_COM_ADSET_ID = "GAM.utm_campaign_value = adset_id"

#: Estado da associação receita <-> conjunto.
ATRIBUIDO_VIA_ADSET = "FATURAMENTO_ATRIBUIDO_VIA_ADSET"
SEM_UTM_ADSET_NO_GAM = "SEM_UTM_ADSET_NO_GAM"
SEM_LEITURA_GAM = "SEM_LEITURA_GAM"
ESTADOS_DE_MAPEAMENTO = frozenset({
    ATRIBUIDO_VIA_ADSET, SEM_UTM_ADSET_NO_GAM, SEM_LEITURA_GAM,
})

FONTE = "META_ADS"

#: Um id de objeto da Meta é uma sequência de dígitos. Nada mais entra na chave.
#:
#: ⚠️ Esta é a "gramática de id" que o contrato de métrica de 2026 registrou
#: como dívida: sem ela, um `utm_campaign_value` que na verdade é uma URL (a
#: JoinAds já devolveu `land_uri` no lugar de `utm_campaign` em dado real)
#: entraria na chave de atribuição como se fosse identidade de objeto.
_ID_META = re.compile(r"\d{1,40}")


class AtribuicaoMetaInvalida(ValueError):
    """Recusa com nome próprio: a coleção não pode virar total."""

    def __init__(self, codigo: str, detalhe: str) -> None:
        super().__init__(f"{codigo}: {detalhe}")
        self.codigo = codigo
        self.detalhe = detalhe


def id_meta_valido(valor: Any) -> bool:
    """`True` só para um id de objeto da Meta bem formado."""
    return isinstance(valor, str) and bool(_ID_META.fullmatch(valor))


def _decimal(valor: Any) -> Decimal | None:
    """Número finito ou `None`. Booleano NUNCA é número aqui."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except (ArithmeticError, ValueError, TypeError):
        return None
    return numero if numero.is_finite() else None


def _inteiro(valor: Any) -> int | None:
    numero = _decimal(valor)
    if numero is None or numero != numero.to_integral_value():
        return None
    return int(numero)


@dataclass(frozen=True)
class LinhaAtribuicao:
    """Uma linha do grão canônico. Imutável de propósito.

    Os campos de dinheiro são `Decimal | None`. `None` é ausência de medida; ele
    nunca é convertido em zero na travessia até a UI.
    """

    # --- identidade do grão ---------------------------------------------
    account_ref: str
    campaign_id: str
    adset_id: str
    date: Data
    metric_scope: str = ESCOPO_CONJUNTO
    metric_version: str = VERSAO_DA_ATRIBUICAO

    # --- escopo de negócio ----------------------------------------------
    project_id: int | None = None

    # --- medida da Meta ---------------------------------------------------
    spend: Decimal | None = None
    impressions: int | None = None
    clicks: int | None = None
    #: ⚠️ NÃO SOMÁVEL entre linhas: alcance é gente, e a mesma pessoa aparece em
    #: dois dias. Viaja para ser exibido no grão em que foi medido, e
    #: `agregar_*` devolve `None` para ele — não a soma.
    reach: int | None = None

    # --- medida do GAM ----------------------------------------------------
    gam_revenue_original: Decimal | None = None
    gam_revenue_brl: Decimal | None = None
    gam_impressions: int | None = None
    gam_clicks: int | None = None
    #: Câmbio efetivamente aplicado pela fonte, quando declarado. Nunca presumido.
    fx_rate: Decimal | None = None

    # --- procedência -------------------------------------------------------
    attribution_method: str | None = None
    mapping_status: str = SEM_LEITURA_GAM
    source: str = FONTE
    currency: str | None = None
    timezone: str | None = None
    #: Instante da leitura que produziu a linha (o `observado_em` da Meta) e o
    #: recibo/`updated_at` do lado GAM. Frescor é parte do contrato.
    source_freshness: str | None = None
    revenue_freshness: str | None = None
    #: `False` quando a leitura que produziu a linha foi parcial.
    completo: bool = True

    def __post_init__(self) -> None:
        if not id_meta_valido(self.campaign_id):
            raise AtribuicaoMetaInvalida(
                "META_CAMPAIGN_ID_INVALIDO",
                "campaign_id precisa ser um id de objeto da Meta")
        if not id_meta_valido(self.adset_id):
            raise AtribuicaoMetaInvalida(
                "META_ADSET_ID_INVALIDO",
                "adset_id precisa ser um id de objeto da Meta")
        if self.metric_scope not in ESCOPOS_CONHECIDOS:
            raise AtribuicaoMetaInvalida(
                "META_ESCOPO_DESCONHECIDO", f"metric_scope {self.metric_scope!r}")
        if self.mapping_status not in ESTADOS_DE_MAPEAMENTO:
            raise AtribuicaoMetaInvalida(
                "META_MAPPING_STATUS_DESCONHECIDO", f"mapping_status {self.mapping_status!r}")
        if not isinstance(self.date, Data):
            raise AtribuicaoMetaInvalida("META_DATA_INVALIDA", "date precisa ser datetime.date")

    @property
    def chave(self) -> tuple[str, str, str, str, str, str]:
        """A chave de idempotência do grão. Nenhum NOME participa dela."""
        return (self.account_ref, self.campaign_id, self.adset_id,
                self.date.isoformat(), self.metric_scope, self.metric_version)

    @property
    def tem_entrega(self) -> bool:
        """Houve entrega medida neste dia?

        Zero impressões com zero gasto não é "sem dado": é entrega medida como
        zero. `None` em ambos é que é ausência.
        """
        return (self.impressions or 0) > 0 or (self.spend or 0) > 0


def linha_de_conjunto_dia(
    *,
    account_ref: str,
    campaign_id: str,
    adset_id: str,
    date: Data,
    insight: Mapping[str, Any] | None,
    receita_gam: Mapping[str, Any] | None,
    gam_disponivel: bool,
    project_id: int | None = None,
    currency: str | None = None,
    timezone: str | None = None,
    completo: bool = True,
) -> LinhaAtribuicao:
    """Monta UMA linha do grão a partir das duas fontes, sem inventar nada.

    `insight` é a linha `latest` da Meta no nível `adset` para o dia.
    `receita_gam` é a linha do GAM cujo `utm_campaign_value` é este `adset_id`.

    `gam_disponivel` distingue os dois "sem receita" que o produto precisa
    diferenciar e que um único `None` esconderia:

    - `gam_disponivel=False` -> a leitura do GAM não aconteceu (contrato
      ausente, conta não unívoca, período incompleto). Estado `SEM_LEITURA_GAM`.
    - `gam_disponivel=True` e `receita_gam is None` -> o GAM foi lido e NÃO
      carrega este conjunto. Estado `SEM_UTM_ADSET_NO_GAM`. Receita continua
      `None`: associação desconhecida não é receita zero.
    """
    insight = insight or {}
    if receita_gam is not None:
        estado = ATRIBUIDO_VIA_ADSET
        metodo: str | None = METODO_UTM_CAMPAIGN_COM_ADSET_ID
    elif gam_disponivel:
        estado, metodo = SEM_UTM_ADSET_NO_GAM, None
    else:
        estado, metodo = SEM_LEITURA_GAM, None

    bruta = _decimal((receita_gam or {}).get("revenue"))
    convertida = _decimal((receita_gam or {}).get("revenue_converted"))
    cambio = _decimal((receita_gam or {}).get("fx_rate"))
    if cambio is None and bruta not in (None, Decimal(0)) and convertida is not None:
        # Câmbio DERIVADO da própria linha, não uma taxa de mercado presumida.
        # Ele existe para auditar a conversão que a fonte já fez, nunca para
        # fazer uma conversão que a fonte não fez.
        cambio = convertida / bruta

    return LinhaAtribuicao(
        account_ref=account_ref,
        campaign_id=campaign_id,
        adset_id=adset_id,
        date=date,
        project_id=project_id,
        spend=_decimal(insight.get("spend")),
        impressions=_inteiro(insight.get("impressions")),
        clicks=_inteiro(insight.get("clicks")),
        reach=_inteiro(insight.get("reach")),
        gam_revenue_original=bruta,
        gam_revenue_brl=convertida,
        gam_impressions=_inteiro((receita_gam or {}).get("impressions")),
        gam_clicks=_inteiro((receita_gam or {}).get("clicks")),
        fx_rate=cambio,
        attribution_method=metodo,
        mapping_status=estado,
        currency=currency,
        timezone=timezone,
        source_freshness=(str(insight.get("observado_em")) if insight.get("observado_em") else None),
        revenue_freshness=(str((receita_gam or {}).get("updated_at"))
                           if (receita_gam or {}).get("updated_at") else None),
        completo=completo,
    )


def recusar_duplicatas(linhas: Sequence[LinhaAtribuicao]) -> None:
    """Uma chave de grão só pode aparecer uma vez na coleção que vai somar.

    Duas linhas do mesmo grão são a MESMA verdade medida duas vezes — nunca o
    dobro. Quem quiser a revisão mais nova resolve isso ANTES de somar (é o que
    `vw_trafego_meta_insight_latest` faz do lado do banco); aqui a duplicata é
    recusada, não desempatada em silêncio.
    """
    vistas: set[tuple[str, ...]] = set()
    for linha in linhas:
        if linha.chave in vistas:
            raise AtribuicaoMetaInvalida(
                "META_GRAO_DUPLICADO",
                f"o grão {linha.chave} apareceu duas vezes na mesma soma")
        vistas.add(linha.chave)


def _exigir_homogeneidade(linhas: Sequence[LinhaAtribuicao]) -> None:
    """Escopo, versão, moeda e fuso precisam ser um só para poder somar."""
    escopos = {l.metric_scope for l in linhas}
    if len(escopos) > 1:
        # ⚠️ ESTE é o erro que dobra o gasto. A leitura campaign-level e as
        # leituras adset-level medem a mesma despesa por caminhos diferentes.
        raise AtribuicaoMetaInvalida(
            "META_ESCOPOS_MISTURADOS",
            f"não somar escopos diferentes na mesma conta: {sorted(escopos)}")
    if len({l.metric_version for l in linhas}) > 1:
        raise AtribuicaoMetaInvalida(
            "META_VERSOES_MISTURADAS", "linhas de versões de atribuição diferentes não somam")
    moedas = {l.currency for l in linhas if l.currency is not None}
    if len(moedas) > 1:
        raise AtribuicaoMetaInvalida("META_MOEDAS_MISTURADAS", f"moedas: {sorted(moedas)}")
    fusos = {l.timezone for l in linhas if l.timezone is not None}
    if len(fusos) > 1:
        raise AtribuicaoMetaInvalida("META_FUSOS_MISTURADOS", f"fusos: {sorted(fusos)}")


def _somar(valores: Iterable[Decimal | int | None]) -> Decimal | None:
    """Soma que preserva ausência.

    Uma parcela desconhecida torna o total desconhecido. Tratar `None` como
    zero produziria um total que PARECE completo e não é — o defeito exato que
    a semântica de ausência deste contrato existe para impedir.
    """
    total = Decimal(0)
    algum = False
    for valor in valores:
        if valor is None:
            return None
        total += Decimal(valor)
        algum = True
    return total if algum else None


def _somar_ignorando_ausentes(valores: Iterable[Decimal | int | None]) -> Decimal | None:
    """Soma das parcelas MEDIDAS, usada só onde a ausência já foi nomeada.

    Serve à receita: um conjunto sem UTM no GAM é associação desconhecida, e a
    campanha continua podendo somar o que de fato foi atribuído — desde que o
    resultado viaje junto com a contagem de conjuntos não atribuídos, que é o
    que `RazaoDaSoma` carrega. Sem essa contagem ao lado, este total mentiria.
    """
    medidos = [Decimal(v) for v in valores if v is not None]
    return sum(medidos, Decimal(0)) if medidos else None


@dataclass(frozen=True)
class RazaoDaSoma:
    """Por que o total é o que é. Vai junto com o total, sempre.

    Um número sozinho não diz se ele é completo. Esta é a diferença entre
    "R$ 0,00 de receita" e "receita desconhecida em 2 dos 7 conjuntos".
    """

    conjuntos: int
    dias: int
    #: Conjuntos DISTINTOS com ao menos um dia atribuído. Serve à frase "5 de 7
    #: conjuntos têm receita"; NÃO serve para decidir completude.
    conjuntos_atribuidos: int
    #: ⚠️ As contagens de ausência são por LINHA (conjunto/dia), não por
    #: conjunto — porque o grão do contrato é conjunto/dia e a ausência é do
    #: dia. A primeira versão contava por conjunto, com subtração de conjunto:
    #: um conjunto atribuído na segunda e sem linha no GAM na terça saía da
    #: contagem, e o total do período aparecia como completo faltando um dia.
    #: O golden pegou isso.
    linhas: int
    linhas_atribuidas: int
    linhas_sem_utm: int
    linhas_sem_leitura_gam: int
    linhas_sem_entrega: int
    spend_completo: bool
    revenue_completo: bool

    def publico(self) -> dict[str, Any]:
        return {
            "conjuntos": self.conjuntos,
            "dias": self.dias,
            "conjuntos_atribuidos": self.conjuntos_atribuidos,
            "linhas": self.linhas,
            "linhas_atribuidas": self.linhas_atribuidas,
            "linhas_sem_utm": self.linhas_sem_utm,
            "linhas_sem_leitura_gam": self.linhas_sem_leitura_gam,
            "linhas_sem_entrega": self.linhas_sem_entrega,
            "spend_completo": self.spend_completo,
            "revenue_completo": self.revenue_completo,
        }


@dataclass(frozen=True)
class Total:
    """Um total e a razão dele. Os derivados nunca são somados: são recalculados."""

    spend: Decimal | None
    revenue_original: Decimal | None
    revenue_brl: Decimal | None
    impressions: int | None
    clicks: int | None
    gam_impressions: int | None
    gam_clicks: int | None
    #: `None` de propósito: alcance não soma. Ver `LinhaAtribuicao.reach`.
    reach: None
    ctr: Decimal | None
    cpc: Decimal | None
    roas_ratio: Decimal | None
    profit_gross: Decimal | None
    retorno_excedente_pct: Decimal | None
    currency: str | None
    timezone: str | None
    razao: RazaoDaSoma
    source_freshness: str | None
    revenue_freshness: str | None

    def publico(self) -> dict[str, Any]:
        return {
            "spend": self.spend,
            "revenue_original": self.revenue_original,
            "revenue_brl": self.revenue_brl,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "gam_impressions": self.gam_impressions,
            "gam_clicks": self.gam_clicks,
            "reach": None,
            "ctr": self.ctr,
            "cpc": self.cpc,
            "roas_ratio": self.roas_ratio,
            "profit_gross": self.profit_gross,
            "retorno_excedente_pct": self.retorno_excedente_pct,
            "currency": self.currency,
            "timezone": self.timezone,
            "source": FONTE,
            "razao": self.razao.publico(),
            "source_freshness": self.source_freshness,
            "revenue_freshness": self.revenue_freshness,
        }


def _minimo_texto(valores: Iterable[str | None]) -> str | None:
    presentes = sorted(v for v in valores if v)
    return presentes[0] if presentes else None


def totalizar(linhas: Sequence[LinhaAtribuicao]) -> Total:
    """O total de uma coleção de linhas do MESMO escopo.

    É esta função — e só ela — que produz dinheiro agregado neste contrato.
    `agregar_campanha_dia`, `agregar_campanha_periodo` e `agregar_conta` são
    recortes que a chamam; nenhum deles soma por conta própria.
    """
    if not linhas:
        return Total(
            spend=None, revenue_original=None, revenue_brl=None, impressions=None,
            clicks=None, gam_impressions=None, gam_clicks=None, reach=None,
            ctr=None, cpc=None, roas_ratio=None, profit_gross=None,
            retorno_excedente_pct=None, currency=None, timezone=None,
            razao=RazaoDaSoma(0, 0, 0, 0, 0, 0, 0, 0, False, False),
            source_freshness=None, revenue_freshness=None)

    _exigir_homogeneidade(linhas)
    recusar_duplicatas(linhas)

    spend = _somar(l.spend for l in linhas)
    impressions = _somar(l.impressions for l in linhas)
    clicks = _somar(l.clicks for l in linhas)
    revenue_brl = _somar_ignorando_ausentes(l.gam_revenue_brl for l in linhas)
    revenue_orig = _somar_ignorando_ausentes(l.gam_revenue_original for l in linhas)
    gam_imp = _somar_ignorando_ausentes(l.gam_impressions for l in linhas)
    gam_clk = _somar_ignorando_ausentes(l.gam_clicks for l in linhas)

    sem_utm = sum(1 for l in linhas if l.mapping_status == SEM_UTM_ADSET_NO_GAM)
    sem_leitura = sum(1 for l in linhas if l.mapping_status == SEM_LEITURA_GAM)
    atribuidas = sum(1 for l in linhas if l.mapping_status == ATRIBUIDO_VIA_ADSET)
    razao = RazaoDaSoma(
        conjuntos=len({l.adset_id for l in linhas}),
        dias=len({l.date for l in linhas}),
        conjuntos_atribuidos=len({l.adset_id for l in linhas
                                  if l.mapping_status == ATRIBUIDO_VIA_ADSET}),
        linhas=len(linhas),
        linhas_atribuidas=atribuidas,
        linhas_sem_utm=sem_utm,
        linhas_sem_leitura_gam=sem_leitura,
        linhas_sem_entrega=sum(1 for l in linhas if not l.tem_entrega),
        spend_completo=spend is not None and all(l.completo for l in linhas),
        # Receita só é completa quando NENHUMA linha do grão ficou sem receita.
        # Um conjunto/dia sem UTM no GAM é associação desconhecida: ele mantém o
        # total honesto porque aparece na razão, mas não deixa o total
        # "completo" — e essa distinção é por DIA, não por conjunto.
        revenue_completo=(
            revenue_brl is not None and not sem_leitura and not sem_utm
            and all(l.completo for l in linhas)),
    )

    ctr = (Decimal(clicks) / Decimal(impressions) * 100
           if impressions and clicks is not None else None)
    cpc = Decimal(spend) / Decimal(clicks) if clicks and spend is not None else None
    roas = profit = excedente = None
    if revenue_brl is not None and spend is not None:
        profit = revenue_brl - spend
        if spend > 0:
            roas = revenue_brl / spend
            # Retorno excedente é uma leitura DIFERENTE de ROAS, não a mesma em
            # outra unidade: ROAS 1,10 e "10% acima do investido" respondem a
            # perguntas distintas, e misturá-las já produziu decisão errada.
            excedente = (revenue_brl / spend - 1) * 100

    return Total(
        spend=spend, revenue_original=revenue_orig, revenue_brl=revenue_brl,
        impressions=int(impressions) if impressions is not None else None,
        clicks=int(clicks) if clicks is not None else None,
        gam_impressions=int(gam_imp) if gam_imp is not None else None,
        gam_clicks=int(gam_clk) if gam_clk is not None else None,
        reach=None, ctr=ctr, cpc=cpc, roas_ratio=roas, profit_gross=profit,
        retorno_excedente_pct=excedente,
        currency=next((l.currency for l in linhas if l.currency), None),
        timezone=next((l.timezone for l in linhas if l.timezone), None),
        razao=razao,
        source_freshness=_minimo_texto(l.source_freshness for l in linhas),
        revenue_freshness=_minimo_texto(l.revenue_freshness for l in linhas),
    )


def agregar_campanha_dia(
    linhas: Sequence[LinhaAtribuicao],
) -> dict[tuple[str, Data], Total]:
    """Campanha/dia = soma dos CONJUNTOS filhos daquele dia. Nada mais.

    ⚠️ Se `linhas` contiver uma leitura de escopo `campaign`, esta função
    RECUSA. É a trava contra o double count: a leitura campaign-level serve
    para reconciliar com este total, nunca para entrar nele.
    """
    for linha in linhas:
        if linha.metric_scope != ESCOPO_CONJUNTO:
            raise AtribuicaoMetaInvalida(
                "META_AGREGACAO_EXIGE_ESCOPO_CONJUNTO",
                "a campanha soma conjuntos; uma leitura campaign-level aqui "
                "somaria a mesma despesa duas vezes")
    grupos: dict[tuple[str, Data], list[LinhaAtribuicao]] = {}
    for linha in linhas:
        grupos.setdefault((linha.campaign_id, linha.date), []).append(linha)
    return {chave: totalizar(grupo) for chave, grupo in sorted(grupos.items())}


def agregar_campanha_periodo(
    linhas: Sequence[LinhaAtribuicao],
) -> dict[str, Total]:
    """Campanha no período inteiro = soma dos conjuntos em todos os dias."""
    for linha in linhas:
        if linha.metric_scope != ESCOPO_CONJUNTO:
            raise AtribuicaoMetaInvalida(
                "META_AGREGACAO_EXIGE_ESCOPO_CONJUNTO",
                "a campanha soma conjuntos, em qualquer recorte de tempo")
    grupos: dict[str, list[LinhaAtribuicao]] = {}
    for linha in linhas:
        grupos.setdefault(linha.campaign_id, []).append(linha)
    return {chave: totalizar(grupo) for chave, grupo in sorted(grupos.items())}


def agregar_conjunto_periodo(
    linhas: Sequence[LinhaAtribuicao],
) -> dict[str, Total]:
    """Conjunto no período inteiro = soma dos dias daquele conjunto."""
    grupos: dict[str, list[LinhaAtribuicao]] = {}
    for linha in linhas:
        grupos.setdefault(linha.adset_id, []).append(linha)
    return {chave: totalizar(grupo) for chave, grupo in sorted(grupos.items())}


def reconciliar_com_campaign_level(
    total_dos_conjuntos: Total,
    leitura_campaign_level: Mapping[str, Any] | None,
    *,
    tolerancia: Decimal = Decimal("0.01"),
) -> dict[str, Any]:
    """Compara a soma dos conjuntos com a leitura campaign-level da Meta.

    O resultado é DIAGNÓSTICO, nunca parcela. Uma divergência não corrige o
    total: ela é reportada para que alguém investigue conjunto faltante,
    janela de atribuição diferente ou leitura parcial.
    """
    if leitura_campaign_level is None:
        return {"reconciliado": None, "motivo": "SEM_LEITURA_CAMPAIGN_LEVEL",
                "spend_conjuntos": total_dos_conjuntos.spend, "spend_campanha": None,
                "diferenca": None}
    spend_campanha = _decimal(leitura_campaign_level.get("spend"))
    soma = total_dos_conjuntos.spend
    if spend_campanha is None or soma is None:
        return {"reconciliado": None, "motivo": "MEDIDA_AUSENTE",
                "spend_conjuntos": soma, "spend_campanha": spend_campanha,
                "diferenca": None}
    diferenca = soma - spend_campanha
    return {
        "reconciliado": abs(diferenca) <= tolerancia,
        "motivo": None if abs(diferenca) <= tolerancia else "DIVERGENCIA_ENTRE_NIVEIS",
        "spend_conjuntos": soma,
        "spend_campanha": spend_campanha,
        "diferenca": diferenca,
    }


def marcar_parcial(linhas: Sequence[LinhaAtribuicao]) -> list[LinhaAtribuicao]:
    """Devolve as linhas com `completo=False`.

    Existe para que um caminho que sabe que leu parcialmente não precise montar
    as linhas de novo só para dizer isso — e não tenha a desculpa de omitir.
    """
    return [replace(linha, completo=False) for linha in linhas]
