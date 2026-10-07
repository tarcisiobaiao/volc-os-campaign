"""BENCHMARK DE MODELOS por funil inteiro — preparado, nunca disparado sozinho.

Compara CONFIGURAÇÕES completas (um modelo por passo) pelo que importa ao
negócio: custo total por funil, latência, retentativas, fallbacks, páginas
bloqueadas e o que a jornada e os portões disseram. Não compara resposta
isolada.

Três comandos, nenhum faz chamada paga:

    python -m funnelforge.benchmark pontuar runs/<id>/state.json [...]
        Pontua runs JÁ FEITOS (recibos salvos). Recalcula o custo pela tabela
        oficial datada (`benchmarks/precos-*.yaml`) ao lado do custo do ledger.
    python -m funnelforge.benchmark estimar <state.json de referência>
        Estima o custo de cada configuração da matriz reaproveitando o PERFIL
        de tokens e tentativas do run de referência.
    python -m funnelforge.benchmark preparar <pasta de saída>
        Escreve um config.yaml por configuração e imprime os comandos
        `funnelforge run-volc` para uma rodada real AUTORIZADA por uma pessoa.

Trocar de modelo continua sendo editar `config.yaml` (ou o perfil): este
módulo não guarda nome de modelo no código.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from funnelforge.domain.models import RunState, StepStatus

RAIZ = Path(__file__).resolve().parents[2]
PRECOS_PADRAO = sorted((RAIZ / "benchmarks").glob("precos-oficiais-*.yaml"))
MATRIZ_PADRAO = RAIZ / "benchmarks" / "matriz-modelos-v1.yaml"

_DATA_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")
_PAGINA_RE = re.compile(r"_p\d+$")


def carregar_precos(caminho: Path | None = None) -> dict:
    caminho = caminho or (PRECOS_PADRAO[-1] if PRECOS_PADRAO else None)
    if caminho is None:
        raise FileNotFoundError("nenhuma tabela benchmarks/precos-oficiais-*.yaml")
    return yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))


def modelo_base(nome: str) -> str:
    """`gemini/gemini-3.5-flash` e `gpt-4.1-2025-04-14` -> nome da tabela."""
    base = (nome or "").split("/")[-1].strip().lower()
    return _DATA_RE.sub("", base)


def custo_pela_tabela(modelo: str, entrada: int, saida: int, precos: dict) -> float | None:
    linha = (precos.get("modelos") or {}).get(modelo_base(modelo))
    if linha is None:
        return None
    return (entrada * linha["entrada"] + saida * linha["saida"]) / 1_000_000


def _tipo(passo: str) -> str:
    return _PAGINA_RE.sub("", passo)


def pontuar_estado(state: RunState, precos: dict) -> dict[str, Any]:
    """Placar de UM run a partir do estado salvo. Sem rede, sem custo."""
    passos = state.step_status
    custo_ledger = sum(r.cost_usd for r in passos.values())
    recalculado, sem_preco = 0.0, set()
    for chave, r in passos.items():
        if not (r.prompt_tokens or r.completion_tokens) or _tipo(chave) == "image_gen":
            recalculado += r.cost_usd           # imagem: preço declarado do run
            continue
        c = custo_pela_tabela(r.model_used, r.prompt_tokens, r.completion_tokens, precos)
        if c is None:
            sem_preco.add(r.model_used or "?")
            recalculado += r.cost_usd
        else:
            recalculado += c
    pagos = [r for r in passos.values() if r.prompt_tokens or r.completion_tokens]
    paginas = state.plan.pages if state.plan else []
    bloqueadas = [p.page_number for p in paginas
                  if (passos.get(f"blocked_p{p.page_number}") or None) is not None]
    prontas = [p.page_number for p in paginas
               if (r := passos.get(f"content_gate_p{p.page_number}")) is not None
               and r.status is not StepStatus.FAILED]
    grafo = passos.get("funnel_graph")
    revisao = state.revisao_global or {}
    materiais = [a for a in revisao.get("achados", []) if a.get("severidade") == "material"]
    return {
        "run_id": state.run_id,
        "custo_ledger_usd": round(custo_ledger, 6),
        "custo_tabela_oficial_usd": round(recalculado, 6),
        "modelos_sem_preco_oficial": sorted(sem_preco),
        "latencia_total_ms": sum(r.latency_ms for r in passos.values()),
        "chamadas_pagas": len(pagos),
        "retentativas": sum(max(0, r.attempts - 1) for r in pagos),
        "fallbacks": sorted(k for k, r in passos.items() if r.status is StepStatus.FALLBACK),
        "paginas": len(paginas),
        "paginas_prontas": len(prontas),
        "paginas_bloqueadas": bloqueadas,
        "grafo_reprovado": bool(grafo and grafo.status is StepStatus.FAILED),
        "achados_materiais_da_jornada": len(materiais),
        "custo_por_pagina_pronta_usd": (round(recalculado / len(prontas), 6)
                                        if prontas else None),
        "por_tipo": _por_tipo(passos),
    }


def _por_tipo(passos: dict) -> dict[str, dict]:
    saida: dict[str, dict] = {}
    for chave, r in passos.items():
        if not (r.prompt_tokens or r.completion_tokens):
            continue
        b = saida.setdefault(_tipo(chave), {"chamadas": 0, "tentativas": 0, "entrada": 0,
                                            "saida": 0, "custo_usd": 0.0, "modelos": set()})
        b["chamadas"] += 1
        b["tentativas"] += r.attempts
        b["entrada"] += r.prompt_tokens
        b["saida"] += r.completion_tokens
        b["custo_usd"] += r.cost_usd
        b["modelos"].add(modelo_base(r.model_used))
    for b in saida.values():
        b["modelos"] = sorted(b["modelos"])
        b["custo_usd"] = round(b["custo_usd"], 6)
    return saida


def estimar_matriz(referencia: RunState, matriz: dict, precos: dict,
                   config_base: dict) -> dict[str, dict]:
    """Custo estimado de cada configuração com o PERFIL de tokens e tentativas
    do run de referência. É estimativa (dito no resultado), não medição."""
    perfil = _por_tipo(referencia.step_status)
    saida: dict[str, dict] = {}
    for nome, sobreposicao in (matriz.get("configuracoes") or {}).items():
        passos = {**(config_base.get("steps") or {})}
        for passo, cfg in (sobreposicao or {}).items():
            passos[passo] = {**(passos.get(passo) or {}), **cfg}
        total, faltando = 0.0, set()
        for tipo, b in perfil.items():
            # `write_pN` agrega LP e internas; a internas (write_page) dominam.
            chave = "write_page" if tipo == "write" else tipo
            modelo = (passos.get(chave) or {}).get("model") or (b["modelos"] or ["?"])[0]
            if tipo == "image_gen":
                total += b["custo_usd"]
                continue
            c = custo_pela_tabela(modelo, b["entrada"], b["saida"], precos)
            if c is None:
                faltando.add(modelo)
                total += b["custo_usd"]
            else:
                total += c
        saida[nome] = {"custo_estimado_usd": round(total, 4),
                       "natureza": "estimativa (perfil de tokens do run de referência)",
                       "modelos_sem_preco_oficial": sorted(faltando)}
    return saida


def preparar(destino: Path, matriz: dict, config_base: dict) -> list[str]:
    """Um config.yaml por configuração + os comandos para rodar. NÃO executa."""
    destino.mkdir(parents=True, exist_ok=True)
    fixture = matriz.get("fixture")
    comandos = []
    for nome, sobreposicao in (matriz.get("configuracoes") or {}).items():
        cfg = copy.deepcopy(config_base)
        cfg.setdefault("run", {})["publish"] = False
        for passo, mudanca in (sobreposicao or {}).items():
            cfg.setdefault("steps", {}).setdefault(passo, {}).update(mudanca)
        pasta = destino / nome
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                                           encoding="utf-8")
        for i in range(int(matriz.get("repeticoes") or 1)):
            comandos.append(f"(cd {pasta} && funnelforge run-volc {RAIZ / fixture})  # {nome} #{i + 1}")
    return comandos


def _resumo(placar: dict) -> dict:
    return {k: v for k, v in placar.items() if k != "por_tipo"}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"pontuar", "estimar", "preparar"}:
        print(__doc__)
        return 2
    precos = carregar_precos()
    config_base = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    matriz = yaml.safe_load(MATRIZ_PADRAO.read_text(encoding="utf-8"))
    if argv[0] == "pontuar":
        placares = [pontuar_estado(RunState.from_json(Path(a).read_text(encoding="utf-8")), precos)
                    for a in argv[1:]]
        print(json.dumps({"placares": [_resumo(p) for p in placares],
                          "mediana_custo_tabela_usd": (median(p["custo_tabela_oficial_usd"]
                                                              for p in placares) if placares else None)},
                         ensure_ascii=False, indent=2))
    elif argv[0] == "estimar":
        ref = RunState.from_json(Path(argv[1]).read_text(encoding="utf-8"))
        print(json.dumps(estimar_matriz(ref, matriz, precos, config_base),
                         ensure_ascii=False, indent=2))
    else:
        for linha in preparar(Path(argv[1]), matriz, config_base):
            print(linha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
