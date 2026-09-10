"""Injected Graph transport for validation and authorized PAUSED creation."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlparse

import httpx

from app.trafego.meta import dominio as meta_dom
from app.trafego.meta.credenciais import SegredoEfemero

from .compilador import PlanoCompiladoMeta, OperacaoMeta, resolver_dependencias
from .contrato import (
    MOTIVO_DESTINO_SHOP_NAO_PROVADO,
    DESTINATION_TYPE_WEBSITE_OPT_OUT,
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
)
from . import contrato as contrato_meta
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
        evidencia_duravel: bool = True,
    ) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.retryable = retryable
        # ⚠️ FALSO quando o read-back ACONTECEU mas NÃO ficou gravado. É um fato
        # sobre o LIVRO, nunca sobre o objeto: a Meta aceitou, o id está
        # registrado e a leitura até pode ter conferido — quem falhou fomos nós.
        #
        # A distinção existe porque confundi-la foi o defeito: com todas as
        # escritas de evidência falhando, a saga criava os quatro objetos e
        # devolvia 200 CREATED_PAUSED. Um recibo incompleto lido como completo é
        # pior que um recibo vazio — ele parece adjudicável.
        self.evidencia_duravel = evidencia_duravel
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


class _EvidenciaNaoGravada(RuntimeError):
    """A evidência do read-back não entrou no livro. Não diz nada do objeto.

    ⚠️ Deliberadamente NÃO é um `ErroRemotoMeta`. Se fosse, o `except` da saga a
    trataria como resultado da Meta, e o reempacotamento de 502 afirmaria que a
    Meta fez algo que ela não fez. Quem falhou fomos nós, gravando.
    """

    def __init__(self, causa: str) -> None:
        super().__init__(causa)
        #: Vocabulário FECHADO — o código do ledger, ou o nome da classe da
        #: exceção. Nunca a mensagem crua: ela pode carregar URL, corpo de
        #: resposta ou qualquer coisa que o transporte tenha anexado.
        self.causa = causa


#: A recusa que o ledger emite quando o token de reivindicação já não vale.
#: Vocabulário FECHADO: comparar por substring de mensagem livre deixaria
#: qualquer erro que mencionasse a palavra virar "fui cercado" — e o caminho do
#: cercado preserva o id em vez de reconciliar, então errar aqui é caro.
CODIGO_CERCADO = "META_STEP_CLAIM_FENCED"


def _cercado(exc: BaseException) -> bool:
    """Se esta recusa do ledger foi a cerca, e não outra coisa.

    ⚠️ O ledger real traduz a exceção do PostgreSQL em
    `META_CREATE_LEDGER_REJECTED` com a mensagem da RPC; o dublê hermético
    levanta o código diretamente. As duas formas precisam ser reconhecidas, ou a
    garantia existiria só num dos dois mundos.
    """
    codigo = str(getattr(exc, "codigo", "") or "")
    if codigo == CODIGO_CERCADO:
        return True
    return codigo == "META_CREATE_LEDGER_REJECTED" and CODIGO_CERCADO in str(exc)


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


def _codigo_numerico_do_provedor(valor: Any) -> str | None:
    """Structured error codes are diagnostics, not account identifiers.

    Never pass arbitrary provider text through this exception to redaction.
    Graph codes are non-negative 32-bit integers; bools, floats, long ids and
    strings containing credentials remain invalid here.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        return None
    texto = str(valor)
    if not re.fullmatch(r"[0-9]{1,10}", texto):
        return None
    numero = int(texto)
    return str(numero) if numero <= 2_147_483_647 else None


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


