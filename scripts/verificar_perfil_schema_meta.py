#!/usr/bin/env python3
"""Verificador dos perfis de schema do trilho Meta (e do ledger PMax).

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

    --runtime     o manifesto cobre TODAS as RPCs que o código do PERFIL chama.
                  Esta é a conferência que teria pego R0-A01 sozinha, e ela é
                  derivada do CÓDIGO — não de uma lista escrita à mão que
                  envelhece em silêncio. A fonte do código é declarada POR
                  PERFIL em `runtime_contract.derivado_de`: o nascimento lê
                  `meta_execucao/registro.py`, o read model lê
                  `meta/read_model.py`. Uma fonte única para todo perfil foi o
                  que deixou `trafego_meta_persistir_snapshot` — chamada em
                  produção — fora de qualquer contrato.

    --catalogo    classifica um catálogo VIVO por coluna, constraint, índice,
                  gatilho, RLS, assinatura de função e grant. Existência de
                  tabela não distingue "CREATE_ONLY antigo" de "perfil
                  atualizado", e foi exatamente essa confusão que o manifesto
                  anterior carregava.

    --lista-apply imprime a lista canônica, para a prova SQL consumir a MESMA.

## LACUNA NOMEADA não é sucesso

⚠️ Quando um perfil não declara contrato de runtime, ou não declara sonda de
catálogo, este programa DIZ ISSO e sai diferente de zero. Pular em silêncio o
que não está declarado é o mesmo defeito de R0-A01 com outra roupa: o verde
passaria a afirmar uma cobertura que ninguém mediu. Uma lacuna se fecha
declarando o contrato — nunca afrouxando a conferência.

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
PERFIL_PADRAO = "CREATE_ONLY"

#: ⚠️ Casa as DUAS formas de chamada que existem no repositório:
#: `self._rpc("nome"` (backend/app/trafego/meta_execucao/registro.py:136) e
#: `self._supa.rpc("nome"` (backend/app/trafego/meta/read_model.py:347). A regex
#: anterior só conhecia a primeira, e por isso o verificador era CEGO para
#: `trafego_meta_persistir_snapshot` — uma RPC de produção, chamada também por um
#: terceiro consumidor fora do backend (n8n/volc_meta_insights_dia_d1.json:451).
#: `\b` antes do `_?` ancora no ponto do atributo e evita casar a DEFINIÇÃO
#: (`def _rpc(self, funcao: str` — sem aspas depois do parêntese).
PADRAO_CHAMADA_RPC = re.compile(r'\b_?rpc\(\s*"([a-z0-9_]+)"')

#: `defined_by` é o ÚLTIMO arquivo do apply_order que emite um CREATE para o
#: nome. Onze das quatorze funções do nascimento são recriadas por mais de um
#: degrau; conferir contra o primeiro aprovaria uma assinatura já substituída.
PADRAO_CREATE_FUNCTION = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+public\.([a-z0-9_]+)")


class Violacao(Exception):
    """Um fato que fecha a janela. Nunca um aviso."""


class LacunaNomeada(Exception):
    """Algo que o manifesto NÃO declara — e cuja ausência não pode passar calada.

    Distinta de `Violacao` só na mensagem: as duas fecham a janela. A separação
    existe para o operador saber se o conserto é corrigir um fato declarado ou
    declarar um fato que falta.
    """


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

def fontes_de_rpc(perfil: dict) -> list[Path]:
    """Os arquivos de código que ESTE perfil serve — declarados no manifesto.

    ⚠️ A fonte é POR PERFIL, e não uma constante do script. Enquanto ela era uma
    constante apontando para `meta_execucao/registro.py`, dois perfis erravam ao
    mesmo tempo: META_READ_MODEL era reprovado por não declarar RPCs do
    nascimento (que ele não serve), e `trafego_meta_persistir_snapshot` — que
    ele SERVE, e que roda em produção — não era cobrada de ninguém.
    """
    contrato = perfil.get("runtime_contract")
    if not contrato:
        raise LacunaNomeada(
            f"o perfil {perfil['id']} não declara contrato de runtime "
            "(`runtime_contract`): nenhuma RPC deste perfil está sendo conferida "
            "contra o código. Declare o contrato no manifesto — a conferência "
            "não pode ser pulada em silêncio")
    declarado = contrato.get("derivado_de")
    caminhos = [declarado] if isinstance(declarado, str) else list(declarado or [])
    if not caminhos:
        raise LacunaNomeada(
            f"o perfil {perfil['id']} declara `runtime_contract` sem "
            "`derivado_de`: a lista de RPCs ficaria escrita à mão, que é "
            "exatamente a lista que envelhece em silêncio")
    return [RAIZ / caminho for caminho in caminhos]


def rpcs_do_runtime(perfil: dict) -> set[str]:
    """As RPCs que o código REALMENTE chama, lidas dos arquivos do perfil."""
    chamadas: set[str] = set()
    for caminho in fontes_de_rpc(perfil):
        if not caminho.exists():
            raise Violacao(
                f"{caminho.relative_to(RAIZ)}: declarada em "
                "`runtime_contract.derivado_de` e AUSENTE no repositório")
        chamadas |= set(PADRAO_CHAMADA_RPC.findall(caminho.read_text(encoding="utf-8")))
    return chamadas


def conferir_runtime(perfil: dict) -> list[str]:
    problemas: list[str] = []
    contrato = perfil.get("runtime_contract", {}).get("rpcs", [])
    declaradas = {rpc["name"] for rpc in contrato}
    chamadas = rpcs_do_runtime(perfil)

    faltando = sorted(chamadas - declaradas)
    if faltando:
        problemas.append(
            "o runtime chama RPCs que o perfil não declara: " + ", ".join(faltando))
    sobrando = sorted(declaradas - chamadas)
    if sobrando:
        problemas.append(
            "o perfil declara RPCs que o runtime não chama: " + ", ".join(sobrando))

    # Toda RPC declarada precisa ser CRIADA por algum arquivo da lista de apply,
    # e o arquivo que vale é o ÚLTIMO que a cria — não o primeiro.
    criadores: dict[str, str] = {}
    for passo in perfil["apply_order"]:
        caminho = RAIZ / passo["file"]
        if not caminho.exists():
            continue
        corpo = caminho.read_text(encoding="utf-8")
        for nome in PADRAO_CREATE_FUNCTION.findall(corpo):
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

#: Cada chave de sonda e onde ela é procurada no JSON do catálogo, mais o rótulo
#: da falta. ⚠️ Sonda com chave DESCONHECIDA é violação, não campo ignorado: um
#: `contraints:` digitado errado passaria silenciosamente e o degrau inteiro
#: seria dado como presente sem nada ter sido conferido.
SONDAS: dict[str, tuple[tuple[str, ...], str]] = {
    "relations": (("relations",), "relação ausente"),
    "columns": (("columns",), "coluna ausente"),
    "constraints": (("constraints",), "constraint ausente"),
    "indexes": (("indexes",), "índice ausente"),
    "triggers": (("triggers",), "gatilho ausente"),
    "functions": (("functions",), "assinatura ausente"),
    "granted_to_service_role": (("granted",), "sem EXECUTE para service_role"),
    "grants": (("grants",), "grant ausente"),
    "rls_enabled": (("rls", "enabled"), "sem ROW LEVEL SECURITY"),
    "rls_forced": (("rls", "forced"), "sem FORCE ROW LEVEL SECURITY"),
    "policies": (("rls", "policies"), "policy ausente"),
}


def _no_catalogo(catalogo: dict, caminho: tuple[str, ...]) -> list:
    atual: object = catalogo
    for chave in caminho:
        if not isinstance(atual, dict):
            return []
        atual = atual.get(chave)
    return list(atual) if isinstance(atual, list) else []


def _assinaturas(catalogo: dict) -> list[str]:
    """As assinaturas vivas, aceitando as duas formas que o leitor emite.

    `functions` é lista de string (o contrato antigo, e o que o leitor continua
    emitindo). `functions_detail` é a mesma coisa com retorno e `prosecdef`.
    Aceitar as duas evita que uma troca no leitor faça o verificador aprovar um
    catálogo que ele deixou de conseguir ler.
    """
    cruas = catalogo.get("functions") or []
    if cruas and isinstance(cruas[0], dict):
        return [item.get("signature", "") for item in cruas]
    if cruas:
        return list(cruas)
    return [item.get("signature", "")
            for item in catalogo.get("functions_detail") or []]


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
    índice, gatilho, RLS, assinatura de função e grant, porque é isso que separa
    "CREATE_ONLY antigo" de "perfil atualizado": as duas instalações têm as
    mesmas três tabelas.
    """
    degraus = _degraus(perfil)
    if not degraus:
        # ⚠️ Zero sonda NÃO é "nada aplicado". Sem sonda nenhuma o classificador
        # devolveria NAO_APLICADO para um catálogo completo, e o operador
        # aplicaria por cima do que já existe.
        return "SEM_SONDA_DECLARADA", [
            f"o perfil {perfil['id']} não declara `catalog_probe` em nenhum "
            "degrau: não há como distinguir aplicado de ausente"]

    presentes: list[str] = []
    faltando: list[str] = []
    for passo in degraus:
        ausentes = _ausentes(passo["catalog_probe"], catalogo)
        if not ausentes:
            presentes.append(Path(passo["file"]).name)
        else:
            faltando.extend(f"{Path(passo['file']).name}: {item}" for item in ausentes)

    nomes = [Path(p["file"]).name for p in degraus]
    completos = [nome for nome in nomes if nome in presentes]
    if not completos:
        return "NAO_APLICADO", faltando
    # Um degrau presente DEPOIS de um ausente é estado parcial: alguém aplicou
    # fora de ordem, ou uma reversão parou no meio. Nunca é "atualizar o resto".
    prefixo = 0
    for nome in nomes:
        if nome in presentes:
            prefixo += 1
        else:
            break
    if prefixo != len(completos):
        return "PARCIAL_OU_DIVERGENTE", faltando
    if prefixo == len(nomes):
        return "PERFIL_ATUAL", []
    return f"ESCADA_INCOMPLETA_ATE_{nomes[prefixo - 1]}", faltando


