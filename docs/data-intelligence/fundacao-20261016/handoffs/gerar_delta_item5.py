"""Gera o delta de roadmap/curadoria do item 5 (coletores canônicos, 17–18/10/2026) no formato do
aplicar_curadoria_delta.py, com a guarda de sha de cada campo calculada sobre os arquivos atuais da branch.

Uso (raiz do repositório): python3 gerar_delta_item5.py <fatos.json> <saida.json>
`fatos.json` traz só o que depende da prova final (canários de termos e Google D-1, replay final, SHA).
Nada vira done: o aceite de P06-T10 e P10-T28 exige 7 dias de leitura e decisões que ainda não existem.
"""
import hashlib
import json
import sys

RP, CP = "volc-os-workbook/ROADMAP-VIVO.json", "docs/volc-os-graph/curadoria-operacional.json"
F = json.load(open(sys.argv[1]))
PREF = "· 18/10/2026 · lab/data-foundation-20261016 (local, sem push, não integrado; produção n8n alterada com autorização do dono de 17/10 10:49): "
REC = "docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/VEREDITO-ITEM5.md"


def sha(v):
    t = "" if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return hashlib.sha256(t.encode()).hexdigest()


r = json.load(open(RP))
T = {t["id"]: t for i in r["initiatives"] for t in i["tasks"]}
c = json.load(open(CP))
N = {x["id"]: (s, x) for s in ("capabilities", "concepts", "documents") for x in c[s]}

P06_T10_PROOF = PREF + (
    "os três coletores Google canônicos (D0 Ps9y…, D-1 7yxs…, termos TFlm…) rodam a versão do contrato item5-20261017 "
    "(collector_version 2): sem linha de métrica na GAQL nada é fabricado (metrics = {} e attributes.metric_row_status = "
    "'metric_row_absent'); zero do proto3 em linha presente segue zero medido; a GAQL pede customer.currency_code e a "
    "observação grava a moeda devolvida pela conta com currency_status 'observed' e currency_source "
    "'gaql:customer.currency_code' (sem BRL fixo). Provas reais relidas no Supabase oficial (read-only): "
    f"{F['prova_google']}. Testes herméticos sobre o mesmo código: 31 (test_item5_contrato_coletores.py e "
    "test_item5_google_d1_implantavel.py). O histórico antigo não foi reescrito: as linhas v1 seguem com zero sintetizado e o "
    "adaptador do lab as marca missing. Replay estrito com as observações novas: " + F["replay"] + f". Recibo: {REC}.")
P06_T10_GAPS = PREF + (
    "falta o critério de 7 dias: dq_zero_sintetizado = 0% 'sem linha' em leitura read-only diária de "
    f"{F['inicio_7d']} em diante (plano no recibo); leitores existentes (economia wip, v17_04, front) ainda não tratam as linhas "
    "antigas pelo veredito do adaptador; os relatórios legados de Google Ads seguem ativos em paralelo (P06-T11).")
P10_T28_PROOF = PREF + (
    "error workflow comum fvqy… (idempotente, mensagens sanitizadas, conta pseudonimizada, classifica falha antes do primeiro "
    "lote, parcial e depois da gravação, só finaliza run ainda running e nunca repete escrita incerta, sem errorWorkflow "
    "próprio para não entrar em loop) ligado aos cinco coletores canônicos e ativo; testado por payloads sintéticos em dry-run "
    "e pelos testes test_error_*; nenhum erro real disparado desde a implantação. Reaper 4V7w… ativo SÓ EM SHADOW (cron 41 * * * *): "
    f"{F['reaper']}; o status de run do ledger não aceita 'abandoned' e a transição exige migration (não autorizada), então os 3 "
    f"órfãos de termos de 15/10 seguem running, intactos. Recibo: {REC}.")
P10_T28_GAPS = PREF + (
    "migration para o estado 'abandoned' (ou RPC oficial equivalente) antes de o reaper sair do shadow e fechar os 3 órfãos; "
    "falha induzida numa cópia inativa de coletor não foi feita (a API pública do n8n não executa cópia inativa); dead letter "
    "persistida não existe; canal de alerta por decidir; dq_runs_orfaos = 0 por 7 dias depende do fechamento dos órfãos.")
RISCO_ZERO = PREF + "o zero sintetizado parou na origem para observações novas dos três coletores Google; o risco segue aberto até 7 dias de dq_zero_sintetizado = 0% e enquanto leitores consumirem as linhas antigas sem o adaptador."
RISCO_REAPER = PREF + "error workflow comum ligado aos cinco canônicos; reaper só em shadow por falta do estado 'abandoned' no schema; os 3 órfãos seguem running."
JOINADS = PREF + "JoinAds intradiário e D-1 (collector_version 5) gravam receita em micros por decimal exato half-even, fail-closed, com a representação recebida em attributes.revenue_original; moeda USD por atestação do dono (currency_status 'attested', currency_source 'owner_attestation'), sem conversão no ledger porque a cotação do VOLC (5,25) está parada desde 18/02/2026 (conversion.status = 'nao_convertido')."

ops = [
    ("P06-T10", "proof", P06_T10_PROOF), ("P06-T10", "gaps", P06_T10_GAPS), ("P06-T10", "status", "partial"),
    ("P06-T10", "links", ["docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/VEREDITO-ITEM5.md",
                          "tests/data-intelligence/fundacao/test_item5_contrato_coletores.py",
                          "tests/data-intelligence/fundacao/test_item5_google_d1_implantavel.py"]),
    ("P10-T28", "proof", P10_T28_PROOF), ("P10-T28", "gaps", P10_T28_GAPS), ("P10-T28", "status", "partial"),
    ("P10-T28", "links", ["docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/VEREDITO-ITEM5.md"]),
]
updates = [{"task_id": t, "campo": k, "valor": v, "base_sha256_campo_anterior": sha(T[t].get(k))} for t, k, v in ops if k != "links"]
updates += [{"task_id": t, "campo": k, "valor": v} for t, k, v in ops if k == "links"]
ev = []
for nid, val in (("risk:google_ads_zero_sintetizado", RISCO_ZERO), ("risk:coletores_canonicos_sem_reaper", RISCO_REAPER),
                 ("concept:joinads_collection_ledger", JOINADS)):
    s, x = N[nid]
    ev.append({"secao": s, "id": nid, "campo": "evidence", "valor": val, "base_sha256_campo_anterior": sha(x.get("evidence"))})

delta = {
    "esquema": "volc-dil.curadoria-delta.v2", "gerado_em": F["gerado_em"], "branch": "lab/data-foundation-20261016",
    "head": F["head"], "aviso": "Aplicado só nesta branch local (sem push, não integrado). Atualidade do grafo vale só para ela.",
    "roadmap_updates": updates, "roadmap_new_tasks": [], "roadmap_initiative_updates": [],
    "curadoria_updates": {"meta": {"campo": "meta.curadoria_atualizada_em", "valor": F["gerado_em"]},
                          "mudancas_de_estado": [], "evidence_appends": ev,
                          "novos_nos": {"concepts": [], "documents": []}, "novas_arestas": []},
}
json.dump(delta, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
print(json.dumps({"updates": len(updates), "evidence": len(ev)}))
