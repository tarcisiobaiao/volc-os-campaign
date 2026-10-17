"""Monta o JSON do error workflow comum dos coletores canônicos (item 5).

Uso: python3 construir_error_workflow.py <saida.json> [--com-webhook-de-teste <path>]
O webhook de teste força dry-run (nunca escreve) e é removido depois dos testes.
A credencial Supabase é referenciada por id (a mesma dos coletores); nenhum segredo vai no JSON.
"""
import json, os, sys, uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SAIDA = Path(sys.argv[1])
WEBHOOK = sys.argv[sys.argv.index("--com-webhook-de-teste") + 1] if "--com-webhook-de-teste" in sys.argv else None
SUPA = {"supabaseApi": {"id": "3lSRuywq3fwQ3z3I", "name": "VOLC Oficial"}}
BASE = "https://database.agenciavolc.com.br/rest/v1"


def nid(nome):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"volc-coletores-error-v1:{nome}"))


def http(nome, pos, metodo, url, corpo=None, prefer="return=representation"):
    p = {"method": metodo, "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
         "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"},
                                                                  {"name": "Prefer", "value": prefer}]},
         "options": {"timeout": 30000}}
    if corpo is not None:
        p.update(sendBody=True, contentType="raw", rawContentType="application/json", body=corpo)
    return {"id": nid(nome), "name": nome, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": p, "credentials": SUPA, "onError": "continueRegularOutput", "alwaysOutputData": True}


def code(nome, pos, arquivo=None, js=None):
    return {"id": nid(nome), "name": nome, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"jsCode": js if js is not None else (AQUI / "codigo" / arquivo).read_text()}}


def se(nome, pos, valor):
    return {"id": nid(nome), "name": nome, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": pos,
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                          "conditions": [{"id": nid(nome + ":c"), "leftValue": "={{ $json.acao }}", "rightValue": valor,
                                                          "operator": {"type": "string", "operation": "equals"}}],
                                          "combinator": "and"}, "options": {}}}


LER_URL = ("={{ $json.fonte === 'google' ? '" + BASE + "/google_ads_collection_run?select=status,batches_written,started_at&idempotency_key=eq.' "
           "+ encodeURIComponent($json.run_key_google) : '" + BASE + "/joinads_collection_run?select=run_key,status,batches_written,receipt"
           "&workflow_id=eq.' + encodeURIComponent($json.workflow_id) + '&workflow_execution_id=eq.' + encodeURIComponent($json.falha_execution_id) }}")
nos = [
    {"id": nid("Error Trigger"), "name": "Error Trigger", "type": "n8n-nodes-base.errorTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
    code("Classificar e sanitizar", [240, 0], "error_classificar.js"),
    {"id": nid("Elegível?"), "name": "Elegível?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [460, 0],
     "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                   "conditions": [{"id": nid("Elegível?:c"), "leftValue": "={{ $json.elegivel }}", "rightValue": "",
                                                   "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                   "combinator": "and"}, "options": {}}},
    http("Ler run", [680, -100], "GET", LER_URL),
    code("Decidir", [900, 0], "error_decidir.js"),
    se("Google?", [1120, 0], "google_finish"),
    http("Finalizar run Google", [1340, -120], "POST", BASE + "/rpc/volc_finish_google_ads_run",
         "={{ JSON.stringify($json.google_documento) }}"),
    se("JoinAds?", [1340, 120], "joinads_patch"),
    http("Finalizar run JoinAds", [1560, 40], "PATCH",
         "={{ '" + BASE + "/joinads_collection_run?status=eq.running&run_key=eq.' + encodeURIComponent($json.joinads_patch.run_key) }}",
         "={{ JSON.stringify($json.joinads_patch.corpo) }}"),
    code("Recibo", [1800, 0], js=(
        "const d = $('Decidir').first().json;\n"
        "const r = $input.first().json ?? {};\n"
        "return [{json: {acao: d.acao, acao_planejada: d.acao_planejada, motivo: d.motivo, estagio: d.estagio, status_final: d.status_final,\n"
        "  fonte: d.fonte, teste: d.teste, run_lido: d.run_lido, registro: d.registro,\n"
        "  escrita: d.acao === 'nenhuma' ? null : (r.error ? {ok: false, erro: String(r.error.message ?? r.error).slice(0, 160)} : {ok: true})}}];\n")),
]
con = {
    "Error Trigger": {"main": [[{"node": "Classificar e sanitizar", "type": "main", "index": 0}]]},
    "Classificar e sanitizar": {"main": [[{"node": "Elegível?", "type": "main", "index": 0}]]},
    "Elegível?": {"main": [[{"node": "Ler run", "type": "main", "index": 0}], [{"node": "Decidir", "type": "main", "index": 0}]]},
    "Ler run": {"main": [[{"node": "Decidir", "type": "main", "index": 0}]]},
    "Decidir": {"main": [[{"node": "Google?", "type": "main", "index": 0}]]},
    "Google?": {"main": [[{"node": "Finalizar run Google", "type": "main", "index": 0}], [{"node": "JoinAds?", "type": "main", "index": 0}]]},
    "JoinAds?": {"main": [[{"node": "Finalizar run JoinAds", "type": "main", "index": 0}], [{"node": "Recibo", "type": "main", "index": 0}]]},
    "Finalizar run Google": {"main": [[{"node": "Recibo", "type": "main", "index": 0}]]},
    "Finalizar run JoinAds": {"main": [[{"node": "Recibo", "type": "main", "index": 0}]]},
}
if WEBHOOK:
    nos += [{"id": nid("Teste (dry-run)"), "name": "Teste (dry-run)", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 220], "webhookId": str(uuid.uuid5(uuid.NAMESPACE_URL, WEBHOOK)),
             "parameters": {"httpMethod": "POST", "path": WEBHOOK, "responseMode": "lastNode", "options": {}}},
            code("Embrulhar teste", [240, 220], js="return [{json: {teste: $json.body ?? {}}}];\n")]
    con["Teste (dry-run)"] = {"main": [[{"node": "Embrulhar teste", "type": "main", "index": 0}]]}
    con["Embrulhar teste"] = {"main": [[{"node": "Classificar e sanitizar", "type": "main", "index": 0}]]}
wf = {"name": "VOLC | Coletores canônicos | Error workflow v1", "nodes": nos, "connections": con,
      "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all",
                   "saveManualExecutions": True, "timezone": "America/Sao_Paulo"}}
os.umask(0o077)
SAIDA.write_text(json.dumps(wf, ensure_ascii=False, indent=1))
print(len(nos), "nós")
