-- 05 · A VERTICAL DE POLÍTICA PRECISA SOBREVIVER AO REFRESH
--
-- ## O defeito que esta migração conserta
--
-- A vertical (`informativo`, `governo_documentos`, `financeiro`, …) é o eixo do
-- portão de habilitação do `volc_ads/policy/spec.py`: ela decide se a campanha
-- exige certificação antes de subir. Quem responde por ela é o OPERADOR, no
-- portão de política do cockpit — é uma afirmação sobre o negócio, não uma
-- inferência que o sistema possa fazer sozinho.
--
-- Só que ela vivia num `useState` do React. Sobrevivia a cliques e morria num
-- F5.
--
-- Medido no card 65 em 19/08/2026: o operador escolheu `informativo`, a página
-- recarregou, a escolha voltou para o inferido `governo_documentos`, e a prova
-- reprovou com "Exige certificacao_servicos_oficiais (política 15332527)". Ele
-- não tinha como saber por quê — a tela ainda mostrava "0 achados" naquele
-- momento. Duas horas de ida e volta por um estado que não persistia.
--
-- ## Por que aqui, e não em tabela nova
--
-- O grão certo é a TENTATIVA DE CAMPANHA: uma vertical por (oportunidade, run),
-- que é exatamente a chave de `pautador_trafego_copy`. E a copy JÁ é escrita
-- contra uma vertical — `escrever(..., vertical=...)` —, então guardá-la ao lado
-- do texto que ela regeu mantém as duas coerentes por construção.
--
-- Tabela própria só se justificaria com histórico de decisão e certificações
-- com validade. Nada disso existe hoje; criá-la agora seria estrutura à espera
-- de um requisito.
--
-- ## Segurança
--
-- `IF NOT EXISTS` nas duas colunas: reaplicar é no-op, não erro. Nenhum dado
-- existente é tocado — as duas nascem nulas, e nulo aqui significa "o operador
-- ainda não declarou", que é diferente de qualquer vertical concreta.
--
-- Aplicar:
--   cat src/sql/volc-sync/05_vertical_persistida.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
--     root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"

BEGIN;

ALTER TABLE public.pautador_trafego_copy
  ADD COLUMN IF NOT EXISTS vertical text,
  ADD COLUMN IF NOT EXISTS certificacoes jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.pautador_trafego_copy.vertical IS
  'Eixo do portão de habilitação (país × vertical) de volc_ads/policy/spec.py. '
  'Declarado pelo OPERADOR no portão de política do cockpit — é afirmação sobre '
  'o negócio, não inferência. NULO = ainda não declarado, e aí vale o inferido '
  'da entidade. Vivia num useState e morria no F5: ver o card 65 em 19/08/2026.';

COMMENT ON COLUMN public.pautador_trafego_copy.certificacoes IS
  'Certificações que o operador declara POSSUIR para esta vertical. Lista de '
  'strings. ⚠️ Declarar uma que não se tem não engana o Google — só troca '
  '"barrado antes de subir" por "reprovado depois de veicular", com a conta '
  'marcada. Por isso o padrão é vazio e o preenchimento é ato deliberado.';

COMMIT;
