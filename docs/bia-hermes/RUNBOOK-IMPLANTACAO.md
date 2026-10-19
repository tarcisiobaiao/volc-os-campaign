# Bia V1: runbook de implantação

Ordem obrigatória: **CP0** (local) → **CP1** (banco) → **CP2** (superfície API do profile `default`) → **CP3** (túnel e ambiente local) → **CP4** (prova real).

CP1 e CP2 são **checkpoints externos**: nenhum deles foi executado nesta branch. Cada um precisa de autorização explícita do Tarcisio, e este documento descreve, para cada um, a operação exata, o alvo, o diff, o rollback e a evidência de que o Telegram não é afetado.

## Estado executado em 15/10/2026

- **CP1 feito.** A v20_01 (o ledger `volc_ops`, que não toca `public`/`app_auth`: fingerprint igual) e a v27_01 (sha `d8b03f4d…`) foram aplicadas pelo protocolo, com backups em `/root/backups/pre-*.dump`. Recibos e postflight estão em `provas/producao/`.
- **CP2 feito.** `api_default.py aplicar` rodou às 00:40Z com um único restart, todos os gates verdes e sem rollback. O recibo está em `provas/hermes-aplicar-recibo-20261016-004014.json`.
- **CP3 e CP4 feitos** no Mac: túnel :18642, FastAPI :8031, Express :3031, Vite :8091. O recibo está em `provas/PROVA-REAL-20261015.md`.

## Fatos de produção lidos antes da execução (somente leitura)

| Fato | Valor |
|---|---|
| Schema `agente_bia` no Supabase oficial | **não existe** |
| Ledger de migrations `volc_ops.migracao_evento` (v20_01) | **não existe** (v20_01 também é candidata) |
| Papel `postgres` | não superusuário, membro de `pg_read_all_data` |
| Postgres | 15.8 |
| Profiles Hermes | só `default` (gateway `hermes-gateway.service`, Telegram) |
| Listener do API Server (antes da CP2) | nenhum. 8642 livre; 127.0.0.1:9119 é o painel |

---

## CP0: prova local (feita nesta branch)

```bash
# backend hermético
cd backend && PYTHONPATH=..:.:tests python3 -m pytest tests/test_agente_bia.py -q
# banco descartável (sem rede, sem porta, nunca produção)
LAB_NOME=volc-freedom-lab-bia MIGRATION=supabase/migrations/v27_01_agente_bia.sql \
  ROLLBACK=supabase/migrations/v27_01_rollback.sql \
  MIGRATION_SUITE=tools/freedom-lab/db/suites/v27_bia.sh tools/freedom-lab/lab.sh recriar
# adaptador ↔ SQL real (com a v27_01 aplicada num container do lab)
BIA_LAB_CONTAINER=volc-freedom-lab-bia PYTHONPATH=..:.:tests python3 -m pytest tests/test_agente_bia_ledger_lab.py -q
# front
npx vitest run src/features/bia
VOLC_PROVA_DE_BUNDLE=1 npx vitest run src/features/bia/__tests__/bia-sem-hermes-no-bundle.test.ts
```

---

## CP1: aplicar a v27_01 no Supabase oficial (checkpoint externo)

- **Alvo:** `https://database.agenciavolc.com.br` (container `supabase-db` em 178.156.196.149).
- **Operação:** o protocolo da casa, que verifica o sha256, faz `pg_dump` antes, aplica numa transação e registra no ledger.
- **Pré-requisito:** o ledger v20_01 precisa existir, e hoje **não existe**. Há duas opções. **(a)** Aplicar a v20_01 antes, pelo mesmo protocolo, com `--cria-ledger`. É decisão própria, que atravessa a v20_02 (linha de base). **(b)** Aplicar a v27_01 à mão, como as anteriores, e registrar depois. A recomendação é (a), se a v20 já estiver aprovada; senão, (b) com recibo manual.
- **Diff:** só o arquivo, sha256 `d8b03f4d095bb3343821a9acd3953dd1a3f412f82cf0a5dfae465bfae143c51c`. Ele cria o schema `agente_bia`, 3 tabelas, 3 gatilhos, 4 funções internas e 11 RPCs `public.volc_agente_*`. Não altera nenhum objeto existente.
- **Impacto no Telegram:** nenhum. É outro servidor (Hetzner) e outro serviço.

