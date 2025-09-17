-- Adiciona coluna costs_division na tabela projects
-- Execute no Supabase SQL Editor

-- Adicionar coluna costs_division (padrão false)
ALTER TABLE projects 
ADD COLUMN IF NOT EXISTS costs_division BOOLEAN DEFAULT false;

-- Comentário para documentação
COMMENT ON COLUMN projects.costs_division IS 'Se o projeto participa da divisão de custos operacionais';

-- Atualizar todos os projetos ativos para participarem por padrão (opcional)
-- UPDATE projects SET costs_division = true WHERE status = 'active';

-- Verificar a alteração
SELECT id, project_name, domain, status, costs_division 
FROM projects 
ORDER BY project_name 
LIMIT 10;