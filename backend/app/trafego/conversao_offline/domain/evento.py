"""O clique observado, a identidade do evento e o corpo que a Data Manager lê.

## Identidade: um clique, uma conversão, uma chave

`transactionId` é derivado de (conta dona, ação, tipo e valor do clique). Ele
NÃO depende do valor: reexecutar a preparação com a mesma receita gera a mesma
chave e o mesmo valor (no-op); com receita revista gera a mesma chave e valor
diferente, que no Google vira AJUSTE (o valor substitui, a contagem não muda).
Ajuste não é aberto por esta entrega: o caso de uso o recusa nomeadamente.

A chave é um hash e não o gclid cru: `transactionId` aparece em relatório e
diagnóstico, e o gclid é dado de usuário.

## O corpo

Campos conferidos em 15/10/2026 contra
https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/send-events
e a referência de `events:ingest`: `destinations[].operatingAccount`,
`loginAccount` (`accountType: GOOGLE_ADS`, `accountId` com 10 dígitos),
`productDestinationId` (id da ConversionAction), `events[].adIdentifiers`,
`conversionValue`, `currency`, `eventTimestamp`, `transactionId`,
`eventSource`, `consent.adUserData`, e `validateOnly` no corpo. `encoding` só é
exigido com `userData`, que este caminho não manda.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.trafego import data_manager as dm

from .valor import Coorte, Pulo, ValorMedido

VERSAO_DA_IDENTIDADE = 1
#: Limite oficial de `events:ingest`.
MAX_EVENTOS_POR_REQUEST = 2000

PULO_SEM_CONSENTIMENTO = "sem_consentimento_do_usuario"
PULO_JANELA_NAO_DECLARADA = "janela_de_clique_nao_declarada"
PULO_CLIQUE_EXPIRADO = "clique_fora_da_janela"
PULO_HORA_SEM_FUSO = "hora_do_clique_sem_fuso"
PULO_JA_ENVIADO = "ja_enviado"
PULO_AJUSTE_NAO_AUTORIZADO = "ajuste_de_valor_nao_autorizado"
PULO_ACAO_SEM_DESTINO = "acao_sem_destino"


@dataclass(frozen=True)
class CliqueObservado:
    """Uma visita paga com identificador de clique, como a porta a lê.

    `consentimento` usa o vocabulário de `data_manager`. `site_visits` hoje
    NÃO tem coluna de consentimento: quando o adaptador de cliques existir
    (ainda não existe; esta entrega só define a porta), ele tem de devolver
    `nao_declarado` e o evento é pulado. É lacuna de coleta, não deste módulo.
    """

    visita_ref: str
    clique: dm.IdentificadorDeClique
    #: A hora da visita (aterrissagem), sempre depois do clique. Com fuso.
    visitado_em: datetime
    coorte: Coorte
    consentimento: str = dm.CONSENTIMENTO_NAO_DECLARADO


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def transaction_id(*, operating_account_id: str, product_destination_id: str,
                   clique: dm.IdentificadorDeClique) -> str:
    base = "|".join(("w14", str(VERSAO_DA_IDENTIDADE), operating_account_id,
                     product_destination_id, clique.tipo, clique.valor))
    return f"volc-w14-{sha256(base)[:40]}"


ELEGIVEL = "elegivel"
PULADO = "pulado"


@dataclass(frozen=True)
class Decisao:
    """O que se decidiu sobre UM clique. Vai inteira para o registro."""

    transaction_id: str
    visita_ref: str
    clique_tipo: str
    clique_sha256: str
    ocorrido_em: Optional[str]
    estado: str
    motivo: Optional[str] = None
    detalhe: Optional[str] = None
    valor: Optional[ValorMedido] = None

    def __post_init__(self) -> None:
        if self.estado == ELEGIVEL and (self.valor is None or self.motivo):
            raise ValueError("decisão elegível exige valor e não tem motivo")
        if self.estado == PULADO and (not self.motivo or self.valor is not None):
            raise ValueError("decisão pulada exige motivo e não carrega valor")
        if self.estado not in (ELEGIVEL, PULADO):
            raise ValueError(f"estado {self.estado!r} desconhecido")

    @classmethod
    def pulada(cls, *, tid: str, clique: CliqueObservado, pulo: Pulo) -> "Decisao":
        return cls(transaction_id=tid, visita_ref=clique.visita_ref,
                   clique_tipo=clique.clique.tipo,
                   clique_sha256=sha256(clique.clique.valor),
                   ocorrido_em=None, estado=PULADO,
                   motivo=pulo.motivo, detalhe=pulo.detalhe)

    def json(self) -> Dict[str, Any]:
        """Para registro e tela. ⚠️ Sem o valor do clique, só o hash."""
        return {
            "transaction_id": self.transaction_id,
            "visita_ref": self.visita_ref,
            "clique_tipo": self.clique_tipo,
            "clique_sha256": self.clique_sha256,
            "ocorrido_em": self.ocorrido_em,
            "estado": self.estado,
            "motivo": self.motivo,
            "detalhe": self.detalhe,
            "valor": None if self.valor is None else str(self.valor.valor),
            "moeda": None if self.valor is None else self.valor.moeda,
            "estimado": None if self.valor is None else self.valor.estimado,
            "valor_impressao": None if self.valor is None else self.valor.impressao(),
            "proveniencia": {} if self.valor is None else dict(self.valor.proveniencia),
        }


# ═══════════════════════════════════════════════════════════════════════════
# O CORPO DE `events:ingest`
# ═══════════════════════════════════════════════════════════════════════════

_CONSENTIMENTO_WIRE = {dm.CONSENTIMENTO_CONCEDIDO: "CONSENT_GRANTED",
                       dm.CONSENTIMENTO_NEGADO: "CONSENT_DENIED"}


def _conta(account_id: str) -> Dict[str, str]:
    digitos = str(account_id or "").replace("-", "")
    if len(digitos) != 10 or not digitos.isdigit():
        raise ValueError(f"conta {account_id!r} não é um customer id de 10 dígitos")
    return {"accountType": "GOOGLE_ADS", "accountId": digitos}


def corpo_ingestao(envelope: dm.Envelope, *, validate_only: bool) -> Dict[str, Any]:
    """O JSON de `POST /v1/events:ingest` para este envelope.

    ⚠️ `validate_only` é obrigatório e sem default: quem chama tem de escrever
    o valor, e o teste de congelamento confere pela AST que o caminho de
    validação o escreve como `True` literal.
    """
    if type(validate_only) is not bool:
        raise TypeError("validate_only precisa ser bool explícito")
    if len(envelope.itens) > MAX_EVENTOS_POR_REQUEST:
        raise ValueError(f"{len(envelope.itens)} eventos; o limite é {MAX_EVENTOS_POR_REQUEST}")
    destino: Dict[str, Any] = {
        "operatingAccount": _conta(envelope.destino.operating_account_id or ""),
        "productDestinationId": str(envelope.destino.product_destination_id),
    }
    if envelope.login_customer_id and envelope.login_customer_id != envelope.destino.operating_account_id:
        destino["loginAccount"] = _conta(envelope.login_customer_id)
    eventos: List[Dict[str, Any]] = []
    for e in envelope.itens:
        if e.valor is None or e.moeda is None:
            raise ValueError("evento sem valor não entra no corpo: este caminho só manda valor medido")
        evento: Dict[str, Any] = {
            "adIdentifiers": {e.clique.tipo: e.clique.valor},
            "conversionValue": _numero_json(e.valor),
            "currency": str(e.moeda).upper(),
            "eventTimestamp": e.ocorrido_em,
            "transactionId": e.chave_de_deduplicacao,
            "eventSource": "WEB",
        }
        wire = _CONSENTIMENTO_WIRE.get(e.consentimento_do_usuario)
        if wire is None:
            raise ValueError("evento sem consentimento declarado não entra no corpo")
        evento["consent"] = {"adUserData": wire}
        eventos.append(evento)
    return {"destinations": [destino], "events": eventos, "validateOnly": validate_only}


def _numero_json(d: Decimal) -> float:
    """O número JSON de um valor em centavos — e a prova de que ele não mudou.

    ⚠️ O JSON da API é número, e `json` escreve float pelo `repr` mais curto.
    Para valores em centavos isso devolve o mesmo texto decimal; a conferência
    abaixo garante que nenhum valor sai diferente do que foi medido.
    """
    f = float(d)
    if Decimal(repr(f)) != d:
        raise ValueError(f"o valor {d} não sobrevive à serialização JSON sem mudar")
    return f


def fatiar(itens: Sequence[Any], tamanho: int = MAX_EVENTOS_POR_REQUEST) -> List[Sequence[Any]]:
    return [itens[i:i + tamanho] for i in range(0, len(itens), tamanho)]
