# Persistência do ciclo de criação e autogestão — série v10

**Agente E · 26/08/2026 · ARQUIVO. Nada aqui foi aplicado em produção.**

Este documento descreve o que a série `v10_*` guarda, por que cada tabela existe
e como provar que ela funciona. As migrations estão em `supabase/migrations/` e
o ciclo aplicar→reverter→reaplicar é rodado por `scripts/provar-ciclo-v10.sh`.

---

## 1. O que foi entregue

| arquivo | o quê |
|---|---|
| `supabase/migrations/v10_01_intencao_e_lote.sql` | 10 tabelas + 2 views: o ciclo de criação |
| `supabase/migrations/v10_01_rollback.sql` | o desfazer, **executável e executado** |
| `supabase/migrations/v10_02_autogestao.sql` | 9 tabelas + 3 views: o motor T1 |
| `supabase/migrations/v10_02_rollback.sql` | idem |
| `backend/app/trafego/lote.py` | derivação da chave, máquina de estados, retomada |
| `backend/app/trafego/intencao.py` | intenção, regra versionada, suficiência de evidência |
| `backend/tests/test_lote*.py`, `test_intencao*.py` | 112 provas |
| `scripts/provar-ciclo-v10.sh` | 100 verificações num Postgres descartável |

**As duas migrations são independentes entre si.** As duas dependem da `v9_01`
(que já está em produção) e nenhuma toca em nada dela. Reverter a autogestão não
derruba o ciclo de criação, e o contrário também vale — é um degrau próprio da
prova.

---

## 2. O modelo

### 2.1 Ciclo de criação — `v10_01`

`intenção → blueprint → lote → itens candidatos → validação local → validate_only
→ aprovação humana → criação PAUSADA → recibo → verificação remota → canário →
ativação progressiva → rollback`

| tabela | o que guarda | chave |
|---|---|---|
| `trafego_intencao` | por que a campanha existe: objetivo, teto, quem declarou e **com base em quê** | `intencao_id` · imutável |
| `trafego_blueprint` | a configuração por canal, como dado versionado | `(chave, versao)` única |
| `trafego_lote` | conta + canal + estado + quota + aprovação humana | `lote_id` |
| `trafego_lote_item` | **a campanha candidata**: plano, estado e erro próprios | `idempotency_key` única |
| `trafego_lote_asset` | assets, com declarado e observado em colunas separadas | `(item_id, papel, ordem)` |
| `trafego_validacao` | cada validação nas 3 camadas (`local`, `validate_only`, `pos_criacao`) | append-only |
| `trafego_recibo` | **cada tentativa de escrita**, criada ANTES da chamada | `(idempotency_key, operacao)` única onde `desfecho='sucesso'` |
| `trafego_verificacao` | o que a conta respondeu depois, com carimbo | append-only |
| `trafego_rollback` | o desfazer, com o `estado_anterior` capturado na solicitação | 1 pendente por item |
| `trafego_lote_transicao` | diário de toda mudança de estado, escrito por gatilho | append-only |

Views: `trafego_item_situacao` (item + recibo em voo + última verificação +
`proxima_acao`) e `trafego_lote_painel` (lote + contagens + `atencao`).

### 2.2 Autogestão T1 — `v10_02`

`snapshot → suficiência → detecção → diagnóstico → proposta → diff → APROVAÇÃO
HUMANA → aplicação → verificação → acompanhamento → rollback`

| tabela | o que guarda | chave |
|---|---|---|
| `trafego_regra_otimizacao` | a regra como dado versionado e imutável — as 12 declarações | `(chave, versao)`; 1 vigente por chave |
| `trafego_evidencia` | o snapshot da decisão + o veredito de suficiência | `evidencia_id` · `colhida_em` NOT NULL |
| `trafego_diagnostico` | sintoma, causa, confiança e **explicação** | append-only |
| `trafego_proposta` | o diff: `valor_atual` × `valor_proposto`, + de quando é o "antes" | `idempotency_key` única |
| `trafego_aprovacao` | a decisão humana + **o diff que foi de fato mostrado** | 1 por proposta |
| `trafego_aplicacao` | cada escrita, criada antes da chamada, com `valor_anterior` | 1 sucesso por chave |
| `trafego_acompanhamento` | `verificacao` (entrou?) e `acompanhamento` (ajudou?) | append-only |
| `trafego_atuacao_reversao` | o desfazer, com o valor a restaurar | 1 por aplicação |
| `trafego_cooldown` | a carência por `(regra_chave, alvo_chave)` | escrita por gatilho |

