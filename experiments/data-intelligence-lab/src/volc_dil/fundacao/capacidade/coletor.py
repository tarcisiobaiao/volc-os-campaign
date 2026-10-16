"""Esqueleto de "coletor seguro": contrato `run_coleta` + executor com timeout, retry, idempotência,
heartbeat, recibo de run e dead letter.

TRAVA (explícita e testada):
- este módulo NÃO contém implementação de escrita externa — nenhum cliente HTTP, nenhum
  `mutate`, nenhum Supabase/Postgres. A fonte é um adaptador INJETADO que precisa declarar
  ``somente_leitura = True`` e não pode expor métodos de escrita (`mutate`, `escrever`, `post`…);
- o destino é um sink INJETADO que precisa declarar ``externo = False``; os únicos sinks daqui
  são em memória;
- o modo padrão é ``dry_run``: lê, normaliza, calcula hashes e contagens, e não grava nada.

Semântica:
- chave de execução determinística = sha256(coletor, conta, janela, slot da agenda). Repetir o
  mesmo slot é no-op (`ja_concluido`); retry dentro do run nunca duplica observação;
- observação idempotente por (chave lógica, métrica, sha256 do valor): reler valor igual não
  cria linha; valor diferente cria NOVA versão (append-only), nunca sobrescreve;
- ausência ≠ zero: métrica sem valor na resposta vira estado ``nao_informado`` com valor None;
- erro transitório (timeout, 429, 5xx) → retry com backoff exponencial e jitter determinístico;
  erro permanente ou desconhecido → dead letter imediata (não martela a API); transitório que
  esgota tentativas → dead letter com motivo ``tentativas_esgotadas``;
- resposta atrasada de uma tentativa que estourou o timeout é descartada (nunca consumida).
"""
from __future__ import annotations

import hashlib
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable

MODOS = ("dry_run", "gravar")
NOMES_DE_ESCRITA_PROIBIDOS = ("mutate", "escrever", "write", "post", "put", "patch", "delete", "apagar",
                              "atualizar", "update", "insert", "upsert", "publicar", "ativar")


class TravaViolada(RuntimeError):
    """Tentativa de usar adaptador com escrita, sink externo ou modo desconhecido."""


class ErroTransitorio(Exception):
    """Falha que pode passar sozinha: timeout, 429, 5xx, conexão interrompida."""


class ErroPermanente(Exception):
    """Falha que não passa com retry: 400, credencial, contrato/schema, permissão."""


@dataclass(frozen=True)
class PedidoLeitura:
    coletor: str
    conta: str
    janela_inicio: str  # ISO date
    janela_fim: str
    slot: str  # instante agendado (ISO), não o instante real de execução

    def chave_execucao(self) -> str:
        return _sha256({"coletor": self.coletor, "conta": self.conta, "janela": [self.janela_inicio, self.janela_fim],
                        "slot": self.slot})


@dataclass(frozen=True)
class LinhaFonte:
    chave: tuple[str, ...]  # identidade estrita: (conta, nível, entidade, segmento, dia)
    valores: dict[str, int | None]  # micros/contagens; None = não informado (≠ 0)


@dataclass(frozen=True)
class RespostaLeitura:
    linhas: tuple[LinhaFonte, ...]
    versao_contrato: str = "v0"


@runtime_checkable
class AdaptadorFonte(Protocol):
    nome: str
    somente_leitura: bool

    def ler(self, pedido: PedidoLeitura) -> RespostaLeitura: ...


@runtime_checkable
class Sink(Protocol):
    externo: bool

    def run_concluido(self, chave_execucao: str) -> bool: ...
    def registrar_run(self, recibo: "ReciboRun") -> None: ...
    def heartbeat(self, coletor: str, instante: datetime, estado: str) -> None: ...
    def gravar(self, chave_execucao: str, observacoes: list["ObservacaoColetada"],
               payloads: dict[str, str]) -> tuple[int, int]: ...
    def dead_letter(self, item: "ItemDeadLetter") -> None: ...


