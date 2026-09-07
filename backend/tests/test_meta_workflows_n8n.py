"""Contraprovas do workflow n8n de insights diários Meta Ads.

Estes testes NÃO reimplementam o que os gates já provam — eles fazem os gates
rodarem dentro da suíte e depois cobrem, em Python puro e num simulador offline
do JavaScript, as invariantes que um gate isolado poderia deixar de fora:

* o par gerador↔JSON (JSON editado à mão some no próximo build);
* o contrato entre a pergunta que o fluxo faz e `app.trafego.meta.dominio` (dois
  produtores que perguntam diferente produzem duas séries que ninguém pode
  somar);
* **a janela D-1 no fuso da CONTA** — a propriedade que o lado Python acabou de
  consertar em `dominio.hoje_na_conta` e que aqui é executada de verdade: duas
  contas em fusos diferentes, no MESMO instante, precisam pedir dias diferentes;
* `landing_page_views` sem `ViewContent` (defeito T05) e ausência que não vira
  zero;
* releitura de dia passado que produz REVISÃO, não gasto duplicado;
* 401/403 que param e exigem ação em vez de repetir.

Nada aqui abre socket, chama a Graph API, fala com o Supabase oficial ou toca no
n8n. O workflow **não é importado, não é executado e não é ativado** por teste
nenhum: o que roda é o texto do `jsCode` dentro de um `node` local, com relógio
injetado e sem rede.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
GERADOR = "n8n/gerar_flows_meta_ledger.py"
VALIDADOR = "scripts/validar_workflows_n8n_meta.py"
D1 = RAIZ / "n8n" / "volc_meta_insights_dia_d1.json"
MIGRATION = RAIZ / "supabase" / "migrations" / "v15_02_meta_ads_insights.sql"


def _rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=RAIZ, capture_output=True, text=True)


def _wf() -> dict:
    return json.loads(D1.read_text(encoding="utf-8"))


def _code(wf: dict, nome: str) -> str:
    for no in wf["nodes"]:
        if no["name"] == nome:
            return no["parameters"]["jsCode"]
    raise AssertionError(f"nó {nome} não existe no workflow")


def _cfg(wf: dict) -> dict[str, str]:
    no = next(n for n in wf["nodes"] if n["name"] == "Config")
    return {a["name"]: a["value"] for a in no["parameters"]["assignments"]["assignments"]}


def _sem_comentarios(js: str) -> str:
    """Só o CÓDIGO. Os comentários citam o defeito antigo textualmente, e uma
    varredura ingênua acusaria a própria explicação como reincidência."""
    return "\n".join(l for l in js.splitlines() if not l.lstrip().startswith("//"))


# ── os gates, rodando de verdade ────────────────────────────────────────────

def test_o_json_em_disco_e_o_que_o_gerador_produz():
    """JSON editado à mão diverge do gerador e some no próximo build."""
    p = _rodar(sys.executable, GERADOR, "--check")
    assert p.returncode == 0, p.stdout + p.stderr


def test_validacao_no_a_no_do_workflow_meta():
    p = _rodar(sys.executable, VALIDADOR)
    assert p.returncode == 0, p.stdout[-6000:] + p.stderr[-2000:]
    assert "falharam 0" in p.stdout


# ── o artefato, em Python puro ──────────────────────────────────────────────

def test_o_workflow_nasce_inativo_e_declara_isso_no_meta():
    wf = _wf()
    assert wf["active"] is False
    assert "INATIVO" in wf["meta"]["volc"]["estado"]


def test_a_credencial_meta_usa_um_tipo_real_e_nao_carrega_segredo():
    """O tipo é REAL; o que falta é o ITEM do cofre — e isso fica declarado.

    ⚠️ POR QUE A CONTRAPROVA ANTIGA DEIXOU DE DESCREVER A VERDADE.

    Este teste exigia `nodeCredentialType == 'metaGraphApiNaoProvisionada'` e
    `id == 'REPLACE_ME'`, com a justificativa de que inventar um tipo plausível
    seria fingir integração. A justificativa continua válida; o que estava errado
    era supor que um tipo INVENTADO fosse o oposto de fingir. Um
    `nodeCredentialType` fora do catálogo da instância não faz o nó "parar por
    falta de credencial": faz o workflow ser inválido. O n8n não oferece o
    seletor, não há onde pendurar o item do cofre, e o operador não consegue
    provisionar nem depois de ter o token na mão. A pendência virava beco sem
    saída, e o teste carimbava isso como estado desejado.

    O tipo agora é `httpHeaderAuth` — nativo do n8n, na forma literal do
    precedente vivo desta base (`n8n/joinads_report_day_before.json:144-146` e
    `:190-194`). Ele guarda NOME e VALOR do cabeçalho dentro do item do cofre, e
    por isso o workflow não sabe (nem precisa saber) qual é o cabeçalho.
    `httpQueryAuth` seria a alternativa óbvia e está proibida: poria o token na
    query string, onde ele vaza para log de proxy e histórico de execução.

    O que continua sendo provado, e continuará depois do provisionamento:
    nenhum segredo viaja, e `provisionada` bate com o que está no nó NOS DOIS
    SENTIDOS.
    """
    wf = _wf()
    graph = next(n for n in wf["nodes"] if n["name"] == "Meta Graph: insights")
    params = graph["parameters"]
    assert params["authentication"] == "genericCredentialType"
    assert params["genericAuthType"] == "httpHeaderAuth"
    assert "nodeCredentialType" not in params
    # O tipo fictício não pode voltar por nenhuma porta.
    bruto = D1.read_text(encoding="utf-8")
    assert "metaGraphApiNaoProvisionada" not in bruto

    cred = graph["credentials"]["httpHeaderAuth"]
    assert set(cred) == {"id", "name"}, "credencial é REFERÊNCIA, nunca valor"

    declarado = wf["meta"]["volc"]["credencial"]
    assert isinstance(declarado["provisionada"], bool)
    assert declarado["tipo"] == params["genericAuthType"]
    # Coerência nos DOIS sentidos: sem ela bastaria virar o booleano para
    # "liberar" um workflow que continua apontando para o marcador.
    if declarado["provisionada"] is False:
        assert cred["id"] == "PROVISIONAR__VOLC_META_ADS_HEADER_AUTH"
        assert declarado["item_id_marcador"] == cred["id"]
        assert declarado["estado"] == "NAO_PROVISIONADA"
        assert wf["meta"]["volc"]["pronto_para_publicar"] is False
        assert "A PROVISIONAR" in cred["name"]
    else:
        assert "PROVISIONAR__" not in bruto
        assert cred["id"].strip() and cred["id"] != "REPLACE_ME"
        assert wf["meta"]["volc"]["pronto_para_publicar"] is True

    # E nenhum caminho alternativo de autorização.
    assert "access_token" not in bruto
    # Com httpHeaderAuth o cabeçalho vive no item do cofre; um cabeçalho de
    # autorização escrito aqui significaria que alguém o montou fora dele.
    assert not re.search(r"(?i)\"authorization\"", bruto)
    assert not re.search(r"(?i)localhost|127\.0\.0\.1|keychain|/Users/", bruto)


def test_a_falta_de_credencial_bloqueia_a_publicacao_de_verdade():
    """O bloqueio é MECÂNICO, não um lembrete no sticky note.

    Uma pendência que depende de alguém ler um aviso não é bloqueio. O publicador
    lê `meta.volc.pronto_para_publicar` do artefato e recusa `--apply` enquanto
    ele for falso — e é isso que este teste amarra, para que ninguém apague o
    portão achando que o aviso basta.
    """
    publicador = (RAIZ / "scripts" / "publicar_workflows_n8n_meta.py").read_text(
        encoding="utf-8")
    assert "pronto_para_publicar" in publicador
    assert "CREDENCIAL_NAO_PROVISIONADA" in publicador
    wf = _wf()
    assert wf["meta"]["volc"]["pronto_para_publicar"] is (
        wf["meta"]["volc"]["credencial"]["provisionada"])


def test_nenhum_destino_fora_da_autoridade_oficial():
    bruto = D1.read_text(encoding="utf-8")
    assert ".supabase.co" not in bruto
    hosts = set(re.findall(r"https?://([A-Za-z0-9._-]+)", bruto))
    assert hosts <= {"database.agenciavolc.com.br", "graph.facebook.com"}, hosts


def test_nenhuma_escrita_na_meta_alcancavel():
    """Fluxo de leitura: nenhum edge de criação/edição de objeto de anúncio."""
    wf = _wf()
    graph = next(n for n in wf["nodes"] if n["name"] == "Meta Graph: insights")
    assert graph["parameters"]["method"] == "GET"
    bruto = D1.read_text(encoding="utf-8")
    for edge in ("/campaigns", "/adsets", "/adcreatives", "/adimages", "/advideos"):
        assert edge not in bruto, edge
    js = _code(wf, "Pagina: preparar pedido")
    assert "/act_${ctx.conta_externa}/insights`" in js


def test_nenhum_segredo_nem_id_de_conta_no_arquivo():
    bruto = D1.read_text(encoding="utf-8")
    for padrao in (r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", r"\bEAA[A-Za-z0-9]{20,}",
                   r"(?i)\bBearer\s+[A-Za-z0-9_\-.]{20,}",
                   r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"):
        assert not re.search(padrao, bruto), padrao
    cfg = _cfg(_wf())
    assert cfg["CONTAS_PERMITIDAS"] == ""
    assert not any(re.fullmatch(r"[0-9]{6,40}", v) for v in cfg.values())


def test_a_pergunta_do_fluxo_e_uma_pergunta_legal_no_dominio():
    """A costura onde dois artefatos discordam calados.

    O fluxo n8n e o backend Python leem a MESMA API. Se um pede
    `time_increment=1` e o outro `all_days`, ou se as listas de campos divergem,
    as duas séries chegam ao mesmo banco e alguém as soma sem perceber que são
    perguntas diferentes.
    """
    from app.trafego.meta import dominio as dom

    cfg = _cfg(_wf())
    assert cfg["CAMPOS_DE_INSIGHT"] == dom.CAMPOS_DE_INSIGHT
    assert cfg["NIVEL"] in dom.NIVEIS_DE_INSIGHT
    assert cfg["TIME_INCREMENT"] == "1"
    assert cfg["ACTION_REPORT_TIME"] in dom.INSTANTES_DE_RELATORIO
    assert cfg["BREAKDOWN"] in dom.BREAKDOWNS_PERMITIDOS
    assert json.loads(cfg["MAX_DIAS_POR_PEDIDO"]) == dict(dom.MAX_DIAS_POR_PEDIDO)
    janelas = tuple(j for j in cfg["JANELAS_DE_ATRIBUICAO"].split(",") if j.strip())
    dom.validar_combinacao_de_insight(
        nivel=cfg["NIVEL"], breakdown=cfg["BREAKDOWN"], janelas=janelas)

    from datetime import date
    pedido = dom.PedidoDeInsights(
        conta_externa="1234567890",
        nivel=cfg["NIVEL"],
        periodo_inicio=date(2026, 9, 6),
        periodo_fim=date(2026, 9, 6),
        fuso_da_conta="America/Sao_Paulo",
        time_increment=cfg["TIME_INCREMENT"],
        breakdown=cfg["BREAKDOWN"],
        action_report_time=cfg["ACTION_REPORT_TIME"],
        janelas_de_atribuicao=janelas,
        limite_por_pagina=int(cfg["LIMITE_POR_PAGINA"]),
    )
    # Sem janela pedida, a etiqueta é `default` dos dois lados.
    assert pedido.janela_declarada == "default"
    assert "janelaDeclarada(janelas)" in _code(_wf(), "Pagina: normalizar")


def test_a_janela_nunca_sai_do_fuso_do_servidor():
    """Regressão nomeada, fixada no texto do nó que a produz."""
    js = _sem_comentarios(_code(_wf(), "Selecionar contas"))
    assert "timezone_name" in js
    assert "dataNaZona(agora, fuso)" in js
    assert "subtrairDias(hojeNaConta, 1)" in js
    assert "CONTA_SEM_FUSO" in js and "FUSO_DESCONHECIDO" in js
    # O fuso do disparo é só rótulo da rodada; ele não pode encostar na janela.
    assert "TZ_DO_DISPARO" not in js and "tz_do_disparo" not in js


def test_a_ausencia_nunca_vira_zero_e_lpv_nao_soma_viewcontent():
    """O defeito T05, fixado como contraprova.

    `landing_page_view` + `offsite_conversion.fb_pixel_view_content` devolvia um
    número que não é nenhuma das duas medidas e ia direto para o custo por LPV do
    painel. E `int(valor or 0)` transformava action presente sem valor medido em
    zero.
    """
    from app.trafego.meta import dominio as dom

    js = _sem_comentarios(_code(_wf(), "Pagina: normalizar"))
    assert f"'{dom.ACTION_TYPE_LPV}'" in js
    assert dom.ACTION_TYPE_VIEW_CONTENT not in js
    assert "|| 0)" not in js
    assert "parseFloat(" not in js
    assert "if (v === null || v === undefined || v === '') return null;" in js
    # `actions` conta eventos, `action_values` soma dinheiro: separadas até o fim.
    assert "expandirAcoes(linha.actions, 'count'" in js
    assert "expandirAcoes(linha.action_values, 'value'" in js


def test_o_fluxo_nao_duplica_regra_financeira_em_code_node():
    """Quem soma dinheiro é a projeção do banco, não o fluxo."""
    wf = _wf()
    js = "\n".join(_sem_comentarios(n["parameters"].get("jsCode", ""))
                   for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code")
    assert not re.search(r"(?i)\b(roas|cpa|cost_per|custo_por|revenue|receita)\b", js)
    assert not re.search(r"spend\s*\+=|\+\s*spend\b", js)
    # E métrica não-aditiva nunca é somada.
    from app.trafego.meta import dominio as dom
    for metrica in dom.METRICAS_NAO_ADITIVAS:
        assert not re.search(rf"\b{metrica}\s*\+=", js), metrica


def test_o_documento_do_fluxo_usa_os_nomes_que_a_rpc_espera():
    """A costura onde o fluxo e a migration discordam calados.

    Um `landing_page_views` no fluxo contra um `lpv` no banco passaria em
    qualquer teste isolado dos dois lados.
    """
    js = _code(_wf(), "Validar semanticamente")
    sql = MIGRATION.read_text(encoding="utf-8")

    bloco = sql.split("CREATE TABLE public.trafego_meta_insight_daily (", 1)[1]
    bloco = bloco.split("CONSTRAINT", 1)[0]
    colunas = set(re.findall(r"^\s{2}([a-z_]+)\s+", bloco, re.M))
    metricas = {"spend", "impressions", "reach", "frequency", "clicks",
                "inline_link_clicks", "landing_page_views", "cpm", "cpc", "ctr"}
    assert metricas <= colunas, sorted(metricas - colunas)

    emitidos = set(re.findall(r"^\s{4}([a-z_]+): f\.[a-z_]+,$", js, re.M))
    assert metricas <= emitidos, sorted(metricas - emitidos)

    # E o envelope respeita os CHECKs de chave que a migration declara: o fluxo
    # produz `meta_snapshot_<32 hex>` e `meta_sync_<32 hex>` porque o banco os
    # exige, não por gosto de formato.
    assert "'meta_snapshot_' + sha256Hex(" in js and ".slice(0, 32)" in js
    assert "'meta_sync_' + sha256Hex(" in js
    assert "'^meta_snapshot_[a-f0-9]{32}$'" in sql
    assert "'^meta_sync_[a-f0-9]{32}$'" in sql


def test_o_fechamento_soma_a_entrada_do_laco_e_nao_um_no_de_dentro():
    """`$('No dentro do laço').all()` devolveria só a última rodada."""
    js = _sem_comentarios(_code(_wf(), "Fechar execucao"))
    assert "$input.all()" in js
    assert not re.search(r"\$\(\s*'[^']+'\s*\)\s*\.all\(", js)


def test_o_contexto_da_iteracao_vem_do_merge_e_nao_de_indice_de_rodada():
    """Regressão herdada do fluxo Google: `$()` dentro do laço resolve pelo
    índice da rodada, e uma conta que falha desalinha os índices."""
    wf = _wf()
    for nome in ("Pagina: normalizar", "Classificar erro da Meta"):
        assert "$('Pagina: preparar pedido')" not in _sem_comentarios(_code(wf, nome)), nome
    merges = {n["name"]: n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.merge"}
    assert set(merges) == {"Juntar contexto e resposta", "Juntar contexto e erro"}
    for no in merges.values():
        assert no["parameters"]["combineBy"] == "combineByPosition"


def test_split_in_batches_liga_done_e_lote_nas_saidas_certas():
    wf = _wf()
    saidas = wf["connections"]["Lote de contas"]["main"]
    assert [c["node"] for c in saidas[0]] == ["Fechar execucao"]           # main[0] = done
    assert [c["node"] for c in saidas[1]] == ["Pagina: preparar pedido"]   # main[1] = lote
    lote = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.splitInBatches")
    assert lote["parameters"]["batchSize"] == 1


def test_o_limit_1_protege_o_fechamento_de_rodar_por_item():
    wf = _wf()
    limite = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.limit")
    assert limite["parameters"]["maxItems"] == 1
    assert wf["connections"]["Fechar execucao"]["main"][0][0]["node"] == limite["name"]


def test_erro_de_autorizacao_nao_tem_como_girar():
    """401/403 seguem para a frente e reentram no laço, que só avança."""
    wf = _wf()
    conexoes = wf["connections"]
    assert [c["node"] for c in conexoes["Meta Graph: insights"]["main"][1]] \
        == ["Juntar contexto e erro"]
    assert [c["node"] for c in conexoes["Classificar erro da Meta"]["main"][0]] \
        == ["Lote de contas"]

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

    assert not alcanca("Classificar erro da Meta", "Pagina: preparar pedido",
                       "Lote de contas")
    graph = next(n for n in wf["nodes"] if n["name"] == "Meta Graph: insights")
    assert graph["retryOnFail"] is True and graph["maxTries"] == 3
    assert graph["waitBetweenTries"] == 5000
    assert graph["onError"] == "continueErrorOutput"


def test_a_agenda_e_declarada_e_nao_colide_com_a_do_google():
    wf = _wf()
    no = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger")
    assert no["parameters"]["rule"]["interval"][0]["expression"] == "0 7 * * *"
    assert _cfg(wf)["PASSOS"] == "07"
    assert wf["settings"]["timezone"] == "America/Sao_Paulo"


def test_o_gate_de_agenda_conhece_o_workflow_meta():
    """Agenda DECLARADA, não descoberta.

    O gate de autoridade de agenda varre artefatos capazes de agendar. Se o
    workflow Meta não estiver no conjunto declarado, ele aparece como "segunda
    agenda desconhecida" — e um gate que acusa o artefato legítimo ensina a
    ignorar o gate.
    """
    texto = (RAIZ / "scripts" / "gate_agenda_unica_gads.py").read_text(encoding="utf-8")
    assert "n8n/volc_meta_insights_dia_d1.json" in texto


# ── o JavaScript, executado de verdade e sem rede ───────────────────────────

_HARNESS = r"""
import fs from 'fs';
const { code, cfg } = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

