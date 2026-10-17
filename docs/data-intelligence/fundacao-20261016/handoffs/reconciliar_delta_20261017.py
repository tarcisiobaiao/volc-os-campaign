"""Gera o delta reconciliado (rodada autorizada de 17/10, item 2) a partir de CURADORIA-DELTA-20261016.json.

Reconciliação com a frente de medição (origin/fix/measurement-control-plane-20261016 @ db65a78a), que já
atualizou P06-T07.proof, P08-T01.proof, P08-T07.proof, cap_behavior.evidence e
concept:tracking_control_plane.evidence. Regras:

1. O texto daquela frente NÃO é sobrescrito: a base é o arquivo de db65a78a nesses 5 campos (o integrador os
   importa idênticos, em commit próprio, antes de aplicar); as 4 operações deste delta que tocam esses campos
   continuam sendo acréscimos e têm a guarda (`base_sha256_campo_anterior`) recalculada sobre a base nova —
   explícito em `reconciliacao.guardas_recalculadas`; nenhuma outra guarda muda.
2. Frases do delta que a v3.1 ou a rodada de 17/10 tornaram falsas ganham uma nota datada entre colchetes
   ("[reconciliado em 17/10: …]") em vez de reescrita silenciosa; cada troca casa exatamente uma vez.
3. P08-T12 sai do delta: a deduplicação por segundo foi corrigida em produção pela frente de medição
   (event_seq, migration 20261016155958) e o item 7 não é refeito; o resíduo (corte por .slice no volc-ingest,
   R2-G19/H2, ainda na linha 51 em db65a78a) fica no gaps de P08-T07.
4. P14-T11 passa de todo a partial (exportação e replay executados uma vez; nada vira done).
5. Novo nó doc:rodada-autorizada-20261017 (recibos desta rodada).
Uso: python3 reconciliar_delta_20261017.py  (da raiz do repositório)
"""
import copy
import hashlib
import json
import subprocess
import sys

ORIG = "docs/data-intelligence/fundacao-20261016/handoffs/CURADORIA-DELTA-20261016.json"
SAIDA = "docs/data-intelligence/fundacao-20261016/handoffs/CURADORIA-DELTA-20261017-RECONCILIADO.json"
REF_MED = "db65a78ae081557773d5c9fdb157cfa6a2bb189a"
RP, CP = "volc-os-workbook/ROADMAP-VIVO.json", "docs/volc-os-graph/curadoria-operacional.json"
R17 = "docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/RECIBO-RODADA-AUTORIZADA-20261017.md"


def sha_campo(v):
    t = "" if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def show(ref, f):
    return json.loads(subprocess.run(["git", "show", f"{ref}:{f}"], capture_output=True, text=True, check=True).stdout)


d = json.load(open(ORIG))
novo = copy.deepcopy(d)
log = []


def troca(obj, chave, velho, novo_txt, onde):
    s = obj[chave]
    n = s.count(velho)
    if n != 1:
        sys.exit(f"{onde}: trecho casou {n} vezes: {velho[:60]!r}")
    obj[chave] = s.replace(velho, novo_txt)
    log.append({"onde": onde, "antes_sha256": sha_campo(s), "depois_sha256": sha_campo(obj[chave])})


def ru(task, campo):
    xs = [u for u in novo["roadmap_updates"] if u["task_id"] == task and u["campo"] == campo]
    assert len(xs) == 1, (task, campo)
    return xs[0]


def nt(task):
    xs = [n["task"] for n in novo["roadmap_new_tasks"] if n["task"]["id"] == task]
    assert len(xs) == 1, task
    return xs[0]


cu = novo["curadoria_updates"]


def ce(i):
    xs = [e for e in cu["evidence_appends"] if e["id"] == i]
    assert len(xs) == 1, i
    return xs[0]


def nn(i):
    xs = [n for s in ("concepts", "documents") for n in cu["novos_nos"][s] if n["id"] == i]
    assert len(xs) == 1, i
    return xs[0]


V31 = "no Sensor v3.1 (GTM v36), 0 de 13 sessões pagas com utm.campaign em 16/10 13:05–22:57"
REC = "receipts/rodada-autorizada-20261017"

