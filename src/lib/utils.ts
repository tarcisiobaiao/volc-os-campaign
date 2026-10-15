import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

/**
 * O tailwind-merge não lê o `tailwind.config.ts`: um tamanho de fonte que ele
 * não conhece (`text-kpi-hero`) é classificado como COR de texto, e o
 * `text-foreground` seguinte o apaga em silêncio. A escala de dado V3
 * (design.md §V3) precisa ser declarada aqui para sobreviver ao `cn`.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["kpi-hero", "kpi", "metrica", "denso", "micro"] }],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
