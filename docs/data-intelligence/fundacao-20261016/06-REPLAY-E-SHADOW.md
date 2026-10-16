# 06 — Replay `as_of` e shadow engine

Thread D da missão "Fundação Data Intelligence" (2026-10-16). Branch `lab/dil-fundacao-20261016-d`.

| Peça | Caminho | Estado (taxonomia do manifesto §7) |
|---|---|---|
| Pacote | `experiments/data-intelligence-lab/src/volc_dil/fundacao/shadow/` (14 módulos) | construído, **testado hermeticamente**, **testado com sintético** |
| Adaptador para dado real | `.../shadow/real.py` + `linhas_formato_real.py` | testado com fixtures **sintéticas no formato real**; **não executado com dado real** |
| Ponte com o simulador (E) | `.../shadow/fonte_simulador.py` | testado com sintético (desde o merge da branch da missão, no próprio worktree) |
| Script | `experiments/data-intelligence-lab/scripts/fundacao_shadow.py` | `--sintetico`, `--simulador`, `--verificar`, modo real |
| Resultados | `experiments/data-intelligence-lab/results/fundacao/shadow/{shadow_resultados.json, SHADOW-RESULTS.md}` | gerados, determinísticos |
| Testes | `tests/data-intelligence/fundacao/test_shadow_*.py` | 76 (inclui `test_shadow_r2.py`, respostas à R2) |

**Nada aqui é `testado em replay` (dado real), `rodando em shadow`, `calibrado` ou eficácia.** Toda
comparação entre políticas é contra a verdade de um gerador sintético.

---

## 1. Arquitetura

```text
linhas v21 / JoinAds v2 (02 §9) ──adaptadores A──┐
RegistroObservacao (simulador E) ──fonte_simulador┤
gerador provisório (linhas no formato real) ──────┘
        │  dedup = Registro D2' da A (releitura redundante vira confirmação; nunca por run)
        ▼
fluxo append-only de Observacao ──► FluxoIndexado (chaves calculadas 1×, ordenado por available_at,
        │                                          hash encadeado dos visíveis, fato de topo ambíguo fora)
        ▼  corte T (ex.: a cada hora de coleta)
as_of(T) (regra da A) ──► juntar_campanha_dia (C), por dia e por moeda ──► SnapshotShadow (imutável, fingerprint)
        │                                                                     │ só isto entra na política
        ▼                                                                     ▼
Diagnostico ◄── política determinística (manter, equal, greedy, regra_margem, guardião 72 h, controles)
        │                                  │
        ▼                                  ▼
kernel de bloqueios (identidade, ambiguidade, custo dimensionado, moeda, câmbio, custom_key trocada,
                     cobertura comprovada contra /earnings, grão misto)
        ▼
PropostaShadow (executavel=False SEMPRE) ──► LedgerShadow (JSONL, hash encadeado, append-only)
        ▼  D+1+k
resultado maduro observado (+ contrafactual verdadeiro, só com gerador) ──► ledger ──► avaliação
```

Peças e responsabilidades (domain/application/infra no sentido do CLAUDE.md: tudo aqui é domínio puro +
um único adaptador de arquivo, o `SinkJsonl`):

| Módulo | Faz | Não faz |
|---|---|---|
| `fluxo.py` | índice por `available_at`; `as_of(T)` idêntico ao da A (delega a `vigente_entre`); fingerprint dos visíveis; quarentena: fato com topo ambíguo sai do corte (`ambiguos_em`) | não lê banco nem relógio; não escolhe entre leituras empatadas |
| `snapshot.py` | fatos campanha × dia (custo, receita, status fino, idade, versões), cobertura por dia, bloqueios, diagnósticos de dado; compatível com as duas APIs da junção da C | não guarda `Observacao` nem o fluxo |
| `politicas.py` | catálogo determinístico; baselines herdadas por composição (`volc_dil.replay.politicas`) | não chama LLM, rede ou banco |
| `kernel.py` | valida que a proposta é do corte; anota bloqueios | não troca a ação proposta |
| `motor.py` | replay serial/paralelo; detector de vazamento; auditoria null × zero | não escreve fora do ledger |
| `ledger.py` | ledger append-only com hash encadeado; sink JSONL restrito | não tem update/delete |
| `avaliacao.py` | plano diário → lucro contrafactual, regret, drawdown, cortes errados, estabilidade; resultado maduro no ledger | não vira "eficácia" |
| `real.py` | linhas reais → adaptadores A → `Registro` D2' (dedup) → replay | não abre conexão; não tem regra de dedup própria |
| `fonte_simulador.py` | `RegistroObservacao` → `Observacao`; `VerdadeSimulador` (re-simula o `Mundo` com outra verba) | o `Mundo` nunca entra no snapshot |
| `_gerador_provisorio.py` | mundo mínimo campanha × dia + linhas no formato real (isolado para troca) | — |
| `controles.py` | controle negativo (`PoliticaTrapaceira`) e corte errado por `observed_at` | só existem para serem pegos |

