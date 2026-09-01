import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive, ArrowRight, Bot, CheckCircle2, ChevronRight, CircleAlert, CircleDashed,
  Clock3, Database, ExternalLink, FileCheck2, Fingerprint, Globe2, Image as ImageIcon,
  KeyRound, Link2, ListFilter, Loader2, LockKeyhole, Megaphone, Network, PlugZap,
  Plus, Search, ShieldCheck, Undo2, Vault, Waypoints, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import * as cofre from "./cofreApi";
import {
  CLUSTER_DESCRIPTION, CLUSTER_LABEL, CUSTODY_LABEL, KIND_CLUSTER, KIND_LABEL,
  STATE_LABEL, VERIFICATION_LABEL, ASSET_CLUSTERS, ASSET_KINDS,
  type AssetCluster, type AssetKind, type AssetState, type VerificationState,
} from "./contract";

/**
 * O Cofre de Ativos, agora contra dado real.
 *
 * ## O que mudou, e por que importa
 *
 * Até 01/09/2026 esta tela lia `fixtures.ts` — um retrato editorial de oito
 * ativos, validado pelo contrato público e honesto sobre ser um retrato. O
 * problema não era a fixture: era ela ser a ÚNICA fonte. Uma tela que sempre
 * mostra os mesmos oito ativos não distingue "o Cofre está vazio" de "o Cofre
 * não respondeu", porque nunca esteve vazio nem deixou de responder.
 *
 * Agora a fonte é `/api/cofre`, e a fixture **não é fallback**. Ela ficou onde
 * já estava, servindo teste hermético e o contrato público. Se a API falhar,
 * esta tela diz que falhou — mostrar o retrato editorial nesse momento seria
 * inventar um inventário e deixar a pessoa concluir que está tudo no ar.
 *
 * ## Os seis estados, e por que nenhum é redundante
 *
 *   carregando        ainda não sei
 *   indisponível      o Cofre não respondeu (503) — diferente de vazio
 *   sem permissão     403: a identidade vale, o papel não
 *   sem sessão        401: entre de novo (é outra ação, não a mesma)
 *   vazio             o Cofre respondeu, e não há ativo — um FATO
 *   com dado          o inventário
 *
 * Colapsar "indisponível" em "vazio" é o defeito clássico de painel: `[]` na
 * tela afirma "você não tem ativos" com a mesma cara com que afirmaria "você
 * tem trinta". As gavetas vêm do servidor justamente para que o vazio continue
 * mostrando a ESTRUTURA — sete gavetas com contagem zero — em vez de uma página
 * em branco que parece defeito.
 */

type VaultView = "inventory" | "relations" | "reviews" | "contract";

const VIEWS: Array<{ id: VaultView; label: string; icon: typeof Vault }> = [
  { id: "inventory", label: "Inventário", icon: Archive },
  { id: "reviews", label: "Revisões", icon: FileCheck2 },
  { id: "relations", label: "Relações", icon: Network },
  { id: "contract", label: "Contrato", icon: Fingerprint },
];
const VALID_VIEWS = new Set<VaultView>(VIEWS.map((v) => v.id));

const STATE_TONE: Record<string, string> = {
  declared: "border-warning/30 bg-warning/10 text-warning",
  verified: "border-info/30 bg-info/10 text-info",
  ready: "border-primary/30 bg-primary/10 text-primary",
  active: "border-success/30 bg-success/10 text-success",
  restricted: "border-warning/30 bg-warning/10 text-warning",
  inactive: "border-border bg-muted text-muted-foreground",
  retired: "border-border bg-muted text-muted-foreground",
};

const VERIFICATION_TONE: Record<string, string> = {
  verified: "text-success",
  partial: "text-warning",
  unverified: "text-muted-foreground",
  expired: "text-destructive",
  failed: "text-destructive",
  blocked: "text-warning",
};

/**
 * Rótulos dos seis estados. Vem do contrato público — que passou a ter os seis
 * em 01/09/2026, depois de uma revisão adversarial mostrar que ele aceitava
 * quatro enquanto o banco gravava seis.
 */
const VERIFICATION_TEXTO: Record<string, string> = VERIFICATION_LABEL;

const CLUSTER_ICONS: Record<string, typeof Vault> = {
  social_presence: Megaphone,
  paid_media: Network,
  web_properties: Globe2,
  communities: Bot,
  creative_production: ImageIcon,
  automation: Waypoints,
  infrastructure: Database,
};

function dataLegivel(valor?: string | null) {
  if (!valor) return "Ainda não conferido";
  const data = new Date(valor.length <= 10 ? `${valor}T12:00:00` : valor);
  if (Number.isNaN(data.getTime())) return valor;
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(data);
}

function StatePill({ state }: { state: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
      STATE_TONE[state] ?? "border-border bg-muted text-muted-foreground")}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {STATE_LABEL[state as AssetState] ?? state}
    </span>
  );
}