let RELOGIO = new Date('2026-09-07T02:00:00.000Z');  // 23:00 do dia 6 em Sao_Paulo
const RealDate = Date;
globalThis.Date = class extends RealDate {
  constructor(...a) { if (a.length === 0) super(RELOGIO.getTime()); else super(...a); }
  static now() { return RELOGIO.getTime(); }
};

function rodar(nome, { entrada = [], nos = {}, runIndex = 0 } = {}) {
  const fn = new Function('$input', '$', '$workflow', '$execution', '$runIndex',
    '"use strict";' + code[nome]);
  const $input = {
    all: () => entrada.map((j) => ({ json: j })),
    first: () => ({ json: entrada[0] }),
  };
  const $ = (n) => {
    if (!(n in nos)) throw new Error('no ausente: ' + n);
    return { first: () => ({ json: nos[n] }), all: () => [{ json: nos[n] }], isExecuted: true };
  };
  return fn($input, $, { id: 'wf' }, { id: 1 }, runIndex);
}

const out = {};
const ident = rodar('Identidade da execucao', { nos: { Config: cfg, Agenda: {} } })[0].json;
out.passo = ident.passo;
out.janela_declarada = ident.janela_declarada;

// Duas contas, fusos diferentes, MESMO instante.
const contas = [
  { cofre_ativo_id: 'meta_account_metaacct_aaaaaaaaaaaaaaaaaaaaaaaa',
    account_external_id: 'act_1234567890', timezone_name: 'America/Sao_Paulo',
    moeda: 'BRL', credential_ativo_id: 'meta_credential_keychain_local' },
  { cofre_ativo_id: 'meta_account_metaacct_bbbbbbbbbbbbbbbbbbbbbbbb',
    account_external_id: '9876543210', timezone_name: 'Asia/Tokyo',
    moeda: 'JPY', credential_ativo_id: 'meta_credential_keychain_local' },
  { cofre_ativo_id: 'meta_account_metaacct_cccccccccccccccccccccccc',
    account_external_id: '5555555555', timezone_name: null },
];
const sel = rodar('Selecionar contas',
  { entrada: contas, nos: { Config: cfg, 'Identidade da execucao': ident } })[0].json;
