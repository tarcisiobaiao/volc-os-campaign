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
