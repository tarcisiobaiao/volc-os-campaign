"""Injected Graph transport for validation and authorized PAUSED creation."""
from __future__ import annotations

import json
import hashlib
import re
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
        detalhe_provedor: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.retryable = retryable
        # Names only. Provider ids remain backend-private even on failures.
        self.objetos_criados = objetos_criados
        self.detalhe_provedor = dict(detalhe_provedor or {})


def _texto_seguro_do_provedor(valor: Any, *, limite: int = 500) -> str | None:
    """Keep actionable Meta diagnostics without leaking tokens or raw ids."""
    texto = str(valor or "").strip()
    if not texto:
        return None
    texto = re.sub(
        r"(?i)(access_token(?:=|\s+))[^&\s]+", r"\1[redacted]", texto)
    texto = re.sub(r"\bact_([0-9]{4,40})\b", lambda m: f"act_••••{m.group(1)[-4:]}", texto)
    texto = re.sub(r"\b([0-9]{7,40})\b", lambda m: f"••••{m.group(1)[-4:]}", texto)
    return texto[:limite]


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
                pendentes.append(operacao.chave)
                continue
            payload = dict(operacao.payload)
            payload["execution_options"] = ["validate_only"]
            resposta = await self._post(operacao, payload, segredo, exige_id=False)
            if resposta.get("success") is not True:
                raise ErroRemotoMeta(
                    "META_REMOTE_RESULT_AMBIGUOUS",
                    f"validate_only de {operacao.chave} nao devolveu sucesso explicito",
                )
            validadas.append(operacao.chave)
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
        tipos: dict[str, str] = {}
        try:
            for operacao in plano.operacoes:
                payload = resolver_dependencias(operacao.payload, ids)
                if operacao.tipo_objeto in {"campaign", "adset", "ad"} and payload.get("status") != "PAUSED":
                    raise ErroDeNascimentoMeta(
                        "META_NOT_PAUSED", f"{operacao.chave} nao esta PAUSED no payload aprovado")
                validacao = dict(payload)
                validacao["execution_options"] = ["validate_only"]
                validado = await self._post(
                    operacao, validacao, segredo, exige_id=False)
                if validado.get("success") is not True:
                    raise ErroRemotoMeta(
                        "META_REMOTE_RESULT_AMBIGUOUS",
                        f"validate_only de {operacao.chave} nao devolveu sucesso explicito",
                    )
                payload_sha256 = hashlib.sha256(
                    json.dumps(
                        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                passo = await self._registro.preparar_passo(
                    plano_sha256=plano.plano_sha256,
                    approval_id=autorizacao.approval_id,
                    ator=autorizacao.ator,
                    nome=operacao.chave,
                    payload_sha256=payload_sha256,
                )
                if passo.estado == "AMBIGUO":
                    raise ErroRemotoMeta(
                        "META_RECONCILIATION_REQUIRED",
                        f"o passo {operacao.chave} esta ambiguo; reconciliar antes de continuar",
                    )
                if passo.estado == "CRIADO":
                    ids[operacao.chave] = str(passo.id_externo)
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
                    ids[operacao.chave] = str(resposta["id"])
                    try:
                        await self._registro.fechar_passo(
                            passo_ref=passo.passo_ref,
                            id_externo=ids[operacao.chave],
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
                    operacao.tipo_objeto, ids[operacao.chave], segredo)
                self._validar_read_back(
                    operacao.tipo_objeto,
                    dados,
                    payload=payload,
                    identificador=ids[operacao.chave],
                    ids=ids,
                )
                read_back[operacao.chave] = dados
                tipos[operacao.chave] = operacao.tipo_objeto
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
            chave: meta_dom.referencia_opaca_objeto(
                conta_externa, tipos[chave], identificador)
            for chave, identificador in ids.items()
        }
        return ResultadoNascimentoMeta(
            desfecho="CREATED_PAUSED",
            plano_sha256=plano.plano_sha256,
            referencias_opacas=opacas,
            read_back={
                chave: {
                    "status": dados.get("configured_status") or dados.get("status"),
                    "effective_status": dados.get("effective_status"),
                    "objective": dados.get("objective"),
                    "optimization_goal": dados.get("optimization_goal"),
                    "destination_type": dados.get("destination_type"),
                    "advantage_state_info": dados.get("advantage_state_info"),
                }
                for chave, dados in read_back.items()
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
            subcodigo = _texto_seguro_do_provedor(
                erro.get("error_subcode") if isinstance(erro, Mapping) else None)
            explicacoes = []
            if isinstance(erro, Mapping):
                for campo in ("error_user_title", "error_user_msg", "message"):
                    valor = _texto_seguro_do_provedor(erro.get(campo))
                    if valor and valor not in explicacoes:
                        explicacoes.append(valor)
            complemento = f": {' — '.join(explicacoes)}" if explicacoes else ""
            raise ErroRemotoMeta(
                "META_REMOTE_VALIDATION_FAILED" if "execution_options" in payload else "META_REMOTE_CREATE_FAILED",
                f"a Meta recusou {operacao.chave} (código {codigo}{f'/{subcodigo}' if subcodigo else ''}){complemento}",
                retryable=resposta.status_code >= 500,
                detalhe_provedor={
                    "code": codigo,
                    "error_subcode": subcodigo,
                    "type": _texto_seguro_do_provedor(
                        erro.get("type") if isinstance(erro, Mapping) else None),
                    "messages": explicacoes,
                },
            )
        if not isinstance(corpo, Mapping):
            raise ErroRemotoMeta("META_INVALID_RESPONSE", "resposta Meta invalida")
        if exige_id:
            identificador = str(corpo.get("id") or "")
            if not identificador.isdigit():
                raise ErroRemotoMeta(
                    "META_REMOTE_RESULT_AMBIGUOUS",
                    f"a criacao de {operacao.chave} nao devolveu id confirmado",
                )
        return corpo

    async def _read_one(
        self, nome: str, identificador: str, segredo: SegredoEfemero,
    ) -> Mapping[str, Any]:
        campos = {
            "campaign": "id,account_id,name,objective,status,configured_status,effective_status,bid_strategy,special_ad_categories,is_adset_budget_sharing_enabled,advantage_state_info",
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
            if bool(dados.get("is_adset_budget_sharing_enabled")) is not bool(
                payload.get("is_adset_budget_sharing_enabled")
            ):
                divergiu("is_adset_budget_sharing_enabled")
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
            criativo_esperado = payload.get("creative")
            esperado = (
                criativo_esperado.get("creative_id")
                if isinstance(criativo_esperado, Mapping) else None
            )
            if str(creative_id or "") != str(esperado or ""):
                divergiu("creative.id")
