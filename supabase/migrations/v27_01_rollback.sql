-- =============================================================================
-- v27_01_rollback — remove o schema da Bia (agente_bia) e as 11 RPCs.
--
-- ⚠️ Histórico de conversa é dado de pessoas. Com linhas no schema, o rollback
-- RECUSA (atômico, nada removido), a menos que o operador declare na MESMA
-- sessão, antes do script:   SET agente_bia.descartar_historico = 'sim';
-- Antes de descartar: exporte o que precisar reconciliar (execuções uncertain).
--
-- Idempotente: sem o schema, não faz nada e termina com sucesso.
-- Não toca em nada fora de `agente_bia` e das funções `public.volc_agente_*`.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $rb$
DECLARE
  linhas bigint;
BEGIN
  IF to_regnamespace('agente_bia') IS NULL THEN
    RAISE NOTICE 'v27_01_rollback: agente_bia não existe; nada a desfazer';
    RETURN;
  END IF;
  SELECT (SELECT count(*) FROM agente_bia.conversa) + (SELECT count(*) FROM agente_bia.execucao)
    INTO linhas;
  IF linhas > 0 AND coalesce(current_setting('agente_bia.descartar_historico', true), '') <> 'sim' THEN
    RAISE EXCEPTION 'v27_01_rollback: agente_bia tem % linha(s); declare agente_bia.descartar_historico=sim para descartar', linhas
      USING ERRCODE = '55000';
  END IF;
END
$rb$;

DROP FUNCTION IF EXISTS public.volc_agente_criar_conversa(uuid, text, text);
DROP FUNCTION IF EXISTS public.volc_agente_listar_conversas(uuid, integer);
DROP FUNCTION IF EXISTS public.volc_agente_historico(uuid, uuid);
DROP FUNCTION IF EXISTS public.volc_agente_execucao(uuid, uuid);
DROP FUNCTION IF EXISTS public.volc_agente_reservar(uuid, uuid, uuid, text, text, integer, jsonb);
DROP FUNCTION IF EXISTS public.volc_agente_iniciar(uuid, uuid);
DROP FUNCTION IF EXISTS public.volc_agente_concluir(uuid, uuid, text, text, text, jsonb);
DROP FUNCTION IF EXISTS public.volc_agente_expirar(uuid, integer);
DROP FUNCTION IF EXISTS public.volc_agente_para_reconciliar(uuid, uuid);
DROP FUNCTION IF EXISTS public.volc_agente_reconciliar(uuid, uuid, text, text, jsonb);
DROP FUNCTION IF EXISTS public.volc_agente_registrar_evento(uuid, uuid, text, jsonb);
DROP SCHEMA IF EXISTS agente_bia CASCADE;

COMMIT;
