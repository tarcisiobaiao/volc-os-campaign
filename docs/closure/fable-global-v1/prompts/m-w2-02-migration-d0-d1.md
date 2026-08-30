# Prompt — M-W2-02 · Migration do fato canônico D0/D-1 (Codex, sessão interativa)

> Interativa porque `supabase/migrations/` é caminho protegido no harness.
> Trabalhe em branch própria (`feat/gads-fato-canonico-v13`); merge é do
> integrador. NADA é aplicado em produção nesta missão.

```text
Missão: escrever a migração do fato canônico Google Ads campanha-dia,
exatamente como o contrato já especifica — o desenho está pronto, não o
redesenhe. AUTORIDADE: docs/architecture/GADS-REPORT-D0-D1-E-CONTRATO-DE-DADOS.md
(seções 'migration proposta' e 'critérios de aceite'); estilo e disciplina:
supabase/migrations/v12_01_google_inteligencia_coletas.sql e o README do
diretório (ledger com preflight/backup/rollback).

Entregas:
1. supabase/migrations/v13_01_gads_fato_canonico.sql criando:
   - trafego_coleta_execucao (ledger de execução por coletor/janela, append-only);
   - google_ads_campanha_dia (fato com chave única customer_id+campaign_id+
     metric_date+segments_hash; métricas anuláveis — NULL=não medido ≠ 0;
     dinheiro em micros com moeda; lido_em; origem/backfill declarados);
   - RPC atômico e idempotente de gravação (SECURITY DEFINER, mesmo padrão
     do volc_registrar_google_inteligencia);
   - projeção de compatibilidade que preserva os consumidores atuais de
     daily_campaign_metrics (view, sem duplicar escrita);
   - RLS forçada, zero grant anon/authenticated.
2. supabase/migrations/v13_01_rollback.sql — reversão completa par a par.
3. Prova em Postgres descartável (docker run postgres:16): ciclo
   aplicar→popular com fixture→provar semântica NULL≠0→reverter→reaplicar.
   Grave o script de prova em supabase/migrations/provas/v13_01_prova.sh +
   .sql e a SAÍDA em comentário do README (como as séries anteriores fazem).
4. Atualize supabase/migrations/README.md: nova seção v13_01 com estado
   'ESCRITA E PROVADA EM DESCARTÁVEL — NÃO APLICADA', hash sha256 dos
   arquivos, e o portão que falta (decisão D3 + autorização de banco).
5. Teste Python: backend/tests/test_gads_fato_contrato.py validando o
   contrato do RPC contra o descartável se disponível, senão marcado
   skipif com motivo explícito (ausência de banco ≠ prova).

Proibições: ZERO conexão com database.agenciavolc.com.br; zero alteração nos
workflows n8n; zero mudança em daily_campaign_metrics; não tocar o
adaptador scripts/adaptar_gads_reports_n8n.py.

Gates locais antes do handoff: bash supabase/migrations/provas/v13_01_prova.sh
(verde no descartável); backend/.venv/bin/python -m pytest backend/tests -q
(sem regressão); git diff --check.

Handoff: SHAs, saída da prova (ciclo completo), hashes dos SQL, e o texto
exato da linha proposta para o ROADMAP (P06-T08: evidência nova, status
permanece partial até aplicar e reconciliar canário D0/D-1).
```
