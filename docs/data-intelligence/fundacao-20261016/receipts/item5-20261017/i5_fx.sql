\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT 'col' t, table_schema||'.'||table_name, column_name, data_type, column_default FROM information_schema.columns
 WHERE column_name ~* '(exchange|cambio|câmbio|cotacao|cotação|dollar|usd_brl|fx_rate)' AND table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 2,3;
SELECT 'fn' t, n.nspname||'.'||p.proname, pg_get_function_identity_arguments(p.oid), '' , '' FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE pg_get_functiondef(p.oid) ~* '(dollar_exchange_rate|exchange_rate|cotacao)' AND n.nspname NOT IN ('pg_catalog','information_schema') AND p.prokind='f' ORDER BY 2;
ROLLBACK;