# ---------------------------------------------------------------- roadmap_updates
troca(ru("P06-T03", "latest_evidence"), "valor", "Replay real exige snapshot autorizado (P14-T11). Segue partial.",
      "Replay real exige snapshot autorizado (P14-T11). [Reconciliado em 17/10: snapshot read-only exportado e replay "
      "executado (P14-T11); recomputada das linhas, a razão kv/earnings ficou 0,968–1,000 em 08–16/10, mas o adaptador "
      f"estrito recusa o earnings com mais de 6 casas decimais (a fonte traz até 17) e o denominador fica indisponível em 5 dos 9 dias; {REC}.] Segue partial.",
      "RU P06-T03.latest_evidence")
troca(ru("P06-T07", "proof"), "valor", "(leitura L6 da GTM API pendente). Nada foi publicado. Segue partial.",
      "(leitura L6 da GTM API pendente). Nada foi publicado. [Reconciliado em 17/10: a evidência da v36 registrada neste "
      "campo pela frente de medição (db65a78a) foi preservada. A leitura L6 read-only confirmou a v36 live, sensor e "
      f"wrapper com sha256 iguais ao repositório em db65a78a e o mesmo filtro de PII; {V31}. No container v35 e v36 só o "
      "WEBS Wrapper chama setTargeting, e ele descarta valores com 10 ou mais dígitos: o caminho do id numérico até a "
      "JoinAds fica inferido como externo ao GTM.] Segue partial.", "RU P06-T07.proof")
troca(ru("P06-T07", "gaps"), "valor", "as versões v34/v35 do container não estão versionadas em main;",
      "as versões v34/v35 do container não estão versionadas em main [reconciliado em 17/10: a v35 (Sensor v3.0) é "
      "igual ao repositório em 128b93ae, hoje só no main local, e a v36 live é igual a db65a78a, fora do main];",
      "RU P06-T07.gaps")
troca(ru("P08-T07", "proof"), "valor", "Nenhum evento novo foi implantado. Segue partial.",
      "Nenhum evento novo foi implantado. [Reconciliado em 17/10: a evidência v3.1 da frente de medição neste campo foi "
      "preservada; em produção o índice passou a raw_events_dedup(sid, pid, event_name, ts_sec, event_seq), lido no "
      "catálogo em 17/10; o versionamento citado foi superado (v3.0 em 128b93ae, v3.1 em db65a78a, igual ao live); "
      f"{V31}.] Segue partial.", "RU P08-T07.proof")
g = ru("P08-T07", "gaps")
troca(g, "valor", "o índice único por segundo colapsa eventos legítimos de mesmo nome (P08-T12); ",
      "[reconciliado em 17/10: a deduplicação por segundo foi corrigida pela frente de medição com event_seq e não é "
      "reavaliada aqui]; ", "RU P08-T07.gaps (P08-T12)")
troca(g, "valor", "o hash da Edge Function em produção não foi conferido com o repositório (leitura L13 pendente); ",
      "[17/10: o hash do volc-ingest no host é igual ao repositório em db65a78a, leitura L13]; ", "RU P08-T07.gaps (L13)")
troca(g, "valor", "(index.ts linha 51 em 918e9571)", "(index.ts linha 51 em 918e9571, e ainda na linha 51 em db65a78a)",
      "RU P08-T07.gaps (slice)")
troca(ru("P09-T09", "proof"), "valor", "está pronto e não foi executado com dado real.",
      "está pronto e não foi executado com dado real [reconciliado em 17/10: executado uma vez sobre snapshot read-only "
      "pseudonimizado (P14-T11), 36 cortes horários; nenhuma política saiu de 'insuficiente' e a anti-baseline null→0 "
      "teve 180 de 180 propostas bloqueadas pelo kernel].", "RU P09-T09.proof")
g = ru("P09-T09", "gaps")
troca(g, "valor", "replay real bloqueado por P14-T11;", "replay real executado uma vez em 17/10 (P14-T11), sem dia maduro;",
      "RU P09-T09.gaps (P14-T11)")
troca(g, "valor", "e o replay real só produziria 'insuficiente'", "e o replay real só produziu 'insuficiente' (confirmado em 17/10)",
      "RU P09-T09.gaps (insuficiente)")
troca(ru("P09-T11", "gaps"), "valor", "replay com dado real bloqueado (P14-T11);",
      "replay com dado real degenerado (P14-T11, 17/10: uma campanha ativa, nada a realocar);", "RU P09-T11.gaps")
troca(ru("P14-T02", "latest_evidence"), "valor",
      "foi negada pela permissão da sessão em 16/10: nada está 'testado em replay' nem 'rodando em shadow'. Segue partial.",
      "foi negada pela permissão da sessão em 16/10: nada está 'testado em replay' nem 'rodando em shadow' [reconciliado "
      "em 17/10: exportada na rodada autorizada; adaptador e replay passaram a 'testado em replay' sobre 3 dias de custo "
      "e 9 de receita, sem nenhuma decisão madura; nada roda em shadow]. Segue partial.", "RU P14-T02.latest_evidence")

