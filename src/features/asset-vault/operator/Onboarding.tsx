/** Hallmark · pre-emit critique: P5 H5 E4 S5 R5 V4 — workspace progressivo, não modal. */
import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import * as cofre from "../cofreApi";
import {
  ASSET_KINDS, CLUSTER_LABEL, KIND_CLUSTER, KIND_LABEL, STATE_LABEL,
  type AssetKind,
} from "../contract";
import { AREA, ENTRADA, FOCO, HIT, PRESSIONAR, PRIMARIO, SECUNDARIO } from "./chrome";
import { ErroDoFormulario } from "./Estados";
import {
  diagnosticarReferencia, fraseDaFalha, montarReferencia1Password,
  retratoDaReferencia, type PecasDaReferencia,
} from "./referencia";

const CHAVE_RASCUNHO = "volc.cofre.onboarding.v2";

const PASSOS = [
  { id: 1, titulo: "Tipo de ativo", porque: "A gaveta nasce do tipo. Escolher os dois convidaria a contradição que o banco recusa." },
  { id: 2, titulo: "Identidade e finalidade", porque: "Sem nome, resumo e próxima ação o ativo não entra na operação. O identificador é a chave estável." },
  { id: 3, titulo: "Owner e custódia", porque: "Declarada não é comprovada. Quem responde pelo ativo precisa estar nomeado antes do acesso." },
  { id: 4, titulo: "Destino", porque: "Projeto, vertical e URL ligam o patrimônio à campanha. São opcionais, mas a ausência fica visível." },
  { id: 5, titulo: "Referência da credencial", porque: "O valor fica no 1Password. Aqui entram cofre, item e campo — nunca senha, token, cookie ou chave." },
  { id: 6, titulo: "Relações", porque: "Sem aresta o Cofre sabe que o ativo existe e não sabe o que cai junto. Pode pular." },
  { id: 7, titulo: "Revisão e confirmação", porque: "O POST só sai daqui. Reenvio com a mesma chave devolve o mesmo recibo." },
] as const;

type Rascunho = {
  passo: number;
  kind: AssetKind;
  ativo_id: string;
  nome: string;
  plataforma: string;
  estado: string;
  criticidade: string;
  resumo: string;
  capacidades: string;
  tags: string;
  proxima_acao: string;
  dono_nome: string;
  dono_custodia: string;
  projeto: string;
  vertical: string;
  display_id: string;
  url_publica: string;
  credencial: PecasDaReferencia & { nome_logico: string; owner_nome: string; finalidade: string; pular: boolean };
  relacao: { tipo: string; destino: string; rotulo: string; pular: boolean };
};

const VAZIO: Rascunho = {
  passo: 1,
  kind: "facebook_page",
  ativo_id: "", nome: "", plataforma: "", estado: "declared", criticidade: "medium",
  resumo: "", capacidades: "", tags: "", proxima_acao: "",
  dono_nome: "", dono_custodia: "declared",
  projeto: "", vertical: "", display_id: "", url_publica: "",
  credencial: { cofre: "", item: "", campo: "credential", nome_logico: "", owner_nome: "", finalidade: "", pular: false },
  relacao: { tipo: "depends_on", destino: "", rotulo: "", pular: true },
};

function lerRascunho(): Rascunho {
  try {
    const cru = sessionStorage.getItem(CHAVE_RASCUNHO);
    if (!cru) return VAZIO;
    const lido = JSON.parse(cru) as Partial<Rascunho>;
    return { ...VAZIO, ...lido, credencial: { ...VAZIO.credencial, ...lido.credencial }, relacao: { ...VAZIO.relacao, ...lido.relacao } };
  } catch {
    return VAZIO;
  }
}

