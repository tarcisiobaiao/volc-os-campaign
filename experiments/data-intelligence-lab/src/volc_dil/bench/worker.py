"""Processo-filho de UMA medição (engine × tamanho). Imprime um JSON no stdout.

Executado pelo orquestrador (`scripts/bench_executar.py`) em subprocesso isolado para que o
pico de RSS (medido pelo pai via `os.wait4`) seja só desta medição.

Uso: python -I worker.py --engine {python_puro,contrato,duckdb,polars,volc_atual,vazio}
                         --parquet P --jsonl J --as-of US --reps 5 --threads 4 --raiz-src S [--raiz-repo R]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time


def _medir(fn, reps: int, aquecer: int = 1):
    for _ in range(aquecer):
        ultimo = fn()
    tempos = []
    for _ in range(reps):
        t0 = time.perf_counter()
        ultimo = fn()
        tempos.append(time.perf_counter() - t0)
    return ultimo, {"mediana_s": statistics.median(tempos), "min_s": min(tempos), "max_s": max(tempos), "reps": reps,
                    "aquecimento_descartado": aquecer}


def _ler_jsonl(caminho: str) -> list[tuple]:
    with open(caminho, encoding="utf-8") as f:
        return [tuple(json.loads(linha)) for linha in f]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--parquet")
    ap.add_argument("--jsonl")
    ap.add_argument("--as-of", type=int)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--reps-carga", type=int, default=3)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--raiz-src", required=True)
    ap.add_argument("--raiz-repo")
    a = ap.parse_args()
    sys.path.insert(0, a.raiz_src)
    out: dict = {"engine": a.engine, "threads": a.threads}
    t0 = time.perf_counter()

    if a.engine == "vazio":
        out["import_s"] = 0.0
    elif a.engine == "volc_atual":
        sys.path.insert(0, a.raiz_repo)
        from datetime import datetime

        from volc_ads.inteligencia_decisao import replay as rp
        from volc_ads.inteligencia_decisao.normalizacao_google_ads import normalizar_linhas_google_ads

        out["import_s"] = time.perf_counter() - t0
        res, out["executar_replay"] = _medir(rp.executar_replay, a.reps)
        out["replay_total"], out["replay_passaram"] = res["total"], res["passaram"]
        fx = json.loads((rp.Path(rp.__file__).with_name("dados") / "linhas_google_ads_sinteticas.json").read_text("utf-8"))
        agora = datetime.fromisoformat(fx["as_of"].replace("Z", "+00:00"))

        def norm():
            return normalizar_linhas_google_ads(fx["google_ads_rows"], agora=agora, as_of_date=fx["as_of_date"],
                                                calendar_timezone=fx["calendar_timezone"],
                                                coverage_receipt=fx["coverage_receipt"])

        _, out["normalizar_linhas_google_ads"] = _medir(norm, a.reps)
        out["linhas_normalizadas"] = len(fx["google_ads_rows"])
    else:
        from volc_dil.bench import engines as E

        if a.engine == "python_puro":
            out["import_s"] = time.perf_counter() - t0
            linhas, out["carga_jsonl"] = _medir(lambda: _ler_jsonl(a.jsonl), a.reps_carga)
            (res, emp), out["operacao"] = _medir(lambda: E.op_python(linhas, a.as_of), a.reps)
            out["exportacao"] = {"mediana_s": 0.0, "nota": "resultado já é lista de tuplas Python"}
        elif a.engine == "contrato":
            out["import_s"] = time.perf_counter() - t0
            linhas, out["carga_jsonl"] = _medir(lambda: _ler_jsonl(a.jsonl), a.reps_carga)
            obs, out["conversao_para_contrato"] = _medir(lambda: E.para_observacoes(linhas), a.reps_carga)
            del linhas
            (res, emp), out["operacao"] = _medir(lambda: E.op_contrato(obs, a.as_of), a.reps)
            out["exportacao"] = {"mediana_s": 0.0, "nota": "resultado já é lista de tuplas Python"}
        elif a.engine == "duckdb":
            con = E.conectar_duckdb(a.threads)
            out["import_s"] = time.perf_counter() - t0
            out["duckdb_config"] = dict(con.execute(
                "SELECT name, value FROM duckdb_settings() WHERE name IN "
                "('threads','autoinstall_known_extensions','autoload_known_extensions','memory_limit')").fetchall())

            def carga():
                con.execute(f"CREATE OR REPLACE TABLE obs AS SELECT * FROM read_parquet('{a.parquet}')")

            _, out["carga_parquet"] = _medir(carga, a.reps_carga)
            emp, out["operacao"] = _medir(lambda: E.op_duckdb(con, a.as_of), a.reps)
            res, out["exportacao"] = _medir(lambda: E.exportar_duckdb(con), max(2, a.reps_carga))
        elif a.engine == "polars":
            import polars as pl

            out["import_s"] = time.perf_counter() - t0
            out["polars_threads"] = pl.thread_pool_size()
            df, out["carga_parquet"] = _medir(lambda: pl.read_parquet(a.parquet), a.reps_carga)
            (nativo, emp), out["operacao"] = _medir(lambda: E.op_polars(df.lazy(), a.as_of), a.reps)
            (_, _), out["scan_parquet_mais_operacao"] = _medir(lambda: E.op_polars(pl.scan_parquet(a.parquet), a.as_of),
                                                               a.reps_carga)
            res, out["exportacao"] = _medir(lambda: E.exportar_polars(nativo), max(2, a.reps_carga))
        else:
            raise SystemExit(f"engine desconhecida: {a.engine}")
        out["n_linhas_resultado"] = len(res)
        out["n_empates"] = emp
        out["resultado_sha256"] = E.hash_resultado(list(res), emp)
    out["parede_total_s"] = time.perf_counter() - t0
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
