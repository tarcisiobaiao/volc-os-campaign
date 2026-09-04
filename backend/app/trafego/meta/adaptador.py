"""Read-only Graph API adapter with an injected transport.

There is no constructor that reads environment variables and no fallback HTTP
client.  A caller must provide both the client and an ephemeral secret.  This
keeps tests hermetic and prevents the package from touching Meta by import.
"""
from __future__ import annotations

from dataclasses import dataclass
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

    async def _listar_edge(
        self, conta: str, tipo: str, segredo: SegredoEfemero,
    ) -> tuple[tuple[dom.ObjetoMeta, ...], int]:
        url = f"{self._base}/{self._versao}/act_{conta}/{_EDGES[tipo]}"
        cursor: str | None = None
        vistos: set[str] = set()
        objetos: list[dom.ObjetoMeta] = []
        paginas = 0
        while True:
            if paginas >= self._max_paginas:
                raise ErroDeLeituraMeta(
                    "META_PAGINATION_LIMIT", "limite seguro de paginas excedido", True)
            params: dict[str, Any] = {
                "fields": _FIELDS[tipo],
                "limit": self._limite,
            }
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
            for linha in corpo["data"]:
                obj = self._normalizar(tipo, linha)
                if obj.id_externo in vistos:
                    raise ErroDeLeituraMeta(
                        "META_DUPLICATE_OBJECT", "objeto repetido entre paginas", True)
                vistos.add(obj.id_externo)
                objetos.append(obj)
            proximo = self._cursor(corpo)
            if proximo is None:
                return tuple(objetos), paginas
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
