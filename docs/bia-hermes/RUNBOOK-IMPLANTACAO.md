# Bia V1: runbook de implantação

Ordem obrigatória: **CP0** (local, já feito) → **CP1** (banco) → **CP2** (Hermes) → **CP3** (túnel e backend local) → **CP4** (prova real).

CP1 e CP2 são **checkpoints externos**: nenhum deles foi executado nesta branch. Cada um precisa de autorização explícita do Tarcisio, e este documento descreve, para cada um, a operação exata, o alvo, o diff, o rollback e a evidência de que o Telegram não é afetado.

## Fatos de produção lidos em 15/10/2026 (somente leitura)

| Fato | Valor |
|---|---|
| Schema `agente_bia` no Supabase oficial | **não existe** |
| Ledger de migrations `volc_ops.migracao_evento` (v20_01) | **não existe** (v20_01 também é candidata) |
| Papel `postgres` | não superusuário, membro de `pg_read_all_data` |
| Postgres | 15.8 |
| Profiles Hermes | só `default` (gateway `hermes-gateway.service`, Telegram) |
| Listener do API Server | nenhum. 8642 e 8643 estão livres; 127.0.0.1:9119 é o painel |

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

## CP2: profile `volcweb` no Hermes (checkpoint externo)

- **Alvo:** VPS `srv1546019` (alias SSH `hermes`), usuário root, `/root/.hermes/profiles/volcweb`. O profile default e `/root/.hermes/` **não são tocados**.
- **Não muda:** Nginx/Traefik, DNS, firewall, systemd do default e Tailscale. O API Server escuta só em 127.0.0.1:8643.

### 2.1 Antes (somente leitura): evidência do Telegram

```bash
ssh hermes 'systemctl is-active hermes-gateway; systemctl show -p MainPID --value hermes-gateway; hermes profile list'
```

Guarde o PID como `PID_DEFAULT_ANTES`.

### 2.2 Criar e configurar (escrita só em `/root/.hermes/profiles/volcweb`)

```bash
scp deploy/hermes-volcweb/configure_profile.py deploy/hermes-volcweb/smoke_hermes.py hermes:/root/bia-volcweb/
ssh -t hermes
  hermes profile create volcweb --no-skills --no-alias --description "Bia VOLC — consulta, sem ferramentas"
  hermes -p volcweb setup model           # interativo: provedor/modelo do profile (sem copiar do default)
  /usr/local/lib/hermes-agent/venv/bin/python /root/bia-volcweb/configure_profile.py
```

**Diff do profile** (`configure_profile.py` faz backup `.bak-bia-<ts>` antes):

```diff
# /root/.hermes/profiles/volcweb/.env
+API_SERVER_ENABLED=true
+API_SERVER_HOST=127.0.0.1
+API_SERVER_PORT=8643
+API_SERVER_KEY=<gerada, não impressa>
# /root/.hermes/profiles/volcweb/config.yaml
+platform_toolsets:
+  api_server: []          # medido: conjunto vazio na v0.18.0
+mcp_servers: {}
+gateway:
+  api_server:
+    max_concurrent_runs: 1
```

O script **recusa** se o `.env` do volcweb tiver `TELEGRAM_*`, `DISCORD_*`, `SLACK_*` ou `WHATSAPP_*`.

### 2.3 Primeiro em foreground, sem tocar no serviço do default

```bash
# sessão SSH 1
hermes -p volcweb gateway run
# sessão SSH 2
PID_DEFAULT_ANTES=<pid de 2.1> /usr/local/lib/hermes-agent/venv/bin/python /root/bia-volcweb/smoke_hermes.py
```

O smoke exige 8643 só em 127.0.0.1, auth obrigatória, `/v1/toolsets` sem nenhum habilitado, 401 sem chave e o `hermes-gateway` default ativo **com o mesmo PID**.

### 2.4 Persistir (depois do smoke verde)

```bash
hermes -p volcweb gateway install      # confira o NOME da unidade que ele mostra
hermes -p volcweb gateway start
hermes -p volcweb gateway status
PID_DEFAULT_ANTES=<pid> /usr/local/lib/hermes-agent/venv/bin/python /root/bia-volcweb/smoke_hermes.py
```

⚠️ O `hermes gateway status` do default avisa "Installed gateway service definition is outdated — Run: sudo hermes gateway restart --system". **Não rode isso nesta missão**: reiniciaria o Telegram.

**Rollback:** `RUNBOOK-ROLLBACK-ROTACAO.md` §3.

---

## CP3: túnel e backend local (no Mac)

```bash
# 1. túnel só para o loopback (não abre porta na VPS nem fora do Mac)
ssh -N -L 127.0.0.1:18643:127.0.0.1:8643 hermes &

# 2. chave do volcweb para o .env do backend, SEM passar pelo terminal/histórico:
ssh hermes "grep '^API_SERVER_KEY=' /root/.hermes/profiles/volcweb/.env | cut -d= -f2-" \
  | { read -r k; printf 'BIA_HERMES_API_KEY=%s\n' "$k" >> backend/.env.local; }

# 3. demais variáveis (backend/.env.local; ver backend/.env.example)
BIA_ENABLED=1
BIA_HERMES_BASE_URL=http://127.0.0.1:18643
BIA_ALLOWED_ORIGINS=http://localhost:8080

# 4. front (.env.local)
VITE_BIA_ENABLED=true

# 5. subir
./start-dev.sh
```

Endurecimento recomendado, não aplicado: uma chave SSH dedicada ao túnel, com `permitopen="127.0.0.1:8643",no-pty,command="/bin/false"` em `authorized_keys`.

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
| `curl http://76.13.161.49:8643/v1/models` (de fora) | conexão recusada (nada escuta fora do loopback) |
| `/v1/toolsets` | nenhum habilitado (o portão também confere a cada envio) |
| read-back da sessão | nenhuma `tool_calls` |

Registre o modelo (de `/v1/capabilities` no smoke), a duração (`_duracao_s` e o evento `concluida.duracao_ms`), o estado e os tokens (evento `concluida`). O custo em moeda **não** é informado pela rota de sessão: anote o do painel do provedor.