def _inicio_confere(lido: Any, enviado: Any, criado_em: Any) -> bool:
    """An elapsed start can only normalize to the object's own creation time.

    Graph clamps an already elapsed requested start to created_time. Exact
    future schedules still must match, as must end_time. The object remains
    explicitly PAUSED, checked independently by the caller.
    """
    if _mesmo_instante(lido, enviado):
        return True
    if not _mesmo_instante(lido, criado_em) or criado_em in (None, ""):
        return False
    try:
        requested = datetime.fromisoformat(str(enviado).replace("Z", "+00:00"))
        created = datetime.fromisoformat(str(criado_em).replace("Z", "+00:00"))
        return requested.tzinfo is not None and created.tzinfo is not None and requested < created
    except (ValueError, TypeError):
        return False


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
    "campaign": "id,account_id,name,objective,buying_type,status,configured_status,effective_status,daily_budget,lifetime_budget,bid_strategy,special_ad_categories,is_adset_budget_sharing_enabled,advantage_state_info,created_time",
    "adset": "id,account_id,campaign_id,name,status,configured_status,effective_status,daily_budget,lifetime_budget,bid_strategy,billing_event,optimization_goal,destination_type,start_time,end_time,targeting,promoted_object,attribution_spec,created_time",
    # destination_spec is now supported by the official v26 changelog and SDK
    # evidence read on 2026-09-09. New snapshots require exact opt-out readback;
    # old snapshots retain the historical interpretation of a missing field.
    #
    # ⚠️ `effective_status` continua OMITIDO, com duas
    # fontes oficiais concordantes, lidas em 07/09/2026:
    #
    #   1. O catálogo gerado do SDK v26.0.0 enumera `status`,
    #      `destination_spec`, `object_story_spec`, `asset_feed_spec` e
    #      `degrees_of_freedom_spec` para AdCreative — e NÃO enumera
    #      `effective_status`. Os campos parecidos que existem são outros:
    #      `effective_authorization_category`, `effective_instagram_media_id`
    #      e `effective_object_story_id`.
    #      https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/26.0.0/facebook_business/adobjects/adcreative.py
    #   2. A referência pública de AdCreative documenta `status` com os valores
    #      `ACTIVE, IN_PROCESS, WITH_ISSUES, DELETED` e não documenta
    #      `effective_status`.
    #      https://developers.facebook.com/docs/marketing-api/reference/ad-creative/
    #
    # Pedir um campo que o catálogo não tem arrisca uma falha na leitura:
    # a Graph pode recusar a leitura inteira por
    # um campo inválido, e o read-back de todo criativo passaria a falhar —
    # depois de o objeto já ter nascido. Ausência no catálogo é sinal de risco,
    # não prova de recusa remota; por isso o campo é OMITIDO do pedido e seu
    # valor NÃO é inventado em lugar nenhum.
    #
    # Os estados de AdCreative são de BIBLIOTECA (ACTIVE/IN_PROCESS/
    # WITH_ISSUES/DELETED), não de veiculação. Um criativo não é pausável, e
    # `PAUSED` nunca foi esperado dele.
    "creative": "id,account_id,name,status,object_story_spec,object_story_id,effective_object_story_id,url_tags,asset_feed_spec,degrees_of_freedom_spec,destination_spec",
    "ad": "id,account_id,campaign_id,adset_id,name,status,configured_status,effective_status,creative,creative_asset_groups_spec,created_time",
}


def _form(payload: Mapping[str, Any]) -> dict[str, str]:
    saida: dict[str, str] = {}
    for chave, valor in payload.items():
        if isinstance(valor, (dict, list, tuple, bool)):
            saida[chave] = json.dumps(valor, separators=(",", ":"), ensure_ascii=False)
        else:
            saida[chave] = str(valor)
    return saida


