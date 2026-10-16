"""Shadow NUNCA escreve fora: não há porta de escrita externa no código, e o ledger só toca o diretório dado."""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

import volc_dil.fundacao.shadow as pacote
from volc_dil.fundacao.shadow._gerador_provisorio import preparar
from volc_dil.fundacao.shadow.ledger import LedgerShadow, SinkJsonl
from volc_dil.fundacao.shadow.motor import executar_replay
from volc_dil.fundacao.shadow.politicas import catalogo_padrao

RAIZ = Path(pacote.__file__).resolve().parent
MODULOS_PROIBIDOS = ("socket", "http", "urllib", "requests", "httpx", "aiohttp", "psycopg", "psycopg2", "asyncpg",
                     "sqlalchemy", "supabase", "subprocess", "smtplib", "ftplib", "paramiko", "google", "grpc",
                     "websocket", "boto3", "openai", "anthropic")
CHAMADAS_PROIBIDAS = ("mutate", "system", "popen", "post", "put", "patch", "delete", "exec", "eval", "urlopen",
                      "connect", "send", "sendall", "execute", "executemany", "publicar", "ativar")


def violacoes(fonte: str) -> list[str]:
    arv = ast.parse(fonte)
    v = []
    for no in ast.walk(arv):
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.name.split(".")[0] in MODULOS_PROIBIDOS:
                    v.append(f"import {a.name}")
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            if no.module.split(".")[0] in MODULOS_PROIBIDOS:
                v.append(f"from {no.module}")
        elif isinstance(no, ast.Call):
            nome = no.func.attr if isinstance(no.func, ast.Attribute) else getattr(no.func, "id", "")
            if nome.lower() in CHAMADAS_PROIBIDAS or nome.lower().startswith("mutate"):
                v.append(f"chamada {nome}()")
            if nome == "open" and len(no.args) >= 2 and isinstance(no.args[1], ast.Constant) and any(
                    c in str(no.args[1].value) for c in "wax+"):
                v.append(f"open(..., {no.args[1].value!r})")
    return v


def test_varredura_estatica_sem_rede_banco_subprocess_mutate():
    arquivos = sorted(RAIZ.glob("*.py"))
    assert len(arquivos) >= 10
    achados = {}
    for f in arquivos:
        v = violacoes(f.read_text(encoding="utf-8"))
        if f.name == "ledger.py":  # único escritor: append no arquivo do sink
            v = [x for x in v if x != "open(..., 'a')"]
        if v:
            achados[f.name] = v
    assert achados == {}


@pytest.mark.parametrize("fonte", [
    "import psycopg\n", "from urllib.request import urlopen\n", "import subprocess\nsubprocess.run(['x'])\n",
    "cliente.mutate(ops)\n", "open('x', 'w')\n", "import requests\nrequests.post('u')\n", "os.system('rm')\n",
])
def test_contraprova_a_varredura_pega_cada_padrao(fonte):
    assert violacoes(fonte)


def test_em_execucao_so_o_arquivo_do_ledger_e_escrito(tmp_path, monkeypatch):
    fs, cortes, cfg = preparar("base", passo_horas=24, hora_inicial=7)
    destino = tmp_path / "ledger_dir"
    destino.mkdir()
    escritas: list[str] = []
    original = builtins.open

    def espiao(arquivo, modo="r", *a, **k):
        if any(c in modo for c in "wax+"):
            escritas.append(str(Path(arquivo).resolve()))
        return original(arquivo, modo, *a, **k)

    monkeypatch.setattr(builtins, "open", espiao)
    antes = set(p for p in tmp_path.rglob("*"))
    led = LedgerShadow(SinkJsonl(destino))
    executar_replay(fs.observacoes, cortes, catalogo_padrao(), config=cfg, ledger=led)
    monkeypatch.setattr(builtins, "open", original)
    alvo = str((destino / "ledger.jsonl").resolve())
    assert escritas and set(escritas) == {alvo}
    novos = set(p for p in tmp_path.rglob("*")) - antes
    assert novos == {destino / "ledger.jsonl"}


def test_nenhuma_proposta_do_catalogo_e_executavel():
    fs, cortes, cfg = preparar("base", passo_horas=24, hora_inicial=7)
    res = executar_replay(fs.observacoes, cortes, catalogo_padrao(), config=cfg)
    assert all(p.executavel is False for d in res.decisoes for p in d.decisao.propostas)
    assert all(p["executavel"] is False for d in res.decisoes for p in d.decisao.para_json()["propostas"])