## 2. Dataset temporal

- **Cortes:** `cortes_regulares(inicio, fim, passo)` — por padrão a cada hora. O mesmo fluxo gera 241 cortes
  em 10 dias; cada corte é um prefixo do fluxo ordenado por `available_at`.
- **Estado `as_of(T)`:** por chave natural, entre as leituras com `available_at <= T`, vence a de maior
  `observed_at`, depois a de maior `available_at` (regra D1 da A: uma leitura antiga chegando atrasada não desfaz
  a mais nova). O índice delega a seleção a `observacao.vigente_entre`; a equivalência com
  `volc_dil.fundacao.observacao.as_of` é provada corte a corte (`test_as_of_do_indice_igual_ao_da_thread_a_em_todos_os_cortes`).
- **Caminho real:** a dedup é o `Registro` D2' da A (R2-G2): releitura redundante vira confirmação, A→B→A e o
  fechamento da janela viram versão, e uma confirmação mais nova é materializada se uma leitura antiga atrasada
  fosse passar à frente — `as_of` sobre as versões = `as_of` sobre todas as leituras, em qualquer ordem
  (`test_g2_releitura_nova_nao_perde_para_leitura_antiga_atrasada`, todas as permutações e cortes). A dedup própria
  anterior ("manter a primeira") quebrava D1 e foi removida.
- **Ambiguidade:** duas leituras diferentes empatadas no TOPO da ordem de versão param o `as_of` da A. No replay
  (`ambiguidade="quarentena"`), o fato INTEIRO sai do corte, a entidade recebe `versao_ambigua:<métrica>:<dia>`
  e o snapshot registra `versao_ambigua_em_quarentena`; nenhuma versão superada é ressuscitada (R2-G11). Empate já
  superado por leitura mais nova não afeta o corte.
- **Custo campanha × dia:** só a leitura SEM dimensões é o custo do dia. Se só há leituras dimensionadas
  (ex.: por dispositivo), o custo sai `invalid` e a entidade é bloqueada (`custo_so_com_dimensoes:<dia>`): somá-las
  exigiria uma partição declarada que o contrato não tem (R2-G12). Havendo o total, ele vence e as dimensionadas
  viram diagnóstico `custo_dimensionado_ignorado`.
- **Junção:** `identidade.juntar_campanha_dia` um dia por vez (cobertura por dia; balde `nao_atribuivel`;
  só receita determinística entra na linha). Moedas de receita diferentes no mesmo dia são juntadas em
  partições por moeda; a mesma campanha com receita em duas moedas no dia vira `moeda_misturada`.
  Dois endpoints/grãos de receita no mesmo dia (R1-F5, dupla contagem) não são somados: o dia fica sem
  receita e com bloqueio `receita_recusada_pela_juncao`. Com a API nova da C passam `as_of=T`, a identidade
  da linha (`endpoint`, `grao`, `dimensao`, `disponivel_em`) e o universo kv coletado; erros tipados da junção
  viram bloqueio do dia. A cobertura é guardada POR MOEDA com o seu denominador (`earnings_dominio_dia`,
  `soma_key_value` ou `indisponivel`); earnings sem valor (`unavailable`) vale para toda partição.
- **Fingerprint do corte:** sha256 de {esquema, T, rótulo, config, **hash encadeado de todas as
  observações visíveis** (chave natural, chave de idempotência, `available_at`, status, valor, moeda,
  cobertura), contagem de visíveis, fatos, cobertura, bloqueios, diagnósticos, **versão do código**}.
  Versão do código = sha256 do conteúdo de `fundacao/{shadow,observacao,identidade}`, `replay/{politicas,motor}.py`
  e `contracts` (chave = caminho relativo, independe da máquina). Observação futura não entra nem como contagem.

## 3. Garantias e como são provadas

