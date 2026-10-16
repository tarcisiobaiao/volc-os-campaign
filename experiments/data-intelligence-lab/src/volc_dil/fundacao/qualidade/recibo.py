"""Recibo de saúde: `health_receipt.json` (manifesto + achados + alertas propostos) e resumo Markdown.

Uso:
    python -m volc_dil.fundacao.qualidade.recibo --cenario producao_conhecida --seed 20261016 --saida DIR
    python -m volc_dil.fundacao.qualidade.recibo --entrada conjunto.json --agora 2026-10-16T15:00:00Z --saida DIR

`--entrada` aceita `{"formato": "tabelas", "tabelas": {<tabela>: [linhas]}}` (export read-only das
tabelas reais) ou `{"formato": "protocolo", ...}`. Nada é enviado: alertas são só propostos.
O fingerprint cobre entrada, parâmetros, código, agora e resultado; não cobre versões nem horário
de geração — mesma entrada + mesmo código = mesmo fingerprint.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from volc_dil.contracts.fingerprint import sha256_codigo, sha256_de, versoes

from .agenda import LIMIARES_PADRAO, SLA, SLA_PADRAO
from .alertas import POLITICAS_PADRAO, decidir_alertas
from .modelo import iso, para_datetime
from .motor import ConjuntoSaude, avaliar_saude, view_da_regra
from .sintetico import AGORA_PADRAO, CENARIOS, gerar_series_deriva, gerar_tabelas

SCHEMA = "volc_dil.health_receipt/v1"
DIR_CODIGO = Path(__file__).resolve().parent


def gerar_recibo(
    conjunto: ConjuntoSaude,
    *,
    agora: datetime,
    origem: str,
    seed: int | None,
    entrada_sha256: str | None = None,
    slas: Mapping[str, SLA] = SLA_PADRAO,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> dict[str, Any]:
    achados = avaliar_saude(conjunto, agora, slas, limiares)
    alertas, _ = decidir_alertas(achados, agora, POLITICAS_PADRAO)
    parametros = {"slas": {k: v.como_dict() for k, v in sorted(slas.items())}, "limiares": dict(limiares)}
    lista = [dict(a.como_dict(), view=view_da_regra(a.regra)) for a in achados]
    por_sev = Counter(a.severidade.value for a in achados)
    manifesto = {
        "nome": "health_receipt",
        "origem": origem,
        "seed": seed,
        "agora": iso(agora),
        "entrada_sha256": entrada_sha256 or sha256_de(conjunto.como_dict()),
        "parametros_sha256": sha256_de(parametros),
        "codigo_sha256": sha256_codigo(str(p) for p in sorted(DIR_CODIGO.glob("*.py"))),
        "contagens": {"runs": len(conjunto.runs), "observacoes": len(conjunto.observacoes),
                      "dias_sensor": len(conjunto.cobertura_sensor), "series_deriva": len(conjunto.series_deriva)},
        "estado": "testado com sintético" if origem.startswith("sintetico") else "dado exportado (ver origem)",
    }
    resumo = {
        "por_severidade": {s: por_sev.get(s, 0) for s in ("critico", "alto", "aviso", "info")},
        "por_regra": dict(sorted(Counter(a.regra for a in achados).items())),
        "pior_severidade": achados[0].severidade.value if achados else "ok",
    }
    corpo = {"schema": SCHEMA, "manifesto": manifesto, "parametros": parametros, "resumo": resumo,
             "achados": lista, "alertas_propostos": [a.como_dict() for a in alertas]}
    corpo["fingerprint"] = sha256_de(corpo)
    corpo["manifesto"] = dict(manifesto, versoes=versoes())
    return corpo


def resumo_markdown(recibo: Mapping[str, Any]) -> str:
    m, r = recibo["manifesto"], recibo["resumo"]
    linhas = [
        "# Recibo de saúde de dados",
        "",
        f"- origem: `{m['origem']}` · estado: **{m['estado']}** · agora: `{m['agora']}` · seed: `{m['seed']}`",
        f"- entrada sha256: `{m['entrada_sha256'][:16]}…` · código: `{m['codigo_sha256'][:16]}…` · "
        f"fingerprint: `{recibo['fingerprint'][:16]}…`",
        f"- contagens: {m['contagens']}",
        f"- pior severidade: **{r['pior_severidade']}** · por severidade: {r['por_severidade']}",
        "",
        "| severidade | regra | fonte | chave | view | mensagem |",
        "|---|---|---|---|---|---|",
    ]
    for a in recibo["achados"]:
        if a["severidade"] == "info":
            continue
        msg = a["mensagem"].replace("|", "\\|")
        linhas.append(f"| {a['severidade']} | `{a['regra']}` | {a['fonte']} | `{a['chave'] or ''}` | "
                      f"{a['view'] or '—'} | {msg} |")
    n_info = r["por_severidade"]["info"]
    linhas += ["", f"{n_info} achado(s) `info` omitidos da tabela (estão no JSON).", "",
               f"Alertas propostos (NÃO enviados): {len(recibo['alertas_propostos'])}."]
    for al in recibo["alertas_propostos"]:
        linhas.append(f"- [{al['politica']} → {al['canal']}] {al['severidade']} `{al['regra']}` {al['chave'] or ''}")
    return "\n".join(linhas) + "\n"


def escrever(recibo: Mapping[str, Any], saida: Path) -> tuple[Path, Path]:
    saida.mkdir(parents=True, exist_ok=True)
    pj, pm = saida / "health_receipt.json", saida / "health_receipt.md"
    pj.write_text(json.dumps(recibo, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pm.write_text(resumo_markdown(recibo), encoding="utf-8")
    return pj, pm


def recibo_sintetico(cenario: str = "producao_conhecida", seed: int = 20261016,
                     agora: datetime = AGORA_PADRAO) -> dict[str, Any]:
    tabelas = gerar_tabelas(seed, cenario, agora)
    conjunto = ConjuntoSaude.de_tabelas(tabelas, agora, series_deriva=gerar_series_deriva(seed, cenario, agora))
    return gerar_recibo(conjunto, agora=agora, origem=f"sintetico:{cenario}", seed=seed,
                        entrada_sha256=sha256_de({"tabelas": tabelas, "series": conjunto.series_deriva}))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cenario", choices=sorted(CENARIOS), default="producao_conhecida")
    ap.add_argument("--seed", type=int, default=20261016)
    ap.add_argument("--agora", default=None, help="ISO-8601 com fuso; padrão: 2026-10-16T15:00:00Z (sintético)")
    ap.add_argument("--entrada", type=Path, default=None, help="JSON exportado (formato tabelas|protocolo)")
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args(argv)
    agora = para_datetime(a.agora) if a.agora else AGORA_PADRAO
    if a.entrada:
        bruto = a.entrada.read_bytes()
        dados = json.loads(bruto)
        conjunto = ConjuntoSaude.de_dict(dados, agora)
        import hashlib

        recibo = gerar_recibo(conjunto, agora=agora, origem=f"arquivo:{a.entrada.name}", seed=None,
                              entrada_sha256=hashlib.sha256(bruto).hexdigest())
    else:
        recibo = recibo_sintetico(a.cenario, a.seed, agora)
    pj, pm = escrever(recibo, a.saida)
    print(f"{pj}\n{pm}\nfingerprint {recibo['fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