function MarcaDeVerificacao({ estado }: { estado: string }) {
  const Icon = estado === "verified" ? CheckCircle2
    : estado === "expired" || estado === "failed" ? CircleAlert : CircleDashed;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs", VERIFICATION_TONE[estado] ?? "text-muted-foreground")}>
      <Icon aria-hidden="true" className="h-3.5 w-3.5" />
      {VERIFICATION_TEXTO[estado] ?? estado}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Os estados que não são "dado"
// ─────────────────────────────────────────────────────────────────────────────

function Moldura({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-7xl p-4 sm:p-6">{children}</div>;
}

function Carregando() {
  return (
    <div className="space-y-4" role="status" aria-label="Carregando o inventário">
      <div className="h-24 animate-pulse rounded-lg border border-border bg-muted/40" />
      <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 xl:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-16 animate-pulse bg-card" />)}
      </div>
      <div className="space-y-2">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-md border border-border bg-muted/30" />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">Consultando o Cofre…</p>
    </div>
  );
}

interface AvisoProps {
  titulo: string;
  texto: string;
  tom?: "erro" | "atencao" | "neutro";
  icone: typeof Vault;
  acao?: { rotulo: string; aoClicar: () => void };
  codigo?: string;
}

function Aviso({ titulo, texto, tom = "neutro", icone: Icon, acao, codigo }: AvisoProps) {
  const borda = tom === "erro" ? "border-destructive/35" : tom === "atencao" ? "border-warning/35" : "border-border";
  const fundo = tom === "erro" ? "bg-destructive/10 text-destructive" : tom === "atencao" ? "bg-warning/10 text-warning" : "bg-muted text-muted-foreground";
  return (
    <section className={cn("rounded-lg border bg-card px-5 py-10 text-center", borda)} role="alert">
      <span className={cn("mx-auto flex h-11 w-11 items-center justify-center rounded-full", fundo)}>
        <Icon aria-hidden="true" className="h-5 w-5" />
      </span>
      <h2 className="mt-4 text-lg font-semibold">{titulo}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{texto}</p>
      {acao ? (
        <button type="button" onClick={acao.aoClicar}
          className="mt-4 inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium hover:bg-muted">
          {acao.rotulo}
        </button>
      ) : null}
      {/* O código é para quem for investigar, não para quem está operando. */}
      {codigo ? <p className="mt-3 text-[11px] uppercase tracking-[0.1em] text-muted-foreground">código {codigo}</p> : null}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Formulários
// ─────────────────────────────────────────────────────────────────────────────

function Campo({ rotulo, ajuda, children }: { rotulo: string; ajuda?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-foreground">{rotulo}</span>
      {children}
      {ajuda ? <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">{ajuda}</span> : null}
    </label>
  );
}

const ENTRADA = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";
const AREA = "min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Painel({ titulo, descricao, aoFechar, children }: {
  titulo: string; descricao: string; aoFechar: () => void; children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card" aria-label={titulo}>
      <header className="flex items-start justify-between gap-4 border-b border-border p-5">
        <div>
          <h3 className="text-sm font-semibold">{titulo}</h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">{descricao}</p>
        </div>
        <button type="button" onClick={aoFechar} aria-label="Fechar" className="rounded-md p-1 text-muted-foreground hover:bg-muted">
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function BotaoDeEnvio({ enviando, rotulo }: { enviando: boolean; rotulo: string }) {
  return (
    <button type="submit" disabled={enviando}
      className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">
      {enviando ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
      {rotulo}
    </button>
  );
}

function ErroDoFormulario({ erro }: { erro: unknown }) {
  if (!erro) return null;
  const mensagem = erro instanceof Error ? erro.message : "Não foi possível concluir.";
  return (
    <p role="alert" className="mt-3 rounded-md border border-destructive/35 bg-destructive/10 px-3 py-2 text-xs text-destructive">
      {mensagem}
    </p>
  );
}

function FormularioDeCadastro({ aoFechar, aoConcluir }: { aoFechar: () => void; aoConcluir: (id: string) => void }) {
  const { toast } = useToast();
  const [kind, setKind] = React.useState<AssetKind>("facebook_page");
  const [form, setForm] = React.useState({
    ativo_id: "", nome: "", plataforma: "", estado: "declared", criticidade: "medium",
    resumo: "", dono_nome: "", dono_custodia: "declared", projeto: "", vertical: "",
    display_id: "", url_publica: "", capacidades: "", tags: "", proxima_acao: "",
  });
  const mudar = (campo: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [campo]: e.target.value }));

  const enviar = useMutation({
    mutationFn: async () => {
      const ativo: Record<string, unknown> = {
        ativo_id: form.ativo_id.trim(),
        kind,
        // A gaveta é DERIVADA do tipo, não escolhida: o contrato diz que um
        // tipo pertence a exatamente uma gaveta, e oferecer as duas escolhas
        // convidaria a contradição que o banco recusa por FK.
        cluster: KIND_CLUSTER[kind],
        nome: form.nome.trim(),
        plataforma: form.plataforma.trim(),
        estado: form.estado,
        criticidade: form.criticidade,
        resumo: form.resumo.trim(),
        dono_nome: form.dono_nome.trim(),
        dono_custodia: form.dono_custodia,
        capacidades: form.capacidades.split(",").map((c) => c.trim()).filter(Boolean),
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        proxima_acao: form.proxima_acao.trim(),
      };
      for (const opcional of ["projeto", "vertical", "display_id", "url_publica"] as const) {
        const valor = form[opcional].trim();
        if (valor) ativo[opcional] = valor;
      }
      return cofre.cadastrarAtivo({
        chave_idempotencia: cofre.chaveDoAto("cadastro", ativo.ativo_id as string, ativo),
        motivo: "cadastro pela tela do Cofre de Ativos",
        ativo,
      });
    },
    onSuccess: (recibo) => {
      toast({
        title: recibo.idempotente ? "Este cadastro já existia" : "Ativo cadastrado",
        description: recibo.idempotente
          ? "O Cofre reconheceu o reenvio e devolveu o mesmo recibo. Nada foi duplicado."
          : `Revisão ${recibo.revisao} registrada na trilha.`,
      });
      if (recibo.ativo_id) aoConcluir(recibo.ativo_id);
    },
  });

  return (
    <Painel titulo="Cadastrar ativo" aoFechar={aoFechar}
      descricao="Identidade, dono e próxima ação. Senha, token, MFA e chave não entram aqui — a referência de acesso é registrada depois, no ativo, e aponta para o cofre externo.">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); enviar.mutate(); }}>
        <Campo rotulo="Identificador" ajuda="minúsculas, dígitos, ':', '_' e '-' — ex.: asset:facebook-page:piloto">
          <input required value={form.ativo_id} onChange={mudar("ativo_id")} className={ENTRADA} placeholder="asset:facebook-page:piloto" />
        </Campo>
        <Campo rotulo="Nome">
          <input required value={form.nome} onChange={mudar("nome")} className={ENTRADA} />
        </Campo>
        <Campo rotulo="Tipo" ajuda={`Gaveta: ${CLUSTER_LABEL[KIND_CLUSTER[kind]]} (derivada do tipo)`}>
          <select value={kind} onChange={(e) => setKind(e.target.value as AssetKind)} className={ENTRADA}>
            {ASSET_KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Plataforma">
          <input required value={form.plataforma} onChange={mudar("plataforma")} className={ENTRADA} placeholder="Meta, Google Ads, WordPress…" />
        </Campo>
        <Campo rotulo="Estado">
          <select value={form.estado} onChange={mudar("estado")} className={ENTRADA}>
            {Object.entries(STATE_LABEL).filter(([v]) => v !== "retired").map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Criticidade">
          <select value={form.criticidade} onChange={mudar("criticidade")} className={ENTRADA}>
            <option value="low">Baixa</option><option value="medium">Média</option>
            <option value="high">Alta</option><option value="critical">Crítica</option>
          </select>
        </Campo>
        <Campo rotulo="Dono">
          <input required value={form.dono_nome} onChange={mudar("dono_nome")} className={ENTRADA} />
        </Campo>
        <Campo rotulo="Custódia" ajuda="declarada é o que alguém afirmou; comprovada é o que foi conferido">
          <select value={form.dono_custodia} onChange={mudar("dono_custodia")} className={ENTRADA}>
            <option value="declared">Declarada</option><option value="verified">Comprovada</option>
            <option value="unassigned">Sem dono definido</option>
          </select>
        </Campo>
        <Campo rotulo="Projeto (opcional)"><input value={form.projeto} onChange={mudar("projeto")} className={ENTRADA} /></Campo>
        <Campo rotulo="Vertical (opcional)"><input value={form.vertical} onChange={mudar("vertical")} className={ENTRADA} /></Campo>
        <Campo rotulo="ID de exibição (opcional)" ajuda="já sanitizado, como •••-•••-1692. Nunca o ID cru quando ele for sensível.">
          <input value={form.display_id} onChange={mudar("display_id")} className={ENTRADA} />
        </Campo>
        <Campo rotulo="Endereço público (opcional)" ajuda="somente HTTP(S)">
          <input value={form.url_publica} onChange={mudar("url_publica")} className={ENTRADA} placeholder="https://…" />
        </Campo>
        <div className="md:col-span-2">
          <Campo rotulo="Resumo" ajuda="10 a 800 caracteres. O que este ativo é, e o que ainda não foi conferido.">
            <textarea required value={form.resumo} onChange={mudar("resumo")} className={AREA} />
          </Campo>
        </div>
        <Campo rotulo="Capacidades" ajuda="separadas por vírgula; pelo menos uma">
          <input required value={form.capacidades} onChange={mudar("capacidades")} className={ENTRADA} placeholder="Publicação orgânica, Distribuição de vídeo" />
        </Campo>
        <Campo rotulo="Tags (opcional)" ajuda="separadas por vírgula">
          <input value={form.tags} onChange={mudar("tags")} className={ENTRADA} />
        </Campo>
        <div className="md:col-span-2">
          <Campo rotulo="Próxima ação" ajuda="o ato concreto seguinte, não uma intenção genérica">
            <textarea required value={form.proxima_acao} onChange={mudar("proxima_acao")} className={AREA} />
          </Campo>
        </div>
        <div className="md:col-span-2">
          <BotaoDeEnvio enviando={enviar.isPending} rotulo="Cadastrar ativo" />
          <ErroDoFormulario erro={enviar.error} />
        </div>
      </form>
    </Painel>
  );
}

function FormularioDeRevisao({ ativo, aoFechar, aoConcluir }: {
  ativo: cofre.DetalheDoAtivo; aoFechar: () => void; aoConcluir: () => void;
}) {
  const { toast } = useToast();
  const [form, setForm] = React.useState({
    nome: ativo.nome, plataforma: ativo.plataforma, estado: ativo.estado,
    criticidade: ativo.criticidade, resumo: ativo.resumo,
    dono_nome: ativo.dono_nome, dono_custodia: ativo.dono_custodia,
    projeto: ativo.projeto ?? "", vertical: ativo.vertical ?? "",
    display_id: ativo.display_id ?? "", url_publica: ativo.url_publica ?? "",
    capacidades: (ativo.capacidades ?? []).join(", "), tags: (ativo.tags ?? []).join(", "),
    proxima_acao: ativo.proxima_acao,
  });
  const [motivo, setMotivo] = React.useState("");
  const mudar = (campo: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [campo]: e.target.value }));

  /**
   * Só o que MUDOU viaja.
   *
   * Mandar o formulário inteiro faria toda revisão reescrever todos os campos —
   * e a trilha registraria "mudou tudo" mesmo quando alguém corrigiu uma vírgula
   * no resumo. Pior: um campo que o formulário carregou vazio (porque a API não
   * o devolveu) apagaria o valor real. O backend é patch, e o cliente precisa
   * falar patch.
   */
  const mudancas = React.useMemo(() => {
    const delta: Record<string, unknown> = {};
    const atual: Record<string, string> = {
      nome: ativo.nome, plataforma: ativo.plataforma, estado: ativo.estado,
      criticidade: ativo.criticidade, resumo: ativo.resumo, dono_nome: ativo.dono_nome,
      dono_custodia: ativo.dono_custodia, projeto: ativo.projeto ?? "",
      vertical: ativo.vertical ?? "", display_id: ativo.display_id ?? "",
      url_publica: ativo.url_publica ?? "", proxima_acao: ativo.proxima_acao,
    };
    for (const [campo, valor] of Object.entries(atual)) {
      const novo = (form as Record<string, string>)[campo].trim();
      if (novo !== valor.trim()) delta[campo] = novo;
    }
    const listas: Array<[string, string[], string]> = [
      ["capacidades", ativo.capacidades ?? [], form.capacidades],
      ["tags", ativo.tags ?? [], form.tags],
    ];
    for (const [campo, antes, texto] of listas) {
      const agora = texto.split(",").map((v) => v.trim()).filter(Boolean);
      if (agora.join("|") !== antes.join("|")) delta[campo] = agora;
    }
    return delta;
  }, [ativo, form]);

  const enviar = useMutation({
    mutationFn: () => cofre.revisarAtivo(ativo.ativo_id, {
      // A chave inclui os CAMPOS mudados: sem isso, duas revisões distintas do
      // mesmo ativo no mesmo minuto compartilhariam chave, e a segunda voltaria
      // como replay da primeira — silenciosamente descartada.
      chave_idempotencia: cofre.chaveDoAto("revisao", ativo.ativo_id, { mudancas, motivo: motivo.trim() }),
      motivo: motivo.trim(),
      mudancas,
    }),
    onSuccess: (recibo) => {
      toast({
        title: recibo.idempotente ? "Esta revisão já havia sido registrada" : "Revisão registrada",
        description: recibo.idempotente
          ? "O Cofre reconheceu o reenvio e devolveu o mesmo recibo."
          : `O ativo está na revisão ${recibo.revisao}.`,
      });
      aoConcluir();
    },
  });

  const nada = Object.keys(mudancas).length === 0;

  return (
    <Painel titulo="Revisar ativo" aoFechar={aoFechar}
      descricao="Só os campos alterados viajam, e a trilha guarda o motivo. Campo não tocado preserva o valor — uma edição de nome não pode zerar a custódia comprovada.">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); enviar.mutate(); }}>
        <Campo rotulo="Nome"><input value={form.nome} onChange={mudar("nome")} className={ENTRADA} /></Campo>
        <Campo rotulo="Plataforma"><input value={form.plataforma} onChange={mudar("plataforma")} className={ENTRADA} /></Campo>
        <Campo rotulo="Estado">
          <select value={form.estado} onChange={mudar("estado")} className={ENTRADA}>
            {Object.entries(STATE_LABEL).filter(([v]) => v !== "retired").map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Criticidade">
          <select value={form.criticidade} onChange={mudar("criticidade")} className={ENTRADA}>
            <option value="low">Baixa</option><option value="medium">Média</option>
            <option value="high">Alta</option><option value="critical">Crítica</option>
          </select>
        </Campo>
        <Campo rotulo="Dono"><input value={form.dono_nome} onChange={mudar("dono_nome")} className={ENTRADA} /></Campo>
        <Campo rotulo="Custódia">
          <select value={form.dono_custodia} onChange={mudar("dono_custodia")} className={ENTRADA}>
            <option value="declared">Declarada</option><option value="verified">Comprovada</option>
            <option value="unassigned">Sem dono definido</option>
          </select>
        </Campo>
        <Campo rotulo="Projeto"><input value={form.projeto} onChange={mudar("projeto")} className={ENTRADA} /></Campo>
        <Campo rotulo="Vertical"><input value={form.vertical} onChange={mudar("vertical")} className={ENTRADA} /></Campo>
        <Campo rotulo="ID de exibição" ajuda="já sanitizado; nunca o ID cru quando ele for sensível">
          <input value={form.display_id} onChange={mudar("display_id")} className={ENTRADA} />
        </Campo>
        <Campo rotulo="Endereço público" ajuda="somente HTTP(S)">
          <input value={form.url_publica} onChange={mudar("url_publica")} className={ENTRADA} />
        </Campo>
        <div className="md:col-span-2">
          <Campo rotulo="Resumo"><textarea value={form.resumo} onChange={mudar("resumo")} className={AREA} /></Campo>
        </div>
        <Campo rotulo="Capacidades" ajuda="separadas por vírgula">
          <input value={form.capacidades} onChange={mudar("capacidades")} className={ENTRADA} />
        </Campo>
        <Campo rotulo="Tags" ajuda="separadas por vírgula">
          <input value={form.tags} onChange={mudar("tags")} className={ENTRADA} />
        </Campo>
        <div className="md:col-span-2">
          <Campo rotulo="Próxima ação"><textarea value={form.proxima_acao} onChange={mudar("proxima_acao")} className={AREA} /></Campo>
        </div>
        <div className="md:col-span-2">
          <Campo rotulo="Motivo da revisão" ajuda="o que mudou e por quê — entra na trilha append-only">
            <input required value={motivo} onChange={(e) => setMotivo(e.target.value)} className={ENTRADA} />
          </Campo>
        </div>
        <div className="md:col-span-2">
          <p className="mb-2 text-xs text-muted-foreground">
            {nada ? "Nenhum campo foi alterado." : `${Object.keys(mudancas).length} campo(s) alterado(s): ${Object.keys(mudancas).join(", ")}.`}
          </p>
          <button type="submit" disabled={enviar.isPending || nada}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">
            {enviar.isPending ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
            Registrar revisão
          </button>
          <ErroDoFormulario erro={enviar.error} />
        </div>
      </form>
    </Painel>
  );
}

