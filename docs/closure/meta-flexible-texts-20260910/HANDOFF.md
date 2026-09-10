# Meta: banco de textos flexíveis por conjunto

## Entrega e decisão

Em 10/09/2026, o editor passou a separar imagens e opções de texto. Um conjunto
emite um anúncio flexível com um grupo contendo suas imagens e seu banco de
textos. A alternativa anterior pareava uma imagem com uma copy e não oferecia
variações editáveis independentes. O campo explícito opta pela recombinação;
snapshots legados sem o campo conservam seus grupos pareados.

Impeccable orientou a hierarquia do editor, campos rotulados, controles de 44px,
contadores e revisão humana visível. Ads orientou a separação entre implementação,
persistência provada e aceitação remota ainda não exercitada.

## Contrato

- Draft: `conjuntos[].flexibleTexts`.
- V2: `adsets[].flexible_texts`.
- Chaves: `primary_text` (1–5, 2200 caracteres), `headline` (1–5, 255),
  `description` (0–5, 255). Draft admite edição incompleta; compilação não.
- Graph: `creative_asset_groups_spec.groups[].texts`, até cinco por `text_type`.
  Imagens deduplicadas por hash dentro do mesmo conjunto, sem misturar pais.
- Um CTA por anúncio flexível. Neste produto, flexível de imagens exige Vendas;
  não foi acrescentado suporte a App Promotion ou vídeos nesta rodada.
- A Meta decide a entrega; não se promete distribuição igual, todas as combinações
  ou equivalência com um experimento A/B.
- Textos completos participam do hash, congelamento, revisão e readback.
- Edição de textos reinicia confirmações das imagens daquele conjunto.
  Importar copy acrescenta opções únicas ou informa limite; não troca campo oculto.
  Publicações existentes não são recombinadas neste modo.

Base documental: guia oficial de formato flexível fornecido integralmente pelo
operador anteriormente. O acesso direto ao [guia Meta](https://developers.facebook.com/documentation/ads-commerce/marketing-api/flexible-ad-format)
retornou 429 nesta sessão. O [SDK oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/ad.py)
expõe `creative_asset_groups_spec`. Nenhuma fonte de terceiros foi usada como
autoridade de payload. Funções PostgreSQL foram conferidas na
[documentação Supabase](https://supabase.com/docs/guides/database/functions).

## Persistência oficial

Migration `20260910075813_meta_flexible_texts_draft.sql` aplicada exclusivamente
em `https://database.agenciavolc.com.br`, após verificar autoridade e ler a função
live inteira. Amplia a allowlist e validação da RPC existente por transformação
guardada, preservando owner, CAS, grants, referências e resets de aprovação.

SHA-256: `53831996d5402633383e2dc32091256ae4522d7d54cb8f35fdba79072f76546b`.

`scripts/provar-meta-flexible-texts.mjs` provou em transação revertida:
save/read, isolamento de owner, CAS, resets, opções inválidas, edição incompleta,
grants privados e reexecução idempotente da migration. Depois da aplicação,
repetiu os testes de dados e reverteu todas as fixtures. Nenhum rascunho do
operador foi alterado e nenhum anúncio foi enviado à Meta.

Para reversão excepcional, antes exportar os rascunhos com `flexibleTexts` e
coordenar o rollback do código: a função anterior encontra-se na migration
`20260909221222_meta_existing_post_draft.sql`, conferida contra a definição live
antes da alteração. Não remover campos dos rascunhos nem rebaixar RPC isoladamente.

## Provas e limitações

- 65 testes focais frontend passaram (contrato/editor/revisão/duplicação/pack/copy).
- 7 testes de retomada passaram, incluindo página real com API dublê:
  recuperar dois pools, editar A, trocar B/A e confirmar arrays no autosave.
- 124 testes backend passaram; mais um teste de snapshot adulterado passou
  posteriormente (25 novos testes de pools no total).
- Build de produção passou. `git diff --check` limpo.
- Chrome com módulos reais e fixture em memória: 375/1440, claro/escuro, teclado,
  adição e preenchimento; sem overflow ou erro JS. Capturas locais em
  `/private/tmp/meta-flexible-editor-{375,1440}-{light,dark}.png`.
- Front 8080 e API 8010 ativos; `/health` respondeu 200 com routers presentes.
  OpenAPI não é público neste backend (404), sem inferir falha de runtime.
- Suíte ampliada de páginas: 33 passaram e 56 falharam em dois arquivos antigos,
  que ainda esperam navegação/carregamento manual como `Carregar minhas contas`.
  Não foi declarada regressão global verde. TypeScript global ainda tem erros
  fora desta entrega; build e testes focais não equivalem a tsc global limpo.
- 14 testes SQL descartáveis preparados não iniciaram por `initdb`/shared memory
  esgotada no macOS. A prova transacional no banco oficial acima foi executada;
  não é alegação de execução dos 14 testes descartáveis.
- Sem canário de publicação flexível real, sem QA autenticado do rascunho do
  operador e sem promessa de aprovação automática pela Meta. P11-T17 permanece
  `partial` no escopo maior. Webgo e motor de imagens não foram alterados.

## Como testar

Reabrir o rascunho, ir a Criativos, escolher conjunto e “Flexível: agrupar por
conjunto”. Acrescentar textos/títulos, selecionar imagens, trocar de conjunto e
voltar. Conferir “Montagem salva no servidor”, revisar todas as opções e seguir
a confirmação de criação PAUSED. Nenhuma criação é disparada por este handoff.
