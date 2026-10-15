"""Contrato único de experimentos do Freedom Lab.

O JSON Schema (`contracts/experimento.schema.json`) cobre a forma. Este módulo
cobre o que a forma não consegue dizer e que é onde experimentos costumam
mentir:

- medida marcada como `observed` sem valor, ou `not_measured` sem motivo;
- chave que aparece ao mesmo tempo em `result.observed` e `result.estimated`
  (estimativa vestida de observação);
- `adopt` com hipótese refutada ou inconclusiva, ou sem que o número observado
  da métrica primária supere o baseline pelo efeito mínimo declarado;
- `adopt` sem reprodução (`reproducible` precisa ser identical|within_tolerance);
- chamada externa incoerente com `replay_without_api`;
- seeds ausentes sem justificativa; replay sem API impossível sem motivo;
- limpeza declarada mas não feita;
- artefato fora do diretório do experimento (`..`, absoluto, `.env`) ou cujo
  SHA-256 não bate com o arquivo em disco.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

RAIZ_LAB = Path(__file__).resolve().parents[2]
SCHEMA = RAIZ_LAB / "contracts" / "experimento.schema.json"


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def _erros_de_forma(exp: dict[str, Any]) -> list[str]:
    import jsonschema

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validador = jsonschema.Draft202012Validator(schema)
    return [
        f"forma: {'/'.join(str(p) for p in e.absolute_path) or '<raiz>'}: {e.message}"
        for e in sorted(validador.iter_errors(exp), key=lambda e: list(e.absolute_path))
    ]


def _erros_semanticos(exp: dict[str, Any], base: Path | None) -> list[str]:
    erros: list[str] = []

    for nome, medida in (exp.get("metrics") or {}).items():
        tipo = medida.get("kind")
        if tipo in ("observed", "estimated") and medida.get("value") is None:
            erros.append(f"metrics.{nome}: kind={tipo} exige value (ausência não é zero)")
        if tipo == "not_measured" and not medida.get("not_measured_reason"):
            erros.append(f"metrics.{nome}: not_measured exige not_measured_reason")
        if tipo == "not_measured" and medida.get("value") is not None:
            erros.append(f"metrics.{nome}: not_measured não pode ter value")
        if medida.get("value") is not None and not _numero(medida["value"]):
            erros.append(f"metrics.{nome}: value precisa ser número finito")

    resultado = exp.get("result") or {}
    comuns = set(resultado.get("observed") or {}) & set(resultado.get("estimated") or {})
    if comuns:
        erros.append(f"result: chaves em observed e estimated ao mesmo tempo: {sorted(comuns)}")

    desfecho = resultado.get("hypothesis_outcome")
    if exp.get("decision") == "adopt":
        if desfecho != "supported":
            erros.append(f"decision=adopt exige hypothesis_outcome=supported (veio {desfecho!r})")
        erros += _erros_de_adocao(exp)

    metodo = exp.get("method") or {}
    chamadas = metodo.get("external_calls") or {}
    if metodo.get("replay_without_api") and chamadas.get("mode") != "none":
        erros.append("method: replay_without_api=true exige external_calls.mode=none")
    if chamadas.get("mode") == "none" and chamadas.get("count", 0) != 0:
        erros.append("method: external_calls.mode=none com count>0")
    if not metodo.get("seeds") and not metodo.get("seeds_not_applicable_reason"):
        erros.append("method: informe seeds ou seeds_not_applicable_reason")
    if metodo.get("replay_without_api") is False and not metodo.get("replay_not_possible_reason"):
        erros.append("method: replay_without_api=false exige replay_not_possible_reason")

    limpeza = exp.get("rollback_or_cleanup") or {}
    if limpeza.get("done") is not True:
        erros.append("rollback_or_cleanup.done precisa ser true antes de fechar o experimento")

    if base is None:
        erros.append("artefatos não conferidos: informe o diretório base do experimento")
    else:
        raiz = base.resolve()
        for art in exp.get("artifacts") or []:
            caminho = (base / art["path"]).resolve()
            if not caminho.is_relative_to(raiz) or ".env" in caminho.name.lower():
                erros.append(f"artifact fora do diretório do experimento: {art['path']}")
                continue
            if not caminho.is_file():
                erros.append(f"artifact ausente: {art['path']}")
            elif sha256_arquivo(caminho) != art["sha256"]:
                erros.append(f"artifact com SHA divergente: {art['path']}")
    return erros


def _numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _recusar_constante(nome: str):
    raise ValueError(f"JSON com {nome}: não é número; ausência se escreve null")


def carregar(caminho: Path) -> dict[str, Any]:
    return json.loads(caminho.read_text(encoding="utf-8"), parse_constant=_recusar_constante)


def _erros_de_adocao(exp: dict[str, Any]) -> list[str]:
    """adopt só passa com número: métrica primária observada, baseline e candidato
    não nulos, efeito no sentido declarado >= min_effect, e resultado reproduzido."""
    h, r = exp["hypothesis"], exp["result"]
    nome = h["primary_metric"]
    obs = (r.get("observed") or {}).get(nome)
    if not isinstance(obs, dict) or obs.get("baseline") is None or obs.get("candidate") is None:
        return [f"decision=adopt exige result.observed.{nome} com baseline e candidate não nulos"]
    if not all(_numero(v) for v in (obs["baseline"], obs["candidate"], h["min_effect"])):
        return ["decision=adopt exige baseline, candidate e min_effect numéricos e finitos (NaN, Infinity e bool não são número)"]
    efeito = obs["candidate"] - obs["baseline"]
    if h["direction"] == "decrease":
        efeito = -efeito
    erros = []
    if efeito < h["min_effect"]:
        erros.append(f"decision=adopt com efeito {efeito:.6g} < min_effect {h['min_effect']}")
    if r.get("reproducible") not in ("identical", "within_tolerance"):
        erros.append(f"decision=adopt exige reproducible identical|within_tolerance (veio {r.get('reproducible')!r})")
    return erros


def validar(exp: dict[str, Any], base_artefatos: Path | None = None) -> list[str]:
    """Devolve a lista de erros; lista vazia significa experimento aceito."""
    erros = _erros_de_forma(exp)
    if erros:
        return erros
    return _erros_semanticos(exp, base_artefatos)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Valida um experimento do Freedom Lab")
    p.add_argument("arquivo", type=Path)
    a = p.parse_args(argv)
    try:
        exp = carregar(a.arquivo)
    except ValueError as e:
        print("ERRO", e)
        print(json.dumps({"experiment_id": None, "valido": False}))
        return 1
    erros = validar(exp, a.arquivo.parent)
    for e in erros:
        print("ERRO", e)
    print(json.dumps({"experiment_id": exp.get("experiment_id"), "valido": not erros}))
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
