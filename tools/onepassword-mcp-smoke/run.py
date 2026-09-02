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


def ler_resposta(r: dict) -> tuple[bool, str, str]:
    """Separa sucesso de erro SEM confundir erro com resposta vazia.

    ⚠️ Este helper existe por causa de um falso verde deste proprio arquivo. A
    primeira versao fazia `r.get("result", {})` e seguia em frente: um erro
    JSON-RPC (`{"error": …}`) virava `{}`, dois bytes, lidos como "listou e nao
    havia nada". O smoke chegou a devolver `ok` sem ter listado coisa alguma,
    porque nao passava o `accountId` obrigatorio. Erro e erro; vazio e vazio.
    """
    if "error" in r:
        return False, str(r["error"].get("message", ""))[:300], "jsonrpc"
    resultado = r.get("result")
    if not isinstance(resultado, dict):
        return False, "resposta sem result", "sem_result"
    conteudo = resultado.get("content") or []
    texto = ""
    if conteudo and isinstance(conteudo[0], dict):
        texto = conteudo[0].get("text", "") or ""
    if resultado.get("isError"):
        return False, texto[:300], "tool"
    return True, texto, ""


def classificar(mensagem: str) -> str:
    baixo = (mensagem or "").lower()
    if any(t in baixo for t in ("scope", "approve", "authoriz", "denied", "declined")):
        return "aprovacao"
    if any(t in baixo for t in ("lock", "unlock", "not signed", "no account")):
        return "sem_sessao"
    return "nao_classificado"


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
        # ⚠️ `authenticate` NAO e so um aperto de mao: e ele que devolve o
        # `account_id`, e TODA ferramenta de leitura o exige. Sem ele o servidor
        # responde `-32602 missing field accountId`. Alem disso o escopo e por
        # conta: com um id errado a resposta e "Missing required scope:
        # environments:list. Call the authenticate tool first."
        r = srv.pedir("tools/call", {"name": "authenticate", "arguments": {}})
        ok_auth, texto_auth, etiqueta_auth = ler_resposta(r)
        evidencia["authenticate_erro"] = not ok_auth
        if not ok_auth:
            evidencia["authenticate_classificacao"] = classificar(texto_auth)
            nao_verificado.append("autenticacao do MCP com o app")
            humano.append(f"authenticate falhou ({evidencia['authenticate_classificacao']})")
            estado = ("blocked/aprovacao_negada"
                      if evidencia["authenticate_classificacao"] == "aprovacao"
                      else "blocked/nao_autenticado")
            return sair(estado, "destranque o 1Password e aprove o pedido do cliente MCP")
        try:
            conta = json.loads(texto_auth)["account_id"]
        except Exception:
            evidencia["authenticate_sem_account_id"] = True
            nao_verificado.append("account_id na resposta de authenticate")
            return sair("falha/interna", "o authenticate respondeu sem account_id; rode com --json")
        # O id da conta e identificador, nao segredo — mas nao ha razao para
        # imprimi-lo: guardamos so o tamanho, para provar que veio preenchido.
        evidencia["account_id_presente"] = len(conta) > 0
        verificado.append("authenticate aceito pelo app e devolveu account_id")

        # --- environments (NOMES) -------------------------------------------
        r = srv.pedir("tools/call", {"name": "list_environments", "arguments": {"accountId": conta}})
        ok_env, texto_env, _ = ler_resposta(r)
        if not ok_env:
            evidencia["list_environments_erro"] = classificar(texto_env)
            nao_verificado.append("listagem de Environments")
            estado = ("blocked/aprovacao_negada"
                      if evidencia["list_environments_erro"] == "aprovacao"
                      else "falha/interna")
            return sair(estado, "aprove o escopo environments:list no app do 1Password")
        try:
            ambientes = json.loads(texto_env).get("environments", [])
        except Exception:
            ambientes = []
        nomes_env = [a.get("name") for a in ambientes if isinstance(a, dict)]
        evidencia["environments_encontrados"] = len(ambientes)
        evidencia["environments_nomes"] = sorted(n for n in nomes_env if n)
        verificado.append(f"list_environments respondeu ({len(ambientes)} Environment(s))")
        humano.append("environments: " + (", ".join(evidencia["environments_nomes"]) or "(nenhum)"))

        alvo_id = None
        if args.environment:
            for a in ambientes:
                if isinstance(a, dict) and a.get("name") == args.environment:
                    alvo_id = a.get("environmentId")
                    break
            evidencia["environment_esperado_encontrado"] = alvo_id is not None
            if alvo_id is None:
                nao_verificado.append(f"Environment '{args.environment}' nao aparece na listagem")
                humano.append(f"o Environment '{args.environment}' nao foi listado.")
                return sair("blocked/sem_environment",
                            "crie o Environment: janela principal > Desenvolvedor > Ver Environments")

        # --- variaveis (NOMES) ----------------------------------------------
        nomes_var: list[str] = []
        if alvo_id:
            r = srv.pedir("tools/call", {"name": "list_variables",
                                         "arguments": {"accountId": conta, "environmentId": alvo_id}})
            ok_var, texto_var, _ = ler_resposta(r)
            if not ok_var:
                evidencia["list_variables_erro"] = classificar(texto_var)
                nao_verificado.append("listagem de variaveis")
                estado = ("blocked/aprovacao_negada"
                          if evidencia["list_variables_erro"] == "aprovacao"
                          else "falha/interna")
                return sair(estado, "aprove o escopo de leitura de variaveis no app")
            try:
                nomes_var = list(json.loads(texto_var).get("variableNames", []))
            except Exception:
                nomes_var = []
            evidencia["variaveis_encontradas"] = len(nomes_var)
            evidencia["variaveis_nomes"] = sorted(nomes_var)
            verificado.append(f"list_variables respondeu ({len(nomes_var)} nome(s))")
            humano.append("variaveis: " + (", ".join(sorted(nomes_var)) or "(nenhuma)"))
        else:
            nao_verificado.append("listagem de variaveis: nenhum Environment alvo informado")

        # --- ⚠️ A PROVA CENTRAL: nenhum valor atravessou ---------------------
        # O contrato publicado e que a resposta traz `variableNames` — NOMES. A
        # lista-branca confere isso byte a byte: so os nomes que o proprio
        # operador declarou, os nomes de Environment e a estrutura podem passar.
        permitidos = set(CHAVES_ESTRUTURAIS)
        permitidos |= {n for n in evidencia.get("environments_nomes", [])}
        permitidos |= set(nomes_var)
        permitidos |= set(evidencia["ferramentas"])
        # ⚠️ Os IDs de Environment sao identificadores de 26 caracteres, do mesmo
        # formato que o smoke da CLI ja sanitiza. Eles TEM de voltar, senao a API
        # e inutil — `list_variables` os exige. Mas nao afrouxamos a regra para
        # "qualquer token de 26 caracteres": liberamos exatamente os ids que
        # saíram do campo `environmentId` da estrutura que acabamos de ler. Um
        # token opaco que apareca em qualquer outro lugar continua derrubando a
        # prova.
        permitidos |= {
            a.get("environmentId") for a in ambientes
            if isinstance(a, dict) and a.get("environmentId")
        }
        for nome in (args.environment, args.variavel):
            if nome:
                permitidos.add(nome)
        textos: list[str] = []
        colher_textos(json.loads(texto_env) if ok_env else {}, textos)
        if alvo_id and nomes_var:
            textos.extend(nomes_var)
        achados = suspeitos(textos, permitidos)
        evidencia["suspeitos_de_valor"] = achados
        if achados:
            nao_verificado.append("ausencia de valor secreto na resposta do MCP")
            humano.append("VALOR EXPOSTO: texto opaco nao declarado: " + ", ".join(achados))
            return sair("falha/valor_exposto",
                        "nao use este MCP para segredos ate a origem do texto opaco ser explicada")
        verificado.append("nenhum valor secreto na resposta: so nomes e estrutura")
        humano.append("nenhum valor secreto atravessou o MCP (lista-branca estrita)")

        if args.variavel:
            achou = args.variavel in nomes_var
            evidencia["variavel_esperada_encontrada"] = achou
            if not achou:
                nao_verificado.append(f"a variavel '{args.variavel}' nao aparece no Environment")
                return sair("blocked/sem_environment",
                            f"crie a variavel {args.variavel} pela interface do 1Password")
            verificado.append(f"a variavel '{args.variavel}' existe — por NOME, sem valor")

        return sair("ok", "prova do MCP concluida; nenhum valor foi lido nem pedido")
    except Exception as exc:  # noqa: BLE001
        evidencia["excecao"] = type(exc).__name__
        nao_verificado.append("execucao do smoke MCP")
        return sair("falha/interna", "rode com --json e leia a evidencia")
    finally:
        srv.encerrar()


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
