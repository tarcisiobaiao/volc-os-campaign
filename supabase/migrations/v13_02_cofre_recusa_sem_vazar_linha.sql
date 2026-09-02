-- =============================================================================
-- v13_02 — a recusa por campo obrigatorio para de anexar a LINHA INTEIRA
-- =============================================================================
--
-- O DEFEITO, MEDIDO EM 01/09/2026 NO SUPABASE OFICIAL, DEPOIS DA v13_01
--
-- `cofre_referenciar_credencial` valida a FORMA do localizador antes do INSERT,
-- exatamente para nao deixar a CHECK falar. O comentario da propria v13_01 diz
-- por que (linhas 1888-1895): a violacao de CHECK anexa
--
--     DETAIL:  Failing row contains (…)
--
-- com a linha inteira, e a linha inteira inclui o valor recusado.
--
-- Mas essa guarda cobre UM caminho. Os demais campos obrigatorios da tabela nao
-- sao conferidos antes do INSERT, e a coluna `localizador` ja esta na linha
-- quando a NOT NULL dispara. Uma ficha sem `owner_nome` — o campo que o
-- PEDIDO-AO-OPERADOR marca como obrigatorio e que um operador esquece — produz:
--
--     ERROR:  null value in column "owner_nome" … violates not-null constraint
--     DETAIL:  Failing row contains (1, asset:…, 1password, …, op://…/…/…, …)
--
-- O endereco `op://` vai junto. Reproduzido nesta base, transacionalmente, com
-- um localizador sintetico.
--
-- ALCANCE HONESTO: `backend/app/asset_vault/infraestrutura.py:94` ja descarta
-- qualquer mensagem do banco que contenha `Failing row contains`, `DETAIL:` ou
-- `op://`. Pela API, portanto, isto NAO chega ao browser. O que sobra — e que a
-- peneira em Python nao alcanca — e o LOG DO SERVIDOR Postgres, e qualquer
-- consumidor futuro que fale com o banco sem passar por aquele adapter. O ADR
-- proibe o localizador em log; e esta missao esta prestes a fazer passar por
-- aqui uma referencia REAL. Por isso a correcao vem ANTES do dado real.
--
-- A FORMA DA CORRECAO
--
-- Nao editamos a v13_01: ela ja esta aplicada, e migration aplicada nao se
-- reescreve. Tambem nao reescrevemos a funcao inteira — copiar 80 linhas para
-- mudar 6 e convite a divergencia silenciosa.
--
-- Um gatilho BEFORE INSERT/UPDATE roda ANTES da checagem de NOT NULL e cobre
-- TODO caminho de escrita, nao so a funcao governada de hoje. Ele nomeia o
-- campo que falta e nunca repete valor nenhum.
-- =============================================================================

DO $guarda$
BEGIN
  IF current_user <> 'postgres' THEN
    RAISE EXCEPTION 'v13_02 exige papel postgres (atual=%)', current_user;
  END IF;
  IF to_regclass('public.cofre_credencial_referencia') IS NULL THEN
    RAISE EXCEPTION 'v13_02 exige a v13_01 aplicada: cofre_credencial_referencia nao existe';
  END IF;
  RAISE NOTICE 'v13_02: guardas ok (papel=%, versao=%)',
    current_user, current_setting('server_version');
END
$guarda$;


CREATE OR REPLACE FUNCTION public.cofre_credencial_campos_obrigatorios()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $funcao$
DECLARE
  faltando text[] := ARRAY[]::text[];
BEGIN
  -- A ordem e a do PEDIDO-AO-OPERADOR, para que a mensagem case com o
  -- formulario que a pessoa preencheu.
  IF NOT public.cofre_texto_util(NEW.ativo_id)     THEN faltando := faltando || 'ativo_id'::text;     END IF;
  IF NOT public.cofre_texto_util(NEW.provider)     THEN faltando := faltando || 'provider'::text;     END IF;
  IF NOT public.cofre_texto_util(NEW.nome_logico)  THEN faltando := faltando || 'nome_logico'::text;  END IF;
  IF NOT public.cofre_texto_util(NEW.localizador)  THEN faltando := faltando || 'localizador'::text;  END IF;
  IF NOT public.cofre_texto_util(NEW.finalidade)   THEN faltando := faltando || 'finalidade'::text;   END IF;
  IF NOT public.cofre_texto_util(NEW.owner_nome)   THEN faltando := faltando || 'owner_nome'::text;   END IF;
  IF NOT public.cofre_texto_util(NEW.estado)       THEN faltando := faltando || 'estado'::text;       END IF;

  IF array_length(faltando, 1) IS NOT NULL THEN
    -- ⚠️ A mensagem cita NOMES DE CAMPO e nada mais. Nenhum valor da linha entra
    -- aqui — e o ponto inteiro desta migration e que a linha nao seja repetida.
    RAISE EXCEPTION
      'referencia de credencial incompleta: falta %. Nenhum valor recebido e repetido aqui, de proposito.',
      array_to_string(faltando, ', ')
      USING ERRCODE = 'not_null_violation';
  END IF;

  RETURN NEW;
END
$funcao$;

COMMENT ON FUNCTION public.cofre_credencial_campos_obrigatorios() IS
  'Recusa referencia de credencial incompleta citando o NOME do campo. Existe para que a NOT NULL nao dispare e anexe DETAIL com a linha inteira, que carrega o localizador.';

DROP TRIGGER IF EXISTS cofre_credencial_obrigatorios ON public.cofre_credencial_referencia;
CREATE TRIGGER cofre_credencial_obrigatorios
  BEFORE INSERT OR UPDATE ON public.cofre_credencial_referencia
  FOR EACH ROW EXECUTE FUNCTION public.cofre_credencial_campos_obrigatorios();


DO $confere$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM pg_trigger t
   JOIN pg_class c ON c.oid = t.tgrelid
   WHERE c.relname = 'cofre_credencial_referencia'
     AND t.tgname = 'cofre_credencial_obrigatorios'
     AND NOT t.tgisinternal;
  IF n <> 1 THEN RAISE EXCEPTION 'v13_02 falhou: gatilho nao instalado'; END IF;
  RAISE NOTICE 'v13_02 OK: gatilho instalado; a recusa por campo obrigatorio nao anexa mais a linha';
END
$confere$;
