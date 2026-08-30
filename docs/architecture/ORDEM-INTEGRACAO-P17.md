# P17 — ordem de integração e ownership da produção criativa

**Estado desta fatia:** S0, fronteiras mecânicas. Nenhuma capacidade de produção
remota foi criada.

## Contratos congelados

| Nome | Autoridade | Papel que não pode ser reinterpretado |
|---|---|---|
| `criativo_job` | `supabase/migrations/v11_01_estudio_criativo.sql`, consumido por `backend/app/criativo/execucao.py` e `persistencia.py` | Job do produto Estúdio: briefing, motor, renditions, custo, eventos e estado percebido pelo operador. |
| `criativo_render_job` | `supabase/migrations/v11_03_execucao_criativa.sql` | Attempt durável de execução. Claim, lease, heartbeat, retry, cancelamento e recibo pertencem ao attempt; ele não substitui nem renomeia `criativo_job`. A ligação entre os dois ainda não foi implementada. |
| `Asset` e `LoteDeAssets` | `volc_ads/criativo/contrato.py` | Identidade, medidas, procedência, falhas e lote canônicos. Produção futura adapta para estes tipos; não cria cópias concorrentes. |
| `Linhagem` | `volc_ads/campanha/brief.py`, projetada por `volc_ads/criativo_ponte.py` | Forma canônica da procedência que atravessa a fronteira de canal. Ausência permanece `None`; confirmação continua derivada dos bytes. |
| `Encomenda`, `Recibo` e máquina local | `backend/app/criativo/bancada/contrato.py` e `bancada/deposito.py` | Contrato hoje provado pela bancada SQLite. S0 não o migra, estende ou apresenta como Postgres. |

`criativo_job` e `criativo_render_job` possuem ciclos de vida diferentes. Um é a
unidade de produto; o outro será uma tentativa executável. Igualar os dois por
nome, compartilhar idempotency key sem escopo ou promover o estado de um por
inferência sobre o outro criaria dupla verdade.

## Fronteira HTTP preservada

O router de produto continua em `backend/app/routers/criativos.py`. As oito
operações já existentes abaixo foram movidas, sem troca de path, DTO,
autenticação, status ou payload, para
`backend/app/routers/criativos_execucao.py`:

| Método | Path | Status base | Portão |
|---|---|---:|---|
| GET | `/api/criativos/bancada/motores` | 200 | `exigir_usuario` |
| POST | `/api/criativos/bancada/trabalhos` | 201; replay 200 | `exigir_usuario` |
| GET | `/api/criativos/bancada/trabalhos` | 200 | `exigir_usuario` |
| GET | `/api/criativos/bancada/trabalhos/{trabalho_id}` | 200 | `exigir_usuario` |
| POST | `/api/criativos/bancada/trabalhos/{trabalho_id}/cancelar` | 200 | `exigir_usuario` |
| POST | `/api/criativos/bancada/trabalhos/{trabalho_id}/retomar` | 201; replay 200 | `exigir_usuario` |
| GET | `/api/criativos/bancada/trabalhos/{trabalho_id}/linhagem` | 200 | `exigir_usuario` |
| GET | `/api/criativos/bancada/arquivo/{trabalho_id}/{slot}` | 200 | `exigir_usuario` |

O app registra primeiro o router de produto e depois o de execução. O prefixo e
a tag pública continuam `/api/criativos` e `criativos`. Nesta fatia, o router de
execução ainda chama `app.criativo.bancada.servico`; trocar esse adapter pertence
a P17-T04 e exige as mesmas provas de contrato nos dois depósitos.

## Territórios exclusivos

| Fatia | Escrita exclusiva | Pode fazer | Não pode antecipar |
|---|---|---|---|
| S0 | `routers/criativos.py`, `routers/criativos_execucao.py`, registro em `main.py`, testes de equivalência e este documento | Separar apresentação e reservar namespaces vazios. | Fila, storage, worker, motor, destino ou alteração de schema. |
| P17-T03 | Migration v11_03 e provas operacionais, em rodada autorizada própria | Aplicar/preflight/rollback no Supabase oficial após autorização explícita. | Alterar contrato HTTP ou executar migration como efeito de import/startup. |
| P17-T04 | `backend/app/criativo/deposito/**` | Definir uma porta única e adapters SQLite/Postgres equivalentes. | Duplicar `Encomenda`/`Recibo`, escolher fallback silencioso ou confundir `criativo_job` com attempt. |
| P17-T05 | `backend/app/criativo/worker/**`, `deploy/creative-worker/README.md` e novo `deploy/creative-worker/runtime/**` | Reivindicar attempts, renovar lease e encerrar com recibo no runtime isolado. | Rodar no processo web, iniciar em import, editar `deploy/creative-worker/remotion/**` ou usar a máquina do Supabase oficial. |
| P17-T06 | novo `backend/app/criativo/storage/**` e testes de contrato próprios | Upload, leitura de volta e verificação de bytes/hash antes de `VERIFIED_OK`. | Converter ausência em zero, declarar verificação só porque o upload respondeu ou criar bucket nesta S0. |
| P17-T07 | novo `backend/app/criativo/render/**`, novo `deploy/creative-worker/remotion/**` e testes herméticos | Tornar fontes e dependências herméticas e registrar decisão de licença. | Abrir rede durante render, editar `deploy/creative-worker/runtime/**` ou afirmar hermetismo por fixture. |
| P17-T08 | `backend/app/criativo/destino.py`, futuro `backend/app/criativo/destinos/**` e adapter de canal aprovado | Propor entrega tipada e idempotente, vincular asset aprovado a destino e guardar recibo. | Publicar automaticamente, chamar plataforma em import/teste ou recriar `Asset`/`LoteDeAssets`/`Linhagem`. |

