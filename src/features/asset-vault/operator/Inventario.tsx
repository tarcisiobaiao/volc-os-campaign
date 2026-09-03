import * as React from "react";
import {
  Bot, ChevronRight, Database, Globe2, Image as ImageIcon, Megaphone,
  Network, Search, Vault, Waypoints,
} from "lucide-react";
import { cn } from "@/lib/utils";
import * as cofre from "../cofreApi";
import {
  ASSET_KINDS, CLUSTER_DESCRIPTION, KIND_CLUSTER, KIND_LABEL, STATE_LABEL,
  type AssetCluster, type AssetKind,
} from "../contract";
import { ENTRADA, FOCO, HIT, PRESSIONAR } from "./chrome";
import { EstadoSemCorrespondencia, EstadoVazio } from "./Estados";
import { rotuloDeVerificacao } from "./visao";

const CLUSTER_ICONS: Record<string, typeof Vault> = {
  social_presence: Megaphone,
  paid_media: Network,
  web_properties: Globe2,
  communities: Bot,
  creative_production: ImageIcon,
  automation: Waypoints,
  infrastructure: Database,
};

function Marca({ estado }: { estado: string }) {
  const palavra = rotuloDeVerificacao(estado);
  const tom =
    estado === "verified" ? "text-success" :
    estado === "expired" || estado === "failed" ? "text-destructive" :
    estado === "blocked" ? "text-warning" :
    "text-muted-foreground";
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", tom)}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {palavra}
    </span>
  );
}

function Estado({ state }: { state: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-border bg-muted/50 px-2 py-1 text-[11px] font-semibold">
      {STATE_LABEL[state as keyof typeof STATE_LABEL] ?? state}
    </span>
  );
}

