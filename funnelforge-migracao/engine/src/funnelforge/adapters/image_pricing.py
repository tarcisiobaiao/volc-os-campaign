"""Preço REAL de uma geração de imagem — sem número inventado.

A geração de imagem é ~12% do custo de um funil e não aparecia em telemetria
nenhuma: as linhas `image_pN` do `report.md` são só a chamada de TEXTO que
escreve o prompt; a imagem saía por um `httpx.post` cru, fora do `run_llm_step`,
sem devolver custo.

De onde vem o preço, nesta ordem, sem chutar:

1) **Tokens de uso + tabela do litellm.** A API de imagens da OpenAI devolve um
   bloco `usage` (`input_tokens`, `output_tokens`, `input_tokens_details`), e o
   litellm carrega `litellm.model_cost` (o `model_prices_and_context_window.json`
   que já vem dentro do pacote — consulta LOCAL, sem rede). Para os modelos
   tarifados por token — é o caso do `gpt-image-2`, o default do `RunConfig` — a
   entrada traz `output_cost_per_image_token` / `input_cost_per_image_token` /
   `input_cost_per_token`. Custo = soma direta.

2) **Preço por imagem do litellm.** Modelos tarifados por imagem (gpt-image-1,
   dall-e-3) estão na tabela em chaves do tipo `medium/1536-x-1024/gpt-image-1`.
   Quem sabe montar essa chave é o próprio litellm:
   `litellm.cost_calculator.default_image_cost_calculator(model=, quality=,
   size=, n=1)`. Conferido nesta máquina: gpt-image-1 medium 1536x1024 → 0.063.

3) **Não sei.** Modelo fora da tabela E sem `usage` na resposta: custo 0.0 com
   `fonte="desconhecido"`, e o passo entra no relatório com um aviso explícito.
   Um zero silencioso mentindo "de graça" é exatamente o defeito que este módulo
   existe para não repetir.

Como consultar a tabela na mão (quando um modelo novo entrar):

    python -c "import litellm,json;print(json.dumps(litellm.model_cost['gpt-image-2'],indent=1))"
    python -c "import litellm;print([k for k in litellm.model_cost if 'gpt-image' in k])"

Se o modelo novo não estiver lá, o caminho é atualizar o litellm
(`pip install -U litellm`) — NÃO escrever o preço à mão aqui, que envelheceria
em silêncio e voltaria a mentir.
"""
from __future__ import annotations

from dataclasses import dataclass

# Rótulos de procedência do preço (o operador lê isso no relatório).
FONTE_TOKENS = "tabela litellm (tokens de uso)"
FONTE_POR_IMAGEM = "tabela litellm (preço por imagem)"
FONTE_DESCONHECIDA = "desconhecido"


@dataclass
class ImageUsage:
    """Telemetria de UMA geração de imagem — o que o ledger precisa saber."""
    cost_usd: float = 0.0
    cost_source: str = FONTE_DESCONHECIDA
    latency_ms: int = 0
    model: str = ""
    size: str = ""
    quality: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def _model_cost_entry(model: str) -> dict | None:
    """Entrada de `litellm.model_cost` para `model` (tentando também sem o
    prefixo de provider). Import preguiçoso: importar litellm custa ~1s e nem
    todo caminho que usa este módulo precisa dele."""
    try:
        import litellm
    except Exception:  # noqa: BLE001 - sem litellm não há tabela; preço fica desconhecido
        return None
    table = getattr(litellm, "model_cost", {}) or {}
    for candidate in (model, model.split("/")[-1]):
        entry = table.get(candidate)
        if isinstance(entry, dict):
            return entry
    return None


def _cost_from_tokens(entry: dict, usage: dict) -> float | None:
    """Custo pelos tokens que a PRÓPRIA API reportou. None quando a entrada da
    tabela não tem preço por token OU a API não reportou uso."""
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    details = usage.get("input_tokens_details") or {}
    text_tokens = int(details.get("text_tokens") or 0)
    image_tokens = int(details.get("image_tokens") or 0)
    if text_tokens + image_tokens != input_tokens:
        # Sem detalhamento confiável: trata tudo como token de texto de entrada.
        text_tokens, image_tokens = input_tokens, 0

    per_text_in = entry.get("input_cost_per_token")
    per_image_in = entry.get("input_cost_per_image_token", per_text_in)
    per_out = entry.get("output_cost_per_image_token", entry.get("output_cost_per_token"))
    if per_out is None and per_text_in is None:
        return None
    cost = text_tokens * float(per_text_in or 0.0)
    cost += image_tokens * float(per_image_in or 0.0)
    cost += output_tokens * float(per_out or 0.0)
    return cost


def image_cost_usd(*, model: str, size: str, quality: str,
                   usage: dict | None) -> tuple[float, str]:
    """(custo_usd, fonte_do_preço). Nunca levanta; nunca inventa número."""
    entry = _model_cost_entry(model)
    if entry is not None and usage:
        cost = _cost_from_tokens(entry, usage)
        if cost is not None:
            return round(cost, 6), FONTE_TOKENS
    try:
        from litellm.cost_calculator import default_image_cost_calculator

        cost = float(default_image_cost_calculator(
            model=model, quality=quality or None, size=size or None, n=1))
        return round(cost, 6), FONTE_POR_IMAGEM
    except Exception:  # noqa: BLE001 - fora da tabela: assumimos NÃO SABER
        return 0.0, FONTE_DESCONHECIDA
