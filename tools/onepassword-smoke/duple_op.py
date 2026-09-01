#!/usr/bin/env python3
"""Duplê controlado do binário `op`, usado APENAS pelo autoteste do smoke.

POR QUE ELE EXISTE: nesta máquina, em 01/09/2026, `which op` devolve
"op not found" e `/Applications/1Password.app` não existe. Sem duplê, a lógica
do smoke — mascaramento, varredura de eco, tipagem dos estados — ficaria sem
prova nenhuma até alguém instalar o 1Password. O duplê imita só o que a
documentação de www.1password.dev declara, nada além:

  * `op --version`
  * `op account list [--format=json]`
  * `op vault list [--format=json]`
  * `op item list --vault <x> [--format=json]`
  * `op run -- <comando>`, que "injeta segredos como variáveis de ambiente
    apenas pela duração do subprocesso" e oculta por padrão segredos impressos
    em stdout/stderr.

Ele é copiado como `op` para um diretório temporário e só entra no PATH quando
o smoke recebe `--duple <dir>` — nunca por conta própria.

MODOS (via VOLC_DUPLE_MODO):
  feliz         -> tudo funciona e o mascaramento funciona
  vazamento     -> mascaramento QUEBRADO: ecoa o segredo em stderr
  app_bloqueado -> `account list` falha com LostConnectionToApp
  sem_contas    -> `account list` falha com "No accounts configured..."
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

MODO = os.environ.get("VOLC_DUPLE_MODO", "")
VALOR = os.environ.get("VOLC_DUPLE_VALOR", "")

# Nomes claramente sintéticos: se um deles vazar para um recibo, fica óbvio que
# a execução foi de duplê e não de cofre real.
ID_COFRE = "dupletestvaultid0000000000"
ID_ITEM = "dupletestitemid00000000000"
NOME_COFRE = "duple-vault"
NOME_ITEM = "duple-item"

MASCARA = "<concealed by 1Password>"


def morrer(mensagem: str, codigo: int = 1) -> int:
    sys.stderr.write(f"[ERROR] 2026/09/01 00:00:00 {mensagem}\n")
    return codigo


def cmd_account_list() -> int:
    if MODO == "app_bloqueado":
        # String documentada para app travado/headless.
        return morrer("error initializing client: LostConnectionToApp")
    if MODO == "sem_contas":
        return morrer("No accounts configured for use with 1Password CLI")
    print(
        json.dumps(
            [
                {
                    "url": "duple.1password.invalid",
                    "email": "duple@invalid.invalid",
                    "user_uuid": "dupletestuserid00000000000",
                    "account_uuid": "dupletestacctid00000000000",
                }
            ]
        )
    )
    return 0


def cmd_vault_list() -> int:
    print(json.dumps([{"id": ID_COFRE, "name": NOME_COFRE}]))
    return 0


def cmd_item_list() -> int:
    print(
        json.dumps(
            [
                {
                    "id": ID_ITEM,
                    "title": NOME_ITEM,
                    "vault": {"id": ID_COFRE, "name": NOME_COFRE},
                }
            ]
        )
    )
    return 0


def cmd_run(argumentos: list[str]) -> int:
    """Resolve referências `op://` do ambiente e roda o comando depois de `--`."""
    if "--no-masking" in argumentos:
        # Nem o duplê aceita: o preflight do smoke deve barrar antes de chegar aqui.
        return morrer("duple: --no-masking e proibido neste smoke", 2)
    if "--" not in argumentos:
        return morrer("duple: `op run` exige `--` antes do comando", 2)
    comando = argumentos[argumentos.index("--") + 1:]
    if not comando:
        return morrer("duple: nada para executar depois de `--`", 2)

    ambiente = os.environ.copy()
    injetadas = 0
    for chave, valor in list(ambiente.items()):
        if valor.startswith("op://"):
            ambiente[chave] = VALOR
            injetadas += 1
    if injetadas == 0:
        return morrer("duple: nenhuma variavel com referencia op:// no ambiente", 2)

    proc = subprocess.run(comando, env=ambiente, capture_output=True, text=True, check=False)
    saida, erro = proc.stdout, proc.stderr
    if MODO == "vazamento":
        # Mascaramento quebrado de propósito, e ainda ecoa o segredo por conta
        # própria — é exatamente isto que a varredura do smoke tem de pegar.
        erro = erro + f"debug: segredo resolvido = {VALOR}\n"
    else:
        saida = saida.replace(VALOR, MASCARA)
        erro = erro.replace(VALOR, MASCARA)
    sys.stdout.write(saida)
    sys.stderr.write(erro)
    return proc.returncode


def main(argv: list[str]) -> int:
    if not MODO:
        return morrer("duple: VOLC_DUPLE_MODO ausente; o duple nao adivinha modo", 3)
    if not VALOR:
        # Ausência é ausência explícita: sem valor de teste o duplê recusa em vez
        # de fabricar um segredo.
        return morrer("duple: VOLC_DUPLE_VALOR ausente; o duple nao inventa segredo", 3)
    if not argv:
        return morrer("duple: nenhum subcomando", 2)
    if argv[0] in ("--version", "-v", "version"):
        # Versão sintética de propósito: a documentação não declara versão mínima
        # e o duplê não vai inventar uma que pareça real.
        print("0.0.0-duple")
        return 0
    if argv[0] == "account" and len(argv) > 1 and argv[1] == "list":
        return cmd_account_list()
    if argv[0] == "vault" and len(argv) > 1 and argv[1] == "list":
        return cmd_vault_list()
    if argv[0] == "item" and len(argv) > 1 and argv[1] == "list":
        return cmd_item_list()
    if argv[0] == "run":
        return cmd_run(argv[1:])
    return morrer(f"duple: subcomando nao imitado: {argv[0]}", 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
