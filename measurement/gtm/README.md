# VOLC Measurement no Google Tag Manager

Fonte versionada dos dois componentes ativos no contêiner oficial do Crédito Up
(`GTM-N4KS27ZV`). O GTM publicado continua sendo a autoridade de execução; estes
arquivos permitem revisão, comparação e recuperação sem depender do editor web.

## Componentes ativos

- `webs-wrapper-v2.html`: normaliza UTMs e contexto editorial para a camada
  `webs`, sem gravar diretamente no banco.
- `volc-sensor-v3.html`: coleta somente eventos comportamentais allowlisted e os
  envia em lote para `volc-ingest`.

O wrapper entrou na versão 35. O sensor v3.1 foi publicado na versão 36 em
16/10/2026, corrigindo a colisão entre eventos legítimos do mesmo tipo ocorridos
no mesmo segundo. A v37 publicou o Sensor v3.2, preservando IDs numéricos de
campanha. A v38 remove das duas tags próprias do VOLC a dependência do Consent
Mode: a medição first-party minimizada roda em toda navegação, enquanto GPC e
`window.volcOptOut()` continuam interrompendo o Sensor. O aviso nativo do tema é
informativo e não controla essas duas tags. Essa decisão não altera tags Google,
GA4, Google Ads, Conversion Linker ou seus próprios requisitos de consentimento.

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
3. Executar preview e verificar rede, `dataLayer`, filtro de PII e que as duas
   tags VOLC não possuem requisito adicional de Consent Mode.
4. Criar uma versão nomeada.
5. Publicar usando OAuth restrito a `tagmanager.publish`.
6. Reler a versão live e executar um canário público sem gerar impressão de
   anúncio artificial.

Nunca reutilizar a chave anônima para escrever diretamente em `raw_events`.

## Verificação de drift e heartbeat

O manifesto `manifest.json` fixa a versão publicada, as tags, os acionadores e
os requisitos adicionais de consentimento esperados (vazios nas tags VOLC). A
prova é somente leitura no GTM e no banco; o
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
