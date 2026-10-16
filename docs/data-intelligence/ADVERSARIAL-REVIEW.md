# ADVERSARIAL-REVIEW — VOLC Data Intelligence Lab

Dois revisores independentes e read-only (F1: contrato, snapshot, replay, bancada, surrogate,
matrizes; F2: Stat Lab, swarm, decisões de bibliotecas) tentaram refutar os artefatos depois
que existiam. Reprodutores ficaram fora do repositório (`/private/tmp/claude-502/f1/`, `/f2/`).
O revisor não reescreveu nada; cada owner corrigiu e respondeu. Commits de resposta:
`9054059d` (F1), `39491835` (F2 Stat Lab), `202bd2d1` (F2 swarm).

**Total:** 35 achados confirmados (12 materiais, 14 menores, 9 notas) + 4 hipóteses.
**Vereditos que mudaram:** nenhum dos dez vereditos de topo mudou de sinal. Mudaram leituras
intermediárias (replay com 30 seeds, atribuição causal do swarm, viés de maturação com IC,
calibração do surrogate) — registradas abaixo.

Legenda da resposta: **corrigido** (mudança + prova) · **limitação aceita** (documentada) · **nota** (sem ação de código).

## 1. F1 — contrato, replay, bancada, surrogate

| ID | Sev. | Achado (resumo) | Resposta | Prova |
|---|---|---|---|---|
| F1-01 | material | Linhagem `cenario:`/`seed:` no snapshot deixava a política reconstruir o mundo e alocar como o oráculo (regret 34 bps); piso não validado | **corrigido**: linhagem constante, `coleta_id` opaco, rótulo `decisao/<dia>`, `validar_decisao` recusa abaixo do piso. **Limitação aceita:** isolamento é por regra de código (AST), não criptográfico — uma política que importe o gerador e force seeds ainda reconstruiria | `test_f101_*` (4), reprodutor do revisor quebra |
| F1-02 | material | `chave_logica` dependia do texto do offset e da ordem do grão → preliminar −03:00 e revisada UTC somavam (27M em vez de 12M); `agregar` somava duplicatas | **corrigido**: UTC canônico em chave, JSON e fingerprint; grão como conjunto; `agregar` recusa chave repetida | `test_f1_02_*` |
| F1-03 | material | Bancada divergia fora do caminho feliz: duplicata exata (10M vs 5M), moeda NULL com lógica de 3 valores, `medido` sem micros | **corrigido**: as 4 engines validam, deduplicam reentrega idêntica, levantam `EmpateDeVersao`/`LinhaMalformada`; comparação NULL-segura (`IS DISTINCT FROM`, `ne_missing`) | `test_f103_*` comparam linha inteira |
| F1-04 | material | Circularidade: `verificar_nao_circular` sem consumidor; portão comparava strings exatas (`'JoinAds'`, `'joinads:v2'` passavam); receita semanal da mesma entidade passava; features sem as-of | **corrigido**: regra única `origens_circulares` com vocabulário fechado de fontes usada por contrato e portão; checagem por entidade + interseção temporal; `Feature.disponivel_em` e remoção por vazamento | `test_f1_04_*` (8 casos) |
| F1-05 | material | Portão tratava grão como ordem linear (`url_day`→`keyword_day` "viável"); painel 1×1200 + 19×1 passava | **corrigido**: reticulado `DERIVAVEL`; contam só unidades com profundidade em treino e teste | `test_f1_05_*` |
| F1-06 | material | `insumos_preliminares=0` era constante declarada; mutante lia 76 preliminares e passava | **corrigido**: motor mede pelo efeito (reexecuta sem preliminares; `dependeu_de_preliminar`); `proportional` opta por `aceitar_parcial=True`, `greedy` recusa | teste com mutante que declara 0 e é pego |
| F1-07 | material | Auditoria null×zero invariante para políticas por razão (13/40 escapes); flag `cega_a_dados` omitida | **corrigido**: perturbação de uma unidade só; 0 escapes no reprodutor; flag publicada | `test_f107_*` |
| F1-08 | material | `contribuicao` transformava receita inferida/parcial/preliminar em lucro sem marca | **corrigido**: recusa método não reconciliado e cobertura parcial (salvo opt-in), marca `preliminar`/`cobertura_completa` | `test_f1_08_*` |
| F1-09 | menor | Conclusões de baseline por mediana de 5 seeds escondiam bimodalidade | **corrigido**: 30 seeds, média/dp/p10/p90/pior caso e diferença pareada vs `equal` com IC. **Leitura mudou** (ver §4) | `results/replay/REPLAY-RESULTS.md` |
| F1-10 | menor | Surrogate concluía de n=3; "IC > 0" passava com sinal nulo | **corrigido**: descritivo real marcado não interpretável e sem conclusão; critério `P(skill>1%) ≥ 0,8` conferido contra sinal nulo; calibração passou de 20×60 para **50×90** | `test_f1_10_*`, `SURROGATE-RESULTS.md` §3 |
| F1-11 | menor | Zeros 0,00 de fonte com `DEFAULT 0` viravam rótulo; `or 0` no golden | **corrigido**: zero ambíguo sai do rótulo (16 → 14 linhas Senac); nulo propaga | `test_f1_11_*` |
| F1-12 | menor | Manifestos de replay/bench sem hash de código/resultado | **corrigido** | JSONs regenerados |
| F1-13 | menor | Números do BENCH-RESULTS não batiam com o JSON; ponto de corte do Polars ignorava conversão | **corrigido**: MDs gerados por `replay_relatorio.py`/`bench_relatorio.py`; engine `polars_de_tuplas` | — |
| F1-14 | menor | Brechas: `politica_futuro` com erro de digitação, `complete` medido no meio da janela, enum como str burlando X02, sinal `"abc"`/NaN, `filtrar` ignorando conta | **corrigido** (todas) | `test_f1_14_*` |
| F1-15 | menor | Manifesto mutável permitia forjar fingerprint registrado | **corrigido**: `MappingProxyType`, fingerprint fixado, integridade confere contagens | `test_f1_15_*` |
| F1-16 | menor | 8 guardas sem teste; teste "vazio vira None" tautológico | **corrigido**: testes para as 8; teste compara contagem de células vazias do CSV com `None` | `test_f1_16_*` |
| F1-17 | nota | Valores monetários diários reais de cliente nomeado nos docs | **corrigido**: substituídos por ordem de grandeza (o CSV de origem já é versionado fora do namespace) | diff dos docs |
| H1–H3 | hipótese | adaptadores reais com tz diferente; "~22×" pós-perf; plano Polars na 2.0 | H1 coberta pelo UTC canônico; H2 confirmada e corrigida (agora 12×); H3 **não testada** | — |

