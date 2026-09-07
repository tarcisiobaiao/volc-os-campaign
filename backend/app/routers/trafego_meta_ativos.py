"""O ato de REGISTRAR mídia numa conta Meta — uma porta, um efeito.

## Por que este router existe separado

`trafego_meta_validacao` declara, no próprio cabeçalho, que não tem rota de
criação, aprovação ou ativação: ele compila e valida. Registrar mídia é um
EFEITO EXTERNO IRREVERSÍVEL — os bytes passam a existir na biblioteca da conta
do cliente. Pendurá-lo lá tornaria aquela declaração falsa.

E `meta_local` é o plano de leitura: descobrir contas, ler inventário,
preparar sincronização. Um POST que escreve na conta ali dentro faria o mesmo
estrago do outro lado.

Então: um router, um ato, uma autorização.

## O que ele NÃO faz

Não cria Campaign, AdSet, Ad nem Creative. Não existe endpoint genérico de
mutação. Não importa arquivo (isso é `criativos_importacao`). Não valida plano
(isso é `trafego_meta_validacao`). Os quatro atos continuam quatro.

## A confirmação não é um checkbox

O corpo do pedido precisa REPETIR a conta e a lista de peças que o operador
está vendo na tela, e o servidor confere que batem com o que ele resolveu. Uma
confirmação que só diga `true` autorizaria qualquer coisa que o cliente
tivesse mandado junto — inclusive uma lista trocada por uma resposta tardia de
outra conta.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.criativo.armazenamento import armazenamento_padrao
from app.routers.meta_local import _credencial_salva, _exigir_host_local
from app.seguranca.identidade import Identidade, exigir_admin
from app.services.supabase_service import SupabaseService
from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import ErroDeLeituraMeta
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao import capacidades as capacidades_meta
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.registro_de_midia import (
    ErroDeRegistroDeMidia,
    LivroDeRegistroDeMidiaSupabase,
    PecaParaRegistrar,
    RegistradorDeMidiaMeta,
)


router = APIRouter(prefix="/api/trafego/meta/ativos", tags=["meta-asset-registration"])

TIMEOUT_UPLOAD = 60.0

SEM_CAMPO_DESCONHECIDO = ConfigDict(extra="forbid")


class PedidoDeRegistroDeMidia(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

    account_ref: str = Field(min_length=8, max_length=180)
    master_refs: list[str] = Field(min_length=1, max_length=10)
    #: ⚠️ A confirmação carrega a CONTA e a CONTAGEM que o operador viu. O
    #: servidor confere as duas contra o que ele mesmo resolveu; divergência é
    #: recusa, não coerção. É a diferença entre "confirmo o que estou vendo" e
    #: "confirmo o que vier".
    confirmar_registro_na_conta: str = Field(min_length=8, max_length=180)
    confirmar_quantidade: int = Field(ge=1, le=10)


def _erro(exc: Exception) -> HTTPException:
    if isinstance(exc, ErroDeNascimentoMeta):
        return HTTPException(
            status_code=409, detail={"codigo": exc.codigo, "mensagem": str(exc)})
    return HTTPException(status_code=500, detail="Falha interna no registro de mídia Meta.")


def _livro() -> LivroDeRegistroDeMidiaSupabase:
    return LivroDeRegistroDeMidiaSupabase(SupabaseService(get_settings()))


@router.get("/capacidades")
async def capacidades_de_registro(
    request: Request,
    account_ref: str = "",
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """O que este servidor pode fazer com mídia NESTA conta.

    ⚠️ Sem `account_ref` a resposta é FECHADA, e não "aberta por enquanto":
    quem não sabe de qual conta está falando não pode receber a autorização de
    nenhuma. Mesma regra de `destino_website_liberado`.
    """
    _exigir_host_local(request)
    del quem
    liberado = capacidades_meta.upload_de_ativo_liberado(account_ref or None)
    return {
        "ok": True,
        "api_version": "v26.0",
        "registro_de_imagem": "ENABLED" if liberado else "BLOCKED_BY_SERVER_FLAG",
        # ⚠️ Vídeo é uma CAPACIDADE DIFERENTE, não uma variação da imagem. Ele
        # exige upload em fases, espera de processamento e uma miniatura de
        # bytes sob nossa custódia — nada disso está provado aqui, e declarar
        # "disponível" faria a tela oferecer um caminho que não existe.
        "registro_de_video": "BLOCKED_UNTIL_VIDEO_PROCESSING_AND_THUMBNAIL_PROVEN",
        "cria_campanha": "NEVER_IN_THIS_ROUTE",
        "motivo": None if liberado else capacidades_meta.motivo_do_upload_fechado(),
        "formatos_aceitos": ["image/jpeg", "image/png"],
        "limite_por_confirmacao": 10,
    }


@router.post("/registrar")
async def registrar(
    payload: PedidoDeRegistroDeMidia,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """Envia bytes JÁ sob custódia para a biblioteca da conta escolhida."""
    _exigir_host_local(request)

    # ── 1. A confirmação bate com o pedido? ─────────────────────────────────
    if payload.confirmar_registro_na_conta != payload.account_ref:
        raise HTTPException(status_code=409, detail={
            "codigo": "META_ASSET_CONFIRMATION_ACCOUNT_MISMATCH",
            "mensagem": (
                "a conta confirmada não é a conta do pedido; recarregue a tela e "
                "confira antes de registrar"
            ),
        })
    if payload.confirmar_quantidade != len(payload.master_refs):
        raise HTTPException(status_code=409, detail={
            "codigo": "META_ASSET_CONFIRMATION_COUNT_MISMATCH",
            "mensagem": (
                "a quantidade confirmada não é a quantidade de peças do pedido; "
                "recarregue a tela e confira antes de registrar"
            ),
        })

    # ── 2. Esta conta foi liberada para receber patrimônio novo? ────────────
    if not capacidades_meta.upload_de_ativo_liberado(payload.account_ref):
        raise HTTPException(status_code=409, detail={
            "codigo": "META_ASSET_UPLOAD_BLOCKED",
            "mensagem": capacidades_meta.motivo_do_upload_fechado(payload.account_ref),
        })

    try:
        # ── 3. Os bytes vêm da NOSSA custódia, nunca do corpo do pedido ─────
        #
        # ⚠️ Aceitar bytes no JSON transformaria esta rota num proxy de upload
        # para qualquer coisa que o navegador quisesse mandar. O que o cliente
        # manda é uma REFERÊNCIA a algo que já passou pelo intake privado, pelo
        # gate de política e pela inspeção de bytes.
        pecas = await _carregar_pecas(payload.master_refs, ator=quem.sub)

        segredo = SegredoEfemero(_credencial_salva(quem).token)
        conta_externa = await _conta_externa_da(payload.account_ref, segredo)

        async with httpx.AsyncClient(
            timeout=TIMEOUT_UPLOAD, follow_redirects=False,
        ) as cliente:
            resultados = await RegistradorDeMidiaMeta(
                cliente, _livro(),
            ).registrar_imagens(
                conta_externa=conta_externa,
                pecas=pecas,
                segredo=segredo,
                # ⚠️ O ATOR VEM DA SESSÃO, nunca do corpo. Aceitá-lo do
                # navegador deixaria o mesmo interessado assinar o próprio
                # recibo.
                ator=quem.sub,
                account_ref=payload.account_ref,
            )
    except (ErroDeRegistroDeMidia, ErroDeNascimentoMeta) as exc:
        raise _erro(exc) from None
    except dom.ContratoMetaInvalido:
        # ⚠️ IRMÃ de ErroDeNascimentoMeta, não descendente — por isso escapava do
        # except acima e virava 500 sem `codigo`, quebrando o contrato de erro
        # sobre o qual a lane inteira é construída. O caso é banal: um handle de
        # conta desatualizado na tela.
        raise HTTPException(status_code=409, detail={
            "codigo": "META_ASSET_ACCOUNT_UNKNOWN",
            "mensagem": (
                "esta conta não está entre as que a credencial desta sessão alcança; "
                "recarregue a lista de contas"
            ),
        }) from None
    except ErroDeLeituraMeta as exc:
        # ⚠️ RuntimeError, e `@dataclass(frozen=True)`: ao atravessar a fronteira
        # ASGI ela virava FrozenInstanceError e o código original sumia até do
        # log. Traduzida aqui, como todas as outras rotas que falam com o mesmo
        # adaptador já fazem (meta_local.py:109-111).
        raise HTTPException(status_code=502, detail={
            "codigo": getattr(exc, "codigo", "META_READ_FAILED"),
            "mensagem": getattr(exc, "mensagem_segura", "a Meta não respondeu à leitura"),
        }) from None

    return {
        "ok": all(item.utilizavel for item in resultados),
        "efeito_externo": "UPLOAD_DE_MIDIA_NA_CONTA_ESCOLHIDA",
        "objetos_criados": 0,
        "resultados": [
            {
                "master_ref": item.master_ref,
                "estado": item.estado,
                # ⚠️ O `image_hash` NÃO sai daqui. O que o navegador recebe é a
                # referência opaca — a mesma que o inventário produz — para que
                # a peça recém-registrada possa ser selecionada sem que o id do
                # provedor atravesse a fronteira.
                "asset_ref": item.asset_ref,
                "motivo": item.motivo,
                "codigo": item.codigo,
            }
            for item in resultados
        ],
        "ambiguos": [
            item.master_ref for item in resultados
            if item.codigo and "AMBIGUOUS" in str(item.estado)
        ],
    }


async def _carregar_pecas(
    master_refs: list[str], *, ator: str,
) -> list[PecaParaRegistrar]:
    """Lê os bytes sob custódia DO DONO, ou recusa com nome próprio.

    ⚠️ A posse resolve por `master → job → criativo_job.criado_por`, e nunca
    pelo projeto. `buscar_master_do_dono` (persistencia.py:447) exige o dono no
    CONTRATO — não é um filtro que a rota lembra de passar, porque uma porta que
    aceita ser chamada sem dono acaba sendo chamada sem dono.

    ⚠️ E "não existe" e "não é seu" produzem a MESMA recusa. Responder diferente
    confirmaria a existência de um master alheio para quem só tem o id.

    ⚠️ Os bytes vêm do armazenamento, e o `content_hash` gravado é CONFERIDO
    contra eles. Sem essa conferência, uma chave trocada no banco mandaria bytes
    diferentes dos que passaram pelo gate de política — e o recibo descreveria
    uma peça que não foi a enviada.
    """
    # ⚠️ O repositório do Estúdio é construído com base+chave, e NÃO com o
    # SupabaseService — é a mesma forma usada por `criativos.py:110`. Manter
    # duas maneiras de abrir a mesma porta é como uma delas fica para trás.
    from app.criativo.persistencia import Repositorio

    ajustes = get_settings()
    repositorio = Repositorio(
        ajustes.supabase_url, ajustes.supabase_service_role_key)
    if not repositorio.habilitado:
        raise ErroDeRegistroDeMidia(
            "META_ASSET_CUSTODY_UNAVAILABLE",
            "o Supabase operacional não está configurado neste backend",
        )
    loja = armazenamento_padrao()
    pecas: list[PecaParaRegistrar] = []
    for referencia in master_refs:
        try:
            linha = await repositorio.buscar_master_do_dono(referencia, criado_por=ator)
        except Exception:
            # ⚠️ Erro de persistência NÃO pode virar 500 aqui. Uma referência
            # malformada faz o PostgREST devolver 22P02, e um 500 diria ao
            # operador "o servidor quebrou" quando a verdade é "essa peça não é
            # sua ou não existe" — a MESMA resposta dos dois casos, de propósito.
            raise ErroDeRegistroDeMidia(
                "META_ASSET_MASTER_NOT_FOUND",
                "uma das peças selecionadas não existe ou não pertence a você",
            ) from None
        if linha is None:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_MASTER_NOT_FOUND",
                "uma das peças selecionadas não existe ou não pertence a você",
            )
        chave = str(linha.get("storage_chave") or "")
        declarado = str(linha.get("content_hash") or "")
        mime = str(linha.get("mime") or "")
        if not chave or not declarado:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_MASTER_INCOMPLETE",
                "uma das peças não tem bytes sob custódia para registrar",
            )
        try:
            conteudo = loja.ler(chave)
        except Exception:
            raise ErroDeRegistroDeMidia(
                "META_ASSET_CUSTODY_UNAVAILABLE",
                "não foi possível ler os bytes de uma das peças sob custódia",
            ) from None
        # `criativo_master.content_hash` é 'sha256:'+64 hex (v11_01:416-417).
        # O parser é ESTRITO: um valor fora da forma não é normalizado em
        # silêncio, ele recusa.
        import hashlib
        import re

        if not re.fullmatch(r"sha256:[0-9a-f]{64}", declarado):
            raise ErroDeRegistroDeMidia(
                "META_ASSET_MASTER_HASH_MALFORMED",
                "o hash gravado da peça não está na forma canônica",
            )
        medido = hashlib.sha256(conteudo).hexdigest()
        if medido != declarado.removeprefix("sha256:"):
            raise ErroDeRegistroDeMidia(
                "META_ASSET_CUSTODY_HASH_DIVERGED",
                "os bytes sob custódia não conferem com o hash aprovado da peça",
            )
        pecas.append(PecaParaRegistrar(
            master_ref=referencia,
            # ⚠️ Nome OPACO derivado do hash. O nome do arquivo do operador
            # pode conter dado pessoal, caminho interno ou marca de terceiro, e
            # ele viajaria para a biblioteca da conta do cliente.
            nome=f"volc_{medido[:16]}",
            mime_type=mime,
            conteudo=conteudo,
        ))
    return pecas


async def _conta_externa_da(account_ref: str, segredo: SegredoEfemero) -> str:
    """Resolve a conta REAL pela credencial da sessão."""
    from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as cliente:
        adaptador = AdaptadorMetaSomenteLeitura(cliente)
        contas = await adaptador.descobrir_contas(segredo)
        conta = AdaptadorMetaSomenteLeitura.resolver_referencia_opaca(contas, account_ref)
        return str(conta.id_externo)
