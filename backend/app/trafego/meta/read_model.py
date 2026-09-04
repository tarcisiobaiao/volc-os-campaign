"""Operational persistence authority for Meta read snapshots.

One backend object owns the write: a single Postgres RPC call.  Without the
server-side flag ``META_READ_MODEL_WRITE_ENABLED=1`` the write path fails before
any Supabase request.  Read methods are projections only and never synthesize
fake inventory.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

import httpx

from . import dominio as dom
from .persistencia import linhas_da_leitura, linhas_de_contas, linhas_de_insights


def _json_default(valor: Any) -> str:
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(type(valor).__name__)


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=_json_default, separators=(",", ":"))


def _sanitize_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in list(item):
            if key.endswith("external_id") or key in {"external_id", "account_external_id", "conta_externa", "objeto_externo", "business_external_id"}:
                item.pop(key, None)
        safe.append(item)
    return safe


@dataclass(frozen=True)
class SnapshotMetaCanonico:
    conta: dom.ContaMetaDescoberta
    leitura: dom.LeituraDaHierarquia
    insights: tuple[dom.InsightMeta, ...]
    mensuracao: Mapping[str, Any]
    janela: str
    observado_em: datetime
    linhas: Mapping[str, list[dict[str, Any]]]
    idempotency_key: str
    snapshot_hash: str

    def payload_rpc(self) -> dict[str, Any]:
        return {
            "provider": dom.META_ADS,
            "account_ref": self.conta.referencia_opaca,
            "account_asset_id": f"meta_account_{self.conta.referencia_opaca}",
            "credential_asset_id": "meta_credential_keychain_local",
            "window": self.janela,
            "observed_at": self.observado_em,
            "idempotency_key": self.idempotency_key,
            "snapshot_hash": self.snapshot_hash,
            "page_count": self.leitura.paginas_lidas,
            "measurement": dict(self.mensuracao),
            "counts": {
                **dict(self.leitura.contagens),
                "insight": len(self.insights),
            },
            "rows": self.linhas,
        }

    def recibo_sanitizado(self, *, escrita: str, repetido: bool = False, resultado_rpc: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": escrita == "executada",
            "conta_opaca": self.conta.referencia_opaca,
            "conta": self.conta.publico(),
            "contagens": {
                **dict(self.leitura.contagens),
                "insight": len(self.insights),
            },
            "paginas_lidas": self.leitura.paginas_lidas,
            "parcialidade": [],
            "erros": [],
            "snapshot_hash": self.snapshot_hash,
            "observado_em": self.observado_em.isoformat(),
            "escrita": escrita,
            "repetido": repetido,
            "run_id": (resultado_rpc or {}).get("run_id"),
            "proxima_acao": "habilitar_META_READ_MODEL_WRITE_ENABLED" if escrita == "bloqueada" else "consultar_inventario_persistido",
        }


def montar_snapshot_canonico(
    conta: dom.ContaMetaDescoberta,
    leitura: dom.LeituraDaHierarquia,
    insights: Sequence[dom.InsightMeta],
    mensuracao: Mapping[str, Any],
    janela: str,
    observado_em: datetime,
) -> SnapshotMetaCanonico:
    dom.instante_utc(observado_em, campo="observado_em")
    if leitura.conta_externa != conta.id_externo:
        raise dom.ContratoMetaInvalido("snapshot mistura contas Meta diferentes")
    linhas: dict[str, list[dict[str, Any]]] = {}
    linhas.update(linhas_de_contas((conta,), observado_em, credencial_ativo_id="meta_credential_keychain_local"))
    linhas.update(linhas_da_leitura(leitura, observado_em, conta_ativo_id=f"meta_account_{conta.referencia_opaca}"))
    linhas.update(linhas_de_insights(tuple(insights), conta_ativo_id=f"meta_account_{conta.referencia_opaca}"))
    medida_rows: list[dict[str, Any]] = []
    for nome, valor in mensuracao.items():
        if isinstance(valor, int) or valor is None:
            medida_rows.append({
                "ad_account_ativo_id": f"meta_account_{conta.referencia_opaca}",
                "measurement_type": str(nome),
                "observed_count": valor,
                "observado_em": observado_em,
                "snapshot_hash": "__pending__",
            })
    linhas["trafego_meta_custom_measurement"] = medida_rows
    bruto_para_hash = {
        "provider": dom.META_ADS,
        "conta": conta.id_externo,
        "janela": janela,
        "linhas": linhas,
    }
    snapshot_hash = "meta_snapshot_" + hashlib.sha256(_stable_json(bruto_para_hash).encode("utf-8")).hexdigest()[:32]
    for row in medida_rows:
        row["snapshot_hash"] = snapshot_hash
    idem = "meta_sync_" + hashlib.sha256(
        f"{dom.META_ADS}|{conta.id_externo}|{janela}|{snapshot_hash}".encode("utf-8")
    ).hexdigest()[:32]
    return SnapshotMetaCanonico(
        conta=conta,
        leitura=leitura,
        insights=tuple(insights),
        mensuracao=dict(mensuracao),
        janela=janela,
        observado_em=observado_em,
        linhas=linhas,
        idempotency_key=idem,
        snapshot_hash=snapshot_hash,
    )


class PersistenciaMetaBloqueada(RuntimeError):
    def __init__(self, recibo: Mapping[str, Any]) -> None:
        self.recibo = dict(recibo)
        super().__init__("persistencia Meta bloqueada por flag server-side")


class RepositorioMetaReadModelSupabase:
    def __init__(self, supabase: Any) -> None:
        self._supa = supabase

    async def _select_seguro(
        self, tabela: str, params: Mapping[str, Any],
    ) -> tuple[list[Mapping[str, Any]], bool]:
        try:
            return list(await self._supa.select(tabela, dict(params))), True
        except httpx.HTTPStatusError as exc:
            # Until the separately-authorized v15 migrations are applied,
            # PostgREST returns 404 for these tables. Absence is a readiness
            # state, not a backend crash and never an empty measured inventory.
            if exc.response is not None and exc.response.status_code == 404:
                return [], False
            raise

    async def persistir_snapshot(self, snapshot: SnapshotMetaCanonico) -> dict[str, Any]:
        if os.environ.get("META_READ_MODEL_WRITE_ENABLED") != "1":
            recibo = snapshot.recibo_sanitizado(escrita="bloqueada")
            raise PersistenciaMetaBloqueada(recibo)
        if not getattr(self._supa, "enabled", False):
            recibo = snapshot.recibo_sanitizado(escrita="bloqueada")
            recibo["proxima_acao"] = "configurar_supabase_service_role_no_backend"
            raise PersistenciaMetaBloqueada(recibo)
        dom.validar_documento_seguro(snapshot.payload_rpc())
        resultado = await self._supa.rpc("trafego_meta_persistir_snapshot", {"p_snapshot": snapshot.payload_rpc()})
        if isinstance(resultado, list) and resultado:
            resultado = resultado[0]
        if not isinstance(resultado, dict):
            resultado = {}
        return snapshot.recibo_sanitizado(escrita="executada", repetido=bool(resultado.get("repetido")), resultado_rpc=resultado)

    async def contas(self) -> dict[str, Any]:
        if not getattr(self._supa, "enabled", False):
            return {"ok": True, "has_snapshot": False, "contas": [], "motivo": "supabase_indisponivel"}
        rows, schema_ready = await self._select_seguro("trafego_meta_ad_account", {"select": "cofre_ativo_id,nome_observado,moeda,timezone_name,account_status,readiness_state,observado_em,ultima_leitura_ok_em", "order": "atualizado_em.desc"})
        if not schema_ready:
            return {"ok": True, "has_snapshot": False, "contas": [], "motivo": "meta_schema_not_applied"}
        return {"ok": True, "has_snapshot": bool(rows), "contas": _sanitize_rows(rows)}

    async def listar(self, entidade: str, conta_opaca: str | None = None) -> dict[str, Any]:
        tabelas = {
            "campanhas": "trafego_meta_campaign",
            "conjuntos": "trafego_meta_adset",
            "anuncios": "trafego_meta_ad",
            "criativos": "trafego_meta_creative",
            "insights": "trafego_meta_insight_daily",
            "mensuracao": "trafego_meta_custom_measurement",
        }
        if entidade not in tabelas:
            raise dom.ContratoMetaInvalido("entidade Meta persistida desconhecida")
        if not getattr(self._supa, "enabled", False):
            return {"ok": True, "has_snapshot": False, "entidade": entidade, "items": [], "motivo": "supabase_indisponivel"}
        params = {"select": "*", "limit": 500, "order": "observado_em.desc"}
        if conta_opaca and entidade in {"campanhas", "criativos", "insights"}:
            params["ad_account_ativo_id"] = f"eq.meta_account_{conta_opaca}"
        rows, schema_ready = await self._select_seguro(tabelas[entidade], params)
        if not schema_ready:
            return {"ok": True, "has_snapshot": False, "entidade": entidade, "items": [], "motivo": "meta_schema_not_applied"}
        return {"ok": True, "has_snapshot": bool(rows), "entidade": entidade, "items": _sanitize_rows(rows)}

    async def detalhe(self, entidade: str, opaque_id: str) -> dict[str, Any]:
        colunas = {
            "campanhas": ("trafego_meta_campaign", "meta_campaign_id"),
            "conjuntos": ("trafego_meta_adset", "meta_adset_id"),
            "anuncios": ("trafego_meta_ad", "meta_ad_id"),
            "criativos": ("trafego_meta_creative", "meta_creative_id"),
        }
        if entidade not in colunas:
            raise dom.ContratoMetaInvalido("detalhe Meta persistido desconhecido")
        if not getattr(self._supa, "enabled", False):
            return {"ok": True, "has_snapshot": False, "entidade": entidade, "item": None, "motivo": "supabase_indisponivel"}
        tabela, coluna = colunas[entidade]
        rows, schema_ready = await self._select_seguro(tabela, {"select": "*", coluna: f"eq.{opaque_id}", "limit": 1})
        if not schema_ready:
            return {"ok": True, "has_snapshot": False, "entidade": entidade, "item": None, "motivo": "meta_schema_not_applied"}
        return {"ok": True, "has_snapshot": bool(rows), "entidade": entidade, "item": _sanitize_rows(rows)[0] if rows else None}

    async def ultimo_recibo(self) -> dict[str, Any]:
        if not getattr(self._supa, "enabled", False):
            return {"ok": True, "has_snapshot": False, "recibo": None, "motivo": "supabase_indisponivel"}
        rows, schema_ready = await self._select_seguro("trafego_meta_sync_run", {"select": "run_id,resultado,concluido_em,paginas_lidas,contagens,snapshot_hash,escrita_executada,erro_codigo,erro_mensagem", "order": "concluido_em.desc", "limit": 1})
        if not schema_ready:
            return {"ok": True, "has_snapshot": False, "recibo": None, "motivo": "meta_schema_not_applied"}
        return {"ok": True, "has_snapshot": bool(rows), "recibo": _sanitize_rows(rows)[0] if rows else None}
