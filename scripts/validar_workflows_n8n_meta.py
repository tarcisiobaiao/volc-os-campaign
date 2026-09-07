#!/usr/bin/env python3
"""Valida o workflow n8n de leitura diária de insights Meta Ads — nó a nó.

## Por que este gate existe

"O JSON dá parse" não é validação de workflow. Um JSON perfeitamente parseável
pode ter conexão apontando para nó que não existe, `{{ }}` dentro de um Code
node (onde n8n não interpola nada), `continueOnFail` transformando erro em item
vazio, credencial escrita à mão no corpo, ou uma expressão referenciando
`$node["Config "]` com um espaço a mais — todos silenciosos até a produção.

Dois terços deste gate são o gate Google (`validar_workflows_n8n_gads.py`) sem
mudança nenhuma, porque as regras de estrutura, expressão, sintaxe e segurança
não são de provedor. O terço restante troca o contrato GAQL pelo **contrato
Meta**, e é onde mora o que este fluxo precisa provar e o fluxo Google não:

* a janela D-1 sai do **fuso da conta** (`trafego_meta_ad_account.timezone_name`),
  nunca do fuso do servidor n8n — o defeito que o lado Python acabou de corrigir
  em `dominio.hoje_na_conta`;
* `time_increment`, `action_report_time`, `breakdown` e as janelas de atribuição
  são pedidos explícitos que voltam no recibo, e **nenhuma janela é carimbada
  sem ter sido pedida**;
* `actions` (conta eventos) e `action_values` (soma dinheiro) permanecem
  separadas do fio até a linha;
* `landing_page_views` sai **apenas** de `action_type == 'landing_page_view'` —
  somar `ViewContent` ali foi o defeito T05;
* paginação é por cursor real (`paging.next` + `paging.cursors.after`), com teto,
  e janela truncada vira **INCOMPLETA** sem avançar marca d'água;
* a credencial Meta é um **placeholder que não resolve** — nenhum token, nenhum
  id de app, nenhum header `Authorization` montado à mão.

Uso:
    python3 scripts/validar_workflows_n8n_meta.py
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
    RAIZ / "n8n" / "volc_meta_insights_dia_d1.json",
]
AGENDAS = {"volc_meta_insights_dia_d1.json": "0 7 * * *"}

DESTINO_OFICIAL = "database.agenciavolc.com.br"
META_HOST = "graph.facebook.com"
#: ⚠️ ERA `metaGraphApiNaoProvisionada`, um tipo INVENTADO. A prova antiga
#: ("o tipo é o placeholder declarado") descrevia bem a INTENÇÃO e mal o
#: RESULTADO: um `nodeCredentialType` fora do catálogo da instância não produz
#: "credencial pendente", produz workflow inválido — o n8n não tem onde pendurar
#: o item do cofre e o operador não consegue provisionar nem depois de ter o
#: token. O tipo passou a ser `httpHeaderAuth`, nativo, na forma literal do
#: precedente vivo desta base (`n8n/joinads_report_day_before.json:144-146` e
#: `:190-194`). O que continua faltando — e continua PROVADO abaixo — é o ITEM
#: do cofre.
CRED_META_TIPO = "httpHeaderAuth"
#: A única forma genérica aceita. `httpQueryAuth` está fora de propósito: ela põe
#: o token na query string, onde ele vaza para log de proxy e para o histórico de
#: execução do n8n.
GENERIC_AUTH_PERMITIDO = {"httpHeaderAuth"}
CRED_META_MARCADOR = "PROVISIONAR__VOLC_META_ADS_HEADER_AUTH"
NO_GRAPH = "Meta Graph: insights"

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
    (re.compile(r"(?i)(?:developer[_-]?token|service[_-]?role[_-]?key|api[_-]?secret|"
                r"app[_-]?secret|client[_-]?secret)"
                r"\"?\s*[:=]\s*\"[A-Za-z0-9_\-]{16,}\""), "segredo literal"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-.]{20,}"), "bearer literal"),
    # Token de usuário/sistema da Meta: prefixos públicos conhecidos.
    (re.compile(r"\bEAA[A-Za-z0-9]{20,}"), "token Meta"),
    (re.compile(r"(?i)\baccess[_-]?token\"?\s*[:=]\s*\"[^\"]{8,}\""), "access_token literal"),
]

# Escrita na Meta. Nenhuma pode ser alcançável a partir deste fluxo: ele é
# somente leitura de insights.
ESCRITA_META = [
    re.compile(r"act_[^\s\"'`]*/(?:campaigns|adsets|ads|adcreatives|adimages|advideos|copies)\b"),
    re.compile(r"(?i)graph\.facebook\.com[^\"']*/(?:campaigns|adsets|ads|adcreatives)\b"),
    re.compile(r"(?i)\"(?:status|effective_status|daily_budget|lifetime_budget|bid_amount)\"\s*:"),
]

# API de ativação do n8n. Nenhum nó pode ligar workflow nenhum.
ATIVACAO_N8N = [
    re.compile(r"/api/v1/workflows/[^\"]*/activate"),
    re.compile(r"/rest/workflows/[^\"]*/activate"),
    re.compile(r"(?i)\"active\"\s*:\s*true"),
    re.compile(r"(?i)n8n-nodes-base\.n8n\b"),
]


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
    string e regex, e a primeira versão do gate irmão acusou como "referência
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


def _config(wf: dict) -> dict[str, str]:
    for no in wf["nodes"]:
        if no["name"] == "Config":
            return {a["name"]: a["value"]
                    for a in no["parameters"]["assignments"]["assignments"]}
    return {}


def _code(wf: dict, nome: str) -> str:
    for no in wf["nodes"]:
        if no["name"] == nome and no["type"] == "n8n-nodes-base.code":
            return no["parameters"]["jsCode"]
    return ""


# ─────────────────────────────────────────────── camadas provider-agnósticas ──


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

    quebradas = []
    for origem, grupos in wf["connections"].items():
        if origem not in nos:
            quebradas.append(f"origem inexistente: {origem}")
        for saidas in grupos.get("main", []):
            for c in saidas:
                if c["node"] not in nos:
                    quebradas.append(f"{origem} -> {c['node']} (destino inexistente)")
    r.prova(f"{rotulo} · nenhuma conexão órfã", not quebradas, "; ".join(quebradas))

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
            dentro_do_laco = nome in {
                "Pagina: preparar pedido", "Pagina: normalizar",
                "Validar semanticamente", "Reconciliar lote",
                "Classificar erro da Meta",
            }
            if dentro_do_laco:
                # O acumulador global proibido: ler TODAS as rodadas de um nó de
                # dentro do laço devolveria só a última e faria o recibo mentir.
                r.prova(f"{rotulo} · [{nome}] não usa $('No').all() como acumulador",
                        re.search(r"\$\(\s*['\"][^'\"]+['\"]\s*\)\s*\.all\(",
                                  codigo) is None)
                # Dentro do laço, `$()` só é seguro para nó de rodada ÚNICA
                # (Config) ou para nó cujo número de rodadas é provadamente igual
                # ao deste (Validar semanticamente ↔ Reconciliar lote).
                permitidos = {"Config", "Validar semanticamente"}
                usados = set(re.findall(r"\$\(\s*'([^']+)'\s*\)", codigo))
                r.prova(f"{rotulo} · [{nome}] só referencia nó de rodada única ou alinhada",
                        usados <= permitidos, ", ".join(sorted(usados - permitidos)))

        elif tipo == "n8n-nodes-base.httpRequest":
            opcoes = params.get("options", {})
            # ⚠️ O GATE ALARGOU, E A REGRA CONTINUA A MESMA: a autorização sai de
            # um ITEM DO COFRE, nunca de algo escrito no workflow. O que mudou é
            # que agora existem DUAS formas legítimas de dizer isso no n8n — o
            # tipo predefinido (`supabaseApi`, que os nós do Supabase usam) e o
            # genérico por cabeçalho (`httpHeaderAuth`, a forma que
            # `n8n/joinads_report_day_before.json:144-146` já usa nesta base). A
            # versão anterior só aceitava a primeira, e por isso obrigava a
            # inventar um `nodeCredentialType` Meta que não existe.
            # `genericAuthType` fica preso à allowlist: `httpQueryAuth` mandaria o
            # token pela query string.
            autentica_por_cofre = (
                (params.get("authentication") == "predefinedCredentialType"
                 and bool(params.get("nodeCredentialType")))
                or (params.get("authentication") == "genericCredentialType"
                    and params.get("genericAuthType") in GENERIC_AUTH_PERMITIDO)
            )
            r.prova(f"{rotulo} · [{nome}] autentica por credencial, não por header manual",
                    autentica_por_cofre,
                    f"{params.get('authentication')}/{params.get('genericAuthType')}")
            r.prova(f"{rotulo} · [{nome}] nenhuma autenticação põe segredo na URL",
                    params.get("genericAuthType") != "httpQueryAuth"
                    and "authentication" not in {
                        p.get("name", "").lower()
                        for p in params.get("queryParameters", {}).get("parameters", [])}
                    and not re.search(r"(?i)access[_-]?token", str(params.get("url", ""))))
            r.prova(f"{rotulo} · [{nome}] credencial é referência (id+nome), sem valor",
                    all(set(v.keys()) <= {"id", "name"}
                        for v in (no.get("credentials") or {}).values()))
            r.prova(f"{rotulo} · [{nome}] tem timeout", isinstance(opcoes.get("timeout"), int))
            r.prova(f"{rotulo} · [{nome}] não silencia erro (neverError falso)",
                    opcoes.get("response", {}).get("response", {}).get("neverError", False)
                    is False)
            r.prova(f"{rotulo} · [{nome}] sem continueOnFail/continueRegularOutput",
                    no.get("continueOnFail") is not True
                    and no.get("onError") != "continueRegularOutput")
            # Um header de autorização montado à mão significaria que o segredo
            # veio de algum lugar do workflow — exatamente o que não pode existir.
            cabecalhos = {p.get("name", "").lower()
                          for p in params.get("headerParameters", {}).get("parameters", [])}
            r.prova(f"{rotulo} · [{nome}] não monta header de autorização à mão",
                    "authorization" not in cabecalhos)
            if params.get("sendBody"):
                r.prova(f"{rotulo} · [{nome}] declara Content-Type coerente com o corpo",
                        params.get("specifyBody") == "json"
                        and any(p.get("name", "").lower() == "content-type"
                                and "json" in p.get("value", "")
                                for p in params.get("headerParameters", {})
                                              .get("parameters", [])))
            if nome != "Alerta de rotina parada":
                r.prova(f"{rotulo} · [{nome}] tem retry limitado (backoff declarado)",
                        no.get("retryOnFail") is True
                        and isinstance(no.get("maxTries"), int)
                        and 1 < no["maxTries"] <= 5
                        and isinstance(no.get("waitBetweenTries"), int)
                        and no["waitBetweenTries"] > 0)

        elif tipo == "n8n-nodes-base.splitInBatches":
            r.prova(f"{rotulo} · [{nome}] typeVersion 3 (done em main[0])",
                    no.get("typeVersion") == 3)
            r.prova(f"{rotulo} · [{nome}] batchSize 1 enquanto a chamada é por conta",
                    params.get("batchSize") == 1)
            saidas = wf["connections"].get(nome, {}).get("main", [])
            r.prova(f"{rotulo} · [{nome}] tem as duas saídas ligadas", len(saidas) == 2
                    and saidas[0] and saidas[1])

        elif tipo == "n8n-nodes-base.merge":
            r.prova(f"{rotulo} · [{nome}] combina por POSIÇÃO (mesma iteração)",
                    params.get("mode") == "combine"
                    and params.get("combineBy") == "combineByPosition")
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


def _tem_node() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


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


def validar_seguranca(wf: dict, r: Relatorio, rotulo: str) -> None:
    bruto = _texto(wf)

    achados = [rot for padrao, rot in SEGREDOS if padrao.search(bruto)]
    r.prova(f"{rotulo} · nenhum segredo literal no JSON", not achados, ", ".join(achados))

    r.prova(f"{rotulo} · nenhuma referência a *.supabase.co",
            ".supabase.co" not in bruto)

    hosts = set(re.findall(r"https?://([A-Za-z0-9._-]+)", bruto))
    permitidos = {DESTINO_OFICIAL, META_HOST}
    r.prova(f"{rotulo} · destinos são exclusivamente {DESTINO_OFICIAL} e {META_HOST}",
            hosts <= permitidos, ", ".join(sorted(hosts - permitidos)))

    escritas = [p.pattern for p in ESCRITA_META if p.search(bruto)]
    r.prova(f"{rotulo} · nenhuma escrita na Meta alcançável", not escritas,
            ", ".join(escritas))

    ativacoes = [p.pattern for p in ATIVACAO_N8N if p.search(bruto)]
    r.prova(f"{rotulo} · nenhuma chamada de ativação da API do n8n", not ativacoes,
            ", ".join(ativacoes))

    # O endpoint Meta é UM só, e é de leitura.
    graph = next((n for n in wf["nodes"] if n["name"] == NO_GRAPH), None)
    r.prova(f"{rotulo} · o nó da Meta existe", graph is not None)
    if graph is not None:
        r.prova(f"{rotulo} · a chamada à Meta é GET",
                graph["parameters"].get("method") == "GET")
    js_pedido = _code(wf, "Pagina: preparar pedido")
    r.prova(f"{rotulo} · o único edge Meta montado é /insights",
            "/act_${ctx.conta_externa}/insights`" in js_pedido)

    cfg = _config(wf)
    r.prova(f"{rotulo} · CONTAS_PERMITIDAS vazio no arquivo versionado",
            cfg.get("CONTAS_PERMITIDAS", "") == "")
    r.prova(f"{rotulo} · nenhum id de conta Meta literal no Config",
            not any(re.fullmatch(r"[0-9]{6,40}", v) for v in cfg.values()))

    # Nenhum caminho local, nenhum admin de máquina: um fluxo que dependesse do
    # Keychain do operador ou de um endpoint em localhost seria inexecutável num
    # servidor n8n — e mentiria sobre estar pronto.
    r.prova(f"{rotulo} · nenhuma dependência de localhost/keychain/arquivo local",
            not re.search(r"(?i)localhost|127\.0\.0\.1|keychain|/Users/|file://", bruto))


def validar_credencial_meta(wf: dict, r: Relatorio, rotulo: str) -> None:
    """Nenhum SEGREDO viaja, e o estado de provisionamento é declarado com honestidade.

    ⚠️ POR QUE A PROVA ANTIGA DEIXOU DE DESCREVER A VERDADE.

    Este bloco exigia `nodeCredentialType == 'metaGraphApiNaoProvisionada'` e
    `cred['id'] == 'REPLACE_ME'`. A intenção era boa — não fingir uma integração
    que não existe — mas o que ele provava era só que o arquivo continuava com
    dois literais. E os dois literais, juntos, produziam algo PIOR que uma
    pendência: um `nodeCredentialType` fora do catálogo da instância não faz o nó
    "parar por falta de credencial", faz o workflow ser inválido. O n8n não
    oferece o seletor, não há onde pendurar o item do cofre, e o operador não
    consegue provisionar nem depois de ter o token na mão. A lacuna virava beco
    sem saída, e o gate carimbava isso como estado desejado.

    O que este bloco prova AGORA — e o que ele continuará provando depois que a
    credencial existir, que é o teste de um gate que não é teatro:

      (a) **nenhum segredo viaja no JSON.** A autorização sai de um item do cofre
          por REFERÊNCIA (id + nome). Nada de valor, nada de cabeçalho montado à
          mão, nada de token em query, nada de `access_token` em Code node.
      (b) **o estado de provisionamento é declarado, e bate com o que está no
          nó.** A coerência é conferida NOS DOIS SENTIDOS: declarar
          `provisionada: false` obriga o nó a carregar o marcador nomeado, e
          declarar `provisionada: true` PROÍBE o marcador. Assim ninguém publica
          um workflow que se diz pronto carregando o placeholder, nem esconde uma
          referência real atrás de um "ainda não provisionado".
    """
    graph = next((n for n in wf["nodes"] if n["name"] == NO_GRAPH), None)
    if graph is None:
        r.prova(f"{rotulo} · nó da Meta presente para conferir credencial", False)
        return

    params = graph["parameters"]
    r.prova(f"{rotulo} · a credencial Meta usa um tipo REAL do n8n (header genérico)",
            params.get("authentication") == "genericCredentialType"
            and params.get("genericAuthType") == CRED_META_TIPO,
            f"{params.get('authentication')}/{params.get('genericAuthType')}")
    # O tipo inventado não pode voltar por nenhuma porta.
    r.prova(f"{rotulo} · nenhum tipo de credencial fictício sobrou no workflow",
            "metaGraphApiNaoProvisionada" not in _texto(wf))

    cred = (graph.get("credentials") or {}).get(CRED_META_TIPO, {})
    r.prova(f"{rotulo} · a credencial Meta é REFERÊNCIA (id+nome), nunca valor",
            set(cred.keys()) == {"id", "name"}, str(sorted(cred)))
    # (a) O id e o nome são rótulos. Se algum deles PARECESSE material de
    # segredo, a varredura global já teria acusado — mas ela varre o arquivo
    # inteiro, e aqui a pergunta é específica: o campo que aponta para o cofre
    # não pode carregar o conteúdo do cofre.
    achados = [rot for padrao, rot in SEGREDOS
               if padrao.search(f"{cred.get('id', '')} {cred.get('name', '')}")]
    r.prova(f"{rotulo} · nem o id nem o nome da credencial carregam segredo",
            not achados, ", ".join(achados))

    # (b) Coerência entre o que o workflow DIZ e o que ele CARREGA.
    declarado = wf.get("meta", {}).get("volc", {}).get("credencial", {})
    provisionada = declarado.get("provisionada")
    r.prova(f"{rotulo} · o meta do workflow declara o provisionamento como booleano",
            isinstance(provisionada, bool), str(type(provisionada).__name__))
    r.prova(f"{rotulo} · o tipo declarado no meta é o mesmo que o nó usa",
            declarado.get("tipo") == params.get("genericAuthType"),
            f"{declarado.get('tipo')} vs {params.get('genericAuthType')}")
    id_no_no = str(cred.get("id", ""))
    if provisionada is False:
        r.prova(f"{rotulo} · não provisionada ⇒ o nó carrega o MARCADOR nomeado, "
                "não um id de cofre",
                id_no_no == CRED_META_MARCADOR, id_no_no)
        r.prova(f"{rotulo} · não provisionada ⇒ o marcador está declarado no meta",
                declarado.get("item_id_marcador") == CRED_META_MARCADOR)
        r.prova(f"{rotulo} · não provisionada ⇒ o workflow não se declara publicável",
                wf["meta"]["volc"].get("pronto_para_publicar") is False)
        r.prova(f"{rotulo} · não provisionada ⇒ o nome do item avisa que falta provisionar",
                "A PROVISIONAR" in str(cred.get("name", "")))
    elif provisionada is True:
        # ⚠️ O outro sentido da coerência. Sem ele, bastaria virar o booleano
        # para "liberar" um workflow que continua apontando para o marcador.
        r.prova(f"{rotulo} · provisionada ⇒ o marcador SUMIU do nó",
                id_no_no != CRED_META_MARCADOR and CRED_META_MARCADOR not in _texto(wf),
                id_no_no)
        r.prova(f"{rotulo} · provisionada ⇒ o id do item do cofre é não-vazio",
                id_no_no.strip() != "" and id_no_no != "REPLACE_ME", id_no_no)
        r.prova(f"{rotulo} · provisionada ⇒ o nome do item não diz mais 'A PROVISIONAR'",
                "A PROVISIONAR" not in str(cred.get("name", "")))

    # (a, continuação) Nenhum caminho alternativo de autorização.
    js_todos = "\n".join(n["parameters"].get("jsCode", "")
                         for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code")
    r.prova(f"{rotulo} · nenhum Code node monta access_token",
            "access_token" not in js_todos)
    consulta = params.get("jsonQuery", "")
    r.prova(f"{rotulo} · a query da Meta sai do pedido tipado, não de literal",
            consulta == "={{ JSON.stringify($json.parametros_graph) }}", consulta)
    # Com `httpHeaderAuth`, NOME e VALOR do cabeçalho vivem no item do cofre. Um
    # cabeçalho de autorização declarado aqui significaria que alguém o montou
    # fora do cofre — o caminho por onde um token entraria no arquivo.
    cabecalhos = {p.get("name", "").lower()
                  for p in params.get("headerParameters", {}).get("parameters", [])}
    r.prova(f"{rotulo} · o cabeçalho de autorização vive no cofre, não no workflow",
            "authorization" not in cabecalhos, ", ".join(sorted(cabecalhos)))


def validar_contrato_meta(wf: dict, r: Relatorio, rotulo: str) -> None:
    """O contrato do PEDIDO, conferido contra `app.trafego.meta.dominio`.

    Aqui não se confere "o campo existe na API" (isso só a Graph responde, e a
    leitura real ainda não aconteceu): confere-se que a PERGUNTA que o fluxo faz
    é uma pergunta legal no contrato Python — mesmo nível, mesmo incremento,
    mesmo instante de relatório, mesmos campos, mesmo teto de dias. Um fluxo que
    pergunta diferente do backend produz duas séries que ninguém pode somar.
    """
    cfg = _config(wf)
    r.prova(f"{rotulo} · o Config declara o grão inteiro do pedido",
            {"NIVEL", "TIME_INCREMENT", "ACTION_REPORT_TIME", "BREAKDOWN",
             "JANELAS_DE_ATRIBUICAO", "CAMPOS_DE_INSIGHT", "MAX_DIAS_POR_PEDIDO",
             "LIMITE_POR_PAGINA", "MAX_PAGINAS", "DIAS_DE_REPROCESSO",
             "RPC_PERSISTIR", "SUPABASE_URL", "GRAPH_BASE", "GRAPH_API_VERSION"}
            <= set(cfg))
    r.prova(f"{rotulo} · a RPC de persistência é configuração, não constante escondida",
            cfg.get("RPC_PERSISTIR") == "trafego_meta_persistir_snapshot")
    r.prova(f"{rotulo} · o Config carrega a URL do Supabase e NENHUMA chave",
            cfg.get("SUPABASE_URL") == f"https://{DESTINO_OFICIAL}"
            and not any("key" in k.lower() or "token" in k.lower() or "secret" in k.lower()
                        for k in cfg))
    r.prova(f"{rotulo} · `actions` e `action_values` são pedidos os dois",
            "actions" in cfg.get("CAMPOS_DE_INSIGHT", "")
            and "action_values" in cfg.get("CAMPOS_DE_INSIGHT", ""))

    sys.path.insert(0, str(RAIZ / "backend"))
    try:
        from app.trafego.meta import dominio as dom
    except Exception as exc:  # noqa: BLE001
        # ⚠️ Ausência do módulo NÃO é prova. É lacuna declarada.
        r.pula(f"{rotulo} · contrato conferido contra app.trafego.meta.dominio",
               f"módulo indisponível ({type(exc).__name__})")
        return

    r.prova(f"{rotulo} · os campos pedidos são LITERALMENTE dominio.CAMPOS_DE_INSIGHT",
            cfg.get("CAMPOS_DE_INSIGHT") == dom.CAMPOS_DE_INSIGHT)
    r.prova(f"{rotulo} · o nível está na allowlist do domínio",
            cfg.get("NIVEL") in dom.NIVEIS_DE_INSIGHT, str(cfg.get("NIVEL")))
    r.prova(f"{rotulo} · time_increment=1 é o único que produz série diária",
            cfg.get("TIME_INCREMENT") == "1"
            and cfg["TIME_INCREMENT"] in dom.INCREMENTOS_DE_TEMPO)
    r.prova(f"{rotulo} · action_report_time está na allowlist do domínio",
            cfg.get("ACTION_REPORT_TIME") in dom.INSTANTES_DE_RELATORIO)
    r.prova(f"{rotulo} · breakdown está na allowlist do domínio",
            cfg.get("BREAKDOWN") in dom.BREAKDOWNS_PERMITIDOS)
    janelas = [j for j in cfg.get("JANELAS_DE_ATRIBUICAO", "").split(",") if j.strip()]
    r.prova(f"{rotulo} · toda janela pedida está na allowlist do domínio",
            all(j in dom.JANELAS_DE_ATRIBUICAO for j in janelas), ", ".join(janelas))
    try:
        dom.validar_combinacao_de_insight(
            nivel=cfg.get("NIVEL", ""), breakdown=cfg.get("BREAKDOWN", ""),
            janelas=janelas)
        combinacao_ok, motivo = True, ""
    except Exception as exc:  # noqa: BLE001
        combinacao_ok, motivo = False, str(exc)
    r.prova(f"{rotulo} · a combinação nível/breakdown/janela é aceita pelo domínio",
            combinacao_ok, motivo)
    r.prova(f"{rotulo} · o teto local de dias é o mesmo do domínio",
            json.loads(cfg.get("MAX_DIAS_POR_PEDIDO", "{}"))
            == {k: v for k, v in dom.MAX_DIAS_POR_PEDIDO.items()})
    r.prova(f"{rotulo} · a janela de reprocesso cabe no teto do incremento",
            int(cfg.get("DIAS_DE_REPROCESSO", "0")) + 1
            <= dom.MAX_DIAS_POR_PEDIDO[cfg.get("TIME_INCREMENT", "1")])
    r.prova(f"{rotulo} · o limite por página cabe na faixa do domínio",
            1 <= int(cfg.get("LIMITE_POR_PAGINA", "0")) <= 500)

    # O pedido montado com esta configuração tem de ser construível: se o
    # `PedidoDeInsights` recusa, o fluxo estaria perguntando o que o backend
    # não deixa perguntar.
    from datetime import date
    try:
        dom.PedidoDeInsights(
            conta_externa="1234567890",
            nivel=cfg["NIVEL"],
            periodo_inicio=date(2026, 9, 6),
            periodo_fim=date(2026, 9, 6),
            fuso_da_conta="America/Sao_Paulo",
            time_increment=cfg["TIME_INCREMENT"],
            breakdown=cfg["BREAKDOWN"],
            action_report_time=cfg["ACTION_REPORT_TIME"],
            janelas_de_atribuicao=tuple(janelas),
            limite_por_pagina=int(cfg["LIMITE_POR_PAGINA"]),
        )
        pedido_ok, motivo = True, ""
    except Exception as exc:  # noqa: BLE001
        pedido_ok, motivo = False, str(exc)
    r.prova(f"{rotulo} · o pedido do fluxo é construível como dominio.PedidoDeInsights",
            pedido_ok, motivo)

    js_norm = _sem_comentarios(_code(wf, "Pagina: normalizar"))
    r.prova(f"{rotulo} · landing_page_views usa o action_type do domínio",
            f"'{dom.ACTION_TYPE_LPV}'" in js_norm)
    r.prova(f"{rotulo} · ViewContent NUNCA entra na conta de LPV",
            dom.ACTION_TYPE_VIEW_CONTENT not in js_norm)
    js_valida = _sem_comentarios(_code(wf, "Validar semanticamente"))
    naoaditivas = [m for m in dom.METRICAS_NAO_ADITIVAS
                   if re.search(rf"\b{m}\s*[:+]=?\s*[a-zA-Z0-9_.]*\s*\+", js_valida)]
    r.prova(f"{rotulo} · nenhuma métrica não-aditiva é somada no fluxo",
            not naoaditivas, ", ".join(naoaditivas))


def validar_fuso_da_conta(wf: dict, r: Relatorio, rotulo: str) -> None:
    """A propriedade mais importante do fluxo, medida no código que a produz.

    ⚠️ REGRESSÃO NOMEADA. Ler "ontem" com a data do host produz, por algumas
    horas toda noite, uma série de um dia que a conta ainda não começou — e o
    zero medido entra no painel como resultado. O lado Python corrigiu isso em
    `dominio.hoje_na_conta`; aqui a mesma regra tem de estar no Code node.
    """
    js = _sem_comentarios(_code(wf, "Selecionar contas"))
    r.prova(f"{rotulo} · a janela lê o fuso vindo da conta",
            "timezone_name" in js)
    r.prova(f"{rotulo} · hoje é calculado NA ZONA DA CONTA",
            "dataNaZona(agora, fuso)" in js)
    r.prova(f"{rotulo} · D-1 sai de aritmética de calendário sobre a data local",
            "subtrairDias(hojeNaConta, 1)" in js)
    r.prova(f"{rotulo} · conta sem fuso é RECUSADA, não cai num padrão",
            "CONTA_SEM_FUSO" in js and "FUSO_DESCONHECIDO" in js)
    r.prova(f"{rotulo} · a janela NÃO sai do fuso do disparo",
            "TZ_DO_DISPARO" not in js and "tz_do_disparo" not in js)
    r.prova(f"{rotulo} · zero conta autorizada falha fechado",
            "SEM_CONTA_AUTORIZADA" in js)
    # ⚠️ SEM FALLBACK UTC, DITO COMO AUSÊNCIA DE UM PADRÃO. `dataNaZona` recebe o
    # fuso da conta e mais nada; um `|| 'UTC'` (ou 'Etc/UTC', ou 'Z') em qualquer
    # ponto do caminho da janela devolveria a data do meridiano de Greenwich com
    # cara de data da conta — que é a regressão inteira, escrita numa linha.
    # Grepar só "UTC" daria falso vermelho: `subtrairDias` usa `Date.UTC` de
    # propósito, como ARITMÉTICA de calendário sobre uma data local já resolvida.
    js_janela = _sem_comentarios(_code(wf, "Selecionar contas")
                                 + "\n" + _code(wf, "Pagina: preparar pedido"))
    fallbacks = re.findall(r"(?:\|\||\?\?)\s*'(?:UTC|Etc/UTC|GMT|Z)'", js_janela)
    r.prova(f"{rotulo} · nenhum fallback para UTC no caminho da janela",
            not fallbacks, ", ".join(fallbacks))
    # A pergunta é sobre a ÚNICA chamada que decide a janela: qual variável de
    # zona ela recebe. Um conjunto é mais honesto que um "não casa com": diz
    # exatamente o que está lá quando falha.
    zonas = set(re.findall(r"dataNaZona\(\s*agora\s*,\s*([A-Za-z_$][\w.$]*)\s*\)", js))
    r.prova(f"{rotulo} · na seleção de contas, `dataNaZona(agora, …)` só recebe `fuso`",
            zonas == {"fuso"}, ", ".join(sorted(zonas)) or "nenhuma chamada")

    ident = _sem_comentarios(_code(wf, "Identidade da execucao"))
    r.prova(f"{rotulo} · a chave da execução usa a data do DISPARO como rótulo",
            "dataDoDisparo" in ident and "data_do_disparo" in ident)

    pedido = _sem_comentarios(_code(wf, "Pagina: preparar pedido"))
    r.prova(f"{rotulo} · o pedido recusa conta que chegou sem fuso resolvido",
            "FUSO_AUSENTE" in pedido)
    r.prova(f"{rotulo} · o fuso da conta viaja no registro do pedido",
            "fuso_da_conta: String(ctx.fuso_da_conta)" in pedido)


def validar_contrato_do_pedido_no_fio(wf: dict, r: Relatorio, rotulo: str) -> None:
    """O que vai no fio, e o que o fato carimba."""
    pedido = _sem_comentarios(_code(wf, "Pagina: preparar pedido"))
    for chave in ("level", "time_range", "time_increment", "action_report_time",
                  "fields", "limit"):
        r.prova(f"{rotulo} · `{chave}` vai explícito no pedido à Graph",
                re.search(rf"^\s*{chave}:", pedido, re.M) is not None)
    r.prova(f"{rotulo} · action_attribution_windows só é enviado quando pedido",
            "if (janelas.length) parametros.action_attribution_windows" in pedido)
    r.prova(f"{rotulo} · breakdowns só é enviado quando não é `none`",
            "if (String(ctx.breakdown) !== 'none') parametros.breakdowns" in pedido)
    r.prova(f"{rotulo} · o pedido recusa campos sem actions/action_values",
            "CAMPOS_SEM_ACTIONS_OU_ACTION_VALUES" in pedido)

    norm = _sem_comentarios(_code(wf, "Pagina: normalizar"))
    r.prova(f"{rotulo} · a etiqueta da janela vem de janelaDeclarada(janelas)",
            "janelaDeclarada(janelas)" in norm)
    r.prova(f"{rotulo} · nenhuma janela nominal é carimbada como literal",
            not re.search(r"janela_atribuicao:\s*'(?:1d|7d|28d)_", norm))
    r.prova(f"{rotulo} · `actions` e `action_values` são expandidos separados",
            "expandirAcoes(linha.actions, 'count'" in norm
            and "expandirAcoes(linha.action_values, 'value'" in norm)
    r.prova(f"{rotulo} · ausência não vira zero (num/inteiro devolvem null)",
            "|| 0)" not in norm and "parseFloat(" not in norm)
    r.prova(f"{rotulo} · a janela de atribuição não é achatada num único valor",
            "presentes.length" in norm and "attribution_window: janela" in norm)

    valida = _sem_comentarios(_code(wf, "Validar semanticamente"))
    r.prova(f"{rotulo} · uma linha com janela carimbada sem pedido é recusada",
            "JANELA_CARIMBADA_SEM_PEDIDO" in valida)
    r.prova(f"{rotulo} · a identidade do fato inclui o instante observado (revisão)",
            "f.observado_em," in valida and "'meta_insight_' + sha256Hex(identidade)" in valida)
    r.prova(f"{rotulo} · o snapshot carrega o registro do pedido",
            "pedido: ctx.pedido" in valida)
    # A impressão digital precisa ser do CONTEÚDO nos DOIS produtores. Se um
    # incluir o instante e o outro não, o mesmo fato vira replay de um lado e
    # revisão do outro — e os dois escrevem na mesma tabela pela mesma RPC.
    r.prova(f"{rotulo} · o hash do snapshot exclui os instantes de observação",
            "SEM_INSTANTE" in valida
            and "'observado_em', 'ultima_vez_visto_em'" in valida
            and "linhas: rows," not in valida)
    # A lacuna anterior fechou: `medida` chegou na migration candidata do read
    # model e o backend passou a emitir as duas medidas na mesma tabela. O que
    # precisa ser vigiado agora é a colisão de chave: `actions` e `action_values`
    # dividem `(fato, ordem)`, então reiniciar a numeração nos valores faria cada
    # linha de dinheiro sobrescrever uma linha de contagem.
    r.prova(f"{rotulo} · contagem e valor vão para a mesma tabela, com `medida`",
            "trafego_meta_insight_action: insightAction" in valida
            and "trafego_meta_insight_action_value" not in valida)
    r.prova(f"{rotulo} · a ordem das actions é contínua e não reinicia nos valores",
            "let ordemDaAction = 0;" in valida
            and "f.actions.concat(f.action_values)" in valida
            and "ordemDaAction += 1;" in valida)
    r.prova(f"{rotulo} · a identidade do fato é a mesma do backend (grão inteiro)",
            all(campo in valida for campo in (
                "f.time_increment,", "f.action_report_time,", "f.fuso_da_conta ||")))
    r.prova(f"{rotulo} · a linha do fato carrega o grão, a moeda e a completude",
            all(campo in valida for campo in (
                "time_increment: f.time_increment", "action_report_time: f.action_report_time",
                "account_timezone: f.fuso_da_conta", "currency: ctx.moeda", "completo: completo")))


def validar_paginacao_e_completude(wf: dict, r: Relatorio, rotulo: str) -> None:
    """Cursor real, teto de página, e a incompletude que trava a marca d'água."""
    norm = _sem_comentarios(_code(wf, "Pagina: normalizar"))
    r.prova(f"{rotulo} · quem decide se há próxima página é paging.next",
            "Boolean(paging && paging.next)" in norm)
    r.prova(f"{rotulo} · o cursor lido é paging.cursors.after",
            "paging.cursors.after" in norm)
    r.prova(f"{rotulo} · paging.next sem cursor vira INCOMPLETO, não laço infinito",
            "META_INVALID_PAGINATION" in norm)
    r.prova(f"{rotulo} · cursor que não avança vira INCOMPLETO",
            "META_PAGINATION_LOOP" in norm)
    r.prova(f"{rotulo} · estourar o teto de páginas vira janela truncada declarada",
            "PAGINACAO_ACIMA_DO_TETO" in norm)

    pedido = _sem_comentarios(_code(wf, "Pagina: preparar pedido"))
    r.prova(f"{rotulo} · o teto de páginas é configuração, não constante escondida",
            "Number(cfg.MAX_PAGINAS)" in pedido)
    r.prova(f"{rotulo} · o cursor entra no pedido como `after`",
            "parametros.after = cursor" in pedido)

    valida = _sem_comentarios(_code(wf, "Validar semanticamente"))
    r.prova(f"{rotulo} · janela incompleta NÃO avança marca d'água",
            "marca_dagua: completo && !houveRecusa ? String(ctx.janela_fim) : null" in valida)
    r.prova(f"{rotulo} · o snapshot declara completude e motivo",
            "completo:" in valida and "motivo_incompleto:" in valida)

    fechar = _sem_comentarios(_code(wf, "Fechar execucao"))
    r.prova(f"{rotulo} · a marca d'água do fechamento exige leitura completa E persistida",
            "completo && it.persistencia_confirmada" in fechar)


