"""`Observacao` canônica append-only, fonte-agnóstica. Domínio puro: sem I/O, sem relógio implícito.

Relógios (ordem obrigatória, documentada em `02-CONTRATO-DE-DADOS.md` §3):

    janela_inicio < janela_fim                       (event time: o período que o número descreve)
    janela_inicio <= observed_at                     (não se mede um período antes de ele começar)
    observed_at <= available_at <= ingested_at       (medição → conhecimento do VOLC → escrita no banco)
    source_updated_at <= available_at  (opcional)    (a fonte não pode dizer que atualizou depois de o VOLC saber)
    observed/zero_confirmed  ⇒ observed_at >= janela_fim   (janela aberta é `partial`, nunca `observed`)

`available_at` é o relógio do replay `as_of`. Ele é o instante em que o VOLC passou a ter o
payload (nunca retroativo: backfill de hoje sobre dia antigo tem `available_at` de hoje).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional
from functools import lru_cache
from zoneinfo import available_timezones

from ...contracts.observation import GRAOS_CONHECIDOS, ContratoViolado
from ...contracts.vocab import Metrica, ValueKind
from . import chaves
from .vocab import (
    BIGINT_MAX,
    BIGINT_MIN,
    COBERTURA_PPM_MAX,
    COBERTURA_PPM_MIN,
    COM_VALOR_OBRIGATORIO,
    SEM_MOTIVO_OBRIGATORIO,
    SEM_VALOR,
    UNIDADE_DA_METRICA,
    StatusObservacao,
    Unidade,
)

_FONTE = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MOEDA = re.compile(r"^[A-Z]{3}$")
# Instante na fronteira JSON: offset explícito obrigatório (espelho SQL em registrar_observacao) (R1-F9)
_INSTANTE_ISO = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?(Z|[+-][0-9]{2}:[0-9]{2})$")
# partial sem cobertura conhecida: cobertura_ppm nulo e este marcador no motivo (R1-F17)
COBERTURA_DESCONHECIDA = "cobertura_desconhecida"


@lru_cache(maxsize=1)
def _fusos() -> frozenset[str]:
    # nome exato da base IANA: no macOS o sistema de arquivos aceita "america/sao_paulo" (R1-F9)
    return frozenset(available_timezones())


class ObservacaoInvalida(ContratoViolado):
    """Observação que viola o contrato canônico. Subclasse do erro herdado para quem já o captura."""


def _texto(nome: str, v: Any, *, obrigatorio: bool = True) -> None:
    if v is None:
        if obrigatorio:
            raise ObservacaoInvalida(f"{nome} é obrigatório")
        return
    # só o espaço ASCII é aparado/recusado nas bordas: é o que `btrim` do Postgres faz (paridade com o CHECK)
    if not isinstance(v, str) or not v.strip(" "):
        raise ObservacaoInvalida(f"{nome} vazio ou não-texto")
    if v != v.strip(" "):
        raise ObservacaoInvalida(f"{nome} com espaço nas bordas (identidade não se normaliza em silêncio)")
    if chaves.tem_controle(v):
        raise ObservacaoInvalida(f"{nome} contém caractere de controle")


def _instante(nome: str, v: Any, *, obrigatorio: bool = True) -> None:
    if v is None:
        if obrigatorio:
            raise ObservacaoInvalida(f"{nome} é obrigatório")
        return
    if not isinstance(v, datetime):
        raise ObservacaoInvalida(f"{nome} precisa ser datetime")
    if v.tzinfo is None or v.utcoffset() is None:
        raise ObservacaoInvalida(f"{nome} sem timezone")


@dataclass(frozen=True, order=True)
class EntidadeRef:
    """Entidade observada. Tipo + id; nunca se casa por nome."""

    tipo: str
    id: str

    def __post_init__(self) -> None:
        _texto("entidade.tipo", self.tipo)
        _texto("entidade.id", self.id)


@dataclass(frozen=True, order=True)
class Coletor:
    """Identidade + versão do código que transformou o payload em observação."""

    nome: str
    versao: str

    def __post_init__(self) -> None:
        _texto("coletor.nome", self.nome)
        _texto("coletor.versao", self.versao)


@dataclass(frozen=True)
class Observacao:
    fonte: str
    conta: str
    entidade: EntidadeRef
    grao: tuple[str, ...]
    metrica: Metrica
    valor: Optional[int]
    unidade: Unidade
    moeda: Optional[str]
    janela_inicio: datetime
    janela_fim: datetime
    timezone: str
    observed_at: datetime
    available_at: datetime
    ingested_at: datetime
    run_id: str
    lote_id: str
    payload_sha256: str
    payload_ref: str
    schema_version: str
    coletor: Coletor
    status: StatusObservacao
    motivo: Optional[str] = None
    value_kind: Optional[ValueKind] = None
    dimensoes: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    source_updated_at: Optional[datetime] = None
    request_id: Optional[str] = None
    cobertura_ppm: Optional[int] = None

    # ------------------------------------------------------------------ validação
    def __post_init__(self) -> None:
        for nome, tipo in (("metrica", Metrica), ("unidade", Unidade), ("status", StatusObservacao)):
            try:
                object.__setattr__(self, nome, tipo(getattr(self, nome)))
            except ValueError as exc:
                raise ObservacaoInvalida(f"{nome} fora do vocabulário: {getattr(self, nome)!r}") from exc
        if self.value_kind is not None:
            try:
                object.__setattr__(self, "value_kind", ValueKind(self.value_kind))
            except ValueError as exc:
                raise ObservacaoInvalida(f"value_kind fora do vocabulário: {self.value_kind!r}") from exc
        if not isinstance(self.fonte, str) or not _FONTE.match(self.fonte):
            raise ObservacaoInvalida(f"fonte precisa ser slug minúsculo: {self.fonte!r}")
        _texto("conta", self.conta)
        if not isinstance(self.entidade, EntidadeRef):
            raise ObservacaoInvalida("entidade precisa ser EntidadeRef")
        if not isinstance(self.coletor, Coletor):
            raise ObservacaoInvalida("coletor precisa ser Coletor")
        for nome in ("run_id", "lote_id", "payload_ref", "schema_version"):
            _texto(nome, getattr(self, nome))
        _texto("request_id", self.request_id, obrigatorio=False)
        _texto("timezone", self.timezone)
        self._validar_grao_dimensoes()
        self._validar_relogios()
        self._validar_payload()
        self._validar_valor()

    def _validar_grao_dimensoes(self) -> None:
        if not isinstance(self.grao, tuple) or not self.grao:
            raise ObservacaoInvalida("grão vazio ou não-tupla")
        object.__setattr__(self, "grao", tuple(sorted(set(self.grao))))
        desconhecidos = set(self.grao) - GRAOS_CONHECIDOS
        if desconhecidos:
            raise ObservacaoInvalida(f"grão desconhecido: {sorted(desconhecidos)}")
        if not isinstance(self.dimensoes, tuple):
            raise ObservacaoInvalida("dimensoes precisa ser tupla de pares")
        nomes = []
        for par in self.dimensoes:
            if not isinstance(par, tuple) or len(par) != 2:
                raise ObservacaoInvalida("dimensão precisa ser par (nome, valor)")
            _texto("dimensao.nome", par[0])
            _texto("dimensao.valor", par[1])
            nomes.append(par[0])
        if nomes != sorted(nomes) or len(set(nomes)) != len(nomes):
            raise ObservacaoInvalida("dimensões precisam vir ordenadas e sem repetição")

    def _validar_relogios(self) -> None:
        for nome in ("janela_inicio", "janela_fim", "observed_at", "available_at", "ingested_at"):
            _instante(nome, getattr(self, nome))
        _instante("source_updated_at", self.source_updated_at, obrigatorio=False)
        if self.timezone not in _fusos():
            raise ObservacaoInvalida(f"timezone inválido: {self.timezone!r}")
        if self.janela_fim <= self.janela_inicio:
            raise ObservacaoInvalida("janela vazia ou invertida")
        if self.observed_at < self.janela_inicio:
            raise ObservacaoInvalida("observed_at anterior ao início da janela")
        if self.available_at < self.observed_at:
            raise ObservacaoInvalida("available_at anterior a observed_at")
        if self.ingested_at < self.available_at:
            raise ObservacaoInvalida("ingested_at anterior a available_at")
        if self.source_updated_at is not None and self.source_updated_at > self.available_at:
            raise ObservacaoInvalida("source_updated_at posterior a available_at")

    def _validar_payload(self) -> None:
        if not isinstance(self.payload_sha256, str) or not _SHA256.match(self.payload_sha256):
            raise ObservacaoInvalida("payload_sha256 precisa ser sha256 hex minúsculo")
        if self.payload_sha256 not in self.payload_ref:
            # referência imutável = endereçada por conteúdo; um caminho mutável sem hash não serve
            raise ObservacaoInvalida("payload_ref precisa conter o payload_sha256 (endereçamento por conteúdo)")

    def _validar_valor(self) -> None:
        v, st, un, m, k = self.valor, self.status, self.unidade, self.metrica, self.value_kind
        if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
            raise ObservacaoInvalida(f"valor precisa ser int (micros ou contagem), não {type(v).__name__}")
        if v is not None and not (BIGINT_MIN <= v <= BIGINT_MAX):
            raise ObservacaoInvalida("valor fora do intervalo bigint")
        if st not in SEM_MOTIVO_OBRIGATORIO and not (isinstance(self.motivo, str) and self.motivo.strip(" ")):
            raise ObservacaoInvalida(f"status {st.value} exige motivo")
        if self.motivo is not None and not isinstance(self.motivo, str):
            raise ObservacaoInvalida("motivo precisa ser texto")
        if st is StatusObservacao.OBSERVED:
            if v is None:
                raise ObservacaoInvalida("observed exige valor não nulo")
            if v == 0:
                raise ObservacaoInvalida("observed com 0: zero afirmado pela fonte é zero_confirmed")
        elif st is StatusObservacao.ZERO_CONFIRMED:
            if v != 0:
                raise ObservacaoInvalida("zero_confirmed exige valor 0 (null != 0)")
        elif st in SEM_VALOR:
            if v is not None:
                raise ObservacaoInvalida(f"{st.value} não carrega valor (null != 0; bruto fica no payload)")
        if st is StatusObservacao.PARTIAL:
            c = self.cobertura_ppm
            if c is None:
                if COBERTURA_DESCONHECIDA not in (self.motivo or ""):
                    raise ObservacaoInvalida(
                        f"partial exige cobertura_ppm declarada em 1..999999 ou motivo com '{COBERTURA_DESCONHECIDA}'")
            elif isinstance(c, bool) or not isinstance(c, int) or not (COBERTURA_PPM_MIN <= c <= COBERTURA_PPM_MAX):
                raise ObservacaoInvalida("partial exige cobertura_ppm declarada em 1..999999")
        elif self.cobertura_ppm is not None:
            raise ObservacaoInvalida("cobertura_ppm só existe em partial")
        if st in COM_VALOR_OBRIGATORIO and self.observed_at < self.janela_fim:
            raise ObservacaoInvalida(f"{st.value} com janela ainda aberta em observed_at: use partial")
        # unidade × métrica × moeda × value_kind
        if un not in UNIDADE_DA_METRICA[m]:
            raise ObservacaoInvalida(f"unidade {un.value} incompatível com {m.value}")
        if un is Unidade.CONTAGEM:
            if self.moeda is not None:
                raise ObservacaoInvalida("contagem não tem moeda")
            if v is not None and v < 0:
                raise ObservacaoInvalida("contagem negativa")
        else:
            if self.moeda is not None and (not isinstance(self.moeda, str) or not _MOEDA.match(self.moeda)):
                raise ObservacaoInvalida(f"moeda inválida: {self.moeda!r}")
            if v is not None and self.moeda is None:
                raise ObservacaoInvalida("valor em micros exige moeda explícita")
        if m is Metrica.RECEITA:
            if k is None:
                raise ObservacaoInvalida("receita exige value_kind explícito")
            if k is ValueKind.OBSERVED_AUCTION_SIGNAL:
                raise ObservacaoInvalida("sinal de leilão não é receita (X02)")
        elif m is Metrica.SINAL:
            if un is Unidade.MICROS and k is not ValueKind.OBSERVED_AUCTION_SIGNAL:
                raise ObservacaoInvalida("sinal monetário só pode ser observed_auction_signal")
            if un is Unidade.CONTAGEM and k is not None:
                raise ObservacaoInvalida("sinal não monetário não tem value_kind")
        elif k is not None:
            raise ObservacaoInvalida(f"{m.value} não tem value_kind")

    # ------------------------------------------------------------------ chaves
    @property
    def chave_natural(self) -> str:
        return chaves.chave_natural(
            fonte=self.fonte,
            conta=self.conta,
            entidade_tipo=self.entidade.tipo,
            entidade_id=self.entidade.id,
            grao=self.grao,
            dimensoes=self.dimensoes,
            metrica=self.metrica.value,
            value_kind=self.value_kind.value if self.value_kind else None,
            janela_inicio=self.janela_inicio,
            janela_fim=self.janela_fim,
            timezone_nome=self.timezone,
        )

    @property
    def chave_base(self) -> str:
        """Chave de idempotência da leitura (identidade + payload + esquema + coletor)."""
        return chaves.chave_base(
            chave_natural_hex=self.chave_natural,
            payload_sha256=self.payload_sha256,
            schema_version=self.schema_version,
            coletor_nome=self.coletor.nome,
            coletor_versao=self.coletor.versao,
        )

    @property
    def conteudo(self) -> tuple:
        """O que uma mesma leitura TEM de repetir. Diferença aqui com a mesma chave = coletor não determinístico."""
        return (self.status.value, self.valor, self.unidade.value, self.moeda, self.cobertura_ppm)

    @property
    def tem_valor(self) -> bool:
        return self.valor is not None

    # ------------------------------------------------------------------ serialização
    def para_json(self) -> dict:
        """Formato de troca com `dil_obs.registrar_observacao(jsonb)`. Instantes em ISO com offset."""
        return {
            "fonte": self.fonte,
            "conta": self.conta,
            "entidade_tipo": self.entidade.tipo,
            "entidade_id": self.entidade.id,
            "grao": list(self.grao),
            "dimensoes": [list(d) for d in self.dimensoes],
            "metrica": self.metrica.value,
            "value_kind": self.value_kind.value if self.value_kind else None,
            "valor": self.valor,
            "unidade": self.unidade.value,
            "moeda": self.moeda,
            "janela_inicio": self.janela_inicio.isoformat(),
            "janela_fim": self.janela_fim.isoformat(),
            "timezone": self.timezone,
            "observed_at": self.observed_at.isoformat(),
            "source_updated_at": self.source_updated_at.isoformat() if self.source_updated_at else None,
            "available_at": self.available_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "run_id": self.run_id,
            "request_id": self.request_id,
            "lote_id": self.lote_id,
            "payload_sha256": self.payload_sha256,
            "payload_ref": self.payload_ref,
            "schema_version": self.schema_version,
            "coletor_nome": self.coletor.nome,
            "coletor_versao": self.coletor.versao,
            "status": self.status.value,
            "motivo": self.motivo,
            "cobertura_ppm": self.cobertura_ppm,
        }

    @classmethod
    def de_json_texto(cls, texto: str) -> "Observacao":
        """Lê o texto JSON como o banco: chave repetida, NaN/Infinity e número não inteiro são recusados."""
        def sem_repeticao(pares):
            nomes = [k for k, _ in pares]
            if len(nomes) != len(set(nomes)):
                raise ObservacaoInvalida("JSON com chave repetida")
            return dict(pares)

        def constante(nome):
            raise ObservacaoInvalida(f"constante JSON não aceita: {nome}")

        try:
            d = json.loads(texto, object_pairs_hook=sem_repeticao, parse_constant=constante)
        except json.JSONDecodeError as exc:
            raise ObservacaoInvalida("JSON malformado") from exc
        if not isinstance(d, dict):
            raise ObservacaoInvalida("observação precisa ser objeto JSON")
        return cls.de_json(d)

    @classmethod
    def de_json(cls, d: Mapping[str, Any]) -> "Observacao":
        conhecidos = set(CAMPOS_JSON)
        extras = set(d) - conhecidos
        if extras:
            raise ObservacaoInvalida(f"campos desconhecidos: {sorted(extras)}")

        def ts(nome: str, obrigatorio: bool = True) -> Optional[datetime]:
            bruto = d.get(nome)
            if bruto is None:
                if obrigatorio:
                    raise ObservacaoInvalida(f"{nome} é obrigatório")
                return None
            if not isinstance(bruto, str) or not _INSTANTE_ISO.match(bruto):
                raise ObservacaoInvalida(f"{nome} precisa ser ISO-8601 com offset explícito")
            try:
                return datetime.fromisoformat(bruto)
            except (TypeError, ValueError) as exc:
                raise ObservacaoInvalida(f"{nome} inválido") from exc

        try:
            return cls(
                fonte=d["fonte"],
                conta=d["conta"],
                entidade=EntidadeRef(d["entidade_tipo"], d["entidade_id"]),
                grao=tuple(d["grao"]),
                dimensoes=tuple(tuple(x) for x in d.get("dimensoes") or ()),  # type: ignore[misc]
                metrica=d["metrica"],
                value_kind=d.get("value_kind"),
                valor=d.get("valor"),
                unidade=d["unidade"],
                moeda=d.get("moeda"),
                janela_inicio=ts("janela_inicio"),  # type: ignore[arg-type]
                janela_fim=ts("janela_fim"),  # type: ignore[arg-type]
                timezone=d["timezone"],
                observed_at=ts("observed_at"),  # type: ignore[arg-type]
                source_updated_at=ts("source_updated_at", False),
                available_at=ts("available_at"),  # type: ignore[arg-type]
                ingested_at=ts("ingested_at"),  # type: ignore[arg-type]
                run_id=d["run_id"],
                request_id=d.get("request_id"),
                lote_id=d["lote_id"],
                payload_sha256=d["payload_sha256"],
                payload_ref=d["payload_ref"],
                schema_version=d["schema_version"],
                coletor=Coletor(d["coletor_nome"], d["coletor_versao"]),
                status=d["status"],
                motivo=d.get("motivo"),
                cobertura_ppm=d.get("cobertura_ppm"),
            )
        except KeyError as exc:
            raise ObservacaoInvalida(f"campo obrigatório ausente: {exc.args[0]}") from exc


CAMPOS_JSON = (
    "fonte", "conta", "entidade_tipo", "entidade_id", "grao", "dimensoes", "metrica", "value_kind",
    "valor", "unidade", "moeda", "janela_inicio", "janela_fim", "timezone", "observed_at",
    "source_updated_at", "available_at", "ingested_at", "run_id", "request_id", "lote_id",
    "payload_sha256", "payload_ref", "schema_version", "coletor_nome", "coletor_versao", "status",
    "motivo", "cobertura_ppm",
)
