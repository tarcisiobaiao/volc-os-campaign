"""Persistencia atomica no Supabase oficial via RPC PostgREST."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .alvo import AlvoColeta, ErroAlvoDivergente, conferir_identidade_devolvida
from .modelo import DocumentoColeta

CAMPOS_INVENTARIO = "volc_campaign_id,campaign_id,customer_id,nome,canal,estado_externo"


class ErroPersistenciaGoogle(RuntimeError):
    pass


@dataclass(frozen=True)
class CampanhaAtiva:
    volc_campaign_id: str
    campaign_id: str
    customer_id: str
    nome: str
    canal: str
    # Estado externo observado no inventario. O scan continuo so traz ENABLED;
    # o caminho one-shot traz o que o alvo for — e precisa dizer qual foi.
    estado_externo: str | None = None


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
        """Agenda continua. Deliberadamente restrita a ENABLED + SEARCH.

        Nao amplie este filtro para alcancar uma campanha pausada: quem chama
        aqui e a varredura agendada, e ampliar gasta cota de toda a carteira a
        cada rodada. Para uma PAUSED nomeada existe ``campanha_por_identidade``.
        """

        parametros = {
            "select": CAMPOS_INVENTARIO,
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
                estado_externo=(
                    None if linha.get("estado_externo") is None
                    else str(linha["estado_externo"])
                ),
            )
            for linha in linhas
        ]

    def campanha_por_identidade(self, alvo: AlvoColeta) -> CampanhaAtiva:
        """Resolve UMA campanha nomeada, em qualquer estado externo.

        Sem filtro de ``estado_externo``: e exatamente isso que torna a PAUSED
        alcancavel. O que substitui o filtro como protecao e a identidade
        completa — conta, ID interno e ID externo — mais a reconferencia do que
        o inventario devolveu. Zero, duas ou uma linha divergente falham fechado
        antes de qualquer chamada ao Google Ads.
        """

        if not isinstance(alvo, AlvoColeta):
            raise ErroAlvoDivergente("alvo precisa ser AlvoColeta")
        parametros = {
            "select": CAMPOS_INVENTARIO,
            "customer_id": f"eq.{alvo.customer_id}",
            "volc_campaign_id": f"eq.{alvo.volc_campaign_id}",
            "campaign_id": f"eq.{alvo.campaign_id}",
            # 2 e suficiente para provar ambiguidade sem paginar a carteira.
            "limit": "2",
        }
        linhas = self._request(
            "trafego_inventario_campanha?" + urlencode(parametros, safe=".,")
        )
        if not linhas:
            raise ErroAlvoDivergente(
                "nenhuma campanha no inventario com essa identidade e conta"
            )
        if len(linhas) > 1:
            raise ErroAlvoDivergente(
                "identidade resolve para mais de uma campanha; recusado"
            )
        linha = linhas[0]
        canal = conferir_identidade_devolvida(alvo, linha)
        estado_externo = linha.get("estado_externo")
        return CampanhaAtiva(
            volc_campaign_id=alvo.volc_campaign_id,
            campaign_id=alvo.campaign_id,
            customer_id=alvo.customer_id,
            nome=str(linha.get("nome") or ""),
            canal=canal,
            estado_externo=None if estado_externo is None else str(estado_externo),
        )

    def registrar(self, documento: DocumentoColeta) -> str:
        resposta = self._request(
            "rpc/volc_registrar_google_inteligencia",
            method="POST",
            body={"documento": documento.serializar()},
        )
        if not isinstance(resposta, str):
            raise ErroPersistenciaGoogle(f"RPC devolveu identificador invalido: {type(resposta).__name__}")
        return resposta
