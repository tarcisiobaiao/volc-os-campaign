#!/usr/bin/env python3
"""Verificador do perfil de schema CREATE_ONLY do nascimento Meta PAUSED.

## Por que ele existe

`SCHEMA-DEPLOY-MANIFEST.json` declarava um perfil que parava na terceira
migration, enquanto o runtime já chamava RPCs que só a quarta e a quinta criam.
Quem seguisse o runbook aplicaria um schema que o código não consegue usar — e
descobriria isso no primeiro despacho, com a janela oficial já aberta.

O conserto não é ajustar o número à mão. É haver UMA lista canônica, no
manifesto, e todo mundo — este verificador, a prova SQL local e o operador — ler
a mesma. Duas listas divergem; é o que aconteceu.

## O que ele confere, e por que cada conferência existe

    --arquivos    sha256 de cada arquivo, dependências declaradas na ordem certa,
                  e NENHUM rollback dentro da lista de apply. Divergência aborta
                  a janela: o que seria aplicado não é o que foi conferido.

    --runtime     o manifesto cobre TODAS as RPCs que `registro.py` chama. Esta
                  é a conferência que teria pego R0-A01 sozinha, e ela é
                  derivada do CÓDIGO — não de uma lista escrita à mão que
                  envelhece em silêncio.

    --catalogo    classifica um catálogo VIVO por colunas, constraints,
                  assinaturas de função e grants. Existência de tabela não
                  distingue "CREATE_ONLY antigo" de "perfil atualizado", e foi
                  exatamente essa confusão que o manifesto anterior carregava.

    --lista-apply imprime a lista canônica, para a prova SQL consumir a MESMA.

## Autoridade

⚠️ Ele NÃO conecta em banco nenhum por conta própria. `--catalogo` lê um arquivo
produzido por `psql` contra um banco que QUEM CHAMA escolheu. Nenhuma
credencial é lida aqui, e nada aponta para o Supabase oficial.

Saída diferente de zero em qualquer violação. Imprimir "FALHA" e sair com zero é
o defeito que este arquivo existe para não repetir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO = (RAIZ / "docs/closure/traffic-operational-closure-v2"
             / "SCHEMA-DEPLOY-MANIFEST.json")
REGISTRO = RAIZ / "backend/app/trafego/meta_execucao/registro.py"
PERFIL_PADRAO = "CREATE_ONLY"


class Violacao(Exception):
    """Um fato que fecha a janela. Nunca um aviso."""


def _perfil(nome: str) -> dict:
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    for perfil in dados["profiles"]:
        if perfil["id"] == nome:
            return perfil
    raise Violacao(f"o manifesto não declara o perfil {nome}")


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# --arquivos
# ---------------------------------------------------------------------------

def conferir_arquivos(perfil: dict) -> list[str]:
    problemas: list[str] = []
    aplicados: list[str] = []
    rollbacks = {
        item["file"] for item in perfil.get("rollback_files_never_in_apply", [])
    }

    for passo in perfil["apply_order"]:
        arquivo = passo["file"]
        caminho = RAIZ / arquivo
        if not caminho.exists():
            problemas.append(f"{arquivo}: declarado no perfil e AUSENTE no repositório")
            continue
        # ⚠️ Rollback dentro da lista de apply é erro de CONSTRUÇÃO da janela,
        # não aviso: um glob ordenado por nome executaria apply e rollback na
        # mesma passada, e o schema ficaria pela metade sem ninguém saber.
        if arquivo in rollbacks:
            problemas.append(f"{arquivo}: é ROLLBACK e está na lista de apply")
        real = _sha256(caminho)
        if real != passo.get("sha256"):
            problemas.append(
                f"{arquivo}: sha256 diverge — manifesto {passo.get('sha256')}, "
                f"arquivo {real}")
        for dependencia in passo.get("depends_on", []):
            if dependencia not in aplicados:
                problemas.append(
                    f"{arquivo}: depende de {dependencia}, que não vem antes na ordem")
        aplicados.append(Path(arquivo).name)

    for item in perfil.get("rollback_files_never_in_apply", []):
        caminho = RAIZ / item["file"]
        if not caminho.exists():
            problemas.append(f"{item['file']}: rollback declarado e ausente")
            continue
        real = _sha256(caminho)
        if real != item.get("sha256"):
            problemas.append(
                f"{item['file']}: sha256 do rollback diverge — "
                f"manifesto {item.get('sha256')}, arquivo {real}")
    return problemas


# ---------------------------------------------------------------------------
# --runtime
# ---------------------------------------------------------------------------

def rpcs_do_runtime() -> set[str]:
    """As RPCs que o backend REALMENTE chama, lidas do código.

    ⚠️ Derivar do código é o ponto. Uma lista escrita à mão no manifesto
    envelhece em silêncio — foi assim que duas RPCs novas ficaram de fora do
    perfil publicado enquanto o runtime já dependia delas.
    """
    fonte = REGISTRO.read_text(encoding="utf-8")
    return set(re.findall(r'_rpc\(\s*"([a-z0-9_]+)"', fonte))


def conferir_runtime(perfil: dict) -> list[str]:
    problemas: list[str] = []
    contrato = perfil.get("runtime_contract", {}).get("rpcs", [])
    declaradas = {rpc["name"] for rpc in contrato}
    chamadas = rpcs_do_runtime()

    faltando = sorted(chamadas - declaradas)
    if faltando:
        problemas.append(
            "o runtime chama RPCs que o perfil não declara: " + ", ".join(faltando))
    sobrando = sorted(declaradas - chamadas)
    if sobrando:
        problemas.append(
            "o perfil declara RPCs que o runtime não chama: " + ", ".join(sobrando))

    # Toda RPC declarada precisa ser CRIADA por algum arquivo da lista de apply,
    # e o arquivo que vale é o ÚLTIMO que a cria — não o primeiro. Onze das
    # dezesseis funções são recriadas por mais de um arquivo da escada.
    criadores: dict[str, str] = {}
    for passo in perfil["apply_order"]:
        caminho = RAIZ / passo["file"]
        if not caminho.exists():
            continue
        corpo = caminho.read_text(encoding="utf-8")
        for nome in re.findall(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+public\.([a-z0-9_]+)", corpo
        ):
            criadores[nome] = Path(passo["file"]).name
    for rpc in contrato:
        nome = rpc["name"]
        real = criadores.get(nome)
        if real is None:
            problemas.append(f"{nome}: nenhum arquivo do perfil cria esta função")
        elif rpc.get("defined_by") != real:
            problemas.append(
                f"{nome}: o perfil diz que é definida por {rpc.get('defined_by')}, "
                f"mas o último CREATE está em {real}")
    return problemas


# ---------------------------------------------------------------------------
# --catalogo
# ---------------------------------------------------------------------------

#: O estado do catálogo, na ordem da escada. Ele é DERIVADO da lista de apply —
#: não enumerado à mão. Uma sexta migration acrescenta um degrau sozinha; uma
#: lista fixa reabriria exatamente o buraco que R0-A01 mediu.
def _degraus(perfil: dict) -> list[dict]:
    return [
        passo for passo in perfil["apply_order"]
        if passo.get("catalog_probe")
    ]


def classificar(perfil: dict, catalogo: dict) -> tuple[str, list[str]]:
    """Diz em que degrau o catálogo está — e o que falta para o próximo.

    ⚠️ A sonda de cada degrau NÃO é "a tabela existe". É coluna, constraint,
    assinatura de função e grant, porque é isso que separa "CREATE_ONLY antigo"
    de "perfil atualizado": as duas instalações têm as mesmas três tabelas.
    """
    presentes: list[str] = []
    faltando: list[str] = []
    for passo in _degraus(perfil):
        sonda = passo["catalog_probe"]
        ausentes = _ausentes(sonda, catalogo)
        if not ausentes:
            presentes.append(Path(passo["file"]).name)
        else:
            faltando.extend(f"{Path(passo['file']).name}: {item}" for item in ausentes)

    degraus = [Path(p["file"]).name for p in _degraus(perfil)]
    completos = [nome for nome in degraus if nome in presentes]
    if not completos:
        return "NAO_APLICADO", faltando
    # Um degrau presente DEPOIS de um ausente é estado parcial: alguém aplicou
    # fora de ordem, ou uma reversão parou no meio. Nunca é "atualizar o resto".
    prefixo = 0
    for nome in degraus:
        if nome in presentes:
            prefixo += 1
        else:
            break
    if prefixo != len(completos):
        return "PARCIAL_OU_DIVERGENTE", faltando
    if prefixo == len(degraus):
        return "PERFIL_ATUAL", []
    return f"ESCADA_INCOMPLETA_ATE_{degraus[prefixo - 1]}", faltando


def _ausentes(sonda: dict, catalogo: dict) -> list[str]:
    faltas: list[str] = []
    for coluna in sonda.get("columns", []):
        if coluna not in catalogo.get("columns", []):
            faltas.append(f"coluna ausente: {coluna}")
    for constraint in sonda.get("constraints", []):
        if constraint not in catalogo.get("constraints", []):
            faltas.append(f"constraint ausente: {constraint}")
    for assinatura in sonda.get("functions", []):
        if assinatura not in catalogo.get("functions", []):
            faltas.append(f"assinatura ausente: {assinatura}")
    for concedida in sonda.get("granted_to_service_role", []):
        if concedida not in catalogo.get("granted", []):
            faltas.append(f"sem EXECUTE para service_role: {concedida}")
    return faltas


def conferir_contrato_no_catalogo(perfil: dict, catalogo: dict) -> list[str]:
    """As assinaturas e grants que o runtime exige, conferidos no catálogo real.

    ⚠️ A comparação é por ASSINATURA DE IDENTIDADE (nome + tipos), nunca por
    nome só. Uma sobrecarga antiga viva ao lado da nova deixa o PostgREST sem
    conseguir escolher, e as duas param de responder — sintoma que "a função
    existe" nunca detecta.
    """
    problemas: list[str] = []
    vivas = catalogo.get("functions", [])
    for rpc in perfil.get("runtime_contract", {}).get("rpcs", []):
        assinatura = f"{rpc['name']}({rpc['identity_args']})"
        if assinatura not in vivas:
            problemas.append(f"assinatura exigida pelo runtime e ausente: {assinatura}")
        # Sobrecarga a mais é tão fatal quanto assinatura a menos.
        homonimas = [f for f in vivas if f.split("(", 1)[0] == rpc["name"]]
        if len(homonimas) > 1:
            problemas.append(
                f"{rpc['name']}: {len(homonimas)} sobrecargas vivas — "
                "nenhuma delas fica chamável pelo PostgREST")
        if rpc.get("service_role_execute", True) and assinatura not in catalogo.get(
            "granted", []
        ):
            problemas.append(f"sem EXECUTE para service_role: {assinatura}")
        if rpc.get("security_definer", True) and assinatura not in catalogo.get(
            "security_definer", []
        ):
            problemas.append(f"perdeu SECURITY DEFINER: {assinatura}")
    return problemas


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--perfil", default=PERFIL_PADRAO)
    argumentos.add_argument("--arquivos", action="store_true")
    argumentos.add_argument("--runtime", action="store_true")
    argumentos.add_argument("--lista-apply", action="store_true")
    argumentos.add_argument(
        "--catalogo", metavar="JSON",
        help="arquivo com o catálogo lido de um banco DESCARTÁVEL")
    opcoes = argumentos.parse_args()

    try:
        perfil = _perfil(opcoes.perfil)
    except (Violacao, KeyError, json.JSONDecodeError) as exc:
        print(f"FALHA: {exc}", file=sys.stderr)
        return 2

    if opcoes.lista_apply:
        for passo in perfil["apply_order"]:
            print(Path(passo["file"]).name)
        return 0

    problemas: list[str] = []
    # Sem opção nenhuma, roda as duas conferências que não precisam de banco.
    tudo = not (opcoes.arquivos or opcoes.runtime or opcoes.catalogo)
    if opcoes.arquivos or tudo:
        problemas += conferir_arquivos(perfil)
    if opcoes.runtime or tudo:
        problemas += conferir_runtime(perfil)
    if opcoes.catalogo:
        catalogo = json.loads(Path(opcoes.catalogo).read_text(encoding="utf-8"))
        estado, faltas = classificar(perfil, catalogo)
        print(f"estado do catálogo: {estado}")
        for falta in faltas:
            print(f"   · {falta}")
        problemas += conferir_contrato_no_catalogo(perfil, catalogo)
        if estado != "PERFIL_ATUAL":
            problemas.append(
                f"o catálogo não está no perfil atual: {estado}")

    if problemas:
        print(f"FALHA: {len(problemas)} violação(ões) do perfil", file=sys.stderr)
        for problema in problemas:
            print(f"   · {problema}", file=sys.stderr)
        return 1
    print(f"perfil {opcoes.perfil}: conferido")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
