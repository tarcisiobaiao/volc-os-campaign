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


def _status_instalacao(log: Path) -> dict:
    """Deriva o status do log (não fixo): SUCESSO se o uv registrou a instalação de confseq."""
    if not log.exists():
        return {"resultado": "NAO_EXECUTADA", "versao": None}
    texto = log.read_text(errors="replace")
    instalou = re.search(r"^\s*\+ confseq==(\S+)", texto, re.M)
    tentou = re.search(r"confseq==([0-9][\w.]*)", texto)
    if instalou:
        return {"resultado": "SUCESSO", "versao": instalou.group(1)}
    return {"resultado": "FALHOU", "versao_tentada": tentou.group(1) if tentou else None,
            "sem_wheel_utilizavel": bool(re.search(r"no usable wheels", texto)),
            "boost_ausente": bool(re.search(r"Could NOT find Boost", texto)),
            "falha_de_build": bool(re.search(r"Failed to build", texto))}


def main() -> None:
    py = SONDA / "confseq" / "bin" / "python"
    importa = {"tentado": py.exists()}
    if py.exists():
        r = subprocess.run([str(py), "-c", "import confseq, sys; print(getattr(confseq, '__version__', '?'))"],
                           capture_output=True, text=True, timeout=60)
        importa.update({"codigo_saida": r.returncode, "importou": r.returncode == 0,
                        "stdout": r.stdout.strip()[:200], "stderr_ultima_linha": (r.stderr.strip().splitlines() or [""])[-1][:200]})
    padrao = _status_instalacao(SONDA / "install.log")
    binario = _status_instalacao(SONDA / "install_binary.log")
    utilizavel = importa.get("importou", False)
    resultado = {
        "schema": "volc_dil.statlab.sonda_confseq/v2",
        "plataforma": {"sistema": platform.system(), "arquitetura": platform.machine(),
                       "python_da_sonda": "3.13.0 (/usr/local/bin/python3.13)"},
        "comando_exclude_newer": "2026-10-01T00:00:00Z",
        "instalacao_padrao": {**padrao, "trechos_log": _trechos(
            SONDA / "install.log", [r"Resolved", r"Building confseq", r"Failed to build", r"Could NOT find Boost",
                                    r"Ninja", r"CMake Generate step failed", r"Installed", r"\+ confseq"])},
        "instalacao_somente_wheel": {**binario, "trechos_log": _trechos(
            SONDA / "install_binary.log", [r"no usable wheels", r"unsatisfiable", r"Wheels are required",
                                           r"Installed", r"\+ confseq"])},
        "importacao_no_venv_da_sonda": importa,
        "confseq_utilizavel": utilizavel,
        "decisao": ("confseq importa na sonda; ainda assim não entra no ambiente principal sem revisão"
                    if utilizavel else
                    "não usar confseq no ambiente principal; CS implementada em NumPy "
                    "(volc_dil.statlab.sequencias_confianca, PrPl-EB). Compilar exigiria Boost >= 1.70 "
                    "e CMake/Ninja instalados globalmente — proibido nesta fase."),
        "nao_testado": "build com Boost local isolado; comparação numérica confseq vs implementação própria",
    }
    n = gravar_json(LAB / "results" / "statlab" / "sonda_confseq.json", resultado)
    print(f"gravado sonda_confseq.json ({n} bytes): padrão={padrao['resultado']} wheel={binario['resultado']} "
          f"import={'ok' if utilizavel else 'falhou'}")


if __name__ == "__main__":
    main()
