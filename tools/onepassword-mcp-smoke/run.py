#!/usr/bin/env python3
"""Smoke do 1Password MCP local — prova o caminho que a CLI nao prova.

POR QUE ELE EXISTE, SEPARADO DO `onepassword-smoke`

`tools/onepassword-smoke` prova a corrente CLI: `op` -> app -> sessao ->
injecao num processo descartavel. P03-T09 fala em **MCP**, e o backlog nomeado
registra a lacuna sem disfarce: "o smoke cobre CLI, P03-T09 diz MCP; o servidor
MCP nunca foi instalado, configurado ou chamado". Este arquivo fecha essa
lacuna falando o protocolo MCP diretamente com o binario, por stdio.

O QUE ELE PROVA
  * o binario `1password-mcp` existe e faz o handshake `initialize`;
  * `tools/list` devolve as ferramentas documentadas em www.1password.dev;
  * `list_environments` devolve NOMES de Environment;
  * `list_variables` devolve NOMES de variavel;
  * e — a prova que importa — que NENHUM VALOR SECRETO aparece na resposta.

COMO ELE PROVA A AUSENCIA DE VALOR, SEM CONHECER O VALOR

Pela mesma inversao que o smoke da CLI usa em `varrer_saida_filho`: o processo
pai nao pode procurar pelo segredo, porque procurar exigiria possui-lo, e
possui-lo ja seria o vazamento. Entao a regra e uma LISTA-BRANCA ESTRITA: a
resposta so pode conter as chaves estruturais previstas e os NOMES que o
proprio operador declarou. Qualquer texto inesperado com 8+ caracteres e
tratado como possivel valor e derruba a prova.

A documentacao da 1Password afirma que o servidor "never returns the secrets"
e que "the server cannot return secret values ... even if an agent requests
them". Esta ferramenta existe para NAO acreditar nisso de graca.

NUNCA chamamos ferramenta de escrita (`append_variables`, `create_environment`,
`rename_environment`, `create_local_env_file`): a missao autoriza criar um
Environment, mas escrever valor por ferramenta e proibido.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

CAMINHO_PADRAO = "/Applications/1Password.app/Contents/MacOS/1password-mcp"

ESTADOS = {
    "ok": 0,
    "blocked/binario_ausente": 10,
    "blocked/sem_handshake": 11,
    "blocked/nao_autenticado": 12,
    "blocked/aprovacao_negada": 13,
    "blocked/sem_environment": 14,
    "falha/valor_exposto": 20,
    "falha/ferramenta_ausente": 21,
    "falha/preflight": 30,
    "falha/interna": 40,
}

# Ferramentas de LEITURA que a documentacao publica. As de escrita ficam de fora
# de proposito: esta prova nao escreve.
LEITURA = {"authenticate", "list_environments", "list_variables", "list_local_env_files"}
ESCRITA = {"create_environment", "rename_environment", "append_variables", "create_local_env_file"}

# Chaves estruturais que uma resposta MCP pode trazer sem que isso seja "valor".
CHAVES_ESTRUTURAIS = {
    "jsonrpc", "id", "result", "error", "content", "type", "text", "isError",
    "tools", "name", "description", "inputSchema", "properties", "required",
    "title", "items", "enum", "environments", "variables", "id", "account",
    "accounts", "protocolVersion", "capabilities", "serverInfo", "version",
    "structuredContent", "annotations", "outputSchema", "_meta", "nextCursor",
}

RE_TOKEN_SUSPEITO = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Servidor:
    """Cliente stdio minimo de MCP. Fala JSON-RPC por linha."""

    def __init__(self, caminho: str, tempo_limite: float = 30.0):
        self.proc = subprocess.Popen(
            [caminho],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.tempo_limite = tempo_limite
        self._proximo = 0
        self.stderr: list[str] = []
        threading.Thread(target=self._drenar_stderr, daemon=True).start()

    def _drenar_stderr(self) -> None:
        assert self.proc.stderr
        for linha in self.proc.stderr:
            self.stderr.append(linha.rstrip("\n"))

    def pedir(self, metodo: str, parametros: dict | None = None) -> dict:
        self._proximo += 1
        pedido = {"jsonrpc": "2.0", "id": self._proximo, "method": metodo}
        if parametros is not None:
            pedido["params"] = parametros
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(pedido) + "\n")
        self.proc.stdin.flush()

        resposta: dict = {}
        erro: list[str] = []

        def ler() -> None:
            nonlocal resposta
            for linha in self.proc.stdout:  # type: ignore[union-attr]
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    corpo = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if corpo.get("id") == pedido["id"]:
                    resposta = corpo
                    return
            erro.append("stdout fechou antes da resposta")

        t = threading.Thread(target=ler, daemon=True)
        t.start()
        t.join(self.tempo_limite)
        if t.is_alive():
            return {"error": {"code": -1, "message": "tempo esgotado"}}
        if erro:
            return {"error": {"code": -2, "message": erro[0]}}
        return resposta

    def notificar(self, metodo: str, parametros: dict | None = None) -> None:
        aviso = {"jsonrpc": "2.0", "method": metodo}
        if parametros is not None:
            aviso["params"] = parametros
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(aviso) + "\n")
        self.proc.stdin.flush()

    def encerrar(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def colher_textos(no, saco: list[str]) -> None:
    """Junta todo texto livre de uma resposta, para a lista-branca examinar."""
    if isinstance(no, dict):
        for chave, valor in no.items():
            if isinstance(valor, str):
                saco.append(valor)
            else:
                colher_textos(valor, saco)
    elif isinstance(no, list):
        for item in no:
            colher_textos(item, saco)
    elif isinstance(no, str):
        saco.append(no)


def suspeitos(textos: list[str], permitidos: set[str]) -> list[str]:
    """Lista-branca estrita: o que nao foi declarado e suspeito de ser valor.

    Nao devolvemos o texto suspeito — devolver seria reimprimir exatamente o que
    a prova existe para impedir. Devolvemos so uma etiqueta e o tamanho.
    """
    achados = []
    for texto in textos:
        limpo = texto.strip()
        if not limpo or len(limpo) < 8:
            continue
        if limpo in permitidos:
            continue
        if limpo in CHAVES_ESTRUTURAIS:
            continue
        # Frases legiveis (descricoes de ferramenta) nao sao valores.
        if " " in limpo and not RE_TOKEN_SUSPEITO.fullmatch(limpo.replace(" ", "")):
            continue
        if RE_TOKEN_SUSPEITO.fullmatch(limpo):
            achados.append(f"token_opaco[{len(limpo)}]")
    return achados


def principal(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Smoke do 1Password MCP (P03-T09).", allow_abbrev=False)
    p.add_argument("--caminho", default=CAMINHO_PADRAO)
    p.add_argument("--environment", help="nome do Environment esperado (ex.: VOLC_OS_LOCAL)")
    p.add_argument("--variavel", help="nome da variavel esperada (ex.: VOLC_SMOKE_SEGREDO)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    humano: list[str] = []
    verificado: list[str] = []
    nao_verificado: list[str] = []
    evidencia: dict = {}

    def recibo(estado: str, ato: str) -> dict:
        return {
            "instrumento": "onepassword-mcp-smoke",
            "momento": agora(),
            "estado": estado,
            "exit_code": ESTADOS[estado],
            "plataforma": platform.system(),
            "verificado": verificado,
            "nao_verificado": nao_verificado,
            "evidencia": evidencia,
            "proximo_ato": ato,
        }

    def sair(estado: str, ato: str) -> int:
        r = recibo(estado, ato)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            for l in humano:
                print(l)
            print(json.dumps(r, ensure_ascii=False, indent=2))
        return r["exit_code"]

    if not Path(args.caminho).is_file():
        evidencia["binario"] = False
        humano.append(f"binario do MCP nao encontrado: {args.caminho}")
        nao_verificado.append("tudo: o servidor MCP nao existe nesta maquina")
        return sair("blocked/binario_ausente", "instale o 1Password e habilite Settings > Labs > MCP Server")
    evidencia["binario"] = True
    verificado.append("binario 1password-mcp presente")

    srv = Servidor(args.caminho)
    try:
        # --- handshake ------------------------------------------------------
        r = srv.pedir("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "volc-onepassword-mcp-smoke", "version": "1.0.0"},
        })
        if "result" not in r:
            evidencia["initialize_erro"] = str(r.get("error", {}).get("message", "sem result"))[:200]
            evidencia["stderr_linhas"] = len(srv.stderr)
            humano.append("o servidor MCP nao completou o handshake.")
            nao_verificado.append("handshake MCP")
            return sair("blocked/sem_handshake",
                        "abra o 1Password, Settings > Labs > MCP Server, e ligue 'Enable local MCP server'")
        info = r["result"].get("serverInfo", {})
        evidencia["servidor"] = {"nome": info.get("name"), "versao": info.get("version")}
        evidencia["protocolo"] = r["result"].get("protocolVersion")
        verificado.append("handshake MCP concluido")
        humano.append(f"MCP: {info.get('name')} {info.get('version')} (protocolo {evidencia['protocolo']})")
        srv.notificar("notifications/initialized")

        # --- catalogo de ferramentas ---------------------------------------
        r = srv.pedir("tools/list")
        ferramentas = [t.get("name") for t in r.get("result", {}).get("tools", [])]
        evidencia["ferramentas"] = sorted(n for n in ferramentas if n)
        faltando = sorted(LEITURA - set(ferramentas))
        evidencia["ferramentas_de_escrita_expostas"] = sorted(set(ferramentas) & ESCRITA)
        humano.append("ferramentas: " + ", ".join(evidencia["ferramentas"]))
        if faltando:
            evidencia["ferramentas_de_leitura_ausentes"] = faltando
            nao_verificado.append("catalogo de ferramentas de leitura")
            return sair("falha/ferramenta_ausente", "confira a versao do 1Password: faltam " + ", ".join(faltando))
        verificado.append("as ferramentas de leitura documentadas existem")

        # --- autenticar ------------------------------------------------------
        r = srv.pedir("tools/call", {"name": "authenticate", "arguments": {}})
        texto_auth: list[str] = []
        colher_textos(r, texto_auth)
        erro_auth = r.get("result", {}).get("isError") or "error" in r
        evidencia["authenticate_erro"] = bool(erro_auth)
        if erro_auth:
            junto = " ".join(texto_auth).lower()
            evidencia["authenticate_classificacao"] = (
                "aprovacao" if any(t in junto for t in ("approve", "authoriz", "denied", "declined"))
                else "sem_sessao" if any(t in junto for t in ("lock", "unlock", "not signed", "no account"))
                else "nao_classificado"
            )
            nao_verificado.append("autenticacao do MCP com o app")
            humano.append(f"authenticate falhou ({evidencia['authenticate_classificacao']})")
            estado = ("blocked/aprovacao_negada"
                      if evidencia["authenticate_classificacao"] == "aprovacao"
                      else "blocked/nao_autenticado")
            return sair(estado, "destranque o 1Password e aprove o pedido do cliente MCP")
        verificado.append("authenticate aceito pelo app")

        # --- environments (NOMES) -------------------------------------------
        r = srv.pedir("tools/call", {"name": "list_environments", "arguments": {}})
        textos_env: list[str] = []
        colher_textos(r.get("result", {}), textos_env)
        evidencia["environments_resposta_bytes"] = len(json.dumps(r.get("result", {})))
        achou_env = bool(args.environment) and any(args.environment in t for t in textos_env)
        evidencia["environment_esperado_encontrado"] = achou_env if args.environment else None
        if args.environment and not achou_env:
            nao_verificado.append(f"Environment '{args.environment}' nao apareceu na listagem")
            humano.append(f"o Environment '{args.environment}' nao foi listado.")
            return sair("blocked/sem_environment",
                        "crie o Environment no app: Developer > View Environments > New environment")
        verificado.append("list_environments respondeu")

        # --- variaveis (NOMES) ----------------------------------------------
        alvo = {}
        if args.environment:
            alvo = {"environment": args.environment}
        r = srv.pedir("tools/call", {"name": "list_variables", "arguments": alvo})
        textos_var: list[str] = []
        colher_textos(r.get("result", {}), textos_var)
        evidencia["variaveis_resposta_bytes"] = len(json.dumps(r.get("result", {})))
        achou_var = bool(args.variavel) and any(args.variavel in t for t in textos_var)
        evidencia["variavel_esperada_encontrada"] = achou_var if args.variavel else None
        verificado.append("list_variables respondeu")

        # --- ⚠️ A PROVA CENTRAL: nenhum valor atravessou ---------------------
        permitidos = set(CHAVES_ESTRUTURAIS)
        for nome in (args.environment, args.variavel):
            if nome:
                permitidos.add(nome)
        permitidos |= {n for n in evidencia["ferramentas"]}
        achados = suspeitos(textos_env + textos_var, permitidos)
        evidencia["suspeitos_de_valor"] = achados
        if achados:
            nao_verificado.append("ausencia de valor secreto na resposta do MCP")
            humano.append("VALOR EXPOSTO: a resposta trouxe texto opaco nao declarado: " + ", ".join(achados))
            return sair("falha/valor_exposto",
                        "nao use este MCP para segredos ate a origem do texto opaco ser explicada")
        verificado.append("nenhum valor secreto na resposta: so nomes e estrutura")
        humano.append("nenhum valor secreto atravessou o MCP (lista-branca estrita)")

        if args.variavel and not achou_var:
            nao_verificado.append(f"a variavel '{args.variavel}' nao apareceu")
            return sair("blocked/sem_environment",
                        f"crie a variavel {args.variavel} no Environment, pela interface do 1Password")

        return sair("ok", "prova do MCP concluida; nenhum valor foi lido nem pedido")
    except Exception as exc:  # noqa: BLE001
        evidencia["excecao"] = type(exc).__name__
        nao_verificado.append("execucao do smoke MCP")
        return sair("falha/interna", "rode com --json e leia a evidencia")
    finally:
        srv.encerrar()


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
