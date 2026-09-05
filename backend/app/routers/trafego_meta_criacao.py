"""Caminho governado do primeiro nascimento Meta PAUSED.

## Por que este router é separado de `trafego_meta_validacao`

Aquele é o plano de controle seguro: compila e conversa com a Meta apenas sob
`execution_options=validate_only`, que não cria nada. Este aqui pode criar
objetos numa conta real. Misturar os dois num módulo faria a autoridade de
criação viajar junto de rotas que não deveriam tê-la nunca, e apagaria a linha
que um leitor precisa enxergar em dez segundos.

São três atos, três rotas, e nenhuma delas faz o trabalho da outra:

    POST .../criacao/aprovar          decide. Não cria.
    POST .../criacao/criar-pausada    cria. Não decide.
    POST .../criacao/reconciliar      lê. Não cria e não decide reenviar.

Não existe rota de ativação, e não é um esquecimento: nada aqui pode levar um
objeto a ENABLE. O único estado de nascimento é PAUSED, provado três vezes —
no contrato, no payload compilado e no read-back de cada passo.

## Fechado por padrão

Duas variáveis independentes precisam estar abertas, e nenhuma delas é a da
validação:

    META_CREATE_PAUSED_ENABLED=1        autoriza o ato de criar
    META_CREATE_LEDGER_WRITE_ENABLED=1  autoriza a escrita do recibo durável

⚠️ `META_VALIDATE_ONLY_ENABLED` **não** entra nesta lista e nunca deve entrar.
Ela autoriza uma chamada que não cria nada; reaproveitá-la aqui faria a licença
de olhar virar licença de gastar.

Com qualquer uma fechada, a rota recusa **antes** de tocar o Keychain, o
Supabase ou a rede. O teste que prova isso substitui `_credencial_salva` e
`httpx.AsyncClient` por armadilhas que falham se forem chamadas.

## A ordem dos portões, e por que ela é essa

O segredo é a última coisa a ser lida, não a primeira:

    host local → ADMIN → confirmação humana → flags
      → aprovação durável relida no servidor → manifesto conferido
      → SÓ ENTÃO Keychain → recompilação → hash conferido → execução

Em `criar-pausada` isso é literal: a aprovação é lida do banco antes de existir
qualquer token no processo. Um `approval_id` expirado, de outra pessoa ou de
outro plano nunca chega perto da credencial.

## O que o navegador manda, e o que ele nunca manda

`criar-pausada` recebe **duas** coisas: a referência opaca da aprovação e o
hash do plano que a tela mostrou. Nenhum payload Meta atravessa o navegador —
o servidor relê o pedido do operador gravado na aprovação e recompila. Assim
uma aba antiga não consegue criar um plano diferente do que foi aprovado: o
hash recompilado teria que bater com o hash gravado, e não bate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.routers.meta_local import _credencial_salva, _exigir_host_local
from app.routers.trafego_meta_validacao import (
    PedidoPlanoMetaPausado,
    _compilar,
    _plano,
)
from app.seguranca.identidade import Identidade, exigir_admin
from app.services.supabase_service import SupabaseService
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.capacidades import (
    FLAG_CRIACAO,
    FLAG_LEDGER,
    autorizacoes_ausentes,
    motivos_ausentes,
)
from app.trafego.meta_execucao.compilador import PlanoCompiladoMeta
from app.trafego.meta_execucao.contrato import AutorizacaoMeta, ErroDeNascimentoMeta
from app.trafego.meta_execucao.executor import ErroRemotoMeta, ExecutorMetaPausado
from app.trafego.meta_execucao.reconciliacao import (
    AUSENTE,
    CRIADO,
    ConclusaoDoPasso,
    ReconciliadorMetaSomenteLeitura,
)
from app.trafego.meta_execucao.registro import RegistroSagaMetaSupabase


router = APIRouter(prefix="/api/trafego/meta/local/criacao", tags=["meta-create-paused"])

TIMEOUT_META = 20.0

#: A frase que o operador precisa digitar. Comparada **exatamente**: sem
#: `.lower()`, sem remover acento, sem aceitar sinônimo. Um gesto que exige
#: atenção não pode ser satisfeito por autocompletar.
CONFIRMACAO_LITERAL = "CRIAR PAUSADA"

#: Quanto tempo uma aprovação vive. Curta de propósito: é o bastante para ler o
#: resumo, digitar a confirmação e clicar, e pouco demais para uma autorização
#: de gasto ficar esquecida numa aba aberta. O banco recusa qualquer coisa
#: acima de uma hora (`trafego_meta_create_approval_expiry`), então este valor
#: pode encurtar sem migration, nunca alargar sem ela.
JANELA_DA_APROVACAO = timedelta(minutes=15)

#: Idade máxima do recibo de `validate_only` aceita por uma aprovação. Uma
#: prova de ontem não descreve a conta de hoje — saldo, Página e biblioteca de
#: imagens mudam sem avisar.
JANELA_DA_VALIDACAO_S = 1800

#: ⚠️ As duas autorizações vivem em `meta_execucao.capacidades`, não aqui. A
#: rota de capacidades RELATA o mesmo conjunto que esta rota EXIGE; se cada uma
#: tivesse a sua lista, o dia de uma terceira flag deixaria a tela dizendo
#: "disponível" sobre uma rota que recusa. `FLAG_CRIACAO` e `FLAG_LEDGER` são
#: reexportados para os testes que ligam e desligam as flags pelo nome.


class PedidoAprovarCriacaoMeta(BaseModel):
    """O que a tela manda para APROVAR. O plano inteiro, mais três decisões."""

    plano: PedidoPlanoMetaPausado
    #: O hash que a tela exibiu ao operador. Se a recompilação no servidor der
    #: outro, alguma coisa mudou entre a conferência e o clique — e a aprovação
    #: descreveria um plano que ninguém leu.
    plano_sha256_esperado: str = Field(min_length=64, max_length=64)
    #: O recibo durável devolvido pela validação remota desta mesma versão.
    validation_id: str = Field(min_length=8, max_length=80)
    confirmar_nascimento_pausado: bool
    confirmacao_digitada: str = Field(min_length=1, max_length=64)


class PedidoCriarPausadaMeta(BaseModel):
    """O que a tela manda para CRIAR: duas referências, nenhum payload Meta."""

    approval_id: str = Field(min_length=8, max_length=80)
    plano_sha256_esperado: str = Field(min_length=64, max_length=64)


class PedidoReconciliarCriacaoMeta(BaseModel):
    approval_id: str = Field(min_length=8, max_length=80)


def _registro_saga() -> RegistroSagaMetaSupabase:
    """Seam única do ledger. Substituída nos testes, como o read model."""
    return RegistroSagaMetaSupabase(SupabaseService(get_settings()))


def _exigir_capacidade_de_criacao() -> None:
    """Recusa antes de Keychain, Supabase ou rede.

    ⚠️ A mensagem cita a CAUSA, não a variável. Quem lê a tela precisa saber
    que autorização falta; quem lê o código precisa saber qual chave abre. Os
    dois públicos são atendidos sem que o nome da variável vaze para o browser.
    """
    if not autorizacoes_ausentes():
        return
    raise HTTPException(status_code=409, detail={
        "codigo": "META_CREATE_PAUSED_BLOCKED",
        "mensagem": "a criação PAUSED permanece fechada neste servidor",
        "autorizacoes_ausentes": motivos_ausentes(),
    })


def _erro(exc: Exception) -> HTTPException:
    """Três status, três significados distintos — e a diferença importa.

    409  uma guarda local ou durável recusou; nada foi despachado.
    422  a Meta olhou o pedido e o reprovou; está provado que nada nasceu.
    502  houve despacho e o resultado é DESCONHECIDO. Não é recusa, não é
         timeout retentável: é o estado que exige reconciliação por leitura.

    ⚠️ `objetos_criados` viaja no corpo do 502 e do 422. Sem esse campo o
    operador não descobre que a saga parou com uma campanha já criada, e a
    reação certa — reconciliar em vez de recomeçar — deixa de ser óbvia.
    """
    if isinstance(exc, ErroDeNascimentoMeta):
        return HTTPException(status_code=409, detail={
            "codigo": exc.codigo, "mensagem": str(exc)})
    if isinstance(exc, ErroRemotoMeta):
        # ⚠️ QUEM DECIDE É A SAGA, NÃO ESTA LISTA.
        #
        # A versão anterior classificava por uma lista de códigos aqui, e a
        # lista errava: um 500 da Meta depois do POST levanta
        # `META_REMOTE_CREATE_FAILED` com `criacao_descartada=False`, o
        # executor marca o passo AMBIGUOUS no banco — e a resposta dizia 422
        # com `reconciliacao_necessaria=false`. O ledger e o protocolo
        # contavam histórias diferentes sobre o mesmo despacho.
        #
        # `exige_reconciliacao` é setada no ponto exato em que a saga deixa um
        # passo ambíguo. Um read-back que falha DEPOIS de o recibo fechar não
        # deixa passo ambíguo nenhum — o objeto existe e está registrado — e
        # por isso os códigos de read-back continuam listados: eles são
        # incerteza sobre o ESTADO do objeto, não sobre a existência dele.
        ambiguo = exc.exige_reconciliacao or exc.codigo in {
            "META_READBACK_FAILED",
            "META_READBACK_DIVERGENT",
        }
        return HTTPException(
            status_code=502 if ambiguo else 422,
            detail={
                "codigo": exc.codigo,
                "mensagem": str(exc),
                # Depois de um despacho, retentar duplica. A saga já devolve
                # `retryable=False` nesses casos; aqui a resposta não pode
                # sugerir o contrário nem por omissão.
                "retry_permitido": False if ambiguo else exc.retryable,
                "reconciliacao_necessaria": ambiguo,
                "objetos_criados": list(exc.objetos_criados),
                "provedor": exc.detalhe_provedor,
            },
        )
    return HTTPException(status_code=500, detail="Falha interna no controle Meta.")


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _manifesto_utilizavel(manifesto: Mapping[str, Any], *, ator: str) -> None:
    """As conferências que não dependem do plano recompilado.

    Rodam ANTES do Keychain de propósito: uma aprovação expirada, revogada ou
    de outra pessoa precisa parar sem que o token seja sequer lido.
    """
    estado = _texto(manifesto.get("state"))
    if estado == "EXPIRED":
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_EXPIRED",
            "esta aprovação expirou; aprove de novo antes de criar")
    if estado != "APPROVED":
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_NOT_ACTIVE", "esta aprovação não está ativa")
    if _texto(manifesto.get("actor_id")) != ator:
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_ACTOR_DIVERGED",
            "quem aprovou não é quem está pedindo a criação")
    if manifesto.get("paused_birth_confirmed") is not True:
        raise ErroDeNascimentoMeta(
            "META_PAUSED_BIRTH_NOT_CONFIRMED",
            "esta aprovação não carrega a confirmação de nascimento PAUSED")
    if _texto(manifesto.get("capability")) != "META_CREATE_PAUSED":
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_CAPABILITY_DIVERGED",
            "esta aprovação não autoriza a criação PAUSED")


def _plano_bate_com_a_aprovacao(
    compilado: PlanoCompiladoMeta,
    manifesto: Mapping[str, Any],
    *,
    esperado_pela_tela: str,
) -> None:
    """A recompilação precisa reproduzir EXATAMENTE o plano aprovado.

    Três hashes têm que coincidir: o que a tela mostrou, o que ficou gravado na
    aprovação e o que o servidor acabou de compilar. Qualquer divergência
    significa que a conta, a Página, a imagem ou o texto mudaram desde a
    aprovação — e o que nasceria não é o que o operador autorizou.
    """
    gravado = _texto(manifesto.get("plan_sha256"))
    if compilado.plano_sha256 != gravado:
        raise ErroDeNascimentoMeta(
            "META_APPROVED_PLAN_DIVERGED",
            "o plano recompilado agora difere do plano aprovado")
    if esperado_pela_tela != gravado:
        raise ErroDeNascimentoMeta(
            "META_APPROVED_PLAN_DIVERGED",
            "a tela pediu a criação de uma versão diferente da aprovada")
    manifesto_gravado = [str(passo) for passo in (manifesto.get("steps_expected") or [])]
    if list(compilado.manifesto_de_passos) != manifesto_gravado:
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_MANIFEST_DIVERGED",
            "as operações do plano não são as que foram aprovadas")
    if int(manifesto.get("operations_expected") or 0) != len(manifesto_gravado):
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_MANIFEST_DIVERGED",
            "a contagem de operações aprovadas não confere com o manifesto")
    if _texto(manifesto.get("account_ref")) != compilado.account_ref:
        raise ErroDeNascimentoMeta(
            "META_APPROVAL_ACCOUNT_DIVERGED",
            "a conta do plano não é a conta aprovada")
    if _texto(manifesto.get("currency")) != "BRL":
        raise ErroDeNascimentoMeta(
            "META_CURRENCY_UNSUPPORTED", "a primeira receita está limitada a contas BRL")


def _orcamento_do_plano(compilado: PlanoCompiladoMeta) -> int:
    """O orçamento diário que o AdSet compilado realmente carrega.

    ⚠️ Isto fecha o risco 6 de `REMAINING-RISKS.md`: até aqui a aprovação fixava
    quais passos existem, mas o orçamento aprovado nunca era confrontado com o
    payload do conjunto. Um plano cujo hash bate já garante o payload — este
    laço existe para que a divergência, se houver, apareça com nome próprio em
    vez de virar uma diferença silenciosa de hash.
    """
    for operacao in compilado.operacoes:
        if operacao.tipo_objeto == "adset":
            verba = operacao.payload.get("daily_budget")
            if isinstance(verba, int) and not isinstance(verba, bool):
                return verba
    raise ErroDeNascimentoMeta(
        "META_BUDGET_NOT_IN_PLAN", "o plano compilado não declara orçamento no conjunto")


def _exigir_validacao_utilizavel(
    recibo: Mapping[str, Any], *, ator: str, plano_sha256: str,
) -> None:
    """Recusa um recibo de validação inutilizável — antes de qualquer segredo.

    Cada recusa tem nome próprio porque cada uma significa uma coisa diferente
    para quem está na tela: validou outro plano, validou como outra pessoa,
    validou faz tempo demais, ou já usou este recibo. "Aprovação inválida" não
    diria nenhuma delas.

    ⚠️ Isto NÃO é a autoridade. `trafego_meta_create_approve` refaz todas estas
    verificações dentro da transação, junto das que dependem do plano
    recompilado. Duas checagens do mesmo fato são deliberadas: esta existe pela
    ORDEM (recusar antes do Keychain), aquela existe pela CORREÇÃO.
    """
    if _texto(recibo.get("plan_sha256")) != plano_sha256:
        raise ErroDeNascimentoMeta(
            "META_VALIDATION_PLAN_DIVERGED",
            "este recibo de validação descreve outro plano")
    if _texto(recibo.get("actor_id")) != ator:
        raise ErroDeNascimentoMeta(
            "META_VALIDATION_ACTOR_DIVERGED",
            "este recibo de validação é de outra pessoa")
    if _texto(recibo.get("coverage")) != "INDEPENDENT_ROOTS_ONLY" \
            or recibo.get("accepted") is not True:
        raise ErroDeNascimentoMeta(
            "META_VALIDATION_NOT_ACCEPTED",
            "este recibo não registra uma validação aceita")
    if int(recibo.get("objects_created") or 0) != 0:
        raise ErroDeNascimentoMeta(
            "META_VALIDATION_NOT_CLEAN",
            "este recibo registra objetos criados; não é um recibo de validação")
    if recibo.get("ja_consumido") is True:
        raise ErroDeNascimentoMeta(
            "META_VALIDATION_RECEIPT_ALREADY_USED",
            "este recibo já autorizou uma aprovação; valide de novo")
    if int(recibo.get("idade_s") or 0) > JANELA_DA_VALIDACAO_S:
        raise ErroDeNascimentoMeta(
            "META_VALIDATION_RECEIPT_STALE",
            "esta validação é antiga demais; valide de novo antes de aprovar")


@router.post("/aprovar")
async def aprovar(
    payload: PedidoAprovarCriacaoMeta,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """Cria a aprovação durável que — e só ela — autoriza um nascimento.

    Este ato **não fala com a Meta para criar nada**. Ele lê a conta para
    resolver os ativos, recompila o plano e grava a decisão humana. O efeito
    externo de mutação é nenhum.
    """
    _exigir_host_local(request)
    # A confirmação humana vem antes das flags de propósito: um pedido sem a
    # frase digitada é um erro do cliente, e responder "está fechado" a ele
    # ensinaria a pessoa errada a coisa errada.
    if payload.confirmacao_digitada.strip() != CONFIRMACAO_LITERAL:
        raise HTTPException(status_code=409, detail={
            "codigo": "META_CREATE_CONFIRMATION_MISSING",
            "mensagem": f"digite exatamente {CONFIRMACAO_LITERAL} para aprovar a criação",
        })
    if not payload.confirmar_nascimento_pausado:
        raise HTTPException(status_code=409, detail={
            "codigo": "META_PAUSED_BIRTH_NOT_CONFIRMED",
            "mensagem": "confirme que os objetos nascem em estado PAUSED",
        })
    _exigir_capacidade_de_criacao()
    registro = _registro_saga()
    try:
        # ⚠️ O RECIBO DE VALIDAÇÃO É CONFERIDO ANTES DO KEYCHAIN.
        #
        # A autoridade continua sendo `trafego_meta_create_approve`, que
        # reconfere tudo dentro da transação. Esta leitura existe só para a
        # ORDEM: um `validation_id` inventado, de outra pessoa, já consumido ou
        # velho precisa parar o pedido sem que o token seja lido e sem que a
        # Meta receba uma única requisição de leitura de ativos.
        _exigir_validacao_utilizavel(
            await registro.consultar_validacao(payload.validation_id),
            ator=quem.sub,
            plano_sha256=payload.plano_sha256_esperado,
        )
        # O contrato do plano é puro e julga primeiro: uma receita recusável
        # para aqui sem que o Keychain seja aberto.
        pedido = _plano(payload.plano)
        segredo = SegredoEfemero(_credencial_salva(quem).token)
        compilado = await _compilar(payload.plano, pedido, segredo)
        if compilado.plano_sha256 != payload.plano_sha256_esperado:
            raise ErroDeNascimentoMeta(
                "META_APPROVED_PLAN_DIVERGED",
                "o plano mudou entre a conferência e a aprovação; confira de novo")
        if compilado.estado_ao_nascer != "PAUSED":
            raise ErroDeNascimentoMeta(
                "META_NOT_PAUSED", "este plano não nasce pausado")
        expira_em = datetime.now(timezone.utc) + JANELA_DA_APROVACAO
        aprovacao = await registro.aprovar(
            plano_sha256=compilado.plano_sha256,
            account_ref=compilado.account_ref,
            ator=quem.sub,
            daily_budget_minor=_orcamento_do_plano(compilado),
            moeda="BRL",
            expires_at=expira_em,
            passos_esperados=compilado.manifesto_de_passos,
            validation_id=payload.validation_id,
            janela_da_validacao_s=JANELA_DA_VALIDACAO_S,
            nascimento_pausado_confirmado=True,
            # O pedido do operador — referências opacas e texto dele. É isto que
            # a criação relê para recompilar sem receber payload do navegador.
            pedido_do_operador=payload.plano.model_dump(mode="json"),
        )
        return {
            "ok": True,
            "efeito_externo": "NENHUM",
            "aprovacao": {
                "approval_id": _texto(aprovacao.get("approval_id")),
                "plano_sha256": compilado.plano_sha256,
                "expires_at": aprovacao.get("expires_at"),
                "operacoes": len(compilado.manifesto_de_passos),
                "manifesto": list(compilado.manifesto_de_passos),
                "orcamento_diario_minor": _orcamento_do_plano(compilado),
                "moeda": "BRL",
                "nascimento_pausado_confirmado": True,
            },
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


@router.post("/criar-pausada")
async def criar_pausada(
    payload: PedidoCriarPausadaMeta,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """Executa a saga aprovada: Campaign → AdSet → Creative → Ad, tudo PAUSED.

    Recebe duas referências e nada mais. O plano é relido do banco, recompilado
    aqui dentro e conferido contra o hash aprovado antes de o executor existir.
    """
    _exigir_host_local(request)
    _exigir_capacidade_de_criacao()
    registro = _registro_saga()
    try:
        # ⚠️ A APROVAÇÃO É LIDA ANTES DO KEYCHAIN. Um approval_id expirado, de
        # outra pessoa ou de outro plano nunca chega perto da credencial.
        manifesto = await registro.manifesto(payload.approval_id)
        _manifesto_utilizavel(manifesto, ator=quem.sub)
        if _texto(manifesto.get("plan_sha256")) != payload.plano_sha256_esperado:
            raise ErroDeNascimentoMeta(
                "META_APPROVED_PLAN_DIVERGED",
                "a tela pediu a criação de uma versão diferente da aprovada")

        pedido_gravado = manifesto.get("plan_request")
        if not isinstance(pedido_gravado, Mapping):
            raise ErroDeNascimentoMeta(
                "META_APPROVAL_PLAN_REQUEST_INVALID",
                "a aprovação não guarda o pedido do operador")
        # O pedido gravado volta a passar pelo contrato inteiro. Ele foi
        # validado uma vez na aprovação, e é validado de novo aqui: uma linha
        # adulterada no banco não vira payload.
        modelo = PedidoPlanoMetaPausado.model_validate(dict(pedido_gravado))
        plano_puro = _plano(modelo)

        segredo = SegredoEfemero(_credencial_salva(quem).token)
        compilado = await _compilar(modelo, plano_puro, segredo)
        _plano_bate_com_a_aprovacao(
            compilado, manifesto, esperado_pela_tela=payload.plano_sha256_esperado)
        if _orcamento_do_plano(compilado) != int(manifesto.get("daily_budget_minor") or -1):
            raise ErroDeNascimentoMeta(
                "META_BUDGET_DIVERGED",
                "o orçamento do conjunto não é o orçamento aprovado")

        autorizacao = AutorizacaoMeta(
            plano_sha256=compilado.plano_sha256,
            ator=quem.sub,
            approval_id=_texto(manifesto.get("approval_id")),
            # A saga valida cada degrau resolvido antes de criá-lo. Essa
            # validação interna pertence ao ato de criar e é autorizada por
            # META_CREATE_PAUSED_ENABLED — nunca pela flag do validate_only.
            permitir_validate_only=True,
            permitir_criar_pausada=True,
        )
        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            resultado = await ExecutorMetaPausado(cliente, registro=registro).criar_pausada(
                compilado, segredo, autorizacao)
        recibo = await registro.recibo(autorizacao.approval_id)
        return {
            "ok": True,
            "desfecho": resultado.desfecho,
            "plano_sha256": resultado.plano_sha256,
            "referencias_opacas": dict(resultado.referencias_opacas),
            "read_back": dict(resultado.read_back),
            "recibo": dict(recibo),
            "retry_permitido": resultado.retry_permitido,
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None
    except httpx.TimeoutException as exc:
        # Rede de segurança: a saga já traduz timeout em ambiguidade, mas um
        # silêncio fora dela não pode escapar como 500 nu e virar "tente de novo".
        raise _erro(ErroRemotoMeta(
            "META_REMOTE_RESULT_AMBIGUOUS",
            "a Meta não respondeu; reconcilie por leitura antes de qualquer novo pedido",
            retryable=False,
        )) from exc


@router.post("/reconciliar")
async def reconciliar(
    payload: PedidoReconciliarCriacaoMeta,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """Decide um recibo AMBÍGUO **por leitura**, e nunca por reenvio.

    Percorre o plano aprovado contra a conta real. Só duas conclusões fecham um
    passo: objeto encontrado e conferido (fecha CRIADO) ou ausência provada por
    listagem completa (fecha FALHO). Tudo o mais permanece AMBIGUO — inclusive
    "não consegui ler", que é diferente de "não existe".

    Nenhum `POST` sai desta rota. Reenviar continua sendo uma decisão humana,
    tomada depois de o recibo estar fechado.
    """
    _exigir_host_local(request)
    _exigir_capacidade_de_criacao()
    registro = _registro_saga()
    try:
        manifesto = await registro.manifesto(payload.approval_id)
        if _texto(manifesto.get("actor_id")) != quem.sub:
            raise ErroDeNascimentoMeta(
                "META_APPROVAL_ACTOR_DIVERGED",
                "quem aprovou não é quem está pedindo a reconciliação")
        passos = manifesto.get("steps")
        passos = list(passos) if isinstance(passos, (list, tuple)) else []
        ambiguos = {
            _texto(item.get("name")): _texto(item.get("step_ref"))
            for item in passos
            if isinstance(item, Mapping) and _texto(item.get("state")) == "AMBIGUOUS"
        }
        # O instante em que cada passo foi preparado. É o que separa "este
        # objeto nasceu do nosso despacho" de "a conta já tinha um homônimo".
        preparados = {
            _texto(item.get("name")): _texto(item.get("prepared_at"))
            for item in passos
            if isinstance(item, Mapping)
        }
        if not ambiguos:
            return {
                "ok": True,
                "efeito_externo": "NENHUM",
                "passos_ambiguos": 0,
                "conclusoes": [],
                "recibo": dict(await registro.recibo(payload.approval_id)),
            }

        pedido_gravado = manifesto.get("plan_request")
        if not isinstance(pedido_gravado, Mapping):
            raise ErroDeNascimentoMeta(
                "META_APPROVAL_PLAN_REQUEST_INVALID",
                "a aprovação não guarda o pedido do operador")
        modelo = PedidoPlanoMetaPausado.model_validate(dict(pedido_gravado))
        segredo = SegredoEfemero(_credencial_salva(quem).token)
        compilado = await _compilar(modelo, _plano(modelo), segredo)
        if compilado.plano_sha256 != _texto(manifesto.get("plan_sha256")):
            raise ErroDeNascimentoMeta(
                "META_APPROVED_PLAN_DIVERGED",
                "o plano recompilado difere do aprovado; não é possível reconciliar por nome")

        async with httpx.AsyncClient(timeout=TIMEOUT_META, follow_redirects=False) as cliente:
            conclusoes = await ReconciliadorMetaSomenteLeitura(cliente).conciliar(
                compilado, segredo,
                passos_ambiguos=tuple(ambiguos), preparados_em=preparados)

        publicadas: list[dict[str, Any]] = []
        for conclusao in conclusoes:
            if conclusao.passo not in ambiguos:
                continue
            publicadas.append(await _fechar_conclusao(
                registro, conclusao, passo_ref=ambiguos[conclusao.passo]))
        return {
            "ok": True,
            "efeito_externo": "NENHUM",
            "passos_ambiguos": len(ambiguos),
            "conclusoes": publicadas,
            "recibo": dict(await registro.recibo(payload.approval_id)),
        }
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None


async def _fechar_conclusao(
    registro: RegistroSagaMetaSupabase,
    conclusao: ConclusaoDoPasso,
    *,
    passo_ref: str,
) -> dict[str, Any]:
    """Aplica ao ledger o que a leitura provou — e só o que ela provou."""
    if conclusao.conclusao == CRIADO and conclusao.id_externo:
        await registro.fechar_passo(
            passo_ref=passo_ref, id_externo=conclusao.id_externo)
        return {
            "passo": conclusao.passo,
            "tipo": conclusao.tipo,
            "conclusao": "FECHADO_COMO_CRIADO",
            "explicacao": "o objeto existe na conta e confere com o plano aprovado",
        }
    if conclusao.conclusao == AUSENTE:
        await registro.resolver_ausente(
            passo_ref=passo_ref, codigo="META_RECONCILED_ABSENT")
        return {
            "passo": conclusao.passo,
            "tipo": conclusao.tipo,
            "conclusao": "FECHADO_COMO_NAO_ENCONTRADO",
            "explicacao": conclusao.motivo or "a listagem completa da conta não tem este objeto",
        }
    # ⚠️ Permanece AMBIGUO. Não provar a ausência não é prová-la, e fechar aqui
    # seria autorizar um reenvio sobre um objeto que pode existir.
    return {
        "passo": conclusao.passo,
        "tipo": conclusao.tipo,
        "conclusao": "PERMANECE_AMBIGUO",
        "explicacao": conclusao.motivo or "a leitura não foi conclusiva",
    }


@router.post("/recibo")
async def recibo(
    payload: PedidoReconciliarCriacaoMeta,
    request: Request,
    quem: Identidade = Depends(exigir_admin),
) -> dict[str, Any]:
    """O recibo sanitizado de uma aprovação. Nunca devolve id externo."""
    _exigir_host_local(request)
    _exigir_capacidade_de_criacao()
    registro = _registro_saga()
    try:
        manifesto = await registro.manifesto(payload.approval_id)
        if _texto(manifesto.get("actor_id")) != quem.sub:
            raise ErroDeNascimentoMeta(
                "META_APPROVAL_ACTOR_DIVERGED",
                "este recibo pertence a outra pessoa")
        return {"ok": True, "recibo": dict(await registro.recibo(payload.approval_id))}
    except (ErroDeNascimentoMeta, ErroRemotoMeta) as exc:
        raise _erro(exc) from None
