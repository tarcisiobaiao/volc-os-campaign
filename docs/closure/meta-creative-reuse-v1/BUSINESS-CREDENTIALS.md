# Conexões Meta por Business Manager · 08/09/2026

Estado: P11-T03 partial. Aba `/settings/integrations?tab=meta-ads` implementada;
a página em branco foi corrigida importando `Settings`.

## Entrega

ADMIN autenticado cadastra/renova, seleciona explicitamente e desabilita conexões.
Token cifrado com Fernet antes do PostgREST, envelope vinculado a owner + Business.
Chave VOLC_SEGREDO_KEY existente preservada fora do banco. Nenhuma resposta inclui
token/ciphertext; erros de validação não ecoam input. Nada em URL/browser storage.
Cadastro confere /me contra /Business/system_users, com paginação limitada.
Resolver oficial atende leitura, validação, mídia e criação sem fallback silencioso.
META_BUSINESS_CREDENTIALS_ENABLED=true habilitado no backend/.env local ignorado.

## Banco oficial

Autoridade: https://database.agenciavolc.com.br.
Migration: supabase/migrations/20260908220817_meta_business_credentials.sql.
SHA256: 92c8c9e7311e38698167d077f75c22fe5f3b51d886a85a40fa86db8841b6384c.

Aplicada por SSH/psql ON_ERROR_STOP em transação. Duas tabelas:
meta_business_credentials e meta_business_selection. RLS + FORCE RLS; nenhum
privilégio para PUBLIC/anon/authenticated; service_role SELECT/INSERT/UPDATE.
FK composta impede selecionar conexão de outro owner. Prova local incluiu ACL
permissivo herdado. Prova oficial INSERT/SELECT/seleção/ROLLBACK sem resíduos.
PostgREST oficial consultado com sucesso pelo backend, sem coluna de segredo.

## Verificação

103 testes backend; testes frontend de página, token, seleção e erros sanitizados.
Build passou. TSC: 76 erros existentes fora dos arquivos alterados nesta tarefa.
Chrome com respostas fictícias: seis capturas 375/768/1440 claro/escuro, zero
erro JS/overflow e sequência de teclado. Não equivale a QA com token real.
Frontend 8080 HTTP 200; endpoint 8010 HTTP 401 sem sessão.

## Pendências explícitas

É acesso sob demanda, não sync contínuo. Always-on requer worker/agenda,
heartbeat e servidor disponível. Cadastro real e permissões dos ativos precisam
de conferência pelo operador; vínculo system user não prova ads_management.

Criação pausada ainda bloqueada: catálogo oficial confirmou ausência de
trafego_meta_ad_account e RPCs trafego_meta_create_approve,
trafego_meta_create_receipt, trafego_meta_create_approval_manifest.
Revisar cadeia de migrations do read model v15_01, executor 20260904183418,
recovery 20260907120000 e consistência 20260907210000 antes de aplicar.
Lista é ponto de partida, não manifesto pronto. Não executar db push global:
a pasta contém arquivos de rollback. Gates de política, conta, idempotência e
PAUSED preservados. Nenhuma criação, ativação, upload, n8n, push ou deploy.

Desconectar no VOLC impede novos usos; não revoga token na Meta nem cancela
requests em andamento. Guardar backup protegido da chave externa: trocá-la sem
recifrar torna registros ilegíveis. Rotas legadas continuam localhost/macOS.

Referência: SDK oficial Meta Business.get_system_users:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/business.py.
