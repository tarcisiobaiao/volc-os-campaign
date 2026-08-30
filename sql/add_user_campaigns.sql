-- Tabela para associar usuários a campanhas específicas
-- Isso permite que operadores vejam apenas as campanhas permitidas dentro dos projetos

CREATE TABLE IF NOT EXISTS user_campaigns (
  id SERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(user_id, campaign_id)
);

-- Índices para melhor performance
CREATE INDEX IF NOT EXISTS idx_user_campaigns_user_id ON user_campaigns(user_id);
CREATE INDEX IF NOT EXISTS idx_user_campaigns_campaign_id ON user_campaigns(campaign_id);

-- Comentários
COMMENT ON TABLE user_campaigns IS 'Associação entre usuários e campanhas específicas que eles podem acessar';
COMMENT ON COLUMN user_campaigns.user_id IS 'UUID do usuário (referência a users.id)';
COMMENT ON COLUMN user_campaigns.campaign_id IS 'ID da campanha (referência a campaigns.id)';
