"""Gera results/bench/BENCH-RESULTS.md a partir dos JSONs (nenhum número digitado à mão).

Uso (da raiz do lab): .venv/bin/python -I scripts/bench_relatorio.py
Lê results/bench/bench_resultados.json e results/bench/replay_escala.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parents[1]
BENCH = RAIZ / "results" / "bench" / "bench_resultados.json"
ESCALA = RAIZ / "results" / "bench" / "replay_escala.json"
SAIDA = RAIZ / "results" / "bench" / "BENCH-RESULTS.md"
TESTES = REPO / "tests" / "data-intelligence" / "test_bench_equivalencia.py"
ORDEM = ["python_puro", "contrato", "duckdb", "duckdb_1thread", "polars", "polars_1thread", "polars_de_tuplas"]


def ms(r: dict, k: str):
    return r[k]["mediana_s"] * 1000 if k in r else None


def f(x, casas=1) -> str:
    if x is None:
        return "–"
    if x >= 100:
        return f"{x:,.0f}".replace(",", " ")
    return f"{x:.{casas}f}"


def carga(r):
    return ms(r, "carga_jsonl") if "carga_jsonl" in r else ms(r, "carga_parquet")


def conv(r):
    return ms(r, "conversao_para_contrato") or ms(r, "conversao_tuplas_para_polars")


def total(r):
    return sum(x for x in (carga(r), conv(r), ms(r, "operacao"), ms(r, "exportacao")) if x)


def corte(tam: dict, motor: str, custo_motor, custo_py, *, com_import: bool) -> str:
    """Menor n da grade em que `motor` fica mais barato que python_puro (com faixa entre pontos)."""
    ns = sorted(tam, key=int)
    anterior = None
    for n in ns:
        e = tam[n]["engines"]
        if motor not in e or "python_puro" not in e:
            continue
        cm = custo_motor(e[motor]) + (e[motor]["import_s"] * 1000 if com_import else 0)
        cp = custo_py(e["python_puro"])
        if cm < cp:
            return f"entre {anterior} e {int(n):.0e}" if anterior else f"≤ {int(n):.0e}"
        anterior = f"{int(n):.0e}"
    return f"> {int(ns[-1]):.0e} (não atingido na grade)"


def main() -> int:
    j = json.loads(BENCH.read_text(encoding="utf-8"))
    esc = json.loads(ESCALA.read_text(encoding="utf-8"))
    res = j["resultado"]
    tam = res["tamanhos"]
    man = j["manifesto"]
    ver = man["versoes"]
    maq = j["maquina"]
    L: list[str] = []
    a = L.append
    n_testes = len(re.findall(r"^def test_", TESTES.read_text(encoding="utf-8"), flags=re.M))
    a("# Bancada DuckDB × Polars × Python puro × contrato (SINTÉTICO)\n")
    a("> **Gerado** por `scripts/bench_relatorio.py` a partir de `results/bench/bench_resultados.json` e "
      "`results/bench/replay_escala.json`; não editar à mão. Dados **sintéticos** (seed "
      f"`{man['seed']}`); mede a operação central do replay, não um workload real do VOLC.\n")
    a("- Execução: `.venv/bin/python -I scripts/bench_executar.py`, `scripts/bench_replay_escala.py`, depois `scripts/bench_relatorio.py`.")
    a(f"- Equivalência: `tests/data-intelligence/test_bench_equivalencia.py` ({n_testes} testes).")
    a(f"- Manifesto: `codigo_sha256={man['codigo_sha256'][:16]}…`, `resultado_sha256={man['resultado_sha256'][:16]}…`, "
      f"`fingerprint={man['fingerprint'][:16]}…`; escala: `codigo_sha256={esc['manifesto']['codigo_sha256'][:16]}…`, "
      f"`resultado_sha256={esc['manifesto']['resultado_sha256'][:16]}…`.\n")
    cfg = tam[max(tam, key=int)]["engines"]["duckdb"].get("duckdb_config", {})
    a(f"**Ambiente:** {maq['cpu']}, {maq['ncpu']} CPUs, {int(maq['memoria_bytes']) / 2**30:.0f} GiB, {maq['plataforma']}; "
      f"CPython {ver['python']}; duckdb {ver['duckdb']}, polars {ver['polars']}, numpy {ver['numpy']}, pandas "
      f"{ver['pandas']} (não usado), sem pyarrow. Threads: {json.dumps(j['threads'], ensure_ascii=False)}. DuckDB: "
      f"{json.dumps(cfg, ensure_ascii=False)}. Cada medição num subprocesso `python -I`; tempo = mediana de "
      f"{man['parametros']['reps']} repetições após 1 aquecimento (carga/conversão/exportação: mediana de 3, ou 2); "
      f"pico de RSS do próprio filho via `os.wait4`. Processo vazio: {res['base']['vazio']['pico_rss_mb']} MB.\n")

    a("## 1. A operação (igual nas quatro implementações)\n")
    a("0. validação de linha (estado×valor×moeda; todas recusam com `LinhaMalformada`); 1. corte `disponivel_em <= as_of`; "
      "2. reentrega idêntica deduplicada e contada, versões diferentes no mesmo instante → `EmpateDeVersao` (contrato: "
      "`VersaoAmbigua`); 3. agregação por conta × campanha × dia × métrica com a semântica do `agregar` (membro sem valor "
      "anula, pior estado vence, >1 moeda → `moedas_misturadas`, 0 → `zero_confirmado`); 4. join custo × receita por "
      "identidade exata, contribuição só com a mesma moeda (comparação NULL-segura).\n")
    a("Implementações: **contrato** (`Observacao` → `Snapshot.construir` → `agregar`), **python_puro** (tuplas + dicts), "
      "**duckdb** (SQL, resultado em tabela temporária), **polars** (lazy, `collect_all`, lendo Parquet) e "
      "**polars_de_tuplas** (mesma operação, mas partindo de tuplas Python em memória: paga a conversão).\n")

    a("## 2. Equivalência\n")
    a("| n alvo | linhas | linhas de resultado | sha256 do resultado | engines | todas iguais | duplicatas exatas |")
    a("|---:|---:|---:|---|---|---|---:|")
    for n in sorted(tam, key=int):
        b = tam[n]
        eng = b["engines"]
        nres = {r.get("n_linhas_resultado") for r in eng.values()}
        hs = {h for h in b["equivalencia"]["hashes"].values()}
        dups = {r.get("n_duplicatas_exatas") for r in eng.values() if r.get("n_duplicatas_exatas") is not None}
        a(f"| {int(n):.0e} | {b['dados']['n_linhas']} | {'/'.join(str(x) for x in sorted(nres))} | "
          f"`{next(iter(hs))[:16]}…` | {', '.join(k for k in ORDEM if k in eng)} | "
          f"{'sim' if b['equivalencia']['todas_iguais'] else '**NÃO**'} | {'/'.join(str(x) for x in sorted(dups))} |")
    a("")
    a("Fora do caminho feliz (testes `test_f103_*`): reentrega idêntica é deduplicada e dá a MESMA linha nas quatro "
      "engines (antes DuckDB/Polars somavam em dobro); versões diferentes no mesmo instante, micros com moeda nula, "
      "`medido` sem micros, `zero_confirmado` ≠ 0 e estado fora do vocabulário levantam a MESMA exceção nas quatro. "
      "A versão \"ingênua\" (soma crua: DuckDB e Polars ignoram NULL; Polars dá 0 para grupo todo nulo) é pega pelo hash.\n")

    a("## 3. Tempo, memória e tamanho\n")
    a("Tempos em ms (mediana). `carga` = JSONL→tuplas (python/contrato/polars_de_tuplas) ou Parquet→memória "
      "(duckdb/polars). `conv` = tuplas → objetos do contrato ou → DataFrame Polars. `import` é do processo frio e oscila "
      "com o cache de disco.\n")
    a("| n | engine | carga | conv | **operação** | export | total (carga+conv+op+export) | import | pico RSS (MB) |")
    a("|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for n in sorted(tam, key=int):
        eng = tam[n]["engines"]
        primeira = True
        for k in ORDEM:
            if k not in eng:
                continue
            r = eng[k]
            if "erro" in r:
                a(f"| {int(n):.0e} | {k} | erro: {r['erro'][:60]} |||||||")
                continue
            a(f"| {f'{int(n):.0e}' if primeira else ''} | {k} | {f(carga(r))} | {f(conv(r))} | **{f(ms(r, 'operacao'))}** | "
              f"{f(ms(r, 'exportacao'))} | {f(total(r))} | {f(r['import_s'] * 1000, 0)} | {r['pico_rss_mb']} |")
            primeira = False
    a("")
    a("| n | Parquet (zstd, writer do Polars) | JSONL plano | JSON do contrato (`para_json`) | tuplas → Polars (ms, 1 medição) |")
    a("|---:|---:|---:|---:|---:|")
    por_obs = None
    for n in sorted(tam, key=int):
        dd = tam[n]["dados"]
        if "json_contrato_bytes" in dd:
            por_obs = dd["json_contrato_bytes"] / dd["n_linhas"]
            jc = f"{dd['json_contrato_bytes'] / 1e6:.2f} MB"
        else:
            jc = f"~{por_obs * dd['n_linhas'] / 1e6:.0f} MB (inferido: {por_obs:.0f} B/obs)" if por_obs else "–"
        a(f"| {int(n):.0e} | {dd['parquet_bytes'] / 1e6:.3f} MB | {dd['jsonl_plano_bytes'] / 1e6:.2f} MB | {jc} | "
          f"{f(dd['tuplas_para_polars_s'] * 1000)} |")
    a("")

    a("**Onde o replay v0 gasta tempo** (`replay_escala.json`, 20 dias, política `proportional`, sem medição de "
      "preliminar, 1 repetição — ordem de grandeza):\n")
    a("| unidades | obs por snapshot (máx) | ms de `Snapshot.construir` por decisão | % do tempo em snapshot |")
    a("|---:|---:|---:|---:|")
    for p in esc["pontos"]:
        a(f"| {p['n_unidades']} | {p['obs_por_snapshot_max']} | {p['snapshot_ms_por_decisao']} | "
          f"{100 * p['snapshot_s'] / p['total_s']:.0f}% |")
    pf = esc["perfil_snapshot"]
    a(f"\nPerfil de `Snapshot.construir` em {pf['n_observacoes']} observações ({pf['construir_s']} s): "
      f"`sha256_de` {100 * pf['frac_sha256_de']:.0f}% e `para_json` {100 * pf['frac_para_json']:.0f}% do tempo cumulativo "
      f"({pf['nota']}); {pf['chamadas_para_json']} chamadas de `para_json` e {pf['chamadas_sha256_de']} de `sha256_de`.\n")

    # números para o veredito
    v = res["base"]["volc_atual"]
    grande = max((n for n in tam if "contrato" in tam[n]["engines"]), key=int)
    eg = tam[grande]["engines"]
    razao_contrato = ms(eg["contrato"], "operacao") / ms(eg["python_puro"], "operacao")
    nmax = max(tam, key=int)
    em = tam[nmax]["engines"]
    sp_pol = ms(em["python_puro"], "operacao") / ms(em["polars"], "operacao")
    sp_duck = ms(em["python_puro"], "operacao") / ms(em["duckdb"], "operacao")
    sp_tup = ms(em["python_puro"], "operacao") / (conv(em["polars_de_tuplas"]) + ms(em["polars_de_tuplas"], "operacao")
                                                 + ms(em["polars_de_tuplas"], "exportacao"))
    imports_duck = [r["import_s"] * 1000 for b in tam.values() for k, r in b["engines"].items() if k.startswith("duckdb")]
    imports_pol = [r["import_s"] * 1000 for b in tam.values() for k, r in b["engines"].items() if k.startswith("polars")]
    def op_py(r): return ms(r, "operacao")
    def mem_tup(r): return conv(r) + ms(r, "operacao") + ms(r, "exportacao")
    def repouso_py(r): return carga(r) + ms(r, "operacao")
    def repouso_eng(r): return carga(r) + ms(r, "operacao") + ms(r, "exportacao")

    a("## 4. Veredito: \"DuckDB + Polars melhoram de fato o replay atual?\"\n")
    a(f"**Replay atual do VOLC (cenários dourados) — não.** `executar_replay()` = {ms(v, 'executar_replay'):.1f} ms "
      f"(mediana), import {v['import_s'] * 1000:.0f} ms, `normalizar_linhas_google_ads` com {v['linhas_normalizadas']} linhas "
      f"= {ms(v, 'normalizar_linhas_google_ads'):.2f} ms; processo inteiro {v['parede_subprocesso_s'] * 1000:.0f} ms, "
      f"{v['pico_rss_mb']} MB. Só importar DuckDB custou {min(imports_duck):.0f}–{max(imports_duck):.0f} ms e Polars "
      f"{min(imports_pol):.0f}–{max(imports_pol):.0f} ms nesta bancada. Não há volume nem álgebra relacional ali.\n")
    a("**Replay econômico em volume — depende do tamanho, e o primeiro gargalo não é a engine:**\n")
    a(f"1. O caminho do **contrato** é {razao_contrato:.0f}× mais lento que tuplas Python na mesma operação em "
      f"{int(grande):.0e} ({f(ms(eg['contrato'], 'operacao'))} × {f(ms(eg['python_puro'], 'operacao'))} ms), e "
      "`Snapshot.construir` domina o replay v0 (tabela acima). Acima de "
      f"{int(grande):.0e} o contrato não foi rodado (estouraria o orçamento de tempo/memória — inferido por extrapolação linear).")
    a(f"2. Em {int(nmax):.0e}, na operação: Polars (Parquet) {sp_pol:.1f}× e DuckDB {sp_duck:.1f}× mais rápidos que "
      f"Python puro. Se os dados já estão em tuplas Python (caso do replay), Polars incluindo conversão + exportação fica "
      f"{sp_tup:.1f}× {'mais rápido' if sp_tup > 1 else 'mais LENTO'} que Python puro.")
    a("3. **Pontos de corte** (menor tamanho da grade em que a engine fica mais barata que Python puro):\n")
    a("| Cenário | Polars | DuckDB |")
    a("|---|---|---|")
    a(f"| dados em tuplas Python, processo longo (conv+op+export vs op) | {corte(tam, 'polars_de_tuplas', mem_tup, op_py, com_import=False)} | – (sem leitor direto de tuplas sem pyarrow/pandas) |")
    a(f"| idem, processo novo (+ import) | {corte(tam, 'polars_de_tuplas', mem_tup, op_py, com_import=True)} | – |")
    a(f"| dados em repouso (Parquet vs JSONL), processo longo | {corte(tam, 'polars', repouso_eng, repouso_py, com_import=False)} | {corte(tam, 'duckdb', repouso_eng, repouso_py, com_import=False)} |")
    a(f"| idem, processo novo (+ import) | {corte(tam, 'polars', repouso_eng, repouso_py, com_import=True)} | {corte(tam, 'duckdb', repouso_eng, repouso_py, com_import=True)} |")
    a("")
    maxobs = max(p["obs_por_snapshot_max"] for p in esc["pontos"])
    a(f"Os snapshots do replay v0 medidos têm até {maxobs} observações; a decisão sobre adotar uma engine deve usar a "
      "linha \"dados em tuplas Python\" (o replay mantém o log em memória), não a de Parquet. O ganho mais barato e "
      "certo é reduzir o custo do `Snapshot` (pedido 1, §6).\n")

    a("**Riscos registrados:**\n")
    for x in [
        "NULL em `SUM`/`sum()` (ambas ignoram; Polars dá 0 para grupo todo nulo); comparação `<>` com NULL é lógica de 3 valores — o plano usa `count`/`null_count`, `IS DISTINCT FROM` e `ne_missing`.",
        "Reentrega duplicada é somada em dobro por um GROUP BY ingênuo — o plano faz `DISTINCT`/`unique()` e conta; versões diferentes no mesmo instante levantam.",
        "`row_number()`/`unique(keep=...)` com empate é não determinístico — o plano não escolhe, recusa.",
        "Overflow: Polars soma `Int64` em `Int64`; DuckDB promove para `HUGEINT` (cast explícito para `BIGINT`).",
        "DuckDB não lê DataFrame Polars sem pyarrow — a troca entre as engines é por Parquet.",
        "`memory_limit` padrão do DuckDB (80% da RAM) num Mac compartilhado: fixar se adotado. Autoload/autoinstall desligados e verificados.",
        "Ambiente paralelo `tools/freedom-lab/`: duckdb 1.5.6 (igual) mas **polars 2.0.0** e CPython 3.14 (`tools/freedom-lab/DEPENDENCIAS.json`). O plano usa `join(how=\"full\", coalesce=True, nulls_equal=False)`, `replace_strict`, `ne_missing`, `unique()` — não testado em polars 2.0; tempos não são transferíveis.",
        "pandas não medido.",
    ]:
        a(f"- {x}")
    a("")
    picos = max(b["dados"]["parquet_bytes"] + b["dados"]["jsonl_plano_bytes"] for b in tam.values())
    a("## 5. Disco\n")
    a(f"Pico de artefatos simultâneos ≈ {picos / 1e6:.0f} MB (Parquet + JSONL do maior tamanho; cada tamanho é apagado "
      "antes do próximo) em `artifacts/bench/` (gitignored); tudo apagado ao fim. Versionado: só JSON/MD de resultado.\n")
    a("## 6. Pedidos de mudança no contrato (não aplicados)\n")
    for x in [
        "`Snapshot.construir`: hashear conteúdo só quando há empate e reaproveitar um único `sha256`/`para_json` por observação para ordenar e para o fingerprint (ver perfil acima).",
        "`contribuicao` entre `Agregado`s com identidade/janela explícitas (a bancada reimplementa o join em `engines._juntar`).",
        "Moeda esperada da unidade declarada (observação sem valor tem `moeda=None` e não pode ser atribuída a um grupo de moeda).",
        "`medido` com valor 0 é aceito no lab e recusado no Orakul (`semantica.py:69`) — alinhar.",
    ]:
        a(f"- {x}")
    SAIDA.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("escrito", SAIDA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
