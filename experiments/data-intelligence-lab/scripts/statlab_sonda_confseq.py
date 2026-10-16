"""Stat Lab — registra o resultado da sonda isolada da lib ``confseq`` (Python 3.13 arm64).

A sonda em si (rede para o PyPI, só nesta etapa e só no venv descartável) foi:
  cd experiments/data-intelligence-lab && export UV_CACHE_DIR=$PWD/.uv-cache UV_PYTHON_DOWNLOADS=never
  .tools/bootstrap/bin/uv venv .tools/probe-d/confseq --python /usr/local/bin/python3.13
  .tools/bootstrap/bin/uv pip install --python .tools/probe-d/confseq/bin/python \
      --exclude-newer 2026-10-01T00:00:00Z confseq > .tools/probe-d/install.log 2>&1
  (+ variante --only-binary :all: > .tools/probe-d/install_binary.log)

Este script NÃO acessa rede: lê os logs locais e tenta importar no venv da sonda.
Grava results/statlab/sonda_confseq.json.
"""

from __future__ import annotations

import platform
import re
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

from volc_dil.statlab.base import gravar_json  # noqa: E402

SONDA = LAB / ".tools" / "probe-d"


def _trechos(log: Path, padroes: list[str]) -> list[str]:
    if not log.exists():
        return [f"log ausente: {log.name}"]
    linhas = log.read_text(errors="replace").splitlines()
    achadas = []
    for ln in linhas:
        s = ln.strip()
        if any(re.search(p, s) for p in padroes) and s not in achadas:
            achadas.append(s[:200])
    return achadas[:12]


def main() -> None:
    py = SONDA / "confseq" / "bin" / "python"
    importa = {"tentado": py.exists()}
    if py.exists():
        r = subprocess.run([str(py), "-c", "import confseq, sys; print(getattr(confseq, '__version__', '?'))"],
                           capture_output=True, text=True, timeout=60)
        importa.update({"codigo_saida": r.returncode,
                        "stdout": r.stdout.strip()[:200], "stderr_ultima_linha": (r.stderr.strip().splitlines() or [""])[-1][:200]})
    resultado = {
        "schema": "volc_dil.statlab.sonda_confseq/v1",
        "plataforma": {"sistema": platform.system(), "arquitetura": platform.machine(),
                       "python_da_sonda": "3.13.0 (/usr/local/bin/python3.13)"},
        "comando_exclude_newer": "2026-10-01T00:00:00Z",
        "instalacao_padrao": {
            "resultado": "FALHOU",
            "versao_resolvida": "confseq==0.0.11 (sdist; único candidato)",
            "trechos_log": _trechos(SONDA / "install.log",
                                    [r"Resolved", r"Building confseq", r"Failed to build", r"Could NOT find Boost",
                                     r"Ninja", r"CMake Generate step failed"]),
        },
        "instalacao_somente_wheel": {
            "resultado": "FALHOU",
            "motivo": "nenhuma versão de confseq tem wheel utilizável para cp313 macOS arm64",
            "trechos_log": _trechos(SONDA / "install_binary.log", [r"no usable wheels", r"unsatisfiable", r"Wheels are required"]),
        },
        "importacao_no_venv_da_sonda": importa,
        "decisao": ("não usar confseq no ambiente principal; CS implementada em NumPy "
                    "(volc_dil.statlab.sequencias_confianca, PrPl-EB). Compilar exigiria Boost >= 1.70 "
                    "e CMake/Ninja instalados globalmente — proibido nesta fase."),
        "nao_testado": "build com Boost local isolado; comparação numérica confseq vs implementação própria",
    }
    n = gravar_json(LAB / "results" / "statlab" / "sonda_confseq.json", resultado)
    print(f"gravado sonda_confseq.json ({n} bytes)")


if __name__ == "__main__":
    main()
