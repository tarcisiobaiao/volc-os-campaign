"""Swarm Lab — conferência da regra de corte por rung contra o Optuna (SONDA ISOLADA).

NÃO roda no venv do lab (Optuna não é dependência). Reprodução:
  cd experiments/data-intelligence-lab && export UV_CACHE_DIR=$PWD/.uv-cache UV_PYTHON_DOWNLOADS=never
  .tools/bootstrap/bin/uv venv .tools/probe-e/optuna --python /usr/local/bin/python3.13
  .tools/bootstrap/bin/uv pip install --python .tools/probe-e/optuna/bin/python --exclude-newer 2026-10-01T00:00:00Z optuna numpy
  .tools/probe-e/optuna/bin/python -I scripts/swarm_crosscheck_optuna.py $PWD/src/volc_dil/swarm/regras.py > results/swarm/swarm_crosscheck_optuna.json
  rm -rf .tools/probe-e
Resultado gravado em 2026-10-16: optuna 5.0.0, 60/60 sequências idênticas.
"""
import json, sys
import numpy as np
import optuna, importlib.util
_spec = importlib.util.spec_from_file_location("regras", sys.argv[1])
regras = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(regras)
from optuna.pruners import SuccessiveHalvingPruner
optuna.logging.set_verbosity(optuna.logging.ERROR)

def numpy_stop_rule(vals, eta):
    # vals: (N, R) valor do trial i no rung r; trials sequenciais; retorna rung máximo alcançado
    N, R = vals.shape
    comp = [[] for _ in range(R)]
    alcancado = np.zeros(N, int)
    for i in range(N):
        for r in range(R):
            comp[r].append(vals[i, r])
            if r == R - 1:
                alcancado[i] = R; break
            c = sorted(comp[r]); idx = len(c) // eta - 1
            if idx == -1: idx = 0
            if vals[i, r] >= c[-(idx + 1)]:
                continue
            alcancado[i] = r + 1; break
    return alcancado

def optuna_rule(vals, eta):
    N, R = vals.shape
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.RandomSampler(seed=0),
                                pruner=SuccessiveHalvingPruner(min_resource=1, reduction_factor=eta, min_early_stopping_rate=0))
    alc = []
    for i in range(N):
        t = study.ask()
        reached = R
        for r in range(R):
            step = eta ** r  # rungs em min_resource * eta^r
            t.report(float(vals[i, r]), step)
            if r < R - 1 and t.should_prune():
                reached = r + 1
                break
        if reached < R:
            study.tell(t, state=optuna.trial.TrialState.PRUNED)
        else:
            study.tell(t, float(vals[i, R - 1]))
        alc.append(reached)
    return np.array(alc)

rng = np.random.default_rng(20261016)
iguais = 0; total = 0; n_completos = []
for rep in range(60):
    eta = [2, 3][rep % 2]
    N, R = 16, 3
    base = rng.normal(size=N)
    vals = base[:, None] + rng.normal(scale=0.5, size=(N, R))
    a, b = regras.asha_parada_na_chegada(vals, eta), optuna_rule(vals, eta)
    iguais += int((a == b).all()); total += 1
    n_completos.append(int((b == R).sum()))
print(json.dumps({"optuna": optuna.__version__, "sequencias": total, "identicas": iguais,
                  "completos_por_sequencia_media": float(np.mean(n_completos)),
                  "nota": "Optuna SuccessiveHalvingPruner = ASHA na variante de PARADA na chegada ao rung (sem retomar pausados); 1os eta-1 trials passam se forem o melhor ate entao"}))
