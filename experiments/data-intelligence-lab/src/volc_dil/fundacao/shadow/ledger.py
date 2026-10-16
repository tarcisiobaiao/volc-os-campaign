"""Ledger de shadow append-only com hash encadeado (memória + JSONL opcional).

Cada entrada é JSON canônico (chaves ordenadas, sem espaço, sem float) com `seq`, `hash_anterior`
e `hash = sha256(entrada sem 'hash')`. Tipos:

- `decisao`: corte T, fingerprint do snapshot, versão do código, política + versão, seed, propostas
  e diagnósticos (as propostas carregam `executavel=false`);
- `resultado`: referência ao hash da decisão, instante de maturidade (D+k) e o resultado maduro
  observado depois (e, com simulador, o contrafactual verdadeiro).

Não há método de atualizar ou apagar. O sink JSONL só escreve UM arquivo dentro do diretório
dado (nome sem separador), em modo append, e recusa continuar um arquivo cuja cadeia não confere.
Nenhum sink externo existe neste pacote (`externo = False` é exigido, como no coletor seguro da B).
Sem relógio de parede: re-executar o mesmo replay produz os mesmos bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Optional, Protocol

from volc_dil.contracts.fingerprint import json_canonico

GENESE = "0" * 64
ESQUEMA_LEDGER = "volc-dil.shadow.ledger.v1"


class LedgerCorrompido(RuntimeError):
    pass


class SinkProibido(RuntimeError):
    pass


class SinkLedger(Protocol):
    externo: bool

    def anexar(self, linha: str) -> None: ...


def _hash(entrada: dict) -> str:
    return hashlib.sha256(json_canonico({k: v for k, v in entrada.items() if k != "hash"}).encode("utf-8")).hexdigest()


def _sem_float(x) -> None:
    if isinstance(x, float):
        raise TypeError("float proibido no ledger")
    if isinstance(x, dict):
        for v in x.values():
            _sem_float(v)
    elif isinstance(x, list):
        for v in x:
            _sem_float(v)


class SinkJsonl:
    """Arquivo `<diretorio>/<nome>` em append. Único ponto de escrita em disco do pacote."""

    externo = False

    def __init__(self, diretorio: os.PathLike | str, nome: str = "ledger.jsonl") -> None:
        if not nome or os.sep in nome or (os.altsep and os.altsep in nome) or nome in (".", "..") or nome.startswith("."):
            raise SinkProibido(f"nome de arquivo inválido para o ledger: {nome!r}")
        self.diretorio = Path(diretorio).resolve()
        if not self.diretorio.is_dir():
            raise SinkProibido(f"diretório do ledger não existe: {self.diretorio}")
        self.caminho = self.diretorio / nome
        if self.caminho.is_symlink():
            raise SinkProibido("ledger não pode ser link simbólico")

    def linhas_existentes(self) -> list[str]:
        if not self.caminho.exists():
            return []
        return self.caminho.read_text(encoding="utf-8").splitlines()

    def anexar(self, linha: str) -> None:
        with open(self.caminho, "a", encoding="utf-8", newline="\n") as f:
            f.write(linha + "\n")


def verificar_linhas(linhas: Iterable[str]) -> tuple[int, str]:
    """Confere a cadeia; devolve (n, último hash)."""
    anterior, n = GENESE, 0
    for i, txt in enumerate(linhas):
        e = json.loads(txt)
        if json_canonico(e) != txt:
            raise LedgerCorrompido(f"linha {i}: não é JSON canônico")
        if e.get("seq") != i or e.get("hash_anterior") != anterior or e.get("hash") != _hash(e):
            raise LedgerCorrompido(f"linha {i}: cadeia de hash quebrada")
        anterior, n = e["hash"], i + 1
    return n, anterior


def verificar_cadeia(caminho: os.PathLike | str) -> int:
    return verificar_linhas(Path(caminho).read_text(encoding="utf-8").splitlines())[0]


class LedgerShadow:
    """Append-only. `entradas` devolve cópia; o sink (se houver) recebe cada linha uma vez."""

    def __init__(self, sink: Optional[SinkLedger] = None) -> None:
        if sink is not None and getattr(sink, "externo", None) is not False:
            raise SinkProibido("sink do ledger precisa declarar externo = False (não há sink externo)")
        self._sink = sink
        self._linhas: list[str] = []
        self._ultimo = GENESE
        self._decisoes: set[str] = set()
        if isinstance(sink, SinkJsonl):
            existentes = sink.linhas_existentes()
            n, ult = verificar_linhas(existentes)
            self._linhas = list(existentes)
            self._ultimo = ult
            self._decisoes = {e["hash"] for e in map(json.loads, existentes) if e["tipo"] == "decisao"}

    def __len__(self) -> int:
        return len(self._linhas)

    @property
    def ultimo_hash(self) -> str:
        return self._ultimo

    @property
    def linhas(self) -> tuple[str, ...]:
        return tuple(self._linhas)

    @property
    def entradas(self) -> tuple[dict, ...]:
        return tuple(json.loads(x) for x in self._linhas)

    def bytes(self) -> bytes:
        return "".join(x + "\n" for x in self._linhas).encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.bytes()).hexdigest()

    def _anexar(self, corpo: dict) -> dict:
        _sem_float(corpo)
        entrada = dict(corpo)
        entrada["esquema"] = ESQUEMA_LEDGER
        entrada["seq"] = len(self._linhas)
        entrada["hash_anterior"] = self._ultimo
        entrada["hash"] = _hash(entrada)
        linha = json_canonico(entrada)
        if self._sink is not None:
            self._sink.anexar(linha)
        self._linhas.append(linha)
        self._ultimo = entrada["hash"]
        if entrada["tipo"] == "decisao":
            self._decisoes.add(entrada["hash"])
        return entrada

    def registrar_decisao(self, *, as_of: str, fingerprint_corte: str, versao_codigo: str, politica: str,
                          versao_politica: str, seed: Optional[int], decisao: dict) -> dict:
        return self._anexar({"tipo": "decisao", "as_of": as_of, "fingerprint_corte": fingerprint_corte,
                             "versao_codigo": versao_codigo, "politica": politica, "versao_politica": versao_politica,
                             "seed": seed, "propostas": decisao["propostas"], "diagnosticos": decisao["diagnosticos"]})

    def registrar_resultado(self, *, ref_hash: str, as_of_maduro: str, k_dias: int, resultado: dict) -> dict:
        if ref_hash not in self._decisoes:
            raise LedgerCorrompido("resultado sem decisão de referência no ledger")
        return self._anexar({"tipo": "resultado", "ref_hash": ref_hash, "as_of_maduro": as_of_maduro, "k_dias": k_dias,
                             "resultado": resultado})
