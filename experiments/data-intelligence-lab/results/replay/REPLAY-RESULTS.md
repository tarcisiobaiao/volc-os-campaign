# Replay econômico v0 — resultados (SINTÉTICO)

> **Gerado** por `scripts/replay_relatorio.py` a partir de `results/replay/replay_resultados.json`; não editar à mão.
> **Natureza:** mundo **sintético** gerado por seed. Nenhum número é validação com dado real do VOLC. Serve para provar a *mecânica* (as_of, restatement, null≠0, moeda, identidade, reprodutibilidade) e comparar baselines sob hipóteses explícitas.

- Execução: `cd experiments/data-intelligence-lab && .venv/bin/python -I scripts/replay_executar.py` (30 seeds × 4 cenários × 5 políticas; 3 processos single-thread; 114.4 s de parede nesta máquina) e depois `scripts/replay_relatorio.py`.
- Código: `src/volc_dil/replay/` (`cenario.py`, `motor.py`, `politicas.py`, `avaliacao.py`, `auditoria.py`).
- Fixture: `fixtures/replay/cenario_mini.json` + `MANIFEST.json` (`scripts/replay_gerar_fixture.py [--verificar]`).
- Contraprovas: `tests/data-intelligence/test_replay_economico.py` (23 testes).
- Manifesto: `codigo_sha256=1c6e0060e4d3d79d…`, `resultado_sha256=9843325f023a6b37…`, `fingerprint=2e0158b71dcbef28…`; `deterministico_sha256=9843325f023a6b37cae23eb8ff274d6c631beb6d7c6b94205b5ae8e279dda65f` (tempos ficam fora da parte determinística; o resultado não depende do número de processos).

## 1. O "replay atual" do VOLC não é um replay econômico temporal

Evidência em `volc_ads/inteligencia_decisao/replay.py`: `_agora()` (l. 61) devolve **um único** `as_of` fixo do dataset; `executar_replay()` (l. 104–115) percorre os cenários dourados e compara 4 campos categóricos (`estado_da_leitura`, `veredito`, `health_gate`, nº de propostas) com o esperado. Não há orçamento alocado, receita com atraso, versão preliminar/revisada, lucro, regret ou oráculo. É um teste de regressão de classificação dourada.
Custo medido (bancada): `executar_replay()` = 3.6 ms (mediana de 5), import 23 ms, processo inteiro 139 ms, pico de RSS 24.0 MB; 8/8 cenários passam.

## 2. Desenho do v0

- **Mundo (verdade, só o avaliador vê):** receita do dia = `alpha_i(t) · ruído_lognormal(i,t) · gasto^0,7`; quebra de regime opcional; uma unidade em USD; RNG por (cenário, unidade, dia) → números aleatórios comuns entre políticas.
- **Emissão:** custo do dia d em d+1 03:00; receita preliminar (`preliminary`, cobertura `partial`) em d+1 06:00; revisada (`revised`, `complete`) em d+3 06:00 com a mesma chave lógica; lacunas `nao_coletado`/`falha`; receita nunca coletada tem a versão final `revised` sem valor. **Linhagem e `coleta_id` são opacos** (sem seed nem nome de cenário) e o rótulo do snapshot é `decisao/<dia>` (F1-01).
- **Motor (malha fechada):** decisão do dia d às 23:00 de d-1; corte `disponivel_em <= as_of` (janela 14 dias); `Snapshot.construir(..., politica_futuro="falhar")` no ponto de consumo; a política recebe só snapshot + contexto; a decisão é validada (universo exato, moeda da unidade, soma por moeda, **piso por unidade**) e registrada sem resultado; o lucro é calculado depois com a verdade madura.
- **Uso de preliminar é MEDIDO, não só declarado (F1-06):** para cada decisão o motor reexecuta a política sobre o mesmo corte sem nenhum número preliminar; se a alocação muda, a decisão `dependeu_de_preliminar`. O relatório traz as duas contagens (declarada × medida).
- **Opt-in explícito de parcial/preliminar:** `proportional` chama `contribuicao(..., aceitar_parcial=True)` e declara `usa_preliminar=True`; `greedy_conservador` usa o padrão do contrato (parcial não vira número) e ainda recusa contribuição marcada como preliminar.
- **Baselines:** `static` (mantém alocação herdada não uniforme), `equal`, `proportional` (média diária da contribuição conhecida em 7 dias; unidade sem valor fica fora com motivo), `greedy_conservador` (só unidades com os 7 dias maduros completos; troca até 20%/passo). Anti-baseline `proportional_naive_null_as_zero`.
- **Por que simulador:** na base atual custo e receita são *latest-wins*/upsert (sem as-of real), o JoinAds legado tem `revenue NOT NULL DEFAULT 0` e um gatilho reescreve a receita campanha-dia (`docs/data-intelligence/DATA-CAPABILITY-MATRIX.md`). Não há histórico de versões para reproduzir o que se sabia em t; e um log histórico só avalia a política que o gerou.

