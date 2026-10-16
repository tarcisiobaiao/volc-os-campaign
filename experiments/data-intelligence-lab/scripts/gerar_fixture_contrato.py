"""Gera a fixture SINTÉTICA de exemplo do contrato (determinística, sem seed aleatória).

Uso: .venv/bin/python scripts/gerar_fixture_contrato.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from volc_dil.contracts import (  # noqa: E402
    ChaveUnidade, Cobertura, Dinheiro, EstadoMedida, Maturidade, Metrica, MetodoAtribuicao,
    Observacao, Snapshot, ValueKind, json_canonico, sha256_arquivo,
)

SP = timezone(timedelta(hours=-3))
D0 = datetime(2026, 9, 1, tzinfo=SP)


def campanha(cid: str) -> ChaveUnidade:
    return ChaveUnidade("acc-sintetica-1", "campaign", cid, ("campaign", "day"))


def base(u, metrica, valor, **kw):
    d = dict(unidade=u, metrica=metrica, valor=valor, estado=EstadoMedida.MEDIDO, janela_inicio=D0,
             janela_fim=D0 + timedelta(days=1), timezone="America/Sao_Paulo",
             observado_em=D0 + timedelta(days=1, hours=1), disponivel_em=D0 + timedelta(days=1, hours=2),
             fonte="google_ads", versao_fonte="sintetico-v1", coleta_id="gads-run-0001",
             cobertura=Cobertura.COMPLETA, maturidade=Maturidade.MADURA, metodo=MetodoAtribuicao.NAO_APLICAVEL,
             linhagem=("fixture:contrato",))
    d.update(kw)
    if d["estado"] is EstadoMedida.MEDIDO and d["valor"] is not None:
        zero = d["valor"].eh_zero() if isinstance(d["valor"], Dinheiro) else d["valor"] == 0
        if zero:
            d["estado"] = EstadoMedida.ZERO_CONFIRMADO
    return Observacao(**d)


def receita(u, micros, **kw):
    kw.setdefault("value_kind", ValueKind.REPORTED_REVENUE)
    kw.setdefault("fonte", "publisher_report")
    kw.setdefault("coleta_id", "pub-run-0001")
    kw.setdefault("metodo", MetodoAtribuicao.DECLARED_CAMPAIGN_FUNNEL)
    return base(u, Metrica.RECEITA, Dinheiro(micros, "BRL") if micros is not None else None, **kw)


obs = [
    base(campanha("c-001"), Metrica.CUSTO, Dinheiro(12_500_000, "BRL")),
    base(campanha("c-001"), Metrica.CLIQUES, 250),
    receita(campanha("c-001"), 9_000_000, maturidade=Maturidade.PRELIMINAR, cobertura=Cobertura.PARCIAL),
    receita(campanha("c-001"), 14_200_000, maturidade=Maturidade.REVISADA, coleta_id="pub-run-0002",
            observado_em=D0 + timedelta(days=3), disponivel_em=D0 + timedelta(days=3, hours=1)),
    base(campanha("c-002"), Metrica.CUSTO, Dinheiro(0, "BRL")),
    receita(campanha("c-002"), None, estado=EstadoMedida.NAO_COLETADO, motivo="relatório do parceiro não chegou"),
    base(campanha("c-003"), Metrica.CUSTO, None, estado=EstadoMedida.FALHA, motivo="timeout na coleta"),
    base(ChaveUnidade("acc-sintetica-1", "session", "s-9", ("session",)), Metrica.SINAL,
         Dinheiro(1_850_000, "USD"), value_kind=ValueKind.OBSERVED_AUCTION_SIGNAL,
         metodo=MetodoAtribuicao.DETERMINISTIC_SESSION, fonte="browser_beacon", coleta_id="beacon-0001"),
]

destino = RAIZ / "fixtures" / "contract" / "observacoes_exemplo.json"
destino.write_text(json.dumps({"rotulo": "SINTÉTICO — exemplo do contrato; não é dado real",
                               "observacoes": [o.para_json() for o in obs]}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
cortes = {"d+1_04h": D0 + timedelta(days=1, hours=4), "d+4": D0 + timedelta(days=4)}
manifesto = {"arquivo": destino.name, "sha256": sha256_arquivo(str(destino)), "n_observacoes": len(obs),
             "natureza": "sintetico", "snapshots": {}}
for nome, corte in cortes.items():
    s = Snapshot.construir(obs, corte, rotulo=nome)
    manifesto["snapshots"][nome] = s.manifesto_json()
(destino.parent / "MANIFEST.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                               encoding="utf-8")
print(json_canonico({k: manifesto[k] for k in ("sha256", "n_observacoes")}))