@dataclass(frozen=True)
class ObservacaoColetada:
    fonte: str
    chave: tuple[str, ...]
    metrica: str
    valor: int | None
    estado: str  # "medido" | "nao_informado"
    disponivel_em: datetime  # instante em que a coleta passou a conhecer o valor
    chave_execucao: str
    payload_sha256: str

    def chave_idempotencia(self) -> str:
        return _sha256({"f": self.fonte, "k": list(self.chave), "m": self.metrica, "v": self.valor, "e": self.estado})


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
    gravadas_novas: int = 0
    repetidas: int = 0
    payloads_distintos: int = 0
    iniciado_em: datetime | None = None
    finalizado_em: datetime | None = None
    erros: list[str] = field(default_factory=list)


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


def verificar_trava(adaptador: object, sink: object, modo: str) -> None:
    if modo not in MODOS:
        raise TravaViolada(f"modo desconhecido {modo!r}; permitidos: {MODOS}")
    if getattr(adaptador, "somente_leitura", None) is not True:
        raise TravaViolada("adaptador precisa declarar somente_leitura = True")
    for nome in dir(adaptador):
        baixo = nome.lower()
        if any(baixo == p or baixo.startswith(p + "_") or baixo.endswith("_" + p) for p in NOMES_DE_ESCRITA_PROIBIDOS):
            if callable(getattr(adaptador, nome, None)):
                raise TravaViolada(f"adaptador expõe método de escrita {nome!r}")
    if getattr(sink, "externo", None) is not False:
        raise TravaViolada("sink precisa declarar externo = False (não há sink externo neste módulo)")


