import React, { useLayoutEffect, useRef } from "react";
import { animate, useReducedMotion } from "framer-motion";

import { AUSENTE, formatarNumero, type FormatoDeNumero } from "@/lib/instrumento";
import { CURVA, DURACAO } from "@/lib/movimento";
import { cn } from "@/lib/utils";

type Props = {
  valor: number | null;
  formato: FormatoDeNumero;
  className?: string;
};

/**
 * Número que chega com um tick curto (design.md §V3).
 *
 * ⚠️ O tick só acontece ENTRE DUAS OBSERVAÇÕES. Na primeira leitura o número
 * aparece pronto: contar a partir de zero desenharia por 640ms um zero que a
 * fonte nunca mediu. De `null` para valor também não anima, pelo mesmo motivo.
 *
 * O texto animado é `aria-hidden`; o leitor de tela recebe só o valor final,
 * sem `aria-live` — um tick anunciado viraria uma contagem falada.
 */
export function NumeroAnimado({ valor, formato, className }: Props) {
  const visivel = useRef<HTMLSpanElement>(null);
  const anterior = useRef<number | null>(null);
  const reduzir = useReducedMotion();
  const final = formatarNumero(valor, formato);

  useLayoutEffect(() => {
    const no = visivel.current;
    if (!no) return;
    const de = anterior.current;
    anterior.current = valor;

    if (valor == null || de == null || de === valor || reduzir) {
      no.textContent = final;
      return;
    }

    no.textContent = formatarNumero(de, formato);
    const controle = animate(de, valor, {
      duration: DURACAO.dado,
      ease: CURVA.dado,
      onUpdate: (v) => {
        no.textContent = formatarNumero(v, formato);
      },
      onComplete: () => {
        no.textContent = final;
      },
    });
    return () => controle.stop();
    // `formato` costuma ser literal recriado a cada render; o que importa é o texto final.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valor, final, reduzir]);

  return (
    <span className={cn("numero", className)}>
      <span ref={visivel} aria-hidden>
        {/* preenchido no layout effect, antes da pintura */}
      </span>
      <span className="sr-only">{final === AUSENTE ? "sem valor" : final}</span>
    </span>
  );
}
