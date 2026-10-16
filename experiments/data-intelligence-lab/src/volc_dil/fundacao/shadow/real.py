"""Adaptador para dado REAL — pronto, testado com fixtures no formato real, NÃO executado com dado real.

Entrada: linhas da junção de 02 §9 (v21 ⋈ lote ⋈ execução; JoinAds v2 ⋈ lote ⋈ execução), exportadas
read-only em JSONL (números lidos com `parse_float=Decimal`). Caminho:

    linhas → adaptar_google_ads_v21 / adaptar_joinads_v2 (thread A) → deduplicar → FluxoIndexado
           → cortes → snapshot → políticas → kernel → ledger

Deduplicação: pelo `Registro` D2' da thread A, nunca por run (`deduplicar`). O v21 regrava a janela a cada
execução (UNIQUE `(run_id, observation_key)`); a re-execução do mesmo slot e as leituras D0 que repetem a
anterior (~80%, recibo (a)) viram CONFIRMAÇÕES, não versões; A→B→A e o fechamento da janela viram versões;
uma leitura antiga chegando atrasada não passa à frente de uma releitura mais nova (D1, R2-G2). Leituras
diferentes empatadas no topo seguem para o fluxo e o fato sai do snapshot (quarentena, R2-G11).

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
from volc_dil.contracts.snapshot import VersaoAmbigua

from ..observacao.modelo import Observacao
from ..observacao.registro import ConflitoIdempotencia, Registro
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
    """Deduplicação = o `Registro` D2' da thread A (R2-G2). Nenhuma regra própria: a dedup "manter a primeira,
    descartar quem repete a anterior" quebrava a ordem de versão D1 — descartava a releitura idêntica MAIS NOVA e
    deixava uma leitura antiga, chegando atrasada, vencer. O `Registro` guarda versões; releitura redundante vira
    confirmação e é materializada como versão quando uma leitura antiga atrasada tentaria passar à frente dela, de
    modo que `as_of` sobre as versões = `as_of` da A sobre todas as leituras, em qualquer corte e ordem de chegada.

    Devolve (versões, nº de leituras que não viraram versão, quarentena). Leituras diferentes empatadas no topo
    (`VersaoAmbigua`) ficam AMBAS no fluxo: o `FluxoIndexado` em quarentena tira o fato do snapshot e bloqueia a
    entidade (não escolhe). Mesma leitura com conteúdo diferente (`ConflitoIdempotencia`) vai só para a quarentena.
    """
    brutas = sorted(observacoes, key=lambda o: (o.available_at, o.chave_natural, o.chave_base))
    reg = Registro()
    ambiguas: list[Observacao] = []
    quarentena: list[tuple[str, str]] = []
    for o in brutas:
        try:
            reg.registrar(o)
        except VersaoAmbigua as e:
            ambiguas.append(o)
            quarentena.append((o.chave_natural, f"versao_ambigua: {e}"))
        except ConflitoIdempotencia as e:
            quarentena.append((o.chave_natural, f"conflito_idempotencia: {e}"))
    versoes = list(reg.observacoes) + ambiguas
    return versoes, len(brutas) - len(versoes), quarentena


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

