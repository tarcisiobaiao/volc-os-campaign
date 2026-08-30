-- v7_17 · ESCOLHA DE PERGUNTA no arraste DESCOBERTAS -> EM VALIDAÇÃO
--
-- ## Por que AQUI, e não em DESCOBERTAS
--
-- Já tentamos avaliar a ENTIDADE em descobertas, e falhou por um motivo que não
-- é de implementação: a entidade não tem UMA pergunta, tem várias, todas
-- legítimas. "CDB" carrega uma comparativa, uma condicional e uma de dado
-- único. Perguntar "qual é o engajamento do CDB" é perguntar a altura de uma
-- família. Medido: 33,3% de estabilidade entre rodadas contra 23,5% de acaso
-- (p = 0,43) — ausência de evidência de sinal. Ver app/entities/leitura.py.
--
-- Em EM VALIDAÇÃO o objeto muda: a entidade já foi escolhida, e o que falta
-- decidir é QUAL PERGUNTA ATACAR. Essa é uma unidade bem definida — a mesma do
-- gerador de funil, onde cada página de solução responde uma pergunta.
--
-- ## O que esta tabela NÃO tem, e por quê
--
-- Nenhuma nota, nenhum ranking, nenhum score. Não existe desfecho medido contra
-- o qual validar uma nota, e nota sem desfecho é opinião com casas decimais —
-- cujo custo não é estar errada, é PARECER MEDIDA. Três revisões externas
-- independentes chegaram nisso por caminhos diferentes.
--
-- ## O que ela cria
--
-- O histórico que a base nunca teve. Toda pergunta que este sistema já viu foi
-- uma que alguém escolheu; as descartadas nunca existiram em lugar nenhum, e
-- sem o contrafactual não há o que perguntar a dado nenhum depois.

CREATE TABLE IF NOT EXISTS public.pautador_question_choices (
    id              bigserial   PRIMARY KEY,
    opportunity_id  bigint      NOT NULL REFERENCES public.pautador_entity_opportunities(id) ON DELETE CASCADE,
    entity_id       bigint      REFERENCES public.pautador_entities(id) ON DELETE SET NULL,
    country_code    text        NOT NULL,

    -- A ESCOLHA. `chosen_index` NULL + `custom_frase` preenchido = o operador
    -- recusou as três e escreveu a dele. É o registro mais valioso da tabela:
    -- marca onde o gerador não viu a pergunta que importa — falha que nenhum
    -- teste de estabilidade detecta, porque as três geradas podem ser
    -- internamente consistentes e todas erradas.
    chosen_index       smallint,
    chosen_frase       text,
    chosen_engajamento text,
    chosen_ignorancia  text,
    custom_frase       text,
    custom_engajamento text,
    custom_ignorancia  text,

    -- As DESCARTADAS, íntegras.
    rejected        jsonb       NOT NULL DEFAULT '[]'::jsonb,

    outcome         text        NOT NULL DEFAULT 'chosen'
                    CHECK (outcome IN ('chosen','custom','skipped','entity_rejected')),
    notes           text,

    chosen_by       uuid        REFERENCES public.users(id) ON DELETE SET NULL,
    chosen_at       timestamptz NOT NULL DEFAULT now()
);

-- SEM UNIQUE em opportunity_id, de propósito: o operador pode revisitar e
-- escolher de novo, e a segunda escolha é INFORMAÇÃO. Nunca sobrescreva a
-- primeira; leia sempre a mais recente por `chosen_at`.
CREATE INDEX IF NOT EXISTS idx_question_choices_opp
    ON public.pautador_question_choices (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_question_choices_data
    ON public.pautador_question_choices (chosen_at DESC);

COMMENT ON TABLE public.pautador_question_choices IS
'Registro da escolha de PERGUNTA no arraste DESCOBERTAS -> EM VALIDAÇÃO. Não
contém nota nem ranking: existe para criar o histórico que nunca existiu — quais
perguntas foram descartadas, e por quem. Não derivar score desta tabela sem
desfecho medido (receita/custo por pergunta x página x período).';

COMMENT ON COLUMN public.pautador_question_choices.rejected IS
'As perguntas candidatas NÃO escolhidas, íntegras. O contrafactual: toda pergunta que o sistema já viu foi uma que alguém escolheu.';
COMMENT ON COLUMN public.pautador_question_choices.custom_frase IS
'O operador recusou as três e escreveu a dele. Sinal de que o gerador não enxergou a pergunta que importa. Acima de ~30% num mês, o prompt de descoberta precisa de trabalho — e aí há evidência do que consertar: as perguntas reais ao lado das geradas.';
COMMENT ON COLUMN public.pautador_question_choices.outcome IS
'chosen | custom | skipped | entity_rejected. `skipped` é DADO, não ausência de dado: saber que o operador pulou informa. Nenhum dos quatro impede o card de mover.';

CREATE OR REPLACE VIEW public.vw_question_choice_ledger AS
SELECT
  c.chosen_at::date            AS dia,
  c.country_code,
  e.canonical_name             AS entidade,
  c.outcome,
  COALESCE(c.chosen_frase, c.custom_frase)             AS pergunta,
  COALESCE(c.chosen_engajamento, c.custom_engajamento) AS engajamento,
  COALESCE(c.chosen_ignorancia,  c.custom_ignorancia)  AS ignorancia,
  jsonb_array_length(c.rejected)                       AS n_descartadas,
  (c.custom_frase IS NOT NULL)                         AS o_humano_reescreveu,
  o.gold_tier, o.score
FROM public.pautador_question_choices c
LEFT JOIN public.pautador_entity_opportunities o ON o.id = c.opportunity_id
LEFT JOIN public.pautador_entities e ON e.id = c.entity_id
ORDER BY c.chosen_at DESC;

COMMENT ON VIEW public.vw_question_choice_ledger IS
'Leitura do ledger de escolhas. `o_humano_reescreveu` é coluna de primeira classe: é onde o gerador erra.';