| Garantia | Como | Teste |
|---|---|---|
| Nenhuma informação futura | a política recebe só `SnapshotShadow` (sem `Observacao`, sem fluxo; recusa outro tipo); integridade conferida antes e depois da política; contraprova: injetar observações com `available_at` no meio dos cortes → políticas honestas mudam **só depois**; o controle `PoliticaTrapaceira` (captura o fluxo) muda **antes** e é detectado | `test_sem_informacao_futura_e_trapaceira_detectada`, `test_snapshot_imutavel_sem_observacao_e_com_integridade`, `test_politica_recusa_o_que_nao_e_snapshot`, `test_observacao_futura_nao_muda_snapshot_nem_fingerprint` |
| Retrodatado não vaza | o corte é por `available_at`; uma versão com `observed_at` retrodatado só aparece quando chega; o corte errado por `observed_at` deixaria entrar | `test_retrodatado_nao_vaza_porque_o_corte_e_por_available_at`, `test_retrodatado_so_vazaria_com_corte_por_observed_at` (simulador `vazamento_tentado`) |
| Restatement tardio não reescreve | linhas do ledger com T anterior ao restatement são **byte a byte** iguais com e sem ele; o restatement aparece em T' > T | `test_reprocessamento_tardio_nao_reescreve_decisao_gravada` |
| null ≠ 0 | regra madura só usa dias com custo e receita `observed`/`zero_confirmed` e idade ≥ maturidade; auditoria metamórfica (ausência → zero confirmado) mostra que a regra distingue e que a anti-baseline `regra_margem_null_zero` não distingue (sinalizada `suspeita_null_como_zero`); `manter` sai como `cega_a_dados` | `test_null_vira_zero_detectado_pela_auditoria` |
| Zero sintetizado (R3) não é campanha morta | v21 sem linha de métrica → `missing zero_sem_linha_de_metrica` (adaptador A); simulador `zero_confirmed` de custo Google sem payload → `missing zero_sem_prova_de_linha`; nenhuma política honesta corta; a anti-baseline propõe "campanha_morta" e é pega | `test_zero_sintetizado_v21_nao_vira_prova_de_campanha_morta`, `test_zero_sintetizado_do_coletor_nao_vira_corte`, `test_replay_de_linhas_reais_ponta_a_ponta` |
| Identidade trocada bloqueia | dia com `custom_key` substituída → bloqueio para as campanhas sem receita válida no dia; colisão no registro (id em duas contas, UTM textual) → bloqueio da entidade; receita colidida vai ao balde | `test_custom_key_trocada_bloqueia_corte`, `test_colisao_de_identidade_bloqueia`, `test_identidade_trocada_vira_bloqueio_de_dia` |
| Moeda misturada bloqueia | receita da campanha em duas moedas no dia → `moeda_misturada`; custo e receita em moedas diferentes sem câmbio declarado → `insuficiente` + bloqueio `moeda_sem_cambio` | `test_moeda_misturada_e_sem_cambio_bloqueiam`, `test_moeda_misturada_exige_cambio_declarado` |
| Sem dupla contagem de receita | grão/endpoint misto no dia não é somado | `test_grao_misto_de_receita_no_dia_bloqueia_sem_somar` |
| Cobertura comprovada antes de mexer em verba (R2-G3) | num dia de evidência, a partição de receita da campanha precisa de denominador `/earnings` e fração ≥ 9/10; earnings ausente (`soma_key_value`, que dá 1 por construção) ou `unavailable` (`indisponivel`) → `cobertura_receita_nao_comprovada`; fração baixa → `cobertura_receita_baixa`. Relaxamento `aceitar_declarado` só para o simulador (sem earnings), gravado em `config_kernel` no ledger | `test_g3_corte_sem_cobertura_comprovada_e_bloqueado`; a anti-baseline null→0 tem todos os cortes bloqueados por declarar dias sem receita (`test_null_zero_propoe_cortes_infundados_e_o_kernel_bloqueia_todos`) |
| Dedup do caminho real respeita D1 (R2-G2) | `Registro` D2' | `test_g2_…` |
| Ambiguidade não ressuscita versão (R2-G11) | fato fora + bloqueio | `test_g11_quarentena_nao_ressuscita_versao_superada`, `test_quarentena_de_versao_ambigua` |
| Custo dimensionado não é escolhido ao acaso (R2-G12) | recusa + bloqueio | `test_g12_custo_com_dimensoes_nao_e_escolhido_ao_acaso` |
| Mutantes da R2 mortos (R2-G13) | D1 (sem portão de cobertura), D6 (sem a 2ª checagem de integridade), D7 (imaturo só por dias), D10 (custo parcial como fechado) e, extras, G11/G12 — cada um derruba ao menos um teste (mutação conferida com script no scratchpad) | `test_g3_…`, `test_d6_…`, `test_d7_…`, `test_d10_…` |
| Determinismo | sem relógio de parede no ledger; JSON canônico sem float; re-executar = mesmos bytes; `--verificar` regenera e compara o sha | `test_determinismo_bytes_identicos`, `test_avaliacao_deterministica`, `fundacao_shadow.py --verificar` |
| Serial = paralelo | cortes distribuídos em `ProcessPoolExecutor`/`ThreadPoolExecutor`; ledger gravado na ordem (T, política) | `test_serial_igual_paralelo_processo_e_thread` |
| Nenhuma escrita externa | varredura AST do pacote (sem `socket/http/urllib/requests/psycopg/subprocess/supabase/google…`, sem `mutate/post/execute/system/…`, `open` em escrita só no ledger) com contraprova por padrão; em execução, `open` espionado: só `<dir>/ledger.jsonl` é escrito; `PropostaShadow(executavel=True)` levanta `ExecucaoProibida`; sink externo recusado | `test_varredura_estatica_sem_rede_banco_subprocess_mutate`, `test_contraprova_a_varredura_pega_cada_padrao`, `test_em_execucao_so_o_arquivo_do_ledger_e_escrito`, `test_proposta_nunca_executavel`, `test_sink_restrito` |
| Ledger append-only e íntegro | hash encadeado; retomada continua a cadeia; adulteração detectada; resultado exige decisão de referência | `test_shadow_ledger.py` |
| Nenhum LLM decide | as políticas são funções puras do snapshot; a varredura recusa `openai`/`anthropic` | varredura |
| Atribuição ≠ causalidade | só campanha × dia determinístico (C); a avaliação contrafactual existe só com a verdade de um gerador; com dado real só `manter` (realizado) e `pausar` (= 0) são identificáveis | §6 |

