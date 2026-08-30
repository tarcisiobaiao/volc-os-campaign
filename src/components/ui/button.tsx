import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-[background-color,border-color,box-shadow,transform,color] duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70 focus-visible:ring-offset-2 active:scale-[0.96] motion-reduce:transition-none motion-reduce:active:scale-100 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-input bg-background/60 hover:bg-accent hover:text-accent-foreground hover:border-primary/40",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/70",
        ghost: "hover:bg-accent/60 hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline active:scale-100",
        /*
         * A variante de identidade. Só três consumidores, todos superfícies
         * sem workspace: `/login`, `/change-password` e o 404.
         *
         * Ela usava `bg-gradient-aurora`, a assinatura COMPLETA. Medido,
         * branco sobre os stops: aurora-blue 1,77:1 e aurora-orange 3,55:1
         * reprovam a AA. Como o gradiente varre os quatro, a palavra "Entrar"
         * ficava ilegível na faixa clara — na ação primária de uma tela em que
         * não existe alternativa.
         *
         * `gradient-aurora-action` é a metade profunda da mesma aurora
         * (deep → purple): mesmo eixo, mesma leitura de marca, e o pior ponto
         * dá 5,96:1.
         */
        aurora:
          "bg-gradient-aurora-action bg-[length:180%_180%] text-white shadow-card hover:bg-[position:100%_50%] hover:shadow-glow transition-[background-position,box-shadow,transform]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
