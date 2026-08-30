import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  Home, FolderOpen, Megaphone, FileText, Rocket, Radar, DollarSign, Zap,
  Users, LogOut, RefreshCw, CornerDownLeft, Circle,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useUserFilters } from "@/hooks/useUserFilters";
import { supabaseDataService, type Project, type Campaign } from "@/services/supabaseDataService";

/** Qualquer parte do app pode abrir a paleta com:
 *  window.dispatchEvent(new Event("volc:command")) */
const OPEN_EVENT = "volc:command";
export const openCommandPalette = () => window.dispatchEvent(new Event(OPEN_EVENT));

type NavEntry = { title: string; href: string; icon: any; adminOnly?: boolean };
const NAV: NavEntry[] = [
  { title: "Dashboard Geral", href: "/", icon: Home, adminOnly: true },
  { title: "Projetos", href: "/dashboard/projects", icon: FolderOpen, adminOnly: true },
  { title: "Campanhas", href: "/settings/campaigns", icon: Megaphone },
  { title: "Relatórios", href: "/reports", icon: FileText, adminOnly: true },
  { title: "Incubadora", href: "/incubator", icon: Rocket, adminOnly: true },
  { title: "Pautador Pro", href: "/pautador-pro", icon: Radar, adminOnly: true },
  { title: "Custos", href: "/settings/costs", icon: DollarSign, adminOnly: true },
  { title: "Integrações", href: "/settings/integrations", icon: Zap, adminOnly: true },
  { title: "Usuários", href: "/settings/users", icon: Users, adminOnly: true },
];

const STATUS_TONE: Record<string, string> = {
  active: "text-success fill-success",
  paused: "text-warning fill-warning",
  completed: "text-muted-foreground fill-muted-foreground",
};

const Kbd = ({ children }: { children: React.ReactNode }) => (
  <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-sans text-[10px] leading-none text-muted-foreground">
    {children}
  </kbd>
);

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();
  const { user, userProfile, signOut } = useAuth();
  const { allowedProjectIds, allowedCampaignIds } = useUserFilters();
  const isAdmin = userProfile?.role === "ADMIN";

  // Atalho ⌘K / Ctrl+K + evento custom.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onEvent = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onEvent);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onEvent);
    };
  }, []);

  // Carrega projetos/campanhas uma vez, sob demanda (na primeira abertura).
  useEffect(() => {
    if (!open || !user || loaded || loading) return;
    setLoading(true);
    Promise.all([
      supabaseDataService.getProjects().catch(() => [] as Project[]),
      supabaseDataService.getCampaigns().catch(() => [] as Campaign[]),
    ])
      .then(([p, c]) => {
        setProjects(Array.isArray(p) ? p : []);
        setCampaigns(Array.isArray(c) ? c : []);
        setLoaded(true);
      })
      .finally(() => setLoading(false));
  }, [open, user, loaded, loading]);

  const go = useCallback(
    (href: string) => {
      setOpen(false);
      setQuery("");
      navigate(href);
    },
    [navigate]
  );

  if (!user) return null;

  const nav = NAV.filter((n) => isAdmin || !n.adminOnly);
  const visibleProjects = isAdmin
    ? projects
    : projects.filter((p) => allowedProjectIds.includes(Number(p.id)));
  const visibleCampaigns = isAdmin
    ? campaigns
    : campaigns.filter(
        (c) => c.googleAdsCampaignId && allowedCampaignIds.includes(c.googleAdsCampaignId)
      );

  const itemCls =
    "group gap-3 rounded-md data-[selected=true]:bg-primary/[0.08] data-[selected=true]:text-foreground";

  const handleRefresh = () => {
    setOpen(false);
    window.location.reload();
  };
  const handleSignOut = () => {
    setOpen(false);
    signOut();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setQuery("");
      }}
    >
      <DialogContent className="overflow-hidden p-0 gap-0 max-w-xl border-border shadow-elevated [&>button]:hidden">
        <DialogTitle className="sr-only">Paleta de comandos</DialogTitle>
        <span className="hairline-aurora absolute inset-x-0 top-0 z-10" />
        <Command loop className="bg-card [&_[cmdk-group-heading]]:kicker [&_[cmdk-group-heading]]:!py-2">
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Buscar telas, projetos, campanhas…"
          />
          <CommandList className="max-h-[min(62vh,440px)] px-1 pb-1">
            {loading && (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                <RefreshCw className="h-4 w-4 animate-spin" /> Carregando…
              </div>
            )}
            <CommandEmpty className="py-8 text-center text-sm text-muted-foreground">
              Nada encontrado.
            </CommandEmpty>

            <CommandGroup heading="Ir para">
              {nav.map((n) => (
                <CommandItem
                  key={n.href}
                  value={`ir ${n.title}`}
                  onSelect={() => go(n.href)}
                  className={itemCls}
                >
                  <span className="rounded-md bg-muted text-muted-foreground p-1.5">
                    <n.icon className="h-4 w-4" />
                  </span>
                  <span className="flex-1 truncate">{n.title}</span>
                  <CornerDownLeft className="h-3.5 w-3.5 opacity-0 transition-opacity group-data-[selected=true]:opacity-50" />
                </CommandItem>
              ))}
            </CommandGroup>

            {visibleProjects.length > 0 && (
              <CommandGroup heading="Projetos">
                {visibleProjects.slice(0, 400).map((p) => (
                  <CommandItem
                    key={p.id}
                    value={`projeto ${p.name} ${p.domain ?? ""}`}
                    onSelect={() => go(`/dashboard/project/${p.id}`)}
                    className={itemCls}
                  >
                    <span className="rounded-md bg-info/10 text-info p-1.5">
                      <FolderOpen className="h-4 w-4" />
                    </span>
                    <span className="flex-1 truncate">{p.name}</span>
                    {p.domain && <span className="kicker truncate max-w-[40%]">{p.domain}</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}

            {visibleCampaigns.length > 0 && (
              <CommandGroup heading="Campanhas">
                {visibleCampaigns.slice(0, 500).map((c) => (
                  <CommandItem
                    key={c.id}
                    value={`campanha ${c.name}`}
                    onSelect={() => go(`/dashboard/campaign/${c.id}`)}
                    className={itemCls}
                  >
                    <span className="rounded-md bg-primary/10 text-primary p-1.5">
                      <Megaphone className="h-4 w-4" />
                    </span>
                    <span className="flex-1 truncate">{c.name}</span>
                    <Circle className={`h-2 w-2 ${STATUS_TONE[c.status] ?? "text-muted-foreground fill-muted-foreground"}`} />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}

            <CommandGroup heading="Ações">
              <CommandItem value="acao atualizar recarregar dados" onSelect={handleRefresh} className={itemCls}>
                <span className="rounded-md bg-muted text-muted-foreground p-1.5">
                  <RefreshCw className="h-4 w-4" />
                </span>
                Atualizar dados
              </CommandItem>
              <CommandItem
                value="acao sair logout"
                onSelect={handleSignOut}
                className={`${itemCls} text-destructive data-[selected=true]:bg-destructive/[0.08] data-[selected=true]:text-destructive`}
              >
                <span className="rounded-md bg-destructive/10 text-destructive p-1.5">
                  <LogOut className="h-4 w-4" />
                </span>
                Sair
              </CommandItem>
            </CommandGroup>
          </CommandList>

          <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Kbd>↑</Kbd><Kbd>↓</Kbd> navegar <Kbd>↵</Kbd> abrir
            </span>
            <span className="flex items-center gap-1.5">
              <Kbd>⌘</Kbd><Kbd>K</Kbd> abrir/fechar
            </span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
