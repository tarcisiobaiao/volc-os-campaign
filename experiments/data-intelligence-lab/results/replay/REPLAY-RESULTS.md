# Replay econômico v0 — resultados (SINTÉTICO)

> **Natureza:** tudo aqui roda sobre um **mundo sintético** gerado por seed. Nenhum número é validação com dado real do VOLC. Serve para provar a *mecânica* (as_of, restatement, null≠0, moeda, identidade, reprodutibilidade) e comparar baselines sob hipóteses explícitas.

- Código: `experiments/data-intelligence-lab/src/volc_dil/replay/` (`cenario.py`, `motor.py`, `politicas.py`, `avaliacao.py`, `auditoria.py`)
- Execução: `cd experiments/data-intelligence-lab && .venv/bin/python -I scripts/replay_executar.py` (~45 s; 4 cenários × 5 seeds × 5 políticas)
- Fixture: `fixtures/replay/cenario_mini.json` + `MANIFEST.json` (regerar: `.venv/bin/python -I scripts/replay_gerar_fixture.py`; checar: `--verificar`)
- Contraprovas: `tests/data-intelligence/test_replay_economico.py` (17 testes, < 1 s)
- JSON com manifesto: `results/replay/replay_resultados.json` — `deterministico_sha256 = a2685d2bf47e39bc497c8c5b8ca40c9c404fc3641d65d3539d84089b400fa8bd` (duas execuções seguidas deram o mesmo sha; os tempos ficam fora da parte determinística).

## 1. O "replay atual" do VOLC não é um replay econômico temporal

Evidência (`volc_ads/inteligencia_decisao/replay.py`):

- `_agora()` (l. 61) devolve **um único** `as_of` fixo do dataset (`2026-08-28T12:00:00Z`); não há sequência de datas de decisão.
- `executar_replay()` (l. 104–115) percorre 8 cenários dourados e compara 4 campos categóricos (`estado_da_leitura`, `veredito`, `health_gate`, nº de propostas) com o esperado. Não há orçamento alocado, receita com atraso, versão preliminar/revisada, lucro, regret ou oráculo.
- `grep` por `restat|prelimin|disponivel|maturi|lucro|regret|aloca` em `volc_ads/inteligencia_decisao/*.py` não acha nenhum conceito de restatement/alocação (só textos de UI).
- Custo medido: **2,7 ms** por `executar_replay()` (mediana de 5, aquecimento descartado) + 19 ms de import; processo inteiro 110 ms de parede (ver `results/bench/BENCH-RESULTS.md`).

É um **teste de regressão de classificação dourada**, útil e barato — não um replay econômico. O v0 abaixo não o substitui; cobre outra pergunta.

## 2. Desenho do v0

**Mundo (verdade, só o avaliador vê):** N unidades (campanhas) com eficiência latente `alpha_i`; receita do dia = `alpha_i(t) · ruído_lognormal(i,t) · gasto^0,7` (retorno decrescente). Gasto = orçamento alocado. Opcional: quebra de regime no dia 30 (metade mais eficiente cai ×0,5, a outra sobe ×1,6). Uma unidade em **USD**, o resto em BRL. RNG por (cenário, unidade, dia) via sha256 → todas as políticas enfrentam o **mesmo** mundo.

**Emissão (o que o VOLC conheceria), com relógios separados:**

| Fato do dia d | `disponivel_em` | Estado/maturidade |
|---|---|---|
| custo | d+1 03:00 | medido/madura; 3% `nao_coletado` (metade com backfill em d+2) |
| receita preliminar | d+1 06:00 | `reported_revenue`, `preliminary`, cobertura `partial`, valor = verdade × U(0,60; 1,05); 5% `falha` |
| receita revisada (restatement) | d+3 06:00 | mesma chave lógica, `revised`, `complete`, valor = verdade; 2% nunca chega (`nao_coletado` nas duas versões) |

