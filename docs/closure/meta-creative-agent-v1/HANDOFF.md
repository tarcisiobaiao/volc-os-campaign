# Assistente de Criativos Meta v1

## Resultado

O Co-Piloto externo foi convertido em um contrato local, tipado e auditável.
O agente emite diagnóstico, jornada, grupos, copy compartilhada e briefs de
peças. Ele não gera mídia e não possui autoridade para criar ou ativar anúncio.

## API

- `POST /api/criativos/meta/agente/operacoes` cria a operação, abre a run antes
  do LLM e executa o primeiro lote.
- `POST /api/criativos/meta/agente/operacoes/{project_ref}/runs` refina uma
  operação usando feedback escopado e decisões aprovadas congeladas.
- `GET /api/criativos/meta/agente/operacoes/{project_ref}` lê estado e runs.
- `POST /api/criativos/meta/agente/operacoes/{project_ref}/decisoes` resolve o
  JSON Pointer no backend e grava um snapshot imutável; o browser não escolhe o
  conteúdo que será congelado.

Todas exigem identidade de usuário. O repositório inclui `owner_id` em cada
leitura e escrita, mesmo usando service role no servidor.

## Invariantes

- Sem fallback fictício quando o modelo não está configurado.
- Modelo padrão configurável: `gemini-3.8-flash`. A prova direta do contrato
  passou na segunda tentativa com três peças; nenhum conteúdo do smoke foi
  persistido.
- A temperatura deste agente é 0.35. O cliente compartilhado mantém 0.9 como
  padrão para não mudar o Pautador existente.
- Duas tentativas no máximo para JSON/contrato inválido.
- O lote é atômico e precisa conter exatamente a quantidade solicitada.
- Toda copy e peça cita fatos existentes no pedido.
- Toda dupla de peças difere em pelo menos três eixos estratégicos.
- Copy externa é referenciada por grupo, não duplicada por peça.
- Aprovado é congelado por caminho, snapshot e SHA-256.
- O recibo de validação é emitido pelo código, nunca aceito do modelo.
- O corpus bruto permanece privado e fora do Git.

## Limite desta entrega

A migration é candidata local e não foi aplicada. Não há frontend nesta fatia.
O próximo consumidor é o engine Meta, que deve traduzir o bundle aprovado para
`AssetDemandManifest`; essa autoridade não foi transferida ao agente.
