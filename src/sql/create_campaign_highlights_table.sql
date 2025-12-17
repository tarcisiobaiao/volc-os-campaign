-- Tabela para rastrear quando campanhas foram destacadas na home
-- Garante rotação: campanha só pode aparecer novamente após 5 dias

CREATE TABLE IF NOT EXISTS campaign_highlights (
  id BIGSERIAL PRIMARY KEY,
  campaign_id BIGINT NOT NULL,
  category VARCHAR(50) NOT NULL CHECK (category IN ('em_alta', 'em_baixa', 'estagnada', 'alerta_tecnico')),
  highlighted_at DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  
  -- Garantir que não há duplicatas no mesmo dia
  UNIQUE(campaign_id, category, highlighted_at)
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_campaign_highlights_campaign_id ON campaign_highlights(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_highlights_highlighted_at ON campaign_highlights(highlighted_at);
CREATE INDEX IF NOT EXISTS idx_campaign_highlights_category ON campaign_highlights(category);

-- Comentários
COMMENT ON TABLE campaign_highlights IS 'Rastreia quando campanhas foram destacadas na home para garantir rotação de 5 dias';
COMMENT ON COLUMN campaign_highlights.campaign_id IS 'ID da campanha destacada';
COMMENT ON COLUMN campaign_highlights.category IS 'Categoria: em_alta, em_baixa, estagnada, alerta_tecnico';
COMMENT ON COLUMN campaign_highlights.highlighted_at IS 'Data em que a campanha foi destacada (usado para calcular rotação de 5 dias)';