## 3. Resultados — 30 seeds (BRL, 8 unidades, 60 dias)

Métrica principal: regret vs oráculo de parâmetros, bps do gasto do horizonte, moeda BRL. "Pareado vs equal" = média por seed de (regret da política − regret do `equal` na mesma seed) com IC 95% t de Student; negativo = melhor que `equal`. "Vitórias" = seeds em que a política teve o menor regret entre as 4 baselines.

| Cenário | Política | média | dp | mediana | p90 | pior | pareado vs equal [IC95] | melhor/pior que equal (seeds) | vitórias | turnover médio (bps/dia) | decisões c/ preliminar: declarado / **medido** |
|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| estacionario | static | 960 | 477 | 873 | 1630 | 1967 | 400 [255; 545] | 5/25 | 1 | 0.0 | 0.0 / 0.0 de 59 |
|  | equal | 561 | 198 | 562 | 855 | 917 | – | – | 7 | 38.4 | 0.0 / 0.0 de 59 |
|  | proportional | 1077 | 892 | 611 | 2424 | 2712 | 516 [172; 861] | 11/19 | 9 | 2627 | 58.0 / 58.0 de 59 |
|  | greedy_conservador | 470 | 173 | 462 | 707 | 902 | -90.7 [-172; -8.8] | 22/8 | 13 | 297 | 0.0 / 0.0 de 59 |
|  | *proportional_naive_null_as_zero* | 1401 | 742 | 1302 | 2423 | 2879 | 840 [548; 1133] | 4/26 | – | 3300 | 58.0 / 56.0 de 59 |
| lacunas_altas | static | 938 | 518 | 860 | 1673 | 2363 | 374 [191; 558] | 8/22 | 0 | 0.0 | 0.0 / 0.0 de 59 |
|  | equal | 564 | 234 | 566 | 766 | 1203 | – | – | 14 | 36.8 | 0.0 / 0.0 de 59 |
|  | proportional | 1151 | 446 | 1108 | 1805 | 2170 | 587 [387; 787] | 4/26 | 2 | 2495 | 58.0 / 58.0 de 59 |
|  | greedy_conservador | 605 | 318 | 576 | 1014 | 1429 | 41.6 [-74.8; 158] | 14/16 | 14 | 118 | 0.0 / 0.0 de 59 |
|  | *proportional_naive_null_as_zero* | 1981 | 357 | 1998 | 2441 | 2551 | 1418 [1254; 1581] | 0/30 | – | 3919 | 58.0 / 55.9 de 59 |
| preliminar_otimista | static | 1066 | 472 | 1008 | 1512 | 2596 | 510 [349; 671] | 3/27 | 0 | 0.0 | 0.0 / 0.0 de 59 |
|  | equal | 556 | 198 | 590 | 770 | 859 | – | – | 5 | 39.1 | 0.0 / 0.0 de 59 |
|  | proportional | 542 | 409 | 362 | 1062 | 2113 | -14.1 [-200; 172] | 21/9 | 17 | 1447 | 58.0 / 58.0 de 59 |
|  | greedy_conservador | 473 | 158 | 426 | 622 | 970 | -83.4 [-176; 9.5] | 17/13 | 8 | 285 | 0.0 / 0.0 de 59 |
|  | *proportional_naive_null_as_zero* | 836 | 462 | 612 | 1566 | 1870 | 280 [81.7; 478] | 11/19 | – | 2024 | 58.0 / 57.4 de 59 |
| quebra_regime | static | 1619 | 459 | 1532 | 2211 | 2816 | 341 [220; 462] | 4/26 | 1 | 0.0 | 0.0 / 0.0 de 59 |
|  | equal | 1278 | 263 | 1304 | 1477 | 2184 | – | – | 5 | 34.8 | 0.0 / 0.0 de 59 |
|  | proportional | 1201 | 736 | 916 | 2258 | 2342 | -76.9 [-419; 265] | 17/13 | 17 | 2592 | 58.0 / 58.0 de 59 |
|  | greedy_conservador | 1176 | 342 | 1143 | 1655 | 1948 | -102 [-252; 47.4] | 18/12 | 7 | 272 | 0.0 / 0.0 de 59 |
|  | *proportional_naive_null_as_zero* | 1530 | 780 | 1460 | 2399 | 2997 | 251 [-111; 614] | 11/19 | – | 3218 | 58.0 / 55.5 de 59 |

