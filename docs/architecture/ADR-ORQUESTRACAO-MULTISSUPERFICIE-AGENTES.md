# ADR — Orquestração multissuperfície de agentes

- **Status:** aceito para operação local
- **Data:** 2026-10-15
- **Baseline de produto anterior ao control plane:** `6124c5501a4ab267057ae4e1f4b20bdbf3ee70f9`
- **Escopo:** Claude Projects, terminal Codex, terminal Claude e integrador único

## Contexto

O VOLC passou a executar missões simultâneas em três superfícies diferentes. O
ganho de velocidade é real, mas cada superfície também pode criar branches,
worktrees, migrations, recibos e mudanças em arquivos centrais. Sem ownership
explícito, o paralelismo produz retrabalho, conflitos silenciosos e versões
incompatíveis da verdade operacional.

O diretório externo `control-plane/` preserva a reconciliação anterior, mas seu
manifesto ainda referencia a fila encerrada antes do `main` canônico atual. Ele
é evidência histórica, não autoridade para novas execuções.

## Decisão

Adotamos três lanes executoras e um quarto papel exclusivo de integração:

1. **Claude Projects — Experience, QA e destinos.** Coordena scouts e revisores
   em paralelo, mas mantém no máximo um writer por conjunto de arquivos. Sua
   primeira frente de escrita é reconstruir o W13 sobre o W7 atual; D1 vem em
   série. Auditorias de FunnelForge, WordPress e destino pago podem ocorrer em
   paralelo, inicialmente em modo read-only.
2. **Terminal Codex — Ads, coleta e plano econômico.** É dono dos coletores
   Google Ads e JoinAds, atribuição econômica, ledger, Decision Lab e propostas
   shadow. Não altera Bia/Hermes nem a experiência editorial.
3. **Terminal Claude — Bia/Hermes.** Fecha a branch já existente com a mesma Bia
   do Telegram, reconcilia o delta contra o `main` atual e entrega um SHA
   candidato. Não cria uma nova persona e não assume coleta Ads.
4. **Integrador único — control plane.** É o único papel autorizado a avançar
   `main`, editar Roadmap/curadoria/grafo, resolver conflitos compartilhados,
   ordenar migrations, fazer push ou executar uma mutação externa autorizada.

Nenhum executor trabalha no checkout oficial. Novas lanes partem do
`origin/main` que já contenha este ADR; `6124c550` é a fotografia anterior ao
commit de coordenação, não uma instrução para voltar a uma base antiga. O
paralelismo termina na entrega de candidatos; a integração permanece serial.

## Ownership e locks

Os locks atuais e o estado das lanes estão no manifesto versionado
`docs/operations/agent-clusters-current.json`.

São exclusivos do integrador:

```text
AGENTS.md
CLAUDE.md
volc-os-workbook/ROADMAP-VIVO.json
docs/volc-os-graph/curadoria-operacional.json
docs/volc-os-graph/volc-os-graph.json
graphify-out/**
supabase/migrations/README.md
backend/app/main.py
src/App.tsx
src/components/layout/Layout.tsx
src/components/layout/Navigation.tsx
package-lock.json
```

Quando um executor precisar de um desses arquivos, ele inclui um patch proposto
no handoff. O integrador decide e aplica uma vez, durante a convergência.

## Contrato de handoff

Cada lane entrega `HANDOFF.md` e `handoff.json` com, no mínimo:

```json
{
  "mission_id": "...",
  "surface": "claude_projects|codex_terminal|claude_terminal",
  "base_sha": "...",
  "branch": "...",
  "head_sha": "...",
  "owned_paths": [],
  "files_changed": [],
  "commits": [],
  "roadmap_tasks": [],
  "graph_nodes": [],
  "gates": [],
  "production_accessed": false,
  "external_mutations": [],
  "migrations": [],
  "secret_scan": "passed|failed|not_run",
  "risks": [],
  "remaining_gaps": [],
  "curation_handoff": [],
  "rollback": "...",
  "candidate_status": "ready_for_review|changes_requested|blocked"
}
```

O `head_sha` entregue é imutável durante a revisão. Qualquer correção gera novo
commit e novo handoff.

## Fluxo de integração

1. congelar o SHA candidato;
2. revisão independente read-only;
3. conferir ancestry, arquivos e ownership;
4. integrar o SHA exato numa branch temporária com `--no-ff`;
5. executar gates focados e depois acumulados;
6. integrar a próxima lane;
7. reconciliar Roadmap, curadoria e grafo uma única vez;
8. criar o commit de convergência;
9. fazer push somente após os gates e a autorização aplicável.

## Hard stops

Uma lane para sem improvisar quando:

- o checkout oficial fica sujo;
- o base SHA muda sem reconciliação;
- surge alteração fora do ownership;
- duas lanes precisam escrever o mesmo arquivo;
- aparece segredo em diff, log ou artefato;
- uma migration aplicada precisaria ser reescrita;
- o rollback não é demonstrável;
- há acesso ou mutação de produção fora do escopo declarado;
- o teste falha por causa não compreendida;
- o espaço livre cai abaixo de 10 GiB; abaixo de 20 GiB gera alerta.

## Consequências

- Desenvolvimento horizontal continua em três superfícies.
- Escrita compartilhada, migrations e release permanecem seriais.
- Claude Projects pode usar multiagentes sem transformar vários agentes em
  vários donos do mesmo arquivo.
- O antigo `control-plane/` permanece como histórico; a época atual nasce em
  `control-plane/current/` e aponta para os manifestos versionados deste ADR.
- A automação do curador pós-merge ainda não existe; portanto P10-T15 permanece
  `partial`.
