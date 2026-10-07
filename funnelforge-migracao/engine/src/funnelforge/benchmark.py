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


def _tipo(passo: str, lps: frozenset[int] = frozenset()) -> str:
    """`write_p1` da LP vira `write_lp`; das internas, `write_page` — custos e
    retentativas da LP (JSON de slots) e das internas (Gutenberg) não se
    misturam."""
    tipo = _PAGINA_RE.sub("", passo)
    if tipo == "write":
        m = re.search(r"_p(\d+)$", passo)
        return "write_lp" if m and int(m.group(1)) in lps else "write_page"
    return tipo


def _lps(state: RunState) -> frozenset[int]:
    from funnelforge.domain.models import PageRole, effective_role
    paginas = state.plan.pages if state.plan else []
    return frozenset(p.page_number for p in paginas if effective_role(p) is PageRole.LP)


def _custo(modelo: str, entrada: int, saida: int, fallback: float, precos: dict,
           sem_preco: set) -> float:
    c = custo_pela_tabela(modelo, entrada, saida, precos)
    if c is None:
        sem_preco.add(modelo or "?")
        return fallback
    return c


def _arquiteto(pasta: Path | None, precos: dict, sem_preco: set) -> dict[str, Any]:
    """Custo e latência do ARQUITETO e do revisor do arquiteto, lidos da
    telemetria que o backend grava em `revisao_arquitetura.telemetria` e que o
    `run-volc` copia para `funnel_architecture.json`."""
    vazio = {"custo_usd": 0.0, "latencia_ms": 0, "chamadas": [], "medido": False}
    arq = (pasta / "funnel_architecture.json") if pasta else None
    if arq is None or not arq.exists():
        return vazio
    dados = json.loads(arq.read_text(encoding="utf-8"))
    dados = dados.get("funnel_architecture", dados) if isinstance(dados, dict) else {}
    tele = ((dados.get("revisao_arquitetura") or {}).get("telemetria") or [])
    chamadas = []
    for t in tele:
        modelo = t.get("modelo_servido") or t.get("modelo_solicitado") or ""
        chamadas.append({**t, "custo_usd": round(_custo(
            modelo, int(t.get("entrada") or 0), int(t.get("saida") or 0), 0.0, precos,
            sem_preco), 6)})
    return {"custo_usd": round(sum(c["custo_usd"] for c in chamadas), 6),
            "latencia_ms": sum(int(c.get("latencia_ms") or 0) for c in chamadas),
            "chamadas": chamadas, "medido": bool(chamadas)}


def _causas(pasta: Path | None) -> dict[str, list[str]]:
    """Passo -> códigos que reprovaram as tentativas (do `log.jsonl`)."""
    log = (pasta / "log.jsonl") if pasta else None
    saida: dict[str, list[str]] = {}
    if log is None or not log.exists():
        return saida
    for linha in log.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        causas = e.get("causas") or ([e["classe"]] if e.get("erro") and e.get("classe") else [])
        if e.get("step") and causas:
            saida.setdefault(e["step"], [])
            saida[e["step"]].extend(c for c in causas if c not in saida[e["step"]])
    return saida


def funil_aprovado(state: RunState) -> bool:
    """O funil inteiro passou: grafo/esqueleto aprovados e toda página com
    portão final OK e nenhuma condenação."""
    passos = state.step_status
    for chave in ("funnel_graph", "revisao_esqueleto"):
        r = passos.get(chave)
        if r is not None and r.status is StepStatus.FAILED:
            return False
    paginas = state.plan.pages if state.plan else []
    if not paginas:
        return False
    for p in paginas:
        n = p.page_number
        gate = passos.get(f"content_gate_p{n}")
        if f"blocked_p{n}" in passos or gate is None or gate.status is StepStatus.FAILED:
            return False
    return True


