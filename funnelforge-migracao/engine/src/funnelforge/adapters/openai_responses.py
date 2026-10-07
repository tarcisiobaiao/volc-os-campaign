"""RESPONSES API com o token do PLANO ChatGPT, no contrato `LLMClient` do motor.

Transcrito de https://developers.openai.com/siwc/token-sharing-open-source/
models-and-inference (07/10/2026): `POST https://api.openai.com/v1/responses`
com `Authorization: Bearer <token do plano>`, `store: false`, `stream: true`;
modelos disponíveis em `GET https://api.openai.com/v1/models` (`slug`,
`visibility: "list"`). O que a doc NÃO documenta para este fluxo é tratado como
não suportado, com erro explícito — nunca suposto:

- busca na web (`web_search`) e entrada com imagem: recusadas;
- `reasoning.effort` e `text.format` (json_schema): enviados só quando o passo
  pede; se o servidor recusar, o erro sobe como está (sem tentativa "sem");
- `temperature`: não é enviada (modelos de raciocínio não a aceitam).

Regras do motor: o modelo servido tem de ser o pedido (senão
`ModeloTrocadoPeloServidor`); nenhum erro do plano cai para API key; custo de
API é 0 — o consumo é do plano, e o recibo diz isso.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from funnelforge.adapters.chatgpt_oauth import (
    ErroDeAutenticacao,
    LimiteDoPlano,
    PlanoInelegivel,
    SessaoExpirada,
)
from funnelforge.config.settings import PREFIXO_DO_PLANO
from funnelforge.pipeline.budget import OrcamentoEstourado
from funnelforge.ports.llm import LLMResult

RESPONSES_URL = "https://api.openai.com/v1/responses"
MODELS_URL = "https://api.openai.com/v1/models"
AUTH_MODE = "chatgpt_plan"


class ModeloIndisponivel(ErroDeAutenticacao):
    codigo = "modelo_indisponivel"


class ModeloTrocadoPeloServidor(ErroDeAutenticacao):
    codigo = "modelo_trocado"


class NaoSuportadoNoPlano(ErroDeAutenticacao):
    codigo = "nao_suportado_no_plano"


class SaidaEstruturadaInvalida(ErroDeAutenticacao):
    codigo = "saida_estruturada_invalida"


class Cancelado(ErroDeAutenticacao):
    codigo = "cancelado"


class FalhaDoPlano(ErroDeAutenticacao):
    codigo = "falha_do_plano"
    retentavel = True               # 503 da doc: backoff limitado (max_retries)


@dataclass
class RespostaHTTP:
    status: int
    linhas: Iterable[str]           # SSE (linhas "data: {...}") quando status 200
    corpo: dict                     # JSON de erro quando status != 200


# enviar(url, headers, body, timeout_s) -> RespostaHTTP ; obter(url, headers, timeout_s) -> (status, json)
Enviar = Callable[[str, dict, dict, float], RespostaHTTP]
Obter = Callable[[str, dict, float], tuple[int, dict]]


def _enviar_httpx(url: str, headers: dict, body: dict, timeout_s: float) -> RespostaHTTP:
    import httpx
    cliente = httpx.Client(timeout=timeout_s)
    req = cliente.build_request("POST", url, headers=headers, json=body)
    resp = cliente.send(req, stream=True)
    if resp.status_code != 200:
        resp.read()
        try:
            corpo = resp.json()
        except ValueError:
            corpo = {}
        cliente.close()
        return RespostaHTTP(resp.status_code, [], corpo)

    def linhas() -> Iterable[str]:
        try:
            yield from resp.iter_lines()
        finally:
            resp.close()
            cliente.close()
    return RespostaHTTP(200, linhas(), {})


def _obter_httpx(url: str, headers: dict, timeout_s: float) -> tuple[int, dict]:
    import httpx
    resp = httpx.get(url, headers=headers, timeout=timeout_s)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {}


def _base(modelo: str) -> str:
    return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", (modelo or "").removeprefix(PREFIXO_DO_PLANO))


def _codigo(corpo: dict) -> str:
    erro = corpo.get("error") if isinstance(corpo.get("error"), dict) else corpo
    return str((erro or {}).get("code") or (erro or {}).get("type") or "")


def erro_do_plano(status: int, corpo: dict, modelo: str) -> ErroDeAutenticacao:
    """Status/código da doc "errors and recovery" -> erro com mensagem humana."""
    codigo = _codigo(corpo)
    if codigo == "subscription_sharing_user_not_eligible":
        return PlanoInelegivel("a conta conectada não é elegível para usar o plano ChatGPT "
                               "neste app. Nada foi cobrado; não repita a chamada.", codigo)
    if codigo == "subscription_sharing_usage_limit_exceeded" or status == 429:
        return LimiteDoPlano("limite de uso do plano ChatGPT atingido: aguarde e veja "
                             "ChatGPT → Configurações → Uso.", codigo or "429")
    if codigo == "subscription_sharing_usage_unavailable" or status == 503:
        return FalhaDoPlano("uso do plano temporariamente indisponível (503).", codigo or "503")
    if status == 401:
        return SessaoExpirada("token do plano recusado (401): rode "
                              "`funnelforge auth login --provider chatgpt`.", codigo or "401")
    if status == 404 or "model" in codigo:
        return ModeloIndisponivel(f"modelo '{modelo}' indisponível para esta conta "
                                  f"({codigo or status}). Nenhum outro modelo foi usado.",
                                  codigo or str(status))
    if codigo in ("chatpass_v2_scope_not_authorized", "chatpass_v2_invalid_authorization_context"):
        return ErroDeAutenticacao(f"grant sem autorização para o plano ({codigo}): confira o "
                                  "client_id e o consentimento.", codigo)
    return FalhaDoPlano(f"Responses API recusou a chamada ({status} {codigo}).",
                        codigo or str(status))


def _texto(conteudo: Any) -> str:
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for p in conteudo:
            if isinstance(p, dict) and p.get("type") == "text":
                partes.append(str(p.get("text", "")))
            else:
                raise NaoSuportadoNoPlano("entrada com imagem não é documentada no fluxo do "
                                          "plano ChatGPT: este passo fica no provedor atual.")
        return "\n".join(partes)
    return str(conteudo or "")


class OpenAIResponsesClient:
    def __init__(self, credencial: Any, *, enviar: Enviar = _enviar_httpx,
                 obter: Obter = _obter_httpx, timeout_s: float = 300.0,
                 cancelar: threading.Event | None = None) -> None:
        self.credencial, self._enviar, self._obter = credencial, enviar, obter
        self.timeout_s, self.cancelar = timeout_s, cancelar or threading.Event()

    def _cabecalhos(self, *, forcar_renovacao: bool = False) -> dict:
        token = self.credencial.access_token(forcar_renovacao=forcar_renovacao)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                "Accept": "text/event-stream"}

    def modelos_disponiveis(self) -> list[str]:
        status, corpo = self._obter(MODELS_URL, self._cabecalhos(), 30.0)
        if status != 200:
            raise erro_do_plano(status, corpo, "(lista de modelos)")
        lista = corpo.get("models") if isinstance(corpo.get("models"), list) else corpo.get("data")
        slugs = []
        for m in lista or []:
            if not isinstance(m, dict):
                continue
            if m.get("visibility") not in (None, "list"):
                continue
            slug = m.get("slug") or m.get("id")
            if slug:
                slugs.append(str(slug))
        return slugs

    def complete(self, model: str, fallbacks: list[str], messages: list[dict],
                 temperature: float, response_schema: type | None = None,
                 web_search: bool = False, reasoning_effort: str | None = None) -> LLMResult:
        if web_search:
            raise NaoSuportadoNoPlano("busca na web não é documentada no fluxo do plano "
                                      "ChatGPT: a pesquisa fica no provedor atual.")
        cadeia = [model, *[f for f in fallbacks if f.startswith(PREFIXO_DO_PLANO)]]
        ultimo: ErroDeAutenticacao | None = None
        for alvo in cadeia:
            try:
                return self._uma_chamada(alvo, messages, response_schema, reasoning_effort)
            except ModeloIndisponivel as exc:
                ultimo = exc               # só um fallback DECLARADO do plano segue
                continue
        assert ultimo is not None
        raise ultimo

    def _uma_chamada(self, modelo: str, messages: list[dict], response_schema: type | None,
                     reasoning_effort: str | None) -> LLMResult:
        slug = modelo.removeprefix(PREFIXO_DO_PLANO)
        body: dict[str, Any] = {
            "model": slug,
            "input": [{"role": m.get("role", "user"), "content": _texto(m.get("content"))}
                      for m in messages],
            "store": False, "stream": True,
        }
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}
        if response_schema is not None:
            body["text"] = {"format": {"type": "json_schema", "name": response_schema.__name__,
                                       "schema": response_schema.model_json_schema(),
                                       "strict": True}}
        inicio = time.perf_counter()
        resp = self._enviar(RESPONSES_URL, self._cabecalhos(), body, self.timeout_s)
        if resp.status == 401:             # uma renovação forçada, uma vez
            resp = self._enviar(RESPONSES_URL, self._cabecalhos(forcar_renovacao=True),
                                body, self.timeout_s)
        if resp.status != 200:
            raise erro_do_plano(resp.status, resp.corpo, slug)
        partes: list[str] = []
        final: dict = {}
        for linha in resp.linhas:
            if self.cancelar.is_set():
                raise Cancelado("chamada cancelada pelo operador.")
            if not linha or not linha.startswith("data:"):
                continue
            dado = linha[5:].strip()
            if dado == "[DONE]":
                break
            try:
                evento = json.loads(dado)
            except ValueError:
                continue
            tipo = evento.get("type")
            if tipo == "response.output_text.delta":
                partes.append(str(evento.get("delta", "")))
            elif tipo in ("response.completed",):
                final = evento.get("response") or {}
                break
            elif tipo in ("response.failed", "response.incomplete", "error"):
                r = evento.get("response") or evento
                raise erro_do_plano(500, {"error": r.get("error") or r.get("incomplete_details")
                                          or {"code": tipo}}, slug)
        if not final:
            # Stream que acabou sem `response.completed` é resposta truncada:
            # sem modelo servido e sem uso confirmados, nada dela é aceito.
            raise FalhaDoPlano(f"stream de '{slug}' terminou sem response.completed "
                               "(resposta truncada descartada).", "stream_incompleto")
        texto = "".join(partes)
        servido = str(final.get("model") or slug)
        if _base(servido) != _base(slug):
            raise ModeloTrocadoPeloServidor(
                f"pedido '{slug}', servido '{servido}': o motor não aceita troca de modelo.")
        parsed = None
        if response_schema is not None:
            try:
                parsed = response_schema.model_validate_json(texto)
            except Exception as exc:  # noqa: BLE001 - qualquer violação do schema
                raise SaidaEstruturadaInvalida(
                    f"saída de '{slug}' não cumpre o schema {response_schema.__name__}: "
                    f"{type(exc).__name__}.") from exc
        uso = final.get("usage") or {}
        return LLMResult(
            text=texto, model_used=PREFIXO_DO_PLANO + servido, parsed=parsed,
            prompt_tokens=int(uso.get("input_tokens") or 0),
            completion_tokens=int(uso.get("output_tokens") or 0),
            cost_usd=0.0, latency_ms=int((time.perf_counter() - inicio) * 1000),
            response_id=str(final.get("id") or ""), auth_mode=AUTH_MODE,
            reasoning_effort=reasoning_effort or "")


class TetoDeChamadas(OrcamentoEstourado):
    """Teto RÍGIDO de chamadas do run. É um `OrcamentoEstourado` de escopo run:
    o pipeline já sabe parar o laço e escrever o relatório."""

    def __str__(self) -> str:
        return (f"Teto rígido de {int(self.teto_usd)} chamadas de LLM atingido antes de "
                f"'{self.passo}': run interrompido.")


class RoteadorDeLLM:
    """`chatgpt/<modelo>` -> plano (Responses API); o resto -> LiteLLM com API
    key, exatamente como antes. Erro do plano NUNCA chama o LiteLLM."""

    def __init__(self, litellm: Any, plano: OpenAIResponsesClient | None = None, *,
                 allow_api_key_fallback: bool = False, max_chamadas: int = 0) -> None:
        self.litellm, self.plano = litellm, plano
        self.allow_api_key_fallback, self.max_chamadas = allow_api_key_fallback, max_chamadas
        self.chamadas = 0
        # Páginas em paralelo dividem este contador: conferir e somar é atômico.
        self._trava = threading.Lock()

    def _contar(self, modelo: str) -> None:
        with self._trava:
            if self.max_chamadas and self.chamadas >= self.max_chamadas:
                raise TetoDeChamadas("run", modelo, float(self.chamadas),
                                     float(self.max_chamadas))
            self.chamadas += 1

    def complete(self, model: str, fallbacks: list[str], messages: list[dict],
                 temperature: float, response_schema: type | None = None,
                 web_search: bool = False, reasoning_effort: str | None = None) -> LLMResult:
        self._contar(model)
        if model.startswith(PREFIXO_DO_PLANO):
            faturados = [f for f in fallbacks if not f.startswith(PREFIXO_DO_PLANO)]
            if faturados and not self.allow_api_key_fallback:
                raise NaoSuportadoNoPlano(f"fallback faturado {faturados} proibido para "
                                          f"'{model}' (allow_api_key_fallback=false).")
            if self.plano is None:
                raise SessaoExpirada(f"'{model}' exige o modo chatgpt_plan com login: rode "
                                     "`funnelforge auth login --provider chatgpt`.")
            return self.plano.complete(model, fallbacks, messages, temperature,
                                       response_schema, web_search, reasoning_effort)
        extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
        return self.litellm.complete(model, fallbacks, messages, temperature,
                                     response_schema, web_search, **extra)
