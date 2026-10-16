"""Checagens sobre execuções de coletor: frescor, completude por slot, runs órfãos, falha silenciosa.

Equivalentes SQL (mesma semântica, testada por equivalência):
`dq_freshness`, `dq_completude_hora`, `dq_runs_orfaos`, `dq_falha_silenciosa`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Mapping, Sequence

from .agenda import (
    JANELA_AVALIACAO,
    LIMIARES_PADRAO,
    SLA,
    SLA_PADRAO,
    TIMEOUT_RUNNING_PADRAO,
    primeiro_run_por_coletor,
)
from .modelo import SUCESSO, Achado, RunDQ, Severidade, StatusRun, iso

# --------------------------------------------------------------------------- frescor


@dataclass(frozen=True)
class EstadoFrescor:
    fonte: str
    coletor: str
    grao: str
    ultimo_sucesso: datetime | None
    slot_referencia: datetime | None
    slots_perdidos: int
    estado: str  # fresco | atrasado | parado | sem_registro
    severidade: str  # ok | aviso | alto | critico


def avaliar_frescor(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[EstadoFrescor]:
    """Um estado por SLA. Frescor = slots vencidos depois do último sucesso (completed|partial)."""
    runs = [r for r in runs if r.started_at <= agora]
    primeiro = primeiro_run_por_coletor(runs, agora)
    parado = int(limiares["frescor_slots_parado"])
    saida: list[EstadoFrescor] = []
    for coletor, sla in sorted(slas.items()):
        sucessos = [r.started_at for r in runs if r.coletor == coletor and r.status in SUCESSO]
        ultimo = max(sucessos) if sucessos else None
        vencidos = [s for s in sla.slots(agora, primeiro.get(coletor)) if s + sla.tolerancia <= agora]
        ref = max(vencidos) if vencidos else None
        perdidos = sum(1 for s in vencidos if ultimo is None or s > ultimo + sla.folga)
        if ultimo is None:
            estado, sev = "sem_registro", "critico"
        elif perdidos == 0:
            estado, sev = "fresco", "ok"
        elif perdidos < parado:
            estado, sev = "atrasado", "aviso"
        else:
            estado, sev = "parado", "alto"
        saida.append(EstadoFrescor(sla.fonte, coletor, sla.grao, ultimo, ref, perdidos, estado, sev))
    return saida


def checar_frescor(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    achados = []
    for e in avaliar_frescor(runs, agora, slas, limiares):
        if e.severidade == "ok":
            continue
        idade = None if e.ultimo_sucesso is None else int((agora - e.ultimo_sucesso).total_seconds())
        achados.append(
            Achado(
                regra=f"frescor_{e.estado}",
                severidade=Severidade(e.severidade),
                fonte=e.fonte,
                grao=e.grao,
                janela=(iso(e.ultimo_sucesso), iso(agora)),
                chave=e.coletor,
                evidencia={
                    "ultimo_sucesso": iso(e.ultimo_sucesso),
                    "slot_referencia": iso(e.slot_referencia),
                    "slots_perdidos": e.slots_perdidos,
                    "idade_s": idade,
                    "agenda": slas[e.coletor].cron,
                    "tolerancia_s": int(slas[e.coletor].tolerancia.total_seconds()),
                },
                mensagem=(
                    f"{e.coletor}: nenhum run bem-sucedido registrado"
                    if e.estado == "sem_registro"
                    else f"{e.coletor}: {e.slots_perdidos} slot(s) vencido(s) sem sucesso desde {iso(e.ultimo_sucesso)}"
                ),
            )
        )
    return achados


# --------------------------------------------------------------------------- completude por slot

_PRECEDENCIA = (
    (StatusRun.COMPLETED, "ok"),
    (StatusRun.PARTIAL, "parcial"),
    (StatusRun.RUNNING, "em_execucao"),
    (StatusRun.FAILED, "falha_declarada"),
)
SEVERIDADE_SLOT = {
    "ok": "ok",
    "pendente": "ok",
    "parcial": "info",
    "em_execucao": "info",
    "falha_declarada": "aviso",
    "ausente_silencioso": "aviso",
}


@dataclass(frozen=True)
class SlotCompletude:
    fonte: str
    coletor: str
    slot: datetime
    dia_local: date
    hora_local: int
    n_runs: int
    classe: str

    @property
    def severidade(self) -> str:
        return SEVERIDADE_SLOT[self.classe]


def avaliar_completude_slots(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
) -> list[SlotCompletude]:
    """Classifica cada slot esperado. `falha_declarada` (run registrou falha) ≠ `ausente_silencioso`
    (nenhum registro); slot cujo prazo ainda não venceu é `pendente`, não buraco."""
    runs = [r for r in runs if r.started_at <= agora]
    primeiro = primeiro_run_por_coletor(runs, agora)
    por_coletor: dict[str, list[RunDQ]] = defaultdict(list)
    for r in runs:
        por_coletor[r.coletor].append(r)
    saida: list[SlotCompletude] = []
    for coletor, sla in sorted(slas.items()):
        for s in sla.slots(agora, primeiro.get(coletor)):
            casados = [r for r in por_coletor[coletor] if s - sla.folga <= r.started_at < s + sla.tolerancia]
            status = {r.status for r in casados}
            classe = None
            for st, nome in _PRECEDENCIA:
                if st in status:
                    classe = nome
                    break
            if classe is None:
                classe = "ausente_silencioso" if s + sla.tolerancia <= agora else "pendente"
            dia, hora = sla.dia_hora_local(s)
            saida.append(SlotCompletude(sla.fonte, coletor, s, dia, hora, len(casados), classe))
    return saida


def checar_completude_slots(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
) -> list[Achado]:
    """Um achado por coletor × dia local com algum slot não-ok. ≥3 ausências silenciosas no dia = alto."""
    grupos: dict[tuple[str, date], list[SlotCompletude]] = defaultdict(list)
    for s in avaliar_completude_slots(runs, agora, slas):
        if s.classe not in ("ok", "pendente"):
            grupos[(s.coletor, s.dia_local)].append(s)
    achados = []
    for (coletor, dia), slots in sorted(grupos.items()):
        por_classe: dict[str, list[int]] = defaultdict(list)
        for s in slots:
            por_classe[s.classe].append(s.hora_local)
        n_aus = len(por_classe.get("ausente_silencioso", []))
        n_falha = len(por_classe.get("falha_declarada", []))
        if n_aus >= 3:
            sev = Severidade.ALTO
        elif n_aus or n_falha:
            sev = Severidade.AVISO
        else:
            sev = Severidade.INFO
        sla = slas[coletor]
        achados.append(
            Achado(
                regra="completude_slots",
                severidade=sev,
                fonte=sla.fonte,
                grao=sla.grao,
                janela=(dia.isoformat(), dia.isoformat()),
                chave=coletor,
                evidencia={k: sorted(v) for k, v in sorted(por_classe.items())},
                mensagem=(
                    f"{coletor} em {dia}: {n_aus} slot(s) sem nenhum registro, {n_falha} com falha declarada"
                ),
            )
        )
    return achados


# --------------------------------------------------------------------------- runs órfãos


@dataclass(frozen=True)
class RunOrfao:
    fonte: str
    coletor: str
    run_id: str
    started_at: datetime
    ultimo_sinal: datetime | None
    timeout_s: int
    idade_s: int


def avaliar_runs_orfaos(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
) -> list[RunOrfao]:
    """`running` além do timeout E sem sinal de vida dentro do timeout. Heartbeat recente salva o run."""
    saida = []
    for r in runs:
        if r.status is not StatusRun.RUNNING or r.started_at > agora:
            continue
        timeout = slas[r.coletor].timeout_running if r.coletor in slas else TIMEOUT_RUNNING_PADRAO
        sinal = r.ultimo_sinal or r.started_at
        if r.started_at < agora - timeout and sinal < agora - timeout:
            saida.append(
                RunOrfao(r.fonte, r.coletor, r.run_id, r.started_at, r.ultimo_sinal,
                         int(timeout.total_seconds()), int((agora - r.started_at).total_seconds()))
            )
    return sorted(saida, key=lambda o: (o.coletor, o.started_at, o.run_id))


def checar_runs_orfaos(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
) -> list[Achado]:
    achados = []
    for o in avaliar_runs_orfaos(runs, agora, slas):
        grao = slas[o.coletor].grao if o.coletor in slas else "run"
        achados.append(
            Achado(
                regra="run_orfao",
                severidade=Severidade.ALTO,
                fonte=o.fonte,
                grao=grao,
                janela=(iso(o.started_at), iso(agora)),
                chave=o.run_id,
                evidencia={
                    "coletor": o.coletor,
                    "started_at": iso(o.started_at),
                    "ultimo_sinal": iso(o.ultimo_sinal),
                    "idade_s": o.idade_s,
                    "timeout_s": o.timeout_s,
                },
                mensagem=f"run {o.run_id} de {o.coletor} em `running` há {o.idade_s // 60} min sem sinal de vida",
            )
        )
    return achados


# --------------------------------------------------------------------------- falha silenciosa


def checar_falha_silenciosa(
    runs: Iterable[RunDQ],
    agora: datetime,
    slas: Mapping[str, SLA] = SLA_PADRAO,
) -> list[Achado]:
    """Run concluído (completed|partial) com 0 linhas onde o contrato espera > 0.
    `linhas_escritas = None` é contagem desconhecida e NÃO dispara (null não é zero)."""
    achados = []
    for r in sorted(runs, key=lambda x: (x.coletor, x.started_at, x.run_id)):
        sla = slas.get(r.coletor)
        if sla is None or sla.min_linhas <= 0:
            continue
        if r.status not in SUCESSO or r.linhas_escritas is None or r.linhas_escritas != 0:
            continue
        if not (agora - JANELA_AVALIACAO < r.started_at <= agora):
            continue
        achados.append(
            Achado(
                regra="falha_silenciosa_run_vazio",
                severidade=Severidade.ALTO,
                fonte=r.fonte,
                grao=sla.grao,
                janela=(iso(r.started_at), iso(r.finished_at)),
                chave=r.run_id,
                evidencia={"coletor": r.coletor, "status": r.status.value, "linhas_escritas": 0,
                           "min_linhas": sla.min_linhas},
                mensagem=f"run {r.run_id} de {r.coletor} terminou `{r.status.value}` com 0 linhas",
            )
        )
    return achados


def linhas_por_coletor(runs: Sequence[RunDQ]) -> dict[str, int]:
    """Utilitário de resumo: quantos runs por coletor (para o recibo)."""
    contagem: dict[str, int] = defaultdict(int)
    for r in runs:
        contagem[r.coletor] += 1
    return dict(sorted(contagem.items()))
