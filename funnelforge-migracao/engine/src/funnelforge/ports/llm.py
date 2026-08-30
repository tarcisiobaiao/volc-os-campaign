from __future__ import annotations
from typing import Protocol
from pydantic import BaseModel


class LLMResult(BaseModel):
    text: str
    model_used: str
    # AS CITAÇÕES QUE O PROVEDOR DEVOLVEU — não as que o modelo digitou.
    #
    # Quando a busca do provedor roda (Gemini com `googleSearch`, Perplexity com
    # `citations`), a resposta traz, junto com o texto, as URIs que o modelo de
    # fato abriu. Elas chegavam e eram descartadas: o cliente lia só
    # `choices[0].message.content`. O modelo então tinha de REDIGITAR os
    # endereços dentro do JSON, de memória — e é aí que nasce
    # `gov.br/.../margem-consignavel-regras-e-limites-a-partir-de-2026`:
    # plausível na forma, 404 no mundo.
    #
    # Medido no primeiro run real: 2 de 3 fontes primárias eram invenção, a
    # página morreu e US$ 0,39 foram embora — com a citação verdadeira
    # trafegando na MESMA resposta, paga e ignorada.
    citations: list[str] = []
    parsed: object | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class LLMClient(Protocol):
    def complete(self, model: str, fallbacks: list[str], messages: list[dict],
                 temperature: float, response_schema: type | None = None,
                 web_search: bool = False) -> LLMResult: ...
