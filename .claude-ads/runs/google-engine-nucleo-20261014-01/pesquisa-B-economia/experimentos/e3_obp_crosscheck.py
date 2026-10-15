"""E3b — confere a implementação mínima contra o obp (zr-obp). SINTÉTICO.

Roda no venv isolado onde `pip install obp` resolveu (em Python 3.13 o pip
recuou para obp 0.4.1; ver e4_instalacao.json). Lê a réplica 0 do cenário A
salva por e3_ope.py e compara IPS/DM/DR do obp com os da implementação numpy.

Rodar: <venv-obp>/bin/python -I e3_obp_crosscheck.py e3_replica0_A.npz [saida.json]
"""
from __future__ import annotations

import json
import sys

import numpy as np
import obp
from obp.ope import DirectMethod, DoublyRobust, InverseProbabilityWeighting, OffPolicyEvaluation

d = np.load(sys.argv[1])
x, a, r, ps, pi_e, qhat = d["x"], d["a"], d["r"], d["pscore"], d["pi_e"], d["qhat"]
n, K = pi_e.shape
bf = {"n_rounds": n, "n_actions": K, "action": a, "reward": r, "pscore": ps,
      "position": None, "context": x}
ope = OffPolicyEvaluation(bandit_feedback=bf, ope_estimators=[
    InverseProbabilityWeighting(), DirectMethod(), DoublyRobust()])
est_obp = ope.estimate_policy_values(action_dist=pi_e[:, :, None],
                                     estimated_rewards_by_reg_model=qhat[:, :, None])
w = pi_e[np.arange(n), a] / ps
proprio = {"ipw": float(np.mean(w * r)), "dm": float(np.mean(np.sum(pi_e * qhat, 1))),
           "dr": float(np.mean(np.sum(pi_e * qhat, 1) + w * (r - qhat[np.arange(n), a])))}
saida = {"rotulo": "SINTETICO", "obp_versao": obp.__version__,
         "obp": {k: float(v) for k, v in est_obp.items()}, "implementacao_numpy": proprio,
         "diferenca_max_abs": max(abs(float(est_obp[k]) - proprio[k]) for k in proprio)}
print(json.dumps(saida, indent=1))
if len(sys.argv) > 2:
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(saida, fh, indent=1)
