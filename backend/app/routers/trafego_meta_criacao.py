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
    SEM_CAMPO_DESCONHECIDO,
    PedidoPlanoMetaPausado,
    _compilar,
    _declaracoes_de_politica,
    _plano,
)
from app.seguranca.identidade import Identidade, exigir_admin
from app.services.supabase_service import SupabaseService
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao import capacidades as capacidades_meta
from app.trafego.meta_execucao.capacidades import (
    autorizacoes_de_processo_ausentes,
    motivos_de_processo_ausentes,
    FLAG_CRIACAO,
    FLAG_LEDGER,
    autorizacoes_ausentes,
    ledger_liberado,
    motivos_ausentes,
    motivos_do_ledger_ausente,
)
from app.trafego.meta_execucao.compilador import (
    VERSAO_DO_COMPILADOR,
    PlanoCompiladoMeta,
    SnapshotMetaInvalido,
    descongelar_plano,
)
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

#: Idade mínima de um passo IN_FLIGHT para a recuperação poder promovê-lo.
#:
#: ⚠️ O limiar é a defesa inteira, porque o schema não tem lease: sem dono e sem
#: expiração de reivindicação, nada consegue afirmar que o processo que
#: reivindicou o passo morreu. A idade é o substituto honesto — e por isso ela
#: precisa ficar CONFORTAVELMENTE acima do timeout HTTP do executor
#: (`TIMEOUT_META`, 20s). Um limiar apertado promoveria um passo que a saga
#: ainda está despachando, e a corrida seguinte gravaria conclusões sobre um
#: passo vivo.
#:
#: Promover NÃO despacha nada: só torna o passo visível para a leitura.
IDADE_MINIMA_DO_ORFAO_S = 300

#: ⚠️ As duas autorizações vivem em `meta_execucao.capacidades`, não aqui. A
#: rota de capacidades RELATA o mesmo conjunto que esta rota EXIGE; se cada uma
#: tivesse a sua lista, o dia de uma terceira flag deixaria a tela dizendo
#: "disponível" sobre uma rota que recusa. `FLAG_CRIACAO` e `FLAG_LEDGER` são
#: reexportados para os testes que ligam e desligam as flags pelo nome.


class PedidoAprovarCriacaoMeta(BaseModel):
    """O que a tela manda para APROVAR. O plano inteiro, mais três decisões."""

    model_config = SEM_CAMPO_DESCONHECIDO

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

    model_config = SEM_CAMPO_DESCONHECIDO

    approval_id: str = Field(min_length=8, max_length=80)
    plano_sha256_esperado: str = Field(min_length=64, max_length=64)


class PedidoReconciliarCriacaoMeta(BaseModel):
    model_config = SEM_CAMPO_DESCONHECIDO

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
    # ⚠️ Só as travas DE PROCESSO aqui. A prova de destino é POR CONTA, e esta
    # porta roda antes de o pedido ser lido — ela não sabe de qual conta se
    # trata. Cobrá-la aqui recusaria toda criação, inclusive a da conta que foi
    # conferida. Quem a cobra é o executor, no único ponto por onde todo
    # despacho passa, com o `account_ref` já resolvido
    # (`META_SHOP_REDIRECT_UNPROVEN`).
    if not autorizacoes_de_processo_ausentes():
        return
    raise HTTPException(status_code=409, detail={
        "codigo": "META_CREATE_PAUSED_BLOCKED",
        "mensagem": "a criação PAUSED permanece fechada neste servidor",
        "autorizacoes_ausentes": motivos_de_processo_ausentes(),
    })


