import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CopyFieldProps {
  value: string;
  label?: string;
  hint?: string;
  className?: string;
}

/**
 * Valor único, pronto para colar num campo de outro painel (nome do Worker,
 * host do domínio…). Existe separado do CodeBlock porque aqui o alvo é um
 * `<input>` alheio: o que importa é o valor exato, sem espaço nem quebra.
 */
export const CopyField: React.FC<CopyFieldProps> = ({ value, label, hint, className }) => {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={cn('space-y-1', className)}>
      {label && <p className="text-[11px] font-medium text-muted-foreground">{label}</p>}
      <button
        type="button"
        onClick={copy}
        aria-label={`Copiar ${label || value}`}
        className="group w-full flex items-center justify-between gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-left transition-colors hover:bg-muted/70"
      >
        <code className="text-xs font-mono truncate">{value}</code>
        <span
          className={cn(
            'shrink-0 inline-flex items-center gap-1 text-[10px] font-medium',
            copied ? 'text-emerald-600' : 'text-muted-foreground group-hover:text-foreground',
          )}
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5" /> copiado
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" /> copiar
            </>
          )}
        </span>
      </button>
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
};
