# Inbox do Roadmap

Decisão: **opção A**. Fila append-only em `volc-os-workbook/`, com escrita
atômica e recibos. O `ROADMAP-VIVO.json` continua sendo a projeção editorial.
O Inbox nunca entra no percentual e nunca é um segundo roadmap.

## Por que não a opção B

Não há armazenamento persistente já existente para esta fila. Inventar uma
tabela no Supabase exigiria migration, que esta frente não toca. Um segundo
JSON “paralelo” no banco viraria autoridade concorrente.

## Arquivos

| arquivo | papel |
| --- | --- |
| `INBOX-ROADMAP.json` | snapshot validado das entradas |
| `INBOX-ROADMAP.receipts.jsonl` | trilha append-only (nunca reescrita) |
| `INBOX-COVERAGE.json` | auditoria explícita de temas conhecidos |

Escrita: arquivo temporário + `fsync` + `rename`. Cada mutação gera um recibo
com ator, horário, hash anterior e hash seguinte.

## O que isto não é

Mensagens de chat, ideias soltas ou esta conversa **não** entram sozinhas.
Captura é um ato explícito no QG ou uma entrada versionada neste diretório.
“Capturada” não significa “adicionada ao roadmap”.
