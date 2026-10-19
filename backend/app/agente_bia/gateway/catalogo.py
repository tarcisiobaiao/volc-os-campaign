"""Catálogo de capacidades do VOLC Agent Gateway.

## Regras do catálogo

1. Capacidade só entra com `efeito="leitura"`. Registrar outra coisa levanta
   `CapacidadeProibida` — a V1 não tem caminho de mutação, nem desligado.
2. Entrada é modelo Pydantic com `extra="forbid"`: parâmetro desconhecido é
   recusado, nunca ignorado. Não há campo de SQL, tabela, URL, tenant ou dono:
   quem chama é a `Identidade` apurada pelo servidor.
3. Papel conferido NO SERVIDOR, antes da validação da entrada (403 não ensina
   o formato a quem não pode usar).
4. A saída é validada pelo modelo de saída antes de sair. Uma implementação
   que devolva campo a mais ou sem frescor quebra aqui, não no cliente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Literal, Mapping, Type

from pydantic import BaseModel, ValidationError

from app.seguranca.identidade import Identidade

Efeito = Literal["leitura"]


class CapacidadeProibida(ValueError):
    """Tentativa de registrar capacidade que não é de leitura."""


class CapacidadeDesconhecida(LookupError):
    pass


class PapelInsuficiente(PermissionError):
    pass


class EntradaRecusada(ValueError):
    def __init__(self, erros: List[Dict[str, str]]) -> None:
        super().__init__("entrada recusada")
        self.erros = erros


@dataclass(frozen=True)
class Capacidade:
    nome: str
    descricao: str
    efeito: str
    papel_minimo: str
    entrada: Type[BaseModel]
    saida: Type[BaseModel]
    executar: Callable[[Identidade, BaseModel], Awaitable[BaseModel]]


def erros_sem_valor(exc: ValidationError) -> List[Dict[str, str]]:
    """Erros de validação SEM o campo `input` (que carrega o valor recusado)."""
    return [{"campo": ".".join(str(p) for p in e.get("loc", ())), "erro": str(e.get("msg", ""))}
            for e in exc.errors()]


class Catalogo:
    def __init__(self) -> None:
        self._capacidades: Dict[str, Capacidade] = {}

    def registrar(self, cap: Capacidade) -> None:
        if cap.efeito != "leitura":
            raise CapacidadeProibida(f"{cap.nome}: efeito {cap.efeito!r} não é permitido na V1")
        if cap.entrada.model_config.get("extra") != "forbid":
            raise CapacidadeProibida(f"{cap.nome}: entrada precisa recusar campo extra")
        if cap.nome in self._capacidades:
            raise CapacidadeProibida(f"{cap.nome}: já registrada")
        self._capacidades[cap.nome] = cap

    def nomes(self) -> List[str]:
        return sorted(self._capacidades)

    def descrever(self) -> List[Dict[str, Any]]:
        return [{
            "nome": c.nome,
            "descricao": c.descricao,
            "efeito": c.efeito,
            "papel_minimo": c.papel_minimo,
            "entrada": c.entrada.model_json_schema(),
            "saida": c.saida.model_json_schema(),
        } for c in (self._capacidades[n] for n in self.nomes())]

    def validar_entrada(self, nome: str, argumentos: Mapping[str, Any]) -> BaseModel:
        cap = self._capacidades.get(nome)
        if cap is None:
            raise CapacidadeDesconhecida(nome)
        try:
            return cap.entrada.model_validate(dict(argumentos))
        except ValidationError as exc:
            raise EntradaRecusada(erros_sem_valor(exc)) from exc

    async def invocar(self, identidade: Identidade, nome: str,
                      argumentos: Mapping[str, Any]) -> Dict[str, Any]:
        cap = self._capacidades.get(nome)
        if cap is None:
            raise CapacidadeDesconhecida(nome)
        if cap.papel_minimo == "ADMIN" and not identidade.e_admin:
            raise PapelInsuficiente(nome)
        entrada = self.validar_entrada(nome, argumentos)
        saida = await cap.executar(identidade, entrada)
        # Revalida pelo modelo de saída: a implementação não escolhe o contrato.
        return cap.saida.model_validate(saida.model_dump()).model_dump(mode="json")
