"""Replay `as_of` + shadow engine da Fundação DIL (thread D): sintético, simulador ou linhas reais exportadas.

Modos (todos SEM rede e SEM escrita fora do diretório de saída):

  --sintetico            gerador provisório (6 cenários), replay horário, avaliação contrafactual, ledgers
  --simulador            Simulator Lab da thread E (se presente no checkout), cenários do catálogo
  --verificar            regenera o --sintetico em memória e compara o sha determinístico com o JSON gravado
  --linhas-v21 P --linhas-joinads P --saida DIR
                         DADO REAL exportado read-only (JSONL da junção de 02 §9): adapta, deduplica,
                         roda o replay horário e grava SÓ `DIR/ledger.jsonl` e `DIR/resumo.json`.
                         Nunca executado nesta missão (exportação depende de autorização do operador).

Saídas do modo sintético/simulador: `results/fundacao/shadow/{shadow_resultados.json, SHADOW-RESULTS.md}`
(com o sha256 de cada ledger); os ledgers JSONL só são gravados com `--ledgers DIR` (~9 MB por cenário).
A parte determinística do JSON exclui tempos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

RAIZ_LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_LAB / "src"))

from volc_dil.contracts.fingerprint import sha256_de  # noqa: E402
from volc_dil.fundacao.shadow import _gerador_provisorio as gp  # noqa: E402
from volc_dil.fundacao.shadow.avaliacao import avaliar, registrar_resultados_maduros  # noqa: E402
from volc_dil.fundacao.shadow.controles import PoliticaTrapaceira  # noqa: E402
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado  # noqa: E402
from volc_dil.fundacao.shadow.ledger import LedgerShadow, SinkJsonl  # noqa: E402
from volc_dil.fundacao.shadow.motor import ConfigShadow, auditar_null_zero, detectar_vazamento, executar_replay  # noqa: E402
from volc_dil.fundacao.shadow.politicas import Manter, RegraMargem, catalogo_padrao, regra_margem_null_zero  # noqa: E402
from volc_dil.fundacao.shadow.snapshot import ConfigCorte, construir_snapshot  # noqa: E402
from volc_dil.fundacao.shadow.versao import versao_codigo  # noqa: E402

SAIDA_PADRAO = RAIZ_LAB / "results" / "fundacao" / "shadow"
HORA_DECISAO = 7
SEED = 20261016
CENARIOS_SIMULADOR = ("estavel", "campanha_nova_aprendendo", "atraso_receita_longo", "restatement_custo",
                      "fonte_fora_do_ar", "zero_falso", "zero_sintetizado_coletor", "identidade_trocada",
                      "moeda_misturada", "vazamento_tentado", "custo_d0_multiversao", "execucao_presa",
                      "gatilho_legado_joinads")


def _rodar(fs, cortes, cfg, dir_ledger: Path | None, nome_ledger: str, hora: int) -> dict:
    fi = FluxoIndexado(fs.observacoes, ambiguidade="quarentena")
    led = LedgerShadow(SinkJsonl(dir_ledger, nome_ledger)) if dir_ledger is not None else LedgerShadow()
    t0 = time.perf_counter()
    res = executar_replay(fi, cortes, catalogo_padrao(), config=cfg, seed=fs.seed, ledger=led)
    t_replay = time.perf_counter() - t0
    n_res = registrar_resultados_maduros(led, res, fi, cfg, hora_decisao=hora, k_dias=4, verdade=fs.verdade)
    t1 = time.perf_counter()
    av = avaliar(res, fs.verdade, hora_decisao=hora, fuso=cfg.corte.fuso)
    t_av = time.perf_counter() - t1
    return {
        "deterministico": {"cenario": fs.nome, "seed": fs.seed, "meta": fs.meta, "n_observacoes": len(fs.observacoes),
                           "n_cortes": len(cortes), "n_decisoes": len(res.decisoes), "n_resultados_maduros": n_res,
                           "decisoes_sha256": res.sha256(), "ledger_sha256": led.sha256(), "ledger_entradas": len(led),
                           "avaliacao": av},
        "tempos": {"replay_s": round(t_replay, 3), "ms_por_corte_todas_politicas": round(1000 * t_replay / max(1, len(cortes)), 2),
                   "avaliacao_s": round(t_av, 3)},
    }


def _gates_sinteticos() -> dict:
    """Contraprovas resumidas para o relatório (os testes são a prova; aqui só os números)."""
    import dataclasses
    from datetime import date

    fs, cortes, cfg = gp.preparar("base", passo_horas=6, hora_inicial=7)
    t_inj = cortes[len(cortes) // 2] + timedelta(minutes=30)
    finais = {}
    for o in fs.observacoes:
        if (o.fonte == "joinads" and o.entidade.tipo == "campaign" and o.entidade.id == "24000000000" and o.valor
                and dict(o.dimensoes).get("revenue_basis") == "client" and date(2026, 9, 4) <= o.janela_inicio.date() < date(2026, 9, 10)):
            d = o.janela_inicio.date()
            if d not in finais or o.available_at > finais[d].available_at:
                finais[d] = o
    inj = []
    for o in finais.values():
        h = hashlib.sha256(f"inj:{o.chave_natural}".encode()).hexdigest()
        inj.append(dataclasses.replace(o, valor=max(10_000, o.valor // 10 // 10_000 * 10_000), payload_sha256=h,
                                       payload_ref=f"inj:{h}", observed_at=t_inj, available_at=t_inj, ingested_at=t_inj))
    honestas = [RegraMargem(), Manter()]
    vaz = detectar_vazamento(fs.observacoes, inj, honestas + [PoliticaTrapaceira(tuple(fs.observacoes))], cortes, config=cfg,
                             politicas_injetadas=honestas + [PoliticaTrapaceira(tuple(fs.observacoes) + tuple(inj))])
    fz, cz, cfgz = gp.preparar("zero_sintetizado", passo_horas=24, hora_inicial=7)
    fi = FluxoIndexado(fz.observacoes)
    snaps = [construir_snapshot(fi, t, cfgz.corte) for t in cz]
    aud = {p.nome: auditar_null_zero(p, snaps) for p in (Manter(), RegraMargem(), regra_margem_null_zero())}
    return {"vazamento": {k: {"cortes_antes": v["cortes_antes"], "alterados_antes": len(v["antes"]),
                              "cortes_depois": v["cortes_depois"], "alterados_depois": len(v["depois"]), "vazou": v["vazou"]}
                          for k, v in vaz.items()},
            "auditoria_null_zero": aud}


def modo_sintetico(dir_led: Path | None) -> dict:
    if dir_led is not None:
        dir_led.mkdir(parents=True, exist_ok=True)
        for f in dir_led.glob("provisorio__*.jsonl"):
            f.unlink()
    out = {}
    for nome in gp.cenarios_provisorios():
        fs, cortes, cfg = gp.preparar(nome, passo_horas=1, dia_inicial=5)
        out[nome] = _rodar(fs, cortes, cfg, dir_led, f"provisorio__{nome}.jsonl", HORA_DECISAO)
    return out


def modo_simulador(dir_led: Path | None, cenarios, n_campanhas: int, n_dias: int) -> dict:
    from volc_dil.fundacao.shadow.fonte_simulador import cortes_do_simulador, fluxo_do_simulador

    if dir_led is not None:
        dir_led.mkdir(parents=True, exist_ok=True)
        for f in dir_led.glob("simulador__*.jsonl"):
            f.unlink()
    out = {}
    for nome in cenarios:
        fs = fluxo_do_simulador(nome, SEED, n_campanhas=n_campanhas, n_dias=n_dias)
        cfg = ConfigShadow(ConfigCorte(cambios=fs.cambios))
        cortes = cortes_do_simulador(fs, dia_inicial=5)
        out[nome] = _rodar(fs, cortes, cfg, dir_led, f"simulador__{nome}.jsonl", HORA_DECISAO)
    return out


def _md(res: dict) -> str:
    def m(x):
        return "—" if x is None else f"{x / 1_000_000:,.0f}".replace(",", ".")

    linhas = ["# Shadow engine — resultados (TESTADO COM SINTÉTICO)", "",
              "> **Gerado** por `scripts/fundacao_shadow.py` a partir de `shadow_resultados.json`; não editar à mão.",
              "> **Natureza:** gerador provisório e/ou Simulator Lab (thread E). Lucro contrafactual vem da VERDADE do",
              "> gerador. Nada aqui é eficácia, calibração ou validação com dado real.", "",
              f"- versão do código (provisório): `{res.get('versao_codigo', '')[:16]}…`; (simulador): "
              f"`{res.get('versao_codigo_simulador', '')[:16]}…`; sha determinístico: `{res['deterministico_sha256'][:16]}…`",
              f"- decisão diária às {HORA_DECISAO}h (America/Sao_Paulo), aplicada ao dia seguinte; menu do oráculo: manter, reduzir 30%, pausar",
              "- valores em BRL (micros ÷ 10⁶), arredondados; `vs manter` positivo = ganharia contra não fazer nada", ""]
    for fonte in ("provisorio", "simulador"):
        bloco = res.get(fonte)
        if not bloco:
            continue
        linhas += [f"## Fonte: {fonte}", ""]
        for nome, r in bloco.items():
            d, t = r["deterministico"], r["tempos"]
            av = d["avaliacao"]
            linhas += [f"### {nome}", "",
                       f"{d['n_observacoes']} observações, {d['n_cortes']} cortes horários, {d['n_decisoes']} decisões, "
                       f"{d['n_resultados_maduros']} resultados maduros no ledger (`{d['ledger_sha256'][:12]}…`); "
                       f"{t['ms_por_corte_todas_politicas']} ms/corte (8 políticas). Lucro de `manter`: {m(av['lucro_manter_micros'])}.", "",
                       "| política | vs manter | vs equal | regret | drawdown | cortes | errados | errados (imaturo) | bloqueadas | trocas entre cortes |",
                       "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
            for pol, v in av["politicas"].items():
                linhas.append(f"| {pol} | {m(v['vs_manter_micros'])} | {m(v.get('vs_equal_micros'))} | {m(v['regret_vs_oraculo_micros'])} | "
                              f"{m(v['drawdown_max_vs_manter_micros'])} | {v['cortes_executaveis_em_tese']} | {v['cortes_errados']} | "
                              f"{v['cortes_errados_por_sinal_imaturo']} | {v['propostas_bloqueadas_no_corte_diario']} | "
                              f"{v['estabilidade']['fracao_trocas']} |")
            linhas.append("")
    g = res.get("gates")
    if g:
        linhas += ["## Contraprovas (resumo; a prova são os testes `test_shadow_*`)", "",
                   "| política | cortes antes da injeção | alterados antes | cortes depois | alterados depois | vazou? |", "|---|---:|---:|---:|---:|---|"]
        for p, v in g["vazamento"].items():
            linhas.append(f"| {p} | {v['cortes_antes']} | {v['alterados_antes']} | {v['cortes_depois']} | {v['alterados_depois']} | {'**sim**' if v['vazou'] else 'não'} |")
        linhas += ["", "| política | snapshots com lacuna | distingue null de zero | sensível a valores | cega | suspeita null→0 |", "|---|---:|---:|---:|---|---|"]
        for p, v in g["auditoria_null_zero"].items():
            linhas.append(f"| {p} | {v['snapshots_com_lacuna']} | {v['decisoes_que_distinguem_null_de_zero']} | {v['decisoes_sensiveis_a_valores']} | "
                          f"{v['cega_a_dados']} | {'**sim**' if v['suspeita_null_como_zero'] else 'não'} |")
    return "\n".join(linhas) + "\n"


def _deterministico(res: dict) -> dict:
    return {k: ({n: r["deterministico"] for n, r in v.items()} if k in ("provisorio", "simulador") else v)
            for k, v in res.items() if k in ("provisorio", "simulador", "gates", "versao_codigo", "versao_codigo_simulador")}


def modo_real(a) -> int:
    from volc_dil.fundacao.shadow.real import carregar_jsonl, replay_de_linhas_reais
    from volc_dil.fundacao.shadow.snapshot import CambioDeclarado

    saida = Path(a.saida).resolve()
    saida.mkdir(parents=True, exist_ok=True)
    cambios = ()
    if a.cambio_usd_brl:
        num, _, den = a.cambio_usd_brl.partition("/")
        cambios = (CambioDeclarado("USD", "BRL", int(num), int(den or 1), "declarado:operador"),)
    cfg = ConfigShadow(ConfigCorte(cambios=cambios))
    adapt, res, led = replay_de_linhas_reais(carregar_jsonl(a.linhas_v21), carregar_jsonl(a.linhas_joinads),
                                             politicas=catalogo_padrao(), config=cfg, diretorio_ledger=saida, seed=None)
    resumo = {"natureza": "testado_em_replay (dado real exportado read-only)", "versao_codigo": versao_codigo(),
              "adaptacao": adapt.resumo(), "n_cortes": len(res.cortes), "n_decisoes": len(res.decisoes),
              "decisoes_sha256": res.sha256(), "ledger_sha256": led.sha256(), "config": cfg.para_json()}
    (saida / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: resumo[k] for k in ("n_cortes", "n_decisoes", "decisoes_sha256", "ledger_sha256")}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--simulador", action="store_true")
    ap.add_argument("--cenarios", nargs="*", default=list(CENARIOS_SIMULADOR))
    ap.add_argument("--n-campanhas", type=int, default=8)
    ap.add_argument("--n-dias", type=int, default=16)
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--saida", default=None)
    ap.add_argument("--ledgers", default=None, help="diretório para gravar os ledgers JSONL (~9 MB por cenário); "
                    "sem ele, só os sha256 entram no resultado")
    ap.add_argument("--linhas-v21")
    ap.add_argument("--linhas-joinads")
    ap.add_argument("--cambio-usd-brl", help="taxa declarada pelo operador como fração, ex.: 27/5 (= 5,40)")
    a = ap.parse_args()
    if a.linhas_v21 or a.linhas_joinads:
        if not (a.linhas_v21 and a.linhas_joinads and a.saida):
            ap.error("modo real exige --linhas-v21, --linhas-joinads e --saida")
        return modo_real(a)
    saida = Path(a.saida).resolve() if a.saida else SAIDA_PADRAO
    arq = saida / "shadow_resultados.json"
    if a.verificar:
        gravado = json.loads(arq.read_text())
        novo = {"provisorio": modo_sintetico(None), "gates": _gates_sinteticos(), "versao_codigo": versao_codigo()}
        esperado = sha256_de(_deterministico({k: gravado[k] for k in ("provisorio", "gates", "versao_codigo")}))
        obtido = sha256_de(_deterministico(novo))
        print(f"esperado {esperado}\nobtido   {obtido}")
        return 0 if esperado == obtido else 1
    saida.mkdir(parents=True, exist_ok=True)
    res = json.loads(arq.read_text()) if arq.exists() else {}
    dir_led = Path(a.ledgers).resolve() if a.ledgers else None
    if a.sintetico:
        res["versao_codigo"] = versao_codigo()
        res["provisorio"] = modo_sintetico(dir_led)
        res["gates"] = _gates_sinteticos()
    if a.simulador:
        # pode rodar noutra árvore (com o simulador da E): a versão do código fica registrada à parte
        res["versao_codigo_simulador"] = versao_codigo()
        res["simulador"] = modo_simulador(dir_led, a.cenarios, a.n_campanhas, a.n_dias)
    res["deterministico_sha256"] = sha256_de(_deterministico(res))
    arq.write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    (saida / "SHADOW-RESULTS.md").write_text(_md(res))
    print(f"gravado {arq} (sha determinístico {res['deterministico_sha256'][:16]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