**Motor (malha fechada):** decisão do orçamento do dia `d` às 23:00 de `d-1`. O log é cortado em `disponivel_em <= as_of` (janela de consulta de 14 dias) e o snapshot é construído com `Snapshot.construir(..., politica_futuro="falhar")` **no ponto de consumo**; a política recebe só snapshot + contexto (universo, moeda de cada unidade, orçamento total por moeda, a própria alocação vigente, piso de 10% da cota igual). A decisão é validada (universo exato, moeda da unidade, soma por moeda fecha) e registrada **sem resultado**. O lucro é calculado depois, com a verdade madura, em `avaliacao.py`.

Por que simulador e não log histórico: com receita dependente do gasto, um log histórico só avalia a política que o gerou (não há contrafactual sem modelo). Além disso, na base atual custo e receita são *latest-wins*/upsert (sem as-of real), o JoinAds legado tem `revenue NOT NULL DEFAULT 0` e o gatilho reescreve a receita campanha-dia (`docs/data-intelligence/DATA-CAPABILITY-MATRIX.md`, linhas JoinAds/Google Ads). Não existe hoje histórico de versões para reproduzir "o que se sabia em t" — por isso o v0 roda sobre sintético.

**Baselines** (`politicas.py`): `static` (mantém alocação herdada, não uniforme), `equal`, `proportional` (média diária da contribuição contábil conhecida nos últimos 7 dias, **inclui preliminar**; dia sem valor é pulado; unidade sem nenhum valor fica fora com motivo e mantém a alocação), `greedy_conservador` (só unidades com os 7 dias maduros mais recentes completos — receita revisada + custo com valor; troca até 20%/passo entre pares melhor/pior ROI se a diferença > 5%). Anti-baseline `proportional_naive_null_as_zero` existe para ser detectada.

**Métricas** (inteiros: micros e bps): lucro realizado, regret vs **oráculo de informação perfeita** (conhece ruído do dia: teto pedido), regret vs **oráculo de parâmetros** (conhece `alpha` e a quebra, não o ruído: separa o aprendível do irredutível), drawdown máximo do lucro acumulado, HHI médio, turnover médio diário, nº de decisões com dado preliminar, sha256 das decisões e do relatório. **Moedas reportadas separadas**; nada soma BRL com USD.

## 3. Resultados (BRL, 8 unidades, 60 dias, 5 seeds; medianas)

Regret em bps do gasto total do horizonte. "Vitórias" = seeds em que a política teve o menor regret entre as 4 baselines.

| Cenário | Política | Regret vs perfeito | Regret vs parâmetros | Vitórias | HHI (bps) | Turnover (bps/dia) | Decisões c/ preliminar |
|---|---|---:|---:|---:|---:|---:|---:|
| estacionário | static | 1013 | 636 | 1 | 1598 | 0 | 0/59 |
| | equal | 903 | 432 | 2 | 1255 | 38 | 0/59 |
| | proportional | 1033 | 482 | 1 | 2080 | 1943 | 58/59 |
| | greedy_conservador | **901** | **347** | 1 | 1867 | 316 | 0/59 |
| | *naive null→0* | 1346 | 796 | – | 2556 | 2602 | 58/59 |
| quebra de regime | static | 2249 | 1852 | 0 | 1540 | 0 | 0/59 |
| | equal | 1748 | 1351 | 1 | 1254 | 35 | 0/59 |
| | proportional | **1178** | **781** | 3 | 2816 | 1785 | 58/59 |
| | greedy_conservador | 1653 | 1263 | 1 | 1868 | 281 | 0/59 |
| | *naive null→0* | 1412 | 1015 | – | 3176 | 2422 | 58/59 |
| preliminar otimista | static | 1603 | 1007 | 0 | 1578 | 0 | 0/59 |
| | equal | 975 | 462 | 1 | 1255 | 36 | 0/59 |
| | proportional | **899** | **340** | 4 | 1824 | 977 | 58/59 |
| | greedy_conservador | 1060 | 599 | 0 | 1899 | 320 | 0/59 |
| | *naive null→0* | 1193 | 642 | – | 2112 | 1669 | 58/59 |
| lacunas altas | static | 2922 | 1361 | 0 | 1660 | 0 | 0/59 |
| | equal | **1958** | **499** | 4 | 1256 | 43 | 0/59 |
| | proportional | 2202 | 759 | 1 | 2776 | 2062 | 58/59 |
| | greedy_conservador | 2349 | 875 | 0 | 1625 | 118 | 0/59 |
| | *naive null→0* | 3106 | 1772 | – | 3867 | 3721 | 58/59 |

