# Exclusão segura de assets e vínculo durável de packs

Data: 08/09/2026
Estado: `LOCAL_READY_DB_APPLIED_PARTIAL`

## Resultado

O Estúdio permite selecionar uma ou mais peças prontas e excluí-las da
biblioteca após confirmação explícita. A operação é um arquivamento: a peça
some da galeria e não entra em novos packs, mas bytes, job, renditions,
procedência e recibos permanecem preservados para auditoria. Uma aprovação
vigente bloqueia o ato; ela precisa ser revogada antes.

No criador Meta, a escolha do pack passou a ter identidade
`owner_id + draft_ref + adset_key`. Cada conjunto exibe o pack confirmado, a
versão do vínculo e um estado bloqueado inequívoco. Trocar de conjunto e voltar
reidrata a escolha do banco; mudar ou retirar exige ato explícito. Um conjunto
com pack vinculado não pode ser removido silenciosamente.

## Contrato de banco

Migration:
`supabase/migrations/20260908230430_meta_creative_draft_pack_selection.sql`

SHA256:
`05333075a699d3181b3629d004f4ca8670146da1c436cb24132011d0b4aed8f6`

Aplicada e relida no Supabase oficial `database.agenciavolc.com.br`. O
postflight confirmou:

- tabela `public.trafego_meta_rascunho_pack`;
- RLS habilitada e forçada;
- zero policies;
- zero privilégios para `anon` e `authenticated`;
- `SELECT/INSERT/UPDATE/DELETE` apenas para `service_role`;
- FK restritiva para `criativo_reuso_pack`;
- unicidade por dono, rascunho e conjunto;
- manifesto e `master_refs` congelados no vínculo;
- compare-and-set pela coluna `version` para conflito entre abas;
- zero linhas sintéticas deixadas no banco.

O vínculo possui `scope=DRAFT_MEDIA_ONLY` e
`launch_authorized=false`. Escolher um pack não publica, não registra mídia na
Meta e não autoriza lançamento.

## Provas

- backend focado: 21 testes verdes;
- frontend focado: galeria, escolha de pack e jornada Meta;
- migration: apply, escrita válida, leitura por `service_role` e recusa de
  `authenticated` em PostgreSQL 15 descartável;
- backend local: as rotas novas estão carregadas e respondem `401` sem sessão;
- build Vite verde;
- TypeScript sem erro nos arquivos desta entrega; a baseline global permanece
  com erros herdados fora do domínio;
- suíte ampliada do domínio criativo: 846 passed e 22 skipped; 37 casos
  Postgres não iniciaram no sandbox por `shmget: Operation not permitted`. A
  migration nova foi provada separadamente em container e no catálogo oficial.

## Limite honesto

Esta entrega fecha a exclusão lógica e a persistência da intenção de usar um
pack em cada conjunto. Ela não fecha a cadeia
`master -> avaliação de política -> registro de mídia na conta Meta ->
creative_id -> ad`. Enquanto essa ponte governada não estiver concluída, o
criador bloqueia a compilação de packs em vez de fingir que a seleção já é um
anúncio publicável.

Nenhuma chamada, criação, edição ou ativação Meta ocorreu nesta rodada.
