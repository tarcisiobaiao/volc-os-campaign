# Contraprovas

As 25 da seção 9 da missão, mais as que a revisão adversarial obrigou a
escrever. Cada uma aponta para o teste que a sustenta.

**Todas as contraprovas da Camada 2 nasceram vermelhas** no commit `ae8495f`,
antes de `oportunidade.py` existir: a coleta falhava com `ModuleNotFoundError`.
Nenhuma descreve comportamento que já funcionava.

Onde uma contraprova já era garantida por outro módulo, o teste **aponta para
lá** em vez de reimplementar a garantia — duplicá-la esconderia qual módulo de
fato a sustenta.

| # | contraprova | onde | resultado |
|---|---|---|---|
| 1 | volume alto com intenção de suporte não vira melhor oportunidade | `test_cp01` | ✅ |
| 2 | linguagem emocional sem demanda não compra prioridade | `test_cp02`, `test_cp02b` | ✅ |
| 3 | dado ausente não vira zero | `test_cp03` | ✅ |
| 4 | zero confirmado ≠ ausência | `test_cp04` | ✅ |
| 5 | resposta oficial que encerra não ganha profundidade | `test_cp05` | ✅ |
| 6 | múltiplas condições e ramos reais são preservados | `test_cp06` | ✅ |
| 7 | evidência melhor nunca decide pior | `test_cp07` | ✅ |
| 8 | desfecho pós-lançamento da própria campanha é recusado | `test_cp08`, `test_cp08b` | ✅ |
| 9 | padrão presente nos controles não vira sinal | `test_cp09` | ✅ |
| 10 | prior fraco nem bloqueia nem autoriza | `test_cp10` + 93 testes de mutação | ✅ |
| 11 | o LLM não devolve o score | `test_cp11` + `test_llm_score_sem_autoridade.py` (36) | ✅ |
| 12 | paráfrases dão a mesma derivação | `test_cp12` | ✅ |
| 13 | construtos sobrepostos não contam duas vezes | `test_cp13` | ⚠️ ver ressalva |
| 14 | falta de sensor vira cobertura menor, não reprovação | `test_cp14` | ✅ |
| 15 | tema forte com zero keywords pagas é estado válido | `test_cp15` | ✅ |
| 16 | CPC, lance, ROAS e budget fora da decisão editorial | `test_cp16` | ⚠️ ver ressalva |
| 17 | cards antigos legíveis, com estado explícito | `test_cp17` | ✅ |
| 18 | reprocessar é determinístico e idempotente | `test_cp18`, `test_cp18b` | ⚠️ ver ressalva |
| 19 | fato, hipótese e desconhecido são conjuntos separados | `test_cp19` | ✅ |
| 20 | não ordena silenciosamente sem cobertura mínima | `test_cp20`, `test_cp20b` | ✅ |
| 21 | página sofisticada não vence por aparência | `test_cp21` | ✅ |
| 22 | sequência longa não é automaticamente melhor | `test_cp22` | ✅ |
| 23 | o formato cita os observáveis que o produziram | `test_cp23` | ✅ |
| 24 | nada no Validador muda o conjunto pago aprovado | `test_cp24` | ✅ |
| 25 | nenhum caminho cria campanha, publica ou chama mutate | `test_cp25` (AST) | ⚠️ ver ressalva |

## Acrescentadas pela revisão adversarial

| contraprova | onde |
|---|---|
| booleano ausente não é `False`, e `"false"` não é `True` | `test_codex_a2_booleano_ausente_nao_e_false` |
| observável não observado não vira fato de zero | `test_codex_a2_observavel_ausente_nao_vira_fato_de_zero` |
| contagem booleana é lixo e não conta | `test_codex_a2_contagem_booleana_e_lixo_e_nao_conta` |
| abaixo do piso o veto não aprova | `test_gemini_p0_veto_abaixo_do_piso_nao_aprova` |
| falha de leitura tem estado próprio | `test_gemini_p0_falha_de_leitura_tem_estado_proprio` |
| cobertura desconhecida retém e não compara | `test_codex_p1_cobertura_none_*` |
| homônimos têm ordem estável | `test_codex_p1_homonimos_tem_ordem_estavel` |
| instabilidade é contradição, não hipótese | `test_gemini_p1_instabilidade_e_contradicao_nao_hipotese` |
| o experimento não afirma custo que não mede | `test_gemini_p2_experimento_nao_afirma_custo_que_nao_mede` |
| o acoplamento CPC→densidade, congelado e delimitado | `test_codex_a5_presenca_de_cpc_move_densidade...` |
| o escopo real da afirmação de mutação externa | `test_codex_a7_a_camada_2_nao_escreve...` |

---

## As três ressalvas, ditas com precisão

### #13 — a garantia é de duplicata textual, não semântica

`test_cp13` prova que nenhum enunciado aparece em dois conjuntos e que os três
são disjuntos. **Não** prova que dois enunciados diferentes descrevem fatos
diferentes: `engajamento` deriva de `ramos_de_acao`, e ambos aparecem como
fatos textualmente distintos. Achado do Codex (P2), aceito e declarado. A
interface exibe a contagem de fatos como força factual, e essa contagem
inclui a sobreposição.

### #16 — vale para a tese; há um acoplamento a montante

Nenhum campo de economia paga aparece na tese — isso está provado. Mas o
Codex achou um caminho **a montante**: a **presença** de `cpc` no cluster vira
`existe_leilao`, que move `densidade` entre `nenhuma` e `rala`, e `densidade`
entra no índice que a tese cita.

Delimitado por medição própria:
- só acontece quando a SERP **não tem nenhum domínio comercial** no top-10;
- só a **presença** é usada, nunca o valor (o próprio sensor recusa o valor:
  superestima o CPC real em 7,4×);
- é **pré-existente** a esta lane.

Congelado em teste e declarado em LIMITATIONS. Corrigir exige remedir a base.

### #18 e #25 — o escopo das duas afirmações era amplo demais

**#18** vale para a Camada 2: dada a mesma evidência, a tese é byte-idêntica e
não muta a entrada. Não vale para o motor de medição: `temperature: 0.9` fixa,
sem seed, sem JSON Schema — `refazer=True` **não** é determinístico.

**#25** vale para a Camada 2, provado por AST. Não valia para a lane inteira: o
Validador escreve no Supabase por desenho, e `_gravar_parcial` aumentou a
frequência dessa escrita. O Codex (A7) apontou, e a afirmação foi corrigida.
Nenhuma escrita ocorreu nesta sessão — o worktree não tem Supabase configurado.

---

## Contraprovas que eu não consegui escrever

Registrado porque a ausência é informação:

- **Não há ground truth.** Nenhum desfecho limpo contra o qual medir se
  `aprofundar` acerta. Por isso este pacote não publica accuracy, precision,
  recall nem uplift: publicá-los seria inventá-los.
- **O passo 2 do funil é inobservável** no corpus do benchmark, então nenhuma
  afirmação sobre "sustenta sequência de páginas" pode citá-lo.
- **O fluxo real de arraste** não foi exercitado ponta a ponta: exige o
  Supabase oficial, proibido nesta missão.
