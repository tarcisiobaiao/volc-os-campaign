"""Persistencia atomica no Supabase oficial via RPC PostgREST."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .modelo import DocumentoColeta


class ErroPersistenciaGoogle(RuntimeError):
    pass


@dataclass(frozen=True)
class CampanhaAtiva:
    volc_campaign_id: str
    campaign_id: str
    customer_id: str
    nome: str
    canal: str


class SupabaseGoogleIntelligence:
    def __init__(self, url: str | None = None, service_key: str | None = None) -> None:
        self.url = (url or os.getenv("VITE_SUPABASE_URL") or "").rstrip("/")
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        if self.url != "https://database.agenciavolc.com.br":
            raise ErroPersistenciaGoogle(
                "autoridade recusada: VITE_SUPABASE_URL precisa ser https://database.agenciavolc.com.br"
            )
        if not self.service_key:
            raise ErroPersistenciaGoogle("SUPABASE_SERVICE_ROLE_KEY ausente")

    def _request(self, path: str, *, method: str = "GET", body: Any = None) -> Any:
        dados = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        request = Request(
            f"{self.url}/rest/v1/{path}", data=dados, method=method,
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                raw = response.read()
        except HTTPError as exc:
            detalhe = exc.read().decode(errors="replace")[:800]
            raise ErroPersistenciaGoogle(f"PostgREST HTTP {exc.code}: {detalhe}") from exc
        except URLError as exc:
            raise ErroPersistenciaGoogle(f"PostgREST indisponivel: {exc.reason}") from exc
        return json.loads(raw) if raw else None

    def campanhas_search_ativas(self, customer_id: str | None = None) -> list[CampanhaAtiva]:
        parametros = {
            "select": "volc_campaign_id,campaign_id,customer_id,nome,canal,estado_externo",
            "estado_externo": "eq.ENABLED",
            "canal": "eq.SEARCH",
            "order": "customer_id.asc,campaign_id.asc",
        }
        if customer_id:
            parametros["customer_id"] = f"eq.{customer_id}"
        linhas = self._request(
            "trafego_inventario_campanha?" + urlencode(parametros, safe=".,")
        )
        return [
            CampanhaAtiva(
                volc_campaign_id=str(linha["volc_campaign_id"]),
                campaign_id=str(linha["campaign_id"]),
                customer_id=str(linha["customer_id"]),
                nome=str(linha["nome"]),
                canal=str(linha["canal"]),
            )
            for linha in linhas
        ]

    def registrar(self, documento: DocumentoColeta) -> str:
        resposta = self._request(
            "rpc/volc_registrar_google_inteligencia",
            method="POST",
            body={"documento": documento.serializar()},
        )
        if not isinstance(resposta, str):
            raise ErroPersistenciaGoogle(f"RPC devolveu identificador invalido: {type(resposta).__name__}")
        return resposta
