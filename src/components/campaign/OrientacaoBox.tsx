import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Brain, ChevronDown, ChevronUp, Clock } from 'lucide-react';

interface OrientacaoBoxProps {
  orientacaoTexto: string | null;
  orientacaoResumo: string | null;
  orientacaoGeradoEm?: string | null;
}

export function OrientacaoBox({
  orientacaoTexto,
  orientacaoResumo,
  orientacaoGeradoEm
}: OrientacaoBoxProps) {
  const [expanded, setExpanded] = useState(false);

  // Se não tem orientação, não renderiza nada
  if (!orientacaoResumo && !orientacaoTexto) {
    return null;
  }

  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="rounded-md bg-primary/10 text-primary p-1.5"><Brain className="h-4 w-4" /></span>
          Insights de IA
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Resumo sempre visível */}
        <div className="space-y-3">
          <div className="rounded-lg border border-border bg-muted/40 p-4">
            <pre className="text-sm font-mono whitespace-pre-wrap text-foreground leading-relaxed">
              {orientacaoResumo || 'Sem resumo disponível'}
            </pre>
          </div>

          {orientacaoGeradoEm && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              <span className="tabular">
                Gerado em: {new Date(orientacaoGeradoEm).toLocaleString('pt-BR', {
                  day: '2-digit',
                  month: '2-digit',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </span>
            </div>
          )}

          {orientacaoTexto && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="w-full gap-2"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-4 w-4" />
                  Ver menos
                </>
              ) : (
                <>
                  <ChevronDown className="h-4 w-4" />
                  Ver análise completa
                </>
              )}
            </Button>
          )}
        </div>

        {/* Análise completa (expandível) */}
        {expanded && orientacaoTexto && (
          <div className="rounded-lg border border-border bg-card p-6 prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Customizar renderização de elementos markdown
                h1: ({ children }) => (
                  <h1 className="font-display text-2xl font-bold text-foreground mb-4 pb-2 border-b border-border">
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2 className="font-display text-xl font-semibold text-foreground mt-6 mb-3">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-lg font-medium text-foreground mt-4 mb-2">
                    {children}
                  </h3>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-primary/60 pl-4 italic text-muted-foreground my-4">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-4">
                    <table className="min-w-full border-collapse border border-border">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-border bg-muted/60 px-4 py-2 text-left kicker">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-border px-4 py-2 text-muted-foreground tabular">
                    {children}
                  </td>
                ),
                hr: () => (
                  <hr className="my-6 hairline-aurora" />
                ),
                code: ({ children }) => (
                  <code className="bg-muted text-primary px-1.5 py-0.5 rounded text-sm font-mono">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-muted p-4 rounded-lg overflow-x-auto my-4">
                    {children}
                  </pre>
                )
              }}
            >
              {orientacaoTexto}
            </ReactMarkdown>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