**Leitura (gerada a partir dos números acima):**

- **estacionario:** menor média = `greedy_conservador`; significativamente melhor que `equal`: `greedy_conservador`; significativamente pior: `static`, `proportional`; distribuição com cauda pesada (dp > 1,5× a do `equal` e média > 1,2× a mediana): `proportional`.
- **lacunas_altas:** menor média = `equal`; significativamente melhor que `equal`: nenhuma; significativamente pior: `static`, `proportional`.
- **preliminar_otimista:** menor média = `greedy_conservador`; significativamente melhor que `equal`: nenhuma; significativamente pior: `static`; distribuição com cauda pesada (dp > 1,5× a do `equal` e média > 1,2× a mediana): `proportional`.
- **quebra_regime:** menor média = `greedy_conservador`; significativamente melhor que `equal`: nenhuma; significativamente pior: `static`; distribuição com cauda pesada (dp > 1,5× a do `equal` e média > 1,2× a mediana): `proportional`.
- Anti-baseline null→0 tem média de regret maior que `proportional` em todos os cenários.
- O regret vs oráculo **perfeito** (conhece o ruído do dia) inclui uma parte irredutível (no JSON, `regret_perfeito_bps`); a ordem das 4 baselines por média é a mesma nas duas métricas em 4/4 cenários (estacionario, lacunas_altas, preliminar_otimista, quebra_regime).
- USD: com uma unidade não há o que realocar; o relatório mostra a moeda separada e todas as políticas empatam.

**Auditoria null × zero** (seed 1): troca cada observação sem valor por `zero_confirmado` (com a cobertura que um valor real teria) e vê se a decisão muda; um segundo teste perturba a receita de UMA unidade (×3, não preserva razões — F1-07) para separar "cega a dados" de "null como 0".

| Política | estacionario | lacunas_altas | preliminar_otimista | quebra_regime |
|---|---|---|---|---|
| static | cega a dados (distingue 0/57; sensível 0) | cega a dados (distingue 0/58; sensível 0) | cega a dados (distingue 0/58; sensível 0) | cega a dados (distingue 0/57; sensível 0) |
| equal | cega a dados (distingue 0/57; sensível 0) | cega a dados (distingue 0/58; sensível 0) | cega a dados (distingue 0/58; sensível 0) | cega a dados (distingue 0/57; sensível 0) |
| proportional | distingue (distingue 48/57; sensível 57) | distingue (distingue 58/58; sensível 58) | distingue (distingue 52/58; sensível 58) | distingue (distingue 51/57; sensível 57) |
| greedy_conservador | distingue (distingue 27/57; sensível 50) | distingue (distingue 38/58; sensível 40) | distingue (distingue 32/58; sensível 50) | distingue (distingue 37/57; sensível 50) |
| proportional_naive_null_as_zero | **suspeita null→0** (distingue 0/57; sensível 57) | **suspeita null→0** (distingue 0/58; sensível 58) | **suspeita null→0** (distingue 0/58; sensível 58) | **suspeita null→0** (distingue 0/57; sensível 57) |

## 4. Contraprovas (todas falham como esperado)

