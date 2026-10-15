# Bia V1: rollback e rotação

Cada camada desliga sozinha, da mais barata para a mais cara. Pare na primeira que resolver.

## 1. Desligar a superfície (segundos, sem perda)

- Front: `VITE_BIA_ENABLED=false` (ou remova a linha) e reinicie o Vite ou faça o deploy. O Layout deixa de importar a Bia.
- Backend: `BIA_ENABLED=` (vazio) e reinicie o uvicorn. Todas as rotas `/api/agent/*` respondem 404 antes do auth.
- Hermes: feche o túnel (`kill` do `ssh -N -L …`). Os envios passam a `failed: hermes_indisponivel` antes de sair, e o histórico continua legível.

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

## 3. Desfazer o profile `volcweb` (VPS)

```bash
hermes -p volcweb gateway stop
hermes -p volcweb gateway uninstall          # se foi instalado como serviço
# opcional, só depois de reconciliar incertas (o read-back usa a sessão):
hermes profile delete volcweb
```

**Nunca** `hermes gateway stop/restart` sem `-p volcweb`: isso derruba o Telegram do default. Confira depois:

```bash
systemctl is-active hermes-gateway
systemctl show -p MainPID --value hermes-gateway
```

O PID tem de ser o mesmo de antes.

Para voltar a configuração do volcweb sem apagar: copie `config.yaml.bak-bia-<ts>` e `.env.bak-bia-<ts>` de volta.

## 4. Rotação da `API_SERVER_KEY` do volcweb

Faça quando houver suspeita de vazamento, saída de quem tinha acesso ao Mac ou a cada 90 dias.

1. Na VPS: gere uma chave nova sem imprimir e troque a linha no `.env` do volcweb.
   ```bash
   python3 - <<'PY'
   import secrets, pathlib
   p = pathlib.Path('/root/.hermes/profiles/volcweb/.env')
   l = [x for x in p.read_text().splitlines() if not x.startswith('API_SERVER_KEY=')]
   p.write_text('\n'.join(l + ['API_SERVER_KEY=' + secrets.token_urlsafe(48)]) + '\n')
   PY
   ```
2. `hermes -p volcweb gateway restart`. Só o volcweb.
3. No Mac: atualize `BIA_HERMES_API_KEY` pelo mesmo pipe do runbook de implantação (CP3, passo 2), sem passar pelo terminal, e reinicie o backend.
4. Valide com `smoke_hermes.py` e com um envio pela UI. A chave antiga tem de dar 401.

Entre os passos 2 e 3 os envios falham com `hermes_autenticacao` (failed, nada sai). Nada fica incerto.

## 5. Retenção

Expurgo manual ou cron do operador, como dono do schema:

```sql
select agente_bia.expurgar(180);   -- mínimo 30; nunca apaga conversa com execução em voo ou incerta
```

Apagar um usuário do auth apaga as conversas dele (`ON DELETE CASCADE`).
