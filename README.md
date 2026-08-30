# VOLC O.S.

Plataforma operacional da VOLC para descoberta, conteúdo, publicação, aquisição,
campanhas, medição, monetização e decisão. O produto une React/TypeScript, backend
Python, motor Google Ads, Supabase self-hosted, n8n e FunnelForge.

## Começar

```bash
npm install
./start-dev.sh
```

Abra `http://localhost:8080`. Instruções de ambiente, banco e deploy ficam em
[`CLAUDE.md`](CLAUDE.md); regras permanentes para agentes ficam em
[`AGENTS.md`](AGENTS.md).

## Autoridade de dados

O único Supabase operacional do VOLC O.S. é o self-hosted em
`https://database.agenciavolc.com.br`. Projetos `*.supabase.co` encontrados no
legado não são alternativas válidas: precisam ser migrados, aposentados ou
mantidos apenas como referência histórica. A decisão e os limites estão no
[ADR de autoridade do Supabase](docs/architecture/ADR-SUPABASE-AUTORIDADE-OPERACIONAL.md).

## Mapa Vivo

Antes de investigar arquitetura ou impacto, consulte o grafo híbrido:

```bash
python3 scripts/atualizar_grafo_volc_os.py --check
.venv-graphify/bin/graphify query "como esta capacidade funciona?"
```

- fonte operacional: `docs/volc-os-graph/volc-os-graph.json`;
- fonte híbrida canônica: `graphify-out/graph.json`;
- guia: [`docs/volc-os-graph/ARQUITETURA-PERMANENTE.md`](docs/volc-os-graph/ARQUITETURA-PERMANENTE.md);
- visualização: `entregaveis/Explorador_Neural_VOLC_OS.html`.

## Organização do repositório

| Zona | Responsabilidade |
|---|---|
| `src/` | produto web e contratos de interface |
| `backend/` | APIs, casos de uso, motores e integrações do backend |
| `volc_ads/` | motor de criação e operação Google Ads |
| `funnelforge-migracao/` | engine e ponte de funis em migração controlada |
| `supabase/` | Edge Functions e artefatos Supabase versionados |
| `src/sql/` | migrações e contratos SQL do produto; leia o README local |
| `sql/` | diagnósticos e histórico SQL fora da linha principal |
| `docs/` | documentação ativa, arquitetura, referências e arquivo histórico |
| `scripts/` | automação reproduzível do repositório |
| `graphify-out/` | grafo híbrido e análises geradas |
| `entregaveis/` | artefatos humanos gerados |

Veja o [índice documental](docs/README.md) e a
[política de higiene](docs/architecture/REPOSITORY-HYGIENE.md).

## Gates mínimos

```bash
npx tsc --noEmit -p tsconfig.app.json
npm run build
python3 scripts/atualizar_grafo_volc_os.py --check
```

Os testes específicos devem ser executados conforme o domínio alterado. Não aplique
SQL pelo nome do arquivo e não remova legado sem prova de ausência de consumidores.