# ---------------------------------------------------------------- roadmap_new_tasks
troca(nt("P06-T10"), "proof", "e o replay real só produz 'insuficiente' (R2-G22, test_shadow_real.py).",
      "e o replay real só produz 'insuficiente' (R2-G22, test_shadow_real.py) [confirmado no replay real de 17/10: 140 de "
      "175 linhas campaign_day são zero sem linha de métrica, todas de 4 campanhas com status PAUSED; a campanha ativa tem "
      "linha de métrica em todas as leituras].", "NT P06-T10.proof")
troca(nt("P06-T11"), "gaps",
      "Leitura de produção pendente: estado ativo e cron reais dos fluxos (API do n8n, filtrando credenciais na origem) e "
      "registro de execuções (leituras L7 e L8 do inventário); nenhuma foi feita.",
      "Leitura de produção pendente: estado ativo e cron reais dos fluxos (API do n8n, filtrando credenciais na origem) e "
      "registro de execuções (leituras L7 e L8 do inventário); nenhuma foi feita. [Reconciliado em 17/10: L7/L8 feitas, só "
      "metadados: os cinco coletores canônicos (Google D0, D-1, termos; JoinAds intradiário e D-1) estão ativos e sem "
      "error workflow; os relatórios legados de Google Ads e JoinAds seguem ativos em paralelo, com dois pares de relatório "
      "Google Ads ativos ao mesmo tempo; a co-autoridade é real e não só de catálogo.]", "NT P06-T11.gaps")
t = nt("P08-T11")
troca(t, "proof", "Nada foi publicado em GTM.",
      "Nada foi publicado em GTM. [Reconciliado em 17/10: a v36 live (VOLC Sensor v3.1, publicada pela frente de medição) "
      f"mantém o mesmo filtro, com sha256 igual a db65a78a; {V31}.]", "NT P08-T11.proof")
ac = t["acceptance"]
i = next(k for k, a in enumerate(ac) if "versão anterior (v34) registrada como rollback" in a)
ac[i] = ac[i].replace("versão anterior (v34) registrada como rollback",
                      "partindo da v36 e preservando event_seq, WEBS Wrapper, consentimentos, triggers e tags de conversão, com a versão anterior (hoje a v36) registrada como rollback")
log.append({"onde": "NT P08-T11.acceptance (rollback a partir da v36)"})
troca(t, "gaps", "Leitura L6 (GTM API read-only, versões 34 e 35) pendente para identificar o setter do key-value da JoinAds e confirmar o rollback.",
      "Leitura L6 feita em 17/10 sobre v35 e v36: só o WEBS Wrapper define key-values e ele descarta o id numérico, então "
      "o setter do key-value numérico da JoinAds está fora do GTM (inferido, não identificado).", "NT P08-T11.gaps")
antes = len(novo["roadmap_new_tasks"])
novo["roadmap_new_tasks"] = [n for n in novo["roadmap_new_tasks"] if n["task"]["id"] != "P08-T12"]
assert len(novo["roadmap_new_tasks"]) == antes - 1
log.append({"onde": "NT P08-T12 removida (dedup por segundo corrigida pela frente de medição; resíduo slice no gaps de P08-T07)"})
t = nt("P14-T11")
t["status"] = "partial"
log.append({"onde": "NT P14-T11.status todo -> partial"})
troca(t, "proof", "(por exemplo 14 valores distintos de custo em 16 runs num dia).",
      "(por exemplo 14 valores distintos de custo em 16 runs num dia). · 17/10/2026, rodada autorizada pelo operador "
      "(16/10 19:00): exportação read-only (REPEATABLE READ READ ONLY + ROLLBACK, default_transaction_read_only=on) de 175 "
      "linhas campaign_day v21, 51 runs v21, 200 linhas JoinAds v2 (earnings e key-value por campanha) e 21 runs JoinAds, "
      "com identificadores pseudonimizados por HMAC e fora do Git; replay horário executado (36 cortes, 6 políticas, três "
      "variantes: estrito, moeda atestada como hipótese e sem runs presos), ledger com cadeia de hash íntegra. Resultado: "
      "nenhuma política saiu de 'insuficiente' (maturidade 0 de 3 dias; uma campanha ativa); a anti-baseline null→0 propôs "
      f"pausar em 180 cortes e o kernel bloqueou os 180. Hashes e agregados em {REC}.", "NT P14-T11.proof")
