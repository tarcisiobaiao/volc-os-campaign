"""Projeção persistida do diagnóstico Search no contrato do frontend.

``trafego_inventario_campanha`` prova que a identidade interna existe. As três
relações ``trafego_google_inteligencia_*`` da v12_01 carregam a coleta, seus
itens e suas métricas. Nenhum request daqui consulta Google Ads. O payload bruto
nunca é devolvido: somente campos explicitamente permitidos viram evidência.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Dict, List, Literal, Optional, Protocol, Sequence, TypeAlias

from pydantic import BaseModel, Field

from app.trafego import inventario
from app.trafego import sentinela as sent

log = logging.getLogger("volc.trafego.diagnostico_persistido")

TIPO_SINAL = "DIAGNOSTICO_ENTREGA"
EstadoDaColeta: TypeAlias = Literal[
    "com_dados", "vazio_confirmado", "parcial", "inelegivel",
    "nao_suportado", "falhou",
]
FrescorDoDiagnostico: TypeAlias = Literal["recente", "velho", "nao_apurado"]

ESTADOS_COLETA: frozenset[str] = frozenset({
    "com_dados", "vazio_confirmado", "parcial", "inelegivel",
    "nao_suportado", "falhou",
})
EIXOS = (
    "conta", "campanha", "orcamento", "grupo", "anuncio", "keyword",
    "segmentacao", "conversao", "leilao",
)

#: Estados da campanha que a conta usa para dizer "isto não vai a leilão".
#: ⚠️ `SUSPENDED` e `MISCONFIGURED` entram em 03/09/2026: os dois são valores
#: reais do enum e caíam no `else` que devolvia "primary_status e serving_status
#: ausentes" — um impedimento factualmente falso, porque os dois campos vieram.
ESTADOS_QUE_IMPEDEM: frozenset[str] = frozenset({
    "NOT_ELIGIBLE", "REMOVED", "ENDED", "SUSPENDED", "MISCONFIGURED",
})
#: O que a campanha pode responder e esta versão sabe interpretar. Um valor fora
#: desta lista NUNCA vira `ok`: ele nomeia a si mesmo no impedimento.
ESTADOS_RECONHECIDOS_DA_CAMPANHA: frozenset[str] = (
    ESTADOS_QUE_IMPEDEM
    #: ⚠️ `NOT_STARTED` não existe em nenhum dos dois enums. O valor real para
    #: "ainda não começou" é `PENDING`, que já está na lista.
    | frozenset({"ENABLED", "ELIGIBLE", "SERVING", "LIMITED", "LEARNING",
                 "PAUSED", "PENDING", "NONE"})
)

#: `customer.status` que impedem a conta inteira de veicular.
CONTA_BLOQUEADA: frozenset[str] = frozenset({"SUSPENDED", "CANCELED", "CLOSED"})

#: `policy_summary.approval_status` — o campo colhido, allowlisted e nunca lido
#: até 03/09/2026. Um anúncio `ENABLED` + `ELIGIBLE` + `DISAPPROVED` saía do
#: diagnóstico como `anuncio: ok`, palavra "presente".
ANUNCIO_REPROVADO: frozenset[str] = frozenset({"DISAPPROVED"})
#: ⚠️ `APPROVED_LIMITED` NÃO é verde: é aprovado com restrição, e a conta o
#: separa de `APPROVED` justamente porque a veiculação é menor.
ANUNCIO_LIMITADO: frozenset[str] = frozenset({"APPROVED_LIMITED"})
#: ⚠️ `REVIEWED_AND_PENDING` NÃO existe em `PolicyReviewStatusEnum`. O quarto
#: valor real é `ELIGIBLE_MAY_SERVE` — em revisão, e veiculando enquanto isso.
ANUNCIO_EM_REVISAO: frozenset[str] = frozenset({
    "REVIEW_IN_PROGRESS", "UNDER_APPEAL", "ELIGIBLE_MAY_SERVE",
})

COLUNAS_CAMPANHA = (
    "volc_campaign_id,customer_id,campaign_id,nome,moeda,canal,estado_externo,"
    "veiculacao,lido_em"
)
COLUNAS_COLETA = (
    "coleta_id,estado,customer_id,volc_campaign_id,campaign_id,"
    "janela_inicio,janela_fim,coletada_em,quantidade,erro_codigo,erro_classe"
)
COLUNAS_ITEM = "item_id,coleta_id,ordinal,tipo_item,recurso_externo,payload"
COLUNAS_METRICA = (
    "metrica_id,coleta_id,recurso_tipo,recurso_externo,nome,estado_valor,"
    "valor_numerico,valor_texto,unidade,moeda"
)
#: ⚠️ `account` e `conversion_goal` entram aqui em 03/09/2026, e sem migration.
#: O CHECK de `tipo_item` na v12_01 é `btrim(tipo_item) <> ''` — aberto — e os
#: dois viajam dentro do documento `DIAGNOSTICO_ENTREGA`, que já é um dos doze
#: `tipo_sinal` que o CHECK fechado aceita. Ver `coletor._diagnostico`.
TIPOS_ITEM = {"account", "campaign", "keyword", "ad", "conversion_goal"}
METRICAS_PERMITIDAS = {
    "impressions", "clicks", "cost_micros", "conversions",
    "all_conversions", "search_impression_share",
    "search_rank_lost_impression_share",
    "search_budget_lost_impression_share", "search_top_impression_share",
    "search_absolute_top_impression_share", "daily_budget_micros",
    "keyword_count", "first_page_cpc_median_micros",
}

# Allowlist dos únicos caminhos brutos que podem virar evidência.
CAMINHOS_ITEM: Dict[str, Dict[str, tuple[str, ...]]] = {
    "account": {
        # ⚠️ O campo que faltava. Sem ele, o eixo `conta` saía `nao_apurado`
        # para SEMPRE — e como `conta` é o degrau 0, `vereditoDaEscada` no
        # frontend devolvia `{tipo:'nao_apurado', eixo:'conta'}` em toda
        # campanha, com ZERO degraus confiáveis. A escada inteira era leitura
        # suspensa permanente: a tela nunca mentia de verde porque nunca
        # diagnosticava nada.
        "customer.status": ("customer", "status"),
        "customer.id": ("customer", "id"),
        "customer.test_account": ("customer", "test_account"),
        "customer.optimization_score": ("customer", "optimization_score"),
    },
    "conversion_goal": {
        "customer_conversion_goal.category": (
            "customer_conversion_goal", "category"
        ),
        "customer_conversion_goal.origin": (
            "customer_conversion_goal", "origin"
        ),
        "customer_conversion_goal.biddable": (
            "customer_conversion_goal", "biddable"
        ),
    },
    "campaign": {
        "campaign.status": ("campaign", "status"),
        "campaign.primary_status": ("campaign", "primary_status"),
        "campaign.primary_status_reasons": ("campaign", "primary_status_reasons"),
        "campaign.serving_status": ("campaign", "serving_status"),
        "campaign.bidding_strategy_type": ("campaign", "bidding_strategy_type"),
        "campaign_budget.amount_micros": ("campaign_budget", "amount_micros"),
        "campaign_budget.has_recommended_budget": ("campaign_budget", "has_recommended_budget"),
        "campaign_budget.recommended_budget_amount_micros": (
            "campaign_budget", "recommended_budget_amount_micros"
        ),
    },
    "keyword": {
        "ad_group_criterion.keyword.match_type": (
            "ad_group_criterion", "keyword", "match_type"
        ),
        "ad_group_criterion.primary_status": (
            "ad_group_criterion", "primary_status"
        ),
        "ad_group_criterion.primary_status_reasons": (
            "ad_group_criterion", "primary_status_reasons"
        ),
        "ad_group_criterion.effective_cpc_bid_micros": (
            "ad_group_criterion", "effective_cpc_bid_micros"
        ),
        "ad_group_criterion.position_estimates.first_page_cpc_micros": (
            "ad_group_criterion", "position_estimates", "first_page_cpc_micros"
        ),
        "ad_group_criterion.quality_info.quality_score": (
            "ad_group_criterion", "quality_info", "quality_score"
        ),
        # Colhidos pelo coletor desde sempre e nunca lidos até 03/09/2026.
        "ad_group_criterion.keyword.text": (
            "ad_group_criterion", "keyword", "text"
        ),
        "ad_group_criterion.position_estimates.top_of_page_cpc_micros": (
            "ad_group_criterion", "position_estimates", "top_of_page_cpc_micros"
        ),
    },
    "ad": {
        "ad_group_ad.status": ("ad_group_ad", "status"),
        "ad_group_ad.primary_status": ("ad_group_ad", "primary_status"),
        "ad_group_ad.primary_status_reasons": (
            "ad_group_ad", "primary_status_reasons"
        ),
        "ad_group_ad.ad_strength": ("ad_group_ad", "ad_strength"),
        "ad_group_ad.action_items": ("ad_group_ad", "action_items"),
        "ad_group_ad.policy_summary.approval_status": (
            "ad_group_ad", "policy_summary", "approval_status"
        ),
        "ad_group_ad.policy_summary.review_status": (
            "ad_group_ad", "policy_summary", "review_status"
        ),
    },
}


class Leitura(BaseModel):
    lido_em: str
    idade_s: int = Field(ge=0)


class EvidenciaDeCampo(BaseModel):
    rotulo: str
    valor: Optional[str]
    campo: str
    janela: Optional[str]
    leitura: Optional[Leitura]
    origem: Literal["conta", "declarado", "derivado"] = "conta"


class DegrauDeEntrega(BaseModel):
    eixo: Literal[
        "conta", "campanha", "orcamento", "grupo", "anuncio", "keyword",
        "segmentacao", "conversao", "leilao",
    ]
    estado: Literal["bloqueia", "limita", "ok", "nao_apurado"]
    palavra: str
    frase: str
    motivo_da_conta: List[str] = Field(default_factory=list)
    evidencias: List[EvidenciaDeCampo] = Field(default_factory=list)
    impedimento: Optional[str]
    propostas: List[str] = Field(default_factory=list)


class DiagnosticoDeEntrega(BaseModel):
    versao: Literal[1] = 1
    volc_campaign_id: str
    customer_id: str
    nome_campanha: str
    moeda: Optional[str]
    estado_coleta: Optional[EstadoDaColeta]
    frescor: FrescorDoDiagnostico
    janela: str
    leitura: Optional[Leitura]
    degraus: List[DegrauDeEntrega]
    parcial: bool


class CaixaDePropostas(BaseModel):
    versao: Literal[1] = 1
    volc_campaign_id: str
    propostas: List[Dict[str, Any]] = Field(default_factory=list)
    leitura: Optional[Leitura]


class VeredictoDaSentinela(BaseModel):
    """O veredito da sentinela, servido pelo BACKEND.

    ⚠️ Até 03/09/2026 o veredito era derivado no CLIENTE
    (`src/lib/diagnostico/escada.ts:44`), e o servidor não emitia campo nenhum.
    Com o eixo `conta` nunca preenchido, essa derivação devolvia
    `{tipo:'nao_apurado', eixo:'conta'}` em toda campanha e ZERO degraus
    confiáveis — a escada inteira era leitura suspensa permanente. Servir o
    veredito daqui é o que faz a tela e o alerta concordarem por construção, em
    vez de por coincidência.
    """

    model_config = {"extra": "forbid"}

    versao: int
    customer_id: str
    volc_campaign_id: str
    escopo: str
    status: str
    severidade: str
    incidente: bool
    observado_em: Optional[str] = None
    janela_inicio: Optional[str] = None
    janela_fim: Optional[str] = None
    janela_do_guardiao: str
    frescor: str
    estado_da_evidencia: str
    causa_primaria: Optional[Dict[str, Any]] = None
    causas_secundarias: List[Dict[str, Any]] = Field(default_factory=list)
    desconhecidos: List[str] = Field(default_factory=list)
    recomendacoes: Dict[str, Any] = Field(default_factory=dict)
    proximo_ato: Optional[str] = None
    chave: str
    #: Sempre `False`, sempre no fio. O operador LÊ que nada foi aplicado, em
    #: vez de deduzir isso da ausência de um botão.
    mutacao_externa: bool = False


class RespostaDoDiagnostico(BaseModel):
    """O envelope do diagnóstico. **Versão 2** desde 03/09/2026.

    A versão sobe porque um consumidor PRECISA saber: até a v1 o veredito era
    derivado no cliente sobre uma escada cujo primeiro degrau nunca era
    preenchido, e agora ele vem do servidor. Um cliente da v1 continua lendo
    `diagnostico` e `propostas` como sempre — o campo novo é opcional — mas um
    cliente que ignora `sentinela` está descartando o veredito e voltando a
    derivar o seu, que é o defeito de origem.
    """

    versao: Literal[2] = 2
    diagnostico: DiagnosticoDeEntrega
    propostas: CaixaDePropostas
    #: `None` só quando a sentinela não pôde ser avaliada. Nunca omitido para
    #: significar "está tudo bem".
    sentinela: Optional[VeredictoDaSentinela] = None


class CampanhaNaoEncontradaError(Exception):
    pass


class IdentificadorInvalidoError(Exception):
    pass


class ServicoIndisponivelError(Exception):
    pass


class RepositorioDiagnostico(Protocol):
    async def campanha(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]: ...
    async def coleta(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]: ...
    async def itens(self, coleta_id: str) -> List[Dict[str, Any]]: ...
    async def metricas(self, coleta_id: str) -> List[Dict[str, Any]]: ...


def validar_volc_campaign_id(valor: str) -> str:
    """Usa a mesma forma canônica do inventário e da página H0."""
    chave = str(valor or "").strip()
    if not chave or not inventario._CHAVE_VALIDA.fullmatch(chave):  # noqa: SLF001
        raise IdentificadorInvalidoError("volc_campaign_id inválido")
    return chave


def _dt(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=valor.tzinfo or timezone.utc).astimezone(timezone.utc)
    if not valor:
        return None
    try:
        parsed = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _leitura(coletada_em: Any, agora: Optional[datetime] = None) -> Optional[Leitura]:
    instante = _dt(coletada_em)
    if instante is None:
        return None
    referencia = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return Leitura(
        lido_em=instante.isoformat(),
        idade_s=max(0, int((referencia - instante).total_seconds())),
    )


def _frescor(leitura: Optional[Leitura]) -> FrescorDoDiagnostico:
    """Aplica a mesma janela de confiança usada pelo inventário canônico."""
    if leitura is None:
        return "nao_apurado"
    return (
        "velho"
        if leitura.idade_s > inventario.SEGUNDOS_PARA_VELHO
        else "recente"
    )


def _janela(coleta: Dict[str, Any]) -> str:
    inicio, fim = coleta.get("janela_inicio"), coleta.get("janela_fim")
    if inicio and fim:
        return f"{inicio} a {fim}"
    if inicio:
        return f"desde {inicio}"
    if fim:
        return f"até {fim}"
    return "janela não declarada"


def _caminho(payload: Any, partes: Sequence[str]) -> Any:
    atual = payload
    for parte in partes:
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor)
    if isinstance(valor, Decimal):
        return format(valor, "f")
    return str(valor)


def _valor_numerico(linha: Dict[str, Any]) -> Optional[Decimal]:
    if linha.get("estado_valor") != "medido":
        return None
    valor = linha.get("valor_numerico")
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _valor_metrica(linha: Dict[str, Any]) -> Optional[str]:
    estado = str(linha.get("estado_valor") or "")
    if estado == "medido":
        valor = linha.get("valor_numerico")
        return _texto(valor if valor is not None else linha.get("valor_texto"))
    if estado == "nao_aplicavel":
        return "não se aplica"
    if estado == "falhou":
        return "falha registrada"
    return None


def _evidencia(
    rotulo: str, campo: str, valor: Any, janela: str, leitura: Optional[Leitura],
) -> EvidenciaDeCampo:
    return EvidenciaDeCampo(
        rotulo=rotulo, valor=_texto(valor), campo=campo, janela=janela,
        leitura=leitura, origem="conta",
    )


def _evidencia_metrica(
    linha: Dict[str, Any], rotulo: str, janela: str, leitura: Optional[Leitura],
) -> EvidenciaDeCampo:
    return EvidenciaDeCampo(
        rotulo=rotulo, valor=_valor_metrica(linha),
        campo=f"metrics.{linha.get('nome')}", janela=janela,
        leitura=leitura, origem="conta",
    )


def _nao_apurado(eixo: str, frase: str, impedimento: str) -> DegrauDeEntrega:
    return DegrauDeEntrega(
        eixo=eixo, estado="nao_apurado", palavra="não apurado", frase=frase,
        impedimento=impedimento,
    )


def _degraus_sem_coleta(motivo: str) -> List[DegrauDeEntrega]:
    return [
        _nao_apurado(eixo, f"{eixo}: {motivo}.", motivo)
        for eixo in EIXOS
    ]


def _mapa_metricas(
    linhas: Sequence[Dict[str, Any]], campaign_id: str,
) -> Dict[str, Dict[str, Any]]:
    """Aceita somente métricas numéricas no grão da campanha solicitada.

    A v12 tipa a identidade como ``recurso_tipo + recurso_externo + nome``.
    Filtrar só por nome permitiria que uma métrica de keyword/ad fosse exibida
    como fato da campanha e que ``valor_texto`` arbitrário atravessasse uma
    allowlist nominalmente numérica.
    """
    saida: Dict[str, Dict[str, Any]] = {}
    for linha in linhas:
        nome = str(linha.get("nome") or "")
        if nome not in METRICAS_PERMITIDAS:
            continue
        if (
            str(linha.get("recurso_tipo") or "") != "campaign"
            or str(linha.get("recurso_externo") or "") != campaign_id
        ):
            raise ServicoIndisponivelError(
                f"A métrica '{nome}' não pertence à campanha da coleta v12."
            )
        estado = str(linha.get("estado_valor") or "")
        if estado not in {"medido", "ausente", "nao_aplicavel", "falhou"}:
            raise ServicoIndisponivelError(
                f"A métrica '{nome}' contém estado fora do contrato v12."
            )
        if estado == "medido":
            if linha.get("valor_texto") is not None or _valor_numerico(linha) is None:
                raise ServicoIndisponivelError(
                    f"A métrica numérica '{nome}' contém valor incompatível."
                )
        elif linha.get("valor_numerico") is not None or linha.get("valor_texto") is not None:
            raise ServicoIndisponivelError(
                f"A métrica não medida '{nome}' não pode carregar valor."
            )
        if nome in saida:
            raise ServicoIndisponivelError(
                f"A coleta v12 contém a métrica duplicada '{nome}'."
            )
        saida[nome] = linha
    return saida


def _itens_por_tipo(
    linhas: Sequence[Dict[str, Any]], campaign_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    saida = {tipo: [] for tipo in TIPOS_ITEM}
    for linha in linhas:
        tipo = str(linha.get("tipo_item") or "")
        if tipo not in TIPOS_ITEM:
            continue
        if (
            tipo == "campaign"
            and str(linha.get("recurso_externo") or "") != campaign_id
        ):
            raise ServicoIndisponivelError(
                "O item de campanha não pertence à campanha da coleta v12."
            )
        payload = linha.get("payload") if isinstance(linha.get("payload"), dict) else {}
        campos = {
            nome: _caminho(payload, caminho)
            for nome, caminho in CAMINHOS_ITEM[tipo].items()
        }
        saida[tipo].append({
            "recurso_externo": linha.get("recurso_externo"), "campos": campos,
        })
    return saida


def _degraus_observados(
    estado_coleta: str,
    itens: Sequence[Dict[str, Any]],
    metricas: Dict[str, Dict[str, Any]],
    janela: str,
    leitura: Optional[Leitura],
    campaign_id: str,
) -> List[DegrauDeEntrega]:
    por_tipo = _itens_por_tipo(itens, campaign_id)
    met = metricas
    degraus: Dict[str, DegrauDeEntrega] = {
        eixo: _nao_apurado(
            eixo, f"A coleta v12 não trouxe evidência suficiente para {eixo}.",
            "campo não colhido ou evidência insuficiente",
        ) for eixo in EIXOS
    }

    # ── o degrau 0, que nunca existiu ───────────────────────────────────────
    #
    # Até 03/09/2026 `conta` ficava no `nao_apurado` inicial para SEMPRE, porque
    # não havia caminho de payload para `customer.status`. Como `conta` é o
    # primeiro eixo da ordem causal, `vereditoDaEscada` (no frontend) devolvia
    # `{tipo:'nao_apurado', eixo:'conta'}` em TODA campanha e `degrausConfiaveis`
    # devolvia lista vazia: a escada inteira era leitura suspensa permanente.
    contas = por_tipo["account"]
    if contas:
        campos_conta = contas[0]["campos"]
        status_conta = campos_conta.get("customer.status")
        ev_conta = [
            _evidencia("estado da conta", "customer.status", status_conta, janela, leitura),
            _evidencia("conta de teste", "customer.test_account",
                       campos_conta.get("customer.test_account"), janela, leitura),
        ]
        texto_conta = None if status_conta is None else str(status_conta).upper()
        if texto_conta is None:
            degraus["conta"] = _nao_apurado(
                "conta", "A linha da conta veio sem o estado dela.",
                "customer.status ausente",
            )
        elif texto_conta in CONTA_BLOQUEADA:
            degraus["conta"] = DegrauDeEntrega(
                eixo="conta", estado="bloqueia", palavra="conta bloqueada",
                frase=(
                    f"A conta de anúncio está {texto_conta}. Nada desta campanha "
                    "vai a leilão enquanto ela estiver assim."
                ),
                evidencias=ev_conta, impedimento=None,
            )
        elif texto_conta == "ENABLED":
            degraus["conta"] = DegrauDeEntrega(
                eixo="conta", estado="ok", palavra="conta habilitada",
                frase="A conta de anúncio respondeu habilitada.",
                evidencias=ev_conta, impedimento=None,
            )
        else:
            degraus["conta"] = DegrauDeEntrega(
                eixo="conta", estado="nao_apurado", palavra="não apurado",
                frase=(
                    f"A conta respondeu o estado {texto_conta!r}, que esta versão "
                    "não reconhece."
                ),
                evidencias=ev_conta,
                impedimento="customer.status fora do vocabulário conhecido",
            )
    elif estado_coleta == "com_dados":
        degraus["conta"] = _nao_apurado(
            "conta",
            "A coleta completa não trouxe a linha da conta. Sem o estado dela, "
            "nada acima sustenta conclusão.",
            "item de conta ausente numa coleta com_dados",
        )

    # ── o degrau da conversão, também morto até aqui ────────────────────────
    metas = por_tipo["conversion_goal"]
    if metas:
        biddables = [
            m for m in metas
            if str(m["campos"].get("customer_conversion_goal.biddable")).lower()
            in {"true", "sim", "1"}
        ]
        ev_metas = [
            _evidencia(f"meta {i + 1}", "customer_conversion_goal.category",
                       m["campos"].get("customer_conversion_goal.category"),
                       janela, leitura)
            for i, m in enumerate(metas)
        ]
        if biddables:
            degraus["conversao"] = DegrauDeEntrega(
                eixo="conversao", estado="ok", palavra="meta observada",
                frase=(
                    f"A conta declarou {len(biddables)} meta(s) de conversão "
                    f"usável(is) para lance, de {len(metas)} observada(s)."
                ),
                evidencias=ev_metas, impedimento=None,
            )
        else:
            degraus["conversao"] = DegrauDeEntrega(
                eixo="conversao", estado="limita", palavra="sem meta para lance",
                frase=(
                    f"A conta observou {len(metas)} meta(s) de conversão e "
                    "nenhuma utilizável para lance."
                ),
                evidencias=ev_metas, impedimento=None,
            )
    elif estado_coleta == "com_dados":
        degraus["conversao"] = DegrauDeEntrega(
            eixo="conversao", estado="limita", palavra="nenhuma meta",
            frase=(
                "A coleta completa observou zero metas de conversão na conta. "
                "Sem meta, lance automático otimiza contra um sinal que não existe."
            ),
            evidencias=[], impedimento=None,
        )

    campanhas = por_tipo["campaign"]
    if campanhas:
        campos = campanhas[0]["campos"]
        status = campos.get("campaign.status")
        primary = campos.get("campaign.primary_status")
        serving = campos.get("campaign.serving_status")
        motivos = campos.get("campaign.primary_status_reasons") or []
        evidencias = [
            _evidencia("estado", "campaign.status", status, janela, leitura),
            _evidencia("estado principal", "campaign.primary_status", primary, janela, leitura),
            _evidencia("veiculação", "campaign.serving_status", serving, janela, leitura),
        ]
        observados = [str(v).upper() for v in (status, primary, serving) if v is not None]
        if status is None:
            estado, palavra, frase, impedimento = (
                "nao_apurado", "não apurado", "A linha da campanha não trouxe seu estado.",
                "campaign.status ausente",
            )
        elif str(status).upper() != "ENABLED":
            estado, palavra, frase, impedimento = (
                "bloqueia", "desligada", "A conta observou a campanha fora do estado ligado.", None,
            )
        elif any(v in ESTADOS_QUE_IMPEDEM for v in observados):
            estado, palavra, frase, impedimento = (
                "bloqueia", "não elegível", "A própria conta observou um estado que impede veiculação.", None,
            )
        elif any(v in {"LIMITED", "LEARNING"} for v in observados):
            estado, palavra, frase, impedimento = (
                "limita", "limitada", "A conta observou a campanha ligada, mas com limitação.", None,
            )
        elif (
            primary is not None
            and serving is not None
            and all(v in {"ENABLED", "ELIGIBLE", "SERVING"} for v in observados)
        ):
            estado, palavra, frase, impedimento = (
                "ok", "ligada", "A conta observou a campanha ligada sem bloqueio nestes campos.", None,
            )
        elif primary is None or serving is None:
            estado, palavra, frase, impedimento = (
                "nao_apurado", "não apurado",
                "A campanha está ligada, mas a coleta não trouxe estado de veiculação.",
                "primary_status e serving_status ausentes",
            )
        else:
            # ⚠️ Este ramo existia e MENTIA. Com `status=ENABLED`,
            # `primary_status=MISCONFIGURED` e `serving_status=SUSPENDED` — três
            # valores reais do enum, todos PRESENTES — ele devolvia
            # `impedimento="primary_status e serving_status ausentes"`. O
            # operador lia que faltou dado quando a conta tinha respondido, e
            # respondido a pior notícia possível.
            desconhecidos_aqui = sorted(
                v for v in observados
                if v not in ESTADOS_RECONHECIDOS_DA_CAMPANHA
            )
            estado, palavra, frase, impedimento = (
                "nao_apurado", "não apurado",
                "A conta respondeu um estado de veiculação que esta versão não "
                f"reconhece: {', '.join(desconhecidos_aqui) or 'combinação inesperada'}.",
                "estado fora do vocabulário conhecido — nunca degradado para ok",
            )
        degraus["campanha"] = DegrauDeEntrega(
            eixo="campanha", estado=estado, palavra=palavra, frase=frase,
            motivo_da_conta=[str(v) for v in motivos] if isinstance(motivos, list) else [str(motivos)],
            evidencias=evidencias, impedimento=impedimento,
        )

    orcamento = met.get("daily_budget_micros")
    perda = met.get("search_budget_lost_impression_share")
    # ⚠️ Colhida pelo coletor, allowlisted em METRICAS_PERMITIDAS desde sempre, e
    # NUNCA lida até 03/09/2026. Numa conta real deste repo a perda por
    # classificação foi medida em 0,90 e a perda por orçamento em 0,00 — e o
    # diagnóstico devolvia `orcamento: ok` com a frase "A conta mediu zero de
    # perda de participação por orçamento", sem uma palavra sobre rank. O verde
    # era verdadeiro sobre o orçamento e enganoso sobre a campanha.
    perda_rank = met.get("search_rank_lost_impression_share")
    evidencias_orcamento = []
    if orcamento:
        evidencias_orcamento.append(_evidencia_metrica(orcamento, "orçamento diário", janela, leitura))
    if perda:
        evidencias_orcamento.append(_evidencia_metrica(perda, "perda por orçamento", janela, leitura))
    perda_num = _valor_numerico(perda or {})
    perda_rank_num = _valor_numerico(perda_rank or {})
    if perda_rank:
        evidencias_orcamento.append(
            _evidencia_metrica(perda_rank, "perda por classificação", janela, leitura)
        )
    if perda_num is not None:
        limita = perda_num > 0
        # A frase do ramo `ok` diz agora sobre o QUE foi medido, e o eixo do
        # leilão recebe a perda por rank logo abaixo. Um zero de orçamento não
        # autoriza mais a leitura de que nada segura a campanha.
        frase_ok = "A conta mediu zero de perda de participação por orçamento."
        if perda_rank_num is not None and perda_rank_num > 0:
            frase_ok = (
                "A conta mediu zero de perda por orçamento — o que segura esta "
                "campanha está medido no degrau do leilão, não aqui."
            )
        degraus["orcamento"] = DegrauDeEntrega(
            eixo="orcamento", estado="limita" if limita else "ok",
            palavra="perda medida" if limita else "sem perda medida",
            frase=("A conta mediu perda de participação por orçamento." if limita else
                   frase_ok),
            evidencias=evidencias_orcamento, impedimento=None,
        )
    elif evidencias_orcamento:
        degraus["orcamento"] = DegrauDeEntrega(
            eixo="orcamento", estado="nao_apurado", palavra="não apurado",
            frase="Há evidência de orçamento, mas a perda por orçamento não foi medida.",
            evidencias=evidencias_orcamento,
            impedimento="search_budget_lost_impression_share não medido",
        )

    # ── o degrau da keyword, com o lance que a allowlist já trazia ─────────
    #
    # ⚠️ `effective_cpc_bid_micros` e `position_estimates.first_page_cpc_micros`
    # atravessavam `CAMINHOS_ITEM` desde a v12 e NUNCA eram lidos. O degrau saía
    # `ok` porque `primary_status` dizia `ELIGIBLE` — que é verdade e não é a
    # pergunta: elegível quer dizer "pode ir a leilão", não "vai". Com lance de
    # R$ 0,50 contra estimativa de R$ 3,20 a keyword é elegível e não aparece.
    #
    # A contagem sai de `sentinela.ler_keywords`, e não de uma segunda
    # implementação aqui: o degrau e o veredito precisam concordar sobre o mesmo
    # denominador, e concordam por usarem a mesma função.
    linhas_kw = por_tipo["keyword"]
    if not linhas_kw and estado_coleta == "com_dados":
        degraus["keyword"] = DegrauDeEntrega(
            eixo="keyword", estado="bloqueia", palavra="nenhuma observada",
            frase="A coleta completa observou zero keywords ativas.",
            impedimento=None,
        )
    elif linhas_kw:
        leitura_kw = sent.ler_keywords(_keywords_para_sentinela(linhas_kw))
        medidas = leitura_kw.medidas_para_lance
        abaixo = leitura_kw.abaixo_da_primeira_pagina
        ev_kw = [
            _evidencia("keywords observadas", "keyword_view",
                       leitura_kw.observadas, janela, leitura),
            _evidencia("com lance abaixo da 1ª página",
                       "ad_group_criterion.effective_cpc_bid_micros < "
                       "position_estimates.first_page_cpc_micros",
                       f"{abaixo} de {medidas}", janela, leitura),
            _evidencia("sem dado de lance", "ad_group_criterion",
                       leitura_kw.sem_dado_de_lance, janela, leitura),
            _evidencia("com Quality Score baixo",
                       "ad_group_criterion.quality_info.quality_score",
                       leitura_kw.baixa_qualidade, janela, leitura),
            _evidencia("grupos de intenção redundantes",
                       "ad_group_criterion.keyword.text (normalizado)",
                       leitura_kw.clusters_redundantes, janela, leitura),
        ]
        if medidas and abaixo == medidas:
            degraus["keyword"] = DegrauDeEntrega(
                eixo="keyword", estado="bloqueia", palavra="lance abaixo da 1ª página",
                frase=(
                    f"Todas as {medidas} keywords com lance medido estão abaixo "
                    "da estimativa de primeira página."
                ),
                evidencias=ev_kw, impedimento=None,
            )
        elif abaixo:
            degraus["keyword"] = DegrauDeEntrega(
                eixo="keyword", estado="limita", palavra="lance abaixo da 1ª página",
                frase=(
                    f"{abaixo} de {medidas} keywords com lance medido estão "
                    "abaixo da estimativa de primeira página."
                ),
                evidencias=ev_kw, impedimento=None,
            )
        elif leitura_kw.aptas:
            degraus["keyword"] = DegrauDeEntrega(
                eixo="keyword", estado="ok", palavra="aptas",
                frase=(
                    f"{leitura_kw.aptas} de {leitura_kw.observadas} keywords "
                    "estão habilitadas e com lance acima da estimativa."
                ),
                evidencias=ev_kw, impedimento=None,
            )
        else:
            degraus["keyword"] = DegrauDeEntrega(
                eixo="keyword", estado="nao_apurado", palavra="não apurado",
                frase=(
                    "Nenhuma keyword pôde ser classificada: "
                    f"{leitura_kw.sem_dado_de_lance} de {leitura_kw.observadas} "
                    "vieram sem lance ou sem estimativa de primeira página."
                ),
                evidencias=ev_kw,
                impedimento="lance ou estimativa de primeira página ausentes",
            )

    for tipo, eixo, rotulo in (("ad", "anuncio", "anúncio"),):
        linhas = por_tipo[tipo]
        if not linhas and estado_coleta == "com_dados":
            degraus[eixo] = DegrauDeEntrega(
                eixo=eixo, estado="bloqueia", palavra="nenhum observado",
                frase=f"A coleta completa observou zero {rotulo}s ativos.", impedimento=None,
            )
        elif linhas:
            campos_estado = (
                ("ad_group_ad.status", "ad_group_ad.primary_status")
                if tipo == "ad" else
                ("ad_group_criterion.primary_status",)
            )
            campos_evidencia = campos_estado + (
                ("ad_group_ad.policy_summary.approval_status",
                 "ad_group_ad.policy_summary.review_status")
                if tipo == "ad" else ()
            )
            evidencias = [
                _evidencia(f"{rotulo} {i + 1}", campo, linha["campos"].get(campo), janela, leitura)
                for i, linha in enumerate(linhas) for campo in campos_evidencia
            ]
            negativos = {"DISABLED", "PAUSED", "REMOVED", "NOT_ELIGIBLE", "ENDED"}
            positivos = {"ENABLED", "ELIGIBLE"}
            estados_por_entidade = []
            reprovados = limitados = em_revisao = 0
            for linha in linhas:
                valores = [linha["campos"].get(campo) for campo in campos_estado]
                normalizados = [str(v).upper() for v in valores if v is not None]
                # ⚠️ A POLÍTICA DO ANÚNCIO, colhida e allowlisted desde sempre e
                # nunca lida até 03/09/2026. Um anúncio com `status=ENABLED`,
                # `primary_status=ELIGIBLE` e
                # `policy_summary.approval_status=DISAPPROVED` saía daqui como
                # `anuncio: ok`, palavra "presente", frase "A conta observou
                # anúncio habilitado" — sobre um anúncio reprovado.
                aprovacao = linha["campos"].get("ad_group_ad.policy_summary.approval_status")
                revisao = linha["campos"].get("ad_group_ad.policy_summary.review_status")
                aprovacao = None if aprovacao is None else str(aprovacao).upper()
                revisao = None if revisao is None else str(revisao).upper()
                if aprovacao in ANUNCIO_REPROVADO:
                    reprovados += 1
                    estados_por_entidade.append("nao_elegivel")
                    continue
                if aprovacao in ANUNCIO_LIMITADO:
                    limitados += 1
                    estados_por_entidade.append("limitado")
                    continue
                if revisao in ANUNCIO_EM_REVISAO:
                    em_revisao += 1
                    estados_por_entidade.append("em_revisao")
                    continue
                if len(normalizados) != len(campos_estado):
                    estados_por_entidade.append("indeterminado")
                elif all(v in positivos for v in normalizados):
                    estados_por_entidade.append("elegivel")
                elif any(v in negativos for v in normalizados):
                    estados_por_entidade.append("nao_elegivel")
                else:
                    estados_por_entidade.append("indeterminado")
            total = len(estados_por_entidade)
            if "elegivel" in estados_por_entidade:
                estado, palavra, frase = "ok", "presente", f"A conta observou {rotulo} habilitado."
            elif "limitado" in estados_por_entidade:
                # Aprovado com restrição não é verde: a conta separa
                # `APPROVED_LIMITED` de `APPROVED` porque a veiculação é menor.
                estado, palavra, frase = (
                    "limita", "aprovado com limite",
                    f"A conta aprovou {limitados} de {total} {rotulo}s com restrição.",
                )
            elif "em_revisao" in estados_por_entidade:
                # ⚠️ Nem aprovado nem reprovado. Afirmar qualquer um dos dois
                # seria inventar um veredito que o Google ainda não deu.
                estado, palavra, frase = (
                    "nao_apurado", "em revisão",
                    f"A conta tem {em_revisao} de {total} {rotulo}s em revisão: "
                    "não estão aprovados e não estão reprovados.",
                )
            elif reprovados and reprovados == total:
                estado, palavra, frase = (
                    "bloqueia", "reprovado",
                    f"A conta reprovou os {total} {rotulo}s por política.",
                )
            elif estados_por_entidade and all(v == "nao_elegivel" for v in estados_por_entidade):
                estado, palavra, frase = "bloqueia", "sem elegível", f"A conta observou {rotulo} não elegível."
            else:
                estado, palavra, frase = "nao_apurado", "não apurado", f"Os {rotulo}s vieram sem estado conclusivo."
            degraus[eixo] = DegrauDeEntrega(
                eixo=eixo, estado=estado, palavra=palavra, frase=frase,
                evidencias=evidencias,
                impedimento=(f"estado dos {rotulo}s ausente" if estado == "nao_apurado" else None),
            )

    impressoes = met.get("impressions")
    if impressoes:
        evidencia_imp = _evidencia_metrica(impressoes, "impressões", janela, leitura)
        numero = _valor_numerico(impressoes)
        if numero is None:
            degraus["leilao"] = DegrauDeEntrega(
                eixo="leilao", estado="nao_apurado", palavra="não apurado",
                frase="A métrica de impressões não foi medida.",
                evidencias=[evidencia_imp], impedimento="impressions não medido",
            )
        else:
            degraus["leilao"] = DegrauDeEntrega(
                eixo="leilao", estado="limita" if numero == 0 else "ok",
                palavra="sem impressões" if numero == 0 else "com impressões",
                frase=("A conta mediu zero impressões nesta janela." if numero == 0 else
                       "A conta registrou impressões nesta janela."),
                evidencias=[evidencia_imp], impedimento=None,
            )
    # ⚠️ COLETA PARCIAL NÃO PRODUZ DEGRAU `ok`.
    #
    # `parcial=True` era só uma bandeira do envelope: os degraus continuavam
    # saindo `ok`, e um `ok` sob leitura parcial AFIRMA sobre o que não foi lido.
    # A regra aqui é a mesma que `escada.ts` aplica no veredito: prova
    # incompleta não sustenta conclusão positiva.
    if estado_coleta == "parcial":
        for eixo, degrau in list(degraus.items()):
            if degrau.estado == "ok":
                degraus[eixo] = DegrauDeEntrega(
                    eixo=eixo, estado="nao_apurado", palavra="não apurado",
                    frase=(
                        f"{degrau.frase} — porém a coleta terminou parcial, e o "
                        "que não foi lido pode contradizer isto."
                    ),
                    motivo_da_conta=degrau.motivo_da_conta,
                    evidencias=degrau.evidencias,
                    impedimento="coleta parcial: leitura incompleta não sustenta ok",
                    propostas=degrau.propostas,
                )
    return [degraus[eixo] for eixo in EIXOS]


class SupabaseRepositorioDiagnostico:
    """Quatro consultas PostgREST, todas com relação e coluna allowlisted."""

    def __init__(self, supa_service: Any):
        self.supa = supa_service

    def _exigir(self) -> None:
        if not self.supa or not getattr(self.supa, "enabled", False):
            raise ServicoIndisponivelError("Supabase oficial não configurado no backend.")

    async def _select(self, tabela: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        self._exigir()
        try:
            return await self.supa.select(tabela, params)
        except Exception as exc:
            log.exception("falha ao ler %s", tabela)
            raise ServicoIndisponivelError("Não foi possível ler o diagnóstico persistido.") from exc

    async def _select_all(self, tabela: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """SELECT paginado. Truncagem silenciosa é falso verde com outra roupa.

        ⚠️ `itens()` e `metricas()` usavam `select`, e o PostgREST deste projeto
        corta toda resposta em `db-max-rows = 1000` IGNORANDO um `limit` maior,
        sem erro nenhum (`app/services/supabase_service.py:74-78`). Uma campanha
        com mais de mil itens era lida pela metade — e como o eixo do anúncio sai
        `ok` quando encontra UM elegível, um único anúncio bom na primeira página
        pintava de verde uma campanha com quinhentos reprovados depois da linha
        mil. O paginador já existia e não era chamado.
        """
        self._exigir()
        try:
            return await self.supa.select_all(tabela, params)
        except Exception as exc:
            log.exception("falha ao ler %s (paginado)", tabela)
            raise ServicoIndisponivelError("Não foi possível ler o diagnóstico persistido.") from exc

    async def campanha(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]:
        linhas = await self._select("trafego_inventario_campanha", {
            "select": COLUNAS_CAMPANHA, "volc_campaign_id": f"eq.{volc_campaign_id}", "limit": 1,
        })
        return linhas[0] if linhas else None

    async def coleta(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]:
        linhas = await self._select("trafego_google_inteligencia_coleta", {
            "select": COLUNAS_COLETA, "volc_campaign_id": f"eq.{volc_campaign_id}",
            "tipo_sinal": f"eq.{TIPO_SINAL}", "order": "coletada_em.desc", "limit": 1,
        })
        return linhas[0] if linhas else None

    async def itens(self, coleta_id: str) -> List[Dict[str, Any]]:
        return await self._select_all("trafego_google_inteligencia_item", {
            "select": COLUNAS_ITEM, "coleta_id": f"eq.{coleta_id}", "order": "ordinal.asc",
        })

    async def metricas(self, coleta_id: str) -> List[Dict[str, Any]]:
        return await self._select_all("trafego_google_inteligencia_metrica", {
            "select": COLUNAS_METRICA, "coleta_id": f"eq.{coleta_id}", "order": "metrica_id.asc",
        })


# ── a ponte para a sentinela ────────────────────────────────────────────────
#
# ⚠️ Uma conversão declarada, e não um segundo diagnóstico. Tudo abaixo lê os
# MESMOS itens e métricas que os degraus leem, e o resultado é uma
# `LeituraParaSentinela` — nenhuma regra de veredito mora aqui. Duas
# implementações da mesma pergunta é como a tela e o alerta passam a discordar
# sem que exista resposta certa entre os dois.


def _num(valor: Any) -> Optional[int]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(Decimal(str(valor)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _metrica_num(linha: Optional[Dict[str, Any]]) -> Optional[Decimal]:
    return None if linha is None else _valor_numerico(linha)


def _keywords_para_sentinela(
    linhas: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    saida: List[Dict[str, Any]] = []
    for linha in linhas:
        campos = linha["campos"]
        saida.append({
            "texto": campos.get("ad_group_criterion.keyword.text"),
            "match_type": campos.get("ad_group_criterion.keyword.match_type"),
            "primary_status": campos.get("ad_group_criterion.primary_status"),
            "primary_status_reasons": campos.get(
                "ad_group_criterion.primary_status_reasons"
            ),
            "lance_micros": campos.get(
                "ad_group_criterion.effective_cpc_bid_micros"
            ),
            "primeira_pagina_micros": campos.get(
                "ad_group_criterion.position_estimates.first_page_cpc_micros"
            ),
            "quality_score": campos.get(
                "ad_group_criterion.quality_info.quality_score"
            ),
        })
    return saida


def _anuncios_para_sentinela(
    linhas: Sequence[Dict[str, Any]],
) -> sent.LeituraDeAnuncios:
    aptos = reprovados = revisao = sem_estado = 0
    motivos: List[str] = []
    for linha in linhas:
        campos = linha["campos"]
        aprovacao = campos.get("ad_group_ad.policy_summary.approval_status")
        revisao_txt = campos.get("ad_group_ad.policy_summary.review_status")
        status = campos.get("ad_group_ad.status")
        primary = campos.get("ad_group_ad.primary_status")
        razoes = campos.get("ad_group_ad.primary_status_reasons")
        if isinstance(razoes, list):
            motivos.extend(str(r) for r in razoes)
        elif razoes is not None:
            motivos.append(str(razoes))

        aprovacao = None if aprovacao is None else str(aprovacao).upper()
        revisao_txt = None if revisao_txt is None else str(revisao_txt).upper()
        if aprovacao in ANUNCIO_REPROVADO:
            reprovados += 1
            continue
        if revisao_txt in ANUNCIO_EM_REVISAO:
            revisao += 1
            continue
        if status is None or primary is None:
            sem_estado += 1
            continue
        if (
            str(status).upper() == "ENABLED"
            and str(primary).upper() in {"ELIGIBLE", "ENABLED"}
            and aprovacao not in ANUNCIO_LIMITADO
        ):
            aptos += 1
    return sent.LeituraDeAnuncios(
        observados=len(linhas), aptos=aptos, reprovados=reprovados,
        em_revisao=revisao, sem_estado=sem_estado,
        motivos=tuple(dict.fromkeys(motivos)),
    )


def _medicao_para_sentinela(
    metas: Sequence[Dict[str, Any]], estado_coleta: Optional[str],
) -> sent.LeituraDeMedicao:
    """Converte as metas observadas no vocabulário de `trafego.prontidao`.

    ⚠️ Sem item de meta E sem coleta completa, o estado é `None` — "não apurei" —
    e NÃO `NAO_PRONTO`. `prontidao.avaliar` documenta exatamente esta distinção
    (`metas_da_conta=None` significa "não conseguimos ler", não "não há meta"), e
    colapsá-las faria uma falha de leitura parecer uma conta sem meta.
    """
    if not metas:
        if estado_coleta == "com_dados":
            return sent.LeituraDeMedicao(
                conversion_goal_status="NAO_PRONTO", metas_observadas=0,
                impedimento="a coleta completa observou zero metas de conversão",
            )
        return sent.LeituraDeMedicao()
    biddables = [
        m for m in metas
        if str(m["campos"].get("customer_conversion_goal.biddable")).lower()
        in {"true", "sim", "1"}
    ]
    return sent.LeituraDeMedicao(
        conversion_goal_status="PRONTO" if biddables else "PARCIAL",
        metas_observadas=len(metas),
        impedimento=(
            None if biddables
            else "nenhuma das metas observadas é utilizável para lance"
        ),
    )


def montar_leitura_da_sentinela(
    *,
    chave: str,
    customer_id: str,
    estado_coleta: Optional[str],
    frescor: str,
    leitura: Optional[Leitura],
    coleta: Optional[Dict[str, Any]],
    itens: Sequence[Dict[str, Any]],
    metricas: Dict[str, Dict[str, Any]],
    campaign_id: str,
    horas_ligada: Optional[float] = None,
    recomendacoes: Optional[sent.QuadroDeRecomendacoes] = None,
    destino: Optional[sent.LeituraDoDestino] = None,
) -> sent.LeituraParaSentinela:
    por_tipo = _itens_por_tipo(itens, campaign_id) if itens else {
        tipo: [] for tipo in TIPOS_ITEM
    }
    quando = leitura.lido_em if leitura else None

    contas = por_tipo["account"]
    status_conta = (
        contas[0]["campos"].get("customer.status") if contas else None
    )
    campanhas = por_tipo["campaign"]
    campos_camp = campanhas[0]["campos"] if campanhas else {}
    razoes = campos_camp.get("campaign.primary_status_reasons")
    if isinstance(razoes, list):
        razoes_tupla = tuple(str(r) for r in razoes)
    elif razoes is None:
        razoes_tupla = ()
    else:
        razoes_tupla = (str(razoes),)

    def _m(nome: str) -> Optional[Decimal]:
        return _metrica_num(metricas.get(nome))

    impressoes = _m("impressions")
    cliques = _m("clicks")
    custo = _m("cost_micros")
    conversoes = _m("conversions")
    perda_orc = _m("search_budget_lost_impression_share")
    perda_rank = _m("search_rank_lost_impression_share")

    return sent.LeituraParaSentinela(
        customer_id=customer_id,
        volc_campaign_id=chave,
        conta=sent.LeituraDaConta(
            customer_id=customer_id,
            status=None if status_conta is None else str(status_conta),
            observado_em=quando,
        ),
        campanha=sent.LeituraDaCampanha(
            status=campos_camp.get("campaign.status"),
            primary_status=campos_camp.get("campaign.primary_status"),
            primary_status_reasons=razoes_tupla,
            serving_status=campos_camp.get("campaign.serving_status"),
            bidding_strategy_type=campos_camp.get("campaign.bidding_strategy_type"),
            horas_ligada=horas_ligada,
            orcamento_diario_micros=_num(
                campos_camp.get("campaign_budget.amount_micros")
            ),
        ),
        metricas=sent.LeituraDeMetricas(
            impressoes=None if impressoes is None else int(impressoes),
            cliques=None if cliques is None else int(cliques),
            custo_micros=None if custo is None else int(custo),
            conversoes=None if conversoes is None else float(conversoes),
            perda_por_orcamento=None if perda_orc is None else float(perda_orc),
            perda_por_rank=None if perda_rank is None else float(perda_rank),
        ),
        keywords=sent.ler_keywords(_keywords_para_sentinela(por_tipo["keyword"])),
        anuncios=_anuncios_para_sentinela(por_tipo["ad"]),
        medicao=_medicao_para_sentinela(por_tipo["conversion_goal"], estado_coleta),
        # ⚠️ O recibo de destino vive em `backend/app/landing_policy/**`, que é
        # ownership de outra frente e não persiste veredito por campanha hoje.
        # `nao_consultado` — e NÃO `ausente` — é a leitura honesta: nós não
        # perguntamos. Dizer `ausente` afirmaria que perguntamos e não havia, e
        # como `ausente` é causa, isso faria o destino sequestrar o veredito de
        # toda campanha. A sentinela declara o não-consultado em `desconhecidos`
        # e rebaixa a evidência para `parcial`, de modo que ninguém sai saudável
        # por engano.
        destino=destino or sent.LeituraDoDestino(estado="nao_consultado"),
        recomendacoes=recomendacoes or sent.QuadroDeRecomendacoes(),
        estado_da_coleta=estado_coleta,
        frescor=frescor,
        observado_em=quando,
        janela_inicio=str(coleta.get("janela_inicio")) if coleta and coleta.get("janela_inicio") else None,
        janela_fim=str(coleta.get("janela_fim")) if coleta and coleta.get("janela_fim") else None,
    )


def _veredito(leitura_sent: sent.LeituraParaSentinela) -> VeredictoDaSentinela:
    return VeredictoDaSentinela(**sent.avaliar(leitura_sent).json())


async def _horas_ligada(
    repositorio: Any, chave: str, agora: Optional[datetime],
) -> Optional[float]:
    """Há quantas horas a campanha está ligada — ou `None`, que NÃO é zero.

    Reusa `alertas.horas_ligada`, que lê o diário `trafego_evento`. É a mesma
    função que o sino usa, e por isso o sino e a sentinela concordam sobre a
    idade da campanha em vez de terem duas contas parecidas.
    """
    buscar = getattr(repositorio, "transicoes", None)
    if buscar is None:
        return None
    try:
        transicoes = await buscar(chave)
    except Exception:  # noqa: BLE001
        log.warning("não foi possível ler as transições de '%s'", chave)
        return None
    from app.trafego import alertas as alt  # noqa: PLC0415 — só neste caminho

    return alt.horas_ligada(
        transicoes or [], (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    )


async def _recomendacoes(
    repositorio: Any, customer_id: str,
) -> sent.QuadroDeRecomendacoes:
    """As recomendações do Google, adjudicadas — nunca aplicadas.

    ⚠️ Os três desfechos são distintos e nenhum degrada para os outros:
    repositório sem o método → `nao_executada`; leitura que estourou →
    `falhou`; leitura boa sem linha → `vazio_confirmado` com `itens=()`. Só o
    último autoriza a frase "o Google não sugeriu nada".
    """
    buscar = getattr(repositorio, "recomendacoes", None)
    if buscar is None or not customer_id:
        return sent.QuadroDeRecomendacoes()
    try:
        coleta, linhas = await buscar(customer_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("falha ao ler recomendações de %s", customer_id)
        return sent.QuadroDeRecomendacoes(
            estado_da_coleta=sent.COLETA_FALHOU,
            impedimento=f"a leitura de recomendações falhou ({type(exc).__name__})",
        )
    if coleta is None:
        return sent.QuadroDeRecomendacoes(
            estado_da_coleta=sent.COLETA_NAO_EXECUTADA,
            impedimento="nenhuma coleta de recomendações registrada para esta conta",
        )
    estado = str(coleta.get("estado") or "")
    quando = coleta.get("coletada_em")
    observado = None if quando is None else str(quando)
    frescor_rec = _frescor(_leitura(quando))
    if estado == "falhou":
        return sent.QuadroDeRecomendacoes(
            estado_da_coleta=sent.COLETA_FALHOU,
            impedimento=(
                "a coleta de recomendações terminou em falhou "
                f"({coleta.get('erro_codigo') or coleta.get('erro_classe') or 'sem código'})"
            ),
        )
    if estado not in {"com_dados", "vazio_confirmado"}:
        return sent.QuadroDeRecomendacoes(
            estado_da_coleta=sent.COLETA_NAO_EXECUTADA,
            impedimento=f"a coleta de recomendações está em {estado or 'estado desconhecido'}",
        )
    itens: List[sent.RecomendacaoAdjudicada] = []
    for linha in linhas or []:
        payload = linha.get("payload") if isinstance(linha.get("payload"), dict) else {}
        rec = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
        impacto = rec.get("impact")
        itens.append(sent.RecomendacaoAdjudicada(
            tipo=str(rec.get("type") or rec.get("type_") or "DESCONHECIDO"),
            alvo=_texto(linha.get("recurso_externo")),
            impacto_informado=(
                None if impacto is None
                else f"{_texto(impacto)} (informado pelo Google, não medido por nós)"
            ),
            observado_em=observado,
            frescor=frescor_rec,
            evidencia=(
                _ev_rec("tipo", "recommendation.type", rec.get("type"), observado),
                _ev_rec("dispensada na conta", "recommendation.dismissed",
                        rec.get("dismissed"), observado),
            ),
        ))
    return sent.QuadroDeRecomendacoes(
        estado_da_coleta=(
            sent.COLETA_COM_DADOS if itens else sent.COLETA_VAZIO_CONFIRMADO
        ),
        itens=tuple(itens),
    )


def _ev_rec(
    rotulo: str, campo: str, valor: Any, quando: Optional[str],
) -> sent.Evidencia:
    return sent.Evidencia(
        rotulo=rotulo, campo=campo, valor=_texto(valor),
        observado_em=quando, origem="conta",
    )


async def obter_diagnostico_campanha(
    volc_campaign_id: str,
    repositorio: RepositorioDiagnostico,
    agora: Optional[datetime] = None,
) -> RespostaDoDiagnostico:
    chave = validar_volc_campaign_id(volc_campaign_id)
    campanha = await repositorio.campanha(chave)
    if campanha is None:
        raise CampanhaNaoEncontradaError(f"Campanha interna '{chave}' não encontrada.")

    coleta = await repositorio.coleta(chave)
    # ⚠️ Os dois sinais abaixo são OPCIONAIS no repositório de propósito. Um
    # repositório que não os implementa produz `None` e
    # `QuadroDeRecomendacoes()` — que a sentinela lê como "não apurei", e NÃO
    # como "não há". Exigi-los no Protocol quebraria todo dublê existente e
    # trocaria uma ausência honesta por um erro de integração.
    horas_ligada = await _horas_ligada(repositorio, chave, agora)
    recomendacoes = await _recomendacoes(repositorio, str(campanha.get("customer_id") or ""))
    customer_id = str(campanha.get("customer_id") or "")
    nome = str(campanha.get("nome") or "campanha sem nome")
    moeda = campanha.get("moeda") or None
    if coleta is None:
        diagnostico = DiagnosticoDeEntrega(
            volc_campaign_id=chave, customer_id=customer_id, nome_campanha=nome,
            moeda=moeda, estado_coleta=None, frescor="nao_apurado",
            janela="coleta ainda não executada", leitura=None,
            degraus=_degraus_sem_coleta("coleta ainda não executada"), parcial=True,
        )
        return RespostaDoDiagnostico(
            diagnostico=diagnostico,
            propostas=CaixaDePropostas(volc_campaign_id=chave, leitura=None),
            # ⚠️ A sentinela é emitida TAMBÉM aqui. Omiti-la quando não há coleta
            # deixaria a superfície sem veredito exatamente no caso em que o
            # silêncio mais se parece com saúde.
            sentinela=_veredito(montar_leitura_da_sentinela(
                chave=chave, customer_id=customer_id, estado_coleta=None,
                frescor="nao_apurado", leitura=None, coleta=None, itens=[],
                metricas={}, campaign_id=str(campanha.get("campaign_id") or ""),
                horas_ligada=horas_ligada,
            )),
        )

    estado = str(coleta.get("estado") or "")
    if estado not in ESTADOS_COLETA:
        raise ServicoIndisponivelError("A coleta persistida contém estado fora do contrato v12.")
    leitura = _leitura(coleta.get("coletada_em"), agora)
    if leitura is None:
        raise ServicoIndisponivelError("A coleta v12 não possui coletada_em válido.")
    janela = _janela(coleta)
    campaign_id = str(campanha.get("campaign_id") or "")
    identidade_esperada = {
        "volc_campaign_id": chave,
        "customer_id": customer_id,
        "campaign_id": campaign_id,
    }
    for campo, esperado in identidade_esperada.items():
        observado = str(coleta.get(campo) or "")
        if not esperado or observado != esperado:
            raise ServicoIndisponivelError(
                f"A identidade '{campo}' da coleta v12 diverge da campanha canônica."
            )
    frescor = _frescor(leitura)
    if estado != "falhou" and frescor == "velho":
        motivo = (
            f"leitura antiga: {leitura.idade_s}s excedem o limite canônico de "
            f"{inventario.SEGUNDOS_PARA_VELHO}s"
        )
        diagnostico = DiagnosticoDeEntrega(
            volc_campaign_id=chave, customer_id=customer_id, nome_campanha=nome,
            moeda=moeda, estado_coleta=estado, frescor="velho", janela=janela,
            leitura=leitura, degraus=_degraus_sem_coleta(motivo), parcial=True,
        )
        return RespostaDoDiagnostico(
            diagnostico=diagnostico,
            propostas=CaixaDePropostas(volc_campaign_id=chave, leitura=None),
            sentinela=_veredito(montar_leitura_da_sentinela(
                chave=chave, customer_id=customer_id, estado_coleta=estado,
                frescor="velho", leitura=leitura, coleta=coleta, itens=[],
                metricas={}, campaign_id=campaign_id, horas_ligada=horas_ligada,
            )),
        )
    if estado in {"falhou", "inelegivel", "nao_suportado", "vazio_confirmado"}:
        motivos = {
            "falhou": "a coleta terminou em falhou",
            "inelegivel": "a coleta declarou a campanha inelegível para este sinal",
            "nao_suportado": "a coleta declarou este diagnóstico não suportado",
            "vazio_confirmado": "a conta respondeu e não devolveu a linha-base da campanha",
        }
        motivo = motivos[estado]
        codigo = coleta.get("erro_codigo") or coleta.get("erro_classe")
        if estado == "falhou" and codigo:
            motivo = f"{motivo} ({codigo})"
        leitura_diagnostico = None if estado == "falhou" else leitura
        if estado == "falhou" and leitura is not None:
            motivo = f"{motivo}; tentativa registrada em {leitura.lido_em}"
        diagnostico = DiagnosticoDeEntrega(
            volc_campaign_id=chave, customer_id=customer_id, nome_campanha=nome,
            moeda=moeda, estado_coleta=estado,
            frescor="nao_apurado" if estado == "falhou" else frescor,
            janela=janela, leitura=leitura_diagnostico,
            degraus=_degraus_sem_coleta(motivo), parcial=True,
        )
        return RespostaDoDiagnostico(
            diagnostico=diagnostico,
            propostas=CaixaDePropostas(
                volc_campaign_id=chave, leitura=None if estado == "falhou" else leitura,
            ),
            sentinela=_veredito(montar_leitura_da_sentinela(
                chave=chave, customer_id=customer_id, estado_coleta=estado,
                frescor="nao_apurado" if estado == "falhou" else frescor,
                leitura=leitura_diagnostico, coleta=coleta, itens=[], metricas={},
                campaign_id=campaign_id, horas_ligada=horas_ligada,
            )),
        )

    coleta_id = str(coleta.get("coleta_id") or "")
    if not coleta_id:
        raise ServicoIndisponivelError("A coleta v12 não possui coleta_id.")
    itens = await repositorio.itens(coleta_id)
    metricas = await repositorio.metricas(coleta_id)
    metricas_por_nome = _mapa_metricas(metricas, campaign_id)
    degraus = _degraus_observados(
        estado, itens, metricas_por_nome, janela, leitura, campaign_id,
    )
    moeda_medida = next(
        (
            m.get("moeda") for m in metricas_por_nome.values()
            if m.get("moeda") and m.get("estado_valor") == "medido"
        ),
        None,
    )
    diagnostico = DiagnosticoDeEntrega(
        volc_campaign_id=chave, customer_id=customer_id, nome_campanha=nome,
        moeda=moeda_medida or moeda, estado_coleta=estado, frescor=frescor,
        janela=janela, leitura=leitura, degraus=degraus,
        parcial=(estado == "parcial" or any(d.estado == "nao_apurado" for d in degraus)),
    )
    return RespostaDoDiagnostico(
        diagnostico=diagnostico,
        propostas=CaixaDePropostas(volc_campaign_id=chave, leitura=leitura),
        sentinela=_veredito(montar_leitura_da_sentinela(
            chave=chave, customer_id=customer_id, estado_coleta=estado,
            frescor=frescor, leitura=leitura, coleta=coleta, itens=itens,
            metricas=metricas_por_nome, campaign_id=campaign_id,
            horas_ligada=horas_ligada, recomendacoes=recomendacoes,
        )),
    )


SupabaseRepositorioLedger = SupabaseRepositorioDiagnostico
DiagnosticoCampanhaResposta = RespostaDoDiagnostico