def _exigir_capacidade_do_ledger() -> None:
    """Portão dos atos duráveis/read-only; não autoriza nenhum POST à Meta."""
    if ledger_liberado():
        return
    raise HTTPException(status_code=409, detail={
        "codigo": "META_CREATE_LEDGER_WRITE_BLOCKED",
        "mensagem": "o registro durável Meta permanece fechado neste servidor",
        "autorizacoes_ausentes": motivos_do_ledger_ausente(),
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


def _passo_envelhecido(passo: Mapping[str, Any]) -> bool:
    """Se o passo foi preparado há tempo bastante para não ter dono vivo.

    A comparação é feita aqui só para EVITAR chamadas inúteis ao banco; quem
    decide de verdade é a RPC, que refaz a conta dentro da transação. Um relógio
    de processo não pode ser a autoridade sobre um estado compartilhado.
    """
    bruto = _texto(passo.get("prepared_at"))
    if not bruto:
        return False
    try:
        quando = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
    except ValueError:
        return False
    if quando.tzinfo is None:
        return False
    return (datetime.now(timezone.utc) - quando).total_seconds() >= IDADE_MINIMA_DO_ORFAO_S


def _plano_congelado_da_aprovacao(manifesto: Mapping[str, Any]) -> PlanoCompiladoMeta:
    """O plano despachável que a aprovação congelou — ou uma recusa nomeada.

    ⚠️ AUSÊNCIA DE SNAPSHOT NÃO VIRA RECOMPILAÇÃO SILENCIOSA. Uma aprovação
    anterior a esta versão não tem plano congelado, e reconstruí-la a partir da
    conta de hoje produziria outro plano com cara do mesmo — exatamente o que
    `MASTER-SPEC.json` proíbe em `immutable_dispatch.migration_compatibility`.
    Ela recebe um código próprio, `META_LEGACY_RECOVERY_REQUIRED`, e segue por
    adjudicação manual com os IDs que o recibo já guarda.
    """
    congelado = manifesto.get("compiled_plan")
    if not isinstance(congelado, Mapping) or not congelado:
        raise ErroDeNascimentoMeta(
            "META_LEGACY_RECOVERY_REQUIRED",
            "esta aprovação é anterior ao plano congelado; ela não pode ser "
            "recompilada em silêncio e precisa de adjudicação manual pelos IDs "
            "já registrados no recibo",
        )
    return descongelar_plano(congelado)


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
    _exigir_capacidade_do_ledger()
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
        _declaracoes_de_politica(payload.plano)
        segredo = SegredoEfemero(_credencial_salva(quem).token)
        compilado = await _compilar(payload.plano, pedido, segredo, ator=quem.sub)
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
            # O ledger materializa a prova de supply por peça. O hash do plano
            # já a sela; persistir também os recibos permite auditoria direta,
            # sem exigir que alguém reconstrua o hash para saber o que aprovou.
            recibos_de_supply=[
                manifesto.prova_publica()
                for manifesto in compilado.asset_supply_manifests
            ],
            # ⚠️ O PLANO DESPACHÁVEL CONGELADO. A partir daqui, criar e
            # reconciliar leem ESTE plano — não a conta de agora. É o que tira
            # a recuperação da dependência de reler a biblioteca, rebaixar
            # bytes do CDN e a atestação de direitos ainda estar na validade.
            plano_congelado=compilado.congelar(),
            versao_do_compilador=VERSAO_DO_COMPILADOR,
            snapshot_sha256=compilado.plano_sha256,
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

    Recebe duas referências e nada mais. O plano DESPACHÁVEL é lido do snapshot
    congelado na aprovação, tem a identidade recalculada e é conferido contra o
    hash aprovado antes de o executor existir. Nenhuma recompilação acontece
    aqui: despachar não faz perguntas sobre o presente, exceto a única que
    importa — se a autorização de destino desta conta continua de pé.
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

        # ⚠️ O PLANO VEM DO SNAPSHOT, NÃO DE UMA RECOMPILAÇÃO.
        #
        # Antes esta rota relia a conta inteira para reconstruir o plano e só
        # então comparava hashes. Recompilar é fazer perguntas sobre o PRESENTE
        # para despachar uma decisão do PASSADO: a biblioteca pode ter mudado, a
        # atestação de direitos pode ter vencido, e o plano aprovado deixava de
        # ser despachável sem que nada nele tivesse mudado.
        #
        # O snapshot é o plano que o operador aprovou, e `descongelar_plano`
        # RECALCULA a identidade dele antes de devolver — uma linha adulterada
        # no banco não vira payload.
        compilado = _plano_congelado_da_aprovacao(manifesto)
        _plano_bate_com_a_aprovacao(
            compilado, manifesto, esperado_pela_tela=payload.plano_sha256_esperado)
        if _orcamento_do_plano(compilado) != int(manifesto.get("daily_budget_minor") or -1):
            raise ErroDeNascimentoMeta(
                "META_BUDGET_DIVERGED",
                "o orçamento do conjunto não é o orçamento aprovado")
        # ⚠️ REVOGAÇÃO É CONFERIDA AGORA, e é a única pergunta sobre o presente
        # que o despacho ainda faz. O snapshot carrega a prova de destino que
        # foi aprovada; se um administrador retirou esta conta da lista de
        # conferidas depois disso, a autorização deixou de existir. Antes essa
        # revogação acontecia por ACIDENTE — a recompilação mudava o hash — e
        # acidente não é mecanismo: a mensagem não dizia a causa e a mesma
        # recompilação quebrava a recuperação histórica junto.
        if not capacidades_meta.destino_website_liberado(compilado.account_ref):
            raise ErroDeNascimentoMeta(
                "META_SHOP_REDIRECT_REVOKED",
                "a conferência de destino desta conta foi revogada depois da aprovação; "
                "aprove de novo depois de conferir a conta",
            )

        segredo = SegredoEfemero(_credencial_salva(quem).token)

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

    Percorre o plano aprovado contra a conta real. Só objeto encontrado e
    conferido fecha CRIADO. Ausência, dúvida ou erro de leitura permanecem
    AMBIGUOS: no P0, uma listagem vazia depois do despacho nunca vira licença
    automática para tentar de novo.

    Nenhum `POST` sai desta rota. Reenviar continua sendo uma decisão humana,
    tomada depois de o recibo estar fechado.
    """
    _exigir_host_local(request)
    _exigir_capacidade_do_ledger()
    registro = _registro_saga()
    try:
        manifesto = await registro.manifesto(payload.approval_id)
        if _texto(manifesto.get("actor_id")) != quem.sub:
            raise ErroDeNascimentoMeta(
                "META_APPROVAL_ACTOR_DIVERGED",
                "quem aprovou não é quem está pedindo a reconciliação")
        passos = manifesto.get("steps")
        passos = list(passos) if isinstance(passos, (list, tuple)) else []

        # ⚠️ O PASSO ÓRFÃO ENTRA NA RECUPERAÇÃO, e antes ele não entrava.
        #
        # `F03`: o filtro era `state == "AMBIGUOUS"` e nada mais. Um passo que
        # ficou IN_FLIGHT — porque o processo caiu entre o POST e o registro da
        # conclusão — era INVISÍVEL aqui, e a rota respondia `passos_ambiguos:
        # 0`. Essa resposta é indistinguível de "nada travado", enquanto o
        # objeto pode existir na conta. Pior: o índice de gêmeo entre aprovações
        # trata IN_FLIGHT como reivindicação viva, então o órfão bloqueava
        # PERMANENTEMENTE qualquer aprovação futura de criar aquele objeto.
        #
        # A promoção é por IDADE e acontece no banco. Ela não despacha nada:
        # torna o passo legível para a adjudicação POR LEITURA, que é read-only.
        orfaos = [
            item for item in passos
            if isinstance(item, Mapping)
            and _texto(item.get("state")) == "IN_FLIGHT"
            and _passo_envelhecido(item)
        ]
        promovidos: list[str] = []
        for orfao in orfaos:
            try:
                await registro.reclamar_orfao(
                    passo_ref=_texto(orfao.get("step_ref")),
                    idade_minima_s=IDADE_MINIMA_DO_ORFAO_S,
                )
            except ErroDeNascimentoMeta:
                # Corrida com um trabalhador que voltou à vida, ou passo que
                # mudou de estado entre a leitura e a promoção. Nenhum dos dois
                # é motivo para derrubar a recuperação dos outros passos.
                continue
            promovidos.append(_texto(orfao.get("name")))
        if promovidos:
            manifesto = await registro.manifesto(payload.approval_id)
            passos = manifesto.get("steps")
            passos = list(passos) if isinstance(passos, (list, tuple)) else []

        ambiguos = {
            _texto(item.get("name")): _texto(item.get("step_ref"))
            for item in passos
            if isinstance(item, Mapping) and _texto(item.get("state")) == "AMBIGUOUS"
        }
        # Órfãos jovens demais para serem promovidos existem e precisam APARECER.
        # Silenciá-los devolveria a mesma resposta enganosa por outra porta.
        em_voo_recentes = [
            _texto(item.get("name")) for item in passos
            if isinstance(item, Mapping) and _texto(item.get("state")) == "IN_FLIGHT"
        ]
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
                "passos_em_voo": em_voo_recentes,
                "passos_promovidos": promovidos,
                "conclusoes": [],
                "recibo": dict(await registro.recibo(payload.approval_id)),
            }

        # ⚠️ O SNAPSHOT, NÃO UMA RECOMPILAÇÃO. Esta era a linha que fazia a
        # recuperação depender de reler a biblioteca, rebaixar os bytes do CDN e
        # de a atestação de direitos ainda estar dentro da validade — `F02`. Um
        # despacho de duas horas atrás parava aqui, em
        # META_ASSET_POLICY_RECEIPT_EXPIRED, antes de conseguir LER o que já
        # podia existir na conta.
        #
        # Ler não precisa de nenhuma dessas perguntas. Precisa do plano que foi
        # despachado, e ele está congelado.
        compilado = _plano_congelado_da_aprovacao(manifesto)
        segredo = SegredoEfemero(_credencial_salva(quem).token)

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
            "passos_em_voo": em_voo_recentes,
            "passos_promovidos": promovidos,
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
        return {
            "passo": conclusao.passo,
            "tipo": conclusao.tipo,
            "conclusao": "PERMANECE_AMBIGUO",
            "explicacao": (
                conclusao.motivo
                or "a leitura não encontrou o objeto, mas ausência pós-despacho não prova inexistência"
            ),
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
    _exigir_capacidade_do_ledger()
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