function FormularioDeCredencial({ ativoId, aoFechar, aoConcluir }: {
  ativoId: string; aoFechar: () => void; aoConcluir: () => void;
}) {
  const { toast } = useToast();
  const [form, setForm] = React.useState({
    provider: "1password", nome_logico: "", localizador: "", finalidade: "",
    owner_nome: "", valido_ate: "",
  });
  const mudar = (campo: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [campo]: e.target.value }));

  const enviar = useMutation({
    mutationFn: async () => {
      const corpo: Record<string, unknown> = {
        chave_idempotencia: cofre.chaveDoAto("credencial", ativoId, form),
        provider: form.provider,
        nome_logico: form.nome_logico.trim(),
        localizador: form.localizador.trim(),
        finalidade: form.finalidade.trim(),
        owner_nome: form.owner_nome.trim(),
      };
      if (form.valido_ate) corpo.valido_ate = form.valido_ate;
      return cofre.referenciarCredencial(ativoId, corpo);
    },
    onSuccess: (recibo) => {
      toast({
        title: recibo.idempotente ? "Esta referência já existia" : "Referência registrada",
        description: "O Cofre guardou provider, nome lógico e finalidade. O valor continua só no cofre externo.",
      });
      aoConcluir();
    },
  });

  return (
    <Painel titulo="Registrar referência de acesso" aoFechar={aoFechar}
      descricao="Aqui entra o ENDEREÇO do item no cofre externo, não o segredo. O Cofre guarda provider, nome lógico, finalidade e validade; o valor nunca sai do 1Password, e este endereço não volta em nenhuma leitura desta tela.">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); enviar.mutate(); }}>
        <Campo rotulo="Cofre externo">
          <select value={form.provider} onChange={mudar("provider")} className={ENTRADA}>
            <option value="1password">1Password</option>
            <option value="bitwarden">Bitwarden</option>
            <option value="vaultwarden">Vaultwarden</option>
            <option value="passbolt">Passbolt</option>
            <option value="infisical">Infisical</option>
          </select>
        </Campo>
        <Campo rotulo="Nome lógico" ajuda="MAIÚSCULAS_COM_UNDERSCORE — ex.: FB_PAGE_ADMIN">
          <input required value={form.nome_logico} onChange={mudar("nome_logico")} className={ENTRADA} placeholder="FB_PAGE_ADMIN" />
        </Campo>
        <div className="md:col-span-2">
          <Campo rotulo="Referência"
            ajuda="No 1Password: op://<cofre>/<item>/[seção/]<campo>, com espaços em %20. Sem query string — uma referência com ?attribute=otp aponta para MFA, e MFA não entra no Cofre nem por endereço.">
            <input required value={form.localizador} onChange={mudar("localizador")} className={ENTRADA}
              placeholder="op://VOLC/Pagina%20Piloto/credential" autoComplete="off" spellCheck={false} />
          </Campo>
        </div>
        <Campo rotulo="Responsável"><input required value={form.owner_nome} onChange={mudar("owner_nome")} className={ENTRADA} /></Campo>
        <Campo rotulo="Válido até (opcional)"><input type="date" value={form.valido_ate} onChange={mudar("valido_ate")} className={ENTRADA} /></Campo>
        <div className="md:col-span-2">
          <Campo rotulo="Finalidade" ajuda="para que este acesso serve, em linguagem operacional">
            <input required value={form.finalidade} onChange={mudar("finalidade")} className={ENTRADA} />
          </Campo>
        </div>
        <div className="md:col-span-2">
          <BotaoDeEnvio enviando={enviar.isPending} rotulo="Registrar referência" />
          <ErroDoFormulario erro={enviar.error} />
        </div>
      </form>
    </Painel>
  );
}

