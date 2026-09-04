"""Injected Graph transport for validation and authorized PAUSED creation."""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from app.trafego.meta import dominio as meta_dom
from app.trafego.meta.credenciais import SegredoEfemero

from .compilador import PlanoCompiladoMeta, OperacaoMeta, resolver_dependencias
from .contrato import AutorizacaoMeta, ErroDeNascimentoMeta
from .registro import RegistroSagaMeta


@dataclass(frozen=True)
class ResultadoValidacaoMeta:
    aceito: bool
    cobertura: str
    operacoes_validadas: tuple[str, ...]
    operacoes_dependentes_pendentes: tuple[str, ...]
    plano_sha256: str


@dataclass(frozen=True)
class ResultadoNascimentoMeta:
    desfecho: str
    plano_sha256: str
    referencias_opacas: Mapping[str, str]
    read_back: Mapping[str, Any]
    retry_permitido: bool


class ErroRemotoMeta(RuntimeError):
    def __init__(
        self,
        codigo: str,
        mensagem: str,
        *,
        retryable: bool = False,
        objetos_criados: tuple[str, ...] = (),
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.retryable = retryable
        # Names only. Provider ids remain backend-private even on failures.
        self.objetos_criados = objetos_criados


def _form(payload: Mapping[str, Any]) -> dict[str, str]:
    saida: dict[str, str] = {}
    for chave, valor in payload.items():
        if isinstance(valor, (dict, list, tuple, bool)):
            saida[chave] = json.dumps(valor, separators=(",", ":"), ensure_ascii=False)
        else:
            saida[chave] = str(valor)
    return saida


class ExecutorMetaPausado:
    def __init__(
        self,
        cliente: httpx.AsyncClient,
        *,
        api_version: str = "v26.0",
        base_url: str = "https://graph.facebook.com",
        registro: RegistroSagaMeta | None = None,
    ) -> None:
        partes = urlparse(base_url)
        if partes.scheme != "https" or partes.hostname != "graph.facebook.com":
            raise ValueError("base Meta precisa ser https://graph.facebook.com")
        if api_version != "v26.0":
            raise ValueError("o executor P0 esta fixado em v26.0")
        self._cliente = cliente
        self._base = base_url.rstrip("/")
        self._versao = api_version
        self._registro = registro

    async def validar_raizes(
        self,
        plano: PlanoCompiladoMeta,
        segredo: SegredoEfemero,
        autorizacao: AutorizacaoMeta,
    ) -> ResultadoValidacaoMeta:
        autorizacao.exigir(plano_sha256=plano.plano_sha256, ato="validate_only")
        validadas: list[str] = []
        pendentes: list[str] = []
        for operacao in plano.operacoes:
            if not operacao.validavel_sem_criar_pai:
                pendentes.append(operacao.nome)
                continue
            payload = dict(operacao.payload)
            payload["execution_options"] = ["validate_only"]
            resposta = await self._post(operacao, payload, segredo, exige_id=False)
            if resposta.get("success") is not True:
                raise ErroRemotoMeta(
                    "META_REMOTE_RESULT_AMBIGUOUS",
                    f"validate_only de {operacao.nome} nao devolveu sucesso explicito",
                )
            validadas.append(operacao.nome)
        return ResultadoValidacaoMeta(
            aceito=True,
            cobertura="INDEPENDENT_ROOTS_ONLY",
            operacoes_validadas=tuple(validadas),
            operacoes_dependentes_pendentes=tuple(pendentes),
            plano_sha256=plano.plano_sha256,
        )

    async def criar_pausada(
        self,
        plano: PlanoCompiladoMeta,
        segredo: SegredoEfemero,
        autorizacao: AutorizacaoMeta,
    ) -> ResultadoNascimentoMeta:
        autorizacao.exigir(plano_sha256=plano.plano_sha256, ato="create_paused")
        # The dependent graph cannot be validated up front: AdSet needs the
        # real Campaign id and Ad needs both AdSet and Creative ids. The safe
        # P0 is therefore a saga: validate the resolved step, then create that
        # same PAUSED step. Both acts need explicit authority.
        autorizacao.exigir(plano_sha256=plano.plano_sha256, ato="validate_only")
        if self._registro is None:
            raise ErroDeNascimentoMeta(
                "META_DURABLE_RECEIPT_UNAVAILABLE",
                "criacao Meta exige registro duravel antes de qualquer POST",
            )
        ids: dict[str, str] = {}
        read_back: dict[str, Mapping[str, Any]] = {}
        try:
            for operacao in plano.operacoes:
                payload = resolver_dependencias(operacao.payload, ids)
                if operacao.nome in {"campaign", "adset", "ad"} and payload.get("status") != "PAUSED":
                    raise ErroDeNascimentoMeta(
                        "META_NOT_PAUSED", f"{operacao.nome} nao esta PAUSED no payload aprovado")
                validacao = dict(payload)
                validacao["execution_options"] = ["validate_only"]
                validado = await self._post(
                    operacao, validacao, segredo, exige_id=False)
                if validado.get("success") is not True:
                    raise ErroRemotoMeta(
                        "META_REMOTE_RESULT_AMBIGUOUS",
                        f"validate_only de {operacao.nome} nao devolveu sucesso explicito",
                    )
                payload_sha256 = hashlib.sha256(
                    json.dumps(
                        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                passo = await self._registro.preparar_passo(
                    plano_sha256=plano.plano_sha256,
                    approval_id=autorizacao.approval_id,
                    nome=operacao.nome,
                    payload_sha256=payload_sha256,
                )
                if passo.estado == "AMBIGUO":
                    raise ErroRemotoMeta(
                        "META_RECONCILIATION_REQUIRED",
                        f"o passo {operacao.nome} esta ambiguo; reconciliar antes de continuar",
                    )
                if passo.estado == "CRIADO":
                    ids[operacao.nome] = str(passo.id_externo)
                else:
                    try:
                        resposta = await self._post(
                            operacao, payload, segredo, exige_id=True)
                    except httpx.TimeoutException:
                        try:
                            await self._registro.marcar_ambiguo(passo_ref=passo.passo_ref)
                        except Exception:
                            pass
                        raise
                    except ErroRemotoMeta as exc:
                        await self._registro.falhar_passo(
                            passo_ref=passo.passo_ref, codigo=exc.codigo)
                        raise
                    ids[operacao.nome] = str(resposta["id"])
                    try:
                        await self._registro.fechar_passo(
                            passo_ref=passo.passo_ref,
                            id_externo=ids[operacao.nome],
                        )
                    except Exception as exc:
                        try:
                            await self._registro.marcar_ambiguo(passo_ref=passo.passo_ref)
                        except Exception:
                            pass
                        raise ErroRemotoMeta(
                            "META_REMOTE_RESULT_AMBIGUOUS",
                            "a Meta criou o objeto, mas o recibo nao fechou; reconciliar por leitura",
                        ) from exc
                # Confirm each durable step before allowing the next dependent
                # object to be created. A mismatch stops the saga immediately.
                dados = await self._read_one(
                    operacao.nome, ids[operacao.nome], segredo)
                self._validar_read_back(
                    operacao.nome,
                    dados,
                    payload=payload,
                    identificador=ids[operacao.nome],
                    ids=ids,
                )
                read_back[operacao.nome] = dados
        except httpx.TimeoutException as exc:
            raise ErroRemotoMeta(
                "META_REMOTE_RESULT_AMBIGUOUS",
                "a Meta nao respondeu; nao reenviar antes de reconciliar por leitura",
                retryable=False,
                objetos_criados=tuple(ids),
            ) from exc
        except ErroRemotoMeta as exc:
            if not ids or exc.objetos_criados:
                raise
            raise ErroRemotoMeta(
                exc.codigo,
                f"{exc}; a saga parou com objetos PAUSED ja criados: {', '.join(ids)}",
                retryable=False,
                objetos_criados=tuple(ids),
            ) from exc
        conta_externa = plano.operacoes[0].endpoint.split("/act_", 1)[1].split("/", 1)[0]
        opacas = {
            nome: meta_dom.referencia_opaca_objeto(
                conta_externa, nome, identificador)
            for nome, identificador in ids.items()
        }
        return ResultadoNascimentoMeta(
            desfecho="CREATED_PAUSED",
            plano_sha256=plano.plano_sha256,
            referencias_opacas=opacas,
            read_back={
                nome: {
                    "status": dados.get("configured_status") or dados.get("status"),
                    "effective_status": dados.get("effective_status"),
                    "objective": dados.get("objective"),
                    "optimization_goal": dados.get("optimization_goal"),
                    "destination_type": dados.get("destination_type"),
                    "advantage_state_info": dados.get("advantage_state_info"),
                }
                for nome, dados in read_back.items()
            },
            retry_permitido=False,
        )

    async def _post(
        self,
        operacao: OperacaoMeta,
        payload: Mapping[str, Any],
        segredo: SegredoEfemero,
        *,
        exige_id: bool,
    ) -> Mapping[str, Any]:
        try:
            resposta = await self._cliente.post(
                f"{self._base}/{self._versao}{operacao.endpoint}",
                data=_form(payload),
                headers={"Authorization": segredo.cabecalho_bearer()},
            )
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError as exc:
            raise ErroRemotoMeta(
                "META_TRANSPORT_ERROR", "a Meta nao respondeu ao pedido", retryable=True) from exc
        try:
            corpo = resposta.json()
        except (ValueError, TypeError):
            corpo = {}
        if resposta.status_code >= 400 or (isinstance(corpo, Mapping) and corpo.get("error")):
            erro = corpo.get("error") if isinstance(corpo, Mapping) else None
            codigo = str(erro.get("code") or resposta.status_code) if isinstance(erro, Mapping) else str(resposta.status_code)
            raise ErroRemotoMeta(
                "META_REMOTE_VALIDATION_FAILED" if "execution_options" in payload else "META_REMOTE_CREATE_FAILED",
                f"a Meta recusou {operacao.nome} (codigo {codigo})",
                retryable=resposta.status_code >= 500,
            )
        if not isinstance(corpo, Mapping):
            raise ErroRemotoMeta("META_INVALID_RESPONSE", "resposta Meta invalida")
        if exige_id:
            identificador = str(corpo.get("id") or "")
            if not identificador.isdigit():
                raise ErroRemotoMeta(
                    "META_REMOTE_RESULT_AMBIGUOUS",
                    f"a criacao de {operacao.nome} nao devolveu id confirmado",
                )
        return corpo

    async def _read_one(
        self, nome: str, identificador: str, segredo: SegredoEfemero,
    ) -> Mapping[str, Any]:
        campos = {
            "campaign": "id,account_id,name,objective,status,configured_status,effective_status,bid_strategy,special_ad_categories,advantage_state_info",
            "adset": "id,account_id,campaign_id,name,status,configured_status,effective_status,daily_budget,bid_strategy,billing_event,optimization_goal,destination_type,targeting,promoted_object",
            "creative": "id,account_id,name,status,effective_status,object_story_spec,asset_feed_spec,degrees_of_freedom_spec",
            "ad": "id,account_id,campaign_id,adset_id,name,status,configured_status,effective_status,creative",
        }
        if nome not in campos:
            raise ErroRemotoMeta("META_READBACK_FAILED", "tipo de objeto Meta desconhecido")
        try:
            resposta = await self._cliente.get(
                f"{self._base}/{self._versao}/{identificador}",
                params={"fields": campos[nome]},
                headers={"Authorization": segredo.cabecalho_bearer()},
            )
        except httpx.HTTPError as exc:
            raise ErroRemotoMeta(
                "META_READBACK_FAILED", "read-back Meta nao respondeu", retryable=True) from exc
        try:
            corpo = resposta.json()
        except (ValueError, TypeError) as exc:
            raise ErroRemotoMeta(
                "META_READBACK_FAILED", f"read-back de {nome} devolveu corpo invalido") from exc
        if (
            resposta.status_code >= 400
            or not isinstance(corpo, Mapping)
            or isinstance(corpo.get("error"), Mapping)
        ):
            raise ErroRemotoMeta("META_READBACK_FAILED", f"read-back de {nome} falhou")
        return corpo

    @staticmethod
    def _validar_read_back(
        nome: str,
        dados: Mapping[str, Any],
        *,
        payload: Mapping[str, Any],
        identificador: str,
        ids: Mapping[str, str],
    ) -> None:
        def divergiu(campo: str) -> None:
            raise ErroRemotoMeta(
                "META_READBACK_DIVERGENT",
                f"read-back de {nome} divergiu no campo {campo}",
            )

        if str(dados.get("id") or "") != identificador:
            divergiu("id")
        if nome in {"campaign", "adset", "ad"}:
            estado = dados.get("configured_status") or dados.get("status")
            if estado != "PAUSED":
                divergiu("status")
            efetivo = dados.get("effective_status")
            if efetivo not in {None, "PAUSED", "PENDING_REVIEW", "IN_PROCESS"}:
                divergiu("effective_status")
        if nome == "creative":
            if dados.get("status") in {"DELETED", "WITH_ISSUES"}:
                divergiu("status")
            if dados.get("effective_status") in {"DELETED", "WITH_ISSUES"}:
                divergiu("effective_status")
        if str(dados.get("name") or "") != str(payload.get("name") or ""):
            divergiu("name")
        if nome == "campaign":
            if dados.get("objective") != payload.get("objective"):
                divergiu("objective")
            categorias = tuple(dados.get("special_ad_categories") or ())
            if categorias != tuple(payload.get("special_ad_categories") or ()):
                divergiu("special_ad_categories")
        elif nome == "adset":
            if str(dados.get("campaign_id") or "") != ids.get("campaign"):
                divergiu("campaign_id")
            for campo in (
                "billing_event", "optimization_goal", "bid_strategy", "destination_type",
            ):
                if dados.get(campo) != payload.get(campo):
                    divergiu(campo)
            try:
                verba_lida = int(str(dados.get("daily_budget")))
            except (TypeError, ValueError):
                divergiu("daily_budget")
                return
            if verba_lida != payload.get("daily_budget"):
                divergiu("daily_budget")
        elif nome == "ad":
            if str(dados.get("adset_id") or "") != ids.get("adset"):
                divergiu("adset_id")
            criativo = dados.get("creative")
            creative_id = criativo.get("id") if isinstance(criativo, Mapping) else None
            if str(creative_id or "") != ids.get("creative"):
                divergiu("creative.id")
