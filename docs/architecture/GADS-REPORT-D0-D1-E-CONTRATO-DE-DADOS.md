# Google Ads Report D0/D-1 — adaptação e contrato de dados
Data da medição: 28/08/2026.

## Decisão operacional

Os dois workflows da operação Webgo são referência de comportamento, não fonte
de dados nem autoridade para o VOLC O.S. Eles continuam ligados ao ambiente e
ao Supabase daquela operação.

Os dois workflows VOLC são os únicos alvos desta adaptação:

| Papel | Workflow VOLC | Estado depois da adaptação |
|---|---|---|
| D0 — hoje | `hN15qFAVOqH0135q` | atualizado, inativo |
| D-1 — ontem | `tKUItcd0AoD9mozV` | atualizado, inativo |

O destino oficial dos dois é `https://database.agenciavolc.com.br`. Nenhuma
referência ao Supabase Webgo foi copiada.

## O que foi corrigido no n8n

- Google Ads API v25 nos dois fluxos;
- `customer_id` observado na subconta passa ao RPC
  `process_google_ads_campaign`; antes os dois enviavam string vazia;
- `metrics.conversions_value` passou a fazer parte da consulta que o código já
  tentava ler;
- `cost_per_conversion` passa a usar a medida devolvida pela API, em micros
  convertidos, em vez de ser recalculada por `custo / conversões`;
- deduplicação interna usa `customer_id + campaign_id`;
- as gravações da campanha e da métrica diária agora se encontram num `Merge`
  antes de o lote avançar; duas respostas paralelas não podem mais avançar o
  mesmo cursor separadamente;
- D-1 passou a declarar `America/Sao_Paulo` explicitamente;
- credenciais foram preservadas e os dois workflows permaneceram inativos.

Os exports anteriores estão preservados fora do Git em diretório privado para
rollback. Os dois workflows de referência Webgo não foram editados.

## O limite que não deve ser escondido

`daily_campaign_metrics` é uma tabela legada de resultado econômico. Ela é
consumida por muitas telas e mistura gasto de mídia, receita, GAM, revshare e
orientações. Hoje ela não possui:

- `customer_id`;
- instante da coleta;
- identidade da execução/coletor;
- moeda da leitura Google Ads;
- resultado da tentativa e motivo de falha;
- distinção estrutural entre `NULL` (não medido) e `0` (medido e zerado);
- `conversions_value`;
- chave canônica por conta, campanha e data.

Por isso, acrescentar dezenas de métricas diretamente nessa tabela criaria uma
tabela larga com granularidades incompatíveis e manteria colisões invisíveis
entre contas. A adaptação do workflow melhora o legado; não transforma esse
legado na nova autoridade.

## Próxima migration proposta — não aplicada

### 1. Ledger da execução

Criar `trafego_coleta_execucao`, append-only, com pelo menos:

- `execucao_id`, `fonte`, `job`, `workflow_id`, `versao_api`;
- janela pedida, início, fim, duração e idempotency key;
- resultado `ok | parcial | falhou`, motivo e escopo;
- contas tentadas, aceitas e recusadas;
- contagens de linhas lidas, aceitas e rejeitadas;
- hash do contrato e carimbo de heartbeat.

### 2. Fato canônico campanha-dia

Criar `google_ads_campanha_dia`, sem defaults numéricos, com chave única:

`(customer_id, campaign_id, metric_date, segments_hash)`.

Campos mínimos:

- identidade: `customer_id`, `campaign_id`, `volc_campaign_id`;
- prova: `execucao_id`, `colhida_em`, `api_version`, `currency_code`;
- entrega: impressões, cliques, interações, custo em micros;
- resultado: conversões, todas as conversões, valores de conversão;
- eficiência: CTR, CPC e custo por conversão;
- leilão Search: impression share, perdas por verba/rank, top/absolute top,
  click share e exact-match impression share;
- `metricas_extras jsonb` para campos compatíveis ainda não promovidos a
  coluna, sem misturar outras granularidades.

`NULL` significa não medido. Zero só entra quando a consulta bem-sucedida
confirmou zero. Todo dinheiro conserva micros e moeda.

### 3. RPC atômico de ingestão

Um único RPC deve:

1. validar execução, conta, janela, moeda e identidade;
2. registrar/atualizar a identidade da campanha;
3. inserir o fato campanha-dia;
4. produzir a projeção de compatibilidade para `daily_campaign_metrics`;
5. fechar o recibo somente após todas as escritas.

Assim o n8n orquestra e agenda; regras de consistência e idempotência ficam no
banco. A projeção mantém as telas legadas enquanto consumidores migram.

### 4. Coletores por granularidade

Não pertencem ao fato campanha-dia e entram em tabelas/rotinas próprias:

- ad group-dia;
- keyword-dia e diagnóstico de Quality Score;
- search term-dia e decisão de negativa/promoção;
- anúncio, asset, landing page e política;
- ação de conversão e saúde de tracking;
- orçamento, bidding, change events e recomendações;
- asset groups e sinais de PMax/Demand Gen.

Essa separação é a ponte para ARBA, Ads Monitor, If This Then Ad, Orakul e o
cockpit VOLC sem “deixar dados na mesa” nem destruir a linhagem.

## Aceite para ativar os workflows

Antes de ligar agenda ou executar manualmente:

- migration e rollback provados em Postgres descartável;
- RLS `ENABLE + FORCE`, zero privilégio `anon/authenticated`, escrita somente
  pelo papel operacional escolhido;
- uma conta-canário e uma janela de um dia;
- contagens Google → RPC → tabela reconciliadas;
- repetição da mesma idempotency key não duplica linha;
- falha parcial preserva a última leitura boa e gera recibo de falha;
- D0 e D-1 não disputam a mesma chave nem fazem o cursor andar duas vezes;
- as telas legadas continuam lendo a projeção de compatibilidade.
