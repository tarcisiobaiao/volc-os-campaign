import * as React from "react";
import { useSearchParams } from "react-router-dom";
import {
  Archive,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  CircleDashed,
  Clock3,
  Database,
  ExternalLink,
  FileCheck2,
  Fingerprint,
  Globe2,
  Image as ImageIcon,
  KeyRound,
  Link2,
  ListFilter,
  LockKeyhole,
  Megaphone,
  Network,
  Search,
  ShieldCheck,
  Vault,
  Video,
  Waypoints,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { INITIAL_ASSETS } from "./fixtures";
import {
  ASSET_CLUSTERS,
  CLUSTER_DESCRIPTION,
  CLUSTER_LABEL,
  CUSTODY_LABEL,
  KIND_LABEL,
  KIND_CLUSTER,
  STATE_LABEL,
  VERIFICATION_LABEL,
  type AssetCluster,
  type AssetKind,
  type AssetState,
  type DigitalAsset,
  type VerificationState,
} from "./contract";

type VaultView = "inventory" | "relations" | "reviews" | "contract";

const VIEWS: Array<{ id: VaultView; label: string; icon: typeof Vault }> = [
  { id: "inventory", label: "Inventário", icon: Archive },
  { id: "reviews", label: "Revisões", icon: FileCheck2 },
  { id: "relations", label: "Relações", icon: Network },
  { id: "contract", label: "Contrato", icon: Fingerprint },
];

const VALID_VIEWS = new Set<VaultView>(VIEWS.map((view) => view.id));

const STATE_TONE: Record<AssetState, string> = {
  declared: "border-warning/30 bg-warning/10 text-warning",
  verified: "border-info/30 bg-info/10 text-info",
  ready: "border-primary/30 bg-primary/10 text-primary",
  active: "border-success/30 bg-success/10 text-success",
  restricted: "border-warning/30 bg-warning/10 text-warning",
  inactive: "border-border bg-muted text-muted-foreground",
  retired: "border-border bg-muted text-muted-foreground",
};

const VERIFICATION_TONE: Record<VerificationState, string> = {
  verified: "text-success",
  partial: "text-warning",
  unverified: "text-muted-foreground",
  expired: "text-destructive",
};

const CLUSTER_ICONS: Record<AssetCluster, typeof Vault> = {
  social_presence: Megaphone,
  paid_media: Network,
  web_properties: Globe2,
  communities: Bot,
  creative_production: ImageIcon,
  automation: Waypoints,
  infrastructure: Database,
};

function dateLabel(value?: string) {
  if (!value) return "Ainda não conferido";
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(date);
}

function StatePill({ state }: { state: AssetState }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]", STATE_TONE[state])}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {STATE_LABEL[state]}
    </span>
  );
}

function VerificationMark({ asset }: { asset: DigitalAsset }) {
  const state = asset.verification.state;
  const Icon = state === "verified" ? CheckCircle2 : state === "expired" ? CircleAlert : CircleDashed;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs", VERIFICATION_TONE[state])}>
      <Icon aria-hidden="true" className="h-3.5 w-3.5" />
      {VERIFICATION_LABEL[state]}
    </span>
  );
}

function Pulse({ assets }: { assets: DigitalAsset[] }) {
  const verified = assets.filter((asset) => asset.verification.state === "verified").length;
  const needsReview = assets.filter((asset) => asset.verification.state !== "verified").length;
  const accessOpen = assets.filter((asset) => asset.credential.required && asset.credential.state !== "referenced").length;
  const ownersOpen = assets.filter((asset) => asset.owner.custody !== "verified").length;
  const cells = [
    [assets.length, "ativos no retrato"],
    [verified, "verificados"],
    [needsReview, "pedem conferência"],
    [ownersOpen, "custódias a provar"],
    [accessOpen, "acessos a organizar"],
  ];
  return (
    <section aria-label="Pulso do patrimônio" className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 xl:grid-cols-5">
      {cells.map(([value, label]) => (
        <div key={label} className="flex items-center gap-3 bg-card px-4 py-3">
          <span className="text-xl font-semibold tabular-nums">{value}</span>
          <span className="text-xs leading-4 text-muted-foreground">{label}</span>
        </div>
      ))}
    </section>
  );
}

