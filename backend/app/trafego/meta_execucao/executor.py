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
        exige_reconciliacao: bool = False,
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
        # ⚠️ Marcado pela SAGA, no ponto exato em que ela deixa um passo
        # AMBÍGUO no ledger. É a única fonte da verdade sobre "precisa
        # reconciliar", e ela precisa viajar com a exceção.
        #
        # A rota tinha uma lista de códigos para adivinhar isso, e a lista
        # errava: `META_REMOTE_CREATE_FAILED` com um 500 da Meta deixa o passo
        # AMBIGUOUS no banco, e a resposta HTTP dizia 422 com
        # `reconciliacao_necessaria=false`. O ledger e o protocolo contavam
        # histórias diferentes sobre o mesmo despacho.
        self.exige_reconciliacao = exige_reconciliacao


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
    # Cadeia opaca longa — token, image_hash, assinatura de CDN. ⚠️ Nomes de
    # campo da Marketing API também são longos (`is_adset_budget_sharing_enabled`
    # tem 31 caracteres) e apagá-los tiraria do operador exatamente o campo que
    # ele precisa corrigir. Identificador snake_case é preservado.
    texto = re.sub(r"\b[A-Za-z0-9_\-]{28,}\b", _mascarar_cadeia_opaca, texto)
    texto = re.sub(r"\bact_([0-9]{4,40})\b", lambda m: f"act_••••{m.group(1)[-4:]}", texto)
    texto = re.sub(r"\b([0-9]{7,40})\b", lambda m: f"••••{m.group(1)[-4:]}", texto)
    return texto[:limite]


_IDENTIFICADOR_DE_CAMPO = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


def _mascarar_cadeia_opaca(achado: "re.Match[str]") -> str:
    texto = achado.group(0)
    return texto if _IDENTIFICADOR_DE_CAMPO.fullmatch(texto) else "[redacted]"


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
    def canonica(valor: Any) -> tuple[str, ...] | None:
        texto = str(valor or "").strip()
        if not texto:
            return None
        partes = urlparse(texto)
        if not partes.scheme or not partes.hostname:
            return None
        caminho = partes.path.rstrip("/") or "/"
        esquema = partes.scheme.lower()
        # Porta e fragmento entram: uma porta não padrão ou outra rota de
        # cliente levam o clique a outro lugar.
        try:
            porta = partes.port
        except ValueError:
            return None
        padrao = {"https": 443, "http": 80}.get(esquema)
        return (
            esquema, partes.hostname.lower(),
            str(porta if porta is not None else padrao),
            caminho, partes.query, partes.fragment)
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


