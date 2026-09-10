# Fechamento local — entrada criativa e automação da jornada Meta

Data: 10/09/2026

## Resultado

- A jornada começa por Business/conta e carrega as contas do Business escolhido sem botão intermediário.
- Ao informar uma URL HTTPS, a página é analisada e o assunto/site/tipo de LP alimentam a nomenclatura. A próxima sequência é reservada pelo rascunho contra o histórico da conta, com CAS e sem renumerar campanhas existentes.
- Fontes de mensuração e públicos da conta são carregados automaticamente nas respectivas etapas.
- O caminho de Dark Post foi retirado da escolha de criativos desta jornada. Rascunhos legados com `existingPostRef` continuam recuperáveis e precisam ser convertidos explicitamente para imagem editável.
- “Duplicar e trocar imagem” preserva copy/identidade, cria um slot vazio e permite enviar JPEG/PNG clicando na própria prévia. A importação é privada; o envio à Meta continua passando por pack, revisão humana, registro e autorização do plano.
- Um pack vinculado continua editável. Após materialização, a pessoa pode trocar imagens, mudar para flexível e editar o banco de até cinco textos por tipo. O estado `LOCKED` estabiliza somente o vínculo pack→conjunto e não congela o conteúdo do anúncio.

## Provas

- `meta-criacao-v2.test.tsx`, `materializar-pack.test.ts`, `nomenclatura-copy.test.tsx` e `jornada.test.ts`: 72 testes aprovados.
- Regressão do wizard V2 completa: 38 testes aprovados, incluindo upload do slot duplicado, ausência do Dark Post e catálogos automáticos.
- Backend focal de rascunho/nomenclatura/packs: 74 testes aprovados.
- Build Vite aprovado; `git diff --check` aprovado.
- `verificar_autoridade_supabase.py`: autoridade confirmada em `https://database.agenciavolc.com.br`.
- Runtime reiniciado: frontend 8080, API Node 3001 e FastAPI 8010 responderam HTTP 200.

## Limites honestos

- Nenhum POST de criação Meta foi executado nesta rodada.
- Nenhum schema novo foi necessário: `topicSourceUrl` vive no JSONB versionado do rascunho; a reserva de nomes usa a migration oficial já instalada.
- A sessão autenticada do operador e o rascunho real indicado ainda precisam de verificação visual/manual.
- Criação continua exclusivamente PAUSED, com aprovação final do plano e sem rota de ativação.
