import React, { useMemo, useState } from 'react';
import { Check, ChevronDown, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface CodeBlockProps {
  /** Conteúdo COMPLETO e final — o que o botão copiar entrega. Nunca placeholder. */
  code: string;
  title?: string;
  /** Etiqueta discreta à direita do título (ex.: "HTML personalizado"). */
  language?: string;
  /** Trechos a destacar: os valores que o wizard injetou. Ver `highlight` abaixo. */
  highlights?: string[];
  /** Acima disso o bloco nasce recolhido — código de tag passa de 200 linhas. */
  collapsedHeight?: number;
  className?: string;
}

/**
 * Bloco de código com cópia integral e destaque do que foi injetado.
 *
 * O destaque existe por um motivo prático: quem cola uma tag no GTM precisa
 * conferir num relance se o pixel e o domínio são os certos, sem ler 200 linhas.
 */
export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  title,
  language,
  highlights = [],
  collapsedHeight = 260,
  className,
}) => {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const lineCount = useMemo(() => code.split('\n').length, [code]);
  const isLong = lineCount > 14;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  // Quebra o código nos trechos destacados. Regex escapada porque os valores
  // vêm do usuário (domínio, pixel) e podem conter caracteres especiais.
  const parts = useMemo(() => {
    const terms = highlights.filter((t) => t && t.length > 2);
    if (!terms.length) return [{ text: code, hit: false }];

    const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const re = new RegExp(`(${escaped.join('|')})`, 'g');

    return code.split(re).map((text) => ({ text, hit: terms.includes(text) }));
  }, [code, highlights]);

  return (
    <div className={cn('rounded-lg border bg-muted/30 overflow-hidden', className)}>
      {(title || language) && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b bg-muted/50">
          <div className="flex items-center gap-2 min-w-0">
            {title && <span className="text-xs font-semibold truncate">{title}</span>}
            {language && (
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground shrink-0">
                {language}
              </span>
            )}
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={handleCopy}
            className="h-7 gap-1.5 text-xs shrink-0"
            aria-label={`Copiar ${title || 'código'}`}
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-600" /> Copiado
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" /> Copiar
              </>
            )}
          </Button>
        </div>
      )}

      <div className="relative">
        <pre
          className="overflow-x-auto p-3 text-[11px] leading-relaxed font-mono"
          style={!expanded && isLong ? { maxHeight: collapsedHeight } : undefined}
        >
          <code>
            {parts.map((p, i) =>
              p.hit ? (
                <mark
                  key={i}
                  className="rounded bg-primary/15 text-primary px-0.5 font-semibold"
                >
                  {p.text}
                </mark>
              ) : (
                <React.Fragment key={i}>{p.text}</React.Fragment>
              ),
            )}
          </code>
        </pre>

        {isLong && !expanded && (
          <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-background to-transparent pointer-events-none" />
        )}
      </div>

      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full border-t py-1.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors flex items-center justify-center gap-1"
        >
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
          {expanded ? 'Recolher' : `Ver as ${lineCount} linhas`}
        </button>
      )}
    </div>
  );
};