troca(t, "gaps", "A forma real de raw_source.metrics da v21 e o fuso de fechamento da JoinAds não foram conferidos;",
      "A forma real de raw_source.metrics da v21 e o fuso de fechamento da JoinAds não foram conferidos [17/10: "
      "raw_source.metrics é objeto e vem vazio nos 140 zeros sintetizados; o fuso da JoinAds segue não conferido];",
      "NT P14-T11.gaps")
FRASE = "Replay com dado real depende de P14-T11 (autorização do operador)."
NOVA = ("Replay com dado real: primeiro snapshot exportado em 17/10 (P14-T11), com 3 dias de custo e uma campanha ativa, "
        "insuficiente para qualquer gatilho desta família.")
for n in novo["roadmap_new_tasks"]:
    if FRASE in n["task"].get("gaps", ""):
        troca(n["task"], "gaps", FRASE, NOVA, f"NT {n['task']['id']}.gaps (frase P14-T11)")
troca(nt("P14-T18"), "explanation" if "0 de 28 sessões pagas, então" in nt("P14-T18").get("explanation", "") else "proof",
      "0 de 28 sessões pagas, então", "0 de 28 sessões pagas (e 0 de 13 no Sensor v3.1), então", "NT P14-T18 (v3.1)") \
    if any("0 de 28 sessões pagas, então" in str(v) for v in nt("P14-T18").values()) else None

# ---------------------------------------------------------------- curadoria
troca(ce("cap_revenue_ingestion"), "valor", "o replay real depende de snapshot autorizado.",
      "o replay real depende de snapshot autorizado [17/10: executado uma vez; o earnings com até 17 casas decimais é "
      "recusado pelo adaptador estrito em 5 de 9 dias].", "CE cap_revenue_ingestion")
troca(ce("cap_attribution"), "valor", "0 de 28 sessões pagas com campanha;", "0 de 28 sessões pagas com campanha, e 0 de 13 no Sensor v3.1;",
      "CE cap_attribution")
troca(ce("cap_behavior"), "valor", "Sensor, wrapper e volc-ingest só estão versionados em wip/historico-measurement-20261015.",
      "Sensor, wrapper e volc-ingest só estão versionados em wip/historico-measurement-20261015 [reconciliado em 17/10: "
      f"superado; v3.0 em 128b93ae e v3.1 em db65a78a, igual ao live; {V31}].", "CE cap_behavior")
troca(ce("concept:tracking_control_plane"), "valor", "o container GTM em produção (versão 35) e esses artefatos só estão versionados em wip.",
      "o container GTM em produção (versão 35) e esses artefatos só estão versionados em wip [reconciliado em 17/10: a "
      "produção está na v36, com sensor e wrapper iguais a db65a78a; a evidência da frente de medição neste campo foi preservada].",
      "CE concept:tracking_control_plane")
r = nn("risk:sensor_campaign_id_pii_filter")
troca(r, "evidence", "(leitura da GTM API pendente). Sensor, wrapper e volc-ingest só existem versionados em wip/historico-measurement-20261015.",
      "(leitura da GTM API pendente; feita em 17/10: só o WEBS Wrapper define key-values no container v35/v36 e ele descarta "
      "o id, então o caminho é externo ao GTM, inferido). Sensor, wrapper e volc-ingest só existem versionados em "
      f"wip/historico-measurement-20261015 [17/10: superado; v3.1 em db65a78a, igual ao live]. {V31[0].upper() + V31[1:]}.",
      "NN risk:sensor_campaign_id_pii_filter")
lab = nn("concept:data_intelligence_lab")
troca(lab, "evidence", "Estado máximo: testado com sintético. Replay com dado real e shadow: nenhum (a exportação do snapshot foi negada pela permissão da sessão).",
      "Estado máximo: testado com sintético. Replay com dado real e shadow: nenhum (a exportação do snapshot foi negada pela "
      "permissão da sessão). · 17/10/2026, rodada autorizada: um replay com dado real sobre snapshot read-only pseudonimizado "
      "(3 dias de custo, 9 de receita; todas as políticas em 'insuficiente'; anti-baseline null→0 bloqueada em 180 de 180); "
      "shadow agendado: nenhum (doc:rodada-autorizada-20261017).", "NN concept:data_intelligence_lab")
