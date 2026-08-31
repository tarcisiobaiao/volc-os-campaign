#!/usr/bin/env python3
"""Testes do frontend que a entrega de lançamento de fato exercita.

## Como este recorte foi escolhido, e por que o anterior estava errado

A primeira versão apontava para `src/lib/trafego` e mais nada. O candidato tocou
quatro módulos — `Lancamento.tsx`, `lib/trafego/lancamento.ts`, `pautadorApi.ts`
e `types/trafego.ts` — e aquele recorte não exercitava o COMPONENTE alterado.
Um gate que não toca o arquivo alterado é verde sobre o vazio.

Os alvos abaixo saíram de análise de imports, não de palpite:

* `lib/trafego/__tests__/lancamento.test.ts` — importa o módulo puro novo;
* `components/trafego/__tests__/lancamento.test.tsx` — importa `pautadorApi` e os tipos;
* `components/trafego/__tests__/prova-honesta.test.tsx` — idem;
* `components/trafego/__tests__/painel-do-lancamento.test.tsx` — importa os tipos;
* `components/trafego/recibos/__tests__/recibo.test.ts` — a leitura do recibo;
* `pages/trafego/__tests__/sincronia-do-lancado.test.tsx` — o caminho do "já lançado";
* `pages/trafego/__tests__/nova-campanha-criterios.test.tsx` — o ÚNICO teste que
  importa o componente `Lancamento` diretamente.

Não é a suíte inteira, de propósito: ela carrega falhas herdadas e o harness
recusa começar sobre baseline vermelho. O recorte é declarado; a suíte inteira
não é substituída em silêncio.

## Zero coletado é FALHA

O filtro do vitest casa por substring de caminho. Um alvo renomeado deixa de
casar e some da rodada sem erro — o gate ficaria verde medindo menos, que é o
modo de falha mais caro que um gate tem. Por isso a contagem de arquivos é
conferida contra o número de alvos declarados.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ALVOS = [
    "src/lib/trafego/__tests__/lancamento.test.ts",
    "src/components/trafego/__tests__/lancamento.test.tsx",
    "src/components/trafego/__tests__/prova-honesta.test.tsx",
    "src/components/trafego/__tests__/painel-do-lancamento.test.tsx",
    "src/components/trafego/recibos/__tests__/recibo.test.ts",
    "src/pages/trafego/__tests__/sincronia-do-lancado.test.tsx",
    "src/pages/trafego/__tests__/nova-campanha-criterios.test.tsx",
]


def main() -> int:
    vitest = RAIZ / "node_modules" / ".bin" / "vitest"
    if not vitest.is_file():
        print(f"gate: vitest ausente em {vitest}", file=sys.stderr)
        return 78

    ausentes = [a for a in ALVOS if not (RAIZ / a).is_file()]
    if ausentes:
        print("gate: alvo declarado não existe no disco: " + ", ".join(ausentes),
              file=sys.stderr)
        return 1

    saida = subprocess.run(
        [str(vitest), "run", *ALVOS, "--reporter=dot"],
        cwd=str(RAIZ), capture_output=True, text=True, check=False,
    )
    texto = (saida.stdout or "") + (saida.stderr or "")
    sys.stdout.write(texto)

    arquivos = re.search(r"Test Files\s+(\d+)\s+passed\s+\((\d+)\)", texto)
    testes = re.search(r"Tests\s+(\d+)\s+passed\s+\((\d+)\)", texto)
    n_arq = int(arquivos.group(2)) if arquivos else 0
    n_tst = int(testes.group(2)) if testes else 0
    print(f"\ncoletado: {n_arq} arquivo(s), {n_tst} teste(s) · alvos declarados: {len(ALVOS)}")

    if n_tst == 0 or n_arq == 0:
        print("gate: ZERO teste coletado — isto é falha, nunca verde", file=sys.stderr)
        return 1
    if n_arq < len(ALVOS):
        print(f"gate: coletou {n_arq} de {len(ALVOS)} alvos declarados — algum alvo "
              f"deixou de casar (renome?) e a rodada mediu menos do que promete",
              file=sys.stderr)
        return 1
    return saida.returncode


if __name__ == "__main__":
    raise SystemExit(main())