```bash
# (a) com ledger
VOLC_AUTORIZA_PRODUCAO="v27_01_agente_bia@d8b03f4d095bb3343821a9acd3953dd1a3f412f82cf0a5dfae465bfae143c51c" \
scripts/migracao-protocolo.sh aplicar --alvo producao \
  --migration supabase/migrations/v27_01_agente_bia.sql \
  --sha d8b03f4d095bb3343821a9acd3953dd1a3f412f82cf0a5dfae465bfae143c51c \
  --rollback supabase/migrations/v27_01_rollback.sql \
  --sha-rollback 04560c174f4fb801298a1b01c1c5ef3dbefac9ebd893840c8dd13815b6e09719 \
  --aprovador Tarcisio

# (b) manual, depois de backup
cat supabase/migrations/v27_01_agente_bia.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 root@178.156.196.149 \
  "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

**Conferência depois de aplicar** (somente leitura):

```sql
select count(*) from pg_proc where proname like 'volc_agente_%';                 -- 11
select count(*) from information_schema.role_routine_grants
 where routine_name like 'volc_agente_%' and grantee in ('anon','authenticated','PUBLIC');  -- 0
```

Recarregue o schema do PostgREST (o protocolo faz isso; à mão: `NOTIFY pgrst, 'reload schema'`).

**Rollback:** ver `RUNBOOK-ROLLBACK-ROTACAO.md` §2. Com histórico gravado, ele recusa salvo declaração explícita.

**Prova já feita deste CP em laboratório:** o mesmo protocolo, contra `docker:volc-freedom-lab-bia` e como `postgres`, aplicou (rc 0), registrou no ledger, recusou o rollback com dado (rc 14), reverteu limpo (rc 0) e deixou o ledger com `revertida`.

---

## CP2: superfície API do profile `default` (a mesma Bia do Telegram)

Decisão do Tarcisio (15/10/2026): **não** se cria outro profile. O VOLC usa o profile `default`, com a mesma identidade, a mesma memória longa e o mesmo modelo, numa **sessão web separada** (`volc_<hex32>`, source `api_server`). Telegram e VOLC nunca escrevem na mesma sessão.

- **Alvo:** VPS `srv1546019` (alias SSH `hermes`), `/root/.hermes/config.yaml` e `/root/.hermes/.env`, unit `hermes-gateway`.
- **Script:** `deploy/hermes-default-api/api_default.py`, copiado para `/root/bia-volc/` e rodado com `/usr/local/lib/hermes-agent/venv/bin/python`.
- **Não muda:** token, toolsets e sessões do Telegram, memória, skills, SOUL, modelo, MCPs, outros `platform_toolsets`, a unit do systemd, Nginx/Traefik, DNS, firewall e Tailscale. **Nunca** `hermes gateway restart --system`.

**Diff** (inserção textual; o YAML inteiro é comparado e só a chave nova pode diferir):

```diff
# /root/.hermes/config.yaml
 platform_toolsets:
+  api_server: []        # medido: zero toolsets na v0.18.0; telegram continua hermes-telegram (17 toolsets)
   cli:
# /root/.hermes/.env
+# Bia VOLC (15/10/2026): API Server só em loopback, sem ferramentas
+API_SERVER_ENABLED=true
+API_SERVER_HOST=127.0.0.1
+API_SERVER_PORT=8642
+API_SERVER_KEY=<gerada no servidor, nunca impressa>
```

Por que `api_server: []` é **obrigatório**: sem essa chave, a superfície API herdaria 13 toolsets, entre eles `terminal`, `file`, `cronjob`, `browser` e `delegation` (medido no preflight).

**Sequência:**

```bash
ssh hermes 'install -d -m 700 /root/bia-volc'
scp deploy/hermes-default-api/api_default.py hermes:/root/bia-volc/
ssh hermes '/usr/local/lib/hermes-agent/venv/bin/python /root/bia-volc/api_default.py preflight'  # leitura
ssh hermes '/usr/local/lib/hermes-agent/venv/bin/python /root/bia-volc/api_default.py ensaio'     # cópias; rollback exato
ssh hermes 'setsid nohup /usr/local/lib/hermes-agent/venv/bin/python /root/bia-volc/api_default.py aplicar \
              > /root/bia-volc/aplicar.log 2>&1 < /dev/null &'                                     # sobrevive a queda do SSH
