-- ====================================================================
-- Script para corrigir a tabela user_campaigns
-- Problema: campaign_id está referenciando campaigns.id (INTEGER)
-- Solução: Deve referenciar campaigns.campaign_id (TEXT/VARCHAR)
-- ====================================================================

BEGIN;

-- 1. Criar uma nova coluna temporária para armazenar o campaign_id correto
ALTER TABLE user_campaigns 
ADD COLUMN IF NOT EXISTS campaign_id_new VARCHAR(255);

-- 2. Migrar os dados: converter campaigns.id para campaigns.campaign_id
UPDATE user_campaigns uc
SET campaign_id_new = c.campaign_id
FROM campaigns c
WHERE c.id = uc.campaign_id::integer;

-- 3. Verificar quantos registros foram atualizados
DO $$
DECLARE
  total_records INTEGER;
  migrated_records INTEGER;
BEGIN
  SELECT COUNT(*) INTO total_records FROM user_campaigns;
  SELECT COUNT(*) INTO migrated_records FROM user_campaigns WHERE campaign_id_new IS NOT NULL;
  
  RAISE NOTICE '✅ Total de registros em user_campaigns: %', total_records;
  RAISE NOTICE '✅ Registros migrados com sucesso: %', migrated_records;
  
  IF migrated_records < total_records THEN
    RAISE WARNING '⚠️  Alguns registros não foram migrados. Verificar manualmente.';
  END IF;
END $$;

-- 4. Remover a constraint antiga
ALTER TABLE user_campaigns
DROP CONSTRAINT IF EXISTS user_campaigns_campaign_id_fkey;

-- 5. Remover a constraint única antiga
ALTER TABLE user_campaigns
DROP CONSTRAINT IF EXISTS user_campaigns_user_id_campaign_id_key;

-- 6. Remover a coluna antiga
ALTER TABLE user_campaigns
DROP COLUMN campaign_id;

-- 7. Renomear a nova coluna
ALTER TABLE user_campaigns
RENAME COLUMN campaign_id_new TO campaign_id;

-- 8. Tornar a coluna NOT NULL
ALTER TABLE user_campaigns
ALTER COLUMN campaign_id SET NOT NULL;

-- 9. Adicionar a nova foreign key referenciando campaigns.campaign_id
ALTER TABLE user_campaigns
ADD CONSTRAINT user_campaigns_campaign_id_fkey
FOREIGN KEY (campaign_id)
REFERENCES campaigns(campaign_id)
ON DELETE CASCADE;

-- 10. Recriar a constraint única
ALTER TABLE user_campaigns
ADD CONSTRAINT user_campaigns_user_id_campaign_id_key
UNIQUE(user_id, campaign_id);

-- 11. Recriar os índices
DROP INDEX IF EXISTS idx_user_campaigns_campaign_id;
CREATE INDEX idx_user_campaigns_campaign_id ON user_campaigns(campaign_id);

-- 12. Atualizar comentários
COMMENT ON COLUMN user_campaigns.campaign_id IS 'Google Ads campaign identifier (referência a campaigns.campaign_id)';
COMMENT ON TABLE user_campaigns IS 'Associação entre usuários operadores e campanhas específicas. Usa campaign_id (identificador do Google Ads) ao invés do ID interno.';

-- 13. Verificar estrutura final
DO $$
DECLARE
  col_type TEXT;
BEGIN
  SELECT data_type INTO col_type
  FROM information_schema.columns
  WHERE table_name = 'user_campaigns' 
    AND column_name = 'campaign_id';
  
  RAISE NOTICE '✅ Tipo da coluna campaign_id: %', col_type;
END $$;

COMMIT;

-- 14. Exibir dados para verificação
SELECT 
  uc.id,
  uc.user_id,
  u.name as user_name,
  uc.campaign_id,
  c.campaign_name,
  c.project_id
FROM user_campaigns uc
JOIN users u ON u.id = uc.user_id
LEFT JOIN campaigns c ON c.campaign_id = uc.campaign_id
ORDER BY uc.created_at DESC
LIMIT 10;