out.janelas_por_fuso = {};
for (const c of sel.contas) out.janelas_por_fuso[c.fuso_da_conta] = c.janela_fim;
out.recusas = sel.contas_recusadas_na_selecao.map((x) => x.motivo);
out.refs_opacas = sel.contas.map((c) => c.conta_ref);

out.sem_conta_falha_fechado = false;
try { rodar('Selecionar contas', { entrada: [], nos: { Config: cfg, 'Identidade da execucao': ident } }); }
catch (e) { out.sem_conta_falha_fechado = /SEM_CONTA_AUTORIZADA/.test(e.message); }

const mapa = rodar('Identidade VOLC por conta', {
  entrada: [{ ad_account_ativo_id: contas[0].cofre_ativo_id, external_id: '111',
              meta_campaign_id: 'volc-1' }],
  nos: { 'Selecionar contas': sel } }).map((i) => i.json);
const ctx = mapa.find((m) => m.fuso_da_conta === 'America/Sao_Paulo');
const pag = rodar('Pagina: preparar pedido', { entrada: [ctx], nos: { Config: cfg } })[0].json;
out.parametros = pag.parametros_graph;
out.url_graph = pag.url_graph;

const resposta = { ...pag, data: [{
  account_id: 'act_1234567890', campaign_id: '111',
  date_start: pag.pedido.periodo_inicio, date_stop: pag.pedido.periodo_fim,
  spend: '10.50', impressions: '1000', clicks: '20',
  actions: [
    { action_type: 'landing_page_view', value: '4' },
    { action_type: 'offsite_conversion.fb_pixel_view_content', value: '7' },
  ],
  action_values: [{ action_type: 'purchase', value: '199.90' }],
}, {
  account_id: '1234567890', campaign_id: '222',
  date_start: pag.pedido.periodo_inicio, date_stop: pag.pedido.periodo_fim,
  spend: '5', impressions: '', clicks: '0',
  actions: [{ action_type: 'landing_page_view' }],
}], paging: { cursors: { after: 'C1' }, next: 'proxima' } };

