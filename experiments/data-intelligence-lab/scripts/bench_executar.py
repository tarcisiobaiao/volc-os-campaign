"""Orquestra a bancada (SINTÉTICA): gera dados, roda cada engine em subprocesso, verifica equivalência.

Uso (da raiz do lab): .venv/bin/python -I scripts/bench_executar.py [--tamanhos 1000,10000,100000,1000000]
                      [--reps 5] [--threads 4] [--manter-artefatos]
Saída: results/bench/bench_resultados.json. Artefatos grandes (Parquet/JSONL) vão para
artifacts/bench/ (gitignored) e são APAGADOS no fim, salvo --manter-artefatos; o JSON guarda
os sha256 e tamanhos.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parents[1]
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

from volc_dil.bench import dados  # noqa: E402
from volc_dil.bench.engines import CONFIG_DUCKDB, para_observacoes  # noqa: E402
from volc_dil.contracts import json_canonico, manifesto_execucao, sha256_arquivo  # noqa: E402

ARTEFATOS = RAIZ / "artifacts" / "bench"
SAIDA = RAIZ / "results" / "bench" / "bench_resultados.json"
WORKER = SRC / "volc_dil" / "bench" / "worker.py"
SEED = 20261015
LIMITE_CONTRATO = 100_000  # acima disso o caminho do contrato estoura o orçamento de 5 min (ver relatório)
TIMEOUT_S = 300


def _maquina() -> dict:
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:  # noqa: BLE001
            return None

    return {"plataforma": platform.platform(), "cpu": sysctl("machdep.cpu.brand_string"),
            "ncpu": sysctl("hw.ncpu"), "memoria_bytes": sysctl("hw.memsize"), "python": sys.version.split()[0]}


def rodar_com_rss(engine: str, **kw) -> dict:
    """Roda em subprocesso e mede o pico de RSS DESTE filho via os.wait4 (não o máximo acumulado)."""
    threads, reps = kw["threads"], kw["reps"]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "POLARS", "OMP"))}
    env.update({"OMP_NUM_THREADS": str(threads), "POLARS_MAX_THREADS": str(threads), "MKL_NUM_THREADS": str(threads)})
    cmd = [sys.executable, "-I", str(WORKER), "--engine", engine, "--reps", str(reps),
           "--reps-carga", str(kw.get("reps_carga", 3)), "--threads", str(threads), "--raiz-src", str(SRC),
           "--raiz-repo", str(REPO)]
    if kw.get("parquet"):
        cmd += ["--parquet", kw["parquet"], "--jsonl", kw["jsonl"], "--as-of", str(kw["as_of"])]
    saida_tmp = ARTEFATOS / f"worker_{engine}_{os.getpid()}.out"
    t0 = time.perf_counter()
    with open(saida_tmp, "wb") as fo, open(str(saida_tmp) + ".err", "wb") as fe:
        p = subprocess.Popen(cmd, stdout=fo, stderr=fe, env=env, cwd=str(RAIZ))
        prazo = time.monotonic() + TIMEOUT_S
        while True:
            pid, status, ru = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() > prazo:
                p.kill()
                os.wait4(p.pid, 0)
                return {"engine": engine, "erro": f"timeout {TIMEOUT_S}s"}
            time.sleep(0.05)
    parede = time.perf_counter() - t0
    p.returncode = os.waitstatus_to_exitcode(status)
    texto = saida_tmp.read_text()
    erro = Path(str(saida_tmp) + ".err").read_text()
    saida_tmp.unlink()
    Path(str(saida_tmp) + ".err").unlink()
    if p.returncode != 0:
        return {"engine": engine, "erro": erro[-2000:]}
    r = json.loads(texto.strip().splitlines()[-1])
    # macOS: ru_maxrss em bytes; Linux: em KiB.
    fator = 1 if sys.platform == "darwin" else 1024
    r["pico_rss_mb"] = round(ru.ru_maxrss * fator / 2**20, 1)
    r["parede_subprocesso_s"] = parede
    return r


def preparar(n: int) -> dict:
    t0 = time.perf_counter()
    linhas = dados.gerar(n, SEED)
    t_gen = time.perf_counter() - t0
    ARTEFATOS.mkdir(parents=True, exist_ok=True)
    pq = ARTEFATOS / f"obs_{n}.parquet"
    jl = ARTEFATOS / f"obs_{n}.jsonl"
    t0 = time.perf_counter()
    df = dados.para_polars(linhas)
    t_df = time.perf_counter() - t0
    t0 = time.perf_counter()
    df.write_parquet(pq)  # writer nativo do Polars (sem pyarrow), compressão padrão zstd
    t_pq = time.perf_counter() - t0
    del df
    t0 = time.perf_counter()
    with open(jl, "w", encoding="utf-8") as f:
        for x in linhas:
            f.write(json.dumps(x, separators=(",", ":")))
            f.write("\n")
    t_jl = time.perf_counter() - t0
    info = {
        "n_alvo": n, "n_linhas": len(linhas), "n_unidades": dados.n_unidades_para(n), "dias": dados.DIAS,
        "geracao_python_s": t_gen, "tuplas_para_polars_s": t_df, "escrita_parquet_s": t_pq, "escrita_jsonl_s": t_jl,
        "parquet_bytes": pq.stat().st_size, "jsonl_plano_bytes": jl.stat().st_size,
        "parquet_sha256": sha256_arquivo(str(pq)), "jsonl_sha256": sha256_arquivo(str(jl)),
    }
    if n <= LIMITE_CONTRATO:
        t0 = time.perf_counter()
        obs = para_observacoes(linhas)
        info["tuplas_para_observacao_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        info["json_contrato_bytes"] = sum(len(json_canonico(o.para_json())) + 1 for o in obs)
        info["observacao_para_json_s"] = time.perf_counter() - t0
        del obs
    return {"info": info, "parquet": str(pq), "jsonl": str(jl)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tamanhos", default="1000,10000,100000,1000000")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--manter-artefatos", action="store_true")
    args = ap.parse_args()
    tamanhos = [int(x) for x in args.tamanhos.split(",")]
    as_of = dados.as_of_padrao_us()
    th = args.threads

    resultado: dict = {"tamanhos": {}, "base": {}}
    resultado["base"]["vazio"] = rodar_com_rss("vazio", threads=th, reps=1)
    print("vazio", resultado["base"]["vazio"].get("pico_rss_mb"), flush=True)
    resultado["base"]["volc_atual"] = rodar_com_rss("volc_atual", threads=th, reps=args.reps)
    print("volc_atual", json.dumps(resultado["base"]["volc_atual"])[:400], flush=True)

    for n in tamanhos:
        prep = preparar(n)
        bloco = {"dados": prep["info"], "engines": {}}
        print(f"\n== n={n} linhas={prep['info']['n_linhas']} parquet={prep['info']['parquet_bytes']} "
              f"jsonl={prep['info']['jsonl_plano_bytes']}", flush=True)
        engines = ["python_puro", "duckdb", "polars"] + (["contrato"] if n <= LIMITE_CONTRATO else [])
        for e in engines:
            r = rodar_com_rss(e, threads=th, reps=args.reps, parquet=prep["parquet"], jsonl=prep["jsonl"], as_of=as_of)
            bloco["engines"][e] = r
            print(e, {k: (round(v["mediana_s"], 4) if isinstance(v, dict) and "mediana_s" in v else v)
                      for k, v in r.items() if k not in ("duckdb_config",)}, flush=True)
        if n >= 100_000:
            for e in ("duckdb", "polars"):
                r = rodar_com_rss(e, threads=1, reps=args.reps, parquet=prep["parquet"], jsonl=prep["jsonl"], as_of=as_of)
                bloco["engines"][f"{e}_1thread"] = r
                print(f"{e}_1thread", round(r.get("operacao", {}).get("mediana_s", -1), 4), r.get("pico_rss_mb"), flush=True)
        hashes = {k: v.get("resultado_sha256") for k, v in bloco["engines"].items()}
        bloco["equivalencia"] = {"hashes": hashes, "todas_iguais": len(set(hashes.values())) == 1 and None not in hashes.values()}
        print("equivalencia", bloco["equivalencia"]["todas_iguais"], flush=True)
        resultado["tamanhos"][str(n)] = bloco
        if not args.manter_artefatos:
            Path(prep["parquet"]).unlink(missing_ok=True)
            Path(prep["jsonl"]).unlink(missing_ok=True)

    manifesto = manifesto_execucao(
        nome="bench_duckdb_polars_v0", seed=SEED,
        entradas={f"parquet_{n}": b["dados"]["parquet_sha256"] for n, b in resultado["tamanhos"].items()},
        parametros={"tamanhos": tamanhos, "reps": args.reps, "threads": th, "as_of_us": as_of,
                    "duckdb_config": CONFIG_DUCKDB, "limite_contrato": LIMITE_CONTRATO, "timeout_s": TIMEOUT_S},
    )
    saida = {"natureza": "sintetico", "manifesto": manifesto, "maquina": _maquina(),
             "threads": {"OMP_NUM_THREADS": th, "POLARS_MAX_THREADS": th, "duckdb_threads": th, "extra": "1 thread em n>=1e5"},
             "resultado": resultado}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nsalvo", SAIDA, SAIDA.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
