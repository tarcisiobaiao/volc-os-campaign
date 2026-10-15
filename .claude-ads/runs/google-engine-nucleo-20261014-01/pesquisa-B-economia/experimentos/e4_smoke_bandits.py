"""E4 — Smoke de instalação/uso de MABWiser e Vowpal Wabbit. SINTÉTICO.

Só prova que as bibliotecas instalam e respondem no venv isolado; não avalia
política nem alega ganho. Cada uma roda no próprio venv:
  <venv-mabwiser>/bin/python -I e4_smoke_bandits.py mabwiser
  <venv-vowpalwabbit>/bin/python -I e4_smoke_bandits.py vw
"""
from __future__ import annotations

import json
import sys

import numpy as np

rng = np.random.default_rng(20261014)
qual = sys.argv[1]
out = {"rotulo": "SINTETICO — smoke de instalacao, nao avaliacao", "lib": qual}

if qual == "mabwiser":
    import mabwiser
    from mabwiser.mab import MAB, LearningPolicy
    # 3 "grupos" com taxa de clique monetizado 2%, 3%, 5% (sintético)
    p = [0.02, 0.03, 0.05]
    arms = rng.integers(0, 3, 3000)
    rew = (rng.random(3000) < np.take(p, arms)).astype(int)
    mab = MAB(arms=[0, 1, 2], learning_policy=LearningPolicy.ThompsonSampling(), seed=7)
    mab.fit(decisions=arms.tolist(), rewards=rew.tolist())
    escolhas = [mab.predict() for _ in range(200)]
    out.update(versao=getattr(mabwiser, "__version__", "?"),
               frac_escolha_melhor_braco=float(np.mean(np.array(escolhas) == 2)),
               nota="TS exige recompensa binaria/limitada por braco; lucro em R$ com sinal nao e o caso nativo.")
elif qual == "vw":
    import vowpalwabbit
    vw = vowpalwabbit.Workspace("--cb_explore_adf --epsilon 0.2 --quiet --random_seed 7")
    custo = {0: 0.2, 1: 0.5, 2: 0.8}   # VW minimiza CUSTO; contexto único
    for _ in range(2000):
        ex = ["shared |s c=1"] + [f"|a acao={k}" for k in range(3)]
        pmf = vw.predict(ex)
        k = int(rng.choice(3, p=np.array(pmf) / np.sum(pmf)))
        rotulado = list(ex)
        c = custo[k] + rng.normal(0, 0.1)
        rotulado[k + 1] = f"0:{c:.4f}:{pmf[k]:.4f} " + rotulado[k + 1]
        vw.learn(rotulado)
    pmf = vw.predict(["shared |s c=1"] + [f"|a acao={k}" for k in range(3)])
    vw.finish()
    out.update(versao=vowpalwabbit.__version__ if hasattr(vowpalwabbit, "__version__") else "9.x",
               pmf_final=[round(float(v), 3) for v in pmf],
               nota="cb_explore_adf grava a probabilidade da acao tomada (pmf) — exatamente o campo que falta no ledger VOLC para OPE.")
print(json.dumps(out, ensure_ascii=False))
