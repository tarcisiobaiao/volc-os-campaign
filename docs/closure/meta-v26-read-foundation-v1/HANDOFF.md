# Meta v26 read foundation v1

## Veredito

`META_V26_READ_FOUNDATION_LOCAL_ACCEPTED`

Este veredito aceita a fundação local e hermética. Não significa Meta configurada,
migration aplicada, conta lida, campanha validada ou campanha criada.

## Entregue

- pacote v26 da Bia incorporado e adjudicado contra o runtime existente;
- 44 capacidades mapeadas em duas direções, 10 etapas de operador e 18 bindings UI/API;
- read model Meta v15_01 isolado das identidades Google-shaped da v9;
- identidade determinística para campaign, adset, ad e creative;
- referência de credencial opaca e resolvedor host-only fail-closed;
- adaptador Graph v26 somente GET, transporte injetado, allowlist de campos,
  paginação limitada e erros sanitizados;
- sincronização que só substitui a projeção e marca ausências após leitura completa;
- Hub com eixo canônico `rede=meta`, sem consultas, notificações ou frescor Google.

## Limites

- sem adapter PostgREST/Supabase de produção e sem rota HTTP Meta;
- sem system user/token real e sem resolução real pelo Cofre;
- sem migration oficial;
- sem leitura Meta real;
- sem Insights, upload de assets, validate remoto ou mutate;
- sem páginas canônicas reais por campanha, conjunto e anúncio.

## Próximo corte operacional

Implementar o resolvedor host-only e o repositório transacional, aplicar a v15_01
em janela separadamente autorizada e então ligar endpoints autenticados de
prontidão, inventário e sincronização somente leitura ao Hub.

