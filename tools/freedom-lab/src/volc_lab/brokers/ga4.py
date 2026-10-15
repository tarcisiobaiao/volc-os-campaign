"""GA4 read-only: properties, streams, metadata e UMA consulta agregada sem PII.

Só GET no Admin API. O único POST é `properties/{id}:runReport` da Data API,
que é leitura. Relatório de prova sem dimensões = sem PII por construção.
Resposta sem linha devolve valores=None: ausência na janela, não zero.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .google_credencial import sessao as _sessao_padrao
from .recibos import agora_utc

ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
DATA = "https://analyticsdata.googleapis.com/v1beta"
GA_RO = "https://www.googleapis.com/auth/analytics.readonly"
_RUNREPORT = re.compile(r"^https://analyticsdata\.googleapis\.com/v1beta/properties/\d+:runReport$")

METRICAS_PERMITIDAS = frozenset({"sessions", "activeUsers", "screenPageViews", "conversions",
                                 "totalRevenue", "eventCount"})


@dataclass(frozen=True)
class InventarioGA4:
    contas: int
    properties: int
    streams: int
    erros_http: int
    em: str

    def recibo(self) -> dict:
        return {"broker": "ga4", "operacao": "leitura:inventario", **asdict(self)}


class ClienteGA4Leitura:
    def __init__(self, *, fabrica_sessao=_sessao_padrao):
        self._s = fabrica_sessao(frozenset({GA_RO}))

    def _get(self, url: str, **kw):
        return self._s.get(url, timeout=30, **kw)

    def _resumos(self) -> list[dict]:
        itens, token = [], None
        while True:
            params = {"pageSize": 200} | ({"pageToken": token} if token else {})
            r = self._get(f"{ADMIN}/accountSummaries", params=params)
            r.raise_for_status()
            d = r.json()
            itens += d.get("accountSummaries", [])
            token = d.get("nextPageToken")
            if not token:
                return itens

    def properties(self) -> list[str]:
        return [p["property"] for a in self._resumos() for p in a.get("propertySummaries", [])]

    def inventariar(self) -> InventarioGA4:
        resumos = self._resumos()
        props = [p["property"] for a in resumos for p in a.get("propertySummaries", [])]
        streams = erros = 0
        for p in props:
            token = None
            while True:
                s = self._get(f"{ADMIN}/{p}/dataStreams", params={"pageToken": token} if token else None)
                if s.status_code != 200:
                    erros += 1
                    break
                d = s.json()
                streams += len(d.get("dataStreams", []))
                token = d.get("nextPageToken")
                if not token:
                    break
        return InventarioGA4(len(resumos), len(props), streams, erros, agora_utc())

    def metadata(self, prop: str) -> dict:
        r = self._get(f"{DATA}/{prop}/metadata")
        r.raise_for_status()
        d = r.json()
        return {"dimensions": len(d.get("dimensions", [])), "metrics": len(d.get("metrics", []))}

    def agregado(self, prop: str, metricas: tuple[str, ...] = ("sessions",),
                 inicio: str = "7daysAgo", fim: str = "yesterday") -> dict:
        fora = set(metricas) - METRICAS_PERMITIDAS
        if fora:
            raise ValueError(f"métrica fora da lista: {sorted(fora)}")
        url = f"{DATA}/{prop}:runReport"
        if not _RUNREPORT.match(url):
            raise ValueError("property inválida para runReport")
        r = self._s.post(url, json={"dateRanges": [{"startDate": inicio, "endDate": fim}],
                                    "metrics": [{"name": m} for m in metricas]}, timeout=30)
        r.raise_for_status()
        linhas = r.json().get("rows", [])
        valores = ({m: v["value"] for m, v in zip(metricas, linhas[0]["metricValues"])}
                   if linhas else None)
        return {"tem_linha": bool(linhas), "valores": valores}
