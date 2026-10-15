"""Recoleta da janela madura Meta (W15) — o segundo workflow do gerador Meta.

O D-1 lê cada dia uma vez. Com `action_report_time=impression`, a conversão de
um clique entra no dia da IMPRESSÃO quando chega, dias depois. A recoleta relê
`[hoje-1-N, hoje-2]` no fuso da conta e grava revisão nova do mesmo grão.

O que este arquivo prova, executando o JavaScript EXATO do workflow em `node`,
com relógio injetado e sem rede:

* a janela é `[hoje-1-N, hoje-2]` NO FUSO DA CONTA, e nunca inclui o D-1;
* N fora de 1..28, ausente ou torto RECUSA antes de qualquer pedido à Meta;
* um N torto no Config NÃO derruba o D-1 (ele nem lê o campo);
* job, modo e chave de fechamento da recoleta não colidem com os do D-1;
* os dois workflows carregam o MESMO código: o que muda é só o Config.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
D1 = RAIZ / "n8n" / "volc_meta_insights_dia_d1.json"
RECOLETA = RAIZ / "n8n" / "volc_meta_insights_dia_recoleta.json"


def _wf(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _cfg(wf: dict) -> dict[str, str]:
    no = next(n for n in wf["nodes"] if n["name"] == "Config")
    return {a["name"]: a["value"] for a in no["parameters"]["assignments"]["assignments"]}


def _codigos(wf: dict) -> dict[str, str]:
    return {n["name"]: n["parameters"]["jsCode"]
            for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code"}


# ── o artefato, em Python puro ──────────────────────────────────────────────

def test_os_dois_workflows_em_disco_sao_o_que_o_gerador_produz():
    p = subprocess.run(["python3", "n8n/gerar_flows_meta_ledger.py", "--check"],
                       cwd=RAIZ, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "2 workflow(s)" in p.stdout


def test_a_recoleta_e_o_mesmo_codigo_com_outro_config():
    """Um só código, dois papéis. Divergir aqui seria um segundo coletor."""
    d1, rec = _wf(D1), _wf(RECOLETA)
    assert _codigos(d1) == _codigos(rec)
    assert [n["name"] for n in d1["nodes"]] == [n["name"] for n in rec["nodes"]]
    assert d1["connections"] == rec["connections"]
    so_no_d1 = set(_cfg(d1)) - set(_cfg(rec))
    so_na_rec = set(_cfg(rec)) - set(_cfg(d1))
    assert so_no_d1 == set() and so_na_rec == {"DIAS_DE_RECOLETA"}
    diferentes = {k for k in _cfg(d1) if _cfg(d1)[k] != _cfg(rec)[k]}
    assert diferentes == {"JOB", "JANELA_MODO", "PASSOS"}


def test_a_recoleta_nasce_inativa_e_sem_credencial():
    rec = _wf(RECOLETA)
    assert rec["active"] is False
    volc = rec["meta"]["volc"]
    assert volc["artefato"] == "n8n/volc_meta_insights_dia_recoleta.json"
    assert volc["papel"] == "RECOLETA"
    assert volc["pronto_para_publicar"] is False
    assert volc["credencial"]["provisionada"] is False


def test_a_agenda_da_recoleta_nao_disputa_hora_com_nenhuma_coleta():
    cfg = _cfg(_wf(RECOLETA))
    no = next(n for n in _wf(RECOLETA)["nodes"]
              if n["type"] == "n8n-nodes-base.scheduleTrigger")
    cron = no["parameters"]["rule"]["interval"][0]["expression"]
    assert cron == "30 8 * * *" and cfg["PASSOS"] == "08"
    # Google D-1 06h, Meta D-1 07h, recoleta Google (W11) 07:15.
    assert cron.split()[1] not in {"6", "7"}
    assert cfg["JOB"] == "meta_insights_dia_recoleta"
    assert cfg["JANELA_MODO"] == "RECOLETA"
    assert cfg["DIAS_DE_RECOLETA"] == "7"
    assert cfg["DIAS_DE_REPROCESSO"] == "0"


def test_o_gate_de_agenda_conhece_a_recoleta_meta():
    texto = (RAIZ / "scripts" / "gate_agenda_unica_gads.py").read_text(encoding="utf-8")
    assert "n8n/volc_meta_insights_dia_recoleta.json" in texto
    p = subprocess.run(["python3", "scripts/gate_agenda_unica_gads.py"],
                       cwd=RAIZ, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-3000:]


# ── o JavaScript, executado de verdade e sem rede ───────────────────────────

_HARNESS = r"""
import fs from 'fs';
const { d1, rec } = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

// 2026-09-07T02:00Z = 23:00 do dia 6 em Sao_Paulo e 11:00 do dia 7 em Toquio.
let RELOGIO = new Date('2026-09-07T02:00:00.000Z');
const RealDate = Date;
globalThis.Date = class extends RealDate {
  constructor(...a) { if (a.length === 0) super(RELOGIO.getTime()); else super(...a); }
  static now() { return RELOGIO.getTime(); }
};

