# VOLC O.S. — guia do projeto

Dashboard de gestão de campanhas/monetização (Google Ads + GAM/AdSense).
Stack: Vite + React 18 + TypeScript + shadcn/ui + Tailwind + React Query + Supabase.
Fork do **webgo** (`metro-campaign-view`) — ver "Sincronização com o webgo".

## Mapa Vivo — memória estrutural obrigatória

O VOLC O.S. possui um knowledge graph híbrido que une operação, banco, automações,
documentos, código e SQL. Antes de responder sobre arquitetura, roadmap, impacto,
fluxos ou limpeza de legado, consulte o grafo; não conclua que algo é lixo apenas
porque o nome parece antigo ou porque não apareceu em uma busca textual simples.

### Ordem das fontes

São cinco níveis, nesta ordem — a autoridade cai a cada degrau:

| # | Camada | Path | Uso |
|---|---|---|---|
| 1 | Curadoria operacional humana | `docs/volc-os-graph/curadoria-operacional.json` | **EDITÁVEL À MÃO.** Estados, prioridades, evidências e significado de negócio |
| 2 | Snapshot operacional gerado | `docs/volc-os-graph/volc-os-graph.json` | **GERADO** (curadoria + snapshots vivos). Não editar |
| 3 | Extração técnica regenerável | `.graphify-cache/code/graphify-out/graph.json` | **GERADO.** Código, SQL, imports e chamadas; nunca é autoridade de negócio |
| 4 | Grafo híbrido canônico | `graphify-out/graph.json` | **GERADO.** Consulta de relações, caminhos e impacto |
| 5 | Exports e visualizações | `graphify-out/obsidian-volc-os/`, `graphify-out/graph.graphml`, `graphify-out/cypher.txt`, `entregaveis/Explorador_Neural_VOLC_OS.html` | **DERIVADOS**, nunca fonte |

Apoio (não entram na cadeia de autoridade):

| Camada | Path | Uso |
|---|---|---|
| Frescor | `graphify-out/UPDATE_STATUS.json` | Data, commit, hashes, fontes e contagens da última geração |
| Guia humano | `docs/volc-os-graph/ARQUITETURA-PERMANENTE.md` | Arquitetura, formatos, Obsidian e nuvem |

O formato canônico é JSON node-link (`nodes` + `links`, compatível com NetworkX).
As exportações GraphML, CSV, Cypher, Obsidian e HTML são derivadas e não devem ser
editadas como fonte.

⚠️ **Editar `volc-os-graph.json` à mão é trabalho perdido** — ele é reescrito no build
seguinte. Curadoria de negócio vai em `docs/volc-os-graph/curadoria-operacional.json`:
o gerador **lê, valida** (schema, clusters, estados, IDs duplicados, referências quebradas)
e combina com os snapshots vivos, e **nunca escreve** nesse arquivo — há uma guarda por hash
(`_guarda_fonte_humana`) que faz o build falhar se ele for tocado.

### Consultar antes de explorar arquivos

```bash
python3 scripts/atualizar_grafo_volc_os.py --check
.venv-graphify/bin/graphify query "como X funciona e a quais domínios se conecta?"
.venv-graphify/bin/graphify path "Origem" "Destino"
.venv-graphify/bin/graphify explain "Componente"
.venv-graphify/bin/graphify affected "Componente" --depth 2
```

Se `--check` retornar `current: false`, informe que o grafo está defasado. Para
atualizar, use sempre o pipeline VOLC:

```bash
python3 scripts/atualizar_grafo_volc_os.py                # reconstrução completa
python3 scripts/atualizar_grafo_volc_os.py --refresh-live # inclui inventário read-only do Supabase
```

**Nunca execute `graphify update .` diretamente.** Isso substituiria o híbrido
por um grafo somente de código e apagaria a camada operacional da saída canônica.

## Direção arquitetural — profissionalização sem reescrita total

O alvo é uma Clean Architecture pragmática, migrada por domínio e sem “big bang”.
Os domínios de negócio reconhecidos no Mapa Vivo são: estratégia/portfólio,
descoberta/pauta, conteúdo/publicação, aquisição/campanhas, medição/monetização,
decisão/atuação, qualidade do publisher, governança, plataforma/integrações e dados.

Para código novo ou módulos tocados durante uma entrega, separe responsabilidades:

```text
domain/          regras e modelos de negócio, sem framework ou I/O
application/     casos de uso e portas/interfaces
infrastructure/  Supabase, Google Ads, n8n, HTTP, arquivos e implementações externas
presentation/    rotas, controllers, páginas, componentes e adaptação de entrada/saída
```