Os namespaces `criativo/deposito`, `criativo/worker`, `criativo/destino.py` e
`deploy/creative-worker` estão vazios de comportamento em S0. Sua importação não
faz I/O e sua existência não é evidência de capacidade.

Ao iniciar cada fatia, o integrador transfere explicitamente o namespace
reservado ao owner declarado acima: P17-T04 recebe `criativo/deposito/**`;
P17-T05 recebe `criativo/worker/**`, o README-raiz e somente
`deploy/creative-worker/runtime/**`; P17-T07 recebe somente
`criativo/render/**` e `deploy/creative-worker/remotion/**`; P17-T08 recebe
`criativo/destino.py`. **Nenhuma tarefa recebe `deploy/creative-worker/**` por
inteiro.** Assim, P17-T05 e P17-T07 nunca possuem simultaneamente a subárvore
Remotion: runtime/claim/lease é de T05; composição, fontes e licença são de T07.
P17-T06 cria somente o caminho novo declarado na tabela. Até cada transferência,
nenhum outro agente edita o território; depois dela, S0 deixa de ser owner. Essa
passagem evita que o esqueleto "sem comportamento" vire uma segunda
implementação por acidente.

## Ordem de integração

1. Integrar S0 e repetir as provas de equivalência das rotas e de segurança no
   commit resultante.
2. Executar P17-T03 somente com autorização externa explícita e prova de backup,
   preflight, RLS, grants e rollback.
3. Implementar P17-T04 contra testes compartilhados de claim, lease, heartbeat,
   idempotência, transição e recibo; só então selecionar depósito por ambiente.
4. Implementar P17-T05 consumindo exclusivamente a porta de P17-T04.
5. Fechar P17-T06 antes de apresentar qualquer artefato remoto como verificado.
6. Fechar P17-T07 antes de usar vídeo como prova de produção hermética.
7. Executar P17-T08 com aprovação humana e sem publicação automática.

P17-T03 a P17-T08 permanecem `todo` após S0. A separação de arquivos reduz
conflito de ownership; não satisfaz os critérios de aceite dessas tarefas.

## Fechamento de P17-T09 (S0 — Contratos HTTP e Ownership)

A tarefa P17-T09 consolida a extração e a preservação estrita da fronteira de execução criativa S0 sem introduzir capacidades produtivas não autorizadas. A primeira bateria foi reaberta em v2 porque a contraprova do Sol mostrou aliasing entre fixture e oráculo nos payloads HTTP, e depois revelou que headers extras não enumerados ainda escapavam do golden. Com oráculos serializados, independentes e headers fechados por allowlist explícita, os cinco critérios binários ficam provados por testes externos:

1. **Equivalência semântica e mutações das oito respostas**: Os goldens HTTP serializados, oito mutantes de payload/bytes aplicados antes da requisição e o mutante de segurança de header extra provam que chave faltante ou extra, tipo concreto, forma estrutural, conteúdo observável, bytes divergentes ou header inesperado fora da allowlist quebram o gate nas rotas cobertas (`/motores`, `/trabalhos` inicial/replay, listagem, leitura rica, cancelamento, retomada, linhagem e `/arquivo`).
2. **Status, header e idempotência de criação e retomada**: Provado status 201 para criações e retomadas iniciais (com despacho do trabalho), status 200 com header `X-Criativo-Idempotente: replay` para reenvios idempotentes (sem redespacho), e isolamento de tenant que impede vazamento ou reutilização indevida entre contas.
3. **Ownership único de rota e subárvore**: Cada path da bancada é registrado exatamente uma vez no app FastAPI montado; o router de produto `criativos.router` não mantém cópia das rotas de execução; e as subárvores futuras (`criativo/deposito`, `criativo/worker`, `criativo/destino.py`, `deploy/creative-worker`) estão desprovidas de comportamento em S0.
4. **Golden OpenAPI reproduzível com diagnóstico útil**: O schema OpenAPI das rotas da bancada é byte-estável e verificado contra o golden original via SHA-256 (`28bb086dcf5ca5f4667b9c0c4aecb1778783c66c288bc060f5cb674981b020e8`); versões de FastAPI e Pydantic são validadas contra a faixa provada; e desvios geram unified diff legível apontando arquivo e nó divergente.
5. **Regressão de segurança e isolamento de I/O**: Todas as rotas recusam credenciais ausentes ou inválidas com 401/403 sem side-effects e sem tocar no disco ou criar diretórios fora do `tmp_path` controlado dos testes.