## 4. Catálogo de políticas

| Política | Versão (resumo) | Regra | Saídas |
|---|---|---|---|
| `manter` | `manter@1` | não fazer nada | `manter` |
| `equal` | `herdada:equal@v0` | `volc_dil.replay.politicas.Igual` sobre o snapshot reprojetado no contrato herdado; verba vigente = custo fechado de D-1 (proxy) | `aumentar`/`reduzir`/`manter`/`insuficiente` |
| `greedy_conservador` | `herdada:greedy_conservador@v0(7d, mat. 4, teto 20%, margem 5%)` | `GulosaConservadora` herdada (só receita madura) | idem |
| `regra_margem` | `regra_margem@1(pausa<-3000, reduz<0→7000, janela 7, min 3, mat 72h)` | margem madura = (receita convertida − custo)/custo em ≥ 3 dias com custo e receita fechados e idade ≥ 72 h; < −30% → pausar; < 0 → reduzir 30%; senão manter; dado insuficiente, câmbio ausente ou custo zero → `insuficiente` (custo zero confirmado **não** é prova de campanha morta) | `pausar`/`reduzir`/`manter`/`insuficiente` |
| `guardiao_72h[X]` (P05-T09) | `guardiao_72h@1(h=72,min_maduros=3)+X` | campanha nova (< 72 h desde o 1º custo observado **ou** < 3 dias com dado maduro) só recebe `alerta`; corte de X é rebaixado, com a ação original na evidência | `alerta` + as de X |
| `regra_margem_imatura` | `mat=0h` | controle: aceita receita preliminar | — |
| `regra_margem_null_zero` | `null0=1` | ANTI-BASELINE: ausência = 0; "sem custo e sem receita" → pausa por `campanha_morta` | existe para ser pega |
| `controle_trapaceira` | `controle_trapaceira@1` | CONTROLE NEGATIVO: lê o fluxo inteiro e usa a versão final | detectado pelo `detectar_vazamento` |

`PropostaShadow`: política, versão, corte (`as_of`), `fingerprint_corte`, entidade (conta, campanha), ação,
`fator_bps` (verba proposta como fração da atual; 10 000 = manter, 0 = pausar), confiança, motivo,
evidência (dias usados, custo, receita convertida, margem, dias imaturos, recusas, câmbio, idade), bloqueios
do kernel, `executavel=False`. Proposta bloqueada conta como `manter` na avaliação. `Diagnostico`: código,
severidade, entidade, detalhe (ex.: `zero_sem_prova_de_linha`, `campanha_nova_em_observacao`,
`sem_entrega_confirmada`, `versao_ambigua_em_quarentena`, `fonte_ignorada`).

## 5. Ledger

