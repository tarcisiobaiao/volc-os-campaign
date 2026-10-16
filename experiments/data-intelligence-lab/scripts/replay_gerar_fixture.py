"""Gera a fixture SINTÉTICA mínima do replay econômico (cenário `mini`) + MANIFEST.

Uso (da raiz do lab): .venv/bin/python -I scripts/replay_gerar_fixture.py [--verificar]
A fixture guarda: especificação do cenário, verdade diária (eficiência e flags), o log de
observações emitido sob a política `static`, os registros de decisão de cada baseline e o
relatório. O teste refaz tudo e exige igualdade byte a byte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from volc_dil.contracts import json_canonico, sha256_de  # noqa: E402
from volc_dil.replay import baselines, cenario_mini, executar, proporcional_ingenua, relatorio_cenario  # noqa: E402
from volc_dil.replay.cenario import Mundo  # noqa: E402
from volc_dil.replay.motor import log_completo  # noqa: E402

DESTINO = RAIZ / "fixtures" / "replay"


def construir() -> tuple[bytes, dict]:
    espec = cenario_mini()
    mundo = Mundo(espec)
    politicas = baselines() + [proporcional_ingenua()]
    execucoes = [executar(espec, p) for p in politicas]
    estatica = execucoes[0]
    verdade = []
    for i in range(espec.n_dias):
        for u in mundo.unidades:
            s = mundo.sorteio(u.chave, i)
            verdade.append({
                "dia": mundo.dia(i).isoformat(), "entidade_id": u.chave.entidade_id, "moeda": u.moeda,
                "eficiencia_milionesimos": int(round(mundo.eficiencia(u.chave, i) * 1_000_000)),
                "custo_nao_coletado": s.custo_nao_coletado, "receita_falha_prelim": s.receita_falha_prelim,
                "receita_nao_coletada": s.receita_nao_coletada,
                "receita_verdadeira_static_micros": mundo.receita_verdadeira(
                    u.chave, i, estatica.alocacoes[i][u.chave].micros),
            })
    corpo = {
        "natureza": "sintetico",
        "aviso": "Dados SINTÉTICOS gerados por seed; não são validação real.",
        "cenario": espec.para_json(),
        "verdade": verdade,
        "log_static": [o.para_json() for o in log_completo(espec, estatica.alocacoes)],
        "decisoes": {e.politica: [d.para_json() for d in e.decisoes] for e in execucoes},
        "relatorio": relatorio_cenario(espec, execucoes),
    }
    conteudo = (json_canonico(corpo) + "\n").encode("utf-8")
    manifesto = {
        "arquivo": "cenario_mini.json",
        "natureza": "sintetico",
        "gerador": "experiments/data-intelligence-lab/scripts/replay_gerar_fixture.py",
        "sha256": __import__("hashlib").sha256(conteudo).hexdigest(),
        "bytes": len(conteudo),
        "seed": espec.seed,
        "n_observacoes_log_static": len(corpo["log_static"]),
        "relatorio_sha256": corpo["relatorio"]["relatorio_sha256"],
        "decisoes_sha256": {k: sha256_de(v) for k, v in sorted(corpo["decisoes"].items())},
    }
    return conteudo, manifesto


def main() -> int:
    conteudo, manifesto = construir()
    if "--verificar" in sys.argv:
        atual = (DESTINO / "cenario_mini.json").read_bytes()
        ok = atual == conteudo
        print("fixture confere" if ok else "fixture DIVERGE")
        return 0 if ok else 1
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "cenario_mini.json").write_bytes(conteudo)
    (DESTINO / "MANIFEST.json").write_text(json.dumps(manifesto, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
    print(json.dumps(manifesto, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
