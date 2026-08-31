"""Resolução tipada de gates: a única autoridade do runtime.

Antes existiam dois caminhos. O compilador tipado (:mod:`gate_types`) era uma
biblioteca verde que ninguém consumia, e ``mission.py`` resolvia gate por
``argv`` livre com ``resolve_gate_argv`` e executava com ``subprocess.run``. Ter
a guarda escrita e não a ter chamada é pior que não tê-la: dá autoridade a uma
proteção que o caminho produtivo nunca atravessa.

Aqui a missão declara `kind` (tipo direto) ou `gate_id` (catálogo). Nos dois
casos sai um :class:`ResolvedGate` com argv construído pelo tipo, digest dos
insumos materiais e timeout — e é este objeto, não a missão, que o runtime
executa.

Fluxo, sem atalho possível::

    spec da missão → tipo (ou catálogo → tipo) → argv + binding
                   → [janela: writer roda] →
    assert_bindings_fresh  → executa      (digest igual)
                           → STALE_INPUT  (digest mudou)
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .failures import FailureClass, HarnessFailure
from .gate_catalog import (
    CONTRACT_VERSION, Catalog, GateBinding, load_catalog, resolve, sem_catalogo,
)
from .fingerprint import tree_fingerprint
from .gate_types import PytestGate, TypedGate, from_spec

#: `kind` reservado: não é um tipo de gate, é a indireção para o catálogo.
KIND_CATALOGO = "catalog"


@dataclass
class ResolvedGate:
    """Gate pronto para executar, com o vínculo material medido."""

    index: int
    kind: str
    argv: list[str]
    timeout_seconds: int
    binding: GateBinding
    typed: TypedGate
    gate_id: str | None = None
    #: Produced autorizados: untracked que o gate pode observar legitimamente.
    produced_paths: list[str] = field(default_factory=list)
    referenced_paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)
    depends_on_produced: list[str] = field(default_factory=list)
    collect_only_argv: list[str] | None = None

    @property
    def runnable_before_writer(self) -> bool:
        return not self.depends_on_produced

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "gate_id": self.gate_id,
            "argv": self.argv,
            "timeout_seconds": self.timeout_seconds,
            "executable": self.argv[0] if self.argv else "",
            "resolved_executable": self.argv[0] if self.argv else "",
            "referenced_paths": self.referenced_paths,
            "depends_on_produced": self.depends_on_produced,
            "runnable_before_writer": self.runnable_before_writer,
            "collect_only_argv": self.collect_only_argv,
            **self.binding.as_dict(),
        }


def build_toolchain(*, repo: Path, worktree: Path) -> dict[str, str]:
    """Interpretadores e binários do gate. Escolha explícita, nunca silenciosa.

    O venv do projeto é ignorado pelo Git e não existe na worktree do agente. A
    ordem é: venv da worktree primária → interpretador do próprio harness. Qual
    dos dois foi escolhido entra no ``context_digest``, então trocar de
    interpretador invalida a prova em vez de reaproveitá-la com régua diferente.
    """

    from ..gates import find_project_venv

    toolchain: dict[str, str] = {}
    try:
        venv = find_project_venv(repo=repo, worktree=worktree)
    except Exception:                       # repositório sem worktree registrada
        venv = None
    python = (venv / "bin" / "python") if venv is not None else None
    toolchain["python"] = str(python) if python and python.is_file() else sys.executable
    toolchain["python_source"] = "project_venv" if python and python.is_file() else "harness"
    for nome in ("git", "npm"):
        achado = shutil.which(nome)
        if achado:
            toolchain[nome] = achado
    tsc = worktree / "node_modules" / ".bin" / "tsc"
    if tsc.is_file():
        toolchain["tsc"] = str(tsc)
    return toolchain


def _binding(
    typed: TypedGate, *, tree: Path, catalog: Catalog | None, definition_digest: str,
    extra_paths: Sequence[str] = (),
) -> GateBinding:
    return GateBinding(
        contract_version=CONTRACT_VERSION,
        catalog_digest=catalog.file_digest if catalog is not None else "",
        definition_digest=definition_digest,
        input_digests=typed.evidence_inputs(worktree=tree),
        # A árvore inteira, sempre. `evidence_inputs` cobre o que o TIPO sabe
        # declarar; o fingerprint cobre o que o gate OBSERVA sem declarar —
        # conftest, pytest.ini, tsconfig, módulos importados pelos testes.
        tree_digest=tree_fingerprint(tree, extra_paths=extra_paths),
    )


def _spec_do_gate(spec: Any) -> dict[str, Any]:
    if hasattr(spec, "model_dump"):
        return spec.model_dump(mode="json")
    if isinstance(spec, Mapping):
        return dict(spec)
    raise HarnessFailure(
        FailureClass.SPEC_ERROR, "gate em formato desconhecido",
        detalhe=type(spec).__name__)


def resolve_mission_gates(
    *,
    gates: Sequence[Any],
    tree: Path,
    toolchain: Mapping[str, str],
    produced_paths: Sequence[Mapping[str, Any]] = (),
    catalog: Catalog | None = None,
) -> list[ResolvedGate]:
    """Resolve todos os gates da missão. Não existe fallback genérico.

    ``produced_paths`` é o que autoriza um gate a citar caminho que ainda não
    existe — a lição da lane B3, preservada: gate sobre arquivo inventado é
    ``SPEC_ERROR`` em milissegundos, não ``exit 4`` depois de 39 minutos de
    writer.
    """

    ferramentas = dict(toolchain)
    prometidos = {p["path"] for p in produced_paths}
    resolvidos: list[ResolvedGate] = []
    catalogo_lido = catalog

    for indice, bruto in enumerate(gates, start=1):
        spec = _spec_do_gate(bruto)
        timeout = int(spec.pop("timeout_seconds", 600) or 600)
        gate_id: str | None = None

        if spec.get("kind") == KIND_CATALOGO:
            gate_id = spec.get("gate_id")
            if not gate_id:
                raise HarnessFailure(
                    FailureClass.SPEC_ERROR, f"gate {indice} de catálogo sem gate_id")
            if catalogo_lido is None:
                catalogo_lido = load_catalog(tree)
            entrada = resolve(catalogo_lido, gate_id)
            typed = from_spec(indice, dict(entrada.spec), from_catalog=True)
            vinculo = _binding(typed, tree=tree, catalog=catalogo_lido,
                               definition_digest=entrada.definition_digest,
                               extra_paths=sorted(prometidos))
            kind = entrada.kind
        else:
            typed = from_spec(indice, dict(spec), from_catalog=False)
            kind = typed.kind
            vinculo = _binding(typed, tree=tree, catalog=None,
                               definition_digest=sem_catalogo(kind=kind).definition_digest,
                               extra_paths=sorted(prometidos))

        typed.timeout_seconds = timeout
        argv = typed.build(worktree=tree, toolchain=ferramentas)

        referenciados = typed.referenced_paths()
        ausentes, dependem = [], []
        for alvo in referenciados:
            if (tree / alvo).exists():
                continue
            (dependem if alvo in prometidos else ausentes).append(alvo)
        if ausentes:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                f"gate {indice} cita caminho inexistente e não declarado em produced_paths",
                detalhe=", ".join(ausentes),
                reproducao=f"ls {ausentes[0]}  # dentro de {tree}",
                evidencia={"gate_index": indice, "missing": ausentes, "argv": argv},
            )

        # O argv de coleta é CONSTRUÍDO sempre, inclusive para gate que depende de
        # `produced_paths`. Construir não é executar, e condicionar a construção
        # deixava justamente os gates NOVOS — os mais propensos a coletar zero
        # testes — sem a conferência da lição B3: eles nasciam com
        # `collect_only_argv=None` e a sonda do postwriter devolvia -1 em
        # silêncio, mesmo depois de o writer ter criado o arquivo.
        collect = (typed.collect_argv(worktree=tree, toolchain=ferramentas)
                   if isinstance(typed, PytestGate) else None)

        resolvidos.append(ResolvedGate(
            index=indice, kind=kind, argv=argv, timeout_seconds=timeout,
            binding=vinculo, typed=typed, gate_id=gate_id,
            produced_paths=sorted(prometidos),
            referenced_paths=referenciados, depends_on_produced=dependem,
            collect_only_argv=collect,
        ))
    return resolvidos


def rebind(
    resolvidos: Sequence[ResolvedGate], *, tree: Path
) -> list[ResolvedGate]:
    """Reancora o vínculo depois das mudanças AUTORIZADAS do writer.

    O fingerprint da árvore é medido na compilação, ANTES do writer — e o writer
    muda a árvore, que é o trabalho dele. Sem reancorar, todo gate sairia
    STALE_INPUT e a guarda viraria um bloqueio universal, o que é tão inútil
    quanto não ter guarda.

    A janela que interessa não é "compilação → execução": é "última mudança
    AUTORIZADA → execução". O ownership já foi conferido quando esta função é
    chamada; daqui em diante qualquer alteração é de terceiro, e é essa que a
    revalidação nos quatro pontos precisa pegar.
    """

    novos: list[ResolvedGate] = []
    for gate in resolvidos:
        vinculo = GateBinding(
            contract_version=gate.binding.contract_version,
            catalog_digest=gate.binding.catalog_digest,
            definition_digest=gate.binding.definition_digest,
            input_digests=gate.typed.evidence_inputs(worktree=tree),
            tree_digest=tree_fingerprint(tree, extra_paths=gate.produced_paths),
        )
        novos.append(ResolvedGate(
            index=gate.index, kind=gate.kind, argv=gate.argv,
            timeout_seconds=gate.timeout_seconds, binding=vinculo,
            typed=gate.typed, gate_id=gate.gate_id,
            produced_paths=gate.produced_paths,
            referenced_paths=gate.referenced_paths,
            missing_paths=gate.missing_paths,
            depends_on_produced=gate.depends_on_produced,
            collect_only_argv=gate.collect_only_argv,
        ))
    return novos


def assert_bindings_fresh(
    resolvidos: Sequence[ResolvedGate], *, tree: Path
) -> None:
    """Reconfere o vínculo imediatamente antes da execução.

    Entre compilar e executar existe uma janela real: o writer roda, o operador
    mexe no repositório, um processo paralelo altera um lockfile. Se o insumo
    material de um gate auditado mudou nessa janela, a execução não acontece.
    Isto NÃO é gate vermelho — não é mérito do candidato — e por isso tem classe
    própria, ``STALE_INPUT``, com zero retry de writer.
    """

    catalogo: Catalog | None = None
    for gate in resolvidos:
        if gate.gate_id is not None:
            if catalogo is None:
                catalogo = load_catalog(tree)
            if catalogo.file_digest != gate.binding.catalog_digest:
                raise HarnessFailure(
                    FailureClass.STALE_INPUT,
                    "o catálogo de gates mudou entre a compilação e a execução",
                    detalhe=f"gate {gate.index} ({gate.gate_id})",
                    reproducao=f"git diff -- {tree}/tools/agent-harness/gate-catalog.json",
                    evidencia={"gate_index": gate.index,
                               "compilado": gate.binding.catalog_digest,
                               "agora": catalogo.file_digest},
                )
            entrada = resolve(catalogo, gate.gate_id)
            if entrada.definition_digest != gate.binding.definition_digest:
                raise HarnessFailure(
                    FailureClass.STALE_INPUT,
                    "a definição do gate mudou entre a compilação e a execução",
                    detalhe=f"gate {gate.index} ({gate.gate_id})",
                    evidencia={"gate_index": gate.index, "gate_id": gate.gate_id},
                )

        agora_arvore = tree_fingerprint(tree, extra_paths=gate.produced_paths)
        if agora_arvore != gate.binding.tree_digest:
            raise HarnessFailure(
                FailureClass.STALE_INPUT,
                "a árvore relevante mudou entre a compilação e a execução",
                detalhe=f"gate {gate.index} ({gate.kind})",
                reproducao="git status --porcelain",
                evidencia={"gate_index": gate.index,
                           "compilado": gate.binding.tree_digest[:16],
                           "agora": agora_arvore[:16]},
            )

        agora = gate.typed.evidence_inputs(worktree=tree)
        if agora != gate.binding.input_digests:
            mudou = sorted(
                set(agora) | set(gate.binding.input_digests)
                if set(agora) != set(gate.binding.input_digests)
                else {k for k, v in agora.items()
                      if gate.binding.input_digests.get(k) != v}
            )
            raise HarnessFailure(
                FailureClass.STALE_INPUT,
                "insumo material do gate mudou entre a compilação e a execução",
                detalhe=f"gate {gate.index}: {', '.join(mudou[:6])}",
                reproducao=f"git status --porcelain -- {' '.join(mudou[:3])}",
                evidencia={"gate_index": gate.index, "inputs_alterados": mudou},
            )
