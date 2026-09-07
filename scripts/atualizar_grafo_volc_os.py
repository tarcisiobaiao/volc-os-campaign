#!/usr/bin/env python3
"""Reconstrói o Mapa Vivo VOLC em uma ordem única, segura e reproduzível.

Por padrão, regenera a fonte operacional a partir dos snapshots locais, extrai a
camada técnica por AST, funde as duas e recria todos os formatos derivados.
Use ``--refresh-live`` para atualizar primeiro o inventário somente-leitura do
Supabase. Use ``--reuse-technical`` apenas quando código e SQL não mudaram.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import venv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".graphify-cache" / "code"

#: ⚠️ A AUTORIDADE DO FRESCOR, e ela é VERSIONADA.
#:
#: `graphify-out/` inteiro é derivado e ignorado pelo Git — de propósito, porque
#: carrega dezenas de MB. A consequência era que o gate oficial não existia em
#: checkout limpo: `--check` só sabia responder lendo
#: `graphify-out/UPDATE_STATUS.json`, e num clone recém-feito esse arquivo não
#: está lá. O gate respondia `{"current": false, "reason": "UPDATE_STATUS.json
#: ausente"}` — não porque o grafo estivesse velho, mas porque a evidência era
#: irreprodutível. Achado bloqueante da revisão independente de 06/09/2026.
#:
#: O manifesto é pequeno (algumas centenas de bytes), mora em caminho
#: rastreado, e é o que qualquer clone consegue conferir.
MANIFESTO = ROOT / "docs" / "volc-os-graph" / "BUILD-STATUS.json"

#: O espelho local. Continua sendo escrito para quem já o lê, e NUNCA decide.
STATUS = ROOT / "graphify-out" / "UPDATE_STATUS.json"

#: Versão do contrato do manifesto. Um manifesto de outro esquema não é lido
#: "na boa vontade": ele falha FECHADO, porque não saber o que os campos
#: significam é o mesmo que não ter evidência nenhuma.
SCHEMA_DO_MANIFESTO = 2
RUNTIME_DB = Path("/private/tmp/volc-supabase-inventory.json")
RUNTIME_CLICKUP = Path("/private/tmp/volc-clickup-tasks-p0.json")
SAFE_DB = ROOT / "docs" / "volc-os-graph" / "supabase-snapshot-2026-08-22.json"
SAFE_CLICKUP = ROOT / "docs" / "volc-os-graph" / "clickup-snapshot-2026-08-22.json"
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql"}
CODE_NAMES = {"package.json", "package-lock.json", "tsconfig.json", "vite.config.ts"}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-live", action="store_true",
                        help="refaz o inventário somente-leitura do Supabase")
    parser.add_argument("--reuse-technical", action="store_true",
                        help="reusa o último AST; permitido somente sem mudanças de código/SQL")
    parser.add_argument("--bootstrap", action="store_true",
                        help="cria .venv-graphify e instala a versão fixada")
    parser.add_argument("--check", action="store_true",
                        help="apenas verifica se os insumos mudaram desde a última atualização")
    return parser.parse_args()


def run(command: list[str]) -> None:
    print("→", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def bootstrap() -> Path:
    target = ROOT / ".venv-graphify"
    if not target.exists():
        venv.EnvBuilder(with_pip=True).create(target)
    python = target / "bin" / "python"
    run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-graphify.txt")])
    return python


def graphify_python(do_bootstrap: bool) -> Path:
    configured = os.environ.get("GRAPHIFY_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        ROOT / ".venv-graphify" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if not candidate or not candidate.exists():
            continue
        result = subprocess.run(
            [str(candidate), "-c", "import graphify"],
            capture_output=True,
        )
        if result.returncode == 0:
            return candidate
    if do_bootstrap:
        return bootstrap()
    raise SystemExit(
        "Graphify não está instalado no ambiente permanente. Execute uma vez:\n"
        "  python3 scripts/atualizar_grafo_volc_os.py --bootstrap\n"
        "ou defina GRAPHIFY_PYTHON para um Python que contenha graphifyy[sql]==0.9.48."
    )


def tracked_inputs() -> list[Path]:
    """Os insumos do grafo — SÓ os rastreados, e nunca o próprio manifesto.

    ⚠️ RASTREADOS, e antes era `-co` (rastreados MAIS não-rastreados). Um
    arquivo `.py` de rascunho na árvore de alguém entrava no digest e fazia o
    gate responder "stale" contra um checkout limpo que não o tem — o mesmo
    defeito de irreprodutibilidade que este gate existe para fechar. Um arquivo
    não commitado não faz parte do commit: quando ele for commitado, o digest
    muda e o gate acusa, que é o momento certo.

    ⚠️ E O MANIFESTO FICA DE FORA, explicitamente. Ele carrega o digest destes
    arquivos; se entrasse na própria conta, todo build produziria um manifesto
    que já nasce inválido — autorreferência sem ponto fixo. Hoje ele já ficaria
    fora por acidente (`.json` não está em `CODE_SUFFIXES`), e é justamente por
    isso que a exclusão é explícita: acidente não é garantia, e alguém que
    acrescentasse `.json` à lista quebraria o gate sem entender por quê.
    """
    result = subprocess.run(
        ["git", "ls-files", "-c"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    paths = []
    for raw in result.stdout.splitlines():
        path = ROOT / raw
        if not path.is_file() or path == MANIFESTO:
            continue
        if path.suffix.lower() in CODE_SUFFIXES or path.name in CODE_NAMES:
            paths.append(path)
    business = ROOT / "docs" / "volc-os-graph" / "volc-os-graph.json"
    if business.exists() and business != MANIFESTO:
        paths.append(business)
    return sorted(set(paths))


def input_digest() -> tuple[str, int]:
    digest = hashlib.sha256()
    paths = tracked_inputs()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), len(paths)


def git_head() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def ensure_runtime_snapshots() -> None:
    if not RUNTIME_DB.exists():
        if not SAFE_DB.exists():
            raise SystemExit("Snapshot sanitizado do Supabase não encontrado.")
        shutil.copy2(SAFE_DB, RUNTIME_DB)
    if not RUNTIME_CLICKUP.exists() and SAFE_CLICKUP.exists():
        safe = json.loads(SAFE_CLICKUP.read_text(encoding="utf-8"))
        payload = {
            "tasks": [
                {"id": item.get("id"), "name": item.get("name"),
                 "status": {"status": item.get("status")}}
                for item in safe.get("tasks", [])
            ]
        }
        RUNTIME_CLICKUP.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_status(*, refreshed_live: bool, reused_technical: bool, python: Path) -> None:
    hybrid = json.loads((ROOT / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    business = json.loads((ROOT / "docs" / "volc-os-graph" / "volc-os-graph.json").read_text(encoding="utf-8"))
    digest, files = input_digest()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip() != ""
    try:
        version = subprocess.run(
            [str(python), "-c", "import importlib.metadata; print(importlib.metadata.version('graphifyy'))"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        version = "unknown"
    payload = {
        "schema_version": SCHEMA_DO_MANIFESTO,
        "generated_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
        "built_at_commit": git_head(),
        "working_tree_dirty_at_build": dirty,
        "input_sha256": digest,
        "input_file_count": files,
        "graphify_version": version,
        "live_sources_refreshed": refreshed_live,
        "technical_layer_reused": reused_technical,
        "sources": {
            "operational": "docs/volc-os-graph/volc-os-graph.json",
            "technical": ".graphify-cache/code/graphify-out/graph.json",
            "canonical_hybrid": "graphify-out/graph.json",
        },
        "counts": {
            "operational_nodes": len(business["nodes"]),
            "operational_edges": len(business["edges"]),
            "hybrid_nodes": len(hybrid["nodes"]),
            "hybrid_edges": len(hybrid["links"]),
        },
        "freshness_rule": (
            "Execute scripts/atualizar_grafo_volc_os.py --check; mudanças no digest "
            "exigem reconstrução. Decisões de negócio novas ainda exigem curadoria humana."
        ),
        "authority": (
            "docs/volc-os-graph/BUILD-STATUS.json é a autoridade do frescor, "
            "porque é versionada e existe em qualquer clone. "
            "graphify-out/UPDATE_STATUS.json é espelho local e nunca decide."
        ),
        "built_at_commit_nao_decide": (
            "⚠️ O frescor é decidido pelo DIGEST DOS INSUMOS, e nunca pela "
            "igualdade entre built_at_commit e o HEAD. built_at_commit registra "
            "onde o build rodou, e é normal que o HEAD fique adiante dele: um "
            "commit que mexe só em documentação fora dos insumos não torna o "
            "grafo velho. Exigir a igualdade criaria o ciclo infinito "
            "build → commit → o HEAD mudou → rebuild → commit, que não converge."
        ),
    }
    corpo = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    # ⚠️ O VERSIONADO PRIMEIRO. Se a escrita do espelho falhar, o que sobra é a
    # autoridade — e não o contrário.
    MANIFESTO.write_text(corpo, encoding="utf-8")
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(corpo, encoding="utf-8")


def _recusar(motivo: str) -> int:
    """Falha FECHADA. Não saber nunca é `current: true`."""
    print(json.dumps({
        "current": False,
        "reason": motivo,
        "authority": str(MANIFESTO.relative_to(ROOT)),
        "current_commit": git_head(),
    }, ensure_ascii=False, indent=2))
    return 1


def check_status() -> int:
    """O gate de frescor. Autoridade = manifesto VERSIONADO, digest = veredito.

    Reprodutível em clone limpo de propósito: nada aqui lê `graphify-out/`, que
    é derivado e ignorado. O espelho local aparece na saída como informação, e
    a sua ausência não muda o veredito.
    """
    if not MANIFESTO.exists():
        return _recusar(
            f"{MANIFESTO.relative_to(ROOT)} ausente — o manifesto versionado é a "
            "autoridade do frescor, e sem ele não há evidência a conferir. "
            "Rode scripts/atualizar_grafo_volc_os.py para produzi-lo.")
    try:
        status = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        return _recusar(f"{MANIFESTO.relative_to(ROOT)} inválido: {erro}")
    if not isinstance(status, dict):
        return _recusar(f"{MANIFESTO.relative_to(ROOT)} não é um objeto JSON")

    esquema = status.get("schema_version")
    if esquema != SCHEMA_DO_MANIFESTO:
        return _recusar(
            f"schema_version {esquema!r} incompatível (este script fala "
            f"{SCHEMA_DO_MANIFESTO}). Um manifesto cujo contrato não se conhece "
            "não é evidência.")
    gravado = status.get("input_sha256")
    if not isinstance(gravado, str) or not gravado:
        return _recusar("manifesto sem input_sha256 — não há o que conferir")

    digest, files = input_digest()
    current = digest == gravado
    print(json.dumps({
        "current": current,
        "reason": ("insumos idênticos" if current
                   else "código, SQL ou fonte operacional mudou"),
        "authority": str(MANIFESTO.relative_to(ROOT)),
        "schema_version": esquema,
        "generated_at": status.get("generated_at"),
        "built_at_commit": status.get("built_at_commit"),
        "current_commit": git_head(),
        "input_sha256": digest,
        "input_file_count": files,
        # ⚠️ O espelho é RELATO, nunca autoridade: o veredito acima não muda
        # com a presença ou a ausência dele.
        "espelho_local": {
            "caminho": str(STATUS.relative_to(ROOT)),
            "presente": STATUS.exists(),
            "usado_como_autoridade": False,
        },
        "nota": (
            "built_at_commit NÃO decide o frescor. É esperado e correto que o "
            "HEAD fique adiante dele quando os commits posteriores mexem só em "
            "documentação fora dos insumos do digest."
        ),
    }, ensure_ascii=False, indent=2))
    return 0 if current else 1


def main() -> None:
    options = args()
    if options.check:
        raise SystemExit(check_status())

    python = graphify_python(options.bootstrap)
    run([sys.executable, str(ROOT / "scripts" / "verificar_segredos.py")])
    if options.refresh_live:
        run([sys.executable, str(ROOT / "scripts" / "inventariar_supabase.py")])
    ensure_runtime_snapshots()
    run([sys.executable, str(ROOT / "scripts" / "gerar_grafo_volc_os.py")])

    technical = CACHE / "graphify-out" / "graph.json"
    if options.reuse_technical:
        if not technical.exists():
            raise SystemExit("Não há camada técnica em cache; execute sem --reuse-technical.")
    else:
        run([
            str(python), "-m", "graphify", "extract", str(ROOT),
            "--code-only", "--max-workers", "1", "--out", str(CACHE),
        ])

    run([
        str(python), str(ROOT / "scripts" / "gerar_graphify_volc_os.py"),
        "--code-graph", str(technical),
    ])
    run([str(python), str(ROOT / "scripts" / "exportar_grafo_volc_os.py")])
    run([sys.executable, str(ROOT / "scripts" / "gerar_explorador_neural_volc_os.py")])
    run([sys.executable, str(ROOT / "scripts" / "auditar_repositorio.py")])
    write_status(
        refreshed_live=options.refresh_live,
        reused_technical=options.reuse_technical,
        python=python,
    )
    print(f"✓ Mapa Vivo atualizado. Estado: {STATUS}")


if __name__ == "__main__":
    main()
