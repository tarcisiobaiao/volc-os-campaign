"""Ledger da Bia no Supabase oficial, só pelas RPCs da v27_01.

Mesmo caminho de `app.seguranca.identidade._papel_do_sub`: PostgREST com a
service_role do backend, chamando funções NOMEADAS. Não há aqui (nem em lugar
nenhum da Bia) leitura de tabela pelo Data API, SQL montado ou nome de tabela
vindo de fora. As regras moram no banco; este arquivo traduz JSON em registro.

A base é a de `Settings.supabase_url`, que `scripts/verificar_autoridade_supabase.py`
confere ser `https://database.agenciavolc.com.br`. Nenhum fallback.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

import httpx

from app.agente_bia.portas import (
    Conversa,
    Execucao,
    Historico,
    Preparo,
    Reserva,
)

log = logging.getLogger("volc.agente_bia.ledger")

TIMEOUT_S = 10.0


class LedgerIndisponivel(RuntimeError):
    """Banco fora do ar, RPC ausente (migration não aplicada) ou resposta fora do contrato."""


def _conversa(d: Mapping[str, Any]) -> Conversa:
    return Conversa(id=str(d["id"]), titulo=d.get("titulo"),
                    criada_em=str(d["criada_em"]), atualizada_em=str(d["atualizada_em"]))


def _execucao(d: Mapping[str, Any]) -> Execucao:
    return Execucao(
        id=str(d["id"]), conversa_id=str(d["conversa_id"]), request_id=str(d["request_id"]),
        estado=str(d["estado"]), entrada=str(d["entrada"]), resposta=d.get("resposta"),
        erro_codigo=d.get("erro_codigo"), contexto=d.get("contexto"),
        criada_em=str(d["criada_em"]), terminada_em=d.get("terminada_em"),
    )


def _preparo(d: Optional[Mapping[str, Any]]) -> Optional[Preparo]:
    if not d:
        return None
    return Preparo(sessao_motor=str(d["sessao_motor"]), entrada=str(d["entrada"]),
                   contexto=d.get("contexto"))


class LedgerSupabase:
    def __init__(self, base_url: str, service_role_key: str, *,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._base = base_url.rstrip("/")
        self._chave = service_role_key
        self._transport = transport

    async def _rpc(self, funcao: str, args: Dict[str, Any]) -> Any:
        url = f"{self._base}/rest/v1/rpc/{funcao}"
        cabecalhos = {
            "apikey": self._chave,
            "Authorization": f"Bearer {self._chave}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=self._transport,
                                         follow_redirects=False, trust_env=False) as c:
                r = await c.post(url, headers=cabecalhos, json=args)
        except httpx.HTTPError as exc:
            log.warning("ledger da Bia inacessível (%s): %s", funcao, type(exc).__name__)
            raise LedgerIndisponivel("ledger inacessível") from exc
        if r.status_code == 404:
            log.error("RPC %s ausente — a migration v27_01 não foi aplicada", funcao)
            raise LedgerIndisponivel("ledger da Bia não instalado no banco")
        if r.status_code >= 400:
            codigo = ""
            try:
                codigo = str((r.json() or {}).get("code") or "")
            except ValueError:
                pass
            # Só o SQLSTATE vai ao log; a mensagem do banco pode citar valores.
            log.warning("RPC %s recusada: HTTP %s sqlstate=%s", funcao, r.status_code, codigo or "-")
            raise LedgerIndisponivel(f"ledger recusou {funcao} ({codigo or r.status_code})")
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError as exc:
            raise LedgerIndisponivel("ledger respondeu fora do contrato") from exc

    async def criar_conversa(self, dono: str, sessao_motor: str, titulo: Optional[str]) -> Conversa:
        d = await self._rpc("volc_agente_criar_conversa",
                            {"p_dono": dono, "p_sessao_motor": sessao_motor, "p_titulo": titulo})
        return _conversa(d)

    async def listar_conversas(self, dono: str, limite: int) -> List[Conversa]:
        d = await self._rpc("volc_agente_listar_conversas", {"p_dono": dono, "p_limite": limite})
        return [_conversa(x) for x in (d or [])]

    async def historico(self, dono: str, conversa_id: str) -> Optional[Historico]:
        d = await self._rpc("volc_agente_historico", {"p_dono": dono, "p_conversa": conversa_id})
        if not d:
            return None
        return Historico(conversa=_conversa(d["conversa"]),
                         execucoes=[_execucao(x) for x in d.get("execucoes") or []])

    async def execucao(self, dono: str, execucao_id: str) -> Optional[Execucao]:
        d = await self._rpc("volc_agente_execucao", {"p_dono": dono, "p_execucao": execucao_id})
        return _execucao(d) if d else None

    async def reservar(self, dono: str, conversa_id: str, request_id: str, entrada: str,
                       impressao: str, limite_por_minuto: int,
                       contexto: Optional[Mapping[str, Any]]) -> Reserva:
        d = await self._rpc("volc_agente_reservar", {
            "p_dono": dono, "p_conversa": conversa_id, "p_request_id": request_id,
            "p_entrada": entrada, "p_impressao": impressao,
            "p_limite_por_minuto": limite_por_minuto,
            "p_contexto": dict(contexto) if contexto else None,
        })
        e = d.get("execucao") if isinstance(d, dict) else None
        return Reserva(resultado=str(d["resultado"]), execucao=_execucao(e) if e else None)

    async def iniciar(self, dono: str, execucao_id: str) -> Optional[Preparo]:
        return _preparo(await self._rpc("volc_agente_iniciar",
                                        {"p_dono": dono, "p_execucao": execucao_id}))

    async def concluir(self, dono: str, execucao_id: str, estado: str,
                       resposta: Optional[str], erro_codigo: Optional[str],
                       detalhe: Mapping[str, Any]) -> Execucao:
        d = await self._rpc("volc_agente_concluir", {
            "p_dono": dono, "p_execucao": execucao_id, "p_estado": estado,
            "p_resposta": resposta, "p_erro_codigo": erro_codigo, "p_detalhe": dict(detalhe),
        })
        return _execucao(d)

    async def expirar(self, dono: str, segundos: int) -> int:
        d = await self._rpc("volc_agente_expirar", {"p_dono": dono, "p_segundos": segundos})
        return int(d or 0)

    async def para_reconciliar(self, dono: str, execucao_id: str) -> Optional[Preparo]:
        return _preparo(await self._rpc("volc_agente_para_reconciliar",
                                        {"p_dono": dono, "p_execucao": execucao_id}))

    async def reconciliar(self, dono: str, execucao_id: str, estado: str,
                          resposta: Optional[str], detalhe: Mapping[str, Any]) -> Execucao:
        d = await self._rpc("volc_agente_reconciliar", {
            "p_dono": dono, "p_execucao": execucao_id, "p_estado": estado,
            "p_resposta": resposta, "p_detalhe": dict(detalhe),
        })
        return _execucao(d)

    async def registrar_evento(self, dono: str, execucao_id: str, tipo: str,
                               detalhe: Mapping[str, Any]) -> None:
        await self._rpc("volc_agente_registrar_evento", {
            "p_dono": dono, "p_execucao": execucao_id, "p_tipo": tipo, "p_detalhe": dict(detalhe),
        })