Views: `trafego_regra_vigente`, `trafego_cooldown_ativo`, `trafego_proposta_painel`.

### 2.3 As duas identidades, honradas — e nenhuma terceira

`plataforma.IdentidadeDeCampanha` (instância) e `plataforma.LinhagemDeCampanha`
continuam sendo as duas identidades do sistema. A v10 aponta para as duas e não
inventa outra:

* a **instância** entra em `trafego_lote_item.volc_campaign_id` → FK para
  `trafego_campanha` (v9), preenchida só quando a campanha passa a existir;
* a **linhagem** entra em `trafego_intencao.campaign_lineage_id` → FK para
  `trafego_linhagem` (v9).

A `idempotency_key` **não é uma terceira identidade**: ela identifica *o pedido*,
não a campanha. Ela morre quando o pedido se resolve; a identidade não.

O id externo continua único **dentro de uma conta**, e por isso a chave externa
viaja como trinca: `plataforma` + `conta_externa` + `id_externo` estão em
`trafego_intencao`, `trafego_lote` e `trafego_evidencia`, sempre juntos.

---

## 3. ⚠️ "A API respondeu timeout mas criou"

É o requisito mais importante do lote inteiro, e a defesa tem **quatro camadas
independentes**. Nenhuma depende de o executor lembrar de nada.

| # | camada | onde |
|---|---|---|
| 1 | recibo escrito **antes** da chamada, com `desfecho='em_voo'` | `v10_01` §7 |
| 2 | item com recibo em voo **não pode** virar `falhou` | gatilho `trafego_item_estado_valido` §11.4 |
| 3 | no máximo **um sucesso** por `(chave, operação)` | `trafego_recibo_sucesso_unico_ux` |
| 4 | no máximo **uma campanha** por item, e vice-versa | `trafego_lote_item_campanha_ux` |

O protocolo:

1. o executor **grava o recibo e faz COMMIT** antes de chamar a plataforma;
2. a chamada estoura o tempo — ou o processo morre. A linha fica em `em_voo`,
   com `respondido_em` nulo. **Isso é a verdade: não sabemos.**
3. o item vai para `indeterminado`. Ele **não pode** ir para `falhou`: `falhou`
   convida à retomada, e retomar sobre uma chamada que talvez tenha criado é
   como nasce a segunda campanha. O gatilho recusa, com mensagem;
4. na retomada, `trafego_item_situacao.proxima_acao` responde `verificar` — e
   **nunca** `criar`. A view e `lote.proxima_acao()` são a mesma regra escrita
   duas vezes, e o script de prova compara as duas contra um Postgres real;
5. a verificação remota busca **pela marca**: a `idempotency_key` foi gravada na
   conta como rótulo, então a pergunta "isto já existe?" não depende de nenhum id
   que talvez nunca tenha voltado;
6. `achou = true` → fecha o recibo como sucesso e adota o id observado.
   `achou = false` (leitura boa, não existe) → libera nova tentativa.
   `achou = NULL` (**não consegui verificar**) → não libera nada. Achatar `NULL`
   em `false` seria a forma mais cara de errar: uma falha de *leitura* viraria
   autorização para criar de novo;
7. mesmo que um executor com defeito reenviasse e criasse duas vezes, a camada 3
   **recusa o segundo `sucesso`**. A transação aborta e o lote para — uma parada
   ruidosa é infinitamente melhor que ser dono de duas campanhas sem saber.

### Por que a chave é derivada do conteúdo