JSONL, uma entrada por (corte, política), `seq` + `hash_anterior` + `hash`; tipos `decisao` (T, fingerprint,
versão do código, política + versão, seed, `config_kernel` — inclusive `cobertura_sem_earnings` —, propostas,
diagnósticos) e `resultado` (referência ao hash da
decisão, corte de maturidade D+1+k, por proposta: `lucro_realizado_manter`, `contrafactual_pausa = 0`,
`ganho_se_pausasse`, e — só com gerador — `verdade_lucro_fator_proposto` / `verdade_lucro_manter`).
Tamanho medido: ~9 MB por cenário de 10 dias × 24 cortes × 8 políticas × 6 campanhas (as evidências
dominam); por isso o script grava ledgers só com `--ledgers DIR` e o resultado guarda o sha256 de cada
ledger. Num job diário real são 24 cortes/dia.

Persistência em Postgres: **não construída** de propósito. A decisão 02 §9.3 reserva `dil_obs` para
observações; um ledger de shadow em banco seria um schema próprio (`dil_shadow`, append-only, mesmas
regras de papéis/RLS de `dil_obs_0001`) — proposta para o integrador, não migration candidata desta thread.

## 6. Avaliação: o que se pode medir

Shadow é malha **aberta** (nada é executado). Métricas sobre a decisão diária às 7 h, aplicada ao dia
seguinte: lucro contrafactual, diferença para `manter` e `equal`, regret contra o oráculo por célula
(máximo de {manter, reduzir 30%, pausar, fator da própria política}), drawdown máximo da diferença
acumulada para `manter`, cortes que perderam dinheiro (e, deles, os feitos com sinal imaturo), propostas
bloqueadas, trocas de ação entre cortes adjacentes, ms por corte.

- **Com gerador** (provisório ou simulador): contrafactual pela verdade. No simulador, `VerdadeSimulador`
  re-simula o `Mundo` com a verba escalada (números aleatórios comuns da E ⇒ contrafactual pareado);
  provado que pausar dá lucro 0 e que a re-simulação com a verba base reproduz o mundo original
  (`test_verdade_simulador_e_pareada`). Limite: o gancho da E é verba DIÁRIA; em `mudanca_orcamento` (verba muda
  às 9h/14h) o `manter` re-simulado com a verba das 00h não reproduz o mundo observado — o JSON traz
  `verdade_manter_vs_mundo` (células divergentes e soma absoluta) e o teste
  `test_divergencia_do_contrafactual_so_onde_a_verba_muda_no_dia` prova que é zero nos demais.
- **Com dado real:** só o lucro realizado de `manter` (o que aconteceu) e o contrafactual de `pausar`
  (= 0, assumindo sem carryover) são identificáveis. `reduzir`/`aumentar` exigem modelo de resposta
  ou experimento — o ledger registra isso como pendência, não como número.

## 7. Resultados — TESTADO COM SINTÉTICO

Gerados por `fundacao_shadow.py --sintetico --simulador` sobre `2d403e19` + respostas à R2; números copiados de
`results/fundacao/shadow/shadow_resultados.json` (sha determinístico `320afd24…`, versão do código `30749a4f…`;
`--verificar` regenera e confere provisório, gates e simulador). Tabelas completas em `SHADOW-RESULTS.md`.
Valores em BRL (micros ÷ 10⁶). Leitura honesta: o mundo provisório foi desenhado com 2 de 6 campanhas de
ROAS 0,45 e 0,60 — qualquer política que corte ganha de `manter` ali; o número não diz nada sobre o VOLC.

### 7.1 Gerador provisório (6 campanhas × 16 dias, 241 cortes horários, 8 políticas, kernel `bloquear`)

| cenário | política | vs manter | regret | cortes | errados | errados (imaturo) | bloqueadas | trocas |
|---|---|---:|---:|---:|---:|---:|---:|---|
| base | equal | −729 | 2.773 | 26 | 12 | 0 | 0 | 120/1440 |
| base | greedy_conservador | 236 | 1.836 | 15 | 0 | 0 | 0 | 120/1440 |
| base | regra_margem | 1.670 | 374 | 27 | 0 | 0 | 0 | 6/1440 |
| base | regra_margem_imatura | 1.862 | 182 | 35 | 2 | 2 | 0 | 4/1440 |
| base | regra_margem_null_zero | 0 | 2.044 | 0 | 0 | 0 | **49** | 88/1440 |
| campanha_nova | regra_margem_imatura | 1.814 | 149 | 33 | 1 | 1 | 0 | 5/1383 |
| campanha_nova | guardiao_72h[imatura] | 1.637 | 327 | 27 | **0** | **0** | 0 | 8/1383 |
| zero_sintetizado | regra_margem | 1.670 | 374 | 27 | 0 | 0 | 0 | 7/1440 |
| zero_sintetizado | regra_margem_null_zero | 0 | 2.044 | 0 | 0 | 0 | **52** | 97/1440 |
| identidade_trocada | regra_margem | 1.119 | 925 | 19 | 0 | 0 | **8** | 9/1440 |
| moeda_misturada | regra_margem | 1.504 | 539 | 18 | 0 | 0 | **9** | 6/1440 |

