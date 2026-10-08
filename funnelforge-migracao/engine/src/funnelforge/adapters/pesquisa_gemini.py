"""Pesquisa do DOSSIÊ pelo SDK oficial `google-genai` — só este passo.

O canário de 07/10/2026 (LiteLLM + `tools=[{"googleSearch": {}}]`, JSON pedido
no texto) voltou vazio 3/3 e não deixou como saber por quê. Aqui:

* Google Search + Structured Output nativos (`response_mime_type`
  application/json + `response_json_schema` derivado de `FatosDoDossie`);
* modelo exato, sem fallback de modelo, sem retentativa;
* TODA chamada deixa metadados sanitizados: finishReason/finishMessage,
  promptFeedback, safetyRatings, consultas, groundingChunks/Supports, tokens,
  modelo servido e o texto devolvido (truncado). Nunca credencial;
* fonte candidata = só as URIs do `groundingMetadata` (redirect resolvido); o
  texto do modelo não promove URL a fonte;
* resposta que não parou em STOP, sem busca, sem grounding ou fora do schema
  é DEFEITO — o dossiê aborta, não "acha zero fatos".

Desvio controlado, UMA vez, só para RECITATION com busca feita ou para
incompatibilidade de Structured Output com a ferramenta: (1) pesquisa grounded
em prosa curta parafraseada; (2) estruturação dessa prosa no schema, SEM busca,
limitada às fontes da chamada (1). Não é retentativa genérica.

Autenticação: a mesma disponível no motor, `GEMINI_API_KEY` (`api_key`).
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from funnelforge.config.settings import StepConfig

MAX_TOKENS_DE_SAIDA = 32768
LIMITE_DO_TEXTO_NO_RECIBO = 1500


class FatoPesquisado(BaseModel):
    afirmacao: str
    tipo: str
    valor: str = ""
    unidade: str = ""
    fonte: str
    vigente_desde: str = ""
    dispositivo: str = ""
    evidencia_resumida: str = Field(default="", max_length=300)
    paginas: list[str] = []
    requisitos: list[str] = []


class FatosDoDossie(BaseModel):
    fatos: list[FatoPesquisado] = []


SCHEMA = FatosDoDossie.model_json_schema()


def _nome(valor: Any) -> str:
    if valor is None:
        return ""
    return str(getattr(valor, "name", None) or valor)


def _texto(resp: Any) -> str:
    partes = []
    for cand in (getattr(resp, "candidates", None) or [])[:1]:
        conteudo = getattr(cand, "content", None)
        for parte in (getattr(conteudo, "parts", None) or []):
            if getattr(parte, "text", None) and not getattr(parte, "thought", False):
                partes.append(parte.text)
    return "".join(partes)


def metadados_sanitizados(resp: Any, chamada: str, latencia_ms: int) -> dict:
    """O recibo de UMA chamada. Sem credencial, sem payload integral."""
    cand = (getattr(resp, "candidates", None) or [None])[0]
    gm = getattr(cand, "grounding_metadata", None) if cand is not None else None
    pf = getattr(resp, "prompt_feedback", None)
    um = getattr(resp, "usage_metadata", None)
    chunks = [c.web for c in (getattr(gm, "grounding_chunks", None) or [])
              if getattr(c, "web", None) is not None]
    texto = _texto(resp)

    def tok(nome: str) -> int:
        return int(getattr(um, nome, 0) or 0) if um is not None else 0

    return {
        "chamada": chamada,
        "modelo_servido": str(getattr(resp, "model_version", "") or ""),
        "response_id": str(getattr(resp, "response_id", "") or ""),
        "finish_reason": _nome(getattr(cand, "finish_reason", None)) if cand else "SEM_CANDIDATO",
        "finish_message": str(getattr(cand, "finish_message", "") or "") if cand else "",
        "block_reason": _nome(getattr(pf, "block_reason", None)),
        "block_reason_message": str(getattr(pf, "block_reason_message", "") or ""),
        "safety_ratings": [
            {"categoria": _nome(getattr(r, "category", None)),
             "probabilidade": _nome(getattr(r, "probability", None)),
             "bloqueado": bool(getattr(r, "blocked", False))}
            for r in (getattr(cand, "safety_ratings", None) or [])],
        # Presença e campos preenchidos do groundingMetadata: o microprobe de
        # 07/10 voltou com URL de redirect do grounding NO TEXTO e 0 chunks —
        # sem isto não se sabe se o metadado veio nulo ou com outro formato.
        "grounding_metadata_presente": gm is not None,
        "grounding_metadata_campos": sorted(
            k for k, v in (gm.model_dump(exclude_none=True).items() if gm is not None else [])
            if v not in ([], {}, "")),
        "redirect_do_grounding_no_texto": "grounding-api-redirect" in texto,
        "web_search_queries": [str(q) for q in (getattr(gm, "web_search_queries", None) or [])],
        "grounding_chunks": len(chunks),
        "grounding_supports": len(getattr(gm, "grounding_supports", None) or []),
        "fontes_do_grounding": [{"uri": str(w.uri or ""), "titulo": str(w.title or "")}
                                for w in chunks],
        "tokens": {"entrada": tok("prompt_token_count"), "saida": tok("candidates_token_count"),
                   "raciocinio": tok("thoughts_token_count"),
                   "ferramenta": tok("tool_use_prompt_token_count"),
                   "total": tok("total_token_count")},
        "latencia_ms": latencia_ms,
        "texto_chars": len(texto),
        "texto_devolvido": texto[:LIMITE_DO_TEXTO_NO_RECIBO],
        "_texto": texto,                 # íntegra para o parse; sai antes do recibo
    }


def _preco(modelo: str) -> tuple[float, float]:
    try:
        from litellm import model_cost
    except Exception:  # noqa: BLE001
        return 0.0, 0.0
    tabela = model_cost.get(f"gemini/{modelo}") or {}
    return (float(tabela.get("input_cost_per_token") or 0.0),
            float(tabela.get("output_cost_per_token") or 0.0))


def custo_de_tokens(meta: dict, modelo: str) -> float:
    """Tokens a preço de tabela (LiteLLM): entrada + ferramenta como entrada;
    saída + raciocínio como saída. As consultas de busca são somadas à parte."""
    entrada, saida = _preco(modelo)
    t = meta.get("tokens") or {}
    return round(entrada * (t.get("entrada", 0) + t.get("ferramenta", 0))
                 + saida * (t.get("saida", 0) + t.get("raciocinio", 0)), 6)


def defeito_da_chamada(meta: dict, *, exige_busca: bool) -> str:
    if meta.get("erro"):
        return f"erro do provedor: {meta['erro']}"
    if meta.get("block_reason"):
        return (f"prompt bloqueado: {meta['block_reason']} "
                f"{meta.get('block_reason_message', '')}").strip()
    if meta.get("finish_reason") != "STOP":
        return (f"finish_reason={meta.get('finish_reason')} "
                f"{meta.get('finish_message', '')}").strip()
    if exige_busca and not meta.get("web_search_queries"):
        return "a busca do Google não foi executada (0 webSearchQueries)"
    if exige_busca and not meta.get("grounding_chunks"):
        return "sem groundingChunks: nenhuma fonte comprovada pelo provedor"
    if not meta.get("texto_chars"):
        return "texto vazio com finish_reason=STOP"
    return ""


def _cliente():
    from google import genai
    from google.genai import types

    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("GEMINI_API_KEY ausente: a pesquisa do dossiê não roda sem ela")
    return genai.Client(api_key=chave, http_options=types.HttpOptions(timeout=180_000))


def _chamar(cliente: Any, modelo: str, prompt: str, *, nome: str, temperatura: float,
            buscar: bool, estruturar: bool, max_tokens: int) -> tuple[Any, dict]:
    from google.genai import errors, types

    config = types.GenerateContentConfig(
        temperature=temperatura, max_output_tokens=max_tokens,
        tools=[types.Tool(google_search=types.GoogleSearch())] if buscar else None,
        response_mime_type="application/json" if estruturar else None,
        response_json_schema=SCHEMA if estruturar else None)
    inicio = time.perf_counter()
    try:
        resp = cliente.models.generate_content(model=modelo, contents=prompt, config=config)
    except errors.APIError as exc:
        lat = int((time.perf_counter() - inicio) * 1000)
        return None, {"chamada": nome, "latencia_ms": lat, "codigo": getattr(exc, "code", None),
                      "erro": f"{getattr(exc, 'code', '')} {getattr(exc, 'status', '')}: "
                              f"{str(getattr(exc, 'message', '') or exc)[:300]}"}
    return resp, metadados_sanitizados(resp, nome, int((time.perf_counter() - inicio) * 1000))


def _incompativel_com_structured_output(meta: dict) -> bool:
    erro = str(meta.get("erro") or "").lower()
    return meta.get("codigo") == 400 and any(
        p in erro for p in ("mime", "json", "schema", "structured"))


def _prompt_em_prosa(prompt: str) -> str:
    return (prompt + "\n\nFORMATO DESTA RESPOSTA: prosa curta, um parágrafo por fato, com "
            "palavras próprias (paráfrase; nenhuma citação literal). Para cada fato diga o "
            "valor, a unidade, a vigência declarada, a página e o requisito que ele cobre, e a "
            "URL de onde veio.")


def _prompt_de_estruturacao(prosa: str, fontes: list[str]) -> str:
    lista = "\n".join(f"- {u}" for u in fontes)
    return ("Estruture no schema SOMENTE os fatos do texto abaixo, que já foi pesquisado. Não "
            "acrescente fato, número ou fonte. `fonte` tem de ser uma destas URLs:\n"
            f"{lista}\n\nTEXTO PESQUISADO:\n{prosa}")


def pesquisar_dossie_nativo(cfg: StepConfig, assunto: str, paginas: list[dict],
                            faltantes: list[dict] | None = None, *, cliente: Any = None,
                            max_tokens: int = MAX_TOKENS_DE_SAIDA):
    """Uma rodada do dossiê pelo SDK nativo -> `RespostaDaPesquisa` (a mesma
    porta do caminho LiteLLM)."""
    from funnelforge.adapters.research_perplexity import _UA, _canonica, _prompt_do_funil
    from funnelforge.pipeline.dossie import RespostaDaPesquisa

    modelo = cfg.model.split("/", 1)[1] if "/" in cfg.model else cfg.model
    cliente = cliente if cliente is not None else _cliente()
    temperatura = float(cfg.temperature)
    prompt = _prompt_do_funil(assunto, paginas, faltantes, estruturado=True)
    metas: list[dict] = []

    resp, meta = _chamar(cliente, modelo, prompt, nome="estruturada_com_busca",
                         temperatura=temperatura, buscar=True, estruturar=True,
                         max_tokens=max_tokens)
    metas.append(meta)
    final, base = meta, meta
    desvio = ("recitation" if meta.get("finish_reason") == "RECITATION"
              and meta.get("web_search_queries") else
              "structured_output_incompativel" if _incompativel_com_structured_output(meta)
              else "")
    if desvio:
        _, prosa = _chamar(cliente, modelo, _prompt_em_prosa(prompt), nome=f"prosa_com_busca:{desvio}",
                           temperatura=temperatura, buscar=True, estruturar=False,
                           max_tokens=max_tokens)
        metas.append(prosa)
        base = final = prosa
        if not defeito_da_chamada(prosa, exige_busca=True):
            fontes = [f["uri"] for f in prosa["fontes_do_grounding"]]
            _, estrut = _chamar(cliente, modelo, _prompt_de_estruturacao(prosa["_texto"], fontes),
                                nome="estruturacao_sem_busca", temperatura=temperatura,
                                buscar=False, estruturar=True, max_tokens=max_tokens)
            metas.append(estrut)
            final = estrut

    defeito = defeito_da_chamada(base, exige_busca=True) or (
        defeito_da_chamada(final, exige_busca=False) if final is not base else "")
    dados: dict = {"fatos": []}
    if not defeito:
        try:
            dados = FatosDoDossie.model_validate_json(final.get("_texto", "")).model_dump()
        except ValidationError as exc:
            defeito = f"structured output fora do schema: {exc.errors()[0].get('msg', '')[:200]}"
    for m in metas:
        m.pop("_texto", None)
    with httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": _UA}) as c:
        citacoes = list(dict.fromkeys(_canonica(f["uri"], c)
                                      for f in base.get("fontes_do_grounding", [])))
    custo = round(sum(custo_de_tokens(m, modelo) for m in metas), 6)
    return RespostaDaPesquisa(
        dados=dados, citacoes=citacoes, modelo_pedido=cfg.model,
        modelo_servido=next((m["modelo_servido"] for m in reversed(metas)
                             if m.get("modelo_servido")), ""),
        auth_mode="api_key",
        prompt_tokens=sum((m.get("tokens") or {}).get("entrada", 0) for m in metas),
        completion_tokens=sum((m.get("tokens") or {}).get("saida", 0)
                              + (m.get("tokens") or {}).get("raciocinio", 0) for m in metas),
        custo_usd=custo, latencia_ms=sum(m.get("latencia_ms", 0) for m in metas),
        consultas_de_busca=sum(len(m.get("web_search_queries") or []) for m in metas),
        finish_reason=str(final.get("finish_reason", "")), defeito=defeito, metadados=metas)
