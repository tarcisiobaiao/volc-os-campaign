# Espelhamento futuro — não executado

Aplicar deltas revistos, não copiar cegamente a worktree inteira: existem numerosas mudanças anteriores de terceiros. O HEAD base desta rodada é be4483b; não é um commit que delimita sozinho todos os deltas deste sprint, pois a árvore já estava suja. Reconciliar com o estado real do Webgo antes de qualquer cherry-pick/cópia. Não transportar env, credenciais, usuários, arquivos de clientes ou storage local.

## Entradas desta implementação

Motor/contrato:

- `services/creative_engine/motores/openai_imagem.py`
- `backend/app/criativo/studio/spec_visual.py`
- `backend/app/criativo/studio/{contrato,adaptador,autorizacao}.py`
- `backend/app/criativo/agente/{contrato,persistencia,prompts}.py`
- `backend/app/criativo/{dominio,execucao}.py`
- `backend/app/routers/criativos_agente.py`
- `supabase/migrations/20260909234342_creative_generation_versions.sql`

LP e interface:

- `backend/app/criativo/contexto_pagina.py`
- `scripts/provar_contexto_lp_persistencia.py`
- `src/features/creative-studio/{api,tipos}.ts`
- `src/features/creative-studio/componentes/{ContextoDaLandingPage,FormularioDeBriefing,PainelDeEstrategia}.tsx`
- `src/pages/trafego/AssistenteCriativoPage.tsx`
- `src/components/trafego/meta/AssistenteNaJornada.tsx`

Montagem Meta:

- `backend/app/trafego/meta_execucao/{contrato_v2,compilador,executor}.py`
- `backend/app/routers/trafego_meta_validacao.py`
- `backend/app/trafego/meta_execucao/posts_existentes.py`
- `src/pages/trafego/MetaCriacaoPage.tsx`
- `src/components/trafego/meta/{FormatoDeCriativos,EscolherPublicacaoMeta}.tsx`
- `src/components/trafego/meta/{rascunho,vinculos,materializarPack}.ts`
- `src/lib/pautadorApi.ts`

## Dependências preexistentes

Packs/append/revisões, origens de publicação, rascunhos CAS, bridge operação/run/job, metadados v16_01, contrato V2 e ledger precisam existir no destino antes da migration nova. O schema de versões exige a tabela `criativo_agente_peca_job` e sua constraint original; confirmar nome, owner, RLS, grants e dados. Não importar configurações nem permitir fallback de banco.

## Provas que devem acompanhar

- `backend/tests/test_criativo_{spec_visual,contexto_pagina,generation_versions_sql,agente_autorizacao_de_gasto,motor_openai,execucao}.py` e testes V2/execução/publicação existentes alterados.
- `src/features/creative-studio/__tests__/contexto-pagina.test.tsx` e testes do Assistente, estratégia, packs e galeria.
- `backend/tests/test_meta_existing_posts.py`, `backend/tests/test_meta_flexible_images.py`.
- `src/components/trafego/meta/__tests__/{formato-criativos,publicacao-existente}.test.tsx` e `vinculos.test.ts`, além dos testes existentes de transporte/materialização.
- `docs/architecture/ADR-CREATIVE-LP-CONTEXT.md` e este diretório.

Antes de liberar no Webgo: nova branch controlada no destino, contrato da identidade própria, verificação da autoridade desse ambiente, migration com backup, teste autenticado e canário limitados. Este manifesto não transfere autorização nem prova do VOLC para outro sistema.