Leitura: (1) a regra madura não fez corte errado em nenhum cenário provisório; a imatura ganha um pouco mais
**e** erra cortes por sinal imaturo; (2) o guardião elimina o corte errado da campanha nova ao custo de atrasar
cortes certos (1.814 → 1.637); (3) depois do portão de cobertura (R2-G3) a anti-baseline null→0 não executa
NENHUM corte em tese: todos os 49–52 cortes dela no corte diário são bloqueados porque ela declara usar dias sem
receita medida (antes da R2 ela errava 10 cortes no `zero_sintetizado`; a auditoria null × zero continua
sinalizando-a); (4) com identidade trocada, 8 propostas de corte da regra madura são bloqueadas; (5) em
`moeda_misturada` a campanha com receita em BRL não tem `/earnings` na sua moeda — 9 cortes bloqueados por
cobertura não comprovada (antes da R2 este cenário saía igual à base); (6) `equal` perde porque realoca verba
para as campanhas ruins; (7) `restatement_tardio` segue igual à base: o restatement injetado não cruza limiar
(o gate de restatement é provado nos testes). O nº de observações caiu (ex.: base 2.567 → 2.375) porque a
dedup agora é o `Registro` D2' (releituras redundantes viram confirmação).

Contraprovas no próprio relatório: com injeção de futuro no meio de 39 cortes, `regra_margem` e `manter` mudam
0 decisões antes da disponibilidade (19 depois); `controle_trapaceira` muda 20 de 20 antes — **vazou**.
Auditoria null × zero: `regra_margem` distingue (2 de 10 snapshots com lacuna mudam; 9 sensíveis a valores),
`regra_margem_null_zero` é `suspeita_null_como_zero`, `manter` é `cega_a_dados`.

### 7.2 Simulator Lab (thread E)

8 campanhas × 16 dias, seed 20261016, 241 cortes horários, **19 dos 20 cenários** do catálogo 1.0.0, 8 políticas,
kernel `cobertura_sem_earnings=aceitar_declarado` (a E não emite `/earnings`). Fora: `escala_10x` (500 campanhas;
só mede volume — custo por corte em §11 — e não muda decisão por campanha). `sensor_sem_campanha` só mexe no
sensor (ignorado pelo snapshot): decisões idênticas às do `estavel`, provado em
`test_cenario_so_de_sensor_nao_muda_decisoes`. `dedup_por_segundo` também injeta bots no mundo (muda a verdade).
Lucro de `manter` é negativo na maioria (−115): a forma de ROAS da E tem mediana ~1,0 e saturação de verba.

| cenário | equal vs manter | regra_margem vs manter / errados | imatura errados (imaturo) | guardião[imatura] errados | null→0 errados / bloqueadas | bloqueadas (regra) | ms/corte |
|---|---:|---|---:|---:|---|---:|---:|
| estavel | 216 | 30 / 2 | 2 (2) | 2 | 1 / 8 | 0 | 28 |
| campanha_nova_aprendendo | 219 | 50 / 2 | 3 (3) | 2 | 3 / 11 | 0 | 38 |
| atraso_receita_longo | 151 | 64 / 4 | 10 (10) | 8 | 0 / **69** | 0 | 34 |
| restatement_custo | 124 | 13 / 5 | 6 (6) | 5 | 5 / 6 | 0 | 31 |
| fonte_fora_do_ar | 201 | 29 / 1 | 1 (1) | 1 | 1 / **35** | 0 | 35 |
| outlier_bot | 217 | 41 / 2 | 7 (7) | 6 | 6 / 8 | 0 | 39 |
| quebra_regime_rpm | 601 | 349 / 1 | 1 (1) | 1 | 0 / 8 | 0 | 44 |
| mudanca_orcamento* | 131 | 59 / 1 | 1 (1) | 1 | 1 / 6 | 0 | 36 |
| sazonal_fim_de_semana | 189 | 26 / 1 | 1 (1) | 1 | 0 / 7 | 0 | 32 |
| dedup_por_segundo | 217 | 46 / 2 | 7 (7) | 6 | 6 / 8 | 0 | 47 |
| zero_falso | 201 | 30 / 2 | 2 (2) | 2 | 2 / 10 | 0 | 22 |
| zero_sintetizado_coletor | 217 | 30 / 2 | 2 (2) | 2 | 2 / 8 | 0 | 135 |
| identidade_trocada | 137 | 2 / 1 | 1 (1) | 1 | 1 / 18 | **6** | 31 |
| moeda_misturada, vazamento_tentado, custo_d0_multiversao, execucao_presa, gatilho_legado_joinads, sensor_sem_campanha | 211–218 | 30 / 2 | 2 (2) | 2 | 1 / 8 | 0 | 28–66 |

