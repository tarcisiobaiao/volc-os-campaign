# Persistência da montagem da campanha Meta

## Decisão e limites

O rascunho completo é intenção editável, não autorização para publicar. Ele guarda
conta/Página por referências opacas, conjuntos com chaves estáveis, orçamento,
público, mensuração, anúncios, copy e proveniência do pack. Não executa Meta nem
gera imagens. As seleções confirmadas de pack continuam no contrato separado já
existente; a aprovação de criação continua no snapshot imutável do executor.

Persistir apenas o pack não preservava a montagem dos anúncios entre conjuntos.
Salvar o Draft inteiro como JSON limitado permite retomar os campos sem converter
texto incompleto de orçamento/geografia em valores diferentes durante a digitação.
O compilador continua sendo a autoridade para validar uma campanha executável.

As declarações `categoryConfirmed`, `assetRightsConfirmed`,
`thirdPartyIdentityCleared` e `assetPolicyConfirmedAt` são zeradas antes de salvar
e ao ler. Retomar um rascunho exige confirmar novamente essas declarações.

## API e autorização

- `GET /api/trafego/meta/drafts/{draft_ref}` recupera a versão do proprietário.
- `PUT /api/trafego/meta/drafts/{draft_ref}` recebe `{expected_version, draft}`.
- O UUID identifica o rascunho; o proprietário vem da sessão administrativa,
  nunca do corpo enviado pelo navegador.
- Primeira escrita: `expected_version=0`. Atualizações exigem a versão atual.
  Conflito retorna HTTP 409 `META_DRAFT_VERSION_CONFLICT`, sem sobrescrever dados.
- HTTP 404 `META_DRAFT_NOT_FOUND` significa somente ausência para esse proprietário.
- Schema ausente retorna HTTP 503 `META_DRAFT_SCHEMA_REQUIRED`.
- Toda resposta válida declara `scope=DRAFT_ONLY` e `launch_authorized=false`.

O DTO é fechado e limitado a 10 conjuntos, 10 anúncios e 120 KB. Identidades de
anúncio/conjunto são únicas; cada anúncio deve apontar para um conjunto existente.
Proveniência de pack deve pertencer à conta escolhida. Campos extras são recusados,
assim como padrões conhecidos de credenciais, sem devolver o input nos erros.
Essa proteção não transforma texto arbitrário em armazenamento de segredos seguro:
tokens continuam exclusivos do cofre operacional.

RLS é forçada. Não há acesso direto à tabela por anon/authenticated/service_role.
Somente as RPCs de leitura/escrita são concedidas ao service_role, com proprietário
e versão explicitamente conferidos. O backend valida o DTO inteiro antes das RPCs.

## Hook e integração

`useMetaCampaignDraft({draftRef,draft,onRestore,enabled})` expõe
`loading`, `saving`, `saved`, `version`, `error`, `conflict`, `saveNow()` e `reload()`.

A hidratação termina antes de salvar. Autosaves têm debounce de 700 ms e são
serializados; alterações durante uma requisição usam a versão retornada pela
requisição anterior. O fingerprint ordena recursivamente as chaves: a ordem de
JSONB não altera a igualdade. Ausência/null de `packOrigin` é normalizada.
Conflito exige recarga explícita; não existe último escritor vence silenciosamente.
`enabled=false` isola o modo demonstrativo de qualquer escrita oficial.

A página deve bloquear edição enquanto recupera dados e chamar `saveNow()` antes
de seguir para a aprovação. A assinatura do plano não é guardada no Draft.

## Migração

Arquivo: `supabase/migrations/20260909000758_meta_campaign_draft_persistence.sql`

SHA256: `5e709189a997a304ff68c6a2eb634481279d434956dca4b7e02cba5a9e919cb0`

Cria tabela e RPCs próprias, sem migrar ou apagar campanhas/seleções existentes.
Foi criada pelo CLI `supabase migration new`; aplicação oficial e recibo pertencem
ao integrador. Este handoff não declara aplicação oficial.

## Provas locais

- `backend/tests/test_meta_campaign_draft.py`: 9 testes passando; DTO, origem,
  rejeição de extras/segredos e erro HTTP sem eco do token.
- `backend/tests/test_meta_campaign_draft_sql.py`: 4 testes passando em PostgreSQL
  descartável; apply/reapply, CAS, isolamento de proprietário, ACLs, integridade.
- `src/hooks/useMetaCampaignDraft.test.tsx`: 6 testes passando; hidratação,
  serialização, conflito, demo, JSON reordenado e save sem alteração seguido de edição.
- `tsc -p tsconfig.app.json` ainda falha em arquivos legados não relacionados;
  nenhum erro apontado no hook/API novos. `git diff --check` limpo.

Não houve nesta subexecução chamada Meta, geração paga, commit ou aplicação oficial.
QA visual autenticado e reconciliação de roadmap/grafo cabem ao integrador único.
