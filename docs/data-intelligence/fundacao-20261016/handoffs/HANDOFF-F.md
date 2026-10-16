# HANDOFF-F — Model Lab e "ouros" quantitativos (worker F → integrador I)

Branch `lab/dil-fundacao-20261016-f` (worktree esparso `worktrees/dil-fundacao-20261016-f`), base `0643fbe4`.
Estado-teto: **testado com sintético**. Nada calibrado com dado real, nada em shadow, nenhuma política.
Documentos: `08-MODEL-LAB.md` (uma seção por técnica + tabela-resumo), `10-BACKLOG-OUROS.md` (todas as
ideias/hipóteses/não promovidos, desta missão e herdados, com roadmap mais próximo).

## 1. Arquivos

| Caminho | Conteúdo |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/modelos/__init__.py` | API pública (funções puras para o shadow) |
| `…/modelos/base.py` | `Achado`, `ic_bootstrap_media`, reexporta `ResultadoInsuficiente`/envelope do Stat Lab |
| `…/modelos/dados.py` | `TabelaVersoes`: painel `as_of` vetorizado, provado equivalente a `visao_as_of` |
| `…/modelos/maturacao.py` | triângulo `as_of`, `nowcast`/`maturar` (CL herdado, BF, fixo), `monitor_maturacao`, `regime_vigente`, curva intradiária |
| `…/modelos/eb.py` | fachada do EB herdado + `vencedores_por_sorte` |
| `…/modelos/mudanca.py` | `media_movel`, `cusum`, `bocpd`, `detectar_quebra`, `calibrar_limiar` |
| `…/modelos/sequencial.py` | `eprocesso_media_limitada`, `e_bh`, `p_binomial_unilateral`, `normalizar_por_limite` (+ CS/BH herdados) |
| `…/modelos/causal.py` | `did_painel`, `tendencias_paralelas`, `placebo_temporal`, `placebo_unidades`, `controle_sintetico(_placebo)` |
| `…/modelos/bandits.py` | `Uniforme`, `Gulosa`, `LinUCB`, `ThompsonLinear`, `rodar`, `ips`, `snips`, `dr`, `PropensaoAusente` |
| `…/modelos/conformal.py` | `quantil_conformal`, `intervalo_conformal`, `escores_escalados`, `aci`, `cobertura` |
| `…/modelos/anomalia.py` | `detectar_anomalias` (lacuna separada), `zero_implausivel`, `nulo_como_zero` (anti-baseline) |
| `…/modelos/alocacao.py` | `ajustar_resposta`, `alocar_orcamento` (KKT), `limites`, `projetar`, `verificar_restricoes`, baselines |
| `…/modelos/tabular.py` | `features_no_corte`, `ajustar`/`ModeloAjustado`, `FeatureMeta`, `checar_vazamento`, `vazamento_empirico` |
| `experiments/data-intelligence-lab/scripts/fundacao_modelos_{comum,maturacao,eb,mudanca,sequencial,causal,surrogate,bandits,conformal,anomalia,alocacao,tabular,relatorio}.py` | experimentos (com `--rapido` que não grava) e gerador do RESUMO |
| `experiments/data-intelligence-lab/results/fundacao/modelos/` | `PRE-REGISTRO.md`, `m1…m12*.json` (13 arquivos), `RESUMO.md` — 172 KB |
| `tests/data-intelligence/fundacao/test_modelos_{dados,maturacao,eb_mudanca,sequencial_causal,bandits_conformal,anomalia_alocacao,tabular_isolamento,relatorio}.py` | 75 testes |
| `docs/data-intelligence/fundacao-20261016/{08-MODEL-LAB,10-BACKLOG-OUROS}.md`, este handoff | documentação |

Não toquei `fundacao/__init__.py`, conftest, `pyproject.toml`/`uv.lock`, roadmap, curadoria, grafo.

## 2. Provas

- Suíte: `OMP_NUM_THREADS=2 <python> -m pytest tests/data-intelligence -q` → **659 passed em 74 s** (584 anteriores + 75 novos); só os novos: 75 em ~8 s.
- Pré-registro commitado antes de qualquer resultado: `eda4f041` (09:56 −03); os scripts vieram depois (`1dd92251`), os resultados no fim (`9182a9a9`).
- `RESUMO.md` é gerado dos JSONs (`fundacao_modelos_relatorio.py`); teste exige regeneração byte a byte e que o `sha256_codigo` de cada manifesto bata com o código atual (todos os JSONs foram regerados com o código congelado).
- Isolamento: teste AST sem `socket/urllib/http/requests/subprocess/importlib/psycopg/supabase/google`, sem `.env`, `os.environ`, `eval/exec`, `~/.ssh` em `modelos/*.py` e nos scripts; conftest herdado bloqueia rede.
- Determinismo: a 2ª rodada completa reproduziu exatamente os números da 1ª (verificado em M1–M5, M7–M10).
- `git diff --check` limpo; resultados < 5 MB.
- Tempos da rodada final (`OMP_NUM_THREADS=2`, um por vez): M1 272 s, M1 pós-registro 128 s, M2 78 s, M3 176 s, M4 12 s, M5 62 s, M6 129 s, M7 208 s, M8 100 s, M9 81 s, M10 162 s, M12 104 s.

## 3. Resultados (sintético; IC95 por bootstrap de seeds)

| técnica | veredito | estado |
|---|---|---|
| Nowcast intradiário do custo D0 | **H1b suportada**: wMAPE 15% do "D0 é final" (0,151 [0,145; 0,156]) | testado com sintético |
| Chain-ladder × BF × fixo (receita) | **H1a refutada**: BF pior (+1,47 p.p. [+0,86; +2,12]); IC80 do CL cobre 70–75% | testado com sintético |
| Monitor de regime de maturação | **H1c refutada** (pré-registrado não calibra: FA 25–52%/mundo); pós-registro calibra e corta viés da idade 1 de −35% para −20% com 48% de recusa | construído · testado hermeticamente |
| EB em campanha nova | **H2 refutada** (só CTR dia 1: MSE 0,70; RPM dia 3: 0,84; sorte sem diferença) | testado com sintético |
| CUSUM/BOCPD × média móvel | **H3 refutada** (CUSUM +0,023 [+0,005; +0,040]; BOCPD −0,10, mas avisa 1,5 dia antes) | testado com sintético |
| e-BH / CS | **H4a e H4b suportadas** (FDR e-BH ≤ 0,009 vs BH 0,28 com 50 olhadas; custo de poder com efeito fraco: 0,06–0,09 vs 0,55–0,66) | testado com sintético |
| DiD / controle sintético | **H5a refutada** por pouco (lucro −0,67 [−1,37; −0,02]); **H5b refutada** (errata R2/G9: DiD enviesado ✓, antes/depois menos enviesado ✗, −0,38 [−0,71; −0,09]); diagnósticos não pegam seleção | testado com sintético |
| Surrogate | veredito herdado não muda; 50×90 ainda insuficiente, 50×100 viável; portão não vê R2 | hold |
| Bandits + OPE | **H7a refutada** (LinUCB supera equal e guloso; Thompson não supera guloso); **H7b refutada** na variância (alvo uniforme); IPS não-viesado, inventada enviesa, sem propensão recusa | testado com sintético; OPE real impossível |
| Conformal | **H8a suportada** (0,895); **H8b refutada** na degradação (split 0,866); ACI 0,901 | testado com sintético |
| Anomalias | **H9a refutada**; **H9b suportada** (0 anomalias em lacuna; null→0: 31,8 falsos/janela); **H9c refutada** (precisão 0,76) | testado com sintético |
| Alocação | **parcial**: **H10a suportada** (histórico as_of maduro após errata R2/G10: regret 116 vs equal 1865, proporcional 1385, guloso 370); **H10b refutada**: ganho de primeira ordem (cortar ROAS < 1), b no teto em 30–40% | testado com sintético |
| SH/ASHA | não reaberto; nenhuma premissa mudou a favor | negativo preservado |
| Ridge × HGB | **H12 suportada** (Ridge 1,006× a média dos maduros; HGB 1,027×); vazamento 100% detectado | testado com sintético |
| DuckDB/Polars, bibliotecas | só referência; nenhuma dependência nova | — |

## 4. Falhas e correções durante o trabalho

1. **Bug real achado por teste:** `aci` não atualizava α quando o intervalo era infinito (α preso abaixo de 0 → cobertura 0,96 em vez de 0,90). Corrigido antes dos experimentos.
2. **Monitor de maturação pré-registrado não calibrou** (MAD de 14–30 pontos subestima a escala de uma razão com cauda pesada; segmentação iterativa multiplica chances). Resultado negativo preservado; variante conservadora rodada e marcada **pós-registro** (`m1_maturacao_pos_registro.json`).
3. **Vazamento no meu primeiro adaptador do surrogate:** usava o valor final da feature com a disponibilidade da 1ª versão. Pego antes do resultado final; corrigido para o valor conhecido às 20h de D+1. O resultado publicado é só o corrigido (o achado "uma linha tardia remove a feature inteira" virou inferência de código, não demonstração).
4. Sombra de variável (`k` do CUSUM × laço) quebrou a 1ª execução pós-registro; corrigido.
5. H7b no 1º rascunho do script olhava só o alvo favorável; corrigido para exigir os dois alvos (o pré-registro não escolhia alvo) — resultado: refutada.
6. Dois testes iniciais afirmavam propriedades falsas (CUSUM sem alarme em 185 passos com referência de 15 pontos; ACI dentro da faixa só no pós-quebra). Reescritos para a propriedade verdadeira (FA cai com h; garantia de longo prazo de Gibbs & Candès); nenhum código foi afrouxado.
7. Exportações faltantes (`bh`, `cs_prpl_eb`, `bocpd_posterior`) quebraram duas execuções; corrigidas.
8. Exportação de snapshot real continua bloqueada (herdado do recibo): nenhum replay com dado real.

## 5. Riscos

1. **Leitura de simulação como evidência.** Todo número aqui é sintético; o gerador decide a força do sinal (ex.: surrogate skill 0,30 por construção).
2. **Alocador "vence" por primeira ordem**: em dado real o corte de ROAS < 1 depende de receita madura e reconciliada (P06-T03/T04); com ROAS mal medido o allocator corta campanhas boas.
3. **Monitor de maturação** com FA alta geraria recusas em massa no shadow.
4. **Detectores com limiar fixo** sem calibração de FA em dado real são ruído (procedimento `calibrar_limiar` existe).
5. **OPE**: qualquer avaliação offline sem propensão logada é inválida; propensão estimada depois do fato enviesa muito.
6. **Causal**: os diagnósticos de pré-tendência passam mesmo sob seleção pelo resultado — não usar como "prova" de efeito.
7. Determinismo entre plataformas não testado (versões no manifesto).

## 6. API para o worker D (shadow)

```python
from volc_dil.fundacao import modelos as M
tab = M.TabelaVersoes.de_registros(registros, fonte="joinads", metrica="revenue", entidades=..., dias=...)
P = tab.painel(as_of_epoch)                                   # (E, D) NaN = desconhecido (= visao_as_of)
tri = M.triangulo_de_tabela(tab, calendario, hora_corte=12, idade_max=7)["agregado"]
M.maturar(tri, as_of_dia, M.ConfigNowcast(janela_coortes=14, maturidade_minima=0.05, min_coortes=5),
          monitor=[M.ConfigMonitor(idade=0, janela_ref=14, k=1.0, h=16.0, escala="max_mad_dp")])
M.nowcast_intradiario(v_h, fator_h, n_h, cfg)                 # custo projetado do dia
M.detectar_quebra(serie, metodo="cusum", n_ref=14, k=0.5, h=15.0)       # -> Achado
M.detectar_anomalias(valores, metodo="robusto_mad", limiar=3.5, janela=14, status=status)  # lacuna ≠ anomalia
M.zero_implausivel(contagens, janela=7, p_max=1e-3, status=status)
M.intervalo_conformal(previsao, escala, escores_cal, alpha=0.1); M.aci(...)
M.alocar_orcamento(curvas, total=..., lo=lo, hi=hi, aversao=0.0); M.verificar_restricoes(x, lo, hi, total)
M.e_bh(e_values, q=0.1); M.eprocesso_media_limitada(x01, mu0)
M.ips(log, pi_alvo)   # levanta PropensaoAusente sem propensão
M.checar_vazamento(metas, origem)
```
Os limiares acima são os usados no laboratório — parâmetros, não política.

## 7. Pedidos de dependência

Nenhum.

## 8. Delta de curadoria proposto (NÃO aplicado; decisão do integrador)

| Tarefa | Estado atual | Proposta | Evidência | Lacuna honesta |
|---|---|---|---|---|
| P14-T06 Ledger e registry do preditivo | `todo` | manter `todo`; registrar insumo: contrato de feature com `disponivel_em` (`FeatureMeta`/`checar_vazamento`) e manifesto de resultado (seeds, sha256 do código, versões) prontos em laboratório | `modelos/tabular.py`, `m12_tabular.json`, `test_modelos_tabular_isolamento.py` | nenhuma tabela no Supabase; nenhuma previsão shadow persistida |
| P14-T07 Baseline preditivo sem vazamento | `todo` | manter `todo`; registrar bancada rolling-origin `as_of` com "último maduro"/"média dos maduros" lado a lado, rótulo de treino só maduro, feature do futuro detectada em 100%; Ridge/HGB não superam a média dos maduros | `08` §12, `m12_tabular.json` | dado real; previsão imutável gravada antes do realizado; aceite pede outputs não negativos (lucro pode ser negativo: definir alvo) |
| P14-T08 Intervalos, champion/challenger, drift | `todo` | manter `todo`; registrar: split conformal (0,895) e ACI (0,901) cobrem o nominal em sintético; CUSUM calibrado por FA; monitor de maturação (pré-registrado falhou) | `08` §1, §3, §8; `m8_conformal.json`, `m3_mudanca.json`, `m1_*.json` | champion/challenger não feito; nada com dado real |
| P14-T09 Simulador read-only de planned_spend | `todo` | manter `todo`; anotar que o grid gasto→lucro por re-simulação CRN (oráculo do M10) existe em laboratório | `scripts/fundacao_modelos_alocacao.py` | modelo calibrado em dado real; exposição read-only no QG |
| P14-T10 Validade científica do Predictive Core | `partial` | manter `partial`; acrescentar evidência de método (as_of por `available_at`, rótulo maduro, detecção de vazamento, comparação pareada na mesma população) | `08` §12, `PRE-REGISTRO.md` | o spike rejeitado não foi reavaliado; nada real |
| P09-T11 Allocator em replay offline | `todo` | manter `todo`; registrar: allocator com restrições verificadas (0 violações) implementado no laboratório; regret simulado muito menor que equal/proporcional, mas por primeira ordem (cortar ROAS < 1); curvatura não identificada sem variação exógena | `08` §10, `m10_alocacao.json` | replay com dado real; campanhas sem consumo de orçamento seguem inelegíveis |
| P09-T13 Allocator em shadow com propostas T1 | `todo` | manter `todo`; acrescentar dependência: propensão logada em cada proposta (para OPE) e P09-T11 real | `08` §7, §10 | nenhuma proposta real |
| P15-T08 Cenários no QG e na Bia em shadow | `todo` | manter `todo`; anotar: atribuição observacional erra sob seleção pelo resultado e os diagnósticos não avisam — cenário exposto precisa declarar o desenho (aleatorizado × observacional) | `08` §5, `m5_causal.json` | depende de modelo aceito (P15-T07) |

Nós do grafo sugeridos: `volc_dil.fundacao.modelos` (cluster decisão/dados, estado `experimento`); arestas
`modelos → statlab` (reuso), `modelos → simulador` (avaliação), `modelos → shadow (D)` (API),
`modelos → qualidade (G)` (lacuna ≠ anomalia, zero implausível, `calibrar_limiar`), `modelos → P14-T07/T08`,
`modelos → P09-T11`.

## 9. Errata — 2026-10-16 (revisão adversarial R2)

Correções pedidas pelo integrador sobre `2d403e19` (merge local `462ac499`); pré-registro intacto; resultados
antigos preservados em `results/fundacao/modelos/errata_20261016/`; errata datada em `08` §16 e no fim do `RESUMO.md`.

| achado | correção | antes | depois |
|---|---|---|---|
| G9 | H5b avaliada pelas duas condições pré-registradas; veredito sai de `H5b_criterios` | suportada | **refutada** (DiD enviesado ✓; antes/depois mais enviesado ✗) |
| G10 | M10 decide com o painel `as_of` maduro observado (dias com custo e receita `final` no instante da decisão), não com a verdade diária; `08` §0 deixa de contar M10 como aprovada | H10a sim / H10b não | H10a sim (116 vs 1865) / H10b não; M10 = parcial |
| G13 (F4) | testes de comportamento que matam o painel ordenado por chegada (regra pré-D1) sem depender da guarda de hash | mutante sobrevivia | morto por 2 testes |

Tempos da reexecução: M5 40 s, M10 268 s (`OMP_NUM_THREADS=2`, um por vez).