\* `mudanca_orcamento`: contrafactual aproximado — 5 de 128 células com `manter` re-simulado ≠ mundo observado
(soma absoluta 8,0 BRL; `verdade_manter_vs_mundo` no JSON), porque o gancho da E é verba diária; nos outros 18
cenários a divergência é 0.

Leitura: (1) no simulador a regra madura ganha pouco de `manter` e **perde para `equal` em todos os 19 cenários**
— resultado negativo para a regra como alocadora, coerente com a herança (replay v0); (2) o sinal imaturo é o que
mais gera corte errado quando a receita demora (`atraso_receita_longo`: 10 com imatura × 4 com madura) ou há bots
(`outlier_bot`/`dedup_por_segundo`: 7 × 2); (3) a anti-baseline null→0, que antes da R2 errava 18–19 cortes em
`atraso_receita_longo`/`fonte_fora_do_ar`, agora tem 69/35 propostas bloqueadas pelo portão de cobertura (ela
declara dias sem receita medida); (4) `quebra_regime_rpm` é o único cenário em que a regra madura captura parte
relevante do ganho (349 de um regret de 1.078 para `manter`), ainda abaixo de `equal` (601); (5) `identidade_trocada`
gera bloqueios do kernel e fatos ambíguos fora do corte; (6) `gatilho_legado_joinads`, `execucao_presa` e
`sensor_sem_campanha` não mudam decisões (fonte legado e sensor ignorados; runs presos não entregam linhas).

## 8. O que está em cada estado

| Estado | O quê |
|---|---|
| testado hermeticamente | snapshot/fingerprint, isolamento por tipo, kernel (inclusive portão de cobertura), ledger, varredura sem escrita externa, adaptador real com fixtures, dedup = `Registro` D2' |
| testado com sintético | políticas e avaliação no gerador provisório (6 cenários) e no simulador da E (19 dos 20 cenários; `escala_10x` fora, ver §7.2) |
| testado em replay | **nada** — exige a exportação read-only de v21/JoinAds v2 (pendente de autorização do operador; recibo de leituras, "Ação negada") |
| rodando em shadow | **nada** |

Desde o merge da branch da missão no worktree D (`880e1e59`, base `2d403e19`) a ponte com o simulador, a junção
endurecida da C e os testes de `test_shadow_simulador.py` rodam no próprio worktree (antes, o merge tinha sido
negado e a validação foi numa cópia).

## 9. Caminho para `testado em replay` e `rodando em shadow`

**Comando exato quando a exportação read-only for autorizada** (o integrador roda; nada abaixo escreve no banco):

```bash
# 1) exportação read-only (sessão com default_transaction_read_only=on), uma linha JSON por registro.
#    As consultas são as de 02 §9 + r.status AS run_status no v21 (runs presos viram diagnóstico).
#    Destino fora do Git: experiments/data-intelligence-lab/artifacts/ (já fora do versionamento).
psql ... -At -c "SET default_transaction_read_only=on; COPY (SELECT row_to_json(x) FROM (<consulta v21 de 02 §9, + r.status AS run_status, WHERE o.grain='campaign_day' AND o.metric_date >= current_date - 21>) x) TO STDOUT" > artifacts/v21_campaign_day.jsonl
psql ... -At -c "SET default_transaction_read_only=on; COPY (SELECT row_to_json(x) FROM (<consulta JoinAds v2 de 02 §9, WHERE o.metric_date >= current_date - 21>) x) TO STDOUT" > artifacts/joinads_v2.jsonl

# 2) replay as_of horário em shadow sobre o dado real (sem rede; grava só ledger.jsonl e resumo.json)
cd experiments/data-intelligence-lab
.venv/bin/python -I scripts/fundacao_shadow.py \
  --linhas-v21 artifacts/v21_campaign_day.jsonl --linhas-joinads artifacts/joinads_v2.jsonl \
  --saida artifacts/shadow-real-$(date +%Y%m%d) --cambio-usd-brl <taxa declarada pelo operador, ex. 27/5>
```