## 2. F2 — Stat Lab

| ID | Sev. | Achado | Resposta | Prova |
|---|---|---|---|---|
| F2-04 | material | Conclusões de maturação "demonstradas" sem IC | **corrigido**: viés com IC95 por mundo (bootstrap B=2000). `receita_estavel` 1–2 d: +1,0% [−4,3; +6,3] → "sem viés detectável" (não demonstra viés pequeno); centavo idade 0: −10,5% [−21,4; +1,2] → **não demonstrado**; D+1: −11,0% [−18,9; −2,4] → se sustenta | `STATLAB-RESULTS.md` |
| F2-05 | menor | Teste de CS aceitava CS inválida | **corrigido**: limite superior ≤ α com 2000 trajetórias, valores de referência à mão, implementação escalar independente | mutantes CS1–CS6 mortos |
| F2-06 | menor | Guarda de maturação duplicada, só uma testada | **corrigido**: `motivo_guarda()` única | MAT1/2/4 mortos |
| F2-07 | menor | Conferência BH absolvia quase tudo | **corrigido**: só empate genuíno no corte; 0 divergências fora da fronteira, 1 empate exato; mutante gera 402 divergências | teste de poder |
| F2-08 | menor | ~60 números digitados à mão no MD | **corrigido**: gerado dos JSONs; teste exige reprodução byte a byte | `test_statlab_relatorio_sonda.py` |
| F2-10 | menor | Calibração de estimador constante publicada | **corrigido**: n/a; top-k sob desempate aleatório (9,67 = sorteio) | SH1/SH2 mortos |
| F2-15 | nota | `janela_fechada` é o oráculo deslocado | **corrigido no texto** + métrica comparável no calendário | JSON marca a derivação |
| F2-16 | nota | Sonda confseq gravava "FALHOU" fixo | **corrigido**: status derivado do log (segue FALHOU) | SONDA1 morto |
| F2-17 | nota | pmf zerava o último bin | **corrigido** (efeito desprezível) | MAT7 morto |

Limitações aceitas do Stat Lab: viés do guarda no cenário de centavo não demonstrado com 300 mundos; IC entre mundos degenera em 0%/100%; calibração instável com variância minúscula (IC largo publicado). 19/19 mutantes do Stat Lab morrem.

