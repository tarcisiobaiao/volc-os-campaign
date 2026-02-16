import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Settings2, ChevronDown, ChevronUp, CheckCircle2, Zap } from 'lucide-react';

interface OtimizacaoBoxProps {
  otimizacaoResumo: string | null;
  otimizacaoJson: any | null;
  otimizacaoRealizadaEm: string | null;
}

export function OtimizacaoBox({
  otimizacaoResumo,
  otimizacaoJson,
  otimizacaoRealizadaEm
}: OtimizacaoBoxProps) {
  const [expanded, setExpanded] = useState(false);

  // Se não tem otimização, não renderiza nada
  if (!otimizacaoResumo && !otimizacaoJson) {
    return null;
  }

  // Extrair informações do JSON se existir
  const jsonDetails = otimizacaoJson ? (
    typeof otimizacaoJson === 'string' ? JSON.parse(otimizacaoJson) : otimizacaoJson
  ) : null;

  return (
    <Card className="border-2 border-emerald-200 dark:border-emerald-800 bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-950/20 dark:to-teal-950/20">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
          <div className="relative">
            <Settings2 className="h-6 w-6" />
            <Zap className="h-3 w-3 absolute -top-1 -right-1 text-yellow-500 animate-pulse" />
          </div>
          Auto Adjust Realizado
          <CheckCircle2 className="h-5 w-5 text-emerald-500 ml-auto" />
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Resumo sempre visível */}
        <div className="space-y-3">
          <div className="bg-white/60 dark:bg-gray-900/40 rounded-lg p-4 border border-emerald-100 dark:border-emerald-800">
            <pre className="text-sm font-mono whitespace-pre-wrap text-gray-800 dark:text-gray-200 leading-relaxed">
              {otimizacaoResumo || 'Ajuste automático realizado com sucesso'}
            </pre>
          </div>

          {otimizacaoRealizadaEm && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="opacity-60">✅</span>
              <span>
                Ajuste realizado em: {new Date(otimizacaoRealizadaEm).toLocaleString('pt-BR', {
                  day: '2-digit',
                  month: '2-digit',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </span>
            </div>
          )}

          {jsonDetails && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded(!expanded)}
              className="w-full gap-2 border-emerald-200 hover:bg-emerald-100 dark:border-emerald-700 dark:hover:bg-emerald-900/20"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-4 w-4" />
                  Ver menos
                </>
              ) : (
                <>
                  <ChevronDown className="h-4 w-4" />
                  Ver detalhes do ajuste
                </>
              )}
            </Button>
          )}
        </div>

        {/* Detalhes do ajuste (expandível) */}
        {expanded && jsonDetails && (
          <div className="bg-white/80 dark:bg-gray-900/60 rounded-lg p-6 border border-emerald-100 dark:border-emerald-800">
            <div className="space-y-4">
              {/* Se houver campos específicos no JSON, mostrar de forma estruturada */}
              {jsonDetails.acao && (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-emerald-700 dark:text-emerald-300">Ação:</span>
                  <span className="text-gray-700 dark:text-gray-300">{jsonDetails.acao}</span>
                </div>
              )}

              {jsonDetails.valor_anterior !== undefined && (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-emerald-700 dark:text-emerald-300">Valor Anterior:</span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {typeof jsonDetails.valor_anterior === 'number'
                      ? `R$ ${jsonDetails.valor_anterior.toFixed(2)}`
                      : jsonDetails.valor_anterior}
                  </span>
                </div>
              )}

              {jsonDetails.valor_novo !== undefined && (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-emerald-700 dark:text-emerald-300">Valor Novo:</span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {typeof jsonDetails.valor_novo === 'number'
                      ? `R$ ${jsonDetails.valor_novo.toFixed(2)}`
                      : jsonDetails.valor_novo}
                  </span>
                </div>
              )}

              {jsonDetails.variacao_percent !== undefined && (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-emerald-700 dark:text-emerald-300">Variação:</span>
                  <span className={`font-semibold ${jsonDetails.variacao_percent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {jsonDetails.variacao_percent >= 0 ? '+' : ''}{jsonDetails.variacao_percent.toFixed(2)}%
                  </span>
                </div>
              )}

              {jsonDetails.motivo && (
                <div className="mt-4 pt-4 border-t border-emerald-200 dark:border-emerald-700">
                  <span className="font-medium text-emerald-700 dark:text-emerald-300 block mb-2">Motivo:</span>
                  <p className="text-gray-700 dark:text-gray-300 text-sm">{jsonDetails.motivo}</p>
                </div>
              )}

              {/* Fallback: mostrar JSON formatado se não houver campos conhecidos */}
              {!jsonDetails.acao && !jsonDetails.valor_anterior && !jsonDetails.motivo && (
                <pre className="text-xs font-mono bg-gray-100 dark:bg-gray-800 p-4 rounded-lg overflow-x-auto">
                  {JSON.stringify(jsonDetails, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
