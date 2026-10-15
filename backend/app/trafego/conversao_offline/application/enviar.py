"""Validar no Google (`validateOnly`) e o envio real, que fica travado.

## Dois caminhos, e só um deles é exercitado

`validar_no_google` manda o lote com `validateOnly: true` LITERAL. O Google
confere e descarta; nada é processado. Pela doutrina de `volc_ads/gads/modo.py`
isso não é escrita, e o teste de congelamento confere pela AST que o literal é
`True` (e há uma conferência em tempo de execução logo antes da chamada).

`enviar_de_verdade` existe para que o caminho seja encontrado com as suas
condições, todas obrigatórias e nesta ordem:

  1. a trava de dois fatores do forge (`modo.destravar(motivo)` no código E
     `FORGE_PERMITIR_ESCRITA=1`), conferida ANTES de qualquer chamada;
  2. uma aprovação humana vinculada à impressão EXATA do envelope e que
     declara se o destino é primário (move o lance) ou não;
  3. um `validateOnly` aceito pelo Google para o MESMO envelope, registrado;
  4. o lote real aberto `em_voo` no registro ANTES da chamada; o banco recusa
     um segundo envio vivo do mesmo envelope ou transaction_id, itens
     diferentes dos validados e item sem decisão elegível com o mesmo valor.

## O que nunca acontece

Timeout, erro de rede, 3xx ou 5xx viram `sem_resposta`, nunca "falhou, tente
de novo às cegas". A saída de `sem_resposta` é reenviar o MESMO envelope
(`preparar_lote(retomar_incertos=True)`): no Google, mesmo `transactionId` na
mesma ação é ajuste, e a contagem não muda; o banco só aceita esse reenvio se
o envelope for idêntico. Falha comprovadamente anterior ao envio (credencial)
fecha o lote como `recusado`, porque nada saiu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping

from app.trafego import data_manager as dm

from ..domain.evento import corpo_ingestao
from . import portas
from .preparar import LotePreparado


class LoteComRecusaLocal(dm.FronteiraRecusou):
    """A validação local recusou itens: o lote não vai nem para validateOnly."""


class AprovacaoInvalida(dm.FronteiraRecusou):
    """A aprovação não existe, não é humana ou não é deste envelope."""


class ValidacaoAusente(dm.FronteiraRecusou):
    """Não há validateOnly aceito pelo Google para este envelope."""


class JaEnviado(dm.FronteiraRecusou):
    """O banco já tem um envio real vivo deste envelope ou destes transaction_ids."""


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AprovacaoDeEnvio:
    """A decisão humana de mandar ESTE envelope. Sem ela, nada sai."""

    impressao: str
    aprovado_por: str
    aprovado_em: datetime
    #: Onde a aprovação está escrita (mensagem, recibo). Rastro, não enfeite.
    referencia: str
    #: O aprovador declara se o destino é primário (o envio move o lance).
    destino_primario: bool = False

    def __post_init__(self) -> None:
        if not _HEX64.match(self.impressao or ""):
            raise AprovacaoInvalida("aprovação sem impressão de envelope válida")
        if not str(self.aprovado_por or "").strip() or not str(self.referencia or "").strip():
            raise AprovacaoInvalida("aprovação anônima ou sem referência")
        if self.aprovado_em.tzinfo is None:
            raise AprovacaoInvalida("aprovado_em sem fuso")
        if type(self.destino_primario) is not bool:
            raise AprovacaoInvalida("destino_primario precisa ser declarado (bool)")

    def json(self) -> Dict[str, Any]:
        return {"impressao": self.impressao, "aprovado_por": self.aprovado_por,
                "aprovado_em": self.aprovado_em.isoformat(), "referencia": self.referencia,
                "destino_primario": self.destino_primario}


@dataclass(frozen=True)
class ResultadoDoLote:
    lote_id: int
    impressao: str
    modo: str
    estado: str
    resposta: portas.RespostaDeIngestao

    def json(self) -> Dict[str, Any]:
        return {"lote_id": self.lote_id, "impressao": self.impressao, "modo": self.modo,
                "estado": self.estado, "resposta": self.resposta.json()}


def _estado(resposta: portas.RespostaDeIngestao) -> str:
    if not resposta.respondeu:
        return "sem_resposta"
    return "aceito" if resposta.aceito else "recusado"


def _sem_cliques(obj: Any, cliques: frozenset) -> Any:
    """A resposta do Google pode ecoar o gclid; ela vai para o registro sem ele."""
    if isinstance(obj, str):
        for c in cliques:
            if c and c in obj:
                obj = obj.replace(c, "[clique]")
        return obj
    if isinstance(obj, Mapping):
        return {k: _sem_cliques(v, cliques) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sem_cliques(v, cliques) for v in obj]
    return obj


def _cliques(lote: LotePreparado) -> frozenset:
    return frozenset(e.clique.valor for e in lote.envelope.itens)


def _abrir(registro: portas.RegistroDeConversoes, lote: LotePreparado, modo: str,
           **extra: Any) -> portas.LoteRegistrado:
    env = lote.envelope
    return registro.abrir_lote(
        modo=modo, impressao=env.impressao(), customer_id=env.customer_id,
        login_customer_id=env.login_customer_id,
        operating_account_id=str(env.destino.operating_account_id),
        product_destination_id=str(env.destino.product_destination_id),
        itens=list(lote.itens), **extra)


# ⚠️ A chamada `transporte.ingerir` fica escrita DENTRO de cada função pública,
# não num helper: o teste de congelamento confere pela AST, na própria função,
# o `validateOnly` literal e a trava antes do verbo. Os helpers só fecham.

def _fechar_por_excecao(registro: portas.RegistroDeConversoes, aberto: portas.LoteRegistrado,
                        exc: BaseException) -> None:
    """Exceção nunca deixa `em_voo` órfão. Só `NaoSaiu` prova que nada saiu."""
    if isinstance(exc, portas.NaoSaiu):
        registro.fechar_lote(lote_id=aberto.lote_id, estado="recusado", request_id=None,
                             resposta={"nao_saiu": str(exc)[:500]})
    else:
        registro.fechar_lote(lote_id=aberto.lote_id, estado="sem_resposta", request_id=None,
                             resposta={"excecao": type(exc).__name__})


def _fechar(registro: portas.RegistroDeConversoes, aberto: portas.LoteRegistrado,
            lote: LotePreparado, resposta: portas.RespostaDeIngestao) -> None:
    registro.fechar_lote(lote_id=aberto.lote_id, estado=_estado(resposta),
                         request_id=resposta.request_id,
                         resposta=_sem_cliques(resposta.json(), _cliques(lote)))


def validar_no_google(*, lotes: List[LotePreparado],
                      transporte: portas.TransporteDataManager,
                      registro: portas.RegistroDeConversoes) -> List[ResultadoDoLote]:
    """Cada lote vai com `validateOnly: true`. Nada é processado pelo Google."""
    resultados: List[ResultadoDoLote] = []
    for lote in lotes:
        if lote.recibo_local.recusados:
            raise LoteComRecusaLocal(
                f"o lote {lote.envelope.impressao()[:12]}… tem "
                f"{lote.recibo_local.recusados} item(ns) recusado(s) localmente")
        corpo = corpo_ingestao(lote.envelope, validate_only=True)
        aberto = _abrir(registro, lote, portas.MODO_VALIDATE_ONLY)
        if corpo.get("validateOnly") is not True:  # conferência em tempo de execução
            _fechar_por_excecao(registro, aberto, portas.NaoSaiu("corpo sem validateOnly"))
            raise AssertionError("validar_no_google montou um corpo que não é validateOnly")
        try:
            resposta = transporte.ingerir(corpo)
        except BaseException as exc:
            _fechar_por_excecao(registro, aberto, exc)
            raise
        _fechar(registro, aberto, lote, resposta)
        resultados.append(ResultadoDoLote(aberto.lote_id, aberto.impressao,
                                          portas.MODO_VALIDATE_ONLY, _estado(resposta), resposta))
    return resultados


def enviar_de_verdade(*, lote: LotePreparado,
                      aprovacao: AprovacaoDeEnvio,
                      validacao_lote_id: int,
                      transporte: portas.TransporteDataManager,
                      registro: portas.RegistroDeConversoes) -> ResultadoDoLote:
    """O envio real de UM lote. Travado; nunca chamado por esta entrega."""
    from volc_ads.gads import modo  # noqa: PLC0415 — o engine mora na raiz

    impressao = lote.envelope.impressao()
    modo.exigir_leitura_apenas(
        f"data_manager: ingestão real ({lote.envelope.customer_id}, "
        f"{len(lote.itens)} eventos, {impressao[:12]}…)")

    if aprovacao.impressao != impressao:
        raise AprovacaoInvalida(
            f"a aprovação é do envelope {aprovacao.impressao[:12]}… e o lote é "
            f"{impressao[:12]}…; aprovação não se transfere")
    if aprovacao.destino_primario != lote.destino_primario:
        raise AprovacaoInvalida(
            "a aprovação declara destino "
            f"{'primário' if aprovacao.destino_primario else 'Secondary'} e o lote vai para "
            f"uma ação {'primária' if lote.destino_primario else 'Secondary'}")
    if lote.recibo_local.recusados:
        raise LoteComRecusaLocal("lote com item recusado localmente não é enviado")
    validacao = registro.ler_lote(validacao_lote_id)
    if (validacao is None or validacao.modo != portas.MODO_VALIDATE_ONLY
            or validacao.estado != "aceito" or validacao.impressao != impressao):
        raise ValidacaoAusente(
            "não há validateOnly aceito pelo Google para este mesmo envelope; "
            "valide primeiro e aprove a impressão validada")

    corpo = corpo_ingestao(lote.envelope, validate_only=False)
    aberto = _abrir(registro, lote, portas.MODO_REAL, aprovacao=aprovacao.json(),
                    validacao_lote_id=validacao_lote_id)
    try:
        resposta = transporte.ingerir(corpo)
    except BaseException as exc:
        _fechar_por_excecao(registro, aberto, exc)
        raise
    _fechar(registro, aberto, lote, resposta)
    return ResultadoDoLote(aberto.lote_id, impressao, portas.MODO_REAL, _estado(resposta), resposta)


_DE_STATUS = {"PROCESSING": "processando", "SUCCESS": "sucesso",
              "FAILURE": "falha", "PARTIAL_SUCCESS": "sucesso_parcial"}


def reconciliar(*, lote_id: int,
                transporte: portas.TransporteDataManager,
                registro: portas.RegistroDeConversoes) -> str:
    """Lê `requestStatus:retrieve` do pedido DESTE lote e o fecha. Nunca reenvia.

    O `request_id` vem do próprio registro, não de parâmetro: fechar um lote
    com o pedido de outro liberaria transaction_ids que podem ter entrado.
    A doc manda esperar 30 minutos antes da primeira leitura e repetir com
    backoff até 24 h; quem agenda é o chamador. `sucesso_parcial` mantém todos
    os itens presos: o diagnóstico da Data Manager é por contagem, não por
    evento, e não diz quais falharam.
    """
    lote = registro.ler_lote(lote_id)
    if lote is None or lote.modo != portas.MODO_REAL:
        raise ValueError(f"lote {lote_id} não é um envio real registrado")
    if not str(lote.request_id or "").strip():
        raise ValueError(f"o lote {lote_id} não tem request_id: não há o que reconciliar")
    status = transporte.status(lote.request_id)
    estado = _DE_STATUS.get(status.estado)
    if estado is None:
        raise ValueError(f"estado {status.estado!r} desconhecido da Data Manager")
    registro.fechar_lote(lote_id=lote_id, estado=estado, request_id=lote.request_id,
                         resposta=dict(status.corpo))
    return estado
