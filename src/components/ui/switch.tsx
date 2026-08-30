import * as React from "react"
import * as SwitchPrimitives from "@radix-ui/react-switch"

import { cn } from "@/lib/utils"

/**
 * ⚠️ CORRIGIDO APÓS REVISÃO ADVERSARIAL.
 *
 * O estado desligado usava `bg-input`. Quando `--input` foi escurecido de 86%
 * para 57% — para a borda de campo alcançar o piso de 3:1 da WCAG 1.4.11 —, o
 * switch pegou carona numa mudança que não era sobre ele: a distinção entre
 * ligado e desligado caiu de 6,08:1 para 2,53:1. Desligado passou a ler como
 * "preenchido", igual ao ligado.
 *
 * Um token servia a dois papéis com requisitos opostos: a borda precisa ser
 * ESCURA para se destacar do campo claro; o trilho desligado precisa ser CLARO
 * para se distinguir do trilho ligado. `--switch-off` separa os dois.
 */
const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      "peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-switch-off",
      className
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        "pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0"
      )}
    />
  </SwitchPrimitives.Root>
))
Switch.displayName = SwitchPrimitives.Root.displayName

export { Switch }