No frontend, `presentation/` pode ser expresso como `pages/`, `components/` e
`hooks/`, mas regras de negócio não devem morar em componentes React. No backend,
routers não devem concentrar regra, persistência e integração no mesmo arquivo.
Código compartilhado só vai para `shared/` quando houver dois consumidores reais;
“shared” não é depósito de utilitários sem dono.

### Protocolo para legado, testes e candidatos a lixo

Antes de mover, consolidar ou remover qualquer arquivo:

1. Consulte `graphify explain`, `affected` e `path` para levantar relações.
2. Confirme com `rg`, imports, rotas, registro de plugins/workflows e referências SQL.
3. Classifique o item como `ativo`, `compatibilidade`, `migração`, `gerado`,
   `experimento`, `duplicado comprovado` ou `candidato sem evidência de uso`.
4. Registre o consumidor substituto e um caminho de rollback.
5. Mova por pequenos lotes e rode os gates relevantes depois de cada lote.
6. Só exclua após provar ausência de consumidores e cobertura do comportamento útil.
7. Atualize o Mapa Vivo ao concluir uma mudança estrutural material.

## Protocolo obrigatório de fechamento

Código pronto não encerra uma entrega material. Antes de dizer que uma feature,
schema, workflow, integração, decisão arquitetural ou tarefa terminou:

1. localize a tarefa correspondente em `volc-os-workbook/ROADMAP-VIVO.json`;
2. registre prova factual, lacunas restantes e estado honesto, sem promover para
   `done` apenas porque há código;
3. atualize a curadoria humana somente quando estado, evidência ou relações de
   negócio realmente mudarem;
4. reconstrua o Mapa Vivo pelo pipeline VOLC e execute `--check`;
5. cite no handoff os IDs das tarefas, nós afetados e o resultado de frescor.

Em trabalho paralelo, investigadores, revisores e writers isolados não disputam
Roadmap/curadoria. Eles entregam um delta de curadoria; o integrador único aplica
e reconstrói uma vez após o merge. Trabalho que só existe numa branch/worktree
não pode marcar a fonte compartilhada como concluída.

Regras adicionais:

- testes antigos não são lixo automaticamente; podem ser a única especificação de
  comportamento legado;
- mocks usados em produção, smoke tests, backfills e adaptadores de migração devem
  ser identificados antes de uma limpeza;
- arquivos gerados devem ter gerador e destino documentados, e não ser corrigidos
  manualmente;
- código morto confirmado deve sair, não ser apenas movido para uma pasta `legacy/`;
- compatibilidade ainda necessária deve ficar atrás de adapter/facade, com condição
  explícita de aposentadoria;
- não misture reorganização estrutural ampla com mudança funcional ampla no mesmo
  lote: preserve a capacidade de provar equivalência e reverter.

O primeiro entregável da profissionalização deve ser um inventário de candidatos,
com evidência, impacto, risco e decisão — não uma exclusão em massa.

## Rodar localmente

```bash
./start-dev.sh          # sobe front (Vite :8080) + api (Express :3001) juntos
./start-dev.sh --stop   # encerra os dois
```

Abra **http://localhost:8080** — hot-reload no front. O Vite faz proxy de `/api` e
`/health` para o Express (`server/index.js`), que fala com o Supabase usando a
`service_role` de `.env.server` (nunca exposta no browser). Também: `npm run dev:all`.

Build/checagem: `npx tsc --noEmit -p tsconfig.app.json` · `npm run build` · `npm test` (Meta CAPI).

⚠️ **`npx tsc --noEmit` puro não checa nada.** O `tsconfig.json` da raiz é *solution-style*
(`"files": []` + `references`), então sem `-p` ou `-b` o compilador roda sobre **zero arquivos**
e sai 0 — um gate que sempre passa. Use sempre `-p tsconfig.app.json` (é ele que tem
`include: ["src"]`).

Segunda armadilha, na mesma trilha: pastas duplicadas em `node_modules/@types/` com sufixo
`" 2"` (cópia de Drive/Finder, npm nunca cria nome com espaço) viram erros `TS2688`
*"Cannot find type definition file"* — e enquanto eles existem o `tsc` **para antes da
checagem semântica**, escondendo todos os erros reais do `src/`. Se aparecer `TS2688`,
apague as duplicatas antes de acreditar no resultado:
```bash
find node_modules/@types -maxdepth 1 -type d -name "* 2" -exec rm -rf {} +
```
Hoje o gate real acusa **76 erros herdados do webgo** (`supabaseDataService.ts` 31,
`ProjectDashboard.tsx` 12, `AddOpportunityModal.tsx` 8, …). Nenhum é do motor de pautas.
Doze deles são `TS2304` ("Cannot find name") — bomba de runtime, não ruído de tipo:
`setCustomDate`/`setRangeStartDate`/`setRangeEndDate` em `ProjectDashboard.tsx`,
`generateCampaignAnalysisData` em `SiteAnalysis.tsx`, `spendError` em `supabaseDataService.ts`.
E note que `npm run build` **não pega nada disso**: esbuild não checa tipos.

