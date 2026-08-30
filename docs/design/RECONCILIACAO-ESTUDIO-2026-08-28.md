# Reconciliação factual — Estúdio Criativo VOLC

**Data:** 28/08/2026
**Método:** leitura direta de `git` e consulta read-only a `database.agenciavolc.com.br`.
**Ordem:** este documento foi escrito ANTES de qualquer código desta fase, e nada
nele veio do relatório anterior. Onde o relatório anterior foi conferido e bateu,
está dito; onde ele estava incompleto, também.

## 1. Git

| Fato | Valor |
|---|---|
| `main` no início desta fase | `5193575` |
| Branch anterior desta frente | `feat/criativos-schema-blindado` @ `608c39a` |
| Base dessa branch | `858f650` |
| Worktree anterior | `/private/tmp/volc-schema-criativos` (limpa, `git status` vazio) |
| Branch desta fase | `feat/estudio-template-lab` @ `870b9df` |
| Worktree desta fase | `/private/tmp/volc-template-lab` |

### O que o relatório anterior não disse: a `main` andou

Entre `858f650` e `5193575` entraram **quatro commits de outra frente** (Decision
Intelligence Lab e governança de agentes):

```
c846b56 feat(trafego): prova o Decision Intelligence Lab com replay sintético
6ff6fa7 fix(trafego): blinda ciência do Decision Intelligence Lab
69f5658 docs(governanca): fecha agentes no Roadmap e no grafo
5193575 docs(graph): registra laboratório de decisão parcial
```

Isso importa por uma razão prática: `git diff --stat main..HEAD` na branch antiga
mostra **4.554 linhas "removidas"**, incluindo `volc_ads/inteligencia_decisao/`
inteiro e `DecisionIntelligenceLab.tsx`. **Nada disso foi removido por esta frente.**
São commits que a `main` ganhou depois e que a branch antiga nunca teve — artefato
da comparação de dois pontos. O delta verdadeiro é o de três pontos:

```
git diff --stat main...HEAD  →  9 arquivos, 1550 inserções, 13 remoções
```

Ler o número errado aqui levaria alguém a concluir que a frente de criativos
destruiu o trabalho do laboratório de decisão. Ela não tocou em nenhum arquivo dele.

### Convergência aplicada

`feat/estudio-template-lab` nasceu de `5193575` e recebeu os dois commits desta
frente por cherry-pick. **Zero conflito.** Verificado depois: `pipeline.py` e
`DecisionIntelligenceLab.tsx` da outra frente estão presentes e intactos ao lado das
migrations v11. Sem merge na `main`, sem push.

## 2. Arquivos que pertencem a esta frente

Os nove do delta de três pontos:

```
backend/app/config.py                                 (+16)
backend/app/criativo/armazenamento.py                 (+33/-)
backend/app/criativo/video_ponte.py                   (+9/-)
docs/creative-engines/DELTA-PROPOSTO-ESTUDIO-C0-C1-C3.md (+76)
scripts/provar-ciclo-v11.sh                           (+121)
services/creative_engine/motores/gemini_imagem.py     (+19)
supabase/migrations/README.md                         (+66)
supabase/migrations/v11_02_parque_criativo.sql        (+1058, novo)
supabase/migrations/v11_02_rollback.sql               (+165, novo)
```

Nenhum arquivo de outra frente aparece. A worktree principal estava com
`git status` limpo no momento da medição.

## 3. Produção — `database.agenciavolc.com.br`

Consulta read-only, sem `ALTER`, sem `INSERT`, sem reaplicação de migration.
**As nove medidas do relatório anterior foram reconferidas uma a uma e todas bateram.**

| Medida | Valor observado |
|---|---|
| Tabelas `criativo_*` | **21** |
| RLS habilitada | 21 de 21 |
| RLS forçada | 21 de 21 |
| Policies | **0** |
| Grants `anon` | nenhum |
| Grants `authenticated` | nenhum |
| Grants `PUBLIC` | nenhum |
| Grants `service_role` | `INSERT, SELECT, UPDATE` nas 21 (sem DELETE, sem TRUNCATE) |
| Gatilhos não-internos | 6 |
| CHECKs em `criativo_*` | 79, **todas validadas** (`convalidated = t`) |

### Parque semeado

| Tabela | Linhas |
|---|---|
| `criativo_motor` | 3 |
| `criativo_modo_de_producao` | 7 |
| `criativo_formato` | 7 |
| `criativo_finalidade` | 9 |
| `criativo_skin` | 15 |
| `criativo_voz` | 14 |
| `criativo_gate` | 28 |
| `criativo_exigencia_de_canal` | 18 |
| `criativo_teto_combinado` | 3 |

### Dado operacional real: zero em tudo

`brand_pack`, `projeto`, `briefing`, `job`, `job_evento`, `master`, `rendition`,
`aprovacao`, `pacote`, `entrega`, `master_gate`, `master_direito` — **0 linhas cada**.

O schema está de pé e **nunca foi exercitado por um operador**. As guardas foram
provadas contra o banco real dentro de transação revertida; nenhuma peça real
nasceu. Qualquer afirmação de que o Estúdio "está em produção" precisa desta
ressalva: a **estrutura** está; a **operação** não começou.

### Storage

`select count(*) from storage.buckets` → **0**. Não há bucket `criativos`, e não
há nenhum outro bucket. O que o backend produz hoje fica no armazenamento local
do processo.

### As três colunas de vínculo

`criativo_job.motor_id`, `criativo_briefing.modo_id` e
`criativo_aprovacao.finalidade_id` existem, são **nullable**, e com 0 jobs não há
como distinguir "não preenchida por decisão" de "não preenchida por defeito". A
distinção só aparece quando o primeiro job real nascer — por isso ela vira critério
de aceite desta fase, não nota de rodapé.

## 4. Frescor do Mapa Vivo

`python3 scripts/atualizar_grafo_volc_os.py --check` → `"current": true`,
gerado em 28/08/2026 14:58 sobre o commit `69f5658`, com
`working_tree_dirty_at_build: true`. Graphify 0.9.48, 1105 arquivos de entrada.

O grafo está fresco **para a `main`**, e não conhece os dois commits desta frente.
Isso é o esperado e é o motivo de o handoff curatorial sair como proposta.
