"""Orquestra uma geração atômica: LLM propõe, Pydantic e regras decidem."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.llm.json_defensivo import extract_json

from .conhecimento import hash_da_base
from .contrato import PedidoDoAgente, ReciboDeValidacao, SaidaDoAgente
from .prompts import SYSTEM_PROMPT, montar_missao
from .validacao import SaidaCriativaInvalida, validar_saida


class ClienteDeModelo(Protocol):
    name: str
    model: str

    async def complete(self, system: str, user: str) -> str: ...


class RespostaDoModeloInvalida(RuntimeError):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("o modelo não produziu um lote criativo válido")


@dataclass(frozen=True)
class ResultadoDoAgente:
    saida: SaidaDoAgente
    modelo: str
    tentativas: int
    request_sha256: str
    knowledge_sha256: str


def hash_do_pedido(pedido: PedidoDoAgente) -> str:
    material = pedido.model_dump(mode="json")
    cru = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(cru.encode("utf-8")).hexdigest()


class AgenteCriativoMeta:
    """Sem fallback realista: falta de modelo é falha explícita, nunca conteúdo falso."""

    def __init__(self, cliente: ClienteDeModelo):
        self.cliente = cliente

    async def executar(self, pedido: PedidoDoAgente) -> ResultadoDoAgente:
        erros: list[str] = []
        for tentativa in (1, 2):
            texto = await self.cliente.complete(
                SYSTEM_PROMPT,
                montar_missao(pedido, erros_anteriores=erros),
            )
            try:
                bruto = extract_json(texto)
                saida = SaidaDoAgente.model_validate(bruto)
                validar_saida(pedido, saida)
            except (ValueError, ValidationError, SaidaCriativaInvalida) as exc:
                if isinstance(exc, SaidaCriativaInvalida):
                    erros = exc.erros
                elif isinstance(exc, ValidationError):
                    erros = [
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                        for e in exc.errors()[:20]
                    ]
                else:
                    erros = [str(exc)]
                continue
            # O recibo é do código, não do modelo. Mesmo que o JSON proponha
            # "valido": true, ele só nasce aqui depois das contraprovas.
            saida = saida.model_copy(
                update={
                    "recibo": ReciboDeValidacao(
                        valido=True,
                        codigos=[
                            "META_CREATIVE_SCHEMA_VALID",
                            "META_CREATIVE_FACT_REFS_VALID",
                            "META_CREATIVE_BATCH_DIVERSITY_VALID",
                            "META_CREATIVE_FROZEN_DECISIONS_PRESERVED",
                        ],
                        avisos=[],
                    )
                }
            )
            return ResultadoDoAgente(
                saida=saida,
                modelo=getattr(self.cliente, "model", getattr(self.cliente, "name", "unknown")),
                tentativas=tentativa,
                request_sha256=hash_do_pedido(pedido),
                knowledge_sha256=hash_da_base(),
            )
        raise RespostaDoModeloInvalida(erros)
