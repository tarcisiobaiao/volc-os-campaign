"""Constrói, a partir dos exports de rollback, as versões novas dos cinco coletores canônicos (item 5).

Uso: python3 construir_item5.py <dir_rollback> <dir_saida> [<id_error_workflow>]
Cada troca de texto casa exatamente uma vez (senão aborta). Não altera cron, timezone, cadência, credenciais
nem nós de trigger. Grava o JSON novo de cada workflow (0600, fora do Git) e o código JoinAds resultante em
codigo/joinads_normaliza_coleta.js (versionado; não contém segredo).
"""
import copy, glob, json, os, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ROLL, SAIDA = Path(sys.argv[1]), Path(sys.argv[2])
ERRWF = sys.argv[3] if len(sys.argv) > 3 else None
os.umask(0o077)
SAIDA.mkdir(parents=True, exist_ok=True)


def carregar(chave):
    (f,) = glob.glob(str(ROLL / f"{chave}__*.json"))
    return json.load(open(f))


def no(w, nome):
    (n,) = [x for x in w["nodes"] if x["name"] == nome]
    return n


def troca(texto, velho, novo, onde):
    if texto.count(velho) != 1:
        sys.exit(f"{onde}: trecho casou {texto.count(velho)} vezes: {velho[:70]!r}")
    return texto.replace(velho, novo)


def gaql(n, onde, velho, novo):
    p = n["parameters"]["bodyParameters"]["parameters"][0]
    p["value"] = troca(p["value"], velho, novo, onde)


def settings(w):
    s = {k: v for k, v in (w.get("settings") or {}).items()
         if k in ("executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution", "saveManualExecutions",
                  "saveExecutionProgress", "executionTimeout", "errorWorkflow", "timezone", "callerPolicy")}
    if ERRWF:
        s["errorWorkflow"] = ERRWF
    return s


