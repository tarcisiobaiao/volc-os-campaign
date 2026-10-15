"""As portas: o que o caso de uso precisa do mundo, sem saber de onde vem.

A receita e o câmbio são do W12 (v23_01: `vw_receita_vigente` e
`cambio_resolver`). Este pacote os consome por estas interfaces e não importa
nada do W12: quando a v23_01 for aplicada, o adaptador PostgREST lê as duas, e
nenhuma linha daqui muda.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple

from ..domain.evento import CliqueObservado
from ..domain.valor import Coorte, CotacaoResolvida, ReceitaDatada


class FonteDeCliques(Protocol):
    def cliques(self, *, customer_id: str, de: date, ate: date) -> Sequence[CliqueObservado]:
        """Visitas pagas da conta com gclid/gbraid/wbraid, no intervalo de coortes."""

    def sessoes_da_coorte(self, coorte: Coorte) -> Optional[int]:
        """Todas as sessões da coorte (com ou sem clique). `None` = não se sabe."""


class FonteDeReceita(Protocol):
    def receita_vigente(self, *, fonte: str, coorte: Coorte,
                        conhecido_ate: Optional[datetime]) -> Optional[ReceitaDatada]:
        """A versão vigente da receita da coorte, como o banco a sabia em `conhecido_ate`."""


class FonteDeCambio(Protocol):
    def resolver(self, *, data: date, par: str, max_defasagem_dias: int,
                 conhecido_ate: Optional[datetime]) -> CotacaoResolvida:
        """`cambio_resolver(data, par, defasagem, conhecido_ate)` da v23_01."""


# ── registro (ledger v25_01) ───────────────────────────────────────────────

MODO_VALIDATE_ONLY = "validate_only"
MODO_REAL = "real"

#: Estados de lote que PRENDEM o transaction_id (não pode ir de novo).
ESTADOS_VIVOS = ("em_voo", "aceito", "sem_resposta", "processando", "sucesso", "sucesso_parcial")


@dataclass(frozen=True)
class EnvioAnterior:
    """Um envio REAL já registrado para este transaction_id."""

    lote_id: int
    estado: str
    valor_impressao: str


@dataclass(frozen=True)
class LoteRegistrado:
    lote_id: int
    impressao: str
    modo: str
    estado: str
    request_id: Optional[str] = None


class RegistroDeConversoes(Protocol):
    def envios_reais_vivos(self, *, operating_account_id: str, product_destination_id: str,
                           transaction_ids: Sequence[str]) -> Mapping[str, EnvioAnterior]:
        ...

    def registrar_decisoes(self, *, rodada: str, customer_id: str,
                           operating_account_id: str, product_destination_id: str,
                           decisoes: Sequence[Dict[str, Any]]) -> None:
        ...

    def abrir_lote(self, *, modo: str, impressao: str, customer_id: str,
                   login_customer_id: str, operating_account_id: str,
                   product_destination_id: str,
                   itens: Sequence[Tuple[str, str]],
                   aprovacao: Optional[Mapping[str, Any]] = None,
                   validacao_lote_id: Optional[int] = None) -> LoteRegistrado:
        """Abre o lote `em_voo` ANTES da chamada. `itens` = (transaction_id, valor_impressao).

        Para `real`, o banco recusa (23505) um segundo envio vivo do mesmo
        envelope ou do mesmo transaction_id: é ele, não este processo, que
        garante o no máximo uma vez.
        """

    def ler_lote(self, lote_id: int) -> Optional[LoteRegistrado]:
        ...

    def fechar_lote(self, *, lote_id: int, estado: str, request_id: Optional[str],
                    resposta: Mapping[str, Any]) -> None:
        ...


# ── transporte (Data Manager) ──────────────────────────────────────────────

@dataclass(frozen=True)
class RespostaDeIngestao:
    """O que `events:ingest` respondeu.

    `respondeu=False` é ignorância (timeout, rede, 5xx): ninguém disse se o
    lote entrou. Nunca vira "falhou, tente de novo".
    """

    respondeu: bool
    aceito: bool
    status_http: Optional[int] = None
    request_id: Optional[str] = None
    avisos: Tuple[Mapping[str, Any], ...] = ()
    erro: Optional[Mapping[str, Any]] = None
    corpo: Mapping[str, Any] = field(default_factory=dict)

    def json(self) -> Dict[str, Any]:
        return {"respondeu": self.respondeu, "aceito": self.aceito,
                "status_http": self.status_http, "request_id": self.request_id,
                "avisos": list(self.avisos), "erro": self.erro}


@dataclass(frozen=True)
class StatusDoPedido:
    """`requestStatus:retrieve`. Só existe para pedido real (nunca validate_only)."""

    estado: str  # PROCESSING | SUCCESS | FAILURE | PARTIAL_SUCCESS
    corpo: Mapping[str, Any] = field(default_factory=dict)


class NaoSaiu(RuntimeError):
    """Falha comprovadamente ANTES de o pedido sair (credencial, montagem)."""


class TransporteDataManager(Protocol):
    def ingerir(self, corpo: Mapping[str, Any]) -> RespostaDeIngestao:
        ...

    def status(self, request_id: str) -> StatusDoPedido:
        ...
