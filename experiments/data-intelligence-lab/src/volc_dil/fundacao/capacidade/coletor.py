"""Esqueleto de "coletor seguro": contrato `run_coleta` + executor com timeout, retry, idempotência,
heartbeat, recibo de run e dead letter — gravando pelas regras do contrato canônico da frente A.

Revisado após a revisão adversarial R1 (F10, F11, F12):

- **Trava por capacidade (F11)**: o adaptador NÃO recebe nem guarda cliente de API. Em cada leitura
  o executor lhe entrega um `ClienteLeitura`, fachada cuja única operação é `consultar(ConsultaLeitura)`;
  `ConsultaLeitura` só admite GAQL `SELECT` ou HTTP `GET`. O transporte (o que fala com a rede) é
  injetado no executor, nunca no adaptador, e este módulo não contém transporte real. O destino em
  modo `gravar` precisa ser exatamente `SinkMemoria` (tipo exato, não subclasse nem declaração).
  Limite honesto: Python não impede código hostil de abrir a própria conexão; a trava fecha os
  caminhos que o executor oferece, e a suíte bloqueia rede (conftest).
- **dry_run com sink nulo (F11)**: no modo padrão nada é gravado em lugar nenhum — nem heartbeat,
  nem recibo, nem dead letter; o sink recebido é ignorado. O recibo volta só para o chamador.
- **Timeout que não prende o processo (F12)**: o transporte recebe o prazo restante (timeout no
  cliente) e a leitura roda numa thread *daemon* como contenção: se a fonte travar, a tentativa é
  abandonada, o resultado tardio nunca é consumido e o interpretador sai sem esperar a thread.
- **A→B→A e equivalência serial × paralela (F10)**: o executor não tem regra própria de dedup. Cada
  linha devolvida vira um payload endereçado por conteúdo; o normalizador da frente A
  (`volc_dil.fundacao.observacao.normalizar`) produz `Observacao` canônicas e o `Registro` da frente A
  decide INSERIDO / NOOP. Regras da frente A após D1/D2: `observed_at` entra na chave da leitura (reler
  o mesmo valor em outra hora é versão nova; retry da mesma leitura é NOOP) e a versão vigente no `as_of`
  é a de maior `observed_at` (empate → maior `available_at`). `observed_at` = instante REAL da leitura
  (carimbo do transporte, ou fim da leitura) — nunca o slot (ver `_observado_em`). `available_at` = relógio
  monotônico do sink na gravação ("relógio do banco"; o coletor não declara quando o VOLC soube, cf. F1).
  Em lote, a leitura pode ser paralela e a gravação é serial por (slot, conta, coletor) — sob D1 a ordem
  de gravação não muda o estado final (vence a medição mais recente); ela só fixa o `available_at`, o que
  deixa o `as_of` por instante de conhecimento determinístico entre serial e paralelo.

Semântica preservada: chave de execução determinística = sha256(coletor, conta, janela, slot); slot
repetido = `ja_concluido`; erro transitório → retry com backoff exponencial e *full jitter*
determinístico; permanente/desconhecido → dead letter sem retry; transitório esgotado → dead letter.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Protocol

from ..observacao import (
    Coletor,
    ContextoLeitura,
    EsquemaPayload,
    PayloadBruto,
    Registro,
    ResultadoRegistro,
    normalizar,
)

MODOS = ("dry_run", "gravar")


class TravaViolada(RuntimeError):
    """Modo desconhecido, sink que não é o de memória, consulta que não é leitura."""


class ErroTransitorio(Exception):
    """Falha que pode passar sozinha: timeout, 429, 5xx, conexão interrompida."""


class ErroPermanente(Exception):
    """Falha que não passa com retry: 400, credencial, contrato/schema, permissão."""


class _TempoEsgotado(Exception):
    pass


# --------------------------------------------------------------------------- capacidade de leitura
_GAQL_SELECT = re.compile(r"^\s*SELECT\s", re.IGNORECASE)


@dataclass(frozen=True)
class ConsultaLeitura:
    """Única forma de pedir dado a uma fonte: GAQL `SELECT` (searchStream) ou HTTP `GET`."""

    tipo: str  # "gaql" | "http_get"
    texto: str  # GAQL ou URL https

    def __post_init__(self) -> None:
        if self.tipo == "gaql":
            if not _GAQL_SELECT.match(self.texto) or ";" in self.texto:
                raise TravaViolada("GAQL precisa ser um único SELECT")
        elif self.tipo == "http_get":
            if not self.texto.startswith("https://"):
                raise TravaViolada("leitura HTTP só por https GET")
        else:
            raise TravaViolada(f"tipo de consulta não é leitura: {self.tipo!r}")


class TransporteLeitura(Protocol):
    """O que fala com a rede (injetado no EXECUTOR). Não existe implementação real neste módulo."""

    def executar_leitura(self, consulta: ConsultaLeitura, timeout_s: float) -> list[Mapping[str, Any]]: ...


class ClienteLeitura:
    """Fachada entregue ao adaptador a cada leitura. Só sabe `consultar`; prazo propagado ao transporte."""

    __slots__ = ("_consultar",)

    def __init__(self, transporte: TransporteLeitura, prazo: Callable[[], float]) -> None:
        def _consultar(consulta: ConsultaLeitura) -> list[Mapping[str, Any]]:
            if not isinstance(consulta, ConsultaLeitura):
                raise TravaViolada("consultar recebe ConsultaLeitura")
            restante = prazo()
            if restante <= 0:
                raise ErroTransitorio("prazo da tentativa esgotado antes da consulta")
            return list(transporte.executar_leitura(consulta, restante))

        object.__setattr__(self, "_consultar", _consultar)

    def consultar(self, consulta: ConsultaLeitura) -> list[Mapping[str, Any]]:
        return self._consultar(consulta)

    def __setattr__(self, *_a) -> None:  # pragma: no cover - imutável
        raise AttributeError("ClienteLeitura é imutável")


# --------------------------------------------------------------------------- contrato
@dataclass(frozen=True)
class PedidoLeitura:
    coletor: str
    conta: str
    janela_inicio: str  # ISO date
    janela_fim: str
    slot: str  # instante AGENDADO (ISO), não o instante real de execução

    def chave_execucao(self) -> str:
        return _sha256({"coletor": self.coletor, "conta": self.conta, "janela": [self.janela_inicio, self.janela_fim],
                        "slot": self.slot})


@dataclass(frozen=True)
class ContextoFonte:
    """O que o adaptador declara sobre a resposta (identidade, janela, moeda provada, esquema)."""

    fonte: str
    entidade_tipo: str
    grao: tuple[str, ...]
    janela_inicio: datetime
    janela_fim: datetime
    timezone: str
    coletor: Coletor
    esquema: EsquemaPayload
    moeda: Optional[str] = None  # só quando a resposta prova a moeda (ex.: customer.currency_code)


@dataclass(frozen=True)
class RespostaLeitura:
    linhas: tuple[Mapping[str, Any], ...]
    contexto: ContextoFonte
    # instante em que a fonte foi lida, carimbado pelo transporte (ex.: início da requisição). Se None, o
    # executor usa o instante em que a leitura terminou. NUNCA o slot agendado: ver `_observado_em`.
    observado_em: Optional[datetime] = None


class Adaptador(Protocol):
    nome: str

    def ler(self, pedido: PedidoLeitura, cliente: ClienteLeitura) -> RespostaLeitura: ...


@dataclass
class ItemDeadLetter:
    pedido: PedidoLeitura
    chave_execucao: str
    motivo: str
    erro: str
    tentativas: int
    instante: datetime


@dataclass
class ReciboRun:
    chave_execucao: str
    pedido: PedidoLeitura
    modo: str
    status: str  # "concluido" | "dry_run" | "ja_concluido" | "dead_letter"
    tentativas: int
    linhas_lidas: int = 0
    observacoes: int = 0
    inseridas: int = 0
    noop: int = 0
    confirmadas: int = 0  # [thread A, D2'] releitura com o mesmo estado: confirmação estreita, não versão
    rejeicoes: int = 0
    payloads_distintos: int = 0
    lido_em: Optional[datetime] = None
    gravado_em: Optional[datetime] = None
    erros: list[str] = field(default_factory=list)
    motivo_dead_letter: Optional[str] = None

    @property
    def gravadas_novas(self) -> int:
        return self.inseridas


@dataclass(frozen=True)
class PoliticaRetry:
    max_tentativas: int = 4
    base_s: float = 1.0
    teto_s: float = 60.0
    timeout_s: float = 30.0
    seed: int = 20261016

    def espera(self, tentativa: int, rng: random.Random) -> float:
        """Backoff exponencial com 'full jitter': U(0, min(teto, base·2^(t−1)))."""
        return rng.uniform(0.0, min(self.teto_s, self.base_s * (2 ** (tentativa - 1))))


def _sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- sink
class RelogioMonotonico:
    """Relógio do sink: UTC real, estritamente crescente (empates viram +1 µs)."""

    def __init__(self, fonte: Callable[[], datetime] | None = None) -> None:
        self._fonte = fonte or (lambda: datetime.now(timezone.utc))
        self._ultimo: datetime | None = None
        self._lock = threading.Lock()

    def __call__(self) -> datetime:
        with self._lock:
            t = self._fonte()
            if self._ultimo is not None and t <= self._ultimo:
                t = self._ultimo + timedelta(microseconds=1)
            self._ultimo = t
            return t


class SinkMemoria:
    """Único destino de gravação aceito. Observações pelo `Registro` da frente A (append-only)."""

    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        self._lock = threading.RLock()
        self.agora = RelogioMonotonico(relogio)
        self.registro = Registro()
        self.payloads: dict[str, bytes] = {}
        self.runs: dict[str, ReciboRun] = {}
        self.heartbeats: list[tuple[str, datetime, str]] = []
        self.dead_letters: list[ItemDeadLetter] = []
        self.chamadas_gravar = 0

    def run_concluido(self, chave_execucao: str) -> bool:
        with self._lock:
            r = self.runs.get(chave_execucao)
            return r is not None and r.status == "concluido"

    def registrar_run(self, recibo: ReciboRun) -> None:
        with self._lock:
            self.runs[recibo.chave_execucao] = recibo

    def heartbeat(self, coletor: str, estado: str) -> None:
        with self._lock:
            self.heartbeats.append((coletor, self.agora(), estado))

    def dead_letter(self, item: ItemDeadLetter) -> None:
        with self._lock:
            self.dead_letters.append(item)

    def gravar(self, observacoes, payloads: Mapping[str, bytes]) -> dict[str, int]:
        with self._lock:
            self.chamadas_gravar += 1
            cont = {r.value: 0 for r in ResultadoRegistro}
            for o in observacoes:
                cont[self.registro.registrar(o).value] += 1
            for h, p in payloads.items():
                self.payloads.setdefault(h, p)
            return cont

    def as_of(self, t: datetime) -> dict[str, tuple]:
        """Conteúdo de negócio conhecido em t, por chave natural (sem relógios nem chaves de run)."""
        return {k: (o.metrica.value, o.entidade.id, o.status.value, o.valor) for k, o in self.registro.as_of(t).items()}

    def instantes_de_gravacao(self) -> list[datetime]:
        return sorted({v.observacao.available_at for v in self.registro.versoes})


class _SinkNulo:
    """dry_run: não grava nada, em lugar nenhum."""

    def run_concluido(self, chave_execucao: str) -> bool:
        return False

    def heartbeat(self, coletor: str, estado: str) -> None:
        return None


def verificar_trava(adaptador: object, sink: object, modo: str) -> None:
    if modo not in MODOS:
        raise TravaViolada(f"modo desconhecido {modo!r}; permitidos: {MODOS}")
    if not callable(getattr(adaptador, "ler", None)):
        raise TravaViolada("adaptador precisa ter ler(pedido, cliente)")
    if modo == "gravar" and type(sink) is not SinkMemoria:
        raise TravaViolada("em 'gravar' o único destino aceito é SinkMemoria (não há sink externo neste módulo)")


# --------------------------------------------------------------------------- fase 1: leitura
@dataclass
class _Leitura:
    pedido: PedidoLeitura
    recibo: ReciboRun
    resposta: Optional[RespostaLeitura] = None
    motivo_falha: Optional[str] = None


def _com_prazo(fn: Callable[[], Any], timeout_s: float) -> Any:
    """Roda `fn` numa thread daemon; estourado o prazo, abandona (o processo pode sair)."""
    caixa: dict[str, Any] = {}
    pronto = threading.Event()

    def alvo() -> None:
        try:
            caixa["r"] = fn()
        except BaseException as e:  # noqa: BLE001 - repassado ao chamador
            caixa["e"] = e
        finally:
            pronto.set()

    threading.Thread(target=alvo, daemon=True, name="coleta-leitura").start()
    if not pronto.wait(timeout_s):
        raise _TempoEsgotado()
    if "e" in caixa:
        raise caixa["e"]
    return caixa["r"]


def _ler(pedido, adaptador, transporte, sink, modo, politica, relogio, dormir) -> _Leitura:
    import time

    chave = pedido.chave_execucao()
    rec = ReciboRun(chave_execucao=chave, pedido=pedido, modo=modo, status="em_andamento", tentativas=0)
    leitura = _Leitura(pedido, rec)
    if sink.run_concluido(chave):
        rec.status = "ja_concluido"
        sink.heartbeat(pedido.coletor, "ja_concluido")
        return leitura
    sink.heartbeat(pedido.coletor, "iniciado")
    rng = random.Random(f"{politica.seed}:{chave}")
    for tentativa in range(1, politica.max_tentativas + 1):
        rec.tentativas = tentativa
        limite = time.monotonic() + politica.timeout_s
        cliente = ClienteLeitura(transporte, lambda limite=limite: limite - time.monotonic())
        try:
            leitura.resposta = _com_prazo(lambda: adaptador.ler(pedido, cliente), politica.timeout_s)
            rec.lido_em = relogio()
            break
        except _TempoEsgotado:
            rec.erros.append(f"t{tentativa}: timeout>{politica.timeout_s}s")
            leitura.motivo_falha = "tentativas_esgotadas"
        except ErroTransitorio as e:
            rec.erros.append(f"t{tentativa}: transitorio: {e}")
            leitura.motivo_falha = "tentativas_esgotadas"
        except (ErroPermanente, TravaViolada) as e:
            rec.erros.append(f"t{tentativa}: permanente: {e}")
            leitura.motivo_falha = "erro_permanente"
            break
        except Exception as e:  # desconhecido = permanente: não martelar a fonte
            rec.erros.append(f"t{tentativa}: desconhecido: {type(e).__name__}: {e}")
            leitura.motivo_falha = "erro_desconhecido"
            break
        sink.heartbeat(pedido.coletor, f"retry_{tentativa}")
        if tentativa < politica.max_tentativas:
            dormir(politica.espera(tentativa, rng))
    return leitura


# --------------------------------------------------------------------------- fase 2: gravação
def _normalizar(leitura: _Leitura, instante: datetime) -> tuple[list, dict[str, bytes], list[str]]:
    resp, ped, rec = leitura.resposta, leitura.pedido, leitura.recibo
    ctx_f = resp.contexto
    observed = _observado_em(resp, rec, instante)
    obs: list = []
    payloads: dict[str, bytes] = {}
    rejeicoes: list[str] = []
    esquemas = {ctx_f.esquema.schema_version: ctx_f.esquema}
    for i, linha in enumerate(resp.linhas):
        # uma linha = um payload endereçado por conteúdo: reler a mesma linha dá o MESMO sha256 e,
        # portanto, a mesma chave de leitura no Registro (é o que permite NOOP e A→B→A)
        corpo = json.dumps([linha], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        pb = PayloadBruto(ctx_f.esquema.schema_version, corpo)
        payloads[pb.sha256] = corpo
        ctx = ContextoLeitura(fonte=ctx_f.fonte, conta=ped.conta, entidade_tipo=ctx_f.entidade_tipo, grao=ctx_f.grao,
                              janela_inicio=ctx_f.janela_inicio, janela_fim=ctx_f.janela_fim, timezone=ctx_f.timezone,
                              observed_at=observed, available_at=instante, ingested_at=instante,
                              run_id=rec.chave_execucao, lote_id=f"{rec.chave_execucao}:{i}", coletor=ctx_f.coletor,
                              moeda=ctx_f.moeda)
        r = normalizar(pb, esquemas, ctx)
        obs.extend(r.observacoes)
        rejeicoes.extend(x.motivo for x in r.rejeicoes)
    return obs, payloads, rejeicoes


class _ObservadoInvalido(Exception):
    pass


def _observado_em(resp: RespostaLeitura, rec: ReciboRun, instante: datetime) -> datetime:
    """`observed_at` = instante REAL da leitura (regra D1 da frente A: a medição mais recente vence).

    Não se usa o slot agendado: uma execução atrasada (fila, retry, backfill) lê o estado da fonte no
    instante em que roda; carimbá-la com o slot antigo diria que o estado das 09h era o das 06h e, sob
    D1, poderia perder para uma leitura que de fato é mais velha. O contrato exige observed ≤ available
    (o instante da gravação); violação é erro do transporte, não algo a corrigir em silêncio.
    """
    obs = resp.observado_em if resp.observado_em is not None else (rec.lido_em or instante)
    if obs.tzinfo is None:
        raise _ObservadoInvalido("observado_em sem timezone")
    if obs > instante:
        raise _ObservadoInvalido("observado_em posterior à gravação (available_at)")
    return obs


def _concluir(leitura: _Leitura, sink, modo: str, relogio: Callable[[], datetime]) -> ReciboRun:
    rec, ped = leitura.recibo, leitura.pedido
    if rec.status == "ja_concluido":
        return rec
    if leitura.resposta is None:
        rec.status = "dead_letter"
        rec.motivo_dead_letter = leitura.motivo_falha or "tentativas_esgotadas"
        if modo == "gravar":
            sink.dead_letter(ItemDeadLetter(ped, rec.chave_execucao, rec.motivo_dead_letter,
                                            rec.erros[-1] if rec.erros else rec.motivo_dead_letter, rec.tentativas,
                                            sink.agora()))
            sink.registrar_run(rec)
            sink.heartbeat(ped.coletor, "dead_letter")
        return rec
    instante = sink.agora() if modo == "gravar" else relogio()
    try:
        obs, payloads, rejeicoes = _normalizar(leitura, instante)
    except _ObservadoInvalido as e:
        rec.erros.append(f"contrato: {e}")
        leitura.resposta, leitura.motivo_falha = None, "observado_em_invalido"
        return _concluir(leitura, sink, modo, relogio)
    rec.linhas_lidas = len(leitura.resposta.linhas)
    rec.observacoes = len(obs)
    rec.payloads_distintos = len(payloads)
    rec.rejeicoes = len(rejeicoes)
    if modo == "dry_run":
        rec.status = "dry_run"
        return rec
    cont = sink.gravar(obs, payloads)
    rec.inseridas, rec.noop = cont["inserido"], cont["noop"]
    rec.confirmadas = cont.get("confirmado", 0)  # [thread A, D2']
    rec.gravado_em = instante
    for motivo in rejeicoes:
        sink.dead_letter(ItemDeadLetter(ped, rec.chave_execucao, f"linha_rejeitada:{motivo}", motivo, rec.tentativas,
                                        instante))
    rec.status = "concluido"
    sink.registrar_run(rec)
    sink.heartbeat(ped.coletor, "concluido")
    return rec


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _preparar(adaptador, sink, modo, relogio):
    verificar_trava(adaptador, sink, modo)
    destino = sink if modo == "gravar" else _SinkNulo()
    rel = sink.agora if modo == "gravar" else (relogio or _agora)
    return destino, rel


def run_coleta(
    pedido: PedidoLeitura,
    *,
    adaptador: Adaptador,
    transporte: TransporteLeitura,
    sink: Optional[SinkMemoria] = None,
    modo: str = "dry_run",
    politica: PoliticaRetry = PoliticaRetry(),
    relogio: Optional[Callable[[], datetime]] = None,
    dormir: Optional[Callable[[float], None]] = None,
) -> ReciboRun:
    """Contrato de execução de UMA coleta (um coletor × conta × janela × slot)."""
    destino, rel = _preparar(adaptador, sink, modo, relogio)
    if dormir is None:
        import time

        dormir = time.sleep
    leitura = _ler(pedido, adaptador, transporte, destino, modo, politica, rel, dormir)
    return _concluir(leitura, destino, modo, rel)


def _ordem(p: PedidoLeitura) -> tuple:
    return (p.slot, p.conta, p.coletor, p.janela_inicio, p.janela_fim)


def executar_lote(pedidos: list[PedidoLeitura], *, paralelismo: int = 1, adaptador: Adaptador,
                  transporte: TransporteLeitura, sink: Optional[SinkMemoria] = None, modo: str = "dry_run",
                  politica: PoliticaRetry = PoliticaRetry(), relogio: Optional[Callable[[], datetime]] = None,
                  dormir: Optional[Callable[[float], None]] = None) -> list[ReciboRun]:
    """Leitura serial ou paralela; gravação SEMPRE serial, na ordem (slot, conta, coletor).

    Devolve os recibos na ordem dos pedidos recebidos.
    """
    if paralelismo < 1:
        raise ValueError("paralelismo >= 1")
    destino, rel = _preparar(adaptador, sink, modo, relogio)
    if dormir is None:
        import time

        dormir = time.sleep
    ler = lambda p: _ler(p, adaptador, transporte, destino, modo, politica, rel, dormir)  # noqa: E731
    if paralelismo == 1:
        leituras = [ler(p) for p in pedidos]
    else:
        with ThreadPoolExecutor(max_workers=paralelismo, thread_name_prefix="lote") as ex:
            leituras = list(ex.map(ler, pedidos))
    recibos: dict[int, ReciboRun] = {}
    for i in sorted(range(len(pedidos)), key=lambda i: _ordem(pedidos[i])):
        recibos[i] = _concluir(leituras[i], destino, modo, rel)
    return [recibos[i] for i in range(len(pedidos))]
