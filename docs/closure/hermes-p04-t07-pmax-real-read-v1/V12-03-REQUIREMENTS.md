# V12-03 requirements — PMax real read v1

**Missão:** P04-T07 PMAX REAL READ V1
**Veredito desta execução:** `NO_ELIGIBLE_PMAX`

## Escopo factual disponível

A leitura real confirmou autenticação e descoberta read-only, mas não encontrou campanha PMax elegível nas contas consultáveis. Portanto, estes requisitos preservam o desenho da missão anterior e **não adicionam payloads provados por sete famílias reais** nesta execução.

## Novos `tipo_sinal` necessários

A futura migration v12_03 continua necessária para permitir persistência honesta das seis famílias estruturais PMax que não cabem no CHECK atual do ledger v12_01:

- `PMAX_CAMPANHA`
- `PMAX_ASSET_GROUPS`
- `PMAX_ASSET_GROUP_ASSETS`
- `PMAX_ASSETS`
- `PMAX_DESEMPENHO_ASSET_GROUP`
- `PMAX_SINAIS`

`PMAX_RECOMENDACOES_FORCA` continua podendo usar `RECOMENDACOES_ARMAZENADAS`, desde que consumidores filtrem por `campaign_id` e `payload.familia` para não misturar varredura de conta com recorte PMax de campanha.

## Payloads e item JSON

Sem alvo real, não houve nova evidência para promover campos a colunas. Requisito conservador:

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
