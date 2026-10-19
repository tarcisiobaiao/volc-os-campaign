"""Adaptador do API Server do Hermes v0.18.0 — profile `default` (a mesma Bia do Telegram).

A superfície `api_server` do profile `default` é configurada SEM ferramentas
(`platform_toolsets.api_server: []`, medido como conjunto vazio na v0.18.0),
enquanto o Telegram mantém as suas (`hermes-telegram`). Cada conversa do VOLC
é uma sessão própria do Hermes (`volc_<hex32>`, source `api_server`), separada
das sessões do Telegram; identidade (SOUL), modelo e memória longa são os do
profile.

Contrato conferido no código instalado na VPS em 15/10/2026
(`gateway/platforms/api_server.py`, somente leitura):

    POST /api/sessions                  {id, title} → 201 | 409 session_exists
    POST /api/sessions/{id}/chat        {input}     → 200 {message:{content}, usage}
    GET  /api/sessions/{id}/messages                → 200 {data:[{role, content, …}]}
    GET  /v1/toolsets                               → 200 {data:[{name, enabled, …}]}

## O que este adaptador se recusa a mandar

A rota `/chat` do Hermes ACEITA `instructions`/`system_message` e o cabeçalho
`X-Hermes-Session-Key` (escopo de memória longa). Este adaptador não envia
nenhum dos dois, nem `model`: o corpo é sempre e só `{"input": texto}`. Não há
parâmetro na assinatura que permita o contrário.

## Classificação de falha (o que decide failed × uncertain)

- conexão recusada / DNS / TLS antes de enviar → `MotorRecusou` (nada saiu);
- 400/401/403/404/409/422/429 → `MotorRecusou`: o Hermes valida auth, sessão e
  corpo ANTES de `_run_agent`;
- timeout de leitura, conexão caída depois de enviar, 5xx, 200 ilegível →
  `MotorIncerto`: o agente pode ter rodado.

Nada do corpo do upstream é repassado: só o código da lista pública.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, List, Optional, Union

import httpx

from app.agente_bia.portas import (
    MensagemDoMotor,
    MotorIncerto,
    MotorRecusou,
    MotorUsouFerramenta,
    RespostaDoMotor,
)

#: Conteúdo do turno: texto puro, ou partes no formato de visão da OpenAI
#: (`{"type":"text"}` + `{"type":"image_url","image_url":{"url":"data:image/…"}}`),
#: que o `_normalize_multimodal_content` do Hermes v0.18.0 aceita.
Conteudo = Union[str, List[dict]]
AoDelta = Optional[Callable[[str], Awaitable[None]]]


def texto_do_conteudo(conteudo: Any) -> str:
    """Texto de uma mensagem lida da sessão: str, lista de partes, ou lista serializada."""
    if isinstance(conteudo, str):
        bruto = conteudo.strip()
        if bruto.startswith("[") and '"type"' in bruto[:200]:
            try:
                conteudo = json.loads(bruto)
            except ValueError:
                return conteudo
        else:
            return conteudo
    if isinstance(conteudo, list):
        return "\n".join(str(p.get("text") or "") for p in conteudo
                         if isinstance(p, dict) and str(p.get("type") or "") in ("text", "input_text"))
    return ""

log = logging.getLogger("volc.agente_bia.hermes")

_RECUSAS = {400, 401, 403, 404, 409, 413, 415, 422, 429}

#: Única forma de id de sessão que este adaptador aceita tocar. A chave do API
#: Server é do profile `default` e abriria também as sessões do Telegram; o
#: adaptador se recusa a falar de qualquer sessão que não seja do VOLC.
_SESSAO_VOLC = re.compile(r"^volc_[0-9a-f]{32}$")


def _exigir_sessao_volc(sessao_motor: str) -> None:
    if not _SESSAO_VOLC.fullmatch(sessao_motor or ""):
        raise MotorRecusou("hermes_recusou")


def _tem_ferramenta(m: dict) -> bool:
    """Chamada/resultado de ferramenta: role=tool, tool_name, ou tool_calls NÃO vazio.

    Medido no state.db real (15/10/2026): mensagem sem ferramenta tem
    tool_calls NULL. Texto "[]"/"null" também é tratado como vazio.
    """
    if m.get("role") == "tool" or m.get("tool_name"):
        return True
    tc = m.get("tool_calls")
    if isinstance(tc, str):
        try:
            tc = json.loads(tc) if tc.strip() else None
        except ValueError:
            return True  # ilegível: na dúvida, conta como uso (falha fechada)
    return bool(tc) if isinstance(tc, (list, dict)) else False


def _codigo_de_recusa(status: int) -> str:
    if status in (401, 403):
        return "hermes_autenticacao"
    if status == 404:
        return "hermes_sessao_ausente"
    return "hermes_recusou"


class HermesHttp:
    def __init__(self, base_url: str, chave: str, *, timeout_s: float,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._base = base_url.rstrip("/")
        self._chave = chave
        self._timeout = timeout_s
        self._transport = transport

    def _cliente(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base,
            transport=self._transport,
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=False,
            headers={"Authorization": f"Bearer {self._chave}"},
            trust_env=False,  # proxy do ambiente não pode ver a chave do profile
        )

    async def verificar_sem_ferramentas(self) -> None:
        """`GET /v1/toolsets`: vivo e sem nenhum toolset habilitado, ou recusa.

        A configuração do profile é intenção; isto é a conferência em runtime,
        a cada envio. Sem ela, "a Bia não tem ferramenta" seria só uma promessa
        sobre um arquivo na VPS.
        """
        try:
            async with self._cliente(10.0) as c:
                r = await c.get("/v1/toolsets")
        except httpx.HTTPError as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        if r.status_code in (401, 403):
            raise MotorRecusou("hermes_autenticacao")
        if r.status_code != 200:
            raise MotorRecusou("hermes_indisponivel")
        try:
            corpo: Any = r.json()
        except ValueError as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        linhas = corpo.get("data") if isinstance(corpo, dict) else corpo
        if not isinstance(linhas, list):
            raise MotorRecusou("hermes_indisponivel")
        if any(isinstance(x, dict) and x.get("enabled") for x in linhas):
            log.error("profile do Hermes com toolset habilitado; envio recusado")
            raise MotorRecusou("hermes_com_ferramentas")

    async def garantir_sessao(self, sessao_motor: str, titulo: str) -> None:
        _exigir_sessao_volc(sessao_motor)
        try:
            async with self._cliente(15.0) as c:
                r = await c.post("/api/sessions", json={"id": sessao_motor, "title": titulo})
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        except httpx.HTTPError as exc:
            # Criar sessão não roda o agente: incerteza aqui não tem efeito
            # colateral, mas também não sabemos se a sessão nasceu. O próximo
            # passo (`conversar`) responderia 404 e cairia em recusa.
            raise MotorRecusou("hermes_indisponivel") from exc
        if r.status_code in (200, 201):
            return
        if r.status_code == 409:
            return  # já existe: é o caminho normal a partir do 2º envio
        if r.status_code in _RECUSAS:
            raise MotorRecusou(_codigo_de_recusa(r.status_code))
        raise MotorRecusou("hermes_indisponivel")

    async def conversar(self, sessao_motor: str, conteudo: Conteudo,
                        ao_delta: AoDelta = None) -> RespostaDoMotor:
        """Um turno. Com `ao_delta`, pelo SSE de sessão (tokens reais); sem, `/chat`."""
        _exigir_sessao_volc(sessao_motor)
        if ao_delta is not None:
            resposta = await self._conversar_em_fluxo(sessao_motor, conteudo, ao_delta)
            if resposta is not None:
                return resposta
            # rota de stream ausente nesta versão: cai no síncrono, sem replay
        inicio = time.monotonic()
        try:
            async with self._cliente(self._timeout) as c:
                r = await c.post(f"/api/sessions/{sessao_motor}/chat", json={"input": conteudo})
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        except httpx.TimeoutException as exc:
            raise MotorIncerto("hermes_timeout") from exc
        except httpx.HTTPError as exc:
            raise MotorIncerto("hermes_conexao") from exc

        if r.status_code in _RECUSAS:
            raise MotorRecusou(_codigo_de_recusa(r.status_code))
        if r.status_code != 200:
            raise MotorIncerto("hermes_resposta_ilegivel")
        try:
            corpo: Any = r.json()
            conteudo = corpo["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MotorIncerto("hermes_resposta_ilegivel") from exc
        if not isinstance(conteudo, str):
            raise MotorIncerto("hermes_resposta_ilegivel")

        uso = corpo.get("usage") if isinstance(corpo, dict) else None
        uso = uso if isinstance(uso, dict) else {}

        def _int(chave: str) -> Optional[int]:
            v = uso.get(chave)
            return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

        return RespostaDoMotor(
            texto=conteudo,
            modelo=None,  # a rota de sessão não informa; vem de /v1/capabilities no smoke
            tokens_entrada=_int("input_tokens") or _int("prompt_tokens"),
            tokens_saida=_int("output_tokens") or _int("completion_tokens"),
            duracao_ms=int((time.monotonic() - inicio) * 1000),
        )

    async def _conversar_em_fluxo(self, sessao_motor: str, conteudo: Conteudo,
                                  ao_delta: Callable[[str], Awaitable[None]]) -> Optional[RespostaDoMotor]:
        """`POST /api/sessions/{id}/chat/stream` (SSE, v0.18.0).

        Repassa SÓ `assistant.delta`. `tool.progress` de raciocínio é descartado;
        qualquer evento de ferramenta FECHA a conexão — o Hermes cancela o turno
        quando o cliente desconecta — e o turno vira falha certa. `None` quando a
        rota não existe (404/405): o chamador usa `/chat`.
        """
        inicio = time.monotonic()
        final: Optional[str] = None
        uso: dict = {}
        erro_no_turno = False
        try:
            async with self._cliente(self._timeout) as c:
                async with c.stream("POST", f"/api/sessions/{sessao_motor}/chat/stream",
                                    json={"input": conteudo}) as r:
                    if r.status_code in (404, 405):
                        corpo = await r.aread()
                        if b"session_not_found" in corpo:
                            raise MotorRecusou("hermes_sessao_ausente")
                        return None
                    if r.status_code in _RECUSAS:
                        raise MotorRecusou(_codigo_de_recusa(r.status_code))
                    if r.status_code != 200:
                        raise MotorIncerto("hermes_resposta_ilegivel")
                    evento = ""
                    async for linha in r.aiter_lines():
                        if linha.startswith("event:"):
                            evento = linha[6:].strip()
                            continue
                        if not linha.startswith("data:"):
                            continue
                        try:
                            dados = json.loads(linha[5:].strip() or "{}")
                        except ValueError:
                            continue
                        if evento == "assistant.delta":
                            delta = dados.get("delta")
                            if isinstance(delta, str) and delta:
                                await ao_delta(delta)
                        elif evento in ("tool.started", "tool.completed", "tool.failed") or (
                                evento == "tool.progress" and dados.get("tool_name") not in (None, "_thinking")):
                            log.error("Hermes sinalizou ferramenta no turno da web; conexão encerrada")
                            raise MotorUsouFerramenta("hermes_usou_ferramenta")
                        elif evento == "assistant.completed":
                            if isinstance(dados.get("content"), str):
                                final = dados["content"]
                        elif evento == "run.completed":
                            uso = dados.get("usage") if isinstance(dados.get("usage"), dict) else {}
                        elif evento == "error":
                            erro_no_turno = True
                        elif evento == "done":
                            break
        except (MotorRecusou, MotorIncerto, MotorUsouFerramenta):
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        except httpx.TimeoutException as exc:
            raise MotorIncerto("hermes_timeout") from exc
        except httpx.HTTPError as exc:
            raise MotorIncerto("hermes_conexao") from exc
        if erro_no_turno or final is None:
            # O turno começou e não terminou limpo: pode ter gravado algo na sessão.
            raise MotorIncerto("hermes_erro_no_turno" if erro_no_turno else "hermes_conexao")

        def _int(chave: str) -> Optional[int]:
            v = uso.get(chave)
            return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

        return RespostaDoMotor(texto=final, modelo=None,
                               tokens_entrada=_int("input_tokens") or _int("prompt_tokens"),
                               tokens_saida=_int("output_tokens") or _int("completion_tokens"),
                               duracao_ms=int((time.monotonic() - inicio) * 1000))

    async def sessao(self, sessao_motor: str) -> dict:
        """`GET /api/sessions/{id}` — contagens, tokens e custo da sessão web (só leitura)."""
        _exigir_sessao_volc(sessao_motor)
        try:
            async with self._cliente(10.0) as c:
                r = await c.get(f"/api/sessions/{sessao_motor}")
        except httpx.HTTPError as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        if r.status_code == 404:
            raise MotorRecusou("hermes_sessao_ausente")
        if r.status_code != 200:
            raise MotorRecusou("hermes_indisponivel")
        try:
            s = r.json()["session"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MotorRecusou("hermes_resposta_ilegivel") from exc
        campos = ("message_count", "tool_call_count", "input_tokens", "output_tokens",
                  "estimated_cost_usd", "started_at", "last_active")
        return {k: s.get(k) for k in campos if k in s}

    async def saude(self) -> dict:
        """`GET /health/detailed` — versão e estado do gateway (só leitura)."""
        try:
            async with self._cliente(10.0) as c:
                r = await c.get("/health/detailed")
        except httpx.HTTPError as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        if r.status_code != 200:
            raise MotorRecusou("hermes_indisponivel")
        try:
            d = r.json()
        except ValueError as exc:
            raise MotorRecusou("hermes_resposta_ilegivel") from exc
        return {"versao": d.get("version"), "gateway": d.get("gateway_state")}

    async def mensagens(self, sessao_motor: str) -> List[MensagemDoMotor]:
        _exigir_sessao_volc(sessao_motor)
        try:
            async with self._cliente(15.0) as c:
                r = await c.get(f"/api/sessions/{sessao_motor}/messages")
        except httpx.HTTPError as exc:
            raise MotorRecusou("hermes_indisponivel") from exc
        if r.status_code != 200:
            raise MotorRecusou(_codigo_de_recusa(r.status_code) if r.status_code in _RECUSAS
                               else "hermes_indisponivel")
        try:
            dados = r.json()["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MotorRecusou("hermes_resposta_ilegivel") from exc
        saida: List[MensagemDoMotor] = []
        for m in dados if isinstance(dados, list) else []:
            if not isinstance(m, dict):
                continue
            papel, conteudo = m.get("role"), m.get("content")
            # Chamada ou resultado de ferramenta vira só um SINAL (para a
            # auditoria do turno); o conteúdo dela nunca sai deste adaptador.
            if _tem_ferramenta(m):
                saida.append(MensagemDoMotor(papel="tool", texto="", ferramenta=True))
                continue
            if papel in ("user", "assistant"):
                saida.append(MensagemDoMotor(papel=papel, texto=texto_do_conteudo(conteudo)))
        return saida
