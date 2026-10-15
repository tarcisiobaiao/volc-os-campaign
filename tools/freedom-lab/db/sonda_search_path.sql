-- =============================================================================
-- sonda_search_path.sql — pré-requisito da v20_02 (linha de base do ledger).
-- A âncora de fingerprint 695e913a… foi medida em produção pela sessão
-- `docker exec … psql -U postgres`, com o search_path efetivo do papel postgres.
-- A v20_02 recusa aplicar se o fingerprint recalculado não bater; se o
-- search_path de produção for outro, ela recusará sempre (seguro, mas inútil).
-- Esta sonda só LÊ: confirma o search_path efetivo e de onde ele vem.
-- NÃO executada nesta missão; rodar exige autorização explícita de leitura de
-- produção, pelo mesmo caminho da sonda_acesso.sql (SQL por stdin do psql).
-- Esperado (medido na imagem supabase/postgres:15.8.1.085): "$user", public, extensions
-- =============================================================================
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SELECT current_user, current_setting('search_path') AS search_path_efetivo;
SELECT r.rolname, coalesce(d.datname, '<todas>') AS banco, s.setconfig
  FROM pg_db_role_setting s
  JOIN pg_roles r ON r.oid = s.setrole
  LEFT JOIN pg_database d ON d.oid = s.setdatabase
 WHERE r.rolname = 'postgres' OR s.setrole = 0;
SELECT name, setting, source FROM pg_settings WHERE name = 'search_path';
ROLLBACK;
