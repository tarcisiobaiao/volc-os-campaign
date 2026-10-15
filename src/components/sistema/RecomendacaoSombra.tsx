import React from "react";

import { Button } from "@/components/ui/button";
import type { EstadoDeProposta } from "@/lib/instrumento";
import { cn } from "@/lib/utils";

import { SeloDeProposta } from "./SeloDeProposta";
import { VerdadeDoDado, type Verdade } from "./VerdadeDoDado";

export type DirecaoDaRecomendacao = "pausar" | "reduzir" | "manter" | "escalar" | "revisar";

const DIRECAO: Record<DirecaoDaRecomendacao, { glifo: string; palavra: string }> = {
  pausar: { glifo: "‖", palavra: "Pausar" },
  reduzir: { glifo: "▼", palavra: "Reduzir verba" },
  manter: { glifo: "=", palavra: "Manter" },
  escalar: { glifo: "▲", palavra: "Escalar verba" },
  revisar: { glifo: "?", palavra: "Revisar à mão" },
};

export type EvidenciaDaRecomendacao = {
  rotulo: string;
  /** Já formatado ("R$ 554,75", "0,07×"). Ausente → "—". */
  valor: string | null;
  /** "real" = medido na conta; "demo"/"parcial" etc. aparecem como selo. */
  verdade: Verdade;
  /** Valor projetado/estressado é hipótese: vem hachurado. */
  hipotese?: boolean;
};

type Props = {
  titulo: string;
  direcao: DirecaoDaRecomendacao;
  /** "Shadow ROAS v1 · janela madura de 16 dias" */
  motor: string;
  confianca?: "baixa" | "media" | "alta" | null;
  evidencias: EvidenciaDaRecomendacao[];
  /** O que aconteceria na conta se alguém executasse. */
  consequencia: string;
  estado?: EstadoDeProposta;
  /**
   * A única ação possível é levar à fila de propostas. Executar não existe
   * aqui (PRODUCT §12). Sem `acao`, o rodapé explica onde a decisão acontece.
   * `bloqueio` desabilita e diz o pré-requisito (PRODUCT §5).
   */
  acao?: { rotulo: string; onClick: () => void; bloqueio?: string };
  className?: string;
};

const CONFIANCA = { baixa: "Confiança baixa", media: "Confiança média", alta: "Confiança alta" } as const;

/**
 * Cartão de recomendação de motor em modo sombra (W7, W13, ORAKUL).
 *
 * Hachura = hipótese. O que foi medido aparece sólido; o projetado, hachurado.
 * O cartão nunca oferece "executar": o máximo é virar proposta.
 */
export function RecomendacaoSombra({
  titulo,
  direcao,
  motor,
  confianca,
  evidencias,
  consequencia,
  estado = "sombra",
  acao,
  className,
}: Props) {
  const d = DIRECAO[direcao];
  const id = React.useId();
  const bloqueioId = `${id}-bloqueio`;

  return (
    <article
      aria-labelledby={id}
      data-estado={estado}
      className={cn(
        "hachura-hipotese rounded-lg border border-dashed border-foreground/30 bg-card p-4 md:p-5",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="kicker">{motor}</p>
          <h3 id={id} className="mt-1 font-display text-lg font-semibold leading-tight text-foreground">
            <span aria-hidden className="mr-1.5 text-primary">
              {d.glifo}
            </span>
            {d.palavra}
            <span className="text-muted-foreground"> · </span>
            {titulo}
          </h3>
        </div>
        <SeloDeProposta estado={estado} />
      </header>

      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {evidencias.map((e) => (
          <div
            key={e.rotulo}
            className={cn(
              "flex items-baseline justify-between gap-3 rounded-md px-2 py-1.5",
              e.hipotese ? "border border-dashed border-border" : "bg-card",
            )}
          >
            <dt className="text-sm text-muted-foreground">
              {e.rotulo}
              {e.hipotese ? <span className="ml-1 text-micro">(projeção)</span> : null}
            </dt>
            <dd className="flex items-center gap-2">
              <span className="numero text-metrica text-foreground">{e.valor ?? "—"}</span>
              {e.verdade !== "real" ? <VerdadeDoDado verdade={e.verdade} /> : null}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 max-w-[70ch] text-sm text-foreground">
        <span className="font-semibold">Se executada: </span>
        {consequencia}
      </p>

      <footer className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-3">
        <p className="text-micro text-muted-foreground">
          {confianca ? `${CONFIANCA[confianca]} · ` : ""}Nada foi enviado à conta.
        </p>
        {acao ? (
          <div className="flex flex-col items-end gap-1">
            <Button
              type="button"
              variant="secondary"
              onClick={acao.onClick}
              disabled={Boolean(acao.bloqueio)}
              aria-describedby={acao.bloqueio ? bloqueioId : undefined}
            >
              {acao.rotulo}
            </Button>
            {acao.bloqueio ? (
              <p id={bloqueioId} className="text-micro text-muted-foreground">
                {acao.bloqueio}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-micro text-muted-foreground">A decisão acontece na fila de propostas.</p>
        )}
      </footer>
    </article>
  );
}
