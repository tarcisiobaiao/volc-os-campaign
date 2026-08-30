-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 11 / Nichos & sazonalidade (ADITIVO, idempotente)
--
-- Nova dimensão de descoberta: nichos selecionáveis (Benefícios, Gov, Educação,
-- Emprego, Finanças, Apps) + tag niche_slug na entidade para persistência.
-- Permite descoberta focada, sem perder a backward-compatibilidade (niches=[]).
--
-- NÃO destrutivo. >>> Rodar no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. pautador_niches — catálogo de nichos selecionáveis (R1)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pautador_niches (
  id                bigserial primary key,
  slug              text not null unique,
  label             text not null,
  guidance          text not null default '',
  allowed_verticals text[] not null default '{}',
  is_active         boolean not null default true,
  sort_order        int not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

CREATE INDEX IF NOT EXISTS idx_pautador_niches_active
    ON public.pautador_niches (is_active);
CREATE INDEX IF NOT EXISTS idx_pautador_niches_sort
    ON public.pautador_niches (sort_order);

DROP TRIGGER IF EXISTS trg_pautador_niches_updated_at ON public.pautador_niches;
CREATE TRIGGER trg_pautador_niches_updated_at
    BEFORE UPDATE ON public.pautador_niches
    FOR EACH ROW EXECUTE FUNCTION public.set_pautador_updated_at();

COMMENT ON TABLE public.pautador_niches IS
    'Pautador Pro — nichos selecionáveis (Benefícios, Gov, Educação, Emprego, Finanças, Apps). Semente-guia da descoberta com foco.';

-- =====================================================================
-- 2. Coluna niche_slug em pautador_entities (R1)
-- =====================================================================
ALTER TABLE public.pautador_entities
  ADD COLUMN IF NOT EXISTS niche_slug text;

COMMENT ON COLUMN public.pautador_entities.niche_slug IS
    'Slug do nicho da entidade (ex: financas, beneficios_sociais). Preenchido pela descoberta quando niches filtrados.';

-- =====================================================================
-- 3. Seed dos 6 nichos (idempotente: on conflict do nothing)
-- =====================================================================
INSERT INTO public.pautador_niches (slug,label,guidance,allowed_verticals,sort_order) VALUES
 ('beneficios_sociais','Benefícios sociais','Programas de transferência de renda, auxílios, bolsas, pensões e amparo social — foco em quem recebe/solicita. NÃO incluir tributos, documentos ou serviços administrativos genéricos.', array['gov_beneficios'],10),
 ('servicos_governo','Serviços do governo','Órgãos, sistemas, documentos, obrigações e serviços públicos (emissão, consulta, agendamento, cadastros). NÃO confundir com benefícios de renda.', array['gov_beneficios'],20),
 ('educacao','Educação','Matrículas, bolsas, financiamento estudantil, vestibulares, cursos e certificações.', array['educacao'],30),
 ('emprego','Emprego','Carreira, trabalho, vagas, trabalho por/em aplicativos, direitos trabalhistas, concursos e qualificação.', array['empregos_concursos'],40),
 ('financas','Finanças','Crédito, empréstimo, financiamento, investimentos, seguros, impostos e apps financeiros.', array['financas','credito','seguros'],50),
 ('aplicativos','Aplicativos','Apps de alto uso e dúvidas utilitárias (como funciona, cadastro, recuperar acesso, tarifas), com ângulo informacional de publisher.', array['tecnologia'],60)
on conflict (slug) do nothing;

-- =====================================================================
-- 4. RLS — admin-by-email (igual v7_01/v7_03). service_role faz BYPASS.
-- =====================================================================
ALTER TABLE public.pautador_niches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pautador_niches admin all" ON public.pautador_niches;
DROP POLICY IF EXISTS "pautador_niches read auth" ON public.pautador_niches;
CREATE POLICY "pautador_niches admin all"
    ON public.pautador_niches FOR ALL TO authenticated
    USING      (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'))
    WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email') AND u.role = 'ADMIN'));
CREATE POLICY "pautador_niches read auth"
    ON public.pautador_niches FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM public.users u WHERE lower(u.email) = lower(auth.jwt() ->> 'email')));

-- =====================================================================
-- Verificação (opcional)
-- SELECT tablename FROM pg_tables WHERE tablename = 'pautador_niches';
-- SELECT * FROM public.pautador_niches ORDER BY sort_order;
-- =====================================================================
