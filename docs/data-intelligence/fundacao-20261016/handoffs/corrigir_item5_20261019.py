"""Correções do item 5 pedidas pelo dono em 17/10 23:39 UTC, aplicadas em 19/10/2026 só nesta branch.

1. As entradas do item 5 foram gravadas com o prefixo de data 18/10/2026 em 17/10: passam a 17/10/2026.
2. O texto do replay passa a refletir o JSON: quatro políticas insuficientes, baseline manter, null→zero com 290
   propostas de pausa, todas bloqueadas.
3. O error workflow passa a ser descrito como configurado e testado por payload sintético, sem prova end-to-end.
4. Acrescenta a entrada de 19/10/2026 com a prova do agendador (execuções naturais de 18 e 19/10) e os 3 primeiros
   dias de dq_zero_sintetizado. Cada troca casa exatamente o número esperado de vezes, senão aborta sem gravar.
Uso (raiz do repositório): python3 corrigir_item5_20261019.py
"""
import json
import sys

RP, CP = "volc-os-workbook/ROADMAP-VIVO.json", "docs/volc-os-graph/curadoria-operacional.json"
HOJE = "2026-10-19"
VELHO_PREF = "· 18/10/2026 · lab/data-foundation-20261016 (local, sem push, não integrado; produção n8n alterada"
NOVO_PREF = "· 17/10/2026 · lab/data-foundation-20261016 (local, sem push, não integrado; produção n8n alterada"
PREF19 = "· 19/10/2026 · lab/data-foundation-20261016 (local, sem push, não integrado; leitura read-only): "

TROCAS_ROADMAP = [
    (VELHO_PREF, NOVO_PREF, 4),
    ("a prova do agendador do D-1 é a execução natural de 18/10 06:17 BRT, pendente nesta escrita.",
     "a prova do agendador do D-1 veio nas execuções naturais seguintes (entrada de 19/10/2026).", 1),
    ("segue insuficiente nas cinco políticas (snapshot 17/10 20:27 BRT, decisões E ca7ea487…, anti-baseline null→zero 290/290 bloqueadas);",
     "segue sem decisão econômica (snapshot 17/10 20:27 BRT, decisões E ca7ea487…): quatro políticas insuficientes "
     "(equal, greedy conservador, regra de margem madura e guardião 72 h), a baseline manter e a anti-baseline null→zero "
     "com 290 propostas de pausa, todas bloqueadas pelo kernel;", 1),
    ("leitura read-only diária de 18/10/2026 em diante",
     "leitura read-only diária a partir de 18/10/2026, primeiro dia inteiro com os três coletores Google na versão nova", 1),
    ("ligado aos cinco coletores canônicos e ativo; testado por payloads sintéticos em dry-run e pelos testes test_error_*; "
     "nenhum erro real disparado desde a implantação.",
     "configurado nos cinco coletores canônicos e ativo; testado por payload sintético em dry-run e pelos testes "
     "test_error_*; ainda sem prova end-to-end de falha real (nenhum erro real disparado desde a implantação).", 1),
]
ACRESCIMOS = {
    "P06-T10": PREF19 + (
        "agendador provado pelas execuções naturais depois do cutover: Google D-1 em 18/10 06:17 e 14:17 e 19/10 06:17 BRT "
        "(3 runs completed, janelas 17/10 e 18/10, 15 observações: 12 metric_row_absent sem custo, 3 present, BRL observed, "
        "lotes e linhas = declarados, 0 erro silencioso); termos 8 execuções e D0 23 desde 18/10 00:00 UTC, todas completed. "
        "dq_zero_sintetizado (zero sem linha nas observações collector_version 2): 0 em 17, 18 e 19/10 (19/10 parcial); a contagem dos "
        "7 dias começa em 18/10, porque 17/10 ainda teve o D-1 antigo às 06:17 e 14:17: 1 de 7 dias inteiros. Segue partial."),
    "P10-T28": PREF19 + (
        "error workflow sem nenhum disparo real até 19/10 10:50 UTC (configurado, sem prova end-to-end); reaper em shadow com "
        "48 execuções e decisão idêntica (os mesmos 3 candidatos); os 3 órfãos seguem running. Migration candidata "
        "running → abandoned preparada e NÃO aplicada (docs/data-intelligence/fundacao-20261016/propostas/"
        "MIGRATION-RUN-ABANDONED.md, 8 testes em PostgreSQL descartável). Segue partial."),
}
EVID_CURADORIA = {
    "risk:google_ads_zero_sintetizado": PREF19 + "dq_zero_sintetizado = 0 nas observações collector_version 2 em 17, 18 e 19/10; agendador do D-1 provado em 18 e 19/10. Risco segue aberto até 7 dias e até os leitores tratarem as linhas antigas.",
}


def trocar(texto, velho, novo, n, onde):
    if texto.count(velho) != n:
        sys.exit(f"{onde}: esperava {n}, achou {texto.count(velho)}: {velho[:70]!r}")
    return texto.replace(velho, novo)


rt = open(RP, encoding="utf-8").read()
for v, nv, n in TROCAS_ROADMAP:
    rt = trocar(rt, v, nv, n, "roadmap")
ct = trocar(open(CP, encoding="utf-8").read(), VELHO_PREF, NOVO_PREF, 3, "curadoria")
r, c = json.loads(rt), json.loads(ct)
T = {t["id"]: t for i in r["initiatives"] for t in i["tasks"]}
for tid, txt in ACRESCIMOS.items():
    T[tid]["proof"] = T[tid]["proof"].rstrip() + " " + txt
    T[tid]["updated_at"] = HOJE
r["updated_at"] = HOJE
N = {x["id"]: x for s in ("capabilities", "concepts", "documents") for x in c[s]}
for nid, txt in EVID_CURADORIA.items():
    N[nid]["evidence"] = N[nid]["evidence"].rstrip() + " " + txt
c["meta"]["curadoria_atualizada_em"] = HOJE
open(RP, "w", encoding="utf-8").write(json.dumps(r, indent=2, ensure_ascii=False) + "\n")
open(CP, "w", encoding="utf-8").write(json.dumps(c, indent=2, ensure_ascii=False) + "\n")
print("ok")