USD (1 unidade): todas as políticas dão o mesmo lucro — com uma unidade por moeda não há o que realocar; o relatório mostra isso em vez de misturar com BRL.

**Leitura honesta:**

- **Nenhum baseline domina.** O trivial `equal` vence com lacunas altas/ruído alto e fica a ~1 p.p. do melhor no estacionário. `greedy_conservador` é o melhor no estacionário (vs parâmetros), mas o **pior para reagir à quebra de regime** (só enxerga dados com ≥4 dias de atraso e anda 20%/passo). `proportional` é o melhor quando o mundo muda, ao custo de turnover de ~20%/dia e concentração alta — e usa preliminar em 58/59 decisões.
- O cenário "preliminar otimista" **não** puniu o `proportional`: o viés otimista foi sorteado para metade das unidades independentemente da eficiência, então não criou armadilha sistemática. Isso refuta a expectativa de que "usar preliminar sempre perde"; não prova o contrário. Um cenário em que o preliminar superestima *as piores* unidades ainda precisa ser rodado (não testado).
- Tratar null como zero custa caro e é detectável: o anti-baseline perde de `proportional` na mediana dos 4 cenários (+230 a +900 bps de regret) e a auditoria metamórfica o pega em 4/4 cenários.
- Grande parte do regret vs oráculo perfeito é **irredutível** (ruído diário que nenhuma política vê antes): a diferença entre as duas colunas de regret é ~380–1560 bps.

**Auditoria null × zero** (`auditoria.py`, seed 1): troca cada observação sem valor por `zero_confirmado` e vê se a decisão muda; um segundo teste dobra os valores para separar "cega a dados" de "null como 0".

| Política | estacionário | quebra | prelim. otimista | lacunas altas |
|---|---|---|---|---|
| static / equal | cega a dados | cega | cega | cega |
| proportional | distingue (48/57) | 51/57 | 52/58 | 58/58 |
| greedy_conservador | distingue (26/57) | 32/57 | 26/58 | 38/58 |
| naive null→0 | **suspeita** (0/57) | **suspeita** | **suspeita** | **suspeita** |

## 4. Contraprovas (todas falham como esperado)

| # | Ataque | Resultado | Teste |
|---|---|---|---|
| a | corte que ignora o `as_of` (entrega o log inteiro) | `VazamentoDeFuturo` no `Snapshot.construir(politica_futuro="falhar")` | `test_a_corte_que_vaza_futuro_levanta_no_ponto_de_consumo` |
| a | snapshot adulterado (obs com `disponivel_em > as_of`) entregue direto à política; snapshot de `as_of` posterior | `VazamentoDeFuturo` na guarda da política (as 5 políticas) | `test_a_snapshot_adulterado_entregue_a_politica_levanta` |
| b | política que trata None como 0 | auditoria metamórfica marca `suspeita_null_como_zero`; decisões e relatório divergem da correta; sem nenhuma receita, a correta exclui todas com motivo e não realoca, a ingênua realoca | `test_b_*` (4 testes) |
| c | pool único BRL+USD; orçamento BRL na unidade USD; `agregar` de receitas BRL+USD | `MoedasDiferentes` nos três | `test_c_*` |
| d | receita ×50 com mesmo `entidade_id` em outra conta | decisões idênticas às sem a impostora + nota `identidade_incompativel`; `contribuicao(custo, receita_impostora)` → `IdentidadeIncompativel` | `test_d_*` |
| e | restatement | no dia t, receita de t-2 é `preliminary` e ≠ verdade; t-4 é `revised` = verdade; t-1 ainda não existe; `greedy` usa 0 preliminares | `test_e_*` |
| f | reprodutibilidade | mesma seed → relatório idêntico byte a byte; seed diferente → diferente; fixture versionada refeita byte a byte; mundo independe da ordem | `test_f_*` |