#: Máscara de campos por tipo de objeto, usada tanto no read-back da saga
#: quanto na reconciliação por leitura. Uma máscara só: se a reconciliação
#: lesse menos campos que o read-back, ela poderia "confirmar" um objeto que a
#: saga teria recusado — e fechar um recibo verde sobre uma divergência.
#:
#: ⚠️ `created_time` entra em campaign, adset e ad porque é o único campo que
#: correlaciona um objeto ao DESPACHO que o criou. Nome igual não prova
#: nascimento: a conta pode já ter uma campanha homônima com a mesma receita, e
#: a reconciliação a adotaria. `AdCreative` não expõe `created_time` na
#: Marketing API, e a consequência está codificada em `reconciliacao.py`: um
#: criativo nunca é fechado por leitura.
CAMPOS_DE_LEITURA: Mapping[str, str] = {
    "campaign": "id,account_id,name,objective,buying_type,status,configured_status,effective_status,bid_strategy,special_ad_categories,is_adset_budget_sharing_enabled,advantage_state_info,created_time",
    "adset": "id,account_id,campaign_id,name,status,configured_status,effective_status,daily_budget,lifetime_budget,bid_strategy,billing_event,optimization_goal,destination_type,start_time,end_time,targeting,promoted_object,attribution_spec,created_time",
    "creative": "id,account_id,name,status,effective_status,object_story_spec,asset_feed_spec,degrees_of_freedom_spec",
    "ad": "id,account_id,campaign_id,adset_id,name,status,configured_status,effective_status,creative,created_time",
}


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
            try:
                resposta = await self._post(operacao, payload, segredo, exige_id=False)
            except httpx.TimeoutException:
                # Silêncio da rede numa chamada `validate_only` NÃO é recusa da
                # Meta, e também não é o silêncio ambíguo de `criar_pausada`:
                # o pedido levava `execution_options=["validate_only"]`, então
                # não existe objeto para ter nascido enquanto ninguém olhava.
                # Por isso este é o único ponto do executor onde um timeout vira
                # erro nomeado e retentável. `_post` continua repassando a
                # exceção crua (o `except httpx.TimeoutException: raise` dele)
                # para a saga de criação, onde o mesmo silêncio precisa virar
                # AMBIGUO e exigir reconciliação.
                #
                # A mensagem cita só `tipo_objeto` — vocabulário fechado
                # (campaign/adset/creative/ad). Nada de texto do operador, id da
                # Meta ou detalhe do provedor entra aqui.
                raise ErroRemotoMeta(
                    "META_VALIDATE_TIMEOUT",
                    "a Meta nao respondeu a validacao de "
                    f"{operacao.tipo_objeto} a tempo; nada foi criado",
                    retryable=True,
                ) from None
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
                        exige_reconciliacao=True,
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
                            # O passo ficou AMBIGUO no ledger; a exceção precisa
                            # dizer isso, senão a resposta HTTP afirma o oposto.
                            exc.exige_reconciliacao = True
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
                            exige_reconciliacao=True,
                        ) from exc
                # Confirm each durable step before allowing the next dependent
                # object to be created. A mismatch stops the saga immediately.
                #
                # ⚠️ O recibo JÁ FECHOU aqui, e essa ordem é deliberada: o id que
                # a Meta acabou de devolver precisa estar gravado antes de
                # qualquer outra coisa, senão uma queda entre o POST e o INSERT
                # perde para sempre a única prova de que o objeto nasceu.
                #
                # O preço é que uma divergência de leitura deixaria o livro
                # dizendo apenas CREATED. Por isso ela é MARCADA no passo antes
                # de a exceção subir: a resposta HTTP diz 502, e o recibo passa
                # a dizer o mesmo.
                try:
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
                except ErroRemotoMeta as exc:
                    marcar = getattr(self._registro, "marcar_readback_divergente", None)
                    if marcar is not None:
                        try:
                            await marcar(passo_ref=passo.passo_ref, codigo=exc.codigo)
                        except Exception:
                            # Falhar ao anotar não pode apagar a divergência que
                            # a exceção carrega: ela continua subindo.
                            pass
                    raise
                read_back[operacao.chave] = dados
                tipos[operacao.chave] = operacao.tipo_objeto
        except httpx.TimeoutException as exc:
            raise ErroRemotoMeta(
                "META_REMOTE_RESULT_AMBIGUOUS",
                "a Meta nao respondeu; nao reenviar antes de reconciliar por leitura",
                retryable=False,
                objetos_criados=tuple(ids),
                exige_reconciliacao=True,
            ) from exc
        except ErroRemotoMeta as exc:
            if not ids or exc.objetos_criados:
                raise
            raise ErroRemotoMeta(
                exc.codigo,
                f"{exc}; a saga parou com objetos PAUSED ja criados: {', '.join(ids)}",
                retryable=False,
                objetos_criados=tuple(ids),
                detalhe_provedor=exc.detalhe_provedor,
                criacao_descartada=exc.criacao_descartada,
                # ⚠️ A bandeira SOBREVIVE ao reempacotamento. Perdê-la aqui
                # devolveria 422 sobre um passo que ficou AMBIGUO no banco.
                exige_reconciliacao=exc.exige_reconciliacao,
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
        validacao = "execution_options" in payload
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
                "META_TRANSPORT_ERROR", "a Meta nao respondeu ao pedido",
                # Só a validação pode ser repetida sozinha: ela não cria nada.
                # Um transporte que cai depois de despachar uma CRIAÇÃO pode ter
                # criado o objeto, e repetir duplicaria a campanha.
                retryable=validacao) from exc
        try:
            corpo = resposta.json()
        except (ValueError, TypeError):
            corpo = {}
        if resposta.status_code >= 400 or (isinstance(corpo, Mapping) and corpo.get("error")):
            erro = corpo.get("error") if isinstance(corpo, Mapping) else None
            # Descarte só é PROVADO quando a própria Meta responde 4xx com um
            # objeto de erro reconhecível. Um 400 de gateway, com corpo vazio ou
            # HTML, pode ter chegado depois do encaminhamento: fica ambíguo.
            recusa_da_meta = isinstance(erro, Mapping) and (
                erro.get("code") is not None or erro.get("message") is not None)
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
                "META_REMOTE_VALIDATION_FAILED" if validacao else "META_REMOTE_CREATE_FAILED",
                f"a Meta recusou {operacao.chave} (código {codigo}{f'/{subcodigo}' if subcodigo else ''}){complemento}",
                retryable=validacao and resposta.status_code >= 500,
                criacao_descartada=(
                    recusa_da_meta and 400 <= resposta.status_code < 500),
                detalhe_provedor={
                    # A tela monta o título com objeto + código + subcódigo. Sem
                    # este campo ela teria que extrair o objeto por regex da
                    # frase traduzida — quebraria no dia em que a frase mudasse.
                    # `chave` já viaja na mensagem e é vocabulário fechado mais,
                    # no lote, a `variation_key` validada pelo contrato.
                    "objeto": operacao.chave,
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
        campos = CAMPOS_DE_LEITURA
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
        # O objeto precisa pertencer à mesma conta que o plano resolveu, e a
        # ausência do campo não vale como pertencimento: uma resposta parcial
        # com id, nome e status certos passaria sem provar a fronteira.
        conta_lida = str(dados.get("account_id") or "").removeprefix("act_").strip()
        if not conta_lida or conta_lida != conta_externa:
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
                    # A chamada para ação é uma decisão do operador: tipo e
                    # destino dela precisam voltar iguais.
                    cta_enviado = enviado.get("call_to_action")
                    if isinstance(cta_enviado, Mapping):
                        cta_lido = lido.get("call_to_action")
                        if not isinstance(cta_lido, Mapping):
                            divergiu("object_story_spec.link_data.call_to_action")
                            return
                        if str(cta_lido.get("type") or "") != str(
                            cta_enviado.get("type") or ""
                        ):
                            divergiu("object_story_spec.link_data.call_to_action.type")
                        destino_enviado = cta_enviado.get("value")
                        destino_lido = cta_lido.get("value")
                        if isinstance(destino_enviado, Mapping) and "link" in destino_enviado:
                            if not isinstance(destino_lido, Mapping) or not _mesmo_destino(
                                destino_lido.get("link"), destino_enviado["link"]
                            ):
                                divergiu(
                                    "object_story_spec.link_data.call_to_action.value.link")
                # O ator do Instagram é identidade: se a Meta devolver outro, o
                # anúncio não é mais o que foi aprovado.
                if str(historia_lida.get("instagram_actor_id") or "") != str(
                    historia_enviada.get("instagram_actor_id") or ""
                ):
                    divergiu("object_story_spec.instagram_actor_id")