def _evidencia_do_readback(
    tipo: str, dados: Any, *, conferido: bool,
) -> dict[str, Any]:
    """A projeção SANITIZADA do que a leitura devolveu.

    Só campos de vocabulário fechado e valores curtos. Nada de id externo, nada
    de texto do operador, nada de `object_story_spec` inteiro — a evidência
    existe para adjudicar um incidente, não para virar uma segunda cópia do
    payload dentro do ledger. A RPC recusa a gravação se encontrar chave
    sensível, e essa recusa é a rede de segurança, não a primeira defesa.
    """
    leitura = dados if isinstance(dados, Mapping) else {}
    destino = leitura.get("destination_spec")
    tipo_destino = destino.get("destination_type") if isinstance(destino, Mapping) else None
    return {
        "matched": bool(conferido),
        "tipo": tipo,
        "status": str(leitura.get("configured_status") or leitura.get("status") or "")[:40] or None,
        "effective_status": (
            str(leitura.get("effective_status") or "")[:40] or None
            if tipo in {"campaign", "adset", "ad"} else "NAO_PEDIDO"
        ),
        "objective": str(leitura.get("objective") or "")[:60] or None,
        "optimization_goal": str(leitura.get("optimization_goal") or "")[:60] or None,
        "advantage_audience_lido": _advantage_audience(leitura.get("targeting")),
        "destination_type_lido": (
            tipo_destino if tipo_destino in {
                DESTINATION_TYPE_WEBSITE_OPT_OUT, "WEBSITE_AND_SHOP", "WEBSITE"
            } else None
        ) if isinstance(tipo_destino, str) else None,
    }


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
        # ⚠️ O LEDGER PRECISA SABER GRAVAR READ-BACK ANTES DO PRIMEIRO POST.
        #
        # Havia um caminho legado adiante: sem `registrar_readback`, a saga
        # seguia gravando só a divergência — e, sem nem isso, seguia em
        # silêncio. Silêncio não é compatibilidade. Nenhum ledger do runtime
        # está nessa situação; o caminho existia para dublês antigos, e um dublê
        # não é motivo para o servidor aceitar despachar sem poder registrar o
        # que leu. A recusa acontece aqui, antes de qualquer efeito externo.
        if not callable(getattr(self._registro, "registrar_readback", None)):
            raise ErroDeNascimentoMeta(
                "META_READBACK_LEDGER_UNAVAILABLE",
                "este registro nao sabe gravar read-back; nada e despachado",
            )
        # ⚠️ O PORTÃO DO DESTINO, ANTES DO PRIMEIRO POST.
        #
        # C01 do contrato mestre: "any inability to prove no unauthorized Shop
        # redirection blocks create_paused". O plano compilado carrega a prova
        # justamente para que a recusa aconteça aqui — no único ponto por onde
        # todo despacho passa — e não numa rota que alguém possa contornar.
        if not plano.destino_website_provado:
            raise ErroDeNascimentoMeta(
                "META_SHOP_REDIRECT_UNPROVEN", MOTIVO_DESTINO_SHOP_NAO_PROVADO)
        # ⚠️ Um plano sem recibo de peça não é despachável: a mídia sairia sem
        # atestação nenhuma por trás. O compilador emite um manifesto por
        # `asset_ref` e o banco exige de 1 a 10 recibos — chegar aqui vazio
        # significa snapshot de outra origem.
        if not plano.asset_supply_manifests:
            raise ErroDeNascimentoMeta(
                "META_ASSET_SUPPLY_MANIFEST_MISSING",
                "este plano nao carrega o recibo de politica das pecas")
        ids: dict[str, str] = {}
        read_back: dict[str, Mapping[str, Any]] = {}
        tipos: dict[str, str] = {}
        try:
            for operacao in plano.operacoes:
                # ⚠️ A PROVA É RECONFERIDA A CADA DEGRAU, porque cada degrau é um
                # POST NOVO. A saga tem quatro passos e pode atravessar o
                # instante em que a atestação vence; deixar o terceiro sair
                # porque o primeiro saiu a tempo é o mesmo defeito da porta,
                # noventa segundos depois.
                #
                # ⚠️ ANTES de `preparar_passo`, de propósito. Depois dele, um
                # passo recusado deixaria uma linha IN_FLIGHT que nunca foi
                # despachada: a recuperação a promoveria a AMBIGUOUS, procuraria
                # na conta um objeto que não existe e ficaria ambígua para
                # sempre — além de prender o índice de gêmeo entre aprovações.
                vencidas = plano.provas_de_midia_vencidas(contrato_meta.agora_utc())
                if vencidas:
                    raise ErroDeNascimentoMeta(
                        "META_ASSET_POLICY_RECEIPT_EXPIRED",
                        "a atestacao da peca venceu durante o despacho; os objetos "
                        "ja criados permanecem PAUSED e legiveis, e nenhum passo "
                        "novo foi enviado",
                    )
                payload = resolver_dependencias(operacao.payload, ids)
                if operacao.tipo_objeto in {"campaign", "adset", "ad"} and payload.get("status") != "PAUSED":
                    raise ErroDeNascimentoMeta(
                        "META_NOT_PAUSED", f"{operacao.chave} nao esta PAUSED no payload aprovado")
                validacao = dict(payload)
                validacao["execution_options"] = ["validate_only"]
                try:
                    validado = await self._post(
                        operacao, validacao, segredo, exige_id=False)
                except httpx.TimeoutException:
                    # No claim or create POST exists for this step yet. Keep
                    # earlier durable IDs, but do not invent an ambiguous step
                    # that reconciliation can never find. A retry still passes
                    # the same approval and ledger; completed steps are reused.
                    raise ErroRemotoMeta(
                        "META_VALIDATE_TIMEOUT",
                        f"a validacao de {operacao.chave} nao respondeu a tempo; "
                        "a criacao deste passo nao foi enviada. Retome a mesma "
                        "operacao; objetos anteriores permanecem PAUSED",
                        retryable=True,
                        objetos_criados=tuple(ids),
                        detalhe_provedor={"objeto": operacao.chave},
                        exige_reconciliacao=False,
                    ) from None
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
                # ⚠️ O TOKEN DA REIVINDICAÇÃO, e ele muda ao longo do passo. É a
                # cerca: só quem o carrega conclui este despacho. `fechar_passo`
                # devolve um token GIRADO, e é esse que autoriza anotar o
                # read-back — separando a autoridade de FECHAR da autoridade de
                # CONFERIR.
                token = passo.claim_token
                if passo.estado == "CRIADO":
                    ids[operacao.chave] = str(passo.id_externo)
                else:
                    try:
                        resposta = await self._post(
                            operacao, payload, segredo, exige_id=True)
                    except httpx.TimeoutException:
                        await self._marcar_ambiguo_sem_derrubar(passo.passo_ref, token)
                        raise
                    except ErroRemotoMeta as exc:
                        # Só a recusa explícita da Meta prova que o objeto não
                        # nasceu. Qualquer outra falha depois do despacho fica
                        # AMBÍGUA para não bloquear a reconciliação por leitura.
                        if exc.criacao_descartada:
                            await self._registro.falhar_passo(
                                passo_ref=passo.passo_ref, codigo=exc.codigo,
                                claim_token=str(token))
                        else:
                            await self._marcar_ambiguo_sem_derrubar(
                                passo.passo_ref, token)
                            # O passo ficou AMBIGUO no ledger; a exceção precisa
                            # dizer isso, senão a resposta HTTP afirma o oposto.
                            exc.exige_reconciliacao = True
                        raise
                    ids[operacao.chave] = str(resposta["id"])
                    try:
                        token = await self._registro.fechar_passo(
                            passo_ref=passo.passo_ref,
                            id_externo=ids[operacao.chave],
                            claim_token=str(passo.claim_token),
                        )
                    except Exception as exc:
                        if _cercado(exc):
                            # ⚠️ A REQUISIÇÃO JÁ FOI ENVIADA E O OBJETO PODE
                            # EXISTIR. Outro processo tomou a reivindicação
                            # enquanto o POST estava no ar; nenhuma linha de
                            # banco cancela o que já saiu. Jogar o id fora
                            # perderia a única prova disso, e concluir por cima
                            # sobrescreveria uma decisão mais nova. O id vira
                            # OBSERVAÇÃO, e a leitura decide.
                            raise await self._registrar_despacho_cercado(
                                operacao, passo.passo_ref,
                                str(passo.claim_token), ids[operacao.chave],
                                ids=ids,
                            ) from exc
                        await self._marcar_ambiguo_sem_derrubar(
                            passo.passo_ref, passo.claim_token)
                        raise ErroRemotoMeta(
                            "META_REMOTE_RESULT_AMBIGUOUS",
                            "a Meta criou o objeto, mas o recibo nao fechou; reconciliar por leitura",
                            exige_reconciliacao=True,
                            objetos_criados=tuple(ids),
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
                # ⚠️ ZERADO A CADA PASSO, e isto conserta um defeito real.
                #
                # A primeira versão lia `locals().get("dados")` no tratamento da
                # divergência. `dados` é de escopo de FUNÇÃO, não de iteração:
                # quando `_read_one` falhava no AdSet, `dados` ainda continha a
                # leitura da Campaign — e a evidência durável da divergência do
                # AdSet era gravada com o status, o objetivo e o Advantage do
                # OBJETO ANTERIOR. Um recibo que descreve o objeto errado é pior
                # que um recibo vazio: ele parece adjudicável.
                dados: Mapping[str, Any] | None = None
                try:
                    dados = await self._read_one(
                        operacao.tipo_objeto, ids[operacao.chave], segredo,
                        regulatory="regional_regulation_identities" in payload)
                    self._validar_read_back(
                        operacao.tipo_objeto,
                        dados,
                        payload=payload,
                        identificador=ids[operacao.chave],
                        ids=ids,
                        conta_externa=plano.conta_externa,
                    )
                except ErroRemotoMeta as exc:
                    # ⚠️ A DIVERGÊNCIA É GRAVADA COM EVIDÊNCIA, não só com um
                    # código. Saber QUE divergiu sem saber EM QUE campo obriga
                    # a repetir a leitura para adjudicar — e a leitura de
                    # amanhã pode já não descrever o instante do despacho.
                    try:
                        await self._registrar_readback(
                            passo.passo_ref,
                            _evidencia_do_readback(
                                operacao.tipo_objeto, dados, conferido=False),
                            codigo=exc.codigo,
                            claim_token=token,
                        )
                    except _EvidenciaNaoGravada:
                        # ⚠️ A DIVERGÊNCIA SOBREVIVE À FALHA DE ANOTÁ-LA. Trocar
                        # o código aqui apagaria o fato mais grave dos dois — o
                        # objeto existe e NÃO é o aprovado. O que muda é a
                        # DURABILIDADE, e a resposta passa a declarar que o
                        # livro não guardou esta divergência.
                        exc.evidencia_duravel = False
                    if not exc.objetos_criados:
                        exc.objetos_criados = tuple(ids)
                    raise
                # O read-back POSITIVO também vira evidência durável, com
                # horário. Antes só o fracasso ficava registrado, e a
                # confirmação existia apenas no corpo da resposta HTTP — quer
                # dizer, apenas no navegador. Mensagem de tela não é recibo.
                try:
                    await self._registrar_readback(
                        passo.passo_ref,
                        _evidencia_do_readback(
                            operacao.tipo_objeto, dados, conferido=True),
                        claim_token=token,
                    )
                except _EvidenciaNaoGravada as falha:
                    # ⚠️ O ID CONTINUA GRAVADO E NADA É REENVIADO. O passo fica
                    # CREATED com o id verdadeiro — é assim que ele permanece
                    # recuperável por leitura. O que falta é a CONFIRMAÇÃO
                    # durável, e sem ela nenhum dependente pode nascer: criar o
                    # próximo seria pendurá-lo numa leitura que só existe nesta
                    # resposta HTTP.
                    #
                    # ⚠️ E isto NÃO é recusa da Meta. `criacao_descartada` fica
                    # falso e `falhar_passo` NÃO é chamado: converter falha
                    # nossa em rejeição provada autorizaria alguém a reenviar
                    # por cima de um objeto que existe.
                    raise ErroRemotoMeta(
                        "META_READBACK_NOT_DURABLE",
                        f"{operacao.chave} nasceu PAUSED e conferiu na leitura, mas a "
                        f"confirmacao nao ficou gravada ({falha.causa}); nada foi "
                        "reenviado e nenhum objeto dependente foi criado",
                        retryable=False,
                        objetos_criados=tuple(ids),
                        criacao_descartada=False,
                        evidencia_duravel=False,
                    ) from falha
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
                # ⚠️ E esta sobrevive pela mesma razão: perdê-la devolveria um
                # 502 afirmando que a evidência ficou gravada quando não ficou.
                evidencia_duravel=exc.evidencia_duravel,
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
                    # ⚠️ `NAO_PEDIDO` e não `None`. Para o criativo o campo saiu
                    # da máscara porque o catálogo oficial v26 não o declara, e
                    # `None` seria lido como "a Meta não devolveu" — quer dizer,
                    # como um fato sobre o objeto. A distinção entre "não
                    # perguntei" e "perguntei e não veio" é a mesma que
                    # `videos_indisponiveis` guarda em `ativos.py`.
                    "effective_status": (
                        dados.get("effective_status")
                        if tipos[chave] in {"campaign", "adset", "ad"}
                        else "NAO_PEDIDO"
                    ),
                    "objective": dados.get("objective"),
                    "optimization_goal": dados.get("optimization_goal"),
                    "advantage_audience_lido": _advantage_audience(dados.get("targeting")),
                    "advantage_state_info": dados.get("advantage_state_info"),
                }
                for chave, dados in read_back.items()
            },
            retry_permitido=False,
        )

    async def _marcar_ambiguo_sem_derrubar(
        self, passo_ref: str, claim_token: str | None,
    ) -> None:
        """Declara a dúvida no livro sem transformar a anotação num segundo erro.

        ⚠️ O `except` largo continua aqui de propósito, e ele não é o defeito de
        R0-A02: quem chamou já está subindo uma exceção que descreve o
        incidente, e falhar ao anotá-lo não pode APAGAR essa exceção. A
        diferença em relação ao read-back é que ali o silêncio produzia um
        SUCESSO certificado; aqui ele nunca produz sucesso nenhum.
        """
        if claim_token is None:
            return
        try:
            await self._registro.marcar_ambiguo(
                passo_ref=passo_ref, claim_token=claim_token)
        except Exception:
            pass

    async def _registrar_despacho_cercado(
        self,
        operacao: OperacaoMeta,
        passo_ref: str,
        claim_token: str,
        id_externo: str,
        *,
        ids: Mapping[str, str],
    ) -> ErroRemotoMeta:
        """Preserva o id visto por um trabalhador que perdeu a autoridade.

        Devolve a exceção que quem chamou deve levantar — nunca um sucesso. O
        passo fica visível para a recuperação por leitura, e o id observado fica
        gravado ao lado da identidade concluída, jamais no lugar dela.
        """
        preservado = False
        registrar = getattr(self._registro, "registrar_despacho_cercado", None)
        if registrar is not None:
            try:
                await registrar(
                    passo_ref=passo_ref, claim_token=claim_token,
                    id_externo=id_externo)
                preservado = True
            except Exception:
                preservado = False
        return ErroRemotoMeta(
            "META_WORKER_FENCED",
            f"a reivindicacao de {operacao.chave} passou a outro processo enquanto o "
            f"pedido estava no ar; o objeto pode existir e "
            + ("o id foi preservado para a leitura"
               if preservado else "o id NAO pode ser preservado no livro")
            + "; nada foi reenviado",
            retryable=False,
            objetos_criados=tuple(ids),
            criacao_descartada=False,
            exige_reconciliacao=True,
            evidencia_duravel=preservado,
        )

    async def _registrar_readback(
        self,
        passo_ref: str,
        evidencia: Mapping[str, Any],
        *,
        codigo: str | None = None,
        claim_token: str | None = None,
    ) -> None:
        """Grava a evidência do read-back. Falhar aqui NÃO é silêncio.

        ⚠️ ERA BEST-EFFORT, e a revisão mediu o preço: com todas as escritas de
        evidência falhando, a saga criava os quatro objetos e devolvia 200
        CREATED_PAUSED com ZERO read-back durável. A confirmação existia só no
        corpo da resposta — quer dizer, só no navegador. `MASTER-SPEC.json` diz
        o contrário em `recovery.durability`: a resposta HTTP da UI não é o
        único recibo.

        Levantar é o que devolve a decisão a QUEM CHAMOU: no caminho positivo a
        saga PARA antes de criar o próximo objeto; no caminho da divergência a
        divergência continua sendo o veredito e só a durabilidade dela cai.
        """
        registrar = getattr(self._registro, "registrar_readback", None)
        if registrar is None:  # pragma: no cover - barrado antes do primeiro POST
            raise _EvidenciaNaoGravada("META_READBACK_LEDGER_UNAVAILABLE")
        try:
            await registrar(
                passo_ref=passo_ref,
                evidencia=dict(evidencia),
                codigo=codigo,
                claim_token=claim_token,
            )
        except Exception as exc:
            # ⚠️ A CAUSA É NORMALIZADA AQUI, e não é zelo estético. O ledger real
            # levanta `ErroDeNascimentoMeta`, que a rota traduz em 409 "nada foi
            # despachado". Deixá-la subir crua depois de quatro POSTs seria
            # trocar um silêncio por uma mentira pior.
            raise _EvidenciaNaoGravada(
                str(getattr(exc, "codigo", None) or type(exc).__name__)[:80]) from exc

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
            codigo = (_codigo_numerico_do_provedor(
                erro.get("code") if isinstance(erro, Mapping) else None)
                or str(resposta.status_code))
            subcodigo = _codigo_numerico_do_provedor(
                erro.get("error_subcode") if isinstance(erro, Mapping) else None)
            explicacoes = []
            anunciante_ausente = codigo == "100" and subcodigo == "3858634"
            if anunciante_ausente:
                explicacoes.append(
                    "A Meta exige um anunciante verificado para as localizações "
                    "deste conjunto. Confira a identidade verificada no "
                    "Gerenciador de Anúncios e vincule o anunciante exigido ao "
                    "conjunto antes de validar novamente. Não alteramos o público "
                    "nem preenchemos uma identidade automaticamente.")
            if isinstance(erro, Mapping):
                for campo in ("error_user_title", "error_user_msg", "message"):
                    valor = _texto_seguro_do_provedor(erro.get(campo))
                    if valor and valor not in explicacoes:
                        explicacoes.append(valor)
            complemento = f": {' — '.join(explicacoes)}" if explicacoes else ""
            raise ErroRemotoMeta(
                ("META_VERIFIED_ADVERTISER_REQUIRED" if anunciante_ausente else
                 "META_REMOTE_VALIDATION_FAILED" if validacao else "META_REMOTE_CREATE_FAILED"),
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
        *, regulatory: bool = False,
    ) -> Mapping[str, Any]:
        campos = CAMPOS_DE_LEITURA
        if nome not in campos:
            raise ErroRemotoMeta("META_READBACK_FAILED", "tipo de objeto Meta desconhecido")
        try:
            resposta = await self._cliente.get(
                f"{self._base}/{self._versao}/{identificador}",
                params={"fields": campos[nome] + (",regional_regulated_categories,regional_regulation_identities" if regulatory and nome == "adset" else "")},
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

        def verba(campo: str) -> None:
            esperado = payload.get(campo)
            lido = dados.get(campo)
            # Graph serializes minor units as digit strings. Absence of a
            # budget at this level is meaningful (CBO); never invent one.
            if esperado is None:
                if lido not in (None, 0, "0"):
                    divergiu(campo)
            elif isinstance(lido, bool) or str(lido) != str(esperado):
                divergiu(campo)

        def projeção_confere(lido: Any, esperado: Any) -> bool:
            # Provider objects may add names beside IDs and reorder lists.
            # Every requested key and list member must still be accounted for.
            if isinstance(esperado, Mapping):
                return isinstance(lido, Mapping) and all(
                    k in lido and projeção_confere(lido[k], v)
                    for k, v in esperado.items())
            if isinstance(esperado, (list, tuple)):
                if not isinstance(lido, (list, tuple)) or len(lido) != len(esperado):
                    return False
                restantes = list(lido)
                for item in esperado:
                    indice = next((i for i, v in enumerate(restantes)
                                   if projeção_confere(v, item)), None)
                    if indice is None:
                        return False
                    restantes.pop(indice)
                return True
            if isinstance(esperado, bool):
                return lido is esperado
            return str(lido) == str(esperado)

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
            # Delivery can be paused by a parent as well as by this object's
            # own configured_status. Meta returns CAMPAIGN_PAUSED for AdSets
            # and CAMPAIGN_PAUSED/ADSET_PAUSED for Ads. These do not contradict
            # the explicit PAUSED check above; rejecting them strands the saga
            # immediately after creating its first AdSet.
            estados_efetivos = {None, "PAUSED", "PENDING_REVIEW", "IN_PROCESS"}
            if nome in {"adset", "ad"}:
                estados_efetivos.add("CAMPAIGN_PAUSED")
            if nome == "ad":
                estados_efetivos.add("ADSET_PAUSED")
            if efetivo not in estados_efetivos:
                divergiu("effective_status")
        if nome == "creative":
            if "url_tags" in payload and sorted(parse_qsl(str(dados.get("url_tags") or ""), keep_blank_values=True)) != sorted(parse_qsl(str(payload["url_tags"]), keep_blank_values=True)):
                divergiu("url_tags")
            # O AdCreative não é um objeto veiculável: ele só entrega através de
            # um Ad, e a Meta o devolve ACTIVE por construção. O que precisa ser
            # recusado é o criativo inutilizável.
            #
            # ⚠️ SÓ `status`. A conferência de `effective_status` saiu junto com
            # o campo na máscara: o catálogo oficial v26 de AdCreative não o
            # declara (ver CAMPOS_DE_LEITURA). Uma comparação sobre um campo que
            # nunca vem seria decorativa — `dados.get(...)` daria `None`, `None`
            # nunca está no conjunto recusado, e a linha passaria a afirmar uma
            # verificação que não acontece.
            if dados.get("status") in {"DELETED", "WITH_ISSUES"}:
                divergiu("status")
        if str(dados.get("name") or "") != str(payload.get("name") or ""):
            divergiu("name")
        if nome == "campaign":
            for campo in ("objective", "buying_type", "bid_strategy"):
                if payload.get(campo) is not None and dados.get(campo) != payload.get(campo):
                    divergiu(campo)
            for campo in ("daily_budget", "lifetime_budget"):
                verba(campo)
            categorias = tuple(dados.get("special_ad_categories") or ())
            if categorias != tuple(payload.get("special_ad_categories") or ()):
                divergiu("special_ad_categories")
            if booleano("is_adset_budget_sharing_enabled") is not bool(
                payload.get("is_adset_budget_sharing_enabled")
            ):
                divergiu("is_adset_budget_sharing_enabled")
        elif nome == "adset":
            if str(dados.get("campaign_id") or "") != str(payload.get("campaign_id") or ids.get("campaign")):
                divergiu("campaign_id")
            for campo in (
                "billing_event", "optimization_goal", "bid_strategy", "destination_type",
            ):
                # Só confere o que foi realmente enviado: destination_type não
                # pertence a esta receita e a Meta pode devolver o dela.
                if campo in payload and dados.get(campo) != payload.get(campo):
                    divergiu(campo)
            for campo in ("daily_budget", "lifetime_budget"):
                verba(campo)
            if not _inicio_confere(dados.get("start_time"), payload.get("start_time"), dados.get("created_time")):
                divergiu("start_time")
            if "end_time" in payload and not _mesmo_instante(dados.get("end_time"), payload["end_time"]):
                divergiu("end_time")
            for campo in ("promoted_object", "attribution_spec", "regional_regulation_identities"):
                if campo in payload and not projeção_confere(dados.get(campo), payload[campo]):
                    divergiu(campo)
            if "regional_regulated_categories" in payload:
                categories = dados.get("regional_regulated_categories")
                expected_categories = payload["regional_regulated_categories"]
                # The live API appends this verification marker to a Brazil
                # beneficiary/payer declaration. Preserve all requested legal
                # categories and identities; only this observed additive
                # marker may differ from the approved request.
                if not isinstance(categories, (list, tuple)) or not all(isinstance(v, str) for v in categories):
                    divergiu("regional_regulated_categories")
                if not set(expected_categories).issubset(categories) or set(categories) - set(expected_categories) - {"VOLUNTARY_VERIFICATION"}:
                    divergiu("regional_regulated_categories")
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
                plataformas = tuple(alvo_lido.get("publisher_platforms") or ())
                if plataformas != tuple(alvo_enviado.get("publisher_platforms") or ()):
                    divergiu("targeting.publisher_platforms")
                for campo in ("geo_locations", "excluded_geo_locations", "locales",
                              "custom_audiences", "excluded_custom_audiences", "flexible_spec"):
                    if campo in alvo_enviado and not projeção_confere(alvo_lido.get(campo), alvo_enviado[campo]):
                        divergiu(f"targeting.{campo}")
                # Advantage+ Audience: confere quando a Meta devolve o campo.
                # A leitura pode omiti-lo, e nesse caso o recibo declara que a
                # escolha não foi confirmada em vez de fingir confirmação.
                esperado = _advantage_audience(alvo_enviado)
                lido = _advantage_audience(alvo_lido)
                if lido is not None and esperado is not None and lido != esperado:
                    divergiu("targeting.targeting_automation.advantage_audience")
        elif nome == "ad":
            expected_groups = payload.get("creative_asset_groups_spec")
            actual_groups = dados.get("creative_asset_groups_spec")
            if expected_groups is not None:
                # Provider-added group_uuid metadata is allowed; missing or
                # additional image/text/CTA groups are not the approved plan.
                if not projeção_confere(actual_groups, expected_groups):
                    divergiu("creative_asset_groups_spec")
                if isinstance(actual_groups, Mapping) and any(
                    isinstance(group, Mapping) and group.get("videos")
                    for group in actual_groups.get("groups", ())
                ):
                    divergiu("creative_asset_groups_spec.videos")
            elif actual_groups:
                divergiu("creative_asset_groups_spec")
            # V2 parents are adset:<key>, not a single global ids['adset'].
            # The payload was resolved against the approved dependency graph.
            if str(dados.get("adset_id") or "") != str(payload.get("adset_id") or ids.get("adset")):
                divergiu("adset_id")
            if "campaign" in ids and str(dados.get("campaign_id") or "") != ids["campaign"]:
                divergiu("campaign_id")
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
            if "object_story_id" in payload:
                if str(dados.get("effective_object_story_id") or dados.get("object_story_id") or "") != str(payload["object_story_id"]):
                    divergiu("object_story_id")
            # Every new own website creative carries the official v26 opt-out.
            # Missing/mutated provider data is not confirmation. Legacy frozen
            # snapshots without this control keep their original read contract.
            if payload.get("destination_spec") == {"destination_type": DESTINATION_TYPE_WEBSITE_OPT_OUT}:
                destino = dados.get("destination_spec")
                if not isinstance(destino, Mapping) or destino.get("destination_type") != DESTINATION_TYPE_WEBSITE_OPT_OUT:
                    divergiu("destination_spec.destination_type")
            # Nunca emitimos asset_feed_spec. Se a Meta devolver um, o objeto
            # criado não é o criativo estático que foi aprovado.
            if "asset_feed_spec" not in payload and dados.get("asset_feed_spec"):
                divergiu("asset_feed_spec")
            # Também rejeita Shop explicitamente retornada em snapshots
            # legados, cujo contrato não exigia destination_spec. Para novos
            # snapshots, a comparação exata acima é obrigatória. O valor de
            # OPT_OUT contém SHOP no nome mas proíbe esse redirecionamento.
            destino_lido = dados.get("destination_spec")
            if isinstance(destino_lido, Mapping):
                tipo_lido = str(destino_lido.get("destination_type") or "").upper()
                if tipo_lido and "SHOP" in tipo_lido and tipo_lido != DESTINATION_TYPE_WEBSITE_OPT_OUT:
                    divergiu("destination_spec.destination_type")
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
