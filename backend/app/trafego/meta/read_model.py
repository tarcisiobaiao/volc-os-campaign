"""Operational persistence authority for Meta read snapshots.

One backend object owns the write: a single Postgres RPC call.  Without the
server-side flag ``META_READ_MODEL_WRITE_ENABLED=1`` the write path fails before
any Supabase request.  Read methods are projections only and never synthesize
fake inventory.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
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


#: Tamanho de pagina padrao e maximo. O teto de 500 anterior nao era pagina:
#: era um CORTE silencioso que se apresentava como inventario completo.
_PAGINA_PADRAO = 100
_PAGINA_MAXIMA = 500

#: Quantos pais resolvemos ao escopar conjuntos/anuncios por conta. Estourar
#: este teto devolve `completo: false` com motivo — nunca uma lista curta que
#: se passa por inteira.
_TETO_DE_ESCOPO = 500


@dataclass(frozen=True)
class _EspecDeEntidade:
    tabela: str
    pk: str
    #: Coluna de conta quando ela existe na propria tabela.
    coluna_de_conta: str | None = None
    #: Quando nao existe, o escopo vem do pai por este par.
    entidade_pai: str | None = None
    coluna_pai: str | None = None
    tipo_de_objeto: str | None = None
    tem_detalhe: bool = True
    exige_conta: bool = False


_ENTIDADES: Mapping[str, _EspecDeEntidade] = {
    "campanhas": _EspecDeEntidade(
        "trafego_meta_campaign", "meta_campaign_id",
        coluna_de_conta="ad_account_ativo_id", tipo_de_objeto="campaign"),
    "conjuntos": _EspecDeEntidade(
        "trafego_meta_adset", "meta_adset_id",
        entidade_pai="campanhas", coluna_pai="meta_campaign_id",
        tipo_de_objeto="adset", exige_conta=True),
    "anuncios": _EspecDeEntidade(
        "trafego_meta_ad", "meta_ad_id",
        entidade_pai="conjuntos", coluna_pai="meta_adset_id",
        tipo_de_objeto="ad", exige_conta=True),
    "criativos": _EspecDeEntidade(
        "trafego_meta_creative", "meta_creative_id",
        coluna_de_conta="ad_account_ativo_id", tipo_de_objeto="creative"),
    "vinculos": _EspecDeEntidade(
        "trafego_meta_ad_creative_binding", "meta_ad_id",
        entidade_pai="anuncios", coluna_pai="meta_ad_id",
        tem_detalhe=False, exige_conta=True),
    "insights": _EspecDeEntidade(
        # Projecao `latest`: uma revisao por grao. A tabela crua guarda o
        # historico e NAO pode ser somada — duas leituras do mesmo dia sao a
        # mesma verdade medida duas vezes, nao o dobro do gasto.
        "vw_trafego_meta_insight_latest", "meta_insight_daily_id",
        coluna_de_conta="ad_account_ativo_id", tem_detalhe=False),
    "mensuracao": _EspecDeEntidade(
        "trafego_meta_custom_measurement", "measurement_type",
        coluna_de_conta="ad_account_ativo_id", tem_detalhe=False),
}


def _codificar_cursor(pk: str, valor: str) -> str:
    bruto = json.dumps({"k": pk, "v": valor}, separators=(",", ":"))
    return base64.urlsafe_b64encode(bruto.encode("utf-8")).decode("ascii").rstrip("=")


def _decodificar_cursor(cursor: str, pk_esperada: str) -> str:
    """Opaque cursor in, primary-key value out — or a typed refusal."""
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        dados = json.loads(base64.urlsafe_b64decode(preenchido.encode("ascii")))
        if not isinstance(dados, dict) or dados.get("k") != pk_esperada:
            raise ValueError("cursor de outra entidade")
        valor = str(dados["v"])
    except Exception as exc:
        raise dom.ContratoMetaInvalido("cursor de paginacao Meta invalido") from exc
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", valor):
        raise dom.ContratoMetaInvalido("cursor de paginacao Meta invalido")
    return valor


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

    # -----------------------------------------------------------------
    # LEITURA ESCOPADA (T07 / F06 / F07 / F10)
    # -----------------------------------------------------------------

    async def contas(self) -> dict[str, Any]:
        if not getattr(self._supa, "enabled", False):
            return {"ok": True, "has_snapshot": False, "contas": [],
                    "estado": "SEM_CONEXAO", "motivo": "supabase_indisponivel"}
        rows, schema_ready = await self._select_seguro(
            "trafego_meta_ad_account",
            {"select": "cofre_ativo_id,account_external_id,nome_observado,moeda,"
                       "timezone_name,account_status,readiness_state,observado_em,"
                       "ultima_leitura_ok_em",
             "order": "cofre_ativo_id.asc"},
        )
        if not schema_ready:
            return {"ok": True, "has_snapshot": False, "contas": [],
                    "estado": "SCHEMA_NAO_APLICADO", "motivo": "meta_schema_not_applied"}
        contas = []
        for row in rows:
            item = dict(row)
            externo = item.get("account_external_id")
            if externo:
                item["conta_ref"] = dom.referencia_opaca_conta(str(externo))
                item["id_mascarado"] = dom.mascarar_id(externo)
            contas.append(item)
        return {
            "ok": True,
            "has_snapshot": bool(rows),
            "estado": "COM_SNAPSHOT" if rows else "SEM_SNAPSHOT",
            "contas": _sanitize_rows(contas),
        }

    async def _contexto_da_conta(self, conta_ref: str) -> Mapping[str, Any] | None:
        """Resolve an opaque account handle to its scope, SERVER-SIDE.

        The browser never sends an ad-account id and is never believed about
        which account it may read: it sends the opaque handle, and the backend
        re-derives the handle from the accounts actually persisted.  A handle
        that matches nothing resolves to nothing — there is no path where an
        id supplied by the caller becomes its own authorization.
        """
        rows, schema_ready = await self._select_seguro(
            "trafego_meta_ad_account",
            {"select": "cofre_ativo_id,account_external_id,moeda,timezone_name,"
                       "observado_em,ultima_leitura_ok_em",
             "order": "cofre_ativo_id.asc"},
        )
        if not schema_ready:
            return None
        for row in rows:
            externo = row.get("account_external_id")
            if not externo:
                continue
            try:
                handle = dom.referencia_opaca_conta(str(externo))
            except dom.ContratoMetaInvalido:
                continue
            if handle == conta_ref:
                return {
                    "ativo_id": row.get("cofre_ativo_id"),
                    "conta_externa": str(externo),
                    "conta_ref": handle,
                    "moeda": row.get("moeda"),
                    "fuso": row.get("timezone_name"),
                    "observado_em": row.get("observado_em"),
                    "ultima_leitura_ok_em": row.get("ultima_leitura_ok_em"),
                }
        return None

    async def _ids_do_escopo(
        self, entidade: str, ativo_id: str,
    ) -> tuple[list[str], bool, str | None]:
        """Resolve the primary keys of ``entidade`` that belong to one account.

        ``trafego_meta_adset`` and ``trafego_meta_ad`` carry no account column —
        they hang off campaign and ad set.  Filtering them by account therefore
        needs a real parental walk.  The previous code simply DROPPED the
        account filter for those two entities, so asking for account A's ad sets
        returned account B's as well.  Walking the parents costs an extra query
        per level and is bounded; a bound that is hit returns incomplete instead
        of a silently short list.
        """
        spec = _ENTIDADES[entidade]
        if spec.coluna_de_conta is not None:
            return [], True, None  # filtro direto, sem walk
        pai = _ENTIDADES[spec.entidade_pai]
        pais, completo, motivo = await self._ids_do_escopo(spec.entidade_pai, ativo_id)
        params: dict[str, Any] = {"select": pai.pk, "limit": _TETO_DE_ESCOPO + 1,
                                  "order": f"{pai.pk}.asc"}
        if pai.coluna_de_conta is not None:
            params[pai.coluna_de_conta] = f"eq.{ativo_id}"
        elif pais:
            params[pai.coluna_pai] = "in.(" + ",".join(pais) + ")"
        else:
            return [], completo, motivo or "ESCOPO_PAI_VAZIO"
        rows, schema_ready = await self._select_seguro(pai.tabela, params)
        if not schema_ready:
            return [], False, "SCHEMA_NAO_APLICADO"
        ids = [str(r[pai.pk]) for r in rows if r.get(pai.pk)]
        if len(ids) > _TETO_DE_ESCOPO:
            return ids[:_TETO_DE_ESCOPO], False, "ESCOPO_PAI_TRUNCADO"
        return ids, completo, motivo

    async def listar(
        self,
        entidade: str,
        conta_ref: str | None = None,
        *,
        cursor: str | None = None,
        tamanho: int = _PAGINA_PADRAO,
    ) -> dict[str, Any]:
        """One page of one entity, always inside one account's scope.

        Three properties the previous version did not have: the account filter
        actually reaches ad sets and ads; the page carries an opaque cursor over
        a TOTAL order (the primary key), so a full sweep cannot skip rows that
        share an ``observado_em``; and the answer says whether it is complete
        instead of letting a 500-row ceiling pass for "all of them".
        """
        if entidade not in _ENTIDADES:
            raise dom.ContratoMetaInvalido("entidade Meta persistida desconhecida")
        spec = _ENTIDADES[entidade]
        tamanho = max(1, min(int(tamanho), _PAGINA_MAXIMA))
        vazio = {"ok": True, "has_snapshot": False, "entidade": entidade,
                 "items": [], "completo": False, "has_more": False,
                 "proximo_cursor": None}
        if not getattr(self._supa, "enabled", False):
            return {**vazio, "estado": "SEM_CONEXAO", "motivo": "supabase_indisponivel"}

        contexto: Mapping[str, Any] | None = None
        if conta_ref:
            contexto = await self._contexto_da_conta(conta_ref)
            if contexto is None:
                # Handle desconhecido NAO vira "conta inteira": vira escopo vazio.
                return {**vazio, "estado": "ESCOPO_DESCONHECIDO",
                        "motivo": "conta_opaca_nao_resolvida"}
        elif spec.exige_conta:
            return {**vazio, "estado": "ESCOPO_OBRIGATORIO",
                    "motivo": "esta entidade exige conta_ref explicita"}

        params: dict[str, Any] = {
            "select": "*",
            "limit": tamanho + 1,          # +1 revela has_more sem um count
            "order": f"{spec.pk}.asc",     # ordem TOTAL e estavel
        }
        completo = True
        motivo: str | None = None
        if contexto is not None:
            if spec.coluna_de_conta is not None:
                params[spec.coluna_de_conta] = f"eq.{contexto['ativo_id']}"
            else:
                pais, completo, motivo = await self._ids_do_escopo(
                    entidade, str(contexto["ativo_id"]))
                if not pais:
                    return {**vazio, "estado": "SEM_SNAPSHOT",
                            "completo": completo, "motivo": motivo,
                            "conta_ref": contexto["conta_ref"]}
                params[spec.coluna_pai] = "in.(" + ",".join(pais) + ")"
        if cursor:
            params[spec.pk] = f"gt.{_decodificar_cursor(cursor, spec.pk)}"

        rows, schema_ready = await self._select_seguro(spec.tabela, params)
        if not schema_ready:
            return {**vazio, "estado": "SCHEMA_NAO_APLICADO",
                    "motivo": "meta_schema_not_applied"}
        has_more = len(rows) > tamanho
        pagina = list(rows)[:tamanho]
        proximo = (_codificar_cursor(spec.pk, str(pagina[-1][spec.pk]))
                   if has_more and pagina else None)
        itens = [self._com_entity_ref(dict(r), spec, contexto) for r in pagina]
        return {
            "ok": True,
            "has_snapshot": bool(pagina),
            "estado": "COM_SNAPSHOT" if pagina else "SEM_SNAPSHOT",
            "entidade": entidade,
            "conta_ref": contexto["conta_ref"] if contexto else None,
            "moeda": contexto.get("moeda") if contexto else None,
            "fuso": contexto.get("fuso") if contexto else None,
            "frescor": contexto.get("ultima_leitura_ok_em") if contexto else None,
            "items": _sanitize_rows(itens),
            "completo": completo and not has_more,
            "has_more": has_more,
            "proximo_cursor": proximo,
            "motivo": motivo,
        }

    def _com_entity_ref(
        self,
        row: dict[str, Any],
        spec: "_EspecDeEntidade",
        contexto: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Attach the ONE public identity, resolving birth and persistence.

        The executor hands the operator ``metaobj_…`` handles at creation time;
        persistence keys the same object by a UUID.  Both are derived from
        (account, type, external id), so both can be recomputed here and the
        row can carry them together — the receipt's handle stops being a dead
        end in the UI, and the historical UUID is not retagged.
        """
        externo = row.get("external_id")
        conta_externa = contexto.get("conta_externa") if contexto else None
        if externo and conta_externa and spec.tipo_de_objeto:
            try:
                row["entity_ref"] = dom.referencia_opaca_objeto(
                    str(conta_externa), spec.tipo_de_objeto, str(externo))
                row["id_mascarado"] = dom.mascarar_id(externo)
            except dom.ContratoMetaInvalido:
                pass
        return row

    async def detalhe(
        self, entidade: str, referencia: str, conta_ref: str | None = None,
    ) -> dict[str, Any]:
        """One object, only if it is inside the requested account's scope.

        The previous version took an id and returned whatever row matched it,
        with no account parameter at all: an operator holding one account's
        handle could read any other account's object simply by knowing its id.
        Scope is now a required part of the question, and the id is resolved
        INSIDE it — an id is evidence of nothing on its own.
        """
        if entidade not in _ENTIDADES or not _ENTIDADES[entidade].tem_detalhe:
            raise dom.ContratoMetaInvalido("detalhe Meta persistido desconhecido")
        spec = _ENTIDADES[entidade]
        vazio = {"ok": True, "has_snapshot": False, "entidade": entidade, "item": None}
        if not getattr(self._supa, "enabled", False):
            return {**vazio, "estado": "SEM_CONEXAO", "motivo": "supabase_indisponivel"}
        if not conta_ref:
            return {**vazio, "estado": "ESCOPO_OBRIGATORIO",
                    "motivo": "detalhe Meta exige conta_ref"}
        contexto = await self._contexto_da_conta(conta_ref)
        if contexto is None:
            return {**vazio, "estado": "ESCOPO_DESCONHECIDO",
                    "motivo": "conta_opaca_nao_resolvida"}

        pagina = await self.listar(entidade, conta_ref, tamanho=_PAGINA_MAXIMA)
        if not pagina.get("ok") or pagina.get("estado") in {
                "SCHEMA_NAO_APLICADO", "SEM_CONEXAO"}:
            return {**vazio, "estado": pagina.get("estado"),
                    "motivo": pagina.get("motivo")}
        for item in pagina.get("items", []):
            if referencia in {item.get("entity_ref"), item.get(spec.pk)}:
                return {"ok": True, "has_snapshot": True, "entidade": entidade,
                        "estado": "COM_SNAPSHOT", "item": item,
                        "conta_ref": contexto["conta_ref"]}
        # Nao encontrado DENTRO do escopo. Pode existir noutra conta; nao dizemos.
        return {**vazio,
                "estado": "NAO_ENCONTRADO_NO_ESCOPO" if pagina.get("completo")
                          else "NAO_ENCONTRADO_ESCOPO_PARCIAL",
                "motivo": "referencia nao pertence a esta conta ou ainda nao sincronizou",
                "conta_ref": contexto["conta_ref"]}

    async def ultimo_recibo(self) -> dict[str, Any]:
        """The last receipt, with the readiness state kept ATTACHED.

        The caller used to collapse three different worlds into one answer:
        "the tables do not exist", "Supabase is unreachable" and "no sync has
        ever run" all became ``recibo: null``. The operator then read the third
        meaning and went looking for a sync that could never have persisted.
        ``estado`` now travels with the answer so the caller cannot lose it.
        """
        if not getattr(self._supa, "enabled", False):
            return {"ok": True, "has_snapshot": False, "recibo": None,
                    "estado": "SEM_CONEXAO", "motivo": "supabase_indisponivel"}
        rows, schema_ready = await self._select_seguro(
            "trafego_meta_sync_run",
            {"select": "run_id,resultado,concluido_em,paginas_lidas,contagens,"
                       "snapshot_hash,escrita_executada,erro_codigo,erro_mensagem",
             "order": "concluido_em.desc", "limit": 1},
        )
        if not schema_ready:
            return {"ok": True, "has_snapshot": False, "recibo": None,
                    "estado": "SCHEMA_NAO_APLICADO", "motivo": "meta_schema_not_applied"}
        return {"ok": True, "has_snapshot": bool(rows),
                "estado": "COM_SNAPSHOT" if rows else "SEM_SNAPSHOT",
                "recibo": _sanitize_rows(rows)[0] if rows else None}