def pontuar_estado(state: RunState, precos: dict, pasta: Path | None = None) -> dict[str, Any]:
    """Placar de UM run a partir do estado salvo (e, se houver, do log e da
    arquitetura gravados ao lado). Sem rede, sem custo."""
    passos = state.step_status
    lps = _lps(state)
    custo_ledger = sum(r.cost_usd for r in passos.values())
    recalculado, sem_preco = 0.0, set()
    for chave, r in passos.items():
        if not (r.prompt_tokens or r.completion_tokens) or _tipo(chave, lps) == "image_gen":
            recalculado += r.cost_usd           # imagem: preço declarado do run
            continue
        recalculado += _custo(r.model_used, r.prompt_tokens, r.completion_tokens,
                              r.cost_usd, precos, sem_preco)
    arquiteto = _arquiteto(pasta, precos, sem_preco)
    total = recalculado + arquiteto["custo_usd"]
    pagos = {k: r for k, r in passos.items() if r.prompt_tokens or r.completion_tokens}
    paginas = state.plan.pages if state.plan else []
    bloqueadas = [p.page_number for p in paginas if f"blocked_p{p.page_number}" in passos]
    prontas = [p.page_number for p in paginas
               if (r := passos.get(f"content_gate_p{p.page_number}")) is not None
               and r.status is not StepStatus.FAILED]
    grafo = passos.get("funnel_graph")
    revisao = state.revisao_global or {}
    causas = _causas(pasta)
    aprovado = funil_aprovado(state)
    return {
        "run_id": state.run_id,
        "custo_ledger_usd": round(custo_ledger, 6),
        "custo_tabela_oficial_usd": round(recalculado, 6),
        "custo_arquiteto_usd": arquiteto["custo_usd"],
        "arquiteto_medido": arquiteto["medido"],
        "custo_total_usd": round(total, 6),
        "funil_aprovado": aprovado,
        "custo_por_funil_aprovado_usd": round(total, 6) if aprovado else None,
        "modelos_sem_preco_oficial": sorted(sem_preco),
        "latencia_total_ms": sum(r.latency_ms for r in passos.values()) + arquiteto["latencia_ms"],
        "chamadas_pagas": len(pagos) + len(arquiteto["chamadas"]),
        "retentativas": sum(max(0, r.attempts - 1) for r in pagos.values()),
        "retentativas_por_passo": {k: {"tentativas": r.attempts,
                                       "causas": causas.get(k, [])}
                                   for k, r in pagos.items() if r.attempts > 1},
        "fallbacks": sorted(k for k, r in passos.items() if r.status is StepStatus.FALLBACK),
        "modelo_pedido_x_servido": {k: {"pedido": r.model_requested, "servido": r.model_used}
                                    for k, r in pagos.items()
                                    if r.model_requested and modelo_base(r.model_requested)
                                    != modelo_base(r.model_used)},
        "paginas": len(paginas),
        "paginas_prontas": len(prontas),
        "paginas_bloqueadas": bloqueadas,
        "grafo_reprovado": bool(grafo and grafo.status is StepStatus.FAILED),
        "bloqueios_da_revisao_global": len(revisao.get("paginas_bloqueadas") or []),
        "custo_por_pagina_pronta_usd": (round(total / len(prontas), 6) if prontas else None),
        "por_tipo": _por_tipo(passos, lps),
    }


def _por_tipo(passos: dict, lps: frozenset[int] = frozenset()) -> dict[str, dict]:
    saida: dict[str, dict] = {}
    for chave, r in passos.items():
        if not (r.prompt_tokens or r.completion_tokens):
            continue
        b = saida.setdefault(_tipo(chave, lps), {"chamadas": 0, "tentativas": 0, "entrada": 0,
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
    perfil = _por_tipo(referencia.step_status, _lps(referencia))
    saida: dict[str, dict] = {}
    for nome, sobreposicao in (matriz.get("configuracoes") or {}).items():
        passos = {**(config_base.get("steps") or {})}
        for passo, cfg in (sobreposicao or {}).items():
            passos[passo] = {**(passos.get(passo) or {}), **cfg}
        total, faltando = 0.0, set()
        for tipo, b in perfil.items():
            chave = {"write_lp": "write_p1"}.get(tipo, tipo)
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
    orcamento = matriz.get("orcamento") or {}
    comandos = []
    for nome, sobreposicao in (matriz.get("configuracoes") or {}).items():
        cfg = copy.deepcopy(config_base)
        cfg.setdefault("run", {})["publish"] = False
        if matriz.get("editorial_v2") is not None:
            cfg["run"]["editorial_v2"] = bool(matriz["editorial_v2"])
        # Teto por run e por página: o próprio motor para ao estourar.
        if orcamento:
            cfg.setdefault("budget", {})
            cfg["budget"]["max_usd_per_run"] = orcamento["max_usd_por_run"]
            cfg["budget"]["max_usd_per_page"] = orcamento["max_usd_por_pagina"]
        for passo, mudanca in (sobreposicao or {}).items():
            cfg.setdefault("steps", {}).setdefault(passo, {}).update(mudanca)
        pasta = destino / nome
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                                           encoding="utf-8")
        for i in range(int(matriz.get("repeticoes") or 1)):
            # O `.env` do motor entra por link simbólico NA HORA de rodar: este
            # passo não lê nem copia segredo.
            comandos.append(f"(cd {pasta} && ln -sf {RAIZ / '.env'} .env && "
                            f"funnelforge run-volc {RAIZ / fixture})  # {nome} #{i + 1}")
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
        placares = [pontuar_estado(RunState.from_json(Path(a).read_text(encoding="utf-8")),
                                   precos, Path(a).parent) for a in argv[1:]]
        aprovados = [p for p in placares if p["funil_aprovado"]]
        print(json.dumps({
            "placares": [_resumo(p) for p in placares],
            "mediana_custo_total_usd": (median(p["custo_total_usd"] for p in placares)
                                        if placares else None),
            # custo de TODOS os runs dividido pelos funis que saíram aprovados:
            # o run reprovado também foi pago.
            "custo_por_funil_aprovado_usd": (round(sum(p["custo_total_usd"] for p in placares)
                                                   / len(aprovados), 6) if aprovados else None),
            "funis_aprovados": f"{len(aprovados)}/{len(placares)}"},
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
