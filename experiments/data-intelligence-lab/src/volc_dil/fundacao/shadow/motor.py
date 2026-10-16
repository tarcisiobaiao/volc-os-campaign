"""Motor do replay `as_of` em shadow: fluxo → corte T → snapshot → política → kernel → ledger.

Fluxo de controle por corte T (sempre o mesmo, serial ou paralelo):

1. `construir_snapshot(fluxo_indexado, T)` — só o que tinha `available_at <= T`;
2. integridade do snapshot conferida ANTES e DEPOIS da política (ela não consegue alterá-lo);
3. `politica.decidir(snapshot)` — a política recebe só o snapshot (isolamento por tipo);
4. `aplicar_kernel` — valida que cada proposta pertence ao corte e anota bloqueios;
5. o ledger recebe as decisões em ordem (T, ordem das políticas). Paralelismo só distribui
   cortes; a ordem de gravação é sempre a mesma, então os bytes são iguais aos do serial.

Não há porta de escrita externa: o motor não importa cliente HTTP, banco, subprocess nem
`mutate`; o único efeito colateral possível é o `SinkJsonl` do ledger, num diretório dado.
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Iterable, Optional, Sequence

from volc_dil.contracts.fingerprint import json_canonico, sha256_de
from volc_dil.contracts.money import Dinheiro
from volc_dil.contracts.vocab import COM_VALOR, EstadoMedida

from ..identidade import Medida
from ..observacao.modelo import Observacao
from .fluxo import FluxoIndexado
from .kernel import ConfigKernel, aplicar_kernel
from .ledger import LedgerShadow
from .politicas import PoliticaShadow, exigir_snapshot
from .snapshot import ConfigCorte, FatoCampanhaDia, SnapshotShadow, construir_snapshot
from .tipos import DecisaoShadow


@dataclass(frozen=True)
class ConfigShadow:
    corte: ConfigCorte = field(default_factory=ConfigCorte)
    kernel: ConfigKernel = field(default_factory=ConfigKernel)

    def para_json(self) -> dict:
        return {"corte": self.corte.para_json(), "kernel": self.kernel.para_json()}


@dataclass(frozen=True)
class DecisaoNoCorte:
    as_of: str
    fingerprint_corte: str
    versao_codigo: str
    politica: str
    versao_politica: str
    decisao: DecisaoShadow

    def para_json(self) -> dict:
        return {"as_of": self.as_of, "fingerprint_corte": self.fingerprint_corte, "versao_codigo": self.versao_codigo,
                "politica": self.politica, "versao_politica": self.versao_politica, **self.decisao.para_json()}


@dataclass(frozen=True)
class ResultadoReplay:
    decisoes: tuple[DecisaoNoCorte, ...]
    cortes: tuple[tuple[str, str, int], ...]  # (as_of, fingerprint, n_visiveis)
    politicas: tuple[str, ...]
    seed: Optional[int]
    tempo_total_s: float = 0.0  # NÃO determinístico; fora de `bytes_canonicos`
    tempo_por_corte_s: tuple[float, ...] = ()

    def bytes_canonicos(self) -> bytes:
        return "".join(json_canonico(d.para_json()) + "\n" for d in self.decisoes).encode("utf-8")

    def sha256(self) -> str:
        import hashlib

        return hashlib.sha256(self.bytes_canonicos()).hexdigest()

    def da_politica(self, nome: str) -> list[DecisaoNoCorte]:
        return [d for d in self.decisoes if d.politica == nome]


def decidir_no_corte(snap: SnapshotShadow, politica: PoliticaShadow, cfg_kernel: ConfigKernel = ConfigKernel()) -> DecisaoShadow:
    exigir_snapshot(snap)
    snap.verificar_integridade()
    dec = politica.decidir(snap)
    if not isinstance(dec, DecisaoShadow):
        raise TypeError(f"{politica.nome} devolveu {type(dec).__name__}, não DecisaoShadow")
    snap.verificar_integridade()
    return aplicar_kernel(snap, politica.nome, dec, cfg_kernel)


def _um_corte(fluxo: FluxoIndexado, t: datetime, politicas: Sequence[PoliticaShadow], cfg: ConfigShadow):
    inicio = time.perf_counter()
    snap = construir_snapshot(fluxo, t, cfg.corte)
    saida = []
    for p in politicas:
        dec = decidir_no_corte(snap, p, cfg.kernel)
        saida.append(DecisaoNoCorte(snap.as_of_iso, snap.fingerprint, snap.versao_codigo, p.nome, p.versao, dec))
    return (snap.as_of_iso, snap.fingerprint, snap.n_visiveis), saida, time.perf_counter() - inicio


_ESTADO_TRABALHADOR: dict = {}


def _iniciar_trabalhador(observacoes, ambiguidade, politicas, cfg) -> None:
    _ESTADO_TRABALHADOR["fluxo"] = FluxoIndexado(observacoes, ambiguidade=ambiguidade)
    _ESTADO_TRABALHADOR["politicas"] = politicas
    _ESTADO_TRABALHADOR["cfg"] = cfg


def _lote_trabalhador(indices_cortes):
    e = _ESTADO_TRABALHADOR
    return [(i, *_um_corte(e["fluxo"], t, e["politicas"], e["cfg"])) for i, t in indices_cortes]


def executar_replay(fluxo: Iterable[Observacao] | FluxoIndexado, cortes: Sequence[datetime],
                    politicas: Sequence[PoliticaShadow], *, config: ConfigShadow = ConfigShadow(),
                    seed: Optional[int] = None, ledger: Optional[LedgerShadow] = None, paralelismo: int = 1,
                    executor: str = "processo") -> ResultadoReplay:
    nomes = [p.nome for p in politicas]
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"nomes de política repetidos: {nomes}")
    fi = fluxo if isinstance(fluxo, FluxoIndexado) else FluxoIndexado(fluxo, ambiguidade="quarentena")
    cortes = tuple(sorted(cortes))
    inicio = time.perf_counter()
    resultados: list = []
    if paralelismo <= 1:
        resultados = [(i, *_um_corte(fi, t, politicas, config)) for i, t in enumerate(cortes)]
    else:
        lotes = [list(enumerate(cortes))[k::paralelismo] for k in range(paralelismo)]
        if executor == "processo":
            with ProcessPoolExecutor(max_workers=paralelismo, initializer=_iniciar_trabalhador,
                                     initargs=(fi.observacoes + tuple(i.obs for i in fi.quarentena), fi.ambiguidade,
                                               tuple(politicas), config)) as ex:
                for parte in ex.map(_lote_trabalhador, lotes):
                    resultados.extend(parte)
        elif executor == "thread":
            with ThreadPoolExecutor(max_workers=paralelismo) as ex:
                for parte in ex.map(lambda lote: [(i, *_um_corte(fi, t, politicas, config)) for i, t in lote], lotes):
                    resultados.extend(parte)
        else:
            raise ValueError(f"executor desconhecido: {executor!r}")
    resultados.sort(key=lambda r: r[0])
    decisoes: list[DecisaoNoCorte] = []
    meta, tempos = [], []
    for _, m, decs, dt in resultados:
        meta.append(m)
        tempos.append(dt)
        decisoes.extend(decs)
    if ledger is not None:
        for d in decisoes:
            ledger.registrar_decisao(as_of=d.as_of, fingerprint_corte=d.fingerprint_corte, versao_codigo=d.versao_codigo,
                                     politica=d.politica, versao_politica=d.versao_politica, seed=seed,
                                     decisao=d.decisao.para_json())
    return ResultadoReplay(tuple(decisoes), tuple(meta), tuple(nomes), seed, time.perf_counter() - inicio, tuple(tempos))


# --------------------------------------------------------------------------- contraprova de futuro
def detectar_vazamento(fluxo: Sequence[Observacao], injecao: Sequence[Observacao], politicas: Sequence[PoliticaShadow],
                       cortes: Sequence[datetime], *, config: ConfigShadow = ConfigShadow(),
                       politicas_injetadas: Optional[Sequence[PoliticaShadow]] = None) -> dict:
    """Replay do fluxo e do fluxo + `injecao` (observações com `available_at` > alguns cortes).

    Para cada política: cortes ANTES do 1º `available_at` injetado em que a decisão mudou (só uma
    política que lê fora do snapshot muda aí → vazamento) e cortes DEPOIS em que mudou (prova de
    que a injeção é material). `politicas_injetadas` permite que um controle trapaceiro capture o
    fluxo injetado (como faria um código que contorna o isolamento).
    """
    limite = min(o.available_at for o in injecao)
    base = executar_replay(fluxo, cortes, politicas, config=config)
    inj = executar_replay(tuple(fluxo) + tuple(injecao), cortes, politicas_injetadas or politicas, config=config)
    saida: dict = {}
    for a, b in zip(base.decisoes, inj.decisoes):
        assert a.as_of == b.as_of and a.politica == b.politica
        r = saida.setdefault(a.politica, {"antes": [], "depois": [], "cortes_antes": 0, "cortes_depois": 0})
        antes = datetime.fromisoformat(a.as_of.replace("Z", "+00:00")) < limite
        r["cortes_antes" if antes else "cortes_depois"] += 1
        if json_canonico(a.decisao.para_json()) != json_canonico(b.decisao.para_json()):
            r["antes" if antes else "depois"].append(a.as_of)
    for r in saida.values():
        r["vazou"] = bool(r["antes"])
    return saida


# --------------------------------------------------------------------------- auditoria null × zero
def _moeda_de(snap: SnapshotShadow, f: FatoCampanhaDia, campo: str) -> str:
    for g in snap.fatos_de(f.entidade):
        v = getattr(g, campo).valor
        if isinstance(v, Dinheiro):
            return v.moeda
    return "BRL"


def snapshot_null_vira_zero(snap: SnapshotShadow) -> SnapshotShadow:
    """Troca toda medida SEM valor por zero confirmado (custo e receita), mantendo idade e versões."""
    novos = []
    for f in snap.fatos:
        g = f
        if f.custo.estado not in COM_VALOR:
            g = replace(g, custo=Medida(EstadoMedida.ZERO_CONFIRMADO, Dinheiro(0, _moeda_de(snap, f, "custo"))),
                        custo_status="zero_confirmed", custo_motivo=None)
        if f.receita.estado not in COM_VALOR:
            g = replace(g, receita=Medida(EstadoMedida.ZERO_CONFIRMADO, Dinheiro(0, _moeda_de(snap, f, "receita"))),
                        receita_status="zero_confirmed", receita_motivo=None)
        novos.append(g)
    return snap.com_fatos(novos, "auditoria_null_zero")


def snapshot_receita_perturbada(snap: SnapshotShadow, entidade) -> SnapshotShadow:
    novos = []
    for f in snap.fatos:
        if f.entidade == entidade and isinstance(f.receita.valor, Dinheiro):
            v = f.receita.valor
            f = replace(f, receita=Medida(EstadoMedida.MEDIDO, Dinheiro(v.micros * 3 + 1_000_000, v.moeda)),
                        receita_status="observed")
        novos.append(f)
    return snap.com_fatos(novos, "auditoria_sensibilidade")


def auditar_null_zero(politica: PoliticaShadow, snapshots: Iterable[SnapshotShadow]) -> dict:
    """Metamórfica: política correta muda a decisão quando ausência vira zero confirmado."""
    n_lacuna = n_distingue = n_sensivel = 0
    for s in snapshots:
        if all(f.custo.estado in COM_VALOR and f.receita.estado in COM_VALOR for f in s.fatos):
            continue
        n_lacuna += 1
        a = politica.decidir(s).assinatura()
        b = politica.decidir(snapshot_null_vira_zero(s)).assinatura()
        n_distingue += a != b
        for e in s.campanhas:
            if politica.decidir(snapshot_receita_perturbada(s, e)).assinatura() != a:
                n_sensivel += 1
                break
    cega = n_lacuna > 0 and n_sensivel == 0
    return {"politica": politica.nome, "snapshots_com_lacuna": n_lacuna, "decisoes_que_distinguem_null_de_zero": n_distingue,
            "decisoes_sensiveis_a_valores": n_sensivel, "cega_a_dados": cega,
            "suspeita_null_como_zero": n_lacuna > 0 and n_distingue == 0 and not cega}


def fingerprint_execucao(resultado: ResultadoReplay, config: ConfigShadow) -> str:
    return sha256_de({"decisoes_sha256": resultado.sha256(), "config": config.para_json(), "seed": resultado.seed})
