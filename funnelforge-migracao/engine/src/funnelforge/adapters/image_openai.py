from __future__ import annotations
import base64
import time

import httpx

from funnelforge.adapters.image_pricing import ImageUsage, image_cost_usd


class OpenAIImageGenerator:
    """Gera a imagem na API de imagens da OpenAI e REPORTA quanto custou.

    A telemetria fica em `last_usage` (um `ImageUsage`), lido por
    `steps.step_image` — mesmo contrato opcional que o `ResearchProvider` já
    usa (`last_cost_usd` e amigos, ver `steps.step_research`). A assinatura de
    `generate` NÃO muda: continua devolvendo bytes, então qualquer
    `ImageGenerator` (inclusive os fakes dos testes) segue válido.

    O preço vem da tabela do litellm a partir do `usage` que a própria API
    devolve — ver `adapters/image_pricing.py`. Quando não dá para saber, o custo
    fica 0.0 com fonte "desconhecido" e o passo mostra isso no relatório, em vez
    de fingir que a imagem foi de graça."""

    def __init__(self, api_key: str, model: str = "gpt-image-2", quality: str = "medium"):
        self.api_key = api_key
        self.model = model
        self.quality = quality
        self.last_usage: ImageUsage | None = None

    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        t0 = time.perf_counter()
        r = httpx.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "prompt": prompt, "size": size,
                  "quality": self.quality},
            timeout=180,
        )
        r.raise_for_status()
        payload = r.json()
        latency_ms = int((time.perf_counter() - t0) * 1000)
        usage = payload.get("usage") if isinstance(payload, dict) else None
        usage = usage if isinstance(usage, dict) else None
        cost, source = image_cost_usd(
            model=self.model, size=size, quality=self.quality, usage=usage)
        self.last_usage = ImageUsage(
            cost_usd=cost, cost_source=source, latency_ms=latency_ms,
            model=self.model, size=size, quality=self.quality,
            input_tokens=int((usage or {}).get("input_tokens") or 0),
            output_tokens=int((usage or {}).get("output_tokens") or 0),
        )
        return base64.b64decode(payload["data"][0]["b64_json"])
