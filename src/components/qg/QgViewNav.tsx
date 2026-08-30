import * as React from "react";
import { Activity, GitFork, Inbox, KanbanSquare, ListChecks, Route, Target } from "lucide-react";
import { cn } from "@/lib/utils";
import type { QgView } from "@/features/work-road/url-state";
import { QG_VIEWS } from "@/features/work-road/url-state";

const ITEMS: Array<{ id: QgView; label: string; icon: typeof Target }> = [
  { id: "agora", label: "Agora", icon: Target },
  { id: "timeline", label: "Timeline", icon: Route },
  { id: "kanban", label: "Kanban", icon: KanbanSquare },
  { id: "lista", label: "Lista", icon: ListChecks },
  { id: "grafo", label: "Grafo", icon: GitFork },
  { id: "execucoes", label: "Execuções", icon: Activity },
  { id: "inbox", label: "Inbox", icon: Inbox },
];

export function QgViewNav({
  view,
  onChange,
}: {
  view: QgView;
  onChange: (view: QgView) => void;
}) {
  const refs = React.useRef<Array<HTMLButtonElement | null>>([]);

  const move = (from: QgView, delta: number) => {
    const index = QG_VIEWS.indexOf(from);
    const next = QG_VIEWS[(index + delta + QG_VIEWS.length) % QG_VIEWS.length];
    onChange(next);
    refs.current[QG_VIEWS.indexOf(next)]?.focus();
  };

  return (
    <nav aria-label="Visões do QG Operacional" className="mt-6 overflow-x-auto">
      <div
        role="tablist"
        aria-orientation="horizontal"
        className="inline-flex min-h-11 min-w-max gap-1 rounded-lg border border-border bg-muted p-1"
      >
        {ITEMS.map((item, index) => {
          const selected = view === item.id;
          return (
            <button
              key={item.id}
              ref={(node) => { refs.current[index] = node; }}
              role="tab"
              type="button"
              id={`qg-tab-${item.id}`}
              aria-selected={selected}
              aria-controls={`qg-panel-${item.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(item.id)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight") { event.preventDefault(); move(item.id, 1); }
                if (event.key === "ArrowLeft") { event.preventDefault(); move(item.id, -1); }
                if (event.key === "Home") { event.preventDefault(); onChange("agora"); refs.current[0]?.focus(); }
                if (event.key === "End") {
                  event.preventDefault();
                  onChange(QG_VIEWS[QG_VIEWS.length - 1]);
                  refs.current[QG_VIEWS.length - 1]?.focus();
                }
              }}
              className={cn(
                "inline-flex h-9 min-h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground",
                "outline-none transition-colors duration-150 ease-out hover:text-foreground",
                "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                "motion-reduce:transition-none",
                selected && "bg-card text-foreground shadow-card",
              )}
            >
              <item.icon aria-hidden="true" className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
