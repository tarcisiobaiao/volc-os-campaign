-- Tabela para armazenar as configurações de divisão de custos entre projetos
-- Execute no Supabase SQL Editor

-- Criar tabela project_cost_sharing
CREATE TABLE IF NOT EXISTS project_cost_sharing (
  id SERIAL PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  month DATE NOT NULL, -- formato YYYY-MM-01
  is_included_in_cost_sharing BOOLEAN NOT NULL DEFAULT false,
  cost_share_amount DECIMAL(10,2) DEFAULT 0, -- valor que o projeto absorveu naquele mês
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Índices para performance
  UNIQUE(project_id, month) -- evita duplicatas para mesmo projeto/mês
);

-- Criar índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_project_cost_sharing_month ON project_cost_sharing(month);
CREATE INDEX IF NOT EXISTS idx_project_cost_sharing_project ON project_cost_sharing(project_id);
CREATE INDEX IF NOT EXISTS idx_project_cost_sharing_included ON project_cost_sharing(is_included_in_cost_sharing);

-- Função para atualizar o timestamp automaticamente
CREATE OR REPLACE FUNCTION update_project_cost_sharing_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para atualizar updated_at automaticamente
DROP TRIGGER IF EXISTS trigger_update_project_cost_sharing_updated_at ON project_cost_sharing;
CREATE TRIGGER trigger_update_project_cost_sharing_updated_at
  BEFORE UPDATE ON project_cost_sharing
  FOR EACH ROW
  EXECUTE FUNCTION update_project_cost_sharing_updated_at();

-- View para facilitar consultas com informações dos projetos
CREATE OR REPLACE VIEW project_cost_sharing_view AS
SELECT 
  pcs.id,
  pcs.project_id,
  p.project_name,
  p.domain,
  p.status as project_status,
  pcs.month,
  pcs.is_included_in_cost_sharing,
  pcs.cost_share_amount,
  pcs.created_at,
  pcs.updated_at
FROM project_cost_sharing pcs
JOIN projects p ON pcs.project_id = p.id
ORDER BY pcs.month DESC, p.project_name;

-- Comentários para documentação
COMMENT ON TABLE project_cost_sharing IS 'Armazena quais projetos participam da divisão de custos operacionais por mês';
COMMENT ON COLUMN project_cost_sharing.project_id IS 'Referência ao projeto na tabela projects';
COMMENT ON COLUMN project_cost_sharing.month IS 'Mês de referência no formato YYYY-MM-01';
COMMENT ON COLUMN project_cost_sharing.is_included_in_cost_sharing IS 'Se o projeto está incluído na divisão de custos do mês';
COMMENT ON COLUMN project_cost_sharing.cost_share_amount IS 'Valor que o projeto absorveu dos custos operacionais';

-- Exemplos de consulta para teste
-- SELECT * FROM project_cost_sharing_view WHERE month = '2025-09-01';
-- SELECT project_name, is_included_in_cost_sharing, cost_share_amount FROM project_cost_sharing_view WHERE month = '2025-09-01' AND is_included_in_cost_sharing = true;