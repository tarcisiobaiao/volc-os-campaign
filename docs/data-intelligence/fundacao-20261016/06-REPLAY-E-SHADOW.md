# 06 — Replay `as_of` e shadow engine

Thread D da missão "Fundação Data Intelligence" (2026-10-16). Branch `lab/dil-fundacao-20261016-d`.

| Peça | Caminho | Estado (taxonomia do manifesto §7) |
|---|---|---|
| Pacote | `experiments/data-intelligence-lab/src/volc_dil/fundacao/shadow/` (14 módulos) | construído, **testado hermeticamente**, **testado com sintético** |
| Adaptador para dado real | `.../shadow/real.py` + `linhas_formato_real.py` | testado com fixtures **sintéticas no formato real**; **não executado com dado real** |
| Ponte com o simulador (E) | `.../shadow/fonte_simulador.py` | testado com sintético numa árvore combinada (ver §8) |
| Script | `experiments/data-intelligence-lab/scripts/fundacao_shadow.py` | `--sintetico`, `--simulador`, `--verificar`, modo real |
| Resultados | `experiments/data-intelligence-lab/results/fundacao/shadow/{shadow_resultados.json, SHADOW-RESULTS.md}` | gerados, determinísticos |
| Testes | `tests/data-intelligence/fundacao/test_shadow_*.py` | 65 (57 neste worktree + 8 que exigem o simulador) |

**Nada aqui é `testado em replay` (dado real), `rodando em shadow`, `calibrado` ou eficácia.** Toda
comparação entre políticas é contra a verdade de um gerador sintético.

---

## 1. Arquitetura

```text
linhas v21 / JoinAds v2 (02 §9) ──adaptadores A──┐
RegistroObservacao (simulador E) ──fonte_simulador┤
gerador provisório (linhas no formato real) ──────┘
        │  dedup por chave natural + payload (nunca por run)
        ▼
fluxo append-only de Observacao ──► FluxoIndexado (chaves calculadas 1×, ordenado por available_at,
        │                                          hash encadeado dos visíveis, quarentena de ambíguos)
        ▼  corte T (ex.: a cada hora de coleta)
as_of(T) (regra da A) ──► juntar_campanha_dia (C), por dia e por moeda ──► SnapshotShadow (imutável, fingerprint)
        │                                                                     │ só isto entra na política
        ▼                                                                     ▼
Diagnostico ◄── política determinística (manter, equal, greedy, regra_margem, guardião 72 h, controles)
        │                                  │
        ▼                                  ▼
kernel de bloqueios (identidade, moeda, câmbio, custom_key trocada, cobertura, grão misto)
        ▼
PropostaShadow (executavel=False SEMPRE) ──► LedgerShadow (JSONL, hash encadeado, append-only)
        ▼  D+1+k
resultado maduro observado (+ contrafactual verdadeiro, só com gerador) ──► ledger ──► avaliação
```

Peças e responsabilidades (domain/application/infra no sentido do CLAUDE.md: tudo aqui é domínio puro +
um único adaptador de arquivo, o `SinkJsonl`):

| Módulo | Faz | Não faz |
|---|---|---|
| `fluxo.py` | índice por `available_at`; `as_of(T)` idêntico ao da A; fingerprint dos visíveis; quarentena de versões ambíguas | não lê banco nem relógio |
| `snapshot.py` | fatos campanha × dia (custo, receita, status fino, idade, versões), cobertura por dia, bloqueios, diagnósticos de dado; compatível com as duas APIs da junção da C | não guarda `Observacao` nem o fluxo |
| `politicas.py` | catálogo determinístico; baselines herdadas por composição (`volc_dil.replay.politicas`) | não chama LLM, rede ou banco |
| `kernel.py` | valida que a proposta é do corte; anota bloqueios | não troca a ação proposta |
| `motor.py` | replay serial/paralelo; detector de vazamento; auditoria null × zero | não escreve fora do ledger |
| `ledger.py` | ledger append-only com hash encadeado; sink JSONL restrito | não tem update/delete |
| `avaliacao.py` | plano diário → lucro contrafactual, regret, drawdown, cortes errados, estabilidade; resultado maduro no ledger | não vira "eficácia" |
| `real.py` | linhas reais → adaptadores A → dedup → replay | não abre conexão |
| `fonte_simulador.py` | `RegistroObservacao` → `Observacao`; `VerdadeSimulador` (re-simula o `Mundo` com outra verba) | o `Mundo` nunca entra no snapshot |
| `_gerador_provisorio.py` | mundo mínimo campanha × dia + linhas no formato real (isolado para troca) | — |
| `controles.py` | controle negativo (`PoliticaTrapaceira`) e corte errado por `observed_at` | só existem para serem pegos |

