"""Adaptadores das portas de custo e receita.

- `SnapshotCusto` / `SnapshotReceita`: leem um JSON `{"lido_em", "fonte",
  "linhas": [...]}` exportado das tabelas do contrato. É o caminho do replay e
  dos testes, e é como a nuvem roda sem dado real.
- `PostgrestSoLeitura`: lê `google_ads_campanha_dia` e `receita_as_of()` pelo
  PostgREST do Supabase oficial com a service_role do AMBIENTE (nunca do
  repositório). Só faz GET na tabela e POST na RPC `receita_as_of`, que é
  STABLE; qualquer outro caminho é recusado antes da rede. Este adaptador não
  roda na nuvem: a prova dele é no Mac/Hetzner.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from volc_lab.sombra_carteira.portas import ContratoQuebrado, CustoDia, Leitura, ReceitaObservada

AUTORIDADE_SUPABASE = "database.agenciavolc.com.br"
PAGINA = 1000


def _ler_snapshot(caminho: Path) -> dict[str, Any]:
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("linhas"), list) or not doc.get("lido_em"):
        raise ContratoQuebrado(f"{caminho.name}: snapshot sem lido_em ou sem linhas")
    return doc


@dataclass(frozen=True)
class SnapshotCusto:
    caminho: Path

    def custo_campanha_dia(self, conta: str, inicio: date, fim: date) -> Leitura:
        doc = _ler_snapshot(self.caminho)
        return Leitura(tuple(doc["linhas"]), str(doc["lido_em"]),
                       str(doc.get("fonte") or f"snapshot {self.caminho.name}"))


@dataclass(frozen=True)
class SnapshotReceita:
    caminho: Path

    def receita_vigente(self, inicio: date, fim: date) -> Leitura:
        doc = _ler_snapshot(self.caminho)
        return Leitura(tuple(doc["linhas"]), str(doc["lido_em"]),
                       str(doc.get("fonte") or f"snapshot {self.caminho.name}"))


Transporte = Callable[[str, str, Mapping[str, str], Optional[bytes]], tuple[int, bytes]]


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Um 3xx levaria a service_role a outro host; vira erro, não redireciona."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar())


def _transporte_urllib(metodo: str, url: str, cabecalhos: Mapping[str, str],
                       corpo: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=dict(cabecalhos))
    try:
        with _ABRIDOR.open(req, timeout=60) as resp:  # noqa: S310 (URL validada no init)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        # 3xx (não seguido), 4xx e 5xx viram status: o chamador recusa com o código.
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ContratoQuebrado(f"leitura sem resposta: {exc}") from exc


@dataclass
class PostgrestSoLeitura:
    """Leitura do contrato pelo PostgREST. Recusa tudo que não seja leitura."""

    url_base: str
    chave_service_role: str
    transporte: Transporte = field(default=_transporte_urllib)
    chamadas: list[tuple[str, str]] = field(default_factory=list)

    _PERMITIDOS = {
        ("GET", "/rest/v1/google_ads_campanha_dia"),
        ("POST", "/rest/v1/rpc/receita_as_of"),
    }

    def __post_init__(self) -> None:
        partes = urllib.parse.urlsplit(self.url_base)
        if partes.scheme != "https" or partes.hostname != AUTORIDADE_SUPABASE:
            # ADR-SUPABASE-AUTORIDADE-OPERACIONAL: o único Supabase operacional.
            raise ValueError(f"Supabase fora da autoridade operacional: {partes.hostname!r}")
        if not self.chave_service_role:
            raise ValueError("service_role ausente no ambiente")

    def _pedir(self, metodo: str, caminho: str, consulta: dict[str, str],
               corpo: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        if (metodo, caminho) not in self._PERMITIDOS:
            raise PermissionError(f"{metodo} {caminho} não é leitura do contrato")
        linhas: list[dict[str, Any]] = []
        deslocamento = 0
        while True:
            q = {**consulta, "limit": str(PAGINA), "offset": str(deslocamento)}
            url = self.url_base.rstrip("/") + caminho + "?" + urllib.parse.urlencode(q, safe="(),.:*")
            cab = {"apikey": self.chave_service_role,
                   "Authorization": f"Bearer {self.chave_service_role}",
                   "Accept": "application/json",
                   "x-volc-proveniencia": "volc_lab.sombra_carteira"}
            dados = None
            if corpo is not None:
                cab["Content-Type"] = "application/json"
                dados = json.dumps(corpo).encode()
            self.chamadas.append((metodo, caminho))
            status, bruto = self.transporte(metodo, url, cab, dados)
            if status != 200:
                raise ContratoQuebrado(f"{caminho}: HTTP {status}")
            pagina = json.loads(bruto)
            if not isinstance(pagina, list):
                raise ContratoQuebrado(f"{caminho}: resposta não é lista")
            linhas.extend(pagina)
            if len(pagina) < PAGINA:
                return linhas
            deslocamento += PAGINA

    def custo_campanha_dia(self, conta: str, inicio: date, fim: date) -> Leitura:
        lido_em = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        linhas = self._pedir("GET", "/rest/v1/google_ads_campanha_dia", {
            "select": ",".join(CustoDia.CAMPOS),
            "customer_id": f"eq.{conta}",
            "and": f"(metric_date.gte.{inicio.isoformat()},metric_date.lte.{fim.isoformat()})",
            "order": "campaign_id.asc,metric_date.asc,fato_id.asc",
        })
        return Leitura(tuple(linhas), lido_em, "PostgREST google_ads_campanha_dia (v12_04)")

    def receita_vigente(self, inicio: date, fim: date) -> Leitura:
        lido_em = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # O instante da leitura vira o conhecido_ate: o replay pede o mesmo corte.
        linhas = self._pedir("POST", "/rest/v1/rpc/receita_as_of", {
            "select": ",".join(ReceitaObservada.CAMPOS),
            "and": f"(data_referencia.gte.{inicio.isoformat()},data_referencia.lte.{fim.isoformat()})",
            "order": "tabela_origem.asc,id.asc",
        }, {"p_conhecido_ate": lido_em, "p_fonte": None})
        return Leitura(tuple(linhas), lido_em, f"PostgREST receita_as_of(conhecido_ate={lido_em}) (v23_01)")