def validar_erros_e_autorizacao(wf: dict, r: Relatorio, rotulo: str) -> None:
    """401/403 param e exigem ação; 429/5xx repetem com limite."""
    cls = _sem_comentarios(_code(wf, "Classificar erro da Meta"))
    r.prova(f"{rotulo} · 401/403 são classificados como AUTENTICACAO",
            "codigo === 401 || codigo === 403" in cls and "'AUTENTICACAO'" in cls)
    r.prova(f"{rotulo} · autenticação exige ação humana",
            "exigeAcaoHumana = classe === 'AUTENTICACAO'" in cls)
    r.prova(f"{rotulo} · 429 é COTA e 5xx é INDISPONIVEL",
            "'COTA'" in cls and "'INDISPONIVEL'" in cls and "codigo === 429" in cls)
    r.prova(f"{rotulo} · autenticação NÃO recomenda repetir",
            "retryNaProximaRodada = classe === 'COTA' || classe === 'INDISPONIVEL'" in cls)
    r.prova(f"{rotulo} · rótulo desconhecido vira DESCONHECIDA, nunca ok",
            "'DESCONHECIDA'" in cls)
    r.prova(f"{rotulo} · a mensagem do erro é rótulo, não corpo bruto",
            "erro_mensagem: motivo" in cls and "String(alvo.message" not in cls.split(
                "erro_mensagem")[-1])

    saude = _sem_comentarios(_code(wf, "Batimento e saude"))
    r.prova(f"{rotulo} · autorização quebrada ganha estado próprio no batimento",
            "BLOQUEADO_AUTORIZACAO" in saude)
    r.prova(f"{rotulo} · ausência de releitura é INDETERMINADO, nunca sucesso",
            "INDETERMINADO" in saude and "lido === null" in saude)
    r.prova(f"{rotulo} · o alerta só carrega referência opaca da conta",
            "conta_ref: c.conta_ref" in saude and "conta_externa" not in saude)

    graph = next(n for n in wf["nodes"] if n["name"] == NO_GRAPH)
    r.prova(f"{rotulo} · o backoff da chamada Meta é limitado e declarado",
            graph.get("maxTries") == 3 and graph.get("waitBetweenTries") == 5000)
    r.prova(f"{rotulo} · a falha da Meta sai por saída de erro, não por item vazio",
            graph.get("onError") == "continueErrorOutput")


