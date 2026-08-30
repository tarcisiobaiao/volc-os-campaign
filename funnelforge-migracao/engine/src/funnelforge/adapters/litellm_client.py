from __future__ import annotations
import time
from litellm import completion, completion_cost
from funnelforge.ports.llm import LLMResult


def _uris_do_grounding(resp) -> list[str]:
    """As URIs que a busca do provedor de fato abriu.

    O Gemini com `googleSearch` devolve `groundingMetadata` junto com o texto, e
    o LiteLLM o guarda em `_hidden_params["vertex_ai_grounding_metadata"]`. A
    forma exata do dicionário varia com a versão da API — já vi as URIs em
    `groundingChunks[].web.uri` e em `groundingAttributions[].web.uri` —, então
    a varredura é DEFENSIVA: procura qualquer chave `uri` em qualquer
    profundidade e não presume esquema.

    Devolve na ordem em que apareceram, sem repetir. Lista vazia é resposta
    legítima: nem toda chamada aciona a busca.
    """
    bruto = getattr(resp, "_hidden_params", None) or {}
    meta = bruto.get("vertex_ai_grounding_metadata")
    if not meta:
        return []
    achadas: list[str] = []

    def varrer(no) -> None:
        if isinstance(no, dict):
            for chave, valor in no.items():
                if chave == "uri" and isinstance(valor, str) and valor.startswith("http"):
                    if valor not in achadas:
                        achadas.append(valor)
                else:
                    varrer(valor)
        elif isinstance(no, (list, tuple)):
            for item in no:
                varrer(item)

    varrer(meta)
    return achadas


class LiteLLMClient:
    # Transient 429/5xx (e.g. `OpenAIException InternalServerError`) must not
    # crash a step outright -- LiteLLM retries the SAME model with backoff
    # before giving up / falling over to `fallbacks`.
    #
    # UM retry, não dois (Frente 3). A retentativa de transporte agora existe em
    # DOIS lugares: aqui (imediata, para o soluço) e no `Runner` (com espera
    # exponencial e classificação de erro). Com 2 aqui × 3 tentativas do runner,
    # um único passo chegava a ~9 requisições — e as internas são INVISÍVEIS ao
    # ledger, porque `completion_cost` só mede a resposta final. Deixar 1 aqui
    # mantém a resiliência ao blip e devolve a contagem ao lugar onde ela é
    # medida.
    NUM_RETRIES = 1
    TIMEOUT_S = 120

    def complete(self, model, fallbacks, messages, temperature,
                 response_schema=None, web_search=False):
        kwargs = {"model": model, "messages": messages, "temperature": temperature,
                  "num_retries": self.NUM_RETRIES, "timeout": self.TIMEOUT_S}
        if fallbacks:
            kwargs["fallbacks"] = fallbacks
        if web_search:
            # Gemini google-search grounding tool (LiteLLM passes it through to
            # the Google AI API). Ignored gracefully by providers that lack it.
            kwargs["tools"] = [{"googleSearch": {}}]
        t0 = time.perf_counter()
        resp = completion(**kwargs)
        t1 = time.perf_counter()
        text = resp.choices[0].message.content or ""
        citations = _uris_do_grounding(resp)
        used = getattr(resp, "model", model) or model
        usage = getattr(resp, "usage", None)
        try:
            cost = float(completion_cost(resp))
        except Exception:  # noqa: BLE001 - cost is best-effort telemetry
            cost = 0.0
        return LLMResult(
            text=text, model_used=used, citations=citations,
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            cost_usd=cost, latency_ms=int((t1 - t0) * 1000),
        )