function SecurityBoundary() {
  return (
    <section className="mt-6 grid gap-4 border-y border-border py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center" aria-label="Fronteira de segurança">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 rounded-md bg-success/10 p-2 text-success"><ShieldCheck aria-hidden="true" className="h-4 w-4" /></span>
        <div>
          <p className="text-sm font-semibold">Aqui mora o patrimônio, não a senha</p>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            O VOLC registra identidade, custódia, evidência e postura de acesso. Senhas, chaves, MFA e códigos de recuperação ficam em um cofre especializado externo.
          </p>
        </div>
      </div>
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-success/25 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
        <LockKeyhole aria-hidden="true" className="h-3.5 w-3.5" /> Zero segredo neste contrato
      </span>
    </section>
  );
}

interface InventoryProps {
  assets: DigitalAsset[];
  selectedId: string | null;
  onSelect: (assetId: string) => void;
}

function Inventory({ assets, selectedId, onSelect }: InventoryProps) {
  const [search, setSearch] = React.useState("");
  const [cluster, setCluster] = React.useState<AssetCluster | "all">("all");
  const [kind, setKind] = React.useState<AssetKind | "all">("all");
  const [state, setState] = React.useState<AssetState | "all">("all");
  const normalized = search.trim().toLocaleLowerCase("pt-BR");
  const filtered = assets.filter((asset) => {
    if (cluster !== "all" && asset.cluster !== cluster) return false;
    if (kind !== "all" && asset.kind !== kind) return false;
    if (state !== "all" && asset.state !== state) return false;
    if (!normalized) return true;
    return [asset.name, asset.platform, asset.project, asset.vertical, ...asset.tags]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("pt-BR")
      .includes(normalized);
  });
  const selected = filtered.find((asset) => asset.id === selectedId) || filtered[0] || null;
  const availableKinds = Object.entries(KIND_LABEL).filter(([value]) => cluster === "all" || KIND_CLUSTER[value as AssetKind] === cluster);
  const groups = ASSET_CLUSTERS.map((id) => ({ id, assets: filtered.filter((asset) => asset.cluster === id) })).filter((group) => group.assets.length > 0);

  const chooseCluster = (next: AssetCluster | "all") => {
    setCluster(next);
    if (kind !== "all" && next !== "all" && KIND_CLUSTER[kind] !== next) setKind("all");
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_25rem]">
      <section aria-labelledby="asset-list-heading" className="min-w-0">
        <div className="flex flex-col gap-3 border-b border-border pb-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Retrato editorial</p>
            <h2 id="asset-list-heading" className="mt-1 text-xl font-semibold tracking-tight">Ativos conhecidos</h2>
            <p className="mt-1 text-sm text-muted-foreground">{filtered.length} de {assets.length}, sem persistência nesta etapa.</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Clock3 aria-hidden="true" className="h-3.5 w-3.5" /> Fonte revisada em 27 ago. 2026
          </div>
        </div>

        <div className="border-b border-border py-4">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Organizar por gaveta</p>
          <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Clusters de ativos">
            <button type="button" onClick={() => chooseCluster("all")} aria-pressed={cluster === "all"} className={cn("shrink-0 rounded-md border px-3 py-2 text-xs font-medium transition-colors", cluster === "all" ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>Todos <span className="ml-1 tabular-nums">{assets.length}</span></button>
            {ASSET_CLUSTERS.map((id) => {
              const Icon = CLUSTER_ICONS[id];
              const count = assets.filter((asset) => asset.cluster === id).length;
              return (
                <button key={id} type="button" onClick={() => chooseCluster(id)} aria-pressed={cluster === id} className={cn("inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-xs font-medium transition-colors", cluster === id ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                  <Icon aria-hidden="true" className="h-3.5 w-3.5" />{CLUSTER_LABEL[id]} <span className="tabular-nums">{count}</span>
                </button>
              );
            })}
          </div>
          {cluster !== "all" ? <p className="mt-2 text-xs text-muted-foreground">{CLUSTER_DESCRIPTION[cluster]}</p> : null}
        </div>

        <div className="grid gap-2 border-b border-border py-4 md:grid-cols-[minmax(14rem,1fr)_12rem_11rem]">
          <label className="relative block">
            <span className="sr-only">Buscar ativos</span>
            <Search aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar ativo, plataforma ou projeto"
              className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label>
            <span className="sr-only">Filtrar por família</span>
            <select value={kind} onChange={(event) => setKind(event.target.value as AssetKind | "all")} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
              <option value="all">Todas as famílias</option>
              {availableKinds.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Filtrar por estado</span>
            <select value={state} onChange={(event) => setState(event.target.value as AssetState | "all")} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
              <option value="all">Todos os estados</option>
              {Object.entries(STATE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        </div>

        {filtered.length ? (
          <div className="space-y-6 pt-5" aria-label="Ativos encontrados">
            {groups.map((group) => {
              const GroupIcon = CLUSTER_ICONS[group.id];
              return (
                <section key={group.id} aria-labelledby={`cluster-${group.id}`}>
                  <div className="flex items-start gap-3 border-b border-border px-3 pb-3">
                    <span className="rounded-md border border-border bg-muted/50 p-2 text-muted-foreground"><GroupIcon aria-hidden="true" className="h-4 w-4" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2"><h3 id={`cluster-${group.id}`} className="text-sm font-semibold">{CLUSTER_LABEL[group.id]}</h3><span className="text-xs tabular-nums text-muted-foreground">{group.assets.length}</span></div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{CLUSTER_DESCRIPTION[group.id]}</p>
                    </div>
                  </div>
                  <div className="hidden grid-cols-[minmax(16rem,1.5fr)_10rem_9rem_8rem_1.5rem] gap-3 border-b border-border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground md:grid">
                    <span>Ativo</span><span>Estado</span><span>Custódia</span><span>Verificação</span><span />
                  </div>
                  <ul className="divide-y divide-border">
                    {group.assets.map((asset) => {
                      const Icon = asset.name.includes("Vídeo") ? Video : CLUSTER_ICONS[asset.cluster];
                      const selectedRow = selected?.id === asset.id;
                      return (
                        <li key={asset.id}>
                          <button type="button" onClick={() => onSelect(asset.id)} aria-pressed={selectedRow} className={cn("grid w-full gap-3 px-3 py-4 text-left outline-none transition-colors hover:bg-muted/45 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring md:grid-cols-[minmax(16rem,1.5fr)_10rem_9rem_8rem_1.5rem] md:items-center", selectedRow && "bg-primary/[0.055]")}>
                            <span className="flex min-w-0 items-start gap-3">
                              <span className={cn("mt-0.5 rounded-md border p-2", selectedRow ? "border-primary/25 bg-primary/10 text-primary" : "border-border bg-muted/50 text-muted-foreground")}><Icon aria-hidden="true" className="h-4 w-4" /></span>
                              <span className="min-w-0"><span className="block truncate text-sm font-semibold text-foreground">{asset.name}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{KIND_LABEL[asset.kind]} · {asset.platform}{asset.external.displayId ? ` · ${asset.external.displayId}` : ""}</span></span>
                            </span>
                            <span><StatePill state={asset.state} /></span>
                            <span className="text-xs text-foreground/80">{asset.owner.displayName}<span className="mt-1 block text-muted-foreground">{asset.owner.custody === "verified" ? "comprovada" : "a provar"}</span></span>
                            <VerificationMark asset={asset} />
                            <ChevronRight aria-hidden="true" className={cn("hidden h-4 w-4 text-muted-foreground md:block", selectedRow && "text-primary")} />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        ) : (
          <div className="py-14 text-center">
            <ListFilter aria-hidden="true" className="mx-auto h-6 w-6 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium">Nenhum ativo neste recorte</p>
            <p className="mt-1 text-xs text-muted-foreground">Ajuste a busca ou os filtros. O inventário original não foi alterado.</p>
          </div>
        )}
      </section>

      <aside aria-label="Detalhe do ativo" className="xl:sticky xl:top-6 xl:self-start">
        {selected ? <AssetInspector asset={selected} /> : (
          <div className="rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">Selecione um ativo para conferir identidade e evidência.</div>
        )}
      </aside>
    </div>
  );
}

function AssetInspector({ asset }: { asset: DigitalAsset }) {
  const Icon = asset.name.includes("Vídeo") ? Video : CLUSTER_ICONS[asset.cluster];
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="asset-inspector-title">
      <header className="border-b border-border p-5">
        <div className="flex items-start justify-between gap-4">
          <span className="rounded-md border border-primary/20 bg-primary/10 p-2.5 text-primary"><Icon aria-hidden="true" className="h-5 w-5" /></span>
          <StatePill state={asset.state} />
        </div>
        <h3 id="asset-inspector-title" className="mt-4 text-lg font-semibold tracking-tight">{asset.name}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{asset.summary}</p>
        {asset.external.publicUrl ? (
          <a href={asset.external.publicUrl} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
            Abrir superfície pública <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-4 border-b border-border p-5 text-xs">
        <div><dt className="text-muted-foreground">Gaveta</dt><dd className="mt-1 font-medium">{CLUSTER_LABEL[asset.cluster]}</dd></div>
        <div><dt className="text-muted-foreground">Tipo</dt><dd className="mt-1 font-medium">{KIND_LABEL[asset.kind]}</dd></div>
        <div><dt className="text-muted-foreground">Criticidade</dt><dd className="mt-1 font-medium capitalize">{asset.criticality}</dd></div>
        <div><dt className="text-muted-foreground">Dono</dt><dd className="mt-1 font-medium">{asset.owner.displayName}</dd></div>
        <div><dt className="text-muted-foreground">Última prova</dt><dd className="mt-1 font-medium">{dateLabel(asset.verification.checkedAt)}</dd></div>
      </dl>

      <div className="border-b border-border p-5">
        <div className="flex items-center gap-2"><KeyRound aria-hidden="true" className="h-4 w-4 text-muted-foreground" /><h4 className="text-sm font-semibold">Postura de acesso</h4></div>
        <div className="mt-3 flex items-center justify-between gap-3 text-xs"><span className="text-muted-foreground">Referência externa</span><span className={cn("font-medium", asset.credential.state === "not_registered" || asset.credential.state === "review_due" ? "text-warning" : "text-foreground")}>{CUSTODY_LABEL[asset.credential.state]}</span></div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{asset.credential.note}</p>
      </div>

      <div className="border-b border-border p-5">
        <div className="flex items-center gap-2"><Link2 aria-hidden="true" className="h-4 w-4 text-muted-foreground" /><h4 className="text-sm font-semibold">Relações conhecidas</h4></div>
        <ul className="mt-3 space-y-2">
          {asset.relations.map((relation) => (
            <li key={`${relation.kind}:${relation.targetId}`} className="flex items-start gap-2 text-xs">
              <ArrowRight aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><span className="font-medium text-foreground">{relation.targetLabel}</span><span className="ml-1 text-muted-foreground">({relation.state === "verified" ? "verificada" : "declarada"})</span></span>
            </li>
          ))}
        </ul>
      </div>

      <div className="border-b border-border p-5">
        <div className="flex items-center gap-2"><FileCheck2 aria-hidden="true" className="h-4 w-4 text-muted-foreground" /><h4 className="text-sm font-semibold">Evidência</h4></div>
        {asset.evidence.map((evidence) => (
          <div key={evidence.id} className="mt-3">
            <p className="text-xs leading-5 text-foreground/85">{evidence.statement}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">{evidence.sourceLabel} · {dateLabel(evidence.observedAt)}</p>
          </div>
        ))}
      </div>

      <div className="bg-muted/30 p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Próxima ação decidida</p>
        <p className="mt-2 text-sm leading-6">{asset.nextAction}</p>
      </div>
    </section>
  );
}

function RelationsView({ assets }: { assets: DigitalAsset[] }) {
  const relations = assets.flatMap((asset) => asset.relations.map((relation) => ({ source: asset, relation })));
  return (
    <section aria-labelledby="relations-heading">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Grafo operacional</p>
        <h2 id="relations-heading" className="mt-1 text-2xl font-semibold tracking-tight">O ativo só ganha valor quando se conecta</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Este recorte mostra relações declaradas e verificadas. Ele não cria nós no grafo enquanto a persistência não existir.</p>
      </div>
      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <div className="hidden grid-cols-[minmax(15rem,1fr)_10rem_minmax(15rem,1fr)_8rem] gap-4 border-b border-border bg-muted/35 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground md:grid">
          <span>Origem</span><span>Relação</span><span>Destino</span><span>Prova</span>
        </div>
        <ul className="divide-y divide-border">
          {relations.map(({ source, relation }) => (
            <li key={`${source.id}:${relation.kind}:${relation.targetId}`} className="grid gap-2 px-4 py-4 text-sm md:grid-cols-[minmax(15rem,1fr)_10rem_minmax(15rem,1fr)_8rem] md:items-center md:gap-4">
              <span className="font-medium">{source.name}</span>
              <span className="font-mono text-[11px] text-muted-foreground">{relation.kind}</span>
              <span className="flex items-center gap-2"><ArrowRight aria-hidden="true" className="h-3.5 w-3.5 text-primary" />{relation.targetLabel}</span>
              <span className={cn("text-xs", relation.state === "verified" ? "text-success" : "text-warning")}>{relation.state === "verified" ? "verificada" : "declarada"}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function ReviewsView({ assets }: { assets: DigitalAsset[] }) {
  const queue = assets.filter((asset) =>
    asset.verification.state !== "verified" ||
    asset.owner.custody !== "verified" ||
    ["not_registered", "review_due"].includes(asset.credential.state),
  );
  return (
    <section aria-labelledby="reviews-heading">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Fila de conferência</p>
        <h2 id="reviews-heading" className="mt-1 text-2xl font-semibold tracking-tight">Lacunas que impedem confiança operacional</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Prioridade combina criticidade, propriedade, frescor e acesso. Ausência continua ausência, nunca aprovação silenciosa.</p>
      </div>
      <ol className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        {queue.map((asset, index) => (
          <li key={asset.id} className="grid gap-4 border-b border-border px-4 py-5 last:border-b-0 md:grid-cols-[2rem_minmax(0,1fr)_13rem] md:items-start">
            <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-muted text-xs font-semibold tabular-nums">{index + 1}</span>
            <div>
              <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{asset.name}</h3><StatePill state={asset.state} /></div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{asset.nextAction}</p>
            </div>
            <div className="space-y-2 text-xs">
              <VerificationMark asset={asset} />
              <p className="text-muted-foreground">Custódia: {asset.owner.custody === "verified" ? "comprovada" : "a provar"}</p>
              <p className="text-muted-foreground">Acesso: {CUSTODY_LABEL[asset.credential.state]}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ContractView() {
  const fields = [
    ["Identidade", "tipo, plataforma, ID público sanitizado, URL e projeto"],
    ["Custódia", "dono declarado, operador e estado da comprovação"],
    ["Estado", "declarado, verificado, pronto, ativo, restrito, inativo ou aposentado"],
    ["Capacidades", "o que o ativo consegue produzir, distribuir, comprar ou monetizar"],
    ["Evidência", "afirmação, procedência, data e responsável pela conferência"],
    ["Relações", "dependências e vínculos com projetos, canais, contas, engines e serviços"],
    ["Acesso", "somente postura e provedor externo, sem locator ou material sensível"],
    ["Próxima ação", "uma decisão concreta que tira o ativo da inércia"],
  ];
  const phases = ["Contrato público", "Schema privado", "API administrativa", "Interface de escrita", "Importação e grafo"];
  return (
    <section aria-labelledby="contract-heading" className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Contrato público v1</p>
        <h2 id="contract-heading" className="mt-1 text-2xl font-semibold tracking-tight">O que um ativo precisa provar</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">Este contrato poderá chegar ao navegador. O locator do cofre e qualquer material secreto pertencem a uma fronteira administrativa separada.</p>
        <dl className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
          {fields.map(([name, description]) => (
            <div key={name} className="grid gap-1 border-b border-border px-4 py-4 last:border-b-0 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-4">
              <dt className="text-sm font-semibold">{name}</dt><dd className="text-sm leading-6 text-muted-foreground">{description}</dd>
            </div>
          ))}
        </dl>
        <section className="mt-8" aria-labelledby="asset-type-catalog">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Catálogo de cadastro</p>
          <h3 id="asset-type-catalog" className="mt-1 text-lg font-semibold tracking-tight">Tipos organizados por gaveta</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">A futura tela de cadastro começa pela gaveta e só então mostra os tipos compatíveis. Isso impede listas técnicas longas e classificações contraditórias.</p>
          <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
            {ASSET_CLUSTERS.map((cluster) => (
              <div key={cluster} className="grid gap-2 border-b border-border px-4 py-4 last:border-b-0 md:grid-cols-[14rem_minmax(0,1fr)] md:gap-5">
                <div><p className="text-sm font-semibold">{CLUSTER_LABEL[cluster]}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{CLUSTER_DESCRIPTION[cluster]}</p></div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(KIND_LABEL).filter(([kind]) => KIND_CLUSTER[kind as AssetKind] === cluster).map(([kind, label]) => <span key={kind} className="rounded-md border border-border bg-muted/35 px-2.5 py-1.5 text-xs text-foreground/85">{label}</span>)}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
      <aside className="space-y-6">
        <section className="rounded-lg border border-success/25 bg-success/5 p-5">
          <div className="flex items-center gap-2 text-success"><ShieldCheck aria-hidden="true" className="h-4 w-4" /><h3 className="text-sm font-semibold">Fronteira obrigatória</h3></div>
          <ul className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
            <li>Senha, chave privada e códigos nunca entram.</li>
            <li>Token e TOTP nunca chegam ao browser.</li>
            <li>O grafo recebe postura, não locator.</li>
            <li>Acesso é auditado pelo backend.</li>
          </ul>
        </section>
        <section>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Ordem de construção</p>
          <ol className="mt-3 space-y-3">
            {phases.map((phase, index) => (
              <li key={phase} className="flex items-center gap-3 text-sm"><span className="flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-[11px] font-semibold">{index + 1}</span>{phase}</li>
            ))}
          </ol>
        </section>
      </aside>
    </section>
  );
}

export function AssetVaultContent() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("visao") as VaultView | null;
  const view: VaultView = requested && VALID_VIEWS.has(requested) ? requested : "inventory";
  const selectedId = params.get("ativo") || INITIAL_ASSETS[0]?.id || null;

  const setView = (next: VaultView) => {
    const nextParams = new URLSearchParams(params);
    if (next === "inventory") nextParams.delete("visao");
    else nextParams.set("visao", next);
    setParams(nextParams, { replace: true });
  };
  const setSelected = (assetId: string) => {
    const nextParams = new URLSearchParams(params);
    nextParams.set("ativo", assetId);
    nextParams.delete("visao");
    setParams(nextParams, { replace: true });
  };

  return (
    <div className="mx-auto w-full max-w-[1540px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <header className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <p className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground"><Vault aria-hidden="true" className="h-3.5 w-3.5 text-primary" />Patrimônio operacional</p>
          <h1 className="mt-3 text-3xl font-bold tracking-[-0.035em] sm:text-4xl">Cofre de Ativos</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground sm:text-base">Uma casa para saber o que a VOLC possui, quem cuida, o que está comprovado e qual ativo precisa sair da inércia.</p>
        </div>
        <div className="text-xs text-muted-foreground lg:text-right">
          <p className="font-medium text-foreground">Contrato v1 · leitura editorial</p>
          <p className="mt-1">Banco e escrita entram na próxima etapa</p>
          <p className="mt-1 inline-flex items-center gap-1.5 lg:justify-end"><span className="h-2 w-2 rounded-full bg-warning" />Nenhuma credencial armazenada</p>
        </div>
      </header>

      <Pulse assets={INITIAL_ASSETS} />
      <SecurityBoundary />

      <nav aria-label="Lentes do Cofre de Ativos" className="mt-6 overflow-x-auto border-b border-border">
        <div role="tablist" className="flex min-w-max gap-1">
          {VIEWS.map((item) => {
            const selected = view === item.id;
            return (
              <button key={item.id} role="tab" type="button" aria-selected={selected} onClick={() => setView(item.id)} className={cn("relative inline-flex h-11 items-center gap-2 px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", selected && "text-foreground")}>
                <item.icon aria-hidden="true" className={cn("h-4 w-4", selected && "text-primary")} />{item.label}
                {item.id === "reviews" ? <span className="rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-semibold text-warning">{INITIAL_ASSETS.filter((asset) => asset.verification.state !== "verified" || asset.owner.custody !== "verified" || ["not_registered", "review_due"].includes(asset.credential.state)).length}</span> : null}
                {selected ? <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary" /> : null}
              </button>
            );
          })}
        </div>
      </nav>

      <main role="tabpanel" className="py-7">
        {view === "inventory" ? <Inventory assets={INITIAL_ASSETS} selectedId={selectedId} onSelect={setSelected} /> : null}
        {view === "relations" ? <RelationsView assets={INITIAL_ASSETS} /> : null}
        {view === "reviews" ? <ReviewsView assets={INITIAL_ASSETS} /> : null}
        {view === "contract" ? <ContractView /> : null}
      </main>

      <footer className="flex flex-col gap-2 border-t border-border py-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span className="inline-flex items-center gap-1.5"><Database aria-hidden="true" className="h-3.5 w-3.5" />Fonte atual: curadoria e observações já comprovadas.</span>
        <span>Persistência futura: Supabase oficial, schema privado e API administrativa.</span>
      </footer>
    </div>
  );
}
