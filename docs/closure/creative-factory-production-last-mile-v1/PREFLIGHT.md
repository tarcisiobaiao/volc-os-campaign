# Preflight factual — Creative Factory Production Last Mile V1

Medido antes de qualquer edição, na worktree isolada.

## Procedência

| | |
|---|---|
| Repositório | `tarcisiobaiao/volc-os-campaign` |
| Base | `origin/volc-os-v2` |
| SHA esperado pelo prompt | `c8ca8628e83742dd7da5242f0a015f76292aafe7` |
| SHA remoto medido | `c8ca8628e83742dd7da5242f0a015f76292aafe7` — **confere, sem divergência** |
| Branch | `sprint/creative-factory-production-last-mile-v1` |
| Worktree | `/private/tmp/volc-creative-factory-production-last-mile-v1` |
| Árvore na criação | limpa |

## Preflight obrigatório

| Comando | Resultado |
|---|---|
| `python3 scripts/verificar_autoridade_supabase.py` | `✓ Supabase oficial: https://database.agenciavolc.com.br` · exit 0 |
| `python3 scripts/atualizar_grafo_volc_os.py --check` | `{"current": false, "reason": "UPDATE_STATUS.json ausente"}` |

⚠️ **O grafo não está apenas defasado: ele não existe nesta linhagem.**
`graphify-out/` não é rastreado em `origin/volc-os-v2` (`git ls-files | grep -c '^graphify-out/'`
devolve **0**) e o diretório não existe na worktree. O relatório da missão anterior já
tinha medido que `git merge-base` entre `main` e `volc-os-v2` é **vazio** — são duas
raízes distintas. Portanto o Mapa Vivo publicado descreve **outra árvore**, e reconstruí-lo
daqui não é possível nem correto: esta missão emite `CURATION-HANDOFF.json` e o integrador
único aplica a curadoria depois, na linhagem que tem o grafo.

## Baseline dos gates — medido no SHA base, árvore limpa

| Gate | Baseline |
|---|---|
| `pytest backend/tests volc_ads -q` | **3358 passed · 53 skipped** (80,96 s) |
| `vitest run` (completo) | **1256 passed · 5 skipped** · 90 arquivos passaram, 1 pulado · exit 0 |
| `tsc --noEmit -p tsconfig.app.json` | **76 erros** — idêntico ao herdado documentado no `CLAUDE.md` |
| `scripts/provar-ciclo-v11_03.sh` | **129 passaram · 0 falharam** — aplicar → operar → reverter → reaplicar |

O Vitest exige `VITE_SUPABASE_URL` e `VITE_SUPABASE_ANON_KEY` presentes; foram usados
**placeholders não-credenciais** (`https://placeholder.invalid`), pelo motivo já medido
na missão anterior: `src/lib/supabase.ts:7` lança na ausência da variável, e o baseline
antigo colapsava **ausência de variável** em **falha de teste**.

## Ferramental disponível nesta máquina

| Ferramenta | Estado |
|---|---|
| Python | 3.14.6 · venv própria da worktree (`.venv-lastmile`), pytest 9.1.1, fastapi 0.115.6, Pillow 12.3.0, psycopg 3.3.5 |
| Node | v26.5.0 · npm 11.17.0 |
| `node_modules` | symlink para o repo principal — `package-lock.json` com **sha1 idêntico**, então não há divergência de árvore de dependências |
| Docker | 28.4.0, ativo |
| PostgreSQL descartável | `initdb`/`pg_ctl` em `/opt/homebrew/bin` (16 e 17) — é o caminho que `provar-ciclo-v11_03.sh` usa, em `mktemp -d` |
| ffmpeg / ffprobe | 8.1.2 |
| Remotion | **ausente do repositório** — `package.json` não cita `remotion`, e `node_modules/remotion` não existe |

## Confirmação de envelope no preflight

Nenhum ato externo. O único Postgres tocado foi o cluster descartável que `initdb`
cria e `pg_ctl stop` destrói dentro de `mktemp -d`.
