"""Injected Graph transport for validation and authorized PAUSED creation."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
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
        criacao_descartada: bool = False,
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.retryable = retryable
        # Names only. Provider ids remain backend-private even on failures.
        self.objetos_criados = objetos_criados
        self.detalhe_provedor = dict(detalhe_provedor or {})
        # True apenas quando a própria Meta recusou o pedido: só nesse caso é
        # provado que nada foi criado. Transporte, corpo inválido ou resposta
        # sem id deixam o passo AMBÍGUO, nunca FALHO.
        self.criacao_descartada = criacao_descartada


def _texto_seguro_do_provedor(valor: Any, *, limite: int = 500) -> str | None:
    """Keep actionable Meta diagnostics without leaking tokens or raw ids."""
    texto = str(valor or "").strip()
    if not texto:
        return None
    # Segredos primeiro: um token pode conter dígitos e seria apenas mascarado
    # parcialmente pelas regras de ID se a ordem fosse invertida.
    texto = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", texto)
    texto = re.sub(
        r"(?i)(access[_ ]?token\s*(?:=|:|\s)\s*)[^&\s\"']+", r"\1[redacted]", texto)
    texto = re.sub(r"\bEAA[A-Za-z0-9_\-]{8,}\b", "[redacted]", texto)
    # Qualquer cadeia opaca longa — token, image_hash, assinatura de CDN.
    texto = re.sub(r"\b[A-Za-z0-9_\-]{28,}\b", "[redacted]", texto)
    texto = re.sub(r"\bact_([0-9]{4,40})\b", lambda m: f"act_••••{m.group(1)[-4:]}", texto)
    texto = re.sub(r"\b([0-9]{7,40})\b", lambda m: f"••••{m.group(1)[-4:]}", texto)
    return texto[:limite]


def _paises(alvo: Mapping[str, Any]) -> tuple[str, ...]:
    geo = alvo.get("geo_locations")
    paises = geo.get("countries") if isinstance(geo, Mapping) else None
    if not isinstance(paises, (list, tuple)):
        return ()
    return tuple(sorted(str(item).upper() for item in paises))


def _advantage_audience(alvo: Any) -> int | None:
    if not isinstance(alvo, Mapping):
        return None
    automacao = alvo.get("targeting_automation")
    if not isinstance(automacao, Mapping) or "advantage_audience" not in automacao:
        return None
    valor = automacao["advantage_audience"]
    if isinstance(valor, bool):
        return int(valor)
    try:
        return int(str(valor))
    except (TypeError, ValueError):
        return None


def _mesmo_destino(lido: Any, enviado: Any) -> bool:
    """Compara duas URLs pela forma canônica, sem afrouxar host nem caminho."""
    def canonica(valor: Any) -> tuple[str, str, str, str] | None:
        texto = str(valor or "").strip()
        if not texto:
            return None
        partes = urlparse(texto)
        if not partes.scheme or not partes.hostname:
            return None
        caminho = partes.path.rstrip("/") or "/"
        return (
            partes.scheme.lower(), partes.hostname.lower(), caminho, partes.query)
    a, b = canonica(lido), canonica(enviado)
    return a is not None and a == b


def _mesmo_instante(lido: Any, enviado: Any) -> bool:
    """A Meta devolve o horário no fuso da conta; o instante é que precisa bater."""
    if enviado in (None, ""):
        return True
    def instante(valor: Any) -> datetime | None:
        texto = str(valor or "").strip()
        if not texto:
            return None
        try:
            return datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None
    a, b = instante(lido), instante(enviado)
    if a is None or b is None or a.tzinfo is None or b.tzinfo is None:
        return False
    return a == b


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
                        # Só a recusa explícita da Meta prova que o objeto não
                        # nasceu. Qualquer outra falha depois do despacho fica
                        # AMBÍGUA para não bloquear a reconciliação por leitura.
                        if exc.criacao_descartada:
                            await self._registro.falhar_passo(
                                passo_ref=passo.passo_ref, codigo=exc.codigo)
                        else:
                            try:
                                await self._registro.marcar_ambiguo(
                                    passo_ref=passo.passo_ref)
                            except Exception:
                                pass
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
                    conta_externa=plano.conta_externa,
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
        opacas = {
            chave: meta_dom.referencia_opaca_objeto(
                plano.conta_externa, tipos[chave], identificador)
            for chave, identificador in ids.items()
        }
        return ResultadoNascimentoMeta(
            desfecho="CREATED_PAUSED",
            plano_sha256=plano.plano_sha256,
            referencias_opacas=opacas,
            read_back={
                chave: {
                    # O AdCreative não é veiculável: ele nasce ACTIVE por
                    # construção e só entrega através de um Ad PAUSED. Declarar
                    # isso evita afirmar "tudo pausado" sobre um objeto que a
                    # Meta nunca pausa.
                    "veiculavel": tipos[chave] in {"campaign", "adset", "ad"},
                    "status": dados.get("configured_status") or dados.get("status"),
                    "effective_status": dados.get("effective_status"),
                    "objective": dados.get("objective"),
                    "optimization_goal": dados.get("optimization_goal"),
                    "advantage_audience_lido": _advantage_audience(dados.get("targeting")),
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
                # 4xx com corpo de erro é recusa provada: nada foi criado.
                # 5xx pode ter criado antes de falhar e continua ambíguo.
                criacao_descartada=400 <= resposta.status_code < 500,
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
            "campaign": "id,account_id,name,objective,buying_type,status,configured_status,effective_status,bid_strategy,special_ad_categories,is_adset_budget_sharing_enabled,advantage_state_info",
            "adset": "id,account_id,campaign_id,name,status,configured_status,effective_status,daily_budget,lifetime_budget,bid_strategy,billing_event,optimization_goal,destination_type,start_time,end_time,targeting,promoted_object,attribution_spec",
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
        conta_externa: str,
    ) -> None:
        def divergiu(campo: str) -> None:
            raise ErroRemotoMeta(
                "META_READBACK_DIVERGENT",
                f"read-back de {nome} divergiu no campo {campo}",
            )

        def booleano(campo: str) -> bool:
            """Ausência não é `false`. A Meta precisa devolver o campo lido."""
            if campo not in dados:
                divergiu(campo)
            valor = dados[campo]
            if isinstance(valor, bool):
                return valor
            if isinstance(valor, str) and valor.strip().lower() in {"true", "false"}:
                return valor.strip().lower() == "true"
            divergiu(campo)
            raise AssertionError  # pragma: no cover - divergiu sempre levanta

        if str(dados.get("id") or "") != identificador:
            divergiu("id")
        # O objeto precisa pertencer à mesma conta que o plano resolveu.
        conta_lida = str(dados.get("account_id") or "").removeprefix("act_").strip()
        if conta_lida and conta_lida != conta_externa:
            divergiu("account_id")
        if nome in {"campaign", "adset", "ad"}:
            estado = dados.get("configured_status") or dados.get("status")
            if estado != "PAUSED":
                divergiu("status")
            efetivo = dados.get("effective_status")
            if efetivo not in {None, "PAUSED", "PENDING_REVIEW", "IN_PROCESS"}:
                divergiu("effective_status")
        if nome == "creative":
            # O AdCreative não é um objeto veiculável: ele só entrega através de
            # um Ad, e a Meta o devolve ACTIVE por construção. O que precisa ser
            # recusado é o criativo inutilizável.
            if dados.get("status") in {"DELETED", "WITH_ISSUES"}:
                divergiu("status")
            if dados.get("effective_status") in {"DELETED", "WITH_ISSUES"}:
                divergiu("effective_status")
        if str(dados.get("name") or "") != str(payload.get("name") or ""):
            divergiu("name")
        if nome == "campaign":
            for campo in ("objective", "buying_type"):
                if payload.get(campo) is not None and dados.get(campo) != payload.get(campo):
                    divergiu(campo)
            categorias = tuple(dados.get("special_ad_categories") or ())
            if categorias != tuple(payload.get("special_ad_categories") or ()):
                divergiu("special_ad_categories")
            if booleano("is_adset_budget_sharing_enabled") is not bool(
                payload.get("is_adset_budget_sharing_enabled")
            ):
                divergiu("is_adset_budget_sharing_enabled")
        elif nome == "adset":
            if str(dados.get("campaign_id") or "") != ids.get("campaign"):
                divergiu("campaign_id")
            for campo in (
                "billing_event", "optimization_goal", "bid_strategy", "destination_type",
            ):
                # Só confere o que foi realmente enviado: destination_type não
                # pertence a esta receita e a Meta pode devolver o dela.
                if campo in payload and dados.get(campo) != payload.get(campo):
                    divergiu(campo)
            try:
                verba_lida = int(str(dados.get("daily_budget")))
            except (TypeError, ValueError):
                divergiu("daily_budget")
                return
            if verba_lida != payload.get("daily_budget"):
                divergiu("daily_budget")
            if not _mesmo_instante(dados.get("start_time"), payload.get("start_time")):
                divergiu("start_time")
            alvo_lido = dados.get("targeting")
            alvo_enviado = payload.get("targeting")
            if isinstance(alvo_enviado, Mapping):
                if not isinstance(alvo_lido, Mapping):
                    divergiu("targeting")
                    return
                paises_enviados = _paises(alvo_enviado)
                if _paises(alvo_lido) != paises_enviados:
                    divergiu("targeting.geo_locations.countries")
                for campo in ("age_min", "age_max"):
                    if campo in alvo_enviado and str(alvo_lido.get(campo)) != str(
                        alvo_enviado[campo]
                    ):
                        divergiu(f"targeting.{campo}")
                # Advantage+ Audience: confere quando a Meta devolve o campo.
                # A leitura pode omiti-lo, e nesse caso o recibo declara que a
                # escolha não foi confirmada em vez de fingir confirmação.
                esperado = _advantage_audience(alvo_enviado)
                lido = _advantage_audience(alvo_lido)
                if lido is not None and esperado is not None and lido != esperado:
                    divergiu("targeting.targeting_automation.advantage_audience")
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
        if nome == "creative":
            # Nunca emitimos asset_feed_spec. Se a Meta devolver um, o objeto
            # criado não é o criativo estático que foi aprovado.
            if "asset_feed_spec" not in payload and dados.get("asset_feed_spec"):
                divergiu("asset_feed_spec")
            historia_lida = dados.get("object_story_spec")
            historia_enviada = payload.get("object_story_spec")
            if isinstance(historia_enviada, Mapping):
                if not isinstance(historia_lida, Mapping):
                    divergiu("object_story_spec")
                    return
                if str(historia_lida.get("page_id") or "") != str(
                    historia_enviada.get("page_id") or ""
                ):
                    divergiu("object_story_spec.page_id")
                enviado = historia_enviada.get("link_data")
                lido = historia_lida.get("link_data")
                if isinstance(enviado, Mapping):
                    if not isinstance(lido, Mapping):
                        divergiu("object_story_spec.link_data")
                        return
                    for campo in ("image_hash", "message", "name", "description"):
                        if campo in enviado and str(lido.get(campo) or "") != str(
                            enviado[campo] or ""
                        ):
                            divergiu(f"object_story_spec.link_data.{campo}")
                    # O destino compara por forma canônica: a Meta pode devolver
                    # o mesmo endereço com a barra final normalizada, e tratar
                    # isso como divergência pararia a saga por nada. Um destino
                    # DIFERENTE continua divergindo.
                    if "link" in enviado and not _mesmo_destino(
                        lido.get("link"), enviado["link"]
                    ):
                        divergiu("object_story_spec.link_data.link")
