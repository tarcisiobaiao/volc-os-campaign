import React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { AUSENTE, ausente, type FormatoDeNumero, type LimitesDeFrescor, type Sentido } from "@/lib/instrumento";
import { cn } from "@/lib/utils";

import { Delta } from "./Delta";
import { Frescor } from "./Frescor";
import { NumeroAnimado } from "./NumeroAnimado";
import { Sparkline } from "./Sparkline";
import { VerdadeDoDado, type Verdade } from "./VerdadeDoDado";

export type TamanhoDeMetrica = "hero" | "faixa" | "compacta";

type Props = {
  rotulo: string;
  valor: number | null;
  formato: FormatoDeNumero;
  /** Estado de verdade do número (PRODUCT.md §4). Obrigatório: não há padrão "real". */
  verdade: Verdade;
  /** Frase curta que acompanha a verdade para leitor de tela ou o selo. */
  detalheDaVerdade?: string;
  lidoEm?: string | Date | null;
  limitesDeFrescor?: LimitesDeFrescor;
  fonte?: string;
  /** Injetável para teste e bancada. */
  agora?: Date;
  delta?: { base: number | null; sentido: Sentido; rotuloBase?: string };
  serie?: { valores: ReadonlyArray<number | null>; rotulo: string; indice?: number };
  tamanho?: TamanhoDeMetrica;
  carregando?: boolean;
  className?: string;
};

const TAMANHO: Record<TamanhoDeMetrica, string> = {
  hero: "text-kpi-hero",
  faixa: "text-kpi",
  compacta: "text-metrica",
};

/** Estados em que o número não pode ser mostrado como número. */
const SEM_NUMERO: ReadonlySet<Verdade> = new Set(["bloqueado", "indisponivel", "erro", "desconhecido"]);

/**
 * Uma métrica com tudo o que a torna operacional: rótulo, valor, verdade,
 * frescor e, se houver base, variação e tendência.
 *
 * As leis que ela impõe, para que nenhuma tela precise lembrar:
 *  - `valor: null` ou não-finito vira "—", nunca 0 nem ∞, e a verdade cai para "desconhecido";
 *  - `verdade: "zero"` só vale com valor 0 medido;
 *  - erro, bloqueio, indisponível e desconhecido escondem o número (o último
 *    bom valor, se existir, é responsabilidade da tela, datado);
 *  - demo sempre leva o selo, inclusive no tamanho compacto;
 *  - sem `delta.sentido`, a variação não tem cor.
 */
export function Metrica({
  rotulo,
  valor,
  formato,
  verdade,
  detalheDaVerdade,
  lidoEm,
  limitesDeFrescor,
  fonte,
  agora,
  delta,
  serie,
  tamanho = "faixa",
  carregando = false,
  className,
}: Props) {
  // Não-finito (ROAS de custo zero, divisão por nada) é ausência, não "∞".
  const semValor = ausente(valor);
  const efetiva: Verdade =
    semValor && !SEM_NUMERO.has(verdade) ? "desconhecido" : verdade === "zero" && valor !== 0 ? "real" : verdade;
  const mostrarNumero = !SEM_NUMERO.has(efetiva) && !semValor;
  const mostrarSelo = efetiva !== "real";

  return (
    <div className={cn("min-w-0", className)} data-verdade={efetiva} aria-busy={carregando || undefined}>
      <p className="kicker truncate">{rotulo}</p>

      {carregando ? (
        <div className="mt-2 space-y-2" aria-label={`${rotulo}: lendo`}>
          <Skeleton className={cn(tamanho === "hero" ? "h-10 w-40" : tamanho === "faixa" ? "h-7 w-28" : "h-5 w-20")} />
          <Skeleton className="h-3 w-24" />
        </div>
      ) : (
        <>
          <div className="mt-1.5 flex flex-wrap items-end gap-x-3 gap-y-1">
            <span className={cn(TAMANHO[tamanho], "font-sans text-foreground", !mostrarNumero && "text-muted-foreground")}>
              {mostrarNumero ? <NumeroAnimado valor={valor} formato={formato} /> : <span aria-label="sem valor">{AUSENTE}</span>}
            </span>
            {serie && mostrarNumero && tamanho !== "compacta" ? (
              <Sparkline
                valores={serie.valores}
                rotulo={serie.rotulo}
                serie={serie.indice}
                largura={tamanho === "hero" ? 120 : 88}
                altura={tamanho === "hero" ? 36 : 26}
                className="mb-1.5"
              />
            ) : null}
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            {mostrarSelo ? <VerdadeDoDado verdade={efetiva} detalhe={detalheDaVerdade} /> : null}
            {delta && mostrarNumero ? (
              <Delta atual={valor} base={delta.base} sentido={delta.sentido} rotuloBase={delta.rotuloBase} />
            ) : null}
            {lidoEm !== undefined ? (
              <Frescor lidoEm={lidoEm} limites={limitesDeFrescor} agora={agora} fonte={fonte} />
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}