export function Inventario({
  inventario, selecionado, aoSelecionar, aoCadastrar,
}: {
  inventario: cofre.Inventario;
  selecionado: string | null;
  aoSelecionar: (id: string) => void;
  aoCadastrar: () => void;
}) {
  const [busca, setBusca] = React.useState("");
  const [gaveta, setGaveta] = React.useState<string>("all");
  const [tipo, setTipo] = React.useState<string>("all");
  const [estado, setEstado] = React.useState<string>("all");

  const normal = busca.trim().toLocaleLowerCase("pt-BR");
  const filtrados = inventario.ativos.filter((a) => {
    if (gaveta !== "all" && a.cluster !== gaveta) return false;
    if (tipo !== "all" && a.kind !== tipo) return false;
    if (estado !== "all" && a.estado !== estado) return false;
    if (!normal) return true;
    return [a.nome, a.plataforma, a.projeto, a.vertical, ...(a.tags ?? [])]
      .filter(Boolean).join(" ").toLocaleLowerCase("pt-BR").includes(normal);
  });

  const grupos = inventario.gavetas
    .slice().sort((a, b) => a.ordem - b.ordem)
    .map((g) => ({ gaveta: g, ativos: filtrados.filter((a) => a.cluster === g.cluster) }))
    .filter((g) => g.ativos.length > 0);

  const tiposDisponiveis = ASSET_KINDS.filter((k) => gaveta === "all" || KIND_CLUSTER[k] === gaveta);
  const escolherGaveta = (proxima: string) => {
    setGaveta(proxima);
    if (tipo !== "all" && proxima !== "all" && KIND_CLUSTER[tipo as AssetKind] !== proxima) setTipo("all");
  };

  return (
    <section aria-labelledby="asset-list-heading" className="min-w-0">
      <div className="border-b border-border pb-4">
        <p className="kicker">Inventário persistido</p>
        <h2 id="asset-list-heading" className="mt-1 font-display text-xl font-semibold tracking-tight">Ativos conhecidos</h2>
        <p className="mt-1 text-sm tabular-nums text-muted-foreground">{filtrados.length} de {inventario.ativos.length}</p>
      </div>

      <div className="border-b border-border py-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Organizar por gaveta</p>
        <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Gavetas do Cofre">
          <button type="button" onClick={() => escolherGaveta("all")} aria-pressed={gaveta === "all"}
            className={cn("shrink-0 rounded-md border px-3 text-xs font-medium", HIT, FOCO, PRESSIONAR,
              gaveta === "all" ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
            Todos <span className="ml-1 tabular-nums">{inventario.ativos.length}</span>
          </button>
          {inventario.gavetas.slice().sort((a, b) => a.ordem - b.ordem).map((g) => {
            const Icon = CLUSTER_ICONS[g.cluster] ?? Vault;
            return (
              <button key={g.cluster} type="button" onClick={() => escolherGaveta(g.cluster)} aria-pressed={gaveta === g.cluster}
                className={cn("inline-flex shrink-0 items-center gap-2 rounded-md border px-3 text-xs font-medium", HIT, FOCO, PRESSIONAR,
                  gaveta === g.cluster ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                <Icon aria-hidden="true" className="h-3.5 w-3.5" />{g.rotulo} <span className="tabular-nums">{g.total}</span>
              </button>
            );
          })}
        </div>
        {gaveta !== "all" ? (
          <p className="mt-2 text-xs text-muted-foreground text-pretty">
            {inventario.gavetas.find((g) => g.cluster === gaveta)?.descricao
              ?? CLUSTER_DESCRIPTION[gaveta as AssetCluster]}
          </p>
        ) : null}
      </div>

      <div className="grid gap-2 border-b border-border py-4 md:grid-cols-[minmax(14rem,1fr)_12rem_11rem]">
        <label className="relative block">
          <span className="sr-only">Buscar ativos</span>
          <Search aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input value={busca} onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar ativo, plataforma ou projeto"
            className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        </label>
        <label>
          <span className="sr-only">Filtrar por família</span>
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} className={ENTRADA}>
            <option value="all">Todas as famílias</option>
            {tiposDisponiveis.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </label>
        <label>
          <span className="sr-only">Filtrar por estado</span>
          <select value={estado} onChange={(e) => setEstado(e.target.value)} className={ENTRADA}>
            <option value="all">Todos os estados</option>
            {Object.entries(STATE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
      </div>

      {filtrados.length ? (
        <>
        <section className="pt-5" aria-label="Ativos encontrados">
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[52rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                  <th className="px-3 py-2 font-semibold">Identidade</th>
                  <th className="px-3 py-2 font-semibold">Tipo</th>
                  <th className="px-3 py-2 font-semibold">Owner</th>
                  <th className="px-3 py-2 font-semibold">Estado</th>
                  <th className="px-3 py-2 font-semibold">Verificação</th>
                  <th className="px-3 py-2 font-semibold">Relações</th>
                  <th className="px-3 py-2 font-semibold">Revisão</th>
                  <th className="px-3 py-2 font-semibold"><span className="sr-only">Ação</span></th>
                </tr>
              </thead>
              {grupos.map((grupo) => (
                <tbody key={grupo.gaveta.cluster}>
                  <tr className="bg-muted/40">
                    <th scope="colgroup" colSpan={8} className="px-3 py-2 text-left text-xs font-semibold">
                      {grupo.gaveta.rotulo}
                      <span className="ml-2 tabular-nums font-normal text-muted-foreground">{grupo.ativos.length}</span>
                    </th>
                  </tr>
                  {grupo.ativos.map((a) => {
                    const marcado = selecionado === a.ativo_id;
                    return (
                      <tr key={a.ativo_id}
                        className={cn("border-b border-border", marcado && "bg-primary/[0.055]")}>
                        <td className="max-w-[16rem] px-3 py-3">
                          <button type="button" onClick={() => aoSelecionar(a.ativo_id)} aria-pressed={marcado}
                            className={cn("block min-w-0 text-left", FOCO, PRESSIONAR)}>
                            <span className="block truncate font-semibold">{a.nome}</span>
                            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                              {a.plataforma}{a.display_id ? ` · ${a.display_id}` : ""}
                            </span>
                          </button>
                        </td>
                        <td className="px-3 py-3 text-xs">{a.tipo_rotulo}</td>
                        <td className="px-3 py-3 text-xs">
                          {a.dono_nome}
                          <span className="mt-0.5 block text-muted-foreground">
                            {a.dono_custodia === "verified" ? "comprovada" : "a provar"}
                          </span>
                        </td>
                        <td className="px-3 py-3"><Estado state={a.estado} /></td>
                        <td className="px-3 py-3"><Marca estado={a.verificacao_estado} /></td>
                        <td className="px-3 py-3 tabular-nums text-xs">
                          {a.relacoes.length
                            ? `${a.relacoes.length}`
                            : <span className="text-muted-foreground">incompleta</span>}
                        </td>
                        <td className="px-3 py-3 tabular-nums text-xs">#{a.revisao_atual}</td>
                        <td className="px-3 py-3">
                          <button type="button" onClick={() => aoSelecionar(a.ativo_id)}
                            className={cn("inline-flex items-center text-xs font-medium text-primary", HIT, FOCO, PRESSIONAR)}
                            aria-label={`Abrir ${a.nome}`}>
                            Abrir <ChevronRight aria-hidden="true" className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              ))}
            </table>
          </div>

        </section>
          <div className="space-y-6 md:hidden" aria-label="Ativos no telefone">
            {grupos.map((grupo) => (
              <section key={grupo.gaveta.cluster} aria-labelledby={`gaveta-${grupo.gaveta.cluster}`}>
                <h3 id={`gaveta-${grupo.gaveta.cluster}`} className="border-b border-border px-1 pb-2 text-sm font-semibold">
                  {grupo.gaveta.rotulo}
                  <span className="ml-2 tabular-nums text-muted-foreground">{grupo.ativos.length}</span>
                </h3>
                <ul className="divide-y divide-border">
                  {grupo.ativos.map((a) => {
                    const marcado = selecionado === a.ativo_id;
                    return (
                      <li key={a.ativo_id}>
                        <button type="button" onClick={() => aoSelecionar(a.ativo_id)} aria-pressed={marcado}
                          className={cn("flex min-h-10 w-full flex-col gap-2 px-1 py-4 text-left", FOCO, PRESSIONAR, marcado && "bg-primary/[0.055]")}>
                          <span className="font-semibold">{a.nome}</span>
                          <span className="text-xs text-muted-foreground">{a.tipo_rotulo} · {a.plataforma}</span>
                          <span className="flex flex-wrap items-center gap-2 text-xs">
                            <Estado state={a.estado} />
                            <Marca estado={a.verificacao_estado} />
                            <span>{a.dono_nome}</span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        </>
      ) : inventario.ativos.length === 0 ? (
        <EstadoVazio aoCadastrar={aoCadastrar} />
      ) : (
        <EstadoSemCorrespondencia />
      )}
    </section>
  );
}