function FormularioDeVerificacao({ ativoId, aoFechar, aoConcluir }: {
  ativoId: string; aoFechar: () => void; aoConcluir: () => void;
}) {
  const { toast } = useToast();
  const [form, setForm] = React.useState({
    alvo: "ativo", resultado: "verified", metodo: "", procedencia: "live_observation",
    evidencia: "", observado_em: new Date().toISOString().slice(0, 16), proximo_ato: "",
    nome_logico: "",
  });
  const mudar = (campo: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [campo]: e.target.value }));

  const enviar = useMutation({
    mutationFn: async () => {
      const corpo: Record<string, unknown> = {
        chave_idempotencia: cofre.chaveDoAto("verificacao", ativoId, form),
        alvo: form.alvo, resultado: form.resultado, metodo: form.metodo.trim(),
        procedencia: form.procedencia, evidencia: form.evidencia.trim(),
        observado_em: new Date(form.observado_em).toISOString(),
      };
      if (form.proximo_ato.trim()) corpo.proximo_ato = form.proximo_ato.trim();
      // Só quando o alvo é a credencial: o banco recusa verificar sem dizer
      // QUAL referência, quando o ativo tem mais de uma.
      if (form.alvo === "credencial" && form.nome_logico.trim()) {
        corpo.nome_logico = form.nome_logico.trim();
      }
      return cofre.registrarVerificacao(ativoId, corpo);
    },
    onSuccess: () => {
      toast({ title: "Verificação registrada", description: "O recibo entrou na trilha append-only." });
      aoConcluir();
    },
  });

  return (
    <Painel titulo="Registrar verificação" aoFechar={aoFechar}
      descricao="Uma prova é método, procedência e o INSTANTE em que foi observada. O campo de data não vem preenchido com 'agora' por acaso: se você conferiu ontem, mude — verificação sem carimbo correto é indistinguível de verificação de um ano atrás.">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); enviar.mutate(); }}>
        <Campo rotulo="O que foi verificado">
          <select value={form.alvo} onChange={mudar("alvo")} className={ENTRADA}>
            <option value="ativo">O ativo</option><option value="credencial">A referência de acesso</option>
            <option value="relacao">Uma relação</option><option value="engine">O engine</option>
          </select>
        </Campo>
        <Campo rotulo="Resultado" ajuda="falhou e bloqueado não são a mesma coisa que não verificado">
          <select value={form.resultado} onChange={mudar("resultado")} className={ENTRADA}>
            <option value="verified">Verificado</option><option value="partial">Verificação parcial</option>
            <option value="failed">Falhou</option><option value="blocked">Bloqueado</option>
            <option value="expired">Revisão vencida</option><option value="unverified">Não verificado</option>
          </select>
        </Campo>
        <Campo rotulo="Método"><input required value={form.metodo} onChange={mudar("metodo")} className={ENTRADA} placeholder="Business Portfolio, leitura da API, conferência manual…" /></Campo>
        <Campo rotulo="Procedência">
          <select value={form.procedencia} onChange={mudar("procedencia")} className={ENTRADA}>
            <option value="live_observation">Observação ao vivo</option>
            <option value="owner_declaration">Declaração do dono</option>
            <option value="provider_record">Registro do provedor</option>
            <option value="repository_inventory">Inventário do repositório</option>
          </select>
        </Campo>
        <Campo rotulo="Observado em" ajuda="o instante da OBSERVAÇÃO, não o do registro">
          <input required type="datetime-local" value={form.observado_em} onChange={mudar("observado_em")} className={ENTRADA} />
        </Campo>
        <Campo rotulo="Próximo ato (opcional)"><input value={form.proximo_ato} onChange={mudar("proximo_ato")} className={ENTRADA} /></Campo>
        {form.alvo === "credencial" ? (
          <div className="md:col-span-2">
            <Campo rotulo="Qual referência foi verificada"
              ajuda="o nome lógico (ex.: FB_PAGE_ADMIN). Obrigatório quando o ativo tem mais de uma referência — conferir uma não torna as outras verificadas.">
              <input value={form.nome_logico} onChange={mudar("nome_logico")} className={ENTRADA} placeholder="FB_PAGE_ADMIN" />
            </Campo>
          </div>
        ) : null}
        <div className="md:col-span-2">
          <Campo rotulo="Evidência" ajuda="o que foi visto, com precisão suficiente para outra pessoa repetir">
            <textarea required value={form.evidencia} onChange={mudar("evidencia")} className={AREA} />
          </Campo>
        </div>
        <div className="md:col-span-2">
          <BotaoDeEnvio enviando={enviar.isPending} rotulo="Registrar verificação" />
          <ErroDoFormulario erro={enviar.error} />
        </div>
      </form>
    </Painel>
  );
}

function FormularioDeRelacao({ ativoId, ativos, aoFechar, aoConcluir }: {
  ativoId: string; ativos: cofre.AtivoDaLista[]; aoFechar: () => void; aoConcluir: () => void;
}) {
  const { toast } = useToast();
  const [tipo, setTipo] = React.useState("depends_on");
  const [modo, setModo] = React.useState<"interno" | "externo">("interno");
  const [destinoId, setDestinoId] = React.useState("");
  const [destinoExterno, setDestinoExterno] = React.useState("");
  const [rotulo, setRotulo] = React.useState("");

  const enviar = useMutation({
    mutationFn: async () => {
      const corpo: Record<string, unknown> = {
        chave_idempotencia: cofre.chaveDoAto("relacao", ativoId, { tipo, destinoId, destinoExterno, rotulo }),
        tipo, destino_rotulo: rotulo.trim(), estado: "declared",
      };
      if (modo === "interno") corpo.destino_id = destinoId;
      else corpo.destino_externo = destinoExterno.trim();
      return cofre.relacionar(ativoId, corpo);
    },
    onSuccess: () => { toast({ title: "Relação registrada" }); aoConcluir(); },
  });

  const candidatos = ativos.filter((a) => a.ativo_id !== ativoId);

  return (
    <Painel titulo="Declarar relação" aoFechar={aoFechar}
      descricao="Um destino, e só um: outro ativo do Cofre (com integridade referencial) ou um alvo externo — projeto, capacidade, conceito — que o Cofre não é dono. Desfazer depois marca a data e o motivo; a aresta não some da trilha.">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); enviar.mutate(); }}>
        <Campo rotulo="Tipo de relação">
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} className={ENTRADA}>
            <option value="belongs_to">pertence a</option><option value="managed_by">é gerido por</option>
            <option value="publishes_to">publica em</option><option value="authenticates_through">autentica por</option>
            <option value="spends_from">gasta de</option><option value="monetizes">monetiza</option>
            <option value="depends_on">depende de</option><option value="produces_for">produz para</option>
          </select>
        </Campo>
        <Campo rotulo="Destino">
          <select value={modo} onChange={(e) => setModo(e.target.value as "interno" | "externo")} className={ENTRADA}>
            <option value="interno">Outro ativo do Cofre</option>
            <option value="externo">Alvo externo (projeto, capacidade)</option>
          </select>
        </Campo>
        {modo === "interno" ? (
          <Campo rotulo="Ativo de destino">
            <select required value={destinoId} onChange={(e) => setDestinoId(e.target.value)} className={ENTRADA}>
              <option value="">Escolha…</option>
              {candidatos.map((a) => <option key={a.ativo_id} value={a.ativo_id}>{a.nome}</option>)}
            </select>
          </Campo>
        ) : (
          <Campo rotulo="Identificador externo" ajuda="ex.: cap:organic-content, project:credito-up">
            <input required value={destinoExterno} onChange={(e) => setDestinoExterno(e.target.value)} className={ENTRADA} />
          </Campo>
        )}
        <Campo rotulo="Rótulo do destino"><input required value={rotulo} onChange={(e) => setRotulo(e.target.value)} className={ENTRADA} /></Campo>
        <div className="md:col-span-2">
          <BotaoDeEnvio enviando={enviar.isPending} rotulo="Declarar relação" />
          <ErroDoFormulario erro={enviar.error} />
        </div>
      </form>
    </Painel>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Inspetor: identidade, postura de acesso, verificação e próximo ato
// ─────────────────────────────────────────────────────────────────────────────