O que o resumo traz: linhas lidas, observações brutas, repetições descartadas (esperado ~80% no D0, recibo (a)),
quarentena, dead letter, runs presos, nº de cortes/decisões, sha do ledger. Com isso P14-T02 ganha
"normaliza linha real com linhagem" e "compara proposta com ocorrido posterior" (o `resultado` maduro).
Ressalvas que o primeiro replay real vai medir: forma real de `raw_source.metrics` (prova de linha do v21);
fuso de fechamento da JoinAds (aviso permanente no snapshot).

**A fixture "formato real" assume o coletor ENDURECIDO (R2-G22).** Depois da R1-F4 a A só aceita moeda com
prova no payload bruto (`customer.currencyCode` no GAQL do v21; `currency` no corpo da JoinAds). O v21 de hoje
grava `'BRL'` fixo na coluna e não traz a moeda no payload: com linhas reais de hoje, todo custo sai
`invalid moeda_nao_provada` e nenhuma política corta (provado em
`test_g22_sem_moeda_no_payload_o_real_sai_invalid_e_nada_e_cortado`). O primeiro replay real útil exige o
coletor pedindo a moeda — ou o replay roda e só produz `insuficiente`, que é o comportamento correto.

**`rodando em shadow` (proposta, não implantada):** job diário read-only às 07:30 BRT, rodado pelo
integrador/operador (fora do Vercel e do n8n de produção): exporta a janela de 21 dias como acima, roda o
replay dos cortes do dia e anexa ao ledger num diretório fora do Git (ou, depois de ADR, num schema
`dil_shadow` append-only); grava os `resultado` maduros D+5. Nenhuma mutação: o pacote não tem cliente
Google Ads, n8n, Supabase nem HTTP, e o teste de varredura falha se alguém acrescentar. Critério para
qualquer proposta virar humana-em-loop: N semanas de ledger com cortes errados por sinal imaturo = 0,
bloqueios explicados e estabilidade aceitável — decisão do operador, com ADR (P09-T09/P09-T13).

## 10. Achados para outras threads (estado em `2d403e19`)

1. **Ordem de versão `as_of` (A) × consumidor correto do simulador (E):** achado desta thread (A escolhia a maior
   `available_at`; leitura antiga atrasada voltava o valor). **Resolvido pela A (D1, `e77d6a41`)**: vigente = maior
   `observed_at`, depois maior `available_at`; o índice do shadow delega a `vigente_entre`. 0 divergências contra
   `visao_as_of` da E (`test_snapshot_reproduz_o_consumidor_correto_do_simulador`).
2. **v21 D0 × `Registro`:** releitura do mesmo payload com cobertura diferente gerava `ConflitoIdempotencia`.
   **Resolvido pela A (D2/D2')**: `observed_at` entra na chave da leitura e a releitura redundante vira confirmação.
   O shadow passou a usar esse `Registro` como dedup do caminho real (R2-G2).
3. **Ambiguidade dependente da ordem:** **resolvido pela A (D3)**: só empate no topo conta, independente da ordem.
   No shadow, o empate no topo tira o fato do corte e bloqueia a entidade (R2-G11).
4. **Simulador `identidade_trocada`:** gera leituras ambíguas no topo — o `as_of` da A para; o replay tira o fato
   e bloqueia (ver contagens no JSON, `versao_ambigua_em_quarentena`).

## 11. Limites

- Gerador provisório é mínimo (campanha × dia, resposta à verba `f^0,8`, sem carryover); o simulador da E é
  a fonte principal.
- No simulador o portão de cobertura roda com `aceitar_declarado` (a E não emite `/earnings`); com o padrão
  (`bloquear`) todo corte no simulador sai bloqueado — é o que aconteceria com dado real sem earnings.
- `equal`/`greedy` usam o custo fechado de D-1 como proxy de verba (o snapshot não lê orçamento).
- Câmbio é parâmetro declarado (`CambioDeclarado`), nunca observação; sem ele não há margem.
- Sessões do sensor não entram (03 §0: tráfego `nao_atribuivel` por campanha hoje).
- Desempenho (JSON atual): 22–66 ms por corte com 8 políticas e 2,2–8,2 mil observações; 135 ms com 12,8 mil
  (`zero_sintetizado_coletor`); `as_of` é O(visíveis) por corte — para meses de histórico, incremental.
- Contrafactual do simulador é aproximado onde a verba muda dentro do dia (`mudanca_orcamento`, §7.2).