function Campo({ rotulo, ajuda, obrigatorio, children }: {
  rotulo: string; ajuda?: string; obrigatorio?: boolean; children: React.ReactNode;
}) {
  return (
    <label className="block min-w-0">
      <span className="text-xs font-medium">
        {rotulo}
        {obrigatorio ? <span className="ml-1 text-destructive">obrigatório</span> : <span className="ml-1 text-muted-foreground">opcional</span>}
      </span>
      {ajuda ? <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground text-pretty">{ajuda}</span> : null}
      <span className="mt-1.5 block">{children}</span>
    </label>
  );
}

export function OnboardingProgressivo({
  aoFechar, aoConcluir,
}: {
  aoFechar: () => void;
  aoConcluir: (id: string) => void;
}) {
  const { toast } = useToast();
  const [rascunho, setRascunho] = React.useState<Rascunho>(lerRascunho);
  const [sucessoIdempotente, setSucessoIdempotente] = React.useState(false);

  React.useEffect(() => {
    sessionStorage.setItem(CHAVE_RASCUNHO, JSON.stringify(rascunho));
  }, [rascunho]);

  const mudar = <K extends keyof Rascunho>(campo: K, valor: Rascunho[K]) =>
    setRascunho((atual) => ({ ...atual, [campo]: valor }));

  const enviar = useMutation({
    mutationFn: async () => {
      const ativo: Record<string, unknown> = {
        ativo_id: rascunho.ativo_id.trim(),
        kind: rascunho.kind,
        cluster: KIND_CLUSTER[rascunho.kind],
        nome: rascunho.nome.trim(),
        plataforma: rascunho.plataforma.trim(),
        estado: rascunho.estado,
        criticidade: rascunho.criticidade,
        resumo: rascunho.resumo.trim(),
        dono_nome: rascunho.dono_nome.trim(),
        dono_custodia: rascunho.dono_custodia,
        capacidades: rascunho.capacidades.split(",").map((c) => c.trim()).filter(Boolean),
        tags: rascunho.tags.split(",").map((t) => t.trim()).filter(Boolean),
        proxima_acao: rascunho.proxima_acao.trim(),
      };
      for (const opcional of ["projeto", "vertical", "display_id", "url_publica"] as const) {
        const valor = rascunho[opcional].trim();
        if (valor) ativo[opcional] = valor;
      }
      const cadastro = await cofre.cadastrarAtivo({
        chave_idempotencia: cofre.chaveDoAto("cadastro", ativo.ativo_id as string, ativo),
        motivo: "cadastro pela tela do Cofre de Ativos",
        ativo,
      });
      const ativoId = cadastro.ativo_id ?? rascunho.ativo_id.trim();
      if (!rascunho.credencial.pular) {
        const falha = diagnosticarReferencia(rascunho.credencial);
        if (falha) throw new Error(fraseDaFalha(falha));
        await cofre.referenciarCredencial(ativoId, {
          chave_idempotencia: cofre.chaveDoAto("credencial", ativoId, rascunho.credencial),
          provider: "1password",
          nome_logico: rascunho.credencial.nome_logico.trim(),
          localizador: montarReferencia1Password(rascunho.credencial),
          finalidade: rascunho.credencial.finalidade.trim(),
          owner_nome: rascunho.credencial.owner_nome.trim(),
        });
      }
      if (!rascunho.relacao.pular && rascunho.relacao.destino.trim()) {
        await cofre.relacionar(ativoId, {
          chave_idempotencia: cofre.chaveDoAto("relacao", ativoId, rascunho.relacao),
          tipo: rascunho.relacao.tipo,
          destino_externo: rascunho.relacao.destino.trim(),
          destino_rotulo: rascunho.relacao.rotulo.trim() || rascunho.relacao.destino.trim(),
          estado: "declared",
        });
      }
      return cadastro;
    },
    onSuccess: (recibo) => {
      sessionStorage.removeItem(CHAVE_RASCUNHO);
      setSucessoIdempotente(Boolean(recibo.idempotente));
      toast({
        title: recibo.idempotente ? "Este cadastro já existia" : "Ativo cadastrado",
        description: recibo.idempotente
          ? "O Cofre reconheceu o reenvio e devolveu o mesmo recibo. Nada foi duplicado."
          : `Revisão ${recibo.revisao} registrada na trilha.`,
      });
      if (recibo.ativo_id) aoConcluir(recibo.ativo_id);
    },
  });

  const passo = PASSOS[rascunho.passo - 1];
  const podeAvancar = validarPasso(rascunho);

  return (
    <section className="rounded-lg border border-border bg-card" aria-label="Cadastrar ativo">
      <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <p className="kicker">Onboarding progressivo</p>
          <h2 className="mt-1 font-display text-lg font-semibold text-balance">{passo.titulo}</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground text-pretty">{passo.porque}</p>
        </div>
        <button type="button" onClick={aoFechar} aria-label="Fechar" className={cn(SECUNDARIO, "px-2")}>Fechar</button>
      </header>

      <ol className="flex gap-1 overflow-x-auto border-b border-border px-5 py-3" aria-label="Etapas do cadastro">
        {PASSOS.map((p) => (
          <li key={p.id}>
            <button type="button" onClick={() => mudar("passo", p.id)}
              aria-current={p.id === rascunho.passo ? "step" : undefined}
              className={cn("min-h-10 rounded-md px-2 text-[11px] font-medium", FOCO, PRESSIONAR,
                p.id === rascunho.passo ? "bg-primary/10 text-primary" : p.id < rascunho.passo ? "text-foreground" : "text-muted-foreground")}>
              {p.id < rascunho.passo ? <Check aria-hidden="true" className="mr-1 inline h-3 w-3" /> : null}
              {p.id}. {p.titulo}
            </button>
          </li>
        ))}
      </ol>

      <form className="grid gap-4 px-5 py-5" onSubmit={(e) => {
        e.preventDefault();
        if (rascunho.passo < 7) {
          if (podeAvancar) mudar("passo", rascunho.passo + 1);
          return;
        }
        enviar.mutate();
      }}>
        {rascunho.passo === 1 ? (
          <Campo rotulo="Tipo" obrigatorio ajuda={`Gaveta: ${CLUSTER_LABEL[KIND_CLUSTER[rascunho.kind]]} (derivada do tipo)`}>
            <select value={rascunho.kind} onChange={(e) => mudar("kind", e.target.value as AssetKind)} className={ENTRADA}>
              {ASSET_KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
            </select>
          </Campo>
        ) : null}

        {rascunho.passo === 2 ? (
          <>
            <Campo rotulo="Identificador" obrigatorio ajuda="minúsculas, dígitos, ':', '_' e '-'.">
              <input required value={rascunho.ativo_id} onChange={(e) => mudar("ativo_id", e.target.value)}
                className={ENTRADA} placeholder="asset:facebook-page:piloto" />
            </Campo>
            <Campo rotulo="Nome" obrigatorio>
              <input required value={rascunho.nome} onChange={(e) => mudar("nome", e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="Plataforma" obrigatorio>
              <input required value={rascunho.plataforma} onChange={(e) => mudar("plataforma", e.target.value)} className={ENTRADA} placeholder="Meta, Google Ads, WordPress…" />
            </Campo>
            <Campo rotulo="Estado" obrigatorio>
              <select value={rascunho.estado} onChange={(e) => mudar("estado", e.target.value)} className={ENTRADA}>
                {Object.entries(STATE_LABEL).filter(([v]) => v !== "retired").map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Criticidade" obrigatorio>
              <select value={rascunho.criticidade} onChange={(e) => mudar("criticidade", e.target.value)} className={ENTRADA}>
                <option value="low">Baixa</option><option value="medium">Média</option>
                <option value="high">Alta</option><option value="critical">Crítica</option>
              </select>
            </Campo>
            <Campo rotulo="Resumo" obrigatorio ajuda="10 a 800 caracteres. O que este ativo é, e o que ainda não foi conferido.">
              <textarea required value={rascunho.resumo} onChange={(e) => mudar("resumo", e.target.value)} className={AREA} />
            </Campo>
            <Campo rotulo="Capacidades" obrigatorio ajuda="separadas por vírgula; pelo menos uma">
              <input required value={rascunho.capacidades} onChange={(e) => mudar("capacidades", e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="Próxima ação" obrigatorio ajuda="o ato concreto seguinte, não uma intenção genérica">
              <textarea required value={rascunho.proxima_acao} onChange={(e) => mudar("proxima_acao", e.target.value)} className={AREA} />
            </Campo>
            <Campo rotulo="Tags" ajuda="separadas por vírgula">
              <input value={rascunho.tags} onChange={(e) => mudar("tags", e.target.value)} className={ENTRADA} />
            </Campo>
          </>
        ) : null}

        {rascunho.passo === 3 ? (
          <>
            <Campo rotulo="Dono" obrigatorio>
              <input required value={rascunho.dono_nome} onChange={(e) => mudar("dono_nome", e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="Custódia" obrigatorio ajuda="declarada é o que alguém afirmou; comprovada é o que foi conferido">
              <select value={rascunho.dono_custodia} onChange={(e) => mudar("dono_custodia", e.target.value)} className={ENTRADA}>
                <option value="declared">Declarada</option>
                <option value="verified">Comprovada</option>
                <option value="unassigned">Sem dono definido</option>
              </select>
            </Campo>
          </>
        ) : null}

        {rascunho.passo === 4 ? (
          <>
            <Campo rotulo="Projeto">
              <input value={rascunho.projeto} onChange={(e) => mudar("projeto", e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="Vertical">
              <input value={rascunho.vertical} onChange={(e) => mudar("vertical", e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="ID de exibição" ajuda="já sanitizado. Nunca o ID cru quando ele for sensível.">
              <input value={rascunho.display_id} onChange={(e) => mudar("display_id", e.target.value)} className={ENTRADA} />
            </Campo>
            <Campo rotulo="Endereço público" ajuda="somente HTTP(S)">
              <input value={rascunho.url_publica} onChange={(e) => mudar("url_publica", e.target.value)} className={ENTRADA} placeholder="https://…" />
            </Campo>
          </>
        ) : null}

        {rascunho.passo === 5 ? (
          <PassoCredencial
            pecas={rascunho.credencial}
            aoMudar={(credencial) => mudar("credencial", credencial)}
          />
        ) : null}

        {rascunho.passo === 6 ? (
          <>
            <label className={cn("flex items-center gap-2 text-sm", HIT)}>
              <input type="checkbox" checked={rascunho.relacao.pular}
                onChange={(e) => mudar("relacao", { ...rascunho.relacao, pular: e.target.checked })} />
              Pular relações neste cadastro
            </label>
            {!rascunho.relacao.pular ? (
              <>
                <Campo rotulo="Tipo de relação" obrigatorio>
                  <select value={rascunho.relacao.tipo} onChange={(e) => mudar("relacao", { ...rascunho.relacao, tipo: e.target.value })} className={ENTRADA}>
                    <option value="belongs_to">pertence a</option>
                    <option value="managed_by">é gerido por</option>
                    <option value="publishes_to">publica em</option>
                    <option value="authenticates_through">autentica por</option>
                    <option value="spends_from">gasta de</option>
                    <option value="depends_on">depende de</option>
                    <option value="produces_for">produz para</option>
                  </select>
                </Campo>
                <Campo rotulo="Destino externo" obrigatorio ajuda="projeto, capacidade ou conceito que o Cofre não é dono. Ex.: cap:organic-content">
                  <input value={rascunho.relacao.destino} onChange={(e) => mudar("relacao", { ...rascunho.relacao, destino: e.target.value })} className={ENTRADA} />
                </Campo>
                <Campo rotulo="Rótulo">
                  <input value={rascunho.relacao.rotulo} onChange={(e) => mudar("relacao", { ...rascunho.relacao, rotulo: e.target.value })} className={ENTRADA} />
                </Campo>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">A relação fica incompleta até alguém declará-la no detalhe.</p>
            )}
          </>
        ) : null}

        {rascunho.passo === 7 ? (
          <dl className="space-y-2 text-sm">
            <div><dt className="text-muted-foreground">Tipo</dt><dd>{KIND_LABEL[rascunho.kind]} · {CLUSTER_LABEL[KIND_CLUSTER[rascunho.kind]]}</dd></div>
            <div><dt className="text-muted-foreground">Identidade</dt><dd>{rascunho.nome || "sem nome"} · {rascunho.ativo_id || "sem id"}</dd></div>
            <div><dt className="text-muted-foreground">Owner</dt><dd>{rascunho.dono_nome || "sem dono"} · {rascunho.dono_custodia}</dd></div>
            <div><dt className="text-muted-foreground">Destino</dt><dd>{rascunho.projeto || "projeto não informado"}</dd></div>
            <div>
              <dt className="text-muted-foreground">Credencial</dt>
              <dd className="text-pretty">{rascunho.credencial.pular ? "não cadastrar referência agora" : retratoDaReferencia(rascunho.credencial)}</dd>
            </div>
            <div><dt className="text-muted-foreground">Relações</dt><dd>{rascunho.relacao.pular ? "incompleta neste cadastro" : rascunho.relacao.rotulo || rascunho.relacao.destino}</dd></div>
            {sucessoIdempotente ? <p className="text-xs text-muted-foreground">Reenvio reconhecido. Nada novo foi gravado.</p> : null}
          </dl>
        ) : null}

        {!podeAvancar && rascunho.passo < 7 ? (
          <p role="alert" className="text-xs text-destructive">{mensagemDoPasso(rascunho)}</p>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
          <button type="button" className={SECUNDARIO} disabled={rascunho.passo === 1}
            onClick={() => mudar("passo", Math.max(1, rascunho.passo - 1))}>
            <ArrowLeft aria-hidden="true" className="h-4 w-4" /> Voltar
          </button>
          {rascunho.passo < 7 ? (
            <button type="submit" className={PRIMARIO} disabled={!podeAvancar}>
              Continuar <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </button>
          ) : (
            <button type="submit" className={PRIMARIO} disabled={enviar.isPending || !podeAvancar}>
              {enviar.isPending ? "Registrando…" : "Cadastrar ativo"}
            </button>
          )}
        </div>
        <ErroDoFormulario erro={enviar.error} />
      </form>
    </section>
  );
}

function PassoCredencial({
  pecas, aoMudar,
}: {
  pecas: Rascunho["credencial"];
  aoMudar: (valor: Rascunho["credencial"]) => void;
}) {
  const falha = pecas.pular ? null : diagnosticarReferencia(pecas);
  return (
    <>
      <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs leading-5 text-pretty">
        1Password contém o valor. O Cofre contém a referência. Conectado não significa credencial válida.
        Referência cadastrada não significa acesso provado. Não há botão que copie ou revele o segredo.
      </p>
      <label className={cn("flex items-center gap-2 text-sm", HIT)}>
        <input type="checkbox" checked={pecas.pular} onChange={(e) => aoMudar({ ...pecas, pular: e.target.checked })} />
        Cadastrar sem referência agora
      </label>
      {!pecas.pular ? (
        <>
          <Campo rotulo="Nome do cofre no 1Password" obrigatorio ajuda="o cofre, não a senha">
            <input value={pecas.cofre} onChange={(e) => aoMudar({ ...pecas, cofre: e.target.value })} className={ENTRADA} placeholder="VOLC" />
          </Campo>
          <Campo rotulo="Nome do item" obrigatorio>
            <input value={pecas.item} onChange={(e) => aoMudar({ ...pecas, item: e.target.value })} className={ENTRADA} placeholder="Pagina do piloto" />
          </Campo>
          <Campo rotulo="Campo" obrigatorio ajuda="use credential. MFA e password são recusados.">
            <input value={pecas.campo} onChange={(e) => aoMudar({ ...pecas, campo: e.target.value })} className={ENTRADA} placeholder="credential" />
          </Campo>
          <Campo rotulo="Nome lógico" obrigatorio ajuda="MAIÚSCULAS_COM_UNDERSCORE">
            <input required value={pecas.nome_logico} onChange={(e) => aoMudar({ ...pecas, nome_logico: e.target.value })} className={ENTRADA} placeholder="FB_PAGE_ADMIN" />
          </Campo>
          <Campo rotulo="Responsável" obrigatorio>
            <input required value={pecas.owner_nome} onChange={(e) => aoMudar({ ...pecas, owner_nome: e.target.value })} className={ENTRADA} />
          </Campo>
          <Campo rotulo="Finalidade" obrigatorio>
            <input required value={pecas.finalidade} onChange={(e) => aoMudar({ ...pecas, finalidade: e.target.value })} className={ENTRADA} />
          </Campo>
          <p className="text-xs text-muted-foreground text-pretty">{retratoDaReferencia(pecas)}</p>
          {falha ? <p role="alert" className="text-xs text-destructive">{fraseDaFalha(falha)}</p> : null}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">A referência fica pendente. Isso não é acesso provado nem credencial válida.</p>
      )}
    </>
  );
}

function validarPasso(r: Rascunho): boolean {
  switch (r.passo) {
    case 1: return Boolean(r.kind);
    case 2:
      return Boolean(r.ativo_id.trim() && r.nome.trim() && r.plataforma.trim() && r.resumo.trim().length >= 10 && r.capacidades.trim() && r.proxima_acao.trim());
    case 3: return Boolean(r.dono_nome.trim());
    case 4: return true;
    case 5:
      if (r.credencial.pular) return true;
      return !diagnosticarReferencia(r.credencial) && Boolean(r.credencial.nome_logico.trim() && r.credencial.owner_nome.trim() && r.credencial.finalidade.trim());
    case 6:
      if (r.relacao.pular) return true;
      return Boolean(r.relacao.destino.trim());
    case 7: return validarPasso({ ...r, passo: 2 }) && validarPasso({ ...r, passo: 3 });
    default: return false;
  }
}

function mensagemDoPasso(r: Rascunho): string {
  if (r.passo === 2 && r.resumo.trim().length > 0 && r.resumo.trim().length < 10) {
    return "O resumo precisa de pelo menos 10 caracteres.";
  }
  if (r.passo === 5 && !r.credencial.pular) {
    const falha = diagnosticarReferencia(r.credencial);
    return falha ? fraseDaFalha(falha) : "Nome lógico, responsável e finalidade são obrigatórios.";
  }
  return "Preencha os campos obrigatórios desta etapa para continuar.";
}
