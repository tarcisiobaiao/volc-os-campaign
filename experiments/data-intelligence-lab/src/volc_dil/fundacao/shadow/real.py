"""Adaptador para dado REAL — pronto, testado com fixtures no formato real, NÃO executado com dado real.

Entrada: linhas da junção de 02 §9 (v21 ⋈ lote ⋈ execução; JoinAds v2 ⋈ lote ⋈ execução), exportadas
read-only em JSONL (números lidos com `parse_float=Decimal`). Caminho:

    linhas → adaptar_google_ads_v21 / adaptar_joinads_v2 (thread A) → deduplicar → FluxoIndexado
           → cortes → snapshot → políticas → kernel → ledger

Deduplicação: por CHAVE NATURAL + CONTEÚDO, nunca por run. O v21 regrava a janela a cada execução
(UNIQUE `(run_id, observation_key)`), então a re-execução do mesmo slot e as leituras D0 que repetem
a anterior (~80% medido, recibo (a)) geram observações com o mesmo fato e o mesmo conteúdo; fica a
PRIMEIRA (o conhecimento é datado da primeira leitura). Uma volta A→B→A é preservada (o conteúdo
mudou entre as leituras). Duas leituras diferentes do mesmo fato no mesmo `available_at` vão para
a quarentena (`versao_ambigua`) em vez de derrubar o replay.

Runs presos em `running` (recibo L9) não mudam o status das observações (02 §9.3): as linhas
existem e foram conhecidas. Viram diagnóstico.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence

from ..observacao import AdaptacaoImpossivel, ObservacaoInvalida, adaptar_google_ads_v21, adaptar_joinads_v2
from ..observacao.modelo import Observacao
from .fluxo import FluxoIndexado, cortes_regulares
from .ledger import LedgerShadow, SinkJsonl
from .motor import ConfigShadow, ResultadoReplay, executar_replay


@dataclass(frozen=True)
class ResultadoAdaptacao:
    observacoes: tuple[Observacao, ...]
    n_linhas_v21: int
    n_linhas_joinads: int
    n_observacoes_brutas: int
    repeticoes_descartadas: int
    quarentena: tuple[tuple[str, str], ...]  # (chave_natural, motivo)
    dead_letter: tuple[tuple[str, int, str], ...]  # (origem, índice da linha, motivo)
    runs_presos: tuple[str, ...]

    @property
    def fracao_repeticao(self) -> Optional[str]:
        if not self.n_observacoes_brutas:
            return None
        return f"{self.repeticoes_descartadas}/{self.n_observacoes_brutas}"

    def resumo(self) -> dict:
        return {"n_linhas_v21": self.n_linhas_v21, "n_linhas_joinads": self.n_linhas_joinads,
                "n_observacoes_brutas": self.n_observacoes_brutas, "n_observacoes": len(self.observacoes),
                "repeticoes_descartadas": self.repeticoes_descartadas, "fracao_repeticao": self.fracao_repeticao,
                "quarentena": [list(q) for q in self.quarentena], "dead_letter": [list(d) for d in self.dead_letter],
                "runs_presos": list(self.runs_presos)}


def deduplicar(observacoes: Iterable[Observacao]) -> tuple[list[Observacao], int, list[tuple[str, str]]]:
    """Por chave natural, em ordem de `available_at`, descarta a versão que repete a anterior mantida:
    mesmo payload (`chave_base`: a mesma leitura relida por outro run; no D0 só a cobertura derivada de
    `collected_at` muda) ou mesmo conteúdo (payload de lote diferente, valores iguais). A→B→A fica."""
    por_nat: dict[str, list[Observacao]] = {}
    for o in observacoes:
        por_nat.setdefault(o.chave_natural, []).append(o)
    mantidas: list[Observacao] = []
    descartadas = 0
    quarentena: list[tuple[str, str]] = []
    for nat, vs in sorted(por_nat.items()):
        vs.sort(key=lambda o: (o.available_at, o.chave_base))
        ultima: Optional[Observacao] = None
        i = 0
        while i < len(vs):
            grupo = [v for v in vs[i:] if v.available_at == vs[i].available_at]
            i += len(grupo)
            conteudos = {g.conteudo for g in grupo}
            if len(conteudos) > 1:
                quarentena.append((nat, f"versao_ambigua:{len(grupo)} leituras com conteúdos diferentes no mesmo available_at"))
                descartadas += len(grupo)
                continue
            o = grupo[0]
            descartadas += len(grupo) - 1
            # repetição = mesmo payload (mesma leitura relida; só o relógio/cobertura mudou) OU mesmo conteúdo
            if ultima is not None and (ultima.chave_base == o.chave_base or ultima.conteudo == o.conteudo):
                descartadas += 1
                continue
            mantidas.append(o)
            ultima = o
    return mantidas, descartadas, quarentena


def observacoes_de_linhas_reais(linhas_v21: Sequence[Mapping], linhas_joinads: Sequence[Mapping]) -> ResultadoAdaptacao:
    brutas: list[Observacao] = []
    dead: list[tuple[str, int, str]] = []
    presos: set[str] = set()
    for origem, linhas, adaptar in (("v21", linhas_v21, adaptar_google_ads_v21), ("joinads_v2", linhas_joinads, adaptar_joinads_v2)):
        for i, linha in enumerate(linhas):
            if origem == "v21" and linha.get("run_status") == "running":
                presos.add(str(linha.get("run_id")))
            try:
                brutas.extend(adaptar(linha))
            except (AdaptacaoImpossivel, ObservacaoInvalida, KeyError) as e:
                dead.append((origem, i, f"{type(e).__name__}: {e}"))
    mantidas, descartadas, quarentena = deduplicar(brutas)
    return ResultadoAdaptacao(tuple(mantidas), len(linhas_v21), len(linhas_joinads), len(brutas), descartadas,
                              tuple(quarentena), tuple(dead), tuple(sorted(presos)))


def carregar_jsonl(caminho: os.PathLike | str) -> list[dict]:
    """Lê a exportação read-only (uma linha JSON por registro). Float vira Decimal, nunca float."""
    saida = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                saida.append(json.loads(linha, parse_float=Decimal))
    return saida


def cortes_do_fluxo(fluxo: FluxoIndexado, passo: timedelta = timedelta(hours=1)) -> tuple[datetime, ...]:
    ini, fim = fluxo.primeiro_available_at(), fluxo.ultimo_available_at()
    if ini is None or fim is None:
        return ()
    ini = ini.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return cortes_regulares(ini, fim + passo, passo)


def replay_de_linhas_reais(linhas_v21: Sequence[Mapping], linhas_joinads: Sequence[Mapping], *, politicas: Sequence,
                           config: ConfigShadow = ConfigShadow(), passo: timedelta = timedelta(hours=1),
                           diretorio_ledger: Optional[os.PathLike | str] = None, seed: Optional[int] = None,
                           paralelismo: int = 1) -> tuple[ResultadoAdaptacao, ResultadoReplay, LedgerShadow]:
    """Linhas reais → replay as_of horário em shadow. Só lê as linhas dadas; só escreve o ledger no diretório dado."""
    adapt = observacoes_de_linhas_reais(linhas_v21, linhas_joinads)
    fluxo = FluxoIndexado(adapt.observacoes)
    ledger = LedgerShadow(SinkJsonl(diretorio_ledger) if diretorio_ledger is not None else None)
    res = executar_replay(fluxo, cortes_do_fluxo(fluxo, passo), politicas, config=config, seed=seed, ledger=ledger,
                          paralelismo=paralelismo)
    return adapt, res, ledger

