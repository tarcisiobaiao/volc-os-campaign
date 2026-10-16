# VOLC Measurement no Google Tag Manager

Fonte versionada dos dois componentes ativos no contêiner oficial do Crédito Up
(`GTM-N4KS27ZV`). O GTM publicado continua sendo a autoridade de execução; estes
arquivos permitem revisão, comparação e recuperação sem depender do editor web.

## Componentes ativos

- `webs-wrapper-v2.html`: normaliza UTMs e contexto editorial para a camada
  `webs`, sem gravar diretamente no banco.
- `volc-sensor-v3.html`: coleta somente eventos comportamentais allowlisted e os
  envia em lote para `volc-ingest`.

Ambos foram publicados na versão 35 do contêiner em 15/10/2026. A versão 34 é o
rollback imediato. A publicação foi feita em workspace isolado e não reativou as
tags legadas de escrita direta no Supabase.

## Fronteira de dados

O navegador nunca recebe `service_role` e não acessa `raw_events` pelo REST. O
único caminho de escrita é:

`GTM -> volc-ingest -> raw_events`

O contrato do endpoint fica em `supabase/functions/volc-ingest/index.ts`; o
endurecimento da tabela fica na migration
`20261015153301_harden_volc_measurement.sql`.

## Publicação segura

1. Criar workspace isolado no GTM.
2. Comparar o HTML proposto com estes arquivos.
3. Executar preview e verificar consentimento, rede e `dataLayer`.
4. Criar uma versão nomeada.
5. Publicar usando OAuth restrito a `tagmanager.publish`.
6. Reler a versão live e executar um canário público sem gerar impressão de
   anúncio artificial.

Nunca reutilizar a chave anônima para escrever diretamente em `raw_events`.

## Verificação de drift e heartbeat

O manifesto `manifest.json` fixa a versão publicada, as tags, os acionadores e
os consentimentos esperados. A prova é somente leitura no GTM e no banco; o
único POST feito é uma contraprova vazia a partir de uma origem inválida, que
deve receber `403` antes de qualquer processamento.

```bash
python3 scripts/verificar_measurement_volc.py \
  --env-file /caminho/seguro/.env \
  --max-heartbeat-hours 48
```

Exit code `0` significa que os fontes publicados conferem, existe heartbeat v3
recente e o navegador anônimo continua sem acesso direto a `raw_events`. O
comando não publica GTM, não insere evento e não altera schema.