function PosturaDeAcesso({ credenciais }: { credenciais: cofre.PosturaDeCredencial[] }) {
  return (
    <div className="border-b border-border p-5">
      <div className="flex items-center gap-2">
        <KeyRound aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-semibold">Postura de acesso</h4>
      </div>
      {credenciais.length === 0 ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          Nenhuma referência registrada. Enquanto isso, o acesso a este ativo depende de alguém
          lembrar onde ele está — que é exatamente o que o Cofre existe para acabar.
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {credenciais.map((c) => (
            <li key={c.referencia_id} className="rounded-md border border-border bg-muted/30 p-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-mono text-xs font-semibold">{c.nome_logico}</span>
                <span className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{c.provider}</span>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{c.finalidade}</p>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                <span>{CUSTODY_LABEL[c.estado as keyof typeof CUSTODY_LABEL] ?? c.estado}</span>
                <MarcaDeVerificacao estado={c.verificacao_estado} />
                <span>última prova: {dataLegivel(c.verificado_em)}</span>
                {c.valido_ate ? <span>válida até {dataLegivel(c.valido_ate)}</span> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {/* Não é decoração: é a frase que explica por que não há um botão "ver senha". */}
      <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-4 text-muted-foreground">
        <LockKeyhole aria-hidden="true" className="mt-0.5 h-3 w-3 shrink-0" />
        O endereço do item no cofre externo não é exibido nem devolvido por esta tela. Ele
        existe no banco, atrás de operação administrativa auditada.
      </p>
    </div>
  );
}

function PerfilDoEngine({ engine }: { engine: cofre.PerfilDeEngine }) {
  const contagens: Array<[string, number | null | undefined]> = [
    ["formatos", engine.formatos], ["skins", engine.skins],
    ["nichos", engine.nichos], ["vozes", engine.vozes],
  ];
  return (
    <div className="border-b border-border p-5">
      <div className="flex items-center gap-2">
        <PlugZap aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-semibold">Engine criativo</h4>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
        <div><dt className="text-muted-foreground">Modalidade</dt><dd className="mt-0.5 font-medium capitalize">{engine.modalidade}</dd></div>
        <div><dt className="text-muted-foreground">Estado operacional</dt><dd className="mt-0.5 font-medium">{engine.estado_operacional.replace(/_/g, " ")}</dd></div>
        {engine.versao_contrato ? <div><dt className="text-muted-foreground">Contrato</dt><dd className="mt-0.5 font-medium">{engine.versao_contrato}</dd></div> : null}
        <div><dt className="text-muted-foreground">Última conferência</dt><dd className="mt-0.5 font-medium">{dataLegivel(engine.verificado_em)}</dd></div>
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        {contagens.map(([rotulo, valor]) => (
          <span key={rotulo} className={cn("rounded-md border px-2 py-1 text-[11px]",
            valor == null ? "border-dashed border-border text-muted-foreground" : "border-border bg-muted/40")}>
            {/* Ausência é ausência DECLARADA. Um "0" aqui seria uma contagem que
                ninguém observou, e o banco recusa gravá-la justamente por isso. */}
            {rotulo}: {valor == null ? "não declarado" : valor}
          </span>
        ))}
      </div>
      {engine.limitacoes.length ? (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Limitações registradas</p>
          <ul className="mt-1.5 space-y-1">
            {engine.limitacoes.map((l) => (
              <li key={l} className="text-xs leading-5 text-muted-foreground">— {l.replace(/_/g, " ")}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="mt-3 text-[11px] leading-4 text-muted-foreground">
        Procedência: <span className="font-mono">{engine.manifesto_fonte}</span>
      </p>
    </div>
  );
}

function Inspetor({ ativoId, ativos, aoAtualizar }: {
  ativoId: string; ativos: cofre.AtivoDaLista[]; aoAtualizar: () => void;
}) {
  const { toast } = useToast();
  const [painel, setPainel] = React.useState<null | "revisao" | "credencial" | "verificacao" | "relacao">(null);
  const consulta = useQuery({
    queryKey: ["cofre", "detalhe", ativoId],
    queryFn: () => cofre.detalhe(ativoId),
    retry: false,
  });

  const aposentar = useMutation({
    mutationFn: (motivo: string) => cofre.aposentar(ativoId, {
      chave_idempotencia: cofre.chaveDoAto("aposentar", ativoId, motivo), motivo,
    }),
    onSuccess: () => { toast({ title: "Ativo aposentado", description: "Ele continua no inventário, com a data e o motivo." }); aoAtualizar(); consulta.refetch(); },
    onError: (e) => toast({ variant: "destructive", title: "Não foi possível aposentar", description: e instanceof Error ? e.message : undefined }),
  });

  const reativar = useMutation({
    mutationFn: (motivo: string) => cofre.reativar(ativoId, {
      chave_idempotencia: cofre.chaveDoAto("reativar", ativoId, motivo), motivo, estado: "active",
    }),
    onSuccess: () => { toast({ title: "Ativo reativado" }); aoAtualizar(); consulta.refetch(); },
    onError: (e) => toast({ variant: "destructive", title: "Não foi possível reativar", description: e instanceof Error ? e.message : undefined }),
  });

  if (consulta.isPending) {
    return <div className="h-96 animate-pulse rounded-lg border border-border bg-muted/30" role="status" aria-label="Carregando o ativo" />;
  }
  if (consulta.isError) {
    const erro = consulta.error;
    const indisponivel = erro instanceof cofre.ErroDoCofre && erro.indisponivel;
    return (
      <Aviso icone={indisponivel ? CircleAlert : CircleDashed}
        tom={indisponivel ? "erro" : "atencao"}
        titulo={indisponivel ? "O Cofre não respondeu" : "Não consegui abrir este ativo"}
        texto={erro instanceof Error ? erro.message : "Falha desconhecida."}
        codigo={erro instanceof cofre.ErroDoCofre ? erro.codigo : undefined}
        acao={{ rotulo: "Tentar de novo", aoClicar: () => void consulta.refetch() }} />
    );
  }

  const ativo = consulta.data;
  const Icon = CLUSTER_ICONS[ativo.cluster] ?? Vault;
  const ultima = ativo.verificacao[0];

  const recarregar = () => { setPainel(null); void consulta.refetch(); aoAtualizar(); };

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="asset-inspector-title">
        <header className="border-b border-border p-5">
          <div className="flex items-start justify-between gap-4">
            <span className="rounded-md border border-primary/20 bg-primary/10 p-2.5 text-primary"><Icon aria-hidden="true" className="h-5 w-5" /></span>
            <StatePill state={ativo.estado} />
          </div>
          <h3 id="asset-inspector-title" className="mt-4 text-lg font-semibold tracking-tight">{ativo.nome}</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{ativo.resumo}</p>
          {ativo.url_publica ? (
            <a href={ativo.url_publica} target="_blank" rel="noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
              Abrir superfície pública <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
            </a>
          ) : null}
          {ativo.aposentado_em ? (
            <p className="mt-3 rounded-md border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
              Aposentado em {dataLegivel(ativo.aposentado_em)} — {ativo.aposentado_motivo}
            </p>
          ) : null}
        </header>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-4 border-b border-border p-5 text-xs">
          <div><dt className="text-muted-foreground">Gaveta</dt><dd className="mt-1 font-medium">{ativo.gaveta_rotulo}</dd></div>
          <div><dt className="text-muted-foreground">Tipo</dt><dd className="mt-1 font-medium">{ativo.tipo_rotulo}</dd></div>
          <div><dt className="text-muted-foreground">Criticidade</dt><dd className="mt-1 font-medium capitalize">{ativo.criticidade}</dd></div>
          <div><dt className="text-muted-foreground">Dono</dt><dd className="mt-1 font-medium">{ativo.dono_nome} · {ativo.dono_custodia === "verified" ? "comprovada" : "declarada"}</dd></div>
          {ativo.display_id ? <div><dt className="text-muted-foreground">Identificador</dt><dd className="mt-1 font-mono font-medium">{ativo.display_id}</dd></div> : null}
          <div><dt className="text-muted-foreground">Revisão</dt><dd className="mt-1 font-medium tabular-nums">{ativo.revisao_atual}</dd></div>
        </dl>

        <div className="border-b border-border p-5">
          <div className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold">Última verificação</h4></div>
          {ultima ? (
            <>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <MarcaDeVerificacao estado={ultima.resultado} />
                <span className="text-muted-foreground">{dataLegivel(ultima.observado_em)}</span>
                <span className="text-muted-foreground">{ultima.metodo}</span>
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">{ultima.evidencia}</p>
            </>
          ) : (
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Nenhuma prova registrada. O estado deste ativo é uma declaração, não uma verificação.
            </p>
          )}
        </div>

        <PosturaDeAcesso credenciais={ativo.credencial} />
        {ativo.engine ? <PerfilDoEngine engine={ativo.engine} /> : null}

        <div className="border-b border-border p-5">
          <div className="flex items-center gap-2"><Link2 aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold">Relações deste ativo</h4></div>
          {ativo.relacoes.length ? (
            <ul className="mt-3 space-y-2">
              {ativo.relacoes.map((r) => (
                <li key={`${r.tipo}:${r.destino}`} className="flex items-start gap-2 text-xs">
                  <ArrowRight aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span><span className="text-muted-foreground">{r.tipo.replace(/_/g, " ")}</span> {r.rotulo}</span>
                </li>
              ))}
            </ul>
          ) : <p className="mt-2 text-xs text-muted-foreground">Nenhuma relação declarada.</p>}
        </div>

        <div className="border-b border-border p-5">
          <div className="flex items-center gap-2"><Clock3 aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold">Próxima ação</h4></div>
          <p className="mt-2 text-xs leading-5">{ativo.proxima_acao}</p>
        </div>

        <div className="flex flex-wrap gap-2 p-5">
          <button type="button" onClick={() => setPainel("revisao")}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-muted">Revisar ativo</button>
          <button type="button" onClick={() => setPainel("verificacao")}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-muted">Registrar verificação</button>
          <button type="button" onClick={() => setPainel("credencial")}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-muted">Registrar referência de acesso</button>
          <button type="button" onClick={() => setPainel("relacao")}
            className="rounded-md border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-muted">Declarar relação</button>
          {ativo.aposentado_em ? (
            <button type="button" disabled={reativar.isPending}
              onClick={() => reativar.mutate("retomada de operação decidida pelo dono")}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-muted disabled:opacity-60">
              <Undo2 aria-hidden="true" className="h-3.5 w-3.5" /> Reativar
            </button>
          ) : (
            <button type="button" disabled={aposentar.isPending}
              onClick={() => aposentar.mutate("ativo sai de operação; permanece no inventário para auditoria")}
              className="rounded-md border border-border bg-background px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted disabled:opacity-60">
              Aposentar
            </button>
          )}
        </div>
      </section>

      {painel === "revisao" ? <FormularioDeRevisao ativo={ativo} aoFechar={() => setPainel(null)} aoConcluir={recarregar} /> : null}
      {painel === "credencial" ? <FormularioDeCredencial ativoId={ativoId} aoFechar={() => setPainel(null)} aoConcluir={recarregar} /> : null}
      {painel === "verificacao" ? <FormularioDeVerificacao ativoId={ativoId} aoFechar={() => setPainel(null)} aoConcluir={recarregar} /> : null}
      {painel === "relacao" ? <FormularioDeRelacao ativoId={ativoId} ativos={ativos} aoFechar={() => setPainel(null)} aoConcluir={recarregar} /> : null}

      {ativo.historico.length ? (
        <section className="rounded-lg border border-border bg-card p-5" aria-label="Histórico do ativo">
          <h4 className="text-sm font-semibold">Trilha</h4>
          <ul className="mt-3 space-y-2">
            {ativo.historico.slice(0, 8).map((h) => (
              <li key={h.revisao} className="flex items-start gap-3 text-xs">
                <span className="tabular-nums text-muted-foreground">#{h.revisao}</span>
                <span className="min-w-0">
                  <span className="font-medium">{h.operacao.replace(/_/g, " ")}</span>
                  <span className="block text-muted-foreground">{h.motivo}</span>
                  <span className="block text-[11px] text-muted-foreground">{dataLegivel(h.ocorrido_em)} · {h.autor_email}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Inventário
// ─────────────────────────────────────────────────────────────────────────────

function Pulso({ ativos }: { ativos: cofre.AtivoDaLista[] }) {
  const verificados = ativos.filter((a) => a.verificacao_estado === "verified").length;
  const pedemProva = ativos.filter((a) => a.verificacao_estado !== "verified").length;
  const semReferencia = ativos.filter((a) => !a.credencial_registrada).length;
  const custodiaAberta = ativos.filter((a) => a.dono_custodia !== "verified").length;
  const celulas: Array<[number, string]> = [
    [ativos.length, "ativos no inventário"],
    [verificados, "verificados"],
    [pedemProva, "pedem conferência"],
    [custodiaAberta, "custódias a provar"],
    [semReferencia, "sem referência de acesso"],
  ];
  return (
    <section aria-label="Pulso do patrimônio" className="mt-6 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 xl:grid-cols-5">
      {celulas.map(([valor, rotulo]) => (
        <div key={rotulo} className="flex items-center gap-3 bg-card px-4 py-3">
          <span className="text-xl font-semibold tabular-nums">{valor}</span>
          <span className="text-xs leading-4 text-muted-foreground">{rotulo}</span>
        </div>
      ))}
    </section>
  );
}

function FronteiraDeSeguranca() {
  return (
    <section className="mt-6 grid gap-4 border-y border-border py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center" aria-label="Fronteira de segurança">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 rounded-md bg-success/10 p-2 text-success"><ShieldCheck aria-hidden="true" className="h-4 w-4" /></span>
        <div>
          <p className="text-sm font-semibold">Aqui mora o patrimônio, não a senha</p>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            O VOLC registra identidade, custódia, evidência e postura de acesso. Senhas, chaves, MFA e
            códigos de recuperação ficam no 1Password. O endereço do item lá também não chega a esta tela.
          </p>
        </div>
      </div>
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-success/25 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
        <LockKeyhole aria-hidden="true" className="h-3.5 w-3.5" /> Zero segredo neste contrato
      </span>
    </section>
  );
}

function Lista({ inventario, selecionado, aoSelecionar, aoCadastrar }: {
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
      <div className="flex flex-col gap-3 border-b border-border pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">Inventário persistido</p>
          <h2 id="asset-list-heading" className="mt-1 text-xl font-semibold tracking-tight">Ativos conhecidos</h2>
          <p className="mt-1 text-sm text-muted-foreground">{filtrados.length} de {inventario.ativos.length}</p>
        </div>
        <button type="button" onClick={aoCadastrar}
          className="inline-flex w-fit items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
          <Plus aria-hidden="true" className="h-4 w-4" /> Cadastrar ativo
        </button>
      </div>

      <div className="border-b border-border py-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Organizar por gaveta</p>
        <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Gavetas do Cofre">
          <button type="button" onClick={() => escolherGaveta("all")} aria-pressed={gaveta === "all"}
            className={cn("shrink-0 rounded-md border px-3 py-2 text-xs font-medium transition-colors",
              gaveta === "all" ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
            Todos <span className="ml-1 tabular-nums">{inventario.ativos.length}</span>
          </button>
          {/* As sete gavetas vêm do servidor e aparecem SEMPRE, inclusive com
              contagem zero: uma gaveta que some quando esvazia faz a estrutura
              do Cofre parecer menor do que é. */}
          {inventario.gavetas.slice().sort((a, b) => a.ordem - b.ordem).map((g) => {
            const Icon = CLUSTER_ICONS[g.cluster] ?? Vault;
            return (
              <button key={g.cluster} type="button" onClick={() => escolherGaveta(g.cluster)} aria-pressed={gaveta === g.cluster}
                className={cn("inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-xs font-medium transition-colors",
                  gaveta === g.cluster ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                <Icon aria-hidden="true" className="h-3.5 w-3.5" />{g.rotulo} <span className="tabular-nums">{g.total}</span>
              </button>
            );
          })}
        </div>
        {gaveta !== "all" ? (
          <p className="mt-2 text-xs text-muted-foreground">
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
        <section className="space-y-6 pt-5" aria-label="Ativos encontrados">
          {grupos.map((grupo) => {
            const GroupIcon = CLUSTER_ICONS[grupo.gaveta.cluster] ?? Vault;
            return (
              <section key={grupo.gaveta.cluster} aria-labelledby={`gaveta-${grupo.gaveta.cluster}`}>
                <div className="flex items-start gap-3 border-b border-border px-3 pb-3">
                  <span className="rounded-md border border-border bg-muted/50 p-2 text-muted-foreground"><GroupIcon aria-hidden="true" className="h-4 w-4" /></span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <h3 id={`gaveta-${grupo.gaveta.cluster}`} className="text-sm font-semibold">{grupo.gaveta.rotulo}</h3>
                      <span className="text-xs tabular-nums text-muted-foreground">{grupo.ativos.length}</span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{grupo.gaveta.descricao}</p>
                  </div>
                </div>
                <div className="hidden grid-cols-[minmax(16rem,1.5fr)_10rem_9rem_8rem_1.5rem] gap-3 border-b border-border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground md:grid">
                  <span>Ativo</span><span>Estado</span><span>Custódia</span><span>Verificação</span><span />
                </div>
                <ul className="divide-y divide-border">
                  {grupo.ativos.map((a) => {
                    const Icon = CLUSTER_ICONS[a.cluster] ?? Vault;
                    const marcado = selecionado === a.ativo_id;
                    return (
                      <li key={a.ativo_id}>
                        <button type="button" onClick={() => aoSelecionar(a.ativo_id)} aria-pressed={marcado}
                          className={cn("grid w-full gap-3 px-3 py-4 text-left outline-none transition-colors hover:bg-muted/45 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring md:grid-cols-[minmax(16rem,1.5fr)_10rem_9rem_8rem_1.5rem] md:items-center",
                            marcado && "bg-primary/[0.055]")}>
                          <span className="flex min-w-0 items-start gap-3">
                            <span className={cn("mt-0.5 rounded-md border p-2", marcado ? "border-primary/25 bg-primary/10 text-primary" : "border-border bg-muted/50 text-muted-foreground")}>
                              <Icon aria-hidden="true" className="h-4 w-4" />
                            </span>
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-semibold text-foreground">{a.nome}</span>
                              <span className="mt-1 block truncate text-xs text-muted-foreground">
                                {a.tipo_rotulo} · {a.plataforma}{a.display_id ? ` · ${a.display_id}` : ""}
                              </span>
                            </span>
                          </span>
                          <span><StatePill state={a.estado} /></span>
                          <span className="text-xs text-foreground/80">{a.dono_nome}
                            <span className="mt-1 block text-muted-foreground">{a.dono_custodia === "verified" ? "comprovada" : "a provar"}</span>
                          </span>
                          <MarcaDeVerificacao estado={a.verificacao_estado} />
                          <ChevronRight aria-hidden="true" className={cn("hidden h-4 w-4 text-muted-foreground md:block", marcado && "text-primary")} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </section>
      ) : inventario.ativos.length === 0 ? (
        /* VAZIO DE VERDADE: o Cofre respondeu, e não há ativo. É um fato, e a
           estrutura continua visível acima — sete gavetas com contagem zero. */
        <div className="py-14 text-center">
          <Vault aria-hidden="true" className="mx-auto h-6 w-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">O Cofre está vazio</p>
          <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground">
            As sete gavetas existem e estão vazias. Comece pelo ativo mais crítico da operação —
            a página monetizada, o MCC, o Supabase — e registre dono, evidência e próxima ação.
          </p>
          <button type="button" onClick={aoCadastrar}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
            <Plus aria-hidden="true" className="h-4 w-4" /> Cadastrar o primeiro ativo
          </button>
        </div>
      ) : (
        <div className="py-14 text-center">
          <ListFilter aria-hidden="true" className="mx-auto h-6 w-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">Nenhum ativo neste recorte</p>
          <p className="mt-1 text-xs text-muted-foreground">Ajuste a busca ou os filtros. O inventário não foi alterado.</p>
        </div>
      )}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// As outras três lentes
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Revisões: o que o inventário está devendo.
 *
 * A ordem não é alfabética nem por data — é por consequência. Um ativo crítico
 * sem prova e sem referência de acesso é um problema diferente de um ativo
 * inativo com revisão vencida, e listar os dois juntos em ordem de nome faz o
 * primeiro se perder no meio do segundo.
 */
const PESO_DA_CRITICIDADE: Record<string, number> = { critical: 3, high: 2, medium: 1, low: 0 };

function Revisoes({ ativos, aoSelecionar }: { ativos: cofre.AtivoDaLista[]; aoSelecionar: (id: string) => void }) {
  const pendentes = ativos
    .map((a) => {
      const faltas: string[] = [];
      if (a.verificacao_estado === "unverified") faltas.push("sem prova registrada");
      if (a.verificacao_estado === "expired") faltas.push("revisão vencida");
      if (a.verificacao_estado === "failed") faltas.push("a última verificação falhou");
      if (a.verificacao_estado === "blocked") faltas.push("acesso bloqueado na última tentativa");
      if (a.verificacao_estado === "partial") faltas.push("verificação apenas parcial");
      if (a.dono_custodia !== "verified") faltas.push("custódia declarada, não comprovada");
      if (!a.credencial_registrada) faltas.push("nenhuma referência de acesso registrada");
      return { ativo: a, faltas };
    })
    .filter((linha) => linha.faltas.length > 0)
    .sort((x, y) => {
      const peso = (PESO_DA_CRITICIDADE[y.ativo.criticidade] ?? 0) - (PESO_DA_CRITICIDADE[x.ativo.criticidade] ?? 0);
      return peso !== 0 ? peso : y.faltas.length - x.faltas.length;
    });

  if (!pendentes.length) {
    return (
      <section className="rounded-lg border border-border bg-card px-5 py-12 text-center">
        <CheckCircle2 aria-hidden="true" className="mx-auto h-6 w-6 text-success" />
        <p className="mt-3 text-sm font-medium">Nada pendente de revisão</p>
        <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground">
          Todo ativo do inventário tem custódia comprovada, prova registrada e referência de acesso.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="revisoes-heading">
      <div className="border-b border-border pb-4">
        <h2 id="revisoes-heading" className="text-xl font-semibold tracking-tight">O que o inventário está devendo</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {pendentes.length} de {ativos.length} ativos, em ordem de consequência — criticidade primeiro,
          depois quantidade de lacunas.
        </p>
      </div>
      <ul className="divide-y divide-border">
        {pendentes.map(({ ativo, faltas }) => (
          <li key={ativo.ativo_id}>
            <button type="button" onClick={() => aoSelecionar(ativo.ativo_id)}
              className="grid w-full gap-2 px-3 py-4 text-left outline-none transition-colors hover:bg-muted/45 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring md:grid-cols-[minmax(14rem,1fr)_minmax(0,1.2fr)_8rem]">
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{ativo.nome}</span>
                <span className="mt-1 block truncate text-xs text-muted-foreground">{ativo.tipo_rotulo} · {ativo.plataforma}</span>
              </span>
              <span className="min-w-0">
                <ul className="space-y-0.5">
                  {faltas.map((f) => (
                    <li key={f} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                      <CircleAlert aria-hidden="true" className="mt-0.5 h-3 w-3 shrink-0 text-warning" />{f}
                    </li>
                  ))}
                </ul>
                <span className="mt-1.5 block text-xs leading-5">{ativo.proxima_acao}</span>
              </span>
              <span className="text-xs">
                <span className="block font-medium capitalize">{ativo.criticidade}</span>
                <span className="mt-1 block text-muted-foreground">{dataLegivel(ativo.verificado_em)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Relações: a lente secundária, como o contrato de produto pede.
 *
 * Ela existe para responder "o que depende do quê", e NÃO é a porta de entrada
 * do Cofre — quem procura um ativo procura pela gaveta. Por isso ela mostra as
 * arestas declaradas, e não tenta desenhar um grafo que competiria com o Mapa
 * Vivo, que é a autoridade de relações do projeto.
 */
function Relacoes({ ativos, aoSelecionar }: { ativos: cofre.AtivoDaLista[]; aoSelecionar: (id: string) => void }) {
  const comArestas = ativos.filter((a) => (a.relacoes ?? []).length > 0);
  const total = comArestas.reduce((soma, a) => soma + a.relacoes.length, 0);
  const nomePorId = new Map(ativos.map((a) => [a.ativo_id, a.nome]));

  return (
    <section aria-labelledby="relacoes-heading">
      <div className="border-b border-border pb-4">
        <h2 id="relacoes-heading" className="text-xl font-semibold tracking-tight">Relações declaradas</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {total} {total === 1 ? "aresta" : "arestas"} em {comArestas.length} de {ativos.length} ativos.
          Esta é uma lente secundária: a porta de entrada do Cofre continua sendo a gaveta.
        </p>
      </div>
      {comArestas.length === 0 ? (
        <div className="py-14 text-center">
          <Network aria-hidden="true" className="mx-auto h-6 w-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">Nenhuma relação declarada</p>
          <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground">
            Relações são declaradas no detalhe de cada ativo. Sem elas, o Cofre sabe o que existe,
            mas não sabe o que cai junto quando um ativo sai do ar.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {comArestas.map((a) => (
            <li key={a.ativo_id} className="py-4">
              <button type="button" onClick={() => aoSelecionar(a.ativo_id)}
                className="text-sm font-semibold hover:underline">{a.nome}</button>
              <ul className="mt-2 space-y-1.5 pl-3">
                {a.relacoes.map((r) => (
                  <li key={`${r.tipo}:${r.destino}`} className="flex items-start gap-2 text-xs">
                    <ArrowRight aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span>
                      <span className="text-muted-foreground">{r.tipo.replace(/_/g, " ")}</span>{" "}
                      {/* Um destino que É um ativo do Cofre vira link; um alvo
                          externo fica como texto, porque o Cofre não é dono dele
                          e fingir que é confundiria quem procura. */}
                      {nomePorId.has(r.destino) ? (
                        <button type="button" onClick={() => aoSelecionar(r.destino)} className="font-medium hover:underline">
                          {r.rotulo}
                        </button>
                      ) : <span className="font-medium">{r.rotulo}</span>}
                      <span className="ml-2 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                        {r.estado === "verified" ? "verificada" : "declarada"}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Contrato: o catálogo de tipos por gaveta, e o que um ativo precisa provar. */
function Contrato({ gavetas }: { gavetas: cofre.GavetaDoCofre[] }) {
  const exigencias = [
    "identidade e tipo, com a gaveta derivada do tipo",
    "dono e estado da custódia — declarada não é comprovada",
    "estado operacional e criticidade",
    "ID sanitizado ou endereço público HTTP(S)",
    "capacidades e próxima ação concreta",
    "postura de acesso, sem segredo e sem o endereço do item no cofre externo",
    "verificação com método, procedência e o instante da observação",
    "relações declaradas ou verificadas",
  ];
  const ordenadas = gavetas.slice().sort((a, b) => a.ordem - b.ordem);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section aria-labelledby="contrato-exigencias">
        <h2 id="contrato-exigencias" className="text-xl font-semibold tracking-tight">O que um ativo precisa provar</h2>
        <ul className="mt-4 space-y-2">
          {exigencias.map((e) => (
            <li key={e} className="flex items-start gap-2 text-sm leading-6">
              <CheckCircle2 aria-hidden="true" className="mt-1 h-3.5 w-3.5 shrink-0 text-success" />{e}
            </li>
          ))}
        </ul>
        <p className="mt-4 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs leading-5 text-muted-foreground">
          O contrato executável está em <span className="font-mono">src/features/asset-vault/contract.ts</span> e no
          schema privado <span className="font-mono">v13_01</span>. Os dois recusam campo desconhecido, URL fora de
          HTTP(S) e tipo colocado na gaveta errada — e há teste que compara os dois, para não divergirem em silêncio.
        </p>
      </section>
      <section aria-labelledby="contrato-tipos">
        <h2 id="contrato-tipos" className="text-xl font-semibold tracking-tight">Tipos organizados por gaveta</h2>
        <div className="mt-4 space-y-4">
          {ordenadas.map((g) => {
            const Icon = CLUSTER_ICONS[g.cluster] ?? Vault;
            const tipos = ASSET_KINDS.filter((k) => KIND_CLUSTER[k] === g.cluster);
            return (
              <section key={g.cluster} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2">
                  <Icon aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">{g.rotulo}</h3>
                  <span className="text-xs tabular-nums text-muted-foreground">{g.total} no inventário</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{g.descricao}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {tipos.map((k) => (
                    <span key={k} className="rounded-md border border-border bg-muted/40 px-2 py-1 text-[11px]">{KIND_LABEL[k]}</span>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// A tela
// ─────────────────────────────────────────────────────────────────────────────

export function AssetVaultContent() {
  const [params, setParams] = useSearchParams();
  const clientes = useQueryClient();
  const [cadastrando, setCadastrando] = React.useState(false);

  const viewBruta = params.get("view") as VaultView | null;
  const view: VaultView = viewBruta && VALID_VIEWS.has(viewBruta) ? viewBruta : "inventory";
  const selecionado = params.get("ativo");

  const inventario = useQuery({
    queryKey: ["cofre", "inventario"],
    queryFn: () => cofre.inventario(),
    // Sem base configurada não há o que perguntar: a chamada falharia com
    // `sem_base` depois de montar cabeçalho e sessão. Gastar a ida para
    // descobrir o que já se sabe é ruído no log de quem for investigar.
    enabled: cofre.cofreConfigurado(),
    // Sem retry: um Cofre que não responde tem de DIZER que não responde, e
    // rápido. Três tentativas silenciosas transformam indisponibilidade em
    // lentidão sem causa visível.
    retry: false,
    staleTime: 30_000,
  });

  const escolher = (ativoId: string) => {
    const proximo = new URLSearchParams(params);
    proximo.set("ativo", ativoId);
    setParams(proximo, { replace: true });
  };
  const trocarView = (proxima: VaultView) => {
    const proximo = new URLSearchParams(params);
    proximo.set("view", proxima);
    setParams(proximo, { replace: true });
  };
  const recarregar = () => void clientes.invalidateQueries({ queryKey: ["cofre"] });

  if (!cofre.cofreConfigurado()) {
    return (
      <Moldura>
        <Aviso icone={PlugZap} tom="atencao" titulo="O Cofre não está configurado neste ambiente"
          texto="A variável VITE_PAUTADOR_API_URL não foi definida, então esta tela não sabe com qual backend falar. Isso é configuração de ambiente, não falta de dado — o inventário pode existir e estar inacessível daqui." />
      </Moldura>
    );
  }

  if (inventario.isPending) return <Moldura><Carregando /></Moldura>;

  if (inventario.isError) {
    const erro = inventario.error;
    const doCofre = erro instanceof cofre.ErroDoCofre ? erro : null;
    // Quatro falhas, quatro telas. Colapsá-las manda a pessoa para a ação errada:
    // 401 pede login, 403 pede acesso, 503 pede espera, e o resto pede
    // investigação. Uma frase genérica não distingue nenhuma delas.
    if (doCofre?.semSessao) {
      return <Moldura><Aviso icone={KeyRound} tom="atencao" titulo="Sua sessão expirou"
        texto="Entre novamente para abrir o Cofre." codigo={doCofre.codigo} /></Moldura>;
    }
    if (doCofre?.semPermissao) {
      return <Moldura><Aviso icone={LockKeyhole} tom="atencao" titulo="Acesso restrito"
        texto="O inventário de ativos e postura de acesso é exclusivo para administradores. Sua identidade é válida; o papel é que não permite." codigo={doCofre.codigo} /></Moldura>;
    }
    if (doCofre?.indisponivel) {
      return <Moldura><Aviso icone={CircleAlert} tom="erro" titulo="O Cofre não respondeu"
        texto={`${doCofre.message} Nada foi alterado, e esta tela não mostra um inventário vazio no lugar — vazio e indisponível são fatos diferentes.`}
        codigo={doCofre.codigo}
        acao={{ rotulo: "Tentar de novo", aoClicar: () => void inventario.refetch() }} /></Moldura>;
    }
    return <Moldura><Aviso icone={CircleAlert} tom="erro" titulo="Não consegui abrir o Cofre"
      texto={erro instanceof Error ? erro.message : "Falha desconhecida."}
      codigo={doCofre?.codigo}
      acao={{ rotulo: "Tentar de novo", aoClicar: () => void inventario.refetch() }} /></Moldura>;
  }

  const dados = inventario.data;
  const ativoAtual = selecionado && dados.ativos.some((a) => a.ativo_id === selecionado)
    ? selecionado
    : dados.ativos[0]?.ativo_id ?? null;

  return (
    <Moldura>
      <header>
        <div className="flex items-start gap-3">
          <span className="rounded-md border border-primary/20 bg-primary/10 p-2.5 text-primary"><Vault aria-hidden="true" className="h-5 w-5" /></span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Cofre de Ativos</h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
              O que existe, em qual gaveta, quem cuida, o que já foi comprovado, como o acesso está
              protegido e qual é a próxima ação concreta.
            </p>
          </div>
        </div>
        <nav aria-label="Modos do Cofre" className="mt-5 flex gap-2 overflow-x-auto">
          {VIEWS.map((v) => {
            const Icon = v.icon;
            return (
              <button key={v.id} type="button" onClick={() => trocarView(v.id)} aria-pressed={view === v.id}
                className={cn("inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                  view === v.id ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                <Icon aria-hidden="true" className="h-4 w-4" />{v.label}
              </button>
            );
          })}
        </nav>
      </header>

      <Pulso ativos={dados.ativos} />
      <FronteiraDeSeguranca />

      {cadastrando ? (
        <div className="mt-6">
          <FormularioDeCadastro aoFechar={() => setCadastrando(false)}
            aoConcluir={(id) => { setCadastrando(false); recarregar(); escolher(id); }} />
        </div>
      ) : null}

      {view === "contract" ? (
        <div className="mt-6"><Contrato gavetas={dados.gavetas} /></div>
      ) : (
        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_25rem]">
          {view === "inventory" ? (
            <Lista inventario={dados} selecionado={ativoAtual} aoSelecionar={escolher}
              aoCadastrar={() => setCadastrando(true)} />
          ) : view === "reviews" ? (
            <Revisoes ativos={dados.ativos} aoSelecionar={escolher} />
          ) : (
            <Relacoes ativos={dados.ativos} aoSelecionar={escolher} />
          )}
          <aside aria-label="Detalhe do ativo" className="xl:sticky xl:top-6 xl:self-start">
            {ativoAtual ? (
              <Inspetor ativoId={ativoAtual} ativos={dados.ativos} aoAtualizar={recarregar} />
            ) : (
              <div className="rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">
                Cadastre um ativo para conferir identidade, evidência e postura de acesso.
              </div>
            )}
          </aside>
        </div>
      )}
    </Moldura>
  );
}

export default AssetVaultContent;