troca(nn("doc:leituras-externas-20261016"), "evidence",
      "Não executadas: GTM API, n8n API e hash da Edge Function. Exportação do snapshot negada pela permissão da sessão.",
      "Não executadas em 16/10: GTM API, n8n API e hash da Edge Function; exportação do snapshot negada pela permissão da "
      "sessão. Todas feitas em 17/10 (doc:rodada-autorizada-20261017).", "NN doc:leituras-externas-20261016")
cu["novos_nos"]["documents"].append({
    "id": "doc:rodada-autorizada-20261017", "label": "Recibo da rodada autorizada de 17/10/2026 (snapshot, replay real e metadados)",
    "cluster": "data", "documenta": "concept:data_intelligence_lab",
    "summary": "Exportação read-only pseudonimizada de v21 campaign_day e JoinAds v2, replay as_of horário com três variantes, e leituras só de metadados de GTM (v35 e v36), n8n (workflows, schedules, error workflows, execuções) e do hash da Edge Function volc-ingest.",
    "evidence": f"docs/data-intelligence/fundacao-20261016/{REC}/ (recibo, SQL, scripts e resumos agregados; nenhum identificador real)."})
log.append({"onde": "NN doc:rodada-autorizada-20261017 (novo)"})
for e in cu["novas_arestas"]:
    if e["source"] == "risk:sensor_campaign_id_pii_filter" and e["target"] == "cap_behavior":
        troca(e, "evidence", "0 de 28 sessões pagas chegam com campanha.", "0 de 28 sessões pagas chegam com campanha (0 de 13 no v3.1).",
              "ED risk:sensor->cap_behavior")

# ---------------------------------------------------------------- guardas sobre a base reconciliada
base_r, base_c = show(REF_MED, RP), show(REF_MED, CP)
tr = {t["id"]: t for i in base_r["initiatives"] for t in i["tasks"]}
nos = {(s, x["id"]): x for s in ("capabilities", "concepts", "documents") for x in base_c[s]}
guardas = []
for u in novo["roadmap_updates"]:
    if (u["task_id"], u["campo"]) in {("P06-T07", "proof"), ("P08-T07", "proof")}:
        velho, u["base_sha256_campo_anterior"] = u.get("base_sha256_campo_anterior"), sha_campo(tr[u["task_id"]].get(u["campo"]))
        guardas.append({"op": f"{u['task_id']}.{u['campo']}", "antes": velho, "depois": u["base_sha256_campo_anterior"]})
for e in cu["evidence_appends"]:
    if e["id"] in ("cap_behavior", "concept:tracking_control_plane"):
        velho, e["base_sha256_campo_anterior"] = e.get("base_sha256_campo_anterior"), sha_campo(nos[(e["secao"], e["id"])].get(e["campo"]))
        guardas.append({"op": f"{e['id']}.{e['campo']}", "antes": velho, "depois": e["base_sha256_campo_anterior"]})
assert len(guardas) == 4, guardas

novo["esquema"] = d["esquema"]
novo["gerado_em"] = "2026-10-17"
novo["substitui"] = "CURADORIA-DELTA-20261016.json (reconciliado; o original fica preservado)"
novo["reconciliacao"] = {
    "frente": "origin/fix/measurement-control-plane-20261016", "head": REF_MED,
    "campos_da_frente_preservados": ["P06-T07.proof", "P08-T01.proof", "P08-T07.proof", "cap_behavior.evidence", "concept:tracking_control_plane.evidence"],
    "como": "o integrador importa esses 5 campos idênticos aos de db65a78a em commit próprio; este delta só acrescenta",
    "guardas_recalculadas": guardas, "trocas": log,
    "removidas": ["P08-T12"], "status_alterados_no_delta": [{"P14-T11": "todo -> partial"}],
    "nada_vira_done": True,
    "aviso_grafo": "o grafo reconstruído nesta branch é corrente só em relação à branch; não vale para o grafo global nem para o main",
}
txt = json.dumps(novo, ensure_ascii=False, indent=2) + "\n"
assert '"status": "done"' not in json.dumps(novo["roadmap_new_tasks"]) and all(u.get("valor") != "done" for u in novo["roadmap_updates"] if u["campo"] == "status")
open(SAIDA, "w").write(txt)
print(json.dumps({"saida": SAIDA, "sha256": hashlib.sha256(txt.encode()).hexdigest(), "trocas": len(log), "guardas_recalculadas": len(guardas),
                  "roadmap_updates": len(novo["roadmap_updates"]), "novas_tarefas": len(novo["roadmap_new_tasks"])}, ensure_ascii=False))
