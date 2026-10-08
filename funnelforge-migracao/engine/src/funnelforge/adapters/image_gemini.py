"""Geracao de imagem pelo SDK oficial ``google-genai``.

Este adapter implementa o mesmo port usado pelo gerador OpenAI. Ele existe
para o motor continuar completo quando o texto usa a sessao ChatGPT, mas a
ferramenta de imagem nao esta liberada nessa sessao. A chave Gemini continua
vindo do ambiente; nunca entra no perfil do run nem nos recibos.
"""
from __future__ import annotations

import time
from typing import Any

from funnelforge.adapters.image_pricing import (
    FONTE_DESCONHECIDA,
    ImageUsage,
    image_cost_usd,
)


def _aspect_ratio(size: str) -> str:
    """Converte o tamanho do motor para um aspect ratio aceito pelo Gemini."""
    try:
        width, height = (int(part) for part in size.lower().split("x", 1))
    except (TypeError, ValueError):
        return "16:9"
    known = {
        (1, 1): "1:1",
        (2, 3): "2:3",
        (3, 2): "3:2",
        (9, 16): "9:16",
        (16, 9): "16:9",
        (3, 4): "3:4",
        (4, 3): "4:3",
    }
    from math import gcd

    divisor = gcd(width, height)
    return known.get((width // divisor, height // divisor), "16:9")


class GeminiImageGenerator:
    """Gera bytes de imagem e expoe telemetria honesta em ``last_usage``."""

    def __init__(self, api_key: str, *, model: str = "gemini-3.1-flash-image-preview",
                 quality: str = "medium", client: Any | None = None) -> None:
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model.removeprefix("gemini/")
        self.quality = quality
        self.last_usage: ImageUsage | None = None

    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        from google.genai import types

        started = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=_aspect_ratio(size),
                    image_size="1K",
                ),
            ),
        )
        image = None
        for part in getattr(response, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                image = bytes(inline.data)
                break
        if not image:
            raise RuntimeError(
                f"{self.model} concluiu sem devolver imagem; o motor nao aceita ativo vazio."
            )

        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        raw_usage = {"input_tokens": prompt_tokens, "output_tokens": output_tokens}
        cost, source = image_cost_usd(
            model=self.model,
            size=size,
            quality=self.quality,
            usage=raw_usage,
        )
        # Se a tabela local ainda nao conhece o modelo, nao inventamos preco.
        # O ledger registra custo desconhecido, em vez de chamar API faturada de gratis.
        self.last_usage = ImageUsage(
            cost_usd=cost,
            cost_source=source or FONTE_DESCONHECIDA,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=self.model,
            size=size,
            quality=self.quality,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
        )
        return image