## Banco de dados — Supabase self-hosted (Hetzner)

O Supabase **não** é o hosted da supabase.com; é self-hosted num servidor Hetzner.
Esta é uma decisão arquitetural fechada: **o único Supabase operacional do VOLC O.S.**
é `https://database.agenciavolc.com.br`. Qualquer `*.supabase.co` encontrado fora de
fixture ou arquivo histórico é consumidor legado a migrar/aposentar, não fallback.
Antes de iniciar ou alterar o ambiente, rode `python3 scripts/verificar_autoridade_supabase.py`.
Veja `docs/architecture/ADR-SUPABASE-AUTORIDADE-OPERACIONAL.md`.
`database.agenciavolc.com.br` → **178.156.196.149** (`ubuntu-4gb-ash-1`, Ashburn).

**Acesso SSH** (chave dedicada, sem passphrase — só nesta máquina):
```bash
ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149
```

**Estrutura no servidor:**
- Supabase (docker-compose): `/root/supabase/docker/`
- Container do Postgres: `supabase-db` · gateway: `supabase-kong` · edge runtime: `supabase-edge-functions` (existe → Meta CAPI viável)
- Backups: `/root/backups/`

**Rodar SQL / aplicar migração** (de dentro do box ou por pipe do SSH):
```bash
# do servidor:
docker exec -i supabase-db psql -U postgres < arquivo.sql
# da sua máquina, sem copiar arquivo:
cat arquivo.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```
Migrações do sync webgov6: `src/sql/volc-sync/` (aplicadas). O `04_*` está **bloqueado**
(2 defeitos destrutivos) — ver `src/sql/volc-sync/README.md`.

**Studio:** atrás do basic-auth do Kong em `https://database.agenciavolc.com.br/`
(usuário/senha do dashboard estão no `.env` vivo do servidor).

### Onde ficam os segredos (nunca commitar)
- `.env` e `.env.server` (locais, gitignored) — já têm a `SUPABASE_SERVICE_ROLE_KEY` correta.
- `~/.ssh/volc-supabase-live.env` (local, chmod 600) — cópia do `.env` vivo do servidor
  (JWT_SECRET, service_role, senha do Postgres, dashboard). É a fonte da verdade das chaves.
- O `.env` vivo no servidor: `/root/supabase/docker/.env`.

### ⚠️ Armadilha do Kong (kong.yml)
O `kong.yml` é **gerado** por um entrypoint `eval echo` que **remove aspas não-escapadas**.
Qualquer `origins: - "*"` no template `/root/supabase/docker/volumes/api/kong.yml` PRECISA
estar escapado como `- \"*\"`, senão o YAML gerado sai `- *` (âncora inválida) e o Kong
**crasha no próximo reboot** — derrubando o site inteiro. Backups: `kong.yml.bak-*` na mesma pasta.

### Se as credenciais "não baterem"
As chaves de API (anon/service_role/JWT) já foram **regeneradas** uma vez — arquivos antigos
(ex.: Google Drive `SECURITY/SUPABASE`) estão **defasados**. A verdade é sempre o
`/root/supabase/docker/.env` vivo. O `Reset root password` da Hetzner é **no-op** aqui
(sem `qemu-guest-agent`); para recuperar acesso perdido, use rescue e monte `/dev/sda1`.

## Sincronização com o webgo (upstream)

Fork do `metro-campaign-view`; remote `upstream` já configurado. Para trazer uma versão nova:
```bash
./scripts/sync-upstream.sh webgov7
```
Faz backup, simula o merge, resolve com `rerere`, poda o Pautador Pro e checa o branding.
O delta permanente (o que sempre diverge) está em **`docs/VOLC-DELTA.md`** — leia antes de
sincronizar. O Pautador Pro fica **fora de escopo**: `./scripts/prune-pautador.sh` (idempotente).

## Deploy

Vercel (projeto `webgo`). O deploy é por push + **Promote to Production** manual no painel.
As funções serverless ficam em `api/` (espelham as rotas do `server/index.js`). Variáveis de
ambiente (incl. `SUPABASE_SERVICE_ROLE_KEY`) são cadastradas no painel da Vercel.
