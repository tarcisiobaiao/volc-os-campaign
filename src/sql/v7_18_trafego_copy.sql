-- =====================================================================
-- v7 HUB DE TRÁFEGO — Etapa 18 / A copy do anúncio, PERSISTIDA (ADITIVO, idempotente)
--
-- POR QUE ESTA TABELA EXISTE
--
-- `POST /api/trafego/copy` roda a cascata de `volc_ads/copy` e demora. Medido
-- em 18/08/2026 no card 73: **174,19 s**, 29.078 tokens de entrada e 34.315 de
-- saída, em duas rodadas de conjunto. É uma chamada de LLM PAGA.
--
-- Até aqui o resultado dela existia só na memória do browser. Sair da página
-- descartava — sem linha no banco, sem arquivo, sem log de que aquilo tinha
-- rodado. O operador voltava e via o botão "escrever a copy" de novo, como se
-- nada tivesse acontecido, e os tokens já estavam gastos.
--
-- É o mesmo defeito que derrubou o acompanhamento do run #7 do Redator:
-- trabalho pago cujo registro depende de alguém continuar olhando.
--
-- POR QUE `keywords` FICA NA LINHA
--
-- A copy é ancorada nos termos SELECIONADOS — o prompt recebe exatamente eles.
-- Sem guardar quais eram, voltar à tela mostraria um texto escrito para outra
-- seleção, e ele parece perfeitamente válido: fala de cartão, cita fato, tem 15
-- títulos. O erro só apareceria no leilão, num anúncio ancorado numa keyword
-- que o operador desmarcou.
--
-- POR QUE `status` E NÃO SÓ O RESULTADO
--
-- A geração roda em segundo plano. Sem estado, uma tela reaberta no meio não
-- distingue "ninguém pediu ainda" de "está rodando há 40 s" — e as duas telas
-- oferecem o mesmo botão, que gastaria de novo.
--
-- ⚠️ `running` NÃO PROVA QUE ALGO ESTÁ RODANDO. A tarefa vive dentro do
-- processo do backend; um reinício a mata e deixa a linha `running` para
-- sempre. Quem lê tem de comparar `atualizado_em` com o teto da rota e tratar
-- linha velha como PERDIDA, não como em andamento. Ver `routers/trafego.py`.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.pautador_trafego_copy (
  id              BIGSERIAL PRIMARY KEY,
  opportunity_id  INTEGER      NOT NULL,
  -- O funil de origem. NULO quando o cockpit foi aberto sem `?run=`.
  run_id          INTEGER,

  -- running | done | error
  status          TEXT         NOT NULL DEFAULT 'running',

  -- Os termos para os quais este texto foi escrito. Ver o cabeçalho.
  keywords        JSONB        NOT NULL DEFAULT '[]'::jsonb,

  -- O que a cascata devolveu, no vocabulário do ENGINE (`title`,
  -- `description1`, `values`) — nunca traduzido, porque a tradução foi
  -- exatamente o que entregava sitelink vazio a `/provar` sem erro nenhum.
  copy            JSONB,

  -- Tokens, latência e custo medidos. `custo_usd` pode vir nulo: o cliente não
  -- inventa preço quando VOLC_ADS_PRECO_* não está configurado.
  medicao         JSONB,

  -- O que a cascata desistiu de consertar, e o diário rodada a rodada. É o que
  -- transforma "reprovou" em "regenerou headline[3] por C7".
  pendentes       JSONB        NOT NULL DEFAULT '[]'::jsonb,
  diario          JSONB        NOT NULL DEFAULT '[]'::jsonb,

  -- Fatos do funil aproveitados e descartados. Medido no card 73: 4 dos 6 têm
  -- `tipo: 'afirmacao'`, que a seção 2 do PROMPT.md não conhece.
  fatos_usados       INTEGER   NOT NULL DEFAULT 0,
  fatos_descartados  JSONB     NOT NULL DEFAULT '[]'::jsonb,

  aceita          BOOLEAN,
  segundos        NUMERIC(10,2),
  erro            TEXT,

  criado_em       TIMESTAMPTZ  NOT NULL DEFAULT now(),
  atualizado_em   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Uma copy por (card, funil). Reescrever SUBSTITUI — guardar histórico de
-- textos descartados encheria a tabela de versões que ninguém sabe datar, e o
-- que importa é qual texto vai subir.
--
-- ⚠️ `COALESCE` porque `run_id` é anulável e, em Postgres, NULL nunca é igual a
-- NULL: um índice único direto deixaria criar infinitas linhas com run nulo
-- para o mesmo card.
CREATE UNIQUE INDEX IF NOT EXISTS pautador_trafego_copy_card_run_uniq
  ON public.pautador_trafego_copy (opportunity_id, COALESCE(run_id, -1));

CREATE INDEX IF NOT EXISTS pautador_trafego_copy_status_idx
  ON public.pautador_trafego_copy (status, atualizado_em DESC);

-- RLS ligada e ZERO policies: quem lê e escreve é o backend com `service_role`,
-- que faz bypass. Nenhum client com `anon`/`authenticated` toca nesta tabela.
-- Ela não guarda segredo, mas guarda TEXTO PAGO — e o proxy genérico
-- `/api/supabase/query` (ver v7_13) é motivo suficiente para não deixá-la
-- aberta por padrão.
ALTER TABLE public.pautador_trafego_copy ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.pautador_trafego_copy IS
  'Copy do anúncio gerada pela cascata de volc_ads/copy. ~174 s e tokens pagos '
  'por geração — persistida para que sair da tela não jogue fora o que foi pago.';
