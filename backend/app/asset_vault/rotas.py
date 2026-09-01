"""HTTP do Cofre de Ativos. Adaptacao de entrada e saida, e nada mais.

Regra mora em `dominio.py`, orquestracao em `aplicacao.py`, persistencia em
`infraestrutura.py`. Este arquivo converte request em chamada, resultado em
resposta, e e o lugar onde os codigos HTTP sao decididos.

## Os codigos, e por que cada um

`200` leitura ou reenvio reconhecido · `201` operacao nova · `400` pedido
invalido · `403` sem papel administrativo · `404` nao existe · `409` conflito de
estado ou de chave de idempotencia · `503` Cofre indisponivel.

O par 200/201 e o que torna a idempotencia VISIVEL: quem recebe 200 com
`X-Cofre-Idempotente: replay` sabe que nada novo foi produzido. Um retry que
devolve 201 duas vezes e um retry que ninguem consegue auditar.

## Por que TODO corpo de entrada e `extra="forbid"`

Porque a alternativa e silencio. Pydantic ignora campo desconhecido por padrao:
alguem manda `{"resumo": "...", "password": "..."}` e a API responde 201 sem
gravar a senha — mas tambem sem dizer que a recusou. A pessoa acha que guardou.
Com `forbid`, a resposta e 400 dizendo qual campo nao existe. A mesma regra vale
no banco (allowlist da secao 15 da v13_01): duas camadas, porque esta pode ser
contornada por um cliente que fale direto com o PostgREST, e aquela nao.

## ⚠️ Por que o corpo e lido CRU e validado a mao

Medido em 01/09/2026, com um app FastAPI minimo:

    POST /x  {"nome": "a", "password": "SENHA-SECRETA-XYZ"}
    422 {"detail":[{"type":"extra_forbidden","loc":["body","password"],
                    "msg":"Extra inputs are not permitted",
                    "input":"SENHA-SECRETA-XYZ"}]}

O handler padrao de `RequestValidationError` serializa `exc.errors()`, e cada
erro do Pydantic v2 carrega o campo `input` — **o valor rejeitado**. Ou seja, a
recusa automatica devolvia ao navegador exatamente a credencial que ela existia
para recusar. E a mesma classe de defeito do `DETAIL: Failing row contains (…)`
do Postgres, um andar acima e com o browser do outro lado.

Nao da para consertar isso com um handler de router: handlers de excecao no
FastAPI sao de APP. Consertar no app inteiro mudaria o corpo de erro de todos os
outros routers, o que nao e desta missao. Entao o Cofre — o unico modulo onde um
422 pode conter credencial — passou a ler o corpo cru e validar sozinho, e
`_validado` monta a mensagem a partir de `loc` e `msg`, NUNCA de `input`.

O custo e o schema de request sumir do OpenAPI. Ele ja nao e publicado por
padrao (`VOLC_DOCS_ABERTAS`), e o contrato continua legivel nos modelos abaixo.

⚠️ ESTE DEFEITO EXISTE NOS OUTROS ROUTERS DESTE BACKEND. Ele nao foi consertado
aqui porque conserta-lo e mudar o contrato de erro de rotas que nao sao desta
missao — esta registrado no handoff como pendencia nomeada.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.asset_vault import dominio as dom
from app.asset_vault.aplicacao import (
    AtivoNaoEncontrado,
    Autor,
    CasosDeUso,
    CofreIndisponivel,
    OperacaoRecusada,
)
from app.asset_vault.infraestrutura import RepositorioSupabase
from app.config import Settings, get_settings
from app.seguranca.identidade import Identidade, exigir_admin

log = logging.getLogger("volc.cofre.http")

router = APIRouter(prefix="/api/cofre", tags=["cofre-de-ativos"], dependencies=[Depends(exigir_admin)])


def _falha(codigo: str, mensagem: str, status: int) -> HTTPException:
    """Erro com forma estavel. O frontend le `detail.mensagem` e mostra."""
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": mensagem})


async def _corpo_json(request: Request) -> dict[str, Any]:
    """Le o corpo sem deixar o FastAPI montar um 422 com `input` dentro."""
    try:
        bruto = await request.json()
    except Exception:  # noqa: BLE001 — corpo ausente, truncado ou nao-JSON
        raise _falha("corpo_invalido", "O corpo do pedido nao e JSON valido.", 400) from None
    if not isinstance(bruto, dict):
        raise _falha("corpo_invalido", "O corpo do pedido precisa ser um objeto JSON.", 400)
    return bruto


def _validado(modelo: type[BaseModel], corpo: dict[str, Any]):
    """Valida sem NUNCA repetir o valor recusado.

    A mensagem vem de `loc` (qual campo) e `msg` (qual regra). `input` e `ctx`
    sao ignorados de proposito: sao os campos onde o Pydantic guarda o valor.
    """
    try:
        return modelo.model_validate(corpo)
    except ValidationError as exc:
        problemas = []
        for erro in exc.errors()[:8]:
            caminho = ".".join(str(p) for p in erro.get("loc", ()) if p != "body") or "(corpo)"
            problemas.append(f"{caminho}: {erro.get('msg', 'valor invalido')}")
        mensagem = "O Cofre recusou este pedido — " + "; ".join(problemas)
        # Cinto e suspensorio: se um `msg` do Pydantic algum dia passar a citar o
        # valor, esta varredura derruba a frase inteira em vez de publica-la.
        dom.recusar_material_de_credencial(mensagem, "mensagem de validacao")
        raise _falha("payload_invalido", mensagem[:600], 400) from None


def obter_casos(settings: Settings = Depends(get_settings)) -> CasosDeUso:
    """Composicao. Sobrescrita nos testes por `dependency_overrides`."""
    from app.services.supabase_service import SupabaseService  # noqa: PLC0415

    return CasosDeUso(RepositorioSupabase(SupabaseService(settings)))


Casos = Annotated[CasosDeUso, Depends(obter_casos)]
Quem = Annotated[Identidade, Depends(exigir_admin)]


# ─────────────────────────────────────────────────────────────────────────────
# Contrato de entrada
# ─────────────────────────────────────────────────────────────────────────────

Texto = Annotated[str, Field(min_length=1, max_length=800)]


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PerfilDeEngine(_Estrito):
    modalidade: Literal["imagem", "video", "audio", "misto"]
    estado_operacional: Literal[
        "catalogado", "externo_parcial", "integrado", "somente_referencia", "aposentado"]
    versao_contrato: Optional[str] = Field(default=None, max_length=60)
    # ⚠️ `gt=0` e nao `ge=0`: ausencia e NULL, nunca zero. Zero formatos seria
    # uma contagem OBSERVADA, e um manifesto que nao declara formato nao
    # observou zero — nao observou nada. O CHECK do banco diz o mesmo.
    formatos: Optional[int] = Field(default=None, gt=0)
    skins: Optional[int] = Field(default=None, gt=0)
    nichos: Optional[int] = Field(default=None, gt=0)
    vozes: Optional[int] = Field(default=None, gt=0)
    manifesto_fonte: Annotated[str, Field(min_length=3, max_length=400)]
    manifesto_sha256: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    fonte_fingerprint: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    capacidades_observadas: list[str] = Field(default_factory=list, max_length=80)
    limitacoes: list[str] = Field(default_factory=list, max_length=80)
    requisitos: list[str] = Field(default_factory=list, max_length=40)
    destinos_compativeis: list[str] = Field(default_factory=list, max_length=60)
    verificado_em: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class NovoAtivo(_Estrito):
    ativo_id: Annotated[str, Field(min_length=3, max_length=180)]
    kind: str
    cluster: str
    nome: Annotated[str, Field(min_length=2, max_length=160)]
    plataforma: Annotated[str, Field(min_length=1, max_length=240)]
    estado: Literal["declared", "verified", "ready", "active", "restricted", "inactive", "retired"]
    criticidade: Literal["low", "medium", "high", "critical"]
    resumo: Annotated[str, Field(min_length=10, max_length=800)]
    dono_nome: Annotated[str, Field(min_length=1, max_length=240)]
    dono_custodia: Literal["declared", "verified", "unassigned"]
    projeto: Optional[str] = Field(default=None, max_length=240)
    vertical: Optional[str] = Field(default=None, max_length=240)
    display_id: Optional[str] = Field(default=None, max_length=80)
    url_publica: Optional[str] = Field(default=None, max_length=2000)
    localizacao_rotulo: Optional[str] = Field(default=None, max_length=240)
    capacidades: list[str] = Field(min_length=1, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=30)
    proxima_acao: Annotated[str, Field(min_length=10, max_length=800)]
    engine: Optional[PerfilDeEngine] = None


class PedidoDeCadastro(_Estrito):
    chave_idempotencia: str
    motivo: Annotated[str, Field(min_length=5, max_length=800)] = "cadastro pelo Cofre de Ativos"
    ativo: NovoAtivo


class RevisaoDeAtivo(_Estrito):
    """Patch, nao put: campo ausente PRESERVA o valor.

    Um put disfarcado de patch e como uma edicao de nome zera a custodia
    comprovada. A funcao do banco faz o mesmo `coalesce`, e os dois concordam.
    """

    nome: Optional[Annotated[str, Field(min_length=2, max_length=160)]] = None
    plataforma: Optional[Annotated[str, Field(min_length=1, max_length=240)]] = None
    estado: Optional[Literal["declared", "verified", "ready", "active", "restricted", "inactive", "retired"]] = None
    criticidade: Optional[Literal["low", "medium", "high", "critical"]] = None
    resumo: Optional[Annotated[str, Field(min_length=10, max_length=800)]] = None
    dono_nome: Optional[Annotated[str, Field(min_length=1, max_length=240)]] = None
    dono_custodia: Optional[Literal["declared", "verified", "unassigned"]] = None
    projeto: Optional[str] = Field(default=None, max_length=240)
    vertical: Optional[str] = Field(default=None, max_length=240)
    display_id: Optional[str] = Field(default=None, max_length=80)
    url_publica: Optional[str] = Field(default=None, max_length=2000)
    localizacao_rotulo: Optional[str] = Field(default=None, max_length=240)
    capacidades: Optional[list[str]] = Field(default=None, max_length=40)
    tags: Optional[list[str]] = Field(default=None, max_length=30)
    proxima_acao: Optional[Annotated[str, Field(min_length=10, max_length=800)]] = None


class PedidoDeRevisao(_Estrito):
    chave_idempotencia: str
    motivo: Annotated[str, Field(min_length=5, max_length=800)]
    mudancas: RevisaoDeAtivo


class PedidoDeRelacao(_Estrito):
    chave_idempotencia: str
    tipo: Literal["belongs_to", "managed_by", "publishes_to", "authenticates_through",
                  "spends_from", "monetizes", "depends_on", "produces_for"]
    destino_id: Optional[str] = Field(default=None, max_length=180)
    destino_externo: Optional[str] = Field(default=None, max_length=180)
    destino_rotulo: Annotated[str, Field(min_length=1, max_length=240)]
    estado: Literal["declared", "verified"] = "declared"


class PedidoDeMotivo(_Estrito):
    chave_idempotencia: str
    motivo: Annotated[str, Field(min_length=10, max_length=800)]


class PedidoDeReativacao(_Estrito):
    chave_idempotencia: str
    motivo: Annotated[str, Field(min_length=10, max_length=800)]
    estado: Literal["declared", "verified", "ready", "active", "restricted", "inactive"]


class PedidoDeVerificacao(_Estrito):
    chave_idempotencia: str
    alvo: Literal["ativo", "credencial", "relacao", "engine"]
    resultado: Literal["unverified", "partial", "verified", "expired", "failed", "blocked"]
    metodo: Annotated[str, Field(min_length=3, max_length=240)]
    procedencia: Literal["owner_declaration", "live_observation", "repository_inventory", "provider_record"]
    evidencia: Annotated[str, Field(min_length=10, max_length=1000)]
    # Sem default: o instante da OBSERVACAO nao e o instante do registro. Deixar
    # o servidor preencher transformaria "conferi ontem" em "conferi agora".
    observado_em: Annotated[str, Field(min_length=10, max_length=40)]
    proximo_ato: Optional[Annotated[str, Field(min_length=5, max_length=800)]] = None
    revisar_em: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PedidoDeCredencial(_Estrito):
    chave_idempotencia: str
    provider: Literal["1password", "bitwarden", "vaultwarden", "passbolt", "infisical"]
    nome_logico: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
    #: ⚠️ O UNICO campo do sistema inteiro que aceita uma secret reference, e ele
    #: NAO volta em resposta nenhuma. A gramatica de `dominio.exigir_localizador`
    #: recusa qualquer coisa que nao seja endereco — sem repetir o que recebeu.
    localizador: Annotated[str, Field(min_length=8, max_length=300)]
    finalidade: Annotated[str, Field(min_length=5, max_length=500)]
    owner_nome: Annotated[str, Field(min_length=1, max_length=240)]
    estado: Literal["not_required", "not_registered", "referenced", "review_due"] = "referenced"
    valido_ate: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


# ─────────────────────────────────────────────────────────────────────────────
# Tradução de falha
# ─────────────────────────────────────────────────────────────────────────────


def _traduzir(exc: Exception) -> HTTPException:
    # ⚠️ Primeiro ramo, e ele nao e detalhe: `_validado` e `_corpo_json` ja
    # levantam `HTTPException` sanitizada, e o `except Exception` das rotas a
    # capturaria. Sem esta linha, um 400 bem escrito virava 500 generico — e o
    # operador perdia justamente a frase que dizia qual campo estava errado.
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, dom.PayloadRecusado):
        return _falha("payload_invalido", str(exc), 400)
    if isinstance(exc, AtivoNaoEncontrado):
        return _falha("nao_encontrado", "Esse ativo nao existe no Cofre.", 404)
    if isinstance(exc, OperacaoRecusada):
        return _falha(exc.codigo, str(exc), exc.status)
    if isinstance(exc, CofreIndisponivel):
        # 503 e nao 200 com lista vazia. Ver o docstring de `aplicacao`.
        return _falha("cofre_indisponivel", str(exc), 503)
    log.exception("cofre: falha nao prevista")
    return _falha("falha_interna", "O Cofre nao conseguiu concluir esta operacao.", 500)


def _autor(quem: Identidade) -> Autor:
    return Autor(sub=quem.sub, email=quem.email or quem.sub)


def _responder(recibo: dict[str, Any], resposta: Response) -> dict[str, Any]:
    """201 para operacao nova, 200 para replay — e o header que diz qual foi."""
    replay = bool(recibo.get("idempotente"))
    resposta.status_code = 200 if replay else 201
    resposta.headers["X-Cofre-Idempotente"] = "replay" if replay else "novo"
    return recibo


# ─────────────────────────────────────────────────────────────────────────────
# Leitura
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/ativos")
async def listar_ativos(
    casos: Casos,
    cluster: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    busca: Optional[str] = Query(default=None, max_length=120),
    incluir_aposentados: bool = Query(default=False),
) -> dict[str, Any]:
    try:
        return await casos.inventario(
            cluster=cluster, kind=kind, estado=estado,
            busca=busca, incluir_aposentados=incluir_aposentados)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/ativos/{ativo_id}")
async def detalhar_ativo(ativo_id: str, casos: Casos) -> dict[str, Any]:
    try:
        return await casos.detalhe(ativo_id)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/ativos/{ativo_id}/credencial")
async def postura_de_credencial(ativo_id: str, casos: Casos) -> dict[str, Any]:
    """Postura, nunca endereco.

    Compare com `PedidoDeCredencial`: `localizador` entra e nao sai. Nem aqui,
    nem em `/ativos/{id}`, nem no recibo de escrita.
    """
    try:
        return {"credenciais": await casos.postura(ativo_id)}
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/ativos/{ativo_id}/handoff")
async def handoff(ativo_id: str, casos: Casos) -> dict[str, Any]:
    """O que o proximo componente precisa saber — e nada que ele possa usar.

    Responde: quais engines existem e o que produzem, qual ativo recebe a peca,
    qual REFERENCIA de acesso sera resolvida (provider + nome logico, jamais o
    endereco), qual perfil de navegador esta relacionado, e qual componente vem
    depois. Nao dispara job, nao abre navegador, nao publica.

    `pronto_para_handoff` e `bloqueios` existem para o chamador nao ter de
    reimplementar a mesma checagem — e para que "faltou registrar a referencia"
    seja um FATO no corpo, e nao um 200 que parece sucesso.
    """
    try:
        return await casos.handoff(ativo_id)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.get("/engines")
async def listar_engines(casos: Casos) -> dict[str, Any]:
    """A ponte para producao criativa: quem existe, o que produz, para onde.

    Responde capacidade. NAO dispara job — o handoff para P03-T11 e P12-T08/T09
    esta em `docs/architecture/COFRE-HANDOFF-PRODUCAO-E-PUBLICACAO.md`.
    """
    try:
        return {"engines": await casos.engines()}
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Escrita
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/ativos", status_code=201)
async def cadastrar_ativo(request: Request, resposta: Response,
                          casos: Casos, quem: Quem) -> dict[str, Any]:
    try:
        pedido = _validado(PedidoDeCadastro, await _corpo_json(request))
        ativo = pedido.ativo
        dom.exigir_id_de_ativo(ativo.ativo_id)
        dom.exigir_gaveta_coerente(ativo.kind, ativo.cluster)
        dom.exigir_url_publica(ativo.url_publica)
        dom.sanitizar_localizacao(ativo.localizacao_rotulo)
        dom.recusar_material_de_credencial(ativo.resumo, "resumo")
        dom.recusar_material_de_credencial(ativo.proxima_acao, "proxima_acao")
        # `exclude_none` para que campo ausente vire ausencia no banco, e nao um
        # `null` explicito que a funcao trataria como "apagar".
        recibo = await casos.cadastrar(
            ativo.model_dump(exclude_none=True), pedido.chave_idempotencia,
            _autor(quem), pedido.motivo)
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.patch("/ativos/{ativo_id}")
async def revisar_ativo(ativo_id: str, request: Request, resposta: Response,
                        casos: Casos, quem: Quem) -> dict[str, Any]:
    try:
        pedido = _validado(PedidoDeRevisao, await _corpo_json(request))
        mudancas = pedido.mudancas.model_dump(exclude_unset=True)
        if not mudancas:
            raise dom.PayloadRecusado("a revisao nao mudou nada.")
        dom.exigir_url_publica(mudancas.get("url_publica"))
        dom.sanitizar_localizacao(mudancas.get("localizacao_rotulo"))
        for campo in ("resumo", "proxima_acao"):
            dom.recusar_material_de_credencial(mudancas.get(campo), campo)
        recibo = await casos.revisar(ativo_id, mudancas, pedido.chave_idempotencia,
                                     _autor(quem), pedido.motivo)
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/ativos/{ativo_id}/relacoes", status_code=201)
async def relacionar(ativo_id: str, request: Request, resposta: Response,
                     casos: Casos, quem: Quem) -> dict[str, Any]:
    try:
        pedido = _validado(PedidoDeRelacao, await _corpo_json(request))
        dom.exigir_id_de_ativo(ativo_id)
        tem_interno = bool(pedido.destino_id)
        tem_externo = bool(pedido.destino_externo)
        if tem_interno == tem_externo:
            raise dom.PayloadRecusado(
                "informe destino_id (outro ativo) OU destino_externo (projeto, "
                "capacidade, conceito) — exatamente um dos dois.")
        payload = pedido.model_dump(exclude_none=True, exclude={"chave_idempotencia"})
        payload["origem_id"] = ativo_id
        recibo = await casos.relacionar(payload, pedido.chave_idempotencia, _autor(quem))
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.delete("/relacoes/{relacao_id}")
async def desfazer_relacao(relacao_id: int, request: Request, resposta: Response,
                           casos: Casos, quem: Quem) -> dict[str, Any]:
    """DELETE no verbo, `desfeito_em` no banco.

    Nao ha DELETE concedido a ninguem em `cofre_relacao`: desfazer e marcar, e a
    relacao desfeita continua na trilha com o motivo. O verbo HTTP descreve a
    intencao de quem chama, nao a operacao de banco.
    """
    try:
        pedido = _validado(PedidoDeMotivo, await _corpo_json(request))
        recibo = await casos.desfazer_relacao(relacao_id, pedido.motivo,
                                              pedido.chave_idempotencia, _autor(quem))
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/ativos/{ativo_id}/aposentadoria", status_code=201)
async def aposentar(ativo_id: str, request: Request, resposta: Response,
                    casos: Casos, quem: Quem) -> dict[str, Any]:
    try:
        pedido = _validado(PedidoDeMotivo, await _corpo_json(request))
        recibo = await casos.aposentar(ativo_id, pedido.motivo,
                                       pedido.chave_idempotencia, _autor(quem))
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/ativos/{ativo_id}/reativacao", status_code=201)
async def reativar(ativo_id: str, request: Request, resposta: Response,
                   casos: Casos, quem: Quem) -> dict[str, Any]:
    try:
        pedido = _validado(PedidoDeReativacao, await _corpo_json(request))
        recibo = await casos.reativar(ativo_id, pedido.estado, pedido.motivo,
                                      pedido.chave_idempotencia, _autor(quem))
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/ativos/{ativo_id}/verificacoes", status_code=201)
async def registrar_verificacao(ativo_id: str, request: Request, resposta: Response,
                                casos: Casos, quem: Quem) -> dict[str, Any]:
    try:
        pedido = _validado(PedidoDeVerificacao, await _corpo_json(request))
        dom.exigir_id_de_ativo(ativo_id)
        dom.recusar_material_de_credencial(pedido.evidencia, "evidencia")
        payload = pedido.model_dump(exclude_none=True, exclude={"chave_idempotencia"})
        payload["ativo_id"] = ativo_id
        recibo = await casos.registrar_verificacao(payload, pedido.chave_idempotencia, _autor(quem))
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc


@router.post("/ativos/{ativo_id}/credencial", status_code=201)
async def referenciar_credencial(ativo_id: str, request: Request, resposta: Response,
                                 casos: Casos, quem: Quem) -> dict[str, Any]:
    """Registra ONDE a credencial mora. O valor nunca passa por aqui.

    O recibo devolve provider e nome logico — o suficiente para o operador
    conferir que registrou a referencia certa, e insuficiente para alguem usar.
    """
    try:
        pedido = _validado(PedidoDeCredencial, await _corpo_json(request))
        dom.exigir_id_de_ativo(ativo_id)
        dom.recusar_material_de_credencial(pedido.finalidade, "finalidade")
        payload = pedido.model_dump(exclude_none=True, exclude={"chave_idempotencia"})
        payload["ativo_id"] = ativo_id
        recibo = await casos.referenciar_credencial(payload, pedido.chave_idempotencia, _autor(quem))
        return _responder(recibo, resposta)
    except Exception as exc:  # noqa: BLE001
        raise _traduzir(exc) from exc
