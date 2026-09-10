-- Referência de estilo: não altera arquivos, aprovações ou modos históricos.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $guard$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'migration requires database administrator';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_attribute
    WHERE attrelid = 'public.criativo_job'::regclass
      AND attname = 'modo_de_composicao' AND NOT attisdropped) THEN
    RAISE EXCEPTION 'v16_01 is required';
  END IF;
END $guard$;
ALTER TABLE public.criativo_job
  DROP CONSTRAINT IF EXISTS criativo_job_modo_composicao_valido;
ALTER TABLE public.criativo_job
  ADD CONSTRAINT criativo_job_modo_composicao_valido CHECK (
    modo_de_composicao IS NULL OR modo_de_composicao IN (
      'sem_foto', 'hibrido', 'reinterpretado', 'referencia_visual'
    )
  );
COMMENT ON COLUMN public.criativo_job.modo_de_composicao IS
  'sem_foto: geração sem anexo; hibrido: pixels preservados; reinterpretado: cena redesenhada; referencia_visual: inspiração de estilo sem colagem. O modo e o hash do anexo integram o plano autorizado.';
NOTIFY pgrst, 'reload schema';
COMMIT;
