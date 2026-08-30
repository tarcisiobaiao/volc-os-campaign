-- v7_16 · AS TRÊS FRASES (portão de leitura, continuação da v7_15)
--
-- Por que três. Com UMA frase por entidade, o rótulo não é propriedade do tema:
-- duas rodadas idênticas (mesmo prompt, mesmo país, mesmo nicho, dry) sobre as 6
-- entidades que caíram nas duas deram
--
--     engajamento igual em 2 de 6      (acaso, com 5 valores, seria 20%)
--     opacidade   igual em 2 de 6
--     e os dois portões dispararam em entidades DIFERENTES
--
-- A causa não está no mapeamento frase->rótulo (esse foi apertado por quatro
-- rodadas e segurou: a classe de erro "quem age é a instituição" morreu). Está
-- em entidade->frase: a mesma entidade tem muitas perguntas possíveis e o modelo
-- sorteia uma. Prova do par medido:
--
--     LCI e LCA      dor quase igual nas duas  ->  rótulo IGUAL nos dois eixos
--     Previdência    dor quase igual nas duas  ->  rótulo DIFERENTE
--       "Quem declara pelo completo deve optar pelo PGBL"   -> condicional
--       "Escolha o PGBL se você faz a declaração completa"  -> comparativo
--
-- Mesmo conteúdo, redação diferente, rótulo diferente. Mais ajuste de prompt não
-- alcança isso. Então o agente passa a escrever TRÊS perguntas plausíveis por
-- entidade, cada uma com o seu rótulo, e o rótulo da oportunidade vira a MODA.
-- Custo: zero chamada nova — as três saem no mesmo JSON.
--
-- A coluna guarda as três porque a moda sem as frases é número sem procedência:
-- é isto que permite auditar um veredito depois de ele ter barrado uma pauta.
--
-- Forma: [{"frase": "...", "engajamento_level": "..."}, ...]
-- Sem CHECK, pelo mesmo motivo da v7_15: item torto é descartado em
-- `leitura.respostas_validas`, e derrubar a gravação inteira por um rótulo seria
-- perder a entidade por causa de um campo.

ALTER TABLE public.pautador_entity_opportunities
  ADD COLUMN IF NOT EXISTS respostas jsonb;

COMMENT ON COLUMN public.pautador_entity_opportunities.respostas IS
  'PERGUNTAS CANDIDATAS: [{"frase","engajamento_level"}]. Nasceram como três votos para um rótulo e NÃO servem para isso (a distribuição é multimodal - ver app/entities/leitura.py). Servem como matéria-prima de funil: uma página de solução por pergunta, com um humano escolhendo. NUNCA entrada de score automático - o mesmo LLM inventando e pontuando as próprias invenções é circuito fechado de opinião, não medição.';

-- Auditoria de um veredito (por que esta entidade foi barrada):
--   SELECT e.canonical_name, o.engajamento_level, r->>'engajamento_level' AS voto, r->>'frase'
--     FROM public.pautador_entity_opportunities o
--     JOIN public.pautador_entities e ON e.id = o.entity_id
--     CROSS JOIN LATERAL jsonb_array_elements(o.respostas) r
--    WHERE o.reading_blocked IS TRUE;
--
-- Divergência interna (as três discordaram): sinal de entidade ambígua, não de erro.
--   SELECT count(*) FROM public.pautador_entity_opportunities
--    WHERE jsonb_array_length(respostas) = 3
--      AND (SELECT count(DISTINCT r->>'engajamento_level')
--             FROM jsonb_array_elements(respostas) r) = 3;
