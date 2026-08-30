import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Settings2, ChevronDown, ChevronUp, CheckCircle2 } from 'lucide-react';

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
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="rounded-md bg-success/10 text-success p-1.5"><Settings2 className="h-4 w-4" /></span>
          Auto Adjust Realizado
          <CheckCircle2 className="h-5 w-5 text-success ml-auto" />
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Resumo sempre visível */}
        <div className="space-y-3">
          <div className="rounded-lg border border-border bg-muted/40 p-4">
            <pre className="text-sm font-mono whitespace-pre-wrap text-foreground leading-relaxed">
              {otimizacaoResumo || 'Ajuste automático realizado com sucesso'}
            </pre>
          </div>

          {otimizacaoRealizadaEm && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-success" />
              <span className="tabular">
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
                  Ver detalhes do ajuste
                </>
              )}
            </Button>
          )}
        </div>

        {/* Detalhes do ajuste (expandível) */}
        {expanded && jsonDetails && (
          <div className="rounded-lg border border-border bg-card p-6">
            <div className="space-y-3">
              {/* Se houver campos específicos no JSON, mostrar de forma estruturada */}
              {jsonDetails.acao && (
                <div className="flex items-center justify-between gap-2">
                  <span className="kicker">Ação</span>
                  <span className="text-sm font-medium text-foreground">{jsonDetails.acao}</span>
                </div>
              )}

              {jsonDetails.valor_anterior !== undefined && (
                <div className="flex items-center justify-between gap-2">
                  <span className="kicker">Valor anterior</span>
                  <span className="text-sm font-medium tabular text-foreground">
                    {typeof jsonDetails.valor_anterior === 'number'
                      ? `R$ ${jsonDetails.valor_anterior.toFixed(2)}`
                      : jsonDetails.valor_anterior}
                  </span>
                </div>
              )}

              {jsonDetails.valor_novo !== undefined && (
                <div className="flex items-center justify-between gap-2">
                  <span className="kicker">Valor novo</span>
                  <span className="text-sm font-medium tabular text-foreground">
                    {typeof jsonDetails.valor_novo === 'number'
                      ? `R$ ${jsonDetails.valor_novo.toFixed(2)}`
                      : jsonDetails.valor_novo}
                  </span>
                </div>
              )}

              {jsonDetails.variacao_percent !== undefined && (
                <div className="flex items-center justify-between gap-2">
                  <span className="kicker">Variação</span>
                  <span className={`text-sm font-semibold tabular ${jsonDetails.variacao_percent >= 0 ? 'text-success' : 'text-destructive'}`}>
                    {jsonDetails.variacao_percent >= 0 ? '+' : ''}{jsonDetails.variacao_percent.toFixed(2)}%
                  </span>
                </div>
              )}

              {jsonDetails.motivo && (
                <div className="mt-4 pt-4 border-t border-border">
                  <span className="kicker block mb-2">Motivo</span>
                  <p className="text-sm text-muted-foreground">{jsonDetails.motivo}</p>
                </div>
              )}

              {/* Fallback: mostrar JSON formatado se não houver campos conhecidos */}
              {!jsonDetails.acao && !jsonDetails.valor_anterior && !jsonDetails.motivo && (
                <pre className="text-xs font-mono bg-muted p-4 rounded-lg overflow-x-auto">
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
