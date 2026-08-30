"""
Transforma o flow ORIGINAL de mineração de KW (export n8n) num flow novo:
  Webhook IN (do nosso backend)  ->  [GOLD verbatim]  ->  Supabase OUT

- Mantém TODOS os nós "ouro" verbatim (Seed Optimizer, Keyword Planner loop,
  Gold Extractor, Final Classifier, DataForSEO, Mega Merger, Gold Miner,
  Funnel Prospector, Funnel Factory).
- Remove ClickUp + triggers + Geo Mapper (geo vem do webhook).
- SCRUB de segredos hardcoded -> expressões $env (nunca expõe valores).
- Liga a saída ao Supabase (pautador_keyword_clusters + entity_seed_queries +
  status da oportunidade), usando $env.SUPABASE_URL / $env.SUPABASE_SERVICE_ROLE_KEY.

Uso: python scripts/build_n8n_kw_webhook_flow.py /Users/mac/Downloads/KW.json
Saída: webgo/n8n/pautador_kw_mining_webhook.json
"""
from __future__ import annotations

import json
import os
import sys
import uuid

SRC = sys.argv[1] if len(sys.argv) > 1 else "/Users/mac/Downloads/KW.json"
WEBGO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(WEBGO, "n8n", "pautador_kw_mining_webhook.json")

# nós "ouro" mantidos verbatim
KEEP = {
    "⚙️ Config Global1", "🧠 AI Seed Optimizer1", "Gemini 2.5 Flash1",
    "Structured Output Parser1", "🌱 Seed Queue Builder1", "🔁 Loop Seeds1",
    "🔍 Keyword Planner API1", "⛏️ Gold Extractor1", "🔄 Mais Ouro?1",
    "🔄 Prep Next Loop1", "⏳ Sleep 15s", "🏆 Final Classifier1",
    "🪄 Prepare Validation Seeds", "🔮 Google Autocomplete2", "Extract Autocomplete2",
    "🧠 Related Keywords Labs2", "Extract Related KW2", "🔀 Merge All Sources2",
    "🔥 Mega Merger2", "Code in JavaScript6", "Google Gemini Chat Model3",
    "Think3", "Message a model in Perplexity", "VOLC Funnel Prospector v2",
    "🏭 FUNNEL FACTORY",
}

# Config Global: rewire de ClickUp -> webhook + scrub de segredos -> $env
CONFIG_REWIRE = {
    "nicho": "={{ $('Webhook').item.json.body.nicho }}",
    "geo_target": "={{ $('Webhook').item.json.body.geo_target }}",
    "país_geo": "={{ $('Webhook').item.json.body.country }}",
    "language_code": "={{ $('Webhook').item.json.body.language_code }}",
    "language_short": "={{ $('Webhook').item.json.body.language_short }}",
    "language_constant": "={{ $('Webhook').item.json.body.language_constant }}",
    "objective": "={{ $('Webhook').item.json.body.objective }}",
    "mcc_id": "={{ $env.GOOGLE_ADS_MCC_ID }}",
    "customer_id": "={{ $env.GOOGLE_ADS_CUSTOMER_ID }}",
    "developer_token": "={{ $env.GOOGLE_ADS_DEVELOPER_TOKEN }}",
}


def _nid() -> str:
    return str(uuid.uuid4())


