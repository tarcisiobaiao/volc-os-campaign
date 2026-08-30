-- v7_15 · PORTÃO DE LEITURA (segundo eixo da descoberta)
--
--   arbitrage_score   volume × eCPM ÷ concorrência          ->  O MERCADO PAGA?
--   reading gate      ignorância · engajamento · opacidade  ->  A PESSOA LÊ?
--
-- Os dois NÃO se substituem. Medidos nas mesmas 20 entidades de finanças/Brasil,
-- a correlação de Spearman entre os ranqueamentos foi -0,092: não medem a mesma
-- coisa. Onde discordam é onde há decisão a tomar.
--
-- Os campos são da OPORTUNIDADE, não da entidade: vivem ao lado de volume_level e
-- irmãos, porque descrevem a PERGUNTA daquela oportunidade, não o órgão.
--
-- Os três *_level vêm do agente de descoberta (vocabulário fechado); os reading_*
-- são computados por backend/app/entities/leitura.py a partir deles.
--
-- SEM CHECK de vocabulário de propósito: o leitura.py já recusa valor inválido
-- (nível torto vira "ausente" e o portão se cala), e um CHECK faria a gravação da
-- oportunidade INTEIRA falhar por causa de um rótulo — perder a entidade toda por
-- um campo é o erro caro aqui. O rótulo torto fica gravado justamente para se
-- depurar o prompt que o produziu.

-- A coluna nasceu `reading_index` numa primeira aplicação desta migração e o nome
-- convidava à comparação errada: o índice do motor multiplica o resultado inteiro
-- pelos portões (`dado_unico` x0,05), enquanto aqui o portão entra DILUÍDO na
-- média (0,05^(1/3) ~ 0,37). Os dois números não são comparáveis, e o nome é a
-- única defesa contra alguém somar um com o outro daqui a três meses. O bloco
-- vem ANTES do ADD para que o ambiente já migrado renomeie (preservando os
-- valores) em vez de ganhar uma segunda coluna.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'pautador_entity_opportunities'
                AND column_name = 'reading_index')
     AND NOT EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'pautador_entity_opportunities'
                AND column_name = 'reading_strength') THEN
    ALTER TABLE public.pautador_entity_opportunities RENAME COLUMN reading_index TO reading_strength;
  END IF;
END $$;

ALTER TABLE public.pautador_entity_opportunities
  ADD COLUMN IF NOT EXISTS ignorancia_level      text,
  ADD COLUMN IF NOT EXISTS engajamento_level     text,
  ADD COLUMN IF NOT EXISTS opacidade_level       text,
  ADD COLUMN IF NOT EXISTS resposta_em_uma_frase text,
  ADD COLUMN IF NOT EXISTS reading_blocked       boolean,
  ADD COLUMN IF NOT EXISTS reading_reason        text,
  ADD COLUMN IF NOT EXISTS reading_strength      numeric(6,4);

COMMENT ON COLUMN public.pautador_entity_opportunities.ignorancia_level IS
  'Buraco de conhecimento com que a pessoa chega: nao_sei_se_existe|nao_sei_se_sirvo|nao_sei_por_que_falhou|so_falta_um_dado|sei_o_que_fazer|nao_preciso_de_nada. PORTÃO em nao_preciso_de_nada.';
COMMENT ON COLUMN public.pautador_entity_opportunities.engajamento_level IS
  'FORMA da pergunta: diagnostico|condicional|sequencial|comparativo|dado_unico. PORTÃO em dado_unico — a resposta esgota em segundos.';
COMMENT ON COLUMN public.pautador_entity_opportunities.opacidade_level IS
  'Quanto a instituição esconde: regra_mudou|fragmentada|ilegivel|clara.';
COMMENT ON COLUMN public.pautador_entity_opportunities.resposta_em_uma_frase IS
  'TESTE LITERAL: a resposta da dúvida em UMA frase, escrita ANTES de escolher engajamento_level. Sem ela a classificação vira ruído.';
COMMENT ON COLUMN public.pautador_entity_opportunities.reading_blocked IS
  'SEMPRE false desde a v7_16: o portão foi rebaixado a SUGESTÃO por medição (estabilidade do rótulo entre rodadas: 33% com 1 frase, 50% com 3, contra 24-30% de acaso; nenhuma se distingue do acaso). A sugestão vive em reading_reason. Ver BARRA_DE_VERDADE em app/entities/leitura.py e a condição de retomada ao lado dela.';
COMMENT ON COLUMN public.pautador_entity_opportunities.reading_reason IS
  'Frase legível do portão, emitida pelo próprio motor (não o código do nível).';
COMMENT ON COLUMN public.pautador_entity_opportunities.reading_strength IS
  'Força de LEITURA (0-1): média geométrica de ignorancia x engajamento x opacidade. NUNCA ORDENAR POR ELA: derivada de rótulos cuja estabilidade entre rodadas foi medida em 33% (1 frase) e 50% (3 frases), contra 24-30% de acaso. Serve para leitura humana do caso, não para ordenar - a ordenação do board é por score (arbitragem). Também não é o índice de 10 eixos do motor; não comparar com motor_pautas.Posicao.indice.';

-- Consulta de conferência pós-run (ver "COMO SABER QUE FUNCIONOU"):
--   SELECT engajamento_level, count(*) FILTER (WHERE reading_blocked) AS barrados, count(*)
--     FROM public.pautador_entity_opportunities
--    WHERE run_id = <ID> GROUP BY 1 ORDER BY 3 DESC;
-- Rótulo uniforme na run inteira = o agente classificou o tema do nicho, não a
-- pergunta de cada entidade. Zero barrados em 20 = o prompt provavelmente não está
-- devolvendo os campos.
