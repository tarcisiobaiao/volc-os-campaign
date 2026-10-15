import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

/**
 * O tailwind-merge não lê o `tailwind.config.ts`: um tamanho de fonte que ele
 * não conhece (`text-kpi-hero`) é classificado como COR de texto, e o
 * `text-foreground` seguinte o apaga em silêncio. A escala de dado V3
 * (design.md §V3) precisa ser declarada aqui para sobreviver ao `cn`; os
 * utilitários V3 de altura, sombra, duração e curva, para deduplicar com os nativos.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["kpi-hero", "kpi", "metrica", "denso", "micro"] }],
      h: [{ h: ["linha-compacta", "linha", "linha-confortavel"] }],
      shadow: [{ shadow: ["instrumento"] }],
      duration: [{ duration: ["dado"] }],
      ease: [{ ease: ["dado", "enter", "move"] }],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