class SinkMemoria:
    """Sink em memória, thread-safe. Observação idempotente; payload deduplicado por sha256 da linha."""

    externo = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.observacoes: dict[str, ObservacaoColetada] = {}
        self.payloads: dict[str, str] = {}
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

    def heartbeat(self, coletor: str, instante: datetime, estado: str) -> None:
        with self._lock:
            self.heartbeats.append((coletor, instante, estado))

    def gravar(self, chave_execucao, observacoes, payloads):
        with self._lock:
            self.chamadas_gravar += 1
            novas = 0
            for o in observacoes:
                k = o.chave_idempotencia()
                if k not in self.observacoes:
                    self.observacoes[k] = o
                    novas += 1
            for h, p in payloads.items():
                self.payloads.setdefault(h, p)
            return novas, len(observacoes) - novas

    def dead_letter(self, item: ItemDeadLetter) -> None:
        with self._lock:
            self.dead_letters.append(item)

    def conjunto_final(self) -> frozenset:
        """Conteúdo de negócio (sem instantes nem chaves de execução) — para provar equivalência."""
        return frozenset((o.fonte, o.chave, o.metrica, o.valor, o.estado) for o in self.observacoes.values())


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def normalizar(fonte: str, resposta: RespostaLeitura, chave_execucao: str,
               disponivel_em: datetime) -> tuple[list[ObservacaoColetada], dict[str, str]]:
    obs: list[ObservacaoColetada] = []
    payloads: dict[str, str] = {}
    for linha in resposta.linhas:
        bruto = json.dumps({"chave": list(linha.chave), "valores": linha.valores}, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(bruto.encode()).hexdigest()
        payloads[h] = bruto
        for metrica in sorted(linha.valores):
            v = linha.valores[metrica]
            if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
                raise ErroPermanente(f"valor não inteiro em {metrica}: {v!r} (use micros)")
            obs.append(ObservacaoColetada(fonte=fonte, chave=tuple(linha.chave), metrica=metrica, valor=v,
                                          estado="medido" if v is not None else "nao_informado",
                                          disponivel_em=disponivel_em, chave_execucao=chave_execucao,
                                          payload_sha256=h))
    return obs, payloads


def run_coleta(
    pedido: PedidoLeitura,
    *,
    adaptador: AdaptadorFonte,
    sink: Sink,
    modo: str = "dry_run",
    politica: PoliticaRetry = PoliticaRetry(),
    relogio: Callable[[], datetime] = _agora,
    dormir: Callable[[float], None] | None = None,
) -> ReciboRun:
    """Contrato de execução de UMA coleta (um coletor × conta × janela × slot)."""
    verificar_trava(adaptador, sink, modo)
    if dormir is None:
        import time

        dormir = time.sleep
    chave = pedido.chave_execucao()
    inicio = relogio()
    recibo = ReciboRun(chave_execucao=chave, pedido=pedido, modo=modo, status="em_andamento", tentativas=0,
                       iniciado_em=inicio)
    if sink.run_concluido(chave):
        recibo.status = "ja_concluido"
        recibo.finalizado_em = relogio()
        sink.heartbeat(pedido.coletor, recibo.finalizado_em, "ja_concluido")
        return recibo
    sink.heartbeat(pedido.coletor, inicio, "iniciado")
    rng = random.Random(f"{politica.seed}:{chave}")
    resposta: RespostaLeitura | None = None
    motivo_falha = None
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"coleta-{pedido.coletor}")
    try:
        for tentativa in range(1, politica.max_tentativas + 1):
            recibo.tentativas = tentativa
            futuro = executor.submit(adaptador.ler, pedido)
            try:
                resposta = futuro.result(timeout=politica.timeout_s)
                break
            except FuturoTimeout:
                futuro.cancel()  # se ainda rodar, o resultado tardio nunca é consumido
                recibo.erros.append(f"t{tentativa}: timeout>{politica.timeout_s}s")
                motivo_falha = "tentativas_esgotadas"
                # executor novo: a thread presa não bloqueia a próxima tentativa
                executor.shutdown(wait=False, cancel_futures=True)
                executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"coleta-{pedido.coletor}")
            except ErroTransitorio as e:
                recibo.erros.append(f"t{tentativa}: transitorio: {e}")
                motivo_falha = "tentativas_esgotadas"
            except ErroPermanente as e:
                recibo.erros.append(f"t{tentativa}: permanente: {e}")
                motivo_falha = "erro_permanente"
                break
            except Exception as e:  # desconhecido = permanente: não martelar a fonte
                recibo.erros.append(f"t{tentativa}: desconhecido: {type(e).__name__}: {e}")
                motivo_falha = "erro_desconhecido"
                break
            sink.heartbeat(pedido.coletor, relogio(), f"retry_{tentativa}")
            if tentativa < politica.max_tentativas:
                dormir(politica.espera(tentativa, rng))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if resposta is None:
        return _para_dead_letter(recibo, sink, pedido, motivo_falha or "tentativas_esgotadas", relogio)

    try:
        observacoes, payloads = normalizar(adaptador.nome, resposta, chave, disponivel_em=relogio())
    except ErroPermanente as e:
        recibo.erros.append(f"normalizacao: {e}")
        return _para_dead_letter(recibo, sink, pedido, "contrato_invalido", relogio)
    recibo.linhas_lidas = len(resposta.linhas)
    recibo.observacoes = len(observacoes)
    recibo.payloads_distintos = len(payloads)
    if modo == "dry_run":
        recibo.status = "dry_run"
    else:
        recibo.gravadas_novas, recibo.repetidas = sink.gravar(chave, observacoes, payloads)
        recibo.status = "concluido"
    recibo.finalizado_em = relogio()
    if modo == "gravar":
        sink.registrar_run(recibo)
    sink.heartbeat(pedido.coletor, recibo.finalizado_em, recibo.status)
    return recibo


def _para_dead_letter(recibo, sink, pedido, motivo, relogio) -> ReciboRun:
    recibo.status = "dead_letter"
    recibo.finalizado_em = relogio()
    sink.dead_letter(ItemDeadLetter(pedido=pedido, chave_execucao=recibo.chave_execucao, motivo=motivo,
                                    erro=recibo.erros[-1] if recibo.erros else motivo, tentativas=recibo.tentativas,
                                    instante=recibo.finalizado_em))
    sink.registrar_run(recibo)
    sink.heartbeat(pedido.coletor, recibo.finalizado_em, "dead_letter")
    return recibo


def executar_lote(pedidos: list[PedidoLeitura], *, paralelismo: int = 1, **kwargs) -> list[ReciboRun]:
    """Executa vários pedidos (serial ou em paralelo). Resultado na ordem dos pedidos."""
    if paralelismo < 1:
        raise ValueError("paralelismo >= 1")
    if paralelismo == 1:
        return [run_coleta(p, **kwargs) for p in pedidos]
    with ThreadPoolExecutor(max_workers=paralelismo, thread_name_prefix="lote") as ex:
        return list(ex.map(lambda p: run_coleta(p, **kwargs), pedidos))
