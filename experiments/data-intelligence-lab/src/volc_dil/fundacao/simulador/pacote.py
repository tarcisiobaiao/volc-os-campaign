"""Pacote de datasets por cenário para os workers D (replay/shadow), F (Model Lab) e G (observabilidade).

Layout (determinístico; mesma seed e versões ⇒ mesmos bytes)::

    <destino>/MANIFEST.json                 seed, versões, sha256 do código, do catálogo e de cada arquivo
    <destino>/<cenario>/cenario.json        parâmetros completos + o que exercita + armadilhas
    <destino>/<cenario>/observacoes.jsonl   ENTRADA de consumidor: registros em ordem de available_at
    <destino>/<cenario>/gabarito.jsonl      AVALIAÇÃO: verdade por obs_id (nunca entrada)
    <destino>/<cenario>/execucoes.jsonl     livro de runs de coleta (completed/failed/running)
    <destino>/<cenario>/verdade_diaria.csv  AVALIAÇÃO: campanha × dia
    <destino>/<cenario>/verdade_horaria.csv AVALIAÇÃO: campanha × hora (somado nos dispositivos)
    <destino>/<cenario>/verdade_campanhas.csv AVALIAÇÃO: atributos latentes
    <destino>/<cenario>/resumo.json         contagens por status/armadilha/fonte e forma medida

Tempos de execução NÃO entram no manifesto (não são determinísticos); vão para
``PERFORMANCE.json``, escrito à parte pelo script.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Iterable, Optional

from volc_dil.contracts.fingerprint import json_canonico, sha256_codigo, sha256_de, versoes

from . import cenarios as _cen
from .calibracao import medir_forma

# Tamanhos do pacote (o catálogo é 50×30; o pacote é reduzido para caber em poucos MB).
TAMANHO_PACOTE = (4, 7)
TAMANHO_PACOTE_ESCALA = (40, 3)


def _arquivos_codigo() -> list[str]:
    raiz = Path(__file__).resolve().parent
    return sorted(str(p) for p in raiz.glob("*.py"))


def _csv(linhas: list[dict]) -> bytes:
    if not linhas:
        return b""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(linhas[0].keys()), lineterminator="\n")
    w.writeheader()
    for linha in linhas:
        w.writerow({k: ("true" if v is True else "false" if v is False else v) for k, v in linha.items()})
    return buf.getvalue().encode("utf-8")


def _jsonl(objs: Iterable[dict]) -> bytes:
    return "".join(json_canonico(o) + "\n" for o in objs).encode("utf-8")


def tamanho_para(nome: str) -> tuple[int, int]:
    return TAMANHO_PACOTE_ESCALA if nome == "escala_10x" else TAMANHO_PACOTE


def conteudo_cenario(nome: str, seed: int, tamanho: Optional[tuple[int, int]] = None) -> dict[str, bytes]:
    """Bytes de cada arquivo de um cenário (sem tocar disco)."""
    from . import VERSAO_SIMULADOR, simular

    n_c, n_d = tamanho or tamanho_para(nome)
    sim = simular(nome, seed, n_campanhas=n_c, n_dias=n_d)
    regs, gab = sim.leituras.registros, sim.leituras.gabarito
    status: dict[str, int] = {}
    arm: dict[str, int] = {}
    por_fonte: dict[str, int] = {}
    for r in regs:
        status[r.status] = status.get(r.status, 0) + 1
        por_fonte[r.fonte] = por_fonte.get(r.fonte, 0) + 1
        for a in gab[r.obs_id].armadilhas:
            arm[a] = arm.get(a, 0) + 1
    e = sim.espec
    cen = {"nome": e.nome, "descricao": e.descricao, "exercita": list(e.exercita), "armadilhas": list(e.armadilhas),
           "adversarial": e.adversarial, "seed": seed, "tamanho_pacote": {"n_campanhas": n_c, "n_dias": n_d},
           "versao_simulador": VERSAO_SIMULADOR, "versao_catalogo": _cen.VERSAO_CATALOGO,
           "parametros": e.como_dict(), "natureza": "sintetico",
           "aviso": "simulação não é prova de eficácia operacional; gabarito e verdade são só para avaliação"}
    forma = {k: round(v, 6) for k, v in medir_forma(sim.mundo).items()}
    runs: dict[str, int] = {}
    for x in sim.leituras.execucoes:
        runs[x["status"]] = runs.get(x["status"], 0) + 1
    resumo = {"n_registros": len(regs), "execucoes_por_status": dict(sorted(runs.items())), "status": dict(sorted(status.items())), "armadilhas": dict(sorted(arm.items())),
              "por_fonte": dict(sorted(por_fonte.items())),
              "available_at_min": regs[0].available_at if regs else None,
              "available_at_max": regs[-1].available_at if regs else None,
              "forma_medida": forma}
    return {
        "cenario.json": (json_canonico(cen) + "\n").encode("utf-8"),
        "observacoes.jsonl": _jsonl(r.como_dict() for r in regs),
        "gabarito.jsonl": _jsonl(gab[r.obs_id].como_dict() for r in regs),
        "execucoes.jsonl": _jsonl(sim.leituras.execucoes),
        "verdade_diaria.csv": _csv(sim.mundo.tabela_diaria()),
        "verdade_horaria.csv": _csv(sim.mundo.tabela_horaria()),
        "verdade_campanhas.csv": _csv(sim.mundo.tabela_campanhas()),
        "resumo.json": (json_canonico(resumo) + "\n").encode("utf-8"),
    }


def gerar_pacote(destino: os.PathLike | str, seed: int, nomes: Optional[Iterable[str]] = None) -> dict:
    """Escreve o pacote e devolve o manifesto. Sobrescreve os arquivos dos cenários pedidos."""
    from . import VERSAO_SIMULADOR

    destino = Path(destino)
    nomes = list(nomes) if nomes is not None else list(_cen.NOMES)
    arquivos: dict[str, dict] = {}
    for nome in nomes:
        pasta = destino / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for arq, dados in conteudo_cenario(nome, seed).items():
            (pasta / arq).write_bytes(dados)
            arquivos[f"{nome}/{arq}"] = {"bytes": len(dados), "sha256": sha256_de_bytes(dados)}
    manifesto = {
        "natureza": "sintetico",
        "gerador": "experiments/data-intelligence-lab/scripts/fundacao_simulador_pacote.py",
        "seed": seed,
        "versao_simulador": VERSAO_SIMULADOR,
        "versao_catalogo": _cen.VERSAO_CATALOGO,
        "catalogo_sha256": _cen.catalogo_sha256(),
        "codigo_sha256": sha256_codigo(_arquivos_codigo()),
        "cenarios": nomes,
        "tamanhos": {n: list(tamanho_para(n)) for n in nomes},
        "arquivos": dict(sorted(arquivos.items())),
        "bytes_total": sum(a["bytes"] for a in arquivos.values()),
        "versoes": {k: v for k, v in versoes().items() if k != "plataforma"},
        "uso": {"entrada_consumidor": ["observacoes.jsonl", "execucoes.jsonl"], "so_avaliacao": ["gabarito.jsonl", "verdade_*.csv"]},
    }
    manifesto["fingerprint"] = sha256_de({k: v for k, v in manifesto.items() if k != "versoes"})
    (destino / "MANIFEST.json").write_bytes((json_canonico(manifesto) + "\n").encode("utf-8"))
    return manifesto


def sha256_de_bytes(dados: bytes) -> str:
    import hashlib

    return hashlib.sha256(dados).hexdigest()
