"""Transporte HTTP da Data Manager API (`datamanager.googleapis.com/v1`).

Fino de propósito: monta nada e decide nada. Recebe o corpo pronto, faz o POST
e traduz a resposta em `RespostaDeIngestao`, separando três estados que um
`try/except` genérico colapsaria:

    2xx           respondeu e aceitou (tem `requestId`, pode ter `fieldWarnings`)
    4xx           respondeu e recusou (fast-fail: o pedido inteiro foi rejeitado)
    5xx / rede    NÃO respondeu: ignorância, nunca "falhou, tente de novo"

A credencial não mora aqui. Quem constrói o transporte injeta `obter_token`
(escopo `https://www.googleapis.com/auth/datamanager`). Na nuvem e nos testes
não há token: os testes usam `httpx.MockTransport`.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

import httpx

from ..application.portas import NaoSaiu, RespostaDeIngestao, StatusDoPedido

BASE = "https://datamanager.googleapis.com/v1"
ESCOPO = "https://www.googleapis.com/auth/datamanager"


def _json(resp: httpx.Response) -> Dict[str, Any]:
    try:
        corpo = resp.json()
    except ValueError:
        return {"texto": resp.text[:2000]}
    return corpo if isinstance(corpo, dict) else {"corpo": corpo}


class TransporteHttp:
    def __init__(self, *, obter_token: Callable[[], str],
                 cliente: Optional[httpx.Client] = None,
                 base: str = BASE, timeout_s: float = 60.0) -> None:
        self._obter_token = obter_token
        self._cliente = cliente or httpx.Client(timeout=timeout_s)
        self._base = base.rstrip("/")

    def _cabecalhos(self) -> Dict[str, str]:
        try:
            token = self._obter_token()
        except Exception as exc:  # noqa: BLE001 — falha de credencial é ANTES do envio
            raise NaoSaiu(f"credencial da Data Manager falhou ({type(exc).__name__}): nada foi enviado") from exc
        if not str(token or "").strip():
            raise NaoSaiu("sem token da Data Manager: nada foi enviado")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def ingerir(self, corpo: Mapping[str, Any]) -> RespostaDeIngestao:
        cabecalhos = self._cabecalhos()
        try:
            resp = self._cliente.post(f"{self._base}/events:ingest", json=dict(corpo),
                                      headers=cabecalhos)
        except httpx.TransportError as exc:
            return RespostaDeIngestao(respondeu=False, aceito=False,
                                      erro={"tipo": type(exc).__name__, "mensagem": str(exc)[:500]})
        dados = _json(resp)
        if resp.status_code >= 500:
            return RespostaDeIngestao(respondeu=False, aceito=False, status_http=resp.status_code,
                                      erro=dados.get("error") or dados, corpo=dados)
        if resp.status_code >= 400:
            return RespostaDeIngestao(respondeu=True, aceito=False, status_http=resp.status_code,
                                      erro=dados.get("error") or dados, corpo=dados)
        # ⚠️ Só 2xx com corpo JSON objeto é aceite. Um 3xx (login, proxy) não é
        # o Google dizendo "ok"; é ninguém dizendo nada. (Revisão W14, achado 3.)
        if not (200 <= resp.status_code < 300) or "texto" in dados or "corpo" in dados:
            return RespostaDeIngestao(respondeu=False, aceito=False, status_http=resp.status_code,
                                      erro={"motivo": "resposta fora de 2xx JSON"}, corpo={})
        return RespostaDeIngestao(
            respondeu=True, aceito=True, status_http=resp.status_code,
            request_id=dados.get("requestId"),
            avisos=tuple(dados.get("fieldWarnings") or ()), corpo=dados)

    def status(self, request_id: str) -> StatusDoPedido:
        resp = self._cliente.get(f"{self._base}/requestStatus:retrieve",
                                 params={"requestId": request_id},
                                 headers=self._cabecalhos())
        resp.raise_for_status()
        dados = _json(resp)
        estados = [d.get("requestStatus") for d in dados.get("requestStatusPerDestination") or ()]
        return StatusDoPedido(estado=agregar(estados), corpo=dados)


#: O guia de diagnóstico diz FAILURE; a referência REST pode escrever FAILED.
#: Os dois são falha. Qualquer outro valor é recusado, nunca adivinhado.
_CONHECIDOS = {"PROCESSING": "PROCESSING", "SUCCESS": "SUCCESS", "FAILURE": "FAILURE",
               "FAILED": "FAILURE", "PARTIAL_SUCCESS": "PARTIAL_SUCCESS"}


class StatusDesconhecido(ValueError):
    """A Data Manager devolveu um estado fora do enum documentado (ou nenhum)."""


def agregar(estados) -> str:
    """Um estado para o lote a partir dos estados por destino. Desconhecido levanta."""
    lista = list(estados)
    if not lista:
        raise StatusDesconhecido("requestStatus sem estado por destino")
    normal = []
    for e in lista:
        if e not in _CONHECIDOS:
            raise StatusDesconhecido(f"estado {e!r} fora do enum documentado")
        normal.append(_CONHECIDOS[e])
    if "PROCESSING" in normal:
        return "PROCESSING"
    if all(e == "SUCCESS" for e in normal):
        return "SUCCESS"
    if all(e == "FAILURE" for e in normal):
        return "FAILURE"
    return "PARTIAL_SUCCESS"
