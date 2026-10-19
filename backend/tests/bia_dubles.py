"""Dublês da Bia para a suíte hermética (não é módulo de teste).

`LedgerMemoria` reproduz a semântica das RPCs da v27_01 em memória: é o que
deixa as rotas serem provadas sem banco. A SQL de verdade é provada à parte,
com os MESMOS cenários, em `tools/freedom-lab/db/suites/v27_bia.sh` (banco
descartável) e em `test_agente_bia_ledger_lab.py` (adaptador ↔ SQL real).

`HermesFalso` é um transporte httpx que imita o contrato do API Server
v0.18.0 conferido na VPS: sessões, chat síncrono e read-back de mensagens.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

import httpx

from app.agente_bia.portas import (
    Conversa,
    Execucao,
    Historico,
    Preparo,
    Reserva,
)

_TRANSICOES = {
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "uncertain"},
    "uncertain": {"succeeded", "failed"},
}


@dataclass
class _Linha:
    exe: Execucao
    dono: str
    impressao: str
    criada: datetime
    iniciada: Optional[datetime] = None


class LedgerMemoria:
    def __init__(self) -> None:
        self.conversas: Dict[str, Dict[str, Any]] = {}
        self.execucoes: Dict[str, _Linha] = {}
        self.eventos: List[Dict[str, Any]] = []
        self.relogio = lambda: datetime.now(timezone.utc)

    # helpers
    def _agora_iso(self) -> str:
        return self.relogio().isoformat()

    def _evento(self, eid: str, tipo: str, de=None, para=None, detalhe=None) -> None:
        self.eventos.append({"execucao_id": eid, "tipo": tipo, "de": de, "para": para,
                             "detalhe": dict(detalhe or {})})

    def _mudar(self, eid: str, **kw: Any) -> Execucao:
        linha = self.execucoes[eid]
        novo = kw.get("estado", linha.exe.estado)
        if novo != linha.exe.estado and novo not in _TRANSICOES.get(linha.exe.estado, set()):
            raise AssertionError(f"transição {linha.exe.estado} → {novo} recusada")
        linha.exe = replace(linha.exe, **kw)
        return linha.exe

    def _conv(self, c: Dict[str, Any]) -> Conversa:
        return Conversa(id=c["id"], titulo=c["titulo"], criada_em=c["criada_em"],
                        atualizada_em=c["atualizada_em"])

    # porta
    async def criar_conversa(self, dono, sessao_motor, titulo):
        assert sessao_motor.startswith("volc_") and len(sessao_motor) == 37
        cid = str(uuid.uuid4())
        agora = self._agora_iso()
        self.conversas[cid] = {"id": cid, "dono": dono, "sessao_motor": sessao_motor,
                               "titulo": titulo, "criada_em": agora, "atualizada_em": agora}
        return self._conv(self.conversas[cid])

    async def listar_conversas(self, dono, limite):
        cs = [c for c in self.conversas.values() if c["dono"] == dono]
        cs.sort(key=lambda c: c["atualizada_em"], reverse=True)
        return [self._conv(c) for c in cs[:limite]]

    async def historico(self, dono, conversa_id):
        c = self.conversas.get(conversa_id)
        if not c or c["dono"] != dono:
            return None
        es = [l.exe for l in self.execucoes.values() if l.exe.conversa_id == conversa_id]
        es.sort(key=lambda e: e.criada_em)
        return Historico(conversa=self._conv(c), execucoes=es)

    async def execucao(self, dono, execucao_id):
        l = self.execucoes.get(execucao_id)
        return l.exe if l and l.dono == dono else None

    async def reservar(self, dono, conversa_id, request_id, entrada, impressao,
                       limite_por_minuto, contexto):
        for l in self.execucoes.values():
            if l.dono == dono and l.exe.request_id == request_id:
                if l.exe.conversa_id == conversa_id and l.impressao == impressao:
                    return Reserva("repetida", l.exe)
                return Reserva("conflito")
        c = self.conversas.get(conversa_id)
        if not c or c["dono"] != dono:
            return Reserva("conversa_inexistente")
        if any(l.exe.conversa_id == conversa_id and l.exe.estado == "uncertain"
               for l in self.execucoes.values()):
            return Reserva("bloqueada_incerta")
        if any(l.dono == dono and l.exe.estado in ("queued", "running")
               for l in self.execucoes.values()):
            return Reserva("ocupado")
        agora = self.relogio()
        recentes = sum(1 for l in self.execucoes.values()
                       if l.dono == dono and l.criada > agora - timedelta(seconds=60))
        if recentes >= max(1, min(limite_por_minuto, 30)):
            return Reserva("limite")
        eid = str(uuid.uuid4())
        exe = Execucao(id=eid, conversa_id=conversa_id, request_id=request_id, estado="queued",
                       entrada=entrada, resposta=None, erro_codigo=None,
                       contexto=dict(contexto) if contexto else None,
                       criada_em=agora.isoformat(), terminada_em=None)
        self.execucoes[eid] = _Linha(exe=exe, dono=dono, impressao=impressao, criada=agora)
        c["atualizada_em"] = agora.isoformat()
        self._evento(eid, "reservada", None, "queued")
        return Reserva("nova", exe)

    async def iniciar(self, dono, execucao_id):
        l = self.execucoes.get(execucao_id)
        if not l or l.dono != dono or l.exe.estado != "queued":
            return None
        self._mudar(execucao_id, estado="running")
        l.iniciada = self.relogio()
        self._evento(execucao_id, "iniciada", "queued", "running")
        c = self.conversas[l.exe.conversa_id]
        return Preparo(sessao_motor=c["sessao_motor"], entrada=l.exe.entrada,
                       contexto=l.exe.contexto)

    async def concluir(self, dono, execucao_id, estado, resposta, erro_codigo, detalhe):
        l = self.execucoes[execucao_id]
        assert l.dono == dono
        if l.exe.estado != "running":
            self._evento(execucao_id, "conclusao_tardia_ignorada", l.exe.estado, estado)
            return l.exe
        exe = self._mudar(execucao_id, estado=estado,
                          resposta=resposta if estado == "succeeded" else None,
                          erro_codigo=None if estado == "succeeded" else erro_codigo,
                          terminada_em=self._agora_iso())
        self._evento(execucao_id, "concluida", "running", estado,
                     {**detalhe, **({"erro_codigo": erro_codigo} if erro_codigo else {})})
        return exe

    async def expirar(self, dono, segundos):
        n = 0
        limite = self.relogio() - timedelta(seconds=max(segundos, 30))
        for eid, l in self.execucoes.items():
            if l.dono != dono or l.exe.estado not in ("queued", "running"):
                continue
            if (l.iniciada or l.criada) < limite:
                novo = "cancelled" if l.exe.estado == "queued" else "uncertain"
                self._mudar(eid, estado=novo, erro_codigo="processo_interrompido",
                            terminada_em=self._agora_iso())
                self._evento(eid, "expirada", None, novo)
                n += 1
        return n

    async def para_reconciliar(self, dono, execucao_id):
        l = self.execucoes.get(execucao_id)
        if not l or l.dono != dono or l.exe.estado != "uncertain":
            return None
        c = self.conversas[l.exe.conversa_id]
        return Preparo(sessao_motor=c["sessao_motor"], entrada=l.exe.entrada, contexto=l.exe.contexto)

    async def reconciliar(self, dono, execucao_id, estado, resposta, detalhe):
        l = self.execucoes[execucao_id]
        assert l.dono == dono and l.exe.estado == "uncertain"
        exe = self._mudar(execucao_id, estado=estado,
                          resposta=resposta if estado == "succeeded" else None,
                          erro_codigo=None if estado == "succeeded" else l.exe.erro_codigo)
        self._evento(execucao_id, "reconciliada", "uncertain", estado, detalhe)
        return exe

    async def registrar_evento(self, dono, execucao_id, tipo, detalhe):
        assert tipo in ("contexto_lido", "reconciliacao_inconclusiva")
        l = self.execucoes.get(execucao_id)
        assert l and l.dono == dono
        self._evento(execucao_id, tipo, None, None, detalhe)

    # para os testes
    def sessao_de(self, conversa_id: str) -> str:
        return self.conversas[conversa_id]["sessao_motor"]


@dataclass
class HermesFalso:
    """API Server v0.18.0, no lugar do socket. Conta e guarda tudo o que recebeu."""
    chave: str = "chave-hermes-de-teste-NUNCA-SAI"
    resposta: str = "conexão VOLC funcionando"
    modo: str = "ok"  # ok | timeout | conexao_recusada | http500 | http401 | ilegivel | fora_do_ar | usa_ferramenta | sem_readback
    ferramentas: List[str] = field(default_factory=list)  # toolsets habilitados no profile
    sessoes: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    titulos: Dict[str, Any] = field(default_factory=dict)
    #: SSE de sessão (v0.18.0). Desligado = 404 na rota de stream (o adaptador
    #: cai no /chat), que é o que os testes antigos exercitam.
    streaming: bool = False
    modo_stream: str = "ok"  # ok | ferramenta | erro | sem_fim
    conteudos: List[Any] = field(default_factory=list)  # o `input` exato de cada turno
    pedidos: List[httpx.Request] = field(default_factory=list)

    @property
    def chats(self) -> List[httpx.Request]:
        return [r for r in self.pedidos if r.url.path.endswith(("/chat", "/chat/stream"))
                and not (r.url.path.endswith("/chat/stream") and not self.streaming)]

    def _sse(self, sid: str, texto: Any) -> httpx.Response:
        self.conteudos.append(texto)
        so_texto = texto if isinstance(texto, str) else " ".join(
            p.get("text", "") for p in texto if isinstance(p, dict) and p.get("type") == "text")
        self.sessoes[sid].append({"role": "user", "content": texto})
        resposta = self.resposta
        linhas = ['event: run.started\ndata: {"seq":1}\n', 'event: message.started\ndata: {"seq":2}\n',
                  'event: tool.progress\ndata: ' + json.dumps({"tool_name": "_thinking", "delta": "RACIOCINIO-SECRETO"}) + "\n"]
        for i, palavra in enumerate(resposta.split(" ")):
            linhas.append("event: assistant.delta\ndata: " + json.dumps({"delta": (" " if i else "") + palavra}) + "\n")
            if self.modo_stream == "ferramenta" and i == 0:
                linhas.append("event: tool.started\ndata: " + json.dumps({"tool_name": "terminal", "args": {"cmd": "ls"}}) + "\n")
        if self.modo_stream == "erro":
            linhas.append("event: error\ndata: " + json.dumps({"message": "Traceback /root/.hermes SEGREDO"}) + "\n")
        elif self.modo_stream != "sem_fim":
            self.sessoes[sid].append({"role": "assistant", "content": resposta})
            linhas.append("event: assistant.completed\ndata: " + json.dumps({"content": resposta, "completed": True}) + "\n")
            linhas.append("event: run.completed\ndata: " + json.dumps({"usage": {"input_tokens": 30, "output_tokens": 4}}) + "\n")
        linhas.append("event: done\ndata: {}\n")
        return httpx.Response(200, content="\n".join(linhas).encode(),
                              headers={"Content-Type": "text/event-stream"})

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._responder)

    def _responder(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        if request.headers.get("Authorization") != f"Bearer {self.chave}":
            return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
        caminho = request.url.path
        if self.modo == "fora_do_ar":
            # Túnel SSH aceita a conexão; o Hermes do outro lado não responde.
            raise httpx.RemoteProtocolError("canal fechado (simulado)", request=request)
        if caminho == "/v1/toolsets":
            nomes = ["terminal", "file", "web"]
            return httpx.Response(200, json={"object": "list", "data": [
                {"name": n, "enabled": n in self.ferramentas} for n in nomes]})
        if caminho == "/api/sessions" and request.method == "POST":
            corpo = json.loads(request.content)
            sid = corpo["id"]
            if sid in self.sessoes:
                return httpx.Response(409, json={"error": {"code": "session_exists"}})
            # Como o Hermes v0.18.0: título é único entre sessões (400 invalid_title).
            if corpo.get("title") in self.titulos.values():
                return httpx.Response(400, json={"error": {"code": "invalid_title"}})
            self.titulos[sid] = corpo.get("title")
            self.sessoes[sid] = []
            return httpx.Response(201, json={"object": "hermes.session", "session": {"id": sid}})
        if caminho.startswith("/api/sessions/") and caminho.endswith("/messages"):
            if self.modo == "sem_readback":
                return httpx.Response(503, json={})
            sid = caminho.split("/")[3]
            if sid not in self.sessoes:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"object": "list", "session_id": sid,
                                             "data": self.sessoes[sid]})
        if caminho.startswith("/api/sessions/") and caminho.endswith("/chat/stream"):
            sid = caminho.split("/")[3]
            if not self.streaming:
                return httpx.Response(404, json={"error": {"code": "not_found"}})
            if sid not in self.sessoes:
                return httpx.Response(404, json={"error": {"code": "session_not_found"}})
            return self._sse(sid, json.loads(request.content)["input"])
        if caminho == "/health/detailed":
            return httpx.Response(200, json={"status": "ok", "version": "0.18.0", "gateway_state": "running",
                                             "platforms": {"telegram": {"state": "connected"}}, "pid": 1})
        if caminho.startswith("/api/sessions/") and caminho.count("/") == 3 and request.method == "GET":
            sid = caminho.split("/")[3]
            if sid not in self.sessoes:
                return httpx.Response(404, json={})
            n = len(self.sessoes[sid])
            return httpx.Response(200, json={"object": "hermes.session", "session": {
                "id": sid, "message_count": n, "tool_call_count": 0, "input_tokens": 10 * n,
                "output_tokens": 2 * n, "estimated_cost_usd": 0.0, "system_prompt": "NAO-SAI"}})
        if caminho.startswith("/api/sessions/") and caminho.endswith("/chat"):
            sid = caminho.split("/")[3]
            if self.modo == "conexao_recusada":
                raise httpx.ConnectError("recusada (simulado)", request=request)
            if sid not in self.sessoes:
                return httpx.Response(404, json={"error": {"code": "session_not_found"}})
            texto = json.loads(request.content)["input"]
            self.sessoes[sid].append({"role": "user", "content": texto})
            if self.modo == "timeout":
                # O agente RESPONDEU no servidor, mas o cliente desistiu antes.
                self.sessoes[sid].append({"role": "assistant", "content": self.resposta})
                raise httpx.ReadTimeout("timeout (simulado)", request=request)
            if self.modo == "http500":
                return httpx.Response(500, text="Traceback (most recent call last): /root/.hermes "
                                                 "API_SERVER_KEY=vazou-do-upstream")
            if self.modo == "http401":
                return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
            if self.modo == "ilegivel":
                return httpx.Response(200, text="<html>proxy</html>")
            historico = [m["content"] for m in self.sessoes[sid] if m["role"] == "user"]
            resposta = self.resposta
            if "Qual é o código" in texto:
                anteriores = " ".join(historico[:-1])
                resposta = "O código é AMBAR." if "AMBAR" in anteriores else "Não sei o código."
            if self.modo == "usa_ferramenta":
                self.sessoes[sid].append({"role": "assistant", "content": None,
                                          "tool_calls": [{"function": {"name": "terminal"}}]})
                self.sessoes[sid].append({"role": "tool", "content": "SAIDA-DA-FERRAMENTA",
                                          "tool_name": "terminal"})
            self.sessoes[sid].append({"role": "assistant", "content": resposta})
            return httpx.Response(200, json={
                "object": "hermes.session.chat.completion", "session_id": sid,
                "message": {"role": "assistant", "content": resposta},
                "usage": {"input_tokens": 12, "output_tokens": 5, "segredo": "nao-repassar"},
            }, headers={"X-Hermes-Session-Id": sid})
        return httpx.Response(404, json={})


class FonteDeContextoFalsa:
    """Snapshot + ledger + fato de UMA campanha, sem rede. Conta as leituras."""

    def __init__(self, *, linha: Optional[Mapping[str, Any]], fechamentos=None, linhas=None) -> None:
        self.linha = dict(linha) if linha else None
        self.fechos = list(fechamentos or [])
        self.linhas = list(linhas or [])
        self.leituras: List[str] = []

    async def uma_campanha(self, ref):
        self.leituras.append("uma_campanha")
        return dict(self.linha) if self.linha and self.linha.get("volc_campaign_id") == ref else None

    async def fechamentos(self, contas, periodo):
        self.leituras.append("fechamentos")
        return list(self.fechos)

    async def linhas_da_campanha(self, customer_id, campaign_id, periodo):
        assert "fechamentos" in self.leituras, "o fato não pode ser lido antes do ledger"
        self.leituras.append("linhas")
        return list(self.linhas)