```

O modo `aplicar`:

1. **Recusa** se o gateway não estiver ativo com Telegram, se houver agente ativo, se a superfície já estiver configurada ou se a porta 8642 estiver ocupada.
2. Faz backup privado (`/root/.hermes/backups-bia/<ts>/`, 700) e registra os hashes antes e depois.
3. Edita, confere e roda `systemctl restart hermes-gateway`, o único restart.
4. Espera até 120 s pelos gates:
   - unit ativa com PID novo;
   - Telegram `connected`;
   - um único `gateway run`;
   - 8642 escutando **só** em `127.0.0.1`;
   - `/health` 200;
   - `/v1/toolsets` sem nenhum habilitado;
   - `/v1/models` sem chave → 401;
   - toolsets do Telegram iguais aos de antes;
   - zero MCP.
5. Com **qualquer** gate falho: restaura os dois arquivos, reinicia, espera o Telegram e registra no recibo.

O recibo fica em `/root/.hermes/backups-bia/<ts>/recibo.json`.

**Rollback manual:** `RUNBOOK-ROLLBACK-ROTACAO.md` §3.

---

## CP3: túnel e backend local (no Mac)

```bash
# 1. túnel só para o loopback (não abre porta na VPS nem fora do Mac)
ssh -N -L 127.0.0.1:18642:127.0.0.1:8642 hermes &

# 2. chave do default para o .env do backend, SEM passar pelo terminal/histórico:
ssh hermes "grep '^API_SERVER_KEY=' /root/.hermes/.env | cut -d= -f2-" \
  | { read -r k; printf 'BIA_HERMES_API_KEY=%s\n' "$k" >> backend/.env.local; }

# 3. demais variáveis (backend/.env.local; ver backend/.env.example)
BIA_ENABLED=1
BIA_HERMES_BASE_URL=http://127.0.0.1:18642
BIA_ALLOWED_ORIGINS=http://localhost:8080

# 4. front (.env.local)
VITE_BIA_ENABLED=true

# 5. subir (caminho canônico atual: abre/reutiliza o túnel, busca a chave
# server-side sem gravá-la e liga as duas flags)
./start-dev.sh --com-bia
```

Endurecimento recomendado, não aplicado: uma chave SSH dedicada ao túnel, com `permitopen="127.0.0.1:8642",no-pty,command="/bin/false"` em `authorized_keys`.

---

## CP4: prova real (inferência real, consome crédito)

Na UI: entre como ADMIN, abra **Bia** e siga o roteiro abaixo. Ou rode tudo de uma vez:

```bash
BIA_TOKEN=<access token da sua sessão ADMIN> BIA_ORIGEM=http://localhost:8080 \
BIA_CAMPANHA=<volc_campaign_id opcional> python3 scripts/bia_prova_real.py > recibo-bia-prova-real.json
```

| Passo | Esperado |
|---|---|
| "Responda apenas: conexão VOLC funcionando." | `succeeded`, texto igual |
| "o código desta conversa é AMBAR" → "qual é o código?" | AMBAR |
| reload | histórico intacto |
| nova conversa → "qual é o código?" | não sabe |
| id aleatório | 404 |
| `model` no corpo | 422 |
| `curl http://76.13.161.49:8642/v1/models` (de fora) | conexão recusada (nada escuta fora do loopback) |
| `/v1/toolsets` | nenhum habilitado (o portão também confere a cada envio) |
| read-back da sessão | nenhuma `tool_calls` |

Registre o modelo (`/v1/capabilities`), a duração (`_duracao_s` e o evento `concluida.duracao_ms`), o estado e os tokens (evento `concluida`). O custo em moeda **não** é informado pela rota de sessão: anote o do painel do provedor.
