# GADS_MULTICHANNEL_BIRTH_V1_PARTIAL_READY_FOR_INTEGRATION

## Veredito

O checkpoint foi recuperado e corrigido. Ele não fecha o nascimento real dos
três canais: fecha a falsa promoção que dizia que Demand Gen e PMax podiam
mutar sem a fronteira HTTP correspondente, e preserva o ganho material de
PMax — URL final exata com expansão automática explicitamente desabilitada.

## Estado factual por canal

| Canal | Monta | validate_only | mutate real | Estado máximo desta entrega |
|---|---:|---:|---:|---|
| Display | sim | sim | já existe, sempre PAUSED | sem mudança arquitetural |
| Demand Gen | sim | sim | não | ready para prova; criação fechada |
| Performance Max | sim, pelo módulo próprio | validador direto existe | não | grafo local pronto para mídia |

PMax não entra no registro HTTP genérico. `ProvarEntrada`/`SubirEntrada` ainda
não carregam `ConfiguracaoPMax`, `ImagensPMax` nem o `ReciboDeMensuracao`
emitido pela leitura da conta. Aceitá-lo ali faria a rota prometer o que não
consegue reconstruir.

## Controle de URL PMax

O `Campaign` PMax emite
`FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION=OPTED_OUT`; o `AssetGroup` recebe
somente a URL final declarada e nasce `PAUSED`. O proto v25 local e uma prova
hermética confirmam os campos, enums e serialização.

## Adjudicação Gemini

`gemini-3.1-pro-preview` confirmou a retirada da promoção prematura e a
manutenção do opt-out. A consulta final usou contexto sanitizado, zero
ferramentas e zero chamadas Google Ads. Artefato:
`GEMINI-FINAL-ADJUDICATION.json`.

## Limites

- Nenhum `validate_only` real foi executado nesta retomada.
- Nenhuma campanha, asset, asset group ou anúncio foi criado.
- PMax precisa da ponte HTTP tipada e do motor de mídia antes de um canário.
- Demand Gen continua deliberadamente bloqueado em `/subir`.
- Roadmap, curadoria e grafo compartilhados não foram editados nesta feature
  branch; o integrador deve aplicar `CURATION-HANDOFF.json` após a integração.

## Zero mutação externa

Zero Google Ads, Supabase, migration, n8n, Data Manager, WordPress, deploy,
merge, rebase, amend, tag ou force push.
