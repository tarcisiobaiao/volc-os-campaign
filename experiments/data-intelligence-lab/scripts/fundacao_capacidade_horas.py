"""Distribuição horária REAL (D30) da campanha Google Ads versionada no repositório — leitura só via git.

Fonte (somente leitura, `git show`): ref `wip/historico-joinads-20261015`,
`.claude-ads/runs/google-ads-recovery-20261015T125729-0300/receipts/d-live-campaign-audit.json`, bloco
`"hour"` (24 segmentos; soma = D30 16/09–15/10 da campanha ativa da conta). Não é série diária: é o
agregado de 30 dias por hora do dia (America/Sao_Paulo). Serve para:
- dizer quanto da atividade cai fora da janela 06–23 do D0;
- calibrar a taxa λ (eventos que mudam a linha por hora) do modelo de volume.

Saída SANITIZADA (R1 F25): só fatias por hora e taxas médias de contagem; nenhum id de conta/campanha e
nenhum valor monetário absoluto vai para o repositório.

Uso: <python> -I scripts/fundacao_capacidade_horas.py --repo <worktree do integrador> --saida <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REF = "wip/historico-joinads-20261015"
CAMINHO = ".claude-ads/runs/google-ads-recovery-20261015T125729-0300/receipts/d-live-campaign-audit.json"
DIAS = 30


def _achar_horas(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("hour"), list) and obj["hour"] and "segment" in obj["hour"][0]:
            return obj["hour"]
        for v in obj.values():
            r = _achar_horas(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _achar_horas(v)
            if r:
                return r
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()
    bruto = subprocess.run(["git", "-C", a.repo, "show", f"{REF}:{CAMINHO}"], check=True, capture_output=True).stdout
    commit = subprocess.run(["git", "-C", a.repo, "rev-parse", REF], check=True, capture_output=True, text=True).stdout.strip()
    horas = sorted(_achar_horas(json.loads(bruto)), key=lambda h: int(h["segment"]))
    assert [int(h["segment"]) for h in horas] == list(range(24)), "esperadas 24 horas"
    met = ("impressions", "clicks", "cost_brl", "conversions_ads")
    tot = {m: sum(h[m] for h in horas) for m in met}
    por_hora = [{"hora": int(h["segment"]), **{m: h[m] for m in met}} for h in horas]

    def fatia(hs):
        return {m: sum(por_hora[i][m] for i in hs) / tot[m] for m in met}

    madrugada = range(0, 6)
    res = {
        "fonte": {"ref": REF, "commit": commit, "caminho": CAMINHO, "sha256": hashlib.sha256(bruto).hexdigest()},
        "periodo": "D30 agregado por hora do dia (16/09–15/10/2026), campanha ativa da conta A, America/Sao_Paulo",
        "sanitizacao": "sem ids e sem valores monetários absolutos; só fatias e taxas de contagem (R1 F25)",
        "fatia_por_hora": [{"hora": h["hora"], **{m: h[m] / tot[m] for m in met}} for h in por_hora],
        "fatia_00_06": fatia(madrugada),
        "fatia_23": fatia([23]),
        "fatia_fora_da_ultima_leitura_d0_aprox": {m: fatia(madrugada)[m] + fatia([23])[m] * 53 / 60 for m in met},
        "impressoes_por_hora_media": tot["impressions"] / (DIAS * 24),
        "impressoes_por_hora_pico": max(h["impressions"] for h in por_hora) / DIAS,
        "impressoes_por_hora_vale": min(h["impressions"] for h in por_hora) / DIAS,
        "nota": "λ = impressões/hora da campanha ativa (1 de 5 campanhas da conta com entrega). Uma linha "
                "campanha-dia muda quando QUALQUER métrica muda; impressão é o evento mais frequente.",
    }
    nomes = {"impressions": "impressoes", "clicks": "cliques", "cost_brl": "custo", "conversions_ads": "conversoes"}

    def renomear(o):
        if isinstance(o, dict):
            return {nomes.get(k, k): renomear(v) for k, v in o.items()}
        if isinstance(o, list):
            return [renomear(v) for v in o]
        return o

    res = renomear(res)
    Path(a.saida).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("fatia_00_06", "impressoes_por_hora_media")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
