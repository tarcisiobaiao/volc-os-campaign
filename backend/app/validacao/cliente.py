"""Cliente assíncrono do DataForSEO — a borda que fala com a rede.

O `motor_pautas/sensores/dataforseo.py` guarda os MAPEADORES, que são funções
puras e rodam sem credencial. Aqui mora só o transporte, e ele é fino de
propósito: quem depende de rede é a borda, não a lógica.

Duas responsabilidades que este arquivo não delega:

1. **Contabilidade de custo, chamada a chamada, dentro do processo.** O custo
   vem de `tasks[].cost` da própria resposta. Um contador em arquivo
   compartilhado entre processos paralelos reportou de 8x a 25x o consumo real
   de cada sonda — o número tem que nascer junto com a resposta que o gerou.

2. **Nunca derrubar o lote inteiro por uma chamada.** Um erro numa SERP não
   pode custar as medições de volume que já foram pagas. Erro vira registro,
   não exceção.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.motor_pautas.sensores.dataforseo import EP

log = logging.getLogger("pautador.validacao.dataforseo")

BASE = "https://api.dataforseo.com/v3"

# Mercados da operação → códigos do DataForSEO. `CO 2170 es` está confirmado
# nas 96 medições; os demais são os códigos oficiais de país.
LOCALIDADES: Dict[str, tuple[int, str]] = {
    "BR": (2076, "pt"),
    "PT": (2620, "pt"),
    "MX": (2484, "es"),
    "CO": (2170, "es"),
    "CL": (2152, "es"),
    "PE": (2604, "es"),
    "AR": (2032, "es"),
    "ES": (2724, "es"),
    "US": (2840, "en"),
    "GB": (2826, "en"),
    "NG": (2566, "en"),
    "PH": (2608, "en"),
}


def localidade(country_code: str) -> Optional[tuple[int, str]]:
    return LOCALIDADES.get((country_code or "").upper())


@dataclass
class Chamada:
    """O registro de UMA chamada. Existe para o relatório poder ser auditado."""

    endpoint: str
    custo_usd: float
    ok: bool
    itens: int = 0
    erro: str = ""


@dataclass
class ClienteDataForSEO:
    settings: Settings
    _chamadas: List[Chamada] = field(default_factory=list)

    @property
    def habilitado(self) -> bool:
        return bool(self.settings.dataforseo_login and self.settings.dataforseo_password)

    @property
    def custo_total(self) -> float:
        return round(sum(c.custo_usd for c in self._chamadas), 6)

    @property
    def chamadas(self) -> List[Chamada]:
        return list(self._chamadas)

    def _auth(self) -> str:
        cru = f"{self.settings.dataforseo_login}:{self.settings.dataforseo_password}"
        return "Basic " + base64.b64encode(cru.encode()).decode()

    async def chamar(self, endpoint: str, tarefas: List[dict]) -> dict:
        """POST. Devolve o envelope cru — a interpretação é dos mapeadores.

        Nunca levanta por erro de rede ou de API: devolve `{}` e registra a
        `Chamada` com `ok=False`. Quem chama decide se aquele eixo fica ausente.
        """
        url = BASE + EP.get(endpoint, endpoint)
        headers = {"Authorization": self._auth(), "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds or 60
            ) as client:
                resp = await client.post(url, headers=headers, json=tarefas)
                resp.raise_for_status()
                dados = resp.json()
        except Exception as exc:  # noqa: BLE001 — erro de uma chamada não é erro do lote
            log.warning("dataforseo %s falhou: %s", endpoint, str(exc)[:200])
            self._chamadas.append(
                Chamada(endpoint=endpoint, custo_usd=0.0, ok=False, erro=str(exc)[:300])
            )
            return {}

        # Custo da PRÓPRIA resposta, somando as tarefas. Cobrado mesmo quando a
        # tarefa devolve status de erro — por isso é registrado antes de checar.
        tarefas_resp = dados.get("tasks") or []
        custo = sum(float(t.get("cost") or 0.0) for t in tarefas_resp if isinstance(t, dict))

        ruins = [
            f"{t.get('status_code')}: {str(t.get('status_message'))[:120]}"
            for t in tarefas_resp
            if isinstance(t, dict) and t.get("status_code") not in (20000, None)
        ]
        n_itens = sum(
            int(r.get("items_count") or 0)
            for t in tarefas_resp
            if isinstance(t, dict)
            for r in (t.get("result") or [])
            if isinstance(r, dict)
        )
        self._chamadas.append(
            Chamada(
                endpoint=endpoint,
                custo_usd=round(custo, 6),
                ok=not ruins,
                itens=n_itens,
                erro=" | ".join(ruins)[:300],
            )
        )
        return dados

    async def em_paralelo(self, pedidos: List[tuple[str, List[dict]]], *, limite: int = 6
                          ) -> List[dict]:
        """Várias chamadas concorrentes, com teto.

        O teto não é enfeite: a conta tem limite por minuto por grupo de
        endpoint (`google_ads` live: 12/min). Estourar devolve erro cobrado.
        """
        sem = asyncio.Semaphore(limite)

        async def _uma(endpoint: str, tarefas: List[dict]) -> dict:
            async with sem:
                return await self.chamar(endpoint, tarefas)

        return await asyncio.gather(*(_uma(e, t) for e, t in pedidos))


def resultados(resposta: dict) -> List[dict]:
    """Os blocos `result` de tarefas bem-sucedidas.

    Distinto de `sensores.itens()`: aqui interessa o RESULT inteiro (que carrega
    `keyword`, `items_count`, `monthly_searches`), não só os `items`.
    """
    out: List[dict] = []
    for t in resposta.get("tasks") or []:
        if not isinstance(t, dict) or t.get("status_code") not in (20000, None):
            continue
        for r in t.get("result") or []:
            if isinstance(r, dict):
                out.append(r)
    return out


def itens_de(resposta: dict) -> List[dict]:
    out: List[dict] = []
    for r in resultados(resposta):
        for i in r.get("items") or []:
            if isinstance(i, dict):
                out.append(i)
    return out
