"""Avaliação offline do REVISOR CONTEXTUAL (reforma editorial, B5).

Roda o revisor do motor (`pipeline/revisao.py`, com as mesmas travas de
código) sobre casos rotulados em pt-BR (`tests/fixtures/avaliacao_revisor/
casos.jsonl`) e mede a CONCORDÂNCIA por categoria.

    # padrão: SIMULAÇÃO — nenhuma chamada, só a estimativa de custo
    PYTHONPATH=src .venv/bin/python scripts/avaliar_revisor.py --saida /tmp/aval

    # execução real: exige --executar E --teto-usd; para ANTES de estourar o teto
    PYTHONPATH=src .venv/bin/python scripts/avaliar_revisor.py --saida /tmp/aval \
        --executar --teto-usd 1.50

As chaves do provedor vêm do AMBIENTE (este script não lê `.env`).

## Como a concordância é medida

`esperado.decisao` compara com o veredito da 1ª RODADA, depois das travas de
coerência do código: `aprova` = o revisor aprovou sem ajuste; `nao_aprova` =
pediu ajuste ou revisão humana. Um caso concorda quando o veredito bate E todo
trecho em `esperado.deve_apontar` foi apontado (achado ou afirmação não
verificada). A decisão final (depois dos patches) também é gravada.

Nada aqui promete desempenho: é medida sobre 32 casos, com o modelo e a data
registrados. Custo estimado usa preço DECLARADO por milhão de tokens — confira
a tabela do provedor antes de confiar no número.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

MOTOR = Path(__file__).resolve().parents[1]
if str(MOTOR / "src") not in sys.path:
    sys.path.insert(0, str(MOTOR / "src"))

from funnelforge.config.settings import StepConfig  # noqa: E402
from funnelforge.pipeline.budget import Orcamento, OrcamentoEstourado  # noqa: E402
from funnelforge.pipeline.revisao import (  # noqa: E402
    MAX_RODADAS,
    Documento,
    executar_revisao,
    montar_prompt_do_revisor,
)
from funnelforge.pipeline.revisao_avulsa import contexto_de_dados  # noqa: E402
from funnelforge.pipeline.runner import Runner  # noqa: E402

CASOS_PADRAO = MOTOR / "tests" / "fixtures" / "avaliacao_revisor" / "casos.jsonl"
# Preço DECLARADO (US$ por milhão de tokens: entrada, saída). Confira no provedor.
PRECO_DECLARADO = {"gpt-4.1": (2.00, 8.00), "gemini/gemini-3.5-flash": (0.30, 2.50)}
PRECO_DESCONHECIDO = (5.00, 15.00)            # conservador para modelo fora da tabela
TOKENS_DE_SAIDA_ESTIMADOS = 900


def _cliente_real():
    """O cliente pago (isolado para o teste trocar por um falso)."""
    from funnelforge.adapters.litellm_client import LiteLLMClient

    return LiteLLMClient()


def carregar_casos(caminho: Path) -> list[dict]:
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()
            if linha.strip()]


def cfg_do_revisor(config: Path) -> StepConfig:
    dados = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    return StepConfig(**((dados.get("steps") or {})["revisor"]))


def documento_do_caso(caso: dict) -> Documento:
    pag = caso["pagina"]
    corpo = pag["corpo"]
    if not isinstance(corpo, str):
        corpo = json.dumps(corpo, ensure_ascii=False)
    return Documento(formato=pag["formato"], corpo=corpo, seotitle=pag.get("seotitle", ""),
                     metadescription=pag.get("metadescription", ""))


def _preco(modelo: str) -> tuple[float, float]:
    return PRECO_DECLARADO.get(modelo, PRECO_DESCONHECIDO)


def estimar_custo_do_caso(caso: dict, modelo: str, hoje: date) -> float:
    doc = documento_do_caso(caso)
    ctx = contexto_de_dados(caso.get("briefing"), caso.get("contexto"), doc, hoje=hoje)
    entrada = len(montar_prompt_do_revisor(doc, ctx, rodada=1)) / 4
    pin, pout = _preco(modelo)
    return (entrada * pin + TOKENS_DE_SAIDA_ESTIMADOS * pout) / 1_000_000


def _apontados(registro: dict) -> list[str]:
    trechos: list[str] = []
    for rodada in registro.get("rodadas") or []:
        trechos += [str(a.get("trecho") or "") for a in rodada.get("achados") or []]
        trechos += [str(a.get("trecho") or "")
                    for a in rodada.get("afirmacoes_nao_verificadas") or []]
    return [t for t in trechos if t]


def _veredito_da_primeira_rodada(registro: dict) -> str:
    """`aprova` só quando a 1ª rodada aprovou E o código aceitou a aprovação."""
    rodadas = registro.get("rodadas") or []
    return "aprova" if len(rodadas) == 1 and registro.get("decisao") == "aprovado" else "nao_aprova"


def avaliar(casos: list[dict], *, llm, cfg: StepConfig, teto_usd: float, saida: Path,
            hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    saida.mkdir(parents=True, exist_ok=True)
    orcamento = Orcamento(teto_run_usd=teto_usd, teto_pagina_usd=0)
    runner = Runner(llm=llm, max_retries=0, runs_dir=saida / "execucao", budget=orcamento,
                    sleep=lambda _s: None)
    gasto = 0.0
    maior_por_chamada = 0.0
    parou = False
    resultados: list[dict] = []
    for caso in casos:
        estimado = estimar_custo_do_caso(caso, cfg.model, hoje)
        previsto = max(maior_por_chamada, estimado) * MAX_RODADAS
        if gasto + previsto > teto_usd:
            parou = True
            break
        doc = documento_do_caso(caso)
        ctx = contexto_de_dados(caso.get("briefing"), caso.get("contexto"), doc, hoje=hoje)
        try:
            r = executar_revisao(doc, ctx, runner=runner, cfg=cfg, run_id=f"caso-{caso['id']}",
                                 numero=int(ctx.pagina.get("numero") or 1))
        except OrcamentoEstourado:
            parou = True
            break
        custo = r.telemetria.cost_usd
        chamadas = max(1, r.telemetria.attempts)
        gasto += custo
        maior_por_chamada = max(maior_por_chamada, custo / chamadas)
        veredito = _veredito_da_primeira_rodada(r.registro)
        apontados = _apontados(r.registro)
        faltou = [t for t in caso["esperado"].get("deve_apontar", [])
                  if not any(t in a or a in t for a in apontados)]
        concorda = veredito == caso["esperado"]["decisao"] and not faltou
        resultados.append({
            "id": caso["id"], "categoria": caso["categoria"],
            "esperado": caso["esperado"]["decisao"], "veredito_1a_rodada": veredito,
            "decisao_final": r.decisao, "motivos": r.registro.get("motivos"),
            "erro": r.registro.get("erro"), "faltou_apontar": faltou, "concorda": concorda,
            "custo_usd": custo, "tokens": [r.telemetria.prompt_tokens,
                                          r.telemetria.completion_tokens],
            "registro": r.registro,
        })
    (saida / "resultados.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in resultados) + "\n", encoding="utf-8")
    por_categoria: dict[str, dict] = defaultdict(lambda: {"casos": 0, "concordam": 0})
    for x in resultados:
        balde = por_categoria[x["categoria"]]
        balde["casos"] += 1
        balde["concordam"] += int(x["concorda"])
    resumo = {
        "modelo": cfg.model, "data": hoje.isoformat(), "teto_usd": teto_usd,
        "gasto_usd": round(gasto, 6), "parou_por_teto": parou,
        "casos_avaliados": len(resultados), "casos_no_arquivo": len(casos),
        "concordancia_geral": (round(sum(x["concorda"] for x in resultados) / len(resultados), 4)
                               if resultados else None),
        "por_categoria": {c: {**v, "concordancia": round(v["concordam"] / v["casos"], 4)}
                          for c, v in sorted(por_categoria.items())},
        "aviso": "Medida sobre casos rotulados; não é promessa de desempenho em produção.",
    }
    (saida / "concordancia.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return resumo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Avaliação offline do revisor contextual.")
    ap.add_argument("--casos", type=Path, default=CASOS_PADRAO)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=MOTOR / "config.yaml")
    ap.add_argument("--executar", action="store_true",
                    help="chama o modelo real (pago); exige --teto-usd > 0")
    ap.add_argument("--teto-usd", type=float, default=None)
    args = ap.parse_args(argv)
    casos = carregar_casos(args.casos)
    cfg = cfg_do_revisor(args.config)
    hoje = date.today()
    if not args.executar:
        total = sum(estimar_custo_do_caso(c, cfg.model, hoje) for c in casos)
        print(f"SIMULAÇÃO: {len(casos)} casos, modelo {cfg.model}. Nenhuma chamada foi feita.")
        print(f"Custo estimado (preço declarado): US$ {total:.4f} com 1 rodada por caso; "
              f"até US$ {total * MAX_RODADAS:.4f} com {MAX_RODADAS} rodadas.")
        print("Para executar de verdade: --executar --teto-usd <valor>.")
        return 0
    if args.teto_usd is None or args.teto_usd <= 0:
        print("--executar exige --teto-usd maior que zero.", file=sys.stderr)
        return 2
    resumo = avaliar(casos, llm=_cliente_real(), cfg=cfg, teto_usd=args.teto_usd,
                     saida=args.saida, hoje=hoje)
    print(json.dumps({k: resumo[k] for k in ("modelo", "gasto_usd", "parou_por_teto",
                                             "casos_avaliados", "concordancia_geral")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