const norm = rodar('Pagina: normalizar', { entrada: [resposta] })[0].json;
out.lpv = norm.fatos.map((f) => f.landing_page_views);
out.impressions = norm.fatos.map((f) => f.impressions);
out.clicks = norm.fatos.map((f) => f.clicks);
out.medidas = {
  actions: norm.fatos[0].actions.map((a) => a.medida),
  action_values: norm.fatos[0].action_values.map((a) => a.medida),
};
out.janela_do_fato = norm.fatos[0].janela_atribuicao;
out.tem_proxima = norm.tem_proxima_pagina;
out.cursor = norm.proximo_cursor;

const ultima = rodar('Pagina: normalizar',
  { entrada: [{ ...resposta, paging: { cursors: { after: 'C1' } } }] })[0].json;
out.ultima_pagina = ultima.tem_proxima_pagina;

const truncada = rodar('Pagina: normalizar',
  { entrada: [{ ...resposta, estourou_o_teto: true }] })[0].json;
out.truncada_motivo = truncada.motivo_incompleto;
out.truncada_marca = rodar('Validar semanticamente',
  { entrada: [truncada] })[0].json.snapshot.marca_dagua;

const val = rodar('Validar semanticamente', { entrada: [norm] })[0].json;
out.snapshot_hash = val.snapshot.snapshot_hash;
out.idempotencia = val.snapshot.idempotency_key;
out.idempotencia_estavel = val.snapshot.stable_idempotency_key;
out.hierarchy_complete = val.snapshot.hierarchy_complete;
out.escopo = val.snapshot.escopo;
out.marca_completa = val.snapshot.marca_dagua;
out.pedido_no_snapshot = val.snapshot.pedido;
out.fato_ids = val.snapshot.rows.trafego_meta_insight_daily.map((l) => l.meta_insight_daily_id);
// Campos crus do fato, para que o teste refaca a identidade pelo lado Python e
// prove que os dois produtores concordam.
out.fatos_persistidos = val.snapshot.rows.trafego_meta_insight_daily.map((l) => ({
  meta_insight_daily_id: l.meta_insight_daily_id,
  provider: l.provider,
  conta_externa: l.conta_externa,
  nivel: l.nivel,
  objeto_externo: l.objeto_externo,
  periodo_inicio: l.periodo_inicio,
  periodo_fim: l.periodo_fim,
  janela_atribuicao: l.janela_atribuicao,
  breakdown: l.breakdown,
  time_increment: l.time_increment,
  action_report_time: l.action_report_time,
  account_timezone: l.account_timezone,
  currency: l.currency,
  completo: l.completo,
  observado_em: l.observado_em,
}));
const acoesPersistidas = val.snapshot.rows.trafego_meta_insight_action;
out.action_values_linhas = acoesPersistidas.filter((a) => a.medida === 'value').length;
out.action_count_linhas = acoesPersistidas.filter((a) => a.medida === 'count').length;
out.action_ordens_por_fato = {};
for (const a of acoesPersistidas) {
  (out.action_ordens_por_fato[a.meta_insight_daily_id] ||= []).push(a.ordem);
}
out.tabelas_de_linha = Object.keys(val.snapshot.rows);
out.parcialidade = val.snapshot.partiality;

// Releitura: mesmo grão, outro instante => REVISÃO nova, nunca linha somada.
const outroInstante = JSON.parse(JSON.stringify(norm));
outroInstante.fatos.forEach((f) => { f.observado_em = '2026-09-09T00:00:00.000Z'; });
out.fato_ids_revisao = rodar('Validar semanticamente', { entrada: [outroInstante] })[0]
  .json.snapshot.rows.trafego_meta_insight_daily.map((l) => l.meta_insight_daily_id);

function classificar(e) {
  return rodar('Classificar erro da Meta',
    { entrada: [{ ...ctx, pagina: 1, acumulado: {}, ...e }] })[0].json;
}
out.erros = {
  e401: classificar({ httpCode: 401 }),
  e403: classificar({ statusCode: 403 }),
  e190: classificar({ error: { error: { code: 190 } } }),
  e429: classificar({ httpCode: 429 }),
  e503: classificar({ httpCode: 503 }),
  eNada: classificar({ message: 'texto bruto secreto' }),
};

const rec = rodar('Reconciliar lote',
  { entrada: [{ ok: true, repetido: false, run_id: 'r1' }],
    nos: { 'Validar semanticamente': val } })[0].json;
out.persistencia_confirmada = rec.persistencia_confirmada;
out.rpc_recusada = false;
try { rodar('Reconciliar lote', { entrada: [{ ok: false }], nos: { 'Validar semanticamente': val } }); }
catch (e) { out.rpc_recusada = /RPC_RECUSOU_O_SNAPSHOT/.test(e.message); }

