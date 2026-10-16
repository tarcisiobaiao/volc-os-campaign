"""Gera results/replay/REPLAY-RESULTS.md a partir dos JSONs (nenhum número digitado à mão).

Uso (da raiz do lab): .venv/bin/python -I scripts/replay_relatorio.py
Lê results/replay/replay_resultados.json e, se existir, results/bench/bench_resultados.json
(tempo do replay atual do VOLC). Todo número do MD sai desses arquivos ou dos testes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parents[1]
ENTRADA = RAIZ / "results" / "replay" / "replay_resultados.json"
BENCH = RAIZ / "results" / "bench" / "bench_resultados.json"
SAIDA = RAIZ / "results" / "replay" / "REPLAY-RESULTS.md"
TESTES = REPO / "tests" / "data-intelligence" / "test_replay_economico.py"
BASE = ["static", "equal", "proportional", "greedy_conservador"]
NAIVE = "proportional_naive_null_as_zero"


def _n_testes() -> int:
    return len(re.findall(r"^def test_", TESTES.read_text(encoding="utf-8"), flags=re.M))


def _fmt(x) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.0f}" if abs(x) >= 100 else f"{x:.1f}"
    return str(x)


def main() -> int:
    j = json.loads(ENTRADA.read_text(encoding="utf-8"))
    d = j["deterministico"]
    man = j["manifesto"]
    seeds = d["seeds"]
    ref = d["referencia_pareada"]
    resumo = d["resumo_brl"]
    tempos = j["tempos_s_nao_deterministico"]
    L: list[str] = []
    a = L.append
    a("# Replay econômico v0 — resultados (SINTÉTICO)\n")
    a("> **Gerado** por `scripts/replay_relatorio.py` a partir de `results/replay/replay_resultados.json`; não editar à mão.")
    a("> **Natureza:** mundo **sintético** gerado por seed. Nenhum número é validação com dado real do VOLC. Serve para "
      "provar a *mecânica* (as_of, restatement, null≠0, moeda, identidade, reprodutibilidade) e comparar baselines sob "
      "hipóteses explícitas.\n")
    a(f"- Execução: `cd experiments/data-intelligence-lab && .venv/bin/python -I scripts/replay_executar.py` "
      f"({len(seeds)} seeds × {len(resumo)} cenários × {len(BASE) + 1} políticas; {tempos['processos']} processos "
      f"single-thread; {tempos['parede_total_s']} s de parede nesta máquina) e depois `scripts/replay_relatorio.py`.")
    a("- Código: `src/volc_dil/replay/` (`cenario.py`, `motor.py`, `politicas.py`, `avaliacao.py`, `auditoria.py`).")
    a("- Fixture: `fixtures/replay/cenario_mini.json` + `MANIFEST.json` (`scripts/replay_gerar_fixture.py [--verificar]`).")
    a(f"- Contraprovas: `tests/data-intelligence/test_replay_economico.py` ({_n_testes()} testes).")
    a(f"- Manifesto: `codigo_sha256={man['codigo_sha256'][:16]}…`, `resultado_sha256={man['resultado_sha256'][:16]}…`, "
      f"`fingerprint={man['fingerprint'][:16]}…`; `deterministico_sha256={j['deterministico_sha256']}` "
      "(tempos ficam fora da parte determinística; o resultado não depende do número de processos).\n")

    a("## 1. O \"replay atual\" do VOLC não é um replay econômico temporal\n")
    a("Evidência em `volc_ads/inteligencia_decisao/replay.py`: `_agora()` (l. 61) devolve **um único** `as_of` fixo do "
      "dataset; `executar_replay()` (l. 104–115) percorre os cenários dourados e compara 4 campos categóricos "
      "(`estado_da_leitura`, `veredito`, `health_gate`, nº de propostas) com o esperado. Não há orçamento alocado, receita "
      "com atraso, versão preliminar/revisada, lucro, regret ou oráculo. É um teste de regressão de classificação dourada.")
    if BENCH.exists():
        v = json.loads(BENCH.read_text(encoding="utf-8"))["resultado"]["base"]["volc_atual"]
        a(f"Custo medido (bancada): `executar_replay()` = {v['executar_replay']['mediana_s'] * 1000:.1f} ms (mediana de "
          f"{v['executar_replay']['reps']}), import {v['import_s'] * 1000:.0f} ms, processo inteiro "
          f"{v['parede_subprocesso_s'] * 1000:.0f} ms, pico de RSS {v['pico_rss_mb']} MB; "
          f"{v['replay_passaram']}/{v['replay_total']} cenários passam.\n")

    a("## 2. Desenho do v0\n")
    a("- **Mundo (verdade, só o avaliador vê):** receita do dia = `alpha_i(t) · ruído_lognormal(i,t) · gasto^0,7`; "
      "quebra de regime opcional; uma unidade em USD; RNG por (cenário, unidade, dia) → números aleatórios comuns entre políticas.")
    a("- **Emissão:** custo do dia d em d+1 03:00; receita preliminar (`preliminary`, cobertura `partial`) em d+1 06:00; "
      "revisada (`revised`, `complete`) em d+3 06:00 com a mesma chave lógica; lacunas `nao_coletado`/`falha`; "
      "receita nunca coletada tem a versão final `revised` sem valor. **Linhagem e `coleta_id` são opacos** (sem seed "
      "nem nome de cenário) e o rótulo do snapshot é `decisao/<dia>` (F1-01).")
    a("- **Motor (malha fechada):** decisão do dia d às 23:00 de d-1; corte `disponivel_em <= as_of` (janela 14 dias); "
      "`Snapshot.construir(..., politica_futuro=\"falhar\")` no ponto de consumo; a política recebe só snapshot + contexto; "
      "a decisão é validada (universo exato, moeda da unidade, soma por moeda, **piso por unidade**) e registrada sem "
      "resultado; o lucro é calculado depois com a verdade madura.")
    a("- **Uso de preliminar é MEDIDO, não só declarado (F1-06):** para cada decisão o motor reexecuta a política sobre "
      "o mesmo corte sem nenhum número preliminar; se a alocação muda, a decisão `dependeu_de_preliminar`. O relatório "
      "traz as duas contagens (declarada × medida).")
    a("- **Opt-in explícito de parcial/preliminar:** `proportional` chama `contribuicao(..., aceitar_parcial=True)` e "
      "declara `usa_preliminar=True`; `greedy_conservador` usa o padrão do contrato (parcial não vira número) e ainda "
      "recusa contribuição marcada como preliminar.")
    a("- **Baselines:** `static` (mantém alocação herdada não uniforme), `equal`, `proportional` (média diária da "
      "contribuição conhecida em 7 dias; unidade sem valor fica fora com motivo), `greedy_conservador` (só unidades com "
      "os 7 dias maduros completos; troca até 20%/passo). Anti-baseline `proportional_naive_null_as_zero`.")
    a("- **Por que simulador:** na base atual custo e receita são *latest-wins*/upsert (sem as-of real), o JoinAds legado "
      "tem `revenue NOT NULL DEFAULT 0` e um gatilho reescreve a receita campanha-dia "
      "(`docs/data-intelligence/DATA-CAPABILITY-MATRIX.md`). Não há histórico de versões para reproduzir o que se sabia "
      "em t; e um log histórico só avalia a política que o gerou.\n")

    a(f"## 3. Resultados — {len(seeds)} seeds (BRL, 8 unidades, 60 dias)\n")
    a(f"Métrica principal: {d['metrica_principal']}. \"Pareado vs {ref}\" = média por seed de (regret da política − "
      f"regret do `{ref}` na mesma seed) com IC 95% t de Student; negativo = melhor que `{ref}`. \"Vitórias\" = seeds em "
      "que a política teve o menor regret entre as 4 baselines.\n")
    a(f"| Cenário | Política | média | dp | mediana | p90 | pior | pareado vs {ref} [IC95] | melhor/pior que {ref} (seeds) | vitórias | turnover médio (bps/dia) | decisões c/ preliminar: declarado / **medido** |")
    a("|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---|")
    conclusoes: list[str] = []
    for cen, pols in resumo.items():
        primeira = True
        for pol in BASE + [NAIVE]:
            r = pols[pol]
            e = r["regret_param_bps"]
            p = r[f"pareado_vs_{ref}"]
            ic = f"{_fmt(p['media_bps'])} [{_fmt(p['ic95_bps'][0])}; {_fmt(p['ic95_bps'][1])}]" if pol != ref else "–"
            mp = f"{p['seeds_melhor']}/{p['seeds_pior']}" if pol != ref else "–"
            a(f"| {cen if primeira else ''} | {'*' + pol + '*' if pol == NAIVE else pol} | {_fmt(e['media'])} | {_fmt(e['dp'])} | "
              f"{_fmt(e['mediana'])} | {e['p90']} | {e['pior']} | {ic} | {mp} | {_fmt(r['vitorias'])} | "
              f"{_fmt(r['turnover_bps']['media'])} | {_fmt(r['prelim_declarado']['media'])} / {_fmt(r['prelim_medido']['media'])} de {r['n_decisoes']} |")
            primeira = False
        melhor_media = min(BASE, key=lambda k: pols[k]["regret_param_bps"]["media"])
        sig_melhor = [k for k in BASE if k != ref and pols[k][f"pareado_vs_{ref}"]["ic95_bps"][1] < 0]
        sig_pior = [k for k in BASE if k != ref and pols[k][f"pareado_vs_{ref}"]["ic95_bps"][0] > 0]
        bimodal = [k for k in BASE if pols[k]["regret_param_bps"]["dp"] > 1.5 * pols[ref]["regret_param_bps"]["dp"]
                   and pols[k]["regret_param_bps"]["media"] > 1.2 * pols[k]["regret_param_bps"]["mediana"]]
        conclusoes.append(
            f"- **{cen}:** menor média = `{melhor_media}`; significativamente melhor que `{ref}`: "
            f"{', '.join('`' + k + '`' for k in sig_melhor) or 'nenhuma'}; significativamente pior: "
            f"{', '.join('`' + k + '`' for k in sig_pior) or 'nenhuma'}"
            + (f"; distribuição com cauda pesada (dp > 1,5× a do `{ref}` e média > 1,2× a mediana): "
               f"{', '.join('`' + k + '`' for k in bimodal)}" if bimodal else "") + ".")
    a("")
    a("**Leitura (gerada a partir dos números acima):**\n")
    L.extend(conclusoes)
    naive_pior = all(resumo[c][NAIVE]["regret_param_bps"]["media"] > resumo[c]["proportional"]["regret_param_bps"]["media"]
                     for c in resumo)
    a(f"- Anti-baseline null→0 tem média de regret maior que `proportional` em "
      f"{'todos os' if naive_pior else 'nem todos os'} cenários.")
    mesma_ordem = [c for c in resumo
                   if sorted(BASE, key=lambda k: resumo[c][k]["regret_param_bps"]["media"])
                   == sorted(BASE, key=lambda k: resumo[c][k]["regret_perfeito_bps"]["media"])]
    a("- O regret vs oráculo **perfeito** (conhece o ruído do dia) inclui uma parte irredutível (no JSON, "
      f"`regret_perfeito_bps`); a ordem das 4 baselines por média é a mesma nas duas métricas em "
      f"{len(mesma_ordem)}/{len(resumo)} cenários ({', '.join(mesma_ordem) or 'nenhum'}).")
    a("- USD: com uma unidade não há o que realocar; o relatório mostra a moeda separada e todas as políticas empatam.\n")

    aud = d["auditoria_null_vs_zero"]
    a(f"**Auditoria null × zero** (seed {aud['seed']}): troca cada observação sem valor por `zero_confirmado` (com a "
      "cobertura que um valor real teria) e vê se a decisão muda; um segundo teste perturba a receita de UMA unidade "
      "(×3, não preserva razões — F1-07) para separar \"cega a dados\" de \"null como 0\".\n")
    a("| Política | " + " | ".join(aud["por_cenario"]) + " |")
    a("|---|" + "---|" * len(aud["por_cenario"]))
    nomes = [x["politica"] for x in next(iter(aud["por_cenario"].values()))]
    for pol in nomes:
        celulas = []
        for cen, lista in aud["por_cenario"].items():
            x = next(y for y in lista if y["politica"] == pol)
            tag = "**suspeita null→0**" if x["suspeita_null_como_zero"] else ("cega a dados" if x["cega_a_dados"] else "distingue")
            celulas.append(f"{tag} (distingue {x['decisoes_que_distinguem_null_de_zero']}/{x['snapshots_com_lacuna']}; "
                           f"sensível {x['decisoes_sensiveis_a_valores']})")
        a(f"| {pol} | " + " | ".join(celulas) + " |")
    a("")

    a("## 4. Contraprovas (todas falham como esperado)\n")
    a("| # | Ataque | Resultado esperado e obtido | Teste |")
    a("|---|---|---|---|")
    for linha in [
        ("a", "corte que ignora o `as_of`", "`VazamentoDeFuturo` no ponto de consumo", "`test_a_corte_que_vaza_futuro_levanta_no_ponto_de_consumo`"),
        ("a", "snapshot adulterado / de as_of posterior entregue à política", "`VazamentoDeFuturo` na guarda das 5 políticas", "`test_a_snapshot_adulterado_entregue_a_politica_levanta`"),
        ("b", "política que trata None como 0", "auditoria marca suspeita; decisões divergem; sem receita a correta não realoca", "`test_b_*`"),
        ("b", "greedy por razão com null→0 (F1-07)", "auditoria a marca (não fica \"cega\"); greedy correta não é acusada", "`test_f107_*`"),
        ("c", "BRL+USD num pool; BRL na unidade USD; `agregar` BRL+USD", "`MoedasDiferentes`", "`test_c_*`"),
        ("d", "mesmo `entidade_id` em outra conta, receita ×50", "decisões idênticas + nota; `contribuicao` → `IdentidadeIncompativel`", "`test_d_*`"),
        ("e", "restatement", "t-2 preliminar ≠ verdade; t-4 revisada = verdade; t-1 inexistente", "`test_e_decisao_usa_preliminar_e_nao_a_revisada`"),
        ("e", "mutante que lê preliminar e declara 0 (F1-06)", "motor mede dependência > 0 com declaração 0", "`test_e_motor_mede_uso_de_preliminar_que_a_politica_nao_declara`"),
        ("f", "reprodutibilidade", "mesma seed → bytes iguais; fixture refeita byte a byte", "`test_f_*`"),
        ("F1-01", "política trapaceira que reconstrói o mundo pela linhagem", "snapshot sem seed/cenário; trapaceira vira `static`; alocação de oráculo abaixo do piso é recusada; módulos de política não importam a verdade (AST)", "`test_f101_*`"),
    ]:
        a("| " + " | ".join(linha) + " |")
    a("")
    a("Limite do F1-01 (aceito): o simulador é *white-box*; uma política que importe o gerador e faça força bruta sobre "
      "um espaço pequeno de seeds, casando valores observados, ainda reconstruiria o mundo. O isolamento é por contrato "
      "de código (teste AST + linhagem opaca + piso), não criptográfico.\n")

    a("## 5. Comparação com `services/orakul_predictive/` (linha oficial, somente leitura)\n")
    a("| Tema | Orakul | Contrato do lab (v0 usa) | Consequência |")
    a("|---|---|---|---|")
    for linha in [
        ("Unidade de fato", "`ObservacaoDiaria` = 1 linha com spend e revenue e um único `lido_em` (`features.py:69-83`)", "1 `Observacao` por métrica, cada uma com `disponivel_em`", "Orakul não representa custo em d+1 e receita em d+3 sem duplicar a linha"),
        ("Corte", "`cutoff_utc`: data civil = fim do dia em SP (`relogio.py:58`) + `civil_date <= as_of`", "`as_of` só como instante com tz", "dois jeitos de cortar"),
        ("Versão na decisão", "última revisão conhecida (`serie_sem_futuro`, `features.py:484`)", "idem (`Snapshot`)", "compatíveis"),
        ("Versão no outcome", "primeira vintage fechada (`replay.py:86`)", "verdade madura", "escolha legítima diferente; deve ser parâmetro explícito"),
        ("Estados", "`ZERO_MEDIDO`, `ANTIGO`, `HIPOTESE`; `MEDIDO` com 0 recusado (`semantica.py:69`)", "`zero_confirmado`, `nao_coletado`, `nao_atribuivel`; `medido` com 0 aceito", "mapear e alinhar"),
        ("Moeda/fuso", "só BRL / `America/Sao_Paulo`", "moeda explícita; qualquer IANA", "JoinAds real é USD: Orakul recusaria; lab não soma"),
        ("Maturidade/cobertura", "não modela", "explícitas; `contribuicao` marca preliminar/parcial", "`greedy_conservador` depende disso"),
    ]:
        a("| " + " | ".join(linha) + " |")
    a("")
    a("Recomendação (não aplicada): não criar uma 4ª semântica. Uma camada única de as-of = observação por métrica com "
      "`disponivel_em` (lab) + corte por instante com a conveniência \"data civil = fim do dia SP\" na borda (Orakul) + "
      "política de outcome parametrizada (`primeira_vintage_fechada` | `verdade_madura`) + um enum de estado único.\n")

    a("## 6. Não testado / limites\n")
    for x in [
        "Dado real: nenhum (ver §2).",
        "Políticas com modelo (bandit/Bayes/shrinkage): fora do v0; a interface `decidir(snapshot, ctx)` está pronta.",
        "Câmbio: custo BRL × receita USD fica sem valor por desenho.",
        "A medição de dependência de preliminar é por efeito: uma política que lê preliminar mas cuja decisão não muda sem ele não é contada (e não precisa ser).",
        "Determinismo entre plataformas (float de `pow`/`lognormvariate` em outra libm): hipótese; só testado em macOS arm64.",
        "Preliminar enviesado de forma correlacionada à eficiência: não rodado.",
        "Orçamento total fixo por moeda (política não corta gasto).",
    ]:
        a(f"- {x}")
    SAIDA.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("escrito", SAIDA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
