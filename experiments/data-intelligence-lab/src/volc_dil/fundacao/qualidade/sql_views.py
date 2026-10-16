"""Gerador de SELECTs somente leitura a partir das views candidatas (sem criar nada no banco).

Produção roda com `default_transaction_read_only=on` nas leituras do integrador: lá não dá para
criar view nem view temporária. Este módulo transforma cada `CREATE VIEW` marcado com
`-- dq:view <nome>` … `-- dq:fim` num SELECT autocontido: as views auxiliares referenciadas
(`dil_qualidade.<x>`) viram CTEs, e `dil_qualidade.agora()` vira `now()`.

    python -m volc_dil.fundacao.qualidade.sql_views          # imprime
    python -m volc_dil.fundacao.qualidade.sql_views --escrever   # regrava selects_somente_leitura.sql
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DIR_VIEWS = Path(__file__).resolve().parents[4] / "migrations_candidatas" / "views_qualidade"
CAMINHO_UP = DIR_VIEWS / "dq_01_views_qualidade.sql"
CAMINHO_DOWN = DIR_VIEWS / "dq_01_views_qualidade.down.sql"
CAMINHO_UP_DIL_OBS = DIR_VIEWS / "dq_02_views_dil_obs.sql"
CAMINHO_DOWN_DIL_OBS = DIR_VIEWS / "dq_02_views_dil_obs.down.sql"
CAMINHO_SELECTS = DIR_VIEWS / "selects_somente_leitura.sql"

AUXILIARES = ("dq_parametros_sla", "dq_parametros_limiares", "dq_runs", "dq_slots")

_BLOCO = re.compile(r"-- dq:view (\w+)\n(.*?)-- dq:fim", re.S)
_CREATE = re.compile(r"CREATE VIEW dil_qualidade\.(\w+) WITH \(security_invoker = true\) AS\n(.*);\s*$", re.S)
_REF = re.compile(r"dil_qualidade\.(dq_\w+)")


def ler_views(sql: str) -> dict[str, str]:
    """nome -> corpo (SELECT/WITH ..., sem ponto-e-vírgula), na ordem do arquivo."""
    saida: dict[str, str] = {}
    for nome, bloco in _BLOCO.findall(sql):
        linhas = [ln for ln in bloco.splitlines() if not ln.lstrip().startswith("--")]
        m = _CREATE.search("\n".join(linhas))
        if not m or m.group(1) != nome:
            raise ValueError(f"bloco dq:view {nome} sem CREATE VIEW correspondente")
        saida[nome] = m.group(2).strip()
    return saida


def _deps(nome: str, views: dict[str, str], vistos: list[str]) -> list[str]:
    for d in _REF.findall(views[nome]):
        if d not in views:
            raise ValueError(f"{nome} referencia {d}, que não está no arquivo")
        if d not in vistos:
            _deps(d, views, vistos)
            vistos.append(d)
    return vistos


def _local(corpo: str) -> str:
    return _REF.sub(r"\1", corpo.replace("dil_qualidade.agora()", "now()"))


def select_autocontido(nome: str, views: dict[str, str]) -> str:
    deps = _deps(nome, views, [])
    corpo = _local(views[nome])
    if not deps:
        return corpo
    ctes = ",\n".join(f"{d} AS (\n{_local(views[d])}\n)" for d in deps)
    if re.match(r"WITH\s", corpo):
        return f"WITH {ctes},\n{corpo[4:].lstrip()}"
    return f"WITH {ctes}\n{corpo}"


def gerar_selects(*caminhos: Path) -> str:
    caminhos = caminhos or (CAMINHO_UP, CAMINHO_UP_DIL_OBS)
    partes = [
        "-- GERADO por `python -m volc_dil.fundacao.qualidade.sql_views --escrever`. NÃO EDITAR À MÃO.",
        "-- Fonte: dq_01_views_qualidade.sql e dq_02_views_dil_obs.sql (mesma pasta).",
        "-- SELECTs puros, para leitura read-only em produção (PGOPTIONS='-c default_transaction_read_only=on').",
        "-- Nenhum cria objeto. As seções dq_obs_* só funcionam se dil_obs existir (thread A).",
        "",
    ]
    for caminho in caminhos:
        views = ler_views(caminho.read_text(encoding="utf-8"))
        for nome in views:
            if nome in AUXILIARES:
                continue
            partes += [f"-- ===== {nome} =====", select_autocontido(nome, views) + ";", ""]
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    texto = gerar_selects()
    if "--escrever" in argv:
        CAMINHO_SELECTS.write_text(texto, encoding="utf-8")
        print(CAMINHO_SELECTS)
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
