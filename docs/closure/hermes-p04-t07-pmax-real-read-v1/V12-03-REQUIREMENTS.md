# V12-03 requirements — PMax real read v1

**Missão:** P04-T07 PMAX REAL READ V1
**Veredito da 1ª rodada:** `NO_ELIGIBLE_PMAX`
**Veredito da 2ª rodada:** `REAL_READ_PARTIAL` (topologia corrigida, alvo real)

## Escopo factual disponível

Na 1ª rodada a leitura real confirmou autenticação e descoberta read-only, mas não encontrou campanha PMax elegível nas contas consultáveis, e estes requisitos preservavam o desenho da missão anterior.

Na 2ª rodada houve alvo real, e duas das sete famílias voltaram com dados (`PMAX_CAMPANHA`, `PMAX_DESEMPENHO_ASSET_GROUP`). Ainda assim **nenhum payload é promovido a coluna aqui**: três famílias caíram por campo recusado e duas por dependência, então o volume observado continua insuficiente para decidir normalização. O que a 2ª rodada muda para a v12_03 está na seção "O que a leitura real acrescentou".

## Novos `tipo_sinal` necessários

A futura migration v12_03 continua necessária para permitir persistência honesta das seis famílias estruturais PMax que não cabem no CHECK atual do ledger v12_01:

- `PMAX_CAMPANHA`
- `PMAX_ASSET_GROUPS`
- `PMAX_ASSET_GROUP_ASSETS`
- `PMAX_ASSETS`
- `PMAX_DESEMPENHO_ASSET_GROUP`
- `PMAX_SINAIS`

`PMAX_RECOMENDACOES_FORCA` continua podendo usar `RECOMENDACOES_ARMAZENADAS`, desde que consumidores filtrem por `campaign_id` e `payload.familia` para não misturar varredura de conta com recorte PMax de campanha.

## O que a leitura real acrescentou

Três consequências da 2ª rodada e da correção que a seguiu (detalhe em `LINHAGEM-CORRECAO-V25.md`):

1. **`erro_codigo` passou a carregar causa estruturada.** Família dependente de leitura que caiu grava `DEPENDENCIA_FALHOU:<familia>` em vez do antigo `PREREQUISITO_NAO_LIDO`. O campo já existe no ledger e continua sendo texto — não há requisito de schema novo — mas quem consultar falhas por código precisa aceitar o prefixo com `:`. Recibos antigos não são reescritos.
2. **O payload ganhou `campos_recusados_pela_api`.** Vive no JSON existente, sem coluna nova, e é o que impede um consumidor futuro de ler a ausência de `asset_coverage` ou de `primary_status_details` como "a campanha não tem isso".
3. **Nenhum campo recusado pela v25 pode virar coluna.** Os nove estão fora da projeção e ninguém os observou; promovê-los a coluna criaria uma coluna que nunca receberá valor.

O requisito central da v12_03 **não muda**: o bloqueio continua sendo o CHECK `trafego_google_coleta_tipo`, e nenhuma das correções desta rodada o toca.

## Payloads e item JSON

Sem alvo real na 1ª rodada, e com cobertura ainda parcial na 2ª, não houve evidência suficiente para promover campos a colunas. Requisito conservador:

- manter itens estruturais e payloads detalhados em JSON existente;
- não criar colunas para asset text, URLs, sinais ou detalhes de policy nesta etapa;
- avaliar colunas somente depois de uma leitura real com alvo PMax e volume observado.

## Métricas

Métricas pedidas pela implementação anterior podem permanecer como itens/métricas no contrato existente até leitura real com alvo elegível:

- `impressions`
- `clicks`
- `cost_micros`
- `conversions`
- `conversions_value`

A v12_03 deve primeiro destravar o vocabulário de `tipo_sinal`; eventual normalização de métricas PMax fica para decisão posterior baseada em volume e consultas de consumo.

## Identidade e idempotência

A chave de idempotência deve preservar os componentes já provados hermeticamente:

- `customer_id`;
- `login_customer_id`;
- `volc_campaign_id`;
- `campaign_id`;
- `tipo_sinal`;
- `familia`;
- `bucket/janela`;
- estado/erro quando necessário para preservar falha seguida de retry verde.

Não colapsar famílias diferentes sob o mesmo `tipo_sinal` sem `payload.familia`/chave adicional.

## Compatibilidade retroativa

A migration futura deve:

1. manter os seis valores atuais do CHECK;
2. adicionar apenas os seis valores PMax estruturais acima;
3. não reescrever recibos existentes;
4. preservar consumidores atuais de `DIAGNOSTICO_ENTREGA` e `RECOMENDACOES_ARMAZENADAS`.

## Migration e rollback necessários

Migration esperada, não implementada nesta missão:

- alterar o CHECK `trafego_google_coleta_tipo` para incluir os seis novos valores;
- rollback deve restaurar o CHECK anterior apenas se não existirem linhas com os novos `tipo_sinal`, ou deve arquivar/remover essas linhas de forma explícita antes de restaurar.

Nenhum SQL foi criado aqui.
## Adendo pós-correção e leitura real final

A 3ª rodada reexecutou as sete famílias no alvo PMax real `PAUSED` após remover os nove campos recusados pela API v25. Estados finais:

| Família | Estado | Contagem |
|---|---|---:|
| `PMAX_CAMPANHA` | `com_dados` | 1 |
| `PMAX_ASSET_GROUPS` | `com_dados` | 4 |
| `PMAX_ASSET_GROUP_ASSETS` | `com_dados` | 137 |
| `PMAX_ASSETS` | `com_dados` | 123 |
| `PMAX_DESEMPENHO_ASSET_GROUP` | `com_dados` | 4 |
| `PMAX_SINAIS` | `com_dados` | 4 |
| `PMAX_RECOMENDACOES_FORCA` | `vazio_confirmado` | 0 |

Impacto para a v12_03:

1. A necessidade dos seis novos `tipo_sinal` estruturais permanece confirmada por leitura real: agora há payload real para todas as famílias, mas ele ainda não deve ser gravado sob `DIAGNOSTICO_ENTREGA` ou outro tipo incorreto.
2. Métricas de `PMAX_DESEMPENHO_ASSET_GROUP` podem permanecer inicialmente no payload/contrato de métricas existente; a leitura real provou baixo volume nesta amostra, não necessidade de coluna nova.
3. `PMAX_RECOMENDACOES_FORCA` com zero recomendações é `vazio_confirmado`; consumidores devem distinguir isso de falha.
4. Campos removidos por incompatibilidade real não devem compor schema da v12_03: `asset_coverage.ad_strength_action_items.*`, `asset_group_asset.primary_status_details.*`, e campos aninhados de `improve_performance_max_ad_strength_recommendation.*` recusados.
5. `asset_group_asset.performance_label` não deve entrar na v12_03 para v25: adjudicado `NOT_SUPPORTED_IN_V25`.