| # | Ataque | Resultado esperado e obtido | Teste |
|---|---|---|---|
| a | corte que ignora o `as_of` | `VazamentoDeFuturo` no ponto de consumo | `test_a_corte_que_vaza_futuro_levanta_no_ponto_de_consumo` |
| a | snapshot adulterado / de as_of posterior entregue à política | `VazamentoDeFuturo` na guarda das 5 políticas | `test_a_snapshot_adulterado_entregue_a_politica_levanta` |
| b | política que trata None como 0 | auditoria marca suspeita; decisões divergem; sem receita a correta não realoca | `test_b_*` |
| b | greedy por razão com null→0 (F1-07) | auditoria a marca (não fica "cega"); greedy correta não é acusada | `test_f107_*` |
| c | BRL+USD num pool; BRL na unidade USD; `agregar` BRL+USD | `MoedasDiferentes` | `test_c_*` |
| d | mesmo `entidade_id` em outra conta, receita ×50 | decisões idênticas + nota; `contribuicao` → `IdentidadeIncompativel` | `test_d_*` |
| e | restatement | t-2 preliminar ≠ verdade; t-4 revisada = verdade; t-1 inexistente | `test_e_decisao_usa_preliminar_e_nao_a_revisada` |
| e | mutante que lê preliminar e declara 0 (F1-06) | motor mede dependência > 0 com declaração 0 | `test_e_motor_mede_uso_de_preliminar_que_a_politica_nao_declara` |
| f | reprodutibilidade | mesma seed → bytes iguais; fixture refeita byte a byte | `test_f_*` |
| F1-01 | política trapaceira que reconstrói o mundo pela linhagem | snapshot sem seed/cenário; trapaceira vira `static`; alocação de oráculo abaixo do piso é recusada; módulos de política não importam a verdade (AST) | `test_f101_*` |

Limite do F1-01 (aceito): o simulador é *white-box*; uma política que importe o gerador e faça força bruta sobre um espaço pequeno de seeds, casando valores observados, ainda reconstruiria o mundo. O isolamento é por contrato de código (teste AST + linhagem opaca + piso), não criptográfico.

## 5. Comparação com `services/orakul_predictive/` (linha oficial, somente leitura)

| Tema | Orakul | Contrato do lab (v0 usa) | Consequência |
|---|---|---|---|
| Unidade de fato | `ObservacaoDiaria` = 1 linha com spend e revenue e um único `lido_em` (`features.py:69-83`) | 1 `Observacao` por métrica, cada uma com `disponivel_em` | Orakul não representa custo em d+1 e receita em d+3 sem duplicar a linha |
| Corte | `cutoff_utc`: data civil = fim do dia em SP (`relogio.py:58`) + `civil_date <= as_of` | `as_of` só como instante com tz | dois jeitos de cortar |
| Versão na decisão | última revisão conhecida (`serie_sem_futuro`, `features.py:484`) | idem (`Snapshot`) | compatíveis |
| Versão no outcome | primeira vintage fechada (`replay.py:86`) | verdade madura | escolha legítima diferente; deve ser parâmetro explícito |
| Estados | `ZERO_MEDIDO`, `ANTIGO`, `HIPOTESE`; `MEDIDO` com 0 recusado (`semantica.py:69`) | `zero_confirmado`, `nao_coletado`, `nao_atribuivel`; `medido` com 0 aceito | mapear e alinhar |
| Moeda/fuso | só BRL / `America/Sao_Paulo` | moeda explícita; qualquer IANA | JoinAds real é USD: Orakul recusaria; lab não soma |
| Maturidade/cobertura | não modela | explícitas; `contribuicao` marca preliminar/parcial | `greedy_conservador` depende disso |

Recomendação (não aplicada): não criar uma 4ª semântica. Uma camada única de as-of = observação por métrica com `disponivel_em` (lab) + corte por instante com a conveniência "data civil = fim do dia SP" na borda (Orakul) + política de outcome parametrizada (`primeira_vintage_fechada` | `verdade_madura`) + um enum de estado único.

## 6. Não testado / limites

- Dado real: nenhum (ver §2).
- Políticas com modelo (bandit/Bayes/shrinkage): fora do v0; a interface `decidir(snapshot, ctx)` está pronta.
- Câmbio: custo BRL × receita USD fica sem valor por desenho.
- A medição de dependência de preliminar é por efeito: uma política que lê preliminar mas cuja decisão não muda sem ele não é contada (e não precisa ser).
- Determinismo entre plataformas (float de `pow`/`lognormvariate` em outra libm): hipótese; só testado em macOS arm64.
- Preliminar enviesado de forma correlacionada à eficiência: não rodado.
- Orçamento total fixo por moeda (política não corta gasto).