## 2. Dataset temporal

- **Cortes:** `cortes_regulares(inicio, fim, passo)` — por padrão a cada hora. O mesmo fluxo gera 241 cortes
  em 10 dias; cada corte é um prefixo do fluxo ordenado por `available_at`.
- **Estado `as_of(T)`:** por chave natural, a versão com maior `available_at <= T` (regra da A). A
  equivalência com `volc_dil.fundacao.observacao.as_of` é provada corte a corte
  (`test_as_of_do_indice_igual_ao_da_thread_a_em_todos_os_cortes`). Versões ambíguas (duas leituras
  diferentes do mesmo fato no mesmo `available_at`) param o `as_of` da A; no replay vão para quarentena
  (saem do índice e viram diagnóstico `versao_ambigua_em_quarentena`), porque escolher uma seria inventar.
- **Junção:** `identidade.juntar_campanha_dia` um dia por vez (cobertura por dia; balde `nao_atribuivel`;
  só receita determinística entra na linha). Moedas de receita diferentes no mesmo dia são juntadas em
  partições por moeda; a mesma campanha com receita em duas moedas no dia vira `moeda_misturada`.
  Dois endpoints/grãos de receita no mesmo dia (R1-F5, dupla contagem) não são somados: o dia fica sem
  receita e com bloqueio `receita_recusada_pela_juncao`. Com a API nova da C passam `as_of=T`, a identidade
  da linha (`endpoint`, `grao`, `dimensao`, `disponivel_em`) e o universo kv coletado; erros tipados da junção
  viram bloqueio do dia.
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
versão do código, política + versão, seed, propostas, diagnósticos) e `resultado` (referência ao hash da
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
  (`test_verdade_simulador_e_pareada`).
- **Com dado real:** só o lucro realizado de `manter` (o que aconteceu) e o contrafactual de `pausar`
  (= 0, assumindo sem carryover) são identificáveis. `reduzir`/`aumentar` exigem modelo de resposta
  ou experimento — o ledger registra isso como pendência, não como número.

## 7. Resultados — TESTADO COM SINTÉTICO

Gerados por `fundacao_shadow.py`; tabelas completas em `results/fundacao/shadow/SHADOW-RESULTS.md`.
Valores em BRL (micros ÷ 10⁶). Leitura honesta: o mundo provisório foi desenhado com 2 de 6 campanhas
de ROAS 0,45 e 0,60 — qualquer política que corte ganha de `manter` ali; o número não diz nada sobre o VOLC.

### 7.1 Gerador provisório (6 campanhas × 16 dias, 241 cortes horários, 8 políticas)

| cenário | política | vs manter | regret | cortes | errados | errados (imaturo) | bloqueadas | trocas |
|---|---|---:|---:|---:|---:|---:|---:|---|
| base | equal | −728 | 2.774 | 26 | 12 | 0 | 0 | 120/1440 |
| base | greedy_conservador | 236 | 1.837 | 15 | 0 | 0 | 0 | 120/1440 |
| base | regra_margem | 1.670 | 374 | 27 | 0 | 0 | 0 | 6/1440 |
| base | regra_margem_imatura | 1.862 | 182 | 35 | 2 | 2 | 0 | 4/1440 |
| base | regra_margem_null_zero | 1.881 | 164 | 49 | 7 | 7 | 0 | 40/1440 |
| campanha_nova | regra_margem_imatura | 1.815 | 150 | 33 | 1 | 1 | 0 | 5/1383 |
| campanha_nova | guardiao_72h[imatura] | 1.637 | 328 | 27 | **0** | **0** | 0 | 8/1383 |
| zero_sintetizado | regra_margem | 1.670 | 374 | 27 | 0 | 0 | 0 | 7/1440 |
| zero_sintetizado | regra_margem_null_zero | 1.410 | 635 | 52 | **10** | 10 | 0 | 43/1440 |
| identidade_trocada | regra_margem | 1.120 | 925 | 19 | 0 | 0 | **8** | 9/1440 |

Leitura: (1) a regra madura não fez nenhum corte errado em nenhum cenário provisório; a imatura ganha um
pouco mais de lucro **e** erra cortes por sinal imaturo; (2) o guardião elimina o corte errado da campanha
nova ao custo de atrasar cortes certos (trade-off explícito: 1.815 → 1.637); (3) a anti-baseline null→0
erra 10 cortes no cenário de zero sintetizado (pausa a melhor campanha por "campanha morta"); (4) com
identidade trocada, 8 propostas de corte foram bloqueadas pelo kernel e contam como manter; (5) `equal`
perde porque realoca verba para as campanhas ruins; (6) `moeda_misturada` e `restatement_tardio`
provisórios saíram iguais à base: a conversão BRL/BRL não muda margens e o restatement injetado não cruzou
nenhum limiar — os gates de moeda e restatement são provados nos testes, não nesses cenários.

Contraprovas no próprio relatório: com injeção de futuro no meio de 39 cortes, `regra_margem` e `manter`
mudam 0 decisões antes da disponibilidade (19 depois); `controle_trapaceira` muda 20 de 20 antes —
**vazou**. Auditoria null × zero: `regra_margem` distingue (2 de 10 snapshots com lacuna mudam, 9 sensíveis a
valores), `regra_margem_null_zero` é `suspeita_null_como_zero`, `manter` é `cega_a_dados`.

### 7.2 Simulator Lab (thread E)

8 campanhas × 16 dias, seed 20261016, 241 cortes horários, 13 cenários do catálogo 1.0.0, 8 políticas;
executado na árvore combinada (§8), versão do código `a1efaf08…` (a junção já é a endurecida pela R1).
Lucro de `manter` no mundo simulado é negativo (−115 na maioria dos cenários): a forma de ROAS calibrada
pela E tem mediana ~1,0 e saturação de verba, então quase qualquer corte ou igualação "ganha" de manter.

| cenário | equal vs manter | regra_margem vs manter / errados | imatura errados (imaturo) | guardião[imatura] errados | null→0 errados | bloqueadas (regra) | ms/corte |
|---|---:|---|---:|---:|---:|---:|---:|
| estavel | 216 | 30 / 2 | 2 (2) | 2 | 4 | 0 | 38 |
| campanha_nova_aprendendo | 219 | 50 / 2 | 3 (3) | 2 | 3 | 0 | 36 |
| atraso_receita_longo | 151 | 64 / 4 | 10 (10) | 8 | 18 | 0 | 35 |
| restatement_custo | 124 | 13 / 5 | 6 (6) | 5 | 7 | 0 | 48 |
| fonte_fora_do_ar | 201 | 29 / 1 | 1 (1) | 1 | **19** | 0 | 67 |
| zero_falso | 201 | 30 / 2 | 2 (2) | 2 | 6 | 0 | 80 |
| zero_sintetizado_coletor | 217 | 30 / 2 | 2 (2) | 2 | 5 | 0 | 195 |
| identidade_trocada | 137 | 2 / 1 | 1 (1) | 1 | 3 | **6** | 54 |
| moeda_misturada, vazamento_tentado, custo_d0_multiversao, execucao_presa (20 runs presos), gatilho_legado_joinads | ≈ estavel | 30 / 2 | 2 | 2 | 4 | 0 | 37–51 |

Leitura: (1) no simulador a regra madura ganha pouco de `manter` e **perde para `equal`** em todos os
cenários — resultado negativo para a regra como alocadora, coerente com a herança (no replay v0 nenhuma
política superava `equal` com confiança fora do estacionário); (2) o sinal imaturo é o que mais gera corte
errado quando a receita demora (`atraso_receita_longo`: 10 com imatura × 4 com madura); (3) a anti-baseline
null→0 explode quando a fonte cai (`fonte_fora_do_ar`: 19 cortes errados × 1 da regra madura) e cai na
armadilha do zero falso; (4) `identidade_trocada` gera bloqueios do kernel e versões ambíguas em quarentena;
(5) `gatilho_legado_joinads` não muda nada porque a fonte legado é ignorada (diagnóstico `fonte_ignorada`);
(6) `execucao_presa` não muda decisões (runs presos não entregam linhas). O guardião só altera a política
imatura (a madura já espera 72 h); no simulador ele reduz pouco (8 × 10) porque a maturação da receita da E
é curta (fecha em D+3 07:00) e as campanhas novas nascem cedo no período.

## 8. O que está em cada estado

| Estado | O quê |
|---|---|
| testado hermeticamente | snapshot/fingerprint, isolamento por tipo, kernel, ledger, varredura sem escrita externa, adaptador real com fixtures |
| testado com sintético | políticas e avaliação no gerador provisório (6 cenários) e no simulador da E (13 cenários, árvore combinada) |
| testado em replay | **nada** — exige a exportação read-only de v21/JoinAds v2 (pendente de autorização do operador; recibo de leituras, "Ação negada") |
| rodando em shadow | **nada** |

A ponte com o simulador e os 8 testes de `test_shadow_simulador.py` foram executados numa árvore combinada
no scratchpad (src do integrador `lab/data-foundation-20261016` + pacote shadow desta thread), porque o
`git merge` da branch da missão no worktree D foi **negado pelo classificador de permissões** (proibição da
missão: merge/rebase). Neste worktree esses testes são `skip` (importorskip). Depois do merge do D na branch
da missão eles rodam no lugar.

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
fuso de fechamento da JoinAds (aviso permanente no snapshot); `currency_code DEFAULT 'USD'` (R1-F4: moeda
inventada não é detectável aqui).

**`rodando em shadow` (proposta, não implantada):** job diário read-only às 07:30 BRT, rodado pelo
integrador/operador (fora do Vercel e do n8n de produção): exporta a janela de 21 dias como acima, roda o
replay dos cortes do dia e anexa ao ledger num diretório fora do Git (ou, depois de ADR, num schema
`dil_shadow` append-only); grava os `resultado` maduros D+5. Nenhuma mutação: o pacote não tem cliente
Google Ads, n8n, Supabase nem HTTP, e o teste de varredura falha se alguém acrescentar. Critério para
qualquer proposta virar humana-em-loop: N semanas de ledger com cortes errados por sinal imaturo = 0,
bloqueios explicados e estabilidade aceitável — decisão do operador, com ADR (P09-T09/P09-T13).

## 10. Achados para outras threads

1. **Ordem de versão `as_of` (A) × consumidor correto do simulador (E):** A escolhe a maior `available_at`; E
   escolhe a medição mais recente (`observed_at`). Quando uma leitura antiga chega atrasada depois da nova,
   A volta para o valor antigo. Medido: 10 de 7.689 valores divergem em `atraso_receita_longo` (20 × 20),
   0 em `estavel`, `identidade_trocada` e `custo_d0_multiversao`. Proposta à A: recusar como vigente uma
   versão cujo `observed_at` é anterior ao da vigente (entrega fora de ordem), mantendo-a no histórico.
2. **v21 D0 × `Registro`:** a mesma leitura (mesmo payload) relida em outra hora tem `cobertura_ppm` diferente
   (derivada de `collected_at`), logo `conteudo` diferente com a mesma `chave_base` — `Registro`/`dil_obs`
   levantariam `ConflitoIdempotencia`. O replay não usa o `Registro` (índice por `(chave_base, available_at)` e
   dedup por payload), mas quem gravar v21 em `dil_obs` vai bater nisso. Liga com R1-F17 (cobertura fabricada).
3. **`as_of` da A depende da ordem para levantar ambiguidade superada:** se a versão ambígua já foi superada,
   a função só levanta quando a vê antes da mais nova na entrada. O índice do shadow ordena por tempo e
   sempre trata (falha ou quarentena) — mais estrito e determinístico.
4. **Simulador `identidade_trocada`:** gera leituras ambíguas (mesmo fato, mesmo `available_at`, payloads
   diferentes; 18 em 20 × 20) — o `as_of` da A para; o replay põe em quarentena.

## 11. Limites

- Gerador provisório é mínimo (campanha × dia, resposta à verba `f^0,8`, sem carryover); o simulador da E é
  a fonte principal depois do merge.
- `equal`/`greedy` usam o custo fechado de D-1 como proxy de verba (o snapshot não lê orçamento).
- Câmbio é parâmetro declarado (`CambioDeclarado`), nunca observação; sem ele não há margem.
- Sessões do sensor não entram (03 §0: tráfego `nao_atribuivel` por campanha hoje).
- Desempenho: ~27 ms por corte com 8 políticas e ~2,5 mil observações; ~85 ms com 12,7 mil
  (`zero_sintetizado_coletor`); `as_of` é O(visíveis) por corte — para meses de histórico, incremental.
