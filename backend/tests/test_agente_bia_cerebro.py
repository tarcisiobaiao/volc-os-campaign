"""Cérebro pela web: rascunho pela Bia (sem ferramenta) e gravação tipada pelo executor.

O executor REAL (`deploy/cerebro-web/volc_cerebro_web.py`) roda aqui contra três
repositórios git temporários; no lugar do `ssh`, um programa falso que só o
executa — o protocolo (JSON no stdin/stdout) é o mesmo do comando forçado.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from app.agente_bia import rotas
from app.agente_bia.cerebro import dominio as cdom
from app.agente_bia.cerebro.infra_ssh import ExecutorCerebroSSH
from test_agente_bia import ADMIN_A, Banca  # noqa: F401

pytestmark = [pytest.mark.identidade_real, pytest.mark.sem_env_file]

EXECUTOR = Path(__file__).resolve().parents[2] / "deploy" / "cerebro-web" / "volc_cerebro_web.py"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout


@pytest.fixture
def cerebros(tmp_path, monkeypatch):
    raiz = tmp_path / "cerebros"
    for nome in ("cerebro-volc", "cerebro-arbitragem", "cerebro-pessoal"):
        repo = raiz / nome
        repo.mkdir(parents=True)
        _git(repo, "init", "-q", "-b", "main")
        (repo / "MAPA.md").write_text("# mapa\n")
        (repo / "SOUL.md").write_text("identidade\n")
        _git(repo, "add", "MAPA.md", "SOUL.md")
        _git(repo, "commit", "-q", "-m", "inicio")
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        (repo / "inbox" / "bia-web").mkdir(parents=True)
    monkeypatch.setenv("VOLC_CEREBROS_RAIZ", str(raiz))
    return raiz


def _ssh_falso(tmp_path: Path) -> str:
    prog = tmp_path / "ssh-falso"
    prog.write_text(f"#!/bin/sh\nexec {sys.executable} {EXECUTOR}\n")
    prog.chmod(prog.stat().st_mode | stat.S_IEXEC)
    return str(prog)


@pytest.fixture
def banca(monkeypatch, tmp_path, cerebros):
    b = Banca(monkeypatch)
    chave = tmp_path / "chave"
    chave.write_text("x")
    b.executor = ExecutorCerebroSSH("volc-cerebro-web@vps.exemplo", str(chave), programa=_ssh_falso(tmp_path))
    b.app.dependency_overrides[rotas.executor_cerebro] = lambda: b.executor
    yield b
    b.fechar()


def _captura(**extra):
    base = {"request_id": str(uuid.uuid4()), "destino": "volc", "titulo": "Paridade web: atalhos do cérebro",
            "tipo": "decisao", "conteudo": "## Decisões\n- Botões chamam executor tipado.\n\n## Hipóteses\n- Usar no dia a dia.",
            "tags": ["bia", "Cérebro Web"]}
    return {**base, **extra}


# ── rascunho (fase A) ───────────────────────────────────────────────────────

def test_rascunho_e_pedido_do_servidor_e_sem_anexo(banca):
    cid = banca.nova()
    r = banca.cliente.post(f"/api/agent/conversations/{cid}/messages", headers=banca.h(),
                           json={"request_id": str(uuid.uuid4()), "intencao": "rascunho_cerebro",
                                 "texto": "foque nas decisões de hoje"})
    assert r.status_code == 202, r.text
    [e] = banca.historico(cid).json()["execucoes"]
    assert e["contexto"]["intencao"] == "rascunho_cerebro"
    [chat] = banca.hermes.chats
    enviado = json.loads(chat.content)["input"]
    assert "CAPTURA" in enviado and "SEM salvar nada" in enviado and "foque nas decisões de hoje" in enviado
    assert "```json" in enviado
    r = banca.cliente.post(f"/api/agent/conversations/{cid}/messages", headers=banca.h(),
                           json={"request_id": str(uuid.uuid4()), "intencao": "rascunho_cerebro",
                                 "contexto": {"campaign_ref": "c1", "janela": "ultimos_7_dias"}})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "intencao_invalida"


def test_intencao_desconhecida_e_recusada(banca):
    cid = banca.nova()
    r = banca.cliente.post(f"/api/agent/conversations/{cid}/messages", headers=banca.h(),
                           json={"request_id": str(uuid.uuid4()), "intencao": "salvar_direto", "texto": "x"})
    assert r.status_code == 422


# ── gravação (fase B) ───────────────────────────────────────────────────────

def test_grava_uma_captura_nova_na_estacao_com_sidecar(banca, cerebros):
    r = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura())
    assert r.status_code == 201, r.text
    c = r.json()["captura"]
    assert c["repo"] == "cerebro-volc" and c["caminho"].startswith("inbox/bia-web/")
    assert c["caminho"].endswith("-paridade-web-atalhos-do-cerebro.md")
    assert c["salvo_no_servidor"] is True and c["sincronizado_github"] is False
    assert c["git"] == {"estado": "??", "commitado": False, "sincronizado_github": False}
    repo = cerebros / "cerebro-volc"
    arquivo = repo / c["caminho"]
    assert arquivo.read_text().startswith("# Paridade web: atalhos do cérebro\n")
    meta = (repo / c["sidecar"]).read_text()
    assert 'autor: "bia-web"' in meta and 'tipo: "proposta-canonica"' in meta and 'maturidade: "draft"' in meta
    assert 'tags: ["bia", "cerebro-web"]' in meta
    assert _git(repo, "log", "--oneline").count("\n") == 1          # nenhum commit novo
    assert (repo / "SOUL.md").read_text() == "identidade\n"         # nada fora da estação


def test_mesmo_request_id_devolve_o_mesmo_arquivo(banca):
    corpo = _captura()
    a = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=corpo)
    b = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=corpo)
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["captura"]["caminho"] == b.json()["captura"]["caminho"]
    assert b.json()["captura"]["ja_existia"] is True


def test_nunca_sobrescreve_arquivo_existente(banca, cerebros):
    a = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura()).json()["captura"]
    b = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura()).json()["captura"]
    assert a["caminho"] != b["caminho"] and b["caminho"].endswith("-2.md")


@pytest.mark.parametrize("campo,valor,codigo", [
    ("conteudo", "token=abc123 da conta", "parece_segredo"),
    ("conteudo", "ghp_" + "a" * 30, "parece_segredo"),
    ("titulo", "", "titulo_vazio"),
    ("conteudo", "   ", "conteudo_vazio"),
])
def test_recusas_antes_do_executor(banca, cerebros, campo, valor, codigo):
    r = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura(**{campo: valor}))
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == codigo
    assert list((cerebros / "cerebro-volc" / "inbox" / "bia-web").iterdir()) == []


def test_destino_fora_da_lista_e_campo_extra_sao_recusados(banca):
    assert banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(),
                              json=_captura(destino="hermes")).status_code == 422
    assert banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(),
                              json=_captura(caminho="../../SOUL.md")).status_code == 422


def test_estacao_ausente_ou_symlink_e_recusada(banca, cerebros, tmp_path):
    estacao = cerebros / "cerebro-pessoal" / "inbox" / "bia-web"
    estacao.rmdir()
    fora = tmp_path / "fora"
    fora.mkdir()
    estacao.symlink_to(fora)
    r = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura(destino="pessoal"))
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "estacao_ausente"
    assert list(fora.iterdir()) == []


def test_rascunho_de_outro_dono_e_404(banca):
    cid = banca.nova()
    banca.cliente.post(f"/api/agent/conversations/{cid}/messages", headers=banca.h(),
                       json={"request_id": str(uuid.uuid4()), "intencao": "rascunho_cerebro"})
    [e] = banca.historico(cid).json()["execucoes"]
    r = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h("tok-admin-b"),
                           json=_captura(execucao_id=e["id"]))
    assert r.status_code == 404
    ok = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura(execucao_id=e["id"]))
    assert ok.status_code == 201


def test_status_so_leitura_dos_tres(banca, cerebros):
    banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura())
    indice = cerebros / "cerebro-volc" / ".git" / "index"
    antes = indice.stat().st_mtime_ns
    r = banca.cliente.get("/api/agent/cerebro/status", headers=banca.h())
    assert r.status_code == 200, r.text
    repos = {x["cerebro"]: x for x in r.json()["repos"]}
    assert set(repos) == {"volc", "arbitragem", "pessoal"}
    assert repos["volc"]["capturas_web_pendentes"] == 1 and repos["volc"]["alteracoes"] == 0
    assert repos["volc"]["a_frente"] == 0 and repos["volc"]["atras"] == 0 and repos["volc"]["estacao_web"]
    assert indice.stat().st_mtime_ns == antes                        # nem o índice foi reescrito
    via_comando = banca.cliente.post("/api/agent/comandos/cerebro", headers=banca.h(), json={})
    assert via_comando.status_code == 200 and via_comando.json()["recibo"]["somente_leitura"] is True


def test_sem_executor_configurado_e_503_sem_detalhe(banca, monkeypatch):
    banca.app.dependency_overrides[rotas.executor_cerebro] = lambda: ExecutorCerebroSSH(None, None)
    r = banca.cliente.get("/api/agent/cerebro/status", headers=banca.h())
    assert r.status_code == 503 and r.json()["detail"]["codigo"] == "cerebro_nao_configurado"
    r = banca.cliente.post("/api/agent/cerebro/capturas", headers=banca.h(), json=_captura())
    assert r.status_code == 503 and "/salve no Telegram" in r.json()["detail"]["mensagem"]


def test_rotas_do_cerebro_exigem_admin(banca):
    assert banca.cliente.get("/api/agent/cerebro/status").status_code == 401
    assert banca.cliente.post("/api/agent/cerebro/capturas", json=_captura()).status_code == 401


def test_executor_recusa_pedido_desconhecido_e_lixo(cerebros):
    for entrada, codigo in ((b'{"op":"rm"}', "op_desconhecida"), (b"nao json", "pedido_invalido"),
                            (b'{"op":"gravar","destino":"volc","tipo":"nota","titulo":"t","conteudo":"c",'
                             b'"request_id":"../x"}', "request_id_invalido")):
        r = subprocess.run([sys.executable, str(EXECUTOR)], input=entrada, capture_output=True,
                           env={**os.environ})
        assert json.loads(r.stdout)["codigo"] == codigo and r.returncode == 2


def test_dominio_valida_e_limpa():
    c = cdom.validar_captura("arbitragem", "Título‮ invertido", "nota", "texto", ["A B", "a-b", "x" * 50])
    assert c.titulo == "Título invertido" and c.tags == ("a-b", "x" * 32)
    with pytest.raises(cdom.CapturaRecusada):
        cdom.validar_captura("volc", "t", "nota", "x" * (cdom.MAX_CONTEUDO + 1))
