# Recibo de prova — zero escrita em produção e zero efeito externo

Gerado pelo integrador no fechamento (16/10/2026), sobre `lab/data-foundation-20261016`, intervalo
`b6e85974..HEAD`. Comandos reproduzíveis a partir da raiz do worktree.

## Escopo do que mudou

| Checagem | Comando | Resultado |
|---|---|---|
| Arquivos fora do namespace da missão | `git diff --name-only b6e85974..HEAD \| grep -vE '^(experiments/data-intelligence-lab/\|docs/data-intelligence/\|tests/data-intelligence/\|research/data-intelligence/)'` | **nenhum** |
| Volume | `git diff --name-only b6e85974..HEAD \| wc -l`; `git rev-list --count [--no-merges] b6e85974..HEAD` | 392 arquivos; 107 commits (76 sem merge) |
| Roadmap, curadoria, grafo, `main` | idem (não aparecem na lista) | **não tocados** (aplicação bloqueada pelo classificador; delta em `handoffs/`) |
| Espaço em branco | `git diff --check b6e85974..HEAD` | 3 avisos de linha em branco no fim de arquivo (`RESUMO.md` gerado e dois `.py`); mantidos de propósito porque o conteúdo entra em fingerprints verificados por teste |
| Segredos | busca por JWT, `service_role`, `sk-`, chave privada, `password=` nos arquivos alterados | só o próprio teste de varredura (`test_observacao_sem_segredos.py`) casa |
| `*.supabase.co` | `grep -ln 'supabase\.co'` nos arquivos alterados | só listas de proibidos em teste e a frase do relatório final que afirma a ausência |
| Rede/mutação no código | `grep` por `requests`, `httpx`, `urllib3`, `psycopg`, `google.ads`, `aiohttp`, `.mutate(`, `urlopen(` em `src/volc_dil/fundacao` | **nenhum** |
| Ids reais | `grep` pelo id da campanha ativa, pela conta Google Ads e pelo domínio do cliente em docs, código, testes, resultados e scripts da missão | só a lista de proibidos de um teste de varredura |

## Produção

| Ação | Feita? | Prova |
|---|---|---|
| Leitura do Postgres oficial | sim, só leitura, 4 rodadas, `default_transaction_read_only=on` confirmado na 1ª consulta | `receipts/leituras-externas/RECIBO-LEITURAS-20261016.md` e os `.sql` da pasta |
| Escrita, DDL, migration, criação de view em produção | **não** | nenhuma consulta fora de SELECT/SHOW nos `.sql` versionados |
| Exportação de dados de produção para disco | **não** (tentativa bloqueada pelo classificador; nada gravado) | recibo, seção "Ação negada" |
| n8n, GTM, Google Ads, JoinAds, WordPress, Edge Functions | **não** acessados | nenhum cliente ou credencial dessas APIs no código; L6–L8, L13 não executadas |
| Push, merge em `main`, deploy | **não** | branch só local; merges apenas entre branches locais da missão |
| `.env` ou `~/.ssh` lidos ou impressos | **não**; a chave SSH foi só usada pelo cliente `ssh` | nenhum conteúdo de segredo em arquivo ou log versionado |

## Testes

`OMP_NUM_THREADS=2 experiments/data-intelligence-lab/.venv/bin/python -m pytest tests/data-intelligence -q`
→ **914 passed, 1 skipped** (medição grande opcional, só com `DIL_BENCH_N`). Determinismo: `scripts/fundacao_shadow.py
--verificar` confere provisório, gates, versão do código e simulador; `scripts/fundacao_simulador_pacote.py --verificar`
e o `RESUMO.md` do Model Lab regeneram byte a byte.

## Limpeza

Clusters PostgreSQL descartáveis apagados por cada frente; worktrees esparsos `worktrees/dil-fundacao-20261016-*`
(~3 MB cada) permanecem até o integrador removê-los; `artifacts/` vazio.