## 3. F2 — Swarm e bibliotecas

`PRE-REGISTRO.md` não foi tocado (`git diff fc05316a` vazio; sha256 `453e0aff…`). Grids regenerados com o código final: 0 diferenças nos campos pré-registrados.

| ID | Sev. | Achado | Resposta | Prova |
|---|---|---|---|---|
| F2-01 | material | Métrica pré-registrada de falsos vencedores pune o ótimo (orçamento forçado; o oráculo "não supera" em 8/12) | **corrigido como exploratório**: resultado pré-registrado mantido; nova métrica `excesso_perdedoras_vs_oraculo` (oráculo = 0); linha do oráculo nas tabelas. Base: greedy 0,101, SH 0,161. Veredito exploratório também NÃO (falha sempre o regret) | `swarm_principal.json` → `pos_registro` |
| F2-02 | material | Resumo causal errado (interferência favorece SH/ASHA; saturação omitida) | **corrigido**: DiD e varredura de saturação PÓS-REGISTRO. Saturação +1794 [1620; 1968] e maturação heterogênea +1308 pioram SH; interferência −220 [−429; −10] **favorece**; não estacionariedade n.s. Sem saturação (cap ×100) SH ganha no pareado −227, mas 0/80 comparações "superam" por qualquer regra | `swarm_pos_registro_{did,saturacao}.json` |
| F2-03 | material | Caminho do veredito sem teste (7 mutantes sobreviviam) | **corrigido**: testes unitários do critério, valores conhecidos, regressão do veredito em 6 seeds | `swarm_mutantes.json`: 11/11 mortos |
| F2-09 | menor | "Melhor SH no base" errado | **corrigido**: `SWARM-TABELAS.md` gerado dos JSONs (`sh_e2_r120brl_gasto_parcial` 8.997) | — |
| F2-11 | nota | 48 combinações de sensibilidade, 42 cenários distintos | **corrigido** na contagem; duplicatas marcadas | — |
| F2-12 | nota | H3 pré-registrada refutada no caso uniforme | **corrigido no texto**: "refutada como formulada"; efeito heterogêneo declarado pós-hoc | — |
| F2-13 | nota | Precedência do pré-registro só por mtime | **limitação aceita**: PRE-REGISTRO 00:08:58, grids 00:15:23–00:22:46, commit 00:26:15 | `SWARM-RESULTS.md` |
| F2-14 | nota | 60/60 vs Optuna valida regra que nenhuma política usa | **corrigido no texto**; política ASHA (variante de promoção) **sem referência externa** — limitação aceita | — |
| F2-18 | nota | Teste anti-rede frágil | **corrigido**: AST de todos os imports + busca de `__import__`, `importlib`, `subprocess`, `socket`, `eval/exec`, `urlopen`; exceção única e explícita `swarm_mutantes.py` (subprocess para pytest local) | contraprova com 6 formas escondidas |
| H-01 | hipótese | H2 sob valor heterogêneo por evento | **não testado** | — |

`LIBRARY-DECISIONS.md` foi revisado por F2 sem achados próprios.

## 4. Leituras que mudaram por causa da revisão

1. **Replay (F1-09):** com 30 seeds e diferença pareada vs `equal`, `greedy_conservador` é melhor só no estacionário (−91 bps [−172; −9]); `proportional` é significativamente **pior** no estacionário (+516) e com lacunas altas (+587); na quebra de regime e no preliminar otimista **nenhuma política supera `equal`**. A leitura anterior (proportional vence com quebra de regime) era artefato de mediana de 5 seeds.
2. **Bancada:** contrato 12× mais lento que tuplas em 1e5 (era ~22× antes da otimização); em 1e6, Polars 5,1×, DuckDB 4,2×, Polars a partir de tuplas 2,5× sobre Python puro, com pico de RSS do Polars 1,8–2,0 GB. Veredito mantido: não compensa no volume atual do replay (≤ ~13 mil obs por corte).
3. **Surrogate:** volume mínimo para relevância com sinal fraco subiu para 50 campanhas × 90 dias; veredito `dados insuficientes` mantido com folga.
4. **Maturação:** o "viés ≤ 1%" no regime estável e o viés no cenário de centavo deixaram de ser demonstrados.
5. **Swarm:** o "NÃO" se mantém, mas a causa é saturação e maturação heterogênea, não interferência (que favorece SH/ASHA); a métrica pré-registrada de falsos vencedores estava mal construída e foi complementada por uma relativa ao oráculo.