def corpo(w):
    return {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"], "settings": settings(w)}


saidas = {}
# ------------------------------------------------------------------ Google campanha-dia (D0 e D-1)
TPL = (AQUI / "codigo" / "google_campaign_day.js").read_text()
for chave, nomes in (
    ("google_d0", dict(campaigns="Google Ads - Get Campaigns1", goals="Google Ads - Get Conversion Goals",
                       budgets="Google Ads - Get Campaign Budget", metrics="Google Ads - Get metrics1",
                       split="Split Out2", fields="Edit Fields2", code="Code")),
    ("google_d1", dict(campaigns="Google Ads - Get Campaigns", goals="Google Ads - Get Conversion Goals1",
                       budgets="Google Ads - Get Campaign Budget2", metrics="Google Ads - Get metrics",
                       split="Split Out", fields="Edit Fields", code="Code15")),
):
    w = copy.deepcopy(carregar(chave))
    code = nomes.pop("code")
    no(w, code)["parameters"]["jsCode"] = TPL.replace("__NOMES__", json.dumps(nomes, ensure_ascii=False))
    gaql(no(w, nomes["campaigns"]), f"{chave} GAQL campanhas", "SELECT\n  campaign.id,", "SELECT\n  customer.currency_code,\n  campaign.id,")
    gaql(no(w, nomes["metrics"]), f"{chave} GAQL métricas", "campaign.id, \n  campaign.name,", "customer.currency_code,\n  campaign.id, \n  campaign.name,")
    ing = no(w, "Supabase | Ingestão canônica shadow")["parameters"]
    b = ing["jsonBody"]
    b = troca(b, "collector_version: 1,", "collector_version: 2,", f"{chave} ingest versão")
    b = troca(b, "currency_code: 'BRL',", "currency_code: $json.currency_code,", f"{chave} ingest moeda")
    b = troca(b, "custom_goal: $json.custom_goal\n        }",
              "custom_goal: $json.custom_goal,\n          metric_row_status: $json.metric_row_status,\n"
              "          currency_status: $json.currency_status,\n          currency_source: $json.currency_source,\n"
              "          contract: 'item5-20261017'\n        }", f"{chave} ingest atributos")
    ing["jsonBody"] = b
    fin = no(w, "Supabase | Finalizar run")["parameters"]
    fin["jsonBody"] = troca(fin["jsonBody"], "collector_version: 1,", "collector_version: 2,", f"{chave} finish versão")
    saidas[chave] = w

# ------------------------------------------------------------------ Google termos e keywords
w = copy.deepcopy(carregar("google_termos"))
no(w, "Code | Normalizar termos e keywords")["parameters"]["jsCode"] = (AQUI / "codigo" / "google_termos.js").read_text()
for nome, velho, novo in (("Supabase | Ingestão termos e keywords", "collector_version: 1,", "collector_version: 2,"),
                          ("Supabase | Finalizar run", "collector_version:1,", "collector_version:2,")):
    p = no(w, nome)["parameters"]
    p["jsonBody"] = troca(p["jsonBody"], velho, novo, f"termos {nome}")
saidas["google_termos"] = w

# ------------------------------------------------------------------ JoinAds (intradiário e D-1: mesmo normalizador)
QUANT = r'''
// [item 5] Dinheiro em micros por aritmética decimal exata (BigInt), arredondamento half-even.
// Nunca usa float binário para normalizar. Fail-closed: não numérico, NaN/infinito, negativo,
// precisão excessiva (mais de 34 dígitos significativos ou escala além de 40) e overflow
// (acima de 1e12 unidades) rejeitam a linha. A representação recebida fica em attributes.revenue_original.
const MICROS_MAX = 10n ** 18n;
function quantizeMicros(value) {
  if (value === null || value === undefined || value === '') return {ok: true, text: null, original: null};
  let s;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return {ok: false, reason: 'nao_finito'};
    s = String(value);
  } else if (typeof value === 'string') {
    s = value.trim().replace(/\s/g, '');
  } else {
    return {ok: false, reason: 'tipo_invalido'};
  }
  const original = s;
  if (s.includes(',') && !s.includes('.')) s = s.replace(',', '.');
  const m = s.match(/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/) || s.match(/^([+-]?)()\.(\d+)(?:[eE]([+-]?\d+))?$/);
  if (!m) return {ok: false, reason: /nan|inf/i.test(s) ? 'nao_finito' : 'nao_numerico'};
  const frac = m[3] || '';
  const digits = ((m[2] || '0') + frac).replace(/^0+(?=\d)/, '');
  const scale = frac.length - Number(m[4] || 0);
  if (digits.replace(/^0+/, '').length > 34 || Math.abs(scale) > 40) return {ok: false, reason: 'precisao_excessiva'};
  if (m[1] === '-' && /[1-9]/.test(digits)) return {ok: false, reason: 'negativo'};
  const n = BigInt(digits);
  const shift = 6 - scale;
  let micros;
  if (shift >= 0) {
    micros = n * (10n ** BigInt(shift));
  } else {
    const d = 10n ** BigInt(-shift);
    const q = n / d;
    const twice = 2n * (n % d);
    micros = (twice > d || (twice === d && q % 2n === 1n)) ? q + 1n : q;
  }
  if (micros > MICROS_MAX) return {ok: false, reason: 'overflow'};
  return {ok: true, text: `${micros / 1000000n}.${(micros % 1000000n).toString().padStart(6, '0')}`, original};
}

function currencyFromRow(row) {
  const c = row?.currency ?? row?.currency_code ?? row?.moeda;
  return typeof c === 'string' && /^[A-Z]{3}$/.test(c.trim()) ? c.trim() : null;
}

function contractAttributes(row, qGross, qClient) {
  // Moeda: a API não declara moeda. Vale a atestação operacional do dono (17/10/2026: earnings bruto da
  // JoinAds é USD), registrada como tal — não é prova técnica. Conversão para BRL NÃO acontece no ledger:
  // a cotação configurada no VOLC está congelada desde 18/02/2026 e não pode ser provada vigente; a conversão
  // única fica para a camada de leitura, com taxa, fonte e vigência explícitas.
  const rowCurrency = currencyFromRow(row);
  const attrs = rowCurrency
    ? {currency_status: 'observed', currency_source: 'joinads_api:row', currency_original: rowCurrency}
    : {currency_status: 'attested', currency_source: 'owner_attestation', currency_original: 'USD',
       currency_attestation_ref: 'dono 2026-10-17T10:51Z; docs/SPEC-ARBITRAGEM.md:10'};
  if (qGross.original !== null || qClient.original !== null) {
    attrs.revenue_quantization = 'decimal_half_even_micros';
    attrs.revenue_original = {revenue_gross: qGross.original, revenue_client: qClient.original};
    attrs.conversion = {status: 'nao_convertido', motivo: 'cotacao_vigente_nao_provada', currency_converted: 'BRL',
      revenue_converted: null, taxa: null, fonte_taxa: null, vigencia: null};
  }
  return attrs;
}
'''
w_d1, w_it = copy.deepcopy(carregar("joinads_d1")), copy.deepcopy(carregar("joinads_intraday"))
orig = no(w_d1, "Normaliza coleta")["parameters"]["jsCode"]
assert orig == no(w_it, "Normaliza coleta")["parameters"]["jsCode"], "normalizadores divergem entre intradiário e D-1"
js = orig
js = troca(js, "function integer(value) {\n  const n = numeric(value);\n  return n === null ? null : Math.round(n);\n}\n",
           "function integer(value) {\n  const n = numeric(value);\n  return n === null ? null : Math.round(n);\n}\n" + QUANT, "joinads quantizador")
js = troca(js, "function baseObservation(endpoint, grain, batchKey, row, day, index) {\n",
           "function baseObservation(endpoint, grain, batchKey, row, day, index) {\n"
           "  const qGross = quantizeMicros(row.revenue ?? row.earnings ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE);\n"
           "  const qClient = quantizeMicros(row.revenue_client ?? row.earnings_client);\n"
           "  for (const [nome, q] of [['revenue_gross', qGross], ['revenue_client', qClient]]) {\n"
           "    if (!q.ok) throw new Error(`revenue_invalid:${nome}:${q.reason}`);\n"
           "  }\n", "joinads base quantiza")
js = troca(js, "    currency_code: cfg.CURRENCY || 'USD',\n", "    currency_code: currencyFromRow(row) || cfg.CURRENCY || 'USD',\n", "joinads moeda")
js = troca(js, "    revenue_gross: numeric(row.revenue ?? row.earnings ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE),\n"
               "    revenue_client: numeric(row.revenue_client ?? row.earnings_client),\n",
           "    revenue_gross: qGross.text,\n    revenue_client: qClient.text,\n", "joinads receita")
js = troca(js, "    attributes: {},\n    data_status: 'observed',\n",
           "    attributes: contractAttributes(row, qGross, qClient),\n    data_status: 'observed',\n", "joinads atributos")
js = troca(js, "    obs.attributes = {source_status: row.status ?? null};\n",
           "    obs.attributes = {...obs.attributes, source_status: row.status ?? null};\n", "joinads pageviews atributos")
js = troca(js, "  obs.attributes = {message: String(row.message ?? '').slice(0, 500) || null};\n",
           "  obs.attributes = {...obs.attributes, message: String(row.message ?? '').slice(0, 500) || null};\n", "joinads policies atributos")
js = troca(js, "    receipt: {phase: 'collecting', endpoint_contract: 'joinads-v2'},\n",
           "    receipt: {phase: 'collecting', endpoint_contract: 'joinads-v2', contract: 'item5-20261017'},\n", "joinads receipt")
(AQUI / "codigo" / "joinads_normaliza_coleta.js").write_text(js)
for chave, w in (("joinads_d1", w_d1), ("joinads_intraday", w_it)):
    no(w, "Normaliza coleta")["parameters"]["jsCode"] = js
    cfg = no(w, "Config")["parameters"]["assignments"]["assignments"]
    (v,) = [a for a in cfg if a["name"] == "COLLECTOR_VERSION"]
    assert v["value"] == 4, (chave, v["value"])
    v["value"] = 5
    saidas[chave] = w

for chave, w in saidas.items():
    p = SAIDA / f"{chave}.json"
    p.write_text(json.dumps(corpo(w), ensure_ascii=False, indent=1))
    os.chmod(p, 0o600)
print(json.dumps({k: {"nodes": len(w["nodes"]), "errorWorkflow": settings(w).get("errorWorkflow")} for k, w in saidas.items()}))
