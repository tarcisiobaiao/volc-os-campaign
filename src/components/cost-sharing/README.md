# ProjectCostSharing Component

Dropdown compacto para selecionar quais projetos dividirão os custos operacionais.

## Funcionalidades

- **UI Minimalista**: Dropdown toggle que ocupa pouco espaço
- **Seleção por Checkbox**: Lista de projetos com checkboxes no dropdown
- **Controles Rápidos**: Botões "Todos" e "Limpar" no dropdown
- **Salvamento Silencioso**: Alterações salvam automaticamente sem feedback
- **Cálculo Inline**: Mostra custo por projeto no dropdown
- **Estado Persistente**: Configurações ficam salvas na tabela projects

## Uso

```tsx
import { ProjectCostSharing } from '@/components/cost-sharing/ProjectCostSharing';

<ProjectCostSharing
  totalCost={getTotalCosts()}
  selectedMonth={selectedMonth}
  onSelectionChange={(selectedProjects, costPerProject) => {
    // Callback executado quando a seleção muda
  }}
/>
```

## Props

- `totalCost`: Valor total dos custos operacionais a serem divididos
- `selectedMonth`: Mês de referência para buscar os projetos
- `onSelectionChange`: Callback chamado quando a seleção muda

## UI Compacta

O componente renderiza como:
```
Divisão de Custos: [Dropdown: "X projetos" ▼] ✓ X projetos selecionados
```

No dropdown:
- Lista de projetos com checkboxes
- Botões "Todos" e "Limpar" 
- Cálculo do custo por projeto
- Scroll para muitos projetos

## Comportamento

- **Falha Silenciosa**: Se a coluna costs_division não existir, não mostra erro
- **Auto-hide**: Se não há projetos, o componente não aparece
- **Loading State**: Mostra "Carregando..." enquanto busca projetos
- **Persistência**: Cada toggle salva imediatamente no banco

## Integração

Integrado na página `CostsSettings.tsx` como um card compacto entre impostos e categorias.