function rodar(code, nome, { entrada = [], nos = {} } = {}) {
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
  return fn($input, $, { id: 'wf' }, { id: 1 }, 0);
}

function erro(code, cfg) {
  try { rodar(code, 'Identidade da execucao', { nos: { Config: cfg, Agenda: {} } }); return null; }
  catch (e) { return String(e.message).split(':')[0]; }
}

const contas = [
  { cofre_ativo_id: 'meta_account_metaacct_aaaaaaaaaaaaaaaaaaaaaaaa',
    account_external_id: 'act_1234567890', timezone_name: 'America/Sao_Paulo',
    moeda: 'BRL', credential_ativo_id: 'meta_credential_keychain_local' },
  { cofre_ativo_id: 'meta_account_metaacct_bbbbbbbbbbbbbbbbbbbbbbbb',
    account_external_id: '9876543210', timezone_name: 'Asia/Tokyo',
    moeda: 'JPY', credential_ativo_id: 'meta_credential_keychain_local' },
];

function rodada(wf, cfg) {
  const ident = rodar(wf.code, 'Identidade da execucao', { nos: { Config: cfg, Agenda: {} } })[0].json;
  const sel = rodar(wf.code, 'Selecionar contas',
    { entrada: contas, nos: { Config: cfg, 'Identidade da execucao': ident } })[0].json;
  const janelas = {};
  for (const c of sel.contas) {
    janelas[c.fuso_da_conta] = { inicio: c.janela_inicio, fim: c.janela_fim,
                                 dias: c.dias_na_janela, hoje: c.hoje_na_conta };
  }
  const mapa = rodar(wf.code, 'Identidade VOLC por conta', {
    entrada: [{ ad_account_ativo_id: contas[0].cofre_ativo_id, external_id: '111',
                meta_campaign_id: 'volc-1' }],
    nos: { 'Selecionar contas': sel } }).map((i) => i.json);
  const ctx = mapa.find((m) => m.fuso_da_conta === 'America/Sao_Paulo');
  const pag = rodar(wf.code, 'Pagina: preparar pedido', { entrada: [ctx], nos: { Config: cfg } })[0].json;
  const norm = rodar(wf.code, 'Pagina: normalizar', { entrada: [{ ...pag, paging: {}, data: [{
    account_id: 'act_1234567890', campaign_id: '111', adset_id: '1111',
    date_start: pag.pedido.periodo_inicio, date_stop: pag.pedido.periodo_inicio,
    spend: '10.50', impressions: '1000', clicks: '20',
    actions: [{ action_type: 'landing_page_view', value: '4' }] }] }] })[0].json;
  const v = rodar(wf.code, 'Validar semanticamente', { entrada: [norm] })[0].json;
  const r = rodar(wf.code, 'Reconciliar lote',
    { entrada: [{ ok: true, repetido: false, run_id: 'r1', chave_origem: 'estavel' }],
      nos: { 'Validar semanticamente': v } })[0].json;
  const f = rodar(wf.code, 'Fechar execucao', { entrada: [{ ...r, motivo_incompleto: null }] })[0].json;
  return {
    ident: { job: ident.job, origem_janela: ident.origem_janela,
             execucao_chave: ident.execucao_chave, dias_de_recoleta: ident.dias_de_recoleta,
             janela_fim_offset: ident.janela_fim_offset, janela_dias: ident.janela_dias },
    janelas,
    pedido: pag.pedido,
    parametros: pag.parametros_graph,
    fechamento_estavel: f.snapshot.stable_idempotency_key,
    fechamento_window: f.snapshot.window,
    fechamento_execucao: f.snapshot.execucao,
  };
}

const out = {};
out.d1 = rodada(d1, d1.cfg);
out.rec = rodada(rec, rec.cfg);
out.rec_n1 = rodada(rec, { ...rec.cfg, DIAS_DE_RECOLETA: '1' }).janelas;
out.rec_n28 = rodada(rec, { ...rec.cfg, DIAS_DE_RECOLETA: '28' }).janelas;

out.erros_recoleta = {};
for (const n of ['0', '29', '-1', 'abc', '', ' ', '7.5', '07d', '100']) {
  out.erros_recoleta[JSON.stringify(n)] = erro(rec.code, { ...rec.cfg, DIAS_DE_RECOLETA: n });
}
const semCampo = { ...rec.cfg };
delete semCampo.DIAS_DE_RECOLETA;
out.erros_recoleta['ausente'] = erro(rec.code, semCampo);
out.erro_reprocesso_na_recoleta = erro(rec.code, { ...rec.cfg, DIAS_DE_REPROCESSO: '3' });
out.erro_modo = erro(rec.code, { ...rec.cfg, JANELA_MODO: 'D0' });

