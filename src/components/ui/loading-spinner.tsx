import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  text?: string;
}

/**
 * O indicador de "estou trabalhando".
 *
 * Duas mudanças, ambas sobre a mesma tensão: movimento reduzido não pode virar
 * tela travada.
 *
 * 1. `data-motion="essencial"` no giro. O bloco global de
 *    `prefers-reduced-motion` no `index.css` desliga movimento em tudo, e é
 *    isso mesmo que ele deve fazer — mas um spinner PARADO deixa de comunicar
 *    "aguarde" e passa a comunicar "quebrou". Aqui a rotação É a informação, e
 *    ela é a única exceção que o produto abre.
 *
 * 2. `animate-pulse` saiu do texto. Piscar o rótulo não acrescenta nada que o
 *    giro ao lado já não diga, e o `design.md` é explícito sobre não pulsar
 *    fora do necessário. O texto agora só está lá para ser lido.
 *
 * O `role="status"` e o `aria-live` polido fazem o leitor de tela anunciar o
 * carregamento sem roubar o foco de quem estava digitando.
 */
export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = "md",
  className,
  text
}) => {
  const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-6 w-6",
    lg: "h-8 w-8"
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex flex-col items-center justify-center gap-2", className)}
    >
      <Loader2
        data-motion="essencial"
        aria-hidden="true"
        className={cn("animate-spin text-primary", sizeClasses[size])}
      />
      {text ? (
        <p className="text-sm text-muted-foreground">{text}</p>
      ) : (
        <span className="sr-only">Carregando</span>
      )}
    </div>
  );
};