Mutantes verificados à mão: trocando `politica_futuro="falhar"` por `"excluir"` no motor, ou removendo a guarda da política, os testes (a) deixam de levantar → falhariam.

## 5. Comparação com `services/orakul_predictive/` (linha oficial, somente leitura)

O Orakul já tem walk-forward as-of (`replay.py`), relógio explícito (`relogio.py`) e ausente≠zero (`semantica.py`). Diferenças de semântica que importam para unificar:

| Tema | Orakul | Contrato do lab (v0 usa) | Consequência |
|---|---|---|---|
| Unidade de fato | `ObservacaoDiaria` = 1 linha com **spend e revenue juntos** e um único `lido_em` (`features.py:69-83`) | 1 `Observacao` por métrica, cada uma com seu `disponivel_em` | Orakul não representa custo conhecido em d+1 e receita só em d+3 sem duplicar a linha; o lab sim |
| Corte | `cutoff_utc`: data civil vira **fim do dia em SP** (`relogio.py:58`) + filtro por `civil_date <= as_of` | `as_of` precisa ser instante com tz (data sozinha é recusada) | dois jeitos de cortar; o do lab é mais estrito |
| Versão usada na decisão | última revisão conhecida no cutoff (`serie_sem_futuro`, `features.py:484`) | idem (`Snapshot`: última versão conhecida por chave lógica) | **compatíveis** |
| Versão usada no outcome | "actual científico é a **primeira vintage fechada**" (`replay.py:86`) | v0 avalia com a **verdade madura** (revisada) | escolha diferente e legítima: Orakul mede previsão contra o 1º fechamento; o lab mede lucro econômico final. Precisa ser parâmetro explícito, não divergência silenciosa |
| Estados | `AUSENTE, ZERO_MEDIDO, MEDIDO, FALHA, NAO_APLICAVEL, ANTIGO, HIPOTESE`; `MEDIDO` com 0 é **recusado** (`semantica.py:69`) | `medido, zero_confirmado, ausente, nao_coletado, falha, nao_atribuivel, nao_aplicavel`; `medido` com 0 é **aceito** | mapear `ZERO_MEDIDO↔zero_confirmado`; `ANTIGO`/`HIPOTESE` não existem no lab (lá viram maturidade/value_kind); `nao_coletado`/`nao_atribuivel` não existem no Orakul |
| Moeda/fuso | só BRL e `America/Sao_Paulo` (`features.py:86-89`) | moeda explícita por valor; qualquer IANA | JoinAds é **USD** na base real: o Orakul recusaria; o lab recusa somar (sem câmbio) |
| Maturidade/cobertura | não modela | `maturidade` e `cobertura` explícitas | `greedy_conservador` depende disso |

**Recomendação (não aplicada):** não criar uma 4ª semântica. O v0 **não** inventou corte novo: usa o `Snapshot` do contrato. Unificar em uma camada única de *as-of* = (a) observação por métrica com `disponivel_em` (lab), (b) corte por instante com a conveniência "data civil = fim do dia SP" do Orakul como função de borda, (c) política de outcome parametrizada (`primeira_vintage_fechada` | `verdade_madura`), (d) um enum de estado único (proposta: lab + `ANTIGO` como flag de frescor, não estado de valor; recusar `medido` com 0 como o Orakul). Quem decide e onde mora é do integrador/arquiteto.

## 6. O que não foi testado / limites

- Dado real: nenhum (ver §2 — não há as-of real na base).
- Política com modelo (bandit/Bayes/shrinkage do statlab): fora do escopo do v0; a interface `decidir(snapshot, ctx)` está pronta para ela.
- Câmbio: o v0 não converte; com custo BRL e receita USD (caso real Google Ads × JoinAds) a contribuição fica **sem valor** por desenho.
- `insumos_preliminares` é autodeclarado pela política (o motor não intercepta leituras do snapshot).
- Determinismo entre plataformas: `pow`/`lognormvariate` de float podem divergir no último ulp em outra libm (hipótese; só testado em macOS arm64).
- Cenário com preliminar enviesado de forma correlacionada à eficiência: não rodado.
- Orçamento total fixo por moeda (política não pode cortar gasto): simplificação do v0.
