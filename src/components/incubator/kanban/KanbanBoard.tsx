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
import { KanbanSiteCard } from './KanbanSiteCard';
import { KANBAN_COLUMNS } from '@/types/incubator';
import type { IncubatorSite, SiteStatus } from '@/types/incubator';

interface KanbanBoardProps {
  sites: IncubatorSite[];
  onSiteClick: (site: IncubatorSite) => void;
  onStatusChange: (siteId: number, newStatus: SiteStatus) => void;
}

export const KanbanBoard: React.FC<KanbanBoardProps> = ({ sites, onSiteClick, onStatusChange }) => {
  const [activeSite, setActiveSite] = React.useState<IncubatorSite | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    })
  );

  // Agrupar sites por coluna
  const sitesByColumn = useMemo(() => {
    const map: Record<string, IncubatorSite[]> = {};
    for (const col of KANBAN_COLUMNS) {
      map[col.id] = sites.filter(s => col.statuses.includes(s.status));
    }
    // Sites pausados ficam fora — podemos adicionar na coluna de origem ou ignorar
    const pausedSites = sites.filter(s => s.status === 'paused');
    if (pausedSites.length > 0) {
      // Adicionar pausados à coluna Draft
      map['draft'] = [...(map['draft'] || []), ...pausedSites];
    }
    return map;
  }, [sites]);

  const handleDragStart = (event: DragStartEvent) => {
    const site = event.active.data.current?.site as IncubatorSite | undefined;
    setActiveSite(site || null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveSite(null);
    const { active, over } = event;
    if (!over) return;

    const site = active.data.current?.site as IncubatorSite | undefined;
    if (!site) return;

    // Descobrir qual coluna foi o destino
    const targetColumnId = typeof over.id === 'string' ? over.id : null;
    const targetColumn = KANBAN_COLUMNS.find(c => c.id === targetColumnId);

    if (targetColumn) {
      // Usar o primeiro status da coluna destino
      const newStatus = targetColumn.statuses[0];
      if (newStatus !== site.status) {
        onStatusChange(site.id, newStatus);
      }
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
        {KANBAN_COLUMNS.map((column) => (
          <KanbanColumn
            key={column.id}
            column={column}
            sites={sitesByColumn[column.id] || []}
            onSiteClick={onSiteClick}
          />
        ))}
      </div>

      <DragOverlay>
        {activeSite ? (
          <div className="w-[280px]">
            <KanbanSiteCard site={activeSite} onClick={() => {}} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
};