## P17-T09 v2 — Oráculos independentes

`backend/tests/test_criativo_rotas_equivalentes.py` não deriva mais expectativas de `_renderizado`, `_dto_esperado`, `_cancelado` nem de outro helper que remonte o DTO público. Cada golden HTTP é um `_GoldenHTTP` congelado com status, headers públicos, bytes serializados e JSON tipado parseado sempre a partir desses bytes. As fixtures que entram nos dublês são copiadas por `copy.deepcopy()` na fronteira de injeção. A prova nominal de aliasing cobre exatamente o defeito reportado: alterar `motores[0].slug` antes da chamada muda a resposta observada, mas não muda o golden esperado. A prova nominal de headers muta `bancada_ler` antes da requisição para emitir `Cache-Control: public, max-age=3600`; esse header extra agora quebra o golden mesmo com corpo e status preservados.

As respostas idempotentes também têm golden próprio: criação replay e retomada replay preservam status `200`, header `X-Criativo-Idempotente: replay`, bytes e JSON tipado, separados das respostas iniciais `201`.

| Mutante | Mutação aplicada antes da requisição HTTP | Propriedade externa violada | Rota e resposta observada | Teste que fica vermelho | Restauração que volta a verde |
|---|---|---|---|---|---|
| M1 | `motores[0].slug = "motor-mutante"` na lista devolvida por `bancada_servico.motores_disponiveis()` | conteúdo observável do catálogo de motores | `GET /api/criativos/bancada/motores` responde `200` com slug mutante | `test_mutante_real_motores_slug_nao_altera_golden_e_morre` | o mesmo teste chama a rota com fixture fresca e `_GOLDEN_MOTORES` volta a passar |
| M2 | wrapper em `criativos_execucao._trabalho_dto` troca `tentativa` por `true` no job criado | tipo concreto e bytes do JSON | `POST /api/criativos/bancada/trabalhos` responde `201` com `tentativa: true` | `test_mutante_real_criacao_tentativa_bool_morre_e_restaura` | o `monkeypatch.context()` restaura o mapper e `_GOLDEN_CRIACAO_INICIAL` volta a passar |
| M3 | wrapper em `_trabalho_dto` troca `vivo` por `false` no item em execução | conteúdo do item listado | `GET /api/criativos/bancada/trabalhos?limite=7` responde `200` com `trabalhos[0].vivo: false` | `test_mutante_real_listagem_vivo_false_morre_e_restaura` | restauração do mapper e fixture fresca fazem `_GOLDEN_LISTAGEM` passar |
| M4 | wrapper em `_artefato_dto` reintroduz `caminho` no artefato público | chave extra e vazamento de caminho local | `GET /api/criativos/bancada/trabalhos/t-rico` responde `200` contendo `recibo.artefatos[0].caminho` | `test_mutante_real_leitura_vaza_caminho_morre_e_restaura` | o mapper original remove `caminho` e `_GOLDEN_LEITURA` volta a passar |
| M5 | wrapper em `_trabalho_dto` troca `canceladoMotivo` por `"outro motivo"` | conteúdo do cancelamento | `POST /api/criativos/bancada/trabalhos/t-cancelled/cancelar` responde `200` com motivo alterado | `test_mutante_real_cancelamento_motivo_alterado_morre_e_restaura` | mapper restaurado e trabalho fresco fazem `_GOLDEN_CANCELAMENTO` passar |
| M6 | wrapper em `_trabalho_dto` troca `retomaDe` por `"t-outro"` no job retomado | linhagem observável da retomada | `POST /api/criativos/bancada/trabalhos/t-original/retomar` responde `201` com origem errada | `test_mutante_real_retomada_linhagem_trocada_morre_e_restaura` | mapper restaurado faz `_GOLDEN_RETOMADA_INICIAL` passar |
| M7 | wrapper em `_trabalho_dto` remove `estado` do segundo item da cadeia | chave obrigatória da linhagem | `GET /api/criativos/bancada/trabalhos/t-retomado-linhagem/linhagem` responde `200` com item sem `estado` | `test_mutante_real_linhagem_remove_estado_morre_e_restaura` | mapper restaurado e cadeia fresca fazem `_GOLDEN_LINHAGEM` passar |
| M8 | arquivo servido é gravado com um byte extra antes da chamada | bytes e `content-length` do artefato | `GET /api/criativos/bancada/arquivo/t-arquivo/1x1` responde `200` com corpo de 32 bytes em vez de 31 | `test_mutante_real_arquivo_bytes_alterados_morre_e_restaura` | arquivo restaurado com 31 bytes faz `_GOLDEN_ARQUIVO` passar |
| M9 | wrapper do handler `bancada_ler` injeta `Cache-Control: public, max-age=3600` antes da requisição HTTP autenticada | header extra de segurança fora da allowlist explícita | `GET /api/criativos/bancada/trabalhos/t-rico` responde `200` com leitura autenticada cacheável publicamente | `test_mutante_real_leitura_cache_publico_em_header_extra_morre_e_restaura` | handler restaurado e allowlist fechada fazem `_GOLDEN_LEITURA` passar sem `cache-control` |