`lote.chave_de_idempotencia()` deriva de
`(intencao_id, plataforma, conta, canal, ordem, plano)` via SHA-256 sobre JSON
canônico. Uma chave sorteada faria **toda retomada parecer criação nova**.
Derivada:

* nada mudou → mesma chave → o sistema reconhece o que existe;
* o plano mudou → chave diferente → é outra coisa, e é a verdade.

`float` é recusado na travessia: `repr(0.1 + 0.2)` não é `'0.3'`, e um plano que
passe por um `round()` numa versão do executor e não passe em outra mudaria de
chave sem mudar de conteúdo. Dinheiro viaja em micros (`int`).

---

## 4. T1 em forma de schema

A automação recomenda; o humano aplica. Quatro travas no banco, não um `if`:

1. `trafego_aplicacao.aprovacao_id` é **NOT NULL com FK**;
2. `trafego_aplicacao_exige_aprovacao` recusa aprovação de **outra** proposta,
   decisão diferente de `aprovada`, proposta **vencida** e alvo **em carência**;
3. `trafego_regra_nivel_conhecido` só aceita `T0` e `T1`. **`T2` não existe no
   vocabulário** — ADR-11. A ausência é o registro da decisão; ele entra por
   migração, com nome e data, e não por um valor que já estava lá esperando;
4. `trafego_proposta_respeita_regra` recusa, no INSERT, as cinco maneiras
   conhecidas de uma proposta ser perigosa: evidência **insuficiente** ou **não
   avaliada**, evidência mais velha que o `frescor_maximo_horas`, delta acima do
   limite percentual, delta acima do limite absoluto, e verba acima do teto.

E `trafego_aplicacao_abre_cooldown` faz a carência nascer sozinha quando uma
aplicação fecha em sucesso — carência que depende de alguém lembrar não é
carência.

---

## 5. O contrato com `regras-canonicas.json` (Agente G)

| | arquivo do Agente G | `trafego_regra_otimizacao` |
|---|---|---|
| é | inventário forense do que o legado **declarou** | contrato do que pode ser **publicado** |
| `null` significa | "não sabemos" (aviso 1 do arquivo) | coluna sem valor |
| autoridade sobre | o que existia no n8n | o que pode gastar verba |

`intencao.MAPA_DO_LEGADO` traduz campo a campo, e
`intencao.adaptar_regra_do_legado()` devolve `(campos, lacunas)`. Ele **traduz
nomes e achata estruturas; nunca inventa valor**.

### O achado, medido em 26/08/2026

**19 regras no arquivo. 19 em `estado: proposta`. Zero publicáveis como estão.**

Isso não é defeito de nenhum dos dois lados. No n8n o limite morava dentro do
`if` do workflow; aqui ele precisa ser *declarado* para poder ser *imposto*. As
lacunas que o adaptador nomeia, em ordem de frequência:

| lacuna | por quê |
|---|---|
| `frescor_maximo_horas` | **nenhuma** regra do n8n declarava idade máxima do dado — a lacuna mais cara do inventário |
| `rollback_janela_horas` | idem |
| `cooldown_horas` | `null` em todas: o legado não tinha carência entre atuações |
| `atraso_conversao_dias` | `null`: o atraso da receita de GAM/AdSense nunca foi medido |
| `amostra_minima` | `null`: precisa ser derivada de intervalo de confiança, não escolhida |
| `limite_de_alteracao` | o legado o declara **por modo** (`EXPLORATION`/`CALIBRATION`/`PRODUCTION`); a coluna é escalar. Escolher um dos três aqui seria decidir sozinho qual regime vale |
| `confianca` | o legado a declara em prosa (`{"exige": …}`); a coluna é número em (0,1] |
| `teto_de_orcamento` | fórmula em texto (`max(budget*0.30, min(10, budget))`); a coluna é micros + moeda |
| `responsavel.aprovador_humano` | `null`: **um domínio não aposenta uma regra** quando ela passa a errar; só uma pessoa faz isso |
| `aprovacao_humana_obrigatoria = false` | em 14 das 19. Seria `T2`, e `T2` não existe |

