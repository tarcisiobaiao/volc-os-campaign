import React, { useMemo } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
} from '@dnd-kit/core';
import { KanbanColumn } from './KanbanColumn';
import { OpportunityCard } from './OpportunityCard';
import { PAUTADOR_KANBAN_COLUMNS } from '@/types/pautador';
import { oppKey } from '@/hooks/pautador/usePautadorPro';
import type { Opportunity, OpportunityStatus } from '@/types/pautador';

interface KanbanBoardProps {
  opportunities: Opportunity[];
  busyKeys: Set<string>;
  onCardClick: (opp: Opportunity) => void;
  onStatusChange: (opp: Opportunity, newStatus: OpportunityStatus) => void;
}

export const KanbanBoard: React.FC<KanbanBoardProps> = ({
  opportunities,
  busyKeys,
  onCardClick,
  onStatusChange,
}) => {
  const [active, setActive] = React.useState<Opportunity | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const byColumn = useMemo(() => {
    const map: Record<string, Opportunity[]> = {};
    for (const col of PAUTADOR_KANBAN_COLUMNS) {
      map[col.id] = opportunities.filter((o) => col.statuses.includes(o.status));
    }
    return map;
  }, [opportunities]);

  const handleDragStart = (event: DragStartEvent) => {
    setActive((event.active.data.current?.opportunity as Opportunity) || null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActive(null);
    const { active: a, over } = event;
    if (!over) return;
    const opp = a.data.current?.opportunity as Opportunity | undefined;
    if (!opp) return;

    // over.id is either a column id (droppable) or a card key (sortable item)
    const overId = typeof over.id === 'string' ? over.id : String(over.id);
    let targetColumn = PAUTADOR_KANBAN_COLUMNS.find((c) => c.id === overId);
    if (!targetColumn) {
      const overOpp = over.data.current?.opportunity as Opportunity | undefined;
      if (overOpp) {
        targetColumn = PAUTADOR_KANBAN_COLUMNS.find((c) => c.statuses.includes(overOpp.status));
      }
    }
    if (targetColumn) {
      const newStatus = targetColumn.statuses[0];
      if (newStatus !== opp.status) onStatusChange(opp, newStatus);
    }
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {PAUTADOR_KANBAN_COLUMNS.map((column, i) => (
          <KanbanColumn
            key={column.id}
            column={column}
            opportunities={byColumn[column.id] || []}
            busyKeys={busyKeys}
            onCardClick={onCardClick}
            index={i}
          />
        ))}
      </div>

      <DragOverlay>
        {active ? (
          <div className="w-[270px]">
            <OpportunityCard cardKey={oppKey(active)} opportunity={active} onClick={() => {}} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
};