const falha = { ...out.erros.e401, acumulado: { paginas: 0, parcialidades: [] } };
const fech = rodar('Fechar execucao',
  { entrada: [{ ...rec, motivo_incompleto: null }, falha] })[0].json;
out.fechamento = {
  escopo: fech.snapshot.escopo,
  account_asset_id: fech.snapshot.account_asset_id,
  contas: fech.snapshot.contas.length,
  exige_acao_humana: fech.resumo.exige_acao_humana,
  resultado: fech.resumo.resultado,
  marcas: fech.snapshot.contas.map((c) => c.marca_dagua),
  idempotencia: fech.snapshot.idempotency_key,
  idempotencia_estavel: fech.snapshot.stable_idempotency_key,
  hierarchy_complete: fech.snapshot.hierarchy_complete,
  // O endereço que "Releitura do recibo" consulta. Tem de ser a chave que a RPC
  // grava — a ESTÁVEL —, não a volátil.
  endereco_releitura: fech.resumo.idempotencia_fechamento,
  texto: JSON.stringify(fech.snapshot.contas),
};

const fechOk = rodar('Fechar execucao', { entrada: [{ ...rec, motivo_incompleto: null }] })[0].json;
out.saude = {
  bloqueado: rodar('Batimento e saude', {
    entrada: [{ chave_de_idempotencia: fech.resumo.idempotencia_fechamento,
                resultado: 'ok', paginas_lidas: fech.resumo.paginas }],
    nos: { 'Fechar execucao': fech } })[0].json.estado_saude,
  sem_releitura: rodar('Batimento e saude',
    { entrada: [], nos: { 'Fechar execucao': fechOk } })[0].json.estado_saude,
  com_releitura: rodar('Batimento e saude', {
    entrada: [{ chave_de_idempotencia: fechOk.resumo.idempotencia_fechamento,
                resultado: 'ok', paginas_lidas: fechOk.resumo.paginas }],
    nos: { 'Fechar execucao': fechOk } })[0].json,
};

out.lote_maior_que_um = false;
try { rodar('Pagina: preparar pedido', { entrada: [ctx, ctx], nos: { Config: cfg } }); }
catch (e) { out.lote_maior_que_um = /LOTE_CONTAS_MAIOR_QUE_UM/.test(e.message); }
out.reprocesso_acima_do_teto = false;
try { rodar('Identidade da execucao', { nos: { Config: { ...cfg, DIAS_DE_REPROCESSO: '500' }, Agenda: {} } }); }
catch (e) { out.reprocesso_acima_do_teto = /REPROCESSO_ACIMA_DO_TETO/.test(e.message); }

// Janelas de atribuição pedidas: uma linha por janela, sem achatar.
const cfgJ = { ...cfg, JANELAS_DE_ATRIBUICAO: '7d_click,1d_view' };
const identJ = rodar('Identidade da execucao', { nos: { Config: cfgJ, Agenda: {} } })[0].json;
const ctxJ = { ...ctx, janelas_solicitadas: identJ.janelas_solicitadas,
               janela_declarada: identJ.janela_declarada };
const pagJ = rodar('Pagina: preparar pedido', { entrada: [ctxJ], nos: { Config: cfgJ } })[0].json;
const normJ = rodar('Pagina: normalizar', { entrada: [{ ...pagJ, paging: {}, data: [{
  account_id: '1234567890', campaign_id: '111',
  date_start: pagJ.pedido.periodo_inicio, date_stop: pagJ.pedido.periodo_fim,
  actions: [{ action_type: 'lead', '7d_click': '5', '1d_view': '3' }] }] }] })[0].json;
out.janelas = {
  etiqueta: identJ.janela_declarada,
  no_fio: pagJ.parametros_graph.action_attribution_windows,
  expandidas: normJ.fatos[0].actions.map((a) => a.attribution_window).sort(),
  fato: normJ.fatos[0].janela_atribuicao,
};

// ── O MESMO PEDIDO, UM MINUTO DEPOIS ────────────────────────────────────────
//
// O defeito que a chave estável existe para consertar: dois cliques com um
// minuto de diferença produziam duas chaves e DOIS runs da mesma leitura.
//
// ⚠️ RODADA MANUAL, e não por agenda — `Agenda` fica FORA de `nos`, que é como o
// `try { $('Agenda').isExecuted } catch` do nó decide `disparo = 'manual'`. Numa
// rodada agendada o `passo` é a HORA (`07`), então dois disparos do mesmo cron
// já colidem por construção; é a rodada manual que ganha `passo = m<HH><MM>` e
// produz duas chaves por causa do relógio. É esse o caso que precisa de prova.
// O relógio anda 61 segundos: muda o minuto (e a chave volátil) sem mudar o dia
// em fuso nenhum. A chave estável TEM de sair idêntica.
function rodarPagina() {
  const i = rodar('Identidade da execucao', { nos: { Config: cfg } })[0].json;
  const s = rodar('Selecionar contas',
    { entrada: contas, nos: { Config: cfg, 'Identidade da execucao': i } })[0].json;
  const m = rodar('Identidade VOLC por conta', {
    entrada: [{ ad_account_ativo_id: contas[0].cofre_ativo_id, external_id: '111',
                meta_campaign_id: 'volc-1' }],
    nos: { 'Selecionar contas': s } }).map((x) => x.json);
  const c = m.find((x) => x.fuso_da_conta === 'America/Sao_Paulo');
  const pg = rodar('Pagina: preparar pedido', { entrada: [c], nos: { Config: cfg } })[0].json;
  const nm = rodar('Pagina: normalizar', { entrada: [{ ...pg, paging: {}, data: [{
    account_id: 'act_1234567890', campaign_id: '111',
    date_start: pg.pedido.periodo_inicio, date_stop: pg.pedido.periodo_fim,
    spend: '10.50', impressions: '1000', clicks: '20',
    actions: [{ action_type: 'landing_page_view', value: '4' }] }] }] })[0].json;
  const v = rodar('Validar semanticamente', { entrada: [nm] })[0].json;
  const r = rodar('Reconciliar lote',
    { entrada: [{ ok: true, repetido: false, run_id: 'r1', chave_origem: 'estavel' }],
      nos: { 'Validar semanticamente': v } })[0].json;
  const f = rodar('Fechar execucao', { entrada: [{ ...r, motivo_incompleto: null }] })[0].json;
  return {
    passo: i.passo,
    janela: `${c.janela_inicio}..${c.janela_fim}`,
    estavel: v.snapshot.stable_idempotency_key,
    volatil: v.snapshot.idempotency_key,
    fech_estavel: f.snapshot.stable_idempotency_key,
    fech_volatil: f.snapshot.idempotency_key,
  };
}
const clique1 = rodarPagina();
RELOGIO = new RealDate('2026-09-07T02:01:01.000Z');
const clique2 = rodarPagina();
RELOGIO = new RealDate('2026-09-07T02:00:00.000Z');
out.dois_cliques = { clique1, clique2 };

