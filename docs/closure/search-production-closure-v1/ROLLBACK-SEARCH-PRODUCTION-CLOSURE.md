# Rollback — fechamento produtivo de Search

*Sprint `sprint/search-production-closure-v1` · base `f45e810`*

Três camadas independentes, da mais barata para a mais cara. Nenhuma delas foi executada
nesta sessão porque nada foi aplicado fora do repositório local.

## 1. Banco — reverter a v10_03 (provado)

```bash
cat supabase/migrations/v10_03_rollback.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
  root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

⚠️ **Leia isto ANTES de rodar.** O rollback derruba as colunas de aprovação, e com elas a
memória de quem autorizou o quê:

```sql
SELECT item_id, idempotency_key, aprovado_por, aprovado_por_sub, aprovado_em, aprovacao_impressao
  FROM public.trafego_lote_item WHERE aprovado_em IS NOT NULL;
```

E ele **reabre o defeito que a v10_03 fecha**: dois recibos em voo para o mesmo item
voltam a ser aceitos, e com eles a possibilidade de duas campanhas concorrentes na mesma
conta sem rastro da segunda.

O arquivo verifica, na própria transação, que a v10_01 continuou inteira — ele só pode
derrubar o que a v10_03 criou. Ciclo `aplicar → reverter → reaplicar sobre banco com
dado` provado em `scripts/provar-ledger-v10-03.sh`, seção M.

Para reverter a série toda, a ordem é a inversa da aplicação:
`v10_03_rollback` → `v10_02_rollback` → `v10_01_rollback`.

## 2. Código — reverter a branch

```bash
git log --oneline f45e810..HEAD          # os 5 commits da sprint
git revert --no-commit b8aac8f 876d090 609ddcf 807e306   # ou:
git reset --hard f45e810                  # a base é a tag harness-v3-supervised-local-accepted
```

Os commits são independentes na direção útil:

| Reverter | Efeito |
|---|---|
| só `876d090` | a tela volta a não mostrar o ledger; o backend continua gravando |
| só `609ddcf` + `b8aac8f` | `/subir` volta a chamar o Google sem recibo prévio |
| só `807e306` | a migration some; **não faça isso com a v10_03 aplicada no banco** |

⚠️ Reverter `807e306` sem rodar o rollback SQL deixa banco e código divergentes: o
`ledger.py` sumiria, mas as funções e o gatilho continuariam no Postgres.

## 3. O que este rollback NÃO desfaz, e é o ponto de decisão que sobrou

**Um `sem_resposta` é permanente.** A camada 3 da v10_01 conta recibos `em_voo` e
`sem_resposta` e recusa `indeterminado -> criando`; um recibo `sem_resposta` nunca reabre
(a v10_01 só permite `em_voo -> fechado`). Consequência: **depois de um timeout, aquele
plano não volta a ser enviável**, mesmo que a verificação prove que a campanha não existe
na conta.

Isso é *fail-closed* e foi **preservado de propósito** nesta sprint — a v10_03 não
afrouxa nenhuma guarda da v10_01. Mas é um item aberto real:

- **hoje**: mudar o plano gera chave de idempotência nova (ela é derivada do conteúdo) e
  o lançamento segue por um item novo. Funciona, mas o operador precisa saber disso.
- **decisão do dono**: se `trafego_verificacao.achou = false` deve ou não liberar um
  reenvio governado do mesmo plano. É afrouxamento de guarda de segurança, e por isso não
  foi tomada aqui.

## 4. Ambiente local

Nada instalado, nada configurado, nenhum processo em pé. As únicas marcas locais:

- `backend/.venv` → symlink para o venv do repositório principal (único com `google-ads`),
  excluído via `.git/info/exclude`. Remover: `rm backend/.venv`.
- `node_modules/` → `npm ci` a partir do lockfile existente.
- Clusters Postgres de prova nascem e morrem dentro dos próprios scripts, em `/tmp`.
