# GATES — traffic-operating-cockpit-v2

Base `207e91f1da290130e8d02b78c3ba1c8e9a761111` · branch
`sprint/traffic-operating-cockpit-v2` · worktree isolada
`/private/tmp/volc-traffic-operating-cockpit-v2`.

Os comandos abaixo foram DESCOBERTOS no repositório (`package.json`,
`pytest.ini`, `scripts/`), não inventados.

## Linha de base medida ANTES de qualquer alteração

Sem baseline não há como distinguir regressão de defeito herdado. Estes números
foram tirados na worktree limpa, no SHA da base:

| gate | comando | baseline no SHA da base |
|---|---|---|
| TypeScript | `npx tsc --noEmit -p tsconfig.app.json` | **76 erros herdados** (conferido contra o número que `CLAUDE.md` documenta) |
| Vitest | `npx vitest run` | **1481 passed, 5 skipped**, 100 arquivos |
| Pytest | `pytest backend/tests volc_ads -q` | **4253 passed, 89 skipped, 1 failed** |

⚠️ **A falha do pytest é herdada e não é minha.** É
`backend/tests/test_trafego.py::test_provar_sem_copy_reprova_e_diz_por_que`: o
cluster do ambiente não foi minerado pelo motor Python de elegibilidade paga, e
a rota devolve `409 N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`. O teste tolera
422, 503 e 504 e não tolera 409. Ela reproduz na árvore intocada.

⚠️ **`npx tsc --noEmit` sem `-p` compila ZERO arquivos e sai 0.** O
`tsconfig.json` da raiz é solution-style. Um gate que sempre passa é pior que
gate nenhum; todos os números acima usam `-p tsconfig.app.json`.

## Resultado ao fim da sprint

| gate | comando | resultado | veredito |
|---|---|---|---|
| TypeScript | `npx tsc --noEmit -p tsconfig.app.json` | conjunto de erros **idêntico ao baseline** (`diff` linha a linha, não só contagem) | sem regressão |
| Vitest completo | `npx vitest run` | **1513 passed, 6 skipped** (eram 1481/5) | +32 casos |
| Pytest (suítes tocadas) | `pytest backend/tests/test_trafego_plataforma.py backend/tests/test_trafego_contrato_canais.py -q` | **99 passed** | verde |
| Bancada fora do bundle | `python3 scripts/gate_bancada_fora_do_bundle.py` | **OK** | verde, e provado que falha |
| Build de produção | `npx vite build` (dentro do gate acima) | conclui | verde |
| Higiene do diff | `git diff --check` | limpo | verde |
| Varredura de segredos | ver abaixo | nenhum | verde |
| Ausência de mutação Google | ver abaixo | nenhuma | verde |
| QA visual | 104 capturas, 4 larguras × 2 temas | 0 overflow, 0 erro de console, 0 alvo < 40px | verde |

### A contagem de erros do `tsc` não é comparada por número

`grep -c "error TS"` conta linhas, e um erro TS2322 ocupa três. A comparação é
feita por conjunto:

```bash
npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep "error TS" | sort > /tmp/now.txt
git stash -q && npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep "error TS" | sort > /tmp/base.txt
git stash pop -q
diff /tmp/base.txt /tmp/now.txt   # vazio = sem regressão
```

Resultado: **vazio**. Nenhum erro novo, nenhum erro herdado sumindo por acidente.

### O gate do bundle foi provado ao contrário

Um gate que nunca falhou não é um gate. Com o alias de produção desligado em
`vite.config.ts`, `gate_bancada_fora_do_bundle.py` acusa
`assets/BancadaVisual-*.js` e sai 1. Religado, sai 0. Registrado porque a versão
BARATA desta prova — ler a fonte e conferir o guarda `import.meta.env.DEV` —
passava enquanto a página ia para o bundle.

### Varredura de segredos

```bash
git diff 207e91f1..HEAD | grep -inE \
  "service_role|eyJ[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY|\
FORGE_PERMITIR_ESCRITA=1|developer_token|refresh_token"
```

Nenhuma ocorrência. O `.env` da worktree é local, `gitignored`, e foi montado
**fail-closed**: sem `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID`,
`GOOGLE_APPLICATION_CREDENTIALS`, `N8N_BASE_URL` nem `N8N_API_KEY`. Uma chamada
ao Google Ads falharia por ausência de credencial antes de sair da máquina.

### Ausência de mutação externa

- `FORGE_PERMITIR_ESCRITA` **nunca** foi exportada. O ambiente subiu sem a flag
  `--permitir-escrita`, e o backend respondeu `{"engine":"mock"}` em `/health`.
- Nenhuma chamada real ao Google Ads, nenhum `validate_only` real, nenhum
  `mutate`. Nenhuma escrita no Supabase oficial, nenhuma migration, nenhum n8n,
  nenhum Data Manager, nenhum WordPress, nenhum AdsPower, nenhum Postiz.
- Nenhum deploy. `main` e `volc-os-v2` intocados; a sprint vive numa branch
  própria a partir de uma worktree isolada.
- O diff não acrescenta nenhum caminho de mutação: as duas rotas capazes de
  alterar conta (`POST /subir`, `POST /remover`) não foram tocadas.

### O que NÃO foi executado, e por quê

- **`pytest` completo ao final.** Rodei as suítes que o diff toca (99 passed) e
  o baseline completo no início. A suíte inteira leva ~3 min e carrega 1 falha
  herdada; ela não foi reexecutada ao final. Declarado em vez de omitido.
- **`npm run lint`.** Não foi executado; não faz parte do baseline medido.
- **`scripts/gate_sem_mutacao_google.py`.** Ele exercita contraprovas de ledger
  que dependem de estado de banco ausente nesta worktree. A garantia de zero
  mutação aqui é ambiental (fail-closed) e estrutural (nenhum caminho novo),
  não uma execução dele.
