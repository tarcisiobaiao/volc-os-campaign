import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Brain, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';

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
    <Card className="border-2 border-purple-200 dark:border-purple-800 bg-gradient-to-br from-purple-50 to-blue-50 dark:from-purple-950/20 dark:to-blue-950/20">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-purple-700 dark:text-purple-300">
          <div className="relative">
            <Brain className="h-6 w-6" />
            <Sparkles className="h-3 w-3 absolute -top-1 -right-1 text-yellow-500 animate-pulse" />
          </div>
          Insights de IA
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Resumo sempre visível */}
        <div className="space-y-3">
          <div className="bg-white/60 dark:bg-gray-900/40 rounded-lg p-4 border border-purple-100 dark:border-purple-800">
            <pre className="text-sm font-mono whitespace-pre-wrap text-gray-800 dark:text-gray-200 leading-relaxed">
              {orientacaoResumo || 'Sem resumo disponível'}
            </pre>
          </div>

          {orientacaoGeradoEm && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="opacity-60">🕐</span>
              <span>
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
              className="w-full gap-2 border-purple-200 hover:bg-purple-100 dark:border-purple-700 dark:hover:bg-purple-900/20"
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
          <div className="bg-white/80 dark:bg-gray-900/60 rounded-lg p-6 border border-purple-100 dark:border-purple-800 prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Customizar renderização de elementos markdown
                h1: ({ children }) => (
                  <h1 className="text-2xl font-bold text-purple-700 dark:text-purple-300 mb-4 pb-2 border-b border-purple-200 dark:border-purple-700">
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2 className="text-xl font-semibold text-purple-600 dark:text-purple-400 mt-6 mb-3">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-lg font-medium text-gray-800 dark:text-gray-200 mt-4 mb-2">
                    {children}
                  </h3>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-purple-400 pl-4 italic text-gray-600 dark:text-gray-400 my-4">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-4">
                    <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-600">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-gray-300 dark:border-gray-600 bg-purple-100 dark:bg-purple-900/30 px-4 py-2 text-left font-semibold text-gray-800 dark:text-gray-200">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-gray-300 dark:border-gray-600 px-4 py-2 text-gray-700 dark:text-gray-300">
                    {children}
                  </td>
                ),
                hr: () => (
                  <hr className="my-6 border-t-2 border-purple-200 dark:border-purple-700" />
                ),
                code: ({ children }) => (
                  <code className="bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200 px-1.5 py-0.5 rounded text-sm font-mono">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg overflow-x-auto my-4">
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
