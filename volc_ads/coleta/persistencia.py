"""Porta de escrita do coletor: só RPC, só no Supabase oficial.

Mesma trava de autoridade de `inteligencia_google/persistencia.py`: qualquer URL
que não seja `https://database.agenciavolc.com.br` é recusada antes da rede.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AUTORIDADE = "https://database.agenciavolc.com.br"
RPCS_PERMITIDAS = frozenset({"volc_registrar_gads_fatos", "volc_registrar_gads_campanha_dia"})


class ErroPersistenciaColeta(RuntimeError):
    pass


class RPC:
    def __init__(self, url: str | None = None, service_key: str | None = None, *, timeout_s: float = 120) -> None:
        self.url = (url or os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL") or "").rstrip("/")
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.timeout_s = timeout_s
        if self.url != AUTORIDADE:
            raise ErroPersistenciaColeta(f"autoridade recusada: a URL precisa ser {AUTORIDADE}")
        if not self.service_key:
            raise ErroPersistenciaColeta("SUPABASE_SERVICE_ROLE_KEY ausente")

    def __call__(self, rpc: str, documento: dict) -> Any:
        if rpc not in RPCS_PERMITIDAS:
            raise ErroPersistenciaColeta(f"RPC fora da lista do coletor: {rpc}")
        corpo = json.dumps({"documento": documento}, ensure_ascii=False).encode()
        req = Request(f"{self.url}/rest/v1/rpc/{rpc}", data=corpo, method="POST", headers={
            "apikey": self.service_key, "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                bruto = resp.read()
        except HTTPError as exc:
            raise ErroPersistenciaColeta(
                f"RPC {rpc} HTTP {exc.code}: {exc.read().decode(errors='replace')[:800]}") from exc
        except URLError as exc:
            raise ErroPersistenciaColeta(f"PostgREST indisponível: {exc.reason}") from exc
        return json.loads(bruto) if bruto else None

    def mapa_volc(self, customer_id: str) -> dict[str, str]:
        """campaign_id → volc_campaign_id da conta, lido do inventário."""
        from urllib.parse import urlencode

        q = urlencode({"select": "campaign_id,volc_campaign_id", "customer_id": f"eq.{customer_id}"}, safe=".,")
        req = Request(f"{self.url}/rest/v1/trafego_inventario_campanha?{q}", headers={
            "apikey": self.service_key, "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                linhas = json.loads(resp.read() or b"[]")
        except (HTTPError, URLError) as exc:
            raise ErroPersistenciaColeta(f"inventário ilegível: {exc}") from exc
        return {str(l["campaign_id"]): str(l["volc_campaign_id"])
                for l in linhas if l.get("campaign_id") and l.get("volc_campaign_id")}

    def execucoes_do_passo(self, prefixo: str) -> list[dict]:
        """Linhas do ledger de um passo da agenda (só leitura).

        ⚠️ Falha de leitura levanta: concluir "não rodou" porque o ledger não
        respondeu faria o agendador repetir em silêncio.
        """
        from urllib.parse import urlencode

        q = urlencode({"select": "execucao_chave,tipo_lote,resultado",
                       "execucao_chave": f"like.{prefixo}:*"}, safe=".,:*")
        req = Request(f"{self.url}/rest/v1/trafego_coleta_execucao?{q}", headers={
            "apikey": self.service_key, "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read() or b"[]")
        except (HTTPError, URLError) as exc:
            raise ErroPersistenciaColeta(f"ledger ilegível: {exc}") from exc