// Um N torto que vaze para o Config do D-1 NAO pode derrubar o D-1.
out.d1_com_recoleta_torta = rodada(d1, { ...d1.cfg, DIAS_DE_RECOLETA: 'abc' }).janelas;

// O mesmo dia de disparo, dois papeis: chaves de fechamento distintas.
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node ausente — a simulação offline do Code node exige o runtime")
    dados = {
        "d1": {"code": _codigos(_wf(D1)), "cfg": _cfg(_wf(D1))},
        "rec": {"code": _codigos(_wf(RECOLETA)), "cfg": _cfg(_wf(RECOLETA))},
    }
    d = tmp_path_factory.mktemp("sim_meta_recoleta")
    (d / "nodes.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    (d / "sim.mjs").write_text(_HARNESS, encoding="utf-8")
    p = subprocess.run(["node", str(d / "sim.mjs"), str(d / "nodes.json")],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-4000:]
    return json.loads(p.stdout)


def test_sim_a_janela_madura_e_hoje_menos_1_menos_n_ate_hoje_menos_2_no_fuso_da_conta(sim):
    """São Paulo: hoje na conta é 06/09 → D-1 é 05/09 → recoleta 7 é 29/08..04/09.
    Tóquio, no MESMO instante: hoje é 07/09 → recoleta 7 é 30/08..05/09."""
    j = sim["rec"]["janelas"]
    assert j["America/Sao_Paulo"] == {"inicio": "2026-08-29", "fim": "2026-09-04",
                                      "dias": 7, "hoje": "2026-09-06"}
    assert j["Asia/Tokyo"] == {"inicio": "2026-08-30", "fim": "2026-09-05",
                               "dias": 7, "hoje": "2026-09-07"}


def test_sim_a_recoleta_nunca_rele_o_d1(sim):
    d1, rec = sim["d1"]["janelas"], sim["rec"]["janelas"]
    for fuso in ("America/Sao_Paulo", "Asia/Tokyo"):
        assert d1[fuso]["inicio"] == d1[fuso]["fim"]          # D-1 é um dia só
        assert rec[fuso]["fim"] < d1[fuso]["inicio"]           # e fica fora da recoleta


def test_sim_os_extremos_de_n_dao_a_janela_certa(sim):
    assert sim["rec_n1"]["America/Sao_Paulo"]["inicio"] == "2026-09-04"
    assert sim["rec_n1"]["America/Sao_Paulo"]["fim"] == "2026-09-04"
    assert sim["rec_n28"]["America/Sao_Paulo"]["inicio"] == "2026-08-08"
    assert sim["rec_n28"]["America/Sao_Paulo"]["dias"] == 28


def test_sim_o_pedido_a_graph_cobre_exatamente_a_janela(sim):
    pedido = sim["rec"]["pedido"]
    assert pedido["periodo_inicio"] == "2026-08-29"
    assert pedido["periodo_fim"] == "2026-09-04"
    # Uma linha por dia: a recoleta não muda o grão do fato.
    assert sim["rec"]["parametros"]["time_increment"] == "1"
    assert sim["rec"]["parametros"]["level"] == "adset"
    assert json.loads(sim["rec"]["parametros"]["time_range"]) == {
        "since": "2026-08-29", "until": "2026-09-04"}


def test_sim_n_fora_do_contrato_recusa_antes_de_falar_com_a_meta(sim):
    for n, codigo in sim["erros_recoleta"].items():
        assert codigo == "DIAS_DE_RECOLETA_INVALIDO", (n, codigo)
    assert sim["erro_reprocesso_na_recoleta"] == "REPROCESSO_NAO_SE_APLICA_A_RECOLETA"
    assert sim["erro_modo"] == "JANELA_MODO_INVALIDO"


def test_sim_um_n_torto_nao_derruba_o_d1(sim):
    assert sim["d1_com_recoleta_torta"] == sim["d1"]["janelas"]


def test_sim_a_identidade_da_recoleta_nao_colide_com_a_do_d1(sim):
    d1, rec = sim["d1"], sim["rec"]
    assert d1["ident"]["job"] == "meta_insights_dia_d1"
    assert d1["ident"]["origem_janela"] == "D-1"
    assert d1["ident"]["dias_de_recoleta"] is None
    assert rec["ident"]["job"] == "meta_insights_dia_recoleta"
    assert rec["ident"]["origem_janela"] == "RECOLETA"
    assert rec["ident"]["dias_de_recoleta"] == 7
    assert rec["ident"]["execucao_chave"].startswith("meta_insights_dia_recoleta:RECOLETA:")
    assert d1["fechamento_estavel"] != rec["fechamento_estavel"]
    # O rótulo que a RPC grava em `cursor_final.window` separa os dois papéis —
    # é por ele que o deadman Meta acha o fechamento de cada um.
    assert d1["fechamento_window"].endswith(":D-1")
    assert rec["fechamento_window"].endswith(":RECOLETA")