def main() -> int:
    src = json.load(open(SRC, encoding="utf-8"))
    nodes = [n for n in src["nodes"] if n["name"] in KEEP]

    # --- scrub + rewire Config Global ---
    for n in nodes:
        if n["name"] == "⚙️ Config Global1":
            for a in n["parameters"]["assignments"]["assignments"]:
                if a["name"] in CONFIG_REWIRE:
                    a["value"] = CONFIG_REWIRE[a["name"]]
            # passa as chaves de linkagem adiante
            for extra in ("opportunity_id", "entity_id", "run_id"):
                n["parameters"]["assignments"]["assignments"].append({
                    "id": _nid(), "name": extra, "type": "string",
                    "value": "={{ $('Webhook').item.json.body." + extra + " }}",
                })
        # --- scrub DataForSEO Authorization hardcoded -> $env ---
        if n["name"] in ("🔮 Google Autocomplete2", "🧠 Related Keywords Labs2"):
            for h in n["parameters"].get("headerParameters", {}).get("parameters", []):
                if h.get("name") == "Authorization":
                    h["value"] = "={{ $env.DATAFORSEO_AUTH_HEADER }}"

    # --- novos nós: Webhook (entrada) + Supabase (saída) ---
    webhook = {
        "parameters": {"httpMethod": "POST", "path": "pautador-kw-mining",
                       "responseMode": "onReceived", "options": {}},
        "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [-3260, 480],
        "id": _nid(), "name": "Webhook", "webhookId": _nid(),
    }

    build_payload_code = r"""
// 📦 Monta o payload do Supabase a partir do resultado da mineração.
const wh = $('Webhook').first().json.body || {};
const gm = $('Code in JavaScript6').first().json || {};
let funis = [];
try {
  let o = $('VOLC Funnel Prospector v2').first().json.output;
  if (typeof o === 'string') o = JSON.parse(o.replace(/```json/g,'').replace(/```/g,'').trim());
  funis = (o && o.funis_sugeridos) || [];
} catch (e) {}
let factory = [];
try { factory = $('🏭 FUNNEL FACTORY').all().map(i => i.json); } catch (e) {}

const ads = gm.production_ads_queue || [];
const seo = gm.content_seo_queue || [];
const toQual = (v) => v >= 50000 ? 'very_high' : v >= 10000 ? 'high' : v >= 1000 ? 'medium' : 'low';

const cluster = {
  opportunity_id: wh.opportunity_id || null,
  run_id: wh.run_id || null,
  cluster_name: 'Cluster: ' + (wh.nicho || ''),
  main_keyword: wh.nicho || null,
  intent: 'informational',
  keywords: ads.slice(0, 25).map(k => ({
    keyword: k.keyword, volume: toQual(k.volume || 0),
    cpc_local: String(k.cpc ?? ''), competition: (k.competition || '').toLowerCase() || null,
    intent: 'informational'
  })),
  total_volume: ads.reduce((s, k) => s + (k.volume || 0), 0),
  raw_keywords: ads,
  production_ads_queue: ads,
  content_seo_queue: seo,
  funis_sugeridos: funis,
  factory_output: factory,
  summary: gm.summary || null,
  services_used: ['n8n:google_ads', 'n8n:dataforseo', 'n8n:gemini'],
  engine: 'n8n',
};

const seed_queries = ads.slice(0, 50).map(k => ({
  entity_id: wh.entity_id || null,
  opportunity_id: wh.opportunity_id || null,
  query: k.keyword, query_type: 'variation', intent: 'informational',
  source: 'n8n', score: k.volume || null,
}));

return [{ json: { cluster, seed_queries, opportunity_id: wh.opportunity_id, entity_id: wh.entity_id } }];
""".strip()

    build_payload = {
        "parameters": {"jsCode": build_payload_code},
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2400, 1184],
        "id": _nid(), "name": "📦 Build Supabase Payload",
    }

    def supa_http(name, pos, method, path_expr, body_expr, prefer):
        return {
            "parameters": {
                "method": method,
                "url": "={{ $env.SUPABASE_URL }}/rest/v1/" + path_expr,
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "apikey", "value": "={{ $env.SUPABASE_SERVICE_ROLE_KEY }}"},
                    {"name": "Authorization", "value": "=Bearer {{ $env.SUPABASE_SERVICE_ROLE_KEY }}"},
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Prefer", "value": prefer},
                ]},
                "sendBody": True, "specifyBody": "json", "jsonBody": body_expr,
                "options": {},
            },
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "id": _nid(), "name": name, "onError": "continueRegularOutput",
        }

    insert_cluster = supa_http(
        "⬆️ Supabase: cluster", [2640, 1080], "POST",
        "pautador_keyword_clusters", "={{ JSON.stringify($json.cluster) }}", "return=minimal",
    )
    insert_queries = supa_http(
        "⬆️ Supabase: seed queries", [2880, 1080], "POST",
        "pautador_entity_seed_queries", "={{ JSON.stringify($('📦 Build Supabase Payload').item.json.seed_queries) }}",
        "return=minimal",
    )
    patch_status = supa_http(
        "✅ Supabase: status mining", [3120, 1080], "PATCH",
        "pautador_entity_opportunities?id=eq.{{ $('📦 Build Supabase Payload').item.json.opportunity_id }}",
        '={{ JSON.stringify({ status: "mining", kanban_stage: "mining" }) }}', "return=minimal",
    )

    nodes += [webhook, build_payload, insert_cluster, insert_queries, patch_status]

    # --- connections: mantém as do ouro, troca entrada/saída ---
    new_conns = {}
    for src_name, conns in src["connections"].items():
        if src_name not in KEEP:
            continue
        kept = {}
        for ctype, groups in conns.items():
            new_groups = []
            for grp in groups:
                new_groups.append([c for c in (grp or []) if c["node"] in KEEP])
            kept[ctype] = new_groups
        new_conns[src_name] = kept

    # Webhook -> Config Global
    new_conns["Webhook"] = {"main": [[{"node": "⚙️ Config Global1", "type": "main", "index": 0}]]}
    # Funnel Factory -> Build Payload -> Supabase chain (substitui saída ClickUp)
    new_conns["🏭 FUNNEL FACTORY"] = {"main": [[{"node": "📦 Build Supabase Payload", "type": "main", "index": 0}]]}
    new_conns["📦 Build Supabase Payload"] = {"main": [[{"node": "⬆️ Supabase: cluster", "type": "main", "index": 0}]]}
    new_conns["⬆️ Supabase: cluster"] = {"main": [[{"node": "⬆️ Supabase: seed queries", "type": "main", "index": 0}]]}
    new_conns["⬆️ Supabase: seed queries"] = {"main": [[{"node": "✅ Supabase: status mining", "type": "main", "index": 0}]]}

    out = {
        "name": "Pautador Pro — KW Mining (Webhook → Supabase)",
        "nodes": nodes,
        "connections": new_conns,
        "settings": {"executionOrder": "v1"},
        "pinData": {},
        "meta": {"templateCredsSetupCompleted": False},
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    # sanity: nenhum segredo conhecido vazou
    blob = json.dumps(out, ensure_ascii=False)
    for needle in ("YZqd52", "Basic Y29", "8696453882", "2932743754"):
        assert needle not in blob, f"VAZOU segredo: {needle}"
    print(f"OK — {len(nodes)} nós | saída: {OUT}")
    print("secrets scrubbed:", "✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
