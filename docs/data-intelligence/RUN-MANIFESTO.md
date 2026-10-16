# RUN-MANIFESTO — VOLC Data Intelligence Lab (execução 2026-10-15)

> Registro de baseline feito **antes** de qualquer implementação. As seções
> "Arquivos" e "Dependências" são atualizadas pelo integrador ao fim de cada fase.

## 1. Baseline

| Item | Valor |
|---|---|
| Data/hora da baseline | 2026-10-15T23:24:08-03:00 (America/Sao_Paulo, `-03`) |
| Worktree | `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/data-intelligence-overnight-20261015` |
| Branch | `lab/data-intelligence-overnight-20261015` (confere) |
| HEAD | `104bb0d089d6013c400014c443f9e79a77adbf20` (confere com a base esperada) |
| `git status` na baseline | `?? docs/data-intelligence/` (2 arquivos do operador: `CLAUDE-PROJECT-MEMORY.md`, `PROMPT-INICIAL-MULTIAGENTICO.md`) |
| Disco livre | 19 GiB de 926 GiB (98% usado) → após ambiente: 18 GiB |
| Máquina | macOS Darwin 24.6.0, arm64, 10 CPUs, 16 GiB RAM |
| Python do sistema | 3.14.6 (`/opt/homebrew`); **usado no lab:** CPython 3.13.0 (`/usr/local/bin/python3.13`, binário universal, executa arm64) |
| `uv` | ausente no sistema; instalado **só** em `experiments/data-intelligence-lab/.tools/bootstrap/` (uv 0.13.1), sem instalação global |
| Node | v26.5.0 (não usado pelo lab) |
| Ferramentas | git, ripgrep 14.1.1, jq |
| `python3 scripts/atualizar_grafo_volc_os.py --check` | `current: true`, `reason: insumos idênticos`, `built_at_commit 6124c550`, `input_sha256 9e9ecd08…be5a0`, 2603 insumos |
| Stash compartilhado | contém entradas de outras frentes; **não tocado** |
| `producao_acessada` | **false** |

## 2. Fontes lidas integralmente antes de editar

- `AGENTS.md`; `CLAUDE.md` (carregado pelo harness); `docs/data-intelligence/CLAUDE-PROJECT-MEMORY.md`.
- Catálogo `CATALOGO-DATA-INTELLIGENCE-ENGINES-VOLC-20261015.md` (cópia lida em `~/Downloads/`; byte-idêntica à de `volc-os-campaign/docs/strategy/`).
- `~/Downloads/GOLD_VOLC_PACOTE_COMPLETO_v2/ANALISE_GOLD_VOLC_v2.md`.
- `FONTE_EXTRAIDA_gold_arbitrage.txt` (1450 linhas). `FONTE_NUMERADA_gold_arbitrage.txt` foi verificada por script: removido o prefixo `Lnnn:`, as 1450 linhas são idênticas à extraída (0 divergências), portanto o conteúdo foi lido uma vez e as referências `Lx` valem para ambas.
- Nenhum arquivo GOLD foi copiado para o repositório.

## 3. Achado de baseline que muda o escopo

`volc_ads/economia/` (núcleo econômico D04 do catálogo, "E/P") **não existe nesta base**.
Ele vive apenas em branches `wip/*` (ex.: `wip/original-worktree-pre-qg-real-20261007`,
commit `043c77f5`) e no checkout histórico `volc-os-campaign`. Consequência: o laboratório
não pode importar o núcleo econômico como autoridade; o contrato do Lab será
autocontido e o encaixe com `volc_ads/economia/` vira handoff, não dependência.

O "replay atual" existente é `volc_ads/inteligencia_decisao/replay.py` (130 linhas): ele
reexecuta ~cenários dourados sintéticos de `cenarios_dourados.json` pelo pipeline do kernel.
Não é um replay econômico temporal sobre séries; o caminho com volume de linhas é
`normalizacao_google_ads.py` (1627 linhas).

## 4. Ambiente isolado

- Projeto: `experiments/data-intelligence-lab/pyproject.toml` + `uv.lock` (27 pacotes resolvidos).
- `exclude-newer = 2026-10-01T00:00:00Z`: só pacotes publicados ≥ 2 semanas antes da baseline (higiene de supply chain). Sem esse corte o resolvedor escolhia `polars 2.0.0`; com ele, `polars 1.44.2`.
- Caches e venv dentro do namespace e fora do Git (`.tools/`, `.venv/`, `.uv-cache/`), via `UV_CACHE_DIR` local e `UV_PYTHON_DOWNLOADS=never`.
- Comando reprodutível:

```bash
cd experiments/data-intelligence-lab
UV_CACHE_DIR=$PWD/.uv-cache UV_PYTHON_DOWNLOADS=never .tools/bootstrap/bin/uv sync --frozen --python /usr/local/bin/python3.13
```

| Pacote | Versão travada |
|---|---|
| duckdb | 1.5.6 |
| polars | 1.44.2 |
| numpy | 2.5.3 |
| scipy | 1.18.1 |
| statsmodels | 0.15.0 |
| scikit-learn | 1.9.1 |
| pandas (transitivo de statsmodels) | 3.0.6 |
| pytest (grupo dev) | 9.1.1 |

Tamanho: `.venv` 430 MB, `.uv-cache` 438 MB (removíveis; ver §7).

## 5. Testes relevantes pré-existentes (somente leitura)

`backend/tests/test_inteligencia_decisao_lab.py`, `test_inteligencia_decisao_normalizador.py`,
`test_intencao.py`, `test_intencao_regras_canonicas.py`, `test_recomendacao_shadow.py`,
`test_reconciliacao_nao_mata_vivo.py`, `test_trafego_custo_canonico.py`,
`test_trafego_reconciliacao.py`, `test_webgo_priors_nao_decisorios.py`,
`test_meta_v26_w15_suite_lab.py`. O `backend/.venv` não existe nesta worktree.

## 6. Diretórios que esta execução escreve

- `experiments/data-intelligence-lab/`
- `docs/data-intelligence/`
- `tests/data-intelligence/`
- `research/data-intelligence/` (somente se um clone raso for indispensável)

Configuração local adicionada: `experiments/data-intelligence-lab/.gitignore` (ignora venv/caches/artefatos) e `tests/data-intelligence/pytest.ini` (isola a coleta do conftest da raiz). Justificativa: manter a suíte do lab hermética e sem depender do `volc_ads.hermetico_testes`.

## 7. Limpeza

Tudo que esta missão cria fora do Git está sob `experiments/data-intelligence-lab/{.tools,.venv,.uv-cache,artifacts}`. Remoção segura: apagar esses quatro diretórios. Nada fora do namespace foi criado.

## 8. Arquivos e commits (fechamento 2026-10-16)

16 commits na branch da missão, todos dentro do namespace; lista, hashes de fixtures, fingerprints, testes e declarações de zero efeito em `PROOF-RECEIPT.json`. Suíte final: 172 testes verdes. Grafo no fechamento: `current: false` (os arquivos do lab entraram nos insumos; 2669 insumos) — rebuild cabe ao integrador após merge. Disco livre final: 15 GiB; fora do Git: `.venv` 458 MB, `.uv-cache` 1,5 GB, `.tools` 40 MB, `artifacts` 0 B.
