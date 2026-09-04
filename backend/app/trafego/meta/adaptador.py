"""Read-only Graph API adapter with an injected transport.

There is no constructor that reads environment variables and no fallback HTTP
client.  A caller must provide both the client and an ephemeral secret.  This
keeps tests hermetic and prevents the package from touching Meta by import.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from . import dominio as dom
from .credenciais import SegredoEfemero


@dataclass(frozen=True)
class ErroDeLeituraMeta(RuntimeError):
    codigo: str
    mensagem_segura: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.codigo}: {self.mensagem_segura}"


_FIELDS: Mapping[str, str] = {
    "campaign": "id,name,status,effective_status,objective",
    "adset": "id,name,status,effective_status,campaign_id,optimization_goal",
    "ad": "id,name,status,effective_status,adset_id,creative",
    "creative": "id,name,object_story_id",
}
_EDGES: Mapping[str, str] = {
    "campaign": "campaigns",
    "adset": "adsets",
    "ad": "ads",
    "creative": "adcreatives",
}
_CAPABILIDADES_DE_LEITURA = {
    "campaign": "META_READ_CAMPAIGNS",
    "adset": "META_READ_ADSETS",
    "ad": "META_READ_ADS",
    "creative": "META_READ_CREATIVES",
    "page": "META_READ_PAGES",
    "instagram": "META_READ_INSTAGRAM",
    "pixel": "META_READ_PIXEL_DATASET",
    "insights": "META_READ_INSIGHTS",
    "custom_conversion": "META_READ_CUSTOM_CONVERSIONS",
}


class AdaptadorMetaSomenteLeitura:
    def __init__(
        self,
        cliente: httpx.AsyncClient,
        *,
        api_version: str = "v26.0",
        base_url: str = "https://graph.facebook.com",
        limite_por_pagina: int = 100,
        max_paginas_por_edge: int = 500,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.hostname != "graph.facebook.com":
            raise ValueError("base Meta precisa ser https://graph.facebook.com")
        if not api_version.startswith("v") or not api_version[1:].replace(".", "").isdigit():
            raise ValueError("versao Graph invalida")
        if limite_por_pagina < 1 or max_paginas_por_edge < 1:
            raise ValueError("limites de paginacao precisam ser positivos")
        self._cliente = cliente
        self._base = base_url.rstrip("/")
        self._versao = api_version
        self._limite = limite_por_pagina
        self._max_paginas = max_paginas_por_edge

    async def descobrir_contas(self, segredo: SegredoEfemero) -> tuple[dom.ContaMetaDescoberta, ...]:
        linhas, _ = await self._listar_url(
            f"{self._base}/{self._versao}/me/adaccounts",
            segredo,
            fields="id,name,account_status,currency,timezone_name,business{id,name}",
            limite=min(self._limite, 100),
        )
        contas: list[dom.ContaMetaDescoberta] = []
        for linha in linhas:
            if not isinstance(linha, dict):
                raise ErroDeLeituraMeta("META_INVALID_RESPONSE", "conta Meta invalida", True)
            business = linha.get("business")
            conta_business = None
            if isinstance(business, dict) and business.get("id"):
                conta_business = dom.BusinessMeta(
                    id_externo=str(business.get("id")), nome=business.get("name"))
            try:
                contas.append(dom.ContaMetaDescoberta(
                    id_externo=str(linha.get("id")),
                    nome=linha.get("name"),
                    status=dom.texto_opcional(linha.get("account_status")),
                    moeda=linha.get("currency"),
                    fuso=linha.get("timezone_name"),
                    business=conta_business,
                ))
            except dom.ContratoMetaInvalido as exc:
                raise ErroDeLeituraMeta("META_INVALID_RESPONSE", str(exc), True) from None
        return tuple(contas)

    @staticmethod
    def resolver_referencia_opaca(
        contas: tuple[dom.ContaMetaDescoberta, ...], referencia_opaca: str,
    ) -> dom.ContaMetaDescoberta:
        for conta in contas:
            if conta.referencia_opaca == referencia_opaca:
                return conta
        raise dom.ContratoMetaInvalido("referencia opaca Meta desconhecida para este operador")

    async def preflight_conta(
        self, referencia_opaca: str, segredo: SegredoEfemero,
    ) -> Mapping[str, Any]:
        contas = await self.descobrir_contas(segredo)
        conta = self.resolver_referencia_opaca(contas, referencia_opaca)
        disponiveis: list[str] = ["META_READ_ACCOUNT"]
        ausentes: list[str] = ["META_CREATE_PAUSED", "META_ENABLE", "META_MUTATE"]
        erros: list[Mapping[str, str]] = []
        contagens: dict[str, int | None] = {}
        paginas_lidas = 0
        for tipo in dom.TIPOS_DE_OBJETO:
            try:
                objetos, paginas = await self._listar_edge(conta.id_externo, tipo, segredo)
                contagens[tipo] = len(objetos)
                paginas_lidas += paginas
                disponiveis.append(_CAPABILIDADES_DE_LEITURA[tipo])
            except ErroDeLeituraMeta as exc:
                contagens[tipo] = None
                ausentes.append(_CAPABILIDADES_DE_LEITURA[tipo])
                erros.append({"capability": _CAPABILIDADES_DE_LEITURA[tipo], "codigo": exc.codigo, "mensagem": exc.mensagem_segura})
        for capability, edge in (("page", "promote_pages"), ("instagram", "instagram_accounts"), ("pixel", "adspixels")):
            try:
                linhas, paginas = await self._listar_url(
                    f"{self._base}/{self._versao}/act_{conta.id_externo}/{edge}",
                    segredo,
                    fields="id,name",
                    limite=25,
                )
                contagens[capability] = len(linhas)
                paginas_lidas += paginas
                disponiveis.append(_CAPABILIDADES_DE_LEITURA[capability])
            except ErroDeLeituraMeta as exc:
                contagens[capability] = None
                ausentes.append(_CAPABILIDADES_DE_LEITURA[capability])
                erros.append({"capability": _CAPABILIDADES_DE_LEITURA[capability], "codigo": exc.codigo, "mensagem": exc.mensagem_segura})
        try:
            conversoes, paginas = await self.ler_conversoes_personalizadas(
                conta.id_externo, segredo)
            contagens["custom_conversion"] = len(conversoes)
            paginas_lidas += paginas
            disponiveis.append("META_READ_CUSTOM_CONVERSIONS")
        except ErroDeLeituraMeta as exc:
            conversoes = ()
            contagens["custom_conversion"] = None
            ausentes.append("META_READ_CUSTOM_CONVERSIONS")
            erros.append({
                "capability": "META_READ_CUSTOM_CONVERSIONS",
                "codigo": exc.codigo,
                "mensagem": exc.mensagem_segura,
            })
        try:
            insights, paginas = await self.ler_insights(
                conta.id_externo,
                segredo,
                nivel="account",
                periodo_inicio=date.today(),
                periodo_fim=date.today(),
            )
            contagens["insights"] = len(insights)
            paginas_lidas += paginas
            disponiveis.append("META_READ_INSIGHTS")
        except ErroDeLeituraMeta as exc:
            contagens["insights"] = None
            ausentes.append("META_READ_INSIGHTS")
            erros.append({"capability": "META_READ_INSIGHTS", "codigo": exc.codigo, "mensagem": exc.mensagem_segura})
        return {
            "ok": True,
            "api_version": self._versao,
            "referencia_opaca": conta.referencia_opaca,
            "conta": conta.publico(),
            "contagens": contagens,
            "estados": {"readiness": conta.prontidao_leitura, "persistencia": "NAO_PERSISTIDO"},
            "capacidades_disponiveis": sorted(set(disponiveis)),
            "capacidades_ausentes": sorted(set(ausentes)),
            "frescor": datetime.now(timezone.utc).isoformat(),
            "paginas_lidas": paginas_lidas,
            "erros": erros,
            "mensuracao": {
                "pixels_ou_datasets": contagens.get("pixel"),
                "conversoes_personalizadas": [dict(item) for item in conversoes],
            },
            "proxima_acao": "preparar_sincronizacao" if not erros else "corrigir_capacidades_ausentes",
        }

    async def ler_conversoes_personalizadas(
        self, conta_externa: str, segredo: SegredoEfemero,
    ) -> tuple[tuple[Mapping[str, Any], ...], int]:
        """Read a sanitized custom-conversion inventory for operator preflight.

        The rule itself is deliberately not returned to the browser. Availability
        and firing timestamps are enough for planning; creation remains a
        separate, absent mutation.
        """
        conta = dom.conta_canonica(conta_externa)
        linhas, paginas = await self._listar_url(
            f"{self._base}/{self._versao}/act_{conta}/customconversions",
            segredo,
            fields=(
                "id,name,custom_event_type,event_source_type,event_source_id,"
                "is_archived,is_unavailable,first_fired_time,last_fired_time"
            ),
            limite=min(self._limite, 100),
        )
        saida: list[Mapping[str, Any]] = []
        for linha in linhas:
            if not isinstance(linha, dict):
                raise ErroDeLeituraMeta(
                    "META_INVALID_RESPONSE", "conversao personalizada invalida", True)
            try:
                identificador = dom.id_externo(
                    linha.get("id"), campo="custom_conversion.id")
                fonte = linha.get("event_source_id")
                fonte_mascarada = dom.mascarar_id(
                    dom.id_externo(fonte, campo="custom_conversion.event_source_id")
                ) if fonte not in (None, "") else None
            except dom.ContratoMetaInvalido as exc:
                raise ErroDeLeituraMeta(
                    "META_INVALID_RESPONSE", str(exc), True) from None
            arquivada = bool(linha.get("is_archived"))
            indisponivel = bool(linha.get("is_unavailable"))
            primeiro = dom.texto_opcional(linha.get("first_fired_time"))
            ultimo = dom.texto_opcional(linha.get("last_fired_time"))
            if arquivada:
                estado = "ARCHIVED"
            elif indisponivel:
                estado = "UNAVAILABLE"
            elif ultimo is None:
                estado = "AVAILABLE_NEVER_FIRED"
            else:
                estado = "AVAILABLE_FIRED"
            saida.append({
                "referencia_opaca": dom.referencia_opaca_objeto(
                    conta, "custom_conversion", identificador),
                "id_mascarado": dom.mascarar_id(identificador),
                "nome": dom.texto_opcional(linha.get("name")) or "Conversao sem nome",
                "custom_event_type": dom.texto_opcional(linha.get("custom_event_type")),
                "event_source_type": dom.texto_opcional(linha.get("event_source_type")),
                "event_source_id_mascarado": fonte_mascarada,
                "first_fired_time": primeiro,
                "last_fired_time": ultimo,
                "estado": estado,
            })
        return tuple(saida), paginas

    async def ler_hierarquia(
        self, conta_externa: str, segredo: SegredoEfemero,
    ) -> dom.LeituraDaHierarquia:
        conta = dom.conta_canonica(conta_externa)
        todos: dict[str, tuple[dom.ObjetoMeta, ...]] = {}
        paginas = 0
        for tipo in dom.TIPOS_DE_OBJETO:
            objetos, lidas = await self._listar_edge(conta, tipo, segredo)
            todos[tipo] = objetos
            paginas += lidas
        return dom.LeituraDaHierarquia(
            conta_externa=conta,
            campanhas=todos["campaign"],
            conjuntos=todos["adset"],
            anuncios=todos["ad"],
            criativos=todos["creative"],
            paginas_lidas=paginas,
        )

    async def ler_insights(
        self,
        conta_externa: str,
        segredo: SegredoEfemero,
        *,
        nivel: str,
        periodo_inicio: date,
        periodo_fim: date,
        breakdown: str = "none",
        janela_atribuicao: str = "default",
    ) -> tuple[tuple[dom.InsightMeta, ...], int]:
        conta = dom.conta_canonica(conta_externa)
        params_extra: dict[str, Any] = {
            "level": nivel,
            # Graph accepts JSON here. httpx coercion of a Python dict emits
            # single quotes and the remote API rejects it.
            "time_range": json.dumps(
                {"since": periodo_inicio.isoformat(), "until": periodo_fim.isoformat()},
                separators=(",", ":"),
            ),
            "fields": "account_id,campaign_id,adset_id,ad_id,date_start,date_stop,spend,impressions,reach,frequency,clicks,inline_link_clicks,cpm,cpc,ctr,actions",
            "limit": self._limite,
        }
        if breakdown != "none":
            params_extra["breakdowns"] = breakdown
        linhas, paginas = await self._listar_url(
            f"{self._base}/{self._versao}/act_{conta}/insights",
            segredo,
            fields=None,
            limite=self._limite,
            parametros_extra=params_extra,
        )
        observacao = datetime.now(timezone.utc)
        saida: list[dom.InsightMeta] = []
        for linha in linhas:
            if not isinstance(linha, dict):
                raise ErroDeLeituraMeta("META_INVALID_RESPONSE", "insight invalido", True)
            try:
                objeto = linha.get(f"{nivel}_id") or linha.get("account_id") or conta
                actions = tuple(
                    dom.AcaoInsightMeta(
                        action_type=str(a.get("action_type") or "unknown"),
                        value=dom.decimal_opcional(a.get("value"), campo="action.value"),
                        attribution_window=str(a.get("attribution_window") or janela_atribuicao),
                        object_level=nivel,
                        date_start=date.fromisoformat(str(linha.get("date_start") or periodo_inicio.isoformat())),
                        date_stop=date.fromisoformat(str(linha.get("date_stop") or periodo_fim.isoformat())),
                    )
                    for a in (linha.get("actions") or []) if isinstance(a, dict)
                )
                saida.append(dom.InsightMeta(
                    provider=dom.META_ADS,
                    conta_externa=conta,
                    nivel=nivel,
                    objeto_externo=str(objeto),
                    periodo_inicio=date.fromisoformat(str(linha.get("date_start") or periodo_inicio.isoformat())),
                    periodo_fim=date.fromisoformat(str(linha.get("date_stop") or periodo_fim.isoformat())),
                    janela_atribuicao=janela_atribuicao,
                    breakdown=breakdown,
                    observado_em=observacao,
                    spend=dom.decimal_opcional(linha.get("spend"), campo="spend"),
                    impressions=_int_opcional(linha.get("impressions")),
                    reach=_int_opcional(linha.get("reach")),
                    frequency=dom.decimal_opcional(linha.get("frequency"), campo="frequency"),
                    clicks=_int_opcional(linha.get("clicks")),
                    inline_link_clicks=_int_opcional(linha.get("inline_link_clicks")),
                    landing_page_views=_landing_page_views(actions),
                    cpm=dom.decimal_opcional(linha.get("cpm"), campo="cpm"),
                    cpc=dom.decimal_opcional(linha.get("cpc"), campo="cpc"),
                    ctr=dom.decimal_opcional(linha.get("ctr"), campo="ctr"),
                    actions=actions,
                ))
            except (ValueError, TypeError, dom.ContratoMetaInvalido) as exc:
                raise ErroDeLeituraMeta(
                    "META_INVALID_RESPONSE",
                    f"insight Meta invalido: {type(exc).__name__}",
                    True,
                ) from None
        return tuple(saida), paginas

    async def _listar_edge(
        self, conta: str, tipo: str, segredo: SegredoEfemero,
    ) -> tuple[tuple[dom.ObjetoMeta, ...], int]:
        linhas, paginas = await self._listar_url(
            f"{self._base}/{self._versao}/act_{conta}/{_EDGES[tipo]}",
            segredo,
            fields=_FIELDS[tipo],
            limite=self._limite,
        )
        objetos: list[dom.ObjetoMeta] = []
        vistos: set[str] = set()
        for linha in linhas:
            obj = self._normalizar(tipo, linha)
            if obj.id_externo in vistos:
                raise ErroDeLeituraMeta(
                    "META_DUPLICATE_OBJECT", "objeto repetido entre paginas", True)
            vistos.add(obj.id_externo)
            objetos.append(obj)
        return tuple(objetos), paginas

    async def _listar_url(
        self,
        url: str,
        segredo: SegredoEfemero,
        *,
        fields: str | None,
        limite: int,
        parametros_extra: Mapping[str, Any] | None = None,
    ) -> tuple[list[Any], int]:
        cursor: str | None = None
        linhas: list[Any] = []
        paginas = 0
        while True:
            if paginas >= self._max_paginas:
                raise ErroDeLeituraMeta(
                    "META_PAGINATION_LIMIT", "limite seguro de paginas excedido", True)
            params: dict[str, Any] = {"limit": limite}
            if fields is not None:
                params["fields"] = fields
            if parametros_extra:
                params.update(parametros_extra)
            if cursor:
                params["after"] = cursor
            try:
                resposta = await self._cliente.get(
                    url,
                    params=params,
                    headers={"Authorization": segredo.cabecalho_bearer()},
                )
            except (httpx.TimeoutException, httpx.NetworkError,
                    httpx.RemoteProtocolError) as exc:
                raise ErroDeLeituraMeta(
                    "META_TRANSPORT_FAILURE", type(exc).__name__, True) from None
            paginas += 1
            if resposta.status_code >= 400:
                raise self._erro_http(resposta.status_code)
            try:
                corpo = resposta.json()
            except ValueError:
                raise ErroDeLeituraMeta(
                    "META_INVALID_RESPONSE", "resposta nao e JSON", True) from None
            if not isinstance(corpo, dict) or not isinstance(corpo.get("data"), list):
                raise ErroDeLeituraMeta(
                    "META_INVALID_RESPONSE", "resposta sem lista data", True)
            linhas.extend(corpo["data"])
            proximo = self._cursor(corpo)
            if proximo is None:
                return linhas, paginas
            if proximo == cursor:
                raise ErroDeLeituraMeta(
                    "META_PAGINATION_LOOP", "cursor de paginacao nao avancou", True)
            cursor = proximo

    @staticmethod
    def _cursor(corpo: Mapping[str, Any]) -> str | None:
        paging = corpo.get("paging")
        if not isinstance(paging, dict) or not paging.get("next"):
            return None
        cursores = paging.get("cursors")
        after = cursores.get("after") if isinstance(cursores, dict) else None
        if not isinstance(after, str) or not after.strip():
            raise ErroDeLeituraMeta(
                "META_INVALID_PAGINATION", "paging.next sem cursor after", True)
        return after

    @staticmethod
    def _normalizar(tipo: str, linha: Any) -> dom.ObjetoMeta:
        if not isinstance(linha, dict):
            raise ErroDeLeituraMeta(
                "META_INVALID_RESPONSE", "objeto Meta nao e documento", True)
        try:
            externo = dom.id_externo(linha.get("id"))
            parent = None
            if tipo == "adset":
                parent = dom.id_externo(linha.get("campaign_id"), campo="campaign_id")
            elif tipo == "ad":
                parent = dom.id_externo(linha.get("adset_id"), campo="adset_id")
            creative_id = None
            if tipo == "ad" and isinstance(linha.get("creative"), dict):
                creative_id = dom.id_externo(
                    linha["creative"].get("id"), campo="creative.id")
            return dom.ObjetoMeta(
                tipo=tipo,
                id_externo=externo,
                nome=dom.texto_opcional(linha.get("name")),
                status=dom.texto_opcional(linha.get("status")),
                effective_status=dom.texto_opcional(linha.get("effective_status")),
                parent_id_externo=parent,
                objetivo=dom.texto_opcional(linha.get("objective")) if tipo == "campaign" else None,
                optimization_goal=(dom.texto_opcional(linha.get("optimization_goal"))
                                   if tipo == "adset" else None),
                object_story_id=(dom.texto_opcional(linha.get("object_story_id"))
                                 if tipo == "creative" else None),
                creative_id_externo=creative_id,
            )
        except dom.ContratoMetaInvalido as exc:
            raise ErroDeLeituraMeta(
                "META_INVALID_RESPONSE", str(exc), True) from None

    @staticmethod
    def _erro_http(status: int) -> ErroDeLeituraMeta:
        if status == 401:
            return ErroDeLeituraMeta(
                "META_AUTHENTICATION_FAILED", "Meta recusou a autenticacao", False)
        if status == 403:
            return ErroDeLeituraMeta(
                "META_PERMISSIONS_INSUFFICIENT", "permissao de leitura insuficiente", False)
        if status == 404:
            return ErroDeLeituraMeta(
                "META_ACCOUNT_INACCESSIBLE", "conta Meta nao acessivel", False)
        if status == 429:
            return ErroDeLeituraMeta(
                "META_RATE_LIMIT", "Meta limitou temporariamente a leitura", True)
        if status >= 500:
            return ErroDeLeituraMeta(
                "META_REMOTE_FAILURE", "Meta indisponivel temporariamente", True)
        return ErroDeLeituraMeta(
            "META_REQUEST_REJECTED", f"Meta recusou a leitura (HTTP {status})", False)


def _int_opcional(valor: Any) -> int | None:
    if valor is None or valor == "":
        return None
    return int(valor)


def _landing_page_views(actions: tuple[dom.AcaoInsightMeta, ...]) -> int | None:
    total = 0
    achou = False
    for acao in actions:
        if acao.action_type in {"landing_page_view", "offsite_conversion.fb_pixel_view_content"}:
            achou = True
            total += int(acao.value or 0)
    return total if achou else None