// A data que um cálculo em UTC teria devolvido no MESMO instante — é ela que as
// janelas das contas precisam contradizer para provar que não há fallback.
out.d1_em_utc = (() => {
  const hojeUtc = new RealDate('2026-09-07T02:00:00.000Z').toISOString().slice(0, 10);
  const d = new RealDate(RealDate.parse(hojeUtc + 'T00:00:00Z') - 86400000);
  return { hoje: hojeUtc, d1: d.toISOString().slice(0, 10) };
})();

// A chave estável da PÁGINA 2 não pode repetir a da página 1: se repetisse, a
// RPC trataria a página 2 como replay e descartaria tudo depois da primeira.
out.estavel_por_pagina = [1, 2, 3].map((n) => rodar('Validar semanticamente',
  { entrada: [{ ...norm, pagina: n }] })[0].json.snapshot.stable_idempotency_key);

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def simulacao(tmp_path_factory):
    """Executa o JavaScript EXATO do workflow, com relógio injetado e zero rede."""
    if shutil.which("node") is None:
        pytest.skip("node ausente — a simulação offline do Code node exige o runtime")
    wf = _wf()
    dados = {
        "code": {n["name"]: n["parameters"]["jsCode"]
                 for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code"},
        "cfg": _cfg(wf),
    }
    d = tmp_path_factory.mktemp("sim_meta")
    (d / "nodes.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    (d / "sim.mjs").write_text(_HARNESS, encoding="utf-8")
    p = subprocess.run(["node", str(d / "sim.mjs"), str(d / "nodes.json")],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-4000:]
    return json.loads(p.stdout)


def test_sim_a_janela_e_d1_no_fuso_da_conta_e_nao_do_servidor(simulacao):
    """⚠️ A PROPRIEDADE MAIS IMPORTANTE DESTE FLUXO, executada.

    Relógio em 2026-09-07T02:00Z. Nesse MESMO instante são 23:00 do dia 6 em
    São Paulo e 11:00 do dia 7 em Tóquio. As duas contas TÊM de pedir dias
    diferentes; se pedissem o mesmo, a janela estaria vindo do servidor.
    """
    janelas = simulacao["janelas_por_fuso"]
    assert janelas["America/Sao_Paulo"] == "2026-09-05"
    assert janelas["Asia/Tokyo"] == "2026-09-06"
    assert janelas["America/Sao_Paulo"] != janelas["Asia/Tokyo"]
    # Conta sem fuso é recusada, não cai num padrão.
    assert "CONTA_SEM_FUSO" in simulacao["recusas"]
    assert simulacao["sem_conta_falha_fechado"] is True
    # E o que viaja é a referência opaca, nunca o id numérico.
    assert all(r.startswith("metaacct_") for r in simulacao["refs_opacas"])


def test_sim_a_janela_contradiz_a_data_utc_do_mesmo_instante(simulacao):
    """A prova de que NÃO existe fallback para UTC — dita como contradição.

    ⚠️ Provar "a janela sai do fuso da conta" comparando duas contas entre si é
    metade da prova: se as duas caíssem no mesmo fallback, elas concordariam
    entre si e estariam as duas erradas. A outra metade é comparar com o que UTC
    teria dado NO MESMO INSTANTE.

    Relógio em 2026-09-07T02:00Z. Nesse instante:
      · em UTC              é dia 7 → D-1 seria 2026-09-06;
      · em America/Sao_Paulo são 23:00 do dia 6 → D-1 é 2026-09-05;
      · em Asia/Tokyo        são 11:00 do dia 7 → D-1 é 2026-09-06.
    São Paulo tem de DISCORDAR de UTC. É nas três horas em que ela discorda que
    o defeito antigo pedia à Meta um dia que a conta ainda não começou — e a
    série vazia entrava no painel como zero medido.
    """
    utc = simulacao["d1_em_utc"]
    assert utc["hoje"] == "2026-09-07" and utc["d1"] == "2026-09-06"
    janelas = simulacao["janelas_por_fuso"]
    assert janelas["America/Sao_Paulo"] == "2026-09-05"
    assert janelas["America/Sao_Paulo"] != utc["d1"], (
        "a janela de São Paulo coincidiu com a de UTC no instante em que elas "
        "TÊM de divergir; isso é a assinatura de um fallback para UTC")
    # E Tóquio, que nesse instante coincide com UTC, coincide por estar na mesma
    # data — não por ter caído no mesmo padrão. A prova disso é discordar de SP.
    assert janelas["Asia/Tokyo"] == "2026-09-06"
    assert janelas["Asia/Tokyo"] != janelas["America/Sao_Paulo"]


def test_sim_dois_cliques_no_mesmo_pedido_dao_UMA_chave_estavel(simulacao):
    """O defeito `chave_origem: 'volatil'`, fixado como contraprova.

    `20260907210000_meta_read_model_consistency.sql:1272-1276` nomeia o problema:
    a chave de idempotência derivava de `snapshot_hash`, que deriva das linhas,
    que carregam `observado_em`. Dois cliques com um segundo de diferença viravam
    duas chaves e DOIS runs da mesma leitura.

    Aqui o relógio anda 61 segundos — o bastante para mudar `passo`,
    `execucao_chave` e `observado_em`, e portanto a chave volátil — sem mudar o
    dia em fuso nenhum. A chave ESTÁVEL tem de sair idêntica.
    """
    a, b = simulacao["dois_cliques"]["clique1"], simulacao["dois_cliques"]["clique2"]
    # O relógio realmente andou (senão o teste passaria por não testar nada).
    assert a["passo"] != b["passo"], (a["passo"], b["passo"])
    assert a["volatil"] != b["volatil"], "a chave volátil deveria ter mudado"
    # E a janela pedida é a mesma: é o MESMO trabalho.
    assert a["janela"] == b["janela"] == "2026-09-05..2026-09-05"
    assert a["estavel"] == b["estavel"], "a chave estável carregou o instante"
    assert a["fech_estavel"] == b["fech_estavel"], (
        "a chave estável do fechamento carregou o instante")
    assert a["fech_volatil"] != b["fech_volatil"]


def test_sim_cada_pagina_tem_a_sua_chave_estavel(simulacao):
    """Sem a página na chave, tudo depois da primeira sumiria em silêncio.

    A RPC devolve `repetido: true` e NÃO escreve quando já existe run 'ok' com a
    chave (`20260907210000:746-757`). Se as páginas 2..N nascessem com a chave da
    página 1, cada uma delas seria descartada como replay — e o recibo diria
    `ok`. A página descreve QUE PEDAÇO do pedido, não QUANDO a resposta chegou.
    """
    chaves = simulacao["estavel_por_pagina"]
    assert len(set(chaves)) == len(chaves) == 3, chaves
    for k in chaves:
        assert re.fullmatch(r"meta_sync_[a-f0-9]{32}", k), k


def test_sim_o_envelope_leva_os_tres_campos_que_a_rpc_canonica_exige(simulacao):
    """A costura onde o fluxo e a RPC discordavam calados.

    Os três campos estão em `read_model.py:101-105` e no comentário-contrato de
    `20260907210000_meta_read_model_consistency.sql:1260-1272`.
    """
    assert simulacao["escopo"] == "insights_pagina"
    assert simulacao["fechamento"]["escopo"] == "insights_fechamento"

    # ⚠️ `false`, e isso é uma AFIRMAÇÃO. `hierarchy_complete` é a única
    # declaração que autoriza a RPC a marcar ausência de campanha/adset/ad
    # (20260907210000:713 e seção 7.7). Este fluxo lê INSIGHTS: nunca percorre a
    # hierarquia. Mandar `true` autorizaria apagar inventário a partir de uma
    # leitura que não olhou para ele.
    assert simulacao["hierarchy_complete"] is False
    assert simulacao["fechamento"]["hierarchy_complete"] is False

    for chave in (simulacao["idempotencia_estavel"],
                  simulacao["fechamento"]["idempotencia_estavel"]):
        assert re.fullmatch(r"meta_sync_[a-f0-9]{32}", chave), chave
    # A estável e a volátil são chaves DIFERENTES: se coincidissem, a estável
    # estaria derivando do mesmo material volátil.
    assert simulacao["idempotencia_estavel"] != simulacao["idempotencia"]

    # ⚠️ E a releitura de saúde procura a chave que o banco GRAVA. Com a estável
    # presente a RPC usa ela (20260907210000:727-742); apontar a releitura para a
    # volátil devolveria zero linha e o batimento carimbaria INDETERMINADO em
    # TODA rodada — um alerta permanente ensina a ignorar alertas.
    assert (simulacao["fechamento"]["endereco_releitura"]
            == simulacao["fechamento"]["idempotencia_estavel"])


def test_a_migration_de_escopo_destrava_os_tres_impedimentos(simulacao):
    """O SQL que torna o envelope gravável — lido, não suposto.

    Sem esta migration os três campos acima não resolvem nada: `v15_01:238` põe
    `CHECK (escopo = 'hierarchy')` e `20260907210000:1203-1205` grava o literal
    `'hierarchy'`, então um snapshot de `insights_pagina` era gravado com o
    escopo ERRADO, em silêncio — pior que uma recusa.
    """
    sql = (RAIZ / "supabase" / "migrations"
           / "20260908000000_meta_insights_escopo.sql").read_text(encoding="utf-8")
    # (a) escopo alargado, e a RPC passa a LER em vez de fixar.
    assert "CHECK (escopo IN ('hierarchy', 'insights_pagina', 'insights_fechamento'))" in sql
    assert "v_escopo             text := coalesce(nullif(p_snapshot->>'escopo', ''), 'hierarchy')" in sql
    assert "v_chave, v_escopo, 'ok'" in sql
    assert "v_chave, 'hierarchy', 'ok'" not in sql
    # (b) conta opcional SÓ no fechamento — CHECK condicional, não NULL geral.
    assert ("CHECK (ad_account_ativo_id IS NOT NULL OR escopo = 'insights_fechamento')"
            in sql)
    assert "ALTER COLUMN ad_account_ativo_id DROP NOT NULL" in sql
    assert "META_SNAPSHOT_SEM_CONTA" in sql
    # (c) completude exigida SÓ na hierarquia — e a marcação de ausência também,
    # senão a migration teria aberto um buraco maior do que fechou.
    assert "IF v_escopo = 'hierarchy' THEN" in sql
    assert "META_LEITURA_SEM_COMPLETUDE" in sql
    assert "IF v_completo AND v_escopo = 'hierarchy' THEN" in sql
    # Aditiva: nada de DROP de dado.
    assert not re.search(r"(?i)\bDROP\s+(TABLE|COLUMN|SCHEMA)\b", sql)
    assert not re.search(r"(?i)\b(DELETE\s+FROM|TRUNCATE)\b", sql)
    # E sem metacomando de psql: o arquivo tem de rodar igual por psql, pelo
    # Supabase CLI ou colado num console SQL.
    assert not re.search(r"(?m)^\s*\\[a-z]", sql)
    # O escopo que o fluxo produz é o escopo que a migration passou a aceitar.
    for escopo in (simulacao["escopo"], simulacao["fechamento"]["escopo"]):
        assert f"'{escopo}'" in sql, escopo


def test_sim_o_pedido_leva_o_grao_inteiro_e_nada_que_nao_foi_pedido(simulacao):
    p = simulacao["parametros"]
    assert p["level"] == "campaign"
    assert p["time_increment"] == "1"
    assert p["action_report_time"] == "impression"
    assert p["time_range"] == '{"since":"2026-09-05","until":"2026-09-05"}'
    assert "actions" in p["fields"] and "action_values" in p["fields"]
    # Sem janela pedida: nada de `action_attribution_windows` no fio, e o fato
    # carimba `default` — nunca uma janela nominal que ninguém solicitou.
    assert "action_attribution_windows" not in p
    assert "breakdowns" not in p
    assert simulacao["janela_do_fato"] == "default"
    assert simulacao["url_graph"].endswith("/act_1234567890/insights")
    assert simulacao["pedido_no_snapshot"]["fuso_da_conta"] == "America/Sao_Paulo"


def test_sim_lpv_ignora_viewcontent_e_ausencia_nao_vira_zero(simulacao):
    # Linha 1: LPV=4 e ViewContent=7. O valor correto é 4, nunca 11.
    assert simulacao["lpv"][0] == 4
    # Linha 2: action de LPV presente SEM valor medido => null, não 0.
    assert simulacao["lpv"][1] is None
    # `impressions: ''` é ausência; `clicks: '0'` é zero medido.
    assert simulacao["impressions"] == [1000, None]
    assert simulacao["clicks"] == [20, 0]
    # Unidades separadas até a linha.
    assert set(simulacao["medidas"]["actions"]) == {"count"}
    assert set(simulacao["medidas"]["action_values"]) == {"value"}
    assert simulacao["action_values_linhas"] == 1
    # Contagem e valor dividem a MESMA tabela, separadas por `medida`: a coluna
    # chegou na migration candidata do read model e o backend emite as duas
    # medidas do mesmo jeito.
    assert "trafego_meta_insight_action_value" not in simulacao["tabelas_de_linha"]
    # A chave da tabela filha e (fato, ordem), entao a numeracao recomeca a cada
    # FATO — e precisa ser continua DENTRO dele, atravessando contagem e valor.
    # Reiniciar nos valores faria cada linha de dinheiro sobrescrever uma linha
    # de contagem, e o total de eventos viraria o total em reais em silencio.
    por_fato = simulacao["action_ordens_por_fato"]
    assert por_fato, "nenhuma action persistida na simulacao"
    for fato, ordens in por_fato.items():
        assert ordens == list(range(len(ordens))), (fato, ordens)
        assert len(set(ordens)) == len(ordens), (fato, ordens)


def test_sim_janela_de_atribuicao_pedida_nao_e_achatada(simulacao):
    j = simulacao["janelas"]
    assert j["etiqueta"] == "1d_view+7d_click"
    assert j["no_fio"] == '["7d_click","1d_view"]'
    # Uma linha POR JANELA: ler só `value` colapsaria as duas num número cujo
    # significado ninguém recupera.
    assert j["expandidas"] == ["1d_view", "7d_click"]
    assert j["fato"] == "1d_view+7d_click"


def test_sim_paginacao_por_cursor_real_e_janela_truncada_incompleta(simulacao):
    # `paging.cursors.after` existe até na última página; quem decide é `next`.
    assert simulacao["tem_proxima"] is True and simulacao["cursor"] == "C1"
    assert simulacao["ultima_pagina"] is False
    assert "PAGINACAO_ACIMA_DO_TETO" in simulacao["truncada_motivo"]
    # Truncada NÃO avança marca d'água; completa avança até o fim da janela.
    assert simulacao["truncada_marca"] is None
    assert simulacao["marca_completa"] == "2026-09-05"


def test_sim_reler_um_dia_passado_gera_revisao_e_nao_gasto_duplicado(simulacao):
    """A identidade do fato inclui o instante da observação.

    Reler D-3 amanhã não soma gasto: produz outra REVISÃO do mesmo grão, e a
    projeção mais recente resolve qual vale.
    """
    assert simulacao["fato_ids"] != simulacao["fato_ids_revisao"]
    assert len(set(simulacao["fato_ids"])) == len(simulacao["fato_ids"])
    for fid in simulacao["fato_ids"] + simulacao["fato_ids_revisao"]:
        assert re.fullmatch(r"meta_insight_[a-f0-9]{64}", fid), fid


def test_sim_as_chaves_do_snapshot_respeitam_os_checks_do_banco(simulacao):
    assert re.fullmatch(r"meta_snapshot_[a-f0-9]{32}", simulacao["snapshot_hash"])
    assert re.fullmatch(r"meta_sync_[a-f0-9]{32}", simulacao["idempotencia"])
    assert re.fullmatch(r"meta_sync_[a-f0-9]{32}", simulacao["fechamento"]["idempotencia"])
    assert simulacao["escopo"] == "insights_pagina"
    assert simulacao["fechamento"]["escopo"] == "insights_fechamento"
    # A lacuna de action_values FECHOU: a coluna `medida` chegou na migration
    # candidata e o backend passou a emitir as duas medidas. Não há mais valor
    # monetário viajando sem destino, então nada a declarar aqui.
    assert not any("ACTION_VALUES_NAO_PERSISTIDOS" in p for p in simulacao["parcialidade"])


def test_sim_401_para_e_exige_acao_403_tambem_e_429_espera_a_proxima_rodada(simulacao):
    e = simulacao["erros"]
    for chave in ("e401", "e403", "e190"):
        assert e[chave]["erro_classe"] == "AUTENTICACAO", chave
        assert e[chave]["exige_acao_humana"] is True, chave
        assert e[chave]["retry_na_proxima_rodada"] is False, chave
    assert e["e429"]["erro_classe"] == "COTA"
    assert e["e429"]["retry_na_proxima_rodada"] is True
    assert e["e503"]["erro_classe"] == "INDISPONIVEL"
    assert e["eNada"]["erro_classe"] == "DESCONHECIDA"
    # A mensagem pública é rótulo, nunca o corpo bruto do erro (que pode
    # carregar token e cabeçalho).
    assert "texto bruto secreto" not in json.dumps(e["eNada"])
    assert e["eNada"]["erro_mensagem"].startswith("META_DESCONHECIDA")


def test_sim_o_recibo_fecha_a_execucao_sem_vazar_conta_nem_dinheiro(simulacao):
    f = simulacao["fechamento"]
    assert f["account_asset_id"] is None       # fechamento é da execução, não de uma conta
    assert f["contas"] == 2
    assert f["exige_acao_humana"] is True
    assert f["resultado"] == "parcial"
    # A conta que falhou não ganha marca d'água; a que leu tudo, ganha.
    assert None in f["marcas"] and "2026-09-05" in f["marcas"]
    assert "1234567890" not in f["texto"] and "9876543210" not in f["texto"]
    assert simulacao["persistencia_confirmada"] is True
    assert simulacao["rpc_recusada"] is True
    assert simulacao["lote_maior_que_um"] is True
    assert simulacao["reprocesso_acima_do_teto"] is True


def test_sim_saudavel_nunca_sai_de_autoatestado(simulacao):
    s = simulacao["saude"]
    assert s["bloqueado"] == "BLOQUEADO_AUTORIZACAO"
    assert s["sem_releitura"] == "INDETERMINADO"
    assert s["com_releitura"]["estado_saude"] == "SAUDAVEL"
    assert s["com_releitura"]["alerta"] is False
    assert s["com_releitura"]["persistencia_confirmada"] is True
    # O que vai para o alerta não carrega id cru nem valor financeiro.
    texto = json.dumps(s["com_releitura"])
    assert "1234567890" not in texto and "199.90" not in texto and "10.50" not in texto


def test_o_fluxo_n8n_e_o_backend_produzem_a_MESMA_identidade_de_fato(simulacao):
    """Os dois produtores escrevem na mesma tabela; divergir e gravar em dobro.

    O fluxo n8n e `persistencia.linhas_de_insights()` calculam o
    `meta_insight_daily_id` cada um do seu lado — um em JavaScript dentro de um
    Code node, o outro em Python. Se as duas listas de campos sairem de sincronia,
    o MESMO fato entra duas vezes com duas chaves diferentes, e a projecao
    `latest` passa a expor duas "revisoes correntes" do mesmo grao. Nenhum dos
    dois lados reclamaria: cada um continua internamente consistente.

    Este teste refaz a identidade pelo lado Python a partir do que o fluxo
    gravou, e exige o mesmo id.
    """
    import hashlib

    fatos = simulacao["fatos_persistidos"]
    assert fatos, "a simulacao nao produziu fato nenhum"
    for f in fatos:
        identidade = "|".join((
            f["provider"],
            f["conta_externa"],
            f["nivel"],
            f["objeto_externo"],
            f["periodo_inicio"],
            f["periodo_fim"],
            f["janela_atribuicao"],
            f["breakdown"],
            f["time_increment"],
            f["action_report_time"],
            f["account_timezone"] or "",
            f["observado_em"],
        ))
        esperado = "meta_insight_" + hashlib.sha256(identidade.encode("utf-8")).hexdigest()
        assert f["meta_insight_daily_id"] == esperado, (
            "o fluxo n8n e o backend divergiram na identidade do fato; "
            "veja n8n/gerar_flows_meta_ledger.py (JS_VALIDAR) e "
            "backend/app/trafego/meta/persistencia.py::linhas_de_insights"
        )


def test_o_grao_do_backend_esta_inteiro_na_linha_gravada_pelo_fluxo(simulacao):
    """Se um campo do grao some da linha, dois pedidos diferentes viram um so."""
    obrigatorios = ("time_increment", "action_report_time", "account_timezone",
                    "currency", "completo")
    for f in simulacao["fatos_persistidos"]:
        for campo in obrigatorios:
            assert campo in f, campo
        assert f["time_increment"], "time_increment vazio nao identifica grao"
        assert f["action_report_time"]
        assert isinstance(f["completo"], bool)