def validar_recibo(wf: dict, r: Relatorio, rotulo: str) -> None:
    """O recibo tem de bastar para reprocessar — e não pode vazar nada."""
    fechar = _sem_comentarios(_code(wf, "Fechar execucao"))
    obrigatorios = [
        "conta_ref", "periodo_inicio", "periodo_fim", "fuso_da_conta", "api_versao",
        "pedido", "paginas", "linhas_lidas", "linhas_aceitas", "linhas_rejeitadas",
        "completo", "motivo_incompleto", "persistencia_confirmada", "marca_dagua",
        "erro_classe", "erro_mensagem",
    ]
    faltando = [c for c in obrigatorios if f"{c}:" not in fechar]
    r.prova(f"{rotulo} · o sub-recibo por conta traz tudo que reprocessa", not faltando,
            ", ".join(faltando))
    r.prova(f"{rotulo} · o recibo usa referência opaca, nunca id de conta cru",
            "conta_ref: String(it.conta_ref)" in fechar
            and "conta_externa:" not in fechar)
    r.prova(f"{rotulo} · o fechamento soma a entrada do laço, não um nó de dentro",
            "$input.all()" in fechar
            and not re.search(r"\$\(\s*'[^']+'\s*\)\s*\.all\(", fechar))
    r.prova(f"{rotulo} · o snapshot de fechamento declara o escopo de execução",
            "escopo: 'insights_fechamento'" in fechar)

    valida = _sem_comentarios(_code(wf, "Validar semanticamente"))
    r.prova(f"{rotulo} · o snapshot da página declara o escopo de página",
            "escopo: 'insights_pagina'" in valida)
    r.prova(f"{rotulo} · a chave de idempotência respeita o CHECK do banco",
            "'meta_sync_' + sha256Hex(" in valida and ".slice(0, 32)" in valida)
    r.prova(f"{rotulo} · o hash do snapshot respeita o CHECK do banco",
            "'meta_snapshot_' + sha256Hex(" in valida)

    # ── os três campos que a RPC canônica exige e o fluxo não emitia ──────────
    #
    # ⚠️ ESTE BLOCO É NOVO PORQUE O ENVELOPE MUDOU, e ele existe para que a
    # próxima pessoa não desfaça a correção sem perceber. Os três campos estão em
    # `20260907210000_meta_read_model_consistency.sql:1260-1272` (o comentário que
    # É o contrato) e em `backend/app/trafego/meta/read_model.py:101-105`.
    for no, js in (("Validar semanticamente", valida),
                   ("Fechar execucao", fechar)):
        r.prova(f"{rotulo} · [{no}] o snapshot declara `hierarchy_complete` booleano",
                re.search(r"hierarchy_complete:\s*(?:true|false)\b", js) is not None)
        # ⚠️ `false`, e não por timidez: `hierarchy_complete` é a ÚNICA declaração
        # que autoriza a RPC a marcar ausência de campanha/adset/ad
        # (20260907210000:713 e 7.7). Este fluxo lê INSIGHTS — nunca percorre a
        # hierarquia —, então `true` aqui autorizaria apagar inventário a partir
        # de uma leitura que não olhou para ele.
        r.prova(f"{rotulo} · [{no}] uma leitura de insights NÃO se declara "
                "hierarquia completa",
                "hierarchy_complete: true" not in js)
        r.prova(f"{rotulo} · [{no}] o snapshot leva a chave de idempotência ESTÁVEL",
                "stable_idempotency_key: idempotenciaEstavel" in js)

    # ⚠️ A CHAVE ESTÁVEL NÃO PODE CONTER O INSTANTE — é literalmente a definição
    # dela (`chave_origem: 'volatil'` é o defeito que ela existe para consertar).
    # Derivar de `snapshot_hash` seria o erro exato: o hash cobre linhas que
    # carregam `observado_em`. Derivar de `execucao_chave` seria o mesmo por outro
    # caminho: numa rodada manual ela termina em `m<HH><MM>`, um relógio.
    estavel_pagina = valida.split("const pedidoEstavel", 1)
    r.prova(f"{rotulo} · a chave estável da página é derivada de um bloco próprio",
            len(estavel_pagina) == 2)
    if len(estavel_pagina) == 2:
        corpo = estavel_pagina[1].split("idempotenciaEstavel =", 1)[0]
        proibidos = [t for t in ("snapshotHash", "execucao_chave", "iniciada_em",
                                 "observado_em", "passo", "Date")
                     if t in corpo]
        r.prova(f"{rotulo} · a chave estável da página não carrega o instante",
                not proibidos, ", ".join(proibidos))
        # E carrega o que DESCREVE o pedido — inclusive a página: sem ela as
        # páginas 2..N nasceriam com a chave da página 1 e a RPC as descartaria
        # como replay (20260907210000:746-757 devolve `repetido` sem escrever).
        exigidos = ["ctx.conta_externa", "janela", "ctx.nivel", "ctx.time_increment",
                    "ctx.action_report_time", "ctx.breakdown", "ctx.janela_declarada",
                    "ctx.campos_de_insight", "pagina="]
        faltando = [t for t in exigidos if t not in corpo]
        r.prova(f"{rotulo} · a chave estável da página descreve o pedido inteiro",
                not faltando, ", ".join(faltando))

    estavel_fecha = fechar.split("const fechamentoEstavel", 1)
    r.prova(f"{rotulo} · a chave estável do fechamento é derivada de um bloco próprio",
            len(estavel_fecha) == 2)
    if len(estavel_fecha) == 2:
        corpo = estavel_fecha[1].split("idempotenciaEstavel =", 1)[0]
        proibidos = [t for t in ("snapshotHash", "execucao_chave", "iniciada_em",
                                 "ultimo_run_id", "agora", "resultado")
                     if t in corpo]
        r.prova(f"{rotulo} · a chave estável do fechamento não carrega o instante "
                "nem o desfecho", not proibidos, ", ".join(proibidos))

    # ⚠️ E A RELEITURA TEM DE PROCURAR A CHAVE QUE O BANCO GRAVOU. Com a chave
    # estável presente, a RPC grava ELA (20260907210000:727-742). Apontar a
    # releitura para a volátil devolveria zero linha e faria "Batimento e saude"
    # carimbar INDETERMINADO em toda rodada — um alerta permanente, que é a
    # maneira mais eficiente de ensinar alguém a ignorar alertas.
    r.prova(f"{rotulo} · o fechamento publica a chave ESTÁVEL como endereço de releitura",
            "idempotencia_fechamento: idempotenciaEstavel" in fechar)
    releitura = next((n for n in wf["nodes"] if n["name"] == "Releitura do recibo"), None)
    r.prova(f"{rotulo} · a releitura consulta por `idempotencia_fechamento`",
            releitura is not None
            and "[\"resumo\"][\"idempotencia_fechamento\"]"
            in str(releitura["parameters"].get("url", "")))

    rec = _sem_comentarios(_code(wf, "Reconciliar lote"))
    r.prova(f"{rotulo} · a persistência só é dada por confirmada com run_id",
            "RPC_SEM_RUN_ID" in rec and "persistencia_confirmada: true" in rec)
    r.prova(f"{rotulo} · RPC que não confirma derruba o lote",
            "RPC_RECUSOU_O_SNAPSHOT" in rec)

    # Nenhuma regra financeira duplicada em Code node: quem soma dinheiro é a
    # projeção do banco, não o fluxo.
    js_todos = "\n".join(_sem_comentarios(n["parameters"].get("jsCode", ""))
                         for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code")
    r.prova(f"{rotulo} · o fluxo não recalcula custo por resultado nem ROAS",
            not re.search(r"(?i)\b(roas|cpa|custo_por|cost_per|receita|revenue)\b", js_todos))
    r.prova(f"{rotulo} · o fluxo não soma spend entre linhas",
            not re.search(r"spend\s*\+=|\+\s*spend\b", js_todos))


def validar_topologia(wf: dict, r: Relatorio, rotulo: str) -> None:
    conexoes = wf["connections"]

    def destinos(nome: str, saida: int) -> list[str]:
        grupos = conexoes.get(nome, {}).get("main", [])
        if len(grupos) <= saida:
            return []
        return [c["node"] for c in grupos[saida]]

    cadeia = [
        ("Agenda", 0, "Config"),
        ("Executar manualmente", 0, "Config"),
        ("Config", 0, "Identidade da execucao"),
        ("Identidade da execucao", 0, "Contas autorizadas"),
        ("Contas autorizadas", 0, "Selecionar contas"),
        ("Selecionar contas", 0, "Objetos conhecidos"),
        ("Objetos conhecidos", 0, "Identidade VOLC por conta"),
        ("Identidade VOLC por conta", 0, "Lote de contas"),
        ("Pagina: preparar pedido", 0, NO_GRAPH),
        ("Pagina: preparar pedido", 0, "Juntar contexto e resposta"),
        ("Pagina: preparar pedido", 0, "Juntar contexto e erro"),
        (NO_GRAPH, 0, "Juntar contexto e resposta"),
        ("Juntar contexto e resposta", 0, "Pagina: normalizar"),
        ("Juntar contexto e erro", 0, "Classificar erro da Meta"),
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
    limite = next((n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.limit"), None)
    r.prova(f"{rotulo} · o Limit do fechamento é de 1 item",
            limite is not None and limite["parameters"]["maxItems"] == 1)

    r.prova(f"{rotulo} · página seguinte volta ao pedido, não ao início",
            destinos("Tem proxima pagina?", 0) == ["Pagina: preparar pedido"])
    r.prova(f"{rotulo} · conta encerrada devolve o controle ao laço de contas",
            destinos("Tem proxima pagina?", 1) == ["Lote de contas"])
    r.prova(f"{rotulo} · alerta sai só da saída verdadeira do teste de falha",
            destinos("Falha real?", 0) == ["Alerta de rotina parada"]
            and destinos("Falha real?", 1) == [])
    r.prova(f"{rotulo} · a saída de erro da Meta casa com o contexto antes de classificar",
            destinos(NO_GRAPH, 1) == ["Juntar contexto e erro"])

    def alcanca(inicio: str, alvo: str, bloqueio: str) -> bool:
        visto, fila = {inicio}, [inicio]
        while fila:
            atual = fila.pop()
            if atual == bloqueio:
                continue
            for saidas in conexoes.get(atual, {}).get("main", []):
                for c in saidas:
                    if c["node"] == alvo:
                        return True
                    if c["node"] not in visto:
                        visto.add(c["node"])
                        fila.append(c["node"])
        return False

    # 401/403 não podem girar: da saída de erro não existe caminho de volta ao nó
    # de requisição sem passar pelo laço de contas, que só avança.
    r.prova(f"{rotulo} · erro de autorização não tem como voltar ao pedido sem passar pelo laço",
            not alcanca("Classificar erro da Meta", "Pagina: preparar pedido",
                        "Lote de contas"))

    # ⚠️ REGRESSÃO NOMEADA (herdada do fluxo irmão). `$()` dentro do laço resolve
    # pelo ÍNDICE DA RODADA do nó que pergunta; uma conta que falha desalinha os
    # índices e a iteração seguinte lê o contexto de OUTRA conta, em silêncio.
    for nome in ("Pagina: normalizar", "Classificar erro da Meta"):
        js = _sem_comentarios(_code(wf, nome))
        r.prova(f"{rotulo} · [{nome}] toma o contexto do Merge, não de $() no laço",
                "$('Pagina: preparar pedido')" not in js)


def validar_agenda(wf: dict, r: Relatorio, rotulo: str, esperado: str) -> None:
    for no in wf["nodes"]:
        if no["type"] == "n8n-nodes-base.scheduleTrigger":
            regras = no["parameters"]["rule"]["interval"]
            crons = [x.get("expression") for x in regras]
            r.prova(f"{rotulo} · a agenda declarada é `{esperado}`", crons == [esperado],
                    str(crons))
            r.prova(f"{rotulo} · a agenda Meta não colide com o D-1 do Google (06h)",
                    crons != ["0 6 * * *"])
            return
    r.prova(f"{rotulo} · existe gatilho de agenda", False)


def main() -> int:
    r = Relatorio()

    for caminho in ALVOS:
        rotulo = "META-D1"
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

        # Round trip de import/export: o que o n8n devolveria num export tem de
        # sobreviver a uma ida e volta por JSON sem perder nada, e o subconjunto
        # que o contrato público do PUT aceita tem de estar completo.
        r.prova(f"{rotulo} · sobrevive ao round trip de import/export",
                json.loads(json.dumps(wf, ensure_ascii=False)) == wf)
        publico = {k: wf[k] for k in ("name", "nodes", "connections", "settings")
                   if k in wf}
        r.prova(f"{rotulo} · o payload público de import está completo",
                set(publico) == {"name", "nodes", "connections", "settings"})
        r.prova(f"{rotulo} · nenhum nó carrega campo interno de execução",
                not any(set(n) & {"issues", "credentialsId", "webhookId", "disabled"}
                        for n in wf["nodes"]))

        nos = validar_estrutura(wf, r, rotulo)
        validar_nos(wf, nos, r, rotulo)
        validar_expressoes(wf, nos, r, rotulo)
        validar_sintaxe_js(wf, r, rotulo)
        validar_topologia(wf, r, rotulo)
        validar_seguranca(wf, r, rotulo)
        validar_credencial_meta(wf, r, rotulo)
        validar_contrato_meta(wf, r, rotulo)
        validar_fuso_da_conta(wf, r, rotulo)
        validar_contrato_do_pedido_no_fio(wf, r, rotulo)
        validar_paginacao_e_completude(wf, r, rotulo)
        validar_erros_e_autorizacao(wf, r, rotulo)
        validar_recibo(wf, r, rotulo)
        validar_agenda(wf, r, rotulo, AGENDAS[caminho.name])

    print()
    print("════════════════════════════════════════════════════════")
    print(f"  passaram {r.ok} · falharam {len(r.falhas)} · pulados {len(r.pulados)}")
    if r.falhas:
        for f in r.falhas:
            print(f"    ✗ {f}")
        return 1
    print("  workflow n8n Meta VALIDADO nó a nó, com topologia e varreduras")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
