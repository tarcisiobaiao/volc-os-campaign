#!/usr/bin/env python3
"""Valida os workflows n8n de ingestão Google Ads campanha-dia — nó a nó.

## Por que este gate existe

"O JSON dá parse" não é validação de workflow. Um JSON perfeitamente parseável
pode ter conexão apontando para nó que não existe, `{{ }}` dentro de um Code
node (onde n8n não interpola nada), `continueOnFail` transformando erro em item
vazio, credencial escrita à mão no corpo, ou uma expressão referenciando
`$node["Config "]` com um espaço a mais — todos silenciosos até a produção.

Este gate confere seis camadas:

1. **estrutura** — chaves obrigatórias, nomes e ids únicos, conexões que
   apontam para nós existentes, alcançabilidade a partir de um gatilho;
2. **nó a nó** — regras específicas de Code, HTTP Request, If, SplitInBatches,
   Limit e Set;
3. **expressões e referências** — `={{ }}` fora de Code, `$node["Nome Exato"]`
   com o nome conferido caractere a caractere, nada de `{{ }}` dentro de JS;
4. **sintaxe real do JavaScript** — cada `jsCode` passa por `node --check`;
5. **contrato GAQL** — cada campo selecionado existe nos descriptors do SDK
   Google Ads v25 instalado (ausência do SDK é PULADO explícito, não prova);
6. **varreduras de segurança** — segredo literal, `*.supabase.co`, mutação
   Google alcançável, chamada de ativação da API do n8n, e `active` verdadeiro.

Uso:
    python3 scripts/validar_workflows_n8n_gads.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ALVOS = [
    RAIZ / "n8n" / "volc_gads_campanha_dia_d0.json",
    RAIZ / "n8n" / "volc_gads_campanha_dia_d1.json",
]

DESTINO_OFICIAL = "database.agenciavolc.com.br"
GOOGLE_HOST = "googleads.googleapis.com"

TIPOS_GATILHO = {
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.executeWorkflowTrigger",
}

# Padrões de segredo. O gate NUNCA imprime o trecho casado.
SEGREDOS = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"), "JWT"),
    (re.compile(r"AIza[0-9A-Za-z_-]{30,}"), "chave Google"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{24,}"), "chave OpenAI"),
    (re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"), "chave privada"),
    (re.compile(r"(?i)(?:developer[_-]?token|service[_-]?role[_-]?key|api[_-]?secret)"
                r"\"?\s*[:=]\s*\"[A-Za-z0-9_\-]{16,}\""), "segredo literal"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-.]{20,}"), "bearer literal"),
]

# Mutação Google Ads. Nenhuma pode ser alcançável a partir destes fluxos.
MUTACAO_GOOGLE = [
    re.compile(r":mutate\b"),
    re.compile(r"\bmutateOperations\b"),
    re.compile(r"\bcampaignBudgets:mutate\b"),
    re.compile(r"(?i)\bgoogleAds:mutate\b"),
    re.compile(r"(?i)\b(campaigns|adGroups|adGroupAds|customers)/[^\"]*:mutate"),
]

# API de ativação do n8n. Nenhum nó pode ligar workflow nenhum.
ATIVACAO_N8N = [
    re.compile(r"/api/v1/workflows/[^\"]*/activate"),
    re.compile(r"/rest/workflows/[^\"]*/activate"),
    re.compile(r"(?i)\"active\"\s*:\s*true"),
    re.compile(r"(?i)n8n-nodes-base\.n8n\b"),
]

# GAQL que não é leitura.
GAQL_ESCRITA = re.compile(r"(?i)\b(insert|update|delete|create|drop|alter|mutate)\b")


class Relatorio:
    def __init__(self) -> None:
        self.ok = 0
        self.falhas: list[str] = []
        self.pulados: list[str] = []

    def prova(self, nome: str, condicao: bool, detalhe: str = "") -> None:
        if condicao:
            self.ok += 1
            print(f"  ok   {nome}")
        else:
            self.falhas.append(nome)
            print(f"  FALHOU  {nome}{(' — ' + detalhe) if detalhe else ''}")

    def pula(self, nome: str, motivo: str) -> None:
        self.pulados.append(nome)
        print(f"  PULADO  {nome} — {motivo}")


def _texto(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _sem_comentarios(js: str) -> str:
    """Remove só linhas INTEIRAS de comentário e blocos `/* */`.

    ⚠️ Conservador de propósito. Um `//` genérico comeria `https://` dentro de
    string e regex, e a primeira versão deste gate acusou como "referência
    quebrada" dois `$('No').all()` que só existiam num COMENTÁRIO explicando o
    que é proibido. Uma prova que falha sobre o próprio texto de aviso não mede
    o workflow.
    """
    sem_bloco = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return "\n".join(
        linha for linha in sem_bloco.splitlines()
        if not linha.lstrip().startswith("//")
    )


def _expressoes(valor, saida: list[str]) -> None:
    if isinstance(valor, str):
        if valor.startswith("="):
            saida.append(valor)
    elif isinstance(valor, dict):
        for v in valor.values():
            _expressoes(v, saida)
    elif isinstance(valor, list):
        for v in valor:
            _expressoes(v, saida)


def validar_estrutura(wf: dict, r: Relatorio, rotulo: str) -> dict[str, dict]:
    for chave in ("name", "nodes", "connections", "settings"):
        r.prova(f"{rotulo} · chave obrigatória '{chave}'", chave in wf)

    nos = {n["name"]: n for n in wf["nodes"]}
    nomes = [n["name"] for n in wf["nodes"]]
    ids = [n["id"] for n in wf["nodes"]]
    r.prova(f"{rotulo} · nomes de nós únicos", len(nomes) == len(set(nomes)))
    r.prova(f"{rotulo} · ids de nós únicos", len(ids) == len(set(ids)))
    r.prova(f"{rotulo} · workflow nasce INATIVO", wf.get("active") is False)
    r.prova(f"{rotulo} · fuso declarado no workflow",
            wf["settings"].get("timezone") == "America/Sao_Paulo")
    r.prova(f"{rotulo} · ordem de execução v1",
            wf["settings"].get("executionOrder") == "v1")

    # conexões apontam para nós existentes, e partem de nós existentes
    quebradas = []
    for origem, grupos in wf["connections"].items():
        if origem not in nos:
            quebradas.append(f"origem inexistente: {origem}")
        for saidas in grupos.get("main", []):
            for c in saidas:
                if c["node"] not in nos:
                    quebradas.append(f"{origem} -> {c['node']} (destino inexistente)")
    r.prova(f"{rotulo} · nenhuma conexão órfã", not quebradas, "; ".join(quebradas))

    # alcançabilidade a partir dos gatilhos
    gatilhos = [n["name"] for n in wf["nodes"] if n["type"] in TIPOS_GATILHO]
    r.prova(f"{rotulo} · tem gatilho de agenda e gatilho manual",
            any(n["type"] == "n8n-nodes-base.scheduleTrigger" for n in wf["nodes"])
            and any(n["type"] == "n8n-nodes-base.manualTrigger" for n in wf["nodes"]))

    alcancados = set(gatilhos)
    fila = list(gatilhos)
    while fila:
        atual = fila.pop()
        for saidas in wf["connections"].get(atual, {}).get("main", []):
            for c in saidas:
                if c["node"] not in alcancados:
                    alcancados.add(c["node"])
                    fila.append(c["node"])
    ilhados = [
        n["name"] for n in wf["nodes"]
        if n["name"] not in alcancados and n["type"] != "n8n-nodes-base.stickyNote"
    ]
    r.prova(f"{rotulo} · nenhum nó ilhado", not ilhados, ", ".join(ilhados))
    return nos


def validar_nos(wf: dict, nos: dict[str, dict], r: Relatorio, rotulo: str) -> None:
    for no in wf["nodes"]:
        nome = no["name"]
        tipo = no["type"]
        params = no.get("parameters", {})

        if tipo == "n8n-nodes-base.code":
            js = params.get("jsCode", "")
            codigo = _sem_comentarios(js)
            r.prova(f"{rotulo} · [{nome}] modo declarado explicitamente",
                    params.get("mode") == "runOnceForAllItems")
            r.prova(f"{rotulo} · [{nome}] devolve itens no formato [{{ json }}]",
                    re.search(r"return\s*\[\s*\{\s*\n?\s*json", codigo) is not None
                    or re.search(r"return\s+[\w.$]+\.map\(", codigo) is not None)
            r.prova(f"{rotulo} · [{nome}] sem `{{{{ }}}}` dentro do JavaScript",
                    "{{" not in js)
            r.prova(f"{rotulo} · [{nome}] sem require()", "require(" not in js)
            r.prova(f"{rotulo} · [{nome}] sem $env", "$env" not in js)
            r.prova(f"{rotulo} · [{nome}] sem credencial literal",
                    not any(p.search(js) for p, _ in SEGREDOS))
            # O acumulador global proibido: ler TODAS as rodadas de um nó de
            # dentro do laço devolveria só a última e faria o recibo mentir.
            dentro_do_laco = nome in {
                "Pagina: preparar pedido", "Pagina: normalizar",
                "Validar semanticamente", "Reconciliar lote",
                "Classificar erro do Google",
            }
            if dentro_do_laco:
                r.prova(f"{rotulo} · [{nome}] não usa $('No').all() como acumulador",
                        re.search(r"\$\(\s*['\"][^'\"]+['\"]\s*\)\s*\.all\(",
                                  codigo) is None)
                # Dentro do laço, `$()` só é seguro para nó de rodada ÚNICA
                # (Config) ou para nó cujo número de rodadas é provadamente igual
                # ao deste (Validar semanticamente ↔ Reconciliar lote, uma
                # rodada por página bem-sucedida).
                permitidos = {"Config", "Validar semanticamente"}
                usados = set(re.findall(r"\$\(\s*'([^']+)'\s*\)", codigo))
                r.prova(f"{rotulo} · [{nome}] só referencia nó de rodada única ou alinhada",
                        usados <= permitidos, ", ".join(sorted(usados - permitidos)))

        elif tipo == "n8n-nodes-base.httpRequest":
            opcoes = params.get("options", {})
            r.prova(f"{rotulo} · [{nome}] autentica por credencial, não por header manual",
                    params.get("authentication") == "predefinedCredentialType"
                    and bool(params.get("nodeCredentialType")))
            r.prova(f"{rotulo} · [{nome}] credencial é referência (id+nome), sem valor",
                    all(set(v.keys()) <= {"id", "name"}
                        for v in (no.get("credentials") or {}).values()))
            r.prova(f"{rotulo} · [{nome}] tem timeout", isinstance(opcoes.get("timeout"), int))
            r.prova(f"{rotulo} · [{nome}] não silencia erro (neverError falso)",
                    opcoes.get("response", {}).get("response", {}).get("neverError", False)
                    is False)
            # continueRegularOutput transformaria falha em item vazio no caminho feliz
            r.prova(f"{rotulo} · [{nome}] sem continueOnFail/continueRegularOutput",
                    no.get("continueOnFail") is not True
                    and no.get("onError") != "continueRegularOutput")
            if params.get("sendBody"):
                r.prova(f"{rotulo} · [{nome}] declara Content-Type coerente com o corpo",
                        params.get("specifyBody") == "json"
                        and any(p.get("name", "").lower() == "content-type"
                                and "json" in p.get("value", "")
                                for p in params.get("headerParameters", {})
                                              .get("parameters", [])))
            if nome != "Alerta de rotina parada":
                r.prova(f"{rotulo} · [{nome}] tem retry controlado",
                        no.get("retryOnFail") is True
                        and isinstance(no.get("maxTries"), int)
                        and 1 < no["maxTries"] <= 5
                        and isinstance(no.get("waitBetweenTries"), int))

        elif tipo == "n8n-nodes-base.splitInBatches":
            r.prova(f"{rotulo} · [{nome}] typeVersion 3 (done em main[0])",
                    no.get("typeVersion") == 3)
            r.prova(f"{rotulo} · [{nome}] batchSize 1 enquanto a chamada é por cliente",
                    params.get("batchSize") == 1)
            saidas = wf["connections"].get(nome, {}).get("main", [])
            r.prova(f"{rotulo} · [{nome}] tem as duas saídas ligadas", len(saidas) == 2
                    and saidas[0] and saidas[1])

        elif tipo == "n8n-nodes-base.merge":
            r.prova(f"{rotulo} · [{nome}] combina por POSIÇÃO (mesma iteração)",
                    params.get("mode") == "combine"
                    and params.get("combineBy") == "combineByPosition")
            entradas = [
                (origem, i)
                for origem, grupos in wf["connections"].items()
                for i, saidas in enumerate(grupos.get("main", []))
                for c in saidas if c["node"] == nome
            ]
            indices = {
                c["index"]
                for grupos in wf["connections"].values()
                for saidas in grupos.get("main", [])
                for c in saidas if c["node"] == nome
            }
            r.prova(f"{rotulo} · [{nome}] tem as duas entradas ligadas",
                    indices == {0, 1}, str(sorted(indices)))

        elif tipo == "n8n-nodes-base.if":
            saidas = wf["connections"].get(nome, {}).get("main", [])
            r.prova(f"{rotulo} · [{nome}] declara as duas saídas", len(saidas) == 2)
            r.prova(f"{rotulo} · [{nome}] condição com operador declarado",
                    all(c.get("operator", {}).get("type")
                        for c in params.get("conditions", {}).get("conditions", [])))


def validar_expressoes(wf: dict, nos: dict[str, dict], r: Relatorio, rotulo: str) -> None:
    problemas: list[str] = []
    referencias: list[str] = []
    for no in wf["nodes"]:
        if no["type"] == "n8n-nodes-base.code":
            continue
        exprs: list[str] = []
        _expressoes(no.get("parameters", {}), exprs)
        for e in exprs:
            corpo = e[1:]
            if "{{" in corpo and "}}" not in corpo:
                problemas.append(f"{no['name']}: chave de expressão sem fechamento")
            for m in re.finditer(r"\$node\[\s*\"([^\"]+)\"\s*\]", corpo):
                referencias.append(f"{no['name']}::{m.group(1)}")
            for m in re.finditer(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)", corpo):
                referencias.append(f"{no['name']}::{m.group(1)}")

    r.prova(f"{rotulo} · expressões fora de Code estão bem formadas", not problemas,
            "; ".join(problemas))

    quebradas = [ref for ref in referencias if ref.split("::", 1)[1] not in nos]
    r.prova(f"{rotulo} · toda referência a nó existe e casa maiúsculas/minúsculas",
            not quebradas, ", ".join(quebradas))

    # Referências dentro dos Code nodes também precisam existir.
    quebradas_js = []
    for no in wf["nodes"]:
        if no["type"] != "n8n-nodes-base.code":
            continue
        for m in re.finditer(r"\$\(\s*'([^']+)'\s*\)",
                             _sem_comentarios(no["parameters"]["jsCode"])):
            if m.group(1) not in nos:
                quebradas_js.append(f"{no['name']}::{m.group(1)}")
    r.prova(f"{rotulo} · referências dentro dos Code nodes existem",
            not quebradas_js, ", ".join(quebradas_js))


def validar_sintaxe_js(wf: dict, r: Relatorio, rotulo: str) -> None:
    if not _tem_node():
        r.pula(f"{rotulo} · sintaxe dos Code nodes", "node não está no PATH")
        return
    ruins = []
    with tempfile.TemporaryDirectory() as d:
        for no in wf["nodes"]:
            if no["type"] != "n8n-nodes-base.code":
                continue
            # n8n embrulha o jsCode num corpo de função; `return` no topo só é
            # legal ali. `node --check` sobre o texto cru daria falso vermelho.
            alvo = Path(d) / (re.sub(r"[^a-zA-Z0-9]+", "_", no["name"]) + ".js")
            alvo.write_text(
                "(async function volcCodeNode() {\n"
                + no["parameters"]["jsCode"]
                + "\n});\n", encoding="utf-8")
            proc = subprocess.run(["node", "--check", str(alvo)],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                ruins.append(f"{no['name']}: {proc.stderr.strip().splitlines()[-1][:120]}")
    r.prova(f"{rotulo} · todo Code node é JavaScript válido", not ruins, "; ".join(ruins))


def _tem_node() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def validar_seguranca(wf: dict, r: Relatorio, rotulo: str) -> None:
    bruto = _texto(wf)

    achados = [rotulo_p for padrao, rotulo_p in SEGREDOS if padrao.search(bruto)]
    r.prova(f"{rotulo} · nenhum segredo literal no JSON", not achados,
            ", ".join(achados))

    r.prova(f"{rotulo} · nenhuma referência a *.supabase.co",
            ".supabase.co" not in bruto)

    hosts = set(re.findall(r"https?://([A-Za-z0-9._-]+)", bruto))
    permitidos = {DESTINO_OFICIAL, GOOGLE_HOST}
    r.prova(f"{rotulo} · destinos são exclusivamente {DESTINO_OFICIAL} e {GOOGLE_HOST}",
            hosts <= permitidos, ", ".join(sorted(hosts - permitidos)))

    mutacoes = [p.pattern for p in MUTACAO_GOOGLE if p.search(bruto)]
    r.prova(f"{rotulo} · nenhuma mutação Google Ads alcançável", not mutacoes,
            ", ".join(mutacoes))

    ativacoes = [p.pattern for p in ATIVACAO_N8N if p.search(bruto)]
    r.prova(f"{rotulo} · nenhuma chamada de ativação da API do n8n", not ativacoes,
            ", ".join(ativacoes))

    # O GAQL montado pelo Code node precisa ser leitura pura.
    campos = _campos_gaql(wf)
    r.prova(f"{rotulo} · a consulta é SELECT/FROM/WHERE, sem verbo de escrita",
            not GAQL_ESCRITA.search(" ".join(campos)))

    cfg = _config(wf)
    r.prova(f"{rotulo} · LOGIN_CUSTOMER_ID vazio no arquivo versionado",
            cfg.get("LOGIN_CUSTOMER_ID", "") == "")
    r.prova(f"{rotulo} · CONTAS_PERMITIDAS vazio no arquivo versionado",
            cfg.get("CONTAS_PERMITIDAS", "") == "")


def _config(wf: dict) -> dict[str, str]:
    for no in wf["nodes"]:
        if no["name"] == "Config":
            return {a["name"]: a["value"]
                    for a in no["parameters"]["assignments"]["assignments"]}
    return {}


def _campos_gaql(wf: dict) -> list[str]:
    cfg = _config(wf)
    return [c for c in cfg.get("GAQL_CAMPOS", "").split(",") if c]


def validar_contrato_gaql(wf: dict, r: Relatorio, rotulo: str) -> None:
    campos = _campos_gaql(wf)
    r.prova(f"{rotulo} · a consulta declara campos", len(campos) >= 20)

    try:
        from google.ads.googleads.v25.common.types import metrics as m_mod
        from google.ads.googleads.v25.common.types import segments as s_mod
        from google.ads.googleads.v25.resources.types import campaign as c_mod
        from google.ads.googleads.v25.resources.types import customer as cu_mod
    except Exception as exc:  # noqa: BLE001
        # ⚠️ Ausência do SDK NÃO é prova. É lacuna declarada.
        r.pula(f"{rotulo} · campos GAQL conferidos contra os descriptors v25",
               f"SDK google-ads indisponível ({type(exc).__name__})")
        return

    conhecidos = {
        "metrics": {f.name for f in m_mod.Metrics.meta.fields.values()},
        "segments": {f.name for f in s_mod.Segments.meta.fields.values()},
        "campaign": {f.name for f in c_mod.Campaign.meta.fields.values()},
        "customer": {f.name for f in cu_mod.Customer.meta.fields.values()},
    }
    desconhecidos = []
    for campo in campos:
        recurso, _, atributo = campo.partition(".")
        if recurso not in conhecidos:
            desconhecidos.append(f"{campo} (recurso desconhecido)")
        elif atributo not in conhecidos[recurso]:
            desconhecidos.append(campo)
    r.prova(f"{rotulo} · os {len(campos)} campos GAQL existem nos descriptors v25",
            not desconhecidos, ", ".join(desconhecidos))


def validar_topologia(wf: dict, r: Relatorio, rotulo: str) -> None:
    conexoes = wf["connections"]

    def destinos(nome: str, saida: int) -> list[str]:
        grupos = conexoes.get(nome, {}).get("main", [])
        if len(grupos) <= saida:
            return []
        return [c["node"] for c in grupos[saida]]

    # A ordem obrigatória do contrato, elo a elo.
    cadeia = [
        ("Agenda", 0, "Config"),
        ("Executar manualmente", 0, "Config"),
        ("Config", 0, "Identidade da execucao"),
        ("Identidade da execucao", 0, "Contas autorizadas"),
        ("Contas autorizadas", 0, "Selecionar contas"),
        ("Selecionar contas", 0, "Campanhas conhecidas"),
        ("Campanhas conhecidas", 0, "Identidade VOLC por conta"),
        ("Identidade VOLC por conta", 0, "Lote de contas"),
        ("Pagina: preparar pedido", 0, "Google Ads: search"),
        ("Pagina: preparar pedido", 0, "Juntar contexto e resposta"),
        ("Pagina: preparar pedido", 0, "Juntar contexto e erro"),
        ("Google Ads: search", 0, "Juntar contexto e resposta"),
        ("Juntar contexto e resposta", 0, "Pagina: normalizar"),
        ("Juntar contexto e erro", 0, "Classificar erro do Google"),
        ("Pagina: normalizar", 0, "Validar semanticamente"),
        ("Validar semanticamente", 0, "RPC: ingerir lote"),
        ("RPC: ingerir lote", 0, "Reconciliar lote"),
        ("Reconciliar lote", 0, "Tem proxima pagina?"),
        ("Fechar execucao", 0, "Limite do fechamento"),
        ("Limite do fechamento", 0, "RPC: fechar recibo"),
        ("RPC: fechar recibo", 0, "Releitura do recibo"),
        ("Releitura do recibo", 0, "Batimento e saude"),
        ("Batimento e saude", 0, "Falha real?"),
    ]
    faltando = [f"{a}[{i}] -> {b}" for a, i, b in cadeia if b not in destinos(a, i)]
    r.prova(f"{rotulo} · a ordem obrigatória do contrato está ligada elo a elo",
            not faltando, "; ".join(faltando))

    r.prova(f"{rotulo} · SplitInBatches main[0] (done) fecha a execução",
            destinos("Lote de contas", 0) == ["Fechar execucao"])
    r.prova(f"{rotulo} · SplitInBatches main[1] (lote atual) entra no laço",
            destinos("Lote de contas", 1) == ["Pagina: preparar pedido"])
    r.prova(f"{rotulo} · Limit 1 protege o caminho de fechamento",
            destinos("Fechar execucao", 0) == ["Limite do fechamento"])

    r.prova(f"{rotulo} · página seguinte volta ao pedido, não ao início",
            destinos("Tem proxima pagina?", 0) == ["Pagina: preparar pedido"])
    r.prova(f"{rotulo} · conta encerrada devolve o controle ao laço de contas",
            destinos("Tem proxima pagina?", 1) == ["Lote de contas"])
    r.prova(f"{rotulo} · alerta sai só da saída verdadeira do teste de falha",
            destinos("Falha real?", 0) == ["Alerta de rotina parada"]
            and destinos("Falha real?", 1) == [])

    # 401/403 não podem girar: da saída de erro não existe caminho de volta ao
    # nó de requisição sem passar pelo laço de contas, que só avança.
    erro_dest = destinos("Google Ads: search", 1)
    r.prova(f"{rotulo} · a saída de erro do Google casa com o contexto antes de classificar",
            erro_dest == ["Juntar contexto e erro"])

    def alcanca(inicio: str, alvo: str, bloqueio: str) -> bool:
        visto, fila = {inicio}, [inicio]
        while fila:
            atual = fila.pop()
            if atual == bloqueio:
                continue
            for grupos in [conexoes.get(atual, {}).get("main", [])]:
                for saidas in grupos:
                    for c in saidas:
                        if c["node"] == alvo:
                            return True
                        if c["node"] not in visto:
                            visto.add(c["node"])
                            fila.append(c["node"])
        return False

    r.prova(f"{rotulo} · erro de autenticação não tem como voltar ao pedido "
            f"sem passar pelo laço",
            not alcanca("Classificar erro do Google", "Pagina: preparar pedido",
                        "Lote de contas"))

    # ⚠️ REGRESSÃO NOMEADA. A primeira versão lia o contexto da iteração com
    # `$('Pagina: preparar pedido')` dentro do laço; `$()` resolve pelo ÍNDICE
    # DA RODADA do nó que pergunta, e uma conta que falha desalinha os índices —
    # a partir dali cada iteração lia o contexto de OUTRA conta, em silêncio.
    # O simulador derrubou isso, e a defesa passou a ser o Merge por posição.
    for nome in ("Pagina: normalizar", "Classificar erro do Google"):
        no = next((n for n in wf["nodes"] if n["name"] == nome), None)
        js = _sem_comentarios(no["parameters"]["jsCode"]) if no else ""
        r.prova(f"{rotulo} · [{nome}] toma o contexto do Merge, não de $() no laço",
                "$('Pagina: preparar pedido')" not in js)


def validar_agenda(wf: dict, r: Relatorio, rotulo: str, esperado: str) -> None:
    for no in wf["nodes"]:
        if no["type"] == "n8n-nodes-base.scheduleTrigger":
            regras = no["parameters"]["rule"]["interval"]
            crons = [x.get("expression") for x in regras]
            r.prova(f"{rotulo} · a agenda declarada é `{esperado}`", crons == [esperado],
                    str(crons))
            return
    r.prova(f"{rotulo} · existe gatilho de agenda", False)


def main() -> int:
    r = Relatorio()
    agendas = {
        "volc_gads_campanha_dia_d0.json": "0 6,12,18,23 * * *",
        "volc_gads_campanha_dia_d1.json": "0 6 * * *",
    }

    for caminho in ALVOS:
        rotulo = caminho.name.replace("volc_gads_campanha_dia_", "").replace(".json", "").upper()
        print(f"\n── {caminho.relative_to(RAIZ)}")
        if not caminho.exists():
            r.prova(f"{rotulo} · arquivo existe", False)
            continue
        try:
            wf = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            r.prova(f"{rotulo} · JSON parseável", False, str(exc))
            continue
        r.prova(f"{rotulo} · JSON parseável", True)

        nos = validar_estrutura(wf, r, rotulo)
        validar_nos(wf, nos, r, rotulo)
        validar_expressoes(wf, nos, r, rotulo)
        validar_sintaxe_js(wf, r, rotulo)
        validar_topologia(wf, r, rotulo)
        validar_seguranca(wf, r, rotulo)
        validar_contrato_gaql(wf, r, rotulo)
        validar_agenda(wf, r, rotulo, agendas[caminho.name])

    # Os dois fluxos precisam ser o MESMO desenho: divergência entre D0 e D-1 é
    # como o legado acabou com dois Code nodes quase iguais e sutilmente
    # diferentes.
    if all(c.exists() for c in ALVOS):
        d0, d1 = (json.loads(c.read_text(encoding="utf-8")) for c in ALVOS)
        r.prova("D0 e D-1 têm exatamente a mesma topologia",
                d0["connections"] == d1["connections"])
        js0 = {n["name"]: n["parameters"].get("jsCode")
               for n in d0["nodes"] if n["type"] == "n8n-nodes-base.code"}
        js1 = {n["name"]: n["parameters"].get("jsCode")
               for n in d1["nodes"] if n["type"] == "n8n-nodes-base.code"}
        r.prova("D0 e D-1 compartilham o MESMO código, byte a byte", js0 == js1)
        r.prova("a diferença entre D0 e D-1 mora só no Config e na agenda",
                _config(d0) != _config(d1)
                and {k: v for k, v in _config(d0).items()
                     if k not in {"JOB", "JANELA_MODO", "PASSOS"}}
                == {k: v for k, v in _config(d1).items()
                    if k not in {"JOB", "JANELA_MODO", "PASSOS"}})

    print()
    print("════════════════════════════════════════════════════════")
    print(f"  passaram {r.ok} · falharam {len(r.falhas)} · pulados {len(r.pulados)}")
    if r.falhas:
        for f in r.falhas:
            print(f"    ✗ {f}")
        return 1
    print("  workflows n8n VALIDADOS nó a nó, com topologia e varreduras")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
