#!/usr/bin/env python3
"""A bancada visual não pode ser publicada — e a prova barata não bastava.

## O defeito que este gate existe para não deixar voltar

`/qa/trafego/...` monta os componentes reais contra fixtures. É ferramenta de
conferência: útil no navegador do desenvolvedor, e nada que deva chegar ao
operador nem a quem visita o site publicado.

A prova de FONTE — guarda `import.meta.env.DEV` na rota, entrada por
`React.lazy`, ninguém importando a página fora de `src/pages/qa` — passava. O
`vite build` de verdade mostrou `assets/BancadaVisual-*.js` no bundle, com as
fixtures dentro. O Rollup monta o grafo de módulos a partir de cada `import()`
ANTES de qualquer eliminação de código morto: guardar a rota elimina o ramo,
guardar o `React.lazy` elimina a chamada, e nenhum dos dois elimina o CHUNK.

O que de fato tira a página dali é trocar o módulo: `vite.config.ts` resolve
`./pages/qa/BancadaVisual` para um substituto vazio quando
`mode === 'production'`.

## Por que um gate separado, e não só o teste

A contraprova mora em `src/pages/qa/__tests__/bancada-fora-de-producao.test.ts`
atrás de `describe.runIf(VOLC_PROVA_DE_BUNDLE === '1')`, porque ela roda um
build inteiro e a suíte é executada dezenas de vezes por hora. Sem alguém que
LIGUE a variável, a suíte fica verde com a prova crítica marcada como skipped —
que é o modo de falha mais caro que um gate tem, e foi exatamente o que a
revisão adversarial apontou.

Este arquivo é esse alguém. Ele liga a variável, exige que o caso tenha rodado
(não apenas passado) e falha se ele aparecer como skipped.

    python3 scripts/gate_bancada_fora_do_bundle.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ALVO = "src/pages/qa/__tests__/bancada-fora-de-producao.test.ts"

#: O caso que precisa ter RODADO. Conferido pelo nome, porque um `runIf` que não
#: dispara sai da saída como skipped e não como falha.
CASO = "o marcador não aparece em nenhum arquivo do bundle"


def main() -> int:
    if not (RAIZ / ALVO).exists():
        print(f"FALHA: {ALVO} não existe. A contraprova do bundle sumiu.")
        return 1

    ambiente = {**os.environ, "VOLC_PROVA_DE_BUNDLE": "1"}
    print(f"→ npx vitest run {ALVO}  (VOLC_PROVA_DE_BUNDLE=1)")
    proc = subprocess.run(
        ["npx", "vitest", "run", ALVO, "--reporter=verbose"],
        cwd=RAIZ, env=ambiente, capture_output=True, text=True, timeout=900,
    )
    saida = proc.stdout + proc.stderr

    # ⚠️ Sair 0 não basta. Um `runIf` que não dispara também sai 0.
    if re.search(rf"[↓-]\s*{re.escape(CASO)}.*skipped", saida) or (
            "skipped" in saida and CASO not in saida):
        print("FALHA: a prova de bundle não rodou — ficou como skipped.")
        print("       Um gate que não executa o caso crítico é verde sobre o vazio.")
        print(saida[-3000:])
        return 1

    if CASO not in saida:
        print(f"FALHA: o caso {CASO!r} não apareceu na saída do vitest.")
        print("       Renomear o caso o tira da rodada em silêncio.")
        print(saida[-3000:])
        return 1

    if proc.returncode != 0:
        print("FALHA: a bancada visual está no bundle de produção.")
        print(saida[-3000:])
        return 1

    print("OK: o build de produção não contém a bancada visual.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
