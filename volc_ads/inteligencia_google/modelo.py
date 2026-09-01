"""Contrato semantico da coleta Google Ads -> Supabase.

Zero e um valor medido. Ausencia, nao aplicabilidade e falha nao carregam valor.
Uma chamada que voltou sem itens e ``vazio_confirmado``; excecao e ``falhou``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

COLETOR_VERSAO = 3
API_VERSAO = "v25"

# Uma familia e o nome da PERGUNTA que a leitura respondeu. Ela existe porque o
# `tipo_sinal` do ledger v12_01 e um CHECK fechado em seis valores, e leituras
# diferentes podem precisar caber sob o mesmo valor sem se confundirem. Formato
# fechado de proposito: a familia entra na chave de idempotencia, e um separador
# ou um sinal de igual dentro dela criaria ambiguidade na chave.
_FAMILIA = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class EstadoColeta(str, Enum):
    COM_DADOS = "com_dados"
    VAZIO_CONFIRMADO = "vazio_confirmado"
    PARCIAL = "parcial"
    INELEGIVEL = "inelegivel"
    NAO_SUPORTADO = "nao_suportado"
    FALHOU = "falhou"


class EstadoValor(str, Enum):
    MEDIDO = "medido"
    AUSENTE = "ausente"
    NAO_APLICAVEL = "nao_aplicavel"
    FALHOU = "falhou"


def _jsonavel(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    raise TypeError(f"tipo nao serializavel: {type(valor).__name__}")


def _json_canonico(valor: Any) -> str:
    return json.dumps(
        valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=_jsonavel,
    )


@dataclass(frozen=True)
class Item:
    tipo_item: str
    payload: dict[str, Any]
    recurso_externo: str | None = None

    def serializar(self, ordinal: int) -> dict[str, Any]:
        return {
            "ordinal": ordinal,
            "tipo_item": self.tipo_item,
            "recurso_externo": self.recurso_externo,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class Metrica:
    recurso_tipo: str
    recurso_externo: str
    nome: str
    estado_valor: EstadoValor
    valor_numerico: int | float | Decimal | None = None
    valor_texto: str | None = None
    unidade: str | None = None
    moeda: str | None = None

    def __post_init__(self) -> None:
        tem_numero = self.valor_numerico is not None
        tem_texto = self.valor_texto is not None
        if self.estado_valor is EstadoValor.MEDIDO and tem_numero == tem_texto:
            raise ValueError("metrica medida exige exatamente um valor")
        if self.estado_valor is not EstadoValor.MEDIDO and (tem_numero or tem_texto):
            raise ValueError("metrica nao medida nao pode carregar valor")

    def serializar(self) -> dict[str, Any]:
        return {
            "recurso_tipo": self.recurso_tipo,
            "recurso_externo": self.recurso_externo,
            "nome": self.nome,
            "estado_valor": self.estado_valor.value,
            "valor_numerico": None if self.valor_numerico is None else str(self.valor_numerico),
            "valor_texto": self.valor_texto,
            "unidade": self.unidade,
            "moeda": self.moeda,
        }


@dataclass
class DocumentoColeta:
    tipo_sinal: str
    estado: EstadoColeta
    customer_id: str
    login_customer_id: str
    competencia: date
    coletada_em: datetime
    bucket: str
    quantidade: int | None
    payload: dict[str, Any] = field(default_factory=dict)
    itens: list[Item] = field(default_factory=list)
    metricas: list[Metrica] = field(default_factory=list)
    volc_campaign_id: str | None = None
    campaign_id: str | None = None
    janela_inicio: date | None = None
    janela_fim: date | None = None
    request_ids: list[str] = field(default_factory=list)
    erro_codigo: str | None = None
    erro_classe: str | None = None
    erro_detalhe: str | None = None
    familia: str | None = None

    def __post_init__(self) -> None:
        if self.familia is not None and not _FAMILIA.fullmatch(self.familia):
            raise ValueError("familia possui formato invalido")
        if self.coletada_em.tzinfo is None:
            raise ValueError("coletada_em precisa de timezone")
        if (self.volc_campaign_id is None) != (self.campaign_id is None):
            raise ValueError("identidade interna e externa da campanha viajam juntas")
        if self.estado is EstadoColeta.COM_DADOS and (self.quantidade or 0) <= 0:
            raise ValueError("com_dados exige quantidade positiva")
        if self.estado is EstadoColeta.VAZIO_CONFIRMADO and self.quantidade != 0:
            raise ValueError("vazio_confirmado exige quantidade zero")
        if self.estado in {
            EstadoColeta.INELEGIVEL, EstadoColeta.NAO_SUPORTADO, EstadoColeta.FALHOU,
        } and self.quantidade is not None:
            raise ValueError("estado sem leitura nao pode inventar quantidade")
        if self.estado is EstadoColeta.FALHOU and not (self.erro_codigo and self.erro_classe):
            raise ValueError("falha precisa de codigo e classe")

    @classmethod
    def agora(cls, **kwargs: Any) -> "DocumentoColeta":
        instante = datetime.now(timezone.utc)
        return cls(coletada_em=instante, competencia=instante.date(), **kwargs)

    def serializar(self) -> dict[str, Any]:
        escopo = self.campaign_id or "conta"
        # Uma falha não pode ocupar para sempre a chave do intervalo e esconder
        # uma repetição posterior bem-sucedida. Estado entra na identidade para
        # preservar ambos os recibos; código/classe distinguem falhas diferentes.
        desfecho = self.estado.value
        if self.estado is EstadoColeta.FALHOU:
            desfecho = "|".join((desfecho, self.erro_codigo or "", self.erro_classe or ""))
        partes = [
            self.customer_id, escopo, self.tipo_sinal, self.bucket,
            str(COLETOR_VERSAO), desfecho,
        ]
        if self.familia is not None:
            # Componente ADICIONAL, nunca posicional: sem familia a chave sai
            # byte a byte igual a de antes desta linha existir, e o que ja esta
            # gravado continua deduplicando contra a proxima repeticao. O
            # prefixo `familia=` desambigua do sufixo de uma falha, cujos dois
            # componentes sao codigo e classe de excecao — nenhum deles carrega
            # `=`, entao nenhuma falha consegue se disfarcar de familia.
            partes.append(f"familia={self.familia}")
        chave = hashlib.sha256("|".join(partes).encode()).hexdigest()
        # A familia viaja no payload porque a RPC v12_01 grava `documento->
        # 'payload'` inteiro e nao tem coluna para ela. O hash cobre o payload
        # efetivo, entao o recibo continua verificavel campo a campo.
        payload = (
            self.payload if self.familia is None
            else {**self.payload, "familia": self.familia}
        )
        payload_hash = hashlib.sha256(_json_canonico(payload).encode()).hexdigest()
        return {
            "chave_idempotencia": chave,
            "tipo_sinal": self.tipo_sinal,
            "familia": self.familia,
            "estado": self.estado.value,
            "customer_id": self.customer_id,
            "login_customer_id": self.login_customer_id,
            "volc_campaign_id": self.volc_campaign_id,
            "campaign_id": self.campaign_id,
            "janela_inicio": self.janela_inicio.isoformat() if self.janela_inicio else None,
            "janela_fim": self.janela_fim.isoformat() if self.janela_fim else None,
            "competencia": self.competencia.isoformat(),
            "coletada_em": self.coletada_em.isoformat(),
            "bucket": self.bucket,
            "api_versao": API_VERSAO,
            "coletor_versao": COLETOR_VERSAO,
            "quantidade": self.quantidade,
            "request_ids": self.request_ids,
            "payload": payload,
            "payload_sha256": payload_hash,
            "erro_codigo": self.erro_codigo,
            "erro_classe": self.erro_classe,
            "erro_detalhe": self.erro_detalhe,
            "itens": [item.serializar(i) for i, item in enumerate(self.itens)],
            "metricas": [metrica.serializar() for metrica in self.metricas],
        }


def metrica_de_dict(
    objeto: dict[str, Any], caminho: tuple[str, ...], *, recurso_tipo: str,
    recurso_externo: str, nome: str, unidade: str | None = None,
    moeda: str | None = None,
) -> Metrica:
    atual: Any = objeto
    for parte in caminho:
        if not isinstance(atual, dict) or parte not in atual:
            return Metrica(
                recurso_tipo, recurso_externo, nome, EstadoValor.AUSENTE,
                unidade=unidade, moeda=moeda,
            )
        atual = atual[parte]
    if atual is None:
        return Metrica(
            recurso_tipo, recurso_externo, nome, EstadoValor.AUSENTE,
            unidade=unidade, moeda=moeda,
        )
    if isinstance(atual, bool):
        return Metrica(
            recurso_tipo, recurso_externo, nome, EstadoValor.MEDIDO,
            valor_texto=str(atual).lower(), unidade=unidade, moeda=moeda,
        )
    if isinstance(atual, (int, float, Decimal)) or (
        isinstance(atual, str) and atual.replace(".", "", 1).isdigit()
    ):
        return Metrica(
            recurso_tipo, recurso_externo, nome, EstadoValor.MEDIDO,
            valor_numerico=Decimal(str(atual)), unidade=unidade, moeda=moeda,
        )
    return Metrica(
        recurso_tipo, recurso_externo, nome, EstadoValor.MEDIDO,
        valor_texto=str(atual), unidade=unidade, moeda=moeda,
    )
