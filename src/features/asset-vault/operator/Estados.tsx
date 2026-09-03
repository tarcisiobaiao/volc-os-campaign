import * as React from "react";
import { CircleAlert, CircleDashed, KeyRound, Loader2, LockKeyhole, PlugZap, Vault } from "lucide-react";
import { cn } from "@/lib/utils";
import { PRIMARIO, SECUNDARIO } from "./chrome";

export function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1400px] overflow-x-clip px-4 py-6 sm:px-6 sm:py-8">
      {children}
    </div>
  );
}

export function Carregando() {
  return (
    <div className="space-y-4" role="status" aria-label="Carregando o inventário">
      <div className="h-24 animate-pulse rounded-lg bg-muted/60" />
      <div className="h-48 animate-pulse rounded-lg bg-muted/40" />
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        Apurando o inventário persistido.
      </div>
    </div>
  );
}

export function Aviso({
  titulo, texto, tom = "neutro", icone: Icon, acao, codigo,
}: {
  titulo: string;
  texto: string;
  tom?: "neutro" | "atencao" | "erro";
  icone: typeof CircleAlert;
  acao?: { rotulo: string; aoClicar: () => void };
  codigo?: string;
}) {
  const borda =
    tom === "erro" ? "border-destructive/35" :
    tom === "atencao" ? "border-warning/35" :
    "border-border";
  return (
    <section className={cn("min-w-0 rounded-lg border bg-card px-4 py-10 text-center sm:px-5", borda)} role="alert">
      <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-muted">
        <Icon aria-hidden="true" className="h-5 w-5" />
      </span>
      <h2 className="mt-4 font-display text-lg font-semibold text-balance">{titulo}</h2>
      <p className="mx-auto mt-2 max-w-lg min-w-0 break-words text-sm leading-6 text-muted-foreground text-pretty">{texto}</p>
      {codigo ? <p className="mt-2 font-mono text-[11px] text-muted-foreground">{codigo}</p> : null}
      {acao ? (
        <button type="button" onClick={acao.aoClicar} className={cn("mt-4", PRIMARIO)}>
          {acao.rotulo}
        </button>
      ) : null}
    </section>
  );
}

export function EstadoNaoConfigurado() {
  return (
    <Aviso
      icone={PlugZap}
      tom="atencao"
      titulo="O Cofre não está configurado neste ambiente"
      texto="A variável VITE_PAUTADOR_API_URL não foi definida, então esta tela não sabe com qual backend falar. Isso é configuração de ambiente, não falta de dado — o inventário pode existir e estar inacessível daqui."
    />
  );
}

export function EstadoSemSessao(codigo?: string) {
  return (
    <Aviso
      icone={KeyRound}
      tom="atencao"
      titulo="Sua sessão expirou"
      texto="Entre novamente para abrir o Cofre."
      codigo={codigo}
    />
  );
}

export function EstadoSemPermissao(codigo?: string) {
  return (
    <Aviso
      icone={LockKeyhole}
      tom="atencao"
      titulo="Acesso restrito"
      texto="O inventário de ativos e postura de acesso é exclusivo para administradores. Sua identidade é válida; o papel é que não permite."
      codigo={codigo}
    />
  );
}

export function EstadoIndisponivel(mensagem: string, codigo: string | undefined, aoTentar: () => void) {
  return (
    <Aviso
      icone={CircleAlert}
      tom="erro"
      titulo="O Cofre não respondeu"
      texto={`${mensagem} Nada foi alterado, e esta tela não mostra um inventário vazio no lugar — vazio e indisponível são fatos diferentes.`}
      codigo={codigo}
      acao={{ rotulo: "Tentar de novo", aoClicar: aoTentar }}
    />
  );
}

export function EstadoFalha(mensagem: string, codigo: string | undefined, aoTentar: () => void) {
  return (
    <Aviso
      icone={CircleAlert}
      tom="erro"
      titulo="Não consegui abrir o Cofre"
      texto={mensagem}
      codigo={codigo}
      acao={{ rotulo: "Tentar de novo", aoClicar: aoTentar }}
    />
  );
}

export function EstadoVazio({ aoCadastrar }: { aoCadastrar: () => void }) {
  return (
    <div className="py-14 text-center">
      <Vault aria-hidden="true" className="mx-auto h-6 w-6 text-muted-foreground" />
      <p className="mt-3 text-sm font-medium">O Cofre está vazio</p>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground text-pretty">
        As sete gavetas existem e estão vazias. Comece pelo ativo mais crítico da operação
        e registre dono, evidência e próxima ação.
      </p>
      <button type="button" onClick={aoCadastrar} className={cn("mt-4", PRIMARIO)}>
        Cadastrar o primeiro ativo
      </button>
    </div>
  );
}

export function EstadoSemCorrespondencia() {
  return (
    <div className="py-14 text-center">
      <CircleDashed aria-hidden="true" className="mx-auto h-6 w-6 text-muted-foreground" />
      <p className="mt-3 text-sm font-medium">Nenhum ativo neste recorte</p>
      <p className="mt-1 text-xs text-muted-foreground">Ajuste a busca ou os filtros. O inventário não foi alterado.</p>
    </div>
  );
}

export function ErroDoFormulario({ erro }: { erro: unknown }) {
  if (!erro) return null;
  const conflito = typeof erro === "object" && erro !== null && "status" in erro && (erro as { status: number }).status === 409;
  const mensagem = erro instanceof Error ? erro.message : "Falha desconhecida.";
  return (
    <p role="alert" className="mt-3 rounded-md border border-destructive/35 bg-destructive/10 px-3 py-2 text-xs text-destructive">
      {conflito
        ? `Conflito de estado ou de chave de idempotência. ${mensagem}`
        : mensagem}
    </p>
  );
}

export { CircleAlert, CircleDashed, KeyRound, LockKeyhole, PlugZap, Vault };
