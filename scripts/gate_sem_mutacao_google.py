#!/usr/bin/env python3
"""Na rota produtiva testada, nenhuma mutação sai sem recibo `em_voo` antes.

## O que este gate alegava, e o que ele provava

A primeira versão declarava três condições no docstring e executava duas: a
terceira — "a rota recusa antes do executor" — nunca era exercitada, e mesmo
assim o gate imprimia "nenhuma mutação Google Ads é alcançável". A conclusão era
mais forte que a evidência, que é exatamente o defeito que este projeto passa o
tempo todo apontando nos outros.

Agora as três são executadas:

1. `FORGE_PERMITIR_ESCRITA` não está armada no ambiente do gate;
2. `volc_ads.gads.modo.escrita_permitida()` responde False;
3. as cinco contraprovas focais da rota rodam de verdade — e elas usam SENTINELA
   no executor (`subir_proibido` chama `pytest.fail` se for invocado) e conferem
   a ORDEM dos atos, não apenas o status HTTP.

## O que este gate NÃO é, dito antes que alguém conclua sozinho

Não é inspeção de rede. Não é contenção de processo — o runner local não contém
o filesystem nem a árvore de processos (risco G1b, declarado pelo próprio
harness). E não é prova sobre portas futuras nem sobre caminhos fora da rota
testada: o CLI `python -m volc_ads.subir --subir`, por exemplo, não passa por
aqui.

A alegação sustentada é estreita e verdadeira: **na rota produtiva testada,
nenhuma mutação foi chamada sem recibo `em_voo` persistido antes.**
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BACKEND = RAIZ / "backend"

CONTRAPROVAS = [
    "tests/test_trafego_ledger.py::test_recusa_do_ledger_impede_qualquer_chamada_que_muta",
    "tests/test_trafego_ledger.py::test_ledger_nao_configurado_recusa_a_escrita_em_vez_de_seguir_sem_recibo",
    "tests/test_trafego_ledger.py::test_ledger_fora_do_ar_tambem_impede_o_mutate",
    "tests/test_trafego_ledger.py::test_o_recibo_em_voo_e_gravado_antes_da_chamada_que_muta",
    "tests/test_trafego_ledger.py::test_sem_resposta_vira_indeterminado_e_recusa_reenvio",
]


def main() -> int:
    falhas: list[str] = []

    if os.environ.get("FORGE_PERMITIR_ESCRITA", "").strip() == "1":
        falhas.append("FORGE_PERMITIR_ESCRITA=1 está no ambiente do gate")
    else:
        print("ok · 1/3 FORGE_PERMITIR_ESCRITA não está armada")

    sys.path.insert(0, str(RAIZ))
    try:
        from volc_ads.gads import modo
    except Exception as exc:  # noqa: BLE001
        # Não conseguir importar NÃO é prova de segurança: é ausência de leitura.
        print(f"gate: não consegui importar volc_ads.gads.modo ({exc}); "
              f"ausência de leitura não vale como trava fechada", file=sys.stderr)
        return 78
    try:
        if bool(modo.escrita_permitida()):
            falhas.append("volc_ads.gads.modo.escrita_permitida() respondeu True")
        else:
            print("ok · 2/3 a trava de escrita está fechada")
    except Exception as exc:  # noqa: BLE001
        print(f"gate: escrita_permitida() levantou {exc}", file=sys.stderr)
        return 78

    ambiente = dict(os.environ)
    ambiente["PYTHONPATH"] = str(RAIZ) + (
        os.pathsep + ambiente["PYTHONPATH"] if ambiente.get("PYTHONPATH") else "")
    ambiente.pop("FORGE_PERMITIR_ESCRITA", None)

    prova = subprocess.run(
        [sys.executable, "-m", "pytest", *CONTRAPROVAS, "-q", "-p", "no:randomly"],
        cwd=str(BACKEND), env=ambiente, capture_output=True, text=True, check=False,
    )
    saida = (prova.stdout or "") + (prova.stderr or "")
    ultimas = [l for l in saida.splitlines() if l.strip()][-3:]
    for l in ultimas:
        print("   " + l)

    if prova.returncode != 0:
        falhas.append("as contraprovas focais da rota NÃO passaram")
    elif f"{len(CONTRAPROVAS)} passed" not in saida:
        # Um node id renomeado é DESELECIONADO em silêncio: pytest sai 0 tendo
        # rodado menos. Verde com menos prova é o pior desfecho possível aqui.
        falhas.append(
            f"esperava {len(CONTRAPROVAS)} contraprovas e a saída não confirma essa "
            f"contagem — algum node id deixou de existir e foi ignorado sem erro")
    else:
        print(f"ok · 3/3 as {len(CONTRAPROVAS)} contraprovas focais da rota passaram, "
              f"com sentinela no executor e conferência de ordem")

    if falhas:
        for f in falhas:
            print(f"gate: {f}", file=sys.stderr)
        return 1

    print("\nna rota produtiva testada, nenhuma mutação foi chamada sem recibo "
          "`em_voo` persistido antes.")
    print("este gate NÃO inspeciona rede, NÃO contém processos e NÃO fala sobre "
          "caminhos fora da rota testada (o CLI de volc_ads, por exemplo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