def _ausentes(sonda: dict, catalogo: dict) -> list[str]:
    faltas: list[str] = []
    for chave, esperados in sonda.items():
        if chave not in SONDAS:
            faltas.append(
                f"sonda desconhecida no manifesto: {chave} "
                f"(conhecidas: {', '.join(sorted(SONDAS))})")
            continue
        caminho, rotulo = SONDAS[chave]
        vivos = _assinaturas(catalogo) if chave == "functions" \
            else _no_catalogo(catalogo, caminho)
        for esperado in esperados:
            if esperado not in vivos:
                faltas.append(f"{rotulo}: {esperado}")
    return faltas


def conferir_contrato_no_catalogo(perfil: dict, catalogo: dict) -> list[str]:
    """As assinaturas e grants que o runtime exige, conferidos no catálogo real.

    ⚠️ A comparação é por ASSINATURA DE IDENTIDADE (nome + tipos), nunca por
    nome só. Uma sobrecarga antiga viva ao lado da nova deixa o PostgREST sem
    conseguir escolher, e as duas param de responder — sintoma que "a função
    existe" nunca detecta.
    """
    problemas: list[str] = []
    vivas = _assinaturas(catalogo)
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
    lacunas: list[str] = []
    # Sem opção nenhuma, roda as duas conferências que não precisam de banco.
    tudo = not (opcoes.arquivos or opcoes.runtime or opcoes.catalogo)
    if opcoes.arquivos or tudo:
        problemas += conferir_arquivos(perfil)
    if opcoes.runtime or tudo:
        # ⚠️ Um perfil sem `runtime_contract` não é um perfil conferido: é um
        # perfil cuja conferência ninguém declarou. Antes, `conferir_runtime`
        # rodava para QUALQUER perfil contra uma fonte fixa, e META_READ_MODEL
        # reprovava por não declarar RPCs que ele nunca serviu.
        try:
            problemas += conferir_runtime(perfil)
        except LacunaNomeada as lacuna:
            lacunas.append(str(lacuna))
        except Violacao as violacao:
            problemas.append(str(violacao))
    if opcoes.catalogo:
        catalogo = json.loads(Path(opcoes.catalogo).read_text(encoding="utf-8"))
        estado, faltas = classificar(perfil, catalogo)
        print(f"estado do catálogo: {estado}")
        for falta in faltas:
            print(f"   · {falta}")
        if estado == "SEM_SONDA_DECLARADA":
            lacunas.extend(faltas)
        else:
            problemas += conferir_contrato_no_catalogo(perfil, catalogo)
            if estado != "PERFIL_ATUAL":
                problemas.append(
                    f"o catálogo não está no perfil atual: {estado}")

    if problemas or lacunas:
        if problemas:
            print(f"FALHA: {len(problemas)} violação(ões) do perfil", file=sys.stderr)
            for problema in problemas:
                print(f"   · {problema}", file=sys.stderr)
        if lacunas:
            print(f"LACUNA NOMEADA: {len(lacunas)} conferência(s) que o manifesto "
                  "não declara — isto NÃO é sucesso", file=sys.stderr)
            for lacuna in lacunas:
                print(f"   · {lacuna}", file=sys.stderr)
        return 1
    print(f"perfil {opcoes.perfil}: conferido")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
