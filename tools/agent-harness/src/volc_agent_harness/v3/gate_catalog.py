"""Catálogo versionado de gates: conteúdo indireto com dono e digest.

A refutação de G1a não parou no ``argv`` livre. Dois tipos de gate selecionam
conteúdo que o harness não escreveu e não audita: ``npm_script`` roda o que
estiver em ``package.json``, e ``tracked_script`` roda o que estiver no arquivo.
"Está rastreado pelo Git" prova origem, não prova revisão — e não prova nada
sobre o instante da execução, porque entre compilar e executar existe uma janela.

O catálogo fecha as duas pontas:

* a missão referencia um gate por **ID**, nunca por conteúdo. Ela não escolhe
  qual script roda nem qual entrada de ``package.json`` é chamada;
* o compilador resolve o ID contra um arquivo **rastreado pelo Git**, calcula o
  digest da definição e dos insumos materiais, e vincula isso à prova;
* imediatamente antes de executar, o digest é medido de novo. Divergiu, é
  ``STALE_INPUT`` — não é gate vermelho, não é mérito do candidato, e não roda.

⚠️ O QUE ISTO NÃO É
Não é contenção de processo. Um script auditado que roda com os privilégios do
harness continua podendo tocar o filesystem inteiro. Isto fecha política de
DECLARAÇÃO e janela de troca de insumo; G1b segue aberta.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .failures import FailureClass, HarnessFailure

#: Caminho do catálogo dentro da árvore. Não é configurável pela missão — uma
#: missão que escolhesse o próprio catálogo seria o mesmo furo com outra roupa.
CATALOGO_RELATIVO = "tools/agent-harness/gate-catalog.json"

#: Versão do contrato de identidade. Entra no digest: mudar a forma de calcular
#: invalida provas antigas em vez de compará-las com régua diferente.
CONTRACT_VERSION = 1

#: A autoridade sobre "este tipo exige catálogo" é UMA: o atributo de classe
#: `TypedGate.exige_catalogo`, em `gate_types`, que é quem `from_spec` consulta.
#: Existia aqui uma constante paralela — sem consumidor e já defasada, porque
#: não listava `build`. Duas fontes para o mesmo fato é como não ter fonte: a
#: que ninguém lê envelhece em silêncio e depois é citada como se valesse.


def tipos_que_exigem_catalogo() -> frozenset[str]:
    """Derivado da única autoridade, nunca redigitado."""

    from .gate_types import TIPOS

    return frozenset(nome for nome, classe in TIPOS.items()
                     if classe.exige_catalogo)


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _canonico(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _rastreado(tree: Path, relativo: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(tree), "ls-files", "--error-unmatch", relativo],
        capture_output=True, check=False,
    ).returncode == 0


@dataclass(frozen=True)
class CatalogEntry:
    gate_id: str
    kind: str
    spec: dict[str, Any]
    description: str
    definition_digest: str


@dataclass(frozen=True)
class Catalog:
    tree: Path
    version: int
    file_digest: str
    entries: Mapping[str, CatalogEntry]

    def __contains__(self, gate_id: str) -> bool:
        return gate_id in self.entries


def load_catalog(tree: Path) -> Catalog:
    """Lê o catálogo da árvore. Não rastreado pelo Git é bloqueio, não aviso."""

    caminho = tree / CATALOGO_RELATIVO
    if not caminho.is_file():
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "catálogo de gates ausente na árvore",
            detalhe=str(caminho),
            reproducao=f"crie {CATALOGO_RELATIVO} e versione-o",
        )
    if not _rastreado(tree, CATALOGO_RELATIVO):
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "catálogo de gates não é rastreado pelo Git; sem revisão não há autoridade",
            detalhe=CATALOGO_RELATIVO,
            reproducao=f"git ls-files --error-unmatch {CATALOGO_RELATIVO}",
        )
    bruto = caminho.read_bytes()
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "catálogo de gates não é JSON válido",
            detalhe=str(erro)[:200],
        ) from erro

    versao = dados.get("catalog_version")
    if versao != CONTRACT_VERSION:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "versão do catálogo de gates incompatível com este harness",
            detalhe=f"catálogo={versao!r} harness={CONTRACT_VERSION}",
        )

    entradas: dict[str, CatalogEntry] = {}
    for gate_id, definicao in sorted((dados.get("gates") or {}).items()):
        if not isinstance(definicao, dict) or "kind" not in definicao:
            raise HarnessFailure(
                FailureClass.SPEC_ERROR,
                "entrada de catálogo sem kind",
                detalhe=gate_id,
            )
        spec = {k: v for k, v in definicao.items() if k != "description"}
        entradas[gate_id] = CatalogEntry(
            gate_id=gate_id,
            kind=definicao["kind"],
            spec=spec,
            description=str(definicao.get("description", "")),
            definition_digest=_sha256_texto(
                f"{CONTRACT_VERSION}|{gate_id}|{_canonico(spec)}"
            ),
        )
    return Catalog(
        tree=tree,
        version=versao,
        file_digest=hashlib.sha256(bruto).hexdigest(),
        entries=entradas,
    )


def resolve(catalog: Catalog, gate_id: str) -> CatalogEntry:
    """Resolve o ID. Um ID que ninguém declarou não vira gate improvisado."""

    entrada = catalog.entries.get(gate_id)
    if entrada is None:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "gate_id não existe no catálogo versionado",
            detalhe=f"{gate_id!r} não está em {sorted(catalog.entries)}",
            reproducao=f"declare {gate_id} em {CATALOGO_RELATIVO}",
        )
    return entrada


@dataclass(frozen=True)
class GateBinding:
    """Vínculo material medido na compilação e reconferido antes de executar."""

    contract_version: int
    catalog_digest: str
    definition_digest: str
    input_digests: dict[str, str]

    def digest(self) -> str:
        return _sha256_texto("|".join([
            str(self.contract_version),
            self.catalog_digest,
            self.definition_digest,
            _canonico(dict(sorted(self.input_digests.items()))),
        ]))

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "catalog_digest": self.catalog_digest,
            "definition_digest": self.definition_digest,
            "input_digests": dict(sorted(self.input_digests.items())),
            "binding_digest": self.digest(),
        }


def sem_catalogo(*, kind: str) -> GateBinding:
    """Vínculo de um gate tipado direto: não há conteúdo indireto para prender."""

    return GateBinding(
        contract_version=CONTRACT_VERSION,
        catalog_digest="",
        definition_digest=_sha256_texto(f"{CONTRACT_VERSION}|direto|{kind}"),
        input_digests={},
    )
