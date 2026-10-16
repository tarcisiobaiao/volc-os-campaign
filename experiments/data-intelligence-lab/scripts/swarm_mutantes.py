"""Swarm Lab — teste de mutação dos testes do swarm (achado F2-03 da revisão adversarial).

Copia src/, scripts/swarm_*.py e tests/data-intelligence/ para um diretório temporário, aplica
cada mutante (uma troca de texto) e roda tests/data-intelligence/test_swarm.py. Um mutante
"morto" faz algum teste falhar; "sobrevivente" é buraco de teste. Nada no repositório é alterado.

Uso (da raiz do repo):
  experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/swarm_mutantes.py
Grava results/swarm/swarm_mutantes.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess  # ÚNICA exceção do teste anti-rede: roda pytest local num diretório temporário
import sys
import tempfile
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
RAIZ = LAB.parents[1]

# SW1..SW7: mutantes da revisão F2 (/private/tmp/claude-502/f2/muts_sw.json), mesmos textos.
MUTANTES = [
    {"id": "SW1 criterio usa IC pareado em vez de ICs marginais", "arq": "swarm/experimento.py",
     "de": 'regret_ok = rc["ic95"][1] < rb["ic95"][0]', "para": 'regret_ok = ic_media(dif)["ic95"][1] < 0'},
    {"id": "SW2 melhor baseline = MAIOR regret", "arq": "swarm/experimento.py",
     "de": "melhor = min(presentes,", "para": "melhor = max(presentes,"},
    {"id": "SW3 criterio 2 e 3 sempre ok", "arq": "swarm/experimento.py",
     "de": '"supera": bool(regret_ok and falsos_ok and dd_ok),', "para": '"supera": bool(regret_ok),'},
    {"id": "SW4 perdedora definida como v<=0.5", "arq": "swarm/simulador.py",
     "de": "perdedora_t = np.vstack([cen.v_em(t) <= 1.0 for t in range(T)])",
     "para": "perdedora_t = np.vstack([cen.v_em(t) <= 0.5 for t in range(T)])"},
    {"id": "SW5 drawdown sempre 0", "arq": "swarm/simulador.py",
     "de": "    return int((pico - acum).max())", "para": "    return 0"},
    {"id": "SW6 madura espera so D-1", "arq": "swarm/politicas.py",
     "de": '        return obs.acumulado(0 if decisao == "parcial" else atraso)',
     "para": '        return obs.acumulado(0 if decisao == "parcial" else max(atraso - 1, 0))'},
    {"id": "SW7 prior do Thompson m0=3 tau0=0.1", "arq": "swarm/politicas.py",
     "de": "m0: float = 1.0, tau0: float = 1.0", "para": "m0: float = 3.0, tau0: float = 0.1"},
    # adicionais do owner
    {"id": "SW8 import de rede escondido dentro de funcao", "arq": "swarm/simulador.py",
     "de": "    p = cen.params\n    K, T, B, m = p.K", "para": "    import socket  # noqa\n    p = cen.params\n    K, T, B, m = p.K"},
    {"id": "SW9 excesso vs oraculo vira fracao absoluta", "arq": "swarm/simulador.py",
     "de": "np.maximum(aloc.astype(np.int64) - aloc_oraculo.astype(np.int64), 0)",
     "para": "aloc.astype(np.int64)"},
    {"id": "SW10 criterio exploratorio usa a metrica pre-registrada", "arq": "swarm/experimento.py",
     "de": 'metrica_falsos="excesso_perdedoras_vs_oraculo_final")', "para": ')'},
    {"id": "SW11 random_sh promove a melhor (vira SH)", "arq": "swarm/politicas.py",
     "de": 'manter = self.rng.choice(idx, size=n_keep, replace=False)',
     "para": 'manter = _ordem_desc(_valor_roi(g, r), idx)[:n_keep]'},
]


def _copiar(dest: Path) -> None:
    shutil.copytree(LAB / "src", dest / "experiments/data-intelligence-lab/src",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (dest / "experiments/data-intelligence-lab/scripts").mkdir(parents=True)
    for f in (LAB / "scripts").glob("swarm_*.py"):
        shutil.copy2(f, dest / "experiments/data-intelligence-lab/scripts" / f.name)
    shutil.copytree(RAIZ / "tests/data-intelligence", dest / "tests/data-intelligence",
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))


def _pytest(raiz: Path) -> tuple[int, str]:
    env = {"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/data-intelligence/test_swarm.py", "-q", "-x",
                        "-p", "no:cacheprovider"], cwd=raiz, capture_output=True, text=True, env=env, timeout=280)
    ult = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
    return r.returncode, ult


def main() -> None:
    saida = {"natureza": "teste de mutacao local; nao toca rede nem o repositorio", "mutantes": []}
    with tempfile.TemporaryDirectory(prefix="swarm-mut-") as d:
        raiz = Path(d)
        _copiar(raiz)
        rc, ult = _pytest(raiz)
        saida["sem_mutacao"] = {"passa": rc == 0, "pytest": ult}
        assert rc == 0, f"suíte não passa sem mutação: {ult}"
        src = raiz / "experiments/data-intelligence-lab/src/volc_dil"
        for m in MUTANTES:
            f = src / m["arq"]
            orig = f.read_text()
            assert orig.count(m["de"]) == 1, ("texto do mutante não encontrado exatamente uma vez", m["id"])
            f.write_text(orig.replace(m["de"], m["para"], 1))
            try:
                rc, ult = _pytest(raiz)
            finally:
                f.write_text(orig)
            estado = "morto" if rc != 0 else "SOBREVIVEU"
            saida["mutantes"].append({"id": m["id"], "estado": estado, "pytest": ult.split(" in ")[0]})
            print(f"{m['id']}: {estado} | {ult}", flush=True)
    saida["sobreviventes"] = [m["id"] for m in saida["mutantes"] if m["estado"] != "morto"]
    out = LAB / "results" / "swarm" / "swarm_mutantes.json"
    out.write_text(json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"sobreviventes: {saida['sobreviventes']}")


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    main()
