# Bia V1: rollback e rotação

Cada camada desliga sozinha, da mais barata para a mais cara. Pare na primeira que resolver.

## 1. Desligar a superfície (segundos, sem perda)

- Front: `VITE_BIA_ENABLED=false` (ou remova a linha) e reinicie o Vite ou faça o deploy. O Layout deixa de importar a Bia.
- Backend: `BIA_ENABLED=` (vazio) e reinicie o uvicorn. Todas as rotas `/api/agent/*` respondem 404 antes do auth.
- Hermes: feche o túnel (`kill` do `ssh -N -L …`). Os envios passam a `failed: hermes_indisponivel` antes de sair, e o histórico continua legível.

**Depois da prova real, o rollback operacional é este, nesta ordem:** desligar a flag, interromper novas chamadas, preservar os recibos e reconciliar `queued`/`running`/`uncertain`. Só então se decide sobre remover o schema. O histórico da prova **não** é apagado para facilitar rollback.

## 2. Reverter a migration v27_01

Antes de tudo, exporte o que estiver `uncertain` e precisar de reconciliação:

```sql
select e.id, e.criada_em, e.erro_codigo from agente_bia.execucao e where e.estado = 'uncertain';
```

Com o protocolo (o ledger registra `revertida`):

```bash
scripts/migracao-protocolo.sh reverter --alvo producao --versao v27_01_agente_bia \
  --rollback supabase/migrations/v27_01_rollback.sql \
  --sha-rollback 04560c174f4fb801298a1b01c1c5ef3dbefac9ebd893840c8dd13815b6e09719 --aprovador Tarcisio
```

- **Com linhas no schema, o rollback RECUSA** (rc 14, transação desfeita). Para descartar o histórico de propósito, rode à mão, na mesma sessão: `SET agente_bia.descartar_historico = 'sim';` seguido do arquivo de rollback.
- O rollback é idempotente: sem o schema, não faz nada.
- Ele só remove `agente_bia` e `public.volc_agente_*`. Fingerprint provado no lab: volta ao anterior, e reaplicar dá o mesmo.

## 3. Desligar a superfície API do profile `default` (VPS)

O `aplicar` já faz isso sozinho quando algum gate falha. À mão, a partir do backup do próprio `aplicar`:

```bash
ssh hermes '/usr/local/lib/hermes-agent/venv/bin/python /root/bia-volc/api_default.py reverter /root/.hermes/backups-bia/<ts>'
```

O script restaura `config.yaml` e `.env` byte a byte (hash igual ao de antes), roda `systemctl restart hermes-gateway` e espera o Telegram voltar a `connected`. Nunca use `hermes gateway restart --system`.

**Antes de reverter, reconcilie as incertas** (o read-back precisa da API no ar). Sessões web antigas continuam no `state.db` do profile, com `source=api_server`; elas não são apagadas.

## 4. Rotação da `API_SERVER_KEY` do profile `default`

Faça quando houver suspeita de vazamento, saída de quem tinha acesso ao Mac ou a cada 90 dias. A chave dá acesso administrativo ao API Server do `default` (sessões, jobs), mesmo só em loopback.

1. Na VPS: faça backup do `.env` e troque só a linha, sem imprimir.
   ```bash
   cp -p /root/.hermes/.env /root/.hermes/backups-bia/env.antes-rotacao-$(date +%s)
   python3 - <<'PY'
   import secrets, pathlib
   p = pathlib.Path('/root/.hermes/.env')
   l = [x for x in p.read_text().splitlines() if not x.startswith('API_SERVER_KEY=')]
   p.write_text('\n'.join(l + ['API_SERVER_KEY=' + secrets.token_urlsafe(48)]) + '\n')
   PY
   ```
2. Rode `systemctl restart hermes-gateway`, que reinicia o Telegram por alguns segundos. Depois rode `api_default.py verificar`.
3. No Mac: atualize `BIA_HERMES_API_KEY` pelo pipe do runbook de implantação (CP3, passo 2) e reinicie o backend.
4. Confira que a chave antiga dá 401.

Entre os passos 2 e 3 os envios falham com `hermes_autenticacao` (failed; nada sai e nada fica incerto).

## 5. Retenção

Expurgo manual ou cron do operador, como dono do schema:

```sql
select agente_bia.expurgar(180);   -- mínimo 30; nunca apaga conversa com execução em voo ou incerta
```

Apagar um usuário do auth apaga as conversas dele (`ON DELETE CASCADE`).
