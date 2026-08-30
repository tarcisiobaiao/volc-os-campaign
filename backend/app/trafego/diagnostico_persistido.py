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
from typing import Any, Dict, List, Literal, Optional, Protocol, Sequence

from pydantic import BaseModel, Field

from app.trafego import inventario

log = logging.getLogger("volc.trafego.diagnostico_persistido")

TIPO_SINAL = "DIAGNOSTICO_ENTREGA"
ESTADOS_COLETA = {
    "com_dados", "vazio_confirmado", "parcial", "inelegivel",
    "nao_suportado", "falhou",
}
EIXOS = (
    "conta", "campanha", "orcamento", "grupo", "anuncio", "keyword",
    "segmentacao", "conversao", "leilao",
)

COLUNAS_CAMPANHA = (
    "volc_campaign_id,customer_id,nome,moeda,canal,estado_externo,"
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
TIPOS_ITEM = {"campaign", "keyword", "ad"}
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
    janela: str
    leitura: Optional[Leitura]
    degraus: List[DegrauDeEntrega]
    parcial: bool


class CaixaDePropostas(BaseModel):
    versao: Literal[1] = 1
    volc_campaign_id: str
    propostas: List[Dict[str, Any]] = Field(default_factory=list)
    leitura: Optional[Leitura]


class RespostaDoDiagnostico(BaseModel):
    versao: Literal[1] = 1
    diagnostico: DiagnosticoDeEntrega
    propostas: CaixaDePropostas


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


def _mapa_metricas(linhas: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    saida: Dict[str, Dict[str, Any]] = {}
    for linha in linhas:
        nome = str(linha.get("nome") or "")
        if nome in METRICAS_PERMITIDAS and nome not in saida:
            saida[nome] = linha
    return saida


def _itens_por_tipo(linhas: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    saida = {tipo: [] for tipo in TIPOS_ITEM}
    for linha in linhas:
        tipo = str(linha.get("tipo_item") or "")
        if tipo not in TIPOS_ITEM:
            continue
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
    metricas: Sequence[Dict[str, Any]],
    janela: str,
    leitura: Optional[Leitura],
) -> List[DegrauDeEntrega]:
    por_tipo = _itens_por_tipo(itens)
    met = _mapa_metricas(metricas)
    degraus: Dict[str, DegrauDeEntrega] = {
        eixo: _nao_apurado(
            eixo, f"A coleta v12 não trouxe evidência suficiente para {eixo}.",
            "campo não colhido ou evidência insuficiente",
        ) for eixo in EIXOS
    }

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
        elif any(v in {"NOT_ELIGIBLE", "REMOVED", "ENDED"} for v in observados):
            estado, palavra, frase, impedimento = (
                "bloqueia", "não elegível", "A própria conta observou um estado que impede veiculação.", None,
            )
        elif any(v in {"LIMITED", "LEARNING"} for v in observados):
            estado, palavra, frase, impedimento = (
                "limita", "limitada", "A conta observou a campanha ligada, mas com limitação.", None,
            )
        elif all(v in {"ENABLED", "ELIGIBLE", "SERVING"} for v in observados):
            estado, palavra, frase, impedimento = (
                "ok", "ligada", "A conta observou a campanha ligada sem bloqueio nestes campos.", None,
            )
        else:
            estado, palavra, frase, impedimento = (
                "nao_apurado", "não apurado",
                "A campanha está ligada, mas a coleta não trouxe estado de veiculação.",
                "primary_status e serving_status ausentes",
            )
        degraus["campanha"] = DegrauDeEntrega(
            eixo="campanha", estado=estado, palavra=palavra, frase=frase,
            motivo_da_conta=[str(v) for v in motivos] if isinstance(motivos, list) else [str(motivos)],
            evidencias=evidencias, impedimento=impedimento,
        )

    orcamento = met.get("daily_budget_micros")
    perda = met.get("search_budget_lost_impression_share")
    evidencias_orcamento = []
    if orcamento:
        evidencias_orcamento.append(_evidencia_metrica(orcamento, "orçamento diário", janela, leitura))
    if perda:
        evidencias_orcamento.append(_evidencia_metrica(perda, "perda por orçamento", janela, leitura))
    perda_num = _valor_numerico(perda or {})
    if perda_num is not None:
        limita = perda_num > 0
        degraus["orcamento"] = DegrauDeEntrega(
            eixo="orcamento", estado="limita" if limita else "ok",
            palavra="perda medida" if limita else "sem perda medida",
            frase=("A conta mediu perda de participação por orçamento." if limita else
                   "A conta mediu zero de perda de participação por orçamento."),
            evidencias=evidencias_orcamento, impedimento=None,
        )
    elif evidencias_orcamento:
        degraus["orcamento"] = DegrauDeEntrega(
            eixo="orcamento", estado="nao_apurado", palavra="não apurado",
            frase="Há evidência de orçamento, mas a perda por orçamento não foi medida.",
            evidencias=evidencias_orcamento,
            impedimento="search_budget_lost_impression_share não medido",
        )

    for tipo, eixo, rotulo in (("ad", "anuncio", "anúncio"), ("keyword", "keyword", "keyword")):
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
            estados = [
                linha["campos"].get(campo)
                for linha in linhas for campo in campos_estado
            ]
            evidencias = [
                _evidencia(f"{rotulo} {i + 1}", campo, linha["campos"].get(campo), janela, leitura)
                for i, linha in enumerate(linhas) for campo in campos_estado
            ]
            normalizados = [str(v).upper() for v in estados if v is not None]
            negativos = {"DISABLED", "PAUSED", "REMOVED", "NOT_ELIGIBLE", "ENDED"}
            if any(v in negativos for v in normalizados):
                estado, palavra, frase = "bloqueia", "sem elegível", f"A conta observou {rotulo} não elegível."
            elif normalizados and all(v in {"ENABLED", "ELIGIBLE"} for v in normalizados):
                estado, palavra, frase = "ok", "presente", f"A conta observou {rotulo} habilitado."
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
        return await self._select("trafego_google_inteligencia_item", {
            "select": COLUNAS_ITEM, "coleta_id": f"eq.{coleta_id}", "order": "ordinal.asc",
        })

    async def metricas(self, coleta_id: str) -> List[Dict[str, Any]]:
        return await self._select("trafego_google_inteligencia_metrica", {
            "select": COLUNAS_METRICA, "coleta_id": f"eq.{coleta_id}", "order": "metrica_id.asc",
        })


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
    customer_id = str(campanha.get("customer_id") or "")
    nome = str(campanha.get("nome") or "campanha sem nome")
    moeda = campanha.get("moeda") or None
    if coleta is None:
        diagnostico = DiagnosticoDeEntrega(
            volc_campaign_id=chave, customer_id=customer_id, nome_campanha=nome,
            moeda=moeda, janela="coleta ainda não executada", leitura=None,
            degraus=_degraus_sem_coleta("coleta ainda não executada"), parcial=True,
        )
        return RespostaDoDiagnostico(
            diagnostico=diagnostico,
            propostas=CaixaDePropostas(volc_campaign_id=chave, leitura=None),
        )

    estado = str(coleta.get("estado") or "")
    if estado not in ESTADOS_COLETA:
        raise ServicoIndisponivelError("A coleta persistida contém estado fora do contrato v12.")
    leitura = _leitura(coleta.get("coletada_em"), agora)
    janela = _janela(coleta)
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
            moeda=moeda, janela=janela, leitura=leitura_diagnostico,
            degraus=_degraus_sem_coleta(motivo), parcial=True,
        )
        return RespostaDoDiagnostico(
            diagnostico=diagnostico,
            propostas=CaixaDePropostas(
                volc_campaign_id=chave, leitura=None if estado == "falhou" else leitura,
            ),
        )

    coleta_id = str(coleta.get("coleta_id") or "")
    if not coleta_id:
        raise ServicoIndisponivelError("A coleta v12 não possui coleta_id.")
    itens = await repositorio.itens(coleta_id)
    metricas = await repositorio.metricas(coleta_id)
    degraus = _degraus_observados(estado, itens, metricas, janela, leitura)
    moeda_medida = next(
        (m.get("moeda") for m in metricas if m.get("moeda") and m.get("estado_valor") == "medido"),
        None,
    )
    diagnostico = DiagnosticoDeEntrega(
        volc_campaign_id=chave, customer_id=customer_id, nome_campanha=nome,
        moeda=moeda_medida or moeda, janela=janela, leitura=leitura, degraus=degraus,
        parcial=(estado == "parcial" or any(d.estado == "nao_apurado" for d in degraus)),
    )
    return RespostaDoDiagnostico(
        diagnostico=diagnostico,
        propostas=CaixaDePropostas(volc_campaign_id=chave, leitura=leitura),
    )


SupabaseRepositorioLedger = SupabaseRepositorioDiagnostico
DiagnosticoCampanhaResposta = RespostaDoDiagnostico
