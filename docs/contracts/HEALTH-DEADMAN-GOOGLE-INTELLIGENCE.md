# Health/deadman do Google Intelligence

Este contrato e uma projecao deterministica e read-only. Ele recebe recibos ja
obtidos e um relogio injetado; nao consulta n8n, Google Ads ou Supabase, nao
persiste a projecao e nao envia alertas.

## Identidade

A unidade de isolamento e a tupla:

`(login_customer_id, customer_id, coletor_id, tipo_coletor)`

Os IDs Google sao normalizados para digitos. O ID do job e normalizado como
slug minusculo e o tipo de sinal como rotulo maiusculo. Schedules so podem
conflitar quando toda a tupla coincide; o mesmo job em outra conta ou MCC e
outro tenant operacional.

## Tabela-verdade

| Evidencia | Schedule/heartbeat | Resultado |
| --- | --- | --- |
| nenhuma tentativa ou sucesso, com ou sem heartbeat | qualquer | `NUNCA_EXECUTADO` |
| tentativa sem sucesso/falha, ainda na janela | schedule presente | `INDETERMINADO` |
| tentativa sem sucesso/falha, apos a janela | schedule presente | `ATRASADO` |
| tentativa mais recente com falha estruturada | qualquer | `FALHOU` |
| sucesso confirmado, mas schedule ausente | ausente | `INDETERMINADO` |
| sucesso confirmado dentro da janela | heartbeat nao exigido | `SAUDAVEL` |
| sucesso confirmado dentro da janela | heartbeat exigido e ausente | `INDETERMINADO` |
| sucesso confirmado dentro da janela | heartbeat exigido e expirado | `ATRASADO` |
| sucesso confirmado apos a janela | qualquer heartbeat presente/aplicavel | `ATRASADO` |
| schedule desabilitado | sem anomalia temporal | `DESABILITADO` |
| timestamp naive, futuro ou sucesso posterior a tentativa | qualquer | `INDETERMINADO` |
| mais de um schedule no mesmo escopo | configuracoes duplicadas/divergentes | `INDETERMINADO` |

`SAUDAVEL` nunca e derivado somente de tentativa ou heartbeat. Ausencia de
heartbeat permanece `None`; tolerancia zero continua sendo zero e exige sinal
no instante de avaliacao.

## Falhas e dados sensiveis

Uma falha publica possui apenas `codigo` e `classe`, ambos rotulos curtos. O
adaptador aceita `DocumentoColeta` ou seu registro serializado, mas nunca le
`erro_detalhe`. Rotulos inseguros viram os codigos genericos `FALHA_COLETA` e
`ErroColeta`; detalhes brutos, tokens e identificadores nao entram na mensagem
da projecao.

## Adaptacao do contrato persistido

`recibo_de_documentos` agrega um historico de `DocumentoColeta`/mappings do
mesmo MCC, conta e tipo. A maior `coletada_em` e a ultima tentativa; o maior
timestamp nao falho e o ultimo sucesso. Se qualquer recibo falho existir no
instante mais recente, a tentativa e falha, mesmo quando outra familia teve
sucesso no mesmo instante. Isso evita que sucesso parcial esconda falha.

O adaptador nao busca o historico nem o schedule. O chamador continua
responsavel por fornecer ambos e por passar heartbeat real quando aplicavel.
