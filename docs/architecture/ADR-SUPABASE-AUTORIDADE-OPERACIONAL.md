# ADR — autoridade operacional do Supabase

**Estado:** aceita em 27/08/2026  
**Dono da decisão:** Tarcisio / VOLC  
**Escopo:** VOLC O.S., seus serviços, jobs, automações e novos desenvolvimentos

## Decisão

O único Supabase oficial e operacional do VOLC O.S. é o self-hosted disponível em:

`https://database.agenciavolc.com.br`

Frontend, APIs, workers, n8n, Edge Functions, rotinas SQL e qualquer novo serviço
do VOLC O.S. devem ler e gravar exclusivamente nessa autoridade, salvo um ambiente
de teste hermético que não processe dados reais.

Um projeto `*.supabase.co` encontrado em código, workflow ou documento legado não
é fallback, réplica nem segunda fonte de verdade. Ele deve ser classificado como:

1. fixture de teste sem dado real;
2. referência histórica arquivada;
3. consumidor legado a migrar;
4. consumidor legado a aposentar.

## Consequências

- nenhuma funcionalidade nova pode criar dependência operacional em
  `*.supabase.co`;
- uma rotina legada não é migrada por substituição cega de URL: tabelas, funções,
  identidade, RLS, idempotência e efeitos precisam ser comparados primeiro;
- não haverá sincronização bidirecional entre o self-hosted e o hospedado;
- dados do hospedado não recebem backfill automático para o banco oficial;
- toda rotina migrada precisa deixar owner, heartbeat, chave de idempotência e
  recibo de execução no desenho canônico;
- documentos arquivados podem preservar URLs antigas para explicar a história,
  desde que estejam claramente marcados como legado;
- segredos nunca entram no ADR, no Roadmap ou no grafo.

## Estado medido na aceitação

Os arquivos vivos `.env`, `.env.local`, `.env.server` e `backend/.env` apontavam
para `database.agenciavolc.com.br`. O frontend, o servidor Node e o FastAPI já
operavam contra o self-hosted. O inventário n8n ainda registrava 271 referências
ao Supabase hospedado; isso é dívida de migração, não ambiguidade de autoridade.

## Proteção executável

`scripts/verificar_autoridade_supabase.py` valida os templates versionados e os
arquivos locais de ambiente que existirem. `start-dev.sh` executa esse gate antes
de iniciar os serviços e falha se `VITE_SUPABASE_URL` ou `SUPABASE_URL` apontar
para outro host.

## Critério para encerrar a migração legada

A tarefa de migração só termina quando cada consumidor inventariado estiver
marcado como migrado, aposentado ou histórico e nenhuma rotina ativa tocar um
Supabase hospedado. A decisão arquitetural já está concluída; a execução dessa
limpeza continua separada e rastreável.