`backend/tests/test_intencao_regras_canonicas.py` guarda o contrato nos dois
sentidos: nenhum campo do arquivo pode ser ignorado em silêncio (um campo
ignorado é um limite que a regra rodaria sem), e `estado` tem de concordar com
publicabilidade — uma regra que se diz `proposta` não pode ser publicável, e uma
promovida a `adotada` sem os campos declarados quebra o teste em vez de quebrar
uma rodada de decisão gastando verba.

---

## 6. Como provar

```bash
./scripts/provar-ciclo-v10.sh                 # 100 verificações, ~15 s
cd backend && PYTHONPATH=.. .venv/bin/python -m pytest tests/ -q -p no:randomly
```

O script sobe um Postgres **descartável** em `/tmp`, recria os papéis do Supabase
**inclusive o `ALTER DEFAULT PRIVILEGES` quebrado de `public`** — sem reproduzir
o defeito medido em 24/08/2026, a prova de que a migration fecha a tabela mediria
um ambiente mais seguro que o real — e roda:

`v9 → v10_01 → v10_02 → [exercita o ciclo] → rollback v10_02 → rollback v10_01 →
reaplica as duas → reexercita as guardas`

Em cada degrau ele confere: RLS ligada **e** forçada, zero policies,
`anon`/`authenticated` sem nenhum dos 4 privilégios, `security_invoker` em toda
view, `service_role` só com SELECT nas views, `DELETE` para ninguém.

E prova **comportamento**, não só estrutura: as 30 recusas do §3 e §4, além de
`proxima_acao` do Python contra a da view, linha a linha.

### Duas armadilhas que a construção deste script pagou

* **`%%%%` em `RAISE`.** Em plpgsql, `%` é substituição e `%%` é literal;
  `%%%%` estoura com `too many parameters specified for RAISE`. A mensagem foi
  reescrita com "por cento" por extenso — ambiguidade em mensagem de erro é
  ambiguidade no pior momento possível.
* **A prova que mede o vazio.** Um `UPDATE` que não encontra linha nenhuma sai
  com sucesso, e uma prova de recusa fica *verde por falta de alvo*. Foi assim
  que a guarda de `valor_anterior` "passou" na primeira rodada, com a linha
  inexistente. A função `recusa()` agora reprova o `UPDATE 0`.

---

## 7. O que esta entrega **não** faz

* não aplica nada em produção — `database.agenciavolc.com.br` ficou fora;
* não chama, não habilita e não pressupõe nenhuma escrita no Google Ads. Ela
  guarda o **rastro** de uma escrita; a trava continua fechada;
* não implementa o executor do lote nem o motor de decisão. Só a persistência,
  as regras que o banco impõe e a metade Python que as espelha;
* não decide o vocabulário de `objetivo` nem de `papel` de asset: os dois ficam
  abertos com CHECK de não-vazio, pela mesma razão que `estrategia` ficou aberta
  na v9_01 — uma lista fechada cedo demais faz o sistema recusar um pedido
  legítimo, e a recusa aparece como defeito de plataforma;
* não fecha nenhuma das 10 lacunas do §5. Fechá-las é decisão humana, uma a uma,
  publicando versões de regra com os números declarados.

## 8. Antes de aplicar em produção, um dia

1. rodar `./scripts/provar-ciclo-v10.sh` na versão daquele momento;
2. conferir que a `v9_01..v9_04` está aplicada (as FKs dependem dela);
3. exportar nada — as tabelas nascem vazias; o export só importa no **rollback**,
   e os comandos estão no cabeçalho de cada arquivo de rollback;
4. `NOTIFY pgrst, 'reload schema';` — sem isso o PostgREST não enxerga as tabelas
   novas e o sintoma é `404` em tabela que existe;
5. o backend precisa subir **junto**: a v10 não altera nada que o código atual
   leia, então a ordem é livre — mas reverter depois de o código usar as tabelas
   troca um problema por uma queda.
