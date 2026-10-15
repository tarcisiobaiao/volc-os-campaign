"""Bia — o adaptador `LedgerSupabase` contra a SQL REAL da v27_01, no banco descartável.

Opt-in: só roda com `BIA_LAB_CONTAINER=<container do freedom-lab>` com a v27_01
aplicada (ver `docs/bia-hermes/RUNBOOK-IMPLANTACAO.md`, seção da prova do lab).
Sem a variável, pula — e diz por quê.

## O que é real e o que é dublado

Real: as 11 RPCs, os gatilhos, os índices e as travas da v27_01 num Postgres
15.8 da imagem Supabase; o `LedgerSupabase` e os casos de uso inteiros.

Dublado: só o PostgREST. Um transporte httpx traduz `POST /rest/v1/rpc/<fn>`
numa chamada `SELECT to_jsonb(public.<fn>(...))` como `service_role`, pelo
`docker exec` do container sem rede. Isso prova o que os testes em memória não
provam: nome de cada parâmetro, tipo, e o formato do JSON que volta.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import uuid

import httpx
import pytest

from app.agente_bia.aplicacao import CasosDeUso
from app.agente_bia.infra_hermes import HermesHttp
from app.agente_bia.infra_ledger import LedgerIndisponivel, LedgerSupabase
from bia_dubles import HermesFalso

CONTAINER = os.environ.get("BIA_LAB_CONTAINER", "")
pytestmark = pytest.mark.skipif(not CONTAINER, reason="BIA_LAB_CONTAINER ausente: prova de lab opt-in")

#: Tipos de cada parâmetro, copiados da v27_01. Um nome errado no adaptador
#: vira erro aqui (parâmetro desconhecido), como viraria no PostgREST.
ASSINATURAS = {
    "volc_agente_criar_conversa": {"p_dono": "uuid", "p_sessao_motor": "text", "p_titulo": "text"},
    "volc_agente_listar_conversas": {"p_dono": "uuid", "p_limite": "integer"},
    "volc_agente_historico": {"p_dono": "uuid", "p_conversa": "uuid"},
    "volc_agente_execucao": {"p_dono": "uuid", "p_execucao": "uuid"},
    "volc_agente_reservar": {"p_dono": "uuid", "p_conversa": "uuid", "p_request_id": "uuid",
                             "p_entrada": "text", "p_impressao": "text",
                             "p_limite_por_minuto": "integer", "p_contexto": "jsonb"},
    "volc_agente_iniciar": {"p_dono": "uuid", "p_execucao": "uuid"},
    "volc_agente_concluir": {"p_dono": "uuid", "p_execucao": "uuid", "p_estado": "text",
                             "p_resposta": "text", "p_erro_codigo": "text", "p_detalhe": "jsonb"},
    "volc_agente_expirar": {"p_dono": "uuid", "p_segundos": "integer"},
    "volc_agente_para_reconciliar": {"p_dono": "uuid", "p_execucao": "uuid"},
    "volc_agente_reconciliar": {"p_dono": "uuid", "p_execucao": "uuid", "p_estado": "text",
                                "p_resposta": "text", "p_detalhe": "jsonb"},
    "volc_agente_registrar_evento": {"p_dono": "uuid", "p_execucao": "uuid", "p_tipo": "text",
                                     "p_detalhe": "jsonb"},
}


def _psql(sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-h", "localhost", "-U", "supabase_admin",
         "-d", "postgres", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
        input=f"\\set VERBOSITY verbose\n{sql}\n", capture_output=True, text=True, timeout=60)


def _literal(valor, tipo: str) -> str:
    if valor is None:
        return f"NULL::{tipo}"
    texto = json.dumps(valor) if tipo == "jsonb" else str(valor)
    tag = "q" + secrets.token_hex(6)
    return f"${tag}${texto}${tag}$::{tipo}"


def _postgrest_do_lab(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer service-do-lab"
    fn = request.url.path.rsplit("/", 1)[-1]
    if fn not in ASSINATURAS:
        return httpx.Response(404, json={"code": "PGRST202"})
    args = json.loads(request.content)
    desconhecidos = set(args) - set(ASSINATURAS[fn])
    assert not desconhecidos, f"{fn}: parâmetro desconhecido {desconhecidos}"
    lista = ", ".join(f"{k} => {_literal(v, ASSINATURAS[fn][k])}" for k, v in args.items())
    r = _psql(f"SET ROLE service_role; SELECT to_jsonb(public.{fn}({lista}));")
    if r.returncode != 0:
        codigo = next((p.split(":")[0].strip() for p in r.stderr.split("ERROR:")[1:2]), "")
        return httpx.Response(400, json={"code": codigo.strip()})
    saida = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    return httpx.Response(200, content=(saida or "null").encode(),
                          headers={"Content-Type": "application/json"})


@pytest.fixture(scope="module")
def dono():
    uid = str(uuid.uuid4())
    r = _psql(f"insert into auth.users (id, aud, role, email) values ('{uid}', 'authenticated', "
              f"'authenticated', 'bia-{uid[:8]}@lab.invalid');")
    assert r.returncode == 0, r.stderr
    yield uid
    _psql(f"delete from auth.users where id = '{uid}';")


def _montar(hermes: HermesFalso, limite: int = 6) -> CasosDeUso:
    ledger = LedgerSupabase("https://lab.invalid", "service-do-lab",
                            transport=httpx.MockTransport(_postgrest_do_lab))
    motor = HermesHttp("http://127.0.0.1:18643", hermes.chave, timeout_s=120,
                       transport=hermes.transporte())
    return CasosDeUso(ledger, motor, limite_por_minuto=limite, max_caracteres=4000,
                      timeout_motor_s=120)


def test_ciclo_completo_contra_a_sql_real(dono):
    hermes = HermesFalso()
    casos = _montar(hermes)

    async def roteiro():
        c = await casos.criar_conversa(dono)
        rid = str(uuid.uuid4())
        r = await casos.reservar_envio(dono, c.id, rid, "O código desta conversa é AMBAR.", None)
        assert r.resultado == "nova" and r.execucao.estado == "queued"
        assert (await casos.reservar_envio(dono, c.id, rid, "O código desta conversa é AMBAR.",
                                           None)).resultado == "repetida"
        e = await casos.executar(dono, r.execucao.id, None)
        assert e.estado == "succeeded" and e.resposta == "conexão VOLC funcionando"
        r2 = await casos.reservar_envio(dono, c.id, str(uuid.uuid4()), "Qual é o código?", None)
        e2 = await casos.executar(dono, r2.execucao.id, None)
        assert e2.resposta == "O código é AMBAR."
        h = await casos.historico(dono, c.id)
        assert [x.estado for x in h.execucoes] == ["succeeded", "succeeded"]
        assert [x.id for x in await casos.listar_conversas(dono)][0] == c.id
        return c

    asyncio.run(roteiro())
    assert len(hermes.chats) == 2


def test_timeout_incerta_bloqueia_e_reconcilia_contra_a_sql_real(dono):
    hermes = HermesFalso(modo="timeout")
    casos = _montar(hermes)

    async def roteiro():
        c = await casos.criar_conversa(dono)
        r = await casos.reservar_envio(dono, c.id, str(uuid.uuid4()), "pergunta", None)
        e = await casos.executar(dono, r.execucao.id, None)
        assert e.estado == "uncertain" and e.erro_codigo == "hermes_timeout"
        with pytest.raises(Exception) as recusa:
            await casos.reservar_envio(dono, c.id, str(uuid.uuid4()), "de novo", None)
        assert getattr(recusa.value, "motivo", "") == "bloqueada_incerta"
        rec = await casos.reconciliar(dono, r.execucao.id)
        assert rec.estado == "succeeded" and rec.resposta == "conexão VOLC funcionando"

    asyncio.run(roteiro())
    assert len(hermes.chats) == 1


def test_outro_dono_nao_le_e_conflito_de_request_id(dono):
    casos = _montar(HermesFalso())

    async def roteiro():
        c = await casos.criar_conversa(dono)
        estranho = str(uuid.uuid4())
        assert await casos._ledger.historico(estranho, c.id) is None
        rid = str(uuid.uuid4())
        r = await casos.reservar_envio(dono, c.id, rid, "a", None)
        await casos.executar(dono, r.execucao.id, None)
        with pytest.raises(Exception) as recusa:
            await casos.reservar_envio(dono, c.id, rid, "b", None)
        assert getattr(recusa.value, "motivo", "") == "conflito"

    asyncio.run(roteiro())


def test_rpc_ausente_vira_ledger_indisponivel():
    ledger = LedgerSupabase("https://lab.invalid", "service-do-lab",
                            transport=httpx.MockTransport(lambda r: httpx.Response(404, json={})))
    with pytest.raises(LedgerIndisponivel):
        asyncio.run(ledger.listar_conversas(str(uuid.uuid4()), 5))
