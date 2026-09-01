# Rollback — fechamento produtivo de Search

*Sprint `sprint/search-production-closure-v1` · base `f45e810`*

Três camadas independentes, da mais barata para a mais cara. Nenhuma delas foi executada
nesta sessão porque nada foi aplicado fora do repositório local.

## 1. Banco — reverter a v10, na ordem inversa da aplicação (provado)

A janela autorizada aplicou **v10_01 → v10_03 → v10_04**. A reversão é a inversa:

```bash
# ⚠️ NUNCA automaticamente depois de uma migration já commitada. Preserve a
# evidência do estado e reporte ANTES: reverter apaga justamente a informação de
# que se precisa para entender o que aconteceu.
for r in v10_04_rollback v10_03_rollback v10_01_rollback; do
  echo "── $r ──"
  cat supabase/migrations/$r.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
    root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1" \
    || { echo "ABORTOU em $r"; break; }
done
```

Reverter só até um degrau é legítimo e às vezes é o certo — `v10_04_rollback` sozinho
devolve a reconciliação da v10_03 e deixa todo o resto de pé.

### 1.1 O que cada rollback custa

| Reverter | Reabre |
|---|---|
| `v10_04_rollback` (`eb93e200b66cf6df…`) | a reconciliação volta a **abortar** no caminho normal: `interrompido->concluido` deixa de existir e todo item `indeterminado` fica sem saída que não seja `UPDATE` à mão. Perde-se também a checagem de posse do item |
| `v10_03_rollback` (`b1c9d6598bd0bf52…`) | dois recibos em voo no mesmo item voltam a ser aceitos, e as colunas de aprovação somem |
| `v10_01_rollback` (`b75eb90b09447493…`) | o ledger inteiro sai |

⚠️ O `v10_04_rollback` restaura o corpo **completo** de `trafego_lote_estado_valido`,
com as quatro guardas da v10_01 (aprovação imutável, identidade do lote, monotonicidade
da quota, `atualizado_em`). Uma versão anterior dele restaurava um corpo truncado — o que
desfaria a v10_04 **e** apagaria guardas alheias junto, que é pior que a migration que ele
desfaz. Confira depois de rodar:

```sql
SELECT pg_get_functiondef(p.oid) LIKE '%a autorizacao nao se reescreve%'
   AND pg_get_functiondef(p.oid) LIKE '%atualizado_em := now()%' AS guardas_intactas
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='trafego_lote_estado_valido';
-- esperado: t
```

### 1.2 Antes de reverter a v10_03

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
dado` provado em `scripts/provar-ledger-v10-03.sh`: seção **M** para a v10_03 e seção
**M2** para a v10_04, ambas sobre banco com dado.

A `v10_02` **não foi aplicada** nesta janela, então `v10_02_rollback` não entra na ordem
de reversão.

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
