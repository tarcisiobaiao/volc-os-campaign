"""HTTP `/api/agent/*` da Bia. Adaptação de entrada e saída, e nada mais.

## Ordem dos portões (a mesma em toda rota)

1. flag `BIA_ENABLED=1` — sem ela, 404 antes de tocar no auth ou no Hermes;
2. `exigir_admin` — 401 sem/invalid token, 503 auth fora do ar, 403 sem papel.
   Na V1 a Bia é só ADMIN; o dono é o `sub` do token, nunca o corpo;
3. corpo lido CRU, limitado em bytes e validado com `extra="forbid"`; o 422
   devolve campo e motivo, nunca o valor recusado (mesmo defeito medido no
   Cofre em 01/09/2026: o handler padrão ecoa o `input`).

## Os códigos

`200` leitura ou repetição idempotente · `201` conversa nova · `202` envio
aceito (a execução segue em fundo) · `401`/`403`/`503` portão · `404` não
existe OU não é seu (mesma resposta, de propósito) · `409` conflito de
request_id, execução em andamento ou conversa com execução incerta · `413`
corpo grande · `422` corpo inválido · `429` limite por minuto · `503` ledger
ou Hermes indisponível.

## O que o corpo NÃO aceita

model, provider, profile, instructions/system prompt, session_id do Hermes,
tools, URL, SQL, tabela, tenant, user/dono. Não há campo para nenhum deles:
`extra="forbid"` transforma cada um em 422.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar
from urllib.parse import unquote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agente_bia import configuracao, dominio as dom
from app.agente_bia.aplicacao import (
    CasosDeUso,
    ContextoLido,
    ConversaNaoEncontrada,
    EnvioRecusado,
    FLUXOS,
    prazo_de_expiracao,
)
from app.agente_bia.anexos import dominio as anexos_dm
from app.agente_bia.anexos.armazem import Armazem
from app.agente_bia.cerebro import dominio as cerebro_dom
from app.agente_bia.cerebro.infra_ssh import CerebroIndisponivel, CerebroRecusou, ExecutorCerebroSSH
from app.agente_bia.comandos import catalogo as comandos
from app.agente_bia.gateway import contexto_campanha as ctxc
from app.agente_bia.gateway.catalogo import (
    Catalogo,
    CapacidadeDesconhecida,
    EntradaRecusada,
    PapelInsuficiente,
    erros_sem_valor,
)
from app.agente_bia.infra_hermes import HermesHttp
from app.agente_bia.infra_ledger import LedgerIndisponivel, LedgerSupabase
from app.agente_bia.portas import RESERVA_REPETIDA, Execucao
from app.config import Settings, get_settings
from app.seguranca.identidade import Identidade, exigir_admin

log = logging.getLogger("volc.agente_bia.http")

MAX_CORPO_BYTES = 32 * 1024


# ── portões e fábricas ──────────────────────────────────────────────────────

def configuracao_da_bia(settings: Settings = Depends(get_settings)) -> configuracao.ConfiguracaoDaBia:
    try:
        return configuracao.ler(settings)
    except configuracao.ConfiguracaoInvalida as exc:
        log.error("configuração da Bia inválida: %s", exc)
        raise HTTPException(status_code=503, detail={
            "codigo": "configuracao_invalida", "mensagem": "Bia mal configurada no servidor."})


def exigir_bia_ligada(settings: Settings = Depends(get_settings)) -> None:
    # Lida direto do Settings, ANTES de validar o resto: com a flag desligada a
    # superfície não existe, nem para dizer "mal configurada" (revisão #7).
    if (settings.bia_enabled or "").strip() != "1":
        raise HTTPException(status_code=404, detail="Not Found")


_ARMAZEM: Optional[Armazem] = None


def armazem() -> Armazem:
    """Armazém privado dos anexos (diretório do host do backend; ver anexos/armazem.py)."""
    global _ARMAZEM
    if _ARMAZEM is None:
        _ARMAZEM = Armazem()
    return _ARMAZEM


def executor_cerebro(settings: Settings = Depends(get_settings)) -> ExecutorCerebroSSH:
    return ExecutorCerebroSSH(settings.bia_cerebro_ssh_destino, settings.bia_cerebro_ssh_chave)


def casos_de_uso(cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia),
                 settings: Settings = Depends(get_settings),
                 arm: Armazem = Depends(armazem)) -> CasosDeUso:
    if not (settings.supabase_url and settings.supabase_service_role_key):
        raise HTTPException(status_code=503, detail={
            "codigo": "ledger_indisponivel", "mensagem": "Ledger da Bia sem configuração."})
    motor = (HermesHttp(cfg.hermes_base_url, cfg.hermes_chave, timeout_s=cfg.timeout_s)
             if cfg.motor_configurado else None)
    return CasosDeUso(LedgerSupabase(settings.supabase_url, settings.supabase_service_role_key),
                      motor, limite_por_minuto=cfg.limite_por_minuto,
                      max_caracteres=cfg.max_caracteres, timeout_motor_s=cfg.timeout_s, armazem=arm)


def _fonte_real():
    from app.agente_bia.gateway.infra_contexto import FonteDoContextoSupabase
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        raise LedgerIndisponivel("supabase sem configuração")
    return FonteDoContextoSupabase(s.supabase_url, s.supabase_service_role_key)


_CATALOGO: Optional[Catalogo] = None


def catalogo() -> Catalogo:
    global _CATALOGO
    if _CATALOGO is None:
        c = Catalogo()
        c.registrar(ctxc.capacidade(_fonte_real))
        _CATALOGO = c
    return _CATALOGO


router = APIRouter(
    prefix="/api/agent",
    tags=["agente-bia"],
    # A flag vem ANTES do admin: desligada, a superfície não existe e nada é
    # perguntado ao Supabase.
    dependencies=[Depends(exigir_bia_ligada), Depends(exigir_admin)],
)


# ── contratos de entrada ────────────────────────────────────────────────────

class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpoNovaConversa(_Estrito):
    pass


class ContextoPedido(_Estrito):
    campaign_ref: str = Field(pattern=ctxc.PADRAO_REF)
    janela: Literal["ultimos_7_dias", "ultimos_14_dias", "ultimos_30_dias"] = "ultimos_7_dias"


class CorpoMensagem(_Estrito):
    request_id: uuid.UUID
    texto: str = Field(default="", max_length=dom.MAX_ENTRADA_ABSOLUTO)
    contexto: Optional[ContextoPedido] = None
    anexos: List[uuid.UUID] = Field(default_factory=list, max_length=anexos_dm.MAX_ANEXOS_POR_MENSAGEM)
    #: Intenção tipada (hoje só o rascunho do cérebro). O servidor monta o pedido.
    intencao: Optional[Literal["rascunho_cerebro"]] = None


class CorpoCaptura(_Estrito):
    request_id: uuid.UUID
    destino: Literal["volc", "arbitragem", "pessoal"]
    titulo: str = Field(max_length=cerebro_dom.MAX_TITULO * 2)
    tipo: Literal["decisao", "captura", "pendencia", "referencia", "nota"]
    conteudo: str = Field(max_length=cerebro_dom.MAX_CONTEUDO + 2000)
    tags: List[str] = Field(default_factory=list, max_length=cerebro_dom.MAX_TAGS)
    execucao_id: Optional[uuid.UUID] = None


class CorpoComando(_Estrito):
    conversa_id: Optional[uuid.UUID] = None


#: Texto que começa com comando. A superfície do Hermes não interpreta `/`; ele
#: iria ao modelo como prompt. Comando passa por `POST /comandos/{nome}`.
_COMANDO_NO_TEXTO = re.compile(r"^\s*/[A-Za-z]")
TEXTO_PADRAO_ANEXOS = "Veja os anexos."


M = TypeVar("M", bound=BaseModel)


async def _corpo(request: Request, modelo: Type[M], *, vazio_permitido: bool = False) -> M:
    tamanho = request.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > MAX_CORPO_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "corpo_grande",
                                                     "mensagem": "Corpo acima do limite."})
    bruto = await request.body()
    if len(bruto) > MAX_CORPO_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "corpo_grande",
                                                     "mensagem": "Corpo acima do limite."})
    if not bruto.strip():
        if vazio_permitido:
            return modelo.model_validate({})
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo ausente.", "erros": []})
    try:
        dados = json.loads(bruto)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "JSON inválido.", "erros": []})
    if not isinstance(dados, dict):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo precisa ser objeto.",
                                                     "erros": []})
    try:
        return modelo.model_validate(dados)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo recusado.",
                                                     "erros": erros_sem_valor(exc)})


def _uuid_ou_404(valor: str) -> str:
    try:
        return str(uuid.UUID(valor))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Não encontrado."})


def _indisponivel(exc: Exception) -> HTTPException:
    log.warning("ledger da Bia indisponível: %s", type(exc).__name__)
    return HTTPException(status_code=503, detail={"codigo": "ledger_indisponivel",
                                                  "mensagem": "Histórico da Bia indisponível."})


# ── projeções de saída ──────────────────────────────────────────────────────

def _contexto_publico(contexto: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """`{campanha, anexos}` para a interface; execuções antigas gravaram só a campanha."""
    if not contexto:
        return None
    if any(k in contexto for k in ("campanha", "anexos", "intencao")):
        anexos = [{k: a.get(k) for k in ("id", "nome", "tipo", "familia", "tamanho")}
                  for a in contexto.get("anexos") or [] if isinstance(a, dict)]
        publico = {"campanha": contexto.get("campanha"), "anexos": anexos}
        if contexto.get("intencao") == cerebro_dom.INTENCAO_RASCUNHO:
            publico["intencao"] = cerebro_dom.INTENCAO_RASCUNHO
        return publico
    return {"campanha": contexto, "anexos": []}


def _recibo(e: Execucao) -> Dict[str, Any]:
    return {
        "id": e.id,
        "conversa_id": e.conversa_id,
        "request_id": e.request_id,
        "estado": e.estado,
        "entrada": e.entrada,
        "resposta": e.resposta,
        "erro": ({"codigo": e.erro_codigo, "mensagem": dom.mensagem_de_erro(e.erro_codigo)}
                 if e.erro_codigo else None),
        "contexto": _contexto_publico(e.contexto),
        "criada_em": e.criada_em,
        "terminada_em": e.terminada_em,
    }


def _conversa(c) -> Dict[str, Any]:
    return {"id": c.id, "titulo": c.titulo, "criada_em": c.criada_em,
            "atualizada_em": c.atualizada_em}


# ── rotas ───────────────────────────────────────────────────────────────────

@router.get("/estado")
async def estado(cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia),
                 cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    return {
        "modo": "consulta",
        "aviso": dom.AVISO_MODO_CONSULTA,
        "memoria": {"compartilhada_com": "telegram", "aviso": dom.AVISO_MEMORIA_COMPARTILHADA},
        "motor_configurado": cfg.motor_configurado,
        "limites": {"max_caracteres": cfg.max_caracteres,
                    "envios_por_minuto": cfg.limite_por_minuto,
                    "espera_maxima_s": prazo_de_expiracao(cfg.timeout_s)},
        "capacidades": cat.nomes(),
    }


@router.post("/conversations", status_code=201)
async def nova_conversa(request: Request, identidade: Identidade = Depends(exigir_admin),
                        casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    await _corpo(request, CorpoNovaConversa, vazio_permitido=True)
    try:
        c = await casos.criar_conversa(identidade.sub)
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"conversa": _conversa(c)}


@router.get("/conversations")
async def conversas(identidade: Identidade = Depends(exigir_admin),
                    casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    try:
        lista = await casos.listar_conversas(identidade.sub)
        saida = []
        for c in lista[:20]:
            # Título legível: a 1ª pergunta da conversa. Nunca o id.
            h = await casos.historico(identidade.sub, c.id)
            primeira = h.execucoes[0].entrada if h.execucoes else ""
            item = _conversa(c)
            item["titulo"] = c.titulo or (" ".join(primeira.split())[:72] or None)
            item["mensagens"] = len(h.execucoes)
            saida.append(item)
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Conversa não encontrada."})
    return {"conversas": saida}


@router.get("/conversations/{conversa_id}/messages")
async def historico(conversa_id: str, identidade: Identidade = Depends(exigir_admin),
                    casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    cid = _uuid_ou_404(conversa_id)
    try:
        h = await casos.historico(identidade.sub, cid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Conversa não encontrada."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"conversa": _conversa(h.conversa), "execucoes": [_recibo(e) for e in h.execucoes],
            "aviso": dom.AVISO_MODO_CONSULTA}


_RECUSAS = {
    "conflito": (409, "request_id_conflito", "Este request_id já foi usado com outro conteúdo."),
    "ocupado": (409, "execucao_em_andamento", "Há um envio seu em andamento. Aguarde a resposta."),
    "bloqueada_incerta": (409, "conversa_incerta",
                          "Esta conversa tem um envio de resultado incerto. Reconcilie ou abra "
                          "uma nova conversa; nada é reenviado automaticamente."),
    "limite": (429, "limite_por_minuto", "Limite de envios por minuto atingido."),
    "conversa_inexistente": (404, "nao_encontrado", "Conversa não encontrada."),
}


@router.post("/conversations/{conversa_id}/messages")
async def enviar(conversa_id: str, request: Request, response: Response,
                 tarefas: BackgroundTasks,
                 identidade: Identidade = Depends(exigir_admin),
                 cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia),
                 casos: CasosDeUso = Depends(casos_de_uso),
                 cat: Catalogo = Depends(catalogo),
                 arm: Armazem = Depends(armazem)) -> Dict[str, Any]:
    cid = _uuid_ou_404(conversa_id)
    corpo = await _corpo(request, CorpoMensagem)
    if not cfg.motor_configurado:
        # Antes de reservar: sem motor, nada entra no ledger como se fosse sair.
        raise HTTPException(status_code=503, detail={"codigo": "hermes_indisponivel",
                                                     "mensagem": dom.mensagem_de_erro("hermes_indisponivel")})
    if _COMANDO_NO_TEXTO.match(corpo.texto):
        raise HTTPException(status_code=422, detail={
            "codigo": "comando_no_texto",
            "mensagem": "Comandos com / não são enviados à Bia como texto. Use a lista de comandos."})
    campanha = None
    if corpo.contexto is not None:
        try:
            campanha = cat.validar_entrada(ctxc.NOME, corpo.contexto.model_dump()).model_dump()
        except EntradaRecusada as exc:
            raise HTTPException(status_code=422, detail={"codigo": "contexto_invalido",
                                                         "mensagem": "Contexto recusado.",
                                                         "erros": exc.erros})
    if corpo.intencao and (corpo.anexos or campanha):
        raise HTTPException(status_code=422, detail={
            "codigo": "intencao_invalida",
            "mensagem": "O rascunho do cérebro é sobre a conversa: envie sem anexos nem contexto."})
    refs = _anexos_da_mensagem(identidade.sub, corpo.anexos, arm)
    texto = corpo.texto if corpo.texto.strip() or not refs else TEXTO_PADRAO_ANEXOS
    if corpo.intencao and not texto.strip():
        texto = cerebro_dom.TEXTO_PADRAO_RASCUNHO
    contexto = None
    if campanha or refs or corpo.intencao:
        contexto = {k: v for k, v in (("campanha", campanha), ("anexos", refs),
                                      ("intencao", corpo.intencao)) if v}
    try:
        reserva = await casos.reservar_envio(identidade.sub, cid, str(corpo.request_id),
                                             texto, contexto)
    except dom.EntradaInvalida as exc:
        raise HTTPException(status_code=422, detail={"codigo": "mensagem_invalida",
                                                     "mensagem": str(exc), "erros": []})
    except EnvioRecusado as exc:
        status, codigo, msg = _RECUSAS.get(exc.motivo, (409, exc.motivo, "Envio recusado."))
        raise HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": msg})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)

    assert reserva.execucao is not None
    if reserva.resultado == RESERVA_REPETIDA:
        # Mesmo request_id, mesmo conteúdo: o recibo existente, e NADA novo sai.
        response.status_code = 200
        response.headers["X-Bia-Idempotente"] = "replay"
        return {"execucao": _recibo(reserva.execucao), "aviso": dom.AVISO_MODO_CONSULTA}

    async def ler_contexto(ref: Dict[str, Any]) -> ContextoLido:
        dados = await cat.invocar(identidade, ctxc.NOME, ref)
        return ContextoLido(ferramenta=ctxc.NOME, dados=dados, resumo=ctxc.resumo_para_recibo(dados))

    tarefas.add_task(_executar_em_fundo, casos, identidade.sub, reserva.execucao.id, ler_contexto, cid)
    response.status_code = 202
    return {"execucao": _recibo(reserva.execucao), "aviso": dom.AVISO_MODO_CONSULTA}


def _anexos_da_mensagem(dono: str, ids: List[uuid.UUID], arm: Armazem) -> List[Dict[str, Any]]:
    """Referências dos anexos do PRÓPRIO dono, nos limites por mensagem. Ou 422."""
    if not ids:
        return []
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail={"codigo": "anexo_repetido",
                                                     "mensagem": "O mesmo anexo foi incluído duas vezes."})
    refs, imagens, bytes_imagens = [], 0, 0
    for i in ids:
        a = arm.obter(dono, str(i))
        if a is None:
            raise HTTPException(status_code=422, detail={
                "codigo": "anexo_invalido", "mensagem": "Um anexo não existe, expirou ou não é seu. Anexe de novo."})
        if a.familia == "imagem":
            imagens += 1
            bytes_imagens += a.tamanho
        refs.append(a.referencia())
    if imagens > anexos_dm.MAX_IMAGENS_POR_MENSAGEM or bytes_imagens > anexos_dm.MAX_BYTES_IMAGENS_POR_MENSAGEM:
        raise HTTPException(status_code=422, detail={
            "codigo": "imagens_demais",
            "mensagem": f"Até {anexos_dm.MAX_IMAGENS_POR_MENSAGEM} imagens e "
                        f"{anexos_dm.MAX_BYTES_IMAGENS_POR_MENSAGEM // anexos_dm.MB} MB de imagem por mensagem."})
    return refs


async def _executar_em_fundo(casos: CasosDeUso, dono: str, execucao_id: str, leitor,
                             conversa_id: Optional[str] = None) -> None:
    try:
        await casos.executar(dono, execucao_id, leitor, conversa_id)
    except Exception as exc:  # noqa: BLE001
        # O ledger caiu no meio. A execução fica onde estava (queued/running) e
        # `expirar` a rebaixa depois — para cancelled ou uncertain, nunca replay.
        log.error("execução %s interrompida no backend: %s", execucao_id, type(exc).__name__)


@router.get("/runs/{execucao_id}")
async def uma_execucao(execucao_id: str, identidade: Identidade = Depends(exigir_admin),
                       casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    eid = _uuid_ou_404(execucao_id)
    try:
        e = await casos.execucao(identidade.sub, eid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Execução não encontrada."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"execucao": _recibo(e)}


@router.post("/runs/{execucao_id}/reconcile")
async def reconciliar(execucao_id: str, request: Request,
                      identidade: Identidade = Depends(exigir_admin),
                      casos: CasosDeUso = Depends(casos_de_uso)) -> Dict[str, Any]:
    eid = _uuid_ou_404(execucao_id)
    await _corpo(request, CorpoNovaConversa, vazio_permitido=True)
    try:
        e = await casos.reconciliar(identidade.sub, eid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Execução incerta não encontrada."})
    except EnvioRecusado as exc:
        raise HTTPException(status_code=503, detail={"codigo": exc.motivo,
                                                     "mensagem": dom.mensagem_de_erro(exc.motivo)})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    return {"execucao": _recibo(e)}


@router.get("/tools")
async def ferramentas(cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    return {"capacidades": cat.descrever(), "mutacoes": []}


@router.post("/tools/{nome}")
async def invocar_ferramenta(nome: str, request: Request,
                             identidade: Identidade = Depends(exigir_admin),
                             cat: Catalogo = Depends(catalogo)) -> Dict[str, Any]:
    if nome not in cat.nomes():
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Capacidade desconhecida."})
    bruto = await request.body()
    if len(bruto) > MAX_CORPO_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "corpo_grande",
                                                     "mensagem": "Corpo acima do limite."})
    try:
        args = json.loads(bruto or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "JSON inválido.", "erros": []})
    if not isinstance(args, dict):
        raise HTTPException(status_code=422, detail={"codigo": "corpo_invalido",
                                                     "mensagem": "Corpo precisa ser objeto.",
                                                     "erros": []})
    try:
        return {"resultado": await cat.invocar(identidade, nome, args)}
    except EntradaRecusada as exc:
        raise HTTPException(status_code=422, detail={"codigo": "entrada_invalida",
                                                     "mensagem": "Entrada recusada.",
                                                     "erros": exc.erros})
    except PapelInsuficiente:
        raise HTTPException(status_code=403, detail="Esta operação exige papel administrativo.")
    except (CapacidadeDesconhecida, ctxc.CampanhaNaoEncontrada):
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Não encontrado."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    except Exception as exc:  # noqa: BLE001 — fonte canônica fora do ar não vira 500 com rastro
        log.warning("capacidade %s indisponível: %s", nome, type(exc).__name__)
        raise HTTPException(status_code=503, detail={"codigo": "contexto_indisponivel",
                                                     "mensagem": dom.mensagem_de_erro("contexto_indisponivel")})


# ── anexos ──────────────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES = max(t.max_bytes for t in anexos_dm.TIPOS.values())


@router.post("/anexos", status_code=201)
async def enviar_anexo(request: Request, identidade: Identidade = Depends(exigir_admin),
                       arm: Armazem = Depends(armazem)) -> Dict[str, Any]:
    """Corpo BRUTO (o arquivo), nome em `X-Bia-Nome` (URL-encoded). Nenhum caminho do navegador.

    O limite é aplicado lendo em blocos: um upload grande é cortado no meio, sem
    gravar nada. O tipo é decidido pelos bytes (`anexos/dominio.identificar`).
    """
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"codigo": "arquivo_grande",
                                                     "mensagem": "Arquivo acima do limite de 10 MB."})
    nome = unquote(request.headers.get("x-bia-nome") or "")[:300]
    partes, total = [], 0
    async for bloco in request.stream():
        total += len(bloco)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail={"codigo": "arquivo_grande",
                                                         "mensagem": "Arquivo acima do limite de 10 MB."})
        partes.append(bloco)
    try:
        anexo = await asyncio.to_thread(arm.guardar, identidade.sub, b"".join(partes), nome,
                                        request.headers.get("content-type"))
    except anexos_dm.AnexoRecusado as exc:
        status = 413 if exc.codigo in ("arquivo_grande", "imagem_grande") else \
            429 if exc.codigo == "cota_excedida" else 422
        raise HTTPException(status_code=status, detail={"codigo": exc.codigo, "mensagem": exc.mensagem})
    except OSError as exc:
        log.warning("bia anexo armazenamento_indisponivel erro=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"codigo": "anexo_indisponivel",
                                                     "mensagem": "O armazenamento de anexos está indisponível. Tente de novo."})
    log.info("bia anexo guardado tipo=%s tamanho=%s", anexo.tipo, anexo.tamanho)
    return {"anexo": anexo.publico()}


@router.get("/anexos/{anexo_id}")
async def baixar_anexo(anexo_id: str, identidade: Identidade = Depends(exigir_admin),
                       arm: Armazem = Depends(armazem)) -> Response:
    """Bytes do PRÓPRIO anexo (miniatura ou download), por stream autenticado."""
    aid = _uuid_ou_404(anexo_id)
    a = arm.obter(identidade.sub, aid)
    dados = arm.bytes_de(identidade.sub, aid) if a else None
    if a is None or dados is None:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Anexo não encontrado."})
    disposicao = "inline" if a.familia == "imagem" else "attachment"
    nome_ascii = re.sub(r"[^A-Za-z0-9._-]", "_", a.nome)[:100]
    return Response(content=dados, media_type=a.mime, headers={
        "Content-Disposition": f'{disposicao}; filename="{nome_ascii}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })


@router.post("/anexos/{anexo_id}/remover")
async def remover_anexo(anexo_id: str, identidade: Identidade = Depends(exigir_admin),
                        arm: Armazem = Depends(armazem)) -> Dict[str, Any]:
    aid = _uuid_ou_404(anexo_id)
    if not arm.remover(identidade.sub, aid):
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Anexo não encontrado."})
    return {"removido": True}


# ── progresso de uma execução (SSE) ─────────────────────────────────────────

_TERMINAIS_E_INCERTO = {"succeeded", "failed", "cancelled", "uncertain"}


@router.get("/runs/{execucao_id}/fluxo")
async def fluxo_da_execucao(execucao_id: str, identidade: Identidade = Depends(exigir_admin),
                            casos: CasosDeUso = Depends(casos_de_uso),
                            cfg: configuracao.ConfiguracaoDaBia = Depends(configuracao_da_bia)) -> StreamingResponse:
    """Estado e texto parcial de UMA execução do dono, como `text/event-stream`.

    Eventos: `estado` (recibo do ledger, quando muda) e `parcial` (texto
    acumulado e filtrado, só quando o Hermes mandou deltas — é isso que sustenta
    "digitando"). Termina no estado final ou incerto. Só leitura: assinar,
    cair e assinar de novo nunca reenvia nada.
    """
    eid = _uuid_ou_404(execucao_id)
    try:
        inicial = await casos.execucao(identidade.sub, eid)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Execução não encontrada."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    dono = identidade.sub
    prazo = time.monotonic() + prazo_de_expiracao(cfg.timeout_s) + 30

    async def eventos():
        def sse(nome: str, dados: Dict[str, Any]) -> bytes:
            return f"event: {nome}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n".encode()

        ultimo_estado = inicial.estado
        yield sse("estado", {"execucao": _recibo(inicial)})
        if ultimo_estado in _TERMINAIS_E_INCERTO:
            return
        ultimo_texto, ultima_leitura, ultimo_envio = None, 0.0, time.monotonic()
        while time.monotonic() < prazo:
            parcial = FLUXOS.ler(eid, dono)
            if parcial and parcial["deltas"] and parcial["texto"] != ultimo_texto:
                ultimo_texto = parcial["texto"]
                yield sse("parcial", {"texto": ultimo_texto, "digitando": True})
                ultimo_envio = time.monotonic()
            agora = time.monotonic()
            if agora - ultima_leitura >= (0.6 if (parcial and parcial["fim"]) else 2.0):
                ultima_leitura = agora
                try:
                    e = await casos.execucao(dono, eid)
                except Exception:  # noqa: BLE001 — leitura falhou: o cliente reconsulta
                    yield sse("aviso", {"codigo": "ledger_indisponivel"})
                    return
                if e.estado != ultimo_estado:
                    ultimo_estado = e.estado
                    yield sse("estado", {"execucao": _recibo(e)})
                    ultimo_envio = agora
                    if e.estado in _TERMINAIS_E_INCERTO:
                        return
            if agora - ultimo_envio > 15:
                yield b": keepalive\n\n"
                ultimo_envio = agora
            await asyncio.sleep(0.25)

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ── comandos / ──────────────────────────────────────────────────────────────

@router.get("/comandos")
async def listar_comandos() -> Dict[str, Any]:
    return {"versao_hermes": comandos.VERSAO_HERMES,
            "classes": comandos.classes_contagem(),
            "comandos": [e.publico() for e in comandos.catalogo()]}


@router.post("/comandos/{nome}")
async def executar_comando(nome: str, request: Request, identidade: Identidade = Depends(exigir_admin),
                           casos: CasosDeUso = Depends(casos_de_uso),
                           ex: ExecutorCerebroSSH = Depends(executor_cerebro)) -> Dict[str, Any]:
    """Executa SÓ comando `disponivel` com `execucao == "backend"`. Recibo estruturado."""
    corpo = await _corpo(request, CorpoComando, vazio_permitido=True)
    entrada = comandos.procurar(nome)
    if entrada is None:
        raise HTTPException(status_code=404, detail={"codigo": "comando_desconhecido",
                                                     "mensagem": f"Comando /{nome[:40]} não existe."})
    if not entrada.disponivel:
        raise HTTPException(status_code=403, detail={"codigo": "comando_indisponivel_na_web",
                                                     "mensagem": entrada.motivo, "classe": entrada.classe})
    if entrada.execucao != "backend":
        raise HTTPException(status_code=409, detail={"codigo": "comando_local",
                                                     "mensagem": f"/{entrada.nome} roda na interface."})
    # Despacho EXPLÍCITO por nome: comando de backend novo no catálogo sem ação
    # aqui é recusado, nunca cai em outro.
    async def _cerebro(_dono: str, _conversa: Optional[str]) -> Dict[str, Any]:
        return await status_do_cerebro(identidade, ex)

    acoes = {"status": casos.status, "cerebro": _cerebro}
    if entrada.nome not in acoes:
        raise HTTPException(status_code=501, detail={"codigo": "comando_sem_acao",
                                                     "mensagem": f"/{entrada.nome} ainda não tem ação no servidor."})
    inicio = time.monotonic()
    try:
        resultado = await acoes[entrada.nome](identidade.sub, str(corpo.conversa_id) if corpo.conversa_id else None)
    except ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                     "mensagem": "Conversa não encontrada."})
    except LedgerIndisponivel as exc:
        raise _indisponivel(exc)
    log.info("bia comando=%s duracao_ms=%s", entrada.nome, int((time.monotonic() - inicio) * 1000))
    return {"comando": entrada.nome, "resultado": resultado,
            "recibo": {"executado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "origem": "backend", "somente_leitura": True,
                       "duracao_ms": int((time.monotonic() - inicio) * 1000)}}


# ── cérebro: status só leitura + gravação tipada (ver cerebro/__init__.py) ───

_INDISPONIVEL_CEREBRO = {
    ("cerebro_nao_configurado", "gravar"): "A gravação no cérebro pela web ainda não está ligada neste servidor. "
                                           "Copie a captura e use /salve no Telegram.",
    ("cerebro_nao_configurado", "status"): "O status do cérebro pela web ainda não está ligado neste servidor. "
                                           "Use /cerebro no Telegram.",
    ("cerebro_indisponivel", "gravar"): "O executor do cérebro não respondeu. Nada foi gravado; tente de novo.",
    ("cerebro_indisponivel", "status"): "O executor do cérebro não respondeu. Tente de novo em instantes.",
}


def _cerebro_indisponivel(exc: CerebroIndisponivel, op: str) -> HTTPException:
    mensagem = _INDISPONIVEL_CEREBRO.get((exc.codigo, op)) or _INDISPONIVEL_CEREBRO[("cerebro_indisponivel", op)]
    return HTTPException(status_code=503, detail={"codigo": exc.codigo, "mensagem": mensagem})


@router.get("/cerebro/status")
async def status_do_cerebro(identidade: Identidade = Depends(exigir_admin),
                            ex: ExecutorCerebroSSH = Depends(executor_cerebro)) -> Dict[str, Any]:
    """Estado git dos três cérebros, SÓ leitura (sem fetch, sem pull)."""
    try:
        r = await ex.status()
    except CerebroIndisponivel as exc:
        raise _cerebro_indisponivel(exc, "status")
    except CerebroRecusou as exc:
        raise HTTPException(status_code=502, detail={"codigo": exc.codigo, "mensagem": exc.mensagem})
    campos = ("cerebro", "branch", "commit", "commit_em", "alteracoes", "capturas_web_pendentes",
              "a_frente", "atras", "ultima_busca", "estacao_web", "ok")
    return {"repos": [{k: repo.get(k) for k in campos} for repo in r.get("repos", [])],
            "verificado_em": r.get("verificado_em"), "somente_leitura": True}


@router.post("/cerebro/capturas", status_code=201)
async def gravar_captura(request: Request, response: Response,
                         identidade: Identidade = Depends(exigir_admin),
                         casos: CasosDeUso = Depends(casos_de_uso),
                         ex: ExecutorCerebroSSH = Depends(executor_cerebro)) -> Dict[str, Any]:
    """Grava UMA captura nova na estação `inbox/bia-web/` do cérebro escolhido.

    Só depois do "confirmar" do operador (o front manda; o servidor confere tudo
    de novo). Sem commit/push. Mesmo `request_id` devolve o mesmo arquivo.
    """
    corpo = await _corpo(request, CorpoCaptura)
    try:
        cap = cerebro_dom.validar_captura(corpo.destino, corpo.titulo, corpo.tipo, corpo.conteudo, corpo.tags)
    except cerebro_dom.CapturaRecusada as exc:
        raise HTTPException(status_code=422, detail={"codigo": exc.codigo, "mensagem": exc.mensagem})
    origem: Dict[str, str] = {}
    if corpo.execucao_id is not None:
        try:
            e = await casos.execucao(identidade.sub, str(corpo.execucao_id))
        except ConversaNaoEncontrada:   # rascunho de outro dono ou inexistente: a mesma resposta
            raise HTTPException(status_code=404, detail={"codigo": "nao_encontrado",
                                                         "mensagem": "Rascunho não encontrado."})
        except LedgerIndisponivel as exc:
            raise _indisponivel(exc)
        origem = {"execucao_id": e.id, "conversa_id": e.conversa_id}
    try:
        r = await ex.gravar(destino=cap.destino, titulo=cap.titulo, tipo=cap.tipo, conteudo=cap.conteudo,
                            tags=list(cap.tags), request_id=str(corpo.request_id), origem=origem)
    except CerebroIndisponivel as exc:
        raise _cerebro_indisponivel(exc, "gravar")
    except CerebroRecusou as exc:
        raise HTTPException(status_code=422, detail={"codigo": exc.codigo, "mensagem": exc.mensagem})
    if r.get("ja_existia"):
        response.status_code = 200
    log.info("bia cerebro captura repo=%s caminho=%s sha256=%s bytes=%s replay=%s",
             r.get("repo"), r.get("caminho"), r.get("sha256"), r.get("bytes"), bool(r.get("ja_existia")))
    return {"captura": {"cerebro": cap.destino, "repo": r.get("repo"), "caminho": r.get("caminho"),
                        "sidecar": r.get("sidecar"), "sha256": r.get("sha256"), "bytes": r.get("bytes"),
                        "salvo_no_servidor": True,
                        "sincronizado_github": False,
                        "git": r.get("git"), "ja_existia": bool(r.get("ja_existia"))}}